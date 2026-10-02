// ============================================================
// GAPTO MOBILE 2027
// Fichero: HojasCategoria.tsx
// Ruta: mobile/src/components/HojasCategoria.tsx
// Descripción: Hojas inferiores de las acciones EDIT-* de Ajustes › Categorías (F09 §12.97.4; lámina SET-CAT v1.0 S04 «Cambiar ámbito», S05 «Desactivar con subcategorías»; mandato F05-01 S6-WIRE+UI §5). Solo presentación: no llaman al cliente; la pantalla decide el comando y trata los rechazos. Renombrar (con la microcopy de que corrige la etiqueta también en la historia y el error de colisión junto al nombre), Cambiar ámbito (uso por naturaleza visible antes de confirmar; si el servidor devuelve un uso distinto, la hoja muestra el nuevo y pide confirmar otra vez), Desactivar (con subcategorías activas: «Desactivar también sus N subcategorías» o Cancelar; sin ellas, confirmación simple) y Reactivar (sin cascada). Velo con tokens y opacidad (sin rgba). Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S7-MAG UI): `Hoja`, `Aviso` y `BotonCritico` se exportan para reutilizarlos en las hojas de magnitudes (HojasMagnitud.tsx); sin cambios de presentación.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Ambito, CategoriaNodo } from '../domain/categoria';
import { useTema } from '../theme/tema';
import { espacio, radio, tipo } from '../theme/tokens';
import { BotonPrimario, Segmentado, Velo } from './Basicos';
import { BotonSecundario } from './SelectorCategorias';

export const MICROCOPY_RENOMBRAR =
  'Corrige la etiqueta también en la historia. Si cambia el significado, crea una categoría nueva y desactiva esta.';
export const MICROCOPY_DESACTIVAR = 'Sigue en la historia y deja de poder elegirse.';
export const MICROCOPY_AMBITO = 'El cambio no modifica lo ya registrado; solo afecta a lo que registres a partir de ahora.';

const ETIQUETA: Record<Ambito, string> = { GASTO: 'Gasto', INGRESO: 'Ingreso', AMBOS: 'Ambos' };
const NATURALEZA: Record<string, string> = { GASTO: 'Gastos', INGRESO: 'Ingresos' };

/** Enumeración natural: «A», «A y B», «A, B y C». */
export function enumerar(nombres: string[]): string {
  if (nombres.length <= 1) return nombres.join('');
  return `${nombres.slice(0, -1).join(', ')} y ${nombres[nombres.length - 1]}`;
}

export function Hoja(p: { titulo: string; testID: string; children: React.ReactNode }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View style={StyleSheet.absoluteFill}>
      <Velo />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.contenedor}>
        <View
          testID={p.testID}
          accessibilityViewIsModal
          style={[s.hoja, { backgroundColor: c.background, paddingBottom: inset.bottom + espacio.l }]}
        >
          <View style={[s.asa, { backgroundColor: c.borderStandard }]} />
          <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{p.titulo}</Text>
          {p.children}
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

export function Aviso(p: { texto: string; testID: string }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
      <Ionicons name="alert-circle-outline" size={18} color={c.warning} />
      <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{p.texto}</Text>
    </View>
  );
}

/** Acción destructiva de la hoja (lámina S05): superficie crítica con texto sobre acento. */
export function BotonCritico(p: { titulo: string; onPress: () => void; testID: string; deshabilitado?: boolean }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.titulo}
      accessibilityState={{ disabled: !!p.deshabilitado }}
      disabled={p.deshabilitado}
      onPress={p.onPress}
      style={({ pressed }) => [s.critico, { backgroundColor: c.critical, opacity: p.deshabilitado ? 0.5 : pressed ? 0.85 : 1 }]}
    >
      <Text style={[tipo.bodyEmphasis, { color: c.onAccent }]}>{p.titulo}</Text>
    </Pressable>
  );
}

// ------------------------------------------------------------------ Renombrar
export function HojaRenombrar(p: {
  nodo: CategoriaNodo;
  guardando: boolean;
  errorNombre: string | null;
  onLimpiarError: () => void;
  onGuardar: (nombre: string) => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const [nombre, setNombre] = useState(p.nodo.nombre);
  const limpio = nombre.trim();
  const sinCambio = limpio === p.nodo.nombre;
  return (
    <Hoja titulo={`Renombrar ${p.nodo.nombre}`} testID="hoja-renombrar">
      <TextInput
        testID="renombrar-nombre"
        accessibilityLabel="Nuevo nombre"
        value={nombre}
        onChangeText={(t) => { setNombre(t); p.onLimpiarError(); }}
        editable={!p.guardando}
        maxLength={200}
        style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: p.errorNombre ? c.critical : c.borderStandard }]}
      />
      {p.errorNombre ? (
        <Text testID="renombrar-error" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{p.errorNombre}</Text>
      ) : null}
      <Text testID="renombrar-microcopy" style={[tipo.footnote, { color: c.textSecondary }]}>{MICROCOPY_RENOMBRAR}</Text>
      <BotonPrimario
        testID="renombrar-guardar"
        titulo="Guardar nombre"
        cargando={p.guardando}
        deshabilitado={limpio === '' || sinCambio || p.guardando}
        onPress={() => p.onGuardar(limpio)}
      />
      <BotonSecundario testID="renombrar-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

// ------------------------------------------------------------------ Cambiar ámbito
export type UsoCarga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; efectos: Record<string, number> };

export function HojaAmbito(p: {
  nodo: CategoriaNodo;
  uso: UsoCarga;
  /** El servidor devolvió un uso distinto del confirmado: se muestra el nuevo y se pide confirmar otra vez. */
  usoCambiado: boolean;
  guardando: boolean;
  onReintentarUso: () => void;
  onConfirmar: (ambito: Ambito) => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const [ambito, setAmbito] = useState<Ambito>(p.nodo.ambito);
  const efectos = p.uso.fase === 'OK' ? p.uso.efectos : null;
  const naturalezas = efectos
    ? [...new Set(['GASTO', 'INGRESO', ...Object.keys(efectos)])]
    : [];
  return (
    <Hoja titulo={`Cambiar ámbito de ${p.nodo.nombre}`} testID="hoja-ambito">
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>Nuevo ámbito</Text>
      <Segmentado<Ambito>
        testIDBase="ambito-nuevo"
        etiquetaGrupo="Nuevo ámbito"
        opciones={(['GASTO', 'INGRESO', 'AMBOS'] as Ambito[]).map((v) => ({ valor: v, etiqueta: ETIQUETA[v] }))}
        valor={ambito}
        onCambiar={setAmbito}
      />
      {p.usoCambiado ? <Aviso testID="ambito-uso-cambiado" texto="El uso de la categoría ha cambiado. Revísalo y confirma de nuevo." /> : null}
      {p.uso.fase === 'CARGANDO' ? <Text testID="ambito-uso-cargando" style={[tipo.subheadline, { color: c.textSecondary }]}>Cargando el uso…</Text> : null}
      {p.uso.fase === 'ERROR' ? (
        <View style={{ gap: espacio.s }}>
          <Aviso testID="ambito-uso-error" texto="No hemos podido consultar el uso de esta categoría." />
          <BotonSecundario testID="ambito-uso-reintentar" titulo="Reintentar" onPress={p.onReintentarUso} />
        </View>
      ) : null}
      {efectos ? (
        <View testID="ambito-uso">
          <Text style={[tipo.footnote, { color: c.textSecondary, marginBottom: espacio.xs }]}>Uso actual de esta categoría:</Text>
          {naturalezas.map((k) => (
            <View key={k} testID={`ambito-uso-${k}`} accessible accessibilityLabel={`${NATURALEZA[k] ?? k}: ${efectos[k] ?? 0}`} style={[s.filaUso, { borderBottomColor: c.separator }]}>
              <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{NATURALEZA[k] ?? k}</Text>
              <Text style={[tipo.body, { color: c.textPrimary }]}>{efectos[k] ?? 0}</Text>
            </View>
          ))}
        </View>
      ) : null}
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{MICROCOPY_AMBITO}</Text>
      <BotonPrimario
        testID="ambito-confirmar"
        titulo={`Cambiar a ${ETIQUETA[ambito]}`}
        cargando={p.guardando}
        deshabilitado={!efectos || ambito === p.nodo.ambito || p.guardando}
        onPress={() => p.onConfirmar(ambito)}
      />
      <BotonSecundario testID="ambito-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

// ------------------------------------------------------------------ Desactivar
export function HojaDesactivar(p: {
  nodo: CategoriaNodo;
  /** Subcategorías activas (todo el subárbol), calculadas en el cliente desde el árbol cargado. */
  activas: CategoriaNodo[];
  guardando: boolean;
  onDesactivar: (modo: 'RAMA' | 'SOLO_SI_SIN_HIJOS_ACTIVOS') => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const n = p.activas.length;
  if (n > 0) {
    return (
      <Hoja titulo={`Desactivar ${p.nodo.nombre}`} testID="hoja-desactivar">
        <Text testID="desactivar-subcategorias" style={[tipo.body, { color: c.textPrimary }]}>
          {`Tiene ${n} ${n === 1 ? 'subcategoría activa' : 'subcategorías activas'}: ${enumerar(p.activas.map((a) => a.nombre))}.`}
        </Text>
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>
          Seguirán apareciendo en lo ya registrado, pero dejarán de poder elegirse.
        </Text>
        <BotonCritico
          testID="desactivar-rama"
          titulo={n === 1 ? 'Desactivar también su subcategoría' : `Desactivar también sus ${n} subcategorías`}
          deshabilitado={p.guardando}
          onPress={() => p.onDesactivar('RAMA')}
        />
        <BotonSecundario testID="desactivar-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
      </Hoja>
    );
  }
  return (
    <Hoja titulo={`Desactivar ${p.nodo.nombre}`} testID="hoja-desactivar">
      <Text testID="desactivar-microcopy" style={[tipo.body, { color: c.textPrimary }]}>{MICROCOPY_DESACTIVAR}</Text>
      <BotonCritico testID="desactivar-confirmar" titulo="Desactivar" deshabilitado={p.guardando} onPress={() => p.onDesactivar('SOLO_SI_SIN_HIJOS_ACTIVOS')} />
      <BotonSecundario testID="desactivar-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

// ------------------------------------------------------------------ Reactivar
export function HojaReactivar(p: { nodo: CategoriaNodo; inactivas: number; guardando: boolean; onReactivar: () => void; onCancelar: () => void }) {
  const { c } = useTema();
  return (
    <Hoja titulo={`Reactivar ${p.nodo.nombre}`} testID="hoja-reactivar">
      <Text style={[tipo.body, { color: c.textPrimary }]}>Volverá a poder elegirse.</Text>
      {p.inactivas > 0 ? (
        <Text testID="reactivar-sin-cascada" style={[tipo.footnote, { color: c.textSecondary }]}>
          {p.inactivas === 1
            ? 'Su subcategoría desactivada seguirá desactivada; puedes reactivarla después.'
            : `Sus ${p.inactivas} subcategorías desactivadas seguirán desactivadas; puedes reactivarlas después una a una.`}
        </Text>
      ) : null}
      <BotonPrimario testID="reactivar-confirmar" titulo="Reactivar" cargando={p.guardando} deshabilitado={p.guardando} onPress={p.onReactivar} />
      <BotonSecundario testID="reactivar-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  contenedor: { flex: 1, justifyContent: 'flex-end' },
  hoja: { borderTopLeftRadius: radio.l, borderTopRightRadius: radio.l, paddingHorizontal: espacio.l, paddingTop: espacio.s, gap: espacio.m },
  asa: { alignSelf: 'center', width: 36, height: 4, borderRadius: 2, marginBottom: espacio.xs },
  input: { borderWidth: 1, borderRadius: radio.m, paddingHorizontal: espacio.m, minHeight: 48 },
  aviso: { flexDirection: 'row', alignItems: 'flex-start', gap: espacio.s, borderRadius: radio.m, padding: espacio.m },
  filaUso: { flexDirection: 'row', alignItems: 'center', minHeight: 40, borderBottomWidth: StyleSheet.hairlineWidth },
  critico: { minHeight: 52, borderRadius: radio.m, alignItems: 'center', justifyContent: 'center', paddingHorizontal: espacio.l },
});
