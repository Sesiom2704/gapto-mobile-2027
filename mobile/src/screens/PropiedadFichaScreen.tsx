// ============================================================
// GAPTO MOBILE 2027
// Fichero: PropiedadFichaScreen.tsx
// Ruta: mobile/src/screens/PropiedadFichaScreen.tsx
// Descripción: Ficha de una propiedad (F06-01 B1 · L-PROP; lámina F06-01 v0.9 D1 Resumen y D2 Sin datos). Cada magnitud por separado y con su procedencia: valor estimado (100 %) con método y fecha (una valoración futura no cuenta; la calcula el servidor), referencia fiscal aparte (nunca desplaza al estimado), tu titularidad y la «Cuota del valor según titularidad», etiquetada como vista estructural (no es una atribución ni dice quién pagó). Lo desconocido se queda desconocido: «No disponible» / «Sin indicar», nunca 0. Coste de adquisición, mejoras e inversión llegan con la compra (B2/B3): aquí «No disponible». Acciones de B1: Revisar valor, Histórico de valoraciones, Titularidad y Editar datos.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// ============================================================

import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { VistaPropiedad } from '../api/propiedades';
import { CabeceraNavegacion, EstadoDato } from '../components/Basicos';
import { estilosFormulario as ef, FilaLista, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { diaMesAnioIso } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import { etiquetaMetodo, etiquetaTipo, formatearPorcentaje, mesCortoAnioIso, MetodoValoracion, textoTitularidad, tuParticipacion } from '../domain/propiedad';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

export const TEXTO_CUOTA_ESTRUCTURAL = 'La cuota según titularidad es una vista del reparto de la propiedad: no es lo que se te atribuye ni dice quién pagó.';
export const TEXTO_INVERSION_VALOR = 'Inversión y valor no se suman ni se restan: son datos distintos.';

/** «Mercado · ene 2028». */
const procedencia = (metodo: MetodoValoracion, fecha: string | null) => `${etiquetaMetodo(metodo)} · ${fecha ? mesCortoAnioIso(fecha) : 'Sin fecha'}`;

export function PropiedadFichaScreen(p: {
  vista: VistaPropiedad;
  onAtras: () => void;
  onRevisarValor: () => void;
  onHistorico: () => void;
  onTitularidad: () => void;
  onEditar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const v = p.vista;
  const tu = tuParticipacion(v.titularidad);
  const sinDatos = !v.valor_estimado && !v.referencia_fiscal;

  return (
    <View testID="prop-ficha" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo={v.nombre} atras={{ etiqueta: 'Propiedades', onPress: p.onAtras }} testIDAtras="prop-ficha-atras" />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Text testID="prop-ficha-tipo" style={[tipo.footnote, { color: c.textSecondary }]}>
          {[etiquetaTipo(v.tipo_propiedad), v.fecha_adquisicion ? `adquirida el ${diaMesAnioIso(v.fecha_adquisicion)}` : 'adquisición desconocida'].join(' · ')}
        </Text>
        <RotuloGrupo texto="Resumen" />
        <Tarjeta testID="prop-resumen">
          <Magnitud testID="prop-valor-estimado" etiqueta="Valor estimado (100 %)" importe={v.valor_estimado?.valor_total ?? null}
            detalle={v.valor_estimado ? procedencia(v.valor_estimado.metodo, v.valor_estimado.fecha_valoracion) : null} />
          {v.referencia_fiscal ? (
            <Magnitud testID="prop-referencia-fiscal" etiqueta="Referencia fiscal" importe={v.referencia_fiscal.valor_total}
              detalle={v.referencia_fiscal.fecha_valoracion ? `Fiscal · ${diaMesAnioIso(v.referencia_fiscal.fecha_valoracion)}` : 'Sin fecha'} />
          ) : null}
          <Magnitud testID="prop-coste" etiqueta="Coste de adquisición" importe={null} detalle="Llega con el registro de la compra" />
          <Magnitud testID="prop-inversion" etiqueta="Inversión acumulada" importe={null} />
          <Fila testID="prop-tu-titularidad" etiqueta="Tu titularidad" valor={tu ?? (v.titularidad.modo === 'DE_OTROS' ? 'No eres titular' : 'Sin indicar')} />
          <Magnitud testID="prop-cuota" etiqueta="Cuota del valor según titularidad" ultima
            importe={v.cuota_segun_titularidad?.importe ?? null}
            detalle={v.cuota_segun_titularidad ? `Vista estructural · ${formatearPorcentaje(v.cuota_segun_titularidad.porcentaje)}` : tu ? 'Sin valor estimado' : 'Sin indicar'} />
        </Tarjeta>
        <Text testID="prop-ficha-nota" style={[tipo.footnote, { color: c.textSecondary }]}>{v.cuota_segun_titularidad ? TEXTO_CUOTA_ESTRUCTURAL : TEXTO_INVERSION_VALOR}</Text>
        {v.cambio_programado ? (
          <Text testID="prop-cambio-programado" style={[tipo.footnote, { color: c.warningText }]}>
            {`Cambio de reparto programado desde el ${diaMesAnioIso(v.cambio_programado.desde!)}: ${textoTitularidad(v.cambio_programado)}.`}
          </Text>
        ) : null}
        <RotuloGrupo texto="Más" />
        <Tarjeta>
          <FilaLista testID="prop-accion-valor" titulo="Revisar valor" detalle={sinDatos ? 'Para saber lo que vale' : undefined} onPress={p.onRevisarValor} />
          <FilaLista testID="prop-accion-historico" titulo="Histórico de valoraciones" detalle={`${v.valoraciones.length} ${v.valoraciones.length === 1 ? 'valoración' : 'valoraciones'}`} onPress={p.onHistorico} />
          <FilaLista testID="prop-accion-titularidad" titulo="Titularidad" detalle={textoTitularidad(v.titularidad)} onPress={p.onTitularidad} />
          <FilaLista testID="prop-accion-editar" titulo="Editar datos" ultima onPress={p.onEditar} />
        </Tarjeta>
      </ScrollView>
    </View>
  );
}

function Magnitud(p: { testID: string; etiqueta: string; importe: string | null; detalle?: string | null; ultima?: boolean }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={[s.fila, !p.ultima && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[tipo.body, { color: c.textPrimary }]}>{p.etiqueta}</Text>
        {p.detalle && p.importe !== null ? <Text testID={`${p.testID}-detalle`} style={[tipo.caption, { color: c.textSecondary }]}>{p.detalle}</Text> : null}
      </View>
      {p.importe !== null ? (
        <Text testID={`${p.testID}-importe`} style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{formatearEur(p.importe)}</Text>
      ) : (
        <EstadoDato testID={`${p.testID}-nd`} estado="NO_DISPONIBLE" />
      )}
    </View>
  );
}

function Fila(p: { testID: string; etiqueta: string; valor: string }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={[s.fila, { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
      <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{p.etiqueta}</Text>
      <Text testID={`${p.testID}-valor`} style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{p.valor}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.m },
});
