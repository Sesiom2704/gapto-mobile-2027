// ============================================================
// GAPTO MOBILE 2027
// Fichero: NuevaMagnitud.tsx
// Ruta: mobile/src/components/NuevaMagnitud.tsx
// Descripción: Alta rápida de una magnitud con su asociación a la categoría en un solo paso (F09 §12.97.10; lámina SET-MAG v0.1 M07–M08; F05-D020 D-MAG-01/05/09). Tarea inmersiva «Cancelar · Nueva magnitud»: nombre, unidad, decimales 0..6 (segmentado SIN preselección), nota de que unidad y decimales no se podrán cambiar, «En <categoría>: Obligatoria / Opcional» sin preselección y «Crear y añadir a <categoría>» desactivada hasta completar, con el texto «Para crear falta: …». La validación es la del servidor (1..80 y 1..20 visibles tras NFKC/recorte/colapso). Colisión de nombre (M08): aviso junto al nombre con la existente y «Usar “<nombre>” en <categoría>» o, si está deshabilitada, «Rehabilitar “<nombre>” y usarla»; sin `detalle` (colisión física residual) mensaje genérico y «Recargar catálogo». Nunca se crea una segunda ni se rehabilita sin acción explícita. Identidad: el formulario guarda un `magnitud_id` que se REUTILIZA en el reintento (red o indeterminado) y solo se renueva cuando el usuario modifica algún dato. Solo presentación: el controlador envía y trata los rechazos.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 2)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { FormNuevaMagnitud, MagnitudCatalogo, subtituloCatalogo, validarNuevaMagnitud, visible } from '../domain/magnitud';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto, Segmentado } from './Basicos';
import { AYUDA_OBLIGATORIEDAD } from './HojasMagnitud';
import { BotonSecundario } from './SelectorCategorias';

export const NOTA_INMUTABLES = 'Unidad y decimales no se podrán cambiar después: para otros, crearás una magnitud nueva.';
export const COLISION_GENERICA = 'Ya existe una magnitud con ese nombre.';

/** Colisión de nombre que el controlador comunica al formulario (M08). */
export type Colision = null | { tipo: 'EXISTENTE'; magnitud: MagnitudCatalogo } | { tipo: 'SIN_DETALLE' };

export interface EnvioNueva {
  magnitud_id: string;
  nombre: string;
  unidad_default: string;
  precision_decimales: number;
  obligatoria: boolean;
}

export function NuevaMagnitud(p: {
  categoria: string;
  nuevoId: () => string;
  guardando: boolean;
  colision: Colision;
  aviso: string | null;
  onCrear: (e: EnvioNueva) => void;
  onUsarExistente: (m: MagnitudCatalogo, obligatoria: boolean) => void;
  onRehabilitarYUsar: (m: MagnitudCatalogo, obligatoria: boolean) => void;
  onRecargarCatalogo: () => void;
  onEditar: () => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [form, setForm] = useState<FormNuevaMagnitud>({ nombre: '', unidad: '', decimales: null, obligatoria: null });
  // Identidad de la intención: se conserva en el reintento; se renueva solo al modificar el formulario.
  const [idIntento, setIdIntento] = useState<string>(() => p.nuevoId());
  const v = validarNuevaMagnitud(form);

  const cambiar = (cambio: Partial<FormNuevaMagnitud>) => {
    setForm((f) => ({ ...f, ...cambio }));
    setIdIntento(p.nuevoId());
    p.onEditar();
  };

  const crear = () => {
    if (!v.completa || form.decimales === null || form.obligatoria === null) return;
    p.onCrear({
      magnitud_id: idIntento,
      nombre: visible(form.nombre),
      unidad_default: visible(form.unidad),
      precision_decimales: form.decimales,
      obligatoria: form.obligatoria,
    });
  };

  const existente = p.colision?.tipo === 'EXISTENTE' ? p.colision.magnitud : null;

  return (
    <View testID="nueva-magnitud" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <BotonTexto testID="nuevamag-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>Nueva magnitud</Text>
        <View style={{ width: 72 }} />
      </View>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[s.cuerpo, { paddingBottom: inset.bottom + espacio.xl }]}>
          {p.aviso ? (
            <View testID="nuevamag-aviso" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
              <Ionicons name="alert-circle-outline" size={18} color={c.warning} />
              <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{p.aviso}</Text>
            </View>
          ) : null}
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>Nombre</Text>
          <TextInput
            testID="nuevamag-nombre"
            accessibilityLabel="Nombre"
            value={form.nombre}
            onChangeText={(t) => cambiar({ nombre: t })}
            editable={!p.guardando}
            maxLength={400}
            style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: p.colision || v.errorNombre ? c.warning : c.borderStandard }]}
          />
          {v.errorNombre ? <Text testID="nuevamag-error-nombre" style={[tipo.footnote, { color: c.critical }]}>{v.errorNombre}</Text> : null}
          {existente ? (
            <View testID="nuevamag-colision" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
              <Ionicons name="information-circle-outline" size={18} color={c.warning} />
              <View style={{ flex: 1, gap: espacio.s }}>
                <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>
                  {existente.enabled ? `Ya existe «${existente.nombre}»` : `Ya existe «${existente.nombre}» (deshabilitada)`}
                </Text>
                <Text style={[tipo.footnote, { color: c.textPrimary }]}>
                  {existente.enabled
                    ? `${subtituloCatalogo(existente)}. No se crea otra: puedes usar la existente.`
                    : 'Puedes rehabilitarla y usarla, o cambiar el nombre.'}
                </Text>
                {existente.enabled ? (
                  <BotonSecundario
                    testID="nuevamag-usar"
                    titulo={`Usar «${existente.nombre}» en ${p.categoria}`}
                    onPress={() => form.obligatoria !== null && p.onUsarExistente(existente, form.obligatoria)}
                  />
                ) : (
                  <BotonSecundario
                    testID="nuevamag-rehabilitar"
                    titulo={`Rehabilitar «${existente.nombre}» y usarla`}
                    onPress={() => form.obligatoria !== null && p.onRehabilitarYUsar(existente, form.obligatoria)}
                  />
                )}
                {form.obligatoria === null ? (
                  <Text testID="nuevamag-colision-falta" style={[tipo.caption, { color: c.textSecondary }]}>
                    {`Elige antes si es obligatoria u opcional en ${p.categoria}.`}
                  </Text>
                ) : null}
              </View>
            </View>
          ) : null}
          {p.colision?.tipo === 'SIN_DETALLE' ? (
            <View testID="nuevamag-colision-generica" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
              <Ionicons name="information-circle-outline" size={18} color={c.warning} />
              <View style={{ flex: 1, gap: espacio.s }}>
                <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{COLISION_GENERICA}</Text>
                <BotonSecundario testID="nuevamag-recargar" titulo="Recargar catálogo" onPress={p.onRecargarCatalogo} />
              </View>
            </View>
          ) : null}
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>Unidad</Text>
          <TextInput
            testID="nuevamag-unidad"
            accessibilityLabel="Unidad"
            value={form.unidad}
            onChangeText={(t) => cambiar({ unidad: t })}
            editable={!p.guardando}
            maxLength={100}
            style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: v.errorUnidad ? c.critical : c.borderStandard }]}
          />
          {v.errorUnidad ? <Text testID="nuevamag-error-unidad" style={[tipo.footnote, { color: c.critical }]}>{v.errorUnidad}</Text> : null}
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>Decimales</Text>
          <Segmentado<string>
            testIDBase="nuevamag-decimales"
            etiquetaGrupo="Decimales"
            opciones={[0, 1, 2, 3, 4, 5, 6].map((d) => ({ valor: String(d), etiqueta: String(d) }))}
            valor={form.decimales === null ? null : String(form.decimales)}
            onCambiar={(d) => cambiar({ decimales: Number(d) })}
          />
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{NOTA_INMUTABLES}</Text>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`En ${p.categoria}`}</Text>
          <Segmentado<boolean>
            testIDBase="nuevamag-obligatoria"
            etiquetaGrupo={`En ${p.categoria}`}
            opciones={[{ valor: true, etiqueta: 'Obligatoria' }, { valor: false, etiqueta: 'Opcional' }]}
            valor={form.obligatoria}
            onCambiar={(o) => cambiar({ obligatoria: o })}
          />
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{AYUDA_OBLIGATORIEDAD(p.categoria)}</Text>
          {v.faltan ? <Text testID="nuevamag-faltan" style={[tipo.footnote, { color: c.textSecondary }]}>{v.faltan}</Text> : null}
          <BotonPrimario
            testID="nuevamag-crear"
            titulo={`Crear y añadir a ${p.categoria}`}
            cargando={p.guardando}
            deshabilitado={!v.completa || p.guardando}
            ayuda={v.faltan ?? undefined}
            onPress={crear}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  cuerpo: { padding: espacio.l, gap: espacio.s },
  input: { borderWidth: 1, borderRadius: radio.m, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
  aviso: { flexDirection: 'row', alignItems: 'flex-start', gap: espacio.s, borderRadius: radio.m, padding: espacio.m },
});
