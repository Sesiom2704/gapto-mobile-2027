// ============================================================
// GAPTO MOBILE 2027
// Fichero: Contextos.tsx
// Ruta: mobile/src/components/Contextos.tsx
// Descripción: Formulario y selector de contexto (F05-03 J2 §2.3/§2.5; F05 §46.3 A6; lámina REG-DYN / SET-TH / SET-CTX v0.1 C01, G03, S03). Formulario C01: Nombre, Tipo (Viaje, Reforma, Evento, Social, Proyecto, Otro; NINGUNO marcado al empezar) y «Fechas opcional» Desde — Hasta (dd/mm/aaaa). Alta con UUID sellado al abrir (el reintento reutiliza el MISMO) y edición con row_version. En el registro, «Crear y usar» devuelve el contexto creado y el registro lo usa; la escritura del contexto es independiente del registro. El selector (G03) lista solo los contextos ACTIVOS, «Sin contexto» y «Nuevo contexto».
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.3/§2.5)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, Contexto, TipoContexto } from '../api/cliente';
import { ddmmaaaaAIso, isoADdmmaaaa } from '../domain/fechas';
import { detalleContexto, filtrar, TIPOS_CONTEXTO } from '../domain/maestros';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, Chip, EstadoDato } from './Basicos';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef } from './Formulario';
import { Hoja } from './HojasCategoria';
import { BotonSecundario } from './SelectorCategorias';

export const TEXTO_CONTEXTO = 'Un contexto agrupa gastos e ingresos de un viaje, una obra o un evento sin cambiar su categoría.';
/** DERIVADO. */
export const TEXTO_FECHA_MAL = 'Escribe la fecha como dd/mm/aaaa.';
/** DERIVADO. */
export const TEXTO_FECHAS_ORDEN = 'La fecha «Hasta» no puede ser anterior a «Desde».';
export const TEXTO_VERSION_CTX = 'Este contexto ha cambiado mientras lo editabas. Hemos cargado la versión actual. Revisa y guarda de nuevo.';
export const TEXTO_INDETERMINADO_CTX = 'No se ha podido confirmar el cambio. Revisa el estado actual antes de repetirlo.';

interface FormCtx {
  nombre: string;
  tipo: TipoContexto | null;
  desde: string;
  hasta: string;
}

const formDe = (x: Contexto | null): FormCtx => ({
  nombre: x?.nombre ?? '',
  tipo: x?.tipo_contexto ?? null,
  desde: x?.fecha_inicio ? isoADdmmaaaa(x.fecha_inicio) : '',
  hasta: x?.fecha_fin ? isoADdmmaaaa(x.fecha_fin) : '',
});

/** Lo que falta o está mal en el formulario (en su orden); vacío = se puede guardar. */
export function faltaContexto(f: FormCtx): string[] {
  const r: string[] = [];
  if (!f.nombre.trim()) r.push('nombre');
  if (f.tipo === null) r.push('tipo');
  return r;
}

function fechas(f: FormCtx): { desde: string | null; hasta: string | null } | string {
  const desde = f.desde.trim() ? ddmmaaaaAIso(f.desde) : null;
  const hasta = f.hasta.trim() ? ddmmaaaaAIso(f.hasta) : null;
  if ((f.desde.trim() && !desde) || (f.hasta.trim() && !hasta)) return TEXTO_FECHA_MAL;
  if (desde && hasta && hasta < desde) return TEXTO_FECHAS_ORDEN;
  return { desde, hasta };
}

export function FormularioContexto(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  existente: Contexto | null;
  tituloBoton: string;
  testID?: string;
  onHecho: (x: Contexto) => void;
  onCancelar: () => void;
  /** Recarga tras VERSION_DESFASADA; devuelve la versión actual (o null). */
  onRecargar?: () => Promise<Contexto | null>;
  pie?: React.ReactNode;
  avisoInicial?: AvisoCaja;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [f, setF] = useState<FormCtx>(formDe(p.existente));
  const [aviso, setAviso] = useState<AvisoCaja>(p.avisoInicial ?? null);
  const [ocupado, setOcupado] = useState(false);
  const idAlta = useRef<string>(p.existente ? p.existente.id : p.nuevoId());
  useEffect(() => setAviso(p.avisoInicial ?? null), [p.avisoInicial]);

  const faltas = faltaContexto(f);
  const guardar = async () => {
    if (ocupado || faltas.length > 0) return;
    const fe = fechas(f);
    if (typeof fe === 'string') return setAviso({ tipo: 'AVISO', texto: fe });
    setOcupado(true);
    setAviso(null);
    const contenido = { nombre: f.nombre.trim(), tipo_contexto: f.tipo!, fecha_inicio: fe.desde, fecha_fin: fe.hasta };
    const r = p.existente
      ? await p.cliente.editarContexto(p.existente.id, { row_version: p.existente.row_version, ...contenido })
      : await p.cliente.altaContexto({ id: idAlta.current, ...contenido });
    setOcupado(false);
    if (r.tipo === 'OK') return p.onHecho(r.datos.contexto);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO_CTX });
    if (r.codigo === 'VERSION_DESFASADA' && p.onRecargar) {
      const x = await p.onRecargar();
      if (x) setF(formDe(x));
      return setAviso({ tipo: 'AVISO', texto: TEXTO_VERSION_CTX });
    }
    setAviso({ tipo: 'AVISO', texto: r.mensaje || TEXTO_INDETERMINADO_CTX });
  };

  return (
    <View testID={p.testID ?? 'form-contexto'} style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={p.existente ? 'Editar contexto' : 'Nuevo contexto'} testIDCancelar="ctx-cancelar" onCancelar={p.onCancelar} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID={aviso.tipo === 'OK' ? 'ctx-aviso-ok' : 'ctx-aviso'} aviso={aviso} /> : null}
        <Campo etiqueta="Nombre">
          <CampoTexto testID="ctx-nombre" etiqueta="Nombre" marcador="Ej.: Finde Cartagena" valor={f.nombre} maximo={120} onCambiar={(t) => setF({ ...f, nombre: t })} />
        </Campo>
        <Campo etiqueta="Tipo">
          <View style={ef.chips}>
            {TIPOS_CONTEXTO.map((t) => (
              <Chip key={t.valor} testID={`ctx-tipo-${t.valor}`} etiqueta={t.etiqueta} seleccionado={f.tipo === t.valor} onPress={() => setF({ ...f, tipo: t.valor })} />
            ))}
          </View>
        </Campo>
        <Campo etiqueta="Fechas" opcional>
          <View style={{ flexDirection: 'row', gap: espacio.s, alignItems: 'center' }}>
            <View style={{ flex: 1 }}>
              <CampoTexto testID="ctx-desde" etiqueta="Desde" marcador="Desde dd/mm/aaaa" valor={f.desde} onCambiar={(t) => setF({ ...f, desde: t })} />
            </View>
            <Text style={[tipo.body, { color: c.textSecondary }]}>—</Text>
            <View style={{ flex: 1 }}>
              <CampoTexto testID="ctx-hasta" etiqueta="Hasta" marcador="Hasta dd/mm/aaaa" valor={f.hasta} onCambiar={(t) => setF({ ...f, hasta: t })} />
            </View>
          </View>
        </Campo>
        <BotonPrimario
          testID="ctx-guardar"
          titulo={ocupado ? 'Guardando…' : p.tituloBoton}
          cargando={ocupado}
          deshabilitado={faltas.length > 0}
          ayuda={faltas.length > 0 ? `Falta: ${faltas.join(' y ')}` : undefined}
          onPress={() => void guardar()}
        />
        {faltas.length > 0 ? <Text testID="ctx-falta" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(' y ')}`}</Text> : null}
        {p.pie}
      </ScrollView>
    </View>
  );
}

/** Selector de contexto del registro (G03): activos, «Sin contexto» y «Nuevo contexto». */
export function SelectorContexto(p: {
  cliente: ClienteApi;
  seleccionadoId: string | null;
  onElegir: (x: Contexto | null) => void;
  onNuevo: () => void;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const [lista, setLista] = useState<Contexto[] | null | 'ERROR'>(null);
  const [filtro, setFiltro] = useState('');
  const cargar = async () => {
    setLista(null);
    const r = await p.cliente.listarContextos();
    setLista(r.tipo === 'OK' ? r.datos.contextos.filter((x) => x.enabled) : 'ERROR');
  };
  useEffect(() => {
    void cargar();
  }, []);
  const visibles = Array.isArray(lista) ? filtrar(lista, filtro) : [];
  return (
    <Hoja titulo="Contexto" testID="selector-contexto">
      <CampoTexto testID="contexto-filtro" etiqueta="Filtrar por nombre" marcador="Filtrar por nombre" valor={filtro} onCambiar={setFiltro} />
      {lista === null ? <EstadoDato estado="CARGANDO" /> : null}
      {lista === 'ERROR' ? (
        <Pressable testID="contextos-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
          <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
        </Pressable>
      ) : null}
      <ScrollView style={{ maxHeight: 320 }} keyboardShouldPersistTaps="handled">
        <Pressable testID="contexto-ninguno" accessibilityRole="button" onPress={() => p.onElegir(null)} style={[s.fila, { borderColor: c.borderDefault }]}>
          <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>Sin contexto</Text>
          {p.seleccionadoId === null ? <Ionicons name="checkmark" size={18} color={c.accent} /> : null}
        </Pressable>
        {visibles.map((x) => (
          <Pressable key={x.id} testID={`contexto-${x.id}`} accessibilityRole="button" accessibilityLabel={`${x.nombre}. ${detalleContexto(x)}`}
            onPress={() => p.onElegir(x)} style={[s.fila, { borderColor: c.borderDefault }]}>
            <View style={{ flex: 1 }}>
              <Text style={[tipo.body, { color: c.textPrimary }]}>{x.nombre}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>{detalleContexto(x)}</Text>
            </View>
            {p.seleccionadoId === x.id ? <Ionicons name="checkmark" size={18} color={c.accent} /> : null}
          </Pressable>
        ))}
        <Pressable testID="contexto-nuevo" accessibilityRole="button" onPress={p.onNuevo} style={[s.fila, { borderColor: c.borderDefault }]}>
          <Ionicons name="add" size={18} color={c.accent} />
          <Text style={[tipo.body, { color: c.accent, flex: 1 }]}>Nuevo contexto</Text>
        </Pressable>
      </ScrollView>
      <BotonSecundario testID="contexto-cerrar" titulo="Cerrar" onPress={p.onCerrar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 8, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: espacio.xs },
});
