// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos_lista.test.tsx
// Ruta: mobile/__tests__/contratos_lista.test.tsx
// Descripción: Lista, detalle y vida del contrato de F06-02/03 (lámina CON v0.8 A1, A2, A3, C1–C4; contrato N1 v1.1 L-CON-01/02, C-CON-02..05) contra dobles en memoria: A1 con el escenario O-1b validado (3 ocupadas · 1 próxima · 1 libre; HAB5 con el fin previsto vencido sigue ocupando y se marca «Termina o prorroga»; el borrador no ocupa; 2 finalizados; SIN importes), A3 sin contratos, A2 con la agencia como persona del contrato y «Renta y fianza · Se añadirán con la parte de cobros», C2 prórroga con motivo, C3 terminar (nada se borra), C3b terminación bloqueada con la explicación antes del botón desactivado (O-14: `terminable = false`, motivo RENTA_PENDIENTE_DE_F06_04; el servidor responde lo mismo), C4 borrador (firmar repite el solape: B2b y sigue en borrador; cancelar con motivo), C1 cambio de inquilino y el flujo completo con navegación mínima.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ContratoDetalleScreen, ContratosFlujo, ContratosListaScreen, siguienteDia } from '../src/screens/ContratosScreen';
import { ProveedorTema } from '../src/theme/tema';
import { AHORA, clienteApi, clienteContratos, detalle, indeterminado, METRICAS, nuevoId, ok, rechazo, reiniciarIds, vista } from './contratos_fixtures';

const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
beforeEach(() => reiniciarIds());
const envolver = (hijo: React.ReactNode, esquema: 'light' | 'dark' = 'light') => (
  <SafeAreaProvider initialMetrics={METRICAS}><ProveedorTema forzar={esquema}>{hijo}</ProveedorTema></SafeAreaProvider>
);

// ------------------------------------------------------------------ A1 / A3
describe('A1 · Contratos de una propiedad', () => {
  test('O-1b: 3 ocupadas · 1 próxima · 1 libre; HAB5 vencida «Termina o prorroga»; borrador aparte; 2 finalizados; sin importes', async () => {
    const contratos = clienteContratos();
    const onAbrir = jest.fn();
    render(envolver(<ContratosListaScreen contratos={contratos} propiedad={vista()} onAtras={jest.fn()} onNuevo={jest.fn()} onAbrir={onAbrir} />));
    await waitFor(() => screen.getByTestId('contratos-hoy-resumen'));
    expect(contratos.contratosDePropiedad).toHaveBeenCalledWith('p1');
    expect(screen.getByTestId('contratos-hoy-resumen').props.children).toBe('3 ocupadas · 1 próxima · 1 libre');
    expect(screen.getByTestId('contrato-fila-c1-detalle').props.children).toBe('Habitación 1 · Carlos Ruiz · desde 1 sep 2026');
    expect(screen.getByTestId('contrato-fila-c2-detalle').props.children).toBe('Habitación 2 · Ana Gil · hasta 31 ago 2027');
    expect(screen.getByTestId('contrato-fila-c5-detalle').props.children).toBe('Habitación 5 · Luis Mora · fin previsto 31 oct 2026');
    expect(screen.getByTestId('contrato-fila-c5-vencido').props.children).toBe('Termina o prorroga');
    expect(screen.queryByTestId('contrato-fila-c1-vencido')).toBeNull();
    expect(screen.getByTestId('contrato-fila-c3-detalle').props.children).toBe('Habitación 3 · Pablo Ros · empieza 1 dic');
    expect(screen.getByTestId('contrato-fila-c4-detalle').props.children).toBe('Habitación 4 · Elena Sanz · sin firmar');
    expect(screen.getByTestId('contratos-sin-importes').props.children).toBe('Sin importes: la renta todavía no existe en la app (llega con la parte de cobros).');
    // finalizados plegados: «Ver 2»
    expect(screen.queryByTestId('contrato-fila-f1')).toBeNull();
    expect(screen.getByTestId('contratos-finalizados-ver').props.accessibilityLabel ?? '').toBeDefined();
    await pulsar('contratos-finalizados-ver');
    expect(screen.getByTestId('contrato-fila-f1')).toBeTruthy();
    expect(screen.getByTestId('contrato-fila-f2')).toBeTruthy();
    await pulsar('contrato-fila-c1');
    expect(onAbrir).toHaveBeenCalledWith('c1');
    // ningún importe de renta en pantalla
    expect(screen.queryByText(/€/)).toBeNull();
  });

  test('un contrato migrado con renta se marca «Renta registrada · se gestiona en la parte de cobros», sin importes', async () => {
    const e = (await clienteContratos().contratosDePropiedad('p1'));
    if (e.tipo !== 'OK') throw new Error('x');
    const contratos = clienteContratos({ contratosDePropiedad: jest.fn(async () => ok({ ...e.datos, contratos: e.datos.contratos.map((c) => (c.contrato_id === 'c1' ? { ...c, renta_registrada: true } : c)) })) });
    render(envolver(<ContratosListaScreen contratos={contratos} propiedad={vista()} onAtras={jest.fn()} onNuevo={jest.fn()} onAbrir={jest.fn()} />));
    await waitFor(() => screen.getByTestId('contrato-fila-c1'));
    expect(screen.getByTestId('contrato-fila-c1-detalle').props.children).toMatch(/Renta registrada · se gestiona en la parte de cobros$/);
    expect(screen.queryByText(/€/)).toBeNull();
  });

  test('A3: sin contratos, con el texto de la lámina y «Nuevo contrato»', async () => {
    const contratos = clienteContratos({ contratosDePropiedad: jest.fn(async () => ok({ hoy: '2026-11-18', habitaciones_ficha: 5, ocupacion: [], contratos: [] })) });
    const onNuevo = jest.fn();
    render(envolver(<ContratosListaScreen contratos={contratos} propiedad={vista()} onAtras={jest.fn()} onNuevo={onNuevo} onAbrir={jest.fn()} />));
    await waitFor(() => screen.getByTestId('contratos-vacio'));
    expect(screen.getByText('Sin contratos')).toBeTruthy();
    expect(screen.getByText('Si alquilas esta propiedad o una parte (por habitaciones), crea aquí cada contrato.')).toBeTruthy();
    expect(screen.queryByTestId('contratos-hoy')).toBeNull();
    await pulsar('contratos-nuevo');
    expect(onNuevo).toHaveBeenCalled();
  });

  test('un fallo de carga se ofrece reintentar, sin inventar una lista vacía', async () => {
    const contratos = clienteContratos();
    contratos.contratosDePropiedad.mockResolvedValueOnce(indeterminado());
    render(envolver(<ContratosListaScreen contratos={contratos} propiedad={vista()} onAtras={jest.fn()} onNuevo={jest.fn()} onAbrir={jest.fn()} />));
    await waitFor(() => screen.getByTestId('contratos-error'));
    expect(screen.queryByTestId('contratos-vacio')).toBeNull();
    await pulsar('contratos-error');
    await waitFor(() => screen.getByTestId('contratos-hoy-resumen'));
  });
});

// ------------------------------------------------------------------ A2
function montarDetalle(contratos = clienteContratos(), extra: Partial<React.ComponentProps<typeof ContratoDetalleScreen>> = {}, esquema: 'light' | 'dark' = 'light') {
  const props = { onAtras: jest.fn(), onCambios: jest.fn(), onTercero: jest.fn(), onSucesor: jest.fn(), onTratamientos: jest.fn(), ...extra };
  render(envolver(<ContratoDetalleScreen contratos={contratos} contratoId="c1" nuevoId={nuevoId} ahora={AHORA} {...props} />, esquema));
  return { contratos, ...props };
}

describe('A2 · detalle del contrato', () => {
  test('personas con la agencia, condiciones, servicios y «Renta y fianza · Se añadirán con la parte de cobros»', async () => {
    const { onTercero } = montarDetalle();
    await waitFor(() => screen.getByTestId('contrato-unidad'));
    expect(screen.getByTestId('contrato-unidad').props.children).toBe('Habitación 1 · Piso Ejemplo');
    expect(screen.getByTestId('contrato-situacion').props.children).toBe('Firmado · vigente');
    expect(screen.getByTestId('contrato-fechas-valor').props.children).toBe('1 sep 2026 al 31 ago 2027');
    expect(screen.getByTestId('contrato-persona-pp5-detalle').props.children).toBe('Agencia');
    expect(screen.getByTestId('contrato-persona-pp3-detalle').props.children).toBe('Inquilino · principal');
    expect(screen.getByTestId('contrato-persona-pp1-titulo').props.children).toBe('Tú');
    expect(screen.getByTestId('contrato-persona-pp2-detalle').props.children).toBe('Arrendador');
    expect(screen.getByTestId('contrato-persona-pp4-detalle').props.children).toBe('Avalista');
    expect(screen.getByTestId('contrato-clausula-valor').props.children).toBe('Revisión anual por IPC');
    expect(screen.getByTestId('contrato-clausula-primera-valor').props.children).toBe('1 sep 2027');
    expect(screen.getByTestId('contrato-servicios-detalle').props.children).toBe('Internet incluido · luz: reparto en cada factura');
    expect(screen.getByTestId('contrato-renta-fianza-valor').props.children).toBe('Se añadirán con la parte de cobros');
    expect(screen.getByTestId('contrato-renta-fianza').props.children[0].props.children).toBe('Renta y fianza');
    expect(screen.queryByText(/€/)).toBeNull();
    await pulsar('contrato-persona-pp3');
    expect(onTercero).toHaveBeenCalledWith('t0000000-0000-4000-8000-000000000003');
  });

  test('funciona también en modo oscuro', async () => {
    montarDetalle(clienteContratos(), {}, 'dark');
    await waitFor(() => screen.getByTestId('contrato-situacion'));
  });

  test('un contrato vigente con el fin previsto vencido lo dice', async () => {
    montarDetalle(clienteContratos({ contrato: jest.fn(async () => ok({ contrato: detalle({ fin_previsto_vencido: true, fecha_fin_prevista: '2026-10-31' }) })) }));
    await waitFor(() => screen.getByTestId('contrato-fin-vencido'));
    expect(screen.getByTestId('contrato-fin-vencido').props.children).toBe('Fin previsto vencido · termina o prorroga');
  });
});

// ------------------------------------------------------------------ C2 prórroga
describe('C2 · prórroga', () => {
  test('exige fecha y motivo; guarda con el motivo y la versión esperada; replay con la misma intención', async () => {
    const { contratos, onCambios } = montarDetalle();
    await waitFor(() => screen.getByTestId('contrato-prorrogar-abrir'));
    await pulsar('contrato-prorrogar-abrir');
    expect(screen.getByTestId('contrato-prorrogar-actual-valor').props.children).toBe('31 ago 2027');
    expect(screen.getByTestId('contrato-prorrogar-guardar').props.accessibilityState.disabled).toBe(true);
    await escribir('contrato-prorrogar-fin', '31/08/2028');
    expect(screen.getByTestId('contrato-prorrogar-guardar').props.accessibilityState.disabled).toBe(true);   // falta el motivo
    await escribir('contrato-prorrogar-motivo', 'Prórroga anual');
    await pulsar('contrato-prorrogar-guardar');
    await waitFor(() => expect(contratos.editarContrato).toHaveBeenCalled());
    expect(contratos.editarContrato).toHaveBeenCalledWith('c1', { intencion_id: expect.any(String), row_version_esperada: 3, fecha_fin_prevista: '2028-08-31', motivo: 'Prórroga anual' });
    expect(onCambios).toHaveBeenCalled();
    await waitFor(() => screen.getByTestId('contrato-detalle'));
  });

  test('un fin anterior al inicio no se envía', async () => {
    const { contratos } = montarDetalle();
    await waitFor(() => screen.getByTestId('contrato-prorrogar-abrir'));
    await pulsar('contrato-prorrogar-abrir');
    await escribir('contrato-prorrogar-fin', '31/08/2026');
    await escribir('contrato-prorrogar-motivo', 'x');
    expect(screen.getByTestId('contrato-prorrogar-guardar').props.accessibilityState.disabled).toBe(true);
    expect(contratos.editarContrato).not.toHaveBeenCalled();
  });
});

// ------------------------------------------------------------------ C3 / C3b
describe('C3 · terminar', () => {
  test('último día real; personas y servicios terminan ese día; la habitación queda libre al día siguiente; nada se borra', async () => {
    const { contratos } = montarDetalle();
    await waitFor(() => screen.getByTestId('contrato-terminar-abrir'));
    await pulsar('contrato-terminar-abrir');
    expect(screen.getByTestId('contrato-terminar-personas-valor').props.children).toBe('Su vigencia acaba ese día');
    expect(screen.getByTestId('contrato-terminar-servicios-valor').props.children).toBe('Terminan ese día');
    expect(screen.getByTestId('contrato-terminar-ayuda').props.children).toBe('No se borra nada: lo registrado se conserva.');
    expect(screen.getByTestId('contrato-terminar-confirmar').props.accessibilityState.disabled).toBe(true);
    await escribir('contrato-terminar-dia', '31/01/2027');
    expect(screen.getByTestId('contrato-terminar-habitacion-valor').props.children).toBe('Libre desde el 1 feb 2027');
    await pulsar('contrato-terminar-confirmar');
    await waitFor(() => expect(contratos.terminarContrato).toHaveBeenCalledWith('c1', { intencion_id: expect.any(String), row_version_esperada: 3, fecha_fin_real: '2027-01-31' }));
  });

  test('FECHA_FIN_ANTERIOR_A_VIGENCIA del servidor se muestra con su texto y deja la pantalla abierta', async () => {
    const contratos = clienteContratos({ terminarContrato: jest.fn(async () => rechazo('FECHA_FIN_ANTERIOR_A_VIGENCIA', 'x')) });
    montarDetalle(contratos);
    await waitFor(() => screen.getByTestId('contrato-terminar-abrir'));
    await pulsar('contrato-terminar-abrir');
    await escribir('contrato-terminar-dia', '31/01/2027');
    await pulsar('contrato-terminar-confirmar');
    await waitFor(() => screen.getByTestId('contrato-tarea-aviso'));
    expect(screen.getByTestId('contrato-tarea-aviso').props.children.props.children).toBe('El fin es anterior al inicio de alguna persona, servicio o cláusula vigente del contrato.');
    expect(screen.getByTestId('contrato-terminar')).toBeTruthy();
  });

  test('siguienteDia pasa de mes y de año', () => {
    expect(siguienteDia('2027-01-31')).toBe('2027-02-01');
    expect(siguienteDia('2026-12-31')).toBe('2027-01-01');
    expect(siguienteDia('2028-02-28')).toBe('2028-02-29');
  });
});

describe('C3b · terminación bloqueada (contrato de V3 con renta)', () => {
  const conRenta = () => clienteContratos({
    contrato: jest.fn(async () => ok({ contrato: detalle({ nombre: '21-VIV-JM', tipo: 'VIVIENDA_COMPLETA', habitacion: null, renta_registrada: true, fecha_fin_prevista: null, terminable: { terminable: false, motivo: 'RENTA_PENDIENTE_DE_F06_04' } }) })),
  });

  test('la explicación va antes del botón, el botón sale desactivado y se puede prorrogar, en claro y en oscuro (O-14)', async () => {
    for (const esquema of ['light', 'dark'] as const) {
      const contratos = conRenta();
      const { unmount } = render(envolver(<ContratoDetalleScreen contratos={contratos} contratoId="c1" nuevoId={nuevoId} ahora={AHORA} onAtras={jest.fn()} />, esquema));
      await waitFor(() => screen.getByTestId('contrato-terminacion-bloqueada'));
      expect(screen.getByTestId('contrato-terminacion-bloqueada-titulo').props.children).toBe('No se puede terminar todavía.');
      expect(screen.getByTestId('contrato-terminacion-bloqueada-texto').props.children)
        .toBe('Este contrato tiene una renta registrada (viene de la versión anterior de la app). Para terminarlo hay que cerrar también su renta, y eso llegará con la parte de cobros.');
      expect(screen.getByTestId('contrato-terminar-bloqueado').props.accessibilityState.disabled).toBe(true);
      expect(screen.getByTestId('contrato-mientras-tanto').props.children).toBe('Mientras tanto puedes prorrogarlo, cambiar personas y servicios.');
      expect(screen.getByTestId('contrato-prorrogar-abrir')).toBeTruthy();
      expect(screen.queryByTestId('contrato-terminar-abrir')).toBeNull();
      expect(screen.getByTestId('contrato-renta-registrada').props.children).toBe('Renta registrada · se gestiona en la parte de cobros');
      expect(contratos.terminarContrato).not.toHaveBeenCalled();
      unmount();
    }
  });

  test('si el servidor responde RENTA_PENDIENTE_DE_F06_04 (estado desfasado) muestra el mismo texto', async () => {
    const contratos = clienteContratos({ terminarContrato: jest.fn(async () => rechazo('OPERACION_NO_PERMITIDA_EN_ESTADO', 'x', { motivo: 'RENTA_PENDIENTE_DE_F06_04' })) });
    montarDetalle(contratos);
    await waitFor(() => screen.getByTestId('contrato-terminar-abrir'));
    await pulsar('contrato-terminar-abrir');
    await escribir('contrato-terminar-dia', '31/01/2027');
    await pulsar('contrato-terminar-confirmar');
    await waitFor(() => screen.getByTestId('contrato-tarea-aviso'));
    expect(screen.getByTestId('contrato-tarea-aviso').props.children.props.children)
      .toBe('Este contrato tiene una renta registrada. Para terminarlo hay que cerrar también su renta, y eso llegará con la parte de cobros. De momento no se puede terminar.');
  });
});

// ------------------------------------------------------------------ C4 borrador
describe('C4 · borrador', () => {
  const borrador = () => clienteContratos({
    contrato: jest.fn(async () => ok({ contrato: detalle({ nombre: '26-HAB4-ES', estado_documental: 'BORRADOR', situacion: 'BORRADOR', habitacion: 4, fecha_inicio: '2026-11-01', fecha_fin_prevista: null }) })),
  });

  test('«Un borrador se completa o se cancela; no se borra»; firmar llama a formalizar con la versión esperada', async () => {
    const contratos = borrador();
    montarDetalle(contratos);
    await waitFor(() => screen.getByTestId('contrato-borrador'));
    expect(screen.getByTestId('contrato-borrador-ayuda').props.children)
      .toBe('Un borrador se completa o se cancela; no se borra. No ocupa la habitación. Solo se puede firmar si en esas fechas no hay otro contrato firmado.');
    expect(screen.getByTestId('contrato-situacion').props.children).toBe('Borrador');
    expect(screen.queryByTestId('contrato-terminar-abrir')).toBeNull();
    await pulsar('contrato-firmar');
    await waitFor(() => expect(contratos.formalizarContrato).toHaveBeenCalledWith('c1', { intencion_id: expect.any(String), row_version_esperada: 3 }));
  });

  test('firmar con solape: B2b con la lista del servidor y sigue siendo borrador', async () => {
    const contratos = borrador();
    contratos.formalizarContrato.mockResolvedValueOnce(rechazo('SOLAPE_CON_CONTRATO_FIRMADO', 'x', { solapados: [{ id: 'z', nombre: '26-VIV-JM', tipo: 'VIVIENDA_COMPLETA', habitacion: null, desde: '2026-09-01', hasta: null }] }));
    montarDetalle(contratos);
    await waitFor(() => screen.getByTestId('contrato-firmar'));
    await pulsar('contrato-firmar');
    await waitFor(() => screen.getByTestId('contrato-detalle-solape'));
    expect(screen.getByText('Ya está alquilada en esas fechas')).toBeTruthy();
    expect(screen.getByTestId('contrato-detalle-solape-fila-0').props.children).toBe('26-VIV-JM · Vivienda completa · 1 sep 2026 → sin fin real');
    expect(screen.getByTestId('contrato-situacion').props.children).toBe('Borrador');
    expect(screen.getByTestId('contrato-firmar')).toBeTruthy();
  });

  test('FALTAN_PARTES_PARA_FORMALIZAR se explica con su texto', async () => {
    const contratos = borrador();
    contratos.formalizarContrato.mockResolvedValueOnce(rechazo('FALTAN_PARTES_PARA_FORMALIZAR', 'x'));
    montarDetalle(contratos);
    await waitFor(() => screen.getByTestId('contrato-firmar'));
    await pulsar('contrato-firmar');
    await waitFor(() => screen.getByTestId('contrato-detalle-aviso'));
    expect(screen.getByTestId('contrato-detalle-aviso').props.children.props.children).toMatch(/hacen falta un arrendador \(o gestor\) y un inquilino principal/);
  });

  test('cancelar exige motivo y no borra: llama a cancelar', async () => {
    const contratos = borrador();
    montarDetalle(contratos);
    await waitFor(() => screen.getByTestId('contrato-cancelar-borrador-abrir'));
    await pulsar('contrato-cancelar-borrador-abrir');
    expect(screen.getByTestId('contrato-cancelar-confirmar').props.accessibilityState.disabled).toBe(true);
    await escribir('contrato-cancelar-motivo', 'No se llegó a firmar');
    await pulsar('contrato-cancelar-confirmar');
    await waitFor(() => expect(contratos.cancelarContrato).toHaveBeenCalledWith('c1', { intencion_id: expect.any(String), row_version_esperada: 3, motivo: 'No se llegó a firmar' }));
  });
});

// ------------------------------------------------------------------ C1 sucesor (formulario)
describe('C1 · cambio de inquilino', () => {
  test('pide el último día del actual y la entrada del nuevo (posterior); la renta no se copia; continúa con el contrato nuevo', async () => {
    const { onSucesor } = montarDetalle();
    await waitFor(() => screen.getByTestId('contrato-sucesor-abrir'));
    await pulsar('contrato-sucesor-abrir');
    expect(screen.getByTestId('contrato-sucesor-inquilino-valor').props.children).toBe('Carlos Ruiz');
    expect(screen.getByText('Último día de Carlos Ruiz')).toBeTruthy();
    expect(screen.getByTestId('contrato-sucesor-continuar').props.accessibilityState.disabled).toBe(true);
    await escribir('contrato-sucesor-fin', '31/01/2027');
    await escribir('contrato-sucesor-inicio', '31/01/2027');
    expect(screen.getByTestId('contrato-sucesor-continuar').props.accessibilityState.disabled).toBe(true);    // empieza el mismo día del último
    await escribir('contrato-sucesor-inicio', '01/02/2027');
    expect(screen.getByTestId('contrato-sucesor-continuar').props.accessibilityState.disabled).toBe(false);
    expect(screen.getByTestId('contrato-sucesor-ayuda').props.children).toMatch(/La renta no se copia/);
    await pulsar('contrato-sucesor-copiar-clausula');
    await pulsar('contrato-sucesor-continuar');
    expect(onSucesor).toHaveBeenCalledWith(expect.objectContaining({ fechaFinReal: '2027-01-31', nuevoInicio: '2027-02-01', copiar: { clausula: true, servicios: false } }));
  });

  test('solo se ofrece en contratos de habitación y vigentes', async () => {
    montarDetalle(clienteContratos({ contrato: jest.fn(async () => ok({ contrato: detalle({ tipo: 'VIVIENDA_COMPLETA', habitacion: null }) })) }));
    await waitFor(() => screen.getByTestId('contrato-prorrogar-abrir'));
    expect(screen.queryByTestId('contrato-sucesor-abrir')).toBeNull();
  });
});

// ------------------------------------------------------------------ concurrencia de versión
test('VERSION_DESFASADA al guardar recarga el contrato y avisa', async () => {
  const contratos = clienteContratos({ terminarContrato: jest.fn(async () => rechazo('VERSION_DESFASADA', 'x')) });
  montarDetalle(contratos);
  await waitFor(() => screen.getByTestId('contrato-terminar-abrir'));
  await pulsar('contrato-terminar-abrir');
  await escribir('contrato-terminar-dia', '31/01/2027');
  await pulsar('contrato-terminar-confirmar');
  await waitFor(() => expect(contratos.contrato.mock.calls.length).toBeGreaterThanOrEqual(2));
  expect(screen.getByTestId('contrato-tarea-aviso').props.children.props.children).toMatch(/ha cambiado mientras lo editabas/);
});

// ------------------------------------------------------------------ flujo
test('flujo: lista → detalle → atrás → nuevo contrato → cancelar; y servicios desde la lista', async () => {
  const contratos = clienteContratos();
  const onSalir = jest.fn();
  render(envolver(<ContratosFlujo cliente={clienteApi()} contratos={contratos} propiedad={vista()} nuevoId={nuevoId} ahora={AHORA} onSalir={onSalir} />));
  await waitFor(() => screen.getByTestId('contrato-fila-c1'));
  await pulsar('contrato-fila-c1');
  await waitFor(() => screen.getByTestId('contrato-detalle'));
  await pulsar('contrato-detalle-atras');
  await waitFor(() => screen.getByTestId('contratos-lista'));
  await pulsar('contratos-nuevo');
  expect(screen.getByTestId('contrato-paso-que')).toBeTruthy();
  await pulsar('contrato-cancelar');
  await waitFor(() => screen.getByTestId('contratos-lista'));
  await pulsar('contratos-servicios');
  await waitFor(() => screen.getByTestId('servicios-lista'));
  await pulsar('servicios-atras');
  await pulsar('contratos-atras');
  expect(onSalir).toHaveBeenCalled();
});

test('flujo: de un contrato a la ficha de una persona y vuelta; y a los servicios del contrato', async () => {
  const contratos = clienteContratos();
  render(envolver(<ContratosFlujo cliente={clienteApi()} contratos={contratos} propiedad={vista()} nuevoId={nuevoId} ahora={AHORA} onSalir={jest.fn()} />));
  await waitFor(() => screen.getByTestId('contrato-fila-c1'));
  await pulsar('contrato-fila-c1');
  await waitFor(() => screen.getByTestId('contrato-persona-pp3'));
  await pulsar('contrato-persona-pp3');
  await waitFor(() => screen.getByTestId('tercero-ficha'));
  await pulsar('tercero-ficha-atras');
  await waitFor(() => screen.getByTestId('contrato-detalle'));
  await pulsar('contrato-servicios');
  await waitFor(() => screen.getByTestId('contrato-servicios-lista'));
  expect(screen.getByTestId('contrato-servicio-fila-s-luz-detalle').props.children).toBe('Reparto en cada factura · desde sep 2026');
  expect(screen.getByTestId('contrato-servicio-fila-s-agua-detalle').props.children).toBe('Sin indicar');
});
