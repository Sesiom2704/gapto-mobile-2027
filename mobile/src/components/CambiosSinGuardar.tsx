// ============================================================
// GAPTO MOBILE 2027
// Fichero: CambiosSinGuardar.tsx
// Ruta: mobile/src/components/CambiosSinGuardar.tsx
// Descripción: M-03 con Q-UX-06 (T1-F06 UX-1): «Más» desde la barra inferior estando ya en «Más» vuelve al menú «Más»; si un formulario de la pila de «Más» tiene cambios sin guardar, antes pregunta «¿Descartar cambios?» con «Descartar» (vuelve al menú y se pierden) y «Seguir editando» (no cambia nada). Contiene: la decisión pura de la barra (`accionBarra`), la señal «hay cambios» que publica cada formulario (`usarCambiosSinGuardar`: compara el formulario con el que había al abrirlo; estado del cliente, nada se guarda) y la hoja de confirmación. Cambiar a otra pestaña y volver no cambia: la pila se conserva.
// Versión: 0.1.0 (F06 T1 UX-1 · M-03, Q-UX-06)
// Versión: 0.2.0 (F06 T1 UX-1 · DUD-UX1-01, decisión de Moisés del lote 26): `usarCambiosSinGuardar` devuelve además `salir` y `hojaDescartar`: salir de un formulario con cambios por «Cancelar»/«Atrás»/cerrar pregunta «¿Descartar cambios?» (Descartar / Seguir editando); sin cambios sale sin preguntar. La app no tiene gesto de deslizar atrás (sin librería de navegación hasta F11): no hay nada más que interceptar.
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTema } from '../theme/tema';
import { espacio, radio, tipo } from '../theme/tokens';
import { BotonPrimario, Velo } from './Basicos';
import type { Destino } from './BarraInferior';
import { BotonSecundario } from './SelectorCategorias';

export type AccionBarra = { tipo: 'IR'; destino: Destino } | { tipo: 'MENU_MAS' } | { tipo: 'PREGUNTAR' };

/**
 * Qué hace la barra inferior al pulsar `d`: cualquier pestaña distinta (o «Más» desde otra) → ir a ella, sin tocar la
 * pila; «Más» estando en «Más» fuera del menú → volver al menú, o PREGUNTAR si hay cambios sin guardar.
 */
export function accionBarra(d: Destino, destino: Destino, enMenuMas: boolean, hayCambios: boolean): AccionBarra {
  if (d !== 'MAS' || destino !== 'MAS' || enMenuMas) return { tipo: 'IR', destino: d };
  return hayCambios ? { tipo: 'PREGUNTAR' } : { tipo: 'MENU_MAS' };
}

/** Lo que devuelve la señal de un formulario: si hay cambios, la salida guardada y la hoja que la confirma. */
export interface SalidaFormulario {
  hay: boolean;
  /** «Cancelar» / «Atrás» / cerrar: con cambios pregunta «¿Descartar cambios?»; sin cambios sale sin preguntar. */
  salir: (accion: () => void) => void;
  /** La hoja «¿Descartar cambios?» mientras hay una salida pendiente de confirmar (o null). */
  hojaDescartar: React.ReactNode;
}

/**
 * Señal «hay cambios sin guardar» de un formulario de la pila de «Más»: mientras `abierto`, compara el formulario con
 * el que tenía al abrirse y lo publica; al cerrarse o desmontarse publica `false`. DUD-UX1-01 (decisión de Moisés):
 * la misma hoja guarda la salida del formulario por «Cancelar»/«Atrás»/cerrar (`salir`): Descartar ejecuta la salida,
 * Seguir editando no cambia nada.
 */
export function usarCambiosSinGuardar(abierto: boolean, form: unknown, publicar?: (hay: boolean) => void): SalidaFormulario {
  const inicial = useRef<string | null>(null);
  const [pendiente, setPendiente] = useState<(() => void) | null>(null);
  const actual = JSON.stringify(form);
  if (!abierto) inicial.current = null;
  else if (inicial.current === null) inicial.current = actual;
  const hay = abierto && inicial.current !== actual;
  useEffect(() => {
    publicar?.(hay);
  }, [hay]);
  useEffect(() => () => publicar?.(false), []);
  const salir = (accion: () => void) => {
    if (hay) setPendiente(() => accion);
    else accion();
  };
  const hojaDescartar = pendiente ? (
    <HojaDescartarCambios
      onDescartar={() => {
        const a = pendiente;
        setPendiente(null);
        a();
      }}
      onSeguir={() => setPendiente(null)}
    />
  ) : null;
  return { hay, salir, hojaDescartar };
}

/** Hoja «¿Descartar cambios?» (Q-UX-06). */
export function HojaDescartarCambios(p: { onDescartar: () => void; onSeguir: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View testID="descartar-cambios" style={[StyleSheet.absoluteFill, s.capa, { justifyContent: 'flex-end' }]}>
      <Velo />
      <View style={[s.hoja, { backgroundColor: c.surfacePrimary, paddingBottom: inset.bottom + espacio.l }]}>
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>¿Descartar cambios?</Text>
        <BotonPrimario testID="descartar-cambios-descartar" titulo="Descartar" onPress={p.onDescartar} />
        <BotonSecundario testID="descartar-cambios-seguir" titulo="Seguir editando" onPress={p.onSeguir} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  capa: { zIndex: 20, elevation: 20 },
  hoja: { borderTopLeftRadius: radio.xl, borderTopRightRadius: radio.xl, padding: espacio.l, gap: espacio.m },
});
