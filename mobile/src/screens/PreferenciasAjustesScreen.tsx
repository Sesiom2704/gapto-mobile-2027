// ============================================================
// GAPTO MOBILE 2027
// Fichero: PreferenciasAjustesScreen.tsx
// Ruta: mobile/src/screens/PreferenciasAjustesScreen.tsx
// Descripción: Ajustes › Preferencias (F05-02 B3; F05-D026 §41.3; lámina SET-PREF / REG-PREF v0.1, sección B S01–S06 y variante oscura; D-PREF-01..06; AJ-B1-10; D-B3-01). Lista agrupada «Todos los gastos» / «Por categoría» / «Desactivadas» con lo que propone cada preferencia y la marca «No disponible» cuando el servidor dice que la cuenta preferida no es elegible hoy (D-PREF-04: solo aquí, nunca en el registro); estado vacío (S05). Nueva preferencia (S02): ámbitos «Todos los gastos» y «Una categoría» (D-PREF-01); el selector de categoría y la lista de cuentas son la MISMA fuente y componente que REG-01 (SelectorCategorias con visibleEnRegistro / elegibleParaGasto; GET /v1/vs01/cuentas-pago de hoy): sin regla de elegibilidad propia del cliente. «Guardar» desactivado si no se propone nada (espejo del CHECK; el servidor sigue siendo la guarda). Preferencia existente del mismo ámbito o PREFERENCIA_EMPATE_CONTRADICTORIO → S03 «Ir a la preferencia», nunca se crea otra. Detalle (S04) con desactivar / reactivar (el servidor comprueba el empate al reactivar) y sin borrado. Editar envía el ESTADO COMPLETO (E05) con `row_version`; VERSION_DESFASADA → recarga y aviso S06, sin reintento automático (patrón M16 de SET-MAG). INDETERMINADO → se recarga antes de repetir; el alta reutiliza su UUID. Los formularios y el selector son tareas inmersivas (ocultan la barra inferior).
// Versión: 0.1.0 (F05-02 B3)
// Versión: 0.2.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E3): las preferencias nuevas llevan SIEMPRE el tipo GASTO (`tipos.GASTO` de la lista); el ámbito «Todos los gastos» es el tipo GASTO sin categoría.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaPago, Preferencia, Respuesta, ResultadoComandoPreferencia, TiposRegistro } from '../api/cliente';
import { BotonPrimario, BotonTexto, CabeceraNavegacion, Chip, EstadoDato, Segmentado } from '../components/Basicos';
import { BotonSecundario, SelectorCategorias } from '../components/SelectorCategorias';
import { Arbol, ancestros, construirArbol, elegibleParaGasto, motivoNoSeleccionable, visibleEnRegistro } from '../domain/categoria';
import { isoLocal } from '../domain/fechas';
import {
  agruparPreferencias,
  ambitoDe,
  contenidoFormulario,
  cuentaNoDisponible,
  FaltaFormulario,
  faltaFormulario,
  FORMULARIO_NUEVO,
  FormularioPreferencia,
  formularioDesde,
  preferenciaDeAmbito,
  siNo,
  textosPropone,
  TITULO_GENERAL,
  TITULO_OTRO,
} from '../domain/preferencias';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

// ------------------------------------------------------------------ textos (lámina SET-PREF; DERIVADO = no está en la lámina)
export const TEXTO_INTRO = 'Gapto propone estos valores al registrar un gasto. Siempre puedes cambiarlos antes de guardar.';
export const TEXTO_PIE = 'Si una categoría tiene preferencia, gana a la general en lo que proponga.';
export const TEXTO_VACIO_TITULO = 'Sin preferencias';
export const TEXTO_VACIO =
  'Crea una para que Gapto te proponga la cuenta o si el gasto cuenta para el presupuesto. También puedes guardarla al registrar un gasto.';
export const TEXTO_CHECK = 'Tiene que proponer al menos una de las dos cosas.';
export const TEXTO_SOLO_NUEVOS = 'Solo afecta a gastos nuevos. Los ya registrados no cambian.';
export const TEXTO_DESACTIVADA =
  'Desactivada: deja de proponerse. Puedes reactivarla cuando quieras; si choca con otra que hayas creado después, te lo diremos.';
export const TEXTO_S06_TITULO = 'Esta preferencia ha cambiado mientras la editabas.';
export const TEXTO_S06 = 'Hemos cargado la versión actual. Revisa y guarda de nuevo.';
export const TEXTO_NO_DISPONIBLE = 'No disponible';
/** DERIVADO. */
export const TEXTO_REACTIVADA = 'Reactivada: vuelve a proponerse.';
/** DERIVADO (detalle: desactivar o reactivar con row_version desfasada). */
export const TEXTO_VERSION_DETALLE = 'Esta preferencia ha cambiado. Hemos cargado la versión actual; revísala antes de repetirlo.';
/** Mismo texto que Ajustes › Categorías (MSG_INDETERMINADO). */
export const TEXTO_INDETERMINADO = 'No se ha podido confirmar el cambio. Revisa el estado actual antes de repetirlo.';
/** DERIVADO. */
export const TEXTO_SIN_RECARGA = 'No se han podido cargar tus preferencias. Vuelve a intentarlo.';
/** DERIVADO: lo que falta para «Guardar» (el espejo del CHECK usa el texto de la lámina). */
export const TEXTO_FALTA: Record<Exclude<FaltaFormulario, 'PROPONER'>, string> = {
  AMBITO: 'Elige a qué gastos se aplica.',
  CATEGORIA: 'Elige la categoría.',
  CUENTA_NO_DISPONIBLE: 'La cuenta actual ya no está disponible: elige otra o «No proponer».',
};

type Carga =
  | { fase: 'CARGANDO' }
  | { fase: 'ERROR' }
  | { fase: 'OK'; prefs: Preferencia[]; tipos: TiposRegistro; cuentas: CuentaPago[]; arbol: Arbol };
type Datos = Extract<Carga, { fase: 'OK' }>;
type Vista = { v: 'LISTA' } | { v: 'DETALLE'; id: string } | { v: 'NUEVA' } | { v: 'EDITAR'; id: string };
type Aviso = { tipo: 'OK' | 'AVISO'; texto: string; irA?: string } | null;

export function PreferenciasAjustesScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  onAtras: () => void;
  onInmersiva: (inmersiva: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [vista, setVista] = useState<Vista>({ v: 'LISTA' });
  const [avisoDetalle, setAvisoDetalle] = useState<Aviso>(null);
  const [ocupado, setOcupado] = useState(false);
  // Formulario (S02 / S06)
  const [form, setForm] = useState<FormularioPreferencia>(FORMULARIO_NUEVO);
  const [idAlta, setIdAlta] = useState<string | null>(null);
  const [avisoForm, setAvisoForm] = useState<Aviso>(null);
  const [conflicto, setConflicto] = useState<Preferencia | null>(null);
  const [selector, setSelector] = useState(false);

  /** Lista, cuentas de REG-01 (hoy) y árbol. En silencio, un fallo conserva lo mostrado y devuelve null. */
  const cargar = useCallback(
    async (silencioso = false): Promise<Datos | null> => {
      if (!silencioso) setCarga({ fase: 'CARGANDO' });
      const [l, cu, a] = await Promise.all([
        p.cliente.listarPreferencias(),
        p.cliente.cuentasPago(isoLocal(p.ahora())),
        p.cliente.arbolCategorias(),
      ]);
      if (l.tipo !== 'OK' || cu.tipo !== 'OK' || a.tipo !== 'OK') {
        if (!silencioso) setCarga({ fase: 'ERROR' });
        return null;
      }
      const datos: Datos = {
        fase: 'OK',
        prefs: l.datos.preferencias,
        tipos: l.datos.tipos,
        cuentas: cu.datos.cuentas,
        arbol: construirArbol(a.datos.categorias),
      };
      setCarga(datos);
      return datos;
    },
    [p.cliente, p.ahora],
  );
  useEffect(() => {
    void cargar();
  }, [cargar]);

  const inmersiva = vista.v === 'NUEVA' || vista.v === 'EDITAR';
  useEffect(() => {
    p.onInmersiva(inmersiva);
  }, [inmersiva]);
  useEffect(() => () => p.onInmersiva(false), []);

  const datos = carga.fase === 'OK' ? carga : null;
  const prefs = datos?.prefs ?? [];
  const tipoGasto = datos?.tipos.GASTO ?? null;
  const ambito = (x: Preferencia) => ambitoDe(x, tipoGasto);
  const porId = (id: string) => prefs.find((x) => x.id === id) ?? null;

  // ---------------------------------------------------------------- nombres visibles
  const nombreCuenta = (id: string) => datos?.cuentas.find((x) => x.cuenta_id === id)?.nombre ?? null;
  const nodo = (id: string) => datos?.arbol.porId.get(id) ?? null;
  /** «Padre › Hija» (ruta completa sin «Todas»). */
  const rutaCategoria = (id: string) => {
    const n = nodo(id);
    return datos && n ? [...ancestros(datos.arbol, id), n].map((x) => x.nombre).join(' › ') : 'Categoría no disponible';
  };
  const rotulo = (x: Preferencia) => {
    const a = ambito(x);
    return a === 'CATEGORIA' ? rutaCategoria(x.categoria_id!) : a === 'GENERAL' ? TITULO_GENERAL : TITULO_OTRO;
  };
  /** Título del detalle (lámina S04: «Supermercado»). */
  const tituloDe = (x: Preferencia) => (ambito(x) === 'CATEGORIA' ? nodo(x.categoria_id!)?.nombre ?? rutaCategoria(x.categoria_id!) : rotulo(x));
  /** «para …» de los avisos S03 y de reactivar. */
  const paraDe = (x: Preferencia) => {
    const a = ambito(x);
    return a === 'CATEGORIA' ? tituloDe(x) : a === 'GENERAL' ? 'todos los gastos' : 'este tipo de gasto';
  };
  /** «que propone …» (lámina S03: «que propone Tarjeta BBVA»). */
  const proponeCorto = (x: Preferencia) =>
    [
      x.cuenta_default_id !== null ? nombreCuenta(x.cuenta_default_id) ?? 'una cuenta no disponible' : null,
      x.presupuestable_default !== null ? `presupuesto: ${siNo(x.presupuestable_default)}` : null,
    ]
      .filter(Boolean)
      .join(' y ');

  // ---------------------------------------------------------------- navegación
  const abrirNueva = () => {
    setForm(FORMULARIO_NUEVO);
    setIdAlta(p.nuevoId()); // UUID del alta sellado al abrir: el reintento usa el MISMO
    setAvisoForm(null);
    setConflicto(null);
    setVista({ v: 'NUEVA' });
  };
  const abrirEditar = (x: Preferencia) => {
    setForm(formularioDesde(x, datos?.cuentas ?? []));
    setAvisoForm(null);
    setConflicto(null);
    setVista({ v: 'EDITAR', id: x.id });
  };
  const abrirDetalle = (id: string, aviso: Aviso = null) => {
    setAvisoDetalle(aviso);
    setSelector(false);
    setVista({ v: 'DETALLE', id });
  };

  // Un detalle o una edición que deja de existir tras recargar vuelve a la lista (sin inventar estado).
  useEffect(() => {
    if (datos && (vista.v === 'DETALLE' || vista.v === 'EDITAR') && !porId(vista.id)) setVista({ v: 'LISTA' });
  }, [carga]);

  // ---------------------------------------------------------------- comandos
  const conflictoDe = (r: Respuesta<unknown>, d: Datos | null): Preferencia | null => {
    const id = r.tipo === 'RECHAZADO' ? r.detalle?.preferencia_conflicto_id : undefined;
    return typeof id === 'string' && d ? d.prefs.find((x) => x.id === id) ?? null : null;
  };

  const guardar = async () => {
    if (ocupado || vista.v === 'LISTA' || vista.v === 'DETALLE') return;
    const base = vista.v === 'EDITAR' ? porId(vista.id) : null;
    if (tipoGasto === null) return;
    const contenido = contenidoFormulario(form, base, tipoGasto);
    setOcupado(true);
    setAvisoForm(null);
    const r: Respuesta<ResultadoComandoPreferencia> = base
      ? await p.cliente.editarPreferencia(base.id, { row_version: base.row_version, ...contenido })
      : await p.cliente.altaPreferencia({ id: idAlta!, ...contenido });
    if (r.tipo === 'OK') {
      await cargar(true);
      setOcupado(false);
      return abrirDetalle(r.datos.preferencia.id);
    }
    const d = r.tipo === 'RECHAZADO' && r.codigo === 'AGREGADO_NO_ENCONTRADO' ? null : await cargar(true);
    setOcupado(false);
    if (r.tipo === 'INDETERMINADO') {
      if (!base && d?.prefs.some((x) => x.id === idAlta)) return abrirDetalle(idAlta!);
      return setAvisoForm({ tipo: 'AVISO', texto: d ? TEXTO_INDETERMINADO : TEXTO_SIN_RECARGA });
    }
    if (r.codigo === 'PREFERENCIA_EMPATE_CONTRADICTORIO') {
      const otra = conflictoDe(r, d);
      if (otra) return setConflicto(otra);
      return setAvisoForm({ tipo: 'AVISO', texto: r.mensaje || TEXTO_INDETERMINADO });
    }
    if (r.codigo === 'VERSION_DESFASADA' && base) {
      const actual = d?.prefs.find((x) => x.id === base.id);
      if (!d || !actual) return setAvisoForm({ tipo: 'AVISO', texto: TEXTO_SIN_RECARGA });
      setForm(formularioDesde(actual, d.cuentas)); // S06: la versión actual, sin reintento automático
      return setAvisoForm({ tipo: 'AVISO', texto: `${TEXTO_S06_TITULO} ${TEXTO_S06}` });
    }
    if (r.codigo === 'AGREGADO_NO_ENCONTRADO') {
      await cargar(true);
      return setVista({ v: 'LISTA' });
    }
    setAvisoForm({ tipo: 'AVISO', texto: r.mensaje || TEXTO_INDETERMINADO });
  };

  const accionDetalle = async (x: Preferencia, accion: 'DESACTIVAR' | 'REACTIVAR') => {
    if (ocupado) return;
    setOcupado(true);
    setAvisoDetalle(null);
    const r =
      accion === 'DESACTIVAR'
        ? await p.cliente.desactivarPreferencia(x.id, x.row_version)
        : await p.cliente.reactivarPreferencia(x.id, x.row_version);
    const d = await cargar(true);
    setOcupado(false);
    if (r.tipo === 'OK') return setAvisoDetalle({ tipo: 'OK', texto: accion === 'DESACTIVAR' ? TEXTO_DESACTIVADA : TEXTO_REACTIVADA });
    if (!d) return setAvisoDetalle({ tipo: 'AVISO', texto: TEXTO_SIN_RECARGA });
    if (r.tipo === 'INDETERMINADO') return setAvisoDetalle({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    if (r.codigo === 'VERSION_DESFASADA') return setAvisoDetalle({ tipo: 'AVISO', texto: TEXTO_VERSION_DETALLE });
    if (r.codigo === 'PREFERENCIA_EMPATE_CONTRADICTORIO') {
      const otra = conflictoDe(r, d);
      if (otra) {
        return setAvisoDetalle({
          tipo: 'AVISO',
          texto: `No se puede reactivar: choca con la preferencia para ${paraDe(otra)} que propone ${proponeCorto(otra)}.`, // DERIVADO
          irA: otra.id,
        });
      }
    }
    setAvisoDetalle({ tipo: 'AVISO', texto: r.mensaje || TEXTO_INDETERMINADO });
  };

  // ---------------------------------------------------------------- render
  if (vista.v === 'NUEVA' || vista.v === 'EDITAR') {
    const base = vista.v === 'EDITAR' ? porId(vista.id) : null;
    const faltas = faltaFormulario(form);
    // S03: ya hay una preferencia habilitada del mismo ámbito → se edita esa, nunca se crea otra.
    const existente =
      conflicto ??
      (vista.v === 'NUEVA' && datos && (form.ambito === 'GENERAL' || (form.ambito === 'CATEGORIA' && form.categoriaId !== null))
        ? preferenciaDeAmbito(datos.prefs, form.ambito === 'GENERAL' ? null : form.categoriaId, datos.tipos.GASTO)
        : null);
    const puede = faltas.length === 0 && existente === null && !ocupado;
    const cuentaActual = form.cuenta !== null && typeof form.cuenta === 'object' ? form.cuenta.noDisponible : null;
    const titulo = base ? tituloDe(base) : 'Nueva preferencia';
    const cambiar = (parche: Partial<FormularioPreferencia>) => {
      setForm((f) => ({ ...f, ...parche }));
      setConflicto(null);
    };
    return (
      <View testID="ajpref-form" style={{ flex: 1, backgroundColor: c.background }}>
        <View style={[s.cabTarea, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
          <BotonTexto
            testID="ajpref-form-cancelar"
            titulo="Cancelar"
            onPress={() => (base ? abrirDetalle(base.id) : setVista({ v: 'LISTA' }))}
          />
          <Text accessibilityRole="header" numberOfLines={1} style={[tipo.titleSmall, { color: c.textPrimary, flexShrink: 1 }]}>
            {titulo}
          </Text>
          <View style={{ width: 72 }} />
        </View>
        <ScrollView contentContainerStyle={[s.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {avisoForm ? <Caja testID="ajpref-form-aviso" aviso={avisoForm} /> : null}

          {base ? (
            <Campo etiqueta="Se aplica a">
              <Text testID="ajpref-form-ambito-fijo" style={[tipo.body, { color: c.textPrimary }]}>
                {ambito(base) === 'CATEGORIA' ? rutaCategoria(base.categoria_id!) : ambito(base) === 'GENERAL' ? 'Todos los gastos' : TITULO_OTRO}
              </Text>
            </Campo>
          ) : (
            <>
              <Campo etiqueta="Se aplica a">
                <Segmentado<'GENERAL' | 'CATEGORIA'>
                  testIDBase="ajpref-ambito"
                  etiquetaGrupo="Se aplica a"
                  opciones={[
                    { valor: 'GENERAL', etiqueta: 'Todos los gastos' },
                    { valor: 'CATEGORIA', etiqueta: 'Una categoría' },
                  ]}
                  valor={form.ambito}
                  onCambiar={(v) => cambiar({ ambito: v, categoriaId: v === 'GENERAL' ? null : form.categoriaId })}
                />
              </Campo>
              {form.ambito === 'CATEGORIA' ? (
                <Campo etiqueta="Categoría">
                  <Pressable
                    testID="ajpref-form-categoria"
                    accessibilityRole="button"
                    accessibilityLabel={`Categoría: ${form.categoriaId ? rutaCategoria(form.categoriaId) : 'Elige categoría'}`}
                    accessibilityHint="Abre el selector de categorías"
                    onPress={() => setSelector(true)}
                    style={[s.campoCategoria, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
                  >
                    <Text style={[tipo.body, { flex: 1, color: form.categoriaId ? c.textPrimary : c.textSecondary }]}>
                      {form.categoriaId ? rutaCategoria(form.categoriaId) : 'Elige categoría'}
                    </Text>
                    <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
                  </Pressable>
                </Campo>
              ) : null}
            </>
          )}

          <Campo etiqueta="Proponer cuenta">
            <View style={s.chips}>
              <Chip testID="ajpref-cuenta-no" etiqueta="No proponer" seleccionado={form.cuenta === null} onPress={() => cambiar({ cuenta: null })} />
              {cuentaActual !== null ? (
                <Chip
                  testID="ajpref-cuenta-actual"
                  etiqueta={`${nombreCuenta(cuentaActual) ?? 'Cuenta actual'} · ${TEXTO_NO_DISPONIBLE}`}
                  seleccionado
                  onPress={() => undefined}
                />
              ) : null}
              {(datos?.cuentas ?? []).map((x) => (
                <Chip
                  key={x.cuenta_id}
                  testID={`ajpref-cuenta-${x.cuenta_id}`}
                  etiqueta={x.nombre}
                  seleccionado={form.cuenta === x.cuenta_id}
                  onPress={() => cambiar({ cuenta: x.cuenta_id })}
                />
              ))}
            </View>
          </Campo>

          <Campo etiqueta="Proponer «¿Cuenta para el presupuesto?»">
            <View style={s.chips}>
              <Chip testID="ajpref-presu-no-proponer" etiqueta="No proponer" seleccionado={form.presupuestable === null} onPress={() => cambiar({ presupuestable: null })} />
              <Chip testID="ajpref-presu-true" etiqueta="Sí" seleccionado={form.presupuestable === true} onPress={() => cambiar({ presupuestable: true })} />
              <Chip testID="ajpref-presu-false" etiqueta="No" seleccionado={form.presupuestable === false} onPress={() => cambiar({ presupuestable: false })} />
            </View>
          </Campo>

          <Text testID="ajpref-check" style={[tipo.footnote, { color: faltas.includes('PROPONER') ? c.textPrimary : c.textSecondary }]}>
            {TEXTO_CHECK}
          </Text>
          {faltas.filter((x): x is Exclude<FaltaFormulario, 'PROPONER'> => x !== 'PROPONER').map((x) => (
            <Text key={x} testID={`ajpref-falta-${x}`} style={[tipo.footnote, { color: c.textSecondary }]}>
              {TEXTO_FALTA[x]}
            </Text>
          ))}

          {existente ? (
            <>
              <View testID="ajpref-existente" accessibilityRole="alert" style={[s.caja, { backgroundColor: c.partialSurface, borderColor: c.warning }]}>
                <Text style={[tipo.footnote, { color: c.textPrimary }]}>
                  <Text style={{ fontWeight: '600', color: c.warning }}>{`Ya existe una preferencia para ${paraDe(existente)}`}</Text>
                  {` que propone ${proponeCorto(existente)}. Edítala en lugar de crear otra.`}
                </Text>
              </View>
              <BotonSecundario testID="ajpref-ir" titulo="Ir a la preferencia" onPress={() => abrirDetalle(existente.id)} />
            </>
          ) : (
            <BotonPrimario
              testID="ajpref-guardar"
              titulo={ocupado ? 'Guardando…' : 'Guardar'}
              cargando={ocupado}
              deshabilitado={!puede}
              ayuda={puede ? undefined : faltas.includes('PROPONER') ? TEXTO_CHECK : undefined}
              onPress={() => void guardar()}
            />
          )}
        </ScrollView>

        {selector && datos ? (
          <SelectorCategorias
            testID="ajpref-selector"
            titulo="Elegir categoría"
            modo="REGISTRO"
            carga={{ fase: 'OK', arbol: datos.arbol }}
            esVisible={(n) => visibleEnRegistro(datos.arbol, n)}
            esSeleccionable={elegibleParaGasto}
            motivo={(n) => motivoNoSeleccionable(n)}
            seleccionadaId={form.categoriaId}
            onElegir={(n) => {
              setSelector(false);
              cambiar({ categoriaId: n.id });
            }}
            onCerrar={() => setSelector(false)}
          />
        ) : null}
      </View>
    );
  }

  if (vista.v === 'DETALLE') {
    const x = porId(vista.id);
    if (!x) return null; // el efecto de recarga vuelve a la lista
    const ambitoX = ambito(x);
    const nombre = x.cuenta_default_id !== null ? nombreCuenta(x.cuenta_default_id) : null;
    return (
      <View testID="ajpref-detalle" style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraNavegacion
          titulo={tituloDe(x)}
          atras={{ etiqueta: 'Preferencias', onPress: () => setVista({ v: 'LISTA' }) }}
          testIDAtras="ajpref-detalle-atras"
          derecha={<BotonTexto testID="ajpref-editar" titulo="Editar" onPress={() => abrirEditar(x)} />}
        />
        <ScrollView contentContainerStyle={[s.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault }]}>
            <FilaDato testID="ajpref-det-ambito" etiqueta="Se aplica a"
              valor={ambitoX === 'CATEGORIA' ? rutaCategoria(x.categoria_id!) : ambitoX === 'GENERAL' ? 'Todos los gastos' : TITULO_OTRO} />
            <FilaDato
              testID="ajpref-det-cuenta"
              etiqueta="Cuenta"
              valor={x.cuenta_default_id === null ? 'No propone' : nombre ?? 'Cuenta no disponible'}
              apagado={x.cuenta_default_id === null}
              noDisponible={x.cuenta_default_id !== null && cuentaNoDisponible(x)}
            />
            <FilaDato testID="ajpref-det-presupuesto" etiqueta="Presupuesto"
              valor={x.presupuestable_default === null ? 'No propone' : siNo(x.presupuestable_default)} apagado={x.presupuestable_default === null} />
            {!x.enabled ? <FilaDato testID="ajpref-det-estado" etiqueta="Estado" valor="Desactivada" ultimo /> : null}
          </View>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SOLO_NUEVOS}</Text>
          {x.enabled ? (
            <BotonSecundario testID="ajpref-desactivar" titulo="Desactivar" critico onPress={() => void accionDetalle(x, 'DESACTIVAR')} />
          ) : (
            <BotonSecundario testID="ajpref-reactivar" titulo="Reactivar" onPress={() => void accionDetalle(x, 'REACTIVAR')} />
          )}
          {avisoDetalle ? <Caja testID={avisoDetalle.tipo === 'OK' ? 'ajpref-aviso-ok' : 'ajpref-aviso'} aviso={avisoDetalle} /> : null}
          {avisoDetalle?.irA ? (
            <BotonSecundario testID="ajpref-aviso-ir" titulo="Ir a la preferencia" onPress={() => abrirDetalle(avisoDetalle.irA!)} />
          ) : null}
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- LISTA (S01 / S05)
  const grupos = datos ? agruparPreferencias(datos.prefs, rotulo, datos.tipos.GASTO) : null;
  return (
    <View testID="pantalla-preferencias" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion
        titulo="Preferencias"
        atras={{ etiqueta: 'Ajustes', onPress: p.onAtras }}
        testIDAtras="ajpref-atras"
        derecha={
          <Pressable testID="ajpref-nueva" accessibilityRole="button" accessibilityLabel="Nueva preferencia" hitSlop={8} onPress={abrirNueva} style={s.mas}>
            <Ionicons name="add" size={24} color={c.accent} />
          </Pressable>
        }
      />
      <ScrollView contentContainerStyle={[s.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {carga.fase === 'CARGANDO' ? <EstadoDato testID="ajpref-cargando" estado="CARGANDO" /> : null}
        {carga.fase === 'ERROR' ? (
          <Pressable testID="ajpref-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {grupos && datos && datos.prefs.length === 0 ? (
          <View testID="ajpref-vacio" style={[s.tarjeta, s.vacio, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault }]}>
            <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{TEXTO_VACIO_TITULO}</Text>
            <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>{TEXTO_VACIO}</Text>
            <BotonPrimario testID="ajpref-vacio-nueva" titulo="Nueva preferencia" onPress={abrirNueva} />
          </View>
        ) : null}
        {grupos && datos && datos.prefs.length > 0 ? (
          <>
            <Text testID="ajpref-intro" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_INTRO}</Text>
            {(
              [
                ['todos', 'Todos los gastos', grupos.todos],
                ['categoria', 'Por categoría', grupos.categoria],
                ['desactivadas', 'Desactivadas', grupos.desactivadas],
              ] as const
            ).map(([clave, titulo, lista]) =>
              lista.length === 0 ? null : (
                <View key={clave} testID={`ajpref-grupo-${clave}`} style={{ gap: espacio.s }}>
                  <Text accessibilityRole="header" style={[tipo.caption, s.seccion, { color: c.textSecondary }]}>{titulo.toUpperCase()}</Text>
                  <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault }]}>
                    {lista.map((x, i) => (
                      <FilaPreferencia
                        key={x.id}
                        id={x.id}
                        titulo={rotulo(x)}
                        propone={textosPropone(x, nombreCuenta).join(' · ')}
                        noDisponible={x.cuenta_default_id !== null && cuentaNoDisponible(x)}
                        desactivada={!x.enabled}
                        ultima={i === lista.length - 1}
                        onPress={() => abrirDetalle(x.id)}
                      />
                    ))}
                  </View>
                </View>
              ),
            )}
            <Text testID="ajpref-pie" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_PIE}</Text>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

// ------------------------------------------------------------------ piezas
function Campo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  const { c } = useTema();
  return (
    <View style={{ gap: espacio.s }}>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{etiqueta}</Text>
      {children}
    </View>
  );
}

function EtiquetaNoDisponible({ testID }: { testID?: string }) {
  const { c } = useTema();
  return (
    <View testID={testID} style={[s.etiqueta, { backgroundColor: c.partialSurface, borderColor: c.warning }]}>
      <Text style={[tipo.caption, { color: c.warning }]}>{TEXTO_NO_DISPONIBLE}</Text>
    </View>
  );
}

function FilaPreferencia(p: {
  id: string;
  titulo: string;
  propone: string;
  noDisponible: boolean;
  desactivada: boolean;
  ultima: boolean;
  onPress: () => void;
}) {
  const { c } = useTema();
  return (
    <Pressable
      testID={`ajpref-fila-${p.id}`}
      accessibilityRole="button"
      accessibilityLabel={[p.titulo, p.propone, p.noDisponible ? TEXTO_NO_DISPONIBLE : null, p.desactivada ? 'Desactivada' : null].filter(Boolean).join('. ')}
      onPress={p.onPress}
      style={({ pressed }) => [s.fila, !p.ultima && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }, { opacity: pressed ? 0.7 : 1 }]}
    >
      <View style={{ flex: 1, gap: 2 }}>
        <Text testID={`ajpref-fila-${p.id}-titulo`} style={[tipo.body, { color: p.desactivada ? c.textSecondary : c.textPrimary }]}>{p.titulo}</Text>
        <View style={s.filaPropone}>
          <Text testID={`ajpref-fila-${p.id}-propone`} style={[tipo.caption, { color: c.textSecondary }]}>{p.propone}</Text>
          {p.noDisponible ? <EtiquetaNoDisponible testID={`ajpref-fila-${p.id}-no-disponible`} /> : null}
        </View>
      </View>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

function FilaDato(p: { testID: string; etiqueta: string; valor: string; apagado?: boolean; noDisponible?: boolean; ultimo?: boolean }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={[s.fila, !p.ultimo && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
      <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{p.etiqueta}</Text>
      <View style={[s.filaPropone, { justifyContent: 'flex-end', flexShrink: 1 }]}>
        <Text testID={`${p.testID}-valor`} style={[tipo.subheadline, { color: p.apagado ? c.textSecondary : c.textPrimary, textAlign: 'right', flexShrink: 1 }]}>
          {p.valor}
        </Text>
        {p.noDisponible ? <EtiquetaNoDisponible testID={`${p.testID}-no-disponible`} /> : null}
      </View>
    </View>
  );
}

function Caja({ aviso, testID }: { aviso: NonNullable<Aviso>; testID: string }) {
  const { c } = useTema();
  const ok = aviso.tipo === 'OK';
  return (
    <View
      testID={testID}
      accessibilityRole={ok ? undefined : 'alert'}
      accessibilityLiveRegion="polite"
      style={[s.caja, { backgroundColor: ok ? c.accentSurface : c.partialSurface, borderColor: ok ? c.accent : c.warning }]}
    >
      <Text style={[tipo.footnote, { color: c.textPrimary }]}>{aviso.texto}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  cabTarea: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth, gap: espacio.s },
  cuerpo: { padding: espacio.l, gap: espacio.l },
  mas: { minHeight: TACTIL_MIN, minWidth: TACTIL_MIN, alignItems: 'flex-end', justifyContent: 'center' },
  seccion: { letterSpacing: 0.6, paddingHorizontal: espacio.xs },
  tarjeta: { borderRadius: radio.m, borderWidth: 1 },
  vacio: { alignItems: 'center', gap: espacio.s, padding: espacio.l },
  fila: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.s, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.m, paddingVertical: espacio.s },
  filaPropone: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: espacio.s },
  etiqueta: { borderRadius: radio.pill, borderWidth: 1, paddingHorizontal: espacio.s, paddingVertical: 1 },
  caja: { borderRadius: radio.m, borderWidth: 1, padding: espacio.m },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  campoCategoria: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 8 },
});
