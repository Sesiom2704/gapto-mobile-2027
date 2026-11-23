// ============================================================
// GAPTO MOBILE 2027
// Fichero: t6_s3_wire_compra_reforma.test.tsx
// Ruta: mobile/__tests__/t6_s3_wire_compra_reforma.test.tsx
// Descripción: F06 T6 «UX ágil» · S3 (mandato F06-T6 NOCHE v1.2, P4): sin cambio del wire. Para las mismas entradas, el
//   payload de la compra (sin y con hipoteca) y el de la reforma son IDÉNTICOS antes y después de S3. Las referencias de
//   `t6_s3_wire_compra_reforma.json` se capturaron con GAPTO_T6_CAPTURAR_WIRE=1 sobre el código anterior a S3 (CompraScreen y
//   compra.ts del commit S1 e2a4db5 = H salvo el selector de «Banco» de S1, que envía el mismo identificador; GastoPropiedadScreen
//   de H). El recorrido es el del usuario: si existe el paso nuevo («Confirmar pago», «Revisar»), lo usa; en H no existe.
//   Los identificadores de intención son UUID por diseño (se compara su forma) y los de línea generados en el cliente se
//   comparan por estructura (`normalizar`).
// Versión: 0.1.0 (F06 T6 · S3)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonio, ParteEnFecha, ResultadoCompra } from '../src/api/patrimonio';
import type { ClientePatrimonioB3, PayloadGastoPropiedad, PropuestaGasto } from '../src/api/patrimonio_b3';
import type { VistaPropiedad } from '../src/api/propiedades';
import { CompraScreen } from '../src/screens/CompraScreen';
import { GastoPropiedadScreen } from '../src/screens/GastoPropiedadScreen';
import { ProveedorTema } from '../src/theme/tema';
import { ANA, BANCO, CTA, CTA2, cuadroPrevio, hipoteca, PARTES, YO } from './hipoteca_fixtures';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

declare const __dirname: string;
declare const process: { env: Record<string, string | undefined> };
const fs: { readFileSync(f: string, e: 'utf8'): string; writeFileSync(f: string, d: string, e: 'utf8'): void; existsSync(f: string): boolean } = require('fs');
const path: { join(...p: string[]): string } = require('path');
const REFERENCIAS = path.join(__dirname, 't6_s3_wire_compra_reforma.json');
const CAPTURAR = process.env.GAPTO_T6_CAPTURAR_WIRE === '1';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });
const AHORA = () => new Date(2026, 9, 10, 10);
const HOY = '2026-10-10';

const hay = (id: string) => screen.queryAllByTestId(id).length > 0;
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
/** Paso nuevo de S3 si existe (en H no existe y no hace falta). */
const siHay = async (id: string) => { if (hay(id)) await pulsar(id); };

function vista(p: Partial<VistaPropiedad> = {}): VistaPropiedad {
  return {
    id: 'p1', nombre: 'Piso Ejemplo', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: '2026-03-20', superficie_m2: null,
    superficie_construida_m2: null, habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
    incluir_en_rentabilidad: true, notas: null, fecha_consulta: HOY,
    titularidad: { modo: 'COMPARTIDA', desde: '2026-03-20', partes: [
      { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '60.0000' },
      { actor_id: ANA, yo: false, tercero_id: 't-ana', nombre: 'Ana', porcentaje: '40.0000' }] },
    cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [], ...p,
  } as VistaPropiedad;
}

/**
 * Identificadores generados en el cliente (`nuevoId` del test: 00000000-0000-4000-8000-NNNNNNNNNNNN) → `<gen-k>` por orden de
 * aparición. Su valor depende de cuántas veces se renderiza la pantalla (`useRef(p.nuevoId())` evalúa el argumento en cada
 * render), no de las entradas; se conserva la estructura (qué identificador se repite y dónde).
 */
function normalizar(x: unknown): unknown {
  const vistos = new Map<string, string>();
  const ir = (v: unknown): unknown => {
    if (typeof v === 'string' && /^00000000-0000-4000-8000-\d{12}$/.test(v)) {
      if (!vistos.has(v)) vistos.set(v, `<gen-${vistos.size + 1}>`);
      return vistos.get(v);
    }
    if (Array.isArray(v)) return v.map(ir);
    if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v as Record<string, unknown>).map(([k, y]) => [k, ir(y)]));
    return v;
  };
  return ir(x);
}

function comparar(caso: string, payload: any) {
  expect(payload.intencion_id).toMatch(UUID);
  const sinId = normalizar({ ...payload, intencion_id: '<uuid>' });
  if (CAPTURAR) {
    const todas = fs.existsSync(REFERENCIAS) ? JSON.parse(fs.readFileSync(REFERENCIAS, 'utf8')) : {};
    todas[caso] = sinId;
    fs.writeFileSync(REFERENCIAS, JSON.stringify(todas, null, 2) + '\n', 'utf8');
    return;
  }
  const ref = JSON.parse(fs.readFileSync(REFERENCIAS, 'utf8'))[caso];
  expect(ref).toBeDefined();
  expect(sinId).toEqual(normalizar(ref));
}

// ------------------------------------------------------------------ compra
function clienteCompra() {
  return {
    cuentasElegibles: jest.fn(async (op: string) => ok({ operacion: op, cuentas: op === 'INGRESO'
      ? [{ cuenta_id: CTA, nombre: 'Cuenta Nómina', moneda: 'EUR' }]
      : [{ cuenta_id: CTA, nombre: 'Cuenta Nómina', moneda: 'EUR' }, { cuenta_id: CTA2, nombre: 'Cuenta Común', moneda: 'EUR' }] })),
    listarTerceros: jest.fn(async () => ok({ terceros: [{ id: BANCO, nombre: 'Banco Ejemplo', naturaleza: 'EMPRESA', enabled: true, row_version: 1 }] })),
    senalesTerceros: jest.fn(async () => ok({ terceros: [] })),
    cuadroHipoteca: jest.fn(async () => ok(cuadroPrevio(20))),
  } as unknown as ClienteApi;
}
function patrimonioCompra() {
  const enviados: any[] = [];
  const api = {
    registrarCompra: jest.fn(async (_id: string, p: any) => {
      enviados.push(p);
      return ok({ propiedad: vista({ row_version: 2 }), idempotente: false, compra: { hechos: [], coste_adquisicion: null, sale_de_tus_cuentas: '-1.00',
        liquidez_atribuible: '-1.00', gasto_del_mes: '0.00', atribucion: null }, hipoteca: hipoteca(), aviso_reparto_distinto: false } as ResultadoCompra);
    }),
    gastoCompraPosterior: jest.fn(),
    leerCoste: jest.fn(),
    titularidadEnFecha: jest.fn(async (_id: string, fecha: string) => ok({ fecha, partes: fecha >= '2026-03-20' ? PARTES : ([] as ParteEnFecha[]) })),
  } as unknown as ClientePatrimonio;
  return { api, enviados };
}
function montarCompra(cli: ClienteApi, pat: ClientePatrimonio) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <CompraScreen cliente={cli} patrimonio={pat} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} onRecargar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

async function hastaGuardar() {
  await pulsar('compra-continuar');
  expect(screen.getByTestId('compra-paso-gastos')).toBeTruthy();
  await pulsar('compra-gasto-anadir');
  await pulsar('compra-gasto-0-concepto-AGENCIA');
  await escribir('compra-gasto-0-importe', '60');
  await pulsar(`compra-gasto-0-cuenta-${CTA2}`);
  await escribir('compra-gasto-0-fecha', '28/02/2026');
  await escribir('compra-gasto-0-pago', '28/02/2026');
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId('compra-atr-titularidad'));
  await pulsar('compra-atr-titularidad');
  await pulsar('compra-continuar');
  await pulsar('compra-guardar');
  await screen.findByTestId('compra-hecho');
}

test('wire · compra sin hipoteca: arras 200 + firma 800 de 1.000,00 €, gasto de agencia y reparto según titularidad', async () => {
  const pat = patrimonioCompra();
  montarCompra(clienteCompra(), pat.api);
  await escribir('compra-precio', '1000,00');
  await escribir('compra-escritura', '20/03/2026');
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId(`compra-pago-0-cuenta-${CTA}`));
  await pulsar(`compra-pago-0-cuenta-${CTA}`);
  await escribir('compra-pago-0-importe', '800');
  await siHay('compra-pago-0-confirmar');
  await pulsar('compra-pago-anadir');
  await pulsar('compra-pago-1-rol-ARRAS');
  await pulsar(`compra-pago-1-cuenta-${CTA2}`);
  await escribir('compra-pago-1-fecha', '15/01/2026');
  await escribir('compra-pago-1-importe', '200');
  await siHay('compra-pago-1-confirmar');
  await hastaGuardar();
  expect(pat.enviados).toHaveLength(1);
  comparar('compra_sin_hipoteca', pat.enviados[0]);
});

test('wire · compra con hipoteca: 200.000,00 € pagados desde la cuenta, préstamo de 160.000,00 € y cuadro previo', async () => {
  const pat = patrimonioCompra();
  montarCompra(clienteCompra(), pat.api);
  await escribir('compra-precio', '200000,00');
  await escribir('compra-escritura', '20/03/2026');
  await pulsar('compra-continuar');
  await waitFor(() => screen.getByTestId(`compra-pago-0-cuenta-${CTA}`));
  await pulsar(`compra-pago-0-cuenta-${CTA}`);
  await escribir('compra-pago-0-importe', '200000');
  await siHay('compra-pago-0-confirmar');
  await pulsar('compra-hip-anadir');
  await pulsar('compra-hip-banco');
  await waitFor(() => screen.getByTestId(`tercero-${BANCO}`));
  await pulsar(`tercero-${BANCO}`);
  await escribir('compra-hip-importe', '160.000,00');
  await waitFor(() => screen.getByTestId(`compra-hip-desembolso-${CTA}`));
  await pulsar(`compra-hip-desembolso-${CTA}`);
  await pulsar('compra-hip-tipo-FIJO');
  await escribir('compra-hip-tasa', '2,5');
  await escribir('compra-hip-plazo', '30');
  await escribir('compra-hip-primera', '20/04/2026');
  await waitFor(() => screen.getByTestId(`compra-hip-cargo-${CTA2}`));
  await pulsar(`compra-hip-cargo-${CTA2}`);
  await waitFor(() => expect(screen.getByTestId('compra-hip-titularidad-propuesta').props.accessibilityState).toMatchObject({ checked: true }));
  await hastaGuardar();
  expect(pat.enviados).toHaveLength(1);
  comparar('compra_con_hipoteca', pat.enviados[0]);
});

// ------------------------------------------------------------------ reforma
const propuesta = (fecha = HOY): PropuestaGasto => ({
  fecha, propiedad_id: 'p1', nombre: 'Piso Ejemplo', titularidad_disponible: true,
  partes: [
    { actor_id: ANA, porcentaje: '50.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana', naturaleza: 'PERSONA' },
    { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null, naturaleza: null },
  ],
  cuenta: { cuenta_id: CTA, solo_mia: true, compartida_con: [] },
});

test('wire · reforma: 8.400 € «Cambio de ventanas», «Yo, todo» desde la cuenta nómina, reparto según titularidad y Ana te debe su parte', async () => {
  const registrar = jest.fn(async (p: PayloadGastoPropiedad) => ok({ hecho_id: p.intencion_id, idempotente: false, tipo_hecho: 'MEJORA_PATRIMONIAL', clase: p.clase,
    importe: p.importe, estado_atribucion: 'COMPLETA', atribuciones: [], posiciones: [], intencion_correccion_id: 'x' }));
  const pat = {
    propuestaGasto: jest.fn(async (_id: string, fecha: string) => ok(propuesta(fecha))),
    registrarGastoPropiedad: registrar,
    mejoraHistorica: jest.fn(), listarGastos: jest.fn(), leerGasto: jest.fn(), impactoCorreccion: jest.fn(), corregirClase: jest.fn(),
  } as unknown as ClientePatrimonioB3;
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <GastoPropiedadScreen cliente={clienteCompra()} patrimonio={pat} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  await escribir('gprop-importe', '8400');
  await escribir('gprop-nota', 'Cambio de ventanas');
  if (!hay('gprop-pago-yo')) await pulsar('gprop-continuar');                  // en H, «¿Quién pagó?» es el paso 2
  await pulsar('gprop-pago-yo');
  await pulsar(`gprop-cuenta-${CTA}`);
  if (!hay('gprop-rep-titularidad')) await pulsar('gprop-continuar');          // en H, el reparto es el paso 3
  await waitFor(() => expect(screen.getByTestId('gprop-rep-titularidad').props.accessibilityState?.checked).toBe(true));
  await pulsar(hay('gprop-revisar') ? 'gprop-revisar' : 'gprop-continuar');      // a «Revisar» (H: paso 4)
  await pulsar('gprop-guardar');
  await screen.findByTestId('gprop-hecho');
  expect(registrar).toHaveBeenCalledTimes(1);
  comparar('reforma', registrar.mock.calls[0][0]);
});
