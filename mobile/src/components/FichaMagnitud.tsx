// ============================================================
// GAPTO MOBILE 2027
// Fichero: FichaMagnitud.tsx
// Ruta: mobile/src/components/FichaMagnitud.tsx
// Descripción: Ficha de una magnitud abierta desde una fila de la sección «Magnitudes» de una categoría (F09 §12.97.10; lámina SET-MAG v0.1 M11–M13). Cabecera «‹ <categoría> · <magnitud>» con nombre, «unidad · decimales» y píldoras de TEXTO. Bloque «En <categoría>» con las acciones de la ASOCIACIÓN: «Hacer obligatoria» / «Hacer opcional» (M11) y «Quitar de <categoría>» (M12, crítica). Las hojas las pinta el controlador encima. Solo presentación. Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1: bloque de la asociación)
// Versión: 0.2.0 (F05-01 S7-MAG UI, hito 2): `BloqueMagnitud` (M13), bloque global «Magnitud · afecta a todas sus categorías»: unidad, decimales y estado; nota de que unidad y decimales no se editan (R17); «Usada en» con la ruta de cada categoría, «esta categoría» marcada y su obligatoriedad en texto; «Aparece en N registros históricos.»; acciones Renombrar y Deshabilitar (crítica) o Rehabilitar, con la microcopy de renombrar. Estados de carga y error del catálogo distintos.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { MagnitudCategoria } from '../domain/categoria';
import { MagnitudCatalogo, textoUnidadDecimales, usosDe } from '../domain/magnitud';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonTexto, CabeceraNavegacion } from './Basicos';
import { MICROCOPY_RENOMBRAR_MAGNITUD, Pildora } from './HojasMagnitud';

export function FichaMagnitud(p: {
  categoria: string;
  asociacion: MagnitudCategoria;
  onAtras: () => void;
  onObligatoriedad: () => void;
  onQuitar: () => void;
  /** Bloque global de la magnitud (hito 2), debajo del bloque de la asociación. */
  children?: React.ReactNode;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const a = p.asociacion;
  return (
    <View testID="ficha-magnitud" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo={a.nombre} atras={{ etiqueta: p.categoria, onPress: p.onAtras }} testIDAtras="ficha-atras" />
      <ScrollView contentContainerStyle={{ paddingBottom: inset.bottom + espacio.xl }}>
        <View style={s.cabecera}>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[tipo.titleMedium, { color: a.enabled ? c.textPrimary : c.textSecondary }]}>{a.nombre}</Text>
            <Text style={[tipo.caption, { color: c.textSecondary }]}>{textoUnidadDecimales(a.unidad_default, a.precision_decimales)}</Text>
          </View>
          {a.enabled ? null : <Pildora texto="Deshabilitada" tono="DESHABILITADA" />}
          <Pildora testID="ficha-pildora" texto={a.obligatoria ? 'Obligatoria' : 'Opcional'} tono={a.obligatoria ? 'OBLIGATORIA' : 'OPCIONAL'} />
        </View>
        <Text accessibilityRole="header" style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>{`En ${p.categoria}`}</Text>
        <Accion
          testID="ficha-obligatoriedad"
          titulo={a.obligatoria ? 'Hacer opcional' : 'Hacer obligatoria'}
          onPress={p.onObligatoriedad}
        />
        <Accion testID="ficha-quitar" titulo={`Quitar de ${p.categoria}`} critica onPress={p.onQuitar} />
        {p.children}
      </ScrollView>
    </View>
  );
}

export function Accion(p: { testID: string; titulo: string; critica?: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.titulo}
      onPress={p.onPress}
      style={({ pressed }) => [s.fila, { borderBottomColor: c.separator, opacity: pressed ? 0.7 : 1 }]}
    >
      <Text style={[tipo.body, { color: p.critica ? c.critical : c.textPrimary, flex: 1 }]}>{p.titulo}</Text>
      {p.critica ? null : <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />}
    </Pressable>
  );
}

export const NOTA_R17 = 'Unidad y decimales no se editan. Para otra unidad o precisión, crea una magnitud nueva.';
export const TEXTO_HISTORICOS = (n: number) => `Aparece en ${n} ${n === 1 ? 'registro histórico' : 'registros históricos'}.`;

/** Bloque global de la magnitud (M13): afecta a todas sus categorías. */
export function BloqueMagnitud(p: {
  fase: 'CARGANDO' | 'OK' | 'ERROR';
  magnitud: MagnitudCatalogo | null;
  categoriaActual: string;
  ruta: (id: string, nombre: string) => string;
  onRenombrar: () => void;
  onDeshabilitar: () => void;
  onRehabilitar: () => void;
  onReintentar: () => void;
}) {
  const { c } = useTema();
  const m = p.magnitud;
  return (
    <View testID="bloque-magnitud">
      <Text accessibilityRole="header" style={[tipo.footnote, estilosFicha.seccion, { color: c.textSecondary }]}>Magnitud · afecta a todas sus categorías</Text>
      {p.fase === 'CARGANDO' ? <Text testID="bloque-cargando" style={[tipo.subheadline, estilosFicha.nota, { color: c.textSecondary }]}>Cargando…</Text> : null}
      {p.fase === 'ERROR' || (p.fase === 'OK' && !m) ? (
        <View testID="bloque-error" style={[estilosFicha.nota, { gap: espacio.s }]}>
          <Text style={[tipo.subheadline, { color: c.textPrimary }]}>No se han podido cargar los datos de la magnitud. Nada se ha cambiado.</Text>
          <BotonTexto testID="bloque-reintentar" titulo="Reintentar" onPress={p.onReintentar} />
        </View>
      ) : null}
      {p.fase === 'OK' && m ? (
        <>
          <Dato etiqueta="Unidad" valor={m.unidad_default} testID="bloque-unidad" />
          <Dato etiqueta="Decimales" valor={String(m.precision_decimales)} testID="bloque-decimales" />
          <Dato etiqueta="Estado" valor={m.enabled ? 'Activa' : 'Deshabilitada'} testID="bloque-estado" />
          <Text testID="bloque-r17" style={[tipo.caption, estilosFicha.nota, { color: c.textSecondary }]}>{NOTA_R17}</Text>
          <Text accessibilityRole="header" style={[tipo.footnote, estilosFicha.seccion, { color: c.textSecondary }]}>Usada en</Text>
          {usosDe(m).map((u) => (
            <View
              key={u.id}
              testID={`usada-${u.id}`}
              accessible
              accessibilityLabel={[p.ruta(u.id, u.nombre), u.id === p.categoriaActual ? 'esta categoría' : null, u.enabled ? null : 'Desactivada', u.obligatoria ? 'Obligatoria' : 'Opcional'].filter(Boolean).join('. ')}
              style={[estilosFicha.fila, { borderBottomColor: c.separator }]}
            >
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={[tipo.body, { color: u.enabled ? c.textPrimary : c.textSecondary }]}>{p.ruta(u.id, u.nombre)}</Text>
                {u.id === p.categoriaActual || !u.enabled ? (
                  <Text style={[tipo.caption, { color: c.textSecondary }]}>{[u.id === p.categoriaActual ? 'esta categoría' : null, u.enabled ? null : 'Desactivada'].filter(Boolean).join(' · ')}</Text>
                ) : null}
              </View>
              <Pildora texto={u.obligatoria ? 'Obligatoria' : 'Opcional'} tono={u.obligatoria ? 'OBLIGATORIA' : 'OPCIONAL'} />
            </View>
          ))}
          <Text testID="bloque-historicos" style={[tipo.footnote, estilosFicha.nota, { color: c.textSecondary }]}>{TEXTO_HISTORICOS(m.n_hechos)}</Text>
          <Text accessibilityRole="header" style={[tipo.footnote, estilosFicha.seccion, { color: c.textSecondary }]}>Acciones</Text>
          <Accion testID="bloque-renombrar" titulo="Renombrar" onPress={p.onRenombrar} />
          {m.enabled ? (
            <Accion testID="bloque-deshabilitar" titulo="Deshabilitar" critica onPress={p.onDeshabilitar} />
          ) : (
            <Accion testID="bloque-rehabilitar" titulo="Rehabilitar" onPress={p.onRehabilitar} />
          )}
          <Text style={[tipo.caption, estilosFicha.nota, { color: c.textSecondary }]}>{MICROCOPY_RENOMBRAR_MAGNITUD}</Text>
        </>
      ) : null}
    </View>
  );
}

function Dato(p: { etiqueta: string; valor: string; testID: string }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} accessible accessibilityLabel={`${p.etiqueta}: ${p.valor}`} style={[estilosFicha.fila, { borderBottomColor: c.separator }]}>
      <Text style={[tipo.body, { color: c.textSecondary, flex: 1 }]}>{p.etiqueta}</Text>
      <Text style={[tipo.body, { color: c.textPrimary }]}>{p.valor}</Text>
    </View>
  );
}

export const estilosFicha = StyleSheet.create({
  seccion: { paddingHorizontal: espacio.l, paddingTop: espacio.l, paddingBottom: espacio.xs },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 4, paddingHorizontal: espacio.l, borderBottomWidth: StyleSheet.hairlineWidth },
  nota: { paddingHorizontal: espacio.l, paddingTop: espacio.m },
});

const s = StyleSheet.create({
  cabecera: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, padding: espacio.l },
  seccion: estilosFicha.seccion,
  fila: estilosFicha.fila,
});
