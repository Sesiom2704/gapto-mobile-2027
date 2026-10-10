// ============================================================
// GAPTO MOBILE 2027
// Fichero: PlantillasAjustesScreen.tsx
// Ruta: mobile/src/screens/PlantillasAjustesScreen.tsx
// Descripción: Ajustes › Plantillas (F05-03 J2 §2.5; F05 §45.3, §46.3 A7; lámina SET-PLT / REG-PLT / HOME-QA v0.2 S01–S05; REG-DYN S05). Lista S01 con el texto de la lámina y los grupos «EN INICIO · n DE 3» (orden de Inicio), «OTRAS PLANTILLAS» y «DESACTIVADAS»; cada fila con su resumen y «No disponible» cuando el servidor avisa de un campo que hoy no se puede usar. Formulario S02 ampliado (S05 de REG-DYN): Nombre (nunca autocompletado), Tipo Gasto/Ingreso, Tercero, Categoría (filtrada por tipo), Contexto, Proponer cuenta (las del registro de ese tipo), Proponer presupuesto, Mostrar en Inicio con nombre corto e icono («El de la categoría»). S03 límite de 3 con «Elegir cuál quitar»; S04 nombre repetido con «Ir a la plantilla»; S05 detalle con desactivar / reactivar (no vuelve a Inicio sola) y orden de Inicio. VERSION_DESFASADA → recarga y aviso, sin reintento automático. Los UUID del alta de la plantilla y del acceso se sellan al abrir el formulario.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.5)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { AccionRapida, ClienteApi, Contexto, CuentaElegible, CuentaPago, Plantilla, Respuesta, Tercero, TiposRegistro } from '../api/cliente';
import { BotonPrimario, BotonTexto, CabeceraNavegacion, Chip, EstadoDato, Segmentado } from '../components/Basicos';
import { FormularioContexto, SelectorContexto } from '../components/Contextos';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoSelector, CampoTexto, estilosFormulario as ef, FilaLista, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { BotonSecundario, SelectorCategorias } from '../components/SelectorCategorias';
import { SelectorIconos } from '../components/SelectorIconos';
import { SelectorTercero } from '../components/SelectorTercero';
import { Arbol, ancestros, construirArbol, elegible, motivoNoSeleccionable, visibleEnRegistro } from '../domain/categoria';
import { isoLocal } from '../domain/fechas';
import { agruparPlantillas, huecosLibres, MAX_ACCESOS, resumenPlantilla, textoHuecos } from '../domain/maestros';
import {
  accionDe,
  contenidoPlantilla,
  faltaPlantilla,
  FORMULARIO_PLANTILLA_NUEVO,
  FormularioPlantilla,
  formularioPlantillaDesde,
  LONGITUD_NOMBRE_ACCESO,
  LONGITUD_NOMBRE_PLANTILLA,
  moverAcceso,
  planAcceso,
  TEXTO_CHECK_PLANTILLA,
  TEXTO_DESACTIVADA_PLANTILLA,
  TEXTO_INTRO_PLANTILLAS,
  TEXTO_LIMITE,
  TEXTO_SOLO_NUEVOS_PLANTILLA,
  textoEnInicio,
  textoFaltaPlantilla,
  textoNombreRepetido,
  tipoDePlantilla,
} from '../domain/plantillas';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

export const TEXTO_VERSION_PLANTILLA = 'Esta plantilla ha cambiado mientras la editabas. Hemos cargado la versión actual. Revisa y guarda de nuevo.';
export const TEXTO_INDETERMINADO_PLANTILLA = 'No se ha podido confirmar el cambio. Revisa el estado actual antes de repetirlo.';
/** DERIVADO. */
export const TEXTO_REACTIVADA_PLANTILLA = 'Reactivada. Para que salga en Inicio, actívalo en «Mostrar en Inicio».';
/** DERIVADO. */
export const TEXTO_VACIO_PLANTILLAS = 'Aún no tienes plantillas. Crea una aquí o guárdala al registrar un gasto.';
export const TEXTO_NO_DISPONIBLE = 'No disponible';

type Datos = {
  plantillas: Plantilla[];
  acciones: AccionRapida[];
  tipos: TiposRegistro;
  arbol: Arbol;
  terceros: Tercero[];
  contextos: Contexto[];
  cuentasGasto: CuentaPago[];
  cuentasIngreso: CuentaElegible[];
};
type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | ({ fase: 'OK' } & Datos);
type Vista = { v: 'LISTA' } | { v: 'DETALLE'; id: string } | { v: 'FORM'; id: string | null };
type Overlay = null | 'CATEGORIA' | 'TERCERO' | 'CONTEXTO' | 'NUEVO_CONTEXTO' | 'ICONO';
type AvisoP = (NonNullable<AvisoCaja> & { irA?: string; elegirQuitar?: boolean }) | null;

export function PlantillasAjustesScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  onAtras: () => void;
  onInmersiva: (x: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [vista, setVista] = useState<Vista>({ v: 'LISTA' });
  const [form, setForm] = useState<FormularioPlantilla>(FORMULARIO_PLANTILLA_NUEVO);
  const [aviso, setAviso] = useState<AvisoP>(null);
  const [overlay, setOverlay] = useState<Overlay>(null);
  const [ocupado, setOcupado] = useState(false);
  const ids = useRef<{ plantilla: string; accion: string } | null>(null);

  const cargar = useCallback(
    async (silencioso = false): Promise<Datos | null> => {
      if (!silencioso) setCarga({ fase: 'CARGANDO' });
      const hoy = isoLocal(p.ahora());
      const [pl, pr, a, te, cx, cg, ci] = await Promise.all([
        p.cliente.listarPlantillas(),
        p.cliente.listarPreferencias(),
        p.cliente.arbolCategorias(),
        p.cliente.listarTerceros(),
        p.cliente.listarContextos(),
        p.cliente.cuentasPago(hoy),
        p.cliente.cuentasElegibles('INGRESO', hoy),
      ]);
      if (pl.tipo !== 'OK' || pr.tipo !== 'OK' || a.tipo !== 'OK' || te.tipo !== 'OK' || cx.tipo !== 'OK' || cg.tipo !== 'OK' || ci.tipo !== 'OK') {
        if (!silencioso) setCarga({ fase: 'ERROR' });
        return null;
      }
      const d: Datos = {
        plantillas: pl.datos.plantillas,
        acciones: pl.datos.acciones,
        tipos: pr.datos.tipos,
        arbol: construirArbol(a.datos.categorias),
        terceros: te.datos.terceros,
        contextos: cx.datos.contextos,
        cuentasGasto: cg.datos.cuentas,
        cuentasIngreso: ci.datos.cuentas,
      };
      setCarga({ fase: 'OK', ...d });
      return d;
    },
    [p.cliente, p.ahora],
  );
  useEffect(() => {
    void cargar();
  }, [cargar]);
  const inmersiva = vista.v === 'FORM';
  useEffect(() => {
    p.onInmersiva(inmersiva);
  }, [inmersiva]);
  useEffect(() => () => p.onInmersiva(false), []);

  const d = carga.fase === 'OK' ? carga : null;
  const porId = (id: string) => d?.plantillas.find((x) => x.id === id) ?? null;
  const tipoP = (x: Plantilla) => tipoDePlantilla(x, d?.tipos ?? null);

  // ---------------------------------------------------------------- nombres visibles
  const rutaCategoria = (id: string) => {
    const n = d?.arbol.porId.get(id);
    return d && n ? [...ancestros(d.arbol, id), n].map((x) => x.nombre).join(' › ') : null;
  };
  const nombreCategoria = (id: string) => d?.arbol.porId.get(id)?.nombre ?? null;
  const nombreCuenta = (id: string) => d?.cuentasGasto.find((x) => x.cuenta_id === id)?.nombre ?? d?.cuentasIngreso.find((x) => x.cuenta_id === id)?.nombre ?? null;
  const nombreTercero = (id: string) => d?.terceros.find((x) => x.id === id)?.nombre ?? null;
  const nombreContexto = (id: string) => d?.contextos.find((x) => x.id === id)?.nombre ?? null;
  const nombres = { categoria: nombreCategoria, cuenta: nombreCuenta, tercero: nombreTercero, contexto: nombreContexto };
  const avisoDe = (x: Plantilla, campo: string) => (x.avisos ?? []).some((a) => a.campo === campo);

  // ---------------------------------------------------------------- navegación
  const abrirForm = (x: Plantilla | null, a: AvisoP = null) => {
    ids.current = { plantilla: x?.id ?? p.nuevoId(), accion: p.nuevoId() }; // sellados al abrir: el reintento usa los MISMOS
    setForm(x && d ? formularioPlantillaDesde(x, accionDe(d.acciones, x.id), d.tipos) : FORMULARIO_PLANTILLA_NUEVO);
    setAviso(a);
    setOverlay(null);
    setVista({ v: 'FORM', id: x?.id ?? null });
  };
  const abrirDetalle = (id: string, a: AvisoP = null) => {
    setAviso(a);
    setOverlay(null);
    setVista({ v: 'DETALLE', id });
  };
  useEffect(() => {
    if (d && vista.v === 'DETALLE' && !porId(vista.id)) setVista({ v: 'LISTA' });
  }, [carga]);

  const avisoRechazo = (r: Respuesta<unknown>): AvisoP => {
    if (r.tipo === 'OK') return null;
    if (r.tipo === 'INDETERMINADO') return { tipo: 'AVISO', texto: TEXTO_INDETERMINADO_PLANTILLA };
    if (r.codigo === 'PLANTILLA_NOMBRE_REPETIDO') {
      const otra = typeof r.detalle?.plantilla_id === 'string' ? r.detalle.plantilla_id : undefined;
      return { tipo: 'AVISO', texto: textoNombreRepetido(form.nombre.trim()), irA: otra };
    }
    if (r.codigo === 'ACCION_LIMITE_ALCANZADO') return { tipo: 'AVISO', texto: TEXTO_LIMITE, elegirQuitar: true };
    if (r.codigo === 'VERSION_DESFASADA' || r.codigo === 'CONJUNTO_ACCIONES_DESFASADO') return { tipo: 'AVISO', texto: TEXTO_VERSION_PLANTILLA };
    return { tipo: 'AVISO', texto: r.mensaje || TEXTO_INDETERMINADO_PLANTILLA };
  };

  // ---------------------------------------------------------------- comandos
  const guardar = async () => {
    if (ocupado || vista.v !== 'FORM' || !d || !ids.current) return;
    if (faltaPlantilla(form).length > 0) return;
    const base = vista.id ? porId(vista.id) : null;
    setOcupado(true);
    setAviso(null);
    const contenido = contenidoPlantilla(form, d.tipos);
    const r = base
      ? await p.cliente.editarPlantilla(base.id, { row_version: base.row_version, ...contenido })
      : await p.cliente.altaPlantilla({ id: ids.current.plantilla, ...contenido });
    if (r.tipo !== 'OK') {
      const nd = await cargar(true);
      setOcupado(false);
      if (r.tipo === 'INDETERMINADO' && !base && nd?.plantillas.some((x) => x.id === ids.current!.plantilla)) {
        return abrirDetalle(ids.current.plantilla);
      }
      if (r.tipo === 'RECHAZADO' && r.codigo === 'VERSION_DESFASADA' && base && nd) {
        const actual = nd.plantillas.find((x) => x.id === base.id);
        if (actual) setForm(formularioPlantillaDesde(actual, accionDe(nd.acciones, actual.id), nd.tipos));
      }
      return setAviso(avisoRechazo(r));
    }
    const plantillaId = r.datos.plantilla.id;
    const plan = planAcceso(form, accionDe(d.acciones, plantillaId));
    let ra: Respuesta<unknown> | null = null;
    if (plan.tipo === 'ALTA') ra = await p.cliente.altaAccion({ id: ids.current.accion, plantilla_registro_id: plantillaId, nombre: plan.nombre, icono_key: plan.icono_key });
    if (plan.tipo === 'EDITAR') ra = await p.cliente.editarAccion(plan.accion.id, { row_version: plan.accion.row_version, nombre: plan.nombre, icono_key: plan.icono_key });
    if (plan.tipo === 'QUITAR') ra = await p.cliente.desactivarAccion(plan.accion.id, plan.accion.row_version);
    const nd = await cargar(true);
    setOcupado(false);
    if (ra && ra.tipo !== 'OK') {
      // La plantilla ya está guardada; el acceso no. Se sigue editando la guardada.
      const guardada = nd?.plantillas.find((x) => x.id === plantillaId) ?? null;
      if (guardada && nd) {
        ids.current = { plantilla: plantillaId, accion: ids.current.accion };
        setForm({ ...formularioPlantillaDesde(guardada, accionDe(nd.acciones, plantillaId), nd.tipos), enInicio: form.enInicio, nombreCorto: form.nombreCorto, iconoKey: form.iconoKey });
        setVista({ v: 'FORM', id: plantillaId });
      }
      return setAviso(avisoRechazo(ra));
    }
    abrirDetalle(plantillaId);
  };

  const cambiarEstado = async (x: Plantilla) => {
    if (ocupado) return;
    setOcupado(true);
    const r = x.enabled ? await p.cliente.desactivarPlantilla(x.id, x.row_version) : await p.cliente.reactivarPlantilla(x.id, x.row_version);
    await cargar(true);
    setOcupado(false);
    if (r.tipo === 'OK') return abrirDetalle(x.id, { tipo: 'OK', texto: x.enabled ? TEXTO_DESACTIVADA_PLANTILLA : TEXTO_REACTIVADA_PLANTILLA });
    abrirDetalle(x.id, avisoRechazo(r));
  };

  const mover = async (accion: AccionRapida, delta: -1 | 1, plantillaId: string) => {
    if (ocupado || !d) return;
    const orden = moverAcceso(d.acciones, accion.id, delta);
    if (!orden) return;
    setOcupado(true);
    const r = await p.cliente.reordenarAcciones(orden);
    await cargar(true);
    setOcupado(false);
    abrirDetalle(plantillaId, r.tipo === 'OK' ? null : avisoRechazo(r));
  };

  const quitarDeInicio = async (accion: AccionRapida, plantillaId: string) => {
    if (ocupado) return;
    setOcupado(true);
    const r = await p.cliente.desactivarAccion(accion.id, accion.row_version);
    await cargar(true);
    setOcupado(false);
    abrirDetalle(plantillaId, r.tipo === 'OK' ? null : avisoRechazo(r));
  };

  const bloqueAviso = (a: AvisoP, prefijo: string) =>
    a ? (
      <>
        <Caja testID={a.tipo === 'OK' ? `${prefijo}-aviso-ok` : `${prefijo}-aviso`} aviso={a} />
        {a.irA ? <BotonSecundario testID={`${prefijo}-ir`} titulo="Ir a la plantilla" onPress={() => abrirDetalle(a.irA!)} /> : null}
        {a.elegirQuitar ? <BotonSecundario testID={`${prefijo}-elegir-quitar`} titulo="Elegir cuál quitar" onPress={() => { setAviso(null); setVista({ v: 'LISTA' }); }} /> : null}
      </>
    ) : null;

  // ---------------------------------------------------------------- formulario (S02)
  if (vista.v === 'FORM' && d) {
    const base = vista.id ? porId(vista.id) : null;
    const faltas = faltaPlantilla(form);
    const falta = textoFaltaPlantilla(faltas);
    const t = form.tipo;
    const cuentas: { cuenta_id: string; nombre: string }[] = t === 'INGRESO' ? d.cuentasIngreso : t === 'GASTO' ? d.cuentasGasto : [];
    const accionActual = base ? accionDe(d.acciones, base.id) : null;
    const libres = huecosLibres(d.acciones) + (accionActual ? 1 : 0);
    const cambiar = (parche: Partial<FormularioPlantilla>) => setForm((f) => ({ ...f, ...parche }));
    const cambiarTipo = (nt: 'GASTO' | 'INGRESO') => {
      const n = form.categoriaId ? d.arbol.porId.get(form.categoriaId) : null;
      const lista = nt === 'INGRESO' ? d.cuentasIngreso : d.cuentasGasto;
      cambiar({
        tipo: nt,
        categoriaId: n && elegible(n, nt) ? form.categoriaId : null,
        cuentaId: form.cuentaId && lista.some((x) => x.cuenta_id === form.cuentaId) ? form.cuentaId : null,
      });
    };
    const cuentaGuardadaFuera = form.cuentaId !== null && !cuentas.some((x) => x.cuenta_id === form.cuentaId);
    return (
      <View testID="ajplt-form" style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraTarea
          titulo={base ? 'Editar plantilla' : 'Nueva plantilla'}
          testIDCancelar="ajplt-cancelar"
          onCancelar={() => (base ? abrirDetalle(base.id) : setVista({ v: 'LISTA' }))}
        />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {bloqueAviso(aviso, 'ajplt-form')}
          <Campo etiqueta="Nombre">
            <CampoTexto testID="ajplt-nombre" etiqueta="Nombre" marcador="Ej.: Compra semanal" valor={form.nombre} maximo={LONGITUD_NOMBRE_PLANTILLA} onCambiar={(x) => cambiar({ nombre: x })} />
          </Campo>
          <Campo etiqueta="Tipo">
            <Segmentado<'GASTO' | 'INGRESO'>
              testIDBase="ajplt-tipo"
              etiquetaGrupo="Tipo"
              opciones={[
                { valor: 'GASTO', etiqueta: 'Gasto' },
                { valor: 'INGRESO', etiqueta: 'Ingreso' },
              ]}
              valor={form.tipo}
              onCambiar={cambiarTipo}
            />
          </Campo>
          <Campo etiqueta="Tercero" opcional>
            <CampoSelector testID="ajplt-tercero" etiqueta="Tercero" valor={form.terceroId ? nombreTercero(form.terceroId) ?? 'Tercero no disponible' : null}
              marcador="No proponer" onPress={() => setOverlay('TERCERO')} />
          </Campo>
          <Campo etiqueta="Categoría" opcional>
            <CampoSelector testID="ajplt-categoria" etiqueta="Categoría" valor={form.categoriaId ? rutaCategoria(form.categoriaId) ?? 'Categoría no disponible' : null}
              marcador={t ? 'No proponer' : 'Elige antes el tipo'} onPress={() => (t ? setOverlay('CATEGORIA') : undefined)} />
          </Campo>
          <Campo etiqueta="Contexto" opcional>
            <CampoSelector testID="ajplt-contexto" etiqueta="Contexto" valor={form.contextoId ? nombreContexto(form.contextoId) ?? 'Contexto no disponible' : null}
              marcador="No proponer" onPress={() => setOverlay('CONTEXTO')} />
          </Campo>
          <Campo etiqueta="Proponer cuenta">
            <View style={ef.chips}>
              <Chip testID="ajplt-cuenta-no" etiqueta="No proponer" seleccionado={form.cuentaId === null} onPress={() => cambiar({ cuentaId: null })} />
              {cuentaGuardadaFuera ? (
                <Chip testID="ajplt-cuenta-actual" etiqueta={`${nombreCuenta(form.cuentaId!) ?? 'Cuenta actual'} · ${TEXTO_NO_DISPONIBLE}`} seleccionado onPress={() => undefined} />
              ) : null}
              {cuentas.map((x) => (
                <Chip key={x.cuenta_id} testID={`ajplt-cuenta-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={form.cuentaId === x.cuenta_id} onPress={() => cambiar({ cuentaId: x.cuenta_id })} />
              ))}
            </View>
          </Campo>
          <Campo etiqueta="Proponer «¿Cuenta para el presupuesto?»">
            <View style={ef.chips}>
              <Chip testID="ajplt-presu-no-proponer" etiqueta="No proponer" seleccionado={form.presupuestable === null} onPress={() => cambiar({ presupuestable: null })} />
              <Chip testID="ajplt-presu-true" etiqueta="Sí" seleccionado={form.presupuestable === true} onPress={() => cambiar({ presupuestable: true })} />
              <Chip testID="ajplt-presu-false" etiqueta="No" seleccionado={form.presupuestable === false} onPress={() => cambiar({ presupuestable: false })} />
            </View>
          </Campo>
          <Campo etiqueta="Mostrar en Inicio">
            <Segmentado<boolean>
              testIDBase="ajplt-inicio"
              etiquetaGrupo="Mostrar en Inicio"
              opciones={[
                { valor: true, etiqueta: 'Sí' },
                { valor: false, etiqueta: 'No' },
              ]}
              valor={form.enInicio}
              onCambiar={(v) => cambiar({ enInicio: v })}
            />
            <Text testID="ajplt-huecos" style={[tipo.footnote, { color: c.textSecondary }]}>{textoHuecos(Math.min(MAX_ACCESOS, libres))}</Text>
          </Campo>
          {form.enInicio ? (
            <>
              <Campo etiqueta="Nombre corto en Inicio">
                <CampoTexto testID="ajplt-nombre-corto" etiqueta="Nombre corto en Inicio" marcador={form.nombre.trim() || 'Ej.: Súper'} valor={form.nombreCorto}
                  maximo={LONGITUD_NOMBRE_ACCESO} onCambiar={(x) => cambiar({ nombreCorto: x })} />
              </Campo>
              <Campo etiqueta="Icono">
                <CampoSelector testID="ajplt-icono" etiqueta="Icono" valor={form.iconoKey} marcador="El de la categoría" onPress={() => setOverlay('ICONO')} />
              </Campo>
            </>
          ) : null}
          <Text testID="ajplt-check" style={[tipo.footnote, { color: faltas.includes('proponer') ? c.textPrimary : c.textSecondary }]}>{TEXTO_CHECK_PLANTILLA}</Text>
          {falta ? <Text testID="ajplt-falta" style={[tipo.footnote, { color: c.textSecondary }]}>{falta}</Text> : null}
          <BotonPrimario testID="ajplt-guardar" titulo={ocupado ? 'Guardando…' : 'Guardar'} cargando={ocupado} deshabilitado={faltas.length > 0}
            ayuda={falta ?? (faltas.length > 0 ? TEXTO_CHECK_PLANTILLA : undefined)} onPress={() => void guardar()} />
        </ScrollView>

        {overlay === 'CATEGORIA' && t ? (
          <SelectorCategorias
            testID="ajplt-selector"
            titulo="Elegir categoría"
            modo="REGISTRO"
            carga={{ fase: 'OK', arbol: d.arbol }}
            esVisible={(n) => visibleEnRegistro(d.arbol, n, t)}
            esSeleccionable={(n) => elegible(n, t)}
            motivo={(n) => motivoNoSeleccionable(n, t)}
            seleccionadaId={form.categoriaId}
            onElegir={(n) => {
              setOverlay(null);
              cambiar({ categoriaId: n.id });
            }}
            naturaleza={t}
            opcionRaiz={{
              etiqueta: 'No proponer',
              subtitulo: 'La plantilla no propone categoría',
              seleccionada: form.categoriaId === null,
              testID: 'ajplt-categoria-no',
              onPress: () => {
                setOverlay(null);
                cambiar({ categoriaId: null });
              },
            }}
            onCerrar={() => setOverlay(null)}
          />
        ) : null}
        {overlay === 'TERCERO' ? (
          <SelectorTercero
            cliente={p.cliente}
            nuevoId={p.nuevoId}
            seleccionadoId={form.terceroId}
            onElegir={(x) => {
              setOverlay(null);
              if (x && !d.terceros.some((y) => y.id === x.id)) setCarga({ ...d, fase: 'OK', terceros: [...d.terceros, x] });
              cambiar({ terceroId: x?.id ?? null });
            }}
            onCerrar={() => setOverlay(null)}
          />
        ) : null}
        {overlay === 'CONTEXTO' ? (
          <SelectorContexto
            cliente={p.cliente}
            seleccionadoId={form.contextoId}
            onElegir={(x) => {
              setOverlay(null);
              if (x && !d.contextos.some((y) => y.id === x.id)) setCarga({ ...d, fase: 'OK', contextos: [...d.contextos, x] });
              cambiar({ contextoId: x?.id ?? null });
            }}
            onNuevo={() => setOverlay('NUEVO_CONTEXTO')}
            onCerrar={() => setOverlay(null)}
          />
        ) : null}
        {overlay === 'NUEVO_CONTEXTO' ? (
          <FormularioContexto
            cliente={p.cliente}
            nuevoId={p.nuevoId}
            existente={null}
            tituloBoton="Crear y usar"
            onHecho={(x) => {
              setOverlay(null);
              setCarga({ ...d, fase: 'OK', contextos: [...d.contextos, x] });
              cambiar({ contextoId: x.id });
            }}
            onCancelar={() => setOverlay('CONTEXTO')}
          />
        ) : null}
        {overlay === 'ICONO' ? (
          <SelectorIconos
            nombreCategoria={form.nombreCorto.trim() || form.nombre.trim() || 'la plantilla'}
            inicial={form.iconoKey}
            accion="Usar este icono"
            onAccion={(k) => {
              setOverlay(null);
              cambiar({ iconoKey: k });
            }}
            onCerrar={() => setOverlay(null)}
          />
        ) : null}
      </View>
    );
  }

  // ---------------------------------------------------------------- detalle (S05)
  if (vista.v === 'DETALLE' && d) {
    const x = porId(vista.id);
    if (!x) return null;
    const accion = accionDe(d.acciones, x.id);
    const tp = tipoP(x);
    const fila = (testID: string, etiqueta: string, valor: string, noDisp = false, apagado = false) => (
      <View testID={testID} style={[s.filaDato, { borderBottomColor: c.borderDefault }]}>
        <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{etiqueta}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: espacio.s, flexShrink: 1 }}>
          <Text testID={`${testID}-valor`} style={[tipo.subheadline, { color: apagado ? c.textSecondary : c.textPrimary, textAlign: 'right', flexShrink: 1 }]}>{valor}</Text>
          {noDisp ? <EtiquetaNoDisponible testID={`${testID}-no-disponible`} /> : null}
        </View>
      </View>
    );
    return (
      <View testID="ajplt-detalle" style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraNavegacion
          titulo={x.nombre}
          atras={{ etiqueta: 'Plantillas', onPress: () => setVista({ v: 'LISTA' }) }}
          testIDAtras="ajplt-detalle-atras"
          derecha={x.enabled ? <BotonTexto testID="ajplt-editar" titulo="Editar" onPress={() => abrirForm(x)} /> : undefined}
        />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Tarjeta>
            {fila('ajplt-det-tipo', 'Tipo', tp === 'INGRESO' ? 'Ingreso' : tp === 'GASTO' ? 'Gasto' : 'No disponible')}
            {fila('ajplt-det-tercero', 'Tercero', x.tercero_id ? nombreTercero(x.tercero_id) ?? 'Tercero no disponible' : 'No propone', avisoDe(x, 'tercero'), !x.tercero_id)}
            {fila('ajplt-det-categoria', 'Categoría', x.categoria_id ? rutaCategoria(x.categoria_id) ?? 'Categoría no disponible' : 'No propone', avisoDe(x, 'categoria'), !x.categoria_id)}
            {fila('ajplt-det-contexto', 'Contexto', x.entidad_id ? nombreContexto(x.entidad_id) ?? 'Contexto no disponible' : 'No propone', avisoDe(x, 'contexto'), !x.entidad_id)}
            {fila('ajplt-det-cuenta', 'Cuenta', x.cuenta_default_id ? nombreCuenta(x.cuenta_default_id) ?? 'Cuenta no disponible' : 'No propone', avisoDe(x, 'cuenta'), !x.cuenta_default_id)}
            {fila('ajplt-det-presupuesto', 'Presupuesto', x.presupuestable_default === null ? 'No propone' : x.presupuestable_default ? 'Sí' : 'No', false, x.presupuestable_default === null)}
            {fila('ajplt-det-inicio', 'En Inicio', textoEnInicio(d.acciones, x.id))}
          </Tarjeta>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SOLO_NUEVOS_PLANTILLA}</Text>
          {accion ? (
            <View style={{ flexDirection: 'row', gap: espacio.s, flexWrap: 'wrap' }}>
              <BotonTexto testID="ajplt-mover-antes" titulo="Mover antes" onPress={() => void mover(accion, -1, x.id)} />
              <BotonTexto testID="ajplt-mover-despues" titulo="Mover después" onPress={() => void mover(accion, 1, x.id)} />
              <BotonTexto testID="ajplt-quitar-inicio" titulo="Quitar de Inicio" onPress={() => void quitarDeInicio(accion, x.id)} />
            </View>
          ) : null}
          {x.enabled ? (
            <BotonSecundario testID="ajplt-desactivar" titulo="Desactivar" critico onPress={() => void cambiarEstado(x)} />
          ) : (
            <BotonSecundario testID="ajplt-reactivar" titulo="Reactivar" onPress={() => void cambiarEstado(x)} />
          )}
          {bloqueAviso(aviso, 'ajplt')}
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- lista (S01)
  const grupos = d ? agruparPlantillas(d.plantillas, d.acciones) : null;
  const filaPlantilla = (x: Plantilla, i: number, n: number, nombreFila?: string) => (
    <FilaLista
      key={x.id}
      testID={`ajplt-fila-${x.id}`}
      titulo={nombreFila ?? x.nombre}
      detalle={resumenPlantilla(x, nombres)}
      apagada={!x.enabled}
      ultima={i === n - 1}
      derecha={(x.avisos ?? []).length > 0 ? <EtiquetaNoDisponible testID={`ajplt-fila-${x.id}-no-disponible`} /> : undefined}
      onPress={() => abrirDetalle(x.id)}
    />
  );
  return (
    <View testID="pantalla-plantillas" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion
        titulo="Plantillas"
        atras={{ etiqueta: 'Ajustes', onPress: p.onAtras }}
        testIDAtras="ajplt-atras"
        derecha={
          <Pressable testID="ajplt-nueva" accessibilityRole="button" accessibilityLabel="Nueva plantilla" hitSlop={8} onPress={() => d && abrirForm(null)} style={ef.mas}>
            <Ionicons name="add" size={24} color={c.accent} />
          </Pressable>
        }
      />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Text testID="ajplt-intro" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_INTRO_PLANTILLAS}</Text>
        {carga.fase === 'CARGANDO' ? <EstadoDato testID="ajplt-cargando" estado="CARGANDO" /> : null}
        {carga.fase === 'ERROR' ? (
          <Pressable testID="ajplt-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {d && d.plantillas.length === 0 ? <Text testID="ajplt-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_VACIO_PLANTILLAS}</Text> : null}
        {grupos && grupos.enInicio.length > 0 ? (
          <View testID="ajplt-grupo-inicio" style={{ gap: espacio.s }}>
            <RotuloGrupo testID="ajplt-grupo-inicio-titulo" texto={`En Inicio · ${grupos.enInicio.length} de ${MAX_ACCESOS}`} />
            <Tarjeta>{grupos.enInicio.map((g, i) => filaPlantilla(g.plantilla, i, grupos.enInicio.length))}</Tarjeta>
          </View>
        ) : null}
        {grupos && grupos.otras.length > 0 ? (
          <View testID="ajplt-grupo-otras" style={{ gap: espacio.s }}>
            <RotuloGrupo texto="Otras plantillas" />
            <Tarjeta>{grupos.otras.map((x, i) => filaPlantilla(x, i, grupos.otras.length))}</Tarjeta>
          </View>
        ) : null}
        {grupos && grupos.desactivadas.length > 0 ? (
          <View testID="ajplt-grupo-desactivadas" style={{ gap: espacio.s }}>
            <RotuloGrupo texto="Desactivadas" />
            <Tarjeta>{grupos.desactivadas.map((x, i) => filaPlantilla(x, i, grupos.desactivadas.length))}</Tarjeta>
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

function EtiquetaNoDisponible({ testID }: { testID?: string }) {
  const { c } = useTema();
  return (
    <View testID={testID} style={[s.etiqueta, { backgroundColor: c.partialSurface, borderColor: c.warning }]}>
      <Text style={[tipo.caption, { color: c.warning }]}>{TEXTO_NO_DISPONIBLE}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  filaDato: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.s, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.m, borderBottomWidth: StyleSheet.hairlineWidth },
  etiqueta: { borderRadius: radio.pill, borderWidth: 1, paddingHorizontal: espacio.s, paddingVertical: 1 },
});
