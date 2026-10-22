// ============================================================
// GAPTO MOBILE 2027
// Fichero: capacidades.test.tsx
// Ruta: mobile/__tests__/capacidades.test.tsx
// Descripción: Capacidades de cuenta en el cliente (F05-06 M4 §3; F09 §12.105 CAP, lámina CAP v0.1). Dominio: resumen de A1, textos de A3/A4 con «Lo ya registrado no cambia», lo que deja de funcionar, aviso B1 («De V3» solo si el servidor lo sabe), historial B4 y aviso B2. Pantallas: Ajustes › Cuentas (A1 con «Sin configurar» arriba), detalle A2/B1 con cuatro interruptores y «Otras» en solo lectura, hoja A3 que no cambia nada hasta confirmar, hoja A4 con el impacto antes de confirmar, VERSION_DESFASADA sin pisar y con recarga, cuenta cerrada en solo lectura, historial B4, modo oscuro. Registro: aviso B2 en «Pagado con», «Cobrado en», «Desde» y «A» (solo con N > 0), que abre Cuentas y vuelve conservando lo escrito; B3 CUENTA_SIN_CAPACIDAD con el mensaje del servidor, el formulario conservado y la cuenta ya no disponible ni elegida. Negativo: ninguna sugerencia ni texto por tipo de cuenta.
// Versión: 0.1.0 (F05-06 M4 F2)
// Versión: 0.2.0 (MANT-M5-ARNESES, AJ-M5-CIERRE-06): importa `tiempos_rn` (30 s por test y 5 s de `waitFor`/`findBy`) contra la intermitencia en frío de las suites de pantalla; sin cambios de aserciones.
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { CapacidadNodo, ClienteApi, CuentaCapacidades, CuentaPago, EntradaHistorialCapacidad, ImpactoCapacidad, Respuesta } from '../src/api/cliente';
import {
  avisoSinConfigurar,
  lineaHistorial,
  lineasImpacto,
  resumenCuenta,
  TEXTO_FORMULARIO_SE_CONSERVA,
  TEXTO_NO_DEDUCE,
  TEXTO_NO_EDITABLE_ESTADO,
  TEXTO_VERSION_CUENTA,
  TEXTO_YA_REGISTRADO,
  textoFaltaCuenta,
  textosHoja,
} from '../src/domain/capacidades';
import { ProveedorTema } from '../src/theme/tema';
import { colores } from '../src/theme/tokens';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

const NOMINA = 'c0000000-0000-4000-8000-00000000000b';
const AHORRO = 'c0000000-0000-4000-8000-00000000000c';
const ING = 'c0000000-0000-4000-8000-00000000000d';
const AHORA = () => new Date(2026, 9, 12, 10, 0, 0);
const MSG_B3 = 'Cuenta nómina ya no puede recibir ingresos. Se cambió mientras registrabas. El ingreso no se ha guardado: elige otra cuenta.';

const ETIQ: Record<string, [string, string]> = {
  PAGAR_GASTO: ['Pagar gastos', 'Aparece en «Pagado con»'],
  RECIBIR_INGRESO: ['Recibir ingresos', 'Aparece en «Cobrado en»'],
  TRANSFERIR_SALIDA: ['Enviar a otras cuentas tuyas', 'Aparece en «Desde»'],
  TRANSFERIR_ENTRADA: ['Recibir de otras cuentas tuyas', 'Aparece en «A»'],
  COMPRA_TARJETA: ['Compras con tarjeta', 'Aún no se usa en el registro'],
  DOMICILIAR: ['Domiciliar recibos', 'Aún no se usa en el registro'],
};
const nodoCap = (codigo: string, permitidas: string[], editable: boolean): CapacidadNodo =>
  ({ codigo, etiqueta: ETIQ[codigo][0], efecto: ETIQ[codigo][1], permitida: permitidas.includes(codigo), editable }) as CapacidadNodo;

function cuenta(id: string, nombre: string, permitidas: string[], o: Partial<CuentaCapacidades> = {}): CuentaCapacidades {
  const registro = ['PAGAR_GASTO', 'RECIBIR_INGRESO', 'TRANSFERIR_SALIDA', 'TRANSFERIR_ENTRADA'];
  return {
    cuenta_id: id, nombre, estado: 'ACTIVA', row_version: 1, origen_v3: false,
    sin_configurar: !registro.some((k) => permitidas.includes(k)),
    capacidades: registro.map((k) => nodoCap(k, permitidas, true)),
    otras: ['COMPRA_TARJETA', 'DOMICILIAR'].map((k) => nodoCap(k, permitidas, false)),
    ...o,
  };
}

const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;

/** Cliente con estado en memoria de cuentas y capacidades (el servidor es la autoridad). */
function fake(o: { cuentas?: CuentaCapacidades[]; impacto?: ImpactoCapacidad; historial?: EntradaHistorialCapacidad[]; cambio?: (id: string, cap: string, permitir: boolean, rv: number) => Respuesta<any> | null; ingreso?: () => Promise<any>; transferencia?: () => Promise<any> } = {}) {
  const st = { cuentas: [...(o.cuentas ?? [])] };
  const porId = (id: string) => st.cuentas.find((x) => x.cuenta_id === id)!;
  const elegibles = (cap: string) => st.cuentas.filter((x) => x.estado === 'ACTIVA' && x.capacidades.some((k) => k.codigo === cap && k.permitida)).map((x) => ({ cuenta_id: x.cuenta_id, nombre: x.nombre, moneda: 'EUR' }));
  const OP: Record<string, string> = { GASTO: 'PAGAR_GASTO', INGRESO: 'RECIBIR_INGRESO', TRANSFERENCIA_ORIGEN: 'TRANSFERIR_SALIDA', TRANSFERENCIA_DESTINO: 'TRANSFERIR_ENTRADA' };
  const cliente: ClienteApi = {
    ...clienteCategoriasStub([nodo({ id: 'trabajo', nombre: 'Trabajo', ambito: 'INGRESO' })]),
    registrarGastoPagado: jest.fn(async () => { throw new Error('no esperado'); }),
    cuentasPago: jest.fn(async () => ok({ cuentas: elegibles('PAGAR_GASTO').map((x) => ({ ...x, propuesta_financiacion: 'SELF_100' })) as CuentaPago[] })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasElegibles: jest.fn(async (operacion: any) => ok({ operacion, cuentas: elegibles(OP[operacion]) })) as any,
    registrarIngresoCobrado: jest.fn(o.ingreso ?? (async () => { throw new Error('no esperado'); })) as any,
    registrarTransferencia: jest.fn(o.transferencia ?? (async () => { throw new Error('no esperado'); })) as any,
    listarCapacidades: jest.fn(async () => ok({ cuentas: st.cuentas, sin_configurar: st.cuentas.filter((x) => x.sin_configurar && x.estado === 'ACTIVA').length })),
    cuentasSinConfigurar: jest.fn(async () => ok({ sin_configurar: st.cuentas.filter((x) => x.sin_configurar && x.estado === 'ACTIVA').length })),
    detalleCapacidades: jest.fn(async (id: string) => ok(porId(id))),
    historialCapacidades: jest.fn(async () => ok({ entradas: o.historial ?? [] })),
    impactoCapacidad: jest.fn(async () => ok(o.impacto ?? { plantillas: [], preferencias: [] })),
    cambiarCapacidad: jest.fn(async (id: string, cap: any, permitir: boolean, rv: number) => {
      const forzada = o.cambio?.(id, cap, permitir, rv);
      if (forzada) return forzada;
      const x = porId(id);
      const permitidas = [...x.capacidades, ...x.otras].filter((k) => (k.codigo === cap ? permitir : k.permitida)).map((k) => k.codigo);
      const nueva = cuenta(id, x.nombre, permitidas, { row_version: x.row_version + 1, origen_v3: x.origen_v3 });
      st.cuentas = st.cuentas.map((y) => (y.cuenta_id === id ? nueva : y));
      return ok({ cuenta: nueva, idempotente: false });
    }) as any,
  };
  return { cliente, st };
}

jest.setTimeout(30000);

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

async function montar(cliente: ClienteApi, esquema: 'light' | 'dark' = 'light') {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar={esquema}>
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await act(async () => undefined);
}
async function pulsar(id: string) {
  await act(async () => fireEvent.press(screen.getByTestId(id)));
}
async function abrirCuentas(cliente: ClienteApi, esquema: 'light' | 'dark' = 'light') {
  await montar(cliente, esquema);
  await pulsar('tab-MAS');
  await pulsar('mas-ajustes');
  await pulsar('ajustes-cuentas');
}
async function abrirDetalle(id: string) {
  await pulsar(`cap-fila-${id}`);
  await screen.findByTestId('cap-registro');
}
const plana = (st: any) => StyleSheet.flatten(st);
const textoDe = (id: string) => {
  const nodoTexto = screen.getByTestId(id);
  const partes: string[] = [];
  const recorrer = (x: any) => {
    if (typeof x === 'string') partes.push(x);
    else if (Array.isArray(x)) x.forEach(recorrer);
    else if (x?.props?.children !== undefined) recorrer(x.props.children);
  };
  recorrer(nodoTexto.props.children);
  return partes.join('');
};

// ------------------------------------------------------------------ dominio
test('dominio: resumen de A1, textos de A3/A4, impacto, B1, historial y B2', () => {
  expect(resumenCuenta(cuenta(NOMINA, 'Cuenta nómina', ['PAGAR_GASTO', 'RECIBIR_INGRESO', 'TRANSFERIR_SALIDA', 'TRANSFERIR_ENTRADA']))).toBe('Pagar · Recibir · Enviar · Recibir de tus cuentas');
  expect(resumenCuenta(cuenta(AHORRO, 'Ahorro', ['TRANSFERIR_SALIDA', 'TRANSFERIR_ENTRADA', 'DOMICILIAR']))).toBe('Enviar · Recibir de tus cuentas');
  expect(resumenCuenta(cuenta(ING, 'Cuenta ING', ['COMPRA_TARJETA'], { origen_v3: true }))).toBe('De V3 · aún no puede hacer nada');
  expect(resumenCuenta(cuenta(ING, 'Cuenta ING', []))).toBe('Aún no puede hacer nada');

  expect(textosHoja('RECIBIR_INGRESO', 'Ahorro', true)).toEqual({
    titulo: '¿Permitir recibir ingresos en Ahorro?', consecuencia: 'Desde ahora podrás elegirla en «Cobrado en» al registrar un ingreso.', boton: 'Permitir' });
  expect(textosHoja('PAGAR_GASTO', 'Cuenta nómina', false)).toEqual({
    titulo: '¿Dejar de pagar gastos con Cuenta nómina?', consecuencia: 'Dejará de aparecer en «Pagado con».', boton: 'Dejar de permitir' });
  expect(textosHoja('TRANSFERIR_ENTRADA', 'Tarjeta BBVA', false).consecuencia).toBe('Dejará de aparecer en «A».');
  expect(TEXTO_YA_REGISTRADO).toBe('Lo ya registrado no cambia.');

  const imp: ImpactoCapacidad = {
    plantillas: [{ plantilla_id: 'p1', nombre: 'Alquiler', enabled: true }],
    preferencias: [
      { preferencia_id: 'f1', enabled: true, categoria_id: 'hogar', categoria_nombre: 'Hogar', tercero_id: null, tercero_nombre: null },
      { preferencia_id: 'f2', enabled: false, categoria_id: null, categoria_nombre: null, tercero_id: null, tercero_nombre: null },
    ],
  };
  expect(lineasImpacto(imp, 'PAGAR_GASTO', 'Cuenta nómina')).toEqual([
    'Plantilla «Alquiler»', 'Preferencia «Gastos de Hogar → Cuenta nómina»', 'Preferencia «Todos los gastos → Cuenta nómina» (desactivada)']);

  expect(avisoSinConfigurar(cuenta(ING, 'Cuenta ING', [], { origen_v3: true }))).toBe(
    'Esta cuenta viene de V3 sin capacidades declaradas. Mientras no elijas qué puede hacer, no aparece al registrar. Lo que ya tiene registrado se conserva.');
  expect(avisoSinConfigurar(cuenta(ING, 'Cuenta ING', []))).not.toMatch(/V3/);

  expect(lineaHistorial({ cuando: '2026-10-12T09:00:00Z', accion: 'ACTIVAR', capacidad: 'PAGAR_GASTO', etiqueta: 'Pagar gastos', actor_tipo: 'USUARIO', actor_es_owner: true }))
    .toEqual({ titulo: 'Permitido: Pagar gastos', detalle: '12 oct 2026 · tú' });
  expect(lineaHistorial({ cuando: '2026-10-12T09:00:00Z', accion: 'DESACTIVAR', capacidad: 'PAGAR_GASTO', etiqueta: 'Pagar gastos', actor_tipo: 'USUARIO', actor_es_owner: true }).titulo)
    .toBe('Ya no permitido: Pagar gastos');
  expect(textoFaltaCuenta(0)).toBeNull();
  expect(textoFaltaCuenta(3)).toBe('¿Falta una cuenta? 3 sin configurar');
});

// ------------------------------------------------------------------ A1
test('A1: Ajustes › Cuentas con «Sin configurar» arriba y «Tus cuentas» con su resumen; sin alta de cuentas', async () => {
  const { cliente } = fake({
    cuentas: [
      cuenta(NOMINA, 'Cuenta nómina', ['PAGAR_GASTO', 'RECIBIR_INGRESO', 'TRANSFERIR_SALIDA', 'TRANSFERIR_ENTRADA']),
      cuenta(ING, 'Cuenta ING', [], { origen_v3: true }),
      cuenta(AHORRO, 'Ahorro', ['TRANSFERIR_SALIDA', 'TRANSFERIR_ENTRADA']),
    ],
  });
  await abrirCuentas(cliente);
  const sin = screen.getByTestId('cap-grupo-sin-configurar');
  expect(within(sin).getByText('SIN CONFIGURAR')).toBeTruthy();
  expect(within(sin).getByTestId(`cap-fila-${ING}-detalle`).props.children).toBe('De V3 · aún no puede hacer nada');
  const tus = screen.getByTestId('cap-grupo-cuentas');
  expect(within(tus).getByText('TUS CUENTAS')).toBeTruthy();
  expect(within(tus).getByTestId(`cap-fila-${NOMINA}-detalle`).props.children).toBe('Pagar · Recibir · Enviar · Recibir de tus cuentas');
  expect(within(tus).getByTestId(`cap-fila-${AHORRO}-detalle`).props.children).toBe('Enviar · Recibir de tus cuentas');
  expect(screen.queryByLabelText(/Nueva cuenta|Añadir cuenta/)).toBeNull();
  await pulsar('cap-atras');
  expect(screen.getByTestId('pantalla-ajustes')).toBeTruthy();
});

// ------------------------------------------------------------------ A2 / B1
test('A2/B1: cuatro interruptores con su efecto, «Otras» en solo lectura, aviso de V3 y sin deducir nada del tipo', async () => {
  const { cliente } = fake({ cuentas: [cuenta(ING, 'Cuenta ING', ['COMPRA_TARJETA'], { origen_v3: true })] });
  await abrirCuentas(cliente);
  await abrirDetalle(ING);
  for (const k of ['PAGAR_GASTO', 'RECIBIR_INGRESO', 'TRANSFERIR_SALIDA', 'TRANSFERIR_ENTRADA']) {
    expect(screen.getByTestId(`cap-${k}-interruptor`).props.value).toBe(false);
    expect(screen.getByTestId(`cap-${k}-efecto`).props.children).toBe(ETIQ[k][1]);
  }
  expect(screen.queryByTestId('cap-COMPRA_TARJETA-interruptor')).toBeNull();
  expect(screen.getByTestId('cap-COMPRA_TARJETA-estado').props.children).toBe('Sí');
  expect(screen.getByTestId('cap-DOMICILIAR-estado').props.children).toBe('No');
  expect(textoDe('cap-sin-configurar')).toMatch(/^Esta cuenta viene de V3 sin capacidades declaradas/);
  expect(screen.getByTestId('cap-no-deduce').props.children).toBe(TEXTO_NO_DEDUCE);
  // Negativo D-CAP-04: ninguna sugerencia, recomendación ni texto por tipo de cuenta.
  for (const t of [/suger/i, /recomend/i, /corriente/i, /efectivo/i, /tarjeta de crédito/i]) expect(screen.queryByText(t)).toBeNull();
  expect(screen.getByTestId('cap-abrir-historial')).toBeTruthy();
});

// ------------------------------------------------------------------ A3
test('A3: activar abre UNA hoja con «Lo ya registrado no cambia»; nada cambia hasta confirmar; Cancelar no escribe', async () => {
  const { cliente } = fake({ cuentas: [cuenta(AHORRO, 'Ahorro', ['TRANSFERIR_SALIDA'])] });
  await abrirCuentas(cliente);
  await abrirDetalle(AHORRO);
  await act(async () => fireEvent(screen.getByTestId('cap-RECIBIR_INGRESO-interruptor'), 'valueChange', true));
  expect(screen.getByTestId('cap-hoja-activar')).toBeTruthy();
  expect(screen.getByText('¿Permitir recibir ingresos en Ahorro?')).toBeTruthy();
  expect(screen.getByTestId('cap-hoja-consecuencia').props.children).toBe(
    'Desde ahora podrás elegirla en «Cobrado en» al registrar un ingreso. Lo ya registrado no cambia.');
  expect(screen.getByTestId('cap-RECIBIR_INGRESO-interruptor').props.value).toBe(false);
  expect(cliente.impactoCapacidad).not.toHaveBeenCalled();
  await pulsar('cap-hoja-cancelar');
  expect(cliente.cambiarCapacidad).not.toHaveBeenCalled();
  expect(screen.queryByTestId('cap-hoja-activar')).toBeNull();

  await act(async () => fireEvent(screen.getByTestId('cap-RECIBIR_INGRESO-interruptor'), 'valueChange', true));
  await pulsar('cap-hoja-confirmar');
  expect(cliente.cambiarCapacidad).toHaveBeenCalledTimes(1);
  expect(cliente.cambiarCapacidad).toHaveBeenCalledWith(AHORRO, 'RECIBIR_INGRESO', true, 1);
  expect(screen.getByTestId('cap-RECIBIR_INGRESO-interruptor').props.value).toBe(true);
  expect(screen.queryByTestId('cap-hoja-activar')).toBeNull();
  // Siguiente cambio con la versión nueva (PD-1).
  await act(async () => fireEvent(screen.getByTestId('cap-PAGAR_GASTO-interruptor'), 'valueChange', true));
  await pulsar('cap-hoja-confirmar');
  expect(cliente.cambiarCapacidad).toHaveBeenLastCalledWith(AHORRO, 'PAGAR_GASTO', true, 2);
});

// ------------------------------------------------------------------ A4
test('A4: desactivar lista antes de confirmar lo que deja de funcionar; no se puede confirmar sin el impacto', async () => {
  const impacto: ImpactoCapacidad = {
    plantillas: [{ plantilla_id: 'p1', nombre: 'Alquiler', enabled: true }],
    preferencias: [{ preferencia_id: 'f1', enabled: true, categoria_id: 'hogar', categoria_nombre: 'Hogar', tercero_id: null, tercero_nombre: null }],
  };
  let soltar: () => void = () => undefined;
  const { cliente } = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['PAGAR_GASTO'])], impacto });
  const original = cliente.impactoCapacidad;
  cliente.impactoCapacidad = jest.fn((id: string, cap: any) => new Promise((r) => { soltar = () => r(original(id, cap) as any); })) as any;
  await abrirCuentas(cliente);
  await abrirDetalle(NOMINA);
  await act(async () => fireEvent(screen.getByTestId('cap-PAGAR_GASTO-interruptor'), 'valueChange', false));
  expect(screen.getByTestId('cap-hoja-desactivar')).toBeTruthy();
  expect(screen.getByText('¿Dejar de pagar gastos con Cuenta nómina?')).toBeTruthy();
  expect(screen.getByTestId('cap-hoja-consecuencia').props.children).toBe('Dejará de aparecer en «Pagado con». Lo ya registrado no cambia.');
  expect(screen.getByTestId('cap-impacto-cargando')).toBeTruthy();
  expect(screen.getByTestId('cap-hoja-confirmar').props.accessibilityState.disabled).toBe(true);
  await act(async () => soltar());
  await waitFor(() => expect(screen.getByTestId('cap-impacto')).toBeTruthy());
  expect(cliente.impactoCapacidad).toHaveBeenCalledWith(NOMINA, 'PAGAR_GASTO');
  expect(screen.getByTestId('cap-impacto-0').props.children).toBe('· Plantilla «Alquiler»');
  expect(screen.getByTestId('cap-impacto-1').props.children).toBe('· Preferencia «Gastos de Hogar → Cuenta nómina»');
  expect(screen.getByText('Quedarán como «No disponible» hasta que elijas otra cuenta o vuelvas a permitirlo.')).toBeTruthy();
  expect(screen.getByTestId('cap-hoja-confirmar').props.accessibilityState.disabled).toBe(false);
  await pulsar('cap-hoja-confirmar');
  expect(cliente.cambiarCapacidad).toHaveBeenCalledWith(NOMINA, 'PAGAR_GASTO', false, 1);
  expect(screen.getByTestId('cap-PAGAR_GASTO-interruptor').props.value).toBe(false);
});

// ------------------------------------------------------------------ conflicto de versión y PD-2
test('Conflicto de versión: aviso sin pisar y recarga del estado actual del servidor', async () => {
  const f = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['PAGAR_GASTO'])], cambio: () => ({ tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: 'x' }) });
  await abrirCuentas(f.cliente);
  await abrirDetalle(NOMINA);
  // Otro dispositivo activó RECIBIR_INGRESO entre tanto.
  f.st.cuentas = [cuenta(NOMINA, 'Cuenta nómina', ['PAGAR_GASTO', 'RECIBIR_INGRESO'], { row_version: 2 })];
  await act(async () => fireEvent(screen.getByTestId('cap-TRANSFERIR_SALIDA-interruptor'), 'valueChange', true));
  await pulsar('cap-hoja-confirmar');
  expect(f.cliente.cambiarCapacidad).toHaveBeenCalledTimes(1); // sin reintento automático
  expect(textoDe('cap-aviso')).toBe(TEXTO_VERSION_CUENTA);
  expect(screen.getByTestId('cap-RECIBIR_INGRESO-interruptor').props.value).toBe(true);
  expect(screen.getByTestId('cap-TRANSFERIR_SALIDA-interruptor').props.value).toBe(false);
});

test('PD-2: cuenta cerrada en solo lectura (interruptores deshabilitados y aviso)', async () => {
  const { cliente } = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['PAGAR_GASTO'], { estado: 'CERRADA' })] });
  await abrirCuentas(cliente);
  await abrirDetalle(NOMINA);
  expect(textoDe('cap-no-editable')).toBe(TEXTO_NO_EDITABLE_ESTADO);
  expect(screen.getByTestId('cap-PAGAR_GASTO-interruptor').props.disabled).toBe(true);
});

// ------------------------------------------------------------------ B4
test('B4: historial de la auditoría (qué, cuándo y quién) y pie; sin entradas inventadas', async () => {
  const historial: EntradaHistorialCapacidad[] = [
    { cuando: '2026-10-12T10:00:00Z', accion: 'ACTIVAR', capacidad: 'TRANSFERIR_ENTRADA', etiqueta: 'Recibir de otras cuentas tuyas', actor_tipo: 'USUARIO', actor_es_owner: true },
    { cuando: '2026-10-12T09:00:00Z', accion: 'ACTIVAR', capacidad: 'PAGAR_GASTO', etiqueta: 'Pagar gastos', actor_tipo: 'USUARIO', actor_es_owner: true },
  ];
  const { cliente } = fake({ cuentas: [cuenta(NOMINA, 'Tarjeta BBVA', ['PAGAR_GASTO', 'TRANSFERIR_ENTRADA'])], historial });
  await abrirCuentas(cliente);
  await abrirDetalle(NOMINA);
  await pulsar('cap-abrir-historial');
  await screen.findByTestId('cap-historial-lista');
  expect(within(screen.getByTestId('cap-historial-0')).getByText('Permitido: Recibir de otras cuentas tuyas')).toBeTruthy();
  expect(within(screen.getByTestId('cap-historial-1')).getByText('12 oct 2026 · tú')).toBeTruthy();
  expect(screen.queryByTestId('cap-historial-2')).toBeNull();
  expect(screen.getByTestId('cap-historial-pie')).toBeTruthy();
  expect(screen.queryByText(/V3/)).toBeNull();
  await pulsar('cap-historial-atras');
  expect(screen.getByTestId('cap-registro')).toBeTruthy();
});

// ------------------------------------------------------------------ oscuro
test('Modo oscuro: lista y detalle con los tokens del tema oscuro', async () => {
  const { cliente } = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['PAGAR_GASTO'])] });
  await abrirCuentas(cliente, 'dark');
  expect(plana(screen.getByTestId('pantalla-cuentas').props.style).backgroundColor).toBe(colores.dark.background);
  await abrirDetalle(NOMINA);
  expect(plana(screen.getByTestId('cap-detalle').props.style).backgroundColor).toBe(colores.dark.background);
  expect(plana(screen.getByTestId('cap-registro').props.style).backgroundColor).toBe(colores.dark.surfacePrimary);
});

// ------------------------------------------------------------------ B2 / B3 en el registro
test('B2: «¿Falta una cuenta? N sin configurar ›» en «Cobrado en»; abre Cuentas y al volver conserva lo escrito y recarga', async () => {
  const f = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['RECIBIR_INGRESO']), cuenta(ING, 'Cuenta ING', [], { origen_v3: true })] });
  await montar(f.cliente);
  await pulsar('accion-registrar');
  await pulsar('tipo-INGRESO');
  await screen.findByTestId(`cuenta-${NOMINA}`);
  fireEvent.changeText(screen.getByTestId('campo-importe'), '1500');
  expect(await screen.findByText('¿Falta una cuenta? 1 sin configurar ›')).toBeTruthy();
  await pulsar('falta-cuenta');
  expect(screen.getByTestId('panel-cuentas')).toBeTruthy();
  await abrirDetalle(ING);
  await act(async () => fireEvent(screen.getByTestId('cap-RECIBIR_INGRESO-interruptor'), 'valueChange', true));
  await pulsar('cap-hoja-confirmar');
  await pulsar('cap-detalle-atras');
  expect(screen.getByTestId('cap-atras').props.accessibilityLabel).toBe('Atrás: Nuevo ingreso');
  await pulsar('cap-atras');
  expect(screen.queryByTestId('panel-cuentas')).toBeNull();
  expect(screen.getByTestId('campo-importe').props.value).toBe('1500');
  expect(await screen.findByTestId(`cuenta-${ING}`)).toBeTruthy(); // ya puede cobrar
  await waitFor(() => expect(screen.queryByTestId('falta-cuenta')).toBeNull()); // N = 0: sin aviso
});

test('B2: el aviso sale al final de «Desde» y de «A» y no sale con N = 0', async () => {
  const f = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['TRANSFERIR_SALIDA']), cuenta(AHORRO, 'Ahorro', ['TRANSFERIR_ENTRADA']), cuenta(ING, 'Cuenta ING', [])] });
  await montar(f.cliente);
  await pulsar('accion-registrar');
  await pulsar('tipo-TRANSFERENCIA');
  await screen.findByTestId(`desde-${NOMINA}`);
  expect(await screen.findByTestId('desde-falta-cuenta')).toBeTruthy();
  expect(screen.getByTestId('a-falta-cuenta')).toBeTruthy();
});

test('B2: con N = 0 no hay aviso en «Pagado con»', async () => {
  const f = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['PAGAR_GASTO'])] });
  await montar(f.cliente);
  await pulsar('accion-registrar');
  await pulsar('tipo-GASTO');
  await screen.findByTestId(`cuenta-${NOMINA}`);
  await act(async () => undefined);
  expect(screen.queryByTestId('falta-cuenta')).toBeNull();
  expect(screen.queryByText(/Falta una cuenta/)).toBeNull();
});

test('B3: CUENTA_SIN_CAPACIDAD al guardar un ingreso: mensaje, formulario conservado y la cuenta ya no está ni elegida', async () => {
  const f = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['RECIBIR_INGRESO']), cuenta(AHORRO, 'Ahorro', ['RECIBIR_INGRESO'])] });
  (f.cliente.registrarIngresoCobrado as jest.Mock).mockImplementation(async () => {
    f.st.cuentas = [cuenta(NOMINA, 'Cuenta nómina', []), cuenta(AHORRO, 'Ahorro', ['RECIBIR_INGRESO'])];
    return { tipo: 'RECHAZADO', codigo: 'CUENTA_SIN_CAPACIDAD', mensaje: MSG_B3, detalle: { cuenta_id: NOMINA, operacion: 'INGRESO' } };
  });
  await montar(f.cliente);
  await pulsar('accion-registrar');
  await pulsar('tipo-INGRESO');
  await screen.findByTestId(`cuenta-${NOMINA}`);
  fireEvent.changeText(screen.getByTestId('campo-importe'), '1500');
  fireEvent.press(screen.getByTestId('campo-categoria'));
  fireEvent.press(screen.getByTestId('cat-trabajo'));
  fireEvent.press(screen.getByTestId('presupuestable-false'));
  fireEvent.press(screen.getByTestId(`cuenta-${NOMINA}`));
  await pulsar('registrar');
  expect(screen.getByText(`${MSG_B3} ${TEXTO_FORMULARIO_SE_CONSERVA}`)).toBeTruthy();
  await waitFor(() => expect(screen.queryByTestId(`cuenta-${NOMINA}`)).toBeNull());
  expect(screen.getByTestId(`cuenta-${AHORRO}`).props.accessibilityState.checked).toBe(false); // ninguna se rellena sola
  expect(screen.getByTestId('campo-importe').props.value).toBe('1500');
  expect(screen.getByTestId('registrar').props.accessibilityState.disabled).toBe(true);
});

test('B3: CUENTA_SIN_CAPACIDAD en «Entre cuentas»: la cuenta de destino deja de estar elegida y el resto se conserva', async () => {
  const msg = 'Ahorro ya no puede recibir de otras cuentas tuyas. Se cambió mientras registrabas. La transferencia no se ha guardado: elige otra cuenta.';
  const f = fake({ cuentas: [cuenta(NOMINA, 'Cuenta nómina', ['TRANSFERIR_SALIDA']), cuenta(AHORRO, 'Ahorro', ['TRANSFERIR_ENTRADA'])] });
  (f.cliente.registrarTransferencia as jest.Mock).mockImplementation(async () => {
    f.st.cuentas = [cuenta(NOMINA, 'Cuenta nómina', ['TRANSFERIR_SALIDA']), cuenta(AHORRO, 'Ahorro', [])];
    return { tipo: 'RECHAZADO', codigo: 'CUENTA_SIN_CAPACIDAD', mensaje: msg };
  });
  await montar(f.cliente);
  await pulsar('accion-registrar');
  await pulsar('tipo-TRANSFERENCIA');
  await screen.findByTestId(`desde-${NOMINA}`);
  fireEvent.press(screen.getByTestId(`desde-${NOMINA}`));
  fireEvent.press(screen.getByTestId(`a-${AHORRO}`));
  fireEvent.changeText(screen.getByTestId('campo-importe'), '200');
  await pulsar('registrar');
  expect(screen.getByText(`${msg} ${TEXTO_FORMULARIO_SE_CONSERVA}`)).toBeTruthy();
  await waitFor(() => expect(screen.queryByTestId(`a-${AHORRO}`)).toBeNull());
  expect(screen.getByTestId(`desde-${NOMINA}`).props.accessibilityState.checked).toBe(true);
  expect(screen.getByTestId('campo-importe').props.value).toBe('200');
});
