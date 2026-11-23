// ============================================================
// GAPTO MOBILE 2027
// Fichero: cat_viv.test.tsx
// Ruta: mobile/__tests__/cat_viv.test.tsx
// Descripción: CAT-VIV (T2-F06, bloque 3) contra dobles en memoria, con los nombres de oráculo del mandato (§9.2) y de la lámina SET-CAT/REG-CAT v1.0: dominio (`exigePropiedad` solo GASTO y por la marca de ESA categoría; faltas; wire `propiedad` con `posiciones_confirmadas`; sellado), O-CV-12 (sin marca el formulario no cambia; con marca «Propiedad» obligatoria), «<cotitular>, todo» (sin «Pagado con»), O-CV-18 (VP-2b: mueble 250 € que cuenta en el mes y no suma al coste), O-CV-16 (una plantilla que deja una categoría marcada en el registro hace obligatoria la propiedad), R06/M5 (registrar desde una previsión con categoría marcada pide la propiedad y la envía), R07 (aviso de lectura en Actividad, sin acción) y O-CV-17 (VP-1: al tocar «Asociada a vivienda» solo cambia la fila; la relectura es silenciosa y el detalle no se desmonta).
// Versión: 0.3.0 (MANT D18, lote 40): se elimina el jest.setTimeout(30000) propio; el límite (90 s) lo fija solo tiempos_rn (R-TEST-TIMEOUT); sin cambios de aserciones.
//   previa: 0.1.0 (F06 T2-F06 CAT-VIV N1 (L-04, lámina SET-CAT/REG-CAT v1.0))
// Versión: 0.4.0 (F06 T6 · S2 FORM-AGIL; F09 0.55 §12.107.1 puntos 1 y 2): los controles se buscan con `ver`/`verPronto` (form_agil.ts), que tocan antes la línea de «Se registrará así», «Más opciones» o «‹ Exprés» como haría el usuario. Mismas aserciones; las de ausencia siguen con queryByTestId.
// Versión: 0.5.0 (F06 T6 · S6 N1 conservador; dictamen 1 Q3/A4, DF-14): la pregunta «¿Qué tipo de gasto es?» ya no se muestra; se comprueba su ausencia y el payload sigue enviando clase GASTO_CORRIENTE.
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, CuentaPago, DetalleActividad, DetallePrevision, FilaActividad, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonioB3, PropuestaGasto } from '../src/api/patrimonio_b3';
import type { ClientePropiedades } from '../src/api/propiedades';
import type { CategoriaNodo } from '../src/domain/categoria';
import { borradorInicial, sellar } from '../src/domain/intencion';
import {
  bloqueWire,
  conDeudas,
  conPropuesta,
  exigePropiedad,
  faltasPropiedad,
  seleccionInicial,
  TEXTO_AVISO_VIVIENDA,
  TEXTO_AVISO_VIVIENDA_DETALLE,
  TEXTO_NO_SUMA_COSTE,
  TEXTO_PREVISION_SIN_PROPIEDAD,
} from '../src/domain/propiedad_registro';
import { CategoriasAjustesScreen, NOTA_VIVIENDA_INGRESO, NOTA_VIVIENDA_NO, NOTA_VIVIENDA_SI, NOTA_VIVIENDA_SI_AMBOS } from '../src/screens/CategoriasAjustesScreen';
import { PrevisionRegistroScreen } from '../src/screens/PrevisionRegistroScreen';
import { RegistroGastoScreen } from '../src/screens/RegistroGastoScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';
import { actVer, ver, verPronto } from './form_agil';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 26, 10, 0, 0);
const HOY = '2026-10-26';
const C1 = 'c0000000-0000-4000-8000-000000000001';
const CONJ = 'c0000000-0000-4000-8000-000000000002';
const YO = 'f0000000-0000-4000-8000-0000000000ff';
const LUCIA = 'a0000000-0000-4000-8000-0000000000a1';
const P1 = 'p0000000-0000-4000-8000-000000000001';
const P2 = 'p0000000-0000-4000-8000-000000000002';
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };

const compartida = (fecha = HOY, propiedad = P1): PropuestaGasto => ({
  fecha, propiedad_id: propiedad, nombre: 'Piso Centro', titularidad_disponible: true,
  partes: [
    { actor_id: LUCIA, porcentaje: '50.0000', yo: false, tercero_id: 't-lucia', nombre: 'Lucía', naturaleza: 'PERSONA' },
    { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null, naturaleza: null },
  ],
  cuenta: null,
});
const soloMia = (fecha = HOY): PropuestaGasto => ({
  fecha, propiedad_id: P2, nombre: 'Casa Playa', titularidad_disponible: true,
  partes: [{ actor_id: YO, porcentaje: '100.0000', yo: true, tercero_id: null, nombre: null, naturaleza: null }], cuenta: null,
});

// ------------------------------------------------------------------ dominio
test('O-CV-12 dominio: exigePropiedad solo en gastos y por la marca de la categoría elegida (Q-CV-03, Q-CV-11)', () => {
  expect(exigePropiedad('GASTO', nodo({ id: 'ibi', nombre: 'IBI', asociada_vivienda: true }))).toBe(true);
  expect(exigePropiedad('GASTO', nodo({ id: 'seg', nombre: 'Seguros', ambito: 'AMBOS', asociada_vivienda: true }))).toBe(true);
  expect(exigePropiedad('INGRESO', nodo({ id: 'seg', nombre: 'Seguros', ambito: 'AMBOS', asociada_vivienda: true }))).toBe(false);
  expect(exigePropiedad('GASTO', nodo({ id: 'hijo', nombre: 'Hijo', parent_id: 'ibi' }))).toBe(false);
  expect(exigePropiedad('GASTO', nodo({ id: 'x', nombre: 'Ocio', asociada_vivienda: false }))).toBe(false);
  expect(exigePropiedad('GASTO', undefined)).toBe(false);
});

test('faltas y wire del bloque: reparto por titularidad, «¿Quién pagó?» sin valor por defecto y deuda preseleccionada', () => {
  expect(faltasPropiedad(null, '120', C1)).toEqual(['la propiedad']);
  const s0 = seleccionInicial(P1, 'Piso Centro');
  expect(faltasPropiedad(s0, '120', C1)).toEqual(['esperar la propuesta de reparto']);
  const s = conPropuesta(s0, compartida());
  expect(s.reparto).toEqual({ modo: 'TITULARIDAD' });
  expect(faltasPropiedad(s, '120', C1)).toEqual(['quién pagó']);
  const yo = conDeudas({ ...s, pago: { ...s.pago, modo: 'YO_TODO' } }, '120');
  expect(faltasPropiedad(yo, '120', C1)).toEqual([]);
  expect(bloqueWire(yo, '120', C1, HOY)).toEqual({
    propiedad_id: P1,
    clase: 'GASTO_CORRIENTE',
    atribucion: { modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_HECHO', fecha_referencia: HOY,
      partes: [{ actor_id: LUCIA, porcentaje: '50.0000' }, { actor_id: YO, porcentaje: '50.0000' }] } },
    pagos: [{ pagador: 'YO', cuenta_id: C1, importe: '120.00' }],
    saldos: [{ actor_id: LUCIA, sentido: 'ME_DEBE', importe: '60.00' }],
    posiciones_confirmadas: [{ actor_id: LUCIA, tipo: 'DERECHO_COBRO', importe: '60.00' }],
  });
  const sinTit = conPropuesta(s0, { ...compartida(), titularidad_disponible: false, partes: [] });
  expect(sinTit.reparto).toBeNull();
  expect(faltasPropiedad(sinTit, '120', C1)).toEqual(['de quién es el gasto']);
  const mia = conPropuesta(seleccionInicial(P2, 'Casa Playa'), soloMia());
  expect(mia.pago.modo).toBe('YO_TODO');
});

test('sellado: con propiedad, SIN_INDICAR + NO_DETERMINADA + `propiedad`; sin ella, el wire de VS-01 no cambia', () => {
  const b = { ...borradorInicial(HOY), importeTexto: '120', presupuestable: true, soloMio: true, cuentaId: C1, propuesta: 'SELF_100' as const,
    categoria: { estado: 'CATEGORIA' as const, id: 'ibi', nombre: 'IBI', ruta: 'IBI', icon_key: null, magnitudes: [] } };
  const sin = sellar(b, 'i1').payload;
  expect(sin.atribucion).toBe('SOLO_MIO');
  expect(sin.financiacion.estado).toBe('PROPUESTA_ACEPTADA');
  expect('propiedad' in sin).toBe(false);
  const w = bloqueWire(conDeudas({ ...conPropuesta(seleccionInicial(P1, 'Piso Centro'), compartida()), pago: { modo: 'YO_TODO', pagadorId: null, mio: '', suyo: '' } }, '120'), '120', C1, HOY);
  const con = sellar({ ...b, propiedad: w }, 'i2').payload;
  expect(con.atribucion).toBe('SIN_INDICAR');
  expect(con.financiacion).toEqual({ estado: 'NO_DETERMINADA' });
  expect(con.propiedad).toEqual(w);
});

// ------------------------------------------------------------------ Registrar gasto
const ARBOL: CategoriaNodo[] = [
  nodo({ id: 'hogar', nombre: 'Hogar' }),
  nodo({ id: 'comunidad', nombre: 'Comunidad', parent_id: 'hogar', asociada_vivienda: true }),
  nodo({ id: 'muebles', nombre: 'Muebles', parent_id: 'hogar', orden: 1, asociada_vivienda: true }),
  nodo({ id: 'ocio', nombre: 'Ocio', orden: 1, asociada_vivienda: false }),
];
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });

const CUENTAS: CuentaPago[] = [
  { cuenta_id: C1, nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
  { cuenta_id: CONJ, nombre: 'Cuenta conjunta', moneda: 'EUR', propuesta_financiacion: 'NO_DETERMINADA' },
];
function cliente(arbol: CategoriaNodo[] = ARBOL, o: { propuestaRegistro?: (q: any) => any } = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(arbol),
    registrarGastoPagado: jest.fn(async (p: any) => ok({ intencion_id: p.intencion_id, hecho_id: p.intencion_id, idempotente: false, importe: p.importe, moneda: 'EUR',
      estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado })) as any,
    cuentasPago: jest.fn(async () => ok({ cuentas: CUENTAS })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    ...(o.propuestaRegistro ? { propuestaRegistro: jest.fn(async (q: any) => ok(o.propuestaRegistro!(q))) as any } : {}),
  } as unknown as ClienteApi;
}
const propiedades = () => ({ listarPropiedades: jest.fn(async () => ok({ propiedades: [
  { id: P1, nombre: 'Piso Centro', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', modo_titularidad: 'COMPARTIDA', valor_estimado: null },
  { id: P2, nombre: 'Casa Playa', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', modo_titularidad: 'INDIVIDUAL', valor_estimado: null }] })) }) as unknown as ClientePropiedades;
const patrimonio = () => ({ propuestaGasto: jest.fn(async (id: string, fecha: string) => ok(id === P2 ? soloMia(fecha) : compartida(fecha))) }) as unknown as ClientePatrimonioB3;

function montarRegistro(c: ClienteApi, extra: Partial<React.ComponentProps<typeof RegistroGastoScreen>> = {}) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema>
        <RegistroGastoScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} onGastoCompartido={jest.fn()}
          propiedades={propiedades()} patrimonio={patrimonio()} {...extra} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}
async function formulario(c: ClienteApi, categoria: 'comunidad' | 'muebles' | 'ocio', importe = '120') {
  montarRegistro(c);
  await verPronto(`cuenta-${C1}`);
  fireEvent.changeText(ver('campo-importe'), importe);
  fireEvent.press(ver('campo-categoria'));
  if (categoria !== 'ocio') fireEvent.press(ver('cat-hogar'));
  await actVer(`cat-${categoria}`, async () => fireEvent.press(ver(`cat-${categoria}`)));
  fireEvent.press(ver('presupuestable-true'));
  if (screen.queryByTestId(`cuenta-${C1}`)) fireEvent.press(ver(`cuenta-${C1}`));
}
const marcado = (id: string) => !!ver(id).props.accessibilityState?.checked || !!ver(id).props.accessibilityState?.selected;
const ids = (raiz: any): string[] => {
  const out: string[] = [];
  const recorrer = (x: any) => {
    if (!x || typeof x !== 'object') return;
    if (Array.isArray(x)) return x.forEach(recorrer);
    if (x.props?.testID) out.push(x.props.testID);
    recorrer(x.children);
  };
  recorrer(raiz);
  return out.sort();
};

test('O-CV-12: sin marca el formulario no cambia (mismos campos que una categoría sin el campo de la marca)', async () => {
  const arbolSinCampo = ARBOL.map(({ asociada_vivienda: _a, ...x }) => x as CategoriaNodo);
  await formulario(cliente(arbolSinCampo), 'ocio');
  const antes = ids(screen.toJSON());
  screen.unmount();
  await formulario(cliente(), 'ocio');
  const despues = ids(screen.toJSON());
  expect(despues).toEqual(antes);
  for (const id of ['solo-mio', 'repartir', 'reembolsable', 'otra-persona', `cuenta-${CONJ}`, 'financiacion']) expect(ver(id)).toBeTruthy();
  expect(screen.queryByTestId('vivienda')).toBeNull();
  expect(screen.queryByTestId('vivienda-solo-tus-cuentas')).toBeNull();
});

test('O-CV-12: con marca, «Propiedad» obligatoria (R01); sin ella no se registra; con ella viaja el bloque con reparto, deuda y confirmación (R02, R03)', async () => {
  const c = cliente();
  await formulario(c, 'comunidad');
  expect(ver('vivienda')).toBeTruthy();
  for (const id of ['solo-mio', 'repartir', 'reembolsable', 'otra-persona', `cuenta-${CONJ}`, 'financiacion']) expect(screen.queryByTestId(id)).toBeNull();
  expect(ver('vivienda-error').props.children).toBe('Falta: la propiedad.');
  expect(ver('faltan').props.children).toBe('Para registrar falta: la propiedad.');
  expect(ver('registrar').props.accessibilityState?.disabled).toBe(true);
  await actVer('registrar', async () => fireEvent.press(ver('registrar')));
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  await act(async () => fireEvent.press(await verPronto(`vivienda-prop-${P1}`)));
  await verPronto('vivienda-titularidad');
  expect(marcado('vivienda-titularidad')).toBe(true);
  expect(ver('vivienda-partes').props.children).toBe('Tu parte: 60,00 € · Lucía: 60,00 €');
  // F06 T6 · S6 (DF-14): sin «¿Qué tipo de gasto es?»; la clase sigue siendo GASTO_CORRIENTE en el bloque (ver el payload).
  for (const k of ['GASTO_CORRIENTE', 'REPARACION', 'MEJORA']) expect(screen.queryByTestId(`vivienda-clase-${k}`)).toBeNull();
  // «¿Quién pagó?» sin valor por defecto.
  expect(ver('faltan').props.children).toBe('Para registrar falta: quién pagó.');
  await actVer('vivienda-quien-yo', async () => fireEvent.press(ver('vivienda-quien-yo')));
  expect(marcado(`vivienda-deuda-${LUCIA}-si`)).toBe(true);
  expect(ver('vivienda-resumen').props.children).toBe('Tu gasto del mes: 60,00 € · Lucía te debe 60,00 €');
  await actVer('registrar', async () => fireEvent.press(ver('registrar')));
  // F06 T6 · S2 (dictamen 1 Q5/A6): con vivienda, «Registrar» abre «Revisar»; se confirma desde ahí.
  expect(ver('revisar-vivienda')).toBeTruthy();
  await actVer('revisar-confirmar', async () => fireEvent.press(ver('revisar-confirmar')));
  await verPronto('registro-exito');
  const pl = (c.registrarGastoPagado as jest.Mock).mock.calls[0][0];
  expect(pl.atribucion).toBe('SIN_INDICAR');
  expect(pl.financiacion).toEqual({ estado: 'NO_DETERMINADA' });
  expect(pl.cuenta_id).toBe(C1);
  expect(pl.propiedad).toEqual({
    propiedad_id: P1, clase: 'GASTO_CORRIENTE',
    atribucion: { modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_HECHO', fecha_referencia: HOY,
      partes: [{ actor_id: LUCIA, porcentaje: '50.0000' }, { actor_id: YO, porcentaje: '50.0000' }] } },
    pagos: [{ pagador: 'YO', cuenta_id: C1, importe: '120.00' }],
    saldos: [{ actor_id: LUCIA, sentido: 'ME_DEBE', importe: '60.00' }],
    posiciones_confirmadas: [{ actor_id: LUCIA, tipo: 'DERECHO_COBRO', importe: '60.00' }],
  });
});

test('con marca: «Lucía, todo» oculta «Pagado con» y propone LE_DEBO; desmarcarlo envía NADA', async () => {
  const c = cliente();
  await formulario(c, 'comunidad');
  await act(async () => fireEvent.press(await verPronto(`vivienda-prop-${P1}`)));
  await verPronto('vivienda-titularidad');
  await actVer(`vivienda-quien-cotitular-${LUCIA}`, async () => fireEvent.press(ver(`vivienda-quien-cotitular-${LUCIA}`)));
  expect(screen.queryByTestId(`cuenta-${C1}`)).toBeNull();
  expect(ver('vivienda-sin-cuenta')).toBeTruthy();
  await actVer(`vivienda-deuda-${LUCIA}-no`, async () => fireEvent.press(ver(`vivienda-deuda-${LUCIA}-no`)));
  await actVer('registrar', async () => fireEvent.press(ver('registrar')));
  // F06 T6 · S2 (dictamen 1 Q5/A6): con vivienda, «Registrar» abre «Revisar»; se confirma desde ahí.
  expect(ver('revisar-vivienda')).toBeTruthy();
  await actVer('revisar-confirmar', async () => fireEvent.press(ver('revisar-confirmar')));
  await verPronto('registro-exito');
  const pl = (c.registrarGastoPagado as jest.Mock).mock.calls[0][0];
  expect(pl.propiedad.pagos).toEqual([{ pagador: LUCIA, importe: '120.00' }]);
  expect(pl.propiedad.saldos).toEqual([{ actor_id: LUCIA, sentido: 'NADA' }]);
  expect(pl.propiedad.posiciones_confirmadas).toEqual([]);
});

test('O-CV-18 (VP-2b, R05): un mueble de 250 € con categoría marcada es un gasto normal de vivienda que cuenta en el mes y no suma al coste', async () => {
  const c = cliente();
  await formulario(c, 'muebles', '250');
  await act(async () => fireEvent.press(await verPronto(`vivienda-prop-${P2}`)));
  await verPronto('vivienda-titularidad');
  expect(screen.queryByTestId('vivienda-quien-yo')).toBeNull(); // sin cotitulares no se pregunta
  await actVer('registrar', async () => fireEvent.press(ver('registrar')));
  // F06 T6 · S2 (dictamen 1 Q5/A6): con vivienda, «Registrar» abre «Revisar»; se confirma desde ahí.
  expect(ver('revisar-vivienda')).toBeTruthy();
  await actVer('revisar-confirmar', async () => fireEvent.press(ver('revisar-confirmar')));
  await verPronto('registro-exito');
  const pl = (c.registrarGastoPagado as jest.Mock).mock.calls[0][0];
  expect(pl.propiedad.clase).toBe('GASTO_CORRIENTE');
  expect(pl.propiedad.pagos).toEqual([{ pagador: 'YO', cuenta_id: C1, importe: '250.00' }]);
  expect(ver('exito-vivienda-propiedad').props.children).toBe('Casa Playa');
  expect(ver('exito-vivienda-reparto').props.children).toBe('Según titularidad: tú 100 %');
  expect(ver('exito-vivienda-mes').props.children).toBe('Cuenta en el gasto de octubre: 250,00 €.');
  expect(ver('exito-vivienda-no-coste').props.children).toBe(TEXTO_NO_SUMA_COSTE);
});

test('O-CV-16: una plantilla que deja una categoría marcada en el registro hace obligatoria la propiedad', async () => {
  const origen = { capa: 'PLANTILLA', plantilla_id: 'p1', preferencia_id: null };
  const c = cliente(ARBOL, { propuestaRegistro: (q) => ({ tipo: q.tipo,
    campos: { categoria: { valor: 'comunidad', origen }, tercero: null, contexto: null, cuenta: { valor: C1, origen }, presupuestable: { valor: true, origen } },
    avisos: [] }) });
  montarRegistro(c, { plantilla: { id: 'p1', nombre: 'Comunidad' } });
  await waitFor(() => expect(ver('categoria-valor').props.children).toBe('Comunidad'));
  fireEvent.changeText(ver('campo-importe'), '120');
  await waitFor(() => expect(ver('vivienda')).toBeTruthy());
  expect(ver('faltan').props.children).toBe('Para registrar falta: la propiedad.');
  expect(screen.queryByTestId('solo-mio')).toBeNull();
});

// ------------------------------------------------------------------ R06 · registrar desde la previsión (M5)
const PREVISION: DetallePrevision = {
  id: 'prev1', regla_id: 'r1', row_version: 3, estado: 'ABIERTA', estado_derivado: 'PENDIENTE', tipo: 'GASTO', concepto: 'Comunidad',
  tercero: null, categoria: { id: 'comunidad', nombre: 'Comunidad', ruta: 'Hogar › Comunidad' }, fecha_esperada_desde: '2026-10-01',
  fecha_esperada_hasta: '2026-10-01', moneda: 'EUR', importe_esperado: '120.00', cuenta_salida: { id: C1, nombre: 'Cuenta nómina' },
  cuenta_entrada: null, presupuestable: true, con_realidad: false, cubierto: '0.00', queda: '120.00', pagos: 0,
} as unknown as DetallePrevision;

test('R06 / M5 (OBL-VIV-01.4): registrar desde una previsión con categoría marcada pide la propiedad y la envía en el bloque', async () => {
  const c = cliente();
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema>
        <PrevisionRegistroScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} detalle={PREVISION} onCerrar={jest.fn()}
          propiedades={propiedades()} patrimonio={patrimonio()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await verPronto('prevision-vivienda');
  expect(ver('prevision-vivienda-aviso').props.children).toBe(TEXTO_PREVISION_SIN_PROPIEDAD);
  await actVer('cubierta-si', async () => fireEvent.press(ver('cubierta-si')));
  expect(ver('prevision-falta').props.children).toBe('Para revisar falta: la propiedad.');
  expect(ver('prevision-revisar').props.accessibilityState?.disabled).toBe(true);
  expect(screen.queryByTestId(`prevision-cuenta-${CONJ}`)).toBeNull();
  await act(async () => fireEvent.press(await verPronto(`prevision-vivienda-prop-${P2}`)));
  await verPronto('prevision-vivienda-titularidad');
  await actVer('prevision-revisar', async () => fireEvent.press(ver('prevision-revisar')));
  await actVer('prevision-registrar', async () => fireEvent.press(ver('prevision-registrar')));
  const pl = (c.registrarGastoPagado as jest.Mock).mock.calls[0][0];
  expect(pl.prevision).toBeTruthy();
  expect(pl.atribucion).toBe('SIN_INDICAR');
  expect(pl.financiacion).toEqual({ estado: 'NO_DETERMINADA' });
  expect(pl.propiedad.propiedad_id).toBe(P2);
  expect(pl.propiedad.pagos).toEqual([{ pagador: 'YO', cuenta_id: C1, importe: '120.00' }]);
});

test('R06: con «Sin categoría» o una categoría sin marca, la previsión se registra como siempre', async () => {
  const c = cliente(ARBOL.map((x) => (x.id === 'comunidad' ? { ...x, asociada_vivienda: false } : x)));
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema>
        <PrevisionRegistroScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} detalle={PREVISION} onCerrar={jest.fn()}
          propiedades={propiedades()} patrimonio={patrimonio()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await verPronto(`prevision-cuenta-${CONJ}`);
  expect(screen.queryByTestId('prevision-vivienda')).toBeNull();
});

// ------------------------------------------------------------------ R07 · aviso de lectura en Actividad
const FILA: FilaActividad = {
  id: 'g7', fecha_hecho: '2026-09-12', tipo: 'GASTO', nota: 'Derrama ascensor', moneda: 'EUR', importe_total: '300.00',
  tercero: null, categoria: { id: 'comunidad', nombre: 'Comunidad', ruta: 'Hogar › Comunidad', enabled: true }, varias: false, contexto: null,
  cuentas: [{ cuenta_id: C1, nombre: 'Cuenta nómina', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA', tu_parte: '300.00', pendiente: null,
  maestros_desactivados: [],
} as unknown as FilaActividad;

async function detalleActividad(aviso: boolean | undefined) {
  const c = {
    ...cliente(),
    actividad: jest.fn(async () => ok({ filas: [FILA], siguiente: null, total: 1 })) as any,
    detalleActividad: jest.fn(async () => ok({ ...FILA, presupuestable: true, magnitudes: [], ...(aviso === undefined ? {} : { aviso_vivienda_sin_propiedad: aviso }) } as DetalleActividad)) as any,
    yo: jest.fn(async () => ok({ nombre: 'Moisés' })) as any,
    resultadoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })) as any,
  } as unknown as ClienteApi;
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light"><Raiz cliente={c} nuevoId={nuevoId} ahora={AHORA} /></ProveedorTema>
    </SafeAreaProvider>,
  );
  for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  await actVer('tab-DIA', async () => fireEvent.press(ver('tab-DIA')));
  await waitFor(() => expect(ver('fila-g7')).toBeTruthy());
  await actVer('fila-g7', async () => fireEvent.press(ver('fila-g7')));
  await waitFor(() => expect(ver('detalle-contenido')).toBeTruthy());
}

test('R07 (OBL-VIV-01.6): un gasto corregido a una categoría marcada muestra el aviso de lectura, sin acción para asociar la propiedad', async () => {
  await detalleActividad(true);
  const aviso = ver('detalle-aviso-vivienda');
  expect(within(aviso).getByText(TEXTO_AVISO_VIVIENDA)).toBeTruthy();
  expect(within(aviso).getByText(TEXTO_AVISO_VIVIENDA_DETALLE)).toBeTruthy();
  expect(screen.queryByText(/Asociar a una propiedad/)).toBeNull();
});

test('R07: sin el aviso (o sin el campo) el detalle no cambia', async () => {
  await detalleActividad(undefined);
  expect(screen.queryByTestId('detalle-aviso-vivienda')).toBeNull();
});

// ------------------------------------------------------------------ Ajustes › Categorías (S01–S05, VP-1)
function clienteAjustes(lista0: CategoriaNodo[], o: { lento?: boolean; falla?: boolean } = {}) {
  let lista = lista0;
  let lecturas = 0;
  const soltar: (() => void)[] = [];
  const arbol = jest.fn(async () => {
    lecturas += 1;
    if (o.lento && lecturas > 1) await new Promise<void>((r) => { soltar.push(r); });
    return ok({ categorias: lista });
  });
  const vivienda = jest.fn(async (id: string, cuerpo: { row_version: number; asociada_vivienda: boolean }) => {
    if (o.falla) return { tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: 'x' } as any;
    lista = lista.map((x) => (x.id === id ? { ...x, asociada_vivienda: cuerpo.asociada_vivienda, row_version: x.row_version + 1 } : x));
    const { magnitudes: _m, capturable: _c, motivo_no_capturable: _mc, ...cat } = lista.find((x) => x.id === id)!;
    return ok({ categoria: cat, idempotente: false, modificadas: [id] }) as any;
  });
  const c = { ...clienteCategoriasStub(lista), arbolCategorias: arbol, viviendaCategoria: vivienda } as unknown as ClienteApi;
  return { c, arbol, vivienda, soltar };
}
async function abrirDetalle(c: ClienteApi, id: string) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema><CategoriasAjustesScreen cliente={c} nuevoId={nuevoId} onAtras={jest.fn()} onInmersiva={jest.fn()} /></ProveedorTema>
    </SafeAreaProvider>,
  );
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  await act(async () => fireEvent.press(await verPronto(`fila-${id}`)));
}

test('S01–S03/S05: fila «Asociada a vivienda» con sus notas; en ingresos no hay fila y se explica por qué', async () => {
  const lista = [nodo({ id: 'super', nombre: 'Supermercado', row_version: 4 }), nodo({ id: 'nomina', nombre: 'Nómina', ambito: 'INGRESO', orden: 1 }),
    nodo({ id: 'seg', nombre: 'Seguros', ambito: 'AMBOS', orden: 2, asociada_vivienda: true }), nodo({ id: 'com', nombre: 'Comunidad', orden: 3, asociada_vivienda: true })];
  const { c } = clienteAjustes(lista);
  await abrirDetalle(c, 'super');
  expect(ver('detalle-vivienda-valor').props.children).toBe('No');
  expect(ver('detalle-vivienda-casa-no')).toBeTruthy();
  expect(ver('detalle-vivienda-nota').props.children).toBe(NOTA_VIVIENDA_NO);
  await actVer('detalle-atras', async () => fireEvent.press(ver('detalle-atras')));
  await act(async () => fireEvent.press(await verPronto('fila-com')));
  expect(ver('detalle-vivienda-casa-si')).toBeTruthy();
  expect(ver('detalle-vivienda-nota').props.children).toBe(NOTA_VIVIENDA_SI);
  await actVer('detalle-atras', async () => fireEvent.press(ver('detalle-atras')));
  await act(async () => fireEvent.press(await verPronto('fila-seg')));
  expect(ver('detalle-vivienda-nota').props.children).toBe(NOTA_VIVIENDA_SI_AMBOS);
  await actVer('detalle-atras', async () => fireEvent.press(ver('detalle-atras')));
  await act(async () => fireEvent.press(await verPronto('fila-nomina')));
  expect(screen.queryByTestId('detalle-vivienda')).toBeNull();
  expect(ver('detalle-vivienda-nota').props.children).toBe(NOTA_VIVIENDA_INGRESO);
});

test('O-CV-17 (VP-1, S04): al tocar «Asociada a vivienda» solo cambia la fila; guarda con el row_version vigente y relee en silencio sin desmontar el detalle', async () => {
  const { c, arbol, vivienda, soltar } = clienteAjustes([nodo({ id: 'super', nombre: 'Supermercado', row_version: 4 })], { lento: true });
  await abrirDetalle(c, 'super');
  const detalle = ver('detalle-categoria');
  await actVer('detalle-vivienda', async () => fireEvent.press(ver('detalle-vivienda')));
  expect(vivienda).toHaveBeenCalledWith('super', { row_version: 4, asociada_vivienda: true });
  // Relectura en curso: el MISMO detalle sigue montado, la fila ya dice «Sí» y no hay «Cargando».
  expect(soltar.length).toBe(1);
  expect(ver('detalle-categoria')).toBe(detalle);
  expect(ver('detalle-vivienda-valor').props.children).toBe('Sí');
  expect(ver('detalle-vivienda-nota').props.children).toBe(NOTA_VIVIENDA_SI);
  expect(screen.queryByText(/Cargando/)).toBeNull();
  await act(async () => { soltar[0](); await new Promise((r) => setTimeout(r, 0)); });
  expect(ver('detalle-categoria')).toBe(detalle);
  expect(ver('detalle-vivienda-valor').props.children).toBe('Sí');
  expect(arbol).toHaveBeenCalledTimes(2);
});

test('VP-1: si el guardado falla, la fila vuelve a su valor con un aviso', async () => {
  const { c } = clienteAjustes([nodo({ id: 'super', nombre: 'Supermercado', row_version: 4 })], { falla: true });
  await abrirDetalle(c, 'super');
  await actVer('detalle-vivienda', async () => fireEvent.press(ver('detalle-vivienda')));
  await waitFor(() => expect(ver('detalle-vivienda-valor').props.children).toBe('No'));
  expect(ver('detalle-aviso')).toBeTruthy();
});
