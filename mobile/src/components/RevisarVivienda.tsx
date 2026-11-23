// ============================================================
// GAPTO MOBILE 2027
// Fichero: RevisarVivienda.tsx
// Ruta: mobile/src/components/RevisarVivienda.tsx
// Descripción: «Revisar» antes de registrar un gasto de vivienda (F06 T6 «UX ágil» S2; F09 0.55 §12.107, lámina REG-AGIL
//   V5; dictamen 1 Q5/A6). Muestra, por persona, su parte (atribución), lo que puso (aportación real) y la posición que
//   se crea, más el presupuesto y lo que sale de tus cuentas. Todo se calcula con las MISMAS funciones de dominio que
//   construyen el bloque `propiedad` del wire (`partesDe`, `saldos`, `confirmacion`, `saleDeMisCuentas`): lo que se ve
//   es lo que se guarda. Cada fila se toca para volver a su bloque. `huellaRevision` identifica la versión mostrada: si
//   cambian la fecha, la titularidad (propuesta), el reparto, la cuenta o las aportaciones, la huella cambia y la pantalla
//   invalida la revisión y la recalcula antes de volver a confirmar (A6). Solo presentación: no envía nada.
// Versión: 0.1.0 (F06 T6 · S2)
// ============================================================

import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { fechaCortaIso } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import { partesDe, type SeleccionPropiedad } from '../domain/propiedad_registro';
import { confirmacion, saldos, saleDeMisCuentas } from '../domain/quien_pago';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto } from './Basicos';

export const TEXTO_REVISAR_PIE = 'Lo que ves aquí es exactamente lo que se guarda. Cada fila se toca para volver a su bloque.';
export const TEXTO_REVISION_CAMBIADA = 'Algo ha cambiado desde que lo revisaste: se ha recalculado. Revísalo de nuevo antes de confirmar.';

/** Huella de lo que la revisión muestra: fecha, titularidad leída, reparto, quién pagó, deudas, cuenta e importe. */
export function huellaRevision(s: SeleccionPropiedad, importe: string, cuentaId: string | null, fecha: string, presupuestable: boolean | null): string {
  return JSON.stringify([fecha, importe, cuentaId, presupuestable, s.propiedadId, s.propuesta, s.reparto, s.pago, s.deudas, s.clase]);
}

export function RevisarVivienda(p: {
  sel: SeleccionPropiedad;
  importe: string;
  fecha: string;
  categoria: string | null;
  tercero: string | null;
  cuenta: string | null;
  presupuestable: boolean | null;
  aviso: string | null;
  enviando: boolean;
  onVolver: () => void;
  /** Vuelve al formulario en el bloque indicado (fila tocada). */
  onBloque: (b: 'importe' | 'propiedad' | 'presupuesto' | 'cuenta' | 'fecha') => void;
  onConfirmar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const partes = partesDe(p.sel);
  const filas = confirmacion(p.sel.pago, p.importe, partes, saldos(p.sel.pago, p.importe, partes, p.sel.deudas));
  const sale = saleDeMisCuentas(p.sel.pago, p.importe, partes);
  const total = parsearImporte(p.importe);
  const Fila = (f: { testID: string; titulo: string; valor: string; detalle?: string; bloque: Parameters<typeof p.onBloque>[0] }) => (
    <Pressable testID={f.testID} accessibilityRole="button" accessibilityLabel={`${f.titulo}: ${f.valor}`} onPress={() => p.onBloque(f.bloque)}
      style={[s.fila, { borderBottomColor: c.borderDefault }]}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[tipo.body, { color: c.textPrimary }]}>{f.titulo}</Text>
        {f.detalle ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{f.detalle}</Text> : null}
      </View>
      <Text testID={`${f.testID}-valor`} style={[tipo.bodyEmphasis, { color: c.textPrimary, flexShrink: 1, textAlign: 'right' }]}>{f.valor}</Text>
    </Pressable>
  );
  return (
    <View testID="revisar-vivienda" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <View style={s.lado}><BotonTexto testID="revisar-volver" titulo="‹ Volver" onPress={p.onVolver} /></View>
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>Revisar</Text>
        <View style={s.lado} />
      </View>
      <ScrollView contentContainerStyle={[s.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {p.aviso ? (
          <View testID="revisar-aviso" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{p.aviso}</Text>
          </View>
        ) : null}
        <Text style={[tipo.caption, { color: c.textSecondary }]}>{`Gasto · ${fechaCortaIso(p.fecha)}`}</Text>
        <Fila testID="revisar-importe" titulo={p.categoria ?? 'Gasto'} valor={total.ok ? formatearEur(total.valor) : p.importe}
          detalle={[p.tercero, p.sel.nombre].filter(Boolean).join(' · ')} bloque="importe" />
        <Text accessibilityRole="header" style={[tipo.caption, { color: c.textSecondary, letterSpacing: 0.6 }]}>POR PERSONA</Text>
        {filas.map((f) => (
          <Fila key={f.actor_id} testID={`revisar-persona-${f.actor_id}`} titulo={f.nombre}
            valor={f.parte ? `Parte ${formatearEur(f.parte)}` : 'Parte sin indicar'}
            detalle={`Puso ${formatearEur(f.puso)}${f.nombre === 'Tú' && p.cuenta && Number(f.puso) > 0 ? ` desde ${p.cuenta}` : ''} · ${f.posicion}`}
            bloque="propiedad" />
        ))}
        <Fila testID="revisar-presupuesto" titulo="Presupuesto" valor={p.presupuestable === null ? '—' : p.presupuestable ? 'Sí' : 'No'} bloque="presupuesto" />
        <Fila testID="revisar-sale" titulo="Sale de tus cuentas" valor={formatearEur(sale)} detalle={p.cuenta ?? undefined} bloque="cuenta" />
        <Fila testID="revisar-fecha" titulo="Fecha" valor={fechaCortaIso(p.fecha)} bloque="fecha" />
        <Text testID="revisar-pie" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_REVISAR_PIE}</Text>
        <BotonPrimario testID="revisar-confirmar" titulo={p.enviando ? 'Guardando…' : 'Confirmar y registrar'} cargando={p.enviando} onPress={p.onConfirmar} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  lado: { width: 96 },
  cuerpo: { padding: espacio.l, gap: espacio.m },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 8, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: espacio.s },
  aviso: { borderRadius: radio.m, padding: espacio.m },
});
