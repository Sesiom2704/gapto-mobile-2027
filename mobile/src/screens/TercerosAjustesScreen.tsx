// ============================================================
// GAPTO MOBILE 2027
// Fichero: TercerosAjustesScreen.tsx
// Ruta: mobile/src/screens/TercerosAjustesScreen.tsx
// Descripción: Ajustes › Terceros (F05-03 J2 §2.5; F05 §46.3 A5, §46.4 R5; lámina REG-DYN / SET-TH / SET-CTX v0.1 S01, S02, P02). Lista con «Todos / Activos / Inactivos» y filtro LOCAL por nombre (normalización C06); fila nombre + naturaleza, «Inactivo» en los desactivados. Alta y edición (S02): Nombre y Naturaleza (Persona, Empresa, Organismo, Otro o «No lo sé»); «Los gastos ya registrados no cambian…». Antes del alta se consultan los posibles duplicados (P02: «Usar el existente», «Reactivar» o «Crear otro»; homónimos válidos, sin fusión). Desactivar / reactivar con row_version y sin borrado. VERSION_DESFASADA → recarga y aviso, sin reintento automático; INDETERMINADO → recarga; el alta reutiliza su UUID.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.5)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, NaturalezaTercero, Respuesta, ResultadoComandoTercero, Tercero } from '../api/cliente';
import { BotonPrimario, CabeceraNavegacion, Chip, EstadoDato, Segmentado } from '../components/Basicos';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef, FilaLista, Tarjeta } from '../components/Formulario';
import { TEXTO_DUPLICADO, TEXTO_INACTIVO } from '../components/SelectorTercero';
import { BotonSecundario } from '../components/SelectorCategorias';
import { detalleTercero, filtrar, NATURALEZAS } from '../domain/maestros';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';

export const TEXTO_S02 = 'Los gastos ya registrados no cambian: el tercero se muestra con su nombre actual.';
/** DERIVADO. */
export const TEXTO_DESACTIVADO = 'Desactivado: deja de ofrecerse al registrar. Lo ya registrado no cambia.';
/** DERIVADO. */
export const TEXTO_REACTIVADO = 'Reactivado: vuelve a ofrecerse al registrar.';
export const TEXTO_VERSION = 'Este tercero ha cambiado mientras lo editabas. Hemos cargado la versión actual. Revisa y guarda de nuevo.';
export const TEXTO_INDETERMINADO = 'No se ha podido confirmar el cambio. Revisa el estado actual antes de repetirlo.';
/** DERIVADO. */
export const TEXTO_VACIO = 'Aún no tienes terceros. Se crean al registrar o desde aquí.';

type Filtro = 'TODOS' | 'ACTIVOS' | 'INACTIVOS';
type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: Tercero[] };
type Vista = { v: 'LISTA' } | { v: 'NUEVO' } | { v: 'EDITAR'; id: string };
interface Form {
  nombre: string;
  naturaleza: NaturalezaTercero | null;
}

export function TercerosAjustesScreen(p: { cliente: ClienteApi; nuevoId: () => string; onAtras: () => void; onInmersiva: (x: boolean) => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [vista, setVista] = useState<Vista>({ v: 'LISTA' });
  const [filtro, setFiltro] = useState<Filtro>('TODOS');
  const [texto, setTexto] = useState('');
  const [form, setForm] = useState<Form>({ nombre: '', naturaleza: null });
  const [idAlta, setIdAlta] = useState<string | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [candidatos, setCandidatos] = useState<Tercero[] | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(
    async (silencioso = false): Promise<Tercero[] | null> => {
      if (!silencioso) setCarga({ fase: 'CARGANDO' });
      const r = await p.cliente.listarTerceros();
      if (r.tipo !== 'OK') {
        if (!silencioso) setCarga({ fase: 'ERROR' });
        return null;
      }
      setCarga({ fase: 'OK', lista: r.datos.terceros });
      return r.datos.terceros;
    },
    [p.cliente],
  );
  useEffect(() => {
    void cargar();
  }, [cargar]);
  useEffect(() => {
    p.onInmersiva(vista.v !== 'LISTA');
  }, [vista.v]);
  useEffect(() => () => p.onInmersiva(false), []);

  const lista = carga.fase === 'OK' ? carga.lista : [];
  const visibles = useMemo(() => {
    const base = lista.filter((t) => (filtro === 'TODOS' ? true : filtro === 'ACTIVOS' ? t.enabled : !t.enabled));
    return filtrar(base, texto).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es') || (a.id < b.id ? -1 : 1));
  }, [lista, filtro, texto]);
  const actual = vista.v === 'EDITAR' ? lista.find((t) => t.id === vista.id) ?? null : null;

  const abrirNuevo = () => {
    setForm({ nombre: '', naturaleza: null });
    setIdAlta(p.nuevoId()); // UUID sellado al abrir: el reintento usa el MISMO
    setAviso(null);
    setCandidatos(null);
    setVista({ v: 'NUEVO' });
  };
  const abrirEditar = (t: Tercero, a: AvisoCaja = null) => {
    setForm({ nombre: t.nombre, naturaleza: t.naturaleza });
    setAviso(a);
    setCandidatos(null);
    setVista({ v: 'EDITAR', id: t.id });
  };

  const tratar = async (r: Respuesta<ResultadoComandoTercero>, base: Tercero | null, ok: string | null) => {
    const l = await cargar(true);
    if (r.tipo === 'OK') {
      if (ok) return abrirEditar(r.datos.tercero, { tipo: 'OK', texto: ok });
      return setVista({ v: 'LISTA' });
    }
    if (r.tipo === 'INDETERMINADO') {
      if (!base && l?.some((t) => t.id === idAlta)) return setVista({ v: 'LISTA' });
      return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    }
    if (r.codigo === 'VERSION_DESFASADA' && base) {
      const x = l?.find((t) => t.id === base.id);
      if (x) setForm({ nombre: x.nombre, naturaleza: x.naturaleza });
      return setAviso({ tipo: 'AVISO', texto: TEXTO_VERSION });
    }
    if (r.codigo === 'TERCERO_NO_ENCONTRADO') return setVista({ v: 'LISTA' });
    setAviso({ tipo: 'AVISO', texto: r.mensaje || TEXTO_INDETERMINADO });
  };

  const guardar = async (forzar = false) => {
    const nombre = form.nombre.trim();
    if (ocupado || !nombre) return;
    setOcupado(true);
    setAviso(null);
    if (!actual && !forzar) {
      const cand = await p.cliente.candidatosTercero(nombre);
      if (cand.tipo === 'OK' && cand.datos.terceros.length > 0) {
        setOcupado(false);
        return setCandidatos(cand.datos.terceros);
      }
    }
    setCandidatos(null);
    const r = actual
      ? await p.cliente.editarTercero(actual.id, { row_version: actual.row_version, nombre, naturaleza: form.naturaleza })
      : await p.cliente.altaTercero({ id: idAlta!, nombre, naturaleza: form.naturaleza });
    await tratar(r, actual, null);
    setOcupado(false);
  };

  const cambiarEstado = async (t: Tercero, accion: 'DESACTIVAR' | 'REACTIVAR') => {
    if (ocupado) return;
    setOcupado(true);
    setAviso(null);
    const r = accion === 'DESACTIVAR' ? await p.cliente.desactivarTercero(t.id, t.row_version) : await p.cliente.reactivarTercero(t.id, t.row_version);
    await tratar(r, t, accion === 'DESACTIVAR' ? TEXTO_DESACTIVADO : TEXTO_REACTIVADO);
    setOcupado(false);
  };

  // ---------------------------------------------------------------- formulario (S02 / P02)
  if (vista.v !== 'LISTA') {
    const nombre = form.nombre.trim();
    return (
      <View testID="ajter-form" style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraTarea titulo={actual ? 'Editar tercero' : 'Nuevo tercero'} testIDCancelar="ajter-cancelar" onCancelar={() => setVista({ v: 'LISTA' })} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {aviso ? <Caja testID={aviso.tipo === 'OK' ? 'ajter-aviso-ok' : 'ajter-aviso'} aviso={aviso} /> : null}
          <Campo etiqueta="Nombre">
            <CampoTexto testID="ajter-nombre" etiqueta="Nombre" valor={form.nombre} maximo={120} onCambiar={(t) => { setForm({ ...form, nombre: t }); setCandidatos(null); }} />
          </Campo>
          <Campo etiqueta="Naturaleza">
            <View style={ef.chips}>
              {NATURALEZAS.map((n) => (
                <Chip key={n.etiqueta} testID={`ajter-nat-${n.valor ?? 'NS'}`} etiqueta={n.etiqueta} seleccionado={form.naturaleza === n.valor}
                  onPress={() => setForm({ ...form, naturaleza: n.valor })} />
              ))}
            </View>
          </Campo>
          {actual ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_S02}</Text> : null}
          {candidatos ? (
            <View testID="ajter-duplicado" style={{ gap: espacio.s }}>
              <Caja testID="ajter-duplicado-aviso" aviso={{ tipo: 'AVISO', texto: TEXTO_DUPLICADO }} />
              <Tarjeta>
                {candidatos.map((t, i) => (
                  <FilaLista key={t.id} testID={`ajter-candidato-${t.id}`} titulo={t.nombre} ultima={i === candidatos.length - 1}
                    detalle={t.enabled ? detalleTercero(t) : `Inactivo · ${TEXTO_INACTIVO}`} apagada={!t.enabled}
                    onPress={() => abrirEditar(t)} />
                ))}
              </Tarjeta>
              {candidatos.filter((t) => !t.enabled).slice(0, 1).map((t) => (
                <BotonPrimario key="r" testID="ajter-reactivar-candidato" titulo="Reactivar" cargando={ocupado} onPress={() => void cambiarEstado(t, 'REACTIVAR')} />
              ))}
              {candidatos.filter((t) => t.enabled).slice(0, 1).map((t) => (
                <BotonSecundario key="u" testID="ajter-usar-existente" titulo="Usar el existente" onPress={() => abrirEditar(t)} />
              ))}
              <BotonSecundario testID="ajter-crear-otro" titulo={`Crear otro «${nombre}»`} onPress={() => void guardar(true)} />
            </View>
          ) : (
            <BotonPrimario testID="ajter-guardar" titulo={ocupado ? 'Guardando…' : 'Guardar'} cargando={ocupado} deshabilitado={!nombre}
              ayuda={nombre ? undefined : 'Falta: nombre'} onPress={() => void guardar()} />
          )}
          {actual ? (
            actual.enabled ? (
              <BotonSecundario testID="ajter-desactivar" titulo="Desactivar" critico onPress={() => void cambiarEstado(actual, 'DESACTIVAR')} />
            ) : (
              <BotonSecundario testID="ajter-reactivar" titulo="Reactivar" onPress={() => void cambiarEstado(actual, 'REACTIVAR')} />
            )
          ) : null}
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- lista (S01)
  return (
    <View testID="pantalla-terceros" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion
        titulo="Terceros"
        atras={{ etiqueta: 'Ajustes', onPress: p.onAtras }}
        testIDAtras="ajter-atras"
        derecha={
          <Pressable testID="ajter-nuevo" accessibilityRole="button" accessibilityLabel="Nuevo tercero" hitSlop={8} onPress={abrirNuevo} style={ef.mas}>
            <Ionicons name="add" size={24} color={c.accent} />
          </Pressable>
        }
      />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        <Segmentado<Filtro>
          testIDBase="ajter-filtro"
          etiquetaGrupo="Mostrar"
          opciones={[
            { valor: 'TODOS', etiqueta: 'Todos' },
            { valor: 'ACTIVOS', etiqueta: 'Activos' },
            { valor: 'INACTIVOS', etiqueta: 'Inactivos' },
          ]}
          valor={filtro}
          onCambiar={setFiltro}
        />
        <CampoTexto testID="ajter-buscar" etiqueta="Filtrar por nombre" marcador="Filtrar por nombre" valor={texto} onCambiar={setTexto} />
        {carga.fase === 'CARGANDO' ? <EstadoDato testID="ajter-cargando" estado="CARGANDO" /> : null}
        {carga.fase === 'ERROR' ? (
          <Pressable testID="ajter-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {carga.fase === 'OK' && lista.length === 0 ? (
          <Text testID="ajter-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_VACIO}</Text>
        ) : null}
        {visibles.length > 0 ? (
          <Tarjeta testID="ajter-lista">
            {visibles.map((t, i) => (
              <FilaLista key={t.id} testID={`ajter-fila-${t.id}`} titulo={t.nombre} apagada={!t.enabled} ultima={i === visibles.length - 1}
                detalle={[t.naturaleza ? detalleTercero({ naturaleza: t.naturaleza }) : null, t.enabled ? null : 'Inactivo'].filter(Boolean).join(' · ')}
                onPress={() => abrirEditar(t)} />
            ))}
          </Tarjeta>
        ) : null}
      </ScrollView>
    </View>
  );
}
