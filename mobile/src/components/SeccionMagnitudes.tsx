// ============================================================
// GAPTO MOBILE 2027
// Fichero: SeccionMagnitudes.tsx
// Ruta: mobile/src/components/SeccionMagnitudes.tsx
// Descripción: Sección plegable «Magnitudes · N» del detalle de categoría de Ajustes › Categorías, entre la fila «Icono» y «Acciones» (F09 §12.97.10; lámina SET-MAG v0.1 M01–M05, M16). Plegada: total y resumen «N obligatorias, M opcionales» (y «No usable en registros nuevos» si alguna obligatoria está deshabilitada). Desplegada: asociaciones en su `orden` con «unidad · decimales» y píldoras de TEXTO (Obligatoria / Opcional / Deshabilitada); tocar una fila abre su ficha; «+ Añadir magnitud» (y «Editar orden» si se ofrece y hay más de una); nota de alcance; estado «No usable en registros nuevos» con su motivo y las tres salidas (M03); vacío (M04) distinto del error de carga (M05, «Reintentar», «Nada se ha cambiado»). Disponible también en categorías desactivadas (P1). Aviso de conflicto con recarga (M16). Solo presentación. Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { MagnitudCategoria } from '../domain/categoria';
import { obligatoriasDeshabilitadas, resumenMagnitudes, textoNoUsable, textoUnidadDecimales } from '../domain/magnitud';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonTexto } from './Basicos';
import { Pildora } from './HojasMagnitud';

export const NOTA_SECCION = 'Las obligatorias bloquean el registro hasta informarlas; nunca se proponen valores por defecto. Cambiar estas opciones afecta solo a registros nuevos.';
export const TITULO_NO_USABLE = 'No usable en registros nuevos';
export const TITULO_VACIO = 'Esta categoría no pide ningún dato adicional';
export const TEXTO_VACIO = (cat: string) => `Al registrar en ${cat} solo se piden importe, fecha y cuenta.`;
export const TITULO_ERROR = 'No se han podido cargar las magnitudes';
export const TEXTO_ERROR = 'No es que no haya: el servidor no ha respondido. Nada se ha cambiado.';

export type FaseCatalogo = 'CARGANDO' | 'OK' | 'ERROR';

export function SeccionMagnitudes(p: {
  categoria: string;
  magnitudes: MagnitudCategoria[];
  abierta: boolean;
  fase: FaseCatalogo;
  aviso: { titulo: string; texto: string } | null;
  onAlternar: () => void;
  onFila: (m: MagnitudCategoria) => void;
  onAnadir: () => void;
  onEditarOrden?: () => void;
  onReintentar: () => void;
}) {
  const { c } = useTema();
  const r = resumenMagnitudes(p.magnitudes);
  const bloqueantes = obligatoriasDeshabilitadas(p.magnitudes);
  const error = p.abierta && p.fase === 'ERROR';
  const titulo = error ? 'Magnitudes' : `Magnitudes · ${r.total}`;
  const sub = error
    ? null
    : [r.texto || null, p.abierta && r.total ? `se piden al registrar en ${p.categoria}` : null, !p.abierta && bloqueantes.length ? TITULO_NO_USABLE : null]
        .filter(Boolean)
        .join(' · ') || null;
  return (
    <View testID="seccion-magnitudes">
      {p.aviso ? (
        <View testID="magnitudes-aviso" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.unknownSurface }]}>
          <Ionicons name="refresh" size={18} color={c.textSecondary} />
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{p.aviso.titulo}</Text>
            <Text style={[tipo.footnote, { color: c.textPrimary }]}>{p.aviso.texto}</Text>
          </View>
        </View>
      ) : null}
      <View style={[s.tarjeta, { borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]}>
        <Pressable
          testID="magnitudes-cabecera"
          accessibilityRole="button"
          accessibilityState={{ expanded: p.abierta }}
          accessibilityLabel={[titulo, sub].filter(Boolean).join('. ')}
          onPress={p.onAlternar}
          style={s.cabecera}
        >
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{titulo}</Text>
            {sub ? <Text testID="magnitudes-resumen" style={[tipo.caption, { color: c.textSecondary }]}>{sub}</Text> : null}
          </View>
          <Ionicons name={p.abierta ? 'chevron-up' : 'chevron-down'} size={18} color={c.textSecondary} />
        </Pressable>
        {p.abierta ? (
          <View style={[s.cuerpo, { borderTopColor: c.separator }]}>
            {p.fase === 'CARGANDO' ? (
              <Text testID="magnitudes-cargando" style={[tipo.subheadline, s.relleno, { color: c.textSecondary }]}>Cargando…</Text>
            ) : null}
            {p.fase === 'ERROR' ? (
              <View testID="magnitudes-error" style={[s.relleno, { gap: espacio.s, alignItems: 'center' }]}>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary, textAlign: 'center' }]}>{TITULO_ERROR}</Text>
                <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>{TEXTO_ERROR}</Text>
                <BotonTexto testID="magnitudes-reintentar" titulo="Reintentar" onPress={p.onReintentar} />
              </View>
            ) : null}
            {p.fase === 'OK' && r.total === 0 ? (
              <View testID="magnitudes-vacio" style={[s.relleno, { gap: espacio.xs, alignItems: 'center' }]}>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary, textAlign: 'center' }]}>{TITULO_VACIO}</Text>
                <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>{TEXTO_VACIO(p.categoria)}</Text>
              </View>
            ) : null}
            {p.fase === 'OK'
              ? p.magnitudes.map((m) => (
                  <Pressable
                    key={m.asociacion_id}
                    testID={`magnitud-fila-${m.asociacion_id}`}
                    accessibilityRole="button"
                    accessibilityLabel={[
                      m.nombre,
                      textoUnidadDecimales(m.unidad_default, m.precision_decimales),
                      m.enabled ? null : 'Deshabilitada',
                      m.obligatoria ? 'Obligatoria' : 'Opcional',
                    ].filter(Boolean).join('. ')}
                    onPress={() => p.onFila(m)}
                    style={({ pressed }) => [s.fila, { borderBottomColor: c.separator, opacity: pressed ? 0.7 : 1 }]}
                  >
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={[tipo.body, { color: m.enabled ? c.textPrimary : c.textSecondary }]}>{m.nombre}</Text>
                      <Text style={[tipo.caption, { color: c.textSecondary }]}>{textoUnidadDecimales(m.unidad_default, m.precision_decimales)}</Text>
                    </View>
                    {m.enabled ? null : <Pildora testID={`magnitud-deshabilitada-${m.asociacion_id}`} texto="Deshabilitada" tono="DESHABILITADA" />}
                    <Pildora texto={m.obligatoria ? 'Obligatoria' : 'Opcional'} tono={m.obligatoria ? 'OBLIGATORIA' : 'OPCIONAL'} />
                    <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
                  </Pressable>
                ))
              : null}
            {p.fase === 'OK' ? (
              <View style={s.acciones}>
                <BotonTexto testID="magnitudes-anadir" titulo="+ Añadir magnitud" onPress={p.onAnadir} />
                {p.onEditarOrden && r.total > 1 ? <BotonTexto testID="magnitudes-editar-orden" titulo="Editar orden" onPress={p.onEditarOrden} /> : null}
              </View>
            ) : null}
            {p.fase === 'OK' && bloqueantes.length ? (
              <View testID="magnitudes-no-usable" accessibilityRole="alert" style={[s.aviso, s.avisoInterno, { backgroundColor: c.partialSurface }]}>
                <Ionicons name="warning-outline" size={18} color={c.warning} />
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{TITULO_NO_USABLE}</Text>
                  <Text style={[tipo.footnote, { color: c.textPrimary }]}>{textoNoUsable(bloqueantes.map((b) => b.nombre))}</Text>
                </View>
              </View>
            ) : null}
          </View>
        ) : null}
      </View>
      {p.abierta && p.fase === 'OK' && r.total > 0 ? (
        <Text testID="magnitudes-nota" style={[tipo.caption, s.nota, { color: c.textSecondary }]}>{NOTA_SECCION}</Text>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  tarjeta: { marginHorizontal: espacio.l, marginTop: espacio.m, borderWidth: StyleSheet.hairlineWidth, borderRadius: radio.m, overflow: 'hidden' },
  cabecera: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.m, paddingVertical: espacio.s },
  cuerpo: { borderTopWidth: StyleSheet.hairlineWidth },
  relleno: { padding: espacio.l },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.m, paddingVertical: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  acciones: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: espacio.m },
  aviso: { flexDirection: 'row', alignItems: 'flex-start', gap: espacio.s, borderRadius: radio.m, padding: espacio.m, marginHorizontal: espacio.l, marginTop: espacio.m },
  avisoInterno: { marginHorizontal: espacio.m, marginBottom: espacio.m },
  nota: { paddingHorizontal: espacio.l, paddingTop: espacio.s },
});
