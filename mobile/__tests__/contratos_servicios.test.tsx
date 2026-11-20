// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos_servicios.test.tsx
// Ruta: mobile/__tests__/contratos_servicios.test.tsx
// Descripción: Servicios de F06-02/03 (lámina CON v0.8 D1, D2, D3, D5; contrato N1 v1.1 C-SRV-01..04, L-SRV-01) contra dobles en memoria: D1 lista con anteriores; D2 alta SIN «Importe esperado» (llega con la parte de cobros) con categoría opcional; D3 tratamiento en el contrato (M-9: incluido, % fijo mayor que 0, reparto en cada factura sin %, la pagas tú, sin indicar; solo anota, no crea cobros; actor = inquilino principal); D5 vida del servicio sin «Cambiar de compañía» y baja con su texto propio si el servidor responde REGLA_SERVICIO_PENDIENTE_DE_F06_04 (O-31: nunca el texto de la renta del contrato).
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ContratoServiciosScreen, ServiciosFlujo } from '../src/screens/ServiciosScreens';
import { ProveedorTema } from '../src/theme/tema';
import { AHORA, clienteApi, clienteContratos, detalle, METRICAS, nuevoId, ok, rechazo, reiniciarIds, vista } from './contratos_fixtures';

const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
beforeEach(() => reiniciarIds());
const envolver = (h: React.ReactNode) => <SafeAreaProvider initialMetrics={METRICAS}><ProveedorTema forzar="light">{h}</ProveedorTema></SafeAreaProvider>;

function montarServicios(contratos = clienteContratos(), cliente = clienteApi()) {
  const onAtras = jest.fn();
  render(envolver(<ServiciosFlujo cliente={cliente} contratos={contratos} propiedad={vista()} nuevoId={nuevoId} ahora={AHORA} onAtras={onAtras} />));
  return { contratos, onAtras };
}

describe('D1 · servicios de la propiedad', () => {
  test('lista con familia y «desde mar 2027»; los anteriores plegados con «Ver 1»', async () => {
    montarServicios();
    await waitFor(() => screen.getByTestId('servicio-fila-s-luz'));
    expect(screen.getByTestId('servicio-fila-s-luz-detalle').props.children).toBe('Suministro · desde mar 2027');
    expect(screen.getByTestId('servicio-fila-s-int-detalle').props.children).toBe('Telecomunicaciones · desde mar 2027');
    expect(screen.queryByTestId('servicio-fila-s-gas')).toBeNull();
    await pulsar('servicios-anteriores-ver');
    expect(screen.getByTestId('servicio-fila-s-gas')).toBeTruthy();
  });

  test('sin servicios: texto claro, no una lista inventada', async () => {
    montarServicios(clienteContratos({ serviciosDePropiedad: jest.fn(async () => ok({ vigentes: [], anteriores: [] })) }));
    await waitFor(() => screen.getByTestId('servicios-vacio'));
  });
});

describe('D2 · alta de servicio', () => {
  test('sin «Importe esperado»; el nombre se propone con el tipo; guarda con propiedad y desde (C-SRV-01)', async () => {
    const { contratos } = montarServicios();
    await waitFor(() => screen.getByTestId('servicios-nuevo'));
    await pulsar('servicios-nuevo');
    expect(screen.queryByText(/Importe esperado/i)).toBeNull();
    expect(screen.queryByText(/importe/i)).toBeNull();
    expect(screen.getAllByTestId(/^servicio-tipo-/)).toHaveLength(8);
    for (const t of ['LUZ', 'AGUA', 'GAS', 'INTERNET', 'LIMPIEZA', 'COMUNIDAD', 'SEGURO', 'OTRO']) expect(screen.getByTestId(`servicio-tipo-${t}`).props.accessibilityState.checked).toBe(false);
    expect(screen.getByTestId('servicio-guardar').props.accessibilityState.disabled).toBe(true);
    await pulsar('servicio-tipo-LUZ');
    expect(screen.getByTestId('servicio-nombre').props.value).toBe('Luz');
    expect(screen.getByTestId('servicio-propiedad-valor').props.children).toBe('Piso Ejemplo');
    expect(screen.getByTestId('servicio-guardar').props.accessibilityState.disabled).toBe(true);      // falta «Desde»
    await escribir('servicio-desde', '01/03/2027');
    await pulsar('servicio-guardar');
    await waitFor(() => expect(contratos.altaServicio).toHaveBeenCalled());
    expect(contratos.altaServicio).toHaveBeenCalledWith({
      intencion_id: expect.any(String), tipo_servicio: 'LUZ', nombre: 'Luz', categoria_default_id: null, propiedad_id: 'p1', desde: '2027-03-01',
    });
    await waitFor(() => screen.getByTestId('servicios-lista'));
    expect(contratos.serviciosDePropiedad).toHaveBeenCalledTimes(2);
  });

  test('la categoría es opcional y se elige entre las de gasto del owner', async () => {
    const cliente = clienteApi({
      arbolCategorias: jest.fn(async () => ok({ categorias: [
        { id: 'k1', parent_id: null, nombre: 'Suministros', codigo: null, ambito: 'GASTO', enabled: true, orden: 1, icon_key: null, presupuestable_default: false, row_version: 1, magnitudes: [], capturable: true, motivo_no_capturable: null },
      ] })),
    });
    const { contratos } = montarServicios(clienteContratos(), cliente);
    await waitFor(() => screen.getByTestId('servicios-nuevo'));
    await pulsar('servicios-nuevo');
    await pulsar('servicio-tipo-AGUA');
    await escribir('servicio-desde', '01/03/2027');
    await pulsar('servicio-categoria');
    await waitFor(() => screen.getByTestId('servicio-categorias'));
    expect(screen.getByTestId('servicio-categoria-ninguna')).toBeTruthy();
    await waitFor(() => screen.getByTestId('servicio-categoria-k1'));
    await pulsar('servicio-categoria-k1');
    await pulsar('servicio-guardar');
    await waitFor(() => expect(contratos.altaServicio).toHaveBeenCalled());
    expect(contratos.altaServicio.mock.calls[0][0].categoria_default_id).toBe('k1');
  });

  test('un rechazo se muestra con su texto y la intención del reintento cambia', async () => {
    const contratos = clienteContratos({ altaServicio: jest.fn(async () => rechazo('SERVICIO_YA_VINCULADO', 'x')) });
    montarServicios(contratos);
    await waitFor(() => screen.getByTestId('servicios-nuevo'));
    await pulsar('servicios-nuevo');
    await pulsar('servicio-tipo-GAS');
    await escribir('servicio-desde', '01/03/2027');
    await pulsar('servicio-guardar');
    await waitFor(() => screen.getByTestId('servicio-aviso'));
    expect(screen.getByTestId('servicio-aviso').props.children.props.children).toBe('Ese servicio ya está vinculado a la propiedad en esas fechas.');
    await pulsar('servicio-guardar');
    await waitFor(() => expect(contratos.altaServicio).toHaveBeenCalledTimes(2));
    expect(contratos.altaServicio.mock.calls[1][0].intencion_id).not.toBe(contratos.altaServicio.mock.calls[0][0].intencion_id);
  });
});

describe('D5 · vida del servicio', () => {
  test('sin «Cambiar de compañía»: solo la explicación; la compañía sale de los últimos pagos', async () => {
    montarServicios();
    await waitFor(() => screen.getByTestId('servicio-fila-s-luz'));
    await pulsar('servicio-fila-s-luz');
    expect(screen.queryByText(/Cambiar de compañía/i)).toBeNull();
    expect(screen.getByTestId('servicio-detalle-compania-valor').props.children).toBe('Eléctrica Sur');
    expect(screen.getByTestId('servicio-compania-ayuda').props.children)
      .toBe('Si cambias de compañía no hace falta tocar nada aquí: cada pago lleva su compañía. Dar de baja pone fecha de fin y no borra pagos.');
  });

  test('dar de baja pone fecha de fin (C-SRV-03) con la versión esperada', async () => {
    const { contratos } = montarServicios();
    await waitFor(() => screen.getByTestId('servicio-fila-s-luz'));
    await pulsar('servicio-fila-s-luz');
    await pulsar('servicio-baja-abrir');
    expect(screen.getByTestId('servicio-baja-confirmar').props.accessibilityState.disabled).toBe(true);
    await escribir('servicio-baja-fin', '31/12/2027');
    await pulsar('servicio-baja-confirmar');
    await waitFor(() => expect(contratos.bajaServicio).toHaveBeenCalledWith('s-luz', { intencion_id: expect.any(String), row_version_esperada: 1, fecha_fin_real: '2027-12-31' }));
  });

  test('O-31: con regla financiera el servidor responde el motivo propio del servicio, nunca el de la renta del contrato', async () => {
    const contratos = clienteContratos({ bajaServicio: jest.fn(async () => rechazo('OPERACION_NO_PERMITIDA_EN_ESTADO', 'x', { motivo: 'REGLA_SERVICIO_PENDIENTE_DE_F06_04' })) });
    montarServicios(contratos);
    await waitFor(() => screen.getByTestId('servicio-fila-s-luz'));
    await pulsar('servicio-fila-s-luz');
    await pulsar('servicio-baja-abrir');
    await escribir('servicio-baja-fin', '31/12/2027');
    await pulsar('servicio-baja-confirmar');
    await waitFor(() => screen.getByTestId('servicio-aviso'));
    const t = screen.getByTestId('servicio-aviso').props.children.props.children;
    expect(t).toBe('Este servicio tiene un pago previsto registrado. Para darlo de baja hay que cerrar ese pago previsto, y eso llegará con la parte de cobros.');
    expect(t).not.toMatch(/renta/i);
  });

  test('un servicio ya dado de baja no ofrece la baja otra vez', async () => {
    montarServicios();
    await waitFor(() => screen.getByTestId('servicios-anteriores-ver'));
    await pulsar('servicios-anteriores-ver');
    await pulsar('servicio-fila-s-gas');
    expect(screen.getByTestId('servicio-detalle-hasta-valor').props.children).toBe('31 ene 2026');
    expect(screen.queryByTestId('servicio-baja-abrir')).toBeNull();
  });
});

describe('D3 · tratamiento en el contrato (M-9)', () => {
  function montarTrat(contratos = clienteContratos()) {
    const onCambios = jest.fn();
    render(envolver(<ContratoServiciosScreen contratos={contratos} contrato={detalle()} nuevoId={nuevoId} ahora={AHORA} onAtras={jest.fn()} onCambios={onCambios} />));
    return { contratos, onCambios };
  }

  test('las cuatro opciones de la lámina más «Sin indicar»; ninguna viene marcada; solo anota, no crea cobros', async () => {
    montarTrat();
    await waitFor(() => screen.getByTestId('contrato-servicio-fila-s-agua'));
    expect(screen.getByTestId('contrato-servicio-fila-s-luz-detalle').props.children).toBe('Reparto en cada factura · desde sep 2026');
    expect(screen.getByTestId('contrato-servicios-no-cobros').props.children).toBe('Cómo se trata cada servicio en este contrato. No crea cobros: solo lo deja anotado.');
    await pulsar('contrato-servicio-fila-s-agua');
    expect(screen.getByText('¿Cómo se trata en este contrato?')).toBeTruthy();
    for (const m of ['INCLUIDO', 'REPERCUTIDO_FIJO', 'POR_FACTURA', 'NO_REPERCUTIDO', 'SIN_INDICAR']) expect(screen.getByTestId(`tratamiento-${m}`).props.accessibilityState.checked).toBe(false);
    expect(screen.getByTestId('tratamiento-INCLUIDO').props.accessibilityLabel).toBe('Incluida en la renta. No se cobra aparte');
    expect(screen.getByTestId('tratamiento-REPERCUTIDO_FIJO').props.accessibilityLabel).toBe('Repercutida con un % fijo. Siempre el mismo porcentaje');
    expect(screen.getByTestId('tratamiento-POR_FACTURA').props.accessibilityLabel).toBe('Se reparte en cada factura. El % se decide en cada gasto');
    expect(screen.getByTestId('tratamiento-NO_REPERCUTIDO').props.accessibilityLabel).toBe('La pagas tú. Sin repercutir');
    expect(screen.getByTestId('tratamiento-ayuda').props.children).toMatch(/mayor que 0/);
    expect(screen.getByTestId('tratamiento-guardar').props.accessibilityState.disabled).toBe(true);
  });

  test('FIJO: % mayor que 0 con el inquilino principal como actor; POR_FACTURA: inquilino y sin %', async () => {
    const { contratos, onCambios } = montarTrat();
    await waitFor(() => screen.getByTestId('contrato-servicio-fila-s-agua'));
    await pulsar('contrato-servicio-fila-s-agua');
    await pulsar('tratamiento-REPERCUTIDO_FIJO');
    await escribir('tratamiento-desde', '01/11/2026');
    expect(screen.getByTestId('tratamiento-guardar').props.accessibilityState.disabled).toBe(true);
    await escribir('tratamiento-porcentaje', '0');
    expect(screen.getByTestId('tratamiento-guardar').props.accessibilityState.disabled).toBe(true);
    await escribir('tratamiento-porcentaje', '50');
    expect(screen.getByTestId('tratamiento-inquilino-valor').props.children).toBe('Carlos Ruiz');
    await pulsar('tratamiento-guardar');
    await waitFor(() => expect(contratos.tratamientoServicio).toHaveBeenCalled());
    expect(contratos.tratamientoServicio).toHaveBeenCalledWith('c1', 's-agua', {
      intencion_id: expect.any(String), row_version_esperada: 3,
      tratamiento: { servicio_id: 's-agua', modo: 'REPERCUTIDO_FIJO', desde: '2026-11-01', actor: { tercero_id: 't0000000-0000-4000-8000-000000000003' }, porcentaje: '50' },
    });
    expect(onCambios).toHaveBeenCalled();
    await waitFor(() => screen.getByTestId('contrato-servicios-lista'));
    // POR_FACTURA
    await pulsar('contrato-servicio-fila-s-int');
    await pulsar('tratamiento-POR_FACTURA');
    await escribir('tratamiento-desde', '01/12/2026');
    await pulsar('tratamiento-guardar');
    await waitFor(() => expect(contratos.tratamientoServicio).toHaveBeenCalledTimes(2));
    const t = contratos.tratamientoServicio.mock.calls[1][2].tratamiento;
    expect(t).toEqual({ servicio_id: 's-int', modo: 'POR_FACTURA', desde: '2026-12-01', actor: { tercero_id: 't0000000-0000-4000-8000-000000000003' } });
    expect(t).not.toHaveProperty('porcentaje');
  });

  test('«La pagas tú» e «Incluida» no llevan actor ni %; «Sin indicar» cierra sin borrar', async () => {
    const { contratos } = montarTrat();
    await waitFor(() => screen.getByTestId('contrato-servicio-fila-s-agua'));
    await pulsar('contrato-servicio-fila-s-agua');
    await pulsar('tratamiento-NO_REPERCUTIDO');
    await escribir('tratamiento-desde', '01/11/2026');
    await pulsar('tratamiento-guardar');
    await waitFor(() => expect(contratos.tratamientoServicio).toHaveBeenCalledTimes(1));
    expect(contratos.tratamientoServicio.mock.calls[0][2].tratamiento).toEqual({ servicio_id: 's-agua', modo: 'NO_REPERCUTIDO', desde: '2026-11-01' });
    await waitFor(() => screen.getByTestId('contrato-servicio-fila-s-luz'));
    await pulsar('contrato-servicio-fila-s-luz');
    await pulsar('tratamiento-SIN_INDICAR');
    await escribir('tratamiento-desde', '01/12/2026');
    await pulsar('tratamiento-guardar');
    await waitFor(() => expect(contratos.tratamientoServicio).toHaveBeenCalledTimes(2));
    expect(contratos.tratamientoServicio.mock.calls[1][2].tratamiento).toEqual({ servicio_id: 's-luz', modo: 'SIN_INDICAR', desde: '2026-12-01' });
  });

  test('errores del servidor con su texto (DESDE_IGUAL_A_VERSION_ABIERTA, ACTOR_NO_ES_INQUILINO)', async () => {
    const contratos = clienteContratos({ tratamientoServicio: jest.fn(async () => rechazo('DESDE_IGUAL_A_VERSION_ABIERTA', 'x')) });
    montarTrat(contratos);
    await waitFor(() => screen.getByTestId('contrato-servicio-fila-s-luz'));
    await pulsar('contrato-servicio-fila-s-luz');
    await pulsar('tratamiento-INCLUIDO');
    await escribir('tratamiento-desde', '01/09/2026');
    await pulsar('tratamiento-guardar');
    await waitFor(() => screen.getByTestId('tratamiento-aviso'));
    expect(screen.getByTestId('tratamiento-aviso').props.children.props.children).toBe('Esa fecha es la misma de la versión vigente: eso es una corrección, no un cambio nuevo.');
  });
});
