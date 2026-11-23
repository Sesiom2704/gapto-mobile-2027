// ============================================================
// GAPTO MOBILE 2027 · LABORATORIO (rama lab-t5)
// Fichero: lab_t5_l1_renta_revision.test.tsx
// Ruta: mobile/__tests__/lab_t5_l1_renta_revision.test.tsx
// Descripción: L1 · tarea del aniversario (R4-A, R5): marca «LAB»; exacta con céntimos y propuesta a la baja; «Aplicar» registra
//   la renta elegida (editable); «No aplicar este año» registra sin renta. Discriminante de M-LAB-L1-07 (propuesta redondeada
//   al alza en el cliente).
// Versión: 0.1.0 (LAB T5 · L1)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { LabRentaRevisionScreen, propuestaRevision } from '../src/screens/LabRentaRevisionScreen';
import { ProveedorTema } from '../src/theme/tema';

jest.mock('expo-font', () => ({ ...jest.requireActual('expo-font'), isLoaded: () => true }));
const METRICAS = { frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };

function montar() {
  const registrarRevision = jest.fn(async () => ({ ok: true }));
  const onCerrar = jest.fn();
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <LabRentaRevisionScreen cliente={{ registrarRevision }} contratoId="k1" nombre="ALLE" aniversario="2026-09-01" rentaAnterior="550.00" onCerrar={onCerrar} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return { registrarRevision, onCerrar };
}

test('R5: exacta y propuesta a la baja', () => {
  expect(propuestaRevision(550, 2)).toEqual({ exacta: 561, propuesta: 561 });
  expect(propuestaRevision(561, 2.8)).toEqual({ exacta: 576.708, propuesta: 576 });
});

test('marca LAB; «Aplicar» registra la propuesta (o la renta editada); «No aplicar este año» sin renta', async () => {
  const { registrarRevision, onCerrar } = montar();
  expect(screen.getByTestId('lab-marca')).toBeTruthy();
  fireEvent.changeText(screen.getByTestId('lab-indice'), '2,9');                  // 550 × 1,029 = 565,95 → 565 (a la baja)
  expect(screen.getByTestId('lab-renta').props.value).toBe('565');
  await act(async () => fireEvent.press(screen.getByTestId('lab-aplicar')));
  expect(registrarRevision).toHaveBeenCalledWith('k1', expect.objectContaining({ decision: 'APLICADA', renta_aplicada: '565.00', indice_porcentaje: '2.9' }));
  expect(onCerrar).toHaveBeenCalledWith(true);
  await act(async () => fireEvent.press(screen.getByTestId('lab-no-aplicar')));
  expect(registrarRevision).toHaveBeenLastCalledWith('k1', expect.objectContaining({ decision: 'NO_APLICADA', motivo: 'No aplicar este año' }));
});
