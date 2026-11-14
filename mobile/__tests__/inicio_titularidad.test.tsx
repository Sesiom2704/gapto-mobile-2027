// ============================================================
// GAPTO MOBILE 2027
// Fichero: inicio_titularidad.test.tsx
// Ruta: mobile/__tests__/inicio_titularidad.test.tsx
// Descripción: B1-R (O-B1R-17) contra dobles en memoria. (N3, Q-B1R-06) Avisos A1/A2 del alta: aparecen solo en su caso y «Usar la fecha de adquisición» rellena «Desde». (L-01b) El alta no deja guardar con «Desde» futuro y usa el texto del servidor. C-PROP-03bis «Corregir desde cuándo»: la ficha ofrece la acción SOLO si el servidor trae `inicio_corregible`; la pantalla solo deja adelantar (anterior al inicio, no futura, no antes de la adquisición), muestra los gastos afectados, avisa con la adquisición desconocida, exige la confirmación visible antes de enviar, envía `inicio_visto` y `primera_version_vista` del servidor y cierra con la vista nueva; un indeterminado reintenta con la misma intención y un rechazo de dominio la renueva y muestra el texto del servidor.
// Versión: 0.1.0 (F06 T2-F06 · B1-R (L-01/L-01b); estructura tomada del Jest del laboratorio lab-t2 45736ad y reescrita para el contrato del §4)
// ============================================================

import './tiempos_rn';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { ClienteApi, Respuesta, Tercero } from '../src/api/cliente';
import type { Afectados, ClientePropiedades, PayloadCorregirInicio, VistaPropiedad } from '../src/api/propiedades';
import { avisoA1, avisoA2, desdeFuturo, faltasInicio, TEXTO_A2, TEXTO_DESDE_FUTURO, textoConfirmacion } from '../src/domain/inicio_titularidad';
import { PropiedadAltaScreen } from '../src/screens/PropiedadAltaScreen';
import { PropiedadesScreen } from '../src/screens/PropiedadesScreen';
import { PropiedadFichaScreen } from '../src/screens/PropiedadFichaScreen';
import { PropiedadInicioScreen } from '../src/screens/PropiedadInicioScreen';
import { ProveedorTema } from '../src/theme/tema';

const YO = 'f0000000-0000-4000-8000-0000000000ff';
const ANA = 'a0000000-0000-4000-8000-0000000000a1';
const AHORA = () => new Date(2026, 9, 10, 10);
const HOY = '2026-10-10';

const vista = (o: Partial<VistaPropiedad> = {}): VistaPropiedad => ({
  id: 'p1', nombre: 'Piso Centro', enabled: true, row_version: 3, tipo_propiedad: 'VIVIENDA', fecha_adquisicion: '2015-06-01',
  superficie_m2: null, superficie_construida_m2: null, habitaciones: null, banos: null, tiene_garaje: null, tiene_trastero: null, referencia_catastral: null,
  incluir_en_rentabilidad: true, notas: null, fecha_consulta: HOY,
  titularidad: { modo: 'COMPARTIDA', desde: '2026-09-01', partes: [
    { actor_id: YO, yo: true, tercero_id: null, nombre: null, porcentaje: '50.0000' },
    { actor_id: ANA, yo: false, tercero_id: 't-ana', nombre: 'Ana', porcentaje: '50.0000' }] },
  cambio_programado: null, valor_estimado: null, referencia_fiscal: null, valor_compra: null, cuota_segun_titularidad: null, valoraciones: [],
  inicio_titularidad: { inicio: '2026-09-01', inicio_corregible: true, primera_version: [{ actor_id: ANA, porcentaje: '50.0000' }, { actor_id: YO, porcentaje: '50.0000' }] },
  ...o,
});

const ok = <T,>(datos: T) => ({ tipo: 'OK', datos }) as Respuesta<T>;
const afectados = (nuevo: string | null, n = 1): Afectados => ({
  propiedad_id: 'p1', inicio_vigente: '2026-09-01', nuevo_desde: nuevo, recuento: n,
  hechos: Array.from({ length: n }, (_, i) => ({ hecho_id: `h${i}`, fecha: '2026-05-15', concepto: 'Fontanero', importe: '300.00', tipo_hecho: 'GASTO', clase: 'GASTO', atribucion: 'NO_LO_SE' as const })),
});

function envolver(ui: React.ReactElement) {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ProveedorTema forzar="light">{ui}</ProveedorTema>
    </SafeAreaProvider>,
  );
}
const pulsar = async (id: string) => act(async () => fireEvent.press(screen.getByTestId(id)));
const escribir = async (id: string, t: string) => act(async () => fireEvent.changeText(screen.getByTestId(id), t));
const deshabilitado = (id: string) => screen.getByTestId(id).props.accessibilityState?.disabled === true;

// ------------------------------------------------------------------ dominio
test('dominio: A1/A2 solo en su caso; cota del alta; reglas de la corrección; confirmación', () => {
  expect(avisoA1('2015-06-01', '2026-09-01')).toBe('Los gastos entre el 1 jun 2015 y el 1 sep 2026 no tendrán reparto propuesto. Si la titularidad empezó al comprar, usa la fecha de adquisición.');
  expect(avisoA1('2015-06-01', '2015-06-01')).toBeNull();
  expect(avisoA1('2015-06-01', '2014-01-01')).toBeNull();
  expect(avisoA1(null, '2026-09-01')).toBeNull();
  expect(avisoA2(null, 'COMPARTIDA')).toBe(TEXTO_A2);
  expect(avisoA2(null, 'DESCONOCIDA')).toBeNull();
  expect(avisoA2(null, null)).toBeNull();
  expect(avisoA2('2015-06-01', 'COMPARTIDA')).toBeNull();
  expect(desdeFuturo('2026-10-11', HOY)).toBe(true);
  expect(desdeFuturo(HOY, HOY)).toBe(false);
  expect(desdeFuturo(null, HOY)).toBe(false);
  expect(faltasInicio('2016-01-01', '2026-09-01', HOY, '2015-06-01')).toEqual([]);
  expect(faltasInicio('2015-06-01', '2026-09-01', HOY, '2015-06-01')).toEqual([]);
  expect(faltasInicio('2026-09-01', '2026-09-01', HOY, null)[0]).toMatch(/solo se puede adelantar/);
  expect(faltasInicio('2026-09-15', '2026-09-01', HOY, null)[0]).toMatch(/solo se puede adelantar/);
  expect(faltasInicio('2015-05-31', '2026-09-01', HOY, '2015-06-01')[0]).toMatch(/adquisición/);
  expect(faltasInicio('2026-10-11', '2026-12-01', HOY, null)).toEqual(['una fecha que no sea futura']);
  expect(faltasInicio(HOY, '2026-12-01', HOY, null)).toEqual([]);
  expect(faltasInicio(null, '2026-09-01', HOY, null)).toEqual(['la nueva fecha (dd/mm/aaaa)']);
  expect(textoConfirmacion('2026-09-01', '2015-06-01', 2)).toBe('El inicio pasa del 1 sep 2026 al 1 jun 2015. Mismas partes. 2 gastos ya registrados no cambian.');
});

// ------------------------------------------------------------------ alta (A1, A2 y L-01b)
const TERCEROS: Tercero[] = [];
const clienteTerceros = () => ({ listarTerceros: jest.fn(async () => ok({ terceros: TERCEROS })) }) as unknown as ClienteApi;
function propiedadesAlta() {
  const altaPropiedad = jest.fn(async (c: any) => ok({ propiedad: vista({ id: c.intencion_id }), idempotente: false, modificadas: [], avisos: [] }));
  return { api: { altaPropiedad } as unknown as ClientePropiedades, altaPropiedad };
}
async function abrirAlta(adquisicion: string | null) {
  const p = propiedadesAlta();
  envolver(<PropiedadAltaScreen cliente={clienteTerceros()} propiedades={p.api} nuevoId={() => 'alta-1'} ahora={AHORA} onCerrar={jest.fn()} />);
  await escribir('prop-alta-nombre', 'Piso Centro');
  await pulsar('prop-alta-tipo-VIVIENDA');
  if (adquisicion) await escribir('prop-alta-adquisicion', adquisicion);
  await pulsar('prop-alta-continuar');
  return p;
}

test('alta A1: «Desde» posterior a la adquisición avisa y «Usar la fecha de adquisición» rellena «Desde»', async () => {
  await abrirAlta('01/06/2015');
  await pulsar('tit-modo-SOLO_MIA');
  expect(screen.getByTestId('tit-desde').props.value).toBe('01/06/2015');
  expect(screen.queryByTestId('prop-alta-aviso-a1')).toBeNull();
  await escribir('tit-desde', '01/09/2026');
  expect(screen.getByTestId('prop-alta-aviso-a1-texto').props.children).toBe(avisoA1('2015-06-01', '2026-09-01'));
  expect(screen.queryByTestId('prop-alta-aviso-a2')).toBeNull();
  await pulsar('prop-alta-usar-adquisicion');
  expect(screen.getByTestId('tit-desde').props.value).toBe('01/06/2015');
  expect(screen.queryByTestId('prop-alta-aviso-a1')).toBeNull();
});

test('alta A2: adquisición «No la sé» con un modo con titularidad; nunca con «Aún no lo sé»', async () => {
  await abrirAlta(null);
  expect(screen.queryByTestId('prop-alta-aviso-a2')).toBeNull();
  await pulsar('tit-modo-SOLO_MIA');
  expect(screen.getByTestId('prop-alta-aviso-a2').props.children).toBe(TEXTO_A2);
  expect(screen.queryByTestId('prop-alta-aviso-a1')).toBeNull();
  await pulsar('tit-modo-DESCONOCIDA');
  expect(screen.queryByTestId('prop-alta-aviso-a2')).toBeNull();
});

test('alta L-01b: con «Desde» futuro no se puede guardar (texto del servidor); con «Desde» = hoy, sí', async () => {
  const p = await abrirAlta(null);
  await pulsar('tit-modo-SOLO_MIA');
  await escribir('tit-desde', '11/10/2026');
  expect(screen.getByTestId('prop-alta-desde-futuro').props.children).toBe(TEXTO_DESDE_FUTURO);
  expect(deshabilitado('prop-alta-guardar')).toBe(true);
  await pulsar('prop-alta-guardar');
  expect(p.altaPropiedad).not.toHaveBeenCalled();
  await escribir('tit-desde', '10/10/2026');
  expect(screen.queryByTestId('prop-alta-desde-futuro')).toBeNull();
  expect(deshabilitado('prop-alta-guardar')).toBe(false);
  await pulsar('prop-alta-guardar');
  expect(p.altaPropiedad).toHaveBeenCalledTimes(1);
  expect(p.altaPropiedad.mock.calls[0][0].titularidad).toEqual({ modo: 'SOLO_MIA', desde: '2026-10-10' });
});

// ------------------------------------------------------------------ ficha
test('ficha: «Corregir desde cuándo» solo si el servidor trae inicio_corregible', () => {
  const fn = jest.fn();
  const props = { onAtras: jest.fn(), onRevisarValor: jest.fn(), onHistorico: jest.fn(), onTitularidad: jest.fn(), onEditar: jest.fn(), onCorregirInicio: fn };
  envolver(<PropiedadFichaScreen vista={vista()} {...props} />);
  expect(screen.getByText('Corregir desde cuándo')).toBeTruthy();
  expect(screen.getByText('Ahora empieza el 1 sep 2026')).toBeTruthy();
  fireEvent.press(screen.getByTestId('prop-accion-inicio'));
  expect(fn).toHaveBeenCalled();
  screen.unmount();
  envolver(<PropiedadFichaScreen vista={vista({ inicio_titularidad: { inicio: '2026-09-01', inicio_corregible: false, primera_version: [] } })} {...props} />);
  expect(screen.queryByTestId('prop-accion-inicio')).toBeNull();
  screen.unmount();
  envolver(<PropiedadFichaScreen vista={vista({ inicio_titularidad: undefined })} {...props} />);
  expect(screen.queryByTestId('prop-accion-inicio')).toBeNull();
});

// ------------------------------------------------------------------ pantalla de corrección
function propiedadesInicio(corregir: (id: string, p: PayloadCorregirInicio) => Promise<Respuesta<any>>) {
  const gastosAfectados = jest.fn(async (_id: string, nuevo: string | null) => ok({ afectados: afectados(nuevo, nuevo ? 2 : 3) }));
  const corregirInicio = jest.fn(corregir);
  return { api: { corregirInicio, gastosAfectados } as unknown as ClientePropiedades, corregirInicio, gastosAfectados };
}

test('pantalla: afectados, confirmación obligatoria y petición exacta; cierra con la vista nueva', async () => {
  const nueva = vista({ row_version: 4 });
  const p = propiedadesInicio(async () => ok({ propiedad: nueva, idempotente: false, modificadas: ['p1'], avisos: [] }));
  const cerrar = jest.fn();
  envolver(<PropiedadInicioScreen propiedades={p.api} vista={vista()} nuevoId={() => 'i-1'} ahora={AHORA} onCerrar={cerrar} />);
  expect(screen.getByTestId('prop-inicio-actual').props.children).toMatch(/empieza ahora el 1 sep 2026/);
  expect(screen.getByTestId('prop-inicio-explicacion').props.children).toBe('Solo para corregir un error: la titularidad empezó antes. Las partes no cambian. Los gastos ya registrados no se recalculan.');
  expect(screen.queryByTestId('prop-inicio-adquisicion-desconocida')).toBeNull();
  await waitFor(() => expect(screen.getByTestId('prop-inicio-afectados')).toBeTruthy());
  expect(screen.getByTestId('prop-inicio-afectados-texto').props.children).toBe('Estos gastos ya registrados no cambian. Si quieres repartirlos, corrígelos uno a uno.');
  expect(p.gastosAfectados).toHaveBeenCalledWith('p1', null);
  expect(deshabilitado('prop-inicio-revisar')).toBe(true);
  await pulsar('prop-inicio-usar-adquisicion');
  await waitFor(() => expect(p.gastosAfectados).toHaveBeenLastCalledWith('p1', '2015-06-01'));
  // sin la confirmación no se envía nada
  expect(screen.queryByTestId('prop-inicio-confirmar')).toBeNull();
  await pulsar('prop-inicio-revisar');
  expect(p.corregirInicio).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.getByTestId('prop-inicio-confirmacion')).toBeTruthy());
  expect(screen.getByText('El inicio pasa del 1 sep 2026 al 1 jun 2015. Mismas partes. 2 gastos ya registrados no cambian.')).toBeTruthy();
  await pulsar('prop-inicio-confirmar');
  expect(p.corregirInicio).toHaveBeenCalledWith('p1', {
    intencion_id: 'i-1', row_version_esperada: 3, nuevo_desde: '2015-06-01', inicio_visto: '2026-09-01', motivo: null,
    primera_version_vista: [{ actor_id: ANA, porcentaje: '50.0000' }, { actor_id: YO, porcentaje: '50.0000' }],
  });
  expect(cerrar).toHaveBeenCalledWith(nueva);
});

test('pantalla: solo adelantar; una fecha posterior o anterior a la adquisición no deja continuar', async () => {
  const p = propiedadesInicio(async () => ok({}));
  envolver(<PropiedadInicioScreen propiedades={p.api} vista={vista()} nuevoId={() => 'i-1'} ahora={AHORA} onCerrar={jest.fn()} />);
  await pulsar('prop-inicio-fecha-otra');
  await escribir('prop-inicio-fecha', '15/09/2026');
  expect(screen.getByTestId('prop-inicio-faltas').props.children).toMatch(/solo se puede adelantar/);
  expect(deshabilitado('prop-inicio-revisar')).toBe(true);
  await escribir('prop-inicio-fecha', '31/05/2015');
  expect(screen.getByTestId('prop-inicio-faltas').props.children).toMatch(/adquisición/);
  expect(deshabilitado('prop-inicio-revisar')).toBe(true);
  await escribir('prop-inicio-fecha', '01/01/2016');
  expect(screen.queryByTestId('prop-inicio-faltas')).toBeNull();
  expect(deshabilitado('prop-inicio-revisar')).toBe(false);
});

test('pantalla: adquisición «No la sé» → aviso visible (la fecha no se presenta como verificada) y sin cota inferior', async () => {
  const p = propiedadesInicio(async () => ok({}));
  envolver(<PropiedadInicioScreen propiedades={p.api} vista={vista({ fecha_adquisicion: null })} nuevoId={() => 'i-1'} ahora={AHORA} onCerrar={jest.fn()} />);
  expect(screen.getByTestId('prop-inicio-adquisicion-desconocida').props.children).toBe('No sabemos cuándo la compraste: la app no puede comprobar esta fecha.');
  expect(screen.queryByTestId('prop-inicio-usar-adquisicion')).toBeNull();
  await pulsar('prop-inicio-fecha-otra');
  await escribir('prop-inicio-fecha', '01/01/1990');
  expect(deshabilitado('prop-inicio-revisar')).toBe(false);
});

test('pantalla: indeterminado reintenta con la MISMA intención; un rechazo la renueva y muestra el texto del servidor', async () => {
  let n = 0;
  const respuestas: Respuesta<any>[] = [
    { tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el cambio.' },
    { tipo: 'RECHAZADO', codigo: 'INICIO_NO_ANTERIOR', mensaje: 'Solo se puede adelantar el inicio: elige una fecha anterior a la actual.' },
    { tipo: 'RECHAZADO', codigo: 'VERSION_DESFASADA', mensaje: 'La propiedad ha cambiado desde que la abriste. Vuelve a cargarla.' },
  ];
  const p = propiedadesInicio(async () => respuestas.shift()!);
  envolver(<PropiedadInicioScreen propiedades={p.api} vista={vista()} nuevoId={() => `i-${++n}`} ahora={AHORA} onCerrar={jest.fn()} />);
  await pulsar('prop-inicio-fecha-otra');
  await escribir('prop-inicio-fecha', '01/01/2016');
  await pulsar('prop-inicio-revisar');
  await pulsar('prop-inicio-confirmar');
  expect(screen.getByTestId('prop-inicio-aviso')).toBeTruthy();
  await pulsar('prop-inicio-confirmar');
  expect(screen.getByText('Solo se puede adelantar el inicio: elige una fecha anterior a la actual.')).toBeTruthy();
  // tras el rechazo hay que volver a confirmar
  expect(screen.queryByTestId('prop-inicio-confirmar')).toBeNull();
  await pulsar('prop-inicio-revisar');
  await pulsar('prop-inicio-confirmar');
  const ids = p.corregirInicio.mock.calls.map((c) => c[1].intencion_id);
  expect(ids).toEqual(['i-1', 'i-1', 'i-2']);
});

// ------------------------------------------------------------------ navegación
test('navegación: desde la ficha, «Corregir desde cuándo» abre la tarea y al cerrar vuelve a la ficha', async () => {
  const v = vista();
  const api = {
    listarPropiedades: jest.fn(async () => ok({ propiedades: [{ id: 'p1', nombre: v.nombre, enabled: true, row_version: 3, tipo_propiedad: 'VIVIENDA', modo_titularidad: 'COMPARTIDA', valor_estimado: null }] })),
    leerPropiedad: jest.fn(async () => ok({ propiedad: v })),
    gastosAfectados: jest.fn(async (_id: string, nuevo: string | null) => ok({ afectados: afectados(nuevo, 0) })),
  } as unknown as ClientePropiedades;
  const patrimonio = { leerCoste: jest.fn(async () => ({ tipo: 'INDETERMINADO', mensaje: '' })) } as any;
  envolver(<PropiedadesScreen cliente={clienteTerceros()} propiedades={api} nuevoId={() => 'i-1'} ahora={AHORA} onInmersiva={jest.fn()} patrimonio={patrimonio} />);
  await waitFor(() => expect(screen.getByTestId('prop-fila-p1')).toBeTruthy());
  await pulsar('prop-fila-p1');
  await waitFor(() => expect(screen.getByTestId('prop-accion-inicio')).toBeTruthy());
  await pulsar('prop-accion-inicio');
  await waitFor(() => expect(screen.getByTestId('prop-inicio-afectados-vacio')).toBeTruthy());
  await pulsar('prop-inicio-cancelar');
  expect(screen.getByTestId('prop-ficha')).toBeTruthy();
});
