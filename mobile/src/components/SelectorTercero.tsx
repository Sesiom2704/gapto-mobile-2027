// ============================================================
// GAPTO MOBILE 2027
// Fichero: SelectorTercero.tsx
// Ruta: mobile/src/components/SelectorTercero.tsx
// Descripción: Selector de tercero del registro y de Ajustes (F05-04 J2 §2.3; F05 §46.3 A5, §46.4 R5; lámina REG-DYN P01/P02). Lista solo los terceros ACTIVOS con filtro local por nombre (normalización C06; no es la búsqueda de F05-05), «Sin tercero» y «+ Crear «texto»». Antes de crear consulta los posibles duplicados al servidor (misma normalización, incluidos los inactivos) y, si los hay, muestra P02: «Ya tienes un tercero con ese nombre. ¿Es el mismo?» con «Usar el existente» (activo), «Reactivar» (inactivo) o «Crear otro «nombre»» (homónimos válidos, sin fusión). El alta es mínima (solo nombre, naturaleza «No lo sé») y escritura INDEPENDIENTE del registro, con UUID generado al iniciar el alta (el reintento reutiliza el MISMO). Un fallo del registro no deshace el alta.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.3)
// Versión: 0.2.0 (F05-05 K3 §2.3; F05 §49.4 A4, D-SRCH-04; lámina SRCH-ACT-AFI A3, A4, A8): «Recientes» (GET /v1/senales/terceros con el tipo y la fecha del registro; motivo «Usado hace N días» o «Frecuente en tus gastos | ingresos»); campo «Buscar o crear tercero»: con 2 o más caracteres consulta al servidor (ILIKE sobre nombre y nombre legal, sensible a acentos en v1) tras una pausa, con los inactivos marcados y «Reactivar» en línea (lo reactiva y lo elige, M-D05); con menos, el filtro local de siempre sobre los activos y «Todos · N terceros». Homónimos con segunda línea de datos reales: naturaleza, registros y último uso. Alta y duplicados (P02) sin cambios.
// Versión: 0.2.1 (F06-M1 Tokens, V1 con anillo (F06-D003; dictamen PT-01..PT-12 del 2026-11-05)): el texto y los iconos con significado usan los tokens de rol (`accentText`, `criticalText`, `positiveText`, `warningText`); los rellenos semánticos siguen solo como relleno, borde o fondo.
// Versión: 0.3.0 (F06 T6 · S1 piezas comunes; F09 0.55 §12.107.1 puntos 5 y 6, FA-01/FA-04): el selector se abre a pantalla completa con el marco común `PantallaSelector` («Cerrar» arriba a la derecha, mismo `testID` `tercero-cerrar`; cierra el teclado al abrirse) y la lista ocupa el alto disponible. Props, callbacks, filtro, alta, duplicados (P02, sigue siendo hoja de diálogo) y «Reactivar» sin cambios.
// Versión: 0.4.0 (F06 T6 · S7-A N2; DP-09, DT-04, F09 0.55 §12.107.3): prop `soloBancos` (Banco de la hipoteca): lista solo los terceros con el rol ENTIDAD_FINANCIERA (GET /v1/terceros?rol=…), sin «Sin tercero», recientes ni búsqueda en el servidor; «+ Crear banco «texto»» crea el tercero y lo marca (si el rol no se escribe, lo dice y no lo elige); sin ninguno, «Marca tus bancos en Ajustes → Terceros». Sin la prop, el selector no cambia.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import type { ClienteApi, Tercero } from '../api/cliente';
import { detalleTercero, detalleUso, filtrar } from '../domain/maestros';
import type { TerceroReciente } from '../domain/senales';
import { textoReciente } from '../domain/senales';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto, EstadoDato } from './Basicos';
import { Aviso, Hoja } from './HojasCategoria';
import { PantallaSelector } from './PantallaSelector';
import { BotonSecundario } from './SelectorCategorias';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: Tercero[] };

export const TEXTO_DUPLICADO = 'Ya tienes un tercero con ese nombre. ¿Es el mismo?';
export const TEXTO_INACTIVO = 'Está desactivado. Te recomendamos reactivarlo en lugar de crear otro.';
export const TEXTO_INACTIVO_BUSQUEDA =
  'Un tercero inactivo no se puede elegir tal cual. «Reactivar» lo vuelve a activar y lo elige; sus preferencias y plantillas no se reactivan solas.';
/** Caracteres a partir de los que la búsqueda consulta al servidor (A4). */
export const MIN_BUSQUEDA = 2;
/** F06 T6 · S7-A: estado vacío del selector de bancos. */
export const TEXTO_SIN_BANCOS = 'Marca tus bancos en Ajustes → Terceros.';
export const TEXTO_BANCO_SIN_MARCAR = 'Se ha creado, pero no se ha podido marcar como banco. Márcalo en Ajustes → Terceros.';
const PAUSA_MS = 300;

type Busqueda = { fase: 'INACTIVA' } | { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: Tercero[] };

export function SelectorTercero(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  titulo?: string;
  seleccionadoId: string | null;
  onElegir: (t: Tercero | null) => void;
  onCerrar: () => void;
  /** F05-05: tipo y fecha del registro para «Recientes» (sin ellos, no se muestran). */
  tipo?: 'GASTO' | 'INGRESO';
  fecha?: string;
  /**
   * F06 T6 · S7-A (DP-09, DT-04): solo bancos. Lista los terceros con el rol ENTIDAD_FINANCIERA (filtro del servidor),
   * sin «Sin tercero», recientes ni búsqueda en el servidor; «+ Crear banco «texto»» crea el tercero y lo marca con `marcar`
   * (rol ENTIDAD_FINANCIERA, ruta de roles de siempre). Sin ninguno: «Marca tus bancos en Ajustes → Terceros».
   */
  soloBancos?: { marcar: (t: Tercero) => Promise<boolean> };
}) {
  const { c } = useTema();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [filtro, setFiltro] = useState('');
  const [recientes, setRecientes] = useState<TerceroReciente[]>([]);
  const [busqueda, setBusqueda] = useState<Busqueda>({ fase: 'INACTIVA' });
  const peticionBusqueda = useRef(0);
  const [candidatos, setCandidatos] = useState<Tercero[] | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const idAlta = useRef<{ nombre: string; id: string } | null>(null);

  const cargar = async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.listarTerceros(p.soloBancos ? { rol: 'ENTIDAD_FINANCIERA' } : undefined);
    setCarga(r.tipo === 'OK' ? { fase: 'OK', lista: r.datos.terceros } : { fase: 'ERROR' });
  };
  useEffect(() => {
    void cargar();
  }, []);

  // F05-05: «Recientes» (señales) para el tipo y la fecha del registro.
  const cargarRecientes = async () => {
    if (!p.tipo || !p.fecha || p.soloBancos) return;
    const r = await p.cliente.senalesTerceros(p.tipo, p.fecha);
    setRecientes(r.tipo === 'OK' ? r.datos.terceros : []);
  };
  useEffect(() => {
    void cargarRecientes();
  }, [p.tipo, p.fecha]);

  const activos = useMemo(() => (carga.fase === 'OK' ? filtrar(carga.lista.filter((t) => t.enabled), filtro) : []), [carga, filtro]);
  const nombre = filtro.trim();
  const enServidor = !p.soloBancos && nombre.length >= MIN_BUSQUEDA;

  // F05-05: búsqueda en el servidor tras una pausa; una respuesta anterior se descarta.
  const buscar = async (texto: string) => {
    const n = ++peticionBusqueda.current;
    setBusqueda({ fase: 'CARGANDO' });
    const r = await p.cliente.buscarTerceros(texto, true);
    if (n !== peticionBusqueda.current) return;
    setBusqueda(r.tipo === 'OK' ? { fase: 'OK', lista: r.datos.terceros } : { fase: 'ERROR' });
  };
  useEffect(() => {
    if (!enServidor) {
      ++peticionBusqueda.current;
      setBusqueda({ fase: 'INACTIVA' });
      return undefined;
    }
    const t = setTimeout(() => void buscar(nombre), PAUSA_MS);
    return () => clearTimeout(t);
  }, [nombre, enServidor]);

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
    if (r.tipo === 'OK') {
      if (!p.soloBancos) return p.onElegir(r.datos.tercero);
      // S7-A: «+ Crear banco»: el tercero nace marcado; si el rol no se escribe, se dice y no se elige.
      setOcupado(true);
      const marcado = await p.soloBancos.marcar(r.datos.tercero);
      setOcupado(false);
      if (marcado) return p.onElegir(r.datos.tercero);
      void cargar();
      return setAviso(TEXTO_BANCO_SIN_MARCAR);
    }
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
    <PantallaSelector titulo={p.titulo ?? 'Tercero'} testID="selector-tercero" onCerrar={p.onCerrar} testIDCerrar="tercero-cerrar">
      <TextInput
        testID="tercero-filtro"
        accessibilityLabel={p.soloBancos ? 'Buscar o crear banco' : 'Buscar o crear tercero'}
        value={filtro}
        onChangeText={setFiltro}
        placeholder={p.soloBancos ? 'Buscar o crear banco' : 'Buscar o crear tercero'}
        placeholderTextColor={c.textSecondary}
        autoCorrect={false}
        style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
      />
      {carga.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
      {carga.fase === 'ERROR' ? (
        <Pressable testID="terceros-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
          <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
        </Pressable>
      ) : null}
      <ScrollView style={{ flex: 1 }} keyboardShouldPersistTaps="handled">
        {nombre === '' && recientes.length > 0 ? (
          <View testID="terceros-recientes">
            <Text style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>Recientes</Text>
            {recientes.map((t) => (
              <Pressable key={`r-${t.tercero_id}`} testID={`reciente-${t.tercero_id}`} accessibilityRole="button"
                accessibilityLabel={`${t.nombre}. ${textoReciente(t, p.fecha ?? t.ultimo_uso, p.tipo ?? 'GASTO')}`}
                onPress={() => p.onElegir({ id: t.tercero_id, nombre: t.nombre, naturaleza: (t.naturaleza as Tercero['naturaleza']) ?? null, enabled: true, row_version: 0 })}
                style={[s.fila, { borderColor: c.borderDefault }]}>
                <View style={{ flex: 1 }}>
                  <Text style={[tipo.body, { color: c.textPrimary }]}>{t.nombre}</Text>
                  <Text style={[tipo.caption, { color: c.textSecondary }]}>{textoReciente(t, p.fecha ?? t.ultimo_uso, p.tipo ?? 'GASTO')}</Text>
                </View>
                {p.seleccionadoId === t.tercero_id ? <Ionicons name="checkmark" size={18} color={c.accentText} /> : null}
              </Pressable>
            ))}
          </View>
        ) : null}
        {!enServidor ? (
          <>
            {p.soloBancos ? null : (
              <Pressable testID="tercero-ninguno" accessibilityRole="button" onPress={() => p.onElegir(null)} style={[s.fila, { borderColor: c.borderDefault }]}>
                <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>Sin tercero</Text>
                {p.seleccionadoId === null ? <Ionicons name="checkmark" size={18} color={c.accentText} /> : null}
              </Pressable>
            )}
            {p.soloBancos && carga.fase === 'OK' && carga.lista.filter((t) => t.enabled).length === 0 ? (
              <Text testID="bancos-vacio" style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>
                {`${TEXTO_SIN_BANCOS} También puedes escribir su nombre y crearlo aquí con «+ Crear banco».`}
              </Text>
            ) : null}
            {nombre === '' && carga.fase === 'OK' ? (
              <Text testID="terceros-todos" style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>
                {p.soloBancos ? `Tus bancos · ${activos.length}` : `Todos · ${activos.length} ${activos.length === 1 ? 'tercero' : 'terceros'}`}
              </Text>
            ) : null}
            {activos.map((t) => (
              <Pressable key={t.id} testID={`tercero-${t.id}`} accessibilityRole="button" accessibilityLabel={t.nombre} onPress={() => p.onElegir(t)}
                style={[s.fila, { borderColor: c.borderDefault }]}>
                <View style={{ flex: 1 }}>
                  <Text style={[tipo.body, { color: c.textPrimary }]}>{t.nombre}</Text>
                  {detalleTercero(t) ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{detalleTercero(t)}</Text> : null}
                </View>
                {p.seleccionadoId === t.id ? <Ionicons name="checkmark" size={18} color={c.accentText} /> : null}
              </Pressable>
            ))}
          </>
        ) : null}
        {enServidor && busqueda.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
        {enServidor && busqueda.fase === 'ERROR' ? (
          <Pressable testID="busqueda-terceros-error" accessibilityRole="button" onPress={() => void buscar(nombre)} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {enServidor && busqueda.fase === 'OK'
          ? busqueda.lista.map((t) =>
              t.enabled ? (
                <Pressable key={t.id} testID={`tercero-${t.id}`} accessibilityRole="button" accessibilityLabel={`${t.nombre}. ${detalleUso(t)}`}
                  onPress={() => p.onElegir(t)} style={[s.fila, { borderColor: c.borderDefault }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={[tipo.body, { color: c.textPrimary }]}>{t.nombre}</Text>
                    {detalleUso(t) ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{detalleUso(t)}</Text> : null}
                  </View>
                  {p.seleccionadoId === t.id ? <Ionicons name="checkmark" size={18} color={c.accentText} /> : null}
                </Pressable>
              ) : (
                <View key={t.id} testID={`tercero-inactivo-${t.id}`} style={[s.fila, { borderColor: c.borderDefault }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={[tipo.body, { color: c.textSecondary }]}>{t.nombre}</Text>
                    <Text style={[tipo.caption, { color: c.textSecondary }]}>{[detalleUso(t), 'Inactivo'].filter(Boolean).join(' · ')}</Text>
                  </View>
                  <BotonTexto testID={`reactivar-${t.id}`} titulo="Reactivar" onPress={() => void reactivar(t)} />
                </View>
              ),
            )
          : null}
        {enServidor && busqueda.fase === 'OK' && busqueda.lista.some((t) => !t.enabled) ? (
          <Text testID="texto-inactivo-busqueda" style={[tipo.caption, { color: c.textSecondary }]}>{TEXTO_INACTIVO_BUSQUEDA}</Text>
        ) : null}
        {nombre ? (
          <Pressable testID="tercero-crear" accessibilityRole="button" disabled={ocupado} onPress={() => void crear(false)} style={[s.fila, { borderColor: c.borderDefault }]}>
            <Ionicons name="add" size={18} color={c.accentText} />
            <Text style={[tipo.body, { color: c.accentText, flex: 1 }]}>{p.soloBancos ? `Crear banco «${nombre}»` : `Crear «${nombre}»`}</Text>
          </Pressable>
        ) : null}
      </ScrollView>
      {aviso ? <Aviso testID="tercero-aviso" texto={aviso} /> : null}
    </PantallaSelector>
  );
}

const s = StyleSheet.create({
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 8, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: espacio.xs },
  seccion: { paddingTop: espacio.m, paddingBottom: espacio.xs },
});
