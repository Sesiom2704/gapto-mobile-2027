// ============================================================
// GAPTO MOBILE 2027
// Fichero: ColaAccionRapida.tsx
// Ruta: mobile/src/components/ColaAccionRapida.tsx
// Descripción: COLA-AR v1.0 (F05 §70.A) en la app. `colaDe(cliente)` da la ÚNICA cola de la app para ese cliente (persistida con AsyncStorage, enganchada a AppState: en segundo plano no se envía nada; al volver se reanuda o se pregunta). `useAccionFinanciera` es lo que usan las pantallas con acciones rápidas financieras (F1 «Pendiente con», F2 «Recibido», F3 «Repetir hoy», F4/F5 previsiones de Inicio y Pendientes): al soltar compone la petición con una identidad nueva y la entrega a la cola; desmontar la pantalla no cancela ni adelanta nada. `AvisosCola` es el aviso global (A.4/A.5), visible en cualquier pantalla: «Cobrando… · Deshacer» con el tiempo restante; «Comprobando el cobro…» mientras se reconcilia; «No se ha guardado · Reintentar»; la pregunta «Enviar / Descartar» tras una ausencia; el motivo del servidor si se rechaza; y el ✓ con el resultado SOLO en CONFIRMADA. La raíz de la app monta un aviso global (`global`); si no hay ninguno montado (pruebas de una pantalla suelta), la pantalla pinta el suyo.
// Versión: 0.1.0 (F05-D056 paso 2, COLA-AR v1.0)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { AccessibilityInfo, Animated, AppState, Pressable, StyleSheet, Text, View } from 'react-native';

import type { ClienteApi, Respuesta } from '../api/cliente';
import { motivoRechazoPosicion } from '../domain/reparto';
import {
  CLAVE_ALMACEN,
  ColaAccionRapida,
  type AlmacenCola,
  type EjecutorCola,
  type IntencionCola,
  type NuevaIntencion,
  type RutaCola,
  type Temporizadores,
  type TextosCola,
} from '../state/colaAccionRapida';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

// ---------------------------------------------------------------- cola de la app
/** Ejecutor de la cola con el cliente de la app: una ruta por acción financiera. */
export function ejecutorDe(cliente: ClienteApi): EjecutorCola {
  return {
    enviar: async (i: IntencionCola): Promise<Respuesta<unknown>> => {
      const p = i.payload as never;
      const id = i.recursoId ?? '';
      switch (i.ruta) {
        case 'COBRO_POSICION':
        case 'PAGO_POSICION': {
          const r = await (i.ruta === 'COBRO_POSICION' ? cliente.cobrarPosicion(id, p) : cliente.pagarPosicion(id, p));
          return r.tipo === 'RECHAZADO' ? { ...r, mensaje: motivoRechazoPosicion(r.codigo) } : r;
        }
        case 'ABONO':
          return cliente.registrarAbono(id, p);
        case 'GASTO':
          return cliente.registrarGastoPagado(p);
        case 'INGRESO':
          return cliente.registrarIngresoCobrado(p);
        case 'TRANSFERENCIA':
          return cliente.registrarTransferencia(p);
        case 'NO_HUBO':
          return cliente.omitirPrevision(id, p);
        default:
          return { tipo: 'RECHAZADO', codigo: 'RUTA_DESCONOCIDA', mensaje: 'Esta acción no se puede enviar.' };
      }
    },
    comprobarConexion: async () => (await cliente.yo()).tipo !== 'INDETERMINADO',
    estadoPrevision: async (id: string) => {
      const r = await cliente.detallePrevision(id);
      return r.tipo === 'OK' ? r.datos.estado : null;
    },
  };
}

const almacenApp: AlmacenCola = {
  leer: () => AsyncStorage.getItem(CLAVE_ALMACEN),
  escribir: (t) => AsyncStorage.setItem(CLAVE_ALMACEN, t),
};
const temporizadoresApp: Temporizadores = {
  ahora: () => Date.now(),
  programar: (fn, ms) => setTimeout(fn, ms),
  cancelar: (t) => clearTimeout(t as ReturnType<typeof setTimeout>),
};

const colas = new WeakMap<ClienteApi, ColaAccionRapida>();

/** La cola de la app para un cliente (una sola por cliente; la app tiene uno). */
export function colaDe(cliente: ClienteApi): ColaAccionRapida {
  let cola = colas.get(cliente);
  if (!cola) {
    const nueva = new ColaAccionRapida(ejecutorDe(cliente), almacenApp, temporizadoresApp);
    cola = nueva;
    colas.set(cliente, nueva);
    AppState.addEventListener?.('change', (e) => {
      if (e === 'background') nueva.alSegundoPlano();
      else if (e === 'active') nueva.alPrimerPlano();
    });
    void nueva.restaurar();
  }
  return cola;
}

/** Re-render con cada cambio de la cola. */
export function useIntenciones(cola: ColaAccionRapida): IntencionCola[] {
  const version = useRef(0);
  const sub = useCallback((avisar: () => void) => cola.suscribir(() => {
    version.current += 1;
    avisar();
  }), [cola]);
  useSyncExternalStore(sub, () => version.current);
  return cola.intenciones();
}

// ---------------------------------------------------------------- pantallas
/** Una acción rápida financiera: la petición se compone con la identidad nueva del swipe. */
export interface AccionFinanciera {
  clave: string;
  ruta: RutaCola;
  recursoId: string | null;
  textos: TextosCola;
  componer: (intencionId: string) => Record<string, unknown> & { intencion_id: string };
}

let avisosGlobales = 0;

export function useAccionFinanciera(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  /** Tras una confirmación: la pantalla vuelve a leer. */
  onHecha: () => void | Promise<void>;
}) {
  const cola = colaDe(p.cliente);
  useIntenciones(cola);
  const onHecha = useRef(p.onHecha);
  onHecha.current = p.onHecha;
  // Desmontar solo deja de escuchar: la intención sigue en la cola (A.4), sin cancelarse ni adelantarse.
  useEffect(() => cola.alConfirmarse(() => void onHecha.current()), [cola]);

  const lanzar = useCallback((a: AccionFinanciera): boolean => {
    if (cola.oculta(a.clave)) return false; // doble swipe: una sola intención
    const intencionId = p.nuevoId();
    const ok = cola.lanzar({ clave: a.clave, ruta: a.ruta, recursoId: a.recursoId, textos: a.textos, payload: a.componer(intencionId) } as NuevaIntencion);
    if (ok) AccessibilityInfo.announceForAccessibility?.(`${a.textos.enCurso}. Deshacer durante 5 segundos`);
    return ok;
  }, [cola, p.nuevoId]);

  return {
    lanzar,
    oculta: (clave: string) => cola.oculta(clave),
    /** Sin aviso global montado (pantalla suelta), la pantalla pinta el suyo. */
    avisos: <AvisosCola cola={cola} />,
  };
}

// ---------------------------------------------------------------- aviso global
/** Lo que dice el aviso de una intención en cada estado (A.5). Ni ✓ ni «Saldado» antes de CONFIRMADA. */
export function textoAviso(i: IntencionCola): string {
  if (i.estado === 'EN_PLAZO') return i.pregunta ? i.textos.pendiente : i.textos.enCurso;
  if (i.estado === 'PENDIENTE_DE_ENVIO' || i.estado === 'ENVIADA') return i.textos.enCurso;
  if (i.estado === 'RESULTADO_DESCONOCIDO') return i.textos.comprobando;
  if (i.estado === 'NO_ENVIADA') return `No se ha guardado · ${i.textos.enCurso.replace(/…/u, '')}`;
  return i.mensaje ?? '';
}

/** Tiempo de cierre automático del aviso de una confirmación. */
export const CIERRE_CONFIRMADA_MS = 4000;

export function AvisosCola(p: { cola: ColaAccionRapida; global?: boolean }) {
  const { c } = useTema();
  const lista = useIntenciones(p.cola);
  useEffect(() => {
    if (!p.global) return;
    avisosGlobales += 1;
    return () => {
      avisosGlobales -= 1;
    };
  }, [p.global]);
  const confirmadas = lista.filter((i) => i.estado === 'CONFIRMADA').map((i) => i.clave).join('|');
  useEffect(() => {
    if (!confirmadas) return;
    const t = setTimeout(() => confirmadas.split('|').forEach((k) => p.cola.cerrar(k)), CIERRE_CONFIRMADA_MS);
    return () => clearTimeout(t);
  }, [confirmadas, p.cola]);
  // El de una pantalla cede ante el global: un único aviso en toda la app.
  if (lista.length === 0 || (!p.global && avisosGlobales > 0)) return null;
  const texto = [tipo.subheadline, { color: c.background, flexShrink: 1 }];
  return (
    <View testID="avisos-rapida" pointerEvents="box-none" accessibilityLiveRegion="polite" style={s.avisos}>
      {lista.map((i) => {
        const k = i.clave;
        const confirmada = i.estado === 'CONFIRMADA';
        const final = confirmada || i.estado === 'RECHAZADA';
        const plazo = i.estado === 'EN_PLAZO' && !i.pregunta;
        return (
          <View key={k} testID={`aviso-rapida-${k}`} accessibilityRole={i.estado === 'RECHAZADA' ? 'alert' : undefined}
            style={[final || i.pregunta || i.estado === 'NO_ENVIADA' ? s.caja : s.pildora, { backgroundColor: c.textPrimary }]}>
            <View style={s.fila}>
              {confirmada ? (
                <View testID={`aviso-rapida-${k}-ok`} style={[s.ok, { backgroundColor: c.accent }]}>
                  <Ionicons name="checkmark" size={15} color={c.onAccent} />
                </View>
              ) : null}
              <Text testID={`aviso-rapida-${k}-texto`} numberOfLines={3} style={texto}>{textoAviso(i)}</Text>
              {plazo ? <Deshacer k={k} vence={i.vence} onPress={() => p.cola.deshacer(k)} /> : null}
            </View>
            {i.pregunta ? (
              <View style={s.botones}>
                <BotonAviso testID={`aviso-rapida-${k}-descartar`} titulo="Descartar" onPress={() => p.cola.descartar(k)} />
                <BotonAviso testID={`aviso-rapida-${k}-enviar`} titulo="Enviar" onPress={() => p.cola.enviarTrasAusencia(k)} />
              </View>
            ) : null}
            {i.estado === 'NO_ENVIADA' ? (
              <View style={s.botones}>
                <BotonAviso testID={`aviso-rapida-${k}-descartar`} titulo="Descartar" onPress={() => p.cola.descartar(k)} />
                <BotonAviso testID={`aviso-rapida-${k}-reintentar`} titulo="Reintentar" onPress={() => p.cola.reintentar(k)} />
              </View>
            ) : null}
            {final ? (
              <View style={s.botones}>
                <BotonAviso testID={`aviso-rapida-${k}-cerrar`} titulo="Cerrar" onPress={() => p.cola.cerrar(k)} />
              </View>
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

/** «Deshacer» con el anillo que se vacía en el tiempo RESTANTE (sigue tras navegar o volver a la app). */
function Deshacer(p: { k: string; vence: number; onPress: () => void }) {
  const { c } = useTema();
  const restante = Math.max(0, p.vence - Date.now());
  const segundos = Math.ceil(restante / 1000);
  return (
    <Pressable testID={`aviso-rapida-${p.k}-deshacer`} accessibilityRole="button" accessibilityLabel={`Deshacer, quedan ${segundos} segundos`}
      hitSlop={8} onPress={p.onPress} style={s.deshacer}>
      <View pointerEvents="none" style={[StyleSheet.absoluteFill, s.deshacerFondo, { backgroundColor: c.background }]} />
      <AnilloDeshacer restanteMs={restante} color={c.accentSurface} pista={c.textSecondary} />
      <Text style={[tipo.subheadline, { color: c.background, fontWeight: '600' }]}>Deshacer</Text>
    </Pressable>
  );
}

function AnilloDeshacer(p: { restanteMs: number; color: string; pista: string }) {
  const inicio = useRef(Math.min(1, p.restanteMs / 5000)).current;
  const resto = useRef(new Animated.Value(inicio)).current;
  useEffect(() => {
    const a = Animated.timing(resto, { toValue: 0, duration: Math.max(0, p.restanteMs), useNativeDriver: false });
    a.start();
    return () => a.stop();
    // Una sola animación por montaje: el tiempo restante se fija al montar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resto]);
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
  avisos: { position: 'absolute', left: espacio.l, right: espacio.l, bottom: espacio.l, gap: espacio.s, alignItems: 'center' },
  pildora: { borderRadius: radio.pill, paddingVertical: 7, paddingLeft: 12, paddingRight: 7, maxWidth: '100%', overflow: 'hidden', opacity: 0.94 },
  caja: { alignSelf: 'stretch', borderRadius: radio.l, paddingHorizontal: espacio.l, paddingVertical: espacio.s, gap: espacio.xs, opacity: 0.96 },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s },
  ok: { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  deshacer: { flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: radio.pill, paddingVertical: 6, paddingLeft: 6, paddingRight: 12, minHeight: 32, overflow: 'hidden' },
  deshacerFondo: { opacity: 0.14, borderRadius: radio.pill },
  anillo: { width: ANILLO, height: ANILLO },
  anilloPista: { position: 'absolute', width: ANILLO, height: ANILLO, borderRadius: ANILLO / 2, borderWidth: ANILLO_GROSOR, opacity: 0.35 },
  mitad: { position: 'absolute', top: 0, width: ANILLO / 2, height: ANILLO, overflow: 'hidden' },
  arco: { position: 'absolute', top: 0, width: ANILLO, height: ANILLO, borderRadius: ANILLO / 2 },
  botones: { flexDirection: 'row', justifyContent: 'flex-end', gap: espacio.l },
  botonAviso: { minHeight: TACTIL_MIN, justifyContent: 'center' },
});
