// ============================================================
// GAPTO MOBILE 2027
// Fichero: HojasMagnitud.tsx
// Ruta: mobile/src/components/HojasMagnitud.tsx
// Descripción: Hojas y piezas de presentación de las magnitudes de una categoría (F09 §12.97.10; lámina SET-MAG v0.1; F05-D020). Solo presentación: no llaman al cliente; el controlador (MagnitudesCategoria.tsx) decide el comando y trata los rechazos. Píldoras de estado con TEXTO («Obligatoria», «Opcional», «Deshabilitada»), nunca solo color. Hito 1: añadir una magnitud existente (M09: aviso previo si está deshabilitada, «Añadir de todos modos»; la obligatoriedad se elige siempre, sin preselección), cambiar obligatoriedad (M11, guarda prospectiva) y quitar de la categoría (M12, mensaje seguro de AJ-S7MAG-06 con N = registros históricos de la magnitud). Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1)
// ============================================================

import React, { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { MagnitudCatalogo } from '../domain/magnitud';
import { useTema } from '../theme/tema';
import { espacio, radio, tipo } from '../theme/tokens';
import { BotonPrimario, Segmentado } from './Basicos';
import { Aviso, BotonCritico, Hoja } from './HojasCategoria';
import { BotonSecundario } from './SelectorCategorias';

/** Ayuda de obligatoriedad (lámina M07, reutilizada al asociar una existente: D46). */
export const AYUDA_OBLIGATORIEDAD = (cat: string) =>
  `Afecta solo a registros nuevos de ${cat}. Una obligatoria bloquea el registro hasta informarla.`;
export const AVISO_DESHABILITADA = (cat: string, mag: string) =>
  `Esta magnitud está deshabilitada. ${cat} no podrá usarse en registros nuevos mientras «${mag}» siga deshabilitada. Añadirla no la rehabilita.`;
export const TEXTO_HACER_OBLIGATORIA = (cat: string, mag: string) =>
  `A partir de ahora, registrar en ${cat} exigirá informar «${mag}». Los registros anteriores no cambian ni se revisan.`;
export const TEXTO_HACER_OPCIONAL = (cat: string, mag: string) =>
  `A partir de ahora, registrar en ${cat} no exigirá informar «${mag}». Los registros anteriores no cambian ni se revisan.`;
/** Mensaje seguro de AJ-S7MAG-06 (M12): N son registros de la MAGNITUD, nunca se atribuyen a la asociación. */
export function textoQuitar(cat: string, nHechos: number | null): string {
  const historia = nHechos === null
    ? 'Retirar su asociación con la categoría no modifica los registros históricos.'
    : `Esta magnitud aparece en ${nHechos} ${nHechos === 1 ? 'registro histórico' : 'registros históricos'}. Retirar su asociación con la categoría no modifica esos registros.`;
  return `${historia} ${cat} dejará de pedirla en registros nuevos; la magnitud sigue existiendo y puede volver a añadirse.`;
}

export type TonoPildora = 'OBLIGATORIA' | 'OPCIONAL' | 'DESHABILITADA';

/** Píldora de estado: borde y texto (el texto lleva el significado; el color solo acompaña). */
export function Pildora(p: { texto: string; tono: TonoPildora; testID?: string }) {
  const { c } = useTema();
  const color = p.tono === 'OBLIGATORIA' ? c.accent : p.tono === 'DESHABILITADA' ? c.warning : c.textSecondary;
  const fondo = p.tono === 'DESHABILITADA' ? c.partialSurface : c.surfacePrimary;
  return (
    <View testID={p.testID} style={[s.pildora, { borderColor: color, backgroundColor: fondo }]}>
      <Text style={[tipo.caption, { color }]}>{p.texto}</Text>
    </View>
  );
}

// ------------------------------------------------------------------ Añadir una existente (M06 -> M09)
export function HojaAnadirExistente(p: {
  categoria: string;
  magnitud: MagnitudCatalogo;
  guardando: boolean;
  onAnadir: (obligatoria: boolean) => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const [obligatoria, setObligatoria] = useState<boolean | null>(null);
  return (
    <Hoja titulo={`Añadir «${p.magnitud.nombre}» a ${p.categoria}`} testID="hoja-anadir-magnitud">
      {p.magnitud.enabled ? null : (
        <Aviso testID="anadir-aviso-deshabilitada" texto={AVISO_DESHABILITADA(p.categoria, p.magnitud.nombre)} />
      )}
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`En ${p.categoria}`}</Text>
      <Segmentado<boolean>
        testIDBase="anadir-obligatoria"
        etiquetaGrupo={`En ${p.categoria}`}
        opciones={[{ valor: true, etiqueta: 'Obligatoria' }, { valor: false, etiqueta: 'Opcional' }]}
        valor={obligatoria}
        onCambiar={setObligatoria}
      />
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{AYUDA_OBLIGATORIEDAD(p.categoria)}</Text>
      <BotonPrimario
        testID="anadir-confirmar"
        titulo={p.magnitud.enabled ? `Añadir a ${p.categoria}` : 'Añadir de todos modos'}
        cargando={p.guardando}
        deshabilitado={obligatoria === null || p.guardando}
        ayuda={obligatoria === null ? 'Falta elegir si es obligatoria u opcional.' : undefined}
        onPress={() => obligatoria !== null && p.onAnadir(obligatoria)}
      />
      <BotonSecundario testID="anadir-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

// ------------------------------------------------------------------ Obligatoriedad (M11)
export function HojaObligatoriedad(p: {
  categoria: string;
  magnitud: string;
  /** Valor ACTUAL de la asociación; la hoja propone el contrario. */
  obligatoria: boolean;
  guardando: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const aObligatoria = !p.obligatoria;
  return (
    <Hoja titulo={aObligatoria ? `¿Obligatoria en ${p.categoria}?` : `¿Opcional en ${p.categoria}?`} testID="hoja-obligatoriedad">
      <Text testID="obligatoriedad-texto" style={[tipo.body, { color: c.textPrimary }]}>
        {aObligatoria ? TEXTO_HACER_OBLIGATORIA(p.categoria, p.magnitud) : TEXTO_HACER_OPCIONAL(p.categoria, p.magnitud)}
      </Text>
      <BotonPrimario
        testID="obligatoriedad-confirmar"
        titulo={aObligatoria ? 'Hacer obligatoria' : 'Hacer opcional'}
        cargando={p.guardando}
        deshabilitado={p.guardando}
        onPress={p.onConfirmar}
      />
      <BotonSecundario testID="obligatoriedad-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

// ------------------------------------------------------------------ Quitar de la categoría (M12)
export function HojaQuitar(p: {
  categoria: string;
  magnitud: string;
  nHechos: number | null;
  guardando: boolean;
  onQuitar: () => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  return (
    <Hoja titulo={`Quitar «${p.magnitud}» de ${p.categoria}`} testID="hoja-quitar">
      <Text testID="quitar-texto" style={[tipo.body, { color: c.textPrimary }]}>{textoQuitar(p.categoria, p.nHechos)}</Text>
      <BotonCritico testID="quitar-confirmar" titulo={`Quitar de ${p.categoria}`} deshabilitado={p.guardando} onPress={p.onQuitar} />
      <BotonSecundario testID="quitar-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  pildora: { borderWidth: 1, borderRadius: radio.pill, paddingHorizontal: espacio.s, paddingVertical: 2, alignSelf: 'center' },
});
