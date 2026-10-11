// ============================================================
// GAPTO MOBILE 2027
// Fichero: SelectorCategorias.tsx
// Ruta: mobile/src/components/SelectorCategorias.tsx
// Descripción: Selector jerárquico de categorías, componente del Design System (F09 §12.97.2; lámina REG-CAT v1.0 R02–R05, R08, R09). Hoja de altura completa con cabecera «Elegir categoría · Cerrar», navegación por niveles y migas («Todas › Alimentación»), opción fija de la raíz («Sin categoría» en el registro; «Raíz» al elegir ubicación en Ajustes). Tocar un nodo con hijos visibles entra en él; si ese nodo es seleccionable, el nivel hijo muestra arriba «Usar “<nombre>”»; una hoja seleccionable se elige al tocarla. Un nodo no seleccionable muestra su motivo en texto y, si tiene descendientes visibles, sigue siendo navegable. La selección vigente se marca con check Y texto («Elegida»), nunca solo con color. Estado vacío «Aún no tienes categorías». Error de carga «No hemos podido cargar tus categorías · Reintentar», separado de la acción deliberada «Continuar sin categoría»: un fallo técnico nunca selecciona nada (AJ-09). Sin alta contextual. Reutilizable: `modo` REGISTRO filtra por visibilidad en el registro; AJUSTES muestra lo que decida el llamador. Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// Versión: 0.2.0 (F05-01 S6-WIRE+UI, correctivo AJ-S6WIREUI-09): el aviso del nivel no seleccionable y el subtítulo de fila solo afirman que las subcategorías se pueden usar si existe algún descendiente elegible (`tieneDescendienteElegible`, naturaleza GASTO del slice); si no, «Puedes entrar para ver sus subcategorías.» y «tiene subcategorías».
// Versión: 0.3.0 (F05-01 P7 · N3, Moisés D-P7-05, microcopy AJ-S6WIREUI-09): solo las ramas con usables = false. Aviso de nivel «… Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría.» (motivo «Desactivada» y resto de motivos) y subtítulo de fila «sus subcategorías tampoco se pueden usar». Ramas usables = true y lógica `usables` sin cambios.
// Versión: 0.4.0 (F05-03/F05-04 J2 §2.3/§2.5): prop opcional `naturaleza` (GASTO por defecto: el comportamiento anterior) para el registro y los ajustes de ingresos; `usables` la usa en lugar de GASTO fijo. Sin imports nuevos.
// Versión: 0.5.0 (F05-05 K3 §2.1; F05 §49.4 A1/A2/A3, D-SRCH-01..03; lámina SRCH-ACT-AFI A1, A2, A6, C2): sección «Sugeridas» (prop opcional `sugeridas`, hasta 3, con ruta y motivo) encima del árbol en la raíz; tocar una sugerida invoca el MISMO `onElegir` que el árbol (R1: misma intención) y solo se muestra si el nodo existe y es seleccionable (nada preseleccionado, C01). Búsqueda opcional (`buscar`) sobre todo el árbol con la normalización C06 (`normalizarNombre`: sin mayúsculas ni acentos): resultados con ruta en el orden del árbol (sin reordenar, I13c); lo no seleccionable se ve atenuado con su motivo y no se puede elegir. Imports nuevos declarados en I13a: TextInput, normalizarNombre y el tipo SugeridaCategoria.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Arbol, CategoriaNodo, ancestros, hijosDe, tieneDescendienteElegible } from '../domain/categoria';
import { normalizarNombre } from '../domain/maestros';
import type { SugeridaCategoria } from '../domain/senales';
import { glifoDe } from '../theme/iconosCategoria';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto } from './Basicos';

export type CargaArbol = { fase: 'CARGANDO' } | { fase: 'OK'; arbol: Arbol } | { fase: 'ERROR' };

export interface OpcionRaiz {
  etiqueta: string;
  subtitulo: string;
  seleccionada: boolean;
  onPress: () => void;
  testID: string;
}

/** Hueco de icono reservado (F09 §12.97.5): glifo de la clave o de reserva, sin color de estado. */
export function IconoCategoriaVista({ iconKey, tamano = 18, testID }: { iconKey: string | null | undefined; tamano?: number; testID?: string }) {
  const { c } = useTema();
  return (
    <View testID={testID} style={[s.hueco, { backgroundColor: c.surfaceSecondary }]} accessibilityElementsHidden importantForAccessibility="no">
      <Ionicons name={glifoDe(iconKey)} size={tamano} color={c.textSecondary} />
    </View>
  );
}

export function SelectorCategorias(p: {
  titulo: string;
  modo: 'REGISTRO' | 'AJUSTES';
  carga: CargaArbol;
  /** Nodos que se listan (en REGISTRO: visibles en el registro). */
  esVisible: (n: CategoriaNodo) => boolean;
  /** Nodos que se pueden elegir. */
  esSeleccionable: (n: CategoriaNodo) => boolean;
  /** Motivo en texto de un nodo no seleccionable (null = ninguno). */
  motivo: (n: CategoriaNodo) => string | null;
  seleccionadaId: string | null;
  opcionRaiz?: OpcionRaiz;
  onElegir: (n: CategoriaNodo) => void;
  onCerrar: () => void;
  onReintentar?: () => void;
  /** Solo REGISTRO: acción deliberada separada del error de carga. */
  onContinuarSinCategoria?: () => void;
  /** Naturaleza del registro (GASTO por defecto). */
  naturaleza?: 'GASTO' | 'INGRESO';
  /** F05-05 A1: hasta 3 sugeridas con ruta y motivo (nunca preseleccionan). */
  sugeridas?: SugeridaCategoria[];
  /** F05-05 A2/A3: campo de búsqueda sobre todo el árbol (C06). */
  buscar?: boolean;
  testID?: string;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [nivel, setNivel] = useState<string | null>(null);
  const [texto, setTexto] = useState('');
  const arbol = p.carga.fase === 'OK' ? p.carga.arbol : null;

  const visiblesDe = (padre: string | null) => (arbol ? hijosDe(arbol, padre).filter(p.esVisible) : []);
  const filas = useMemo(() => visiblesDe(nivel), [arbol, nivel, p.esVisible]);
  const actual = arbol && nivel ? arbol.porId.get(nivel) ?? null : null;
  const migas = arbol && actual ? [...ancestros(arbol, actual.id), actual] : [];
  // AJ-S6WIREUI-09: naturaleza del registro (GASTO salvo que el llamador diga INGRESO; F05-04).
  const usables = (n: CategoriaNodo) => !!arbol && tieneDescendienteElegible(arbol, n, p.naturaleza ?? 'GASTO');

  // F05-05 A2: coincidencias en el orden del árbol (recorrido en preorden; sin reordenar).
  const consulta = p.buscar ? normalizarNombre(texto) : '';
  const coincidencias = useMemo(() => {
    if (!arbol || consulta === '') return [];
    const out: CategoriaNodo[] = [];
    const visitar = (padre: string | null) => {
      for (const n of hijosDe(arbol, padre).filter(p.esVisible)) {
        if (normalizarNombre(n.nombre).includes(consulta)) out.push(n);
        visitar(n.id);
      }
    };
    visitar(null);
    return out;
  }, [arbol, consulta, p.esVisible]);
  // F05-05 A1: solo las sugeridas que existen en el árbol y se pueden elegir.
  const sugeridas = (p.sugeridas ?? [])
    .map((x) => ({ x, n: arbol?.porId.get(x.categoria_id) }))
    .filter((y): y is { x: SugeridaCategoria; n: CategoriaNodo } => !!y.n && p.esSeleccionable(y.n));

  const tocar = (n: CategoriaNodo) => {
    if (visiblesDe(n.id).length > 0) return setNivel(n.id);
    if (p.esSeleccionable(n)) p.onElegir(n);
  };

  return (
    <View testID={p.testID ?? 'selector-categorias'} style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <View style={{ width: 72 }} />
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{p.titulo}</Text>
        <BotonTexto testID="selector-cerrar" titulo="Cerrar" onPress={p.onCerrar} />
      </View>

      {p.carga.fase === 'ERROR' ? (
        <View testID="selector-error" style={[s.cuerpo, { flex: 1, justifyContent: 'space-between', paddingBottom: inset.bottom + espacio.l }]}>
          <View style={{ gap: espacio.m }}>
            <View accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
              <Ionicons name="alert-circle-outline" size={18} color={c.warning} />
              <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>No hemos podido cargar tus categorías.</Text>
            </View>
            {p.onReintentar ? <BotonSecundario testID="selector-reintentar" titulo="Reintentar" onPress={p.onReintentar} /> : null}
          </View>
          {p.onContinuarSinCategoria ? (
            <View style={{ gap: espacio.s }}>
              <Text style={[tipo.footnote, { color: c.textSecondary }]}>Si prefieres no clasificarlo ahora:</Text>
              <BotonSecundario testID="selector-continuar-sin" titulo="Continuar sin categoría" onPress={p.onContinuarSinCategoria} />
            </View>
          ) : null}
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ paddingBottom: inset.bottom + espacio.xl }} keyboardShouldPersistTaps="handled">
          {p.buscar && nivel === null ? (
            <View style={s.buscador}>
              <TextInput
                testID="selector-busqueda"
                accessibilityLabel="Buscar categoría"
                value={texto}
                onChangeText={setTexto}
                placeholder="Buscar categoría"
                placeholderTextColor={c.textSecondary}
                autoCorrect={false}
                style={[tipo.body, s.campoBusqueda, { color: c.textPrimary, backgroundColor: c.surfaceSecondary }]}
              />
              {texto ? <BotonTexto testID="selector-busqueda-limpiar" titulo="Borrar" onPress={() => setTexto('')} /> : null}
            </View>
          ) : null}

          {consulta !== '' ? (
            <View testID="selector-resultados">
              <Text style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>
                {coincidencias.length === 1 ? '1 resultado' : `${coincidencias.length} resultados`}
              </Text>
              {coincidencias.map((n) => {
                const sel = p.esSeleccionable(n);
                const mot = sel ? null : p.motivo(n);
                return (
                  <FilaSelector
                    key={n.id}
                    testID={`resultado-${n.id}`}
                    iconKey={n.icon_key}
                    titulo={n.nombre}
                    subtitulo={[arbol ? [...ancestros(arbol, n.id), n].map((m) => m.nombre).join(' › ') : null, mot].filter(Boolean).join(' · ')}
                    apagada={!sel}
                    elegida={p.seleccionadaId === n.id}
                    deshabilitada={!sel}
                    onPress={() => p.onElegir(n)}
                  />
                );
              })}
              <Text testID="selector-busqueda-nota" style={[tipo.caption, s.seccion, { color: c.textSecondary }]}>
                Sin distinguir mayúsculas ni acentos.
              </Text>
            </View>
          ) : null}

          {consulta === '' && nivel === null && p.carga.fase === 'OK' && sugeridas.length > 0 ? (
            <View testID="selector-sugeridas">
              <Text style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>Sugeridas</Text>
              {sugeridas.map(({ x, n }) => (
                <FilaSelector
                  key={`s-${n.id}`}
                  testID={`sugerida-${n.id}`}
                  iconKey={n.icon_key}
                  titulo={n.nombre}
                  subtitulo={x.ruta}
                  detalle={x.motivo}
                  elegida={p.seleccionadaId === n.id}
                  onPress={() => p.onElegir(n)}
                />
              ))}
              <Text style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>Todas</Text>
            </View>
          ) : null}

          {consulta === '' ? (
          <>
          {nivel === null && p.opcionRaiz ? (
            <FilaSelector
              testID={p.opcionRaiz.testID}
              iconKey={null}
              titulo={p.opcionRaiz.etiqueta}
              subtitulo={p.opcionRaiz.subtitulo}
              elegida={p.opcionRaiz.seleccionada}
              onPress={p.opcionRaiz.onPress}
            />
          ) : null}

          {nivel !== null ? (
            <View testID="selector-migas" style={[s.migas, { borderBottomColor: c.separator }]}>
              <Pressable testID="selector-miga-todas" accessibilityRole="link" onPress={() => setNivel(null)} hitSlop={8}>
                <Text style={[tipo.footnote, { color: c.accent }]}>Todas</Text>
              </Pressable>
              {migas.map((m, i) => (
                <React.Fragment key={m.id}>
                  <Text style={[tipo.footnote, { color: c.textSecondary }]}> › </Text>
                  {i < migas.length - 1 ? (
                    <Pressable testID={`selector-miga-${m.id}`} accessibilityRole="link" onPress={() => setNivel(m.id)} hitSlop={8}>
                      <Text style={[tipo.footnote, { color: c.accent }]}>{m.nombre}</Text>
                    </Pressable>
                  ) : (
                    <Text style={[tipo.footnote, { color: c.textPrimary }]}>{m.nombre}</Text>
                  )}
                </React.Fragment>
              ))}
            </View>
          ) : null}

          {p.carga.fase === 'CARGANDO' ? (
            <Text testID="selector-cargando" style={[tipo.subheadline, s.cuerpo, { color: c.textSecondary }]}>Cargando…</Text>
          ) : null}

          {actual && p.esSeleccionable(actual) ? (
            <FilaSelector
              testID="selector-usar"
              iconKey={actual.icon_key}
              titulo={`Usar «${actual.nombre}»`}
              subtitulo="Elegir la categoría general"
              enfasis
              elegida={p.seleccionadaId === actual.id}
              onPress={() => p.onElegir(actual)}
            />
          ) : null}
          {actual && !p.esSeleccionable(actual) && p.motivo(actual) ? (
            <View testID="selector-aviso-nivel" style={[s.aviso, s.avisoNivel, { backgroundColor: c.unknownSurface }]}>
              <Ionicons name="information-circle-outline" size={18} color={c.textSecondary} />
              <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>
                {p.motivo(actual) === 'Desactivada'
                  ? `${actual.nombre} está desactivada y no se puede elegir. ${usables(actual) ? 'Sus subcategorías activas sí.' : 'Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría.'}`
                  : `${actual.nombre} no se puede elegir (${p.motivo(actual)!.toLowerCase()}). ${usables(actual) ? 'Sus subcategorías sí.' : 'Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría.'}`}
              </Text>
            </View>
          ) : null}

          {nivel === null && p.carga.fase === 'OK' && p.opcionRaiz && filas.length > 0 ? (
            <Text style={[tipo.footnote, s.seccion, { color: c.textSecondary }]}>Categorías</Text>
          ) : null}

          {p.carga.fase === 'OK' && nivel === null && filas.length === 0 ? (
            <View testID="selector-vacio" style={s.vacio}>
              <IconoCategoriaVista iconKey={null} tamano={22} />
              <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>Aún no tienes categorías</Text>
              <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>
                {p.modo === 'REGISTRO'
                  ? 'Puedes crearlas en Ajustes › Categorías o registrar este gasto sin categoría.'
                  : 'Crea la primera con «Nueva categoría».'}
              </Text>
            </View>
          ) : null}

          {filas.map((n) => {
            const conHijos = visiblesDe(n.id).length > 0;
            const sel = p.esSeleccionable(n);
            const mot = sel ? null : p.motivo(n);
            const subtitulo = [mot, !sel && conHijos && mot ? (usables(n) ? 'tiene subcategorías que sí puedes usar' : 'sus subcategorías tampoco se pueden usar') : null].filter(Boolean).join(' · ') || undefined;
            return (
              <FilaSelector
                key={n.id}
                testID={`cat-${n.id}`}
                iconKey={n.icon_key}
                titulo={n.nombre}
                subtitulo={subtitulo}
                apagada={!sel}
                chevron={conHijos}
                elegida={p.seleccionadaId === n.id}
                deshabilitada={!sel && !conHijos}
                onPress={() => tocar(n)}
              />
            );
          })}
          </>
          ) : null}
        </ScrollView>
      )}
    </View>
  );
}

function FilaSelector(p: {
  testID: string;
  iconKey: string | null;
  titulo: string;
  subtitulo?: string;
  /** F05-05: tercera línea (motivo de una sugerida), en acento. */
  detalle?: string;
  elegida?: boolean;
  enfasis?: boolean;
  apagada?: boolean;
  chevron?: boolean;
  deshabilitada?: boolean;
  onPress: () => void;
}) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityState={{ selected: !!p.elegida, disabled: !!p.deshabilitada }}
      accessibilityLabel={[p.titulo, p.subtitulo, p.detalle, p.elegida ? 'Elegida' : null].filter(Boolean).join('. ')}
      disabled={p.deshabilitada}
      onPress={p.onPress}
      style={({ pressed }) => [s.fila, { borderBottomColor: c.separator, opacity: pressed ? 0.7 : 1 }]}
    >
      <IconoCategoriaVista iconKey={p.iconKey} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[tipo.body, { color: p.enfasis ? c.accent : p.apagada ? c.textSecondary : c.textPrimary, fontWeight: p.enfasis ? '600' : '400' }]}>
          {p.titulo}
        </Text>
        {p.subtitulo ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{p.subtitulo}</Text> : null}
        {p.detalle ? <Text style={[tipo.caption, { color: c.accent }]}>{p.detalle}</Text> : null}
      </View>
      {p.elegida ? (
        <View style={s.elegida}>
          <Ionicons name="checkmark" size={16} color={c.accent} />
          <Text style={[tipo.footnote, { color: c.accent, fontWeight: '600' }]}>Elegida</Text>
        </View>
      ) : null}
      {p.chevron ? <Ionicons name="chevron-forward" size={18} color={c.textSecondary} /> : null}
    </Pressable>
  );
}

/** Botón de contorno (lámina R09): superficie primaria con borde, texto de acento. */
export function BotonSecundario(p: { titulo: string; onPress: () => void; testID?: string; critico?: boolean }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.titulo}
      onPress={p.onPress}
      style={({ pressed }) => [s.secundario, { borderColor: c.borderStandard, backgroundColor: c.surfacePrimary, opacity: pressed ? 0.85 : 1 }]}
    >
      <Text style={[tipo.bodyEmphasis, { color: p.critico ? c.critical : c.accent }]}>{p.titulo}</Text>
    </Pressable>
  );
}

export { BotonPrimario };

const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  cuerpo: { padding: espacio.l },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.l, paddingVertical: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  hueco: { width: 32, height: 32, borderRadius: radio.s, alignItems: 'center', justifyContent: 'center' },
  migas: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', paddingHorizontal: espacio.l, paddingVertical: espacio.m, borderBottomWidth: StyleSheet.hairlineWidth },
  aviso: { flexDirection: 'row', alignItems: 'flex-start', gap: espacio.s, borderRadius: radio.m, padding: espacio.m },
  avisoNivel: { margin: espacio.l },
  seccion: { paddingHorizontal: espacio.l, paddingTop: espacio.l, paddingBottom: espacio.xs },
  vacio: { alignItems: 'center', gap: espacio.s, padding: espacio.xxl },
  elegida: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  buscador: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.l, paddingTop: espacio.m },
  campoBusqueda: { flex: 1, minHeight: TACTIL_MIN, borderRadius: radio.m, paddingHorizontal: espacio.m },
  secundario: { minHeight: 52, borderRadius: radio.m, borderWidth: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: espacio.l },
});
