// ============================================================
// GAPTO MOBILE 2027
// Fichero: t6_s1_piezas_comunes.test.tsx
// Ruta: mobile/__tests__/t6_s1_piezas_comunes.test.tsx
// Descripción: F06 T6 «UX ágil» · S1 piezas comunes (F09 0.55 §12.107.1 puntos 5, 6 y 9):
//   - botones: Principal, Crítico y Texto viven en Basicos.tsx; HojasCategoria reexporta el Crítico (mismo objeto). El Secundario
//     sigue en SelectorCategorias hasta S2 (test_154 I13-A; DESVIACIONES T6-D-03);
//   - selectores (Tercero, Participante, Contexto) a pantalla completa con «Cerrar» arriba a la derecha y teclado cerrado al abrirse;
//     los que ya eran pantalla completa (Magnitudes, Iconos, Persona del reparto) también cierran el teclado (Categoría, en S2);
//   - teclado decimal en porcentaje, plazo y tipo (`CampoTexto decimal`), sin puntos de miles;
//   - «Banco» de la compra y «Tercero» de Registrar gasto usan el mismo selector común (`SelectorTercero`) y el valor
//     que se envía es el identificador del tercero elegido.
// Versión: 0.1.0 (F06 T6 · S1 piezas comunes)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { Keyboard } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta } from '../src/api/cliente';
import * as Basicos from '../src/components/Basicos';
import { SelectorContexto } from '../src/components/Contextos';
import { CampoTexto } from '../src/components/Formulario';
import * as HojasCategoria from '../src/components/HojasCategoria';
import { PantallaSelector } from '../src/components/PantallaSelector';
import * as SelectorCategorias from '../src/components/SelectorCategorias';
import { SelectorTercero } from '../src/components/SelectorTercero';
import { ProveedorTema } from '../src/theme/tema';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));

declare const __dirname: string;
const fs: { readFileSync(f: string, e: 'utf8'): string } = require('fs');
const path: { join(...p: string[]): string } = require('path');
const fuente = (rel: string) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');

const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } };
const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const montar = (el: React.ReactElement) =>
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">{el}</ProveedorTema>
    </SafeAreaProvider>,
  );

afterEach(() => jest.restoreAllMocks());

test('punto 9 · el botón crítico vive en Basicos y HojasCategoria reexporta el mismo componente', () => {
  expect(typeof Basicos.BotonPrimario).toBe('function');
  expect(typeof Basicos.BotonCritico).toBe('function');
  expect(typeof Basicos.BotonTexto).toBe('function');
  expect(SelectorCategorias.BotonPrimario).toBe(Basicos.BotonPrimario);
  expect(HojasCategoria.BotonCritico).toBe(Basicos.BotonCritico);
  expect(fuente('src/components/HojasCategoria.tsx')).not.toMatch(/export function Boton(Secundario|Critico|Primario|Texto)/);
});

test('punto 9 · Secundario y Crítico: alto 52 y radio 12, como el Principal', () => {
  montar(
    <>
      <Basicos.BotonPrimario testID="b-pri" titulo="Guardar" onPress={jest.fn()} />
      <SelectorCategorias.BotonSecundario testID="b-sec" titulo="Volver" onPress={jest.fn()} />
      <Basicos.BotonCritico testID="b-cri" titulo="Borrar" onPress={jest.fn()} />
    </>,
  );
  const estilo = (id: string) => Object.assign({}, ...[screen.getByTestId(id).props.style].flat(Infinity).filter(Boolean));
  for (const id of ['b-pri', 'b-sec', 'b-cri']) {
    expect(estilo(id).minHeight).toBe(52);
    expect(estilo(id).borderRadius).toBe(12);
  }
});

test('puntos 5 y 6 · PantallaSelector: pantalla completa, «Cerrar» arriba a la derecha y teclado cerrado al abrirse', async () => {
  const cerrar = jest.spyOn(Keyboard, 'dismiss');
  const onCerrar = jest.fn();
  montar(
    <PantallaSelector titulo="Banco" testID="sel" onCerrar={onCerrar} testIDCerrar="sel-cerrar">
      <></>
    </PantallaSelector>,
  );
  expect(cerrar).toHaveBeenCalledTimes(1);
  const raiz = Object.assign({}, ...[screen.getByTestId('sel').props.style].flat(Infinity).filter(Boolean));
  expect(raiz).toMatchObject({ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 });
  await pulsar('sel-cerrar');
  expect(onCerrar).toHaveBeenCalledTimes(1);
});

test('puntos 5 y 6 · los selectores de Tercero, Participante y Contexto usan el marco común; los de pantalla completa cierran el teclado', () => {
  for (const f of ['src/components/SelectorTercero.tsx', 'src/components/SelectorParticipante.tsx', 'src/components/Contextos.tsx']) {
    const t = fuente(f);
    expect(t).toMatch(/<PantallaSelector titulo=/);
    expect(t).not.toMatch(/<Hoja titulo=[^>]*testID="selector-(tercero|participante|contexto)"/);
    expect(t).not.toMatch(/<ScrollView style=\{\{ maxHeight: 320 \}\}/);
  }
  for (const f of ['src/components/SelectorMagnitudes.tsx', 'src/components/SelectorIconos.tsx', 'src/components/Reparto.tsx']) {
    expect(fuente(f)).toMatch(/useCerrarTecladoAlAbrir\(\);/);
  }
});

test('punto 9 · CampoTexto decimal: teclado decimal y sin puntos de miles; los campos de porcentaje, plazo y tipo lo usan', () => {
  const cambiar = jest.fn();
  montar(<CampoTexto decimal testID="pct" etiqueta="Porcentaje" valor="" onCambiar={cambiar} />);
  const campo = screen.getByTestId('pct');
  expect(campo.props.keyboardType).toBe('decimal-pad');
  expect(campo.props.inputMode).toBe('decimal');
  fireEvent.changeText(campo, '12345,5');
  expect(cambiar).toHaveBeenCalledWith('12345,5');
  const usos: [string, RegExp][] = [
    ['src/screens/CompraScreen.tsx', /<CampoTexto decimal testID="compra-hip-tasa"/],
    ['src/screens/CompraScreen.tsx', /<CampoTexto decimal testID="compra-hip-plazo"/],
    ['src/screens/CompraScreen.tsx', /<CampoTexto key=\{a\.actor_id\} decimal testID=\{`\$\{p\.testID\}-pct-/],
    ['src/screens/ContratoAltaScreen.tsx', /<CampoTexto decimal testID="contrato-clausula-porcentaje"/],
    ['src/screens/ContratoAltaScreen.tsx', /<CampoTexto decimal testID="contrato-clausula-periodicidad"/],
    ['src/screens/ContratoAltaScreen.tsx', /<CampoTexto decimal testID=\{`contrato-servicio-/],
    ['src/screens/GastoPropiedadScreen.tsx', /<CampoTexto key=\{a\.actor_id\} decimal testID=/],
    ['src/screens/HipotecaCuadroScreen.tsx', /<CampoTexto key=\{a\.actor_id\} decimal testID=/],
    ['src/screens/RevisarTipoScreen.tsx', /<CampoTexto decimal testID="hip-rev-tasa"/],
    ['src/screens/RevisarTipoScreen.tsx', /<CampoTexto decimal testID="hip-rev-diferencial"/],
    ['src/screens/ServiciosScreens.tsx', /<CampoTexto decimal testID="tratamiento-porcentaje"/],
  ];
  for (const [f, re] of usos) expect([f, re.test(fuente(f))]).toEqual([f, true]);
});

test('punto 5 · «Banco» de la compra usa el mismo selector de terceros que Registrar gasto; se envía el identificador elegido', async () => {
  const compra = fuente('src/screens/CompraScreen.tsx');
  const registro = fuente('src/screens/RegistroGastoScreen.tsx');
  const imp = "import { SelectorTercero } from '../components/SelectorTercero';";
  expect(compra).toContain(imp);
  expect(registro).toContain(imp);
  expect(compra).not.toMatch(/function bancosVisibles|testID="compra-hip-banco-buscar"/);
  // La compra guarda como financiador el id que devuelve el selector (el payload se comprueba en hipoteca_pantallas).
  expect(compra).toMatch(/setHip\(\{ \.\.\.hip, financiadorId: t \? t\.id : null \}\)/);

  // El selector común devuelve el tercero elegido con su identificador, sin transformarlo.
  const cli = {
    listarTerceros: jest.fn(async () => ok({ terceros: [{ id: 'banco-1', nombre: 'Banco Ejemplo', naturaleza: 'EMPRESA', enabled: true, row_version: 3 }] })),
    senalesTerceros: jest.fn(),
  } as unknown as ClienteApi;
  const elegir = jest.fn();
  const cerrar = jest.spyOn(Keyboard, 'dismiss');
  montar(<SelectorTercero cliente={cli} nuevoId={() => 'x'} titulo="Banco" seleccionadoId={null} onElegir={elegir} onCerrar={jest.fn()} />);
  expect(cerrar).toHaveBeenCalled();
  expect(screen.getByTestId('tercero-cerrar')).toBeTruthy();
  await waitFor(() => screen.getByTestId('tercero-banco-1'));
  await pulsar('tercero-banco-1');
  expect(elegir).toHaveBeenCalledWith(expect.objectContaining({ id: 'banco-1' }));
});

test('puntos 5 y 6 · selector de Contexto: pantalla completa, «Cerrar» arriba, teclado cerrado y mismas acciones', async () => {
  const cli = {
    listarContextos: jest.fn(async () => ok({ contextos: [
      { id: 'ctx-1', nombre: 'Viaje', tipo_contexto: 'VIAJE', fecha_inicio: null, fecha_fin: null, enabled: true, row_version: 1 },
      { id: 'ctx-off', nombre: 'Viejo', tipo_contexto: 'VIAJE', fecha_inicio: null, fecha_fin: null, enabled: false, row_version: 1 }] })),
  } as unknown as ClienteApi;
  const elegir = jest.fn();
  const nuevo = jest.fn();
  const onCerrar = jest.fn();
  const cerrarTeclado = jest.spyOn(Keyboard, 'dismiss');
  montar(<SelectorContexto cliente={cli} seleccionadoId={null} onElegir={elegir} onNuevo={nuevo} onCerrar={onCerrar} />);
  expect(cerrarTeclado).toHaveBeenCalledTimes(1);
  const raiz = Object.assign({}, ...[screen.getByTestId('selector-contexto').props.style].flat(Infinity).filter(Boolean));
  expect(raiz).toMatchObject({ position: 'absolute', top: 0, bottom: 0 });
  await waitFor(() => screen.getByTestId('contexto-ctx-1'));
  expect(screen.queryByTestId('contexto-ctx-off')).toBeNull();
  await pulsar('contexto-ctx-1');
  expect(elegir).toHaveBeenCalledWith(expect.objectContaining({ id: 'ctx-1' }));
  await pulsar('contexto-ninguno');
  expect(elegir).toHaveBeenLastCalledWith(null);
  await pulsar('contexto-nuevo');
  expect(nuevo).toHaveBeenCalledTimes(1);
  await pulsar('contexto-cerrar');
  expect(onCerrar).toHaveBeenCalledTimes(1);
});
