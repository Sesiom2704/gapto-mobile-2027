// ============================================================
// GAPTO MOBILE 2027
// Fichero: ActividadScreen.tsx
// Ruta: mobile/src/screens/ActividadScreen.tsx
// Descripción: Día a día › Actividad v0 (F05 §49.4 A7/A8, §49.5 R11/R12; D-SRCH-06..09, 12, 13; P-ACT-01..03; F09 DAY-01; lámina SRCH-ACT-AFI v0.2 B1–B13 y C4). Solo lectura. Cabecera «Día a día» con pestañas Actividad / Estadísticas («Próximamente», atenuada), periodo ▾ (este mes por defecto; mes anterior, otro mes, entre fechas), búsqueda y Filtros (recuento de grupos). Lista agrupada por día con el título calculado en la línea principal, la secundaria con lo que el título no dice, el importe con signo solo si describe la magnitud (ingresos «+» neutros, transferencia sin signo) y «Total · reparto sin indicar | parcial» cuando procede; sin hora. Búsqueda en todo el historial con el alcance explícito, agrupada por mes y con el motivo de la coincidencia cuando no es evidente; «Cancelar» restaura periodo, filtros y scroll (DAY-Q08). Filtros por tipo, categoría (con subcategorías), cuenta, tercero y contexto con «Limpiar» y «Ver N resultados»; línea de filtros activos con «Limpiar». Detalle rápido de solo lectura (gasto, ingreso, transferencia) con altura estable. Estados de carga (barras), error con «Reintentar» (nunca «no hay registros») y vacío. Modo «Registros de <tercero>» (C4): filtrada por el tercero, todo el historial y sin totales. Las hojas son inmersivas (`onInmersiva`): el velo cubre la barra inferior.
// Versión: 0.1.0 (F05-05 K3 §2.6)
// Versión: 0.2.0 (F05-05 K4-C; acta K4-A2 P12, deuda K-1, CC-05-8 / DAY-Q08): «Cancelar» restaura el desplazamiento cuando la lista posterior a la cancelación ya está cargada (`onContentSizeChange` con la ref `restaurarY`), en lugar de un `setTimeout` que actuaba sobre el esqueleto y se recortaba a 0. Un solo intento; la carga, los filtros y el contrato no cambian.
// Versión: 0.3.0 (F05-06 K-7; F05 §51.8, F09 §12.104 B1/B4): la fila y la cabecera del detalle muestran el icono de la categoría (`categoria.icon_key`); transferencia con el icono de intercambio; «Varias» y sin categoría, icono de reserva. Fondo neutro (tinte C3b pendiente). Nada más cambia.
// Versión: 0.4.0 (F05-06 M2-B §B1; lámina DEV A3, A4, B1, B2; D-DEV-01, 06, 07; P-DEV-03, 04): devolución contextual. El detalle de un gasto que no es devolución ofrece «Registrar devolución» (abre la tarea de devolución, `onRegistrarDevolucion`); el de una compra con devoluciones las lista (tocar abre la devolución) con lo devuelto y el neto derivado; el de una devolución muestra «Devolución de: <compra> ›» (vuelve a la compra), el abono (recibido en <cuenta> o pendiente) y, si está pendiente, «Registrar abono» (hoja B2). La fila de una devolución con el abono pendiente admite el swipe «Cobrado» (en un contenedor que captura el movimiento horizontal, para que el Pressable de la fila no se quede el gesto) y la acción de accesibilidad «Cobrado»; los dos abren la misma hoja con confirmación de cuenta y fecha. `abrir` abre el detalle de un hecho desde fuera (ida y vuelta tras registrar). Tras un abono se recargan la lista y el detalle.
// Versión: 0.5.0 (F05-06 M2-C; acta M2 iPhone O-1; P-DEV-04): pista visual del swipe «Cobrado». Al arrastrar a la izquierda la fila sigue al dedo (con tope `TOPE_SWIPE`) y deja ver detrás la franja «Confirmar abono»; al superar `UMBRAL_SWIPE` la franja pasa al color de acento. Al soltar, la fila vuelve con animación; por encima del umbral se abre la misma hoja de siempre. La franja es decorativa (oculta a VoiceOver); el toque, el scroll vertical, la acción accesible «Cobrado» y las demás filas no cambian.
// Versión: 0.6.0 (F05-06 M3 §B1; lámina REP v0.2 E5/E6, P-REP-03/04): el detalle de un gasto que no es devolución lee su reparto (GET /v1/hechos/{id}/reparto, solo si la raíz pasa `onCorregirReparto`) y ofrece «Pendiente con <persona>» por cada parte con deuda y «Corregir reparto» cuando el servidor lo considera corregible; si no lo es, no se ofrece nada que el motor no admita. Ambos se abren fuera de la pantalla (tareas inmersivas de la raíz).
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, PanResponder, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, DetalleActividad, FilaActividad, TipoActividad } from '../api/cliente';
import { AbonoHoja } from '../components/AbonoHoja';
import { BotonPrimario, BotonTexto, Chip } from '../components/Basicos';
import { Hoja } from '../components/HojasCategoria';
import { BotonSecundario, CargaArbol, IconoCategoriaVista, SelectorCategorias } from '../components/SelectorCategorias';
import {
  agrupar,
  consulta,
  etiquetasFiltros,
  Filtros,
  gruposActivos,
  importeFila,
  marcaReparto,
  mesDelPeriodo,
  NOMBRE_FILTRO_TIPO,
  Periodo,
  secundariaFila,
  SIN_FILTROS,
  textoAlcance,
  textoCoincidencia,
  textoPeriodo,
  textoTuParte,
  tituloFila,
  tituloTransferencia,
} from '../domain/actividad';
import { construirArbol } from '../domain/categoria';
import { nombreCorto, ofreceRegistrarAbono, ofreceRegistrarDevolucion, TEXTO_NETO, textoDevolucionDe } from '../domain/devolucion';
import { ayer, ddmmaaaaAIso, diaMesAnioIso, diaMesIso, isoLocal, mesAnioIso, mesDesplazadoIso } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import type { RepartoDeHecho } from '../domain/reparto';
import { filtrar } from '../domain/maestros';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; filas: FilaActividad[]; siguiente: string | null; total: number };
type HojaAbierta =
  | null
  | { h: 'PERIODO' }
  | { h: 'OTRO_MES'; mes: string }
  | { h: 'ENTRE_FECHAS'; desde: string; hasta: string }
  | { h: 'FILTROS' }
  | { h: 'F_CATEGORIA' }
  | { h: 'F_LISTA'; campo: 'cuenta' | 'tercero' | 'contexto' }
  | { h: 'DETALLE'; id: string }
  | { h: 'ABONO'; dev: { id: string; titulo: string; importe: string; origenId: string }; volverA: string | null };
type Opcion = { id: string; nombre: string; detalle?: string };

export const TEXTO_ERROR = 'No se ha podido cargar la actividad';
export const TEXTO_ERROR_DETALLE = 'Revisa la conexión. Tus registros no se han perdido.';
export const TEXTO_EDICION = 'Para cambiar este registro hará falta la edición (prevista en F05-06).';
export const TEXTO_ENTRE_CUENTAS_DETALLE = 'No es un gasto ni un ingreso: tu dinero cambia de cuenta.';
export const TEXTO_MES_NATURAL = 'El mes es el natural mientras F08 no defina el mes financiero (día de inicio en Ajustes).';
const PAUSA_MS = 300;

export function ActividadScreen(p: {
  cliente: ClienteApi;
  ahora: () => Date;
  refresco?: number;
  onRegistrar?: () => void;
  onInmersiva?: (x: boolean) => void;
  /** C4: «Registros de <tercero>» (filtrada por el tercero, todo el historial, sin totales). */
  tercero?: { id: string; nombre: string; onAtras: () => void; onLimpiar?: () => void } | null;
  /** F05-06 M2: «Registrar devolución» desde el detalle de un gasto (tarea inmersiva fuera de la pantalla). */
  onRegistrarDevolucion?: (origenId: string) => void;
  /** F05-06 M2: identidad nueva para «Registrar abono». */
  nuevoId?: () => string;
  /** F05-06 M2: abre el detalle de un hecho desde fuera (ida y vuelta tras registrar una devolución). */
  abrir?: { id: string; clave: number } | null;
  /** F05-06 M3: «Corregir reparto» y «Pendiente con <persona>» desde el detalle de un gasto. */
  onCorregirReparto?: (hechoId: string) => void;
  onPendienteCon?: (t: { terceroId: string; nombre: string }) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoy = useMemo(() => p.ahora(), [p.ahora]);
  const hoyIso = isoLocal(hoy);
  const ayerIso = isoLocal(ayer(hoy));
  const inicialFiltros: Filtros = p.tercero ? { ...SIN_FILTROS, tercero: { id: p.tercero.id, nombre: p.tercero.nombre } } : SIN_FILTROS;
  const inicialPeriodo: Periodo = p.tercero ? { tipo: 'TODO' } : { tipo: 'ESTE_MES' };
  const [periodo, setPeriodo] = useState<Periodo>(inicialPeriodo);
  const [filtros, setFiltros] = useState<Filtros>(inicialFiltros);
  const [buscando, setBuscando] = useState(false);
  const [texto, setTexto] = useState('');
  const [textoVigente, setTextoVigente] = useState('');
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [hoja, setHoja] = useState<HojaAbierta>(null);
  const [borrador, setBorrador] = useState<Filtros>(inicialFiltros);
  const [recuento, setRecuento] = useState<number | null>(null);
  const [arbol, setArbol] = useState<CargaArbol>({ fase: 'CARGANDO' });
  const [opciones, setOpciones] = useState<{ cuenta: Opcion[]; tercero: Opcion[]; contexto: Opcion[] } | null>(null);
  const [reparto, setReparto] = useState<RepartoDeHecho | null>(null);
  const [detalle, setDetalle] = useState<{ fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; d: DetalleActividad }>({ fase: 'CARGANDO' });
  const [cargandoMas, setCargandoMas] = useState(false);
  const peticion = useRef(0);
  const scroll = useRef<ScrollView | null>(null);
  const desplazamiento = useRef(0);
  const guardado = useRef<{ periodo: Periodo; filtros: Filtros; y: number } | null>(null);
  // K4-C (P12): desplazamiento pendiente de restaurar tras «Cancelar», y la petición vigente al cancelar. Se aplica
  // una sola vez cuando la lista POSTERIOR a la cancelación ya está cargada (nunca sobre el esqueleto ni sobre los
  // resultados de la búsqueda que aún se ven hasta que se relanza la carga).
  const restaurarY = useRef<{ y: number; desde: number } | null>(null);

  useEffect(() => {
    p.onInmersiva?.(hoja !== null);
  }, [hoja]);
  useEffect(() => () => p.onInmersiva?.(false), []);

  // Búsqueda: tras una pausa se aplica el texto vigente.
  useEffect(() => {
    const t = setTimeout(() => setTextoVigente(buscando ? texto.trim() : ''), PAUSA_MS);
    return () => clearTimeout(t);
  }, [texto, buscando]);

  const cargar = useCallback(async () => {
    const n = ++peticion.current;
    setCarga({ fase: 'CARGANDO' });
    if (buscando && textoVigente === '') return setCarga({ fase: 'OK', filas: [], siguiente: null, total: 0 });
    const r = await p.cliente.actividad(consulta(periodo, filtros, hoyIso, buscando ? textoVigente : null));
    if (n !== peticion.current) return;
    setCarga(r.tipo === 'OK' ? { fase: 'OK', filas: r.datos.filas, siguiente: r.datos.siguiente, total: r.datos.total } : { fase: 'ERROR' });
  }, [p.cliente, periodo, filtros, buscando, textoVigente, hoyIso]);
  useEffect(() => {
    void cargar();
  }, [cargar, p.refresco]);

  const cargarMas = async () => {
    if (carga.fase !== 'OK' || !carga.siguiente || cargandoMas) return;
    setCargandoMas(true);
    const n = peticion.current;
    const r = await p.cliente.actividad({ ...consulta(periodo, filtros, hoyIso, buscando ? textoVigente : null), cursor: carga.siguiente });
    setCargandoMas(false);
    if (n !== peticion.current || r.tipo !== 'OK') return;
    setCarga({ fase: 'OK', filas: [...carga.filas, ...r.datos.filas], siguiente: r.datos.siguiente, total: r.datos.total });
  };

  // ---------------------------------------------------------------- búsqueda (DAY-Q08)
  const abrirBusqueda = () => {
    guardado.current = { periodo, filtros, y: desplazamiento.current };
    restaurarY.current = null;
    setTexto('');
    setTextoVigente('');
    setBuscando(true);
  };
  const cancelarBusqueda = () => {
    const g = guardado.current;
    setBuscando(false);
    setTexto('');
    setTextoVigente('');
    if (g) {
      setPeriodo(g.periodo);
      setFiltros(g.filtros);
      restaurarY.current = { y: g.y, desde: peticion.current };
    }
  };
  // Un solo intento sobre la lista ya cargada; si el contenido es más corto que y, el ScrollView recorta.
  const restaurarDesplazamiento = () => {
    const r = restaurarY.current;
    if (!r || carga.fase !== 'OK' || peticion.current <= r.desde) return;
    restaurarY.current = null;
    scroll.current?.scrollTo({ y: r.y, animated: false });
  };

  // ---------------------------------------------------------------- filtros (DAY-Q09)
  const abrirFiltros = async () => {
    setBorrador(filtros);
    setHoja({ h: 'FILTROS' });
    if (opciones === null) {
      const [cu1, cu2, cu3, te, cx] = await Promise.all([
        p.cliente.cuentasElegibles('GASTO', hoyIso),
        p.cliente.cuentasElegibles('INGRESO', hoyIso),
        p.cliente.cuentasElegibles('TRANSFERENCIA_ORIGEN', hoyIso),
        p.cliente.listarTerceros(),
        p.cliente.listarContextos(),
      ]);
      const cuentas = new Map<string, Opcion>();
      for (const r of [cu1, cu2, cu3]) if (r.tipo === 'OK') for (const x of r.datos.cuentas) cuentas.set(x.cuenta_id, { id: x.cuenta_id, nombre: x.nombre });
      setOpciones({
        cuenta: [...cuentas.values()],
        tercero: te.tipo === 'OK' ? te.datos.terceros.map((t) => ({ id: t.id, nombre: t.nombre, detalle: t.enabled ? undefined : 'Inactivo' })) : [],
        contexto: cx.tipo === 'OK' ? cx.datos.contextos.map((x) => ({ id: x.id, nombre: x.nombre, detalle: x.enabled ? undefined : 'Desactivado' })) : [],
      });
    }
  };
  useEffect(() => {
    if (hoja?.h !== 'FILTROS') return;
    let vivo = true;
    setRecuento(null);
    void (async () => {
      const r = await p.cliente.actividad({ ...consulta(periodo, borrador, hoyIso, null), limite: 1 });
      if (vivo && r.tipo === 'OK') setRecuento(r.datos.total);
    })();
    return () => {
      vivo = false;
    };
  }, [hoja?.h, borrador, periodo]);
  const abrirCategoria = async () => {
    setHoja({ h: 'F_CATEGORIA' });
    if (arbol.fase !== 'OK') {
      const r = await p.cliente.arbolCategorias();
      setArbol(r.tipo === 'OK' ? { fase: 'OK', arbol: construirArbol(r.datos.categorias) } : { fase: 'ERROR' });
    }
  };
  const aplicarFiltros = () => {
    setFiltros(borrador);
    setHoja(null);
  };
  // C4: «Limpiar» deja la Actividad normal (Día a día sin filtros); si no, quita los filtros.
  const limpiar = () => (p.tercero?.onLimpiar ? p.tercero.onLimpiar() : setFiltros(p.tercero ? inicialFiltros : SIN_FILTROS));

  // ---------------------------------------------------------------- detalle (DAY-RULE-01/02)
  const abrirDetalle = async (id: string) => {
    setHoja({ h: 'DETALLE', id });
    setDetalle({ fase: 'CARGANDO' });
    setReparto(null);
    const r = await p.cliente.detalleActividad(id);
    setDetalle(r.tipo === 'OK' ? { fase: 'OK', d: r.datos } : { fase: 'ERROR' });
    if (r.tipo === 'OK' && p.onCorregirReparto && ofreceRegistrarDevolucion(r.datos)) {
      const rep = await p.cliente.repartoDeHecho(id);
      if (rep.tipo === 'OK') setReparto(rep.datos);
    }
  };
  useEffect(() => {
    if (p.abrir) void abrirDetalle(p.abrir.id);
  }, [p.abrir?.clave]);

  // ---------------------------------------------------------------- abono (D-DEV-07, P-DEV-04)
  const abrirAbono = (f: FilaActividad, volverA: string | null) => {
    if (!ofreceRegistrarAbono(f) || !f.devolucion_de) return;
    setHoja({ h: 'ABONO', volverA, dev: { id: f.id, titulo: textoDevolucionDe(f.devolucion_de), importe: f.importe_total ?? '0', origenId: f.devolucion_de.hecho_id } });
  };
  const cerrarAbono = (registrado: boolean, volverA: string | null) => {
    if (registrado) void cargar();
    if (volverA) void abrirDetalle(volverA);
    else setHoja(null);
  };

  const nGrupos = gruposActivos(filtros) - (p.tercero ? 1 : 0);
  const etiquetas = etiquetasFiltros(filtros);
  const grupos = carga.fase === 'OK' ? agrupar(carga.filas, buscando ? 'MES' : 'DIA', hoyIso, ayerIso) : [];

  return (
    <View testID="pantalla-actividad" style={{ flex: 1, backgroundColor: c.background }}>
      <View style={{ paddingTop: inset.top + espacio.s, paddingHorizontal: espacio.l, gap: espacio.s }}>
        {p.tercero ? (
          <View style={s.filaCabecera}>
            <BotonTexto testID="actividad-atras" titulo={`‹ ${p.tercero.nombre}`} onPress={p.tercero.onAtras} />
            <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{`Registros de ${p.tercero.nombre}`}</Text>
            <View style={{ width: 72 }} />
          </View>
        ) : buscando ? null : (
          <>
            <Text accessibilityRole="header" style={[tipo.titleLarge, { color: c.textPrimary }]}>Día a día</Text>
            <View style={s.pestanas}>
              <View testID="pestana-actividad" accessibilityRole="tab" accessibilityState={{ selected: true }} style={[s.pestana, { borderBottomColor: c.accent }]}>
                <Text style={[tipo.subheadline, { color: c.accent, fontWeight: '600' }]}>Actividad</Text>
              </View>
              <View testID="pestana-estadisticas" accessibilityRole="tab" accessibilityState={{ disabled: true, selected: false }} style={s.pestana}>
                <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Estadísticas · Próximamente</Text>
              </View>
            </View>
          </>
        )}
        {buscando ? (
          <View style={s.filaCabecera}>
            <TextInput
              testID="actividad-busqueda"
              accessibilityLabel="Buscar en la actividad"
              autoFocus
              value={texto}
              onChangeText={setTexto}
              placeholder="Tercero, categoría, contexto, nota o importe"
              placeholderTextColor={c.textSecondary}
              autoCorrect={false}
              style={[tipo.body, s.campo, { color: c.textPrimary, backgroundColor: c.surfaceSecondary }]}
            />
            <BotonTexto testID="actividad-cancelar-busqueda" titulo="Cancelar" onPress={cancelarBusqueda} />
          </View>
        ) : (
          <View style={s.filaCabecera}>
            <Pressable testID="actividad-periodo" accessibilityRole="button" accessibilityLabel={`Periodo: ${textoPeriodo(periodo, hoyIso)}`}
              onPress={() => setHoja({ h: 'PERIODO' })} style={s.boton}>
              <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{`${textoPeriodo(periodo, hoyIso)} ▾`}</Text>
            </Pressable>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: espacio.m }}>
              {p.tercero ? null : (
                <Pressable testID="actividad-buscar" accessibilityRole="button" accessibilityLabel="Buscar" hitSlop={8} onPress={abrirBusqueda}>
                  <Ionicons name="search" size={22} color={c.textPrimary} />
                </Pressable>
              )}
              <Pressable testID="actividad-filtros" accessibilityRole="button" onPress={() => void abrirFiltros()} hitSlop={8}>
                <Text style={[tipo.subheadline, { color: nGrupos > 0 ? c.accent : c.textPrimary, fontWeight: nGrupos > 0 ? '600' : '400' }]}>
                  {nGrupos + (p.tercero ? 1 : 0) > 0 ? `Filtros · ${nGrupos + (p.tercero ? 1 : 0)}` : 'Filtros'}
                </Text>
              </Pressable>
            </View>
          </View>
        )}
        {etiquetas.length > 0 && !buscando ? (
          <View testID="actividad-linea-filtros" style={s.lineaFiltros}>
            <Text style={[tipo.footnote, { color: c.textSecondary, flex: 1 }]} numberOfLines={1}>{etiquetas.join(' · ')}</Text>
            <BotonTexto testID="actividad-limpiar" titulo="Limpiar" onPress={limpiar} />
          </View>
        ) : null}
        {buscando && textoVigente !== '' ? (
          <View testID="actividad-alcance" style={[s.alcance, { backgroundColor: c.surfaceSecondary }]}>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{textoAlcance(textoVigente, carga.fase === 'OK' ? carga.total : null)}</Text>
          </View>
        ) : null}
      </View>

      <ScrollView
        ref={scroll}
        testID="actividad-lista"
        onScroll={(e) => {
          desplazamiento.current = e.nativeEvent.contentOffset.y;
        }}
        scrollEventThrottle={64}
        onContentSizeChange={restaurarDesplazamiento}
        contentContainerStyle={{ padding: espacio.l, paddingBottom: inset.bottom + espacio.xxl, gap: espacio.m }}
      >
        {carga.fase === 'CARGANDO' ? (
          <View testID="actividad-cargando" accessibilityLabel="Cargando" style={{ gap: espacio.s }}>
            {[0, 1, 2, 3].map((i) => (
              <View key={i} style={[s.barra, { backgroundColor: c.surfaceSecondary }]} />
            ))}
          </View>
        ) : null}
        {carga.fase === 'ERROR' ? (
          <View testID="actividad-error" accessibilityRole="alert" style={[s.tarjetaError, { backgroundColor: c.partialSurface }]}>
            <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{TEXTO_ERROR}</Text>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_ERROR_DETALLE}</Text>
            <BotonSecundario testID="actividad-reintentar" titulo="Reintentar" onPress={() => void cargar()} />
          </View>
        ) : null}
        {carga.fase === 'OK' && carga.filas.length === 0 && !(buscando && textoVigente === '') ? (
          <View testID="actividad-vacio" style={s.vacio}>
            {buscando ? (
              <>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary, textAlign: 'center' }]}>{`Nada coincide con «${textoVigente}»`}</Text>
                <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>
                  Busca por tercero, categoría, contexto, nota o importe (por ejemplo, 48,72).
                </Text>
              </>
            ) : nGrupos > 0 ? (
              <>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary, textAlign: 'center' }]}>Nada coincide con los filtros</Text>
                <BotonTexto testID="actividad-vacio-limpiar" titulo="Limpiar" onPress={limpiar} />
              </>
            ) : (
              <>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary, textAlign: 'center' }]}>
                  {mesDelPeriodo(periodo, hoyIso) ? `No hay registros en ${mesDelPeriodo(periodo, hoyIso)}` : 'No hay registros en este periodo'}
                </Text>
                {p.onRegistrar && !p.tercero ? <BotonPrimario testID="actividad-registrar" titulo="Registrar" onPress={p.onRegistrar} /> : null}
              </>
            )}
          </View>
        ) : null}
        {grupos.map((g) => (
          <View key={g.clave} testID={`grupo-${g.clave}`} style={{ gap: espacio.xs }}>
            <Text accessibilityRole="header" style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{g.titulo}</Text>
            <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
              {g.filas.map((f, i) => (
                <FilaVista key={f.id} f={f} conFecha={buscando || !!p.tercero} ultima={i === g.filas.length - 1} onPress={() => void abrirDetalle(f.id)}
                  onCobrado={ofreceRegistrarAbono(f) && p.nuevoId ? () => abrirAbono(f, null) : undefined} />
              ))}
            </View>
          </View>
        ))}
        {carga.fase === 'OK' && carga.siguiente ? (
          <BotonSecundario testID="actividad-mas" titulo={cargandoMas ? 'Cargando…' : 'Cargar más'} onPress={() => void cargarMas()} />
        ) : null}
      </ScrollView>

      {hoja?.h === 'PERIODO' ? (
        <Hoja titulo="Periodo" testID="hoja-periodo">
          {([
            { k: 'ESTE_MES', t: 'Este mes', d: mesAnioIso(hoyIso), on: () => setPeriodo({ tipo: 'ESTE_MES' }) },
            { k: 'MES_ANTERIOR', t: 'Mes anterior', d: mesAnioIso(mesDesplazadoIso(hoyIso, -1)), on: () => setPeriodo({ tipo: 'MES_ANTERIOR' }) },
            ...(p.tercero ? [{ k: 'TODO', t: 'Todo el historial', d: '', on: () => setPeriodo({ tipo: 'TODO' }) }] : []),
          ] as const).map((o) => (
            <Opcion key={o.k} testID={`periodo-${o.k}`} titulo={o.t} detalle={o.d} radio seleccionada={periodo.tipo === o.k}
              onPress={() => { o.on(); setHoja(null); }} />
          ))}
          <Opcion testID="periodo-OTRO_MES" titulo="Otro mes" radio seleccionada={periodo.tipo === 'OTRO_MES'} chevron
            onPress={() => setHoja({ h: 'OTRO_MES', mes: periodo.tipo === 'OTRO_MES' ? periodo.mes : mesDesplazadoIso(hoyIso, -1) })} />
          <Opcion testID="periodo-ENTRE_FECHAS" titulo="Entre fechas" radio seleccionada={periodo.tipo === 'ENTRE_FECHAS'} chevron
            onPress={() => setHoja({ h: 'ENTRE_FECHAS', desde: '', hasta: '' })} />
          <Text style={[tipo.caption, { color: c.textSecondary }]}>{TEXTO_MES_NATURAL}</Text>
          <BotonSecundario testID="periodo-cerrar" titulo="Cerrar" onPress={() => setHoja(null)} />
        </Hoja>
      ) : null}

      {hoja?.h === 'OTRO_MES' ? (
        <Hoja titulo="Otro mes" testID="hoja-otro-mes">
          <View style={s.filaCabecera}>
            <BotonTexto testID="otro-mes-anterior" titulo="‹" onPress={() => setHoja({ h: 'OTRO_MES', mes: mesDesplazadoIso(hoja.mes, -1) })} />
            <Text testID="otro-mes-valor" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{mesAnioIso(hoja.mes)}</Text>
            <BotonTexto testID="otro-mes-siguiente" titulo="›"
              onPress={() => { if (hoja.mes.slice(0, 7) < hoyIso.slice(0, 7)) setHoja({ h: 'OTRO_MES', mes: mesDesplazadoIso(hoja.mes, 1) }); }} />
          </View>
          <BotonPrimario testID="otro-mes-usar" titulo="Ver este mes" onPress={() => { setPeriodo({ tipo: 'OTRO_MES', mes: hoja.mes }); setHoja(null); }} />
          <BotonSecundario testID="otro-mes-cancelar" titulo="Cancelar" onPress={() => setHoja({ h: 'PERIODO' })} />
        </Hoja>
      ) : null}

      {hoja?.h === 'ENTRE_FECHAS' ? (
        <Hoja titulo="Entre fechas" testID="hoja-entre-fechas">
          <TextInput testID="entre-desde" accessibilityLabel="Desde, día barra mes barra año" value={hoja.desde} placeholder="Desde dd/mm/aaaa"
            placeholderTextColor={c.textSecondary} maxLength={10} inputMode="numeric"
            onChangeText={(t) => setHoja({ ...hoja, desde: t })} style={[tipo.body, s.campo, { color: c.textPrimary, backgroundColor: c.surfaceSecondary }]} />
          <TextInput testID="entre-hasta" accessibilityLabel="Hasta, día barra mes barra año" value={hoja.hasta} placeholder="Hasta dd/mm/aaaa"
            placeholderTextColor={c.textSecondary} maxLength={10} inputMode="numeric"
            onChangeText={(t) => setHoja({ ...hoja, hasta: t })} style={[tipo.body, s.campo, { color: c.textPrimary, backgroundColor: c.surfaceSecondary }]} />
          {(() => {
            const d = ddmmaaaaAIso(hoja.desde);
            const h = ddmmaaaaAIso(hoja.hasta);
            const ok = !!d && !!h && d <= h;
            return (
              <>
                {hoja.desde.length >= 10 && hoja.hasta.length >= 10 && !ok ? (
                  <Text testID="entre-error" style={[tipo.footnote, { color: c.critical }]}>Revisa las fechas: «desde» no puede ser posterior a «hasta».</Text>
                ) : null}
                <BotonPrimario testID="entre-usar" titulo="Ver estas fechas" deshabilitado={!ok}
                  onPress={() => { if (ok) { setPeriodo({ tipo: 'ENTRE_FECHAS', desde: d!, hasta: h! }); setHoja(null); } }} />
              </>
            );
          })()}
          <BotonSecundario testID="entre-cancelar" titulo="Cancelar" onPress={() => setHoja({ h: 'PERIODO' })} />
        </Hoja>
      ) : null}

      {hoja?.h === 'FILTROS' ? (
        <Hoja titulo="Filtros" testID="hoja-filtros">
          <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Tipo</Text>
          <View style={s.chips}>
            {(['GASTO', 'INGRESO', 'TRANSFERENCIA'] as TipoActividad[]).map((t) => (
              <Chip key={t} testID={`filtro-tipo-${t}`} etiqueta={NOMBRE_FILTRO_TIPO[t]} seleccionado={borrador.tipos.includes(t)}
                onPress={() => setBorrador({ ...borrador, tipos: borrador.tipos.includes(t) ? borrador.tipos.filter((x) => x !== t) : [...borrador.tipos, t] })} />
            ))}
          </View>
          <CampoFiltro testID="filtro-categoria" etiqueta="Categoría" valor={borrador.categoria ? `${borrador.categoria.nombre} (con subcategorías)` : 'Todas'}
            onPress={() => void abrirCategoria()} />
          <CampoFiltro testID="filtro-cuenta" etiqueta="Cuenta" valor={borrador.cuenta?.nombre ?? 'Todas'} onPress={() => setHoja({ h: 'F_LISTA', campo: 'cuenta' })} />
          {p.tercero ? null : (
            <CampoFiltro testID="filtro-tercero" etiqueta="Tercero" valor={borrador.tercero?.nombre ?? 'Todos'} onPress={() => setHoja({ h: 'F_LISTA', campo: 'tercero' })} />
          )}
          <CampoFiltro testID="filtro-contexto" etiqueta="Contexto" valor={borrador.contexto?.nombre ?? 'Todos'} onPress={() => setHoja({ h: 'F_LISTA', campo: 'contexto' })} />
          <View style={s.filaCabecera}>
            <BotonTexto testID="filtros-limpiar" titulo="Limpiar" onPress={() => setBorrador(p.tercero ? inicialFiltros : SIN_FILTROS)} />
            <View style={{ flex: 1 }}>
              <BotonPrimario testID="filtros-ver" titulo={recuento === null ? 'Ver resultados' : `Ver ${recuento} ${recuento === 1 ? 'resultado' : 'resultados'}`} onPress={aplicarFiltros} />
            </View>
          </View>
        </Hoja>
      ) : null}

      {hoja?.h === 'F_CATEGORIA' ? (
        <SelectorCategorias
          titulo="Categoría"
          modo="AJUSTES"
          carga={arbol}
          esVisible={() => true}
          esSeleccionable={() => true}
          motivo={() => null}
          seleccionadaId={borrador.categoria?.id ?? null}
          opcionRaiz={{ etiqueta: 'Todas', subtitulo: 'Sin filtrar por categoría', seleccionada: !borrador.categoria, testID: 'filtro-categoria-todas',
            onPress: () => { setBorrador({ ...borrador, categoria: null }); setHoja({ h: 'FILTROS' }); } }}
          onElegir={(n) => { setBorrador({ ...borrador, categoria: { id: n.id, nombre: n.nombre } }); setHoja({ h: 'FILTROS' }); }}
          onCerrar={() => setHoja({ h: 'FILTROS' })}
          onReintentar={() => void abrirCategoria()}
          buscar
        />
      ) : null}

      {hoja?.h === 'F_LISTA' ? (
        <HojaLista
          titulo={{ cuenta: 'Cuenta', tercero: 'Tercero', contexto: 'Contexto' }[hoja.campo]}
          todas={hoja.campo === 'cuenta' ? 'Todas' : 'Todos'}
          opciones={opciones?.[hoja.campo] ?? null}
          seleccionada={borrador[hoja.campo]?.id ?? null}
          onElegir={(o) => { setBorrador({ ...borrador, [hoja.campo]: o }); setHoja({ h: 'FILTROS' }); }}
          onCerrar={() => setHoja({ h: 'FILTROS' })}
        />
      ) : null}

      {hoja?.h === 'DETALLE' ? (
        <Hoja titulo={detalle.fase === 'OK' ? tituloTransferencia(detalle.d) ?? tituloFila(detalle.d) : 'Detalle'} testID="hoja-detalle">
          <ScrollView style={{ maxHeight: 420 }} testID="detalle-scroll">
            {detalle.fase === 'CARGANDO' ? <View style={[s.barra, { backgroundColor: c.surfaceSecondary }]} /> : null}
            {detalle.fase === 'ERROR' ? (
              <View style={{ gap: espacio.s }}>
                <Text style={[tipo.subheadline, { color: c.textPrimary }]}>No se ha podido cargar el detalle.</Text>
                <BotonSecundario testID="detalle-reintentar" titulo="Reintentar" onPress={() => void abrirDetalle(hoja.id)} />
              </View>
            ) : null}
            {detalle.fase === 'OK' ? <DetalleVista d={detalle.d} onAbrir={(id) => void abrirDetalle(id)} /> : null}
          </ScrollView>
          {detalle.fase === 'OK' && ofreceRegistrarDevolucion(detalle.d) && p.onRegistrarDevolucion ? (
            <BotonSecundario testID="detalle-registrar-devolucion" titulo="Registrar devolución"
              onPress={() => { const id = detalle.d.id; setHoja(null); p.onRegistrarDevolucion!(id); }} />
          ) : null}
          {detalle.fase === 'OK' && reparto && reparto.hecho_id === detalle.d.id && p.onPendienteCon
            ? reparto.partes.filter((x) => x.posicion && x.tercero_id).map((x) => (
                <BotonSecundario key={x.atribucion_id} testID={`detalle-pendiente-${x.tercero_id}`} titulo={`Pendiente con ${x.nombre}`}
                  onPress={() => { setHoja(null); p.onPendienteCon!({ terceroId: x.tercero_id!, nombre: x.nombre }); }} />
              ))
            : null}
          {detalle.fase === 'OK' && reparto && reparto.hecho_id === detalle.d.id && reparto.corregible && p.onCorregirReparto ? (
            <BotonSecundario testID="detalle-corregir-reparto" titulo="Corregir reparto"
              onPress={() => { const id = detalle.d.id; setHoja(null); p.onCorregirReparto!(id); }} />
          ) : null}
          {detalle.fase === 'OK' && ofreceRegistrarAbono(detalle.d) && p.nuevoId ? (
            <BotonSecundario testID="detalle-registrar-abono" titulo="Registrar abono" onPress={() => abrirAbono(detalle.d, detalle.d.id)} />
          ) : null}
          <Text style={[tipo.caption, { color: c.textSecondary }]}>{TEXTO_EDICION}</Text>
          <BotonSecundario testID="detalle-cerrar" titulo="Cerrar" onPress={() => setHoja(null)} />
        </Hoja>
      ) : null}

      {hoja?.h === 'ABONO' && p.nuevoId ? (
        <AbonoHoja cliente={p.cliente} nuevoId={p.nuevoId} ahora={p.ahora} devolucion={hoja.dev} onCerrar={(r) => cerrarAbono(r, hoja.volverA)} />
      ) : null}
    </View>
  );
}

/** Distancia horizontal (px) a la izquierda que dispara el swipe «Cobrado» (P-DEV-04). */
export const UMBRAL_SWIPE = 72;
/** Desplazamiento máximo (px) de la fila durante el swipe «Cobrado» (O-1): deja ver la franja entera sin vaciar la fila. */
export const TOPE_SWIPE = 160;
/** Texto de la franja que aparece detrás de la fila al deslizar (O-1, patrón iOS). */
export const TEXTO_FRANJA_COBRADO = 'Confirmar abono';

type FaseSwipe = 'reposo' | 'arrastrando' | 'superado';

function FilaVista(p: { f: FilaActividad; conFecha: boolean; ultima: boolean; onPress: () => void; onCobrado?: () => void }) {
  const { c } = useTema();
  const f = p.f;
  const titulo = tituloTransferencia(f) ?? tituloFila(f);
  const secundaria = textoCoincidencia(f) ?? secundariaFila(f);
  const marca = marcaReparto(f);
  const onCobrado = useRef(p.onCobrado);
  onCobrado.current = p.onCobrado;
  // O-1: la fila sigue al dedo (solo a la izquierda, con tope) y deja ver detrás la franja «Confirmar abono», que se
  // intensifica al superar el umbral. Al soltar la fila vuelve a su sitio con animación.
  const desplazamiento = useRef(new Animated.Value(0)).current;
  const [fase, setFase] = useState<FaseSwipe>('reposo');
  // Swipe «Cobrado» (DAY-RULE-03): solo en una devolución con el abono pendiente; abre la confirmación, nunca registra solo.
  // Va en un contenedor que CAPTURA el movimiento horizontal: el Pressable de la fila es responder desde el toque y sus
  // manejadores pisarían los del gesto (en web y en nativo); al capturar, el Pressable se cancela y no hay toque.
  const gesto = useMemo(() => {
    const horizontal = (g: { dx: number; dy: number }) => !!onCobrado.current && Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy);
    const volver = () => {
      setFase('reposo');
      Animated.timing(desplazamiento, { toValue: 0, duration: 180, useNativeDriver: false }).start(); // el arrastre ya va por JS (setValue)
    };
    return PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => horizontal(g),
      onMoveShouldSetPanResponderCapture: (_, g) => horizontal(g),
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: () => setFase('arrastrando'),
      onPanResponderMove: (_, g) => {
        desplazamiento.setValue(Math.max(-TOPE_SWIPE, Math.min(0, g.dx)));
        setFase(g.dx <= -UMBRAL_SWIPE ? 'superado' : 'arrastrando');
      },
      onPanResponderRelease: (_, g) => {
        volver();
        if (onCobrado.current && g.dx <= -UMBRAL_SWIPE) onCobrado.current();
      },
      onPanResponderTerminate: volver,
    });
  }, [desplazamiento]);
  const fila = (
    <Pressable
      testID={`fila-${f.id}`}
      accessibilityRole="button"
      accessibilityLabel={[titulo, secundaria, importeFila(f), marca].filter(Boolean).join('. ')}
      accessibilityActions={p.onCobrado ? [{ name: 'cobrado', label: 'Cobrado' }] : undefined}
      onAccessibilityAction={(e) => {
        if (e.nativeEvent.actionName === 'cobrado') p.onCobrado?.();
      }}
      onPress={p.onPress}
      style={({ pressed }) => [s.fila, { borderBottomColor: c.separator, borderBottomWidth: p.ultima ? 0 : StyleSheet.hairlineWidth, opacity: pressed ? 0.7 : 1 }]}
    >
      <IconoFila f={f} testID={`actividad-icono-${f.id}`} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[tipo.body, { color: c.textPrimary }]} numberOfLines={1}>{titulo}</Text>
        {secundaria ? <Text style={[tipo.caption, { color: c.textSecondary }]} numberOfLines={1}>{secundaria}</Text> : null}
      </View>
      <View style={{ alignItems: 'flex-end', gap: 2 }}>
        <Text style={[tipo.body, { color: c.textPrimary, fontVariant: ['tabular-nums'] }]}>{importeFila(f)}</Text>
        {marca ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{marca}</Text> : null}
        {p.conFecha ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{diaMesIso(f.fecha_hecho)}</Text> : null}
      </View>
    </Pressable>
  );
  if (!p.onCobrado) return fila;
  const superado = fase === 'superado';
  return (
    <View testID={`fila-swipe-${f.id}`} style={s.swipe} {...gesto.panHandlers}>
      {fase !== 'reposo' ? (
        // Decorativa: la acción accesible sigue siendo «Cobrado» en la fila (S1); VoiceOver no ve la franja.
        <View testID={`franja-cobrado-${f.id}`} accessibilityElementsHidden importantForAccessibility="no-hide-descendants"
          style={[s.franja, { backgroundColor: superado ? c.accent : c.accentSurface }]}>
          <Ionicons name="checkmark" size={18} color={superado ? c.onAccent : c.accent} />
          <Text style={[tipo.body, { color: superado ? c.onAccent : c.accent, fontWeight: '600' }]}>{TEXTO_FRANJA_COBRADO}</Text>
        </View>
      ) : null}
      <Animated.View testID={`fila-desplazable-${f.id}`} style={{ backgroundColor: c.surfacePrimary, transform: [{ translateX: desplazamiento }] }}>
        {fila}
      </Animated.View>
    </View>
  );
}

function IconoFila({ f, testID }: { f: FilaActividad; testID: string }) {
  const { c } = useTema();
  if (f.tipo === 'TRANSFERENCIA') {
    return (
      <View testID={testID} style={[s.icono, { backgroundColor: c.surfaceSecondary }]}>
        <Ionicons name="swap-horizontal" size={18} color={c.textSecondary} />
      </View>
    );
  }
  return <IconoCategoriaVista testID={testID} iconKey={f.varias ? null : f.categoria?.icon_key ?? null} />;
}

function DetalleVista({ d, onAbrir }: { d: DetalleActividad; onAbrir: (id: string) => void }) {
  const { c } = useTema();
  const kv: [string, string][] = [];
  const nombreTipo = d.devolucion_de ? 'Devolución' : d.tipo === 'GASTO' ? 'Gasto' : d.tipo === 'INGRESO' ? 'Ingreso' : 'Entre cuentas';
  if (d.devolucion_de) {
    // A4: lo devuelto, el abono, la categoría y tu parte (sin signo: no es un ingreso).
    kv.push(['Devuelto', formatearEur(d.importe_total ?? '0')]);
    const cobro = d.cuentas.find((x) => x.rol === 'COBRO');
    kv.push(['Abono', d.abono === 'COBRADO' ? `Recibido en ${cobro?.nombre ?? 'la cuenta'}` : 'Pendiente']);
    kv.push(['Categoría', d.categoria ? `${d.categoria.ruta}${d.categoria.enabled ? '' : ' (desactivada)'}` : 'Sin categoría']);
    kv.push(['Tu parte', d.estado_reparto === 'COMPLETA' && d.tu_parte !== null ? formatearEur(d.tu_parte.replace('-', '')) : 'Sin indicar']);
  } else if (d.tipo === 'TRANSFERENCIA') {
    kv.push(['Importe', formatearEur(d.importe_total ?? '0')]);
    kv.push(['Desde', d.cuentas.find((x) => x.rol === 'ORIGEN')?.nombre ?? '—']);
    kv.push(['A', d.cuentas.find((x) => x.rol === 'DESTINO')?.nombre ?? '—']);
  } else {
    kv.push(['Total del hecho', `${d.tipo === 'INGRESO' ? '+' : ''}${formatearEur(d.importe_total ?? '0')}`]);
    kv.push(['Tu parte', textoTuParte(d)]);
    kv.push([d.tipo === 'INGRESO' ? 'Cobrado en' : 'Pagado con', d.cuentas[0]?.nombre ?? '—']);
    kv.push(['Categoría', d.varias ? 'Varias' : d.categoria ? `${d.categoria.ruta}${d.categoria.enabled ? '' : ' (desactivada)'}` : 'Sin categoría']);
    if (d.tercero) kv.push([d.tipo === 'INGRESO' ? 'De' : 'Tercero', `${d.tercero.nombre}${d.tercero.enabled ? '' : ' (desactivado)'}`]);
    if (d.contexto) kv.push(['Contexto', `${d.contexto.nombre}${d.contexto.enabled ? '' : ' (desactivado)'}`]);
    for (const m of d.magnitudes) kv.push([m.nombre, `${m.valor}${m.unidad ? ` ${m.unidad}` : ''}`]);
    kv.push(['Presupuesto', d.presupuestable ? 'Sí' : 'No']);
  }
  kv.push(['Nota', (d.nota ?? '').trim() || '—']);
  const origen = d.devolucion_de;
  const devs = d.devoluciones;
  return (
    <View testID="detalle-contenido" style={{ gap: espacio.s }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: espacio.s }}>
        <IconoFila f={d} testID="detalle-icono" />
        <Text testID="detalle-subtitulo" style={[tipo.footnote, { color: c.textSecondary }]}>{`${nombreTipo} · ${diaMesAnioIso(d.fecha_hecho)}`}</Text>
      </View>
      {kv.map(([k, v]) => (
        <View key={k} testID={`kv-${k}`} style={s.kv}>
          <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{k}</Text>
          <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1, textAlign: 'right' }]}>{v}</Text>
        </View>
      ))}
      {d.tipo === 'TRANSFERENCIA' ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_ENTRE_CUENTAS_DETALLE}</Text> : null}
      {origen ? (
        <Pressable testID="detalle-devolucion-de" accessibilityRole="link" accessibilityLabel={`Devolución de ${textoDevolucionDe(origen)}`}
          onPress={() => onAbrir(origen.hecho_id)} style={s.kv}>
          <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Devolución de</Text>
          <Text style={[tipo.subheadline, { color: c.accent }]}>{`${nombreCorto(origen)} · ${diaMesIso(origen.fecha_hecho)} ›`}</Text>
        </Pressable>
      ) : null}
      {devs ? (
        <View testID="detalle-devoluciones" style={{ gap: espacio.xs }}>
          {devs.items.map((x) => (
            <Pressable key={x.hecho_id} testID={`detalle-devolucion-${x.hecho_id}`} accessibilityRole="link" onPress={() => onAbrir(x.hecho_id)} style={s.kv}>
              <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Devolución</Text>
              <Text style={[tipo.subheadline, { color: c.accent }]}>
                {`${formatearEur(x.importe)} · ${diaMesIso(x.fecha_hecho)}${x.abono === 'PENDIENTE' ? ' · abono pendiente' : ''} ›`}
              </Text>
            </Pressable>
          ))}
          <View testID="detalle-neto" style={s.kv}>
            <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Neto tras devoluciones</Text>
            <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{formatearEur(devs.neto)}</Text>
          </View>
          <Text style={[tipo.caption, { color: c.textSecondary }]}>{`Queda por devolver ${formatearEur(devs.queda)}. El neto ${TEXTO_NETO.toLowerCase()}`}</Text>
        </View>
      ) : null}
    </View>
  );
}

function Opcion(p: { testID: string; titulo: string; detalle?: string; radio?: boolean; seleccionada?: boolean; chevron?: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable testID={p.testID} accessibilityRole="radio" accessibilityState={{ checked: !!p.seleccionada }} onPress={p.onPress}
      style={[s.opcion, { borderBottomColor: c.separator }]}>
      <Ionicons name={p.seleccionada ? 'radio-button-on' : 'radio-button-off'} size={20} color={p.seleccionada ? c.accent : c.textSecondary} />
      <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{p.titulo}</Text>
      {p.detalle ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{p.detalle}</Text> : null}
      {p.chevron ? <Ionicons name="chevron-forward" size={18} color={c.textSecondary} /> : null}
    </Pressable>
  );
}

function CampoFiltro(p: { testID: string; etiqueta: string; valor: string; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable testID={p.testID} accessibilityRole="button" accessibilityLabel={`${p.etiqueta}: ${p.valor}`} onPress={p.onPress}
      style={[s.opcion, { borderBottomColor: c.separator }]}>
      <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{p.etiqueta}</Text>
      <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{p.valor}</Text>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

function HojaLista(p: { titulo: string; todas: string; opciones: Opcion[] | null; seleccionada: string | null; onElegir: (o: Opcion | null) => void; onCerrar: () => void }) {
  const { c } = useTema();
  const [f, setF] = useState('');
  const lista = p.opciones ? filtrar(p.opciones, f) : [];
  return (
    <Hoja titulo={p.titulo} testID="hoja-lista-filtro">
      <TextInput testID="lista-filtro" accessibilityLabel="Filtrar por nombre" value={f} onChangeText={setF} placeholder="Filtrar por nombre"
        placeholderTextColor={c.textSecondary} style={[tipo.body, s.campo, { color: c.textPrimary, backgroundColor: c.surfaceSecondary }]} />
      <ScrollView style={{ maxHeight: 320 }} keyboardShouldPersistTaps="handled">
        <Opcion testID="lista-todas" titulo={p.todas} radio seleccionada={p.seleccionada === null} onPress={() => p.onElegir(null)} />
        {p.opciones === null ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>Cargando…</Text> : null}
        {lista.map((o) => (
          <Opcion key={o.id} testID={`lista-${o.id}`} titulo={o.nombre} detalle={o.detalle} radio seleccionada={p.seleccionada === o.id}
            onPress={() => p.onElegir({ id: o.id, nombre: o.nombre })} />
        ))}
      </ScrollView>
      <BotonSecundario testID="lista-cerrar" titulo="Cerrar" onPress={p.onCerrar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  filaCabecera: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.s, minHeight: TACTIL_MIN },
  pestanas: { flexDirection: 'row', gap: espacio.l },
  pestana: { paddingVertical: espacio.xs, borderBottomWidth: 2, borderBottomColor: 'transparent' },
  boton: { minHeight: TACTIL_MIN, justifyContent: 'center' },
  campo: { flex: 1, minHeight: TACTIL_MIN, borderRadius: radio.m, paddingHorizontal: espacio.m },
  lineaFiltros: { flexDirection: 'row', alignItems: 'center', gap: espacio.s },
  alcance: { borderRadius: radio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.xs },
  barra: { height: 56, borderRadius: radio.m },
  tarjetaError: { borderRadius: radio.m, padding: espacio.l, gap: espacio.s },
  vacio: { alignItems: 'center', gap: espacio.s, paddingVertical: espacio.xxl },
  tarjeta: { borderRadius: radio.m, overflow: 'hidden' },
  swipe: { overflow: 'hidden' },
  franja: { ...StyleSheet.absoluteFill, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: espacio.s, paddingHorizontal: espacio.m },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, paddingHorizontal: espacio.m, paddingVertical: espacio.s, minHeight: TACTIL_MIN + 12 },
  icono: { width: 32, height: 32, borderRadius: radio.s, alignItems: 'center', justifyContent: 'center' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  opcion: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 4, borderBottomWidth: StyleSheet.hairlineWidth },
  kv: { flexDirection: 'row', justifyContent: 'space-between', gap: espacio.m },
});

