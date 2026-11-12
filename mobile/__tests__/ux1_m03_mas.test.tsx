// ============================================================
// GAPTO MOBILE 2027
// Fichero: ux1_m03_mas.test.tsx
// Ruta: mobile/__tests__/ux1_m03_mas.test.tsx
// Descripción: M-03 con Q-UX-06 (T1-F06 UX-1). En la app (Raiz): «Más» estando en «Más» vuelve al menú sin preguntar
//   si no hay cambios; cambiar de pestaña y volver conserva la pila. Decisión pura de la barra (`accionBarra`) y
//   oráculo O-M03-01 «con cambios, pulsar Más no navega sin confirmar». Con un formulario que publica la señal
//   (`usarCambiosSinGuardar`), compuesto como en App.tsx: sin cambios vuelve al menú; con cambios pregunta
//   «¿Descartar cambios?»; «Seguir editando» conserva lo escrito; «Descartar» vuelve al menú.
// Versión: 0.1.0 (F06 T1 UX-1 · M-03)
// Versión: 0.2.0 (F06 T1 UX-1 · DUD-UX1-01, decisión de Moisés del lote 26): salir de un formulario de la pila de «Más» por «Cancelar» con cambios pregunta «¿Descartar cambios?»; «Seguir editando» conserva lo escrito y «Descartar» sale; sin cambios sale sin preguntar (alta de categoría en la app y formulario de prueba).
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React, { useState } from 'react';
import { Text, TextInput, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, Respuesta } from '../src/api/cliente';
import type { CategoriaNodo } from '../src/domain/categoria';
import { BarraInferior, type Destino } from '../src/components/BarraInferior';
import { accionBarra, HojaDescartarCambios, usarCambiosSinGuardar } from '../src/components/CambiosSinGuardar';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, nodo } from './fixtures_categorias';

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const LISTA: CategoriaNodo[] = [nodo({ id: 'hogar', nombre: 'Hogar' })];

function cliente(): ClienteApi {
  return {
    ...clienteCategoriasStub(LISTA),
    arbolCategorias: jest.fn(async () => ({ tipo: 'OK', datos: { categorias: LISTA } }) as Respuesta<{ categorias: CategoriaNodo[] }>),
    registrarGastoPagado: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
    cuentasPago: jest.fn(async () => ({ tipo: 'OK' as const, datos: { cuentas: [] } })),
    gastoMes: jest.fn(async () => ({ tipo: 'INDETERMINADO' as const, mensaje: '' })),
  } as ClienteApi;
}

async function montarApp() {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente()} nuevoId={() => 'c0000000-0000-4000-8000-000000000001'} ahora={() => new Date(2026, 10, 12, 10)} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  for (let i = 0; i < 3; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));

// ------------------------------------------------------------------ decisión pura de la barra
test('accionBarra: otra pestaña o «Más» desde otra → ir; «Más» en «Más» → menú sin cambios, PREGUNTAR con cambios (O-M03-01)', () => {
  expect(accionBarra('INICIO', 'MAS', false, true)).toEqual({ tipo: 'IR', destino: 'INICIO' });
  expect(accionBarra('MAS', 'INICIO', false, true)).toEqual({ tipo: 'IR', destino: 'MAS' }); // volver a la pestaña conserva la pila
  expect(accionBarra('MAS', 'MAS', true, true)).toEqual({ tipo: 'IR', destino: 'MAS' }); // ya en el menú: nada que hacer
  expect(accionBarra('MAS', 'MAS', false, false)).toEqual({ tipo: 'MENU_MAS' });
  expect(accionBarra('MAS', 'MAS', false, true)).toEqual({ tipo: 'PREGUNTAR' }); // O-M03-01: con cambios NO navega sin confirmar
});

// ------------------------------------------------------------------ en la app
test('App: Más › Ajustes › Categorías y «Más» en la barra vuelve al menú «Más» sin preguntar (sin cambios)', async () => {
  await montarApp();
  await pulsar('tab-MAS');
  await pulsar('mas-ajustes');
  await pulsar('ajustes-categorias');
  expect(await screen.findByTestId('fila-hogar')).toBeTruthy();
  await pulsar('tab-MAS');
  expect(screen.getByTestId('mas-ajustes')).toBeTruthy(); // menú «Más»
  expect(screen.queryByTestId('fila-hogar')).toBeNull();
  expect(screen.queryByTestId('descartar-cambios')).toBeNull();
});

test('App: cambiar a otra pestaña y volver conserva la pila de «Más» (como hoy)', async () => {
  await montarApp();
  await pulsar('tab-MAS');
  await pulsar('mas-ajustes');
  await pulsar('ajustes-categorias');
  expect(await screen.findByTestId('fila-hogar')).toBeTruthy();
  await pulsar('tab-INICIO');
  await pulsar('tab-MAS');
  expect(screen.getByTestId('fila-hogar')).toBeTruthy(); // sigue en Categorías
});

// ------------------------------------------------------------------ formulario que publica la señal, compuesto como en App.tsx
function FormularioDePrueba(p: { onCambios: (hay: boolean) => void }) {
  const [nombre, setNombre] = useState('Mercadona');
  usarCambiosSinGuardar(true, { nombre }, p.onCambios);
  return <TextInput testID="form-nombre" value={nombre} onChangeText={setNombre} />;
}
function PilaDePrueba() {
  const [destino, setDestino] = useState<Destino>('MAS');
  const [pantalla, setPantalla] = useState<'MAS' | 'FORM'>('FORM');
  const [cambios, setCambios] = useState(false);
  const [preguntar, setPreguntar] = useState(false);
  const pulsarBarra = (d: Destino) => {
    const a = accionBarra(d, destino, pantalla === 'MAS', cambios);
    if (a.tipo === 'IR') return setDestino(a.destino);
    if (a.tipo === 'MENU_MAS') return setPantalla('MAS');
    setPreguntar(true);
  };
  return (
    <View style={{ flex: 1 }}>
      {pantalla === 'MAS' ? <Text testID="menu-mas">Más</Text> : <FormularioDePrueba onCambios={setCambios} />}
      {preguntar ? (
        <HojaDescartarCambios
          onDescartar={() => { setPreguntar(false); setCambios(false); setPantalla('MAS'); }}
          onSeguir={() => setPreguntar(false)}
        />
      ) : null}
      <BarraInferior actual={destino} onCambiar={pulsarBarra} />
    </View>
  );
}
function montarPila() {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PilaDePrueba />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

test('Más → Más sin cambios: vuelve al menú sin preguntar', async () => {
  montarPila();
  await pulsar('tab-MAS');
  expect(screen.getByTestId('menu-mas')).toBeTruthy();
  expect(screen.queryByTestId('descartar-cambios')).toBeNull();
});

test('con cambios: pregunta «¿Descartar cambios?» y no navega; «Seguir editando» conserva lo escrito', async () => {
  montarPila();
  await act(async () => fireEvent.changeText(screen.getByTestId('form-nombre'), 'Mercadona Centro'));
  await pulsar('tab-MAS');
  expect(screen.getByTestId('descartar-cambios')).toBeTruthy();
  expect(screen.getByText('¿Descartar cambios?')).toBeTruthy();
  expect(screen.queryByTestId('menu-mas')).toBeNull(); // no ha navegado
  await pulsar('descartar-cambios-seguir');
  expect(screen.queryByTestId('descartar-cambios')).toBeNull();
  expect(screen.getByTestId('form-nombre').props.value).toBe('Mercadona Centro'); // sin pérdida
});

test('con cambios: «Descartar» vuelve al menú «Más» (los cambios se pierden)', async () => {
  montarPila();
  await act(async () => fireEvent.changeText(screen.getByTestId('form-nombre'), 'Mercadona Centro'));
  await pulsar('tab-MAS');
  await pulsar('descartar-cambios-descartar');
  expect(screen.getByTestId('menu-mas')).toBeTruthy();
  expect(screen.queryByTestId('form-nombre')).toBeNull();
});

test('volver al valor de partida ya no cuenta como cambio: vuelve sin preguntar', async () => {
  montarPila();
  await act(async () => fireEvent.changeText(screen.getByTestId('form-nombre'), 'Otro'));
  await act(async () => fireEvent.changeText(screen.getByTestId('form-nombre'), 'Mercadona'));
  await pulsar('tab-MAS');
  expect(screen.getByTestId('menu-mas')).toBeTruthy();
});

// ------------------------------------------------------------------ DUD-UX1-01: salida por «Cancelar»
async function abrirAltaCategoria() {
  await montarApp();
  await pulsar('tab-MAS');
  await pulsar('mas-ajustes');
  await pulsar('ajustes-categorias');
  expect(await screen.findByTestId('fila-hogar')).toBeTruthy();
  await pulsar('nueva-categoria');
  expect(await screen.findByTestId('nueva-categoria-pantalla')).toBeTruthy();
}

test('DUD-UX1-01 · App: «Cancelar» sin cambios sale del alta sin preguntar', async () => {
  await abrirAltaCategoria();
  await pulsar('alta-cancelar');
  expect(screen.queryByTestId('descartar-cambios')).toBeNull();
  expect(screen.queryByTestId('nueva-categoria-pantalla')).toBeNull();
  expect(screen.getByTestId('fila-hogar')).toBeTruthy();
});

test('DUD-UX1-01 · App: «Cancelar» con cambios pregunta; «Seguir editando» conserva lo escrito; «Descartar» sale', async () => {
  await abrirAltaCategoria();
  await act(async () => fireEvent.changeText(screen.getByTestId('alta-nombre'), 'Mascotas'));
  await pulsar('alta-cancelar');
  expect(screen.getByTestId('descartar-cambios')).toBeTruthy(); // O-DUD01-01: con cambios no sale sin confirmar
  expect(screen.getByTestId('nueva-categoria-pantalla')).toBeTruthy();
  await pulsar('descartar-cambios-seguir');
  expect(screen.queryByTestId('descartar-cambios')).toBeNull();
  expect(screen.getByTestId('alta-nombre').props.value).toBe('Mascotas');
  await pulsar('alta-cancelar');
  await pulsar('descartar-cambios-descartar');
  expect(screen.queryByTestId('nueva-categoria-pantalla')).toBeNull();
  expect(screen.getByTestId('fila-hogar')).toBeTruthy();
});

function FormularioConSalida(p: { onSalir: () => void }) {
  const [nombre, setNombre] = useState('Mercadona');
  const salida = usarCambiosSinGuardar(true, { nombre });
  return (
    <View style={{ flex: 1 }}>
      {salida.hojaDescartar}
      <Text testID="form-cancelar" onPress={() => salida.salir(p.onSalir)}>Cancelar</Text>
      <TextInput testID="form-nombre" value={nombre} onChangeText={setNombre} />
    </View>
  );
}

test('DUD-UX1-01 · `salir`: sin cambios sale; con cambios pregunta y solo «Descartar» sale (O-DUD01-01)', async () => {
  const onSalir = jest.fn();
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <FormularioConSalida onSalir={onSalir} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  await pulsar('form-cancelar');
  expect(onSalir).toHaveBeenCalledTimes(1);
  await act(async () => fireEvent.changeText(screen.getByTestId('form-nombre'), 'Otro'));
  await pulsar('form-cancelar');
  expect(onSalir).toHaveBeenCalledTimes(1);
  expect(screen.getByText('¿Descartar cambios?')).toBeTruthy();
  await pulsar('descartar-cambios-seguir');
  expect(onSalir).toHaveBeenCalledTimes(1);
  await pulsar('form-cancelar');
  await pulsar('descartar-cambios-descartar');
  expect(onSalir).toHaveBeenCalledTimes(2);
});
