// ============================================================
// GAPTO MOBILE 2027
// Fichero: NuevaCategoriaScreen.tsx
// Ruta: mobile/src/screens/NuevaCategoriaScreen.tsx
// Descripción: Alta de categoría CREATE-M (F09 §12.97.4 y §12.97.6; lámina SET-CAT v1.0 S02/I03). Tarea inmersiva (sin barra inferior): nombre; icono opcional (selector de iconos); ubicación (raíz o padre con ruta visible, elegida con el selector jerárquico en modo AJUSTES restringido a padres habilitados con toda su cadena habilitada, AJ-S4-03); ámbito Gasto / Ingreso / Ambos SIN preselección; «¿Cuenta para el presupuesto por defecto?» Sí/No SIN preselección, con microcopy de que no rellena el registro; acción principal desactivada hasta completar, indicando lo que falta. Aviso D-198 en lenguaje potencial SOLO con padre, no modal (F05-01-R10). El `id` lo genera la app y se SELLA con la petición en el primer envío: ante INDETERMINADO se reintenta la MISMA petición con el MISMO id (idempotencia del alta AJ-S4-05) y el formulario queda bloqueado; un rechazo definitivo libera la edición y el siguiente envío usa id nuevo. Códigos: CATEGORIA_NOMBRE_DUPLICADO junto al nombre; CATEGORIA_PADRE_DESHABILITADO / CATEGORIA_PADRE_NO_VALIDO recargan el árbol y piden otra ubicación; ICONO_CATEGORIA_NO_VALIDO se explica y recarga.
// Versión: 0.1.0 (F05-01 S6-WIRE+UI (este mandato))
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { AltaCategoria, ClienteApi } from '../api/cliente';
import { BotonPrimario, BotonTexto, Segmentado } from '../components/Basicos';
import { IconoCategoriaVista, SelectorCategorias } from '../components/SelectorCategorias';
import { SelectorIconos } from '../components/SelectorIconos';
import { Ambito, Arbol, ancestros } from '../domain/categoria';
import { iconoDe } from '../theme/iconosCategoria';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

type Envio =
  | { fase: 'EDITANDO' }
  | { fase: 'ENVIANDO'; sellada: AltaCategoria }
  | { fase: 'INDETERMINADO'; sellada: AltaCategoria; mensaje: string };

export const AVISO_D198 = 'Las nuevas subcategorías pueden quedar incluidas en presupuestos que cubran esta rama.';

export function NuevaCategoriaScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  arbol: Arbol;
  padreInicial: string | null;
  onRecargarArbol: () => Promise<void> | void;
  onCancelar: () => void;
  onCreada: (padre: string | null) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [nombre, setNombre] = useState('');
  const [padre, setPadre] = useState<string | null>(p.padreInicial);
  const [ambito, setAmbito] = useState<Ambito | null>(null);
  const [presupuestable, setPresupuestable] = useState<boolean | null>(null);
  const [iconKey, setIconKey] = useState<string | null>(null);
  const [selector, setSelector] = useState<'UBICACION' | 'ICONO' | null>(null);
  const [envio, setEnvio] = useState<Envio>({ fase: 'EDITANDO' });
  const [errorNombre, setErrorNombre] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const enVuelo = useRef(false);

  const bloqueado = envio.fase !== 'EDITANDO';
  const nodoPadre = padre ? p.arbol.porId.get(padre) ?? null : null;
  const rutaPadre = nodoPadre ? [...ancestros(p.arbol, nodoPadre.id), nodoPadre].map((n) => n.nombre).join(' › ') : null;

  const faltan = [
    nombre.trim() === '' ? 'nombre' : null,
    ambito === null ? 'ámbito' : null,
    presupuestable === null ? 'si cuenta para el presupuesto' : null,
  ].filter(Boolean) as string[];
  const listo = faltan.length === 0;
  const textoFaltan = listo ? '' : `Para crear falta: ${faltan.length === 1 ? faltan[0] : `${faltan.slice(0, -1).join(', ')} y ${faltan[faltan.length - 1]}`}.`;

  const enviar = async (sellada: AltaCategoria) => {
    if (enVuelo.current) return; // doble tap: nunca un segundo POST
    enVuelo.current = true;
    setEnvio({ fase: 'ENVIANDO', sellada });
    try {
      const r = await p.cliente.crearCategoria(sellada);
      if (r.tipo === 'OK') return p.onCreada(sellada.parent_id);
      if (r.tipo === 'INDETERMINADO') return setEnvio({ fase: 'INDETERMINADO', sellada, mensaje: r.mensaje });
      // Rechazo definitivo: nada persistido; se libera la edición (el siguiente envío usa id nuevo).
      setEnvio({ fase: 'EDITANDO' });
      if (r.codigo === 'CATEGORIA_NOMBRE_DUPLICADO') setErrorNombre('Ya hay una categoría activa con ese nombre en el mismo nivel.');
      else if (r.codigo === 'CATEGORIA_PADRE_DESHABILITADO' || r.codigo === 'CATEGORIA_PADRE_NO_VALIDO') {
        setPadre(null);
        setAviso('La ubicación elegida ya no está disponible. Elige otra.');
        await p.onRecargarArbol();
      } else if (r.codigo === 'ICONO_CATEGORIA_NO_VALIDO') {
        setIconKey(null);
        setAviso('Ese icono no está disponible. Elige otro o «Sin icono».');
        await p.onRecargarArbol();
      } else setAviso(`No se ha creado. ${r.mensaje}`);
    } finally {
      enVuelo.current = false;
    }
  };

  const onCrear = () => {
    if (envio.fase === 'INDETERMINADO') return void enviar(envio.sellada); // MISMA petición, MISMO id
    if (!listo || bloqueado || ambito === null || presupuestable === null) return;
    setErrorNombre(null);
    setAviso(null);
    void enviar(
      Object.freeze({ id: p.nuevoId(), nombre: nombre.trim(), parent_id: padre, ambito, presupuestable_default: presupuestable, icon_key: iconKey }),
    );
  };

  const icono = iconoDe(iconKey);

  return (
    <KeyboardAvoidingView testID="nueva-categoria-pantalla" style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <BotonTexto testID="alta-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>Nueva categoría</Text>
        <View style={{ width: 72 }} />
      </View>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Campo etiqueta="Nombre" error={errorNombre ?? undefined}>
          <TextInput
            testID="alta-nombre"
            accessibilityLabel="Nombre de la categoría"
            value={nombre}
            onChangeText={(t) => { setNombre(t); setErrorNombre(null); }}
            editable={!bloqueado}
            maxLength={200}
            placeholder="Ej. Fruterías"
            placeholderTextColor={c.textSecondary}
            style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: errorNombre ? c.critical : c.borderStandard }]}
          />
        </Campo>

        <Campo etiqueta="Icono (opcional)">
          <FilaElegir testID="alta-icono" icono={<IconoCategoriaVista iconKey={iconKey} />} texto={icono?.etiqueta ?? 'Sin icono'} deshabilitada={bloqueado} onPress={() => setSelector('ICONO')} />
        </Campo>

        <Campo etiqueta="Ubicación">
          <FilaElegir
            testID="alta-ubicacion"
            texto={rutaPadre ? `Dentro de ${rutaPadre}` : 'Categoría principal (raíz)'}
            deshabilitada={bloqueado}
            onPress={() => setSelector('UBICACION')}
          />
        </Campo>

        <Campo etiqueta="Ámbito">
          <Segmentado<Ambito>
            testIDBase="alta-ambito"
            etiquetaGrupo="Ámbito"
            opciones={[{ valor: 'GASTO', etiqueta: 'Gasto' }, { valor: 'INGRESO', etiqueta: 'Ingreso' }, { valor: 'AMBOS', etiqueta: 'Ambos' }]}
            valor={ambito}
            onCambiar={(v) => !bloqueado && setAmbito(v)}
          />
        </Campo>

        <Campo etiqueta="¿Cuenta para el presupuesto por defecto?">
          <Segmentado<boolean>
            testIDBase="alta-presupuesto"
            etiquetaGrupo="¿Cuenta para el presupuesto por defecto?"
            opciones={[{ valor: true, etiqueta: 'Sí' }, { valor: false, etiqueta: 'No' }]}
            valor={presupuestable}
            onCambiar={(v) => !bloqueado && setPresupuestable(v)}
          />
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>
            Es solo un valor de referencia: al registrar un gasto se te seguirá preguntando.
          </Text>
        </Campo>

        {padre !== null ? (
          <View testID="aviso-d198" style={[s.aviso, { backgroundColor: c.unknownSurface }]}>
            <Ionicons name="information-circle-outline" size={18} color={c.textSecondary} />
            <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{AVISO_D198}</Text>
          </View>
        ) : null}

        {aviso ? (
          <View testID="alta-aviso" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            <Ionicons name="alert-circle-outline" size={18} color={c.warning} />
            <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{aviso}</Text>
          </View>
        ) : null}
        {envio.fase === 'INDETERMINADO' ? (
          <View testID="alta-indeterminado" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>
              No se ha podido confirmar el alta. Puedes reintentar: no se duplicará.
            </Text>
          </View>
        ) : null}

        {!listo && envio.fase === 'EDITANDO' ? (
          <Text testID="alta-faltan" style={[tipo.footnote, { color: c.textSecondary }]}>{textoFaltan}</Text>
        ) : null}
        <BotonPrimario
          testID="alta-crear"
          titulo={envio.fase === 'INDETERMINADO' ? 'Reintentar' : envio.fase === 'ENVIANDO' ? 'Guardando…' : 'Crear categoría'}
          cargando={envio.fase === 'ENVIANDO'}
          deshabilitado={envio.fase === 'EDITANDO' && !listo}
          ayuda={envio.fase === 'EDITANDO' && !listo ? textoFaltan : undefined}
          onPress={onCrear}
        />
      </ScrollView>

      {selector === 'UBICACION' ? (
        <SelectorCategorias
          titulo="Ubicación"
          modo="AJUSTES"
          carga={{ fase: 'OK', arbol: p.arbol }}
          // AJ-S4-03: solo padres habilitados con toda su cadena habilitada (los deshabilitados y su rama no se ofrecen).
          esVisible={(n) => n.enabled}
          esSeleccionable={(n) => n.enabled}
          motivo={() => null}
          seleccionadaId={padre}
          opcionRaiz={{
            etiqueta: 'Categoría principal',
            subtitulo: 'Sin categoría superior (raíz)',
            seleccionada: padre === null,
            onPress: () => { setPadre(null); setSelector(null); },
            testID: 'ubicacion-raiz',
          }}
          onElegir={(n) => { setPadre(n.id); setAviso(null); setSelector(null); }}
          onCerrar={() => setSelector(null)}
          testID="selector-ubicacion"
        />
      ) : null}
      {selector === 'ICONO' ? (
        <SelectorIconos
          nombreCategoria={nombre.trim() || 'Nueva categoría'}
          inicial={iconKey}
          accion="Usar este icono"
          onAccion={(k) => { setIconKey(k); setSelector(null); }}
          onCerrar={() => setSelector(null)}
        />
      ) : null}
    </KeyboardAvoidingView>
  );
}

function Campo({ etiqueta, error, children }: { etiqueta: string; error?: string; children: React.ReactNode }) {
  const { c } = useTema();
  return (
    <View style={{ gap: espacio.s }}>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{etiqueta}</Text>
      {children}
      {error ? <Text testID="alta-error-nombre" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{error}</Text> : null}
    </View>
  );
}

function FilaElegir(p: { testID: string; texto: string; icono?: React.ReactNode; deshabilitada?: boolean; onPress: () => void }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="button"
      accessibilityLabel={p.texto}
      disabled={p.deshabilitada}
      onPress={p.onPress}
      style={[s.elegir, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
    >
      {p.icono}
      <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{p.texto}</Text>
      <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  form: { padding: espacio.l, gap: espacio.xl },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4, minWidth: 0 },
  elegir: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 8 },
  aviso: { flexDirection: 'row', alignItems: 'flex-start', gap: espacio.s, borderRadius: radio.m, padding: espacio.m },
});
