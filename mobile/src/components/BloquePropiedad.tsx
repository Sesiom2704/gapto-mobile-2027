// ============================================================
// GAPTO MOBILE 2027
// Fichero: BloquePropiedad.tsx
// Ruta: mobile/src/components/BloquePropiedad.tsx
// Descripción: CAT-VIV (T2-F06, bloque 3) · bloque «Propiedad» de «Registrar gasto» y de «Registrar desde la previsión» cuando la categoría está «Asociada a vivienda» (lámina SET-CAT/REG-CAT v1.0 R01–R03 y R06; OBL-VIV-01): selector OBLIGATORIO de propiedad (chips con tus propiedades activas) con «Falta: la propiedad.», reparto propuesto según la titularidad en la fecha del gasto (visible y marcado, con «No lo sé»; nunca 100 % mío por defecto), «¿Qué tipo de gasto es?» (Gasto corriente por defecto · Reparación; nunca Mejora) y «¿Quién pagó?» de PAG con la deuda del cotitular preseleccionada y desmarcable (DM-07, L-08) y su confirmación visible. La propuesta se relee al cambiar la fecha, la propiedad o la cuenta; lo que tocó el usuario se conserva.
// Versión: 0.1.0 (F06 T2-F06 CAT-VIV N1 (L-04, lámina SET-CAT/REG-CAT v1.0))
// Versión: 0.1.1 (F06 T2-F06 CAT-VIV N1, capturas del paso 11): el reparto propuesto («Según la titularidad…») va en columna para que el texto largo se ajuste al ancho (antes desbordaba el formulario en R02/R03).
// Versión: 0.1.2 (F06 T2-F06 CAT-VIV N1, repetición de capturas sobre 8146e24): «Sí / No, no me debe nada…» de la deuda también en columna (desbordaba con Dynamic Type en R03).
// Versión: 0.2.0 (F06 T6 · S6 N1 conservador; dictamen 1 Q3/A4, DF-14, F09 0.55 §12.107.3; enmienda Q-CV-04 / B3 AJ-11): se retira «¿Qué tipo de gasto es?» (chips Gasto corriente / Reparación). La selección conserva `clase` = GASTO_CORRIENTE, el valor por defecto que ya se enviaba: el payload es idéntico. El servidor no cambia y sigue aceptando REPARACION (equivalencia en test_323).
// ============================================================

import React, { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { ClientePatrimonioB3, PropuestaGasto } from '../api/patrimonio_b3';
import type { ClientePropiedades, FilaPropiedad } from '../api/propiedades';
import { hayPropuesta, textoPropuesta, TEXTO_SIN_TITULARIDAD } from '../domain/gasto_propiedad';
import { formatearEur } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import {
  ClaseRegistro,
  conDeudas,
  conPropuesta,
  esDeOtros,
  opcionesPagoVivienda,
  partesDe,
  resumenConfirmacion,
  seleccionInicial,
  SeleccionPropiedad,
  TEXTO_DE_OTROS,
  TEXTO_EXIGE_PROPIEDAD,
  TEXTO_GASTO_CORRIENTE,
  TEXTO_NO_LO_SE_PROPIEDAD,
  textoPartes,
} from '../domain/propiedad_registro';
import { necesitaCuenta, propuestas, saleDeMisCuentas, TEXTO_NO_ES_MOVIMIENTO, TEXTO_QUIEN_PAGO, TEXTO_SIN_MOVIMIENTO } from '../domain/quien_pago';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { Chip, EstadoDato } from './Basicos';
import { estilosFormulario as ef } from './Formulario';


export function BloquePropiedad(p: {
  testID: string;
  propiedades: ClientePropiedades;
  patrimonio: ClientePatrimonioB3;
  fecha: string;
  cuentaId: string | null;
  importe: string;
  valor: SeleccionPropiedad | null;
  onCambiar: (s: SeleccionPropiedad | null) => void;
  /** Propuesta releída: el padre la aplica sobre su estado vigente (no pisa lo que el usuario tocó mientras llegaba). */
  onPropuesta: (propiedadId: string, prop: PropuestaGasto) => void;
  error?: string | null;
  bloqueado?: boolean;
  /** Oculta «¿Qué tipo de gasto es?» y «¿Quién pagó?» (no se usa en el registro; reservado). */
  soloPropiedad?: boolean;
}) {
  const { c } = useTema();
  const [lista, setLista] = useState<FilaPropiedad[] | null>(null);
  const [errorLista, setErrorLista] = useState(false);

  useEffect(() => {
    let vivo = true;
    void p.propiedades.listarPropiedades().then((r) => {
      if (!vivo) return;
      if (r.tipo === 'OK') setLista(r.datos.propiedades.filter((x) => x.enabled));
      else setErrorLista(true);
    });
    return () => { vivo = false; };
  }, [p.propiedades]);

  // Relectura de la propuesta en la fecha del gasto (con la cuenta: solo dice si es compartida).
  useEffect(() => {
    const s = p.valor;
    if (!s || !esFechaIso(p.fecha)) return;
    let vivo = true;
    void p.patrimonio.propuestaGasto(s.propiedadId, p.fecha, p.cuentaId).then((r) => {
      if (!vivo) return;
      const prop: PropuestaGasto = r.tipo === 'OK' ? r.datos
        : { fecha: p.fecha, propiedad_id: s.propiedadId, nombre: s.nombre, titularidad_disponible: false, partes: [], cuenta: null };
      p.onPropuesta(s.propiedadId, prop);
    });
    return () => { vivo = false; };
  }, [p.valor?.propiedadId, p.fecha, p.cuentaId]); // eslint-disable-line react-hooks/exhaustive-deps

  const s = p.valor;
  const set = (x: Partial<SeleccionPropiedad>, recalcular = true) => {
    if (!s || p.bloqueado) return;
    const n = { ...s, ...x };
    p.onCambiar(recalcular ? conDeudas(n, p.importe) : n);
  };
  const partes = s ? partesDe(s) : [];
  const deudas = s && s.propuesta ? propuestas(s.pago, p.importe, partes) : [];
  const opciones = s && s.propuesta ? opcionesPagoVivienda(s) : [];
  const conCotitulares = opciones.length > 1;

  return (
    <View testID={p.testID} style={{ gap: espacio.s }}>
      <Text testID={`${p.testID}-exige`} style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_EXIGE_PROPIEDAD}</Text>
      {lista === null && !errorLista ? <EstadoDato testID={`${p.testID}-cargando`} estado="CARGANDO" /> : null}
      {errorLista ? <EstadoDato testID={`${p.testID}-error-lista`} estado="ERROR_CARGA" detalle="No se pudieron cargar tus propiedades" /> : null}
      {lista !== null && lista.length === 0 ? (
        <EstadoDato testID={`${p.testID}-sin`} estado="NO_DISPONIBLE" detalle="No tienes propiedades: da de alta una en Patrimonio" />
      ) : null}
      {lista !== null && lista.length > 0 ? (
        <View style={ef.chips}>
          {lista.map((x) => (
            <Chip key={x.id} testID={`${p.testID}-prop-${x.id}`} etiqueta={x.nombre} seleccionado={s?.propiedadId === x.id}
              onPress={() => !p.bloqueado && p.onCambiar(s?.propiedadId === x.id ? s : seleccionInicial(x.id, x.nombre))} />
          ))}
        </View>
      ) : null}
      {p.error ? <Text testID={`${p.testID}-error`} accessibilityRole="alert" style={[tipo.footnote, { color: c.criticalText }]}>{p.error}</Text> : null}
      {s && s.propuesta === null ? <EstadoDato testID={`${p.testID}-propuesta-cargando`} estado="CARGANDO" /> : null}
      {s && s.propuesta !== null && esDeOtros(s) ? (
        <Text testID={`${p.testID}-de-otros`} style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_DE_OTROS}</Text>
      ) : null}
      {s && s.propuesta !== null && !esDeOtros(s) && !p.soloPropiedad ? (
        <>
          <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>¿De quién es el gasto?</Text>
          <View style={lc.columna}>
            {hayPropuesta(s.propuesta) ? (
              <Chip testID={`${p.testID}-titularidad`} etiqueta={textoPropuesta(s.nombre, s.propuesta)} seleccionado={s.reparto?.modo === 'TITULARIDAD'}
                onPress={() => set({ reparto: { modo: 'TITULARIDAD' }, repartoTocado: true })} />
            ) : null}
            <Chip testID={`${p.testID}-no-lo-se`} etiqueta={TEXTO_NO_LO_SE_PROPIEDAD} seleccionado={s.reparto?.modo === 'NO_LO_SE'}
              onPress={() => set({ reparto: { modo: 'NO_LO_SE' }, repartoTocado: true })} />
          </View>
          {!hayPropuesta(s.propuesta) ? (
            <Text testID={`${p.testID}-sin-titularidad`} style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_SIN_TITULARIDAD}</Text>
          ) : null}
          {textoPartes(s, p.importe) ? <Text testID={`${p.testID}-partes`} style={[tipo.footnote, { color: c.textSecondary }]}>{textoPartes(s, p.importe)}</Text> : null}

          {/* F06 T6 · S6 (dictamen 1 Q3/A4, DF-14): sin «¿Qué tipo de gasto es?»; la clase queda en GASTO_CORRIENTE, lo que ya se enviaba por defecto. */}
          <Text testID={`${p.testID}-corriente`} style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_GASTO_CORRIENTE}</Text>

          {conCotitulares ? (
            <>
              <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{TEXTO_QUIEN_PAGO}</Text>
              <View style={ef.chips}>
                {opciones.map((o) => (
                  <Chip key={o.clave} testID={`${p.testID}-quien-${o.clave}`} etiqueta={o.etiqueta}
                    seleccionado={s.pago.modo === o.modo && (o.pagadorId === null || s.pago.pagadorId === o.pagadorId)}
                    onPress={() => set({ pago: { ...s.pago, modo: o.modo, pagadorId: o.pagadorId }, deudasTocadas: false })} />
                ))}
              </View>
              {s.pago.modo !== null && !necesitaCuenta(s.pago) ? (
                <Text testID={`${p.testID}-sin-cuenta`} style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_MOVIMIENTO}</Text>
              ) : null}
              {deudas.map((d) => {
                const marcada = s.deudas[d.actor_id]?.marcada ?? true;
                const marcar = (v: boolean) =>
                  set({ deudas: { ...s.deudas, [d.actor_id]: { marcada: v, importe: s.deudas[d.actor_id]?.importe ?? d.maximo } }, deudasTocadas: true }, false);
                return (
                  <View key={d.actor_id} testID={`${p.testID}-deuda-${d.actor_id}`} style={{ gap: espacio.xs }}>
                    <Text style={[tipo.body, { color: c.textPrimary }]}>
                      {d.sentido === 'ME_DEBE' ? `${d.nombre} te debe su parte (${formatearEur(d.maximo)})` : `¿Le debes su parte (${formatearEur(d.maximo)}) a ${d.nombre}?`}
                    </Text>
                    <View style={lc.columna}>
                      <Chip testID={`${p.testID}-deuda-${d.actor_id}-si`} etiqueta="Sí" seleccionado={marcada} onPress={() => marcar(true)} />
                      <Chip testID={`${p.testID}-deuda-${d.actor_id}-no`}
                        etiqueta={d.sentido === 'ME_DEBE' ? 'No, no me debe nada (ya está saldado o le invito)' : 'No, no le debo nada (ya está saldado)'}
                        seleccionado={!marcada} onPress={() => marcar(false)} />
                    </View>
                  </View>
                );
              })}
              {deudas.length > 0 ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NO_ES_MOVIMIENTO}</Text> : null}
            </>
          ) : null}
          {s.pago.modo !== null && s.reparto !== null ? (
            <View testID={`${p.testID}-confirmacion`} style={{ gap: espacio.xs }}>
              {necesitaCuenta(s.pago) ? (
                <Text testID={`${p.testID}-sale`} style={[tipo.footnote, { color: c.textPrimary }]}>
                  {`Sale de tu cuenta: −${formatearEur(saleDeMisCuentas(s.pago, p.importe, partes.length > 0 ? partes : [{ actor_id: 'YO', porcentaje: '100', yo: true, nombre: null, naturaleza: null }]))}`}
                </Text>
              ) : null}
              {resumenConfirmacion(s, p.importe) ? (
                <Text testID={`${p.testID}-resumen`} style={[tipo.footnote, { color: c.textPrimary }]}>{resumenConfirmacion(s, p.importe)}</Text>
              ) : null}
            </View>
          ) : null}
        </>
      ) : null}
    </View>
  );
}

const lc = StyleSheet.create({
  columna: { gap: espacio.s },
});
