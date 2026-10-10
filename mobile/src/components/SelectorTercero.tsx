// ============================================================
// GAPTO MOBILE 2027
// Fichero: SelectorTercero.tsx
// Ruta: mobile/src/components/SelectorTercero.tsx
// Descripción: Selector de tercero del registro y de Ajustes (F05-04 J2 §2.3; F05 §46.3 A5, §46.4 R5; lámina REG-DYN P01/P02). Lista solo los terceros ACTIVOS con filtro local por nombre (normalización C06; no es la búsqueda de F05-05), «Sin tercero» y «+ Crear «texto»». Antes de crear consulta los posibles duplicados al servidor (misma normalización, incluidos los inactivos) y, si los hay, muestra P02: «Ya tienes un tercero con ese nombre. ¿Es el mismo?» con «Usar el existente» (activo), «Reactivar» (inactivo) o «Crear otro «nombre»» (homónimos válidos, sin fusión). El alta es mínima (solo nombre, naturaleza «No lo sé») y escritura INDEPENDIENTE del registro, con UUID generado al iniciar el alta (el reintento reutiliza el MISMO). Un fallo del registro no deshace el alta.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.3)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import type { ClienteApi, Tercero } from '../api/cliente';
import { detalleTercero, filtrar } from '../domain/maestros';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, EstadoDato } from './Basicos';
import { Aviso, Hoja } from './HojasCategoria';
import { BotonSecundario } from './SelectorCategorias';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: Tercero[] };

export const TEXTO_DUPLICADO = 'Ya tienes un tercero con ese nombre. ¿Es el mismo?';
export const TEXTO_INACTIVO = 'Está desactivado. Te recomendamos reactivarlo en lugar de crear otro.';

export function SelectorTercero(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  titulo?: string;
  seleccionadoId: string | null;
  onElegir: (t: Tercero | null) => void;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [filtro, setFiltro] = useState('');
  const [candidatos, setCandidatos] = useState<Tercero[] | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const idAlta = useRef<{ nombre: string; id: string } | null>(null);

  const cargar = async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.listarTerceros();
    setCarga(r.tipo === 'OK' ? { fase: 'OK', lista: r.datos.terceros } : { fase: 'ERROR' });
  };
  useEffect(() => {
    void cargar();
  }, []);

  const activos = useMemo(() => (carga.fase === 'OK' ? filtrar(carga.lista.filter((t) => t.enabled), filtro) : []), [carga, filtro]);
  const nombre = filtro.trim();

  const crear = async (forzar: boolean) => {
    if (!nombre || ocupado) return;
    setOcupado(true);
    setAviso(null);
    if (!forzar) {
      const cand = await p.cliente.candidatosTercero(nombre);
      if (cand.tipo === 'OK' && cand.datos.terceros.length > 0) {
        setOcupado(false);
        return setCandidatos(cand.datos.terceros);
      }
    }
    // UUID del alta fijado por nombre: «Reintentar» reutiliza el MISMO (R5).
    if (!idAlta.current || idAlta.current.nombre !== nombre) idAlta.current = { nombre, id: p.nuevoId() };
    const r = await p.cliente.altaTercero({ id: idAlta.current.id, nombre, naturaleza: null });
    setOcupado(false);
    if (r.tipo === 'OK') return p.onElegir(r.datos.tercero);
    setAviso(r.tipo === 'INDETERMINADO' ? 'No se ha podido confirmar el alta. Vuelve a intentarlo: no se duplicará.' : r.mensaje);
  };

  const reactivar = async (t: Tercero) => {
    setOcupado(true);
    const r = await p.cliente.reactivarTercero(t.id, t.row_version);
    setOcupado(false);
    if (r.tipo === 'OK') return p.onElegir(r.datos.tercero);
    setAviso(r.tipo === 'INDETERMINADO' ? 'No se ha podido confirmar el cambio. Vuelve a cargar antes de repetirlo.' : r.mensaje);
  };

  if (candidatos) {
    return (
      <Hoja titulo={`Crear «${nombre}»`} testID="tercero-duplicado">
        <Aviso testID="tercero-duplicado-aviso" texto={TEXTO_DUPLICADO} />
        {candidatos.map((t) => (
          <View key={t.id} testID={`candidato-${t.id}`} style={[s.fila, { borderColor: c.borderDefault }]}>
            <View style={{ flex: 1 }}>
              <Text style={[tipo.body, { color: c.textPrimary }]}>{t.nombre}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>{detalleTercero(t) || (t.enabled ? '' : 'Inactivo')}</Text>
              {!t.enabled ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{TEXTO_INACTIVO}</Text> : null}
            </View>
          </View>
        ))}
        {candidatos.filter((t) => t.enabled).slice(0, 1).map((t) => (
          <BotonPrimario key="usar" testID="tercero-usar-existente" titulo="Usar el existente" onPress={() => p.onElegir(t)} />
        ))}
        {candidatos.filter((t) => !t.enabled).slice(0, 1).map((t) => (
          <BotonPrimario key="reactivar" testID="tercero-reactivar" titulo="Reactivar" cargando={ocupado} onPress={() => void reactivar(t)} />
        ))}
        <BotonSecundario testID="tercero-crear-otro" titulo={`Crear otro «${nombre}»`} onPress={() => { setCandidatos(null); void crear(true); }} />
        {aviso ? <Aviso testID="tercero-aviso" texto={aviso} /> : null}
      </Hoja>
    );
  }

  return (
    <Hoja titulo={p.titulo ?? 'Tercero'} testID="selector-tercero">
      <TextInput
        testID="tercero-filtro"
        accessibilityLabel="Filtrar por nombre"
        value={filtro}
        onChangeText={setFiltro}
        placeholder="Filtrar por nombre"
        placeholderTextColor={c.textSecondary}
        style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
      />
      {carga.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
      {carga.fase === 'ERROR' ? (
        <Pressable testID="terceros-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
          <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
        </Pressable>
      ) : null}
      <ScrollView style={{ maxHeight: 320 }} keyboardShouldPersistTaps="handled">
        <Pressable testID="tercero-ninguno" accessibilityRole="button" onPress={() => p.onElegir(null)} style={[s.fila, { borderColor: c.borderDefault }]}>
          <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>Sin tercero</Text>
          {p.seleccionadoId === null ? <Ionicons name="checkmark" size={18} color={c.accent} /> : null}
        </Pressable>
        {activos.map((t) => (
          <Pressable key={t.id} testID={`tercero-${t.id}`} accessibilityRole="button" accessibilityLabel={t.nombre} onPress={() => p.onElegir(t)}
            style={[s.fila, { borderColor: c.borderDefault }]}>
            <View style={{ flex: 1 }}>
              <Text style={[tipo.body, { color: c.textPrimary }]}>{t.nombre}</Text>
              {detalleTercero(t) ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{detalleTercero(t)}</Text> : null}
            </View>
            {p.seleccionadoId === t.id ? <Ionicons name="checkmark" size={18} color={c.accent} /> : null}
          </Pressable>
        ))}
        {nombre ? (
          <Pressable testID="tercero-crear" accessibilityRole="button" disabled={ocupado} onPress={() => void crear(false)} style={[s.fila, { borderColor: c.borderDefault }]}>
            <Ionicons name="add" size={18} color={c.accent} />
            <Text style={[tipo.body, { color: c.accent, flex: 1 }]}>{`Crear «${nombre}»`}</Text>
          </Pressable>
        ) : null}
      </ScrollView>
      {aviso ? <Aviso testID="tercero-aviso" texto={aviso} /> : null}
      <BotonSecundario testID="tercero-cerrar" titulo="Cerrar" onPress={p.onCerrar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 8, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: espacio.xs },
});
