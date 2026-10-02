// ============================================================
// GAPTO MOBILE 2027
// Fichero: SelectorMagnitudes.tsx
// Ruta: mobile/src/components/SelectorMagnitudes.tsx
// Descripción: Selector del catálogo de magnitudes del owner para añadir una a la categoría (F09 §12.97.10; lámina SET-MAG v0.1 M06; GET /v1/magnitudes). Tarea inmersiva «Cancelar · Añadir magnitud a <categoría>» con búsqueda por nombre y tres secciones: «Disponibles», «Deshabilitadas» (marcadas en texto) y «Ya en <categoría>» (atenuadas, con check y su obligatoriedad, no elegibles). Subtítulo «unidad · decimales · usada en …» / «sin categorías». Error de carga distinto de «sin resultados». Al pie, «Nueva magnitud» cuando el llamador la ofrece (alta rápida, M07). Solo presentación: elegir entrega la magnitud al controlador. Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { MagnitudCategoria } from '../domain/categoria';
import { MagnitudCatalogo, seccionesSelector, subtituloCatalogo } from '../domain/magnitud';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonTexto } from './Basicos';
import type { FaseCatalogo } from './SeccionMagnitudes';
import { BotonSecundario } from './SelectorCategorias';

export function SelectorMagnitudes(p: {
  categoria: string;
  fase: FaseCatalogo;
  catalogo: MagnitudCatalogo[];
  asociadas: MagnitudCategoria[];
  onElegir: (m: MagnitudCatalogo) => void;
  onNueva?: () => void;
  onCerrar: () => void;
  onReintentar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [busqueda, setBusqueda] = useState('');
  const sec = seccionesSelector(p.catalogo, p.asociadas, busqueda);
  const sinResultados = p.fase === 'OK' && !sec.disponibles.length && !sec.deshabilitadas.length && !sec.yaEn.length;

  const fila = (m: MagnitudCatalogo) => (
    <Pressable
      key={m.id}
      testID={`selmag-${m.id}`}
      accessibilityRole="button"
      accessibilityLabel={`${m.nombre}. ${subtituloCatalogo(m)}`}
      onPress={() => p.onElegir(m)}
      style={({ pressed }) => [s.fila, { borderBottomColor: c.separator, opacity: pressed ? 0.7 : 1 }]}
    >
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[tipo.body, { color: m.enabled ? c.textPrimary : c.textSecondary }]}>{m.nombre}</Text>
        <Text style={[tipo.caption, { color: c.textSecondary }]}>{subtituloCatalogo(m)}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );

  return (
    <View testID="selector-magnitudes" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <BotonTexto testID="selmag-cancelar" titulo="Cancelar" onPress={p.onCerrar} />
        <Text accessibilityRole="header" numberOfLines={1} style={[tipo.titleSmall, { color: c.textPrimary, flexShrink: 1 }]}>
          {`Añadir magnitud a ${p.categoria}`}
        </Text>
        <View style={{ width: 72 }} />
      </View>
      <View style={s.buscar}>
        <TextInput
          testID="selmag-buscar"
          accessibilityLabel="Buscar por nombre"
          placeholder="Buscar por nombre"
          placeholderTextColor={c.textSecondary}
          value={busqueda}
          onChangeText={setBusqueda}
          style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfaceSecondary }]}
        />
      </View>
      <ScrollView contentContainerStyle={{ paddingBottom: espacio.xl }}>
        {p.fase === 'CARGANDO' ? <Text testID="selmag-cargando" style={[tipo.subheadline, s.relleno, { color: c.textSecondary }]}>Cargando…</Text> : null}
        {p.fase === 'ERROR' ? (
          <View testID="selmag-error" style={[s.relleno, { gap: espacio.s }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>No hemos podido cargar tus magnitudes. Nada se ha cambiado.</Text>
            <BotonSecundario testID="selmag-reintentar" titulo="Reintentar" onPress={p.onReintentar} />
          </View>
        ) : null}
        {sinResultados ? (
          <Text testID="selmag-vacio" style={[tipo.subheadline, s.relleno, { color: c.textSecondary }]}>
            {busqueda.trim() ? 'Ninguna magnitud coincide con la búsqueda.' : 'Aún no tienes magnitudes.'}
          </Text>
        ) : null}
        {sec.disponibles.length ? <Text accessibilityRole="header" style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>Disponibles</Text> : null}
        {sec.disponibles.map(fila)}
        {sec.deshabilitadas.length ? <Text accessibilityRole="header" style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>Deshabilitadas</Text> : null}
        {sec.deshabilitadas.map(fila)}
        {sec.yaEn.length ? <Text accessibilityRole="header" style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>{`Ya en ${p.categoria}`}</Text> : null}
        {sec.yaEn.map((a) => (
          <View
            key={a.magnitud_id}
            testID={`selmag-ya-${a.magnitud_id}`}
            accessible
            accessibilityLabel={`${a.nombre}. Ya en ${p.categoria}, ${a.obligatoria ? 'obligatoria' : 'opcional'}`}
            accessibilityState={{ disabled: true, checked: true }}
            style={[s.fila, { borderBottomColor: c.separator }]}
          >
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[tipo.body, { color: c.textSecondary }]}>{a.nombre}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>{a.obligatoria ? 'Obligatoria' : 'Opcional'}</Text>
            </View>
            <Ionicons name="checkmark" size={18} color={c.accent} />
          </View>
        ))}
      </ScrollView>
      {p.onNueva ? (
        <View style={[s.pie, { borderTopColor: c.separator, paddingBottom: inset.bottom + espacio.l }]}>
          <BotonSecundario testID="selmag-nueva" titulo="Nueva magnitud" onPress={p.onNueva} />
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.s, paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  buscar: { paddingHorizontal: espacio.l, paddingVertical: espacio.s },
  input: { borderRadius: radio.m, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN },
  relleno: { padding: espacio.l },
  seccion: { paddingHorizontal: espacio.l, paddingTop: espacio.l, paddingBottom: espacio.xs },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.l, paddingVertical: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  pie: { padding: espacio.l, borderTopWidth: StyleSheet.hairlineWidth },
});
