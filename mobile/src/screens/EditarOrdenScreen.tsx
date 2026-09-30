// ============================================================
// GAPTO MOBILE 2027
// Fichero: EditarOrdenScreen.tsx
// Ruta: mobile/src/screens/EditarOrdenScreen.tsx
// Descripción: Editar orden de un nivel de Ajustes › Categorías (D-UI-01; F05-D012 §26.3; lámina SET-CAT v1.0 S06). Tarea inmersiva (sin barra inferior) con «Cancelar · Editar orden», migas del nivel y la microcopy «El orden solo cambia entre categorías del mismo nivel y se guarda de una vez». Lista el conjunto COMPLETO de hermanos (activos y desactivados, estos con el texto «Desactivada») con controles subir / bajar por fila, deshabilitados en los extremos. Solo presentación: «Guardar orden» entrega a la pantalla el orden propuesto y es la pantalla la que decide la ÚNICA llamada a POST /v1/categorias/reordenar (o ninguna si no hay cambios).
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BotonPrimario, BotonTexto } from '../components/Basicos';
import { IconoCategoriaVista } from '../components/SelectorCategorias';
import { CategoriaNodo, moverHermano } from '../domain/categoria';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

export function EditarOrdenScreen(p: {
  /** Migas del nivel («Todas» y los ancestros hasta el nivel, incluido). */
  migas: string[];
  hermanos: CategoriaNodo[];
  guardando: boolean;
  onGuardar: (orden: CategoriaNodo[]) => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [orden, setOrden] = useState<CategoriaNodo[]>(p.hermanos);

  return (
    <View testID="editar-orden" style={{ flex: 1, backgroundColor: c.background }}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <BotonTexto testID="orden-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>Editar orden</Text>
        <View style={{ width: 72 }} />
      </View>
      <Text testID="orden-migas" style={[tipo.footnote, s.migas, { color: c.textSecondary, borderBottomColor: c.separator }]}>
        {p.migas.join(' › ')}
      </Text>
      <ScrollView contentContainerStyle={{ paddingBottom: espacio.xl }}>
        <Text style={[tipo.footnote, s.ayuda, { color: c.textSecondary }]}>
          El orden solo cambia entre categorías del mismo nivel y se guarda de una vez.
        </Text>
        {orden.map((n, i) => (
          <View key={n.id} testID={`orden-fila-${n.id}`} style={[s.fila, { borderBottomColor: c.separator }]}>
            <IconoCategoriaVista iconKey={n.icon_key} />
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[tipo.body, { color: n.enabled ? c.textPrimary : c.textSecondary }]}>{n.nombre}</Text>
              {n.enabled ? null : <Text style={[tipo.caption, { color: c.textSecondary }]}>Desactivada</Text>}
            </View>
            <BotonFlecha
              testID={`orden-subir-${n.id}`}
              glifo="arrow-up"
              etiqueta={`Subir ${n.nombre}`}
              deshabilitado={i === 0 || p.guardando}
              onPress={() => setOrden((o) => moverHermano(o, i, -1))}
            />
            <BotonFlecha
              testID={`orden-bajar-${n.id}`}
              glifo="arrow-down"
              etiqueta={`Bajar ${n.nombre}`}
              deshabilitado={i === orden.length - 1 || p.guardando}
              onPress={() => setOrden((o) => moverHermano(o, i, 1))}
            />
          </View>
        ))}
      </ScrollView>
      <View style={[s.pie, { borderTopColor: c.separator, paddingBottom: inset.bottom + espacio.l }]}>
        <BotonPrimario testID="orden-guardar" titulo="Guardar orden" cargando={p.guardando} deshabilitado={p.guardando} onPress={() => p.onGuardar(orden)} />
      </View>
    </View>
  );
}

function BotonFlecha(p: { testID: string; glifo: 'arrow-up' | 'arrow-down'; etiqueta: string; deshabilitado: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.etiqueta}
      accessibilityState={{ disabled: p.deshabilitado }}
      disabled={p.deshabilitado}
      onPress={p.onPress}
      style={[s.flecha, { borderColor: c.borderStandard, opacity: p.deshabilitado ? 0.35 : 1 }]}
    >
      <Ionicons name={p.glifo} size={18} color={c.textPrimary} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  migas: { paddingHorizontal: espacio.l, paddingVertical: espacio.m, borderBottomWidth: StyleSheet.hairlineWidth },
  ayuda: { paddingHorizontal: espacio.l, paddingTop: espacio.m, paddingBottom: espacio.s },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.l, paddingVertical: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  flecha: { width: TACTIL_MIN, height: TACTIL_MIN, borderRadius: radio.s, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  pie: { padding: espacio.l, borderTopWidth: StyleSheet.hairlineWidth },
});
