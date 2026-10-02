// ============================================================
// GAPTO MOBILE 2027
// Fichero: MagnitudesCategoria.tsx
// Ruta: mobile/src/components/MagnitudesCategoria.tsx
// Descripción: Controlador de las magnitudes de una categoría en Ajustes › Categorías (F05-D020; F09 §12.97.10; lámina SET-MAG v0.1). Hook `useMagnitudesCategoria` que la pantalla de detalle llama siempre: devuelve la SECCIÓN (para el ScrollView del detalle), la PANTALLA a mostrar en lugar del detalle (selector del catálogo o ficha) y si la tarea es inmersiva (oculta la barra inferior). Las asociaciones se leen del árbol (GET /v1/categorias, con `asociacion_id`); el catálogo (GET /v1/magnitudes) se carga al desplegar la sección y aporta `n_hechos` y las categorías de cada magnitud. Cada comando usa la identidad cargada (asociacion_id + magnitud_id + obligatoria_actual; row_version de la magnitud) y, tras confirmar, recarga árbol y catálogo. Conflictos (VERSION_DESFASADA, ASOCIACION_YA_EXISTE, ASOCIACION_NO_EXISTE, CONJUNTO_MAGNITUDES_DESFASADO): se cierra la tarea, se recarga y se avisa «Las magnitudes de <categoría> han cambiado…» (M16), sin reintento automático. INDETERMINADO: se recarga antes de cualquier repetición; nunca se duplica.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1: sección, añadir existente, obligatoriedad, quitar y conflictos)
// ============================================================

import React, { useCallback, useEffect, useState } from 'react';

import type { ClienteApi, Respuesta } from '../api/cliente';
import type { CategoriaNodo, MagnitudCategoria } from '../domain/categoria';
import type { MagnitudCatalogo } from '../domain/magnitud';
import { FichaMagnitud } from './FichaMagnitud';
import { HojaAnadirExistente, HojaObligatoriedad, HojaQuitar } from './HojasMagnitud';
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

type CargaCatalogo = { fase: 'CARGANDO' } | { fase: 'OK'; magnitudes: MagnitudCatalogo[] } | { fase: 'ERROR' };
type Vista = null | { tipo: 'SELECTOR' } | { tipo: 'FICHA'; asociacionId: string };
type HojaAbierta = null | { tipo: 'ANADIR'; magnitud: MagnitudCatalogo } | { tipo: 'OBLIGATORIEDAD' } | { tipo: 'QUITAR' };
export type AvisoMagnitudes = { titulo: string; texto: string } | null;

export function useMagnitudesCategoria(p: {
  cliente: ClienteApi;
  categoria: CategoriaNodo | null;
  /** Recarga el árbol SIN pasar por «cargando» (la vista no parpadea). */
  recargarArbol: () => Promise<void>;
}) {
  const [abierta, setAbierta] = useState(false);
  const [catalogo, setCatalogo] = useState<CargaCatalogo>({ fase: 'CARGANDO' });
  const [vista, setVista] = useState<Vista>(null);
  const [hoja, setHoja] = useState<HojaAbierta>(null);
  const [aviso, setAviso] = useState<AvisoMagnitudes>(null);
  const [guardando, setGuardando] = useState(false);
  const cat = p.categoria;
  const catId = cat?.id ?? null;

  useEffect(() => {
    setAbierta(false);
    setVista(null);
    setHoja(null);
    setAviso(null);
  }, [catId]);

  const cargarCatalogo = useCallback(async () => {
    setCatalogo({ fase: 'CARGANDO' });
    const r = await p.cliente.catalogoMagnitudes();
    setCatalogo(r.tipo === 'OK' ? { fase: 'OK', magnitudes: r.datos.magnitudes } : { fase: 'ERROR' });
  }, [p.cliente]);

  useEffect(() => {
    if (abierta || vista) void cargarCatalogo();
  }, [abierta, vista?.tipo, catId]);

  const recargarTodo = async () => {
    await Promise.all([p.recargarArbol(), cargarCatalogo()]);
  };

  /** Trata el resultado de un comando: OK -> `alOk` y recarga; rechazo -> cierra, avisa y recarga (nunca reintenta). */
  const tratar = async (r: Respuesta<unknown>, alOk: () => void) => {
    if (r.tipo === 'OK') {
      alOk();
      setAviso(null);
      await recargarTodo();
      return;
    }
    setHoja(null);
    setVista(null);
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

  const anadir = (m: MagnitudCatalogo, obligatoria: boolean) =>
    conGuardado(async () => {
      if (!cat) return;
      const r = await p.cliente.asociarMagnitud(cat.id, { origen: 'EXISTENTE', magnitud_id: m.id, obligatoria });
      await tratar(r, () => {
        setHoja(null);
        setVista(null);
      });
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
      await tratar(r, () => {
        setHoja(null);
        setVista(null);
      });
    });

  const fase: FaseCatalogo = catalogo.fase;
  const magnitudesCatalogo = catalogo.fase === 'OK' ? catalogo.magnitudes : [];
  const delCatalogo = (id: string) => magnitudesCatalogo.find((m) => m.id === id) ?? null;

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
          onCerrar={() => { setHoja(null); setVista(null); }}
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
  } else if (cat && asociacion) {
    const enCatalogo = delCatalogo(asociacion.magnitud_id);
    pantalla = (
      <>
        <FichaMagnitud
          categoria={cat.nombre}
          asociacion={asociacion}
          onAtras={() => { setHoja(null); setVista(null); }}
          onObligatoriedad={() => setHoja({ tipo: 'OBLIGATORIEDAD' })}
          onQuitar={() => setHoja({ tipo: 'QUITAR' })}
        />
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
            nHechos={enCatalogo ? enCatalogo.n_hechos : null}
            guardando={guardando}
            onQuitar={() => void quitar(asociacion)}
            onCancelar={() => setHoja(null)}
          />
        ) : null}
      </>
    );
  }

  return { seccion, pantalla, inmersiva: vista?.tipo === 'SELECTOR' || hoja !== null };
}
