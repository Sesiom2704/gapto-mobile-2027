// ============================================================
// GAPTO MOBILE 2027
// Fichero: EdicionHecho.tsx
// Ruta: mobile/src/components/EdicionHecho.tsx
// Descripción: Hojas de «Más» del detalle de un hecho (F05-06 M1; lámina EDIT-HECHO v0.1 D-EDIT-01, 06, 07; CONTRATO_M1 v0.1 §2). HojaMasHecho: «Corregir» y «Anular por duplicado»; lo que el servidor no admite aparece atenuado con su motivo (nunca se oculta en silencio) y no se puede pulsar. HojaAnularDuplicado (B1): qué hace y qué no (anular no borra; deja de contar en el saldo y en el Resultado; no se deshace; si hubo devolución, otra vía), declaración explícita de duplicado SIN marcar al entrar, motivo con opciones fijas más «Otro…» y «Anular registro» en rojo, que solo se habilita con la declaración y el motivo. Sin swipe (SWIPE-RULE: nunca anular ni corregir por gesto).
// Versión: 0.1.0 (F05-06 M1)
// Versión: 0.2.0 (F05-06 M1 v1.1; Q9 opción (a)): en un registro de V3, «Más» ofrece además «Corregir categoría» (solo si el servidor trae la acción; atenuada con su motivo si no se admite). HojaCorregirCategoria: lo que NO cambia (importe, fecha, cuenta y descripción), la categoría actual → la nueva (se elige con el selector del registro), motivo con opciones fijas más «Otro…» y «Guardar categoría», que solo se habilita con una categoría distinta y el motivo.
// ============================================================

import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { AccionEdicionWire } from '../api/cliente';
import { DECLARACION_DUPLICADO, MOTIVOS_ANULAR, MOTIVOS_CATEGORIA, TEXTO_ANULAR, TEXTO_ANULAR_DEVOLUCION, TEXTO_SOLO_CATEGORIA } from '../domain/edicion';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto, Chip } from './Basicos';
import { Hoja } from './HojasCategoria';

/** Acción de «Más»: atenuada con su motivo cuando el servidor no la admite. */
function AccionMas(p: { testID: string; titulo: string; accion: AccionEdicionWire; critico?: boolean; onPress: () => void }) {
  const { c } = useTema();
  const ok = p.accion.disponible;
  return (
    <View style={{ gap: espacio.xs }}>
      <Pressable testID={p.testID} accessibilityRole="button" accessibilityLabel={p.titulo} accessibilityState={{ disabled: !ok }}
        disabled={!ok} onPress={ok ? p.onPress : undefined}
        style={[s.accion, { borderColor: c.borderStandard, backgroundColor: c.surfacePrimary, opacity: ok ? 1 : 0.5 }]}>
        <Text style={[tipo.bodyEmphasis, { color: !ok ? c.textSecondary : p.critico ? c.critical : c.accent }]}>{p.titulo}</Text>
      </Pressable>
      {!ok && p.accion.motivo ? <Text testID={`${p.testID}-motivo`} style={[tipo.caption, { color: c.textSecondary }]}>{p.accion.motivo}</Text> : null}
    </View>
  );
}

export function HojaMasHecho(p: {
  acciones: { corregir: AccionEdicionWire; anular_duplicado: AccionEdicionWire; corregir_categoria?: AccionEdicionWire | null };
  onCorregir: () => void;
  onAnular: () => void;
  onCorregirCategoria?: () => void;
  onCerrar: () => void;
}) {
  const categoria = p.acciones.corregir_categoria;
  return (
    <Hoja titulo="Más" testID="hoja-mas-hecho">
      {categoria && p.onCorregirCategoria ? (
        <AccionMas testID="mas-corregir-categoria" titulo="Corregir categoría" accion={categoria} onPress={p.onCorregirCategoria} />
      ) : null}
      <AccionMas testID="mas-corregir" titulo="Corregir" accion={p.acciones.corregir} onPress={p.onCorregir} />
      <AccionMas testID="mas-anular" titulo="Anular por duplicado" accion={p.acciones.anular_duplicado} critico onPress={p.onAnular} />
      <BotonTexto testID="mas-hecho-cerrar" titulo="Cancelar" onPress={p.onCerrar} />
    </Hoja>
  );
}

export function HojaAnularDuplicado(p: {
  titulo: string;
  declarado: boolean;
  onDeclarar: (v: boolean) => void;
  motivo: string;
  motivoOtro: boolean;
  onMotivo: (texto: string, otro: boolean) => void;
  enviando: boolean;
  error: string | null;
  onConfirmar: () => void;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const listo = p.declarado && !!p.motivo.trim() && !p.enviando;
  return (
    <Hoja titulo={`¿Anular «${p.titulo}»?`} testID="hoja-anular-duplicado">
      <Text testID="anular-efecto" style={[tipo.body, { color: c.textSecondary }]}>{TEXTO_ANULAR}</Text>
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_ANULAR_DEVOLUCION}</Text>
      <Pressable testID="anular-declaracion" accessibilityRole="checkbox" accessibilityState={{ checked: p.declarado }}
        accessibilityLabel={DECLARACION_DUPLICADO} onPress={() => p.onDeclarar(!p.declarado)}
        style={[s.declaracion, { borderColor: p.declarado ? c.accent : c.borderStandard, backgroundColor: c.surfacePrimary }]}>
        <View style={[s.casilla, { borderColor: p.declarado ? c.accent : c.borderStandard, backgroundColor: p.declarado ? c.accent : c.surfacePrimary }]}>
          {p.declarado ? <Text style={[tipo.caption, { color: c.onAccent, fontWeight: '700' }]}>✓</Text> : null}
        </View>
        <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{DECLARACION_DUPLICADO}</Text>
      </Pressable>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Motivo obligatorio</Text>
      <View style={s.chips}>
        {MOTIVOS_ANULAR.map((m, i) => (
          <Chip key={m} testID={`anular-motivo-${i}`} etiqueta={m} seleccionado={!p.motivoOtro && p.motivo === m} onPress={() => p.onMotivo(m, false)} />
        ))}
        <Chip testID="anular-motivo-otro" etiqueta="Otro…" seleccionado={p.motivoOtro} onPress={() => p.onMotivo('', true)} />
      </View>
      {p.motivoOtro ? (
        <TextInput testID="anular-motivo-texto" accessibilityLabel="Motivo" value={p.motivo} onChangeText={(t) => p.onMotivo(t, true)} maxLength={200}
          style={[tipo.body, s.input, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]} />
      ) : null}
      {p.error ? <Text testID="anular-error" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{p.error}</Text> : null}
      <Pressable testID="anular-confirmar" accessibilityRole="button" accessibilityLabel="Anular registro" accessibilityState={{ disabled: !listo, busy: p.enviando }}
        disabled={!listo} onPress={listo ? p.onConfirmar : undefined}
        style={[s.critico, { backgroundColor: c.critical, opacity: listo ? 1 : 0.4 }]}>
        <Text style={[tipo.bodyEmphasis, { color: c.onAccent }]}>{p.enviando ? 'Anulando…' : 'Anular registro'}</Text>
      </Pressable>
      <BotonTexto testID="anular-cancelar" titulo="Cancelar" onPress={p.onCerrar} />
    </Hoja>
  );
}

export function HojaCorregirCategoria(p: {
  titulo: string;
  actual: string | null;
  nueva: string | null;
  onElegir: () => void;
  motivo: string;
  motivoOtro: boolean;
  onMotivo: (texto: string, otro: boolean) => void;
  listo: boolean;
  enviando: boolean;
  error: string | null;
  onGuardar: () => void;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const puede = p.listo && !p.enviando;
  return (
    <Hoja titulo={`Corregir categoría de «${p.titulo}»`} testID="hoja-corregir-categoria">
      <Text testID="categoria-solo" style={[tipo.body, { color: c.textSecondary }]}>{TEXTO_SOLO_CATEGORIA}</Text>
      <Text testID="categoria-actual" style={[tipo.footnote, { color: c.textSecondary }]}>{`Ahora: ${p.actual ?? 'Sin categoría'}`}</Text>
      <Pressable testID="categoria-elegir" accessibilityRole="button" accessibilityLabel="Elegir categoría" onPress={p.onElegir}
        style={[s.accion, { borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]}>
        <Text style={[tipo.bodyEmphasis, { color: p.nueva ? c.textPrimary : c.accent }]}>{p.nueva ? `Nueva: ${p.nueva}` : 'Elegir categoría'}</Text>
      </Pressable>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Motivo obligatorio</Text>
      <View style={s.chips}>
        {MOTIVOS_CATEGORIA.map((m, i) => (
          <Chip key={m} testID={`categoria-motivo-${i}`} etiqueta={m} seleccionado={!p.motivoOtro && p.motivo === m} onPress={() => p.onMotivo(m, false)} />
        ))}
        <Chip testID="categoria-motivo-otro" etiqueta="Otro…" seleccionado={p.motivoOtro} onPress={() => p.onMotivo('', true)} />
      </View>
      {p.motivoOtro ? (
        <TextInput testID="categoria-motivo-texto" accessibilityLabel="Motivo" value={p.motivo} onChangeText={(t) => p.onMotivo(t, true)} maxLength={200}
          style={[tipo.body, s.input, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]} />
      ) : null}
      {p.error ? <Text testID="categoria-error" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{p.error}</Text> : null}
      <BotonPrimario testID="categoria-guardar" titulo={p.enviando ? 'Guardando…' : 'Guardar categoría'} deshabilitado={!puede} onPress={() => { if (puede) p.onGuardar(); }} />
      <BotonTexto testID="categoria-cancelar" titulo="Cancelar" onPress={p.onCerrar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  accion: { minHeight: 52, borderRadius: radio.m, borderWidth: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: espacio.l },
  declaracion: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.m, padding: espacio.m, minHeight: TACTIL_MIN },
  casilla: { width: 22, height: 22, borderRadius: radio.s, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
  critico: { minHeight: 52, borderRadius: radio.m, alignItems: 'center', justifyContent: 'center', paddingHorizontal: espacio.l },
});
