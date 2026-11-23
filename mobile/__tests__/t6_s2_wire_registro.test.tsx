// ============================================================
// GAPTO MOBILE 2027
// Fichero: t6_s2_wire_registro.test.tsx
// Ruta: mobile/__tests__/t6_s2_wire_registro.test.tsx
// Descripción: F06 T6 «UX ágil» · S2 (mandato F06-T6 NOCHE v1.2, P3): sin cambio del wire. Para las mismas entradas,
//   el payload enviado por Registrar gasto / ingreso es IDÉNTICO antes (H = 2c3e532) y después de FORM-AGIL, en tres
//   casos: gasto, gasto de vivienda 50 % e ingreso. Las referencias de `t6_s2_wire_registro.json` se capturaron
//   ejecutando este mismo test sobre H con GAPTO_T6_CAPTURAR_WIRE=1 (evidencia P3).
//   El recorrido es el de un usuario: toca lo que ve. Si un control vive tras una línea de resumen («Se registrará así»)
//   o en «Más opciones», toca antes esa línea; en H esas líneas no existen y el control ya está a la vista.
//   El identificador de la intención es aleatorio por diseño (UUID); se compara su forma, no su valor.
// Versión: 0.1.0 (F06 T6 · S2)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaPago, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonioB3, PropuestaGasto } from '../src/api/patrimonio_b3';
import type { ClientePropiedades } from '../src/api/propiedades';
import type { CategoriaNodo } from '../src/domain/categoria';
import { RegistroGastoScreen } from '../src/screens/RegistroGastoScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

declare const __dirname: string;
declare const process: { env: Record<string, string | undefined> };
const fs: { readFileSync(f: string, e: 'utf8'): string; writeFileSync(f: string, d: string, e: 'utf8'): void; existsSync(f: string): boolean } = require('fs');
const path: { join(...p: string[]): string } = require('path');
const REFERENCIAS = path.join(__dirname, 't6_s2_wire_registro.json');
const CAPTURAR = process.env.GAPTO_T6_CAPTURAR_WIRE === '1';

const AHORA = () => new Date(2026, 9, 26, 10, 0, 0);
const HOY = '2026-10-26';
const C1 = 'c0000000-0000-4000-8000-000000000001';
const CONJ = 'c0000000-0000-4000-8000-000000000002';
const YO = 'f0000000-0000-4000-8000-0000000000ff';
const LUCIA = 'a0000000-0000-4000-8000-0000000000a1';
const P1 = 'p0000000-0000-4000-8000-000000000001';
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const ARBOL: CategoriaNodo[] = [
  nodo({ id: 'hogar', nombre: 'Hogar' }),
  nodo({ id: 'comunidad', nombre: 'Comunidad', parent_id: 'hogar', asociada_vivienda: true }),
  nodo({ id: 'ocio', nombre: 'Ocio', orden: 1, asociada_vivienda: false }),
  nodo({ id: 'nomina', nombre: 'Nómina', orden: 2, ambito: 'INGRESO' }),
];
const CUENTAS: CuentaPago[] = [
  { cuenta_id: C1, nombre: 'Cuenta nómina', moneda: 'EUR', propuesta_financiacion: 'SELF_100' },
  { cuenta_id: CONJ, nombre: 'Cuenta conjunta', moneda: 'EUR', propuesta_financiacion: 'NO_DETERMINADA' },
];
const compartida = (fecha = HOY): PropuestaGasto => ({
  fecha, propiedad_id: P1, nombre: 'Piso Centro', titularidad_disponible: true,
  partes: [
    { actor_id: LUCIA, porcentaje: '50.0000', yo: false, tercero_id: 't-lucia', nombre: 'Lucía', naturaleza: 'PERSONA' },
    { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null, naturaleza: null },
  ],
  cuenta: null,
});

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });

const resultado = (p: any) => ok({ intencion_id: p.intencion_id, hecho_id: p.intencion_id, idempotente: false, importe: p.importe, moneda: 'EUR',
  estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: p.financiacion?.estado ?? 'NO_DETERMINADA', estado_categorial: p.categoria.estado });
function cliente(): ClienteApi {
  return {
    ...clienteCategoriasStub(ARBOL),
    registrarGastoPagado: jest.fn(async (p: any) => resultado(p)) as any,
    registrarIngresoCobrado: jest.fn(async (p: any) => resultado(p)) as any,
    cuentasPago: jest.fn(async () => ok({ cuentas: CUENTAS })),
    cuentasElegibles: jest.fn(async () => ok({ operacion: 'INGRESO', cuentas: CUENTAS.map(({ propuesta_financiacion: _p, ...x }) => x) })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
  } as unknown as ClienteApi;
}
const propiedades = () => ({ listarPropiedades: jest.fn(async () => ok({ propiedades: [
  { id: P1, nombre: 'Piso Centro', enabled: true, row_version: 1, tipo_propiedad: 'VIVIENDA', modo_titularidad: 'COMPARTIDA', valor_estimado: null }] })) }) as unknown as ClientePropiedades;
const patrimonio = () => ({ propuestaGasto: jest.fn(async (_id: string, fecha: string) => ok(compartida(fecha))) }) as unknown as ClientePatrimonioB3;

function montar(c: ClienteApi, tipo: 'GASTO' | 'INGRESO') {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema>
        <RegistroGastoScreen cliente={c} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} onGastoCompartido={jest.fn()} tipo={tipo}
          propiedades={propiedades()} patrimonio={patrimonio()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

/** Línea de resumen («Se registrará así») o entrada de «Más opciones» detrás de la que vive cada control. */
const LINEA: [RegExp, string][] = [
  [/^presupuestable-/, 'linea-presupuesto'],
  [/^cuenta-/, 'linea-cuenta'],
  [/^(solo-mio|repartir|reembolsable)$/, 'linea-quien'],
  [/^fecha-/, 'linea-fecha'],
  [/^(campo-nota|campo-contexto|abrir-mas-detalles)$/, 'mas-opciones'],
];
/** Toca un control como lo haría el usuario: si no está a la vista, abre antes su línea. */
async function tocar(id: string) {
  if (!screen.queryByTestId(id)) {
    const linea = LINEA.find(([re]) => re.test(id))?.[1];
    if (linea && screen.queryByTestId(linea)) await act(async () => fireEvent.press(screen.getByTestId(linea)));
  }
  await act(async () => fireEvent.press(screen.getByTestId(id)));
}
async function escribir(id: string, t: string) {
  if (!screen.queryByTestId(id)) {
    const linea = LINEA.find(([re]) => re.test(id))?.[1];
    if (linea && screen.queryByTestId(linea)) await act(async () => fireEvent.press(screen.getByTestId(linea)));
    if (id === 'campo-nota' && screen.queryByTestId('abrir-mas-detalles')) await act(async () => fireEvent.press(screen.getByTestId('abrir-mas-detalles')));
  }
  await act(async () => fireEvent.changeText(screen.getByTestId(id), t));
}
/** Registrar; con vivienda, la pantalla «Revisar» se confirma (en H no existe). */
async function registrar() {
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  if (screen.queryByTestId('revisar-confirmar')) await act(async () => fireEvent.press(screen.getByTestId('revisar-confirmar')));
  await screen.findByTestId('registro-exito');
}
async function categoria(ruta: string[]) {
  await act(async () => fireEvent.press(screen.getByTestId('campo-categoria')));
  for (const id of ruta) await act(async () => fireEvent.press(screen.getByTestId(`cat-${id}`)));
}

function comparar(caso: string, payload: any) {
  expect(payload.intencion_id).toMatch(UUID);
  const sinId = { ...payload, intencion_id: '<uuid>' };
  if (CAPTURAR) {
    const todas = fs.existsSync(REFERENCIAS) ? JSON.parse(fs.readFileSync(REFERENCIAS, 'utf8')) : {};
    todas[caso] = sinId;
    fs.writeFileSync(REFERENCIAS, JSON.stringify(todas, null, 2) + '\n', 'utf8');
    return;
  }
  const ref = JSON.parse(fs.readFileSync(REFERENCIAS, 'utf8'))[caso];
  expect(ref).toBeDefined();
  expect(sinId).toEqual(ref);
}

test('wire · gasto: 23,40 € de Ocio, presupuesto Sí, cuenta nómina, solo mío, ayer, con nota', async () => {
  const c = cliente();
  montar(c, 'GASTO');
  await screen.findByTestId('campo-importe');
  await escribir('campo-importe', '23,40');
  await categoria(['ocio']);
  await tocar('presupuestable-true');
  await tocar(`cuenta-${C1}`);
  await tocar('solo-mio');
  await tocar('fecha-ayer');
  await escribir('campo-nota', 'Cine');
  await registrar();
  expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
  comparar('gasto', (c.registrarGastoPagado as jest.Mock).mock.calls[0][0]);
});

test('wire · gasto de vivienda 50 %: 180 € de Comunidad en Piso Centro, «Yo, todo» con la cuenta nómina', async () => {
  const c = cliente();
  montar(c, 'GASTO');
  await screen.findByTestId('campo-importe');
  await escribir('campo-importe', '180');
  await categoria(['hogar', 'comunidad']);
  await tocar('presupuestable-true');
  await tocar(`vivienda-prop-${P1}`);
  await screen.findByTestId('vivienda-titularidad');
  await tocar('vivienda-quien-yo');
  await tocar(`cuenta-${C1}`);
  await registrar();
  expect(c.registrarGastoPagado).toHaveBeenCalledTimes(1);
  comparar('vivienda', (c.registrarGastoPagado as jest.Mock).mock.calls[0][0]);
});

test('wire · ingreso: 1.250,00 € de Nómina, presupuesto No, cobrado en la cuenta nómina, solo mío', async () => {
  const c = cliente();
  montar(c, 'INGRESO');
  await screen.findByTestId('campo-importe');
  await escribir('campo-importe', '1.250,00');
  await categoria(['nomina']);
  await tocar('presupuestable-false');
  await tocar(`cuenta-${C1}`);
  await tocar('solo-mio');
  await registrar();
  expect(c.registrarIngresoCobrado).toHaveBeenCalledTimes(1);
  comparar('ingreso', (c.registrarIngresoCobrado as jest.Mock).mock.calls[0][0]);
});
