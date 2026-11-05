// ============================================================
// GAPTO MOBILE 2027
// Fichero: Reparto.tsx
// Ruta: mobile/src/components/Reparto.tsx
// Descripción: Piezas comunes de las pantallas de reparto y posiciones (F05-06 M3; lámina REP v0.2). `SelectorPersona` (E7, P-REP-05): solo terceros ACTIVOS de tipo persona, con filtro local, «Recientes» por uso y alta en el momento («+ Crear persona «texto»», naturaleza PERSONA, UUID generado al iniciar el alta y reutilizado en el reintento). `OpcionAtenuada`: lo que esta versión no hace se ve atenuado y con su motivo en lenguaje llano (§57.1.1). `Campo`, `FilaRevision`, `CabeceraTarea` y `Aviso` siguen el patrón de la devolución (DEV v0.1).
// Versión: 0.1.0 (F05-06 M3 §B1)
// Versión: 0.2.0 (F05-D052 paso 2 · C-03, F05 §66.A.3): `SelectorPersona` admite `naturalezas` (por defecto solo PERSONA: el reparto no cambia). Con PERSONA y EMPRESA («Quién te lo debe» de C-03) lista ambas con su tipo, busca «persona o empresa», ofrece crear persona o empresa y su nota es la de C-03; ORGANISMO, OTRO y sin naturaleza nunca aparecen (DEU-C03-NATURALEZAS). `excluir` sigue quitando, p. ej., el comercio del gasto.
// Versión: 0.2.1 (F06-M1 Tokens, V1 con anillo (F06-D003; dictamen PT-01..PT-12 del 2026-11-05)): el texto y los iconos con significado usan los tokens de rol (`accentText`, `criticalText`, `positiveText`, `warningText`); los rellenos semánticos siguen solo como relleno, borde o fondo.
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, Tercero } from '../api/cliente';
import { TEXTO_SOLO_PERSONAS } from '../domain/reparto';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonTexto, EstadoDato } from './Basicos';

export function Campo({ etiqueta, children, testID }: { etiqueta: string; children: React.ReactNode; testID?: string }) {
  const { c } = useTema();
  return (
    <View testID={testID} style={{ gap: espacio.s }}>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{etiqueta}</Text>
      {children}
    </View>
  );
}

export function FilaRevision(p: { testID: string; titulo: string; detalle?: string; valor: string; etiqueta?: string }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={[s.kv, { paddingVertical: espacio.xs }]}>
      <View style={{ flex: 1 }}>
        <Text style={[tipo.body, { color: c.textPrimary }]}>{p.titulo}</Text>
        {p.detalle ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{p.detalle}</Text> : null}
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        {p.valor ? <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{p.valor}</Text> : null}
        {p.etiqueta ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{p.etiqueta}</Text> : null}
      </View>
    </View>
  );
}

export function Bloque({ titulo, children, testID }: { titulo: string; children: React.ReactNode; testID?: string }) {
  const { c } = useTema();
  return (
    <View testID={testID} style={{ gap: espacio.s }}>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{titulo}</Text>
      <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>{children}</View>
    </View>
  );
}

export function CabeceraTarea({ titulo, izquierda, derecha }: { titulo: string; izquierda: React.ReactNode; derecha?: React.ReactNode }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
      <View style={{ minWidth: 72 }}>{izquierda}</View>
      <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{titulo}</Text>
      <View style={{ minWidth: 72, alignItems: 'flex-end' }}>{derecha}</View>
    </View>
  );
}

export function Aviso({ testID, texto, critico }: { testID: string; texto: string; critico?: boolean }) {
  const { c } = useTema();
  return (
    <View testID={testID} accessibilityLiveRegion={critico ? 'assertive' : 'polite'}
      style={[s.aviso, critico ? { backgroundColor: c.surfacePrimary, borderColor: c.critical, borderWidth: 1 } : { backgroundColor: c.partialSurface }]}>
      <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{texto}</Text>
    </View>
  );
}

/** Lo que no se hace en esta versión: atenuado, sin acción y con su motivo (§57.1.1). */
export function OpcionAtenuada({ testID, titulo, motivo }: { testID: string; titulo: string; motivo: string }) {
  const { c } = useTema();
  return (
    <View testID={testID} accessibilityState={{ disabled: true }} accessibilityLabel={`${titulo}. No disponible: ${motivo}`} style={{ gap: espacio.xs }}>
      <View style={[s.chipApagado, { borderColor: c.borderDefault }]}>
        <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{titulo}</Text>
      </View>
      <Text testID={`${testID}-motivo`} style={[tipo.footnote, { color: c.textSecondary }]}>{motivo}</Text>
    </View>
  );
}

export function Inicial({ nombre }: { nombre: string }) {
  const { c } = useTema();
  return (
    <View style={[s.inicial, { backgroundColor: c.accentSurface }]} accessibilityElementsHidden importantForAccessibility="no">
      <Text style={[tipo.subheadline, { color: c.accentText, fontWeight: '600' }]}>{(nombre.trim()[0] ?? '·').toUpperCase()}</Text>
    </View>
  );
}

type NaturalezaAdmitida = 'PERSONA' | 'EMPRESA';
const NOMBRE_NATURALEZA: Record<NaturalezaAdmitida, string> = { PERSONA: 'Persona', EMPRESA: 'Empresa' };

/** E7 · P-REP-05: personas del reparto (solo terceros de tipo persona); con `naturalezas`, también empresas (C-03). */
export function SelectorPersona(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  excluir: string[];
  titulo?: string;
  onElegir: (t: { id: string; nombre: string }) => void;
  onCancelar: () => void;
  /** F05-D052 C-03: naturalezas admitidas (por defecto solo PERSONA). La política la fija el servidor por ruta. */
  naturalezas?: NaturalezaAdmitida[];
  /** Nota al pie (por defecto la del reparto). */
  nota?: string;
}) {
  const naturalezas: NaturalezaAdmitida[] = p.naturalezas ?? ['PERSONA'];
  const conEmpresas = naturalezas.includes('EMPRESA');
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [lista, setLista] = useState<{ fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; terceros: Tercero[] }>({ fase: 'CARGANDO' });
  const [texto, setTexto] = useState('');
  const [alta, setAlta] = useState<{ fase: 'NADA' } | { fase: 'ENVIANDO' } | { fase: 'ERROR'; mensaje: string }>({ fase: 'NADA' });
  const idAlta = useRef<{ nombre: string; id: string } | null>(null);

  const cargar = async () => {
    setLista({ fase: 'CARGANDO' });
    const r = await p.cliente.listarTerceros();
    setLista(r.tipo === 'OK' ? { fase: 'OK', terceros: r.datos.terceros } : { fase: 'ERROR' });
  };
  useEffect(() => {
    void cargar();
  }, []);

  const norm = (t: string) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  const personas =
    lista.fase === 'OK'
      ? lista.terceros
          .filter((t) => t.enabled && naturalezas.includes(t.naturaleza as NaturalezaAdmitida) && !p.excluir.includes(t.id))
          .filter((t) => !texto.trim() || norm(t.nombre).includes(norm(texto)))
          .sort((a, b) => (b.usos ?? 0) - (a.usos ?? 0) || a.nombre.localeCompare(b.nombre))
      : [];
  const nombreNuevo = texto.trim();
  const existeIgual = personas.some((t) => norm(t.nombre) === norm(nombreNuevo));

  const crear = async (naturaleza: NaturalezaAdmitida = 'PERSONA') => {
    if (!nombreNuevo || alta.fase === 'ENVIANDO') return;
    // Mismo UUID en el reintento del MISMO alta (nombre y naturaleza); otro alta, UUID nuevo.
    const clave = `${naturaleza}:${nombreNuevo}`;
    if (!idAlta.current || idAlta.current.nombre !== clave) idAlta.current = { nombre: clave, id: p.nuevoId() };
    setAlta({ fase: 'ENVIANDO' });
    const r = await p.cliente.altaTercero({ id: idAlta.current.id, nombre: nombreNuevo, naturaleza });
    if (r.tipo === 'OK') {
      idAlta.current = null;
      setAlta({ fase: 'NADA' });
      p.onElegir({ id: r.datos.tercero.id, nombre: r.datos.tercero.nombre });
    } else setAlta({ fase: 'ERROR', mensaje: r.mensaje });
  };

  return (
    <View testID="selector-persona" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={p.titulo ?? 'Añadir persona'} izquierda={<BotonTexto testID="selector-persona-atras" titulo="‹ Atrás" onPress={p.onCancelar} />} />
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: espacio.l, gap: espacio.m, paddingBottom: inset.bottom + espacio.xxl }}>
        <TextInput testID="selector-persona-buscar" accessibilityLabel={conEmpresas ? 'Buscar persona o empresa' : 'Buscar persona'}
          placeholder={conEmpresas ? 'Buscar persona o empresa' : 'Buscar persona'} placeholderTextColor={c.textSecondary}
          value={texto} onChangeText={setTexto}
          style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]} />
        {lista.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
        {lista.fase === 'ERROR' ? (
          <Pressable testID="selector-persona-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {lista.fase === 'OK' ? (
          <View style={{ gap: espacio.xs }}>
            <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{texto.trim() ? (conEmpresas ? 'Personas y empresas' : 'Personas') : 'Recientes'}</Text>
            {personas.map((t) => (
              <Pressable key={t.id} testID={`persona-${t.id}`} accessibilityRole="button" accessibilityLabel={t.nombre} onPress={() => p.onElegir({ id: t.id, nombre: t.nombre })}
                style={[s.fila, { backgroundColor: c.surfacePrimary }]}>
                <Inicial nombre={t.nombre} />
                <View style={{ flex: 1 }}>
                  <Text style={[tipo.body, { color: c.textPrimary }]}>{t.nombre}</Text>
                  <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`${NOMBRE_NATURALEZA[t.naturaleza as NaturalezaAdmitida] ?? 'Persona'}${t.usos ? ` · ${t.usos} ${t.usos === 1 ? 'registro' : 'registros'}` : ''}`}</Text>
                </View>
              </Pressable>
            ))}
            {personas.length === 0 && !nombreNuevo ? (
              <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{conEmpresas ? 'Todavía no tienes personas ni empresas. Escribe un nombre para crearla.' : 'Todavía no tienes personas. Escribe un nombre para crearla.'}</Text>
            ) : null}
          </View>
        ) : null}
        {nombreNuevo && !existeIgual ? (
          <Pressable testID="selector-persona-crear" accessibilityRole="button" onPress={() => void crear('PERSONA')} style={[s.fila, { backgroundColor: c.surfacePrimary }]}>
            <Text style={[tipo.body, { color: c.accentText }]}>{alta.fase === 'ENVIANDO' ? 'Creando…' : `+ Crear persona «${nombreNuevo}»`}</Text>
          </Pressable>
        ) : null}
        {conEmpresas && nombreNuevo && !existeIgual && alta.fase !== 'ENVIANDO' ? (
          <Pressable testID="selector-persona-crear-empresa" accessibilityRole="button" onPress={() => void crear('EMPRESA')} style={[s.fila, { backgroundColor: c.surfacePrimary }]}>
            <Text style={[tipo.body, { color: c.accentText }]}>{`+ Crear empresa «${nombreNuevo}»`}</Text>
          </Pressable>
        ) : null}
        {alta.fase === 'ERROR' ? <Aviso testID="selector-persona-alta-error" texto={alta.mensaje} critico /> : null}
        <Text testID="selector-persona-solo-personas" style={[tipo.footnote, { color: c.textSecondary }]}>{p.nota ?? TEXTO_SOLO_PERSONAS}</Text>
      </ScrollView>
    </View>
  );
}

export const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  form: { padding: espacio.l, gap: espacio.xl },
  tarjeta: { borderRadius: radio.m, padding: espacio.m, gap: espacio.s },
  kv: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: espacio.m },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderRadius: radio.m, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 8 },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4, minWidth: 0 },
  inputImporte: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN, width: 112, textAlign: 'right' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  chipApagado: { borderWidth: 1, borderRadius: radio.pill, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN, justifyContent: 'center', alignSelf: 'flex-start', opacity: 0.5 },
  aviso: { borderRadius: radio.m, padding: espacio.m, gap: espacio.s },
  inicial: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  pantalla: { flex: 1, paddingHorizontal: espacio.l, justifyContent: 'space-between' },
  exito: { borderRadius: radio.l, padding: espacio.xl, alignItems: 'center', gap: espacio.s },
});
