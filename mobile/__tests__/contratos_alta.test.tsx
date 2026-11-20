// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos_alta.test.tsx
// Ruta: mobile/__tests__/contratos_alta.test.tsx
// Descripción: Asistente «Nuevo contrato» de F06-02/03 (lámina CON v0.8 B1–B6, B2b, B3b; contrato N1 v1.1 C-CON-01, C-CON-05) contra dobles en memoria: recorrido de 5 pasos sin renta ni fianza y una sola operación de guardado (payload exacto, sin `renta`/`fianza`); B2b «Ya está alquilada en esas fechas» (solape bloqueante para firmados, solo borrador; vivienda completa ↔ habitación en los dos sentidos; el fin previsto no libera) y el 409 SOLAPE_CON_CONTRATO_FIRMADO del servidor con su lista; D25 en pantalla («Tú» no es inquilino, ni agencia ni administrador; principal solo en arrendadores e inquilinos; la agencia no cuenta para firmar); B3b agencia o administrador sin propuesta de rol; E3 (propuesta de rol tras guardar, nada marcado, escritura independiente que no deshace el contrato); reintento con la misma intención tras un indeterminado y con intención nueva si el contenido cambia; cambio de inquilino (C1) que guarda con POST …/sucesor.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ContratoDetalle } from '../src/api/contratos';
import { TEXTO_INQUILINO_NO_YO } from '../src/domain/contratos';
import { ContratoAltaScreen } from '../src/screens/ContratoAltaScreen';
import { ProveedorTema } from '../src/theme/tema';
import {
  AHORA, clienteApi, clienteContratos, detalle, ficha, fila, indeterminado, METRICAS, nuevoId, ok, rechazo, reiniciarIds, escenarioA1, T_AGENCIA, T_ELENA, T_LAURA, tercero, terceroUso, vista,
} from './contratos_fixtures';

const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
beforeEach(() => reiniciarIds());

function montar(contratos = clienteContratos(), onCerrar = jest.fn(), extra: Partial<React.ComponentProps<typeof ContratoAltaScreen>> = {}) {
  render(
    <SafeAreaProvider initialMetrics={METRICAS}>
      <ProveedorTema forzar="light">
        <ContratoAltaScreen cliente={clienteApi()} contratos={contratos} propiedad={vista()} nuevoId={nuevoId} ahora={AHORA} onCerrar={onCerrar} {...extra} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
  return { contratos, onCerrar };
}

const conElena = (extra: Record<string, unknown> = {}) => clienteContratos({
  tercerosParaContrato: jest.fn(async () => ok({ terceros: [terceroUso(T_ELENA, 'Elena Sanz', { tipo: 'SIN_USO' }), terceroUso(T_AGENCIA, 'Inmobiliaria Centro', { tipo: 'SIN_USO' }, { naturaleza: 'EMPRESA' })] })),
  fichaTercero: jest.fn(async (id: string) => ok(ficha({ tercero: tercero(id, id === T_ELENA ? 'Elena Sanz' : 'Inmobiliaria Centro', { row_version: 7 }), roles: [], uso: [] }))),
  ...extra,
});

async function pasoQue(habitacion = 4) {
  await pulsar('contrato-tipo-HABITACION');
  await waitFor(() => screen.getByTestId(`contrato-habitacion-${habitacion}`));
  await pulsar(`contrato-habitacion-${habitacion}`);
  await pulsar('contrato-continuar');
}
async function pasoFechas(firmado: boolean, inicio = '01/11/2026') {
  expect(screen.getByTestId('contrato-paso-fechas')).toBeTruthy();
  await escribir('contrato-inicio', inicio);
  await escribir('contrato-fin-previsto', '31/10/2027');
  await pulsar(firmado ? 'contrato-estado-FORMALIZADO' : 'contrato-estado-BORRADOR');
  await pulsar('contrato-continuar');
}
async function anadirInquilino() {
  await pulsar('contrato-anadir-inquilino');
  await waitFor(() => screen.getByTestId(`participante-${T_ELENA}`));
  await pulsar(`participante-${T_ELENA}`);
}
async function hastaResumen() {
  await pasoQue();
  await pasoFechas(true);
  await waitFor(() => screen.getByTestId('contrato-persona-PROPIETARIO-yo'));
  await anadirInquilino();
  await pulsar('contrato-continuar');                       // → B4
  await pulsar('contrato-clausula-IPC');
  await pulsar('contrato-continuar');                       // → B5
  await waitFor(() => screen.getByTestId('contrato-servicio-s-luz-abrir'));
  await pulsar('contrato-servicio-s-luz-abrir');
  await pulsar('contrato-servicio-s-luz-POR_FACTURA');
  await pulsar('contrato-continuar');                       // → B6
  await waitFor(() => screen.getByTestId('contrato-paso-resumen'));
}

test('B1 → B6: 5 pasos sin renta ni fianza; nada viene marcado; el resumen guarda todo en UNA operación', async () => {
  const { contratos } = montar(conElena());
  // B1: ningún tipo marcado; el texto explica el borrador por solape
  expect(screen.getByTestId('contrato-paso-que')).toBeTruthy();
  for (const t of ['VIVIENDA_COMPLETA', 'HABITACION', 'OTRO']) expect(screen.getByTestId(`contrato-tipo-${t}`).props.accessibilityState.checked).toBe(false);
  expect(screen.getByTestId('contrato-que-ayuda').props.children).toMatch(/solo podrás guardarlo como borrador/);
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(true);
  await pulsar('contrato-tipo-HABITACION');
  await waitFor(() => screen.getByTestId('contrato-habitacion-1'));
  expect(screen.getByTestId('contrato-habitacion-1').props.accessibilityLabel).toBe('Habitación 1. Ocupada');
  expect(screen.getByTestId('contrato-habitacion-2').props.accessibilityLabel).toBe('Habitación 2. Ocupada hasta 31 ago 2027');
  expect(screen.getByTestId('contrato-habitacion-3').props.accessibilityLabel).toBe('Habitación 3. Contrato desde 1 dic');
  expect(screen.getByTestId('contrato-habitacion-4').props.accessibilityLabel).toBe('Habitación 4. Libre');
  expect(screen.getAllByTestId(/^contrato-habitacion-\d$/)).toHaveLength(5);
  await pulsar('contrato-habitacion-4');
  await pulsar('contrato-continuar');
  // B2: «¿Está firmado?» sin valor por defecto
  expect(screen.getByTestId('contrato-estado-FORMALIZADO').props.accessibilityState.checked).toBe(false);
  expect(screen.getByTestId('contrato-estado-BORRADOR').props.accessibilityState.checked).toBe(false);
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(true);
  await escribir('contrato-inicio', '01/11/2026');
  await escribir('contrato-fin-previsto', '31/10/2027');
  await pulsar('contrato-estado-FORMALIZADO');
  await pulsar('contrato-continuar');
  // B3: arrendadores propuestos por la titularidad; «Tú» principal; «Tú» no se ofrece como inquilino
  await waitFor(() => screen.getByTestId('contrato-persona-PROPIETARIO-yo'));
  expect(contratos.propuestaContrato).toHaveBeenCalledWith('p1', { tipo: 'HABITACION', habitacion: 4, inicio: '2026-11-01' });
  expect(screen.getByTestId('contrato-persona-PROPIETARIO-yo-principal').props.accessibilityState.checked).toBe(true);
  expect(screen.getByTestId(`contrato-persona-PROPIETARIO-${T_LAURA}-principal`).props.accessibilityState.checked).toBe(false);
  expect(screen.getByTestId('contrato-personas-ayuda').props.children).toMatch(/Hace falta un principal solo en arrendadores e inquilinos/);
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(true);   // falta inquilino
  await anadirInquilino();
  expect(screen.getByTestId(`contrato-persona-INQUILINO-${T_ELENA}-principal`).props.accessibilityState.checked).toBe(true);
  await pulsar('contrato-continuar');
  // B4: nada elegido → continuar desactivado
  expect(screen.getByTestId('contrato-paso-revision')).toBeTruthy();
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(true);
  await pulsar('contrato-clausula-IPC');
  await pulsar('contrato-continuar');
  // B5
  await waitFor(() => screen.getByTestId('contrato-servicio-s-luz-abrir'));
  await pulsar('contrato-servicio-s-luz-abrir');
  await pulsar('contrato-servicio-s-luz-POR_FACTURA');
  await pulsar('contrato-continuar');
  // B6
  await waitFor(() => screen.getByTestId('contrato-nombre'));
  expect(screen.getByTestId('contrato-nombre').props.value).toBe('26-HAB4-ES');
  expect(contratos.propuestaContrato).toHaveBeenLastCalledWith('p1', { tipo: 'HABITACION', habitacion: 4, inicio: '2026-11-01', inquilinoId: T_ELENA });
  expect(screen.getByTestId('contrato-res-sin-renta').props.children).toBe('La renta y la fianza las añadirás desde el contrato cuando llegue la parte de cobros.');
  expect(screen.getByTestId('contrato-res-inquilinos-valor').props.children).toBe('Elena Sanz');
  expect(screen.getByTestId('contrato-res-arrendadores-valor').props.children).toBe('Tú y Laura Pérez');
  expect(screen.queryAllByTestId(/renta|fianza|cobro|cuenta/i).filter((x) => /-(renta|fianza|cobro|cuenta)/i.test(x.props.testID ?? '') && !/sin-renta/.test(x.props.testID))).toHaveLength(0);
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-hecho'));
  expect(contratos.altaContrato).toHaveBeenCalledTimes(1);
  const enviado = contratos.altaContrato.mock.calls[0][0];
  expect(enviado).toEqual({
    intencion_id: '00000000-0000-4000-8000-000000000001', propiedad_id: 'p1', tipo: 'HABITACION', habitacion: 4, nombre: '26-HAB4-ES', fecha_inicio: '2026-11-01',
    fecha_fin_prevista: '2027-10-31', estado: 'FORMALIZADO',
    personas: [
      { actor: 'YO', rol: 'PROPIETARIO', principal: true },
      { actor: { tercero_id: T_LAURA }, rol: 'PROPIETARIO', principal: false },
      { actor: { tercero_id: T_ELENA }, rol: 'INQUILINO', principal: true },
    ],
    clausula_revision: { tipo: 'IPC', indice_referencia: 'IPC INE', periodicidad_meses: null, fecha_primera_revision: null },
    servicios: [{ servicio_id: 's-luz', modo: 'POR_FACTURA', desde: '2026-11-01', actor: { tercero_id: T_ELENA } }],
  });
  expect(enviado).not.toHaveProperty('renta');
  expect(enviado).not.toHaveProperty('fianza');
});

test('B2b: si la habitación está alquilada en esas fechas, solo borrador (decisión 3); «Revisar fechas» vuelve y «Guardar como borrador» sigue como borrador', async () => {
  const viv = fila({ contrato_id: 'viv', nombre: '26-VIV-JM', tipo: 'VIVIENDA_COMPLETA', habitacion: null, fecha_inicio: '2026-09-01', fecha_fin_prevista: '2027-08-31' });
  const contratos = conElena({ contratosDePropiedad: jest.fn(async () => ok({ ...escenarioA1(), contratos: [viv] })) });
  montar(contratos);
  await pasoQue(2);
  await escribir('contrato-inicio', '01/11/2026');
  await pulsar('contrato-estado-FORMALIZADO');
  await pulsar('contrato-continuar');
  expect(screen.getByTestId('contrato-solape')).toBeTruthy();
  expect(screen.getByText('Ya está alquilada en esas fechas')).toBeTruthy();
  expect(screen.getByTestId('contrato-solape-info-intro').props.children).toBe('La habitación 2 desde el 1 nov 2026 coincide con este contrato firmado de la vivienda completa:');
  expect(screen.getByTestId('contrato-solape-info-fila-0').props.children).toBe('26-VIV-JM · Vivienda completa · 1 sep 2026 → sin fin real');
  expect(screen.getByTestId('contrato-solape-info-aviso').props.children)
    .toBe('No se puede guardar como firmado. Puedes guardarlo como borrador y firmarlo cuando registres el fin real de ese contrato, o revisar las fechas.');
  expect(screen.queryByTestId('contrato-paso-personas')).toBeNull();
  // Revisar fechas: vuelve a B2 sin avanzar
  await pulsar('contrato-solape-revisar');
  expect(screen.getByTestId('contrato-paso-fechas')).toBeTruthy();
  // Guardar como borrador: avanza a Personas con estado BORRADOR (un borrador no cuenta para el solape)
  await pulsar('contrato-continuar');
  await pulsar('contrato-solape-borrador');
  await waitFor(() => screen.getByTestId('contrato-paso-personas'));
  await anadirInquilino();
  await pulsar('contrato-continuar');
  await pulsar('contrato-clausula-NO_SE');
  await pulsar('contrato-continuar');
  await pulsar('contrato-continuar');
  await waitFor(() => screen.getByTestId('contrato-guardar'));
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-hecho'));
  expect(contratos.altaContrato.mock.calls[0][0].estado).toBe('BORRADOR');
  expect(contratos.altaContrato.mock.calls[0][0]).not.toHaveProperty('clausula_revision');   // «No lo sé»: sin fila, nunca NINGUNA
});

test('el borrador no se compara: la misma habitación como BORRADOR avanza sin B2b', async () => {
  const contratos = conElena();
  montar(contratos);
  await pasoQue(2);                                   // la 2 está ocupada por un firmado en el escenario A1
  await pasoFechas(false);
  expect(screen.queryByTestId('contrato-solape')).toBeNull();
  await waitFor(() => screen.getByTestId('contrato-paso-personas'));
});

test('el fin previsto vencido NO libera: la habitación 5 sigue ocupada y firmar choca (decisión 6)', async () => {
  montar(conElena());
  await pasoQue(5);
  await pasoFechas(true, '18/11/2026');
  expect(screen.getByTestId('contrato-solape')).toBeTruthy();
  expect(screen.getByTestId('contrato-solape-info-fila-0').props.children).toBe('25-HAB5-LM · Habitación 5 · 1 nov 2025 → sin fin real');
});

test('vivienda completa choca con una habitación firmada (sentido contrario) y OTRO no choca con nada', async () => {
  montar(conElena());
  await pulsar('contrato-tipo-VIVIENDA_COMPLETA');
  await pulsar('contrato-continuar');
  await waitFor(() => screen.getByTestId('contrato-paso-fechas'));
  await escribir('contrato-inicio', '01/11/2026');
  await pulsar('contrato-estado-FORMALIZADO');
  await pulsar('contrato-continuar');
  expect(screen.getByTestId('contrato-solape')).toBeTruthy();
  expect(screen.getByTestId('contrato-solape-info-intro').props.children).toMatch(/^La vivienda completa desde el 1 nov 2026 coincide con este contrato firmado de una habitación:$/);
});

test('OTRO no solapa con nada', async () => {
  montar(conElena());
  await pulsar('contrato-tipo-OTRO');
  await pulsar('contrato-continuar');
  await waitFor(() => screen.getByTestId('contrato-paso-fechas'));
  await escribir('contrato-inicio', '01/11/2026');
  await pulsar('contrato-estado-FORMALIZADO');
  await pulsar('contrato-continuar');
  await waitFor(() => screen.getByTestId('contrato-paso-personas'));
});

test('el 409 del servidor (solape bajo el lock) lleva a B2b con SU lista y no deja nada guardado', async () => {
  const contratos = conElena({
    altaContrato: jest.fn(async () => rechazo('SOLAPE_CON_CONTRATO_FIRMADO', 'x', { solapados: [{ id: 'z', nombre: '26-HAB4-ZZ', tipo: 'HABITACION', habitacion: 4, desde: '2026-10-01', hasta: null }] })),
  });
  montar(contratos);
  await hastaResumen();
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-solape'));
  expect(screen.getByTestId('contrato-solape-info-fila-0').props.children).toBe('26-HAB4-ZZ · Habitación 4 · 1 oct 2026 → sin fin real');
  expect(screen.queryByTestId('contrato-hecho')).toBeNull();
});

test('D25 en pantalla: «Tú» no se ofrece como inquilino; con «Tú» solo como propietario o gestor; la agencia no cuenta para firmar', async () => {
  montar(conElena());
  await pasoQue();
  await pasoFechas(true);
  await waitFor(() => screen.getByTestId('contrato-persona-PROPIETARIO-yo'));
  // el flujo del inquilino abre el selector de terceros directamente: no hay opción «Añadirme a mí»
  await pulsar('contrato-anadir-inquilino');
  await waitFor(() => screen.getByTestId('selector-participante'));
  expect(screen.queryByTestId('contrato-anadir-yo')).toBeNull();
  expect(screen.queryByText('Tú')).toBeNull();
  await pulsar('participante-cerrar');
  // solo una agencia como «inquilino» de nada: añadir agencia y seguir sin inquilino → no se puede continuar (no cuenta como parte)
  await pulsar('contrato-anadir-agencia');
  await pulsar('contrato-anadir-rol-AGENCIA');
  expect(screen.queryByTestId('contrato-anadir-yo')).toBeNull();               // «Tú» no puede ser agencia ni administrador
  await pulsar('contrato-quien');
  await waitFor(() => screen.getByTestId(`participante-${T_AGENCIA}`));
  await pulsar(`participante-${T_AGENCIA}`);
  expect(screen.getByTestId(`contrato-persona-AGENCIA-${T_AGENCIA}`)).toBeTruthy();
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(true);
  expect(screen.getByTestId('contrato-faltas').props.children).toBe('Para firmar hace falta un inquilino.');
});

test('B3b: agencia o administrador son solo terceros, sin principal obligatorio, con el texto de la lámina y SIN propuesta de rol tras guardar', async () => {
  const guardadoConAgencia = detalle({ contrato_id: 'nuevo', personas: [
    { persona_id: 'a', rol: 'INQUILINO', principal: true, actor: { yo: false, tercero_id: T_ELENA, nombre: 'Elena Sanz' }, vigente_desde: '2026-11-01', vigente_hasta: null },
    { persona_id: 'b', rol: 'ADMINISTRADOR', principal: false, actor: { yo: false, tercero_id: T_AGENCIA, nombre: 'Inmobiliaria Centro' }, vigente_desde: '2026-11-01', vigente_hasta: null },
  ] });
  const contratos = conElena({ altaContrato: jest.fn(async () => ok({ contrato_id: 'nuevo', row_version: 1, idempotente: false, contrato: guardadoConAgencia })) });
  montar(contratos);
  await pasoQue();
  await pasoFechas(true);
  await waitFor(() => screen.getByTestId('contrato-persona-PROPIETARIO-yo'));
  await anadirInquilino();
  await pulsar('contrato-anadir-agencia');
  expect(screen.getByTestId('contrato-anadir-rol-AGENCIA').props.accessibilityLabel).toBe('Agencia. Ha intermediado el alquiler');
  expect(screen.getByTestId('contrato-anadir-rol-ADMINISTRADOR').props.accessibilityLabel).toBe('Administrador. Gestiona el contrato o la finca');
  expect(screen.queryByTestId('contrato-quien')).toBeNull();                      // primero el papel
  await pulsar('contrato-anadir-rol-ADMINISTRADOR');
  expect(screen.getByTestId('contrato-agencia-ayuda').props.children).toBe('Queda como persona del contrato. No sustituye al arrendador ni al inquilino.');
  await pulsar('contrato-quien');
  await waitFor(() => screen.getByTestId(`participante-${T_AGENCIA}`));
  await pulsar(`participante-${T_AGENCIA}`);
  // sin principal marcado y aun así se puede continuar
  expect(screen.getByTestId(`contrato-persona-ADMINISTRADOR-${T_AGENCIA}-principal`).props.accessibilityState.checked).toBe(false);
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(false);
  await pulsar('contrato-continuar');
  await pulsar('contrato-clausula-NINGUNA');
  await pulsar('contrato-continuar');
  await pulsar('contrato-continuar');
  await waitFor(() => screen.getByTestId('contrato-guardar'));
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-hecho'));
  expect(contratos.altaContrato.mock.calls[0][0].personas).toContainEqual({ actor: { tercero_id: T_AGENCIA }, rol: 'ADMINISTRADOR', principal: false });
  // E3: el contrato devuelto lleva a la agencia (T_AGENCIA) entre sus personas; ni se consulta su ficha ni se le propone ningún rol
  await waitFor(() => screen.getByTestId('contrato-rol-propuesta'));
  const titulos: string[] = [];
  while (screen.queryByTestId('contrato-rol-propuesta')) {
    titulos.push(String(screen.getByTestId('contrato-rol-propuesta-titulo').props.children));
    await pulsar('contrato-rol-no');
  }
  expect(titulos.join(' | ')).not.toMatch(/Inmobiliaria Centro/);
  expect(contratos.fichaTercero).not.toHaveBeenCalledWith(T_AGENCIA);
  expect(contratos.anadirRoles).not.toHaveBeenCalled();
});

test('E3: tras guardar se propone el rol de inquilino (nada marcado); «Sí» es una escritura independiente; si falla, el contrato ya está guardado', async () => {
  const guardado: ContratoDetalle = detalle({
    contrato_id: 'nuevo', nombre: '26-HAB4-ES',
    personas: [
      { persona_id: 'a', rol: 'INQUILINO', principal: true, actor: { yo: false, tercero_id: T_ELENA, nombre: 'Elena Sanz' }, vigente_desde: '2026-11-01', vigente_hasta: null },
      { persona_id: 'b', rol: 'AGENCIA', principal: false, actor: { yo: false, tercero_id: T_AGENCIA, nombre: 'Inmobiliaria Centro' }, vigente_desde: '2026-11-01', vigente_hasta: null },
    ],
  });
  const contratos = conElena({
    altaContrato: jest.fn(async () => ok({ contrato_id: 'nuevo', row_version: 1, idempotente: false, contrato: guardado })),
    anadirRoles: jest.fn(async () => rechazo('VERSION_DESFASADA', 'x')),
  });
  const { onCerrar } = montar(contratos);
  await hastaResumen();
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-rol-propuesta'));
  expect(screen.getByTestId('contrato-rol-propuesta-titulo').props.children).toBe('Elena Sanz no tiene el rol «Inquilino»');
  expect(screen.getByTestId('contrato-rol-propuesta-texto').props.children).toMatch(/Un rol añadido no se puede quitar\.$/);
  // la agencia no genera propuesta: solo se consultó la ficha de Elena para proponer (la de la agencia sí se lee, pero no se propone nada)
  expect(contratos.anadirRoles).not.toHaveBeenCalled();                          // nada viene marcado ni se escribe solo
  await pulsar('contrato-rol-si');
  await waitFor(() => screen.getByTestId('contrato-rol-aviso'));
  expect(contratos.anadirRoles).toHaveBeenCalledWith(T_ELENA, { intencion_id: expect.any(String), row_version_esperada: 7, anadir: ['INQUILINO'] });
  expect(screen.getByTestId('contrato-rol-aviso').props.children.props.children).toMatch(/El contrato ya está guardado\.$/);
  expect(screen.queryByTestId('contrato-rol-propuesta')).toBeNull();
  await pulsar('contrato-listo');
  expect(onCerrar).toHaveBeenCalledWith(guardado);
});

test('E3: «No» no escribe ningún rol', async () => {
  const guardado = detalle({ contrato_id: 'nuevo', personas: [{ persona_id: 'a', rol: 'INQUILINO', principal: true, actor: { yo: false, tercero_id: T_ELENA, nombre: 'Elena Sanz' }, vigente_desde: '2026-11-01', vigente_hasta: null }] });
  const contratos = conElena({ altaContrato: jest.fn(async () => ok({ contrato_id: 'nuevo', row_version: 1, idempotente: false, contrato: guardado })) });
  montar(contratos);
  await hastaResumen();
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-rol-propuesta'));
  await pulsar('contrato-rol-no');
  expect(contratos.anadirRoles).not.toHaveBeenCalled();
  expect(screen.queryByTestId('contrato-rol-propuesta')).toBeNull();
});

test('un fallo indeterminado no dice que ha fallado y el reintento reenvía la MISMA intención; si el contenido cambia, intención nueva', async () => {
  const contratos = conElena();
  contratos.altaContrato.mockResolvedValueOnce(indeterminado());
  contratos.altaContrato.mockResolvedValueOnce(rechazo('FECHA_INICIO_REQUERIDA', 'x'));
  montar(contratos);
  await hastaResumen();
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-aviso'));
  expect(screen.getByTestId('contrato-aviso').props.children.props.children).toBe('No se ha podido confirmar si el contrato se guardó. Pulsa de nuevo «Guardar contrato»: no se duplicará.');
  await pulsar('contrato-guardar');                                              // reintento idéntico → replay
  await waitFor(() => expect(contratos.altaContrato).toHaveBeenCalledTimes(2));
  expect(contratos.altaContrato.mock.calls[1][0]).toEqual(contratos.altaContrato.mock.calls[0][0]);
  await waitFor(() => screen.getByTestId('contrato-aviso'));
  expect(screen.getByTestId('contrato-aviso').props.children.props.children).toBe('Falta la fecha de inicio.');
  // el contenido cambia (otro nombre) → intención nueva
  await escribir('contrato-nombre', 'Otro nombre');
  await pulsar('contrato-guardar');
  await waitFor(() => expect(contratos.altaContrato).toHaveBeenCalledTimes(3));
  expect(contratos.altaContrato.mock.calls[2][0].intencion_id).not.toBe(contratos.altaContrato.mock.calls[0][0].intencion_id);
  expect(contratos.altaContrato.mock.calls[2][0].nombre).toBe('Otro nombre');
});

test('un rechazo del servidor se muestra con texto propio (no el código)', async () => {
  const contratos = conElena({ altaContrato: jest.fn(async () => rechazo('PROPIEDAD_FUERA_DE_PATRIMONIO', 'x')) });
  montar(contratos);
  await hastaResumen();
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-aviso'));
  expect(screen.getByTestId('contrato-aviso').props.children.props.children).toBe('Esa propiedad ya había salido de tu patrimonio en la fecha de inicio.');
});

test('B5: % fijo exige porcentaje mayor que 0; sin inquilino principal no se puede repercutir', async () => {
  montar(conElena());
  await pasoQue();
  await pasoFechas(true);
  await waitFor(() => screen.getByTestId('contrato-persona-PROPIETARIO-yo'));
  await anadirInquilino();
  await pulsar('contrato-continuar');
  await pulsar('contrato-clausula-NINGUNA');
  await pulsar('contrato-continuar');
  await waitFor(() => screen.getByTestId('contrato-servicio-s-luz-abrir'));
  await pulsar('contrato-servicio-s-luz-abrir');
  await pulsar('contrato-servicio-s-luz-REPERCUTIDO_FIJO');
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(true);
  await escribir('contrato-servicio-s-luz-porcentaje', '0');
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(true);
  await escribir('contrato-servicio-s-luz-porcentaje', '50');
  expect(screen.getByTestId('contrato-continuar').props.accessibilityState.disabled).toBe(false);
  expect(screen.getByTestId('contrato-servicio-s-luz-abrir').props.children).toBeTruthy();
  expect(screen.getByTestId('contrato-servicios-ayuda').props.children).toBe('Cómo se trata cada servicio en este contrato. No crea cobros: solo lo deja anotado.');
});

test('cancelar en el primer paso cierra sin guardar; atrás vuelve un paso', async () => {
  const { onCerrar } = montar(conElena());
  await pasoQue();
  await pulsar('contrato-atras');
  expect(screen.getByTestId('contrato-paso-que')).toBeTruthy();
  await pulsar('contrato-cancelar');
  expect(onCerrar).toHaveBeenCalledWith(null);
});

test('B1b: el selector de propiedad lista solo las del patrimonio y cambia la propiedad', async () => {
  const contratos = conElena();
  montar(contratos, jest.fn(), { propiedad: null, propiedades: [vista({ id: 'pa', nombre: 'Casa Ejemplo', habitaciones: null }), vista({ id: 'pb', nombre: 'Piso Ejemplo' }), vista({ id: 'pc', nombre: 'Vendida', enabled: false })] });
  expect(screen.getByTestId('contrato-propiedad').props.accessibilityLabel).toBe('Propiedad: Elige la propiedad');
  await pulsar('contrato-propiedad');
  expect(screen.getByTestId('contrato-propiedad-ayuda').props.children).toBe('Solo propiedades en tu patrimonio. Las vendidas no aparecen.');
  expect(screen.queryByTestId('contrato-propiedad-pc')).toBeNull();
  await pulsar('contrato-propiedad-pb');
  expect(screen.getByTestId('contrato-propiedad').props.accessibilityLabel).toBe('Propiedad: Piso Ejemplo');
  await waitFor(() => expect(contratos.contratosDePropiedad).toHaveBeenCalledWith('pb'));
});

test('C1 · cambio de inquilino: empieza en Personas con los arrendadores del actual y guarda con POST …/sucesor (una operación)', async () => {
  const actual = detalle();
  const contratos = conElena({ sucesorContrato: jest.fn(async () => ok({ contrato_id: 'sucesor', row_version: 1, idempotente: false, contrato: detalle({ contrato_id: 'sucesor', nombre: '27-HAB1-ES' }) })) });
  const { onCerrar } = montar(contratos, jest.fn(), { sucesor: { actual, fechaFinReal: '2027-01-31', nuevoInicio: '2027-02-01', copiar: { clausula: true, servicios: true } } });
  expect(screen.getByTestId('contrato-paso-personas')).toBeTruthy();
  expect(screen.getByText('Cambio de inquilino')).toBeTruthy();
  expect(screen.getByTestId('contrato-persona-PROPIETARIO-yo')).toBeTruthy();
  expect(screen.getByTestId(`contrato-persona-PROPIETARIO-${T_LAURA}`)).toBeTruthy();
  await anadirInquilino();
  await pulsar('contrato-continuar');                    // B4 con la cláusula copiada: ya elegida
  expect(screen.getByTestId('contrato-clausula-IPC').props.accessibilityState.checked).toBe(true);
  await pulsar('contrato-continuar');
  await pulsar('contrato-continuar');                    // B5 con los servicios copiados
  await waitFor(() => screen.getByTestId('contrato-guardar'));
  await pulsar('contrato-guardar');
  await waitFor(() => screen.getByTestId('contrato-hecho'));
  expect(contratos.altaContrato).not.toHaveBeenCalled();
  const [id, cuerpo] = contratos.sucesorContrato.mock.calls[0];
  expect(id).toBe('c1');
  expect(cuerpo.row_version_esperada).toBe(3);
  expect(cuerpo.fecha_fin_real).toBe('2027-01-31');
  expect(cuerpo.nuevo).not.toHaveProperty('propiedad_id');
  expect(cuerpo.nuevo).not.toHaveProperty('tipo');
  expect(cuerpo.nuevo).not.toHaveProperty('habitacion');
  expect(cuerpo.nuevo).not.toHaveProperty('renta');
  expect(cuerpo.nuevo.fecha_inicio).toBe('2027-02-01');
  expect(cuerpo.nuevo.estado).toBe('FORMALIZADO');
  expect(cuerpo.nuevo.clausula_revision).toEqual({ tipo: 'IPC', indice_referencia: 'IPC INE', periodicidad_meses: 12, fecha_primera_revision: '2027-09-01' });
  await pulsar('contrato-listo');
  expect(onCerrar).toHaveBeenCalled();
});

test('un tercero de otro tipo de uso no cambia el literal «Tú no puedes ser inquilino»', () => {
  expect(TEXTO_INQUILINO_NO_YO).toBe('Tú no puedes ser inquilino de tu propio contrato.');
});
