// ============================================================
// GAPTO MOBILE 2027
// Fichero: Prevision.tsx
// Ruta: mobile/src/components/Prevision.tsx
// Descripción: Piezas de la confirmación de previsiones (F05-06 M5 §B1; láminas PREV v0.2 y HOME-01 v0.4). FilaPrevisionVista: concepto, línea (vencida, pago parcial, «Entre cuentas») e importe por naturaleza («~», «+» en color neutro, «Desconocido»); el deslizamiento a la izquierda solo ABRE la confirmación del swipe («Pagado» / «Cobrado», DAY-RULE-03), y también como acción accesible. Campana con contador junto al perfil (I01; «!» si falla, nada sin pendientes). HojaSwipe (B1, D-PREV-12): previsión, esperado, consecuencia, importe real propuesto («Revisa»), cuenta y fecha antes de «Confirmar pago y cubrir». HojaOmitir (B3): motivo opcional y «No hubo este mes». AvisoEstadoActual (B7): tras un 409 la app no dice «hecho» y enseña el estado real.
// Versión: 0.1.0 (F05-06 M5 §B1)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useMemo, useRef } from 'react';
import { PanResponder, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { FilaPrevision } from '../api/cliente';
import { importeFila, intervaloTexto, lineaFila, TEXTO_NO_SABEMOS, verboSwipe, estadoLegible, consecuencia } from '../domain/prevision';
import { useTema } from '../theme/tema';
import { espacio, importe as estiloImporte, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto, Chip, Velo } from './Basicos';

const UMBRAL_SWIPE = 60;

/** Fila de una previsión (Inicio, «Pendientes», «Próximos»). */
export function FilaPrevisionVista(p: {
  fila: FilaPrevision;
  testID: string;
  onPress?: () => void;
  /** Solo si la previsión admite el swipe (gasto o ingreso, esperado conocido, cuenta y sin pagos). */
  onSwipe?: () => void;
  enProximos?: boolean;
  usarQueda?: boolean;
  ultima?: boolean;
}) {
  const { c } = useTema();
  const f = p.fila;
  const onSwipe = p.onSwipe;
  const responder = useMemo(() => {
    // Gesto horizontal claro: la fila lo toma aunque el Pressable interior tenga el toque (fase de captura).
    const horizontal = (_: unknown, g: { dx: number; dy: number }) => !!onSwipe && Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy);
    return PanResponder.create({
      onMoveShouldSetPanResponder: horizontal,
      onMoveShouldSetPanResponderCapture: horizontal,
      onPanResponderTerminationRequest: () => false,
      onPanResponderRelease: (_, g) => {
        if (onSwipe && g.dx < -UMBRAL_SWIPE) onSwipe();
      },
    });
  }, [onSwipe]);
  const verbo = verboSwipe(f.tipo);
  return (
    <View {...responder.panHandlers}>
      <Pressable
        testID={p.testID}
        accessibilityRole={p.onPress ? 'button' : 'text'}
        accessibilityLabel={`${f.concepto}. ${lineaFila(f, p.enProximos)}. ${importeFila(f, p.usarQueda)}`}
        accessibilityActions={onSwipe ? [{ name: 'activate' }, { name: 'swipe', label: verbo }] : undefined}
        onAccessibilityAction={(e) => {
          if (e.nativeEvent.actionName === 'swipe') onSwipe?.();
          if (e.nativeEvent.actionName === 'activate') p.onPress?.();
        }}
        onPress={p.onPress}
        disabled={!p.onPress}
        style={({ pressed }) => [s.fila, !p.ultima && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }, { opacity: pressed ? 0.7 : 1 }]}
      >
        <View style={{ flex: 1, gap: 2 }}>
          <Text testID={`${p.testID}-concepto`} numberOfLines={1} style={[tipo.body, { color: c.textPrimary, fontWeight: '600' }]}>{f.concepto}</Text>
          <Text testID={`${p.testID}-linea`} style={[tipo.caption, { color: f.vencida ? c.warning : c.textSecondary }]}>{lineaFila(f, p.enProximos)}</Text>
        </View>
        <Text testID={`${p.testID}-importe`} style={[estiloImporte.secondary, s.importeFila, { color: c.textPrimary, fontVariant: ['tabular-nums'] }]}>
          {importeFila(f, p.usarQueda)}
        </Text>
      </Pressable>
    </View>
  );
}

/** Campana de Inicio junto al perfil (HOME-01 I01/I05). Sin pendientes no se pinta. */
export function CampanaPendientes(p: { contador: string | null; onPress: () => void }) {
  const { c } = useTema();
  if (p.contador === null) return null;
  const error = p.contador === '!';
  return (
    <Pressable
      testID="campana-pendientes"
      accessibilityRole="button"
      accessibilityLabel={error ? 'Pendientes: no se pudieron cargar' : `Pendientes: ${p.contador}`}
      onPress={p.onPress}
      hitSlop={8}
      style={s.campana}
    >
      <Ionicons name="notifications-outline" size={22} color={c.textPrimary} />
      <View style={[s.contador, { backgroundColor: c.warning }]}>
        <Text testID="campana-contador" style={[tipo.caption, { color: c.onAccent, fontWeight: '700' }]}>{p.contador}</Text>
      </View>
    </Pressable>
  );
}

function HojaBase(p: { testID: string; children: React.ReactNode; onCerrar: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View style={StyleSheet.absoluteFill}>
      <Pressable testID={`${p.testID}-velo`} accessibilityLabel="Cerrar" onPress={p.onCerrar} style={StyleSheet.absoluteFill}>
        <Velo />
      </Pressable>
      <View testID={p.testID} style={[s.hoja, { backgroundColor: c.surfacePrimary, paddingBottom: inset.bottom + espacio.l }]}>{p.children}</View>
    </View>
  );
}

function Dato({ etiqueta, valor, testID }: { etiqueta: string; valor: string; testID?: string }) {
  const { c } = useTema();
  return (
    <View style={s.dato}>
      <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{etiqueta}</Text>
      <Text testID={testID} style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600', flexShrink: 1, textAlign: 'right' }]}>{valor}</Text>
    </View>
  );
}

/** B1 · Swipe «Pagado» / «Cobrado»: resumen previo y decisión de cubrir (D-PREV-08, D-PREV-12). */
export function HojaSwipe(p: {
  fila: FilaPrevision;
  importeTexto: string;
  onImporte: (t: string) => void;
  cuenta: { id: string; nombre: string } | null;
  fecha: string;
  fechaTexto: string;
  enviando: boolean;
  error: string | null;
  onConfirmar: () => void;
  onFormularioCompleto: () => void;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const f = p.fila;
  const verbo = f.tipo === 'INGRESO' ? 'cobraste' : 'pagaste';
  return (
    <HojaBase testID="hoja-swipe" onCerrar={p.onCerrar}>
      <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{`¿${verbo.charAt(0).toUpperCase()}${verbo.slice(1)} ${f.concepto}?`}</Text>
      <Dato etiqueta="Previsión" valor={`${f.concepto} · ${intervaloTexto(f)}`} />
      <Dato etiqueta="Esperado" valor={importeFila(f)} testID="swipe-esperado" />
      <Dato etiqueta="Consecuencia" valor={consecuencia(true)} testID="swipe-consecuencia" />
      <View style={{ gap: espacio.xs }}>
        <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Importe real · Revisa</Text>
        <TextInput
          testID="swipe-importe"
          accessibilityLabel="Importe real"
          value={p.importeTexto}
          onChangeText={p.onImporte}
          keyboardType="decimal-pad"
          style={[tipo.body, s.input, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]}
        />
      </View>
      <Dato etiqueta="Cuenta y fecha" valor={`${p.cuenta?.nombre ?? 'Sin cuenta'} · ${p.fechaTexto}`} testID="swipe-cuenta" />
      <BotonTexto testID="swipe-formulario-completo" titulo="¿Otro tercero, varios pagos o varias cuentas? Abrir el formulario completo" onPress={p.onFormularioCompleto} />
      {p.error ? <Text testID="swipe-error" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{p.error}</Text> : null}
      <BotonPrimario testID="swipe-confirmar" titulo={f.tipo === 'INGRESO' ? 'Confirmar cobro y cubrir' : 'Confirmar pago y cubrir'}
        onPress={p.onConfirmar} cargando={p.enviando} deshabilitado={!p.cuenta} />
    </HojaBase>
  );
}

/** B3 · «No hubo este mes»: motivo opcional; no se registra ningún gasto ni se mueve dinero. */
export function HojaOmitir(p: {
  fila: FilaPrevision;
  motivo: string;
  onMotivo: (t: string) => void;
  enviando: boolean;
  error: string | null;
  onConfirmar: () => void;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const tipoTexto = p.fila.tipo === 'INGRESO' ? 'ingreso' : p.fila.tipo === 'TRANSFERENCIA' ? 'movimiento' : 'gasto';
  return (
    <HojaBase testID="hoja-omitir" onCerrar={p.onCerrar}>
      <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{`¿No hubo ${p.fila.concepto} este mes?`}</Text>
      <Text style={[tipo.body, { color: c.textSecondary }]}>
        {`La previsión del ${intervaloTexto(p.fila)} deja de estar pendiente. No se registra ningún ${tipoTexto} ni se mueve dinero.`}
      </Text>
      <TextInput
        testID="omitir-motivo"
        accessibilityLabel="Motivo opcional"
        placeholder="Motivo opcional"
        placeholderTextColor={c.textSecondary}
        value={p.motivo}
        onChangeText={p.onMotivo}
        maxLength={200}
        style={[tipo.body, s.input, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]}
      />
      {p.error ? <Text testID="omitir-error" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{p.error}</Text> : null}
      <BotonPrimario testID="omitir-confirmar" titulo="No hubo este mes" onPress={p.onConfirmar} cargando={p.enviando} />
      <BotonTexto testID="omitir-cancelar" titulo="Cancelar" onPress={p.onCerrar} />
    </HojaBase>
  );
}

/** B7 · Estado actual tras un rechazo o un fallo: nunca «hecho» (D-PREV-14). */
export function AvisoEstadoActual(p: {
  concepto: string;
  intervalo: string;
  estado: string;
  derivado: string | null;
  incierto: boolean;
  mensaje: string;
  onEntendido: () => void;
}) {
  const { c } = useTema();
  return (
    <HojaBase testID="aviso-estado-actual" onCerrar={p.onEntendido}>
      <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{p.incierto ? 'No sabemos si se guardó' : 'Ha cambiado; revisa'}</Text>
      <Text testID="aviso-estado-texto" style={[tipo.body, { color: c.textSecondary }]}>{p.incierto ? TEXTO_NO_SABEMOS : p.mensaje}</Text>
      <Dato etiqueta={`${p.concepto} · ${p.intervalo}`} valor={estadoLegible(p.estado, p.derivado)} testID="aviso-estado-valor" />
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>Este segundo intento no ha guardado nada. Deshacer una omisión no está disponible en esta versión.</Text>
      <BotonPrimario testID="aviso-entendido" titulo="Entendido" onPress={p.onEntendido} />
    </HojaBase>
  );
}

/** «¿Queda cubierta la previsión?»: dos opciones, NINGUNA marcada al entrar (P-PREV-02). */
export function QuedaCubierta(p: { valor: boolean | null; onCambiar: (v: boolean) => void; testIDBase?: string }) {
  const { c } = useTema();
  const base = p.testIDBase ?? 'cubierta';
  return (
    <View style={{ gap: espacio.s }} accessibilityRole="radiogroup" accessibilityLabel="¿Queda cubierta la previsión?">
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>
        ¿Queda cubierta la previsión?{p.valor === null ? <Text style={{ fontWeight: '400' }}> elige una</Text> : null}
      </Text>
      <View style={s.chips}>
        <Chip testID={`${base}-si`} etiqueta="Sí, queda cubierta" seleccionado={p.valor === true} onPress={() => p.onCambiar(true)} />
        <Chip testID={`${base}-no`} etiqueta="No, falta una parte" seleccionado={p.valor === false} onPress={() => p.onCambiar(false)} />
      </View>
    </View>
  );
}

/** Acción del detalle con su motivo atenuado si no está disponible. */
export function AccionPrevision(p: { testID: string; titulo: string; disponible: boolean; motivo: string | null; onPress: () => void; primaria?: boolean }) {
  const { c } = useTema();
  return (
    <View style={{ gap: espacio.xs }}>
      {p.primaria ? (
        <BotonPrimario testID={p.testID} titulo={p.titulo} onPress={p.onPress} deshabilitado={!p.disponible} />
      ) : (
        <Pressable
          testID={p.testID}
          accessibilityRole="button"
          accessibilityState={{ disabled: !p.disponible }}
          disabled={!p.disponible}
          onPress={p.disponible ? p.onPress : undefined}
          style={[s.secundario, { borderColor: c.borderStandard, opacity: p.disponible ? 1 : 0.5 }]}
        >
          <Text style={[tipo.bodyEmphasis, { color: p.disponible ? c.accent : c.textSecondary }]}>{p.titulo}</Text>
        </Pressable>
      )}
      {!p.disponible && p.motivo ? <Text testID={`${p.testID}-motivo`} style={[tipo.caption, { color: c.textSecondary }]}>{p.motivo}</Text> : null}
    </View>
  );
}

export function usarIntencion(nuevoId: () => string) {
  /** Identidad de una acción: se conserva para reintentar tras un fallo de conexión y se libera al terminar. */
  const ref = useRef<string | null>(null);
  return {
    actual: () => (ref.current ??= nuevoId()),
    liberar: () => {
      ref.current = null;
    },
  };
}

const s = StyleSheet.create({
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 12, paddingVertical: espacio.s },
  importeFila: { fontSize: 17, lineHeight: 22 },
  campana: { minWidth: TACTIL_MIN, minHeight: TACTIL_MIN, alignItems: 'center', justifyContent: 'center' },
  contador: { position: 'absolute', top: 4, right: 2, minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 4, alignItems: 'center', justifyContent: 'center' },
  hoja: { position: 'absolute', left: 0, right: 0, bottom: 0, borderTopLeftRadius: radio.xl, borderTopRightRadius: radio.xl, padding: espacio.l, gap: espacio.m },
  dato: { flexDirection: 'row', justifyContent: 'space-between', gap: espacio.m },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  secundario: { minHeight: 52, borderRadius: radio.m, borderWidth: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: espacio.l },
});
