// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos_terceros.test.tsx
// Ruta: mobile/__tests__/contratos_terceros.test.tsx
// Descripción: Terceros de F06-02/03 (lámina CON v0.8 E1, E2, E6, B3c y B3d; contrato N1 v1.1 L-TER-01, C-TER-01, C-TER-03, V-bis y V-ter; Q-CON-13 «añadir y editar, no retirar») contra dobles en memoria: E1 ficha con roles fijos (sin «Quitar»), «Uso en Gapto» y sin direcciones; E2 añadir roles (los que tiene, bloqueados; catálogo completo visible; aviso «un rol añadido no se puede quitar»; nada marcado; RETIRADA_NO_ADMITIDA y ROL_DESCONOCIDO con texto); E6 clasificación sin desasignar; V-bis selector con homónimos por naturaleza y uso en Gapto (solo activos; filas idénticas → ficha «Es esta persona»; nada elegido; aislado por lo que devuelve el servidor); V-ter reutiliza el `SelectorTercero` y su hoja de duplicados de F05 tal cual (Usar / Reactivar / Crear otro) sin crear otra.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { SelectorParticipante } from '../src/components/SelectorParticipante';
import { TerceroFichaScreen } from '../src/screens/TerceroFichaScreen';
import { ProveedorTema } from '../src/theme/tema';
import { clienteApi, clienteContratos, ficha, METRICAS, nuevoId, ok, rechazo, reiniciarIds, T_CARLOS, T_CARLOS2, tercero, terceroUso } from './contratos_fixtures';

const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
beforeEach(() => reiniciarIds());
const envolver = (h: React.ReactNode, esquema: 'light' | 'dark' = 'light') => <SafeAreaProvider initialMetrics={METRICAS}><ProveedorTema forzar={esquema}>{h}</ProveedorTema></SafeAreaProvider>;

// ------------------------------------------------------------------ E1 / E2 / E6
describe('ficha de tercero (E1, E2, E6)', () => {
  function montar(contratos = clienteContratos(), esquema: 'light' | 'dark' = 'light') {
    const onContrato = jest.fn();
    const onAtras = jest.fn();
    render(envolver(<TerceroFichaScreen contratos={contratos} terceroId={T_CARLOS} nuevoId={nuevoId} onAtras={onAtras} onContrato={onContrato} />, esquema));
    return { contratos, onContrato, onAtras };
  }

  test('E1: naturaleza, roles fijos sin «Quitar», uso en Gapto con contrato y vigencia, sin direcciones', async () => {
    const { contratos, onContrato } = montar();
    await waitFor(() => screen.getByTestId('tercero-naturaleza'));
    expect(contratos.fichaTercero).toHaveBeenCalledWith(T_CARLOS);
    expect(screen.getByTestId('tercero-naturaleza-valor').props.children).toBe('Persona');
    expect(screen.getByTestId('tercero-rol-fijo-INQUILINO')).toBeTruthy();
    expect(screen.queryByText(/^(Quitar|Eliminar|Borrar)$/i)).toBeNull();
    expect(screen.queryByText(/Direcci/i)).toBeNull();
    expect(screen.getByTestId('tercero-roles-fijos').props.children).toBe('Los roles se pueden añadir, no quitar.');
    expect(screen.getByTestId('tercero-uso-c1-titulo').props.children).toBe('Contrato 26-HAB1-CR');
    expect(screen.getByTestId('tercero-uso-c1-detalle').props.children).toBe('Inquilino · desde 1 sep 2026');
    expect(screen.queryByText(/€/)).toBeNull();                                  // navega, no suma importes
    await pulsar('tercero-uso-c1');
    expect(onContrato).toHaveBeenCalledWith('c1');
  });

  test('E1 en oscuro y sin uso: «Sin uso»', async () => {
    montar(clienteContratos({ fichaTercero: jest.fn(async () => ok(ficha({ uso: [], roles: [] }))) }), 'dark');
    await waitFor(() => screen.getByTestId('tercero-sin-uso'));
    expect(screen.getByTestId('tercero-sin-roles')).toBeTruthy();
  });

  test('E2: los roles que tiene salen bloqueados, el resto visibles, nada marcado y el aviso de que no se quita', async () => {
    montar();
    await waitFor(() => screen.getByTestId('tercero-roles-abrir'));
    await pulsar('tercero-roles-abrir');
    expect(screen.getByTestId('tercero-rol-tiene-INQUILINO')).toBeTruthy();
    expect(screen.queryByTestId('tercero-rol-INQUILINO')).toBeNull();            // ya lo tiene: no se puede desmarcar
    for (const r of ['AVALISTA', 'GESTOR', 'COMERCIO', 'SUMINISTRADOR', 'ASEGURADORA', 'EMPLEADOR', 'ENTIDAD_FINANCIERA', 'FINANCIADOR', 'OBLIGADO_REEMBOLSO']) {
      expect(screen.getByTestId(`tercero-rol-${r}`).props.accessibilityState.checked).toBe(false);
    }
    expect(screen.queryByTestId('tercero-rol-AGENCIA')).toBeNull();               // agencia y administrador no son roles de tercero
    expect(screen.queryByTestId('tercero-rol-ADMINISTRADOR')).toBeNull();
    expect(screen.getByTestId('tercero-roles-aviso').props.children).toBe('Revisa antes de guardar. En esta versión un rol añadido no se puede quitar.');
    expect(screen.getByTestId('tercero-roles-guardar').props.accessibilityState.disabled).toBe(true);
  });

  test('E2: «Añadir 1 rol» envía solo lo que se añade, con la versión del tercero; la ficha se relee', async () => {
    const { contratos } = montar();
    await waitFor(() => screen.getByTestId('tercero-roles-abrir'));
    await pulsar('tercero-roles-abrir');
    await pulsar('tercero-rol-AVALISTA');
    expect(screen.getByText('Añadir 1 rol')).toBeTruthy();
    await pulsar('tercero-roles-guardar');
    await waitFor(() => expect(contratos.anadirRoles).toHaveBeenCalledWith(T_CARLOS, { intencion_id: expect.any(String), row_version_esperada: 4, anadir: ['AVALISTA'] }));
    await waitFor(() => screen.getByTestId('tercero-ficha'));
    expect(contratos.fichaTercero).toHaveBeenCalledTimes(2);
  });

  test('E2: ROL_DESCONOCIDO y RETIRADA_NO_ADMITIDA se explican; el siguiente intento usa intención nueva', async () => {
    const contratos = clienteContratos({ anadirRoles: jest.fn(async () => rechazo('RETIRADA_NO_ADMITIDA', 'x')) });
    montar(contratos);
    await waitFor(() => screen.getByTestId('tercero-roles-abrir'));
    await pulsar('tercero-roles-abrir');
    await pulsar('tercero-rol-GESTOR');
    await pulsar('tercero-rol-COMERCIO');
    expect(screen.getByText('Añadir 2 roles')).toBeTruthy();
    await pulsar('tercero-roles-guardar');
    await waitFor(() => screen.getByTestId('tercero-aviso'));
    expect(screen.getByTestId('tercero-aviso').props.children.props.children).toBe('En esta versión un rol o una clasificación añadidos no se pueden quitar.');
    await pulsar('tercero-roles-guardar');
    await waitFor(() => expect(contratos.anadirRoles).toHaveBeenCalledTimes(2));
    expect(contratos.anadirRoles.mock.calls[1][1].intencion_id).not.toBe(contratos.anadirRoles.mock.calls[0][1].intencion_id);
  });

  test('E6: la clasificación se añade, no se quita; el aviso lo dice; solo las activas y no asignadas; principal opcional', async () => {
    const contratos = clienteContratos({ fichaTercero: jest.fn(async () => ok(ficha({ clasificaciones: [{ clasificacion_id: 'k1', nombre: 'Familia de inquilinos', principal: true }] }))) });
    montar(contratos);
    await waitFor(() => screen.getByTestId('tercero-clasif-k1'));
    expect(screen.getByTestId('tercero-clasif-k1-valor').props.children).toBe('Principal');
    expect(screen.getByTestId('tercero-clasificacion-nota').props.children)
      .toBe('Tu forma de agruparlos. Una clasificación asignada no se puede quitar a una persona; si la desactivas en la lista de clasificaciones, deja de usarse para todos.');
    expect(screen.queryByText(/^(Quitar|Desasignar)$/i)).toBeNull();
    await pulsar('tercero-clasificacion-abrir');
    await waitFor(() => screen.getByTestId('tercero-clasificacion-k2'));
    expect(screen.queryByTestId('tercero-clasificacion-k1')).toBeNull();          // ya asignada
    await pulsar('tercero-clasificacion-k2');
    await pulsar('tercero-clasificacion-principal');
    await pulsar('tercero-clasificacion-guardar');
    await waitFor(() => expect(contratos.anadirClasificacion).toHaveBeenCalledWith(T_CARLOS, { intencion_id: expect.any(String), row_version_esperada: 4, anadir: ['k2'], principal: 'k2' }));
  });
});

// ------------------------------------------------------------------ V-bis / V-ter
describe('selector de persona del asistente (B3c, B3d)', () => {
  const inq = { tipo: 'CONTRATO', rol: 'INQUILINO', contrato_id: 'c1', contrato_nombre: '26-HAB1-CR', desde: '2026-09-01', hasta: null } as const;
  function montar(contratos = clienteContratos(), cliente = clienteApi()) {
    const onElegir = jest.fn();
    const onCerrar = jest.fn();
    render(envolver(<SelectorParticipante contratos={contratos} cliente={cliente} nuevoId={nuevoId} titulo="Inquilino" onElegir={onElegir} onCerrar={onCerrar} />));
    return { contratos, cliente, onElegir, onCerrar };
  }
  const homonimos = () => clienteContratos({
    tercerosParaContrato: jest.fn(async () => ok({ terceros: [
      terceroUso(T_CARLOS, 'Carlos Ruiz', inq),
      terceroUso(T_CARLOS2, 'Carlos Ruiz', { tipo: 'MOVIMIENTO', fecha: '2026-10-12' }),
      terceroUso('t-3', 'Carlos Ruiz', { tipo: 'SIN_USO' }),
      terceroUso('t-4', 'Carlos Martín', { tipo: 'SIN_USO' }),
    ] })),
  });

  test('B3c: homónimos con naturaleza y uso en Gapto; el que no es homónimo, sin segunda línea; nada viene elegido', async () => {
    const { onElegir } = montar(homonimos());
    await waitFor(() => screen.getByTestId(`participante-${T_CARLOS}`));
    expect(screen.getByTestId(`participante-${T_CARLOS}-uso`).props.children).toBe('Persona · inquilino en 26-HAB1-CR');
    expect(screen.getByTestId(`participante-${T_CARLOS2}-uso`).props.children).toBe('Persona · último movimiento 12 oct');
    expect(screen.getByTestId('participante-t-3-uso').props.children).toBe('Persona · sin uso');
    expect(screen.queryByTestId('participante-t-4-uso')).toBeNull();
    expect(screen.getByTestId('participante-ayuda').props.children).toBe('Si hay dos con el mismo nombre, se muestra al lado si es persona o empresa y su uso en Gapto. Nada viene elegido.');
    expect(onElegir).not.toHaveBeenCalled();
    await pulsar(`participante-${T_CARLOS}`);
    expect(onElegir).toHaveBeenCalledWith(expect.objectContaining({ id: T_CARLOS, nombre: 'Carlos Ruiz' }));
  });

  test('O-30: dos filas idénticas no se eligen directamente; se abre la ficha y se confirma «Es esta persona»', async () => {
    const contratos = clienteContratos({
      tercerosParaContrato: jest.fn(async () => ok({ terceros: [terceroUso('a', 'Carlos Ruiz', { tipo: 'SIN_USO' }), terceroUso('b', 'Carlos Ruiz', { tipo: 'SIN_USO' })] })),
      fichaTercero: jest.fn(async (id: string) => ok(ficha({ tercero: tercero(id, 'Carlos Ruiz'), uso: [], roles: [] }))),
    });
    const { onElegir } = montar(contratos);
    await waitFor(() => screen.getByTestId('participante-a'));
    expect(screen.getByTestId('participante-a-uso').props.children).toBe('Persona · sin uso · ver ficha');
    await pulsar('participante-a');
    expect(onElegir).not.toHaveBeenCalled();                                      // la fila no elige
    await waitFor(() => screen.getByTestId('participante-ficha'));
    expect(contratos.fichaTercero).toHaveBeenCalledWith('a');
    await pulsar('participante-es-esta');
    expect(onElegir).toHaveBeenCalledWith(expect.objectContaining({ id: 'a' }));
  });

  test('los inactivos no aparecen en el selector de participantes', async () => {
    const contratos = clienteContratos({ tercerosParaContrato: jest.fn(async () => ok({ terceros: [terceroUso('a', 'Carlos Ruiz', { tipo: 'SIN_USO' }), terceroUso('b', 'Carlos Ruiz', { tipo: 'SIN_USO' }, { enabled: false })] })) });
    montar(contratos);
    await waitFor(() => screen.getByTestId('participante-a'));
    expect(screen.queryByTestId('participante-b')).toBeNull();
    expect(screen.queryByTestId('participante-a-uso')).toBeNull();               // ya no es homónimo entre activos
  });

  test('la búsqueda consulta al servidor con el texto', async () => {
    const { contratos } = montar(homonimos());
    await waitFor(() => screen.getByTestId(`participante-${T_CARLOS}`));
    await escribir('participante-filtro', 'Carlos');
    await waitFor(() => expect(contratos.tercerosParaContrato).toHaveBeenLastCalledWith('Carlos'));
  });

  test('un fallo de carga se ofrece reintentar', async () => {
    const contratos = clienteContratos();
    contratos.tercerosParaContrato.mockResolvedValueOnce({ tipo: 'INDETERMINADO', mensaje: 'x' });
    montar(contratos);
    await waitFor(() => screen.getByTestId('participante-error'));
    await pulsar('participante-error');
    await waitFor(() => screen.getByTestId('participante-vacio'));
  });

  test('B3d (V-ter): «+ Nuevo tercero» abre el selector EXISTENTE de F05; con un duplicado activo, su hoja ofrece Usar el existente / Crear otro', async () => {
    const cliente = clienteApi({ candidatosTercero: jest.fn(async () => ok({ terceros: [tercero(T_CARLOS, 'Carlos Ruiz', { enabled: true })] })) });
    const { onElegir } = montar(clienteContratos(), cliente);
    await waitFor(() => screen.getByTestId('participante-nuevo'));
    await pulsar('participante-nuevo');
    await waitFor(() => screen.getByTestId('selector-tercero'));
    await escribir('tercero-filtro', 'Carlos Ruiz');
    await pulsar('tercero-crear');
    await waitFor(() => screen.getByTestId('tercero-duplicado'));
    expect(screen.getByTestId('tercero-duplicado-aviso')).toBeTruthy();
    expect(screen.getByTestId('tercero-crear-otro')).toBeTruthy();
    await pulsar('tercero-usar-existente');
    expect(onElegir).toHaveBeenCalledWith(expect.objectContaining({ id: T_CARLOS }));
    expect(cliente.altaTercero).not.toHaveBeenCalled();                          // usar no crea nada
  });

  test('B3d (V-ter): un inactivo se reactiva por el circuito de F05 antes de usarlo; «Crear otro» da de alta uno nuevo', async () => {
    const cliente = clienteApi({ candidatosTercero: jest.fn(async () => ok({ terceros: [tercero(T_CARLOS, 'Carlos Ruiz', { enabled: false, row_version: 9 })] })) });
    const { onElegir } = montar(clienteContratos(), cliente);
    await waitFor(() => screen.getByTestId('participante-nuevo'));
    await pulsar('participante-nuevo');
    await escribir('tercero-filtro', 'Carlos Ruiz');
    await pulsar('tercero-crear');
    await waitFor(() => screen.getByTestId('tercero-reactivar'));
    await pulsar('tercero-reactivar');
    await waitFor(() => expect(cliente.reactivarTercero).toHaveBeenCalledWith(T_CARLOS, 9));
    await waitFor(() => expect(onElegir).toHaveBeenCalled());
  });

  test('B3d: «Crear otro» da de alta un tercero nuevo (escritura independiente de F05) y lo elige', async () => {
    const cliente = clienteApi({ candidatosTercero: jest.fn(async () => ok({ terceros: [tercero(T_CARLOS, 'Carlos Ruiz')] })) });
    const { onElegir } = montar(clienteContratos(), cliente);
    await waitFor(() => screen.getByTestId('participante-nuevo'));
    await pulsar('participante-nuevo');
    await escribir('tercero-filtro', 'Carlos Ruiz');
    await pulsar('tercero-crear');
    await waitFor(() => screen.getByTestId('tercero-crear-otro'));
    await pulsar('tercero-crear-otro');
    await waitFor(() => expect(cliente.altaTercero).toHaveBeenCalledWith({ id: expect.any(String), nombre: 'Carlos Ruiz', naturaleza: null }));
    await waitFor(() => expect(onElegir).toHaveBeenCalled());
  });
});
