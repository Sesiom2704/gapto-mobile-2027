// ============================================================
// GAPTO MOBILE 2027
// Fichero: MagnitudesCategoria.tsx
// Ruta: mobile/src/components/MagnitudesCategoria.tsx
// Descripción: Controlador de las magnitudes de una categoría en Ajustes › Categorías (F05-D020; F09 §12.97.10; lámina SET-MAG v0.1). Hook `useMagnitudesCategoria` que la pantalla de detalle llama siempre: devuelve la SECCIÓN (para el ScrollView del detalle), la PANTALLA a mostrar en lugar del detalle (selector del catálogo o ficha) y si la tarea es inmersiva (oculta la barra inferior). Las asociaciones se leen del árbol (GET /v1/categorias, con `asociacion_id`); el catálogo (GET /v1/magnitudes) se carga al desplegar la sección y aporta `n_hechos` y las categorías de cada magnitud. Cada comando usa la identidad cargada (asociacion_id + magnitud_id + obligatoria_actual; row_version de la magnitud) y, tras confirmar, recarga árbol y catálogo. Conflictos (VERSION_DESFASADA, ASOCIACION_YA_EXISTE, ASOCIACION_NO_EXISTE, CONJUNTO_MAGNITUDES_DESFASADO): se cierra la tarea, se recarga y se avisa «Las magnitudes de <categoría> han cambiado…» (M16), sin reintento automático. INDETERMINADO: se recarga antes de cualquier repetición; nunca se duplica.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1: sección, añadir existente, obligatoriedad, quitar y conflictos)
// Versión: 0.2.0 (F05-01 S7-MAG UI, hito 2): alta NUEVA (M07) con la identidad del formulario reutilizada en el reintento (indeterminado: aviso y recarga, mismo `magnitud_id`) y colisión de nombre (M08: usar la existente o rehabilitarla y usarla, dos llamadas encadenadas y la segunda solo si la primera confirma; sin `detalle`, mensaje genérico y recarga del catálogo; IDENTIDAD_REUTILIZADA: aviso, identidad nueva solo si el usuario edita); Editar orden (M10: conjunto COMPLETO en UNA llamada; sin cambios no se envía nada); ficha global (M13) con renombrar (colisión junto al nombre), deshabilitar en dos pasos con el impacto que calcula el servidor (M14) y, si el conjunto cambia entre la consulta y la confirmación, «El impacto ha cambiado» con la lista nueva y otra confirmación (M15), nunca un reenvío automático; rehabilitar con confirmación simple.
// ============================================================

import React, { useCallback, useEffect, useState } from 'react';

import { ClienteApi, detalleImpacto, detalleNombreDuplicado, Respuesta } from '../api/cliente';
import type { CategoriaNodo, MagnitudCategoria } from '../domain/categoria';
import { conjuntoReordenar, filasImpacto, MagnitudCatalogo, mismoOrdenAsociaciones, usosDe } from '../domain/magnitud';
import { EditarOrdenMagnitudes } from './EditarOrdenMagnitudes';
import { BloqueMagnitud, FichaMagnitud } from './FichaMagnitud';
import {
  HojaAnadirExistente,
  HojaDeshabilitar,
  HojaObligatoriedad,
  HojaQuitar,
  HojaRehabilitar,
  HojaRenombrarMagnitud,
} from './HojasMagnitud';
import { Colision, EnvioNueva, NuevaMagnitud } from './NuevaMagnitud';
import { FaseCatalogo, SeccionMagnitudes } from './SeccionMagnitudes';
import { SelectorMagnitudes } from './SelectorMagnitudes';

export const CONFLICTOS_MAGNITUDES = new Set(['VERSION_DESFASADA', 'ASOCIACION_YA_EXISTE', 'ASOCIACION_NO_EXISTE', 'CONJUNTO_MAGNITUDES_DESFASADO']);
export const AVISO_CAMBIADAS = (cat: string) => ({
  titulo: `Las magnitudes de ${cat} han cambiado`,
  texto: 'Se ha recargado el estado actual. Revisa y repite la acción si sigue haciendo falta.',
});
export const AVISO_INDETERMINADO = {
  titulo: 'No se ha podido confirmar el cambio',
  texto: 'Se ha recargado el estado actual. Revísalo antes de repetir la acción: nunca se duplica.',
};
export const AVISO_SIN_CAMBIOS_ORDEN = { titulo: 'Sin cambios', texto: 'El orden ya era ese: no se ha enviado nada.' };
export const AVISO_NUEVA_INDETERMINADO = 'No se ha podido confirmar la creación. Puedes volver a pulsar «Crear»: no se duplicará.';
export const AVISO_NUEVA_REUTILIZADA = 'Ya se envió esta magnitud con otros datos. Cambia algún dato antes de volver a crearla.';
export const MSG_RENOMBRAR_DUPLICADO = (nombre: string | null) =>
  nombre ? `Ya existe «${nombre}». Elige otro nombre.` : 'Ya tienes una magnitud con ese nombre. Elige otro nombre.';

type CargaCatalogo = { fase: 'CARGANDO' } | { fase: 'OK'; magnitudes: MagnitudCatalogo[] } | { fase: 'ERROR' };
type Vista = null | { tipo: 'SELECTOR' } | { tipo: 'NUEVA' } | { tipo: 'ORDEN' } | { tipo: 'FICHA'; asociacionId: string };
type HojaAbierta =
  | null
  | { tipo: 'ANADIR'; magnitud: MagnitudCatalogo }
  | { tipo: 'OBLIGATORIEDAD' }
  | { tipo: 'QUITAR' }
  | { tipo: 'RENOMBRAR' }
  | { tipo: 'DESHABILITAR'; afectadas: { id: string; nombre: string }[]; previas: string[] | null; cambiado: boolean }
  | { tipo: 'REHABILITAR' };
export type AvisoMagnitudes = { titulo: string; texto: string } | null;

export function useMagnitudesCategoria(p: {
  cliente: ClienteApi;
  categoria: CategoriaNodo | null;
  nuevoId: () => string;
  /** Ruta visible de una categoría («Hogar › Luz»); `nombre` si no está en el árbol cargado. */
  ruta: (id: string, nombre: string) => string;
  /** Recarga el árbol SIN pasar por «cargando» (la vista no parpadea). */
  recargarArbol: () => Promise<void>;
}) {
  const [abierta, setAbierta] = useState(false);
  const [catalogo, setCatalogo] = useState<CargaCatalogo>({ fase: 'CARGANDO' });
  const [vista, setVista] = useState<Vista>(null);
  const [hoja, setHoja] = useState<HojaAbierta>(null);
  const [aviso, setAviso] = useState<AvisoMagnitudes>(null);
  const [guardando, setGuardando] = useState(false);
  const [colision, setColision] = useState<Colision>(null);
  const [avisoNueva, setAvisoNueva] = useState<string | null>(null);
  const [errorNombre, setErrorNombre] = useState<string | null>(null);
  const cat = p.categoria;
  const catId = cat?.id ?? null;

  useEffect(() => {
    setAbierta(false);
    setVista(null);
    setHoja(null);
    setAviso(null);
  }, [catId]);

  const cargarCatalogo = useCallback(async (): Promise<MagnitudCatalogo[] | null> => {
    setCatalogo({ fase: 'CARGANDO' });
    const r = await p.cliente.catalogoMagnitudes();
    setCatalogo(r.tipo === 'OK' ? { fase: 'OK', magnitudes: r.datos.magnitudes } : { fase: 'ERROR' });
    return r.tipo === 'OK' ? r.datos.magnitudes : null;
  }, [p.cliente]);

  // El catálogo se carga cuando pasa a hacer falta (sección desplegada o una vista abierta); tras cada comando se
  // recarga explícitamente. Cerrar una vista con la sección desplegada no lo vuelve a pedir.
  const necesitaCatalogo = abierta || vista !== null;
  useEffect(() => {
    if (necesitaCatalogo) void cargarCatalogo();
  }, [necesitaCatalogo, catId]);

  const recargarTodo = async () => {
    await Promise.all([p.recargarArbol(), cargarCatalogo()]);
  };

  const cerrar = () => {
    setHoja(null);
    setVista(null);
    setColision(null);
    setAvisoNueva(null);
  };

  /** Trata el resultado de un comando: OK -> `alOk` y recarga; rechazo -> cierra, avisa y recarga (nunca reintenta). */
  const tratar = async (r: Respuesta<unknown>, alOk: () => void) => {
    if (r.tipo === 'OK') {
      alOk();
      setAviso(null);
      await recargarTodo();
      return;
    }
    cerrar();
    setAbierta(true);
    if (r.tipo === 'INDETERMINADO') setAviso(AVISO_INDETERMINADO);
    else if (CONFLICTOS_MAGNITUDES.has(r.codigo)) setAviso(AVISO_CAMBIADAS(cat?.nombre ?? ''));
    else setAviso({ titulo: 'No se ha podido completar la acción', texto: r.mensaje || 'Se ha recargado el estado actual.' });
    await recargarTodo();
  };

  const conGuardado = async (accion: () => Promise<void>) => {
    if (guardando) return;
    setGuardando(true);
    try {
      await accion();
    } finally {
      setGuardando(false);
    }
  };

  const magnitudesCatalogo = catalogo.fase === 'OK' ? catalogo.magnitudes : [];
  const delCatalogo = (id: string) => magnitudesCatalogo.find((m) => m.id === id) ?? null;

  // ------------------------------------------------------------------ asociaciones
  const anadir = (m: MagnitudCatalogo, obligatoria: boolean) =>
    conGuardado(async () => {
      if (!cat) return;
      const r = await p.cliente.asociarMagnitud(cat.id, { origen: 'EXISTENTE', magnitud_id: m.id, obligatoria });
      await tratar(r, cerrar);
    });

  const crear = (e: EnvioNueva) =>
    conGuardado(async () => {
      if (!cat) return;
      setAvisoNueva(null);
      const r = await p.cliente.asociarMagnitud(cat.id, {
        origen: 'NUEVA',
        magnitud: { magnitud_id: e.magnitud_id, nombre: e.nombre, unidad_default: e.unidad_default, precision_decimales: e.precision_decimales },
        obligatoria: e.obligatoria,
      });
      if (r.tipo === 'RECHAZADO' && r.codigo === 'MAGNITUD_NOMBRE_DUPLICADO') {
        const d = detalleNombreDuplicado(r);
        const lista = await cargarCatalogo();
        const existente = d && lista ? lista.find((m) => m.id === d.magnitud_id) ?? null : null;
        setColision(existente ? { tipo: 'EXISTENTE', magnitud: existente } : { tipo: 'SIN_DETALLE' });
        return;
      }
      if (r.tipo === 'RECHAZADO' && r.codigo === 'IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION') return setAvisoNueva(AVISO_NUEVA_REUTILIZADA);
      if (r.tipo === 'RECHAZADO' && r.codigo === 'ENTRADA_INVALIDA') return setAvisoNueva(r.mensaje || 'Revisa los datos.');
      if (r.tipo === 'INDETERMINADO') {
        // El formulario conserva su identidad: el reintento reenvía el MISMO magnitud_id (idempotente en el servidor).
        setAvisoNueva(AVISO_NUEVA_INDETERMINADO);
        await recargarTodo();
        return;
      }
      await tratar(r, cerrar);
    });

  const rehabilitarYUsar = (m: MagnitudCatalogo, obligatoria: boolean) =>
    conGuardado(async () => {
      if (!cat) return;
      const r1 = await p.cliente.rehabilitarMagnitud(m.id, { row_version: m.row_version });
      if (r1.tipo !== 'OK') return tratar(r1, cerrar);
      const r2 = await p.cliente.asociarMagnitud(cat.id, { origen: 'EXISTENTE', magnitud_id: m.id, obligatoria });
      await tratar(r2, cerrar);
    });

  const guardarOrden = (orden: MagnitudCategoria[]) =>
    conGuardado(async () => {
      if (!cat) return;
      if (mismoOrdenAsociaciones(orden, cat.magnitudes)) {
        cerrar();
        setAviso(AVISO_SIN_CAMBIOS_ORDEN);
        return;
      }
      const r = await p.cliente.reordenarMagnitudes(cat.id, { asociaciones: conjuntoReordenar(orden) });
      await tratar(r, cerrar);
    });

  const asociacion: MagnitudCategoria | null =
    vista?.tipo === 'FICHA' ? cat?.magnitudes.find((m) => m.asociacion_id === vista.asociacionId) ?? null : null;
  // Una ficha cuya asociación ya no existe tras recargar vuelve al detalle (sin inventar estado).
  useEffect(() => {
    if (vista?.tipo === 'FICHA' && cat && !asociacion) setVista(null);
  }, [cat, asociacion, vista?.tipo]);

  const cambiarObligatoriedad = (a: MagnitudCategoria) =>
    conGuardado(async () => {
      if (!cat) return;
      const r = await p.cliente.obligatoriaMagnitud(cat.id, a.asociacion_id, {
        magnitud_id: a.magnitud_id,
        obligatoria_actual: a.obligatoria,
        obligatoria: !a.obligatoria,
      });
      await tratar(r, () => setHoja(null));
    });

  const quitar = (a: MagnitudCategoria) =>
    conGuardado(async () => {
      if (!cat) return;
      const r = await p.cliente.retirarMagnitud(cat.id, a.asociacion_id, { magnitud_id: a.magnitud_id, obligatoria_actual: a.obligatoria });
      await tratar(r, cerrar);
    });

  // ------------------------------------------------------------------ la magnitud (afecta a todas sus categorías)
  const renombrar = (m: MagnitudCatalogo, nombre: string) =>
    conGuardado(async () => {
      const r = await p.cliente.renombrarMagnitud(m.id, { nombre, row_version: m.row_version });
      if (r.tipo === 'RECHAZADO' && r.codigo === 'MAGNITUD_NOMBRE_DUPLICADO') {
        const d = detalleNombreDuplicado(r);
        return setErrorNombre(MSG_RENOMBRAR_DUPLICADO(d ? delCatalogo(d.magnitud_id)?.nombre ?? null : null));
      }
      if (r.tipo === 'RECHAZADO' && r.codigo === 'ENTRADA_INVALIDA') return setErrorNombre('Revisa el nombre: de 1 a 80 caracteres.');
      await tratar(r, () => setHoja(null));
    });

  const deshabilitar = (m: MagnitudCatalogo) =>
    conGuardado(async () => {
      // Primera llamada sin confirmación: si no hay impacto, confirma directamente.
      const r = await p.cliente.deshabilitarMagnitud(m.id, { row_version: m.row_version, confirmacion_impacto: null });
      const afectadas = r.tipo === 'RECHAZADO' && r.codigo === 'MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION' ? detalleImpacto(r) : null;
      if (afectadas) return setHoja({ tipo: 'DESHABILITAR', afectadas, previas: null, cambiado: false });
      await tratar(r, () => setHoja(null));
    });

  const confirmarDeshabilitar = (m: MagnitudCatalogo, afectadas: { id: string; nombre: string }[]) =>
    conGuardado(async () => {
      const confirmadas = afectadas.map((a) => a.id);
      const r = await p.cliente.deshabilitarMagnitud(m.id, { row_version: m.row_version, confirmacion_impacto: confirmadas });
      const nuevas = r.tipo === 'RECHAZADO' && r.codigo === 'MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION' ? detalleImpacto(r) : null;
      // M15: el conjunto cambió entre la consulta y la confirmación: se muestra y se pide confirmar otra vez.
      if (nuevas) return setHoja({ tipo: 'DESHABILITAR', afectadas: nuevas, previas: confirmadas, cambiado: true });
      await tratar(r, () => setHoja(null));
    });

  const rehabilitar = (m: MagnitudCatalogo) =>
    conGuardado(async () => {
      const r = await p.cliente.rehabilitarMagnitud(m.id, { row_version: m.row_version });
      await tratar(r, () => setHoja(null));
    });

  // ------------------------------------------------------------------ presentación
  const fase: FaseCatalogo = catalogo.fase;

  const seccion = cat ? (
    <SeccionMagnitudes
      categoria={cat.nombre}
      magnitudes={cat.magnitudes}
      abierta={abierta}
      fase={fase}
      aviso={aviso}
      onAlternar={() => setAbierta((x) => !x)}
      onFila={(m) => { setAviso(null); setVista({ tipo: 'FICHA', asociacionId: m.asociacion_id }); }}
      onAnadir={() => { setAviso(null); setVista({ tipo: 'SELECTOR' }); }}
      onEditarOrden={() => { setAviso(null); setVista({ tipo: 'ORDEN' }); }}
      onReintentar={() => void cargarCatalogo()}
    />
  ) : null;

  let pantalla: React.ReactNode = null;
  if (cat && vista?.tipo === 'SELECTOR') {
    pantalla = (
      <>
        <SelectorMagnitudes
          categoria={cat.nombre}
          fase={fase}
          catalogo={magnitudesCatalogo}
          asociadas={cat.magnitudes}
          onElegir={(m) => setHoja({ tipo: 'ANADIR', magnitud: m })}
          onNueva={() => { setHoja(null); setColision(null); setAvisoNueva(null); setVista({ tipo: 'NUEVA' }); }}
          onCerrar={cerrar}
          onReintentar={() => void cargarCatalogo()}
        />
        {hoja?.tipo === 'ANADIR' ? (
          <HojaAnadirExistente
            categoria={cat.nombre}
            magnitud={hoja.magnitud}
            guardando={guardando}
            onAnadir={(ob) => void anadir(hoja.magnitud, ob)}
            onCancelar={() => setHoja(null)}
          />
        ) : null}
      </>
    );
  } else if (cat && vista?.tipo === 'NUEVA') {
    pantalla = (
      <NuevaMagnitud
        categoria={cat.nombre}
        nuevoId={p.nuevoId}
        guardando={guardando}
        colision={colision}
        aviso={avisoNueva}
        onCrear={(e) => void crear(e)}
        onUsarExistente={(m, ob) => void anadir(m, ob)}
        onRehabilitarYUsar={(m, ob) => void rehabilitarYUsar(m, ob)}
        onRecargarCatalogo={() => { setColision(null); void cargarCatalogo(); }}
        onEditar={() => { setColision(null); setAvisoNueva(null); }}
        onCancelar={cerrar}
      />
    );
  } else if (cat && vista?.tipo === 'ORDEN') {
    pantalla = (
      <EditarOrdenMagnitudes
        categoria={cat.nombre}
        asociaciones={cat.magnitudes}
        guardando={guardando}
        onGuardar={(orden) => void guardarOrden(orden)}
        onCancelar={cerrar}
      />
    );
  } else if (cat && asociacion) {
    const m = delCatalogo(asociacion.magnitud_id);
    pantalla = (
      <>
        <FichaMagnitud
          categoria={cat.nombre}
          asociacion={asociacion}
          onAtras={cerrar}
          onObligatoriedad={() => setHoja({ tipo: 'OBLIGATORIEDAD' })}
          onQuitar={() => setHoja({ tipo: 'QUITAR' })}
        >
          <BloqueMagnitud
            fase={fase}
            magnitud={m}
            categoriaActual={cat.id}
            ruta={p.ruta}
            onRenombrar={() => { setErrorNombre(null); setHoja({ tipo: 'RENOMBRAR' }); }}
            onDeshabilitar={() => m && void deshabilitar(m)}
            onRehabilitar={() => setHoja({ tipo: 'REHABILITAR' })}
            onReintentar={() => void cargarCatalogo()}
          />
        </FichaMagnitud>
        {hoja?.tipo === 'OBLIGATORIEDAD' ? (
          <HojaObligatoriedad
            categoria={cat.nombre}
            magnitud={asociacion.nombre}
            obligatoria={asociacion.obligatoria}
            guardando={guardando}
            onConfirmar={() => void cambiarObligatoriedad(asociacion)}
            onCancelar={() => setHoja(null)}
          />
        ) : null}
        {hoja?.tipo === 'QUITAR' ? (
          <HojaQuitar
            categoria={cat.nombre}
            magnitud={asociacion.nombre}
            nHechos={m ? m.n_hechos : null}
            guardando={guardando}
            onQuitar={() => void quitar(asociacion)}
            onCancelar={() => setHoja(null)}
          />
        ) : null}
        {hoja?.tipo === 'RENOMBRAR' && m ? (
          <HojaRenombrarMagnitud
            magnitud={m.nombre}
            guardando={guardando}
            errorNombre={errorNombre}
            onLimpiarError={() => setErrorNombre(null)}
            onGuardar={(n) => void renombrar(m, n)}
            onCancelar={() => setHoja(null)}
          />
        ) : null}
        {hoja?.tipo === 'DESHABILITAR' && m ? (
          <HojaDeshabilitar
            magnitud={m.nombre}
            filas={filasImpacto(hoja.afectadas, usosDe(m), hoja.previas, p.ruta)}
            cambiado={hoja.cambiado}
            guardando={guardando}
            onDeshabilitar={() => void confirmarDeshabilitar(m, hoja.afectadas)}
            onCancelar={() => setHoja(null)}
          />
        ) : null}
        {hoja?.tipo === 'REHABILITAR' && m ? (
          <HojaRehabilitar magnitud={m.nombre} guardando={guardando} onRehabilitar={() => void rehabilitar(m)} onCancelar={() => setHoja(null)} />
        ) : null}
      </>
    );
  }

  const inmersiva = vista?.tipo === 'SELECTOR' || vista?.tipo === 'NUEVA' || vista?.tipo === 'ORDEN' || hoja !== null;
  return { seccion, pantalla, inmersiva };
}
