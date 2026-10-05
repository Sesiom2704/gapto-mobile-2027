// ============================================================
// GAPTO MOBILE 2027
// Fichero: regcat.test.tsx
// Ruta: mobile/__tests__/regcat.test.tsx
// Descripción: REG-CAT (F09 §12.97.1–12.97.3; F05 §22.2 C01/C07, §28.2; lámina REG-CAT v1.0): campo «Categoría» tras «Concepto», sin preselección y bloqueante mientras esté Pendiente; selector jerárquico (raíz con «Sin categoría», «Usar…» solo en nodo elegible, hoja elegible se elige al tocar, motivo en texto en nodo no seleccionable navegable, migas, estado vacío, error de carga que NUNCA selecciona «Sin categoría»); magnitudes (obligatoria sin valor por defecto que bloquea y se nombra, opcional, valor canónico con punto en el sellado, nunca `unidad`); confirmación antes de descartar valores al cambiar de categoría o elegir «Sin categoría»; `presupuestable_default` no rellena el registro; recuperación tras rechazo definitivo de categoría (intención sellada no reenviada, árbol recargado, categoría marcada, decisiones conservadas, identidad nueva).
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S6-WIRE+UI, correctivo AJ-S6WIREUI-09): el selector no promete subcategorías seleccionables cuando ningún descendiente es elegible (padre no seleccionable cuyo único hijo visible no es capturable, tipo Gas); caso positivo con hijo elegible; casos de `tieneDescendienteElegible`.
// Versión: 0.3.0 (F05-01 P7 · N3, Moisés D-P7-05, AJ-P7BAT-12): los tests AJ-09 afirman el literal exacto del aviso de nivel en las cuatro combinaciones {Desactivada, Solo ingresos} × {usables false, true} (las de «Desactivada» con fixture de cliente, PR-01) y del subtítulo de fila en las dos; el de «Solo ingresos» sin descendiente elegible es el discriminante de U17.
// ============================================================

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, CuentaPago, Respuesta, ResultadoRegistro } from '../src/api/cliente';
import { construirArbol, tieneDescendienteElegible, type CategoriaNodo } from '../src/domain/categoria';
import type { PayloadGastoPagado } from '../src/domain/intencion';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, LISTA, mag, nodo } from './fixtures_categorias';

const CUENTA = 'c0000000-0000-4000-8000-000000000001';
const AHORA = () => new Date(2026, 8, 24, 10, 0, 0);

function ok(p: PayloadGastoPagado): Respuesta<ResultadoRegistro> {
  return { tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: 'COMPLETA', aportacion_criterio: null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado } };
}

function fake(o: { arboles?: Respuesta<{ categorias: CategoriaNodo[] }>[]; registrar?: (p: PayloadGastoPagado) => Promise<Respuesta<ResultadoRegistro>> } = {}) {
  const enviados: PayloadGastoPagado[] = [];
  const cola = [...(o.arboles ?? [{ tipo: 'OK', datos: { categorias: LISTA } } as Respuesta<{ categorias: CategoriaNodo[] }>])];
  const stub = clienteCategoriasStub(LISTA);
  const cliente: ClienteApi = {
    ...stub,
    arbolCategorias: jest.fn(async () => (cola.length > 1 ? cola.shift()! : cola[0])),
    registrarGastoPagado: jest.fn(async (p) => {
      enviados.push(p);
      return (o.registrar ?? (async (x) => ok(x)))(p);
    }),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK', datos: { cuentas: [{ cuenta_id: CUENTA, nombre: 'Cuenta (sintética)', moneda: 'EUR', propuesta_financiacion: 'SELF_100' }] } }) as Respuesta<{ cuentas: CuentaPago[] }>),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
  };
  return { cliente, enviados };
}

let n = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;

async function abrir(cliente: ClienteApi) {
  render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  fireEvent.press(await screen.findByTestId('accion-gasto'));
  await screen.findByTestId('financiacion');
}

function basicos() {
  fireEvent.changeText(screen.getByTestId('campo-importe'), '23,40');
  fireEvent.changeText(screen.getByTestId('campo-concepto'), 'Factura');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
}

const abrirSelector = () => fireEvent.press(screen.getByTestId('campo-categoria'));
const texto = (id: string) => screen.getByTestId(id).props.children;

beforeEach(() => {
  n = 0;
});

test('campo Pendiente sin preselección: bloquea, se nombra en faltan y no se envía nada', async () => {
  const f = fake();
  await abrir(f.cliente);
  basicos();
  expect(texto('categoria-valor')).toBe('Elige categoría');
  expect(screen.getByTestId('registrar')).toBeDisabled();
  expect(texto('faltan')).toBe('Para registrar falta: categoría.');
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  expect(f.enviados).toHaveLength(0);
});

test('selector: raíz con «Sin categoría», nodos visibles en el registro y motivo en texto', async () => {
  const f = fake();
  await abrir(f.cliente);
  abrirSelector();
  expect(screen.getByTestId('selector-sin-categoria')).toBeTruthy();
  expect(screen.getByTestId('cat-hogar')).toBeTruthy();
  expect(screen.getByTestId('cat-trabajo')).toBeTruthy(); // INGRESO con hijo GASTO: navegable
  expect(screen.getByText(/Solo ingresos · tiene subcategorías que sí puedes usar/)).toBeTruthy();
  expect(screen.getByTestId('cat-ocio')).toBeTruthy(); // padre desactivado con hijo activo (fixture)
  expect(screen.getByText(/Desactivada · tiene subcategorías que sí puedes usar/)).toBeTruthy();
  expect(screen.queryByTestId('cat-viejo')).toBeNull(); // hoja desactivada: oculta en el registro
});

test('«Usar…» solo en nodo elegible; nodo no elegible navegable sin «Usar…» y con motivo', async () => {
  const f = fake();
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  expect(screen.getByTestId('selector-usar')).toBeTruthy();
  expect(screen.getByText('Usar «Hogar»')).toBeTruthy();
  // No capturable (magnitud obligatoria no disponible): visible, no seleccionable y con motivo (F09 §12.97.3, R05).
  expect(screen.getByTestId('cat-gas').props.accessibilityState.disabled).toBe(true);
  expect(screen.getByText('Requiere un dato no disponible')).toBeTruthy();
  fireEvent.press(screen.getByTestId('cat-gas'));
  expect(screen.getByTestId('selector-categorias')).toBeTruthy(); // no se elige
  fireEvent.press(screen.getByTestId('selector-miga-todas'));
  fireEvent.press(screen.getByTestId('cat-trabajo'));
  expect(screen.queryByTestId('selector-usar')).toBeNull();
  expect(screen.getByTestId('selector-aviso-nivel')).toBeTruthy();
  expect(screen.queryByTestId('cat-nomina')).toBeNull();
  // Hoja elegible: se selecciona al tocarla y vuelve al formulario con la ruta.
  fireEvent.press(screen.getByTestId('cat-prof'));
  expect(screen.queryByTestId('selector-categorias')).toBeNull();
  expect(texto('categoria-valor')).toBe('Gastos profesionales');
  expect(texto('categoria-ruta')).toBe('Trabajo');
});

// AJ-S6WIREUI-09: padres no seleccionables cuyo único hijo visible no es capturable (tipo Gas).
const GAS_SOLO = (id: string, padre: string) =>
  nodo({ id, nombre: `Gas ${padre}`, parent_id: padre, capturable: false, motivo_no_capturable: 'MAGNITUD_OBLIGATORIA_NO_DISPONIBLE', magnitudes: [mag({ magnitud_id: `m-${id}`, nombre: 'Consumo de gas', enabled: false })] });
const LISTA_SIN_USABLES: CategoriaNodo[] = [
  nodo({ id: 'sum', nombre: 'Suministros', ambito: 'INGRESO' }),
  GAS_SOLO('gas1', 'sum'),
  nodo({ id: 'casa', nombre: 'Casa vieja', enabled: false, orden: 1 }),
  GAS_SOLO('gas2', 'casa'),
];

// Literales congelados por Moisés D-P7-05 (N3): idénticos carácter a carácter en el componente y en U17.
const NEGATIVO = 'Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría.';
const avisoNivel = (): string => {
  const textos = screen.getByTestId('selector-aviso-nivel').findAllByType(Text).filter((t: { props: { children: unknown } }) => typeof t.props.children === 'string' && t.props.children.includes('se puede elegir'));
  expect(textos).toHaveLength(1);
  return textos[0].props.children;
};

test('AJ-09 N3: subtítulo de fila con y sin descendiente elegible (literal exacto)', async () => {
  const sin = fake({ arboles: [{ tipo: 'OK', datos: { categorias: LISTA_SIN_USABLES } }] });
  await abrir(sin.cliente);
  abrirSelector();
  expect(screen.getByText('Solo ingresos · sus subcategorías tampoco se pueden usar')).toBeTruthy();
  expect(screen.getByText('Desactivada · sus subcategorías tampoco se pueden usar')).toBeTruthy();
  expect(screen.queryByText(/sí puedes usar/)).toBeNull();
  screen.unmount();
  const con = fake();
  await abrir(con.cliente);
  abrirSelector();
  expect(screen.getByText('Solo ingresos · tiene subcategorías que sí puedes usar')).toBeTruthy();
  expect(screen.getByText('Desactivada · tiene subcategorías que sí puedes usar')).toBeTruthy();
  expect(screen.queryByText(/tampoco se pueden usar/)).toBeNull();
});

test('AJ-09 N3: aviso de nivel sin descendiente elegible, motivo «Solo ingresos» (literal exacto)', async () => {
  const f = fake({ arboles: [{ tipo: 'OK', datos: { categorias: LISTA_SIN_USABLES } }] });
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-sum'));
  expect(avisoNivel()).toBe(`Suministros no se puede elegir (solo ingresos). ${NEGATIVO}`);
});

test('AJ-09 N3: aviso de nivel sin descendiente elegible, motivo «Desactivada» (literal exacto; fixture de cliente, PR-01)', async () => {
  const f = fake({ arboles: [{ tipo: 'OK', datos: { categorias: LISTA_SIN_USABLES } }] });
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-casa'));
  expect(avisoNivel()).toBe(`Casa vieja está desactivada y no se puede elegir. ${NEGATIVO}`);
});

test('AJ-09 N3: aviso de nivel con descendiente elegible, motivo «Solo ingresos» (literal exacto)', async () => {
  const f = fake();
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-trabajo'));
  expect(avisoNivel()).toBe('Trabajo no se puede elegir (solo ingresos). Sus subcategorías sí.');
});

test('AJ-09 N3: aviso de nivel con descendiente elegible, motivo «Desactivada» (literal exacto; fixture de cliente, PR-01)', async () => {
  const f = fake();
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-ocio'));
  expect(avisoNivel()).toBe('Ocio está desactivada y no se puede elegir. Sus subcategorías activas sí.');
});

test('AJ-09: tieneDescendienteElegible recorre el subárbol (hoja o intermedio) con la naturaleza dada', () => {
  const sin = construirArbol(LISTA_SIN_USABLES);
  expect(tieneDescendienteElegible(sin, sin.porId.get('sum')!)).toBe(false);
  expect(tieneDescendienteElegible(sin, sin.porId.get('casa')!)).toBe(false);
  const con = construirArbol(LISTA);
  expect(tieneDescendienteElegible(con, con.porId.get('trabajo')!)).toBe(true);
  expect(tieneDescendienteElegible(con, con.porId.get('ocio')!)).toBe(true);
  expect(tieneDescendienteElegible(con, con.porId.get('trabajo')!, 'INGRESO')).toBe(true); // Nómina
  expect(tieneDescendienteElegible(con, con.porId.get('hogar')!, 'INGRESO')).toBe(false);
  // Nieto elegible bajo un intermedio no elegible.
  const nieto = construirArbol([
    nodo({ id: 'a', nombre: 'A', ambito: 'INGRESO' }),
    nodo({ id: 'b', nombre: 'B', ambito: 'INGRESO', parent_id: 'a' }),
    nodo({ id: 'c', nombre: 'C', parent_id: 'b' }),
  ]);
  expect(tieneDescendienteElegible(nieto, nieto.porId.get('a')!)).toBe(true);
});

test('selección vigente con check Y texto («Elegida»)', async () => {
  const f = fake();
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('selector-usar'));
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  expect(screen.getByText('Elegida')).toBeTruthy();
  expect(screen.getByTestId('selector-usar').props.accessibilityState.selected).toBe(true);
});

test('estado vacío: «Aún no tienes categorías» con «Sin categoría» disponible', async () => {
  const f = fake({ arboles: [{ tipo: 'OK', datos: { categorias: [] } }] });
  await abrir(f.cliente);
  abrirSelector();
  expect(screen.getByTestId('selector-vacio')).toBeTruthy();
  expect(screen.getByText('Aún no tienes categorías')).toBeTruthy();
  fireEvent.press(screen.getByTestId('selector-sin-categoria'));
  expect(texto('categoria-valor')).toBe('Sin categoría');
});

test('error de carga: Reintentar separado de «Continuar sin categoría»; el fallo nunca selecciona nada', async () => {
  const f = fake({ arboles: [{ tipo: 'INDETERMINADO', mensaje: 'x' }, { tipo: 'OK', datos: { categorias: LISTA } }] });
  await abrir(f.cliente);
  abrirSelector();
  expect(await screen.findByTestId('selector-error')).toBeTruthy();
  expect(screen.getByText('No hemos podido cargar tus categorías.')).toBeTruthy();
  fireEvent.press(screen.getByTestId('selector-cerrar'));
  expect(texto('categoria-valor')).toBe('Elige categoría'); // AJ-09: sin selección automática
  abrirSelector();
  await act(async () => fireEvent.press(screen.getByTestId('selector-reintentar')));
  expect(await screen.findByTestId('cat-hogar')).toBeTruthy();
  expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2);
  expect(f.enviados).toHaveLength(0); // reintentar la carga no crea intención
  expect(texto('categoria-valor')).toBe('Elige categoría');
});

test('«Continuar sin categoría» tras el error es una decisión deliberada', async () => {
  const f = fake({ arboles: [{ tipo: 'INDETERMINADO', mensaje: 'x' }] });
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(await screen.findByTestId('selector-continuar-sin'));
  expect(texto('categoria-valor')).toBe('Sin categoría');
});

test('magnitud obligatoria sin valor por defecto: bloquea y se nombra; al informarla se sella canónica y sin unidad', async () => {
  const f = fake();
  await abrir(f.cliente);
  basicos();
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('cat-luz'));
  expect(texto('categoria-ruta')).toBe('Hogar');
  expect(screen.getByTestId('datos-categoria')).toBeTruthy();
  expect(screen.getByTestId('magnitud-kwh').props.value).toBe(''); // nunca «0»
  expect(screen.getByTestId('microcopy-obligatoria')).toBeTruthy();
  expect(screen.getByTestId('registrar')).toBeDisabled();
  expect(texto('faltan')).toBe('Para registrar falta: consumo eléctrico (kWh).');
  fireEvent.changeText(screen.getByTestId('magnitud-kwh'), '12,5');
  expect(screen.getByTestId('registrar')).toBeEnabled();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[0].categoria).toEqual({ estado: 'CATEGORIA', categoria_id: 'luz', magnitudes: [{ magnitud_id: 'kwh', valor: '12.5' }] });
  expect(JSON.stringify(f.enviados[0])).not.toContain('unidad');
});

test('magnitud opcional marcada «(opcional)»: vacía no bloquea ni viaja', async () => {
  const f = fake();
  await abrir(f.cliente);
  basicos();
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('cat-agua'));
  expect(screen.getByText(/\(opcional\)/)).toBeTruthy();
  expect(screen.getByTestId('registrar')).toBeEnabled();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[0].categoria).toEqual({ estado: 'CATEGORIA', categoria_id: 'agua', magnitudes: [] });
});

test('valor con más decimales de los admitidos: error visible al escribir y bloqueo', async () => {
  const f = fake();
  await abrir(f.cliente);
  basicos();
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('cat-luz'));
  fireEvent.changeText(screen.getByTestId('magnitud-kwh'), '1,234');
  expect(screen.getByText('Máximo 2 decimales.')).toBeTruthy();
  expect(screen.getByTestId('registrar')).toBeDisabled();
  expect(texto('faltan')).toBe('Para registrar falta: consumo eléctrico válido (kWh).');
});

test('cambio de categoría sin valores: sin confirmación; con valores: confirmación que los lista', async () => {
  const f = fake();
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('cat-agua'));
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('cat-luz'));
  expect(screen.queryByTestId('confirmar-descarte')).toBeNull();
  expect(texto('categoria-valor')).toBe('Luz');
  fireEvent.changeText(screen.getByTestId('magnitud-kwh'), '245');
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('cat-agua'));
  expect(screen.getByTestId('confirmar-descarte')).toBeTruthy();
  expect(screen.getByTestId('descarte-kwh')).toBeTruthy();
  expect(screen.getByText('245 kWh')).toBeTruthy();
  fireEvent.press(screen.getByTestId('descarte-mantener'));
  expect(texto('categoria-valor')).toBe('Luz');
  expect(screen.getByTestId('magnitud-kwh').props.value).toBe('245');
  // «Sin categoría» descarta todas con la misma confirmación.
  abrirSelector();
  fireEvent.press(screen.getByTestId('selector-sin-categoria'));
  expect(screen.getByTestId('confirmar-descarte')).toBeTruthy();
  fireEvent.press(screen.getByTestId('descarte-confirmar'));
  expect(texto('categoria-valor')).toBe('Sin categoría');
  expect(screen.queryByTestId('datos-categoria')).toBeNull();
});

test('cambio entre categorías con una magnitud común: se conserva sin confirmación', async () => {
  const comun = [
    nodo({ id: 'a', nombre: 'A', magnitudes: [mag({ magnitud_id: 'm', nombre: 'Litros', unidad_default: 'l' })] }),
    nodo({ id: 'b', nombre: 'B', orden: 1, magnitudes: [mag({ magnitud_id: 'm', nombre: 'Litros', unidad_default: 'l' })] }),
  ];
  const f = fake({ arboles: [{ tipo: 'OK', datos: { categorias: comun } }] });
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-a'));
  fireEvent.changeText(screen.getByTestId('magnitud-m'), '40');
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-b'));
  expect(screen.queryByTestId('confirmar-descarte')).toBeNull();
  expect(screen.getByTestId('magnitud-m').props.value).toBe('40');
});

test('presupuestable_default de la categoría no rellena «¿Cuenta para el presupuesto?»', async () => {
  const f = fake();
  await abrir(f.cliente);
  abrirSelector();
  fireEvent.press(screen.getByTestId('cat-hogar'));
  fireEvent.press(screen.getByTestId('selector-usar')); // Hogar: presupuestable_default = true
  expect(screen.getByTestId('presupuestable-true').props.accessibilityState.selected).toBe(false);
  expect(screen.getByTestId('presupuestable-false').props.accessibilityState.selected).toBe(false);
});

test.each(['CATEGORIA_NO_ELEGIBLE', 'MAGNITUD_VALOR_NO_VALIDO'])(
  'rechazo %s tras confirmar: no se reenvía, árbol recargado, categoría marcada, decisiones conservadas e identidad nueva',
  async (codigo) => {
    let k = 0;
    const f = fake({
      registrar: async (p) => (++k === 1 ? { tipo: 'RECHAZADO', codigo, mensaje: 'x' } : ok(p)),
    });
    await abrir(f.cliente);
    basicos();
    abrirSelector();
    fireEvent.press(screen.getByTestId('cat-hogar'));
    fireEvent.press(screen.getByTestId('cat-luz'));
    fireEvent.changeText(screen.getByTestId('magnitud-kwh'), '12,5');
    await act(async () => fireEvent.press(screen.getByTestId('registrar')));
    expect(await screen.findByTestId('categoria-invalida')).toBeTruthy();
    expect(texto('categoria-valor')).toBe('Elige otra categoría');
    expect(screen.getByTestId('error-dominio')).toBeTruthy();
    await waitFor(() => expect(f.cliente.arbolCategorias).toHaveBeenCalledTimes(2));
    expect(f.enviados).toHaveLength(1); // la intención sellada no se reenvía
    expect(screen.getByTestId('registrar')).toBeDisabled();
    // Las demás decisiones se conservan.
    expect(screen.getByTestId('campo-importe').props.value).toBe('23,40');
    expect(screen.getByTestId('presupuestable-true').props.accessibilityState.selected).toBe(true);
    abrirSelector();
    fireEvent.press(screen.getByTestId('selector-sin-categoria'));
    await act(async () => fireEvent.press(screen.getByTestId('registrar')));
    await screen.findByTestId('registro-exito');
    expect(f.enviados[1].intencion_id).not.toBe(f.enviados[0].intencion_id);
    expect(f.enviados[1].categoria).toEqual({ estado: 'SIN_CATEGORIA' });
  },
);
