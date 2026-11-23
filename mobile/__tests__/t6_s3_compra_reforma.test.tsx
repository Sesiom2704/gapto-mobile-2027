// ============================================================
// GAPTO MOBILE 2027
// Fichero: t6_s3_compra_reforma.test.tsx
// Ruta: mobile/__tests__/t6_s3_compra_reforma.test.tsx
// Descripción: F06 T6 «UX ágil» · S3 (F09 0.55 §12.107.2; lámina REG-AGIL v0.8 C1–C4 y R1/R2; mandato P4):
//   - importe del préstamo por porcentaje en céntimos enteros con round_half_up (medio céntimo), pct de hasta 2 decimales;
//   - totales de presentación «de la hipoteca» y «resto, sin hipoteca» (DT-02) y ayuda «préstamo ≤ precio» (DT-03);
//   - pagos que se confirman y quedan en una línea con Editar y Eliminar; «Cancelar» deshace; `faltasPagos` no cambia;
//   - reforma: exprés + «Revisar»; editar → invalidar → recalcular → reconfirmar; cancelar; `posiciones_confirmadas` = lo mostrado.
// Versión: 0.1.0 (F06 T6 · S3)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonio, ParteEnFecha, ResultadoCompra } from '../src/api/patrimonio';
import type { ClientePatrimonioB3, PayloadGastoPropiedad, PayloadGastoPropiedadV2, PropuestaGasto } from '../src/api/patrimonio_b3';
import type { VistaPropiedad } from '../src/api/propiedades';
import { borradorInicial, faltasPagos, importePorcentaje, prestamoSuperaPrecio, totalesPagos } from '../src/domain/compra';
import { CompraScreen, TEXTO_PRESTAMO_SUPERA } from '../src/screens/CompraScreen';
import { GastoPropiedadScreen, TEXTO_REVISION_CAMBIADA } from '../src/screens/GastoPropiedadScreen';
import { ProveedorTema } from '../src/theme/tema';
import { ANA, CTA, CTA2, hipoteca, PARTES, YO } from './hipoteca_fixtures';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });
const AHORA = () => new Date(2026, 9, 10, 10);
const HOY = '2026-10-10';
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const texto = (id: string) => screen.getByTestId(id).props.children;
const deshabilitado = (id: string) => screen.getByTestId(id).props.accessibilityState?.disabled === true;

function vista(p: Partial<VistaPropiedad> = {}): VistaPropiedad {
  return {
    id: 'p1', nombre: 'Piso Ejemplo', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: '2026-03-20', superficie_m2: null,
    superficie_construida_m2: null, habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
    incluir_en_rentabilidad: true, notas: null, fecha_consulta: HOY,
    titularidad: { modo: 'COMPARTIDA', desde: '2026-03-20', partes: [
      { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '50.0000' },
      { actor_id: ANA, yo: false, tercero_id: 't-ana', nombre: 'Ana', porcentaje: '50.0000' }] },
    cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [], ...p,
  } as VistaPropiedad;
}

// ------------------------------------------------------------------ dominio (presentación)
test('AJ-UX2-07: préstamo por % en céntimos enteros con round_half_up; pct de hasta 2 decimales; solo el importe', () => {
  expect(importePorcentaje('200.000,00', '80')).toBe('160000.00');
  expect(importePorcentaje('200000,00', '90')).toBe('180000.00');
  // Medio céntimo: 100,05 × 50 % = 50,025 → 50,03 (hacia arriba); 100,03 × 50 % = 50,015 → 50,02.
  expect(importePorcentaje('100,05', '50')).toBe('50.03');
  expect(importePorcentaje('100,03', '50')).toBe('50.02');
  // 0,01 × 50 % = 0,005 → 0,01; 0,01 × 49,99 % = 0,004999 → 0,00.
  expect(importePorcentaje('0,01', '50')).toBe('0.01');
  expect(importePorcentaje('0,01', '49,99')).toBe('0.00');
  expect(importePorcentaje('100,01', '33,33')).toBe('33.33');            // 33,333333 → 33,33
  expect(importePorcentaje('250.000,00', '75,5')).toBe('188750.00');
  expect(importePorcentaje('250.000,00', '75.55')).toBe('188875.00');
  // Enteros grandes sin pérdida (BigInt): 99.999.999.999,99 × 99,99 %.
  expect(importePorcentaje('99.999.999.999,99', '99,99')).toBe('99989999999.99');
  for (const malo of ['', '0', '100,001', '12,345', '101', 'abc', '-5']) expect(importePorcentaje('1000,00', malo)).toBeNull();
  expect(importePorcentaje('', '80')).toBeNull();
});

test('DT-02/DT-03: totales de presentación y ayuda «préstamo ≤ precio»; `faltasPagos` no cambia', () => {
  const b = { ...borradorInicial(HOY), precio: '200.000,00', fechaEscritura: '2026-03-03', pagos: [
    { id: 'a', rol: 'ARRAS' as const, cuentaId: CTA, fecha: '2026-01-15', importe: '20.000,00' },
    { id: 'f', rol: 'FIRMA' as const, cuentaId: CTA2, fecha: '2026-03-03', importe: '175.000,00' },
    { id: 'o', rol: 'OTRO' as const, cuentaId: CTA, fecha: '2026-03-03', importe: '5.000,00' }] };
  expect(totalesPagos(b, '160.000,00')).toEqual({ precio: '200000.00', pagado: '200000.00', hipoteca: '160000.00', resto: '40000.00', falta: '0.00' });
  expect(totalesPagos({ ...b, pagos: [] }, '160.000,00')).toEqual({ precio: '200000.00', pagado: '0.00', hipoteca: '160000.00', resto: '0.00', falta: '200000.00' });
  expect(totalesPagos(b, null)).toMatchObject({ hipoteca: null, resto: null });
  expect(faltasPagos(b)).toEqual([]);
  expect(faltasPagos({ ...b, pagos: b.pagos.slice(1) })).toEqual(['los pagos tienen que sumar el precio']);
  expect(prestamoSuperaPrecio('200.000,00', '200.000,00')).toBe(false);
  expect(prestamoSuperaPrecio('200.000,00', '200.000,01')).toBe(true);
});

// ------------------------------------------------------------------ compra
function clienteCompra() {
  return {
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: [{ cuenta_id: CTA, nombre: 'Cuenta Nómina', moneda: 'EUR' }, { cuenta_id: CTA2, nombre: 'Cuenta Común', moneda: 'EUR' }] })),
    listarTerceros: jest.fn(async () => ok({ terceros: [] })),
    senalesTerceros: jest.fn(async () => ok({ terceros: [] })),
  } as unknown as ClienteApi;
}
function patrimonioCompra() {
  return {
    registrarCompra: jest.fn(async () => ok({ propiedad: vista(), idempotente: false, compra: { hechos: [], coste_adquisicion: null, sale_de_tus_cuentas: '-1.00',
      liquidez_atribuible: '-1.00', gasto_del_mes: '0.00', atribucion: null }, hipoteca: hipoteca(), aviso_reparto_distinto: false } as ResultadoCompra)),
    gastoCompraPosterior: jest.fn(), leerCoste: jest.fn(),
    titularidadEnFecha: jest.fn(async (_id: string, fecha: string) => ok({ fecha, partes: PARTES as ParteEnFecha[] })),
  } as unknown as ClientePatrimonio;
}
async function compraEnPagos(precio = '200000,00') {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <CompraScreen cliente={clienteCompra()} patrimonio={patrimonioCompra()} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} onRecargar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await escribir('compra-precio', precio);
  await escribir('compra-escritura', '20/03/2026');
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId(`compra-pago-0-cuenta-${CTA}`));
}

test('C2/C3: un pago se confirma y queda en su línea con Editar y Eliminar; «Cancelar» deshace; «Continuar» solo si cuadra', async () => {
  await compraEnPagos('1000,00');
  expect(texto('compra-tot-falta-valor')).toBe('1.000,00 €');
  await pulsar(`compra-pago-0-cuenta-${CTA}`);
  expect(deshabilitado('compra-pago-0-confirmar')).toBe(true);                    // falta el importe
  await escribir('compra-pago-0-importe', '600');
  expect(screen.queryByTestId('compra-pago-anadir')).toBeNull();                  // un pago a la vez
  await pulsar('compra-pago-0-confirmar');
  expect(texto('compra-pago-0-linea-titulo')).toBe('En la firma · 600,00 €');
  for (const id of ['compra-pago-0-editar', 'compra-pago-0-eliminar']) expect(screen.getByTestId(id)).toBeTruthy();
  expect(deshabilitado('compra-continuar')).toBe(true);                           // no cuadra (faltasPagos)
  // Nuevo pago y «Cancelar»: se quita.
  await pulsar('compra-pago-anadir');
  expect(screen.getByTestId('compra-pago-1')).toBeTruthy();
  await pulsar('compra-pago-1-cancelar');
  expect(screen.queryByTestId('compra-pago-1')).toBeNull();
  expect(screen.queryByTestId('compra-pago-1-linea')).toBeNull();
  // Editar y «Cancelar»: vuelve a lo confirmado.
  await pulsar('compra-pago-0-editar');
  await escribir('compra-pago-0-importe', '999');
  await pulsar('compra-pago-0-cancelar');
  expect(texto('compra-pago-0-linea-titulo')).toBe('En la firma · 600,00 €');
  // Segundo pago (arras) que cuadra.
  await pulsar('compra-pago-anadir');
  await pulsar(`compra-pago-1-cuenta-${CTA2}`);
  await escribir('compra-pago-1-fecha', '15/01/2026');
  await escribir('compra-pago-1-importe', '400');
  await pulsar('compra-pago-1-confirmar');
  expect(texto('compra-pago-1-linea-titulo')).toBe('Arras · 400,00 €');
  expect(texto('compra-tot-falta-valor')).toBe('0,00 € ✓');
  expect(deshabilitado('compra-continuar')).toBe(false);
  // Eliminar vuelve a dejarlo sin cuadrar.
  await pulsar('compra-pago-1-eliminar');
  expect(deshabilitado('compra-continuar')).toBe(true);
});

test('C4: 80 % · 90 % · Otro % · Otro importe; el importe se ve y se edita; ayuda «préstamo ≤ precio»; totales de la hipoteca', async () => {
  await compraEnPagos('200000,00');
  await pulsar(`compra-pago-0-cuenta-${CTA}`);
  await escribir('compra-pago-0-importe', '200000');
  await pulsar('compra-pago-0-confirmar');
  await pulsar('compra-hip-anadir');
  await pulsar('compra-hip-pct-80');
  expect(screen.getByTestId('compra-hip-importe').props.value).toBe('160.000,00');
  expect(texto('compra-tot-hipoteca-valor')).toBe('160.000,00 €');
  expect(texto('compra-tot-resto-valor')).toBe('40.000,00 €');
  await pulsar('compra-hip-pct-90');
  expect(screen.getByTestId('compra-hip-importe').props.value).toBe('180.000,00');
  await pulsar('compra-hip-pct-otro');
  expect(screen.getByTestId('compra-hip-pct').props.keyboardType).toBe('decimal-pad');
  await escribir('compra-hip-pct', '75,5');
  expect(screen.getByTestId('compra-hip-importe').props.value).toBe('151.000,00');
  // El importe calculado se puede corregir a mano («Otro importe»).
  await escribir('compra-hip-importe', '150.500,00');
  const otro = screen.getByTestId('compra-hip-otro-importe').props.accessibilityState;
  expect(!!(otro?.checked || otro?.selected)).toBe(true);
  expect(screen.queryByTestId('compra-hip-supera')).toBeNull();
  await escribir('compra-hip-importe', '250.000,00');
  expect(texto('compra-hip-supera')).toBe(TEXTO_PRESTAMO_SUPERA);
  expect(texto('compra-faltas')).toMatch(/un préstamo que no supere el precio/);
});

// ------------------------------------------------------------------ reforma
const prop = (yo = '50.0000', ana = '50.0000', fecha = HOY): PropuestaGasto => ({
  fecha, propiedad_id: 'p1', nombre: 'Piso Ejemplo', titularidad_disponible: true,
  partes: [
    { actor_id: ANA, porcentaje: ana, yo: false, tercero_id: 't-ana', nombre: 'Ana', naturaleza: 'PERSONA' },
    { actor_id: YO, porcentaje: yo, yo: true, tercero_id: null, nombre: null, naturaleza: null },
  ],
  cuenta: { cuenta_id: CTA, solo_mia: true, compartida_con: [] },
});
function montarReforma(propuestaGasto: jest.Mock) {
  const registrar = jest.fn(async (p: PayloadGastoPropiedad) => ok({ hecho_id: p.intencion_id, idempotente: false, tipo_hecho: 'MEJORA_PATRIMONIAL', clase: p.clase,
    importe: p.importe, estado_atribucion: 'COMPLETA', atribuciones: [], posiciones: [], intencion_correccion_id: 'x' }));
  const onCerrar = jest.fn();
  const pat = { propuestaGasto, registrarGastoPropiedad: registrar, mejoraHistorica: jest.fn(), listarGastos: jest.fn(), leerGasto: jest.fn(),
    impactoCorreccion: jest.fn(), corregirClase: jest.fn() } as unknown as ClientePatrimonioB3;
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <GastoPropiedadScreen cliente={clienteCompra()} patrimonio={pat} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={onCerrar} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return { registrar, onCerrar };
}

test('R1/R2: exprés en una pantalla; «Revisar»; «‹ Volver» y cambiar quién pagó invalida; se recalcula, se reconfirma y viaja lo mostrado', async () => {
  const { registrar } = montarReforma(jest.fn(async (_id: string, fecha: string) => ok(prop('50.0000', '50.0000', fecha))));
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  for (const id of ['gprop-importe', 'gprop-nota', 'gprop-quien-pago', 'gprop-bloque-fecha', 'gprop-fecha-hoy', 'gprop-revisar']) expect(screen.getByTestId(id)).toBeTruthy();
  expect(screen.queryByTestId('gprop-continuar')).toBeNull();
  await escribir('gprop-importe', '8400');
  await pulsar('gprop-pago-yo');
  await pulsar(`gprop-cuenta-${CTA}`);
  await waitFor(() => expect(screen.getByTestId('gprop-rep-titularidad').props.accessibilityState?.checked).toBe(true));
  await pulsar('gprop-revisar');
  expect(screen.getByTestId('gprop-paso-confirmar')).toBeTruthy();
  expect(texto(`gprop-conf-${ANA}-posicion`)).toBe('Ana te debe 4.200,00 €');
  // Editar: «‹ Volver» invalida la revisión; cambiar quién pagó y volver a revisar recalcula.
  await pulsar('gprop-atras');
  expect(screen.getByTestId('gprop-expres')).toBeTruthy();
  await pulsar('gprop-pago-cada-uno');
  await pulsar('gprop-revisar');
  expect(texto(`gprop-conf-${ANA}-posicion`)).toBe('No queda nada pendiente');
  expect(texto(`gprop-conf-${ANA}-puso`)).toBe('Puso: 4.200,00 €');
  await pulsar('gprop-guardar');
  expect(registrar).toHaveBeenCalledTimes(1);
  const body = registrar.mock.calls[0][0] as unknown as PayloadGastoPropiedadV2;
  expect(body.posiciones_confirmadas).toEqual([]);                                // = lo mostrado («No queda nada pendiente»)
  expect(body.pagos).toHaveLength(2);
  expect(body.pagos).toEqual(expect.arrayContaining([{ pagador: 'YO', cuenta_id: CTA, importe: '4200.00' }, { pagador: ANA, importe: '4200.00' }]));
});

test('A6: si la propuesta cambia mientras se revisa, «Confirmar» no envía: se recalcula, se avisa y hay que reconfirmar', async () => {
  let soltar: (() => void) | null = null;
  let llamadas = 0;
  const propuestaGasto = jest.fn((_id: string, fecha: string, cuenta?: string | null) => {
    llamadas += 1;
    // La relectura con la Cuenta Común llega tarde y con otra titularidad (60/40).
    if (cuenta === CTA2) return new Promise((res) => { soltar = () => res(ok(prop('60.0000', '40.0000', fecha))); });
    return Promise.resolve(ok(prop('50.0000', '50.0000', fecha)));
  });
  const { registrar } = montarReforma(propuestaGasto as unknown as jest.Mock);
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  await escribir('gprop-importe', '1000');
  await pulsar('gprop-pago-yo');
  await pulsar(`gprop-cuenta-${CTA}`);
  await waitFor(() => expect(screen.getByTestId('gprop-rep-titularidad').props.accessibilityState?.checked).toBe(true));
  await pulsar(`gprop-cuenta-${CTA2}`);                                           // relectura en vuelo
  await pulsar('gprop-revisar');
  expect(texto(`gprop-conf-${ANA}-posicion`)).toBe('Ana te debe 500,00 €');
  await act(async () => { soltar?.(); await new Promise((r) => setTimeout(r, 0)); });
  await pulsar('gprop-guardar');
  expect(registrar).not.toHaveBeenCalled();
  expect(screen.getByTestId('gprop-revision-cambiada')).toBeTruthy();
  expect(JSON.stringify(screen.toJSON())).toContain(TEXTO_REVISION_CAMBIADA);
  expect(texto(`gprop-conf-${ANA}-posicion`)).toBe('Ana te debe 400,00 €');       // recalculado con 60/40
  await pulsar('gprop-guardar');                                                  // reconfirmar
  expect(registrar).toHaveBeenCalledTimes(1);
  const body = registrar.mock.calls[0][0] as unknown as PayloadGastoPropiedadV2;
  expect(body.posiciones_confirmadas).toEqual([{ actor_id: ANA, tipo: 'DERECHO_COBRO', importe: '400.00' }]);
  expect(llamadas).toBeGreaterThanOrEqual(2);
});

test('cancelar: desde «Revisar», «‹ Volver» no envía; «Cancelar» cierra sin cambios', async () => {
  const { registrar, onCerrar } = montarReforma(jest.fn(async (_id: string, fecha: string) => ok(prop('50.0000', '50.0000', fecha))));
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  await escribir('gprop-importe', '300');
  await pulsar('gprop-pago-yo');
  await pulsar(`gprop-cuenta-${CTA}`);
  await waitFor(() => expect(screen.getByTestId('gprop-rep-titularidad').props.accessibilityState?.checked).toBe(true));
  await pulsar('gprop-revisar');
  await pulsar('gprop-atras');
  expect(registrar).not.toHaveBeenCalled();
  await pulsar('gprop-cancelar');
  expect(onCerrar).toHaveBeenCalledWith(false);
  expect(registrar).not.toHaveBeenCalled();
});
