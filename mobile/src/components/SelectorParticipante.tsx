// ============================================================
// GAPTO MOBILE 2027
// Fichero: SelectorParticipante.tsx
// Ruta: mobile/src/components/SelectorParticipante.tsx
// Descripción: Selector de persona del asistente de contratos (F06-02/03 V-bis y V-ter; lámina CON v0.8 B3c y B3d; decisión 7 = A y decisión 5 = B de Moisés, 18-11). V-bis (n.º 132 parcial): lista SOLO terceros ACTIVOS; cuando hay dos o más con el mismo nombre normalizado cada fila muestra su naturaleza (persona o empresa) y su USO EN GAPTO (contrato más reciente con rol y etiqueta, o último movimiento, o «sin uso»), derivado al leer por el servidor, nunca almacenado. Si dos filas siguen idénticas, la fila NO se elige directamente: abre su ficha y se confirma desde ella («Es esta persona»). Nada viene elegido. V-ter: «+ Nuevo tercero» abre el `SelectorTercero` EXISTENTE de F05 tal como está (su hoja `tercero-duplicado` con Usar / Reactivar / Crear otro; reactivar es el circuito de F05); aquí no se crea ninguna hoja ni lectura de duplicados nueva, y un inactivo nunca se elige sin reactivarlo antes. No toca `SelectorTercero`.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import type { ClienteApi, Tercero } from '../api/cliente';
import type { ClienteContratos, FichaTercero, TerceroParaContrato } from '../api/contratos';
import { detalleHomonimo, filasSelector, textoNaturaleza, textoUso, TEXTO_HOMONIMOS_AYUDA } from '../domain/contratos';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, BotonTexto, EstadoDato } from './Basicos';
import { Aviso, Hoja } from './HojasCategoria';
import { SelectorTercero } from './SelectorTercero';
import { BotonSecundario } from './SelectorCategorias';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: TerceroParaContrato[] };

export function SelectorParticipante(p: {
  contratos: ClienteContratos;
  cliente: ClienteApi;
  nuevoId: () => string;
  titulo: string;
  onElegir: (t: Tercero) => void;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const [filtro, setFiltro] = useState('');
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [ficha, setFicha] = useState<{ t: TerceroParaContrato; f: FichaTercero | null } | null>(null);
  const [nuevo, setNuevo] = useState(false);
  const peticion = useRef(0);

  const cargar = async (q: string) => {
    const n = ++peticion.current;
    setCarga({ fase: 'CARGANDO' });
    const r = await p.contratos.tercerosParaContrato(q);
    if (n !== peticion.current) return;
    setCarga(r.tipo === 'OK' ? { fase: 'OK', lista: r.datos.terceros } : { fase: 'ERROR' });
  };
  useEffect(() => {
    void cargar(filtro.trim());
  }, [filtro]);

  const abrirFicha = async (t: TerceroParaContrato) => {
    setFicha({ t, f: null });
    const r = await p.contratos.fichaTercero(t.id);
    setFicha({ t, f: r.tipo === 'OK' ? r.datos : null });
  };

  // V-ter: el selector EXISTENTE de F05, sin cambios (su hoja de duplicados incluye inactivos y reactiva por el circuito de F05).
  if (nuevo) {
    return (
      <SelectorTercero cliente={p.cliente} nuevoId={p.nuevoId} titulo="Nuevo tercero" seleccionadoId={null}
        onElegir={(t) => { if (t) p.onElegir(t); else setNuevo(false); }} onCerrar={() => setNuevo(false)} />
    );
  }

  if (ficha) {
    const { t, f } = ficha;
    return (
      <Hoja titulo={t.nombre} testID="participante-ficha">
        <Text testID="participante-ficha-naturaleza" style={[tipo.body, { color: c.textPrimary }]}>{textoNaturaleza(t.naturaleza)}</Text>
        {f === null ? <EstadoDato estado="CARGANDO" /> : (
          <View testID="participante-ficha-uso" style={{ gap: espacio.xs }}>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>USO EN GAPTO</Text>
            {f.uso.length === 0 ? <Text style={[tipo.body, { color: c.textPrimary }]}>{textoUso(t.uso)}</Text> : f.uso.map((u) => (
              <Text key={u.contrato_id} style={[tipo.body, { color: c.textPrimary }]}>{`${u.contrato_nombre} · ${u.rol.toLowerCase()}`}</Text>
            ))}
          </View>
        )}
        <BotonPrimario testID="participante-es-esta" titulo="Es esta persona" onPress={() => p.onElegir(t)} />
        <BotonSecundario testID="participante-ficha-volver" titulo="Volver" onPress={() => setFicha(null)} />
      </Hoja>
    );
  }

  const filas = carga.fase === 'OK' ? filasSelector(carga.lista) : [];
  return (
    <Hoja titulo={p.titulo} testID="selector-participante">
      <TextInput testID="participante-filtro" accessibilityLabel="Buscar en tus terceros" value={filtro} onChangeText={setFiltro}
        placeholder="Buscar en tus terceros" placeholderTextColor={c.textSecondary} autoCorrect={false}
        style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]} />
      {carga.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
      {carga.fase === 'ERROR' ? (
        <Pressable testID="participante-error" accessibilityRole="button" onPress={() => void cargar(filtro.trim())} style={{ minHeight: TACTIL_MIN }}>
          <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
        </Pressable>
      ) : null}
      <ScrollView style={{ maxHeight: 320 }} keyboardShouldPersistTaps="handled">
        {filas.map(({ tercero: t, homonimo, identica }) => (
          <Pressable key={t.id} testID={`participante-${t.id}`} accessibilityRole="button"
            accessibilityLabel={homonimo ? `${t.nombre}. ${detalleHomonimo(t)}${identica ? '. Ver ficha' : ''}` : t.nombre}
            onPress={() => (identica ? void abrirFicha(t) : p.onElegir(t))} style={[s.fila, { borderColor: c.borderDefault }]}>
            <View style={{ flex: 1 }}>
              <Text style={[tipo.body, { color: c.textPrimary }]}>{t.nombre}</Text>
              {homonimo ? <Text testID={`participante-${t.id}-uso`} style={[tipo.caption, { color: c.textSecondary }]}>{detalleHomonimo(t) + (identica ? ' · ver ficha' : '')}</Text> : null}
            </View>
          </Pressable>
        ))}
        {carga.fase === 'OK' && filas.length === 0 ? <Text testID="participante-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>No hay terceros con ese nombre.</Text> : null}
      </ScrollView>
      <Text testID="participante-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_HOMONIMOS_AYUDA}</Text>
      <BotonTexto testID="participante-nuevo" titulo="+ Nuevo tercero" onPress={() => setNuevo(true)} />
      <BotonSecundario testID="participante-cerrar" titulo="Cerrar" onPress={p.onCerrar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN + 8, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: espacio.xs },
});
