// ============================================================
// GAPTO MOBILE 2027
// Fichero: ContextosAjustesScreen.tsx
// Ruta: mobile/src/screens/ContextosAjustesScreen.tsx
// Descripción: Ajustes › Contextos (F05-03 J2 §2.5; F05 §46.3 A6; lámina REG-DYN / SET-TH / SET-CTX v0.1 S03, C01). Lista con el texto de la lámina, filas «Finde Cartagena» / «Viaje · 10–12 oct» y, desactivados, «Evento · Desactivado». Alta y edición con el formulario C01 (FormularioContexto); desactivar / reactivar con row_version y sin borrado. VERSION_DESFASADA → recarga y aviso, sin reintento automático.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.5)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, Contexto } from '../api/cliente';
import { CabeceraNavegacion, EstadoDato } from '../components/Basicos';
import { FormularioContexto, TEXTO_CONTEXTO, TEXTO_INDETERMINADO_CTX, TEXTO_VERSION_CTX } from '../components/Contextos';
import { AvisoCaja, estilosFormulario as ef, FilaLista, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { BotonSecundario } from '../components/SelectorCategorias';
import { detalleContexto } from '../domain/maestros';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';

/** DERIVADO. */
export const TEXTO_DESACTIVADO_CTX = 'Desactivado: deja de ofrecerse al registrar. Lo ya registrado no cambia.';
/** DERIVADO. */
export const TEXTO_REACTIVADO_CTX = 'Reactivado: vuelve a ofrecerse al registrar.';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: Contexto[] };
type Vista = { v: 'LISTA' } | { v: 'NUEVO' } | { v: 'EDITAR'; id: string; aviso: AvisoCaja };

export function ContextosAjustesScreen(p: { cliente: ClienteApi; nuevoId: () => string; onAtras: () => void; onInmersiva: (x: boolean) => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [vista, setVista] = useState<Vista>({ v: 'LISTA' });
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(
    async (silencioso = false): Promise<Contexto[] | null> => {
      if (!silencioso) setCarga({ fase: 'CARGANDO' });
      const r = await p.cliente.listarContextos();
      if (r.tipo !== 'OK') {
        if (!silencioso) setCarga({ fase: 'ERROR' });
        return null;
      }
      setCarga({ fase: 'OK', lista: r.datos.contextos });
      return r.datos.contextos;
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
  const ordenar = (l: Contexto[]) => [...l].sort((a, b) => a.nombre.localeCompare(b.nombre, 'es') || (a.id < b.id ? -1 : 1));
  const activos = ordenar(lista.filter((x) => x.enabled));
  const desactivados = ordenar(lista.filter((x) => !x.enabled));

  const cambiarEstado = async (x: Contexto) => {
    if (ocupado) return;
    setOcupado(true);
    const r = x.enabled ? await p.cliente.desactivarContexto(x.id, x.row_version) : await p.cliente.reactivarContexto(x.id, x.row_version);
    const l = await cargar(true);
    setOcupado(false);
    let aviso: AvisoCaja;
    if (r.tipo === 'OK') aviso = { tipo: 'OK', texto: x.enabled ? TEXTO_DESACTIVADO_CTX : TEXTO_REACTIVADO_CTX };
    else if (r.tipo === 'INDETERMINADO') aviso = { tipo: 'AVISO', texto: TEXTO_INDETERMINADO_CTX };
    else if (r.codigo === 'VERSION_DESFASADA') aviso = { tipo: 'AVISO', texto: TEXTO_VERSION_CTX };
    else aviso = { tipo: 'AVISO', texto: r.mensaje || TEXTO_INDETERMINADO_CTX };
    if (l && !l.some((y) => y.id === x.id)) return setVista({ v: 'LISTA' });
    setVista({ v: 'EDITAR', id: x.id, aviso });
  };

  if (vista.v !== 'LISTA') {
    const actual = vista.v === 'EDITAR' ? lista.find((x) => x.id === vista.id) ?? null : null;
    return (
      <FormularioContexto
        key={actual ? `${actual.id}-${actual.row_version}` : 'nuevo'}
        testID="ajctx-form"
        cliente={p.cliente}
        nuevoId={p.nuevoId}
        existente={actual}
        tituloBoton="Guardar"
        avisoInicial={vista.v === 'EDITAR' ? vista.aviso : null}
        onHecho={() => {
          void cargar(true);
          setVista({ v: 'LISTA' });
        }}
        onCancelar={() => setVista({ v: 'LISTA' })}
        onRecargar={async () => (await cargar(true))?.find((x) => x.id === actual?.id) ?? null}
        pie={
          actual ? (
            actual.enabled ? (
              <BotonSecundario testID="ajctx-desactivar" titulo="Desactivar" critico onPress={() => void cambiarEstado(actual)} />
            ) : (
              <BotonSecundario testID="ajctx-reactivar" titulo="Reactivar" onPress={() => void cambiarEstado(actual)} />
            )
          ) : null
        }
      />
    );
  }

  return (
    <View testID="pantalla-contextos" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion
        titulo="Contextos"
        atras={{ etiqueta: 'Ajustes', onPress: p.onAtras }}
        testIDAtras="ajctx-atras"
        derecha={
          <Pressable testID="ajctx-nuevo" accessibilityRole="button" accessibilityLabel="Nuevo contexto" hitSlop={8} onPress={() => setVista({ v: 'NUEVO' })} style={ef.mas}>
            <Ionicons name="add" size={24} color={c.accent} />
          </Pressable>
        }
      />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Text testID="ajctx-intro" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CONTEXTO}</Text>
        {carga.fase === 'CARGANDO' ? <EstadoDato testID="ajctx-cargando" estado="CARGANDO" /> : null}
        {carga.fase === 'ERROR' ? (
          <Pressable testID="ajctx-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {(
          [
            ['activos', null, activos],
            ['desactivados', 'Desactivados', desactivados],
          ] as const
        ).map(([clave, titulo, l]) =>
          l.length === 0 ? null : (
            <View key={clave} testID={`ajctx-grupo-${clave}`} style={{ gap: espacio.s }}>
              {titulo ? <RotuloGrupo texto={titulo} /> : null}
              <Tarjeta>
                {l.map((x, i) => (
                  <FilaLista key={x.id} testID={`ajctx-fila-${x.id}`} titulo={x.nombre} detalle={detalleContexto(x)} apagada={!x.enabled}
                    ultima={i === l.length - 1} onPress={() => setVista({ v: 'EDITAR', id: x.id, aviso: null })} />
                ))}
              </Tarjeta>
            </View>
          ),
        )}
      </ScrollView>
    </View>
  );
}
