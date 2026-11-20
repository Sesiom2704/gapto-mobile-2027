// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos_sin_renta.test.tsx
// Ruta: mobile/__tests__/contratos_sin_renta.test.tsx
// Descripción: Frontera «sin renta» y entrada desde la ficha de F06-02/03 (contrato N1 v1.1 R-E-01, PC-CON-01; lámina CON v0.8 «Sin renta ni fianza en todo el bloque»): ninguna petición del cliente de contratos tiene campos `renta`, `fianza`, cobro ni cuenta de cobro (guarda estática sobre las fuentes nuevas); el cliente de contratos no se cuela en `cliente.ts` (test_154 I13a: igualdad exacta de imports); la ficha de la propiedad solo muestra «Contratos» si recibe `onContratos` (sin la prop no cambia) y la fila no lleva importes. «Quitar» no existe en roles ni clasificaciones.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { PropiedadFichaScreen } from '../src/screens/PropiedadFichaScreen';
import { ProveedorTema } from '../src/theme/tema';
import { METRICAS, vista } from './contratos_fixtures';

declare const __dirname: string;
const fs: { readFileSync(f: string, e: 'utf8'): string } = require('fs');
const path: { join(...p: string[]): string } = require('path');
const RAIZ = path.join(__dirname, '..');
const leer = (rel: string) => fs.readFileSync(path.join(RAIZ, rel), 'utf8');

const FUENTES_NUEVAS = [
  'src/api/contratos.ts', 'src/domain/contratos.ts', 'src/components/SelectorParticipante.tsx', 'src/components/OpcionesContrato.tsx',
  'src/screens/ContratoAltaScreen.tsx', 'src/screens/ContratosScreen.tsx', 'src/screens/ServiciosScreens.tsx', 'src/screens/TerceroFichaScreen.tsx',
];

test('guarda estática: ninguna fuente nueva define campos de renta, fianza o cobro (R-E-01)', () => {
  for (const f of FUENTES_NUEVAS) {
    const codigo = leer(f).split('\n').filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*') && !l.trim().startsWith('/**')).join('\n');
    // sin los literales de texto: solo claves de objeto o de tipo (`renta:`, `fianza?:`, `renta_mensual`, `dia_cobro`, `cuenta_cobro`…)
    const sinTextos = codigo.replace(/'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`[^`]*`/g, "''");
    expect(sinTextos).not.toMatch(/(^|[\s{,(])(renta|fianza)\??\s*:/m);
    expect(sinTextos).not.toMatch(/\b(renta_mensual|dia_cobro|cuenta_cobro|importe_renta|ipc_aplicado|calendario_renta|cobros?)\s*[:?]/);
  }
});

test('el cliente de contratos va aparte: `cliente.ts` no lo importa ni lo reexporta (test_154 I13a)', () => {
  const c = leer('src/api/cliente.ts');
  expect(c).not.toMatch(/from '\.\/contratos'/);
  expect(c).not.toMatch(/crearClienteContratos/);
  const nuevo = leer('src/api/contratos.ts');
  expect(nuevo).toMatch(/from '\.\/cliente'/);
});

test('ni las fuentes nuevas ni los textos incluyen «Quitar» como acción de roles o clasificaciones', () => {
  for (const f of ['src/screens/TerceroFichaScreen.tsx', 'src/domain/contratos.ts']) {
    expect(leer(f)).not.toMatch(/titulo="(Quitar|Eliminar|Desasignar)[^"]*"/);
  }
});

function ficha(extra: Partial<React.ComponentProps<typeof PropiedadFichaScreen>> = {}) {
  return render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <PropiedadFichaScreen vista={vista()} onAtras={jest.fn()} onRevisarValor={jest.fn()} onHistorico={jest.fn()} onTitularidad={jest.fn()} onEditar={jest.fn()} {...extra} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

test('la ficha muestra la fila «Contratos» solo con `onContratos`, sin importes, y la abre', async () => {
  const onContratos = jest.fn();
  ficha({ onContratos });
  expect(screen.getByTestId('prop-accion-contratos-titulo').props.children).toBe('Contratos');
  expect(screen.getByTestId('prop-accion-contratos-detalle').props.children).toBe('Alquileres, personas y servicios');
  await act(async () => fireEvent.press(screen.getByTestId('prop-accion-contratos')));
  expect(onContratos).toHaveBeenCalled();
});

test('sin `onContratos` la ficha no cambia', () => {
  ficha();
  expect(screen.queryByTestId('prop-accion-contratos')).toBeNull();
});
