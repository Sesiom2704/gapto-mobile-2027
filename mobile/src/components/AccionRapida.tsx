// ============================================================
// GAPTO MOBILE 2027
// Fichero: AccionRapida.tsx
// Ruta: mobile/src/components/AccionRapida.tsx
// Descripción: Swipe como acción rápida en toda la app (F05-06 M5 SWIPE; regla de Moisés del 2026-10-22, que sustituye a DAY-RULE-03 y a D-PREV-08/12 en lo que contradigan). Pieza común de todas las pantallas: FilaDeslizable (la fila sigue al dedo con tope y deja ver detrás la franja de la acción, de acento pasado el umbral; al soltar vuelve) y useAccionRapida (aviso «<Nombre> cobrada/pagada · Deshacer» durante 5 s; la petición sale al terminar la espera y «Deshacer» la cancela sin tocar el servidor). La identidad de la intención se fija al soltar y se conserva tras un INDETERMINADO, para que el reintento sea idempotente; un segundo gesto sobre la misma fila mientras espera o envía se ignora. Si la app pasa a segundo plano o la pantalla se desmonta durante la espera, no se envía nada. Un rechazo devuelve la fila con el motivo del servidor; nunca un éxito falso. Solo para acciones que crean o confirman realidad con datos completos: nunca anular, borrar, corregir ni omitir.
// Versión: 0.1.0 (F05-06 M5 SWIPE)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, AppState, PanResponder, Pressable, StyleSheet, Text, View } from 'react-native';

import type { Respuesta } from '../api/cliente';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

/** Espera antes de enviar: el tiempo de «Deshacer». */
export const ESPERA_DESHACER_MS = 5000;
/** Distancia horizontal (px) a la izquierda que dispara el swipe. */
export const UMBRAL_SWIPE = 72;
/** Desplazamiento máximo (px) de la fila durante el swipe: deja ver la franja entera sin vaciar la fila. */
export const TOPE_SWIPE = 160;

/** Texto llano cuando el servidor rechaza sin mensaje. */
export const TEXTO_RECHAZO_GENERICO = 'El servidor no lo ha aceptado.';

type FaseSwipe = 'reposo' | 'arrastrando' | 'superado';

/** Fila con swipe a la izquierda. Sin `onDeslizar` se pinta la fila tal cual, sin gesto. */
export function FilaDeslizable(p: {
  /** Prefijo de los testID: `fila-swipe-<id>`, `fila-desplazable-<id>` y `franja-<franjaId>-<id>`. */
  id: string;
  franjaId: string;
  franja: string;
  onDeslizar?: () => void;
  /** Fondo de la fila mientras se desplaza (el de la pantalla o el de la superficie). */
  fondo?: 'background' | 'surfacePrimary';
  children: React.ReactNode;
}) {
  const { c } = useTema();
  const onDeslizar = useRef(p.onDeslizar);
  onDeslizar.current = p.onDeslizar;
  const desplazamiento = useRef(new Animated.Value(0)).current;
  const [fase, setFase] = useState<FaseSwipe>('reposo');
  // El contenedor CAPTURA el movimiento horizontal: el Pressable de la fila es responder desde el toque y sus manejadores
  // pisarían los del gesto (en web y en nativo); al capturar, el Pressable se cancela y no hay toque.
  const gesto = useMemo(() => {
    const horizontal = (g: { dx: number; dy: number }) => !!onDeslizar.current && Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy);
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
        if (onDeslizar.current && g.dx <= -UMBRAL_SWIPE) onDeslizar.current();
      },
      onPanResponderTerminate: volver,
    });
  }, [desplazamiento]);
  if (!p.onDeslizar) return <>{p.children}</>;
  const superado = fase === 'superado';
  return (
    <View testID={`fila-swipe-${p.id}`} style={s.swipe} {...gesto.panHandlers}>
      {fase !== 'reposo' ? (
        // Decorativa: la acción accesible sigue en la fila; VoiceOver no ve la franja.
        <View testID={`franja-${p.franjaId}-${p.id}`} accessibilityElementsHidden importantForAccessibility="no-hide-descendants"
          style={[s.franja, { backgroundColor: superado ? c.accent : c.accentSurface }]}>
          <Ionicons name="checkmark" size={18} color={superado ? c.onAccent : c.accent} />
          <Text style={[tipo.body, { color: superado ? c.onAccent : c.accent, fontWeight: '600' }]}>{p.franja}</Text>
        </View>
      ) : null}
      <Animated.View testID={`fila-desplazable-${p.id}`} style={{ backgroundColor: c[p.fondo ?? 'surfacePrimary'], transform: [{ translateX: desplazamiento }] }}>
        {p.children}
      </Animated.View>
    </View>
  );
}

/** Una acción rápida: `enviar` compone la petición con la identidad fijada al soltar. */
export interface AccionRapida {
  clave: string;
  /** «Nómina cobrada», «Electricidad pagada». */
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

function AvisosAccionRapida(p: {
  vivas: Viva[];
  fallos: Fallo[];
  onDeshacer: (clave: string) => void;
  onReintentar: (f: Fallo) => void;
  onCerrar: (clave: string) => void;
}) {
  const { c } = useTema();
  // Colores invertidos para que el aviso destaque sobre la pantalla, con tokens del DS.
  const fondo = { backgroundColor: c.textPrimary };
  const texto = [tipo.subheadline, { color: c.background, flexShrink: 1 }];
  return (
    <View testID="avisos-rapida" pointerEvents="box-none" accessibilityLiveRegion="polite" style={s.avisos}>
      {p.vivas.map((v) => (
        <View key={v.a.clave} testID={`aviso-rapida-${v.a.clave}`} style={[s.aviso, fondo]}>
          <Text testID={`aviso-rapida-${v.a.clave}-texto`} style={texto}>{v.fase === 'ESPERA' ? v.a.texto : `Guardando: ${v.a.texto}…`}</Text>
          {v.fase === 'ESPERA' ? <BotonAviso testID={`aviso-rapida-${v.a.clave}-deshacer`} titulo="Deshacer" onPress={() => p.onDeshacer(v.a.clave)} /> : null}
        </View>
      ))}
      {p.fallos.map((f) => (
        <View key={f.a.clave} testID={`fallo-rapida-${f.a.clave}`} accessibilityRole="alert" style={[s.aviso, s.fallo, fondo]}>
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
    <Pressable testID={p.testID} accessibilityRole="button" accessibilityLabel={p.titulo} onPress={p.onPress} hitSlop={8} style={s.boton}>
      <Text style={[tipo.subheadline, { color: c.background, fontWeight: '700' }]}>{p.titulo}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  swipe: { overflow: 'hidden' },
  franja: { ...StyleSheet.absoluteFill, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: espacio.s, paddingHorizontal: espacio.m },
  avisos: { position: 'absolute', left: espacio.l, right: espacio.l, bottom: espacio.l, gap: espacio.s },
  aviso: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.m, borderRadius: radio.m, paddingHorizontal: espacio.l, paddingVertical: espacio.s, minHeight: 52 },
  fallo: { flexDirection: 'column', alignItems: 'stretch' },
  botones: { flexDirection: 'row', justifyContent: 'flex-end', gap: espacio.l },
  boton: { minHeight: TACTIL_MIN, justifyContent: 'center' },
});
