// ============================================================
// GAPTO MOBILE 2027
// Fichero: CampoFecha.tsx
// Ruta: mobile/src/components/CampoFecha.tsx
// Descripción: Componente ÚNICO de fecha de la app (F06-M M-07, DM-06; T1-F06 UX-1). Solo presentación: opciones en chips (el patrón «Hoy · Ayer · Otra fecha» de las filas 1–6 o las de cada pantalla), campo dd/mm/aaaa con máscara (las barras se ponen solas al escribir cifras, `enmascararFecha`; un texto que ya trae barras en otra posición se respeta tal cual) y calendario mensual en JS (View/Pressable, lunes primero) que escribe la fecha elegida en el mismo campo. El componente NO decide qué fecha vale: cada pantalla conserva su estado, su validación, sus mensajes y sus testID; el calendario solo deshabilita los días posteriores a `max` donde la pantalla ya tiene la regla «≤ hoy». Sin dependencia nueva (R-SEL-02).
// Versión: 0.1.0 (F06 T1 UX-1 · M-07)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { ddmmaaaaAIso, enmascararFecha, isoADdmmaaaa, isoLocal, mesAnioIso, mesDesplazadoIso, rejillaMesIso } from '../domain/fechas';
import { esFechaIso } from '../domain/intencion';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { Chip } from './Basicos';

export interface OpcionFecha {
  testID: string;
  etiqueta: string;
  seleccionado: boolean;
  onPress: () => void;
}

const DIAS_SEMANA = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const NOMBRES_DIA = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

/** Primer día del mes que abre el calendario: el de la fecha escrita si existe; si no, el de `max` o el de hoy. */
export function mesInicialCalendario(texto: string | null, hoyIso: string, max?: string | null): string {
  const escrita = texto ? ddmmaaaaAIso(texto) : null;
  const base = escrita && esFechaIso(escrita) ? escrita : max && max < hoyIso ? max : hoyIso;
  return `${base.slice(0, 7)}-01`;
}

export function CampoFecha(p: {
  /** testID del campo de texto: se conserva el de cada pantalla (`campo-fecha`, `prop-val-fecha`, `tit-desde`…). */
  testID: string;
  /** Nombre accesible del campo (el de cada pantalla). */
  etiqueta: string;
  /** Texto del campo; `null` = sin campo (p. ej. con «Hoy» o «Ayer» elegidos). */
  texto: string | null;
  /** Recibe el texto ya enmascarado (o la fecha elegida en el calendario como dd/mm/aaaa). */
  onTexto: (t: string) => void;
  /** Fecha civil de hoy (ISO): mes que abre el calendario si no hay fecha escrita (por defecto, la del dispositivo). */
  hoyIso?: string;
  opciones?: OpcionFecha[];
  marcador?: string;
  editable?: boolean;
  /** Borde crítico (error visible de la pantalla). */
  error?: boolean;
  /** Último día elegible en el calendario (ISO), solo donde la pantalla ya exige «≤ hoy». */
  max?: string | null;
  /** Fondo del campo: el de un formulario (por defecto) o el de una hoja. */
  fondo?: 'primario' | 'secundario';
}) {
  const { c } = useTema();
  const hoyIso = p.hoyIso ?? isoLocal(new Date());
  const [abierto, setAbierto] = useState(false);
  const [mes, setMes] = useState<string>(() => mesInicialCalendario(p.texto, hoyIso, p.max));
  const editable = p.editable !== false;
  const elegida = p.texto ? ddmmaaaaAIso(p.texto) : null;

  const alternar = () => {
    if (!editable) return;
    if (!abierto) setMes(mesInicialCalendario(p.texto, hoyIso, p.max));
    setAbierto(!abierto);
  };
  const elegir = (iso: string) => {
    if (!editable || (p.max && iso > p.max)) return;
    p.onTexto(isoADdmmaaaa(iso));
    setAbierto(false);
  };

  return (
    <View style={{ gap: espacio.s }}>
      {p.opciones && p.opciones.length > 0 ? (
        <View style={s.chips}>
          {p.opciones.map((o) => (
            <Chip key={o.testID} testID={o.testID} etiqueta={o.etiqueta} seleccionado={o.seleccionado} onPress={o.onPress} />
          ))}
        </View>
      ) : null}
      {p.texto !== null ? (
        <View style={s.fila}>
          <TextInput
            testID={p.testID}
            accessibilityLabel={p.etiqueta}
            value={p.texto}
            editable={editable}
            onChangeText={(t) => p.onTexto(enmascararFecha(t))}
            placeholder={p.marcador ?? 'dd/mm/aaaa'}
            placeholderTextColor={c.textSecondary}
            inputMode="numeric"
            maxLength={10}
            style={[
              tipo.body,
              s.input,
              {
                color: c.textPrimary,
                backgroundColor: p.fondo === 'secundario' ? c.surfaceSecondary : c.surfacePrimary,
                borderColor: p.error ? c.critical : c.borderStandard,
              },
            ]}
          />
          <Pressable
            testID={`${p.testID}-calendario`}
            accessibilityRole="button"
            accessibilityLabel={abierto ? 'Cerrar el calendario' : 'Elegir en el calendario'}
            accessibilityState={{ expanded: abierto, disabled: !editable }}
            onPress={alternar}
            style={[s.boton, { borderColor: abierto ? c.accent : c.borderStandard, backgroundColor: abierto ? c.accentSurface : c.surfacePrimary }]}
          >
            <Ionicons name={abierto ? 'calendar' : 'calendar-outline'} size={22} color={abierto ? c.accentText : c.textPrimary} />
          </Pressable>
        </View>
      ) : null}
      {p.texto !== null && abierto ? (
        <View testID={`${p.testID}-cal`} style={[s.calendario, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault }]}>
          <View style={s.cabecera}>
            <Pressable testID={`${p.testID}-cal-anterior`} accessibilityRole="button" accessibilityLabel="Mes anterior" onPress={() => setMes(mesDesplazadoIso(mes, -1))} style={s.flecha}>
              <Ionicons name="chevron-back" size={20} color={c.textPrimary} />
            </Pressable>
            <Text testID={`${p.testID}-cal-mes`} accessibilityRole="header" style={[tipo.bodyEmphasis, { color: c.textPrimary, flex: 1, textAlign: 'center' }]}>
              {mesAnioIso(mes)}
            </Text>
            <Pressable testID={`${p.testID}-cal-siguiente`} accessibilityRole="button" accessibilityLabel="Mes siguiente" onPress={() => setMes(mesDesplazadoIso(mes, 1))} style={s.flecha}>
              <Ionicons name="chevron-forward" size={20} color={c.textPrimary} />
            </Pressable>
          </View>
          <View style={s.semana}>
            {DIAS_SEMANA.map((d) => (
              <Text key={d} style={[tipo.caption, s.celdaTexto, { color: c.textSecondary }]}>{d}</Text>
            ))}
          </View>
          {rejillaMesIso(mes).map((semana, i) => (
            <View key={i} style={s.semana}>
              {semana.map((iso, j) => {
                if (iso === null) return <View key={j} style={s.celda} />;
                const fuera = !!p.max && iso > p.max;
                const sel = iso === elegida;
                const dia = Number(iso.slice(8, 10));
                return (
                  <Pressable
                    key={iso}
                    testID={`${p.testID}-cal-${iso}`}
                    accessibilityRole="button"
                    accessibilityLabel={`${NOMBRES_DIA[j]} ${dia}`}
                    accessibilityState={{ disabled: fuera, selected: sel }}
                    disabled={fuera}
                    onPress={() => elegir(iso)}
                    style={[s.celda, sel && { backgroundColor: c.accent, borderRadius: radio.pill }]}
                  >
                    <Text style={[tipo.subheadline, { color: sel ? c.onAccent : fuera ? c.textSecondary : c.textPrimary, opacity: fuera ? 0.4 : 1, fontWeight: iso === hoyIso ? '600' : '400' }]}>
                      {dia}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s },
  input: { flex: 1, borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
  boton: { width: TACTIL_MIN + 4, height: TACTIL_MIN + 4, borderWidth: 1, borderRadius: radio.s, alignItems: 'center', justifyContent: 'center' },
  calendario: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radio.m, padding: espacio.s, gap: espacio.xs },
  cabecera: { flexDirection: 'row', alignItems: 'center' },
  flecha: { width: TACTIL_MIN, height: TACTIL_MIN, alignItems: 'center', justifyContent: 'center' },
  semana: { flexDirection: 'row' },
  celda: { flex: 1, minHeight: TACTIL_MIN - 4, alignItems: 'center', justifyContent: 'center' },
  celdaTexto: { flex: 1, textAlign: 'center' },
});
