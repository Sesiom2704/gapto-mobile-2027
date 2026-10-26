// ============================================================
// GAPTO MOBILE 2027
// Fichero: Reembolso.tsx
// Ruta: mobile/src/components/Reembolso.tsx
// Descripción: «Me lo reembolsan» (C-03; lámina F05-07 v0.3 C2 y D1; F05 §66.2, §66.A.2/§66.A.3; D-F0507L-05). Tarea encima del registro, que conserva lo escrito. «Quién te lo debe» abre el selector de personas y empresas (nunca el comercio del gasto; ORGANISMO, OTRO y sin naturaleza no aparecen). «Cuánto te deben» no tiene nada marcado: «Todo · <total>» u «Otra cantidad» (de 0,01 € al total). «Hecho» deshabilitado hasta elegir ambos, con lo que falta dicho en texto. Texto fijo «Cómo se registra» (el gasto cuenta entero en tu Resultado; el cobro no será un ingreso) y la exclusión visible de la previsión (DEU-C03-PREVISION). Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-D052 paso 2 · C-03 UI C2)
// ============================================================

import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import {
  faltaReembolso,
  ReembolsoBorrador,
  REEMBOLSO_VACIO,
  TEXTO_COMO_SE_REGISTRA,
  TEXTO_CUANTO,
  TEXTO_ELIGE_QUIEN,
  TEXTO_OTRA_CANTIDAD,
  TEXTO_QUIEN,
  TEXTO_SIN_PREVISION,
  TEXTO_SOLO_PERSONAS_EMPRESAS,
  TEXTO_TODO,
  TITULO_REEMBOLSO,
} from '../domain/reembolso';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto, Chip } from './Basicos';
import { CabeceraTarea, Campo, Inicial, s, SelectorPersona } from './Reparto';

export function ReembolsoHoja(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  /** Total del gasto (texto canónico, ya válido). */
  total: string;
  /** Comercio del gasto: nunca puede ser quien te lo debe. */
  comercioId: string | null;
  inicial: ReembolsoBorrador | null;
  onHecho: (r: ReembolsoBorrador) => void;
  onAtras: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [r, setR] = useState<ReembolsoBorrador>(p.inicial ?? REEMBOLSO_VACIO);
  const [selector, setSelector] = useState(false);
  const faltan = faltaReembolso(p.total, r, p.comercioId);

  return (
    <KeyboardAvoidingView testID="reembolso" style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <CabeceraTarea titulo={TITULO_REEMBOLSO} izquierda={<BotonTexto testID="reembolso-atras" titulo="‹ Atrás" onPress={p.onAtras} />} />
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Campo etiqueta={TEXTO_QUIEN}>
          <Pressable testID="reembolso-quien" accessibilityRole="button" accessibilityLabel={`${TEXTO_QUIEN}: ${r.nombre ?? TEXTO_ELIGE_QUIEN}`}
            onPress={() => setSelector(true)} style={[s.fila, { backgroundColor: c.surfacePrimary }]}>
            {r.nombre ? <Inicial nombre={r.nombre} /> : null}
            <Text testID="reembolso-quien-valor" style={[tipo.body, { color: r.nombre ? c.textPrimary : c.textSecondary, flex: 1 }]}>{r.nombre ?? TEXTO_ELIGE_QUIEN}</Text>
            <Text style={[tipo.body, { color: c.textSecondary }]}>›</Text>
          </Pressable>
        </Campo>
        <Campo etiqueta={TEXTO_CUANTO}>
          <View style={s.chips}>
            <Chip testID="reembolso-todo" etiqueta={TEXTO_TODO(p.total)} seleccionado={r.modo === 'TODO'} onPress={() => setR((x) => ({ ...x, modo: 'TODO' }))} />
            <Chip testID="reembolso-otra" etiqueta={TEXTO_OTRA_CANTIDAD} seleccionado={r.modo === 'OTRA'} onPress={() => setR((x) => ({ ...x, modo: 'OTRA' }))} />
          </View>
          {r.modo === 'OTRA' ? (
            <View style={[s.fila, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard, borderWidth: 1 }]}>
              <Text style={[tipo.body, { color: c.textSecondary }]}>€</Text>
              <TextInput testID="reembolso-importe" accessibilityLabel={`${TEXTO_CUANTO}, en euros`} value={r.importeTexto}
                onChangeText={(t) => setR((x) => ({ ...x, importeTexto: t }))} keyboardType="decimal-pad" inputMode="decimal" placeholder="0,00"
                placeholderTextColor={c.textSecondary} style={[tipo.body, { flex: 1, minWidth: 0, color: c.textPrimary }]} />
            </View>
          ) : null}
        </Campo>
        <View testID="reembolso-como" style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
          <Text accessibilityRole="header" style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>Cómo se registra</Text>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_COMO_SE_REGISTRA(p.total)}</Text>
          <Text testID="reembolso-sin-prevision" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_PREVISION}</Text>
        </View>
        {faltan.length > 0 ? (
          <Text testID="reembolso-faltan" accessibilityLiveRegion="polite" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltan.join(' y ')}.`}</Text>
        ) : null}
        <BotonPrimario testID="reembolso-hecho" titulo="Hecho" deshabilitado={faltan.length > 0} ayuda={faltan.length > 0 ? `Falta: ${faltan.join(' y ')}.` : undefined}
          onPress={() => { if (faltan.length === 0) p.onHecho(r); }} />
      </ScrollView>
      {selector ? (
        <SelectorPersona cliente={p.cliente} nuevoId={p.nuevoId} titulo={TEXTO_QUIEN} naturalezas={['PERSONA', 'EMPRESA']} nota={TEXTO_SOLO_PERSONAS_EMPRESAS}
          excluir={p.comercioId ? [p.comercioId] : []}
          onCancelar={() => setSelector(false)}
          onElegir={(t) => {
            setSelector(false);
            setR((x) => ({ ...x, terceroId: t.id, nombre: t.nombre }));
          }} />
      ) : null}
    </KeyboardAvoidingView>
  );
}
