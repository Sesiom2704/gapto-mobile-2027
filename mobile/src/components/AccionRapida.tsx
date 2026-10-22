// ============================================================
// GAPTO MOBILE 2027
// Fichero: AccionRapida.tsx
// Ruta: mobile/src/components/AccionRapida.tsx
// Descripción: Swipe como acción rápida en toda la app (F05-06 M5 SWIPE; regla de Moisés del 2026-10-22, que sustituye a DAY-RULE-03 y a D-PREV-08/12 en lo que contradigan). Pieza común de todas las pantallas: FilaDeslizable (la fila sigue al dedo con tope y deja ver detrás la franja de la acción, de acento pasado el umbral; al soltar vuelve) y useAccionRapida (aviso «<Nombre> cobrada/pagada · Deshacer» durante 5 s; la petición sale al terminar la espera y «Deshacer» la cancela sin tocar el servidor). La identidad de la intención se fija al soltar y se conserva tras un INDETERMINADO, para que el reintento sea idempotente; un segundo gesto sobre la misma fila mientras espera o envía se ignora. Si la app pasa a segundo plano o la pantalla se desmonta durante la espera, no se envía nada. Un rechazo devuelve la fila con el motivo del servidor; nunca un éxito falso. Solo para acciones que crean o confirman realidad con datos completos: nunca anular, borrar, corregir ni omitir.
// Versión: 0.1.0 (F05-06 M5 SWIPE)
// Versión: 0.2.0 (F05-06 M5 SWIPE2; lámina SWIPE-01 v0.2, estilo C; SWIPE-RULE): dos lados. A la DERECHA la acción principal y positiva (tono «confirmar»: círculo de 46 px de acento con etiqueta sobre `accentSurface`); a la IZQUIERDA la alternativa («No hubo» y «Más» en tono neutro; «Desactivar» en tono de aviso). Nunca el rojo (`critical`): `coloresTono` es el único mapa de tonos. Deslizar a medias deja el botón visible (tocarlo lo ejecuta); deslizar del todo lo ejecuta, con vibración ligera al pasar el umbral. Filas en tarjeta. Aviso flotante translúcido con ✓ en círculo (hasta dos líneas: el importe nunca se corta) y «Deshacer» con un anillo que se vacía en 5 s. Acciones accesibles «derecha» / «izquierda» con la etiqueta de cada lado (`accesibilidadLados`), la misma función que el gesto.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, AppState, PanResponder, Pressable, StyleSheet, Text, View } from 'react-native';

import type { Respuesta } from '../api/cliente';
import { useTema } from '../theme/tema';
import type { Colores } from '../theme/tokens';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

/** Espera antes de enviar: el tiempo de «Deshacer». */
export const ESPERA_DESHACER_MS = 5000;
/** Distancia (px) a partir de la cual, al soltar, la fila queda abierta enseñando el botón. */
export const UMBRAL_SWIPE = 72;
/** Desplazamiento de la fila abierta a medias (lámina SWIPE-01: 150 px). */
export const ABIERTO_SWIPE = 150;
/** Fracción del ancho de la fila a partir de la cual soltar ejecuta la acción. */
export const FRACCION_TOTAL = 0.45;
/** Ancho supuesto mientras la fila no se ha medido. */
const ANCHO_INICIAL = 360;
/** Compatibilidad con la pista O-1 de M2: el tope del arrastre a medias. */
export const TOPE_SWIPE = ABIERTO_SWIPE;

/** Texto llano cuando el servidor rechaza sin mensaje. */
export const TEXTO_RECHAZO_GENERICO = 'El servidor no lo ha aceptado.';

/** Tono de un lado: confirmar (verde), neutro (gris) o aviso (naranja). No existe el tono rojo. */
export type TonoSwipe = 'confirmar' | 'neutro' | 'aviso';

export interface LadoSwipe {
  etiqueta: string;
  icono: React.ComponentProps<typeof Ionicons>['name'];
  tono: TonoSwipe;
  onEjecutar: () => void;
}

/** Colores de un tono con tokens del DS (lámina: --soft/--ac, --s2/--t2, --ps/--warn). Nunca `critical`. */
export function coloresTono(c: Colores, tono: TonoSwipe): { fondo: string; circulo: string; sobreCirculo: string; etiqueta: string } {
  if (tono === 'confirmar') return { fondo: c.accentSurface, circulo: c.accent, sobreCirculo: c.onAccent, etiqueta: c.accent };
  if (tono === 'aviso') return { fondo: c.partialSurface, circulo: c.warning, sobreCirculo: c.onAccent, etiqueta: c.warning };
  return { fondo: c.surfaceSecondary, circulo: c.textSecondary, sobreCirculo: c.background, etiqueta: c.textSecondary };
}

/** Acciones accesibles de una fila deslizable: las mismas funciones que el gesto. */
export function accesibilidadLados(derecha?: LadoSwipe, izquierda?: LadoSwipe, extra: { name: string; label?: string }[] = []) {
  const acciones = [...extra];
  if (derecha) acciones.push({ name: 'derecha', label: derecha.etiqueta });
  if (izquierda) acciones.push({ name: 'izquierda', label: izquierda.etiqueta });
  return {
    accessibilityActions: acciones.length > 0 ? acciones : undefined,
    /** Devuelve true si la acción era de un lado. */
    ejecutar: (nombre: string): boolean => {
      if (nombre === 'derecha' && derecha) return derecha.onEjecutar(), true;
      if (nombre === 'izquierda' && izquierda) return izquierda.onEjecutar(), true;
      return false;
    },
  };
}

type FaseSwipe = 'reposo' | 'arrastrando' | 'total';

/** Fila en tarjeta con swipe a los dos lados. Sin lados se pinta la tarjeta sin gesto. */
export function FilaDeslizable(p: {
  /** Sufijo de los testID: `fila-swipe-<id>`, `fila-desplazable-<id>`, `swipe-accion-<id>-<lado>` y `swipe-boton-<id>-<lado>`. */
  id: string;
  derecha?: LadoSwipe;
  izquierda?: LadoSwipe;
  /** Sin tarjeta (la fila ya es tarjeta o vive dentro de otra). */
  sinTarjeta?: boolean;
  children: React.ReactNode;
}) {
  const { c } = useTema();
  const lados = useRef({ derecha: p.derecha, izquierda: p.izquierda });
  lados.current = { derecha: p.derecha, izquierda: p.izquierda };
  const desplazamiento = useRef(new Animated.Value(0)).current;
  const ancho = useRef(ANCHO_INICIAL);
  const base = useRef(0); // posición al empezar el gesto (0, ABIERTO o −ABIERTO)
  const [fase, setFase] = useState<FaseSwipe>('reposo');
  const [lado, setLado] = useState<'derecha' | 'izquierda' | null>(null);
  const [abierta, setAbierta] = useState(false);
  const total = () => Math.max(UMBRAL_SWIPE + 1, ancho.current * FRACCION_TOTAL);

  const mover = (x: number, animar: boolean) => {
    if (animar) Animated.timing(desplazamiento, { toValue: x, duration: 180, useNativeDriver: false }).start();
    else desplazamiento.setValue(x);
  };
  const cerrar = useCallback(() => {
    base.current = 0;
    setAbierta(false);
    setFase('reposo');
    setLado(null);
    mover(0, true);
  }, []);
  const ejecutar = useCallback((cual: 'derecha' | 'izquierda') => {
    const l = lados.current[cual];
    cerrar();
    l?.onEjecutar();
  }, [cerrar]);

  const gesto = useMemo(() => {
    const permitido = (dx: number) => (dx > 0 ? !!lados.current.derecha : !!lados.current.izquierda);
    const horizontal = (g: { dx: number; dy: number }) =>
      Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy) && (base.current !== 0 || permitido(g.dx));
    const posicion = (dx: number) => {
      const x = base.current + dx;
      const max = lados.current.derecha ? ancho.current : 0;
      const min = lados.current.izquierda ? -ancho.current : 0;
      return Math.max(min, Math.min(max, x));
    };
    return PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => horizontal(g),
      onMoveShouldSetPanResponderCapture: (_, g) => horizontal(g),
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: () => setFase('arrastrando'),
      onPanResponderMove: (_, g) => {
        const x = posicion(g.dx);
        mover(x, false);
        setLado(x > 0 ? 'derecha' : x < 0 ? 'izquierda' : null);
        const pasa = Math.abs(x) >= total();
        setFase((f) => {
          if (pasa && f !== 'total') void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => undefined);
          return pasa ? 'total' : 'arrastrando';
        });
      },
      onPanResponderRelease: (_, g) => {
        const x = posicion(g.dx);
        if (x >= total() && lados.current.derecha) return ejecutar('derecha');
        if (x <= -total() && lados.current.izquierda) return ejecutar('izquierda');
        if (x >= UMBRAL_SWIPE && lados.current.derecha) {
          base.current = ABIERTO_SWIPE;
          setAbierta(true);
          setFase('arrastrando');
          setLado('derecha');
          return mover(ABIERTO_SWIPE, true);
        }
        if (x <= -UMBRAL_SWIPE && lados.current.izquierda) {
          base.current = -ABIERTO_SWIPE;
          setAbierta(true);
          setFase('arrastrando');
          setLado('izquierda');
          return mover(-ABIERTO_SWIPE, true);
        }
        cerrar();
      },
      onPanResponderTerminate: () => cerrar(),
    });
  }, [desplazamiento, cerrar, ejecutar]);

  const tarjeta = p.sinTarjeta ? null : [s.tarjeta, { borderColor: c.borderDefault }];
  const contenido = (
    <Animated.View testID={`fila-desplazable-${p.id}`} style={[{ backgroundColor: c.surfacePrimary, transform: [{ translateX: desplazamiento }] }, tarjeta]}>
      {abierta ? (
        // Abierta a medias: tocar la fila la cierra (no abre el detalle por accidente).
        <Pressable testID={`swipe-cerrar-${p.id}`} accessibilityLabel="Cerrar" onPress={cerrar} style={StyleSheet.absoluteFill} />
      ) : null}
      {p.children}
    </Animated.View>
  );
  if (!p.derecha && !p.izquierda) return <View testID={`fila-tarjeta-${p.id}`} style={tarjeta ? s.envoltorio : undefined}>{contenido}</View>;
  const l = lado ? lados.current[lado] : undefined;
  const col = l ? coloresTono(c, l.tono) : null;
  return (
    <View testID={`fila-swipe-${p.id}`} style={[s.swipe, !p.sinTarjeta && s.envoltorio, col && { backgroundColor: col.fondo }]}
      onLayout={(e) => (ancho.current = e.nativeEvent.layout.width || ANCHO_INICIAL)} {...gesto.panHandlers}>
      {fase !== 'reposo' && l && lado && col ? (
        // La acción accesible sigue en la fila; VoiceOver no ve el fondo (el botón es para el dedo).
        <View testID={`swipe-accion-${p.id}-${lado}`} accessibilityElementsHidden importantForAccessibility="no-hide-descendants"
          style={[s.fondo, lado === 'derecha' ? s.fondoDerecha : s.fondoIzquierda]}>
          <Pressable testID={`swipe-boton-${p.id}-${lado}`} onPress={() => ejecutar(lado)} style={[s.boton, lado === 'izquierda' && s.botonIzquierda]}>
            <View style={[s.circulo, { backgroundColor: col.circulo }, fase === 'total' && s.circuloTotal]}>
              <Ionicons name={l.icono} size={22} color={col.sobreCirculo} />
            </View>
            <Text style={[tipo.caption, { color: col.etiqueta, fontWeight: '600' }]}>{l.etiqueta}</Text>
          </Pressable>
        </View>
      ) : null}
      {contenido}
    </View>
  );
}

/** Una acción rápida: `enviar` compone la petición con la identidad fijada al soltar. */
export interface AccionRapida {
  clave: string;
  /** «Nómina cobrada · 2.100,00 €», «Electricidad pagada · 74,00 €». */
  texto: string;
  enviar: (intencionId: string) => Promise<Respuesta<unknown>>;
}

type Viva = { a: AccionRapida; id: string; fase: 'ESPERA' | 'ENVIANDO'; temporizador: ReturnType<typeof setTimeout> | null };
type Fallo = { a: AccionRapida; id: string; mensaje: string; incierto: boolean };

export function useAccionRapida(p: {
  nuevoId: () => string;
  /** Tras un OK: la pantalla vuelve a leer; la fila sigue oculta hasta que termina. */
  onHecha: (clave: string) => void | Promise<void>;
}) {
  const vivas = useRef(new Map<string, Viva>()); // guarda síncrona: un segundo gesto no crea otra intención
  const identidades = useRef(new Map<string, string>()); // se conservan tras un INDETERMINADO
  const montado = useRef(true);
  const onHecha = useRef(p.onHecha);
  onHecha.current = p.onHecha;
  const [, setVersion] = useState(0);
  const [fallos, setFallos] = useState<Fallo[]>([]);
  const refrescar = () => montado.current && setVersion((v) => v + 1);
  const quitarFallo = (clave: string) => setFallos((l) => l.filter((x) => x.a.clave !== clave));

  const enviar = useCallback(async (clave: string) => {
    const v = vivas.current.get(clave);
    if (!v) return;
    v.fase = 'ENVIANDO';
    v.temporizador = null;
    refrescar();
    let r: Respuesta<unknown>;
    try {
      r = await v.a.enviar(v.id);
    } catch {
      r = { tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.' };
    }
    if (!montado.current) return;
    if (r.tipo === 'OK') {
      identidades.current.delete(clave);
      try {
        await onHecha.current(clave);
      } finally {
        vivas.current.delete(clave);
        refrescar();
      }
      return;
    }
    vivas.current.delete(clave);
    if (r.tipo === 'RECHAZADO') identidades.current.delete(clave);
    const incierto = r.tipo === 'INDETERMINADO';
    const mensaje = r.mensaje || TEXTO_RECHAZO_GENERICO;
    setFallos((l) => [...l.filter((x) => x.a.clave !== clave), { a: v.a, id: v.id, mensaje, incierto }]);
    AccessibilityInfo.announceForAccessibility?.(incierto ? `No sabemos si se guardó ${v.a.texto}. ${mensaje}` : `No se ha guardado. ${mensaje}`);
    refrescar();
  }, []);

  const lanzar = useCallback((a: AccionRapida): boolean => {
    if (vivas.current.has(a.clave)) return false;
    const id = identidades.current.get(a.clave) ?? p.nuevoId();
    identidades.current.set(a.clave, id);
    const v: Viva = { a, id, fase: 'ESPERA', temporizador: null };
    vivas.current.set(a.clave, v);
    v.temporizador = setTimeout(() => void enviar(a.clave), ESPERA_DESHACER_MS);
    quitarFallo(a.clave);
    AccessibilityInfo.announceForAccessibility?.(`${a.texto}. Deshacer durante 5 segundos`);
    refrescar();
    return true;
  }, [p.nuevoId, enviar]);

  /** Cancela la espera: no se envía nada. */
  const cancelar = useCallback((clave: string) => {
    const v = vivas.current.get(clave);
    if (!v || v.fase !== 'ESPERA') return;
    if (v.temporizador) clearTimeout(v.temporizador);
    vivas.current.delete(clave);
    refrescar();
  }, []);
  const cancelarTodas = useCallback(() => {
    for (const [clave, v] of [...vivas.current]) if (v.fase === 'ESPERA') cancelar(clave);
  }, [cancelar]);

  const reintentar = (f: Fallo) => {
    if (vivas.current.has(f.a.clave)) return;
    quitarFallo(f.a.clave);
    vivas.current.set(f.a.clave, { a: f.a, id: f.id, fase: 'ENVIANDO', temporizador: null });
    void enviar(f.a.clave);
  };

  // Si la app se va a segundo plano (o se cierra) durante la espera, no se envía nada.
  useEffect(() => {
    const sub = AppState.addEventListener?.('change', (e) => {
      if (e === 'background') cancelarTodas();
    });
    return () => sub?.remove?.();
  }, [cancelarTodas]);
  useEffect(() => {
    montado.current = true;
    return () => {
      montado.current = false;
      for (const v of vivas.current.values()) if (v.fase === 'ESPERA' && v.temporizador) clearTimeout(v.temporizador);
    };
  }, []);

  const lista = [...vivas.current.values()];
  const avisos = lista.length > 0 || fallos.length > 0 ? (
    <AvisosAccionRapida vivas={lista} fallos={fallos} onDeshacer={cancelar} onReintentar={reintentar} onCerrar={quitarFallo} />
  ) : null;
  return {
    lanzar,
    /** La fila sale mientras espera, se envía o la pantalla vuelve a leer tras el OK. */
    oculta: (clave: string) => vivas.current.has(clave),
    avisos,
  };
}

/** Anillo de 5 s alrededor de «Deshacer»: se vacía en sentido horario (dos semicírculos que giran). */
function AnilloDeshacer(p: { color: string; pista: string }) {
  const resto = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const a = Animated.timing(resto, { toValue: 0, duration: ESPERA_DESHACER_MS, useNativeDriver: false });
    a.start();
    return () => a.stop();
  }, [resto]);
  // Arco restante = 360·resto, desde las 12 en sentido horario: mitad derecha hasta 180°, luego la izquierda.
  const giroDerecha = resto.interpolate({ inputRange: [0, 0.5, 1], outputRange: ['-135deg', '45deg', '45deg'] });
  const giroIzquierda = resto.interpolate({ inputRange: [0, 0.5, 1], outputRange: ['-135deg', '-135deg', '45deg'] });
  const arco = { borderColor: 'transparent', borderWidth: ANILLO_GROSOR };
  return (
    <View testID="anillo-deshacer" style={s.anillo}>
      <View style={[s.anilloPista, { borderColor: p.pista }]} />
      <View style={[s.mitad, { left: ANILLO / 2 }]}>
        <Animated.View style={[s.arco, { left: -ANILLO / 2 }, arco, { borderTopColor: p.color, borderRightColor: p.color, transform: [{ rotate: giroDerecha }] }]} />
      </View>
      <View style={[s.mitad, { left: 0 }]}>
        <Animated.View style={[s.arco, arco, { borderBottomColor: p.color, borderLeftColor: p.color, transform: [{ rotate: giroIzquierda }] }]} />
      </View>
    </View>
  );
}

function AvisosAccionRapida(p: {
  vivas: Viva[];
  fallos: Fallo[];
  onDeshacer: (clave: string) => void;
  onReintentar: (f: Fallo) => void;
  onCerrar: (clave: string) => void;
}) {
  const { c } = useTema();
  // Lámina: píldora translúcida con los colores invertidos de la pantalla (tokens del DS, sin colores físicos).
  const texto = [tipo.subheadline, { color: c.background, flexShrink: 1 }];
  const capa = <View pointerEvents="none" style={[StyleSheet.absoluteFill, s.capa, { backgroundColor: c.textPrimary }]} />;
  return (
    <View testID="avisos-rapida" pointerEvents="box-none" accessibilityLiveRegion="polite" style={s.avisos}>
      {p.vivas.map((v) => (
        <View key={v.a.clave} testID={`aviso-rapida-${v.a.clave}`} style={s.pildora}>
          {capa}
          <View style={[s.ok, { backgroundColor: c.accent }]}>
            <Ionicons name="checkmark" size={15} color={c.onAccent} />
          </View>
          <Text testID={`aviso-rapida-${v.a.clave}-texto`} numberOfLines={2} style={texto}>{v.fase === 'ESPERA' ? v.a.texto : `Guardando: ${v.a.texto}…`}</Text>
          {v.fase === 'ESPERA' ? (
            <Pressable testID={`aviso-rapida-${v.a.clave}-deshacer`} accessibilityRole="button" accessibilityLabel="Deshacer" hitSlop={8}
              onPress={() => p.onDeshacer(v.a.clave)} style={s.deshacer}>
              <View pointerEvents="none" style={[StyleSheet.absoluteFill, s.deshacerFondo, { backgroundColor: c.background }]} />
              <AnilloDeshacer color={c.accentSurface} pista={c.textSecondary} />
              <Text style={[tipo.subheadline, { color: c.background, fontWeight: '600' }]}>Deshacer</Text>
            </Pressable>
          ) : null}
        </View>
      ))}
      {p.fallos.map((f) => (
        <View key={f.a.clave} testID={`fallo-rapida-${f.a.clave}`} accessibilityRole="alert" style={[s.fallo, { backgroundColor: c.textPrimary }]}>
          <Text testID={`fallo-rapida-${f.a.clave}-texto`} style={texto}>
            {f.incierto ? `No sabemos si se guardó: ${f.a.texto}. ${f.mensaje}` : `No se ha guardado: ${f.a.texto}. ${f.mensaje}`}
          </Text>
          <View style={s.botones}>
            {f.incierto ? <BotonAviso testID={`fallo-rapida-${f.a.clave}-reintentar`} titulo="Reintentar" onPress={() => p.onReintentar(f)} /> : null}
            <BotonAviso testID={`fallo-rapida-${f.a.clave}-cerrar`} titulo="Cerrar" onPress={() => p.onCerrar(f.a.clave)} />
          </View>
        </View>
      ))}
    </View>
  );
}

function BotonAviso(p: { testID: string; titulo: string; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable testID={p.testID} accessibilityRole="button" accessibilityLabel={p.titulo} onPress={p.onPress} hitSlop={8} style={s.botonAviso}>
      <Text style={[tipo.subheadline, { color: c.background, fontWeight: '700' }]}>{p.titulo}</Text>
    </Pressable>
  );
}

const ANILLO = 20;
const ANILLO_GROSOR = 2.5;

const s = StyleSheet.create({
  envoltorio: { borderRadius: radio.l, overflow: 'hidden' },
  tarjeta: { borderRadius: radio.l, borderWidth: StyleSheet.hairlineWidth },
  swipe: { overflow: 'hidden' },
  fondo: { ...StyleSheet.absoluteFill, flexDirection: 'row', alignItems: 'center', paddingHorizontal: espacio.l },
  fondoDerecha: { justifyContent: 'flex-start' },
  fondoIzquierda: { justifyContent: 'flex-end' },
  boton: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN },
  botonIzquierda: { flexDirection: 'row-reverse' },
  circulo: { width: 46, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center' },
  circuloTotal: { transform: [{ scale: 1.08 }] },
  avisos: { position: 'absolute', left: espacio.l, right: espacio.l, bottom: espacio.l, gap: espacio.s, alignItems: 'center' },
  pildora: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, borderRadius: radio.pill, paddingVertical: 7, paddingLeft: 8, paddingRight: 7, maxWidth: '100%', overflow: 'hidden' },
  capa: { opacity: 0.9, borderRadius: radio.pill },
  ok: { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  deshacer: { flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: radio.pill, paddingVertical: 6, paddingLeft: 6, paddingRight: 12, minHeight: 32, overflow: 'hidden' },
  deshacerFondo: { opacity: 0.14, borderRadius: radio.pill },
  anillo: { width: ANILLO, height: ANILLO },
  anilloPista: { position: 'absolute', width: ANILLO, height: ANILLO, borderRadius: ANILLO / 2, borderWidth: ANILLO_GROSOR, opacity: 0.35 },
  mitad: { position: 'absolute', top: 0, width: ANILLO / 2, height: ANILLO, overflow: 'hidden' },
  arco: { position: 'absolute', top: 0, width: ANILLO, height: ANILLO, borderRadius: ANILLO / 2 },
  fallo: { alignSelf: 'stretch', borderRadius: radio.l, paddingHorizontal: espacio.l, paddingVertical: espacio.s, gap: espacio.xs },
  botones: { flexDirection: 'row', justifyContent: 'flex-end', gap: espacio.l },
  botonAviso: { minHeight: TACTIL_MIN, justifyContent: 'center' },
});
