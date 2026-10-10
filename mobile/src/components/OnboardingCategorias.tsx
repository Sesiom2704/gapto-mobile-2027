// ============================================================
// GAPTO MOBILE 2027
// Fichero: OnboardingCategorias.tsx
// Ruta: mobile/src/components/OnboardingCategorias.tsx
// Descripción: Oferta de categorías sugeridas (F05-03 J2 §2.6; F05 §46.3 A9; lámina SET-PLT / REG-PLT / HOME-QA v0.2 O01/O02). O01: en Ajustes › Categorías SIN ninguna categoría (ni activa ni desactivada), «Aún no tienes categorías» con «Empezar con categorías sugeridas» o «Empezar desde cero». O02: el árbol sugerido v1 que devuelve el servidor (GET /v1/categorias/sugeridas), por grupos con sus hijos, y «Crear estas categorías» (POST /v1/categorias/onboarding). El servidor decide si aplica (ONBOARDING_NO_APLICABLE si ya hay alguna categoría) y es idempotente; el cliente no crea nada por su cuenta y nunca lo ofrece con categorías existentes.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.6)
// ============================================================

import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, NodoSugerido } from '../api/cliente';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, EstadoDato } from './Basicos';
import { AvisoCaja, CabeceraTarea, Caja, estilosFormulario as ef, Tarjeta } from './Formulario';
import { IconoCategoriaVista } from './SelectorCategorias';
import { BotonSecundario } from './SelectorCategorias';

export const TEXTO_O01_TITULO = 'Aún no tienes categorías';
export const TEXTO_O01 = 'Puedes empezar con un árbol sugerido y adaptarlo, o crear las tuyas desde cero.';
export const textoO02 = (grupos: number) => `${grupos} grupos. Podrás renombrar, mover o desactivar cualquiera después.`;
/** DERIVADO. */
export const TEXTO_ONBOARDING_NO_APLICABLE = 'Ya tienes categorías: el árbol sugerido solo se ofrece cuando no hay ninguna.';
/** DERIVADO. */
export const TEXTO_ONBOARDING_INDETERMINADO = 'No se ha podido confirmar. Vuelve a cargar antes de repetirlo: no se duplicará.';

export function OfertaOnboarding(p: { onSugeridas: () => void; onDesdeCero: () => void }) {
  const { c } = useTema();
  return (
    <View testID="onboarding-oferta" style={{ gap: espacio.m, paddingVertical: espacio.l }}>
      <Text accessibilityRole="header" style={[tipo.bodyEmphasis, { color: c.textPrimary, textAlign: 'center' }]}>{TEXTO_O01_TITULO}</Text>
      <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>{TEXTO_O01}</Text>
      <BotonPrimario testID="onboarding-sugeridas" titulo="Empezar con categorías sugeridas" onPress={p.onSugeridas} />
      <BotonSecundario testID="onboarding-desde-cero" titulo="Empezar desde cero" onPress={p.onDesdeCero} />
    </View>
  );
}

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; nodos: NodoSugerido[] };

export function CategoriasSugeridas(p: { cliente: ClienteApi; onCreadas: () => void; onCancelar: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.categoriasSugeridas();
    setCarga(r.tipo === 'OK' ? { fase: 'OK', nodos: r.datos.nodos } : { fase: 'ERROR' });
  };
  useEffect(() => {
    void cargar();
  }, []);

  const crear = async () => {
    if (ocupado) return;
    setOcupado(true);
    setAviso(null);
    const r = await p.cliente.onboardingCategorias();
    setOcupado(false);
    if (r.tipo === 'OK') return p.onCreadas();
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_ONBOARDING_INDETERMINADO });
    setAviso({ tipo: 'AVISO', texto: r.codigo === 'ONBOARDING_NO_APLICABLE' ? TEXTO_ONBOARDING_NO_APLICABLE : r.mensaje || TEXTO_ONBOARDING_INDETERMINADO });
  };

  // Grupos = nodos de nivel 1 en el orden del fichero (orden del servidor); hijos por ruta del padre.
  const nodos = carga.fase === 'OK' ? carga.nodos : [];
  const grupos = nodos.filter((n) => n.padre === null);
  const hijos = (ruta: string) => nodos.filter((n) => n.padre === ruta);

  return (
    <View testID="onboarding-sugeridas-pantalla" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraTarea titulo="Categorías sugeridas" testIDCancelar="onboarding-cancelar" onCancelar={p.onCancelar} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {carga.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
        {carga.fase === 'ERROR' ? (
          <Pressable testID="onboarding-error" accessibilityRole="button" onPress={() => void cargar()} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {carga.fase === 'OK' ? (
          <>
            <Text testID="onboarding-resumen" style={[tipo.footnote, { color: c.textSecondary }]}>{textoO02(grupos.length)}</Text>
            <Tarjeta testID="onboarding-lista">
              {grupos.map((g) => {
                const h = hijos(g.ruta);
                return (
                  <View key={g.ruta} testID={`sugerida-${g.ruta}`} style={{ flexDirection: 'row', gap: espacio.m, padding: espacio.m, alignItems: 'center' }}>
                    <IconoCategoriaVista iconKey={g.icon_key} />
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={[tipo.body, { color: c.textPrimary }]}>{g.nombre}</Text>
                      {h.length > 0 ? (
                        <Text style={[tipo.caption, { color: c.textSecondary }]}>{h.map((x) => x.nombre).join(', ')}</Text>
                      ) : null}
                    </View>
                    <Text style={[tipo.caption, { color: c.textSecondary }]}>{h.length}</Text>
                  </View>
                );
              })}
            </Tarjeta>
            {aviso ? <Caja testID="onboarding-aviso" aviso={aviso} /> : null}
            <BotonPrimario testID="onboarding-crear" titulo={ocupado ? 'Creando…' : 'Crear estas categorías'} cargando={ocupado} onPress={() => void crear()} />
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}
