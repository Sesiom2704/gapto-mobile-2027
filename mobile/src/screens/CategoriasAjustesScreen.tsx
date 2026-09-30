// ============================================================
// GAPTO MOBILE 2027
// Fichero: CategoriasAjustesScreen.tsx
// Ruta: mobile/src/screens/CategoriasAjustesScreen.tsx
// Descripción: Ajustes › Categorías (F09 §12.97.4; lámina SET-CAT v1.0 S01, S03, I01). Lista con el mismo patrón de niveles y migas que el selector y filtro Activas / Todas (Activas por defecto: decisión de ejecución). Las desactivadas se muestran con tratamiento `inactive` (texto secundario) Y el texto «Desactivada», nunca solo con color. Hueco de icono reservado en cada fila (reserva para NULL o clave desconocida). Un nodo con subcategorías entra en su nivel; dentro del nivel, «Ver detalle de “<nombre>”» abre su detalle; una hoja abre su detalle al tocarla. Detalle: ámbito, estado, presupuesto por defecto e icono; la fila «Icono» abre el selector de iconos y guarda con el `row_version` vigente (permitido en desactivadas). Conflicto de versión: se recarga y se muestra el estado actual, sin reintento automático. Indeterminado: se recarga antes de cualquier repetición. El alta (CREATE-M) y los selectores son tareas inmersivas: ocultan la barra inferior.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S6-WIRE+UI (este mandato), commit 2): acciones EDIT-* en el detalle (lámina SET-CAT S03–S05; mandato §5) y Editar orden en la lista (S06; D-UI-01). Cada comando usa el `row_version` del estado cargado. Conflicto (VERSION_DESFASADA, CONJUNTO_HERMANOS_DESFASADO): se recarga y se muestra el estado actual, nunca se reintenta solo. INDETERMINADO: se recarga antes de cualquier repetición; nunca se duplica. Renombrar: colisión junto al nombre. Mover: selector en modo AJUSTES sin el propio subárbol ni padres desactivados; elegir la ubicación actual no envía nada. Cambiar ámbito: GET /uso antes de confirmar y `confirmacion_uso` igual a ese uso; ante CAMBIO_AMBITO_REQUIERE_CONFIRMACION se muestra el uso nuevo (`detalle.efectos_activos`) y se pide confirmar otra vez; sin coherencia padre/hijo (Q3). Desactivar: con subcategorías activas (N del árbol cargado, subárbol completo) solo RAMA o Cancelar; sin ellas confirmación simple SOLO_SI_SIN_HIJOS_ACTIVOS; si aun así llega CATEGORIA_TIENE_HIJOS_ACTIVOS se recarga y se ofrece RAMA. Reactivar: solo este nodo (sin cascada). Editar orden: conjunto COMPLETO de hermanos (activos y desactivados) y UNA llamada a POST /v1/categorias/reordenar; sin cambios no se envía nada («Sin cambios», decisión de ejecución); nunca /{id}/orden.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import type { Respuesta } from '../api/cliente';
import { BotonPrimario, CabeceraNavegacion, EstadoDato, Segmentado } from '../components/Basicos';
import { HojaAmbito, HojaDesactivar, HojaReactivar, HojaRenombrar, UsoCarga } from '../components/HojasCategoria';
import { BotonSecundario, CargaArbol, IconoCategoriaVista, SelectorCategorias } from '../components/SelectorCategorias';
import { SelectorIconos } from '../components/SelectorIconos';
import { Ambito, CategoriaNodo, ancestros, construirArbol, descendientes, hijosDe, mismoOrden, subcategoriasActivas } from '../domain/categoria';
import { iconoDe } from '../theme/iconosCategoria';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { EditarOrdenScreen } from './EditarOrdenScreen';
import { NuevaCategoriaScreen } from './NuevaCategoriaScreen';

export type Filtro = 'ACTIVAS' | 'TODAS';

export const ETIQUETA_AMBITO: Record<Ambito, string> = { GASTO: 'Gasto', INGRESO: 'Ingreso', AMBOS: 'Ambos' };

export const MSG_VERSION = 'La categoría ha cambiado desde que la abriste. Te mostramos su estado actual.';
export const MSG_INDETERMINADO = 'No se ha podido confirmar el cambio. Revisa el estado actual antes de repetirlo.';

export const MSG_SIN_CAMBIOS_ORDEN = 'Sin cambios: el orden ya era ese.';
export const MSG_CONJUNTO_DESFASADO = 'Las categorías de este nivel han cambiado mientras editabas. Te mostramos el orden actual.';
export const MSG_MOVER_PRESUPUESTO =
  'No se puede mover: forma parte de un presupuesto que ya no está en borrador. Sigue en su ubicación actual.';
export const MSG_MOVER_PADRE_DESHABILITADO =
  'El destino, o alguna categoría por encima, está desactivado. Te mostramos el estado actual; elige otro destino.';
export const MSG_MOVER_PADRE_NO_VALIDO = 'El destino ya no es válido. Te mostramos el estado actual; elige otro destino.';
export const MSG_REACTIVAR_ANCESTRO =
  'No se puede reactivar: una categoría por encima está desactivada. Reactiva antes esa categoría.';
export const MSG_NOMBRE_DUPLICADO = 'Ya hay una categoría activa con ese nombre en el mismo nivel.';
export const MSG_HIJOS_ACTIVOS = 'Ahora tiene subcategorías activas. Revisa cuáles antes de desactivarla.';

type Tarea =
  | { tipo: 'ALTA'; padre: string | null }
  | { tipo: 'ICONO' | 'RENOMBRAR' | 'MOVER' | 'AMBITO' | 'DESACTIVAR' | 'REACTIVAR' }
  | { tipo: 'ORDEN'; padre: string | null }
  | null;

/** Aviso común de un resultado: OK sin aviso; indeterminado y conflicto de versión con su texto; el resto, `undefined`. */
function avisoComun(r: Respuesta<unknown>): string | null | undefined {
  if (r.tipo === 'OK') return null;
  if (r.tipo === 'INDETERMINADO') return MSG_INDETERMINADO;
  if (r.codigo === 'VERSION_DESFASADA') return MSG_VERSION;
  return undefined;
}

/** Aviso final de un comando: el común o, si es otro rechazo, su mensaje (o el de reserva). */
function avisoFinal(r: Respuesta<unknown>, reserva: string): string | null {
  const comun = avisoComun(r);
  if (comun !== undefined) return comun;
  return r.tipo === 'RECHAZADO' ? r.mensaje || reserva : null;
}

export function CategoriasAjustesScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  onAtras: () => void;
  onInmersiva: (inmersiva: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [carga, setCarga] = useState<CargaArbol>({ fase: 'CARGANDO' });
  const [filtro, setFiltro] = useState<Filtro>('ACTIVAS');
  const [nivel, setNivel] = useState<string | null>(null);
  const [detalleId, setDetalleId] = useState<string | null>(null);
  const [tarea, setTarea] = useState<Tarea>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [errorNombre, setErrorNombre] = useState<string | null>(null);
  const [uso, setUso] = useState<UsoCarga>({ fase: 'CARGANDO' });
  const [usoCambiado, setUsoCambiado] = useState(false);

  const cargar = useCallback(async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.arbolCategorias();
    if (r.tipo !== 'OK') return setCarga({ fase: 'ERROR' });
    setCarga({ fase: 'OK', arbol: construirArbol(r.datos.categorias) });
  }, [p.cliente]);
  useEffect(() => {
    void cargar();
  }, [cargar]);
  useEffect(() => {
    p.onInmersiva(tarea !== null);
  }, [tarea]);

  const arbol = carga.fase === 'OK' ? carga.arbol : null;
  const visible = (n: CategoriaNodo) => filtro === 'TODAS' || n.enabled;
  const hijosVisibles = (id: string | null) => (arbol ? hijosDe(arbol, id).filter(visible) : []);
  const detalle = arbol && detalleId ? arbol.porId.get(detalleId) ?? null : null;
  const nodoNivel = arbol && nivel ? arbol.porId.get(nivel) ?? null : null;
  // Mover: destino habilitado y fuera del propio subárbol (los desactivados y su rama no se listan).
  const excluidos = new Set(arbol && detalle ? [detalle.id, ...descendientes(arbol, detalle.id).map((n) => n.id)] : []);
  const destinoValido = (n: CategoriaNodo) => n.enabled && !excluidos.has(n.id);

  // Un nivel o detalle que deja de existir tras recargar vuelve a la raíz (sin inventar estado).
  useEffect(() => {
    if (!arbol) return;
    if (nivel && !arbol.porId.has(nivel)) setNivel(null);
    if (detalleId && !arbol.porId.has(detalleId)) setDetalleId(null);
  }, [arbol]);

  const guardarIcono = async (iconKey: string | null) => {
    if (!detalle || guardando) return;
    setGuardando(true);
    const r = await p.cliente.iconoCategoria(detalle.id, { row_version: detalle.row_version, icon_key: iconKey });
    setGuardando(false);
    setTarea(null);
    if (r.tipo === 'OK') setAviso(null);
    else if (r.tipo === 'INDETERMINADO') setAviso(MSG_INDETERMINADO);
    else if (r.codigo === 'VERSION_DESFASADA') setAviso(MSG_VERSION);
    else if (r.codigo === 'ICONO_CATEGORIA_NO_VALIDO') setAviso('Ese icono no está disponible. Elige otro o «Sin icono».');
    else setAviso(r.mensaje || 'No se ha podido guardar el icono.');
    void cargar(); // siempre se muestra el estado persistido; nunca se reintenta solo
  };

  /** Cierra la tarea, deja el aviso y recarga SIEMPRE: se muestra el estado persistido; nunca se reintenta solo. */
  const cerrarYRecargar = (msg: string | null) => {
    setTarea(null);
    setAviso(msg);
    void cargar();
  };

  const renombrar = async (nombre: string) => {
    if (!detalle || guardando) return;
    setGuardando(true);
    const r = await p.cliente.renombrarCategoria(detalle.id, { row_version: detalle.row_version, nombre });
    setGuardando(false);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CATEGORIA_NOMBRE_DUPLICADO') return setErrorNombre(MSG_NOMBRE_DUPLICADO);
    cerrarYRecargar(avisoFinal(r, 'No se ha podido renombrar.'));
  };

  const mover = async (destino: string | null) => {
    if (!detalle || guardando) return;
    if (destino === detalle.parent_id) return setTarea(null); // ubicación actual: no se envía nada
    setGuardando(true);
    const r = await p.cliente.moverCategoria(detalle.id, { row_version: detalle.row_version, parent_id: destino });
    setGuardando(false);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CATEGORIA_MOVIMIENTO_BLOQUEADO_POR_PRESUPUESTO') return cerrarYRecargar(MSG_MOVER_PRESUPUESTO);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CATEGORIA_PADRE_DESHABILITADO') return cerrarYRecargar(MSG_MOVER_PADRE_DESHABILITADO);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CATEGORIA_PADRE_NO_VALIDO') return cerrarYRecargar(MSG_MOVER_PADRE_NO_VALIDO);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CATEGORIA_NOMBRE_DUPLICADO')
      return cerrarYRecargar('No se puede mover: ya hay una categoría activa con ese nombre en el destino.');
    cerrarYRecargar(avisoFinal(r, 'No se ha podido mover la categoría.'));
  };

  const cargarUso = async (id: string) => {
    setUso({ fase: 'CARGANDO' });
    const r = await p.cliente.usoCategoria(id);
    setUso(r.tipo === 'OK' ? { fase: 'OK', efectos: r.datos.efectos_activos } : { fase: 'ERROR' });
  };

  const abrirAmbito = () => {
    if (!detalle) return;
    setUsoCambiado(false);
    setTarea({ tipo: 'AMBITO' });
    void cargarUso(detalle.id);
  };

  const cambiarAmbito = async (ambito: Ambito) => {
    if (!detalle || guardando || uso.fase !== 'OK') return;
    setGuardando(true);
    const r = await p.cliente.cambiarAmbitoCategoria(detalle.id, { row_version: detalle.row_version, ambito, confirmacion_uso: uso.efectos });
    setGuardando(false);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CAMBIO_AMBITO_REQUIERE_CONFIRMACION') {
      // El uso cambió: se muestra el vigente y se pide confirmar otra vez (nunca se reenvía solo).
      const vigente = r.detalle?.efectos_activos;
      setUsoCambiado(true);
      if (vigente && typeof vigente === 'object') setUso({ fase: 'OK', efectos: vigente as Record<string, number> });
      else void cargarUso(detalle.id);
      return;
    }
    cerrarYRecargar(avisoFinal(r, 'No se ha podido cambiar el ámbito.'));
  };

  const desactivar = async (modo: 'RAMA' | 'SOLO_SI_SIN_HIJOS_ACTIVOS') => {
    if (!detalle || guardando) return;
    setGuardando(true);
    const r = await p.cliente.desactivarCategoria(detalle.id, { row_version: detalle.row_version, modo });
    setGuardando(false);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CATEGORIA_TIENE_HIJOS_ACTIVOS') {
      // Subcategorías activas que el árbol cargado no mostraba: se recarga y la hoja ofrece RAMA.
      setAviso(MSG_HIJOS_ACTIVOS);
      void cargar();
      return;
    }
    cerrarYRecargar(avisoFinal(r, 'No se ha podido desactivar.'));
  };

  const reactivar = async () => {
    if (!detalle || guardando) return;
    setGuardando(true);
    const r = await p.cliente.reactivarCategoria(detalle.id, { row_version: detalle.row_version });
    setGuardando(false);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CATEGORIA_PADRE_DESHABILITADO') return cerrarYRecargar(MSG_REACTIVAR_ANCESTRO);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CATEGORIA_NOMBRE_DUPLICADO')
      return cerrarYRecargar(`No se puede reactivar: ya hay una categoría activa llamada «${detalle.nombre}» en el mismo nivel. Renombra una de las dos antes.`);
    cerrarYRecargar(avisoFinal(r, 'No se ha podido reactivar.'));
  };

  const guardarOrden = async (padre: string | null, orden: CategoriaNodo[]) => {
    if (!arbol || guardando) return;
    // Sin cambios: no se envía nada (decisión de ejecución).
    if (mismoOrden(orden, hijosDe(arbol, padre))) return cerrarYRecargar(MSG_SIN_CAMBIOS_ORDEN);
    setGuardando(true);
    const r = await p.cliente.reordenarCategorias({ parent_id: padre, hermanos: orden.map((n) => ({ id: n.id, row_version: n.row_version })) });
    setGuardando(false);
    if (r.tipo === 'RECHAZADO' && r.codigo === 'CONJUNTO_HERMANOS_DESFASADO') return cerrarYRecargar(MSG_CONJUNTO_DESFASADO);
    cerrarYRecargar(avisoFinal(r, 'No se ha podido guardar el orden.'));
  };

  // ------------------------------------------------------------------ tareas inmersivas
  if (tarea?.tipo === 'ALTA' && arbol) {
    return (
      <NuevaCategoriaScreen
        cliente={p.cliente}
        nuevoId={p.nuevoId}
        arbol={arbol}
        padreInicial={tarea.padre}
        onRecargarArbol={cargar}
        onCancelar={() => setTarea(null)}
        onCreada={(padre) => {
          setTarea(null);
          setDetalleId(null);
          setNivel(padre);
          void cargar();
        }}
      />
    );
  }

  if (tarea?.tipo === 'ORDEN' && arbol) {
    const padre = tarea.padre;
    const nodoPadre = padre ? arbol.porId.get(padre) : undefined;
    return (
      <EditarOrdenScreen
        migas={['Todas', ...(nodoPadre ? [...ancestros(arbol, nodoPadre.id), nodoPadre].map((n) => n.nombre) : [])]}
        hermanos={hijosDe(arbol, padre)}
        guardando={guardando}
        onGuardar={(orden) => void guardarOrden(padre, orden)}
        onCancelar={() => setTarea(null)}
      />
    );
  }

  // ------------------------------------------------------------------ detalle
  if (detalle && arbol) {
    const padre = detalle.parent_id ? arbol.porId.get(detalle.parent_id) : undefined;
    const ruta = [...ancestros(arbol, detalle.id), detalle].map((n) => n.nombre).join(' › ');
    const icono = iconoDe(detalle.icon_key);
    return (
      <View testID="detalle-categoria" style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraNavegacion
          titulo={detalle.nombre}
          atras={{ etiqueta: padre?.nombre ?? 'Categorías', onPress: () => { setDetalleId(null); setAviso(null); } }}
          testIDAtras="detalle-atras"
        />
        <ScrollView contentContainerStyle={{ paddingBottom: inset.bottom + espacio.xl }}>
          <View style={s.cabDetalle}>
            <IconoCategoriaVista iconKey={detalle.icon_key} tamano={22} testID="detalle-icono-vista" />
            <View style={{ flex: 1 }}>
              <Text style={[tipo.titleMedium, { color: detalle.enabled ? c.textPrimary : c.textSecondary }]}>{detalle.nombre}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>{ruta}</Text>
            </View>
          </View>
          {aviso ? (
            <View testID="detalle-aviso" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
              <Ionicons name="alert-circle-outline" size={18} color={c.warning} />
              <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{aviso}</Text>
            </View>
          ) : null}
          <FilaDato etiqueta="Ámbito" valor={ETIQUETA_AMBITO[detalle.ambito]} testID="detalle-ambito" />
          <FilaDato etiqueta="Estado" valor={detalle.enabled ? 'Activa' : 'Desactivada'} testID="detalle-estado" />
          <FilaDato etiqueta="Presupuesto por defecto" valor={detalle.presupuestable_default ? 'Sí' : 'No'} testID="detalle-presupuesto" />
          <Pressable
            testID="detalle-icono"
            accessibilityRole="button"
            accessibilityLabel={`Icono: ${icono?.etiqueta ?? 'Sin asignar'}. Cambiar icono`}
            onPress={() => setTarea({ tipo: 'ICONO' })}
            style={[s.filaDato, { borderBottomColor: c.separator }]}
          >
            <Text style={[tipo.body, { color: c.textSecondary, flex: 1 }]}>Icono</Text>
            {icono ? <Ionicons name={icono.glifo} size={18} color={c.textSecondary} /> : null}
            <Text style={[tipo.body, { color: c.textPrimary }]}>{icono?.etiqueta ?? 'Sin asignar'}</Text>
            <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
          </Pressable>
          <Text accessibilityRole="header" style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>Acciones</Text>
          <FilaAccion testID="accion-renombrar" titulo="Renombrar" onPress={() => { setErrorNombre(null); setTarea({ tipo: 'RENOMBRAR' }); }} />
          <FilaAccion testID="accion-mover" titulo="Mover a otra categoría" onPress={() => setTarea({ tipo: 'MOVER' })} />
          <FilaAccion testID="accion-ambito" titulo="Cambiar ámbito" onPress={abrirAmbito} />
          {detalle.enabled ? (
            <FilaAccion testID="accion-desactivar" titulo="Desactivar" critica onPress={() => setTarea({ tipo: 'DESACTIVAR' })} />
          ) : (
            <FilaAccion testID="accion-reactivar" titulo="Reactivar" onPress={() => setTarea({ tipo: 'REACTIVAR' })} />
          )}
          <Text style={[tipo.caption, s.nota, { color: c.textSecondary }]}>
            Renombrar corrige el nombre también en lo ya registrado. Si cambia su significado, crea otra categoría y desactiva esta.
          </Text>
        </ScrollView>
        {tarea?.tipo === 'ICONO' ? (
          <SelectorIconos
            nombreCategoria={detalle.nombre}
            inicial={detalle.icon_key}
            accion="Guardar icono"
            guardando={guardando}
            onAccion={(k) => void guardarIcono(k)}
            onCerrar={() => setTarea(null)}
          />
        ) : null}
        {tarea?.tipo === 'RENOMBRAR' ? (
          <HojaRenombrar
            nodo={detalle}
            guardando={guardando}
            errorNombre={errorNombre}
            onLimpiarError={() => setErrorNombre(null)}
            onGuardar={(n) => void renombrar(n)}
            onCancelar={() => setTarea(null)}
          />
        ) : null}
        {tarea?.tipo === 'MOVER' ? (
          <SelectorCategorias
            testID="selector-mover"
            titulo={`Mover ${detalle.nombre}`}
            modo="AJUSTES"
            carga={carga}
            esVisible={destinoValido}
            esSeleccionable={destinoValido}
            motivo={() => null}
            seleccionadaId={detalle.parent_id}
            opcionRaiz={{
              etiqueta: 'Categoría principal',
              subtitulo: 'Sin categoría superior (raíz)',
              seleccionada: detalle.parent_id === null,
              onPress: () => void mover(null),
              testID: 'mover-raiz',
            }}
            onElegir={(n) => void mover(n.id)}
            onCerrar={() => setTarea(null)}
            onReintentar={() => void cargar()}
          />
        ) : null}
        {tarea?.tipo === 'AMBITO' ? (
          <HojaAmbito
            nodo={detalle}
            uso={uso}
            usoCambiado={usoCambiado}
            guardando={guardando}
            onReintentarUso={() => void cargarUso(detalle.id)}
            onConfirmar={(a) => void cambiarAmbito(a)}
            onCancelar={() => setTarea(null)}
          />
        ) : null}
        {tarea?.tipo === 'DESACTIVAR' ? (
          <HojaDesactivar
            nodo={detalle}
            activas={subcategoriasActivas(arbol, detalle.id)}
            guardando={guardando}
            onDesactivar={(m) => void desactivar(m)}
            onCancelar={() => setTarea(null)}
          />
        ) : null}
        {tarea?.tipo === 'REACTIVAR' ? (
          <HojaReactivar
            nodo={detalle}
            inactivas={descendientes(arbol, detalle.id).filter((n) => !n.enabled).length}
            guardando={guardando}
            onReactivar={() => void reactivar()}
            onCancelar={() => setTarea(null)}
          />
        ) : null}
      </View>
    );
  }

  // ------------------------------------------------------------------ lista por niveles
  const filas = hijosVisibles(nivel);
  const migas = arbol && nodoNivel ? [...ancestros(arbol, nodoNivel.id), nodoNivel] : [];
  const padreNivel = nodoNivel && arbol && nodoNivel.parent_id ? arbol.porId.get(nodoNivel.parent_id) : undefined;
  return (
    <View testID="pantalla-categorias" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion
        titulo={nodoNivel ? nodoNivel.nombre : 'Categorías'}
        atras={{ etiqueta: nodoNivel ? padreNivel?.nombre ?? 'Categorías' : 'Ajustes', onPress: () => (nodoNivel ? setNivel(nodoNivel.parent_id) : p.onAtras()) }}
        testIDAtras="categorias-atras"
        derecha={
          <Pressable testID="categorias-mas" accessibilityRole="button" accessibilityLabel="Nueva categoría" hitSlop={8} onPress={() => setTarea({ tipo: 'ALTA', padre: nodoNivel?.enabled ? nodoNivel.id : null })}>
            <Ionicons name="add" size={24} color={c.accent} />
          </Pressable>
        }
      />
      <View style={s.filtro}>
        <Segmentado<Filtro>
          testIDBase="filtro"
          etiquetaGrupo="Mostrar"
          opciones={[{ valor: 'ACTIVAS', etiqueta: 'Activas' }, { valor: 'TODAS', etiqueta: 'Todas' }]}
          valor={filtro}
          onCambiar={setFiltro}
        />
      </View>
      {nodoNivel ? (
        <View testID="categorias-migas" style={[s.migas, { borderBottomColor: c.separator }]}>
          <Pressable testID="categorias-miga-todas" accessibilityRole="link" onPress={() => setNivel(null)} hitSlop={8}>
            <Text style={[tipo.footnote, { color: c.accent }]}>Todas</Text>
          </Pressable>
          {migas.map((m, i) => (
            <React.Fragment key={m.id}>
              <Text style={[tipo.footnote, { color: c.textSecondary }]}> › </Text>
              {i < migas.length - 1 ? (
                <Pressable testID={`categorias-miga-${m.id}`} accessibilityRole="link" onPress={() => setNivel(m.id)} hitSlop={8}>
                  <Text style={[tipo.footnote, { color: c.accent }]}>{m.nombre}</Text>
                </Pressable>
              ) : (
                <Text style={[tipo.footnote, { color: c.textPrimary }]}>{m.nombre}</Text>
              )}
            </React.Fragment>
          ))}
        </View>
      ) : null}
      <ScrollView contentContainerStyle={{ paddingBottom: espacio.xl }}>
        {carga.fase === 'CARGANDO' ? <View style={s.estado}><EstadoDato estado="CARGANDO" /></View> : null}
        {carga.fase === 'ERROR' ? (
          <Pressable testID="categorias-error" accessibilityRole="button" onPress={() => void cargar()} style={[s.estado, { minHeight: TACTIL_MIN }]}>
            <EstadoDato estado="ERROR_CARGA" detalle="No hemos podido cargar tus categorías · Tocar para reintentar" />
          </Pressable>
        ) : null}
        {aviso ? (
          <View testID="lista-aviso" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface, marginTop: espacio.m }]}>
            <Ionicons name="alert-circle-outline" size={18} color={c.warning} />
            <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{aviso}</Text>
          </View>
        ) : null}
        {nodoNivel ? (
          <Fila
            testID="ver-detalle-nivel"
            iconKey={nodoNivel.icon_key}
            titulo={`Ver detalle de «${nodoNivel.nombre}»`}
            enfasis
            onPress={() => setDetalleId(nodoNivel.id)}
          />
        ) : null}
        {carga.fase === 'OK' && filas.length === 0 && !nodoNivel ? (
          <View testID="categorias-vacio" style={s.estado}>
            <Text style={[tipo.body, { color: c.textSecondary }]}>
              {filtro === 'ACTIVAS' ? 'No tienes categorías activas en este nivel.' : 'Aún no tienes categorías.'}
            </Text>
          </View>
        ) : null}
        {filas.map((n) => {
          const nHijos = hijosVisibles(n.id).length;
          const sub = [
            n.enabled ? null : 'Desactivada',
            n.ambito === 'INGRESO' ? 'Ingreso' : n.ambito === 'AMBOS' ? 'Gasto e ingreso' : null,
            nHijos > 0 ? `${nHijos} ${nHijos === 1 ? 'subcategoría' : 'subcategorías'}` : null,
          ].filter(Boolean).join(' · ');
          return (
            <Fila
              key={n.id}
              testID={`fila-${n.id}`}
              iconKey={n.icon_key}
              titulo={n.nombre}
              subtitulo={sub || undefined}
              inactiva={!n.enabled}
              onPress={() => (nHijos > 0 ? setNivel(n.id) : setDetalleId(n.id))}
            />
          );
        })}
      </ScrollView>
      <View style={[s.pie, { borderTopColor: c.separator }]}>
        {arbol && hijosDe(arbol, nivel).length > 1 ? (
          <BotonSecundario testID="editar-orden-abrir" titulo="Editar orden" onPress={() => { setAviso(null); setTarea({ tipo: 'ORDEN', padre: nivel }); }} />
        ) : null}
        <BotonPrimario testID="nueva-categoria" titulo="Nueva categoría" onPress={() => setTarea({ tipo: 'ALTA', padre: nodoNivel?.enabled ? nodoNivel.id : null })} />
      </View>
    </View>
  );
}

function Fila(p: { testID: string; iconKey: string | null; titulo: string; subtitulo?: string; inactiva?: boolean; enfasis?: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={[p.titulo, p.subtitulo].filter(Boolean).join('. ')}
      onPress={p.onPress}
      style={({ pressed }) => [s.fila, { borderBottomColor: c.separator, opacity: pressed ? 0.7 : 1 }]}
    >
      <IconoCategoriaVista iconKey={p.iconKey} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[tipo.body, { color: p.enfasis ? c.accent : p.inactiva ? c.textSecondary : c.textPrimary, fontWeight: p.enfasis ? '600' : '400' }]}>{p.titulo}</Text>
        {p.subtitulo ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{p.subtitulo}</Text> : null}
      </View>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

function FilaAccion(p: { testID: string; titulo: string; critica?: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.titulo}
      onPress={p.onPress}
      style={({ pressed }) => [s.filaDato, { borderBottomColor: c.separator, opacity: pressed ? 0.7 : 1 }]}
    >
      <Text style={[tipo.body, { color: p.critica ? c.critical : c.textPrimary, flex: 1 }]}>{p.titulo}</Text>
      {p.critica ? null : <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />}
    </Pressable>
  );
}

function FilaDato(p: { etiqueta: string; valor: string; testID: string }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} accessible accessibilityLabel={`${p.etiqueta}: ${p.valor}`} style={[s.filaDato, { borderBottomColor: c.separator }]}>
      <Text style={[tipo.body, { color: c.textSecondary, flex: 1 }]}>{p.etiqueta}</Text>
      <Text style={[tipo.body, { color: c.textPrimary }]}>{p.valor}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  filtro: { paddingHorizontal: espacio.l, paddingVertical: espacio.s },
  migas: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', paddingHorizontal: espacio.l, paddingVertical: espacio.m, borderBottomWidth: StyleSheet.hairlineWidth },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.l, paddingVertical: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  filaDato: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 4, paddingHorizontal: espacio.l, borderBottomWidth: StyleSheet.hairlineWidth },
  cabDetalle: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, padding: espacio.l },
  aviso: { flexDirection: 'row', alignItems: 'flex-start', gap: espacio.s, borderRadius: radio.m, padding: espacio.m, marginHorizontal: espacio.l, marginBottom: espacio.m },
  estado: { padding: espacio.l },
  seccion: { paddingHorizontal: espacio.l, paddingTop: espacio.l, paddingBottom: espacio.xs },
  nota: { paddingHorizontal: espacio.l, paddingTop: espacio.m },
  pie: { padding: espacio.l, gap: espacio.s, borderTopWidth: StyleSheet.hairlineWidth },
});
