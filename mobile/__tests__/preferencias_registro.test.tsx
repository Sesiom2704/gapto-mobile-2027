// ============================================================
// GAPTO MOBILE 2027
// Fichero: preferencias_registro.test.tsx
// Ruta: mobile/__tests__/preferencias_registro.test.tsx
// Descripción: Preferencias de registro en «Nuevo gasto» (F05-02 B2; F05-D026 §41.3/§41.4, E1/E2/E3; F05-D027 §42.7; lámina SET-PREF / REG-PREF v0.1 R01–R07, D-PREF-02..06). Propuesta por campo con origen visible; lo explícito gana (un campo tocado no se recalcula al cambiar de categoría); sin fallback laxo del cliente (AJ-B1-09) y nunca una cuenta fuera de la lista (AJ-B1-11); el reintento del registro no vuelve a pedir la propuesta. «Guardar como preferencia»: oculta con «Sin categoría» y cuando no hay nada que recordar; alta con el UUID de la tarjeta (el reintento usa el MISMO); edición con el ESTADO COMPLETO (E05); conflicto R07 «Sustituir / Mantener»; VERSION_DESFASADA y empate → recarga y se vuelve a preguntar; fallo R06 sin afectar al hecho.
// v0.2.0 (F05-02 B2-V): discriminante de M03 (E1 / REG-01): con la propuesta pendiente, fallida o rechazada, «¿Cuenta para el presupuesto?» no está preseleccionado y no se envía sin decisión explícita.
// v0.3.0 (F05-02 B3, AJ-B2-04): alta aditiva de la rama de D6 «tras VERSION_DESFASADA o un empate, al recargar ya no hay conflicto → se vuelve a la tarjeta», sin R07 y sin otra escritura.
// v0.4.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E3; decisión OPCIÓN A2 del STOP 2, tabla «tests adaptados»): toda preferencia lleva tipo. El doble devuelve `tipos` en la lista; las preferencias de «Una categoría» son de tipo GASTO y el alta y la edición de «Guardar como preferencia» esperan `tipo_hecho_id: TIPOS.GASTO` en lugar de null.
// v0.5.0 (F05-03/F05-04 J2+J3 §2.2/§2.7): navegación «Registrar» + hoja de tipos y nota opcional en «Más detalles» (corte de Concepto). Ningún oráculo de preferencias cambia.
// Versión: 0.5.0
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type {
  ClienteApi,
  ContenidoPreferencia,
  CuentaPago,
  ListaPreferencias,
  Preferencia,
  PropuestaRegistro,
  Respuesta,
  ResultadoComandoPreferencia,
  ResultadoRegistro,
} from '../src/api/cliente';
import { borradorInicial, type PayloadGastoPagado } from '../src/domain/intencion';
import { aplicarPropuesta, indexar, propuestaAplicable } from '../src/domain/preferencias';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

/** F05-04 §2.7 (corte de Concepto): la nota opcional se escribe en «Más detalles». */
function escribirNota(t: string) {
  if (!screen.queryByTestId('campo-nota')) fireEvent.press(screen.getByTestId('abrir-mas-detalles'));
  fireEvent.changeText(screen.getByTestId('campo-nota'), t);
}

const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
const EFECTIVO = 'c0000000-0000-4000-8000-00000000000b';
const COMUN = 'c0000000-0000-4000-8000-00000000000c';
const USD = 'c0000000-0000-4000-8000-00000000000d';
const AHORA = () => new Date(2026, 8, 24, 10, 0, 0);
const HOY = '2026-09-24';

const CATEGORIAS = [nodo({ id: 'super', nombre: 'Supermercado' }), nodo({ id: 'limpieza', nombre: 'Limpieza', orden: 1 })];

const cuenta = (cuenta_id: string, nombre: string, moneda = 'EUR'): CuentaPago => ({ cuenta_id, nombre, moneda, propuesta_financiacion: 'SELF_100' });
const TRES = [cuenta(TARJETA, 'Tarjeta BBVA'), cuenta(EFECTIVO, 'Efectivo'), cuenta(COMUN, 'Cuenta común')];

/** Ids de tipo que informa GET /v1/preferencias (E3). */
const TIPOS = { GASTO: 't-gasto', INGRESO: 't-ingreso' };

function pref(p: Partial<Preferencia> & { id: string }): Preferencia {
  return {
    tipo_hecho_id: TIPOS.GASTO, categoria_id: null, tercero_id: null, entidad_id: null, cuenta_default_id: null,
    presupuestable_default: null, prioridad: 100, enabled: true, row_version: 1, ...p,
  };
}

const GENERAL = pref({ id: 'p-general', presupuestable_default: true });
const SUPER_TARJETA = pref({ id: 'p-super', categoria_id: 'super', cuenta_default_id: TARJETA });

/** Propuesta del resolver: cuenta y presupuestable con el id de la preferencia (o DEFAULT_GENERAL). */
function prop(c: [string, string | null] | null, pr: [boolean, string] | null): PropuestaRegistro {
  return {
    cuenta: c ? { valor: c[0], origen: c[1] === null ? { capa: 'DEFAULT_GENERAL', preferencia_id: null } : { capa: 'PREFERENCIA', preferencia_id: c[1] } } : null,
    presupuestable: pr ? { valor: pr[0], origen: { capa: 'PREFERENCIA', preferencia_id: pr[1] } } : null,
  };
}

function ok(p: PayloadGastoPagado): Respuesta<ResultadoRegistro> {
  return { tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado } };
}

function okPref(c: ContenidoPreferencia & { id: string }, row_version = 1): Respuesta<ResultadoComandoPreferencia> {
  return { tipo: 'OK', datos: { preferencia: { ...c, enabled: true, row_version }, idempotente: false, modificadas: [c.id] } };
}

type Opciones = {
  cuentas?: CuentaPago[];
  propuesta?: (fecha: string, cat: string | null) => PropuestaRegistro;
  prefs?: () => Preferencia[];
  registrar?: (p: PayloadGastoPagado) => Promise<Respuesta<ResultadoRegistro>>;
  alta?: (c: ContenidoPreferencia & { id: string }) => Promise<Respuesta<ResultadoComandoPreferencia>>;
  editar?: (id: string, c: ContenidoPreferencia & { row_version: number }) => Promise<Respuesta<ResultadoComandoPreferencia>>;
};

function fake(o: Opciones = {}) {
  const enviados: PayloadGastoPagado[] = [];
  const consultas: [string, string | null][] = [];
  const cliente: ClienteApi = {
    ...clienteCategoriasStub(CATEGORIAS),
    registrarGastoPagado: jest.fn(async (p) => {
      enviados.push(p);
      return (o.registrar ?? (async (x) => ok(x)))(p);
    }),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: o.cuentas ?? TRES } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    propuestaPreferencias: jest.fn(async (fecha: string, cat: string | null) => {
      consultas.push([fecha, cat]);
      return { tipo: 'OK', datos: (o.propuesta ?? (() => prop(null, null)))(fecha, cat) } as Respuesta<PropuestaRegistro>;
    }),
    listarPreferencias: jest.fn(async () => ({ tipo: 'OK', datos: { preferencias: (o.prefs ?? (() => []))(), tipos: TIPOS } }) as Respuesta<ListaPreferencias>),
    altaPreferencia: jest.fn(async (c) => (o.alta ?? (async (x) => okPref(x)))(c)),
    editarPreferencia: jest.fn(async (id, c) => (o.editar ?? (async (_i, x) => okPref({ ...x, id }, x.row_version + 1)))(id, c)),
  };
  return { cliente, enviados, consultas };
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

async function abrir(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  fireEvent.press(await screen.findByTestId('accion-registrar'));
  fireEvent.press(screen.getByTestId('tipo-GASTO')); // F05-04 §2.2: «Registrar» → hoja de tipos
  await screen.findByTestId('registro-form');
  await waitFor(() => expect(cliente.propuestaPreferencias).toHaveBeenCalled());
}

function elegirCategoria(id: string) {
  fireEvent.press(screen.getByTestId('campo-categoria'));
  fireEvent.press(screen.getByTestId(`cat-${id}`));
}

function sinCategoria() {
  fireEvent.press(screen.getByTestId('campo-categoria'));
  fireEvent.press(screen.getByTestId('selector-sin-categoria'));
}

function basicos() {
  fireEvent.changeText(screen.getByTestId('campo-importe'), '42,18');
  escribirNota('Compra');
}

const seleccionada = (id: string) => screen.getByTestId(id).props.accessibilityState.checked;
const textoDe = (id: string) => screen.getByTestId(id).props.children;

/** Texto plano de un nodo con Text anidados. */
function plano(id: string): string {
  const partes: string[] = [];
  const visitar = (x: unknown): void => {
    if (typeof x === 'string' || typeof x === 'number') partes.push(String(x));
    else if (Array.isArray(x)) x.forEach(visitar);
    else if (x && typeof x === 'object' && 'props' in (x as object)) visitar((x as { props: { children: unknown } }).props.children);
  };
  visitar(screen.getByTestId(id).props.children);
  return partes.join('');
}

async function registrar() {
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
}

// ------------------------------------------------------------------ R01–R04: propuesta
test('R01: sin preferencia aplicable no hay preselección de cuenta ni de presupuesto (varias cuentas)', async () => {
  const f = fake();
  await abrir(f.cliente);
  await waitFor(() => expect(screen.getByTestId(`cuenta-${TARJETA}`)).toBeTruthy());
  for (const c of [TARJETA, EFECTIVO, COMUN]) expect(seleccionada(`cuenta-${c}`)).toBe(false);
  expect(screen.getByTestId('presupuestable-true').props.accessibilityState.selected).toBe(false);
  expect(screen.queryByTestId('origen-cuenta')).toBeNull();
  expect(screen.queryByTestId('origen-presupuestable')).toBeNull();
  // Con categoría pendiente se pide el contexto «Sin categoría» para la fecha del formulario.
  expect(f.consultas[0]).toEqual([HOY, null]);
});

test('R02: propuesta por campo con su origen visible; financiación sobre la cuenta propuesta; se sella tal cual', async () => {
  const f = fake({
    propuesta: (_f, cat) => (cat === 'super' ? prop([TARJETA, 'p-super'], [true, 'p-general']) : prop(null, [true, 'p-general'])),
    prefs: () => [GENERAL, SUPER_TARJETA],
  });
  await abrir(f.cliente);
  basicos();
  elegirCategoria('super');
  await waitFor(() => expect(seleccionada(`cuenta-${TARJETA}`)).toBe(true));
  expect(f.consultas.at(-1)).toEqual([HOY, 'super']);
  expect(textoDe('origen-cuenta')).toBe('Propuesta: tu preferencia para Supermercado.');
  expect(screen.getByTestId('presupuestable-true').props.accessibilityState.selected).toBe(true);
  expect(textoDe('origen-presupuestable')).toBe('Propuesta: tu preferencia general.');
  expect(textoDe('financiacion-texto')).toBe('Financiado por ti · cuenta 100 % tuya');
  // La propuesta no cuenta como modificación: «Cancelar» con solo la propuesta no la cuenta.
  expect(screen.getByTestId('registrar')).toBeEnabled();
  await registrar();
  expect(f.enviados[0]).toMatchObject({ cuenta_id: TARJETA, presupuestable: true, financiacion: { estado: 'PROPUESTA_ACEPTADA' } });
});

test('R03 lo explícito gana: la cuenta tocada no se recalcula al cambiar de categoría; el presupuesto sí', async () => {
  const f = fake({
    propuesta: (_f, cat) =>
      cat === 'super' ? prop([TARJETA, 'p-super'], [true, 'p-general']) : cat === 'limpieza' ? prop([COMUN, 'p-limpieza'], [false, 'p-limpieza']) : prop(null, null),
    prefs: () => [GENERAL, SUPER_TARJETA, pref({ id: 'p-limpieza', categoria_id: 'limpieza', cuenta_default_id: COMUN, presupuestable_default: false })],
  });
  await abrir(f.cliente);
  basicos();
  elegirCategoria('super');
  await waitFor(() => expect(seleccionada(`cuenta-${TARJETA}`)).toBe(true));
  fireEvent.press(screen.getByTestId(`cuenta-${EFECTIVO}`));
  expect(textoDe('origen-cuenta')).toBe('Elegida por ti.');
  elegirCategoria('limpieza');
  await waitFor(() => expect(f.consultas.at(-1)).toEqual([HOY, 'limpieza']));
  await waitFor(() => expect(textoDe('origen-presupuestable')).toBe('Propuesta: tu preferencia para Limpieza.'));
  expect(screen.getByTestId('presupuestable-false').props.accessibilityState.selected).toBe(true);
  expect(seleccionada(`cuenta-${EFECTIVO}`)).toBe(true); // no se pisa
  expect(seleccionada(`cuenta-${COMUN}`)).toBe(false);
  expect(textoDe('origen-cuenta')).toBe('Elegida por ti.');
  // El presupuesto tocado tampoco se recalcula.
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  expect(textoDe('origen-presupuestable')).toBe('Elegida por ti.');
  elegirCategoria('super');
  await waitFor(() => expect(f.consultas.at(-1)).toEqual([HOY, 'super']));
  await act(async () => {});
  expect(screen.getByTestId('presupuestable-true').props.accessibilityState.selected).toBe(true);
  expect(textoDe('origen-presupuestable')).toBe('Elegida por ti.');
  expect(seleccionada(`cuenta-${EFECTIVO}`)).toBe(true);
  await registrar();
  expect(f.enviados[0]).toMatchObject({ cuenta_id: EFECTIVO, presupuestable: true });
});

test('R04 / sin propuesta tras una propuesta previa: los campos no tocados vuelven a «sin preselección»', async () => {
  const f = fake({
    propuesta: (_f, cat) => (cat === 'super' ? prop([TARJETA, 'p-super'], [true, 'p-super2']) : prop(null, null)),
    prefs: () => [SUPER_TARJETA, pref({ id: 'p-super2', categoria_id: 'super', presupuestable_default: true })],
  });
  await abrir(f.cliente);
  elegirCategoria('super');
  await waitFor(() => expect(seleccionada(`cuenta-${TARJETA}`)).toBe(true));
  elegirCategoria('limpieza'); // su preferencia apunta a una cuenta no elegible: el resolver no propone nada
  await waitFor(() => expect(seleccionada(`cuenta-${TARJETA}`)).toBe(false));
  expect(screen.getByTestId('presupuestable-true').props.accessibilityState.selected).toBe(false);
  expect(screen.queryByTestId('origen-cuenta')).toBeNull();
  expect(screen.queryByTestId('origen-presupuestable')).toBeNull();
});

// E1 / REG-01 (discriminante de M03): el valor inicial del borrador es lo que se ve mientras la
// propuesta no ha llegado; si la petición falla, aplicarPropuesta(SIN_PROPUESTA) lo deja pendiente.
const PROPUESTA_SIN_EXITO: [string, () => Promise<Respuesta<PropuestaRegistro>>][] = [
  ['pendiente (aún no ha llegado)', () => new Promise<Respuesta<PropuestaRegistro>>(() => {})],
  ['fallida (INDETERMINADO)', async () => ({ tipo: 'INDETERMINADO', mensaje: 'x' })],
  ['rechazada (CATEGORIA_NO_ELEGIBLE)', async () => ({ tipo: 'RECHAZADO', codigo: 'CATEGORIA_NO_ELEGIBLE', mensaje: '' })],
];

test.each(PROPUESTA_SIN_EXITO)('E1: propuesta %s → presupuestable sin preselección y sin envío hasta decidir', async (_caso, respuesta) => {
  const f = fake();
  f.cliente.propuestaPreferencias = jest.fn(respuesta);
  await abrir(f.cliente);
  await waitFor(() => expect(screen.getByTestId(`cuenta-${TARJETA}`)).toBeTruthy());
  await act(async () => {});
  const marcado = (v: boolean) => screen.getByTestId(`presupuestable-${v}`).props.accessibilityState.selected;
  expect(marcado(true)).toBe(false);
  expect(marcado(false)).toBe(false);
  expect(screen.queryByTestId('origen-presupuestable')).toBeNull();
  basicos();
  sinCategoria(); // vuelve a pedir la propuesta, con el mismo resultado
  fireEvent.press(screen.getByTestId(`cuenta-${EFECTIVO}`));
  await act(async () => {});
  expect(marcado(true)).toBe(false);
  expect(marcado(false)).toBe(false);
  expect(textoDe('faltan')).toBe('Para registrar falta: si cuenta para el presupuesto.');
  expect(screen.getByTestId('registrar')).toBeDisabled();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  expect(f.cliente.registrarGastoPagado).not.toHaveBeenCalled();
  // Con la decisión explícita ya se puede registrar, y se sella lo elegido.
  fireEvent.press(screen.getByTestId('presupuestable-false'));
  expect(screen.getByTestId('registrar')).toBeEnabled();
  await registrar();
  expect(f.enviados[0]).toMatchObject({ cuenta_id: EFECTIVO, presupuestable: false });
});

test('sin fallback laxo (AJ-B1-09): una única cuenta en otra moneda y sin propuesta del resolver no se preselecciona', async () => {
  const f = fake({ cuentas: [cuenta(USD, 'Cuenta USD', 'USD')] });
  await abrir(f.cliente);
  await waitFor(() => expect(screen.getByTestId(`cuenta-${USD}`)).toBeTruthy());
  await act(async () => {});
  expect(seleccionada(`cuenta-${USD}`)).toBe(false);
  expect(screen.queryByTestId('origen-cuenta')).toBeNull();
  basicos();
  sinCategoria();
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  expect(textoDe('faltan')).toBe('Para registrar falta: cuenta de pago.');
});

test('única cuenta EUR propuesta por el resolver (DEFAULT_GENERAL): «Propuesta: es tu única cuenta disponible.»', async () => {
  const f = fake({ cuentas: [cuenta(TARJETA, 'Tarjeta BBVA')], propuesta: () => prop([TARJETA, null], null) });
  await abrir(f.cliente);
  await waitFor(() => expect(seleccionada(`cuenta-${TARJETA}`)).toBe(true));
  expect(textoDe('origen-cuenta')).toBe('Propuesta: es tu única cuenta disponible.');
});

test('AJ-B1-11: nunca se preselecciona una cuenta que no esté en la lista de elegibles', async () => {
  const f = fake({ cuentas: [cuenta(EFECTIVO, 'Efectivo'), cuenta(COMUN, 'Cuenta común')], propuesta: () => prop([TARJETA, 'p-general'], null), prefs: () => [pref({ id: 'p-general', cuenta_default_id: TARJETA })] });
  await abrir(f.cliente);
  await waitFor(() => expect(f.cliente.propuestaPreferencias).toHaveBeenCalled());
  await act(async () => {});
  expect(seleccionada(`cuenta-${EFECTIVO}`)).toBe(false);
  expect(seleccionada(`cuenta-${COMUN}`)).toBe(false);
  expect(screen.queryByTestId('origen-cuenta')).toBeNull();
  basicos();
  sinCategoria();
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  expect(textoDe('faltan')).toBe('Para registrar falta: cuenta de pago.');
});

test('AJ-B1-11 (dominio): la propuesta de una cuenta fuera de la lista no llega al borrador ni como valor oculto', () => {
  const lista = [cuenta(EFECTIVO, 'Efectivo'), cuenta(COMUN, 'Cuenta común')];
  const indice = indexar([pref({ id: 'p-general', cuenta_default_id: TARJETA })]);
  const ap = propuestaAplicable(prop([TARJETA, 'p-general'], null), indice, lista);
  expect(ap.cuenta).toBeNull();
  const b = aplicarPropuesta(borradorInicial(HOY), ap, lista);
  expect(b.cuentaId).toBeNull();
  expect(b.cuentaOrigen).toBe('PENDIENTE');
  // Discriminante inverso: la misma propuesta con la cuenta en la lista sí se aplica.
  const conTarjeta = [...lista, cuenta(TARJETA, 'Tarjeta BBVA')];
  expect(aplicarPropuesta(borradorInicial(HOY), propuestaAplicable(prop([TARJETA, 'p-general'], null), indice, conTarjeta), conTarjeta).cuentaId).toBe(TARJETA);
});

test('origen no explicable (la preferencia no está en la lista): el campo no se aplica', async () => {
  const f = fake({ propuesta: () => prop([TARJETA, 'p-fantasma'], null), prefs: () => [] });
  await abrir(f.cliente);
  await waitFor(() => expect(f.cliente.listarPreferencias).toHaveBeenCalled());
  await act(async () => {});
  expect(seleccionada(`cuenta-${TARJETA}`)).toBe(false);
});

test('la fecha nueva vuelve a pedir la propuesta para esa fecha', async () => {
  const f = fake();
  await abrir(f.cliente);
  fireEvent.press(screen.getByTestId('fecha-ayer'));
  await waitFor(() => expect(f.consultas.at(-1)).toEqual(['2026-09-23', null]));
});

test('reintento del registro (INDETERMINADO): misma intención y sin volver a pedir la propuesta', async () => {
  let nRegistro = 0;
  let cambiada = false;
  const f = fake({
    propuesta: (_f, cat) => (cat === 'super' ? prop([cambiada ? EFECTIVO : TARJETA, 'p-super'], null) : prop(null, null)),
    prefs: () => [SUPER_TARJETA],
    registrar: async (p) => (++nRegistro === 1 ? { tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.' } : ok(p)),
  });
  await abrir(f.cliente);
  basicos();
  elegirCategoria('super');
  await waitFor(() => expect(seleccionada(`cuenta-${TARJETA}`)).toBe(true));
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('estado-indeterminado');
  cambiada = true; // la preferencia cambia en el servidor entre envío y reintento
  const antes = (f.cliente.propuestaPreferencias as jest.Mock).mock.calls.length;
  await act(async () => fireEvent.press(screen.getByTestId('reintentar')));
  await screen.findByTestId('registro-exito');
  expect((f.cliente.propuestaPreferencias as jest.Mock).mock.calls.length).toBe(antes);
  expect(f.enviados).toHaveLength(2);
  expect(f.enviados[1]).toEqual(f.enviados[0]);
  expect(f.enviados[1].cuenta_id).toBe(TARJETA);
});

// ------------------------------------------------------------------ R05–R07: «Guardar como preferencia»
async function registrarCon(f: ReturnType<typeof fake>, o: { categoria: string | null; cuenta: string; presupuestable: boolean }) {
  await abrir(f.cliente);
  basicos();
  if (o.categoria) elegirCategoria(o.categoria);
  else sinCategoria();
  await waitFor(() => expect(f.consultas.at(-1)?.[1]).toBe(o.categoria));
  await act(async () => {});
  if (!seleccionada(`cuenta-${o.cuenta}`)) fireEvent.press(screen.getByTestId(`cuenta-${o.cuenta}`));
  if (!screen.getByTestId(`presupuestable-${o.presupuestable}`).props.accessibilityState.selected) {
    fireEvent.press(screen.getByTestId(`presupuestable-${o.presupuestable}`));
  }
  await registrar();
}

test('tarjeta oculta con «Sin categoría» (D-PREF-05)', async () => {
  const f = fake();
  await registrarCon(f, { categoria: null, cuenta: EFECTIVO, presupuestable: true });
  expect(screen.queryByTestId('pref-tarjeta')).toBeNull();
  expect(f.cliente.altaPreferencia).not.toHaveBeenCalled();
});

test('tarjeta oculta cuando no hay nada que recordar (valores finales = propuestos)', async () => {
  const f = fake({ propuesta: (_f, cat) => (cat === 'super' ? prop([TARJETA, 'p-super'], [true, 'p-general']) : prop(null, null)), prefs: () => [GENERAL, SUPER_TARJETA] });
  await registrarCon(f, { categoria: 'super', cuenta: TARJETA, presupuestable: true });
  expect(screen.queryByTestId('pref-tarjeta')).toBeNull();
});

test('R05: casillas iniciales por diferencia; alta con ámbito «Una categoría» y el UUID de la tarjeta; aviso «Preferencia guardada»', async () => {
  const f = fake({ propuesta: () => prop(null, [true, 'p-general']), prefs: () => [GENERAL] });
  await registrarCon(f, { categoria: 'super', cuenta: TARJETA, presupuestable: true });
  const tarjeta = within(screen.getByTestId('pref-tarjeta'));
  expect(tarjeta.getByText('¿Recordarlo para Supermercado?')).toBeTruthy();
  expect(seleccionada('pref-casilla-cuenta')).toBe(true); // difiere: no había propuesta de cuenta
  expect(seleccionada('pref-casilla-presupuestable')).toBe(false); // coincide con la general
  expect(tarjeta.getByText('Se propondrá en tus próximos gastos de Supermercado. Podrás cambiarlo siempre.')).toBeTruthy();
  const idTarjeta = '00000000-0000-4000-8000-000000000002'; // 1 = intención; 2 = generado al abrir la tarjeta
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  expect(f.cliente.altaPreferencia).toHaveBeenCalledWith({
    id: idTarjeta, tipo_hecho_id: TIPOS.GASTO, categoria_id: 'super', tercero_id: null, entidad_id: null,
    cuenta_default_id: TARJETA, presupuestable_default: null, prioridad: 100,
  });
  expect(await screen.findByText('Preferencia guardada')).toBeTruthy();
  expect(f.cliente.registrarGastoPagado).toHaveBeenCalledTimes(1); // el hecho no se toca
});

test('editar envía el ESTADO COMPLETO (E05): el campo no recordado conserva su valor actual', async () => {
  const existente = pref({ id: 'p-super', categoria_id: 'super', presupuestable_default: true, row_version: 3 });
  const f = fake({ propuesta: (_f, cat) => (cat === 'super' ? prop(null, [true, 'p-super']) : prop(null, null)), prefs: () => [existente] });
  await registrarCon(f, { categoria: 'super', cuenta: EFECTIVO, presupuestable: true });
  expect(seleccionada('pref-casilla-cuenta')).toBe(true);
  expect(seleccionada('pref-casilla-presupuestable')).toBe(false);
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  expect(f.cliente.altaPreferencia).not.toHaveBeenCalled();
  expect(f.cliente.editarPreferencia).toHaveBeenCalledWith('p-super', {
    row_version: 3, tipo_hecho_id: TIPOS.GASTO, categoria_id: 'super', tercero_id: null, entidad_id: null,
    cuenta_default_id: EFECTIVO, presupuestable_default: true, prioridad: 100,
  });
  expect(await screen.findByTestId('pref-guardada')).toBeTruthy();
});

test('R06: fallo → aviso y «Reintentar» con el MISMO UUID; el gasto sigue registrado', async () => {
  let intentos = 0;
  const f = fake({ alta: async (c) => (++intentos === 1 ? { tipo: 'INDETERMINADO', mensaje: 'x' } : okPref(c)) });
  await registrarCon(f, { categoria: 'super', cuenta: EFECTIVO, presupuestable: false });
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  expect(plano('pref-error')).toBe(
    'No se pudo guardar la preferencia. El gasto sí está registrado. Puedes reintentarlo o crearla luego en Ajustes › Preferencias.',
  );
  expect(screen.getByTestId('registro-exito')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('pref-reintentar')));
  expect(await screen.findByTestId('pref-guardada')).toBeTruthy();
  const llamadas = (f.cliente.altaPreferencia as jest.Mock).mock.calls.map((c) => c[0]);
  expect(llamadas).toHaveLength(2);
  expect(llamadas[1]).toEqual(llamadas[0]); // mismo UUID y mismo contenido
  expect(f.cliente.registrarGastoPagado).toHaveBeenCalledTimes(1);
});

test('R07: conflicto → «Mantener» no escribe; «Sustituir» edita con row_version; VERSION_DESFASADA recarga y vuelve a preguntar', async () => {
  let version = 1;
  let actual = EFECTIVO;
  const lista = () => [pref({ id: 'p-super', categoria_id: 'super', cuenta_default_id: actual, row_version: version })];
  let ediciones = 0;
  const f = fake({
    propuesta: (_f, cat) => (cat === 'super' ? prop([EFECTIVO, 'p-super'], null) : prop(null, null)),
    prefs: lista,
    editar: async (id, c) => {
      if (++ediciones === 1) {
        version = 2; // otra sesión la cambió mientras tanto
        actual = COMUN;
        return { tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: '' };
      }
      return okPref({ ...c, id }, c.row_version + 1);
    },
  });
  await registrarCon(f, { categoria: 'super', cuenta: TARJETA, presupuestable: true });
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  expect(screen.getByText('Ya tienes una preferencia para Supermercado')).toBeTruthy();
  expect(plano('pref-conflicto-texto')).toBe('Ahora propone pagar con Efectivo. ¿Quieres que proponga Tarjeta BBVA a partir de ahora?');
  expect(within(screen.getByTestId('pref-mantener')).getByText('Mantener Efectivo')).toBeTruthy();
  fireEvent.press(screen.getByTestId('pref-mantener'));
  expect(screen.queryByTestId('pref-conflicto')).toBeNull();
  expect(f.cliente.editarPreferencia).not.toHaveBeenCalled();
  expect(f.cliente.altaPreferencia).not.toHaveBeenCalled(); // nunca se crea otra que la contradiga
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  await act(async () => fireEvent.press(screen.getByTestId('pref-sustituir')));
  expect((f.cliente.editarPreferencia as jest.Mock).mock.calls[0]).toEqual([
    'p-super',
    // Sin propuesta de presupuesto la casilla venía marcada: se recuerda también (sin conflicto: la existente no lo propone).
    { row_version: 1, tipo_hecho_id: TIPOS.GASTO, categoria_id: 'super', tercero_id: null, entidad_id: null, cuenta_default_id: TARJETA, presupuestable_default: true, prioridad: 100 },
  ]);
  // Recargada: vuelve a preguntar con el valor ACTUAL.
  await waitFor(() => expect(plano('pref-conflicto-texto')).toBe('Ahora propone pagar con Cuenta común. ¿Quieres que proponga Tarjeta BBVA a partir de ahora?'));
  await act(async () => fireEvent.press(screen.getByTestId('pref-sustituir')));
  expect((f.cliente.editarPreferencia as jest.Mock).mock.calls[1][1].row_version).toBe(2);
  expect(await screen.findByTestId('pref-guardada')).toBeTruthy();
  expect(f.cliente.altaPreferencia).not.toHaveBeenCalled();
});

test('R07 por carrera: el alta responde PREFERENCIA_EMPATE_CONTRADICTORIO → se recarga y se pregunta', async () => {
  let creada = false;
  const f = fake({
    prefs: () => (creada ? [pref({ id: 'p-otra', categoria_id: 'super', cuenta_default_id: EFECTIVO })] : []),
    alta: async () => {
      creada = true; // otra sesión la creó entre la lectura y el alta
      return { tipo: 'RECHAZADO', codigo: 'PREFERENCIA_EMPATE_CONTRADICTORIO', mensaje: '', detalle: { preferencia_conflicto_id: 'p-otra' } };
    },
  });
  await registrarCon(f, { categoria: 'super', cuenta: TARJETA, presupuestable: true });
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  expect(await screen.findByTestId('pref-conflicto')).toBeTruthy();
  expect(plano('pref-conflicto-texto')).toBe('Ahora propone pagar con Efectivo. ¿Quieres que proponga Tarjeta BBVA a partir de ahora?');
  expect(f.cliente.altaPreferencia).toHaveBeenCalledTimes(1);
});

test('R07 con presupuesto: texto y «Mantener la actual»', async () => {
  const f = fake({ prefs: () => [pref({ id: 'p-super', categoria_id: 'super', presupuestable_default: false })], propuesta: () => prop(null, null) });
  await registrarCon(f, { categoria: 'super', cuenta: TARJETA, presupuestable: true });
  fireEvent.press(screen.getByTestId('pref-casilla-cuenta')); // solo el presupuesto
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  expect(plano('pref-conflicto-texto')).toBe(
    'Ahora propone que cuenta para el presupuesto: No. ¿Quieres que proponga que cuenta para el presupuesto: Sí a partir de ahora?',
  );
  expect(within(screen.getByTestId('pref-mantener')).getByText('Mantener la actual')).toBeTruthy();
});

// ------------------------------------------------------------------ AJ-B2-04 (rama de D6 sin conflicto tras recargar)
test.each([
  ['VERSION_DESFASADA en la edición', 'EDITAR'],
  ['PREFERENCIA_EMPATE_CONTRADICTORIO en el alta', 'ALTA'],
] as const)('AJ-B2-04: %s y, al recargar, ya no hay conflicto → vuelve a la tarjeta, sin R07 y sin escribir', async (_caso, via) => {
  // Antes: EDITAR → existe la de Supermercado sin cuenta (se editaría); ALTA → no existe ninguna (se daría de alta).
  // Mientras tanto, otra sesión deja la de Supermercado proponiendo YA la cuenta elegida (Tarjeta): no hay conflicto.
  let cambiada = false;
  const inicial = via === 'EDITAR' ? [pref({ id: 'p-super', categoria_id: 'super', presupuestable_default: true, row_version: 1 })] : [];
  const despues = [pref({ id: 'p-super', categoria_id: 'super', cuenta_default_id: TARJETA, presupuestable_default: true, row_version: 2 })];
  const f = fake({
    propuesta: () => prop(null, null),
    prefs: () => (cambiada ? despues : inicial),
    editar: async () => {
      cambiada = true;
      return { tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: '' };
    },
    alta: async () => {
      cambiada = true;
      return { tipo: 'RECHAZADO', codigo: 'PREFERENCIA_EMPATE_CONTRADICTORIO', mensaje: '', detalle: { preferencia_conflicto_id: 'p-super' } };
    },
  });
  await registrarCon(f, { categoria: 'super', cuenta: TARJETA, presupuestable: true });
  fireEvent.press(screen.getByTestId('pref-casilla-presupuestable')); // solo la cuenta
  expect(seleccionada('pref-casilla-cuenta')).toBe(true);
  expect(seleccionada('pref-casilla-presupuestable')).toBe(false);
  await act(async () => fireEvent.press(screen.getByTestId('pref-guardar')));
  await waitFor(() => expect(f.cliente.listarPreferencias).toHaveBeenCalledTimes(2)); // lectura previa + recarga tras el rechazo
  expect(screen.getByTestId('pref-tarjeta')).toBeTruthy(); // vuelve a la tarjeta
  expect(screen.queryByTestId('pref-conflicto')).toBeNull(); // sin R07
  expect(screen.queryByTestId('pref-error')).toBeNull();
  expect(screen.queryByTestId('pref-guardada')).toBeNull();
  // Ninguna escritura más que la rechazada.
  expect(f.cliente.editarPreferencia).toHaveBeenCalledTimes(via === 'EDITAR' ? 1 : 0);
  expect(f.cliente.altaPreferencia).toHaveBeenCalledTimes(via === 'ALTA' ? 1 : 0);
  expect(f.cliente.registrarGastoPagado).toHaveBeenCalledTimes(1);
});
