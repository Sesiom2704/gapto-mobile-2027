// ============================================================
// GAPTO MOBILE 2027
// Fichero: SelectorIconos.tsx
// Ruta: mobile/src/components/SelectorIconos.tsx
// Descripción: Selector de icono de categoría (F09 §12.97.9 I02/I04; lámina SET-CAT v1.0). Hoja de altura completa «Icono de <nombre> · Cerrar» con vista previa de la categoría con el icono elegido, opción «Sin icono» (→ null: la app usa el icono de reserva, que nunca se persiste) y las claves ACTIVAS de la biblioteca v1 agrupadas con su etiqueta visible. La elegida se marca con check Y texto («Elegido»), nunca solo con color. La acción principal la decide el llamador («Guardar icono» en el detalle; «Usar este icono» en el alta). Solo claves publicadas: el cliente nunca inventa ni recorta claves.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { categoriaIconoFallback, iconoDe, iconosActivosPorGrupo } from '../theme/iconosCategoria';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto } from './Basicos';
import { IconoCategoriaVista } from './SelectorCategorias';

export function SelectorIconos(p: {
  nombreCategoria: string;
  inicial: string | null;
  accion: string;
  guardando?: boolean;
  aviso?: string | null;
  onAccion: (iconKey: string | null) => void;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  // Una clave inicial desconocida (legacy) se muestra como reserva y no se preselecciona.
  const [elegida, setElegida] = useState<string | null>(iconoDe(p.inicial) ? p.inicial : null);
  const cambiado = elegida !== p.inicial;

  return (
    <View testID="selector-iconos" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <View style={{ width: 72 }} />
        <Text accessibilityRole="header" numberOfLines={1} style={[tipo.titleSmall, { color: c.textPrimary, flexShrink: 1 }]}>Icono de {p.nombreCategoria}</Text>
        <BotonTexto testID="iconos-cerrar" titulo="Cerrar" onPress={p.onCerrar} />
      </View>
      <ScrollView contentContainerStyle={[s.cuerpo, { paddingBottom: inset.bottom + espacio.xl }]}>
        <View testID="iconos-vista-previa" style={s.vista}>
          <IconoCategoriaVista iconKey={elegida} tamano={20} />
          <View style={{ flex: 1 }}>
            <Text style={[tipo.body, { color: c.textPrimary }]}>{p.nombreCategoria}</Text>
            <Text style={[tipo.caption, { color: c.textSecondary }]}>Vista previa con el icono elegido</Text>
          </View>
        </View>

        <Text style={[tipo.footnote, { color: c.textSecondary }]}>Sin icono</Text>
        <View style={s.rejilla}>
          <CeldaIcono testID="icono-ninguno" glifo={categoriaIconoFallback} etiqueta="Sin icono" elegida={elegida === null} onPress={() => setElegida(null)} />
        </View>

        {iconosActivosPorGrupo().map(({ grupo, iconos }) => (
          <View key={grupo} style={{ gap: espacio.s }}>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{grupo}</Text>
            <View style={s.rejilla}>
              {iconos.map((i) => (
                <CeldaIcono key={i.clave} testID={`icono-${i.clave}`} glifo={i.glifo} etiqueta={i.etiqueta} elegida={elegida === i.clave} onPress={() => setElegida(i.clave)} />
              ))}
            </View>
          </View>
        ))}

        {p.aviso ? (
          <Text testID="iconos-aviso" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{p.aviso}</Text>
        ) : null}
        <BotonPrimario
          testID="iconos-accion"
          titulo={p.guardando ? 'Guardando…' : p.accion}
          cargando={p.guardando}
          deshabilitado={!cambiado}
          ayuda={cambiado ? undefined : 'Elige un icono distinto del actual.'}
          onPress={() => p.onAccion(elegida)}
        />
      </ScrollView>
    </View>
  );
}

function CeldaIcono(p: { testID: string; glifo: React.ComponentProps<typeof Ionicons>['name']; etiqueta: string; elegida: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="radio"
      accessibilityState={{ selected: p.elegida, checked: p.elegida }}
      accessibilityLabel={`${p.etiqueta}${p.elegida ? '. Elegido' : ''}`}
      onPress={p.onPress}
      style={[s.celda, { borderColor: p.elegida ? c.accent : 'transparent', backgroundColor: p.elegida ? c.accentSurface : undefined }]}
    >
      <View style={[s.glifo, { backgroundColor: c.surfaceSecondary }]}>
        <Ionicons name={p.glifo} size={20} color={p.elegida ? c.accent : c.textSecondary} />
      </View>
      <Text numberOfLines={1} style={[tipo.caption, { color: c.textPrimary }]}>{p.etiqueta}</Text>
      {p.elegida ? <Text style={[tipo.caption, { color: c.accent, fontWeight: '600' }]}>✓ Elegido</Text> : null}
    </Pressable>
  );
}

const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  cuerpo: { padding: espacio.l, gap: espacio.m },
  vista: { flexDirection: 'row', alignItems: 'center', gap: espacio.m },
  rejilla: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  celda: { width: 76, minHeight: TACTIL_MIN + 32, alignItems: 'center', gap: espacio.xs, borderWidth: 1.5, borderRadius: radio.m, paddingVertical: espacio.s },
  glifo: { width: 40, height: 40, borderRadius: radio.s, alignItems: 'center', justifyContent: 'center' },
});
