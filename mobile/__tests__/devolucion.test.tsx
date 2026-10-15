// ============================================================
// GAPTO MOBILE 2027
// Fichero: devolucion.test.tsx
// Ruta: mobile/__tests__/devolucion.test.tsx
// Descripción: Devolución contextual (F05-06 M2-B §B2; lámina DEV v0.1). Dominio puro (límite, neto derivado, propuesta P-DEV-01, títulos y etiquetas de la Actividad), formulario A1 (origen fijo con lo devuelto y lo que queda, «De la compra», «Tuya» solo demostrable y «Todo mío» atenuado en B4, abono sin respuesta por defecto, «Todavía no» sin liquidez, límite B3, compra no disponible), revisión A2 (relación, abono real o pendiente, lo que no cambia, neto), envío (UUID sellado, doble toque, INDETERMINADO con la MISMA identidad, rechazo EXCEDE con el mensaje del servidor), confirmación con ida y vuelta; hoja de abono B2 (cuenta de la compra propuesta, confirmación, YA_CONCILIADO); Actividad (fila sin «+» ni «−» con «Devolución» / «Abono pendiente», «Registrar devolución» solo en gastos que no son devoluciones, «Registrar abono» solo con el abono pendiente, swipe «Cobrado» por la acción de accesibilidad, ida y vuelta compra ↔ devolución). Nunca «Ingreso».
// Versión: 0.1.0 (F05-06 M2-B §B2)
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, ContextoDevolucion, DetalleActividad, FilaActividad } from '../src/api/cliente';
import { AbonoHoja } from '../src/components/AbonoHoja';
import { importeFila, marcaReparto, secundariaFila, tituloFila } from '../src/domain/actividad';
import {
  atribucionInicial,
  faltaDevolucion,
  netoTras,
  ofreceRegistrarAbono,
  ofreceRegistrarDevolucion,
  superaLoQueQueda,
  textoDevolucionDe,
} from '../src/domain/devolucion';
import { ActividadScreen } from '../src/screens/ActividadScreen';
import { DevolucionScreen } from '../src/screens/DevolucionScreen';
import { TEXTO_FORMULARIO_SE_CONSERVA } from '../src/domain/capacidades';
import { ProveedorTema } from '../src/theme/tema';
import { colores } from '../src/theme/tokens';

import { clienteCategoriasStub } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';

const CTX: ContextoDevolucion = {
  origen_id: 'compra', fecha_hecho: '2026-08-20', nota: 'Abrigo', tercero: 'Zara', categoria_id: 'ropa', categoria: 'Ropa',
  importe_total: '120.00', devuelto: '0.00', queda: '120.00', neto: '120.00', devoluciones: [], disponible: true, motivo: null,
  atribucion_propuesta: 'SOLO_MIO', tuya_disponible: true, cuenta_compra: { cuenta_id: 'bbva', nombre: 'Tarjeta BBVA' },
};
const CUENTAS = [{ cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', moneda: 'EUR', elegible: true, motivo: null },
  { cuenta_id: 'nomina', nombre: 'Cuenta nómina', moneda: 'EUR', elegible: true, motivo: null }];

function cliente(o: Partial<ClienteApi> = {}): ClienteApi {
  return {
    ...clienteCategoriasStub(),
    registrarGastoPagado: jest.fn(),
    cuentasPago: jest.fn(),
    gastoMes: jest.fn(),
    contextoDevolucion: jest.fn(async () => ({ tipo: 'OK', datos: CTX }) as any),
    cuentasElegibles: jest.fn(async (op: string) => ({ tipo: 'OK', datos: { operacion: op, cuentas: CUENTAS } }) as any),
    registrarDevolucion: jest.fn(async (_: string, pl: any) => ({ tipo: 'OK', datos: {
      hecho_id: pl.intencion_id, origen_id: 'compra', idempotente: false, importe: pl.importe,
      estado_atribucion: pl.atribucion === 'SOLO_MIO' ? 'COMPLETA' : 'NO_DISPONIBLE', abono: pl.abono.estado, devuelto: '40.00', queda: '80.00' } }) as any),
    ...o,
  } as ClienteApi;
}

function envolver(ui: React.ReactElement) {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema>{ui}</ProveedorTema>
    </SafeAreaProvider>,
  );
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;

function textoPlano(): string {
  return JSON.stringify(screen.toJSON());
}

// ------------------------------------------------------------------ dominio
describe('dominio', () => {
  test('límite D-DEV-08 y neto derivado D-DEV-05', () => {
    expect(superaLoQueQueda('80,00', '80.00')).toBe(false);
    expect(superaLoQueQueda('80,01', '80.00')).toBe(true);
    expect(superaLoQueQueda('95', '80.00')).toBe(true);
    expect(netoTras({ importe_total: '120.00', devuelto: '40.00' }, '60.00')).toBe('20.00');
    expect(faltaDevolucion({ importeTexto: '95', fecha: HOY, abono: 'TODAVIA_NO', cuentaAbono: null, queda: '80.00' }, HOY))
      .toEqual(['un importe que no supere lo que queda']);
    expect(faltaDevolucion({ importeTexto: '40', fecha: HOY, abono: null, cuentaAbono: null, queda: '80.00' }, HOY))
      .toEqual(['si ya te han abonado el dinero']);
    expect(faltaDevolucion({ importeTexto: '40', fecha: HOY, abono: 'OTRA', cuentaAbono: null, queda: '80.00' }, HOY))
      .toEqual(['la cuenta del abono']);
  });

  test('P-DEV-01: «Tuya» solo si el servidor la demuestra', () => {
    expect(atribucionInicial({ tuya_disponible: true })).toBe('SOLO_MIO');
    expect(atribucionInicial({ tuya_disponible: false })).toBe('SIN_INDICAR');
  });

  test('P-DEV-03 / D-DEV-07: la fila de una devolución no lleva signo y dice «Devolución» o «Abono pendiente»', () => {
    const f = { id: 'd', fecha_hecho: '2026-09-10', tipo: 'GASTO', nota: 'Talla', moneda: 'EUR', importe_total: '40.00', tercero: null,
      categoria: { id: 'ropa', nombre: 'Ropa', ruta: 'Ropa', enabled: true }, varias: false, contexto: null,
      cuentas: [], estado_reparto: 'COMPLETA', tu_parte: '-40.00', pendiente: null, maestros_desactivados: [],
      devolucion_de: { hecho_id: 'compra', nota: 'Abrigo', fecha_hecho: '2026-08-20', tercero: 'Zara' }, abono: 'PENDIENTE' } as FilaActividad;
    expect(tituloFila(f)).toBe('Devolución · Abrigo');
    expect(importeFila(f)).toBe('40,00 €');
    expect(importeFila(f)).not.toMatch(/[+−-]/);
    expect(marcaReparto(f)).toBe('Abono pendiente');
    expect(marcaReparto({ ...f, abono: 'COBRADO' })).toBe('Devolución');
    expect(secundariaFila(f)).toBe('Zara · Ropa');
    expect(ofreceRegistrarDevolucion(f)).toBe(false);
    expect(ofreceRegistrarAbono(f)).toBe(true);
    expect(ofreceRegistrarAbono({ ...f, abono: 'COBRADO' })).toBe(false);
    expect(ofreceRegistrarDevolucion({ tipo: 'GASTO', devolucion_de: null })).toBe(true);
    expect(ofreceRegistrarDevolucion({ tipo: 'INGRESO', devolucion_de: null })).toBe(false);
    expect(textoDevolucionDe(f.devolucion_de!)).toBe('Abrigo · 20 ago');
  });
});

// ------------------------------------------------------------------ formulario y revisión
async function abrir(c: ClienteApi, onCerrar = jest.fn()) {
  envolver(<DevolucionScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} origenId="compra" onCerrar={onCerrar} />);
  await screen.findByTestId('devolucion-origen');
  return onCerrar;
}

describe('A1 formulario', () => {
  test('origen fijo, «De la compra», «Tuya» propuesta, sin respuesta de abono por defecto y nunca «Ingreso»', async () => {
    await abrir(cliente());
    const origen = screen.getByTestId('devolucion-origen');
    expect(within(origen).getByText('Abrigo · Zara')).toBeTruthy();
    expect(within(origen).getAllByText('120,00 €')).toHaveLength(2); // importe de la compra y lo que queda
    expect(within(screen.getByTestId('devolucion-queda')).getByText('120,00 €')).toBeTruthy();
    expect(within(screen.getByTestId('devolucion-categoria')).getByText('De la compra')).toBeTruthy();
    expect(screen.getByTestId('atribucion-tuya').props.accessibilityState).toMatchObject({ checked: true });
    for (const id of ['abono-compra', 'abono-otra', 'abono-todavia-no']) {
      expect(screen.getByTestId(id).props.accessibilityState).toMatchObject({ checked: false });
    }
    expect(within(screen.getByTestId('abono-compra')).getByText('Sí, en Tarjeta BBVA')).toBeTruthy();
    expect(textoPlano()).not.toMatch(/[Ii]ngreso/);
    expect(screen.getByTestId('revisar').props.accessibilityState).toMatchObject({ disabled: true });
  });

  test('B4: compra sin reparto → «Sin indicar» por defecto y «Todo mío» atenuado con su motivo', async () => {
    await abrir(cliente({ contextoDevolucion: jest.fn(async () => ({ tipo: 'OK', datos: { ...CTX, tuya_disponible: false, atribucion_propuesta: 'SIN_INDICAR' } }) as any) }));
    expect(screen.queryByTestId('atribucion-tuya')).toBeNull();
    expect(screen.getByTestId('atribucion-todo-mio-no-disponible').props.accessibilityState).toMatchObject({ disabled: true });
    expect(screen.getByTestId('atribucion-sin-indicar').props.accessibilityState).toMatchObject({ checked: true });
    expect(screen.getByTestId('atribucion-motivo')).toBeTruthy();
  });

  test('B3: más de lo que queda se explica y no deja revisar', async () => {
    await abrir(cliente({ contextoDevolucion: jest.fn(async () => ({ tipo: 'OK', datos: { ...CTX, devuelto: '40.00', queda: '80.00' } }) as any) }));
    fireEvent.changeText(screen.getByTestId('campo-importe'), '95');
    fireEvent.press(screen.getByTestId('abono-todavia-no'));
    expect(screen.getByTestId('devolucion-supera')).toHaveTextContent(/80,00 €/);
    expect(screen.getByTestId('revisar').props.accessibilityState).toMatchObject({ disabled: true });
  });

  test('compra que ya no admite devolución: motivo, sin formulario', async () => {
    await abrir(cliente({ contextoDevolucion: jest.fn(async () => ({ tipo: 'OK', datos: { ...CTX, disponible: false, motivo: 'DEVOLUCION_ORIGEN_V3_VARIOS_EFECTOS' } }) as any) }));
    expect(screen.getByTestId('devolucion-no-disponible')).toHaveTextContent(/versión anterior/);
    expect(screen.queryByTestId('campo-importe')).toBeNull();
  });

  test('error de carga de la compra: «Reintentar» vuelve a leer y muestra el origen', async () => {
    let llamadas = 0;
    const c = cliente({ contextoDevolucion: jest.fn(async () => (++llamadas === 1 ? { tipo: 'INDETERMINADO', mensaje: 'sin red' } : { tipo: 'OK', datos: CTX }) as any) });
    envolver(<DevolucionScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} origenId="compra" onCerrar={jest.fn()} />);
    const reintentar = await screen.findByTestId('devolucion-reintentar-carga');
    await act(async () => fireEvent.press(reintentar));
    expect(await screen.findByTestId('devolucion-origen')).toBeTruthy();
    expect(c.contextoDevolucion).toHaveBeenCalledTimes(2);
  });

  test('C1 en oscuro: fondo del tema oscuro, «Todavía no» con su texto y nunca «Ingreso»', async () => {
    render(
      <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
        <ProveedorTema forzar="dark">
          <DevolucionScreen cliente={cliente()} nuevoId={nuevoId} ahora={AHORA} origenId="compra" onCerrar={jest.fn()} />
        </ProveedorTema>
      </SafeAreaProvider>,
    );
    await screen.findByTestId('devolucion-origen');
    expect(JSON.stringify(screen.toJSON())).toContain(colores.dark.background);
    expect(JSON.stringify(screen.toJSON())).not.toContain(colores.light.background);
    fireEvent.press(screen.getByTestId('abono-todavia-no'));
    expect(screen.getByTestId('abono-todavia-no-texto')).toBeTruthy();
    expect(textoPlano()).not.toMatch(/[Ii]ngreso/);
  });
});

describe('A2 revisión, envío y confirmación', () => {
  test('«Todavía no»: revisión con abono pendiente; payload sellado PENDIENTE; ida y vuelta', async () => {
    const c = cliente();
    const onCerrar = await abrir(c);
    fireEvent.changeText(screen.getByTestId('campo-importe'), '40');
    fireEvent.press(screen.getByTestId('abono-todavia-no'));
    expect(screen.getByTestId('abono-todavia-no-texto')).toBeTruthy();
    fireEvent.press(screen.getByTestId('revisar'));
    expect(screen.getByTestId('revision-origen')).toHaveTextContent(/Abrigo · Zara/);
    expect(screen.getByTestId('revision-devolucion')).toHaveTextContent(/Reduce tu gasto en Ropa de octubre/);
    expect(screen.getByTestId('revision-abono')).toHaveTextContent(/Pendiente: no cuenta como dinero disponible/);
    expect(screen.getByTestId('revision-no-cambia')).toHaveTextContent(/Sigue siendo de 120,00 €/);
    expect(screen.getByTestId('revision-neto')).toHaveTextContent(/80,00 €/);
    expect(textoPlano()).not.toMatch(/[Ii]ngreso/);
    await act(async () => fireEvent.press(screen.getByTestId('registrar-devolucion')));
    const [origen, payload] = (c.registrarDevolucion as jest.Mock).mock.calls[0];
    expect(origen).toBe('compra');
    expect(payload).toMatchObject({ importe: '40.00', moneda: 'EUR', fecha_hecho: HOY, atribucion: 'SOLO_MIO', abono: { estado: 'PENDIENTE' } });
    expect(Object.isFrozen(payload)).toBe(true);
    expect(await screen.findByTestId('devolucion-exito-relacion')).toHaveTextContent('Devolución de Abrigo · 20 ago');
    expect(screen.getByTestId('devolucion-exito-abono')).toHaveTextContent('Abono pendiente');
    fireEvent.press(screen.getByTestId('devolucion-ver-compra'));
    expect(onCerrar).toHaveBeenCalledWith(true, 'compra');
  });

  test('«Ya cobrado» en la cuenta de la compra: revisión con el movimiento real y payload COBRADO', async () => {
    const c = cliente();
    await abrir(c);
    fireEvent.changeText(screen.getByTestId('campo-importe'), '40');
    await waitFor(() => expect(screen.getByTestId('abono-compra')).toBeTruthy());
    fireEvent.press(screen.getByTestId('abono-compra'));
    fireEvent.press(screen.getByTestId('revisar'));
    expect(screen.getByTestId('revision-abono')).toHaveTextContent(/Abono en Tarjeta BBVA/);
    expect(screen.getByTestId('revision-abono')).toHaveTextContent(/Entra dinero real/);
    await act(async () => fireEvent.press(screen.getByTestId('registrar-devolucion')));
    expect((c.registrarDevolucion as jest.Mock).mock.calls[0][1].abono).toEqual({ estado: 'COBRADO', cuenta_id: 'bbva', fecha: HOY });
  });

  test('INDETERMINADO reintenta la MISMA identidad; doble toque no duplica', async () => {
    let llamadas = 0;
    const c = cliente({ registrarDevolucion: jest.fn(async () => (++llamadas === 1 ? { tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro.' }
      : { tipo: 'OK', datos: { hecho_id: 'd', origen_id: 'compra', idempotente: true, importe: '40.00', estado_atribucion: 'COMPLETA', abono: 'PENDIENTE', devuelto: '40.00', queda: '80.00' } }) as any) });
    await abrir(c);
    fireEvent.changeText(screen.getByTestId('campo-importe'), '40');
    fireEvent.press(screen.getByTestId('abono-todavia-no'));
    fireEvent.press(screen.getByTestId('revisar'));
    await act(async () => {
      fireEvent.press(screen.getByTestId('registrar-devolucion'));
      fireEvent.press(screen.getByTestId('registrar-devolucion'));
    });
    expect(await screen.findByTestId('estado-indeterminado')).toBeTruthy();
    expect(c.registrarDevolucion).toHaveBeenCalledTimes(1);
    await act(async () => fireEvent.press(screen.getByTestId('reintentar')));
    const [[, a], [, b]] = (c.registrarDevolucion as jest.Mock).mock.calls;
    expect(b).toBe(a);
    expect(await screen.findByTestId('devolucion-exito')).toBeTruthy();
  });

  test('rechazo EXCEDE: vuelve al formulario con el mensaje del servidor y recarga lo que queda', async () => {
    const c = cliente({ registrarDevolucion: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'EXCEDE_CAPACIDAD_REVERSIBLE',
      mensaje: 'Supera lo que queda por devolver de esta compra (20,00 €).', detalle: { queda: '20.00' } }) as any) });
    await abrir(c);
    fireEvent.changeText(screen.getByTestId('campo-importe'), '40');
    fireEvent.press(screen.getByTestId('abono-todavia-no'));
    fireEvent.press(screen.getByTestId('revisar'));
    await act(async () => fireEvent.press(screen.getByTestId('registrar-devolucion')));
    expect(await screen.findByTestId('error-dominio')).toHaveTextContent(/20,00 €/);
    expect(screen.getByTestId('devolucion-form')).toBeTruthy();
    expect(c.contextoDevolucion).toHaveBeenCalledTimes(2);
  });

  test('rechazo CUENTA_SIN_CAPACIDAD: mensaje, el formulario se conserva y se recargan las cuentas', async () => {
    const c = cliente({ registrarDevolucion: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'CUENTA_SIN_CAPACIDAD',
      mensaje: 'Esa cuenta no puede usarse para esto.' }) as any) });
    await abrir(c);
    fireEvent.changeText(screen.getByTestId('campo-importe'), '40');
    await waitFor(() => expect(screen.getByTestId('abono-compra')).toBeTruthy());
    fireEvent.press(screen.getByTestId('abono-compra'));
    fireEvent.press(screen.getByTestId('revisar'));
    const antes = (c.cuentasElegibles as jest.Mock).mock.calls.length;
    await act(async () => fireEvent.press(screen.getByTestId('registrar-devolucion')));
    expect(await screen.findByTestId('error-dominio')).toHaveTextContent(new RegExp(TEXTO_FORMULARIO_SE_CONSERVA));
    expect(screen.getByTestId('campo-importe').props.value).toBe('40');
    expect((c.cuentasElegibles as jest.Mock).mock.calls.length).toBe(antes + 1);
  });
});

// ------------------------------------------------------------------ abono B2
describe('B2 registrar abono', () => {
  test('propone la cuenta de la compra, confirma y no se cierra sin cuenta', async () => {
    const registrarAbono = jest.fn(async () => ({ tipo: 'OK', datos: { hecho_id: 'd', movimiento_id: 'm', idempotente: false, importe: '40.00', abono: 'COBRADO' } }) as any);
    const c = cliente({ registrarAbono });
    const onCerrar = jest.fn();
    envolver(<AbonoHoja cliente={c} nuevoId={nuevoId} ahora={AHORA} devolucion={{ id: 'd', titulo: 'Abrigo · 20 ago', importe: '40.00', origenId: 'compra' }} onCerrar={onCerrar} />);
    await waitFor(() => expect(screen.getByTestId('abono-cuenta-compra').props.accessibilityState).toMatchObject({ checked: true }));
    expect(screen.getByTestId('abono-devolucion')).toHaveTextContent('Devolución de Abrigo · 20 ago · 40,00 €');
    expect(screen.getByTestId('abono-confirmar')).toHaveTextContent('Confirmar abono de 40,00 €');
    fireEvent.press(screen.getByTestId('abono-formulario-completo'));
    expect(screen.getByTestId('abono-otro-importe')).toBeTruthy();
    await act(async () => fireEvent.press(screen.getByTestId('abono-confirmar')));
    expect(registrarAbono).toHaveBeenCalledWith('d', expect.objectContaining({ cuenta_id: 'bbva', fecha: HOY }));
    expect(onCerrar).toHaveBeenCalledWith(true);
  });

  test('YA_CONCILIADO: se muestra el mensaje y no se cierra', async () => {
    const c = cliente({ registrarAbono: jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'YA_CONCILIADO', mensaje: 'Esta devolución ya tiene su abono registrado.' }) as any) });
    const onCerrar = jest.fn();
    envolver(<AbonoHoja cliente={c} nuevoId={nuevoId} ahora={AHORA} devolucion={{ id: 'd', titulo: 'Abrigo · 20 ago', importe: '40.00', origenId: 'compra' }} onCerrar={onCerrar} />);
    await waitFor(() => expect(screen.getByTestId('abono-cuenta-compra').props.accessibilityState).toMatchObject({ checked: true }));
    await act(async () => fireEvent.press(screen.getByTestId('abono-confirmar')));
    expect(await screen.findByTestId('abono-error')).toHaveTextContent(/ya tiene su abono/);
    expect(onCerrar).not.toHaveBeenCalled();
  });
});

// ------------------------------------------------------------------ Actividad
const COMPRA: FilaActividad = {
  id: 'compra', fecha_hecho: '2026-10-02', tipo: 'GASTO', nota: 'Abrigo', moneda: 'EUR', importe_total: '120.00',
  tercero: { id: 'zara', nombre: 'Zara', enabled: true }, categoria: { id: 'ropa', nombre: 'Ropa', ruta: 'Ropa', enabled: true }, varias: false,
  contexto: null, cuentas: [{ cuenta_id: 'bbva', nombre: 'Tarjeta BBVA', rol: 'PAGO', enabled: true }], estado_reparto: 'COMPLETA', tu_parte: '120.00',
  pendiente: null, maestros_desactivados: [], devolucion_de: null, abono: null,
};
const DEV: FilaActividad = {
  ...COMPRA, id: 'dev', fecha_hecho: HOY, nota: 'Talla', importe_total: '40.00', tercero: null, cuentas: [], tu_parte: '-40.00',
  devolucion_de: { hecho_id: 'compra', nota: 'Abrigo', fecha_hecho: '2026-10-02', tercero: 'Zara' }, abono: 'PENDIENTE',
};

function clienteActividad(o: Partial<ClienteApi> = {}) {
  const detalles: Record<string, DetalleActividad> = {
    compra: { ...COMPRA, presupuestable: true, magnitudes: [], devoluciones: { items: [{ hecho_id: 'dev', fecha_hecho: HOY, importe: '40.00', abono: 'PENDIENTE' }], devuelto: '40.00', queda: '80.00', neto: '80.00' } },
    dev: { ...DEV, presupuestable: true, magnitudes: [], devoluciones: null },
  };
  return cliente({
    actividad: jest.fn(async () => ({ tipo: 'OK', datos: { filas: [DEV, COMPRA], siguiente: null, total: 2 } }) as any),
    detalleActividad: jest.fn(async (id: string) => ({ tipo: 'OK', datos: detalles[id] }) as any),
    ...o,
  });
}

describe('Actividad', () => {
  test('B1: fila de la devolución sin signo con «Abono pendiente»; la compra con «−»', async () => {
    envolver(<ActividadScreen cliente={clienteActividad()} ahora={AHORA} nuevoId={nuevoId} onRegistrarDevolucion={jest.fn()} />);
    const f = await screen.findByTestId('fila-dev');
    expect(within(f).getByText('Devolución · Abrigo')).toBeTruthy();
    expect(within(f).getByText('40,00 €')).toBeTruthy();
    expect(within(f).getByText('Abono pendiente')).toBeTruthy();
    expect(within(screen.getByTestId('fila-compra')).getByText('−120,00 €')).toBeTruthy();
    expect(textoPlano()).not.toMatch(/\+40/);
  });

  test('A3/A4: «Registrar devolución» solo en la compra; ida y vuelta compra ↔ devolución; «Registrar abono» en la pendiente', async () => {
    const onRegistrarDevolucion = jest.fn();
    envolver(<ActividadScreen cliente={clienteActividad()} ahora={AHORA} nuevoId={nuevoId} onRegistrarDevolucion={onRegistrarDevolucion} />);
    fireEvent.press(await screen.findByTestId('fila-compra'));
    await screen.findByTestId('detalle-devoluciones');
    expect(screen.getByTestId('detalle-neto')).toHaveTextContent(/80,00 €/);
    expect(screen.getByTestId('detalle-registrar-devolucion')).toBeTruthy();
    expect(screen.queryByTestId('detalle-registrar-abono')).toBeNull();
    fireEvent.press(screen.getByTestId('detalle-devolucion-dev'));
    await screen.findByTestId('detalle-devolucion-de');
    expect(screen.queryByTestId('detalle-registrar-devolucion')).toBeNull();
    expect(screen.getByTestId('detalle-registrar-abono')).toBeTruthy();
    expect(screen.getByTestId('kv-Abono')).toHaveTextContent(/Pendiente/);
    expect(screen.getByTestId('kv-Tu parte')).toHaveTextContent(/40,00 €/);
    fireEvent.press(screen.getByTestId('detalle-devolucion-de'));
    await screen.findByTestId('detalle-devoluciones');
    fireEvent.press(screen.getByTestId('detalle-registrar-devolucion'));
    expect(onRegistrarDevolucion).toHaveBeenCalledWith('compra');
  });

  test('P-DEV-04: swipe «Cobrado» abre la confirmación de cuenta y fecha (nunca registra solo)', async () => {
    const c = clienteActividad({ registrarAbono: jest.fn() as any });
    envolver(<ActividadScreen cliente={c} ahora={AHORA} nuevoId={nuevoId} onRegistrarDevolucion={jest.fn()} />);
    const f = await screen.findByTestId('fila-dev');
    expect(f.props.accessibilityActions).toEqual([{ name: 'cobrado', label: 'Cobrado' }]);
    expect(screen.getByTestId('fila-compra').props.accessibilityActions).toBeUndefined();
    fireEvent(f, 'accessibilityAction', { nativeEvent: { actionName: 'cobrado' } });
    expect(await screen.findByTestId('hoja-abono')).toBeTruthy();
    expect(c.registrarAbono).not.toHaveBeenCalled();
  });

  test('P-DEV-04: el gesto real (contenedor que captura el movimiento horizontal) abre la hoja solo pasado el umbral', async () => {
    const c = clienteActividad({ registrarAbono: jest.fn() as any });
    envolver(<ActividadScreen cliente={c} ahora={AHORA} nuevoId={nuevoId} onRegistrarDevolucion={jest.fn()} />);
    await screen.findByTestId('fila-dev');
    expect(screen.queryByTestId('fila-swipe-compra')).toBeNull();
    const z = screen.getByTestId('fila-swipe-dev');
    // Historial de un solo toque que va de x=300 a x=300+dx (formato del ResponderTouchHistoryStore).
    const evento = (dx: number, dy: number, ts: number) => {
      const toque = { touchActive: true, startPageX: 300, startPageY: 20, startTimeStamp: ts - 5,
        currentPageX: 300 + dx, currentPageY: 20 + dy, currentTimeStamp: ts, previousPageX: 300, previousPageY: 20, previousTimeStamp: ts - 5 };
      const touchHistory = { numberActiveTouches: 1, indexOfSingleActiveTouch: 0, mostRecentTimeStamp: ts, touchBank: [toque] };
      return { nativeEvent: { changedTouches: [], touches: [], pageX: 300 + dx, pageY: 20 + dy, timestamp: ts }, touchHistory };
    };
    let reloj = 0; // marcas de tiempo crecientes entre gestos: PanResponder solo cuenta movimientos posteriores
    const gesto = (dx: number, dy: number) => {
      const captura = z.props.onMoveShouldSetResponderCapture(evento(dx / 2, dy / 2, (reloj += 10)));
      if (captura) {
        z.props.onResponderGrant(evento(dx / 2, dy / 2, reloj));
        z.props.onResponderMove(evento(dx, dy, (reloj += 10)));
        z.props.onResponderRelease(evento(dx, dy, (reloj += 10)));
      }
      return captura;
    };
    expect(gesto(0, -80)).toBe(false); // vertical: lo deja para el scroll
    await act(async () => { gesto(-40, 0); }); // horizontal corto: captura pero no llega al umbral
    expect(screen.queryByTestId('hoja-abono')).toBeNull();
    await act(async () => { expect(gesto(-100, 0)).toBe(true); });
    expect(await screen.findByTestId('hoja-abono')).toBeTruthy();
    expect(c.registrarAbono).not.toHaveBeenCalled();
  });
});
