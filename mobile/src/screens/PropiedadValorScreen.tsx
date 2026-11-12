// ============================================================
// GAPTO MOBILE 2027
// Fichero: PropiedadValorScreen.tsx
// Ruta: mobile/src/screens/PropiedadValorScreen.tsx
// Descripción: Valor de una propiedad (F06-01 B1 · C-PROP-04 alta y L-PROP; lámina F06-01 v0.9 D3 Revisar valor y v0.1 B2 Histórico). D3: nueva valoración del inmueble completo (100 %) con fecha y método obligatorios entre Mercado, Tasación, Manual y Valor de referencia (ya no ofrece «Compra»: la crea solo la compra); «Esto es una estimación: no cambia el coste ni tu dinero». B2: histórico del más reciente al más antiguo, solo lectura; las valoraciones sin fecha, al final como evidencia; la referencia fiscal nunca se presenta como valor de mercado; un valor que cambia se registra como valoración nueva y conserva la anterior. VERSION_DESFASADA → D4 Recargar.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// Versión: 0.2.0 (F06-01 B1 MANT N3 del selector, AJ-B1C-01 / PC-B1-04 opción A): la fecha de D3 se elige con «Hoy · Ayer · Otra fecha», el patrón de AbonoHoja (propuesta Hoy; Hoy y Ayer en la fecha civil del dispositivo con `isoLocal` y `ayer` de domain/fechas; «Otra fecha» abre el campo dd/mm/aaaa y solo admite una fecha que exista en el calendario, `esFechaIso`). Sin límite nuevo: C-PROP-04 solo exige una fecha (`fecha_valoracion: date`, no nula). La petición no cambia (fecha_valoracion ISO).
// Versión: 0.3.0 (F06 T1 UX-1 · M-07, DM-06: la fecha usa el componente único `CampoFecha` (chips, campo dd/mm/aaaa con máscara y calendario en JS); se conservan el estado, las reglas de cada campo, los testID y los textos de validación; sin mínimo ni máximo, C-PROP-04; con D-M2-04 acepta años 0001–0099, p. ej. 0050-06-15).
// ============================================================

import React, { useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClientePropiedades, Valoracion, VistaPropiedad } from '../api/propiedades';
import { BotonPrimario, CabeceraNavegacion, Chip, EstadoDato } from '../components/Basicos';
import { CampoFecha } from '../components/CampoFecha';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef, Tarjeta } from '../components/Formulario';
import { ayer, ddmmaaaaAIso, diaMesAnioIso, fechaCortaIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import { detalleValoracion, METODOS_ELEGIBLES, MetodoValoracion, TEXTO_INDETERMINADO_PROP, textoErrorB1 } from '../domain/propiedad';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';
import { ConflictoPropiedad } from './PropiedadEditarScreen';

export const TEXTO_ESTIMACION = 'Esto es una estimación: no cambia el coste ni tu dinero.';
export const TEXTO_SIN_FECHA = 'Una valoración sin fecha se conserva como evidencia, pero no se usa como punto de la evolución del patrimonio.';
export const TEXTO_CAMBIO_VALOR = 'Si el valor ha cambiado, añade una valoración nueva: la anterior se conserva.';

type Elegible = Exclude<MetodoValoracion, 'COMPRA'>;
interface FormValor {
  valor: string;
  /** ISO (Hoy, Ayer u Otra fecha válida) o el texto escrito en «Otra fecha» mientras no es una fecha. */
  fecha: string;
  metodo: Elegible | null;
  fuente: string;
}

/** Histórico B2: con fecha del más reciente al más antiguo (empate: id descendente); sin fecha, al final. */
export function ordenHistorico(vs: Valoracion[]): Valoracion[] {
  const conFecha = vs.filter((v) => v.fecha_valoracion).sort((a, b) => (a.fecha_valoracion! < b.fecha_valoracion! ? 1 : a.fecha_valoracion! > b.fecha_valoracion! ? -1 : a.id < b.id ? 1 : -1));
  return [...conFecha, ...vs.filter((v) => !v.fecha_valoracion)];
}

export function faltaValor(f: FormValor): string[] {
  const r: string[] = [];
  if (!parsearImporte(f.valor).ok) r.push('valor mayor que 0 con 2 decimales como mucho');
  if (!esFechaIso(f.fecha)) r.push('fecha como dd/mm/aaaa');
  if (f.metodo === null) r.push('de dónde sale');
  return r;
}

/** D3: nueva valoración. */
export function ValoracionFormScreen(p: {
  propiedades: ClientePropiedades;
  vista: VistaPropiedad;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (actualizada: VistaPropiedad | null) => void;
  onRecargar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  // Fecha civil del dispositivo, como AbonoHoja: propuesta Hoy; el chip deja de marcarse si cambia el día.
  const hoyIso = isoLocal(p.ahora());
  const ayerIso = isoLocal(ayer(p.ahora()));
  const [f, setF] = useState<FormValor>(() => ({ valor: '', fecha: hoyIso, metodo: null, fuente: '' }));
  const [otraFecha, setOtraFecha] = useState<string | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [conflicto, setConflicto] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const id = useRef(p.nuevoId());
  const faltas = faltaValor(f);
  const ultimo = p.vista.valor_estimado;

  const guardar = async () => {
    if (ocupado || faltas.length > 0) return;
    setOcupado(true);
    setAviso(null);
    const imp = parsearImporte(f.valor);
    const r = await p.propiedades.altaValoracion(p.vista.id, {
      intencion_id: id.current,
      row_version_esperada: p.vista.row_version,
      valor_total: imp.ok ? imp.valor : f.valor,
      fecha_valoracion: f.fecha,
      metodo: f.metodo!,
      fuente: f.fuente.trim() ? f.fuente.trim() : null,
      notas: null,
    });
    setOcupado(false);
    if (r.tipo === 'OK') return p.onCerrar(r.datos.propiedad);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO_PROP });
    if (r.codigo === 'VERSION_DESFASADA') return setConflicto(true);
    setAviso({ tipo: 'AVISO', texto: textoErrorB1(r.codigo, r.mensaje) });
  };

  if (conflicto) return <ConflictoPropiedad titulo="Revisar valor" onCancelar={() => p.onCerrar(null)} onRecargar={p.onRecargar} />;

  return (
    <View testID="prop-val-nueva" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo="Revisar valor" testIDCancelar="prop-val-cancelar" onCancelar={() => p.onCerrar(null)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="prop-val-aviso" aviso={aviso} /> : null}
        <View testID="prop-val-ultimo" style={{ gap: 2 }}>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>Último valor</Text>
          {ultimo ? (
            <>
              <Text style={[tipo.titleMedium, { color: c.textPrimary }]}>{formatearEur(ultimo.valor_total)}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>{detalleValoracion(ultimo, diaMesAnioIso)}</Text>
            </>
          ) : (
            <EstadoDato estado="NO_DISPONIBLE" />
          )}
        </View>
        <Campo etiqueta="¿Cuánto vale hoy el inmueble completo?">
          <CampoTexto testID="prop-val-valor" etiqueta="Valor del inmueble completo" marcador="Ej.: 250.000,00" valor={f.valor} onCambiar={(t) => setF({ ...f, valor: t })} />
        </Campo>
        <Campo etiqueta="Fecha">
          <CampoFecha
            testID="prop-val-fecha"
            etiqueta="Fecha del valor, día barra mes barra año"
            hoyIso={hoyIso}
            texto={otraFecha}
            onTexto={(t) => { setOtraFecha(t); setF({ ...f, fecha: ddmmaaaaAIso(t) ?? t }); }}
            opciones={[
              { testID: 'prop-val-hoy', etiqueta: 'Hoy', seleccionado: otraFecha === null && f.fecha === hoyIso, onPress: () => { setOtraFecha(null); setF({ ...f, fecha: hoyIso }); } },
              { testID: 'prop-val-ayer', etiqueta: 'Ayer', seleccionado: otraFecha === null && f.fecha === ayerIso, onPress: () => { setOtraFecha(null); setF({ ...f, fecha: ayerIso }); } },
              { testID: 'prop-val-otra', etiqueta: 'Otra fecha', seleccionado: otraFecha !== null, onPress: () => setOtraFecha(esFechaIso(f.fecha) ? isoADdmmaaaa(f.fecha) : f.fecha) },
            ]}
          />
          <Text testID="prop-val-fecha-elegida" style={[tipo.footnote, { color: c.textSecondary }]}>
            {esFechaIso(f.fecha) ? fechaCortaIso(f.fecha) : 'Escribe la fecha como dd/mm/aaaa.'}
          </Text>
        </Campo>
        <Campo etiqueta="¿De dónde sale?">
          <View style={ef.chips}>
            {METODOS_ELEGIBLES.map((m) => (
              <Chip key={m.valor} testID={`prop-val-metodo-${m.valor}`} etiqueta={m.etiqueta} seleccionado={f.metodo === m.valor} onPress={() => setF({ ...f, metodo: m.valor })} />
            ))}
          </View>
        </Campo>
        <Campo etiqueta="Fuente" opcional>
          <CampoTexto testID="prop-val-fuente" etiqueta="Fuente" marcador="Escritura, portal, tasadora…" valor={f.fuente} maximo={160} onCambiar={(t) => setF({ ...f, fuente: t })} />
        </Campo>
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_ESTIMACION}</Text>
        <BotonPrimario
          testID="prop-val-guardar"
          titulo={ocupado ? 'Guardando…' : 'Guardar valoración'}
          cargando={ocupado}
          deshabilitado={faltas.length > 0}
          ayuda={faltas.length > 0 ? `Falta: ${faltas.join(', ')}` : undefined}
          onPress={() => void guardar()}
        />
        {faltas.length > 0 ? <Text testID="prop-val-falta" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}`}</Text> : null}
      </ScrollView>
    </View>
  );
}

/** B2 Histórico (solo lectura). */
export function HistoricoValoracionesScreen(p: { vista: VistaPropiedad; onAtras: () => void; onNueva: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const lista = ordenHistorico(p.vista.valoraciones);
  const haySinFecha = lista.some((v) => !v.fecha_valoracion);

  return (
    <View testID="prop-val-historico" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo="Histórico de valoraciones" atras={{ etiqueta: 'Resumen', onPress: p.onAtras }} testIDAtras="prop-val-historico-atras" />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {lista.length === 0 ? <EstadoDato testID="prop-val-historico-vacio" estado="NO_DISPONIBLE" detalle="Aún no hay valoraciones" /> : null}
        {lista.length > 0 ? (
          <Tarjeta>
            {lista.map((v, i) => (
              <View key={v.id} testID={`prop-val-fila-${v.id}`}
                style={[s.fila, i < lista.length - 1 && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{formatearEur(v.valor_total)}</Text>
                  <Text style={[tipo.caption, { color: c.textSecondary }]}>{detalleValoracion(v, diaMesAnioIso)}</Text>
                </View>
              </View>
            ))}
          </Tarjeta>
        ) : null}
        {haySinFecha ? <Text testID="prop-val-sin-fecha" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_FECHA}</Text> : null}
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CAMBIO_VALOR}</Text>
        <BotonPrimario testID="prop-val-historico-nueva" titulo="Añadir valoración" onPress={p.onNueva} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.m, minHeight: TACTIL_MIN + 8 },
});
