// ============================================================
// GAPTO MOBILE 2027
// Fichero: edicion_hecho.test.tsx
// Ruta: mobile/__tests__/edicion_hecho.test.tsx
// Descripción: «Corregir» y «Anular por duplicado» (F05-06 M1; lámina EDIT-HECHO v0.1; CONTRATO_M1 v0.1 §2; F05 §61.2). Dominio puro (cambios antes → después, lo que falta, payloads con SOLO lo que cambia y `error_de_registro` explícito, declaración sin defecto) y pantallas en claro y oscuro: «Más» del detalle con la elegibilidad del servidor (atenuada con su motivo y sin envío), anular con declaración y motivo obligatorios («Otro…» con texto), ANULADO tras confirmar y la lista releída, misma identidad tras un fallo de conexión; corregir con el formulario precargado, «Editado» con el valor anterior, revisión del impacto, motivo obligatorio, conflicto de versión sin pisar (B3) y registro no corregible explicado. Sin swipe.
// Versión: 0.1.0 (F05-06 M1)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, DetalleActividad, EdicionHecho, FilaActividad } from '../src/api/cliente';
import { cambiosEdicion, componerAnulacion, componerCorreccion, faltaEdicion, formularioInicial } from '../src/domain/edicion';
import { ActividadScreen } from '../src/screens/ActividadScreen';
import { CorregirHechoScreen } from '../src/screens/CorregirHechoScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 12, 10, 0, 0);
const SI = { disponible: true, codigo: null, motivo: null };
const NO = (codigo: string, motivo: string) => ({ disponible: false, codigo, motivo });

const PAGO: EdicionHecho = {
  hecho_id: 'compra', row_version: 3, estado: 'ACTIVO', tipo: 'GASTO', importe: '48.72', fecha: '2026-10-10', moneda: 'EUR',
  origen_v3: false, anulado: null,
  movimientos: [{ movimiento_id: 'm1', row_version: 2, pata: 'SALIDA', cuenta: { id: 'bbva', nombre: 'Tarjeta BBVA' }, importe: '48.72', fecha: '2026-10-10' }],
  acciones: { corregir: SI, anular_duplicado: SI },
};
const TRANSF: EdicionHecho = {
  ...PAGO, hecho_id: 'tr', tipo: 'TRANSFERENCIA', importe: '500.00',
  movimientos: [
    { movimiento_id: 's', row_version: 1, pata: 'SALIDA', cuenta: { id: 'nomina', nombre: 'Cuenta nómina' }, importe: '500.00', fecha: '2026-10-10' },
    { movimiento_id: 'e', row_version: 4, pata: 'ENTRADA', cuenta: { id: 'ahorro', nombre: 'Ahorro' }, importe: '500.00', fecha: '2026-10-10' },
  ],
};
const CUENTAS = [{ cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', moneda: 'EUR' }, { cuenta_id: 'efectivo', nombre: 'Efectivo', moneda: 'EUR' }];

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => {
  n = 0;
});

function envolver(ui: React.ReactElement, forzar?: 'dark' | 'light') {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema forzar={forzar}>{ui}</ProveedorTema>
    </SafeAreaProvider>,
  );
}

// ==================================================================
// Dominio
// ==================================================================
describe('dominio', () => {
  test('cambios antes → después y payload de OP-21P con SOLO lo que cambia', () => {
    const f = { ...formularioInicial(PAGO), importe: '47,82' };
    expect(cambiosEdicion(PAGO, f)).toEqual([{ campo: 'importe', antes: '48.72', despues: '47.82' }]);
    expect(componerCorreccion(PAGO, f, '  Importe mal tecleado ', 'i1')).toEqual({ ruta: 'PAGO', payload: {
      intencion_id: 'i1', row_version: 3, movimiento_row_version: 2, motivo: 'Importe mal tecleado', error_de_registro: true, importe: '47.82' } });
    const g = { ...formularioInicial(PAGO), fecha: '2026-10-09', cuentaSalida: 'efectivo' };
    expect(componerCorreccion(PAGO, g, 'Fecha equivocada', 'i2').payload).toEqual({
      intencion_id: 'i2', row_version: 3, movimiento_row_version: 2, motivo: 'Fecha equivocada', error_de_registro: true,
      fecha: '2026-10-09', cuenta_id: 'efectivo' });
  });

  test('transferencia: versiones de las dos patas y cuentas por pata', () => {
    const f = { ...formularioInicial(TRANSF), cuentaEntrada: 'otra' };
    expect(componerCorreccion(TRANSF, f, 'Otro dato mal elegido', 'i')).toEqual({ ruta: 'TRANSFERENCIA', payload: {
      intencion_id: 'i', row_version: 3, movimientos_row_version: { s: 1, e: 4 }, motivo: 'Otro dato mal elegido', error_de_registro: true,
      cuenta_destino_id: 'otra' } });
    expect(faltaEdicion(TRANSF, { ...f, cuentaEntrada: 'nomina' }, null)).toEqual(['dos cuentas distintas']);
  });

  test('lo que falta: algún cambio, importe válido y motivo', () => {
    expect(faltaEdicion(PAGO, formularioInicial(PAGO), null)).toEqual(['algún cambio']);
    expect(faltaEdicion(PAGO, { ...formularioInicial(PAGO), importe: '0' }, null)).toEqual(['un importe mayor que cero']);
    expect(faltaEdicion(PAGO, { ...formularioInicial(PAGO), importe: '47,82' }, '  ')).toEqual(['el motivo']);
  });

  test('anulación: la declaración viaja tal cual (sin defecto) con las versiones de cada movimiento', () => {
    expect(componerAnulacion(TRANSF, ' Lo registré dos veces ', true, 'i')).toEqual({
      intencion_id: 'i', row_version: 3, movimientos_row_version: { s: 1, e: 4 }, motivo: 'Lo registré dos veces', duplicado_declarado: true });
    expect(componerAnulacion(PAGO, 'x', false, 'i').duplicado_declarado).toBe(false);
  });
});

// ==================================================================
// «Más» en el detalle de la Actividad
// ==================================================================
const FILA: FilaActividad = {
  id: 'compra', fecha_hecho: '2026-10-10', tipo: 'GASTO', nota: 'Compra semanal', moneda: 'EUR', importe_total: '48.72',
  tercero: { id: 'aldi', nombre: 'ALDI', enabled: true }, categoria: null, varias: false, contexto: null,
  cuentas: [{ cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA', tu_parte: '48.72',
  pendiente: null, maestros_desactivados: [], devolucion_de: null, abono: null,
};
const DETALLE: DetalleActividad = { ...FILA, presupuestable: true, magnitudes: [], devoluciones: null } as DetalleActividad;

function clienteActividad(edicion: EdicionHecho, o: Partial<ClienteApi> = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    registrarGastoPagado: jest.fn(), cuentasPago: jest.fn(), gastoMes: jest.fn(),
    actividad: jest.fn(async () => ({ tipo: 'OK', datos: { filas: [FILA], siguiente: null, total: 1 } }) as any),
    detalleActividad: jest.fn(async () => ({ tipo: 'OK', datos: DETALLE }) as any),
    repartoDeHecho: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' }) as any),
    edicionHecho: jest.fn(async () => ({ tipo: 'OK', datos: edicion }) as any),
    ...o,
  } as ClienteApi;
}

async function abrirMas(c: ClienteApi, onCorregirHecho = jest.fn(), forzar?: 'dark') {
  envolver(<ActividadScreen cliente={c} ahora={AHORA} nuevoId={nuevoId} onCorregirHecho={onCorregirHecho} />, forzar);
  fireEvent.press(await screen.findByTestId('fila-compra'));
  const mas = await screen.findByTestId('detalle-mas');
  await act(async () => fireEvent.press(mas));
  await screen.findByTestId('hoja-mas-hecho');
  return onCorregirHecho;
}

describe('«Más» del detalle', () => {
  test('sin `onCorregirHecho` no hay «Más» (sigue el texto previo)', async () => {
    envolver(<ActividadScreen cliente={clienteActividad(PAGO)} ahora={AHORA} nuevoId={nuevoId} />);
    fireEvent.press(await screen.findByTestId('fila-compra'));
    await screen.findByTestId('hoja-detalle');
    expect(screen.queryByTestId('detalle-mas')).toBeNull();
  });

  test('«Corregir» abre la tarea con el hecho y su título', async () => {
    const c = clienteActividad(PAGO);
    const onCorregirHecho = await abrirMas(c);
    expect(c.edicionHecho).toHaveBeenCalledWith('compra');
    fireEvent.press(screen.getByTestId('mas-corregir'));
    expect(onCorregirHecho).toHaveBeenCalledWith('compra', expect.stringMatching(/ALDI|Compra semanal/));
  });

  test('lo no admitido se ve atenuado con su motivo y no se envía', async () => {
    const motivo = 'Registro migrado de la versión anterior (V3): en esta versión no se corrige ni se anula desde la app.';
    const c = clienteActividad({ ...PAGO, origen_v3: true, acciones: { corregir: NO('ORIGEN_IMPORTADO', motivo), anular_duplicado: NO('ORIGEN_IMPORTADO', motivo) } },
      { anularDuplicado: jest.fn() as any });
    const onCorregirHecho = await abrirMas(c, jest.fn(), 'dark');
    for (const id of ['mas-corregir', 'mas-anular']) {
      expect(screen.getByTestId(id)).toBeDisabled();
      expect(screen.getByTestId(`${id}-motivo`)).toHaveTextContent(motivo);
      fireEvent.press(screen.getByTestId(id));
    }
    expect(onCorregirHecho).not.toHaveBeenCalled();
    expect(screen.queryByTestId('hoja-anular-duplicado')).toBeNull();
    expect(c.anularDuplicado).not.toHaveBeenCalled();
  });

  test('anular exige la declaración y el motivo; «Otro…» con texto; ANULADO y lista releída', async () => {
    const anular = jest.fn(async (_id: string, pl: any) => ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, hecho_id: 'compra', row_version: 4, estado: 'ANULADO', idempotente: false } }) as any);
    const c = clienteActividad(PAGO, { anularDuplicado: anular });
    await abrirMas(c);
    fireEvent.press(screen.getByTestId('mas-anular'));
    expect(screen.getByTestId('anular-efecto')).toHaveTextContent(/No se puede deshacer/);
    expect(screen.getByTestId('anular-declaracion').props.accessibilityState.checked).toBe(false); // sin marcar al entrar
    expect(screen.getByTestId('anular-confirmar')).toBeDisabled();
    fireEvent.press(screen.getByTestId('anular-motivo-0'));
    expect(screen.getByTestId('anular-confirmar')).toBeDisabled(); // falta la declaración
    fireEvent.press(screen.getByTestId('anular-declaracion'));
    fireEvent.press(screen.getByTestId('anular-motivo-otro'));
    expect(screen.getByTestId('anular-confirmar')).toBeDisabled(); // «Otro…» sin texto
    fireEvent.changeText(screen.getByTestId('anular-motivo-texto'), 'Lo metí desde el móvil y el ordenador');
    const lecturas = (c.actividad as jest.Mock).mock.calls.length;
    await act(async () => fireEvent.press(screen.getByTestId('anular-confirmar')));
    expect(anular.mock.calls[0]).toEqual(['compra', { intencion_id: expect.any(String), row_version: 3, movimientos_row_version: { m1: 2 },
      motivo: 'Lo metí desde el móvil y el ordenador', duplicado_declarado: true }]);
    expect(await screen.findByTestId('anulado-texto')).toHaveTextContent(/ya no cuenta/);
    await waitFor(() => expect((c.actividad as jest.Mock).mock.calls.length).toBeGreaterThan(lecturas));
  });

  test('anular: tras un fallo de conexión el reintento usa la MISMA intención; un rechazo se explica', async () => {
    const anular = jest.fn()
      .mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro.' })
      .mockResolvedValueOnce({ tipo: 'RECHAZADO', codigo: 'HECHO_CON_REALIDAD_ASOCIADA', mensaje: 'No se puede anular: tiene una devolución u otra operación registrada.' });
    await abrirMas(clienteActividad(PAGO, { anularDuplicado: anular as any }));
    fireEvent.press(screen.getByTestId('mas-anular'));
    fireEvent.press(screen.getByTestId('anular-declaracion'));
    fireEvent.press(screen.getByTestId('anular-motivo-1'));
    await act(async () => fireEvent.press(screen.getByTestId('anular-confirmar')));
    expect(await screen.findByTestId('anular-error')).toHaveTextContent(/no se anulará dos veces/);
    await act(async () => fireEvent.press(screen.getByTestId('anular-confirmar')));
    expect(anular.mock.calls[1][1].intencion_id).toBe(anular.mock.calls[0][1].intencion_id);
    expect(await screen.findByTestId('anular-error')).toHaveTextContent(/tiene una devolución/);
  });
});

// ==================================================================
// Corregir
// ==================================================================
function clienteCorregir(edicion: EdicionHecho, o: Partial<ClienteApi> = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    edicionHecho: jest.fn(async () => ({ tipo: 'OK', datos: edicion }) as any),
    cuentasElegibles: jest.fn(async (op: string) => ({ tipo: 'OK', datos: { operacion: op, cuentas: CUENTAS } }) as any),
    ...o,
  } as ClienteApi;
}

function montarCorregir(c: ClienteApi, hechoId = 'compra', forzar?: 'dark') {
  const onCerrar = jest.fn();
  envolver(<CorregirHechoScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} hechoId={hechoId} titulo="Compra semanal" onCerrar={onCerrar} />, forzar);
  return onCerrar;
}

describe('Corregir', () => {
  test('A2/A3: precargado, «Editado» con el valor anterior, revisión del impacto, motivo obligatorio y guardar', async () => {
    const corregir = jest.fn(async (_id: string, pl: any) => ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, hecho_id: 'compra', row_version: 4, estado: 'ACTIVO', idempotente: false } }) as any);
    const onCerrar = montarCorregir(clienteCorregir(PAGO, { corregirPago: corregir }));
    expect(await screen.findByTestId('corregir-hecho-solo-errores')).toHaveTextContent(/nunca fueron ciertos/);
    expect(screen.getByTestId('corregir-hecho-importe').props.value).toBe('48,72');
    expect(screen.getByTestId('corregir-hecho-cuenta-salida-bbva').props.accessibilityState.checked).toBe(true);
    expect(screen.getByTestId('corregir-hecho-revisar')).toBeDisabled(); // sin cambios
    fireEvent.changeText(screen.getByTestId('corregir-hecho-importe'), '47,82');
    expect(screen.getByTestId('corregir-hecho-editado-importe')).toHaveTextContent(/Editado · antes 48,72 €/);
    fireEvent.press(screen.getByTestId('corregir-hecho-revisar'));
    expect(screen.getByTestId('corregir-hecho-cambio-importe')).toHaveTextContent(/48,72 € → 47,82 €/);
    expect(screen.getByTestId('corregir-hecho-impacto-SALIDA')).toHaveTextContent(/−48,72 € → −47,82 €/);
    expect(screen.getByTestId('corregir-hecho-impacto-resultado')).toHaveTextContent(/Gastos −0,90 €/);
    expect(screen.getByTestId('corregir-hecho-guardar')).toBeDisabled(); // motivo obligatorio
    fireEvent.press(screen.getByTestId('corregir-hecho-motivo-0'));
    await act(async () => fireEvent.press(screen.getByTestId('corregir-hecho-guardar')));
    expect(corregir.mock.calls[0]).toEqual(['compra', { intencion_id: expect.any(String), row_version: 3, movimiento_row_version: 2,
      motivo: 'Importe mal tecleado', error_de_registro: true, importe: '47.82' }]);
    fireEvent.press(await screen.findByTestId('corregir-hecho-listo'));
    expect(onCerrar).toHaveBeenCalledWith(true);
  });

  test('B3: conflicto de versión sin pisar; «Recargar y volver a corregir» relee', async () => {
    const ahora = { ...PAGO, row_version: 4, importe: '47.82' };
    const leer = jest.fn().mockResolvedValueOnce({ tipo: 'OK', datos: PAGO }).mockResolvedValue({ tipo: 'OK', datos: ahora });
    const corregir = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA',
      mensaje: 'Este registro ha cambiado mientras lo corregías. Tus cambios no se han aplicado.', detalle: { edicion: ahora } }) as any);
    montarCorregir(clienteCorregir(PAGO, { edicionHecho: leer as any, corregirPago: corregir }), 'compra', 'dark');
    fireEvent.press(await screen.findByTestId('corregir-hecho-fecha-2026-10-11'));
    fireEvent.press(screen.getByTestId('corregir-hecho-revisar'));
    fireEvent.press(screen.getByTestId('corregir-hecho-motivo-1'));
    await act(async () => fireEvent.press(screen.getByTestId('corregir-hecho-guardar')));
    expect(await screen.findByTestId('corregir-hecho-cambiado')).toHaveTextContent(/ha cambiado mientras lo corregías/);
    expect(screen.getByTestId('corregir-hecho-ahora-importe')).toHaveTextContent(/47,82 €/);
    expect(screen.getByTestId('corregir-hecho-querias-fecha')).toHaveTextContent(/10 oct 2026 → 11 oct 2026/);
    await act(async () => fireEvent.press(screen.getByTestId('corregir-hecho-recargar')));
    await waitFor(() => expect(screen.getByTestId('corregir-hecho-importe').props.value).toBe('47,82'));
    expect(leer).toHaveBeenCalledTimes(2);
  });

  test('sin respuesta: «Reintentar» con la MISMA intención; un rechazo del servidor se explica', async () => {
    const corregir = jest.fn()
      .mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro.' })
      .mockResolvedValueOnce({ tipo: 'RECHAZADO', codigo: 'OPERACION_NO_PERMITIDA_EN_ESTADO', mensaje: 'Corregir es solo para datos que nunca fueron ciertos.' });
    montarCorregir(clienteCorregir(PAGO, { corregirPago: corregir as any }));
    fireEvent.changeText(await screen.findByTestId('corregir-hecho-importe'), '40');
    fireEvent.press(screen.getByTestId('corregir-hecho-revisar'));
    fireEvent.press(screen.getByTestId('corregir-hecho-motivo-otro'));
    expect(screen.getByTestId('corregir-hecho-guardar')).toBeDisabled();
    fireEvent.changeText(screen.getByTestId('corregir-hecho-motivo-texto'), 'Puse los céntimos mal');
    await act(async () => fireEvent.press(screen.getByTestId('corregir-hecho-guardar')));
    expect(await screen.findByTestId('corregir-hecho-indeterminado')).toHaveTextContent(/no se corregirá dos veces/);
    expect(screen.getByTestId('corregir-hecho-guardar')).toHaveTextContent('Reintentar');
    await act(async () => fireEvent.press(screen.getByTestId('corregir-hecho-guardar')));
    expect(corregir.mock.calls[1][1].intencion_id).toBe(corregir.mock.calls[0][1].intencion_id);
    expect(await screen.findByTestId('corregir-hecho-error')).toHaveTextContent(/nunca fueron ciertos/);
  });

  test('transferencia: cuentas de salida y entrada; la misma cuenta en las dos no se revisa', async () => {
    const corregir = jest.fn(async (_id: string, pl: any) => ({ tipo: 'OK', datos: { intencion_id: pl.intencion_id, hecho_id: 'tr', row_version: 4, estado: 'ACTIVO', idempotente: false } }) as any);
    const c = clienteCorregir(TRANSF, {
      corregirTransferencia: corregir,
      cuentasElegibles: jest.fn(async (op: string) => ({ tipo: 'OK', datos: { operacion: op, cuentas: [
        { cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR' }, { cuenta_id: 'ahorro', nombre: 'Ahorro', moneda: 'EUR' }] } }) as any),
    });
    montarCorregir(c, 'tr');
    fireEvent.press(await screen.findByTestId('corregir-hecho-cuenta-entrada-nomina'));
    expect(screen.getByTestId('corregir-hecho-faltan')).toHaveTextContent(/dos cuentas distintas/);
    expect(screen.getByTestId('corregir-hecho-revisar')).toBeDisabled();
    fireEvent.press(screen.getByTestId('corregir-hecho-cuenta-entrada-ahorro'));
    fireEvent.changeText(screen.getByTestId('corregir-hecho-importe'), '450');
    fireEvent.press(screen.getByTestId('corregir-hecho-revisar'));
    expect(screen.queryByTestId('corregir-hecho-impacto-resultado')).toBeNull(); // una transferencia no cambia el Resultado
    fireEvent.press(screen.getByTestId('corregir-hecho-motivo-0'));
    await act(async () => fireEvent.press(screen.getByTestId('corregir-hecho-guardar')));
    expect(corregir.mock.calls[0][1]).toEqual({ intencion_id: expect.any(String), row_version: 3, movimientos_row_version: { s: 1, e: 4 },
      motivo: 'Importe mal tecleado', error_de_registro: true, importe: '450.00' });
  });

  test('no corregible: se dice por qué y no hay formulario', async () => {
    const motivo = 'Tiene reparto con otras personas: en esta versión no se corrige aquí. El reparto se corrige con «Corregir reparto».';
    montarCorregir(clienteCorregir({ ...PAGO, acciones: { ...PAGO.acciones, corregir: NO('REPARTO', motivo) } }));
    expect(await screen.findByTestId('corregir-hecho-no-corregible')).toHaveTextContent(motivo);
    expect(screen.queryByTestId('corregir-hecho-form')).toBeNull();
  });
});
