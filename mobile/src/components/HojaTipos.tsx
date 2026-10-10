// ============================================================
// GAPTO MOBILE 2027
// Fichero: HojaTipos.tsx
// Ruta: mobile/src/components/HojaTipos.tsx
// Descripción: Hoja «¿Qué quieres registrar?» (F05-04 J2 §2.2; F05 §46.3 A1; lámina REG-DYN T01): Gasto, Ingreso y Entre cuentas, SIN preselección; nota de devolución y «Cancelar». La abre «Registrar» de Inicio y el botón «Tipo» del formulario antes del primer envío.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.2)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { NOTA_DEVOLUCION, TipoRegistro, TIPOS_REGISTRO } from '../domain/registro';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonTexto, Velo } from './Basicos';

const ICONO: Record<TipoRegistro, React.ComponentProps<typeof Ionicons>['name']> = {
  GASTO: 'arrow-up-circle-outline',
  INGRESO: 'arrow-down-circle-outline',
  TRANSFERENCIA: 'swap-horizontal-outline',
};

export function HojaTipos(p: { actual?: TipoRegistro | null; onElegir: (t: TipoRegistro) => void; onCancelar: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View style={StyleSheet.absoluteFill}>
      <Velo />
      <View style={s.contenedor}>
        <View testID="hoja-tipos" accessibilityViewIsModal style={[s.hoja, { backgroundColor: c.background, paddingBottom: inset.bottom + espacio.l }]}>
          <View style={[s.asa, { backgroundColor: c.borderStandard }]} />
          <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>¿Qué quieres registrar?</Text>
          {TIPOS_REGISTRO.map((t) => (
            <Pressable
              key={t.tipo}
              testID={`tipo-${t.tipo}`}
              accessibilityRole="button"
              accessibilityLabel={`${t.titulo}. ${t.subtitulo}`}
              accessibilityState={{ selected: p.actual === t.tipo }}
              onPress={() => p.onElegir(t.tipo)}
              style={({ pressed }) => [s.fila, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault, opacity: pressed ? 0.8 : 1 }]}
            >
              <Ionicons name={ICONO[t.tipo]} size={26} color={c.accent} />
              <View style={{ flex: 1 }}>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{t.titulo}</Text>
                <Text style={[tipo.footnote, { color: c.textSecondary }]}>{t.subtitulo}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
            </Pressable>
          ))}
          <Text testID="nota-devolucion" style={[tipo.footnote, { color: c.textSecondary }]}>{NOTA_DEVOLUCION}</Text>
          <View style={{ alignItems: 'center' }}>
            <BotonTexto testID="tipos-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
          </View>
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  contenedor: { flex: 1, justifyContent: 'flex-end' },
  hoja: { borderTopLeftRadius: radio.xl, borderTopRightRadius: radio.xl, padding: espacio.l, gap: espacio.m },
  asa: { alignSelf: 'center', width: 36, height: 5, borderRadius: 3 },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderRadius: radio.m, borderWidth: StyleSheet.hairlineWidth, padding: espacio.m, minHeight: TACTIL_MIN + 16 },
});
