// ============================================================
// GAPTO MOBILE 2027
// Fichero: HojasMagnitud.tsx
// Ruta: mobile/src/components/HojasMagnitud.tsx
// Descripción: Hojas y piezas de presentación de las magnitudes de una categoría (F09 §12.97.10; lámina SET-MAG v0.1; F05-D020). Solo presentación: no llaman al cliente; el controlador (MagnitudesCategoria.tsx) decide el comando y trata los rechazos. Píldoras de estado con TEXTO («Obligatoria», «Opcional», «Deshabilitada»), nunca solo color. Hito 1: añadir una magnitud existente (M09: aviso previo si está deshabilitada, «Añadir de todos modos»; la obligatoriedad se elige siempre, sin preselección), cambiar obligatoriedad (M11, guarda prospectiva) y quitar de la categoría (M12, mensaje seguro de AJ-S7MAG-06 con N = registros históricos de la magnitud). Consume solo tokens semánticos.
// Versión: 0.1.0 (F05-01 S7-MAG UI, hito 1)
// Versión: 0.2.0 (F05-01 S7-MAG UI, hito 2): renombrar la magnitud (microcopy de M13; colisión junto al nombre), deshabilitar con impacto calculado por el servidor bajo lock (M14) y «El impacto ha cambiado» con la lista nueva (M15), y rehabilitar con confirmación simple.
// Versión: 0.3.0 (F05-01 S7-MAG UI, D59 aprobada por Moisés): deshabilitar SIN impacto pide una confirmación simple «¿Deshabilitar «X»?» antes de enviar.
// ============================================================

import React, { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import type { FilaImpacto, MagnitudCatalogo } from '../domain/magnitud';
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

// ------------------------------------------------------------------ Renombrar la magnitud (M13)
export const MICROCOPY_RENOMBRAR_MAGNITUD =
  'Renombrar corrige el nombre también en lo ya registrado. Si cambia su significado, crea otra magnitud y deshabilita esta.';

export function HojaRenombrarMagnitud(p: {
  magnitud: string;
  guardando: boolean;
  errorNombre: string | null;
  onLimpiarError: () => void;
  onGuardar: (nombre: string) => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  const [nombre, setNombre] = useState(p.magnitud);
  const limpio = nombre.trim();
  return (
    <Hoja titulo={`Renombrar «${p.magnitud}»`} testID="hoja-renombrar-magnitud">
      <TextInput
        testID="renmag-nombre"
        accessibilityLabel="Nuevo nombre"
        value={nombre}
        onChangeText={(t) => { setNombre(t); p.onLimpiarError(); }}
        editable={!p.guardando}
        maxLength={400}
        style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: p.errorNombre ? c.critical : c.borderStandard }]}
      />
      {p.errorNombre ? <Text testID="renmag-error" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{p.errorNombre}</Text> : null}
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{MICROCOPY_RENOMBRAR_MAGNITUD}</Text>
      <BotonPrimario
        testID="renmag-guardar"
        titulo="Guardar nombre"
        cargando={p.guardando}
        deshabilitado={limpio === '' || limpio === p.magnitud || p.guardando}
        onPress={() => p.onGuardar(limpio)}
      />
      <BotonSecundario testID="renmag-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

// ------------------------------------------------------------------ Deshabilitar (M14 / M15)
export const TEXTO_DESHABILITAR =
  'Es obligatoria en estas categorías, que dejarán de poder usarse en registros nuevos hasta que la rehabilites o la hagas opcional:';
export const NOTA_DESHABILITAR = 'Nada de lo ya registrado cambia. No se quita de ninguna categoría.';
export const IMPACTO_CAMBIADO = {
  titulo: 'El impacto ha cambiado',
  texto: 'Mientras confirmabas, otra categoría ha empezado a usar esta magnitud. Revisa la lista y confirma de nuevo.',
};

export function HojaDeshabilitar(p: {
  magnitud: string;
  filas: FilaImpacto[];
  cambiado: boolean;
  guardando: boolean;
  onDeshabilitar: () => void;
  onCancelar: () => void;
}) {
  const { c } = useTema();
  return (
    <Hoja titulo={`Deshabilitar «${p.magnitud}»`} testID="hoja-deshabilitar">
      {p.cambiado ? (
        <View testID="deshabilitar-cambiado" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
          <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{IMPACTO_CAMBIADO.titulo}</Text>
          <Text style={[tipo.footnote, { color: c.textPrimary }]}>{IMPACTO_CAMBIADO.texto}</Text>
        </View>
      ) : (
        <Text style={[tipo.body, { color: c.textPrimary }]}>{TEXTO_DESHABILITAR}</Text>
      )}
      <View>
        {p.filas.map((f) => (
          <View key={f.id} testID={`impacto-${f.id}`} accessible accessibilityLabel={`${f.nombre}: ${f.etiqueta}`} style={[s.filaImpacto, { borderBottomColor: c.separator }]}>
            <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{f.nombre}</Text>
            <Text style={[tipo.caption, { color: c.textSecondary }]}>{f.etiqueta}</Text>
          </View>
        ))}
      </View>
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{NOTA_DESHABILITAR}</Text>
      <BotonCritico testID="deshabilitar-confirmar" titulo="Deshabilitar de todos modos" deshabilitado={p.guardando} onPress={p.onDeshabilitar} />
      <BotonSecundario testID="deshabilitar-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

// ------------------------------------------------------------------ Deshabilitar sin impacto (D59)
export const TEXTO_CONFIRMAR_DESHABILITAR = 'Dejará de poder pedirse en registros nuevos. Lo ya registrado no cambia.';

export function HojaConfirmarDeshabilitar(p: { magnitud: string; guardando: boolean; onDeshabilitar: () => void; onCancelar: () => void }) {
  const { c } = useTema();
  return (
    <Hoja titulo={`¿Deshabilitar «${p.magnitud}»?`} testID="hoja-confirmar-deshabilitar">
      <Text style={[tipo.body, { color: c.textPrimary }]}>{TEXTO_CONFIRMAR_DESHABILITAR}</Text>
      <BotonCritico testID="confirmar-deshabilitar" titulo="Deshabilitar" deshabilitado={p.guardando} onPress={p.onDeshabilitar} />
      <BotonSecundario testID="confirmar-deshabilitar-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

// ------------------------------------------------------------------ Rehabilitar
export const TEXTO_REHABILITAR = 'Volverá a poder pedirse en las categorías que la usan. Lo ya registrado no cambia.';

export function HojaRehabilitar(p: { magnitud: string; guardando: boolean; onRehabilitar: () => void; onCancelar: () => void }) {
  const { c } = useTema();
  return (
    <Hoja titulo={`Rehabilitar «${p.magnitud}»`} testID="hoja-rehabilitar">
      <Text style={[tipo.body, { color: c.textPrimary }]}>{TEXTO_REHABILITAR}</Text>
      <BotonPrimario testID="rehabilitar-confirmar" titulo="Rehabilitar" cargando={p.guardando} deshabilitado={p.guardando} onPress={p.onRehabilitar} />
      <BotonSecundario testID="rehabilitar-cancelar" titulo="Cancelar" onPress={p.onCancelar} />
    </Hoja>
  );
}

const s = StyleSheet.create({
  input: { borderWidth: 1, borderRadius: radio.m, paddingHorizontal: espacio.m, minHeight: 48 },
  aviso: { gap: 2, borderRadius: radio.m, padding: espacio.m },
  filaImpacto: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: 40, borderBottomWidth: StyleSheet.hairlineWidth },
  pildora: { borderWidth: 1, borderRadius: radio.pill, paddingHorizontal: espacio.s, paddingVertical: 2, alignSelf: 'center' },
});
