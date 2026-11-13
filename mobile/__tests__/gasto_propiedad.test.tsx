// ============================================================
// GAPTO MOBILE 2027
// Fichero: gasto_propiedad.test.tsx
// Ruta: mobile/__tests__/gasto_propiedad.test.tsx
// Descripción: B3 · Obras y gastos de una propiedad en el cliente (F06-01 B3; R1 v0.9.5 §III.1bis 3–5, 8, 8bis y 8ter; oráculos v0.7 §A.8 y §A.10.6–§A.10.7, parte cliente) contra dobles en memoria:
//   - O9.8 propuesta según la titularidad de la PROPIEDAD (YO 100) aunque la cuenta sea compartida; O9.9 en la fecha del hecho; O9.10 «No lo sé» y «Otro reparto» no envían SEGUN_TITULARIDAD_ACEPTADA; O9.12 sin titularidad nada marcado y envío bloqueado;
//   - O9.14/O9.15 «Te debe su parte: Sí» por defecto con cuenta solo tuya y cotitular persona, y «No»; O9.16 cuenta compartida sin preselección, importe a mano sin valor previo y aportación MANUAL; O9.18 EMPRESA y O9.21 «No lo sé» no ofrecen; O9.20 la mejora histórica no ofrece;
//   - O9.23 confirmación (quién, cuánto, concepto, parte atribuida, «Se creará un derecho de cobro» y la atribución que se persistirá) y `derechos_confirmados` = exactamente lo mostrado; ATRIBUCION_PROPUESTA_DESFASADA vuelve al reparto con la propuesta releída.
// Versión: 0.1.0 (F06 T1-F06 B3 N1)
// Versión: 0.2.0 (F06 T1-F06 B3 ajuste N3 · decisión de Moisés 2026-11-13 «B3 alcance y CAT-VIV» v1.0): cambio DECLARADO de alcance de pantalla: el alta solo ofrece
//   «Reforma o mejora» (MEJORA fijada, sin chips de clase ni categoría/presupuesto). El test C1 de las tres clases pasa a fijar ese alcance; la
//   regla de dominio de las tres clases (faltasDatos) sigue cubierta y la corrección de clase (C-MEJ-03) no cambia.
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { ClientePatrimonioB3, PayloadGastoPropiedad, PropuestaGasto } from '../src/api/patrimonio_b3';
import type { VistaPropiedad } from '../src/api/propiedades';
import {
  alCambiarPropuesta, borradorInicial, BorradorGastoPropiedad, derechos, faltasDatos, faltasReparto, payloadGastoPropiedad, payloadMejoraHistorica,
  repartirImporte, repartoInicial, TEXTO_SE_CREA_DERECHO, textoPropuesta,
} from '../src/domain/gasto_propiedad';
import { GastoPropiedadScreen, MejoraHistoricaScreen } from '../src/screens/GastoPropiedadScreen';
import { ProveedorTema } from '../src/theme/tema';

const YO = 'f0000000-0000-4000-8000-0000000000ff';
const ANA = 'a0000000-0000-4000-8000-0000000000a1';
const C1 = 'c0000000-0000-4000-8000-0000000000c1';
const C2 = 'c0000000-0000-4000-8000-0000000000c2';
const CAT = 'ca000000-0000-4000-8000-0000000000ca';
const AHORA = () => new Date(2026, 9, 10, 10);
const HOY = '2026-10-10';
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;

const prop = (o: Partial<PropuestaGasto> & { naturaleza?: 'PERSONA' | 'EMPRESA'; soloMia?: boolean | null } = {}): PropuestaGasto => ({
  fecha: HOY, propiedad_id: 'p1', nombre: 'Piso Ejemplo', titularidad_disponible: true,
  partes: [
    { actor_id: ANA, porcentaje: '50.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana', naturaleza: o.naturaleza ?? 'PERSONA' },
    { actor_id: YO, porcentaje: '50.0000', yo: true, tercero_id: null, nombre: null, naturaleza: null },
  ],
  cuenta: o.soloMia === null ? null : { cuenta_id: C1, solo_mia: o.soloMia ?? true, compartida_con: o.soloMia === false ? [ANA] : [] },
  ...o,
});

function vista(): VistaPropiedad {
  return {
    id: 'p1', nombre: 'Piso Ejemplo', enabled: true, row_version: 3, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: '2026-03-20', superficie_m2: null,
    superficie_construida_m2: null, habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
    incluir_en_rentabilidad: true, notas: null, fecha_consulta: HOY,
    titularidad: { modo: 'COMPARTIDA', desde: '2026-03-20', partes: [
      { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '50.0000' },
      { actor_id: ANA, yo: false, tercero_id: 't-ana', nombre: 'Ana', porcentaje: '50.0000' }] },
    cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [],
  } as VistaPropiedad;
}

const borrador = (o: Partial<BorradorGastoPropiedad> = {}): BorradorGastoPropiedad => ({ ...borradorInicial(HOY), clase: 'MEJORA', importe: '300', cuentaId: C1, ...o });

// ------------------------------------------------------------------ dominio
test('O9.8: propiedad SOLO_MIA pagada con cuenta compartida → propuesta YO 100; la cuenta no entra en la propuesta', () => {
  const q: PropuestaGasto = { ...prop({ soloMia: false }), partes: [{ actor_id: YO, porcentaje: '100.0000', yo: true, tercero_id: null, nombre: null, naturaleza: null }] };
  const b = alCambiarPropuesta(borrador(), q, q.partes);
  expect(b.reparto).toEqual({ modo: 'TITULARIDAD' });
  const p = payloadGastoPropiedad('i1', 'p1', b, q, q.partes, derechos(b, q, q.partes, 'x'));
  expect(p.atribucion).toEqual({ modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_HECHO', fecha_referencia: HOY,
    partes: [{ actor_id: YO, porcentaje: '100.0000' }] } });
  expect(JSON.stringify(p.atribucion)).not.toContain(C1);
  expect(p.deuda).toEqual([]);
  expect(p.derechos_confirmados).toEqual([]);
});

test('O9.9: la propuesta y la fecha de referencia son las de la FECHA DEL HECHO', () => {
  const q = prop({ fecha: '2026-05-15' });
  const b = alCambiarPropuesta(borrador({ fecha: '2026-05-15' }), q, q.partes);
  const p = payloadGastoPropiedad('i1', 'p1', b, q, q.partes, []);
  expect(p.fecha_hecho).toBe('2026-05-15');
  expect(p.atribucion).toEqual(expect.objectContaining({ propuesta_vista: expect.objectContaining({ fecha_referencia: '2026-05-15' }) }));
  expect(textoPropuesta('Piso Ejemplo', q)).toBe('Según la titularidad de Piso Ejemplo el 15 may 2026: tú 50 %, Ana 50 %');
});

test('O9.10: con «No lo sé» o «Otro reparto» nunca se envía SEGUN_TITULARIDAD_ACEPTADA', () => {
  const q = prop();
  const nolose = payloadGastoPropiedad('i', 'p1', borrador({ reparto: { modo: 'NO_LO_SE' } }), q, q.partes, []);
  expect(nolose.atribucion).toEqual({ modo: 'NO_LO_SE' });
  expect(nolose.deuda).toEqual([]);
  const manual = payloadGastoPropiedad('i', 'p1', borrador({ reparto: { modo: 'MANUAL', partes: { [YO]: '70', [ANA]: '30' } } }), q, q.partes, []);
  expect(manual.atribucion).toEqual({ modo: 'MANUAL', partes: [{ actor_id: YO, porcentaje: '70' }, { actor_id: ANA, porcentaje: '30' }] });
});

test('O9.12: sin titularidad en la fecha no se marca nada (nunca YO 100) y falta elegir', () => {
  const q = { ...prop(), titularidad_disponible: false, partes: [] };
  expect(repartoInicial(q)).toBeNull();
  const b = alCambiarPropuesta(borrador(), q, []);
  expect(b.reparto).toBeNull();
  expect(faltasReparto(b, q, [])).toEqual(['elegir de quién es el gasto']);
});

test('O9.14 / O9.15: Sí por defecto (cuenta solo tuya, persona) con el importe de su parte; «No» lo quita', () => {
  const q = prop();
  const b = alCambiarPropuesta(borrador(), q, q.partes);
  expect(b.deuda[ANA]).toEqual({ me_debe: 'SI', importe: '' });
  const d = derechos(b, q, q.partes, 'Cocina · Piso Ejemplo');
  expect(d).toEqual([{ actor_id: ANA, nombre: 'Ana', importe: '150.00', parte: '150.00', porcentaje: '50.0000', concepto: 'Cocina · Piso Ejemplo' }]);
  const p = payloadGastoPropiedad('i', 'p1', b, q, q.partes, d);
  expect(p.deuda).toEqual([{ actor_id: ANA, me_debe: 'SI' }]);
  expect(p.derechos_confirmados).toEqual([{ actor_id: ANA, importe: '150.00' }]);
  expect(p.aportacion_indicada).toBeNull();
  const no = { ...b, deudaTocada: true, deuda: { [ANA]: { me_debe: 'NO' as const, importe: '' } } };
  const pn = payloadGastoPropiedad('i', 'p1', no, q, q.partes, derechos(no, q, q.partes, 'x'));
  expect(pn.deuda).toEqual([{ actor_id: ANA, me_debe: 'NO' }]);
  expect(pn.derechos_confirmados).toEqual([]);
});

test('O9.16: cuenta compartida → sin preselección, importe sin valor previo y aportación MANUAL', () => {
  const q = prop({ soloMia: false });
  const b = alCambiarPropuesta(borrador(), q, q.partes);
  expect(b.deuda[ANA]).toEqual({ me_debe: null, importe: '' });
  expect(faltasReparto(b, q, q.partes)).toEqual(['elegir si Ana te debe su parte']);
  const si = { ...b, deudaTocada: true, deuda: { [ANA]: { me_debe: 'SI' as const, importe: '' } } };
  expect(faltasReparto(si, q, q.partes)).toEqual(['cuánto te debe Ana (como mucho su parte)']);
  const mas = { ...si, deuda: { [ANA]: { me_debe: 'SI' as const, importe: '150,01' } } };
  expect(faltasReparto(mas, q, q.partes)).toHaveLength(1);
  const bien = { ...si, deuda: { [ANA]: { me_debe: 'SI' as const, importe: '120' } } };
  expect(faltasReparto(bien, q, q.partes)).toEqual([]);
  const p = payloadGastoPropiedad('i', 'p1', bien, q, q.partes, derechos(bien, q, q.partes, 'x'));
  expect(p.aportacion_indicada).toBe('MANUAL');
  expect(p.derechos_confirmados).toEqual([{ actor_id: ANA, importe: '120.00' }]);
});

test('O9.18 / O9.21: EMPRESA y «No lo sé» no ofrecen «Te debe su parte»', () => {
  const qe = prop({ naturaleza: 'EMPRESA' });
  const be = alCambiarPropuesta(borrador(), qe, qe.partes);
  expect(be.deuda).toEqual({});
  const pe = payloadGastoPropiedad('i', 'p1', be, qe, qe.partes, derechos(be, qe, qe.partes, 'x'));
  expect(pe.deuda).toEqual([{ actor_id: ANA, me_debe: 'NO' }]);
  expect(pe.derechos_confirmados).toEqual([]);
  const q = prop();
  const bn = borrador({ reparto: { modo: 'NO_LO_SE' }, repartoTocado: true });
  expect(derechos(bn, q, q.partes, 'x')).toEqual([]);
});

test('O9.20: la mejora histórica no lleva deuda ni derechos', () => {
  const q = prop();
  const p = payloadMejoraHistorica('i', 3, 'Reforma integral', '12000', '2019-03-14', { modo: 'TITULARIDAD' }, q);
  expect(p).not.toHaveProperty('deuda');
  expect(p).not.toHaveProperty('derechos_confirmados');
  expect(p.importe).toBe('12000.00');
});

test('§1.2: reparto HALF_EVEN con residuo determinista (suma = total)', () => {
  expect(repartirImporte('100.00', [{ actor_id: 'a', porcentaje: '33.3333' }, { actor_id: 'b', porcentaje: '33.3333' }, { actor_id: 'c', porcentaje: '33.3334' }]))
    .toEqual({ a: '33.33', b: '33.33', c: '33.34' });
  expect(repartirImporte('0.05', [{ actor_id: 'a', porcentaje: '50' }, { actor_id: 'b', porcentaje: '50' }])).toEqual({ a: '0.03', b: '0.02' });
});

test('clase: sin valor por defecto; Mejora sin categoría ni presupuesto y las otras dos los exigen', () => {
  expect(faltasDatos({ ...borradorInicial(HOY), importe: '1', cuentaId: C1 })).toEqual(['la clase del gasto']);
  expect(faltasDatos(borrador({ clase: 'REPARACION' }))).toEqual(['la categoría', 'si cuenta para el presupuesto']);
  const p = payloadGastoPropiedad('i', 'p1', borrador({ clase: 'MEJORA', categoriaId: CAT, presupuestable: true }), prop(), prop().partes, []);
  expect(p.categoria_id).toBeNull();
  expect(p.presupuestable).toBeNull();
});

// ------------------------------------------------------------------ pantallas
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
beforeEach(() => { n = 0; });
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const marcado = (id: string) => !!screen.getByTestId(id).props.accessibilityState?.checked;
const cliente = () => ({
  cuentasElegibles: jest.fn(async () => ok({ operacion: 'GASTO', cuentas: [{ cuenta_id: C1, nombre: 'Cuenta Nómina', moneda: 'EUR' }, { cuenta_id: C2, nombre: 'Cuenta Común', moneda: 'EUR' }] })),
  arbolCategorias: jest.fn(async () => ok({ categorias: [{ id: CAT, nombre: 'Reparaciones', parent_id: null, enabled: true, ambito: 'GASTO', capturable: true, magnitudes: [], motivo_no_capturable: null, orden: 0, icon_key: null }] })),
}) as unknown as ClienteApi;

function patrimonio(q: (fecha: string, cuenta?: string | null) => PropuestaGasto, registrar?: jest.Mock) {
  return {
    propuestaGasto: jest.fn(async (_id: string, fecha: string, cuenta?: string | null) => ok(q(fecha, cuenta))),
    registrarGastoPropiedad: registrar ?? jest.fn(async (p: PayloadGastoPropiedad) => ok({ hecho_id: p.intencion_id, idempotente: false, tipo_hecho: 'MEJORA_PATRIMONIAL', clase: p.clase,
      importe: p.importe, estado_atribucion: 'COMPLETA', atribuciones: [], posiciones: [], intencion_correccion_id: 'x' })),
    mejoraHistorica: jest.fn(async () => ok({})),
    listarGastos: jest.fn(), leerGasto: jest.fn(), impactoCorreccion: jest.fn(), corregirClase: jest.fn(),
  } as unknown as ClientePatrimonioB3 & Record<string, jest.Mock>;
}

async function montar(pat: ClientePatrimonioB3) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <GastoPropiedadScreen cliente={cliente()} patrimonio={pat} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

async function datosMejora() {
  await escribir('gprop-importe', '300');
  await pulsar(`gprop-cuenta-${C1}`);
  await pulsar('gprop-continuar');
}

test('C1 (ajuste N3, decisión 2026-11-13): el alta solo ofrece «Reforma o mejora»; sin Reparación, Gasto corriente, categoría ni presupuesto', async () => {
  await montar(patrimonio(() => prop()));
  expect(screen.getByText('Reforma o mejora (aumenta el valor)')).toBeTruthy();
  for (const k of ['MEJORA', 'REPARACION', 'GASTO_CORRIENTE']) expect(screen.queryByTestId(`gprop-clase-${k}`)).toBeNull();
  expect(screen.queryByTestId('gprop-sin-clase')).toBeNull();
  expect(screen.queryByTestId(`gprop-categoria-${CAT}`)).toBeNull();
  expect(screen.queryByTestId('gprop-presupuestable-si')).toBeNull();
  expect(screen.getByTestId('gprop-nota-registrar-gasto')).toBeTruthy();
  await escribir('gprop-importe', '300');
  await pulsar(`gprop-cuenta-${C1}`);
  expect(screen.queryByTestId('gprop-faltas')).toBeNull();   // la clase ya no falta: va fijada a MEJORA
  await pulsar('gprop-continuar');
  expect(screen.getByTestId('gprop-paso-reparto')).toBeTruthy();
});

test('O9.14 + O9.23: reparto marcado, «Sí» por defecto, confirmación visible y derechos_confirmados = lo mostrado', async () => {
  const pat = patrimonio(() => prop());
  await montar(pat);
  await datosMejora();
  expect(pat.propuestaGasto).toHaveBeenLastCalledWith('p1', HOY, C1);           // fecha del HECHO y la cuenta elegida
  expect(marcado('gprop-rep-titularidad')).toBe(true);
  expect(screen.getByTestId('gprop-rep-titularidad').props.accessibilityLabel).toBe('Según la titularidad de Piso Ejemplo el 10 oct 2026: tú 50 %, Ana 50 %');
  expect(marcado(`gprop-debe-${ANA}-si`)).toBe(true);
  await pulsar('gprop-continuar');
  expect(screen.getByTestId(`gprop-derecho-${ANA}-quien`).props.children).toBe('Ana te debe 150,00 €');
  expect(screen.getByTestId(`gprop-derecho-${ANA}-aviso`).props.children).toBe(TEXTO_SE_CREA_DERECHO);
  expect(screen.getByText('Parte que se le atribuye: 50 % · 150,00 €')).toBeTruthy();
  expect(screen.getByTestId(`gprop-atr-${ANA}`)).toBeTruthy();
  await pulsar('gprop-guardar');
  const body = (pat.registrarGastoPropiedad as jest.Mock).mock.calls[0][0] as PayloadGastoPropiedad;
  expect(body.derechos_confirmados).toEqual([{ actor_id: ANA, importe: '150.00' }]);
  expect(body.deuda).toEqual([{ actor_id: ANA, me_debe: 'SI' }]);
  expect(body.atribucion.modo).toBe('SEGUN_TITULARIDAD_ACEPTADA');
  expect(screen.getByTestId('gprop-hecho')).toBeTruthy();
});

test('O9.15 + O9.23: si cambia a «No», el derecho desaparece de la confirmación y del envío', async () => {
  const pat = patrimonio(() => prop());
  await montar(pat);
  await datosMejora();
  await pulsar(`gprop-debe-${ANA}-no`);
  await pulsar('gprop-continuar');
  expect(screen.queryByTestId(`gprop-derecho-${ANA}`)).toBeNull();
  expect(screen.queryByText(TEXTO_SE_CREA_DERECHO)).toBeNull();
  await pulsar('gprop-guardar');
  const body = (pat.registrarGastoPropiedad as jest.Mock).mock.calls[0][0] as PayloadGastoPropiedad;
  expect(body.derechos_confirmados).toEqual([]);
  expect(body.deuda).toEqual([{ actor_id: ANA, me_debe: 'NO' }]);
});

test('O9.16: cuenta compartida → nada marcado, el envío exige elegir y el importe se teclea', async () => {
  const pat = patrimonio(() => prop({ soloMia: false }));
  await montar(pat);
  await datosMejora();
  expect(marcado(`gprop-debe-${ANA}-si`) || marcado(`gprop-debe-${ANA}-no`)).toBe(false);
  expect(screen.getByTestId('gprop-faltas').props.children).toContain('elegir si Ana te debe su parte');
  await pulsar(`gprop-debe-${ANA}-si`);
  expect(screen.getByTestId(`gprop-debe-${ANA}-importe`).props.value).toBe('');
  await escribir(`gprop-debe-${ANA}-importe`, '120');
  await pulsar('gprop-continuar');
  await pulsar('gprop-guardar');
  const body = (pat.registrarGastoPropiedad as jest.Mock).mock.calls[0][0] as PayloadGastoPropiedad;
  expect(body.aportacion_indicada).toBe('MANUAL');
  expect(body.derechos_confirmados).toEqual([{ actor_id: ANA, importe: '120.00' }]);
});

test('O9.18: cotitular EMPRESA → «Te debe su parte» no se ofrece', async () => {
  await montar(patrimonio(() => prop({ naturaleza: 'EMPRESA' })));
  await datosMejora();
  expect(screen.queryByTestId(`gprop-debe-${ANA}`)).toBeNull();
  expect(screen.getByTestId(`gprop-no-debe-${ANA}`)).toBeTruthy();
});

test('O9.12 / O9.21: sin titularidad nada marcado y bloqueado; con «No lo sé» no se ofrece la deuda', async () => {
  const pat = patrimonio(() => ({ ...prop(), titularidad_disponible: false, partes: [] }));
  await montar(pat);
  await datosMejora();
  expect(screen.queryByTestId('gprop-rep-titularidad')).toBeNull();
  expect(screen.getByTestId('gprop-rep-sin-titularidad')).toBeTruthy();
  expect(screen.getByTestId('gprop-faltas').props.children).toContain('elegir de quién es el gasto');
  await pulsar('gprop-rep-no-lo-se');
  expect(screen.queryByTestId(`gprop-debe-${ANA}`)).toBeNull();
  expect(screen.queryByTestId('gprop-faltas')).toBeNull();
});

test('ATRIBUCION_PROPUESTA_DESFASADA: vuelve al reparto con la propuesta releída y otra intención', async () => {
  const registrar = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'ATRIBUCION_PROPUESTA_DESFASADA', mensaje: '' }));
  const pat = patrimonio(() => prop(), registrar as unknown as jest.Mock);
  await montar(pat);
  await datosMejora();
  await pulsar('gprop-continuar');
  const llamadas = (pat.propuestaGasto as jest.Mock).mock.calls.length;
  await pulsar('gprop-guardar');
  expect(screen.getByTestId('gprop-paso-reparto')).toBeTruthy();
  expect(screen.getByTestId('gprop-rep-aviso')).toBeTruthy();
  expect((pat.propuestaGasto as jest.Mock).mock.calls.length).toBeGreaterThan(llamadas);
  await pulsar('gprop-continuar');
  await pulsar('gprop-guardar');
  const [a, b] = registrar.mock.calls.map((c: any[]) => (c[0] as PayloadGastoPropiedad).intencion_id);
  expect(a).not.toBe(b);
});

test('O9.20 (pantalla): la mejora histórica no ofrece «Te debe su parte»', async () => {
  const pat = patrimonio(() => prop());
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <MejoraHistoricaScreen patrimonio={pat} vista={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={jest.fn()} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  expect(screen.getByTestId('mh-sin-pago')).toBeTruthy();
  expect(screen.queryByText(/te debe/i)).toBeNull();
  expect(marcado('mh-rep-titularidad')).toBe(true);
});
