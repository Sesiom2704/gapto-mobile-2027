// ============================================================
// GAPTO MOBILE 2027
// Fichero: registro_tipo.test.tsx
// Ruta: mobile/__tests__/registro_tipo.test.tsx
// Descripción: Inicio HOME-01 v0.3 con la marca del AJUSTE A1 y el registro por tipo (F05-03/F05-04 J2+J3 §2.1–§2.4; láminas HOME-01 v0.3, HOME-QA v0.2 H01–H03, REG-DYN T01/T02/G01–G03/I01/X01/N01 y REG-PLT R01–R06). Inicio: cabecera de marca como UN elemento accesible «GaptoMobile» (sin «2027» ni lema), ilustración decorativa oculta, «Registrar» abre la hoja SIN preselección, accesos (máx. 3) y estado sin accesos. Ingreso cobrado: cuentas para cobrar, categorías por tipo, payload y éxito. Gasto con tercero (propuesta del registro por tipo). Cambio de tipo T02 antes del primer envío y fijado después. «No lo sé» en una obligatoria. Plantilla desde un acceso: chip, origen «De tu plantilla …», «Quitar» y campos tocados no se pisan. «Entre cuentas»: misma cuenta, payload, reintento con la MISMA identidad, FECHA_FUTURA. Éxito: «Guardar como plantilla» (nombre obligatorio y nunca autocompletado) y «Guardar como preferencia» para el tercero o la categoría. SHA de los 18 PNG de marca.
// Versión: 0.1.0 (F05-03/F05-04 J2+J3 §2.1–§2.4; AJUSTE A1)
// Versión: 0.2.0 (F05-03/F05-04 J3 §2.7 y §3): corte de Concepto (CNC-18/20) y casos de cierre §45.7-6 (plantilla con magnitud obligatoria) y §46.7-11 (duplicado activo «Usar el existente»).
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, CuentaPago, Plantilla, Respuesta, ResultadoRegistro } from '../src/api/cliente';
import type { PayloadGastoPagado } from '../src/domain/intencion';
import { borradorInicial } from '../src/domain/intencion';
import { accesosDeInicio, resultadoDelMes, TEXTO_SIN_ACCESOS } from '../src/domain/inicio';
import { aplicarCamposPlantilla, quitarPlantilla } from '../src/domain/registro';
import { TEXTO_FECHA_FUTURA } from '../src/screens/RegistroGastoScreen';
import { TEXTO_MISMA_CUENTA } from '../src/screens/TransferenciaScreen';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, mag, nodo } from './fixtures_categorias';

/** F05-04 §2.7 (corte de Concepto): la nota opcional se escribe en «Más detalles». */
function escribirNota(t: string) {
  if (!screen.queryByTestId('campo-nota')) fireEvent.press(screen.getByTestId('abrir-mas-detalles'));
  fireEvent.changeText(screen.getByTestId('campo-nota'), t);
}

declare const __dirname: string;
const fs: { readFileSync(f: string): Uint8Array } = require('fs');
const path: { join(...p: string[]): string } = require('path');
const crypto: { createHash(a: string): { update(b: Uint8Array): { digest(e: 'hex'): string } } } = require('crypto');

const TARJETA = 'c0000000-0000-4000-8000-00000000000a';
const NOMINA = 'c0000000-0000-4000-8000-00000000000b';
const AHORRO = 'c0000000-0000-4000-8000-00000000000c';
const AHORA = () => new Date(2026, 9, 10, 10, 0, 0);
const HOY = '2026-10-10';
const TIPOS = { GASTO: 't-gasto', INGRESO: 't-ingreso' };

const ARBOL = [
  nodo({ id: 'alim', nombre: 'Alimentación' }),
  nodo({ id: 'super', nombre: 'Supermercado', parent_id: 'alim', icon_key: 'alimentacion.carrito' }),
  nodo({ id: 'coche', nombre: 'Coche', orden: 1 }),
  nodo({ id: 'gasolina', nombre: 'Gasolina', parent_id: 'coche', magnitudes: [mag({ magnitud_id: 'litros', nombre: 'Litros', unidad_default: 'l' })] }),
  nodo({ id: 'trabajo', nombre: 'Trabajo', ambito: 'INGRESO', orden: 2 }),
  nodo({ id: 'nomina', nombre: 'Nómina', parent_id: 'trabajo', ambito: 'INGRESO' }),
];

const okGasto = (p: PayloadGastoPagado): Respuesta<ResultadoRegistro> => ({
  tipo: 'OK',
  datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'NO_DISPONIBLE', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado },
});

const plt = (p: Partial<Plantilla> & { id: string; nombre: string }): Plantilla => ({
  tipo_hecho_id: TIPOS.GASTO, categoria_id: null, tercero_id: null, entidad_id: null, cuenta_default_id: null, presupuestable_default: null,
  enabled: true, row_version: 1, tipo: 'GASTO', avisos: [], ...p,
});

function fake(o: { plantillas?: Plantilla[]; acciones?: any[]; propuesta?: (q: any) => any; transferencia?: (p: any) => Promise<any>; ingreso?: (p: any) => Promise<any> } = {}) {
  const cliente: ClienteApi = {
    ...clienteCategoriasStub(ARBOL),
    registrarGastoPagado: jest.fn(async (p: PayloadGastoPagado) => okGasto(p)),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [{ cuenta_id: TARJETA, nombre: 'Tarjeta BBVA', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasElegibles: jest.fn(async (operacion: any) => {
      const l = operacion === 'INGRESO' ? [{ cuenta_id: NOMINA, nombre: 'Cuenta nómina', moneda: 'EUR' }]
        : operacion === 'GASTO' ? [] : [{ cuenta_id: NOMINA, nombre: 'Cuenta nómina', moneda: 'EUR' }, { cuenta_id: AHORRO, nombre: 'Ahorro', moneda: 'EUR' }];
      return { tipo: 'OK', datos: { operacion, cuentas: l } } as any;
    }),
    listarTerceros: jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [{ id: 'ter-aldi', nombre: 'ALDI', naturaleza: 'EMPRESA', enabled: true, row_version: 1 }] } }) as any),
    listarPlantillas: jest.fn(async () => ({ tipo: 'OK', datos: { plantillas: o.plantillas ?? [], acciones: o.acciones ?? [] } }) as any),
    propuestaRegistro: jest.fn(async (q: any) => ({ tipo: 'OK', datos: o.propuesta?.(q) ?? { tipo: q.tipo, campos: { categoria: null, tercero: null, contexto: null, cuenta: null, presupuestable: null }, avisos: [] } }) as any),
    registrarIngresoCobrado: jest.fn(o.ingreso ?? (async (p: any) => ({ tipo: 'OK', datos: { intencion_id: p.intencion_id, hecho_id: 'h1', idempotente: false, tipo: 'INGRESO', importe: p.importe, moneda: 'EUR', estado_atribucion: 'NO_DISPONIBLE', estado_categorial: p.categoria.estado } }))) as any,
    registrarTransferencia: jest.fn(o.transferencia ?? (async (p: any) => ({ tipo: 'OK', datos: { intencion_id: p.intencion_id, hecho_id: 'h2', idempotente: false, tipo: 'TRANSFERENCIA', importe: p.importe, moneda: 'EUR', estado_atribucion: null, estado_categorial: null } }))) as any,
  };
  return cliente;
}

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
  await screen.findByTestId('accion-registrar');
  await act(async () => undefined);
}

async function pulsar(id: string) {
  await act(async () => fireEvent.press(screen.getByTestId(id)));
}

async function abrirTipo(t: 'GASTO' | 'INGRESO' | 'TRANSFERENCIA') {
  await pulsar('accion-registrar');
  await pulsar(`tipo-${t}`);
}

function elegirCategoria(padre: string, hija: string) {
  fireEvent.press(screen.getByTestId('campo-categoria'));
  fireEvent.press(screen.getByTestId(`cat-${padre}`));
  fireEvent.press(screen.getByTestId(`cat-${hija}`));
}

// ------------------------------------------------------------------ Inicio (A1, §2.1)
test('A1: cabecera de marca como UN elemento «GaptoMobile» con rol de cabecera; sin «2027» ni lema; ilustración oculta', async () => {
  await montar(fake());
  const marca = screen.getByTestId('marca-inicio');
  expect(marca.props.accessibilityLabel).toBe('GaptoMobile');
  expect(marca.props.accessibilityRole).toBe('header');
  expect(marca.props.accessible).toBe(true);
  expect(screen.getByTestId('marca-simbolo').props.style).toEqual({ width: 34, height: 34 });
  expect(screen.getByTestId('marca-nombre').props.style).toEqual({ width: 132.25, height: 24 });
  expect(screen.getByTestId('marca-nombre').props.resizeMode).toBe('contain');
  expect(screen.queryByText(/2027/)).toBeNull();
  expect(screen.queryByText('TUS FINANZAS, EN EQUILIBRIO')).toBeNull();
  expect(screen.queryByTestId('ilustracion-liquidez')).toBeNull(); // oculta a la accesibilidad
  const ilu = screen.getByTestId('ilustracion-liquidez', { includeHiddenElements: true });
  expect(ilu.props.style).toEqual({ width: 112, height: 112 });
});

test('A1: los PNG de marca del repositorio tienen el SHA-256 de la entrega (§3.1 y manifest)', () => {
  const esperado: Record<string, string> = {
    'gm-simbolo-cabecera-claro.png': '7708f41bbeca5ab83cbfe4c5ba458c50f6a2218e03dacc8c35200ff0cd4e4b19',
    'gm-simbolo-cabecera-claro@2x.png': 'dde602b5598799cb29b97cc395659cea08d2505d5ba66e086ecb602fda6f7eed',
    'gm-simbolo-cabecera-claro@3x.png': 'd0dda0491c66f45d3811e1b27345ffd7f6d29bc52d58c1bbb73a944014230e47',
    'gm-simbolo-cabecera-oscuro.png': '9450292aff656f3d67e187b99f597cb550a993267db5cdd0b924d5f1666b6caa',
    'gm-simbolo-cabecera-oscuro@2x.png': '2e59af3029c544a5734639e2a0a053bc9c47aa90f7df7e41ed8a53ea319dfac3',
    'gm-simbolo-cabecera-oscuro@3x.png': '1eda1e1753b7f873325c180017e366a16a8430affdc149d6439036e8e6bca5eb',
    'gm-nombre-claro.png': '94061686ef237d4413858130858e7373b3213c831a59383f8876d31fe8a340a5',
    'gm-nombre-claro@2x.png': '967b2879dc523c79290af57bd500a242198b76ad337a95908a1dbda001f5b402',
    'gm-nombre-claro@3x.png': '4c96dd253a260bf26a31146a1390b66253a114a6f6b7dfcc3a0078ac500bf9b8',
    'gm-nombre-oscuro.png': '7a3a0aa347d4ee8bfaf5a810444e9692e38278cdd04de4c2df6141b29bb68612',
    'gm-nombre-oscuro@2x.png': 'be8c969c830154998a13982878d7844a9007ba4577b6037418c3b75963ab388c',
    'gm-nombre-oscuro@3x.png': '3a167e1b13cd8ea0166b2b0195cd130eedfd9d2db2b446276633406a3a32e437',
    // Ausente de la tabla §3.1 de la entrega; SHA del manifest MANIFEST_SHA256.txt verificado (discrepancia declarada).
    'gm-ilustracion-liquidez-claro.png': '75f18c7a7e70f6e5a78cc968718c616fae637f176ca86a55eec66d04585282e6',
    'gm-ilustracion-liquidez-claro@2x.png': '53670a36c4dd3d026388372b7ed73210c4fb3b88660ad25b2cdd8e519dda00fb',
    'gm-ilustracion-liquidez-claro@3x.png': 'a2bf3fc334fef2abf799e593ca4f8c28942a8f0e0b10cd45173d5ab2f6808bc5',
    'gm-ilustracion-liquidez-oscuro.png': 'a6d8f25380ab21f56386a8bb6595f59b17060b915609c1054a2cb1c29877fd6b',
    'gm-ilustracion-liquidez-oscuro@2x.png': '457f1f02b22a27782dfa2b2316de14edf28df22326aa4fa9960096ed033e168a',
    'gm-ilustracion-liquidez-oscuro@3x.png': '08083df3c9589b2cdb599034effba7849a9e5c07346c6f7859a99708d0000bfc',
  };
  expect(Object.keys(esperado)).toHaveLength(18);
  for (const [f, sha] of Object.entries(esperado)) {
    const datos = fs.readFileSync(path.join(__dirname, '..', 'assets', 'marca', f));
    expect([f, crypto.createHash('sha256').update(datos).digest('hex')]).toEqual([f, sha]);
  }
});

test('§2.1: «Registrar» abre la hoja de tipos SIN preselección; sin accesos, «Añadir acceso» y el texto H03', async () => {
  await montar(fake());
  expect(screen.getByTestId('accesos-vacio').props.children).toBe(TEXTO_SIN_ACCESOS);
  await pulsar('accion-registrar');
  for (const t of ['GASTO', 'INGRESO', 'TRANSFERENCIA']) expect(screen.getByTestId(`tipo-${t}`).props.accessibilityState.selected).toBe(false);
  expect(screen.getByTestId('nota-devolucion')).toBeTruthy();
  await pulsar('tipos-cancelar');
  expect(screen.queryByTestId('hoja-tipos')).toBeNull();
  await pulsar('acceso-anadir');
  expect(await screen.findByTestId('pantalla-plantillas')).toBeTruthy();
});

test('§2.1 (dominio): accesos máx. 3 en el orden de Inicio; Resultado con signo y tono', () => {
  const p = [1, 2, 3, 4].map((i) => plt({ id: `p${i}`, nombre: `P${i}`, categoria_id: 'super' }));
  const a = [3, 1, 2, 0].map((o, i) => ({ id: `a${i}`, nombre: `A${i}`, plantilla_registro_id: `p${i + 1}`, orden: o, icono_key: null, enabled: true, row_version: 1 }));
  const l = accesosDeInicio(p, a, () => 'alimentacion.carrito');
  expect(l.map((x) => x.accion.id)).toEqual(['a3', 'a1', 'a2']);
  expect(l[0].iconoKey).toBe('alimentacion.carrito');
  expect(resultadoDelMes('120.00')).toEqual({ texto: '+120,00 €', tono: 'positive' });
  expect(resultadoDelMes('-35.50')).toEqual({ texto: '−35,50 €', tono: 'critical' });
  expect(resultadoDelMes('0.00')).toEqual({ texto: '0,00 €', tono: 'neutral' });
});

// ------------------------------------------------------------------ Ingreso
test('Ingreso: «Cobrado en» con cuentas para cobrar, solo categorías de ingreso, payload sin concepto y éxito', async () => {
  const c = fake();
  await montar(c);
  await abrirTipo('INGRESO');
  expect(screen.getByText('Nuevo ingreso')).toBeTruthy();
  expect(screen.queryByTestId('campo-concepto')).toBeNull();
  await waitFor(() => expect(screen.getByTestId(`cuenta-${NOMINA}`)).toBeTruthy());
  expect(c.cuentasElegibles).toHaveBeenCalledWith('INGRESO', HOY);
  expect(screen.queryByTestId(`cuenta-${TARJETA}`)).toBeNull();
  fireEvent.changeText(screen.getByTestId('campo-importe'), '1500');
  fireEvent.press(screen.getByTestId('campo-categoria'));
  expect(screen.queryByTestId('cat-alim')).toBeNull(); // solo gastos: oculta en ingresos
  fireEvent.press(screen.getByTestId('cat-trabajo'));
  fireEvent.press(screen.getByTestId('cat-nomina'));
  fireEvent.press(screen.getByTestId('presupuestable-false'));
  fireEvent.press(screen.getByTestId(`cuenta-${NOMINA}`));
  expect(screen.queryByTestId('financiacion')).toBeNull();
  await pulsar('abrir-mas-detalles');
  fireEvent.changeText(screen.getByTestId('campo-nota'), '  Nómina octubre ');
  await pulsar('registrar');
  expect(c.registrarIngresoCobrado).toHaveBeenCalledWith({
    intencion_id: '00000000-0000-4000-8000-000000000001', importe: '1500.00', moneda: 'EUR', fecha_hecho: HOY, cuenta_id: NOMINA,
    presupuestable: false, atribucion: 'SIN_INDICAR', categoria: { estado: 'CATEGORIA', categoria_id: 'nomina', magnitudes: [] }, nota: 'Nómina octubre',
  });
  expect(c.registrarGastoPagado).not.toHaveBeenCalled();
  expect(await screen.findByText('Ingreso registrado')).toBeTruthy();
  expect(screen.getByTestId('exito-titulo').props.children).toBe('Nómina octubre');
}, 30000);

// ------------------------------------------------------------------ Gasto con tercero
test('Gasto con tercero: el tercero viaja, la propuesta es la del registro por tipo y el éxito ofrece «Para ALDI / Para Supermercado»', async () => {
  const c = fake({ propuesta: (q) => ({ tipo: q.tipo, campos: { categoria: null, tercero: null, contexto: null, cuenta: { valor: TARJETA, origen: { capa: 'DEFAULT_GENERAL', plantilla_id: null, preferencia_id: null } }, presupuestable: null }, avisos: [] }) });
  await montar(c);
  await abrirTipo('GASTO');
  fireEvent.changeText(screen.getByTestId('campo-importe'), '4');
  escribirNota('Compra');
  await pulsar('campo-tercero');
  await act(async () => fireEvent.press(await screen.findByTestId('tercero-ter-aldi')));
  expect(screen.getByTestId('tercero-valor').props.children).toBe('ALDI');
  await waitFor(() => expect(c.propuestaRegistro).toHaveBeenCalledWith(expect.objectContaining({ tipo: 'GASTO', terceroId: 'ter-aldi' })));
  elegirCategoria('alim', 'super');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  await waitFor(() => expect(screen.getByTestId(`cuenta-${TARJETA}`).props.accessibilityState.checked).toBe(true));
  await pulsar('registrar');
  expect(c.registrarGastoPagado).toHaveBeenCalledWith(expect.objectContaining({ tercero_id: 'ter-aldi', categoria: { estado: 'CATEGORIA', categoria_id: 'super', magnitudes: [] } }));
  expect(await screen.findByText('Gasto registrado')).toBeTruthy();
  expect(screen.getByTestId('pref-ambito-TERCERO')).toBeTruthy();
  expect(screen.getByTestId('pref-ambito-CATEGORIA')).toBeTruthy();
  expect(screen.getByText('Para ALDI')).toBeTruthy();
}, 30000);

// ------------------------------------------------------------------ Cambio de tipo (T02)
test('T02: cambiar de Gasto a Ingreso conserva importe y fecha, quita la categoría de gastos con aviso; tras enviar no hay «Tipo»', async () => {
  const c = fake();
  await montar(c);
  await abrirTipo('GASTO');
  fireEvent.changeText(screen.getByTestId('campo-importe'), '12,50');
  elegirCategoria('alim', 'super');
  await waitFor(() => expect(screen.getByTestId(`cuenta-${TARJETA}`)).toBeTruthy());
  fireEvent.press(screen.getByTestId(`cuenta-${TARJETA}`));
  await pulsar('cambiar-tipo');
  await pulsar('tipo-INGRESO');
  expect(screen.getByText('Nuevo ingreso')).toBeTruthy();
  expect(screen.getByTestId('campo-importe').props.value).toBe('12,50');
  expect(screen.getByTestId('categoria-valor').props.children).toBe('Elige categoría');
  expect(screen.getByTestId('aviso-registro-0').props.children).toBe(
    'Has cambiado de Gasto a Ingreso. Se mantienen el importe y la fecha. Se han quitado la categoría «Supermercado» (no admite ingresos) y la cuenta «Tarjeta BBVA» (no se puede usar para cobrar).',
  );
  elegirCategoria('trabajo', 'nomina');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  await waitFor(() => expect(screen.getByTestId(`cuenta-${NOMINA}`)).toBeTruthy());
  fireEvent.press(screen.getByTestId(`cuenta-${NOMINA}`));
  c.registrarIngresoCobrado = jest.fn(async () => ({ tipo: 'RECHAZADO', codigo: 'FECHA_FUTURA', mensaje: 'x' })) as any;
  await pulsar('registrar');
  expect(screen.getByTestId('error-dominio')).toBeTruthy();
  expect(screen.getByText(`No se ha registrado. ${TEXTO_FECHA_FUTURA}`)).toBeTruthy();
  expect(screen.queryByTestId('cambiar-tipo')).toBeNull(); // tras el primer envío el tipo queda fijado
}, 30000);

test('T02 hacia «Entre cuentas»: cambia de pantalla conservando importe y fecha', async () => {
  await montar(fake());
  await abrirTipo('GASTO');
  fireEvent.changeText(screen.getByTestId('campo-importe'), '30');
  await pulsar('cambiar-tipo');
  await pulsar('tipo-TRANSFERENCIA');
  expect(await screen.findByTestId('transferencia-form')).toBeTruthy();
  expect(screen.getByTestId('campo-importe').props.value).toBe('30');
  expect(within(screen.getByTestId('avisos-registro')).getByText('Has cambiado de Gasto a Entre cuentas. Se mantienen el importe y la fecha.')).toBeTruthy();
}, 30000);

// ------------------------------------------------------------------ «No lo sé»
test('A9: «No lo sé» en una obligatoria desbloquea el registro y la declara en el wire', async () => {
  const c = fake();
  await montar(c);
  await abrirTipo('GASTO');
  fireEvent.changeText(screen.getByTestId('campo-importe'), '60');
  escribirNota('Gasolina');
  elegirCategoria('coche', 'gasolina');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  fireEvent.press(await screen.findByTestId(`cuenta-${TARJETA}`));
  expect(screen.getByTestId('registrar')).toBeDisabled();
  fireEvent.press(screen.getByTestId('no-lo-se-litros'));
  expect(screen.getByTestId('no-lo-se-texto-litros').props.children).toBe('Se registrará sin litros. Podrás añadirlo después.');
  await pulsar('registrar');
  expect(c.registrarGastoPagado).toHaveBeenCalledWith(expect.objectContaining({ categoria: { estado: 'CATEGORIA', categoria_id: 'gasolina', magnitudes: [], desconocidas: ['litros'] } }));
}, 30000);

// ------------------------------------------------------------------ Plantilla
test('Plantilla desde un acceso: chip, origen «De tu plantilla …» por campo y «Quitar» retira lo que puso', async () => {
  const sem = plt({ id: 'p1', nombre: 'Súper semanal', categoria_id: 'super', cuenta_default_id: TARJETA });
  const origen = { capa: 'PLANTILLA', plantilla_id: 'p1', preferencia_id: null };
  const c = fake({
    plantillas: [sem],
    acciones: [{ id: 'a1', nombre: 'Súper', plantilla_registro_id: 'p1', orden: 0, icono_key: null, enabled: true, row_version: 1 }],
    propuesta: (q) => ({
      tipo: q.tipo,
      campos: q.plantillaId
        ? { categoria: { valor: 'super', origen }, tercero: { valor: 'ter-aldi', origen }, contexto: null, cuenta: { valor: TARJETA, origen }, presupuestable: null }
        : { categoria: null, tercero: null, contexto: null, cuenta: null, presupuestable: null },
      avisos: [],
    }),
  });
  await montar(c);
  await pulsar('acceso-a1');
  expect(await screen.findByTestId('chip-plantilla')).toBeTruthy();
  await waitFor(() => expect(screen.getByTestId('categoria-valor').props.children).toBe('Supermercado'));
  expect(screen.getByTestId('origen-categoria').props.children).toBe('De tu plantilla Súper semanal.');
  expect(screen.getByTestId('tercero-valor').props.children).toBe('ALDI');
  expect(screen.getByTestId('origen-cuenta').props.children).toBe('De tu plantilla Súper semanal.');
  expect(c.propuestaRegistro).toHaveBeenCalledWith(expect.objectContaining({ plantillaId: 'p1', tipo: 'GASTO' }));
  await pulsar('quitar-plantilla');
  expect(screen.queryByTestId('chip-plantilla')).toBeNull();
  expect(screen.getByTestId('categoria-valor').props.children).toBe('Elige categoría');
  expect(screen.getByTestId('tercero-valor').props.children).toBe('Elige tercero');
}, 30000);

test('Plantilla (dominio): los campos tocados por el usuario nunca se pisan; «Quitar» conserva lo elegido', () => {
  const b0 = { ...borradorInicial(HOY), terceroId: 'ter-mio', terceroNombre: 'Mío', terceroOrigen: 'USUARIO' as const, categoria: { estado: 'SIN_CATEGORIA' as const } };
  const origen = { capa: 'PLANTILLA' };
  const r = aplicarCamposPlantilla(b0, { id: 'p1', nombre: 'X' }, { categoria: { valor: 'super', origen }, tercero: { valor: 'ter-aldi', origen }, contexto: null },
    { arbol: null, tipo: 'GASTO', tercero: () => 'ALDI', contexto: () => null });
  expect(r.b.terceroId).toBe('ter-mio');
  expect(r.b.categoria).toEqual({ estado: 'SIN_CATEGORIA' });
  expect(quitarPlantilla(r.b).terceroId).toBe('ter-mio');
});

// ------------------------------------------------------------------ Entre cuentas
test('X01: misma cuenta bloquea con aviso; INDETERMINADO reintenta con la MISMA identidad; éxito «Movimiento registrado»', async () => {
  let llamadas = 0;
  const c = fake({
    transferencia: async (p) => {
      llamadas += 1;
      if (llamadas === 1) return { tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.' };
      return { tipo: 'OK', datos: { intencion_id: p.intencion_id, hecho_id: 'h2', idempotente: true, tipo: 'TRANSFERENCIA', importe: p.importe, moneda: 'EUR', estado_atribucion: null, estado_categorial: null } };
    },
  });
  await montar(c);
  await abrirTipo('TRANSFERENCIA');
  await waitFor(() => expect(screen.getByTestId(`desde-${NOMINA}`)).toBeTruthy());
  fireEvent.press(screen.getByTestId(`desde-${NOMINA}`));
  fireEvent.press(screen.getByTestId(`a-${NOMINA}`));
  expect(screen.getByTestId('a-misma').props.children).toBe(TEXTO_MISMA_CUENTA);
  fireEvent.changeText(screen.getByTestId('campo-importe'), '200');
  expect(screen.getByTestId('registrar')).toBeDisabled();
  fireEvent.press(screen.getByTestId(`a-${AHORRO}`));
  await pulsar('registrar');
  expect(screen.getByTestId('estado-indeterminado')).toBeTruthy();
  await pulsar('reintentar');
  const ids = (c.registrarTransferencia as jest.Mock).mock.calls.map((x) => x[0].intencion_id);
  expect(ids).toEqual(['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000001']);
  expect((c.registrarTransferencia as jest.Mock).mock.calls[0][0]).toEqual({
    intencion_id: '00000000-0000-4000-8000-000000000001', importe: '200.00', moneda: 'EUR', fecha_hecho: HOY, cuenta_origen_id: NOMINA, cuenta_destino_id: AHORRO,
  });
  expect(await screen.findByText('Movimiento registrado')).toBeTruthy();
}, 30000);

// ------------------------------------------------------------------ Guardar como plantilla
test('R06: «Guardar como plantilla…» exige nombre (nunca autocompletado) y guarda lo marcado con el tipo', async () => {
  const c = fake();
  c.altaPlantilla = jest.fn(async (x: any) => ({ tipo: 'OK', datos: { plantilla: { ...x, enabled: true, row_version: 1 }, idempotente: false, modificadas: [x.id] } })) as any;
  await montar(c);
  await abrirTipo('GASTO');
  fireEvent.changeText(screen.getByTestId('campo-importe'), '4');
  escribirNota('Compra');
  elegirCategoria('alim', 'super');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  fireEvent.press(await screen.findByTestId(`cuenta-${TARJETA}`));
  await pulsar('registrar');
  await pulsar('guardar-como-plantilla');
  expect(screen.getByTestId('plantilla-nombre').props.value).toBe('');
  expect(screen.getByTestId('plantilla-falta').props.children).toBe('Falta: nombre');
  fireEvent.press(screen.getByTestId('plantilla-casilla-presupuestable'));
  fireEvent.changeText(screen.getByTestId('plantilla-nombre'), 'Súper');
  await waitFor(() => expect(screen.getByTestId('plantilla-guardar')).not.toBeDisabled());
  await pulsar('plantilla-guardar');
  expect(c.altaPlantilla).toHaveBeenCalledWith({
    id: expect.any(String), nombre: 'Súper', tipo_hecho_id: TIPOS.GASTO, tercero_id: null, categoria_id: 'super', entidad_id: null,
    cuenta_default_id: TARJETA, presupuestable_default: null,
  });
  expect(screen.getByTestId('plantilla-aviso-ok')).toBeTruthy();
}, 30000);

// ------------------------------------------------------------------ Corte de Concepto (§2.7; CNC-18/CNC-20)
test('CNC-18/20: gasto sin nota no envía concepto y el éxito muestra el título calculado (nunca vacío ni «null»)', async () => {
  const c = fake();
  await montar(c);
  await abrirTipo('GASTO');
  expect(screen.queryByTestId('campo-concepto')).toBeNull(); // ya no hay «Concepto» obligatorio
  fireEvent.changeText(screen.getByTestId('campo-importe'), '4');
  elegirCategoria('alim', 'super');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  fireEvent.press(await screen.findByTestId(`cuenta-${TARJETA}`));
  expect(screen.queryByTestId('faltan')).toBeNull();
  await pulsar('abrir-mas-detalles');
  fireEvent.changeText(screen.getByTestId('campo-nota'), '   '); // solo espacios = ausencia
  await pulsar('registrar');
  const enviado = (c.registrarGastoPagado as jest.Mock).mock.calls[0][0];
  expect('concepto' in enviado).toBe(false);
  expect(await screen.findByText('Gasto registrado')).toBeTruthy();
  expect(screen.getByTestId('exito-titulo').props.children).toBe('Supermercado');
}, 30000);

test('CNC-20: sin nota, tercero ni categoría el título es «Gasto · importe»', async () => {
  const c = fake();
  await montar(c);
  await abrirTipo('GASTO');
  fireEvent.changeText(screen.getByTestId('campo-importe'), '23,5');
  fireEvent.press(screen.getByTestId('campo-categoria'));
  fireEvent.press(screen.getByTestId('selector-sin-categoria'));
  fireEvent.press(screen.getByTestId('presupuestable-false'));
  fireEvent.press(await screen.findByTestId(`cuenta-${TARJETA}`));
  await pulsar('registrar');
  expect(await screen.findByText('Gasto registrado')).toBeTruthy();
  expect(screen.getByTestId('exito-titulo').props.children).toBe('Gasto · 23,50 €');
}, 30000);

// ------------------------------------------------------------------ casos de cierre (§45.7-6, §46.7-11)
test('§45.7-6: plantilla cuya categoría exige magnitud obligatoria → se pide el dato (o «No lo sé») antes de registrar', async () => {
  const origen = { capa: 'PLANTILLA', plantilla_id: 'p2', preferencia_id: null };
  const c = fake({
    plantillas: [plt({ id: 'p2', nombre: 'Gasolinera', categoria_id: 'gasolina' })],
    acciones: [{ id: 'a2', nombre: 'Gasolina', plantilla_registro_id: 'p2', orden: 0, icono_key: null, enabled: true, row_version: 1 }],
    propuesta: (q) => ({ tipo: q.tipo, campos: { categoria: q.plantillaId ? { valor: 'gasolina', origen } : null, tercero: null, contexto: null, cuenta: q.plantillaId ? { valor: TARJETA, origen } : null, presupuestable: q.plantillaId ? { valor: true, origen } : null }, avisos: [] }),
  });
  await montar(c);
  await pulsar('acceso-a2');
  await waitFor(() => expect(screen.getByTestId('categoria-valor').props.children).toBe('Gasolina'));
  fireEvent.changeText(screen.getByTestId('campo-importe'), '50');
  await waitFor(() => expect(screen.getByTestId(`cuenta-${TARJETA}`).props.accessibilityState.checked).toBe(true));
  expect(screen.getByTestId('magnitud-litros')).toBeTruthy();
  expect(screen.getByTestId('registrar')).toBeDisabled();
  fireEvent.changeText(screen.getByTestId('magnitud-litros'), '35,5');
  await pulsar('registrar');
  expect(c.registrarGastoPagado).toHaveBeenCalledWith(expect.objectContaining({ categoria: { estado: 'CATEGORIA', categoria_id: 'gasolina', magnitudes: [{ magnitud_id: 'litros', valor: '35.5' }] } }));
}, 30000);

test('§46.7-11: alta de tercero con duplicado ACTIVO → «Usar el existente» (sin crear otro)', async () => {
  const c = fake();
  c.candidatosTercero = jest.fn(async () => ({ tipo: 'OK', datos: { terceros: [{ id: 'ter-aldi', nombre: 'ALDI', naturaleza: 'EMPRESA', enabled: true, row_version: 1 }] } })) as any;
  await montar(c);
  await abrirTipo('GASTO');
  await pulsar('campo-tercero');
  fireEvent.changeText(await screen.findByTestId('tercero-filtro'), 'aldi');
  await pulsar('tercero-crear');
  expect(await screen.findByTestId('tercero-duplicado-aviso')).toBeTruthy();
  await pulsar('tercero-usar-existente');
  expect(screen.getByTestId('tercero-valor').props.children).toBe('ALDI');
  expect(c.altaTercero).not.toHaveBeenCalled();
}, 30000);
