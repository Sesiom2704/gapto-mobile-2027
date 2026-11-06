// ============================================================
// GAPTO MOBILE 2027
// Fichero: Titularidad.tsx
// Ruta: mobile/src/components/Titularidad.tsx
// Descripción: Editor de titularidad de una propiedad (F06-01 B1; lámina F06-01 v0.9 A2 y v0.1 C2; C-PROP-01 §I.1 y C-PROP-03). Modos «Solo mía», «Compartida», «Es de otra persona» y «Aún no lo sé» (este último solo en el alta), ninguno marcado al empezar; filas «Tú» y cotitulares con su porcentaje escrito como texto exacto (4 decimales); total visible «Total 100 % ✓» o «Total 90 % · falta un 10 %» sin repartir el resto; fecha «Desde» obligatoria salvo en «Aún no lo sé». Los cotitulares se eligen en una hoja entre los terceros activos: solo PERSONA o EMPRESA (Q-10); los demás aparecen apagados con el motivo. El servidor revalida todo.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import type { ClienteApi, Tercero } from '../api/cliente';
import { estadoSuma, FormTitularidad, MODOS_TITULARIDAD, ModoTitularidad, ParteForm, partesParaModo, TEXTO_SUMA, TEXTO_TITULARIDAD_DIMENSION } from '../domain/propiedad';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { EstadoDato } from './Basicos';
import { Campo, CampoTexto } from './Formulario';
import { Hoja } from './HojasCategoria';
import { BotonSecundario } from './SelectorCategorias';

export function EditorTitularidad(p: {
  cliente: ClienteApi;
  form: FormTitularidad;
  onCambiar: (f: FormTitularidad) => void;
  nuevaClave: () => string;
  /** Modos ofrecidos (el cambio desde una fecha no admite «Aún no lo sé»). */
  modos?: ModoTitularidad[];
  /** Texto bajo la fecha «Desde» (p. ej., «fecha de adquisición»). */
  ayudaDesde?: string;
  testID?: string;
}) {
  const { c } = useTema();
  const [hoja, setHoja] = useState(false);
  const f = p.form;
  const modos = MODOS_TITULARIDAD.filter((m) => !p.modos || p.modos.includes(m.valor));
  const suma = f.partes.length > 0 ? estadoSuma(f.partes) : null;
  const conPartes = f.modo === 'COMPARTIDA' || f.modo === 'DE_OTROS';
  const cambiarParte = (clave: string, porcentaje: string) => p.onCambiar({ ...f, partes: f.partes.map((x) => (x.clave === clave ? { ...x, porcentaje } : x)) });
  const quitar = (clave: string) => p.onCambiar({ ...f, partes: f.partes.filter((x) => x.clave !== clave) });
  const anadir = (t: Tercero) => {
    setHoja(false);
    if (f.partes.some((x) => !x.yo && x.terceroId === t.id)) return;
    p.onCambiar({ ...f, partes: [...f.partes, { clave: p.nuevaClave(), yo: false, terceroId: t.id, nombre: t.nombre, porcentaje: '' }] });
  };

  return (
    <View testID={p.testID ?? 'titularidad'} style={{ gap: espacio.l }}>
      <View style={{ gap: espacio.s }}>
        {modos.map((m) => {
          const sel = f.modo === m.valor;
          return (
            <Pressable
              key={m.valor}
              testID={`tit-modo-${m.valor}`}
              accessibilityRole="radio"
              accessibilityState={{ checked: sel }}
              accessibilityLabel={`${m.titulo}. ${m.detalle}`}
              onPress={() => p.onCambiar({ ...f, modo: m.valor, partes: partesParaModo(m.valor, f.partes, p.nuevaClave) })}
              style={[s.modo, { borderColor: sel ? c.accent : c.borderStandard, backgroundColor: sel ? c.accentSurface : c.surfacePrimary }]}
            >
              <Ionicons name={sel ? 'radio-button-on' : 'radio-button-off'} size={20} color={sel ? c.accentText : c.textSecondary} />
              <View style={{ flex: 1 }}>
                <Text style={[tipo.body, { color: c.textPrimary, fontWeight: sel ? '600' : '400' }]}>{m.titulo}</Text>
                <Text style={[tipo.caption, { color: c.textSecondary }]}>{m.detalle}</Text>
              </View>
            </Pressable>
          );
        })}
      </View>

      {conPartes ? (
        <View style={{ gap: espacio.s }}>
          {f.partes.map((x) => (
            <FilaParte key={x.clave} parte={x} onPorcentaje={(t) => cambiarParte(x.clave, t)} onQuitar={x.yo ? undefined : () => quitar(x.clave)} />
          ))}
          <Pressable testID="tit-anadir" accessibilityRole="button" onPress={() => setHoja(true)} style={s.anadir}>
            <Ionicons name="add" size={18} color={c.accentText} />
            <Text style={[tipo.body, { color: c.accentText }]}>Añadir persona</Text>
          </Pressable>
          {suma ? (
            <Text testID="tit-total" accessibilityLiveRegion="polite" style={[tipo.bodyEmphasis, { color: suma.ok ? c.textPrimary : c.warningText }]}>
              {suma.texto}
            </Text>
          ) : null}
          {suma && !suma.ok ? <Text testID="tit-suma-aviso" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SUMA}</Text> : null}
        </View>
      ) : null}
      {f.modo === 'SOLO_MIA' ? <Text testID="tit-solo-mia" style={[tipo.body, { color: c.textPrimary }]}>Tú · 100 %</Text> : null}

      {f.modo !== null && f.modo !== 'DESCONOCIDA' ? (
        <Campo etiqueta="Desde">
          <CampoTexto testID="tit-desde" etiqueta="Desde" marcador="dd/mm/aaaa" valor={f.desde} onCambiar={(t) => p.onCambiar({ ...f, desde: t })} />
          {p.ayudaDesde ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{p.ayudaDesde}</Text> : null}
        </Campo>
      ) : null}
      {f.modo === 'DESCONOCIDA' ? (
        <Text testID="tit-desconocida" style={[tipo.footnote, { color: c.textSecondary }]}>Tu parte quedará «sin indicar»: nunca se muestra como 0 ni como 100 %.</Text>
      ) : null}
      {f.modo !== null ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_TITULARIDAD_DIMENSION}</Text> : null}

      {hoja ? <HojaCotitular cliente={p.cliente} excluidos={f.partes.flatMap((x) => (x.yo ? [] : [x.terceroId]))} onElegir={anadir} onCerrar={() => setHoja(false)} /> : null}
    </View>
  );
}

function FilaParte(p: { parte: ParteForm; onPorcentaje: (t: string) => void; onQuitar?: () => void }) {
  const { c } = useTema();
  const id = p.parte.yo ? 'yo' : p.parte.terceroId;
  return (
    <View testID={`tit-parte-${id}`} style={[s.parte, { borderColor: c.borderDefault, backgroundColor: c.surfacePrimary }]}>
      <Text style={[tipo.body, { color: c.textPrimary, flex: 1, minWidth: 0 }]} numberOfLines={2}>{p.parte.nombre}</Text>
      <TextInput
        testID={`tit-pct-${id}`}
        accessibilityLabel={`Porcentaje de ${p.parte.nombre}`}
        value={p.parte.porcentaje}
        onChangeText={p.onPorcentaje}
        keyboardType="decimal-pad"
        placeholder="0"
        placeholderTextColor={c.textSecondary}
        style={[tipo.body, s.pct, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.background }]}
      />
      <Text style={[tipo.body, { color: c.textSecondary }]}>%</Text>
      {p.onQuitar ? (
        <Pressable testID={`tit-quitar-${id}`} accessibilityRole="button" accessibilityLabel={`Quitar a ${p.parte.nombre}`} hitSlop={8} onPress={p.onQuitar} style={s.quitar}>
          <Ionicons name="close-circle" size={20} color={c.textSecondary} />
        </Pressable>
      ) : null}
    </View>
  );
}

/** Hoja de cotitulares: terceros activos; solo PERSONA o EMPRESA se pueden elegir (Q-10). */
export function HojaCotitular(p: { cliente: ClienteApi; excluidos: string[]; onElegir: (t: Tercero) => void; onCerrar: () => void }) {
  const { c } = useTema();
  const [lista, setLista] = useState<Tercero[] | null | 'ERROR'>(null);
  const [filtro, setFiltro] = useState('');
  const cargar = async () => {
    setLista(null);
    const r = await p.cliente.listarTerceros();
    setLista(r.tipo === 'OK' ? r.datos.terceros.filter((t) => t.enabled && !p.excluidos.includes(t.id)) : 'ERROR');
  };
  useEffect(() => {
    void cargar();
  }, []);
  const q = filtro.trim().toLocaleLowerCase('es');
  const visibles = Array.isArray(lista) ? [...lista].filter((t) => !q || t.nombre.toLocaleLowerCase('es').includes(q)).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')) : [];
  return (
    <Hoja titulo="Añadir persona" testID="hoja-cotitular">
      <CampoTexto testID="cotitular-filtro" etiqueta="Filtrar por nombre" marcador="Filtrar por nombre" valor={filtro} onCambiar={setFiltro} />
      {lista === null ? <EstadoDato estado="CARGANDO" /> : null}
      {lista === 'ERROR' ? (
        <Pressable testID="cotitular-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
          <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
        </Pressable>
      ) : null}
      <ScrollView style={{ maxHeight: 320 }} keyboardShouldPersistTaps="handled">
        {visibles.map((t) => {
          const admitida = t.naturaleza === 'PERSONA' || t.naturaleza === 'EMPRESA';
          return (
            <Pressable
              key={t.id}
              testID={`cotitular-${t.id}`}
              accessibilityRole="button"
              accessibilityState={{ disabled: !admitida }}
              disabled={!admitida}
              onPress={() => p.onElegir(t)}
              style={[s.fila, { borderColor: c.borderDefault }]}
            >
              <View style={{ flex: 1 }}>
                <Text style={[tipo.body, { color: admitida ? c.textPrimary : c.textSecondary }]}>{t.nombre}</Text>
                <Text style={[tipo.caption, { color: c.textSecondary }]}>
                  {t.naturaleza === 'PERSONA' ? 'Persona' : t.naturaleza === 'EMPRESA' ? 'Empresa' : 'Solo personas o empresas pueden ser titulares. Indícalo en Ajustes › Terceros.'}
                </Text>
              </View>
            </Pressable>
          );
        })}
        {Array.isArray(lista) && visibles.length === 0 ? (
          <Text testID="cotitular-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>No hay terceros activos que coincidan. Créalos en Ajustes › Terceros.</Text>
        ) : null}
      </ScrollView>
      <BotonSecundario testID="cotitular-cerrar" titulo="Cerrar" onPress={p.onCerrar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  modo: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.m, padding: espacio.m, minHeight: TACTIL_MIN + 8 },
  parte: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, borderWidth: 1, borderRadius: radio.m, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 8 },
  // Ancho fijo: en web el campo tomaba todo el sobrante y recortaba el nombre del titular (gate B1, capturas 0.5.2).
  pct: { borderWidth: 1, borderRadius: radio.s, width: 88, flexShrink: 0, minHeight: TACTIL_MIN, paddingHorizontal: espacio.s, textAlign: 'right' },
  quitar: { minHeight: TACTIL_MIN, minWidth: TACTIL_MIN, alignItems: 'center', justifyContent: 'center' },
  anadir: { flexDirection: 'row', alignItems: 'center', gap: espacio.xs, minHeight: TACTIL_MIN },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 8, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: espacio.xs },
});
