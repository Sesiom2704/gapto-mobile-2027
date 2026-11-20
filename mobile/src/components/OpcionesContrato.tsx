// ============================================================
// GAPTO MOBILE 2027
// Fichero: OpcionesContrato.tsx
// Ruta: mobile/src/components/OpcionesContrato.tsx
// Descripción: Piezas comunes de las pantallas de F06-02/03 (lámina CON v0.8): fila de opción con título y detalle (tipo, habitación, firmado o no, cláusula, tratamiento de servicio; ninguna viene marcada de antemano), indicador de paso del asistente («El contrato» · «Las condiciones», 5 pasos) y fila informativa. Solo tokens semánticos (DS-RULE-12).
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { NOMBRE_PASO, PASOS_CONTRATO, PasoContrato } from '../domain/contratos';
import { ddmmaaaaAIso, isoADdmmaaaa } from '../domain/fechas';
import { esFechaIso } from '../domain/intencion';
import { CampoFecha } from './CampoFecha';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

/** Fecha ISO con el `CampoFecha` único de UX-1 (dd/mm/aaaa con máscara y calendario). Vacío = sin fecha. */
export function CampoFechaIso(p: { testID: string; etiqueta: string; iso: string; hoyIso: string; onCambiar: (iso: string) => void }) {
  const [texto, setTexto] = useState<string>(esFechaIso(p.iso) ? isoADdmmaaaa(p.iso) : p.iso);
  return <CampoFecha testID={p.testID} etiqueta={p.etiqueta} hoyIso={p.hoyIso} texto={texto} onTexto={(t) => { setTexto(t); p.onCambiar(ddmmaaaaAIso(t) ?? t); }} />;
}

/** Opción de selección única con título y detalle. `seleccionada` nunca viene a true por defecto. */
export function OpcionFila(p: { testID: string; titulo: string; detalle?: string; seleccionada: boolean; onPress: () => void; deshabilitada?: boolean }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="radio"
      accessibilityState={{ selected: p.seleccionada, checked: p.seleccionada, disabled: !!p.deshabilitada }}
      accessibilityLabel={[p.titulo, p.detalle].filter(Boolean).join('. ')}
      disabled={p.deshabilitada}
      onPress={p.onPress}
      style={[s.opcion, { borderColor: p.seleccionada ? c.accent : c.borderStandard, backgroundColor: p.seleccionada ? c.accentSurface : c.surfacePrimary, opacity: p.deshabilitada ? 0.6 : 1 }]}
    >
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[tipo.body, { color: p.seleccionada ? c.accentText : c.textPrimary, fontWeight: p.seleccionada ? '600' : '400' }]}>{p.titulo}</Text>
        {p.detalle ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{p.detalle}</Text> : null}
      </View>
      {p.seleccionada ? <Text accessibilityElementsHidden style={[tipo.body, { color: c.accentText }]}>✓</Text> : null}
    </Pressable>
  );
}

/** «El contrato · Qué, Fechas, Personas» y «Las condiciones · Revisión, Servicios». Un resumen no es un paso. */
export function IndicadorPasos(p: { paso: PasoContrato; testID?: string }) {
  const { c } = useTema();
  const pasos: PasoContrato[] = PASOS_CONTRATO.filter((x) => x !== 'RESUMEN');
  const i = pasos.indexOf(p.paso);
  const grupo = i < 0 ? 'Revisar' : i < 3 ? 'El contrato' : 'Las condiciones';
  return (
    <View testID={p.testID ?? 'contrato-pasos'} accessible accessibilityLabel={i < 0 ? 'Revisar contrato' : `Paso ${i + 1} de 5, ${NOMBRE_PASO[p.paso]}`} style={{ gap: 2 }}>
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{grupo}</Text>
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>
        {pasos.map((x, j) => `${j < i ? '✓' : j + 1} ${NOMBRE_PASO[x]}`).join('   ')}
      </Text>
    </View>
  );
}

export function FilaInfo(p: { testID?: string; etiqueta: string; valor: string }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={s.info}>
      <Text style={[tipo.body, { color: c.textSecondary, flex: 1 }]}>{p.etiqueta}</Text>
      <Text testID={p.testID ? `${p.testID}-valor` : undefined} style={[tipo.body, { color: c.textPrimary, flexShrink: 1, textAlign: 'right' }]}>{p.valor}</Text>
    </View>
  );
}

/** B2b · «Ya está alquilada en esas fechas»: los contratos firmados con los que coincide y por qué no se puede firmar. */
export function SolapeInfo(p: { testID: string; titulo: string; intro: string; filas: string[]; aviso: string }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} accessibilityRole="alert" style={[s.solape, { backgroundColor: c.partialSurface, borderColor: c.warning }]}>
      <Text accessibilityRole="header" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{p.titulo}</Text>
      <Text testID={`${p.testID}-intro`} style={[tipo.footnote, { color: c.textPrimary }]}>{p.intro}</Text>
      {p.filas.map((f, i) => <Text key={i} testID={`${p.testID}-fila-${i}`} style={[tipo.body, { color: c.textPrimary }]}>{f}</Text>)}
      <Text testID={`${p.testID}-aviso`} style={[tipo.footnote, { color: c.textPrimary }]}>{p.aviso}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  solape: { borderRadius: radio.m, borderWidth: 1, padding: espacio.m, gap: espacio.s },
  opcion: { minHeight: TACTIL_MIN + 8, borderRadius: radio.m, borderWidth: 1, paddingHorizontal: espacio.m, paddingVertical: espacio.s, flexDirection: 'row', alignItems: 'center', gap: espacio.s },
  info: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: espacio.m, paddingVertical: espacio.xs },
});
