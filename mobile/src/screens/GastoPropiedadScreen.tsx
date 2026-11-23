// ============================================================
// GAPTO MOBILE 2027
// Fichero: GastoPropiedadScreen.tsx
// Ruta: mobile/src/screens/GastoPropiedadScreen.tsx
// Descripción: Obras y gastos de una propiedad (F06-01 B3; R1 v0.9.5 Parte III; lámina F06-01 v0.9 C1 Una pregunta por gasto con las TRES clases, C2 Resumen de la reforma, C3 Mejora histórica; boceto L-5 de la corrección de clase, R1_LAMINAS §2). Pantallas:
//   - `GastosPropiedadScreen`: tarea con su propia pila (lista C2 → detalle del gasto → «Corregir la clase»; «Añadir un gasto» y «Mejora antigua»).
//   - `GastoPropiedadScreen` (C-MEJ-01): datos (clase sin valor por defecto; Mejora oculta categoría y presupuesto) → «¿De quién es el gasto?» con la propuesta según la titularidad de la propiedad EN LA FECHA DEL HECHO marcada y visible (origen y fecha), «Otro reparto» y «No lo sé», y «Te debe su parte» por cotitular (Sí por defecto solo con cuenta solo tuya y persona; exclusiones de 8ter) → confirmación (8bis: quién debe, cuánto, concepto, parte atribuida, «Se creará un derecho de cobro» y la atribución que se persistirá) → hecho. ATRIBUCION_PROPUESTA_DESFASADA vuelve al reparto con la propuesta releída.
//   - `MejoraHistoricaScreen` (C-MEJ-02): sin pago ni «Te debe su parte».
//   - `CorregirClaseScreen` (C-MEJ-03): solo con `intencion_correccion_id`; clase actual → nueva; categoría y presupuesto sin valor previo al pasar a gasto; tabla Antes/Después de este gasto; motivo obligatorio; IMPACTO_CORRECCION_DESFASADO avisa y recarga la tabla.
//   Con deuda (8quater) el detalle no ofrece «Corregir la clase» y muestra la limitación literal; nunca propone anular y recrear ni la corrección de categoría como equivalentes. Todas las fechas con el CampoFecha de UX-1.
// Versión: 0.1.0 (F06 T1-F06 B3 N1)
// Versión: 0.2.0 (F06 T1-F06 B3 ajuste N3 · decisión de Moisés 2026-11-13 «B3 alcance y CAT-VIV» v1.0): el alta
//   (C-MEJ-01) solo ofrece «Reforma o mejora» (clase MEJORA preseleccionada, sin chips, sin categoría ni presupuesto);
//   los gastos corrientes y las reparaciones se registran desde «Registrar gasto». Lista «Reformas y mejoras · <propiedad>»
//   y botón «Añadir una reforma o mejora». La corrección de clase (C-MEJ-03) y la lista no cambian: siguen mostrando y
//   corrigiendo lo que haya, también reparaciones y gastos corrientes ya registrados.
// Versión: 0.2.2 (F06 T1-F06 B3 ajuste N3 · KO 2 de la prueba en iPhone, decisión de Moisés del 2026-11-13 «según tu recomendación»):
//   solo texto: «No, le invito» pasa a «No, no me debe nada (lo pagamos a medias o ya está saldado)». El modelo de pagador y deuda en
//   ambos sentidos (aportaciones) pasa al diseño del tren 2 con CAT-VIV. Sin cambios de comportamiento, contrato ni testID.
// Versión: 0.2.1 (F06 T1-F06 B3 ajuste N3 · KO visual iPhone casilla 7): las fechas de B3 (alta de reforma y mejora antigua)
//   muestran los chips «Hoy · Ayer · Otra fecha» con el patrón de RegistroGasto/PropiedadValor (Hoy por defecto, ≤ hoy).
// Versión: 0.2.3 (F06 T1-F06 B3 ajuste N3 · HT2-01 · decisión 1 de Moisés del 2026-11-14, F06-00_Decisiones_Moises_2026-11-14_HT2-01_y_Q-29_v1.0
//   SHA 6ba8afd3…a9cbc0; parche del laboratorio lote 30): el «No» de «¿Te debe su parte?» deja de decir «lo pagamos a medias»
//   («No, no me debe nada (ya está saldado o le invito)») y se avisa de que el pago a medias aún no se puede registrar bien
//   (testID gprop-aviso-a-medias). Solo texto; sin backend, contrato ni DDL. R-L29-05 / HT2-01 sigue ALTO y abierto (receptor PAG, tren 2).
// Versión: 0.3.0 (F06 T2-F06 PAG N1; reapertura acotada de B3 por L-02; contrato operativo único del mandato PAG §1.1 y §1.4):
//   - alta en cuatro pasos: datos → «¿Quién pagó?» («Yo, todo», «Cada uno su parte», «<Cotitular>, todo», «Otra combinación» solo con dos
//     titulares y «Desde una cuenta compartida», que sigue la vía de B3) con la cuenta solo cuando pagas tú → reparto y «¿Queda algo pendiente?»
//     (ME_DEBE o LE_DEBO por el desequilibrio completo, preseleccionado, visible y desmarcable, importe editable a la baja; nunca frente a una
//     EMPRESA ni con «No lo sé») → confirmación por persona (su parte, lo que puso y la posición que se crea, o «No queda nada pendiente»), con
//     `posiciones_confirmadas` = lo mostrado (C-MEJ-01 v2);
//   - SUSTITUCIÓN del aviso N3 de HT2-01 en el mismo cambio: se retiran `gprop-aviso-a-medias` y el chip «No, no me debe nada (ya está saldado
//     o le invito)»; el pago a medias se registra con «Cada uno su parte» u «Otra combinación». Los gastos ya registrados no se reescriben;
//   - detalle: «Quién pagó» (desde tu cuenta o por la suya), lo que salió de tus cuentas, las posiciones en su sentido, «Pago sin declarar» en
//     los hechos anteriores, la limitación de 8quater con su ampliación «en cualquier sentido» y «Ver el movimiento en la cuenta»
//     (L-MOV-CUENTA, pantalla nueva `MovimientosCuentaScreen`).
//   Código de partida: laboratorio lab-t2 (43a71c4, a0d1af4, 10b9596), copia revisada.
// Versión: 0.3.1 (F06 T2-F06 ajuste N3 · KO-2 y KO-3 de la prueba en iPhone; decisión de Moisés del 2026-11-15,
// Versión: 0.4.0 (F06 T3 · cadena de noche 21->22-11, T-D MANT N3 cliente; D-C7-07): los campos de importe ponen los puntos de miles al teclear (`formatearImporteAlTeclear`).
//   F06-00_Decisiones_Moises_2026-11-15_KO1_reclasificacion_N3_v1.0.md, 022b115a…): la relectura de la propuesta al cambiar fecha o
//   cuenta es silenciosa (sin «cargando», descarta respuestas atrasadas) y los importes de «Otra combinación» llevan su etiqueta visible.
// Versión: 0.5.0 (F06 T6 · S1 piezas comunes; F09 0.55 §12.107.1 punto 9): los campos de porcentaje, plazo y tipo abren el teclado decimal (`CampoTexto decimal`); sin otros cambios.
// Versión: 0.6.0 (F06 T6 · S3 reforma; F09 0.55 §12.107.2 DP-05 y lámina REG-AGIL v0.8 R1/R2; dictamen 1 Q5/A6): el alta de la reforma deja los cuatro pasos y pasa a exprés + «Revisar»: en una pantalla, Propiedad, Importe, «Qué se hizo», «¿Quién pagó?» con la cuenta, reparto con lo pendiente y Fecha (los bloques de antes, mismos testID y reglas: `gprop-paso-datos`, `gprop-paso-pago` y `gprop-paso-reparto` son ahora sus contenedores); «Revisar» (gprop-revisar) muestra lo que se guardará y vincula esa versión: si al confirmar ya no coincide, se recalcula y hay que reconfirmar; «‹ Volver» invalida la revisión. `posiciones_confirmadas` = lo mostrado. La mejora antigua ya era una sola pantalla. Payload sin cambios.
// ============================================================

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaElegible } from '../api/cliente';
import type {
  ClaseGasto, ClientePatrimonioB3, ComparacionImpacto, FilaGastoPropiedad, LecturaGastoPropiedad, PartePropuesta, PropuestaGasto,
} from '../api/patrimonio_b3';
import type { VistaPropiedad } from '../api/propiedades';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { CampoFecha } from '../components/CampoFecha';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef, FilaLista, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { ancestros, CategoriaNodo, construirArbol, elegibleParaGasto } from '../domain/categoria';
import { ayer, ddmmaaaaAIso, diaMesAnioIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import {
  alCambiarPropuesta, atribucionTexto, AYUDA_CLASE, borradorInicial, BorradorGastoPropiedad, clasesDestino, completarDeuda,
  cuentaCompartida, Derecho, derechos, EleccionReparto, faltasCorreccion, faltasDatos, faltasReparto, filasImpacto, hayPropuesta,
  muestraLimitacion, NOMBRE_CLASE, ofreceCorregir, ofreceDeuda, partesEfectivas, payloadCorreccion, payloadGastoPropiedad, payloadGastoPropiedadV2,
  payloadMejoraHistorica, repartirImporte, repartoInicial, resumenGastos, seleccionInicial, SeleccionCorreccion, TEXTO_CUENTA_COMPARTIDA,
  TEXTO_DESFASADA, TEXTO_IMPACTO_DESFASADO, TEXTO_INDETERMINADO, TEXTO_LIMITACION_8QUATER, TEXTO_LIMITACION_SENTIDO, TEXTO_PAGO_SIN_DECLARAR, TEXTO_SE_CREA_DERECHO,
  TEXTO_SIN_PAGO, TEXTO_SIN_TITULARIDAD, textoError, textoPropuesta,
} from '../domain/gasto_propiedad';
import { formatearEur, parsearImporte } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import {
  ajustarDeudas, confirmacion, Cotitular, DeudaElegida, EleccionPago, faltasPago, ModoPago, necesitaCuenta, opcionesPago, pagoInicial, pagosWire,
  posicionesConfirmadas, propuestas, saldos, saleDeMisCuentas, TEXTO_DESMARCAR, TEXTO_DESMARCAR_LE, TEXTO_EMPRESA, TEXTO_NADA_PENDIENTE,
  TEXTO_NO_ES_MOVIMIENTO, TEXTO_NO_LO_SE, TEXTO_QUIEN_PAGO, TEXTO_SIN_MOVIMIENTO, textoPosicion,
} from '../domain/quien_pago';
import { MovimientosCuentaScreen } from './MovimientosCuentaScreen';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

/** Alta de B3 (decisión 2026-11-13): solo «Reforma o mejora». */
const TEXTO_CLASE_ALTA = 'Reforma o mejora (aumenta el valor)';
const TEXTO_GASTOS_EN_REGISTRAR = 'Los gastos corrientes y las reparaciones se registran desde «Registrar gasto».';
/** PAG: la cuenta se elige en «¿Quién pagó?» (solo si pagas tú). */
const faltasDatosAlta = (b: BorradorGastoPropiedad) => faltasDatos(b).filter((x) => x !== 'la cuenta');
const importeDeTexto = (t: string) => {
  const r = parsearImporte(t);
  return r.ok ? r.valor : '0';
};

/** Fecha de B3 con el patrón de RegistroGasto y PropiedadValor: chips «Hoy · Ayer · Otra fecha» (Hoy por defecto), campo solo con «Otra fecha», regla ≤ hoy. */
function Fecha(p: { testID: string; etiqueta: string; iso: string; hoyIso: string; ayerIso: string; onCambiar: (iso: string) => void }) {
  const [otra, setOtra] = useState<string | null>(p.iso === p.hoyIso || p.iso === p.ayerIso ? null : esFechaIso(p.iso) ? isoADdmmaaaa(p.iso) : p.iso);
  return (
    <CampoFecha testID={p.testID} etiqueta={p.etiqueta} hoyIso={p.hoyIso} max={p.hoyIso} texto={otra}
      onTexto={(t) => { setOtra(t); p.onCambiar(ddmmaaaaAIso(t) ?? t); }}
      opciones={[
        { testID: `${p.testID}-hoy`, etiqueta: 'Hoy', seleccionado: otra === null && p.iso === p.hoyIso, onPress: () => { setOtra(null); p.onCambiar(p.hoyIso); } },
        { testID: `${p.testID}-ayer`, etiqueta: 'Ayer', seleccionado: otra === null && p.iso === p.ayerIso, onPress: () => { setOtra(null); p.onCambiar(p.ayerIso); } },
        { testID: `${p.testID}-otra`, etiqueta: 'Otra fecha', seleccionado: otra !== null, onPress: () => setOtra(esFechaIso(p.iso) ? isoADdmmaaaa(p.iso) : p.iso) },
      ]} />
  );
}

function Linea(p: { testID: string; etiqueta: string; valor: string; fuerte?: boolean }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={s.linea}>
      <Text style={[p.fuerte ? tipo.bodyEmphasis : tipo.body, { color: c.textPrimary, flex: 1 }]}>{p.etiqueta}</Text>
      <Text testID={`${p.testID}-valor`} style={[p.fuerte ? tipo.bodyEmphasis : tipo.body, { color: c.textPrimary }]}>{p.valor}</Text>
    </View>
  );
}

/** Categorías elegibles para un gasto (lista plana con su ruta; la elección siempre es del usuario). */
function Categorias(p: { testID: string; cliente: ClienteApi; valor: string | null; onCambiar: (id: string) => void }) {
  const [lista, setLista] = useState<{ id: string; texto: string }[] | null>(null);
  useEffect(() => {
    void p.cliente.arbolCategorias().then((r) => {
      if (r.tipo !== 'OK') return setLista([]);
      const a = construirArbol(r.datos.categorias);
      setLista(r.datos.categorias.filter((n: CategoriaNodo) => elegibleParaGasto(n)).map((n) => ({ id: n.id, texto: [...ancestros(a, n.id).map((x) => x.nombre), n.nombre].join(' › ') })));
    });
  }, []);
  if (lista === null) return <EstadoDato testID={`${p.testID}-cargando`} estado="CARGANDO" />;
  if (lista.length === 0) return <EstadoDato testID={`${p.testID}-sin`} estado="NO_DISPONIBLE" detalle="Sin categorías de gasto" />;
  return (
    <View style={ef.chips}>
      {lista.map((x) => <Chip key={x.id} testID={`${p.testID}-${x.id}`} etiqueta={x.texto} seleccionado={p.valor === x.id} onPress={() => p.onCambiar(x.id)} />)}
    </View>
  );
}

function Presupuesto(p: { testID: string; valor: boolean | null; onCambiar: (v: boolean) => void }) {
  return (
    <Campo etiqueta="¿Cuenta para el presupuesto?">
      <View style={ef.chips}>
        <Chip testID={`${p.testID}-si`} etiqueta="Sí" seleccionado={p.valor === true} onPress={() => p.onCambiar(true)} />
        <Chip testID={`${p.testID}-no`} etiqueta="No" seleccionado={p.valor === false} onPress={() => p.onCambiar(false)} />
      </View>
    </Campo>
  );
}

/** Actores para «Otro reparto»: los de la propuesta (con naturaleza) o, sin ella, los de la titularidad de la ficha. */
function actoresDe(v: VistaPropiedad, prop: PropuestaGasto | null): PartePropuesta[] {
  if (prop && prop.partes.length > 0) return prop.partes;
  return v.titularidad.partes.map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje, yo: x.yo, tercero_id: x.tercero_id, nombre: x.nombre, naturaleza: null }));
}

/** «¿De quién es el gasto?»: la propuesta marcada por defecto si existe (DM-02); «Otro reparto» y «No lo sé» siempre. */
function Reparto(p: {
  testID: string; propiedad: string; prop: PropuestaGasto | null; eleccion: EleccionReparto; actores: PartePropuesta[];
  onCambiar: (e: EleccionReparto) => void; aviso?: string | null;
}) {
  const { c } = useTema();
  const manual = p.eleccion?.modo === 'MANUAL' ? p.eleccion.partes : null;
  return (
    <View testID={p.testID} style={{ gap: espacio.m }}>
      {p.prop === null ? <EstadoDato testID={`${p.testID}-cargando`} estado="CARGANDO" /> : null}
      {hayPropuesta(p.prop) ? (
        <Chip testID={`${p.testID}-titularidad`} etiqueta={textoPropuesta(p.propiedad, p.prop!)} seleccionado={p.eleccion?.modo === 'TITULARIDAD'}
          onPress={() => p.onCambiar({ modo: 'TITULARIDAD' })} />
      ) : null}
      {p.prop !== null && !hayPropuesta(p.prop) ? <Text testID={`${p.testID}-sin-titularidad`} style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_SIN_TITULARIDAD}</Text> : null}
      <Chip testID={`${p.testID}-manual`} etiqueta="Otro reparto · indica cuánto es de cada uno" seleccionado={p.eleccion?.modo === 'MANUAL'}
        onPress={() => p.onCambiar({ modo: 'MANUAL', partes: Object.fromEntries(p.actores.map((a) => [a.actor_id, ''])) })} />
      {manual ? p.actores.map((a) => (
        <CampoTexto key={a.actor_id} decimal testID={`${p.testID}-pct-${a.actor_id}`} etiqueta={`Porcentaje de ${a.yo ? 'ti' : a.nombre ?? 'otra persona'}`} marcador="%"
          valor={manual[a.actor_id] ?? ''} onCambiar={(t) => p.onCambiar({ modo: 'MANUAL', partes: { ...manual, [a.actor_id]: t } })} />
      )) : null}
      <Chip testID={`${p.testID}-no-lo-se`} etiqueta="No lo sé · tu parte quedará «sin indicar»" seleccionado={p.eleccion?.modo === 'NO_LO_SE'}
        onPress={() => p.onCambiar({ modo: 'NO_LO_SE' })} />
      {p.aviso ? <Text testID={`${p.testID}-aviso`} style={[tipo.footnote, { color: c.warningText }]}>{p.aviso}</Text> : null}
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>La propuesta sale de la titularidad de la propiedad en la fecha del gasto, nunca de la cuenta. Si la titularidad cambia más adelante, este reparto no cambia.</Text>
    </View>
  );
}

/** C-MEJ-01 · Reforma o mejora de una propiedad: datos → «¿Quién pagó?» → reparto y lo que queda pendiente → confirmación (PAG). */
export function GastoPropiedadScreen(p: {
  cliente: ClienteApi;
  patrimonio: ClientePatrimonioB3;
  vista: VistaPropiedad;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (cambio: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const ayerIso = isoLocal(ayer(p.ahora()));
  // F06 T6 · S3 (F09 0.55 §12.107.2, DP-05; lámina R1/R2): exprés (datos, quién pagó, reparto y fecha en una pantalla) → «Revisar» → hecho.
  type Paso = 'EXPRES' | 'REVISAR' | 'HECHO';
  const [paso, setPaso] = useState<Paso>('EXPRES');
  // A6: «Revisar» vincula la versión del cálculo mostrada; si cambia algo, se invalida y se recalcula antes de reconfirmar.
  const revisada = useRef<string | null>(null);
  const [avisoRevision, setAvisoRevision] = useState<string | null>(null);
  // Decisión 2026-11-13: el alta solo registra reformas o mejoras; la clase va fijada (sin chip).
  const [b, setB] = useState<BorradorGastoPropiedad>(() => ({ ...borradorInicial(hoyIso), clase: 'MEJORA' }));
  const [pago, setPago] = useState<EleccionPago>(pagoInicial);
  const [deudas, setDeudas] = useState<Record<string, DeudaElegida>>({});
  const [deudasTocadas, setDeudasTocadas] = useState(false);
  const [cuentas, setCuentas] = useState<CuentaElegible[]>([]);
  const [prop, setProp] = useState<PropuestaGasto | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [avisoRep, setAvisoRep] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const intencion = useRef(p.nuevoId());
  const actores = actoresDe(p.vista, prop);
  const compartida = pago.modo === 'COMPARTIDA';

  useEffect(() => {
    if (!esFechaIso(b.fecha)) return;
    void p.cliente.cuentasElegibles('GASTO', b.fecha).then((r) => { if (r.tipo === 'OK') setCuentas(r.datos.cuentas); });
  }, [b.fecha]);
  // KO-2 (prueba en iPhone del tren 2, 2026-11-15): la relectura es silenciosa; se conserva la propuesta mostrada
  // hasta que llega la nueva (sin «cargando» ni recarga de la pantalla) y se descartan las respuestas atrasadas.
  const lectura = useRef(0);
  const leerPropuesta = async () => {
    if (!esFechaIso(b.fecha)) return;
    const n = ++lectura.current;
    const r = await p.patrimonio.propuestaGasto(p.vista.id, b.fecha, b.cuentaId);
    if (n !== lectura.current) return;
    const nueva: PropuestaGasto = r.tipo === 'OK' ? r.datos : { fecha: b.fecha, propiedad_id: p.vista.id, nombre: p.vista.nombre, titularidad_disponible: false, partes: [], cuenta: null };
    setProp(nueva);
    setB((x) => alCambiarPropuesta(x, nueva, actoresDe(p.vista, nueva)));
  };
  // Relectura si cambian la fecha o la cuenta: lo que el usuario no tocó se vuelve a proponer.
  useEffect(() => { void leerPropuesta(); }, [b.fecha, b.cuentaId]);

  const concepto = b.nota.trim() || (b.clase ? NOMBRE_CLASE[b.clase].split(' (')[0] : 'Gasto');
  const partes = partesEfectivas(b.reparto, prop, actores);
  const imp = repartirImporte(b.importe, partes);
  const noLoSe = b.reparto?.modo === 'NO_LO_SE';
  const cotitulares: Cotitular[] = actores.filter((x) => !x.yo).map((x) => ({ actor_id: x.actor_id, nombre: x.nombre }));
  const numTitulares = actores.length;
  // PAG (L-08): deudas propuestas por el desequilibrio completo, preseleccionadas y desmarcables en los dos sentidos.
  const props = compartida ? [] : propuestas(pago, b.importe, partes);
  useEffect(() => { setDeudas((d) => ajustarDeudas(d, props, deudasTocadas)); }, [JSON.stringify(props)]);
  const saldosEnvio = saldos(pago, b.importe, partes, deudas);
  const posiciones = posicionesConfirmadas(saldosEnvio);
  // Vía de B3 (cuenta compartida, 8ter): sin preselección y con el importe a mano.
  const mostrados: Derecho[] = compartida ? derechos(b, prop, actores, `${concepto} · ${p.vista.nombre}`) : [];
  const cuentaEsCompartida = cuentaCompartida(prop);
  // En el exprés falta lo de los tres bloques de antes (datos, quién pagó y reparto), con las mismas reglas.
  const faltas = paso === 'EXPRES'
    ? [...new Set([...faltasDatosAlta(b), ...faltasPago(pago, b.importe, partes, noLoSe, b.cuentaId, cuentaEsCompartida, deudas, numTitulares),
      ...faltasReparto(b, prop, actores, !compartida)])]
    : [];
  /** Huella de lo que «Revisar» muestra y se envía: fecha, importe, cuenta, titularidad leída, reparto, quién pagó y deudas. */
  const huella = JSON.stringify([b.fecha, b.importe, b.cuentaId, b.nota, prop, b.reparto, pago, deudas, b.deuda, saldosEnvio, posiciones, mostrados]);
  const abrirRevision = () => {
    revisada.current = huella;
    setAvisoRevision(null);
    setPaso('REVISAR');
  };
  const volverAlExpres = () => {
    revisada.current = null;
    setAvisoRevision(null);
    setPaso('EXPRES');
  };

  const cambiarReparto = (e: EleccionReparto) => {
    setAvisoRep(null);
    setB({ ...b, reparto: e, repartoTocado: true, deuda: completarDeuda(b.deuda, e, prop, actores) });
  };
  const elegirPago = (modo: ModoPago, pagadorId: string | null) => setPago({ ...pago, modo, pagadorId });
  const cambiarDeudaPag = (actor: string, marcada: boolean) => {
    setDeudasTocadas(true);
    setDeudas({ ...deudas, [actor]: { marcada, importe: deudas[actor]?.importe ?? '' } });
  };
  const importeDeudaPag = (actor: string, t: string) => {
    setDeudasTocadas(true);
    setDeudas({ ...deudas, [actor]: { marcada: true, importe: t } });
  };
  const cambiarDeuda = (actor: string, me: 'SI' | 'NO') => setB({ ...b, deudaTocada: true, deuda: { ...b.deuda, [actor]: { me_debe: me, importe: b.deuda[actor]?.importe ?? '' } } });
  const importeDeuda = (actor: string, t: string) => setB({ ...b, deudaTocada: true, deuda: { ...b.deuda, [actor]: { me_debe: 'SI', importe: t } } });

  const guardar = async () => {
    if (ocupado) return;
    if (revisada.current !== huella) {
      // A6: lo mostrado ya no es lo que se enviaría: se recalcula (se muestra lo nuevo) y hay que volver a confirmar.
      revisada.current = huella;
      return setAvisoRevision(TEXTO_REVISION_CAMBIADA);
    }
    setOcupado(true);
    setAviso(null);
    // PAG: `posiciones_confirmadas` = exactamente lo que muestra esta confirmación; con la cuenta compartida, la forma de B3
    // (`derechos_confirmados` = lo mostrado, 8bis). El servidor nunca infiere una deuda.
    const cuerpo = compartida
      ? payloadGastoPropiedad(intencion.current, p.vista.id, b, prop, actores, mostrados)
      : payloadGastoPropiedadV2(intencion.current, p.vista.id, b, prop, pagosWire(pago, b.importe, partes, b.cuentaId), saldosEnvio, posiciones);
    const r = await p.patrimonio.registrarGastoPropiedad(cuerpo);
    setOcupado(false);
    if (r.tipo === 'OK') return setPaso('HECHO');
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    if (r.codigo === 'ATRIBUCION_PROPUESTA_DESFASADA') {
      intencion.current = p.nuevoId();
      setB((x) => ({ ...x, repartoTocado: false, deudaTocada: false }));
      setDeudasTocadas(false);
      setAvisoRep(TEXTO_DESFASADA);
      revisada.current = null;
      setPaso('EXPRES');
      return void leerPropuesta();
    }
    setAviso({ tipo: 'AVISO', texto: textoError(r.codigo, r.mensaje) });
  };

  if (paso === 'HECHO') {
    return (
      <View testID="gprop-hecho" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Reforma o mejora guardada" testIDCancelar="gprop-hecho-cerrar" onCancelar={() => p.onCerrar(true)} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Text style={[tipo.body, { color: c.textPrimary }]}>{b.clase === 'MEJORA' ? 'Suma al coste de la vivienda. No es gasto del mes.' : 'Cuenta como gasto del mes.'}</Text>
          <BotonPrimario testID="gprop-listo" titulo="Listo" onPress={() => p.onCerrar(true)} />
        </ScrollView>
      </View>
    );
  }

  const titulo = paso === 'REVISAR' ? 'Revisar' : 'Reforma o mejora';
  const confirmar = compartida ? [] : confirmacion(pago, b.importe, partes, saldosEnvio);
  return (
    <View testID={paso === 'REVISAR' ? 'gprop-paso-confirmar' : 'gprop-expres'} style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={titulo} testIDCancelar="gprop-cancelar" onCancelar={() => p.onCerrar(false)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="gprop-aviso" aviso={aviso} /> : null}
        {paso === 'EXPRES' ? (
          <View testID="gprop-paso-datos" style={{ gap: espacio.l }}>
            <Linea testID="gprop-propiedad" etiqueta="Propiedad" valor={p.vista.nombre} />
            <CampoTexto importe testID="gprop-importe" etiqueta="Importe" marcador="0,00" valor={b.importe} onCambiar={(t) => setB({ ...b, importe: t })} />
            <CampoTexto testID="gprop-nota" etiqueta="Qué se hizo" marcador="Opcional (p. ej., cambio de ventanas)" valor={b.nota} onCambiar={(t) => setB({ ...b, nota: t })} />
            <View testID="gprop-clase" style={{ gap: 2 }}>
              <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{TEXTO_CLASE_ALTA}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>{AYUDA_CLASE.MEJORA}</Text>
            </View>
            <Text testID="gprop-nota-registrar-gasto" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_GASTOS_EN_REGISTRAR}</Text>
          </View>
        ) : null}
        {paso === 'EXPRES' ? (
          <View testID="gprop-paso-pago" style={{ gap: espacio.l }}>
            <RotuloGrupo texto={TEXTO_QUIEN_PAGO} />
            <View testID="gprop-quien-pago" style={ef.chips}>
              {opcionesPago(cotitulares).map((o) => (
                <Chip key={o.clave} testID={`gprop-pago-${o.clave}`} etiqueta={o.etiqueta}
                  seleccionado={pago.modo === o.modo && (o.modo !== 'COTITULAR_TODO' || pago.pagadorId === o.pagadorId)}
                  onPress={() => elegirPago(o.modo, o.pagadorId)} />
              ))}
            </View>
            {pago.modo === 'MIXTO' ? (
              <>
                <Campo etiqueta="Lo que pusiste tú (desde tu cuenta)">
                  <CampoTexto importe testID="gprop-pago-mio" etiqueta="Lo que pusiste tú (desde tu cuenta)" marcador="0,00" valor={pago.mio} onCambiar={(t) => setPago({ ...pago, mio: t })} />
                </Campo>
                <Campo etiqueta={`Lo que puso ${cotitulares[0]?.nombre ?? 'el otro titular'} (por su cuenta)`}>
                  <CampoTexto importe testID="gprop-pago-suyo" etiqueta={`Lo que puso ${cotitulares[0]?.nombre ?? 'el otro titular'} (por su cuenta)`} marcador="0,00" valor={pago.suyo}
                    onCambiar={(t) => setPago({ ...pago, suyo: t })} />
                </Campo>
              </>
            ) : null}
            {pago.modo === 'COTITULAR_TODO' ? <Text testID="gprop-pago-sin-movimiento" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_MOVIMIENTO}</Text> : null}
            {necesitaCuenta(pago) ? (
              <Campo etiqueta={compartida ? 'Cuenta compartida' : 'Tu cuenta'}>
                {cuentas.length === 0 ? <EstadoDato testID="gprop-cuenta-sin" estado="NO_DISPONIBLE" detalle="Sin cuentas para pagar" /> : (
                  <View style={ef.chips}>
                    {cuentas.map((x) => <Chip key={x.cuenta_id} testID={`gprop-cuenta-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={b.cuentaId === x.cuenta_id} onPress={() => setB({ ...b, cuentaId: x.cuenta_id })} />)}
                  </View>
                )}
              </Campo>
            ) : null}
          </View>
        ) : null}
        {paso === 'EXPRES' ? (
          <View testID="gprop-paso-reparto" style={{ gap: espacio.l }}>
            <RotuloGrupo texto="¿De quién es el gasto?" />
            <Reparto testID="gprop-rep" propiedad={p.vista.nombre} prop={prop} eleccion={b.reparto} actores={actores} onCambiar={cambiarReparto} aviso={avisoRep} />
            {partes.some((x) => !x.yo) || noLoSe ? <RotuloGrupo texto="¿Queda algo pendiente?" /> : null}
            {noLoSe && !compartida ? <Text testID="gprop-deuda-no-lo-se" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NO_LO_SE}</Text> : null}
            {!compartida ? (
              <>
                {props.map((x) => (
                  <Tarjeta key={x.actor_id} testID={`gprop-deuda-${x.actor_id}`}>
                    <View style={{ padding: espacio.m, gap: espacio.s }}>
                      <Text testID={`gprop-deuda-${x.actor_id}-texto`} style={[tipo.body, { color: c.textPrimary }]}>{textoPosicion(x.sentido, x.nombre, deudas[x.actor_id]?.marcada ? importeDeTexto(deudas[x.actor_id].importe) : x.maximo)}</Text>
                      <View style={ef.chips}>
                        <Chip testID={`gprop-deuda-${x.actor_id}-si`} etiqueta={x.sentido === 'ME_DEBE' ? 'Sí, me lo debe' : 'Sí, se lo debo'} seleccionado={deudas[x.actor_id]?.marcada === true} onPress={() => cambiarDeudaPag(x.actor_id, true)} />
                        <Chip testID={`gprop-deuda-${x.actor_id}-no`} etiqueta={TEXTO_NADA_PENDIENTE} seleccionado={deudas[x.actor_id]?.marcada === false} onPress={() => cambiarDeudaPag(x.actor_id, false)} />
                      </View>
                      {deudas[x.actor_id]?.marcada ? (
                        <CampoTexto importe testID={`gprop-deuda-${x.actor_id}-importe`} etiqueta={`Importe (como mucho ${formatearEur(x.maximo)}; menos si le invitas a una parte)`} marcador={x.maximo}
                          valor={deudas[x.actor_id]?.importe ?? ''} onCambiar={(t) => importeDeudaPag(x.actor_id, t)} />
                      ) : null}
                      <Text style={[tipo.caption, { color: c.textSecondary }]}>{x.sentido === 'ME_DEBE' ? TEXTO_DESMARCAR : TEXTO_DESMARCAR_LE}</Text>
                    </View>
                  </Tarjeta>
                ))}
                {partes.filter((x) => !x.yo && x.naturaleza !== 'PERSONA').map((x) => (
                  <Text key={x.actor_id} testID={`gprop-no-debe-${x.actor_id}`} style={[tipo.footnote, { color: c.textSecondary }]}>{`${x.nombre ?? 'Otra persona'}: ${TEXTO_EMPRESA}`}</Text>
                ))}
                {partes.some((x) => !x.yo) && props.length === 0 && !noLoSe ? (
                  <Text testID="gprop-deuda-nada" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NADA_PENDIENTE}</Text>
                ) : null}
              </>
            ) : (
              <>
                {partes.some((x) => ofreceDeuda(x, imp[x.actor_id], prop, false)) ? (
                  <Text testID="gprop-compartida" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CUENTA_COMPARTIDA}</Text>
                ) : null}
                {partes.filter((x) => !x.yo).map((x) => (
                  ofreceDeuda(x, imp[x.actor_id], prop, false) ? (
                    <Tarjeta key={x.actor_id} testID={`gprop-debe-${x.actor_id}`}>
                      <View style={{ padding: espacio.m, gap: espacio.s }}>
                        <Text style={[tipo.body, { color: c.textPrimary }]}>{`¿${x.nombre ?? 'Otra persona'} te debe algo? (su parte: ${formatearEur(imp[x.actor_id] ?? '0')})`}</Text>
                        <View style={ef.chips}>
                          <Chip testID={`gprop-debe-${x.actor_id}-si`} etiqueta="Sí" seleccionado={b.deuda[x.actor_id]?.me_debe === 'SI'} onPress={() => cambiarDeuda(x.actor_id, 'SI')} />
                          <Chip testID={`gprop-debe-${x.actor_id}-no`} etiqueta={TEXTO_NADA_PENDIENTE} seleccionado={b.deuda[x.actor_id]?.me_debe === 'NO'} onPress={() => cambiarDeuda(x.actor_id, 'NO')} />
                        </View>
                        {b.deuda[x.actor_id]?.me_debe === 'SI' ? (
                          <CampoTexto importe testID={`gprop-debe-${x.actor_id}-importe`} etiqueta={`¿Cuánto te debe ${x.nombre ?? 'esa persona'}?`} marcador="Indícalo tú"
                            valor={b.deuda[x.actor_id]?.importe ?? ''} onCambiar={(t) => importeDeuda(x.actor_id, t)} />
                        ) : null}
                      </View>
                    </Tarjeta>
                  ) : (
                    <Text key={x.actor_id} testID={`gprop-no-debe-${x.actor_id}`} style={[tipo.footnote, { color: c.textSecondary }]}>
                      {`${x.nombre ?? 'Otra persona'}: ${x.naturaleza === 'EMPRESA' ? TEXTO_EMPRESA : 'sin deuda'}`}
                    </Text>
                  )
                ))}
              </>
            )}
          </View>
        ) : null}
        {paso === 'EXPRES' ? (
          <View testID="gprop-bloque-fecha" style={{ gap: espacio.l }}>
            <Campo etiqueta="Fecha del gasto y del pago">
              <Fecha testID="gprop-fecha" etiqueta="Fecha del gasto" iso={b.fecha} hoyIso={hoyIso} ayerIso={ayerIso} onCambiar={(iso) => setB({ ...b, fecha: iso })} />
            </Campo>
          </View>
        ) : null}
        {paso === 'REVISAR' ? (
          <>
            {avisoRevision ? <Caja testID="gprop-revision-cambiada" aviso={{ tipo: 'AVISO', texto: avisoRevision }} /> : null}
            <Tarjeta testID="gprop-resumen">
              <Linea testID="gprop-res-clase" etiqueta="Clase" valor={TEXTO_CLASE_ALTA} />
              <Linea testID="gprop-res-importe" etiqueta="Importe" valor={formatearEur(parsearImporte(b.importe).ok ? (parsearImporte(b.importe) as { valor: string }).valor : '0')} fuerte />
              <Linea testID="gprop-res-fecha" etiqueta="Fecha" valor={esFechaIso(b.fecha) ? diaMesAnioIso(b.fecha) : b.fecha} />
              <Linea testID="gprop-res-gasto-mes" etiqueta="Cuenta como gasto del mes" valor={b.clase === 'MEJORA' ? 'No · suma al coste' : 'Sí'} />
              <Linea testID="gprop-res-sale" etiqueta="Sale de tus cuentas" valor={formatearEur(compartida ? importeDeTexto(b.importe) : saleDeMisCuentas(pago, b.importe, partes))} />
            </Tarjeta>
            <RotuloGrupo texto="De quién es (lo que se guardará)" />
            <Tarjeta testID="gprop-atribucion">
              {atribucionTexto(b, prop, actores).map((x) => <Text key={x.actor_id} testID={`gprop-atr-${x.actor_id}`} style={[tipo.body, s.pad, { color: c.textPrimary }]}>{x.texto}</Text>)}
              {partes.length === 0 ? <Text testID="gprop-atr-sin" style={[tipo.body, s.pad, { color: c.textSecondary }]}>Tu parte quedará «sin indicar»</Text> : null}
            </Tarjeta>
            {!compartida ? (
              <>
                <RotuloGrupo texto="Quién pagó y qué queda pendiente" />
                {confirmar.map((x) => (
                  <Tarjeta key={x.actor_id} testID={`gprop-conf-${x.actor_id}`}>
                    <View style={{ padding: espacio.m, gap: 2 }}>
                      <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{x.nombre}</Text>
                      {x.parte !== null ? <Text testID={`gprop-conf-${x.actor_id}-parte`} style={[tipo.caption, { color: c.textSecondary }]}>{`Su parte: ${formatearEur(x.parte)}`}</Text> : null}
                      <Text testID={`gprop-conf-${x.actor_id}-puso`} style={[tipo.caption, { color: c.textSecondary }]}>{`Puso: ${formatearEur(x.puso)}`}</Text>
                      <Text testID={`gprop-conf-${x.actor_id}-posicion`} style={[tipo.body, { color: c.textPrimary }]}>{x.posicion}</Text>
                    </View>
                  </Tarjeta>
                ))}
                {partes.length === 0 ? (
                  <Text testID="gprop-conf-pagos" style={[tipo.body, { color: c.textPrimary }]}>{pagosWire(pago, b.importe, partes, b.cuentaId).map((x) => `${x.pagador === 'YO' ? 'Tú' : cotitulares.find((y) => y.actor_id === x.pagador)?.nombre ?? 'Otra persona'} puso ${formatearEur(x.importe)}`).join(' · ')}</Text>
                ) : null}
                {posiciones.length > 0 ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NO_ES_MOVIMIENTO}</Text> : null}
              </>
            ) : (
              <>
                {mostrados.length > 0 ? <RotuloGrupo texto="Derechos de cobro" /> : null}
                {mostrados.map((d) => (
                  <Tarjeta key={d.actor_id} testID={`gprop-derecho-${d.actor_id}`}>
                    <View style={{ padding: espacio.m, gap: 2 }}>
                      <Text testID={`gprop-derecho-${d.actor_id}-quien`} style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{`${d.nombre} te debe ${formatearEur(d.importe)}`}</Text>
                      <Text style={[tipo.caption, { color: c.textSecondary }]}>{`Por: ${d.concepto}`}</Text>
                      <Text style={[tipo.caption, { color: c.textSecondary }]}>{`Parte que se le atribuye: ${Number(d.porcentaje).toLocaleString('es-ES', { maximumFractionDigits: 4 })} % · ${formatearEur(d.parte)}`}</Text>
                      <Text testID={`gprop-derecho-${d.actor_id}-aviso`} style={[tipo.footnote, { color: c.accentText }]}>{TEXTO_SE_CREA_DERECHO}</Text>
                    </View>
                  </Tarjeta>
                ))}
                {mostrados.length === 0 ? <Text testID="gprop-conf-nada" style={[tipo.body, { color: c.textPrimary }]}>{TEXTO_NADA_PENDIENTE}</Text> : null}
                {mostrados.length > 0 ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NO_ES_MOVIMIENTO}</Text> : null}
              </>
            )}
          </>
        ) : null}
        {faltas.length > 0 ? <Text testID="gprop-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        {paso === 'REVISAR' ? (
          <>
            <Text testID="gprop-revisar-pie" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_PIE_REVISAR_REFORMA}</Text>
            <BotonPrimario testID="gprop-guardar" titulo="Confirmar y guardar" cargando={ocupado} onPress={() => void guardar()} />
            <BotonTexto testID="gprop-atras" titulo="‹ Volver" onPress={volverAlExpres} />
          </>
        ) : (
          <BotonPrimario testID="gprop-revisar" titulo="Revisar" deshabilitado={faltas.length > 0}
            ayuda={faltas.length > 0 ? `Falta: ${faltas.join(', ')}.` : undefined} onPress={abrirRevision} />
        )}
      </ScrollView>
    </View>
  );
}

/** F06 T6 · S3 (A6): textos de «Revisar» de la reforma. */
export const TEXTO_PIE_REVISAR_REFORMA = 'Lo que ves aquí es exactamente lo que se guarda. Si cambias la fecha, el reparto, quién pagó o la cuenta, la revisión se invalida y se recalcula.';
export const TEXTO_REVISION_CAMBIADA = 'Algo ha cambiado desde que lo revisaste: se ha recalculado. Revísalo de nuevo y confirma.';

/** C-MEJ-02 · Mejora histórica (sin pago: nunca «Te debe su parte»). */
export function MejoraHistoricaScreen(p: {
  patrimonio: ClientePatrimonioB3;
  vista: VistaPropiedad;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (cambio: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const ayerIso = isoLocal(ayer(p.ahora()));
  const [descripcion, setDescripcion] = useState('');
  const [importe, setImporte] = useState('');
  const [fecha, setFecha] = useState(hoyIso);
  const [prop, setProp] = useState<PropuestaGasto | null>(null);
  const [eleccion, setEleccion] = useState<EleccionReparto>(null);
  const [tocado, setTocado] = useState(false);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);
  const intencion = useRef(p.nuevoId());
  useEffect(() => {
    if (!esFechaIso(fecha)) return;
    setProp(null);
    void p.patrimonio.propuestaGasto(p.vista.id, fecha).then((r) => {
      const nueva = r.tipo === 'OK' ? r.datos : null;
      setProp(nueva ?? { fecha, propiedad_id: p.vista.id, nombre: p.vista.nombre, titularidad_disponible: false, partes: [], cuenta: null });
      if (!tocado) setEleccion(repartoInicial(nueva));
    });
  }, [fecha]);
  const actores = actoresDe(p.vista, prop);
  const borrador = { ...borradorInicial(fecha), importe, reparto: eleccion };
  const faltas = [
    ...(descripcion.trim() ? [] : ['qué se hizo']),
    ...(parsearImporte(importe).ok ? [] : ['un importe mayor que 0']),
    ...(esFechaIso(fecha) ? [] : ['la fecha']),
    ...faltasReparto(borrador, prop, actores, true),
  ];
  const guardar = async () => {
    if (ocupado || faltas.length > 0) return;
    setOcupado(true);
    setAviso(null);
    const r = await p.patrimonio.mejoraHistorica(p.vista.id, payloadMejoraHistorica(intencion.current, p.vista.row_version, descripcion, importe, fecha, eleccion, prop));
    setOcupado(false);
    if (r.tipo === 'OK') return p.onCerrar(true);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    if (r.codigo === 'ATRIBUCION_PROPUESTA_DESFASADA') {
      intencion.current = p.nuevoId();
      setTocado(false);
      setFecha((f) => f);
    }
    setAviso({ tipo: 'AVISO', texto: textoError(r.codigo, r.mensaje) });
  };
  return (
    <View testID="mejora-historica" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo="Mejora antigua" testIDCancelar="mh-cancelar" onCancelar={() => p.onCerrar(false)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="mh-aviso" aviso={aviso} /> : null}
        <CampoTexto testID="mh-descripcion" etiqueta="Qué se hizo" marcador="Ej.: Reforma integral" valor={descripcion} onCambiar={setDescripcion} />
        <CampoTexto importe testID="mh-importe" etiqueta="Importe" marcador="0,00" valor={importe} onCambiar={setImporte} />
        <Campo etiqueta="Fecha">
          <Fecha testID="mh-fecha" etiqueta="Fecha de la mejora" iso={fecha} hoyIso={hoyIso} ayerIso={ayerIso} onCambiar={setFecha} />
        </Campo>
        <Text testID="mh-sin-pago" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_PAGO}</Text>
        <RotuloGrupo texto="¿De quién es la mejora?" />
        <Reparto testID="mh-rep" propiedad={p.vista.nombre} prop={prop} eleccion={eleccion} actores={actores} onCambiar={(e) => { setTocado(true); setEleccion(e); }} />
        {faltas.length > 0 ? <Text testID="mh-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        <BotonPrimario testID="mh-guardar" titulo="Guardar" cargando={ocupado} deshabilitado={faltas.length > 0} onPress={() => void guardar()} />
      </ScrollView>
    </View>
  );
}

/** C-MEJ-03 · Corregir la clase (boceto L-5). Solo se abre con `intencion_correccion_id`. */
export function CorregirClaseScreen(p: {
  cliente: ClienteApi;
  patrimonio: ClientePatrimonioB3;
  propiedadId: string;
  lectura: LecturaGastoPropiedad;
  onCerrar: (cambio: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const l = p.lectura;
  const [sel, setSel] = useState<SeleccionCorreccion>(seleccionInicial);
  const [comp, setComp] = useState<ComparacionImpacto | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);
  const destinos = clasesDestino(l);
  const leerImpacto = async (x: SeleccionCorreccion) => {
    setComp(null);
    if (x.clase === null || (x.clase !== 'MEJORA' && x.presupuestable === null)) return;
    const r = await p.patrimonio.impactoCorreccion(p.propiedadId, l.hecho_id, x.clase, x.clase === 'MEJORA' ? null : x.presupuestable);
    if (r.tipo === 'OK') setComp(r.datos.comparacion);
  };
  useEffect(() => { void leerImpacto(sel); }, [sel.clase, sel.presupuestable]);
  const faltas = [...faltasCorreccion(sel), ...(sel.clase !== null && comp === null && faltasCorreccion(sel).length === 0 ? ['el impacto'] : [])];
  const corregir = async () => {
    if (ocupado || faltas.length > 0 || comp === null) return;
    setOcupado(true);
    setAviso(null);
    const r = await p.patrimonio.corregirClase(p.propiedadId, l.hecho_id, payloadCorreccion(l, sel, comp));
    setOcupado(false);
    if (r.tipo === 'OK') return p.onCerrar(true);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    if (r.codigo === 'IMPACTO_CORRECCION_DESFASADO') {
      setAviso({ tipo: 'AVISO', texto: TEXTO_IMPACTO_DESFASADO });
      return void leerImpacto(sel);
    }
    setAviso({ tipo: 'AVISO', texto: textoError(r.codigo, r.mensaje) });
  };
  return (
    <View testID="corregir-clase" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo="Corregir la clase del gasto" testIDCancelar="cc-cancelar" onCancelar={() => p.onCerrar(false)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="cc-aviso" aviso={aviso} /> : null}
        <Text testID="cc-contexto" style={[tipo.body, { color: c.textPrimary }]}>
          {`${l.nota ?? 'Gasto'} · ${formatearEur(l.importe)} · ${diaMesAnioIso(l.fecha)} · registrado como ${l.clase === 'MEJORA' ? 'Mejora' : 'Reparación o gasto corriente'}`}
        </Text>
        <RotuloGrupo texto="¿Qué fue en realidad?" />
        {destinos.map((k) => (
          <Chip key={k} testID={`cc-clase-${k}`} etiqueta={NOMBRE_CLASE[k]} seleccionado={sel.clase === k}
            onPress={() => setSel({ ...sel, clase: k, ...(k === 'MEJORA' ? { categoriaId: null, presupuestable: null } : {}) })} />
        ))}
        {sel.clase !== null && sel.clase !== 'MEJORA' ? (
          <>
            <Campo etiqueta="Categoría">
              <Categorias testID="cc-categoria" cliente={p.cliente} valor={sel.categoriaId} onCambiar={(id) => setSel({ ...sel, categoriaId: id })} />
            </Campo>
            <Presupuesto testID="cc-presupuestable" valor={sel.presupuestable} onCambiar={(v) => setSel({ ...sel, presupuestable: v })} />
          </>
        ) : null}
        <CampoTexto testID="cc-motivo" etiqueta="Motivo" marcador="¿Por qué lo corriges?" valor={sel.motivo} onCambiar={(t) => setSel({ ...sel, motivo: t })} />
        {comp ? (
          <>
            <RotuloGrupo texto="Así cambia este gasto" />
            <Tarjeta testID="cc-impacto">
              {filasImpacto(comp).map((f) => <Linea key={f.clave} testID={`cc-imp-${f.clave}`} etiqueta={f.etiqueta} valor={`${f.antes} → ${f.despues}`} />)}
            </Tarjeta>
          </>
        ) : null}
        {faltas.length > 0 ? <Text testID="cc-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        <BotonPrimario testID="cc-corregir" titulo="Corregir" cargando={ocupado} deshabilitado={faltas.length > 0} onPress={() => void corregir()} />
      </ScrollView>
    </View>
  );
}

/**
 * Detalle del gasto: «Corregir la clase» solo con intención vigente; con deuda en cualquier sentido, la limitación literal (8quater) y su
 * ampliación. PAG: «Quién pagó», lo que salió de tus cuentas, las posiciones en su sentido y «Ver el movimiento en la cuenta».
 */
export function DetalleGastoPropiedad(p: { lectura: LecturaGastoPropiedad; onCorregir: () => void; nombres?: Record<string, string>;
  onVerMovimientos?: (cuentaId: string) => void }) {
  const { c } = useTema();
  const l = p.lectura;
  const nombre = (a: string) => p.nombres?.[a] ?? 'Otra persona';
  const pos = l.pago?.posiciones ?? [];
  const cuentaMov = l.pago?.cuentas_movimiento?.[0] ?? null;
  return (
    <View testID="gprop-detalle" style={{ gap: espacio.m }}>
      <Tarjeta>
        <Linea testID="gprop-det-clase" etiqueta="Clase" valor={l.clase === 'MEJORA' ? 'Mejora · suma al coste' : 'Gasto'} />
        <Linea testID="gprop-det-importe" etiqueta="Importe" valor={formatearEur(l.importe)} fuerte />
        <Linea testID="gprop-det-fecha" etiqueta="Fecha" valor={diaMesAnioIso(l.fecha)} />
        {l.con_deuda && pos.length === 0 ? <Linea testID="gprop-det-deuda" etiqueta="Derecho de cobro" valor="Sí" /> : null}
        {pos.map((x) => (
          <Linea key={`${x.actor_id}-${x.tipo}`} testID={`gprop-det-pos-${x.actor_id}`}
            etiqueta={x.sentido === 'LE_DEBO' ? `Le debes a ${nombre(x.actor_id)}` : `${nombre(x.actor_id)} te debe`} valor={formatearEur(x.importe)} />
        ))}
      </Tarjeta>
      {l.pago ? (
        <>
          <RotuloGrupo texto="Quién pagó" />
          <Tarjeta testID="gprop-det-pago">
            {l.pago.declarado ? l.pago.pagos.map((x) => (
              <Linea key={x.actor_id} testID={`gprop-det-pago-${x.actor_id}`} etiqueta={`${nombre(x.actor_id)}${x.con_movimiento ? ' · desde tu cuenta' : ' · por su cuenta'}`}
                valor={formatearEur(x.importe)} />
            )) : <Text testID="gprop-det-pago-sin-declarar" style={[tipo.body, s.pad, { color: c.textSecondary }]}>{TEXTO_PAGO_SIN_DECLARAR}</Text>}
            <Linea testID="gprop-det-sale" etiqueta="Salió de tus cuentas" valor={formatearEur(l.pago.sale_de_mis_cuentas)} />
          </Tarjeta>
          {cuentaMov && p.onVerMovimientos ? <BotonTexto testID="gprop-ver-movimiento" titulo="Ver el movimiento en la cuenta" onPress={() => p.onVerMovimientos!(cuentaMov)} /> : null}
        </>
      ) : null}
      {ofreceCorregir(l) ? <BotonTexto testID="gprop-corregir-clase" titulo="Corregir la clase" onPress={p.onCorregir} /> : null}
      {muestraLimitacion(l) ? <Text testID="gprop-limitacion" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_LIMITACION_8QUATER}</Text> : null}
      {muestraLimitacion(l) ? <Text testID="gprop-limitacion-sentido" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_LIMITACION_SENTIDO}</Text> : null}
    </View>
  );
}

/** C2 · Reformas y mejoras de la propiedad: lista (muestra todo lo registrado, también reparaciones y gastos) con lo que suma al coste y lo que es gasto, detalle y corrección. */
export function GastosPropiedadScreen(p: {
  cliente: ClienteApi;
  patrimonio: ClientePatrimonioB3;
  vista: VistaPropiedad;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (cambio: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  type Nivel = { n: 'LISTA' } | { n: 'DETALLE'; id: string } | { n: 'CORREGIR'; l: LecturaGastoPropiedad } | { n: 'NUEVO' } | { n: 'HISTORICA' }
    | { n: 'MOVIMIENTOS'; cuentaId: string; hechoId: string };
  const [nivel, setNivel] = useState<Nivel>({ n: 'LISTA' });
  const [filas, setFilas] = useState<FilaGastoPropiedad[] | null>(null);
  const [lectura, setLectura] = useState<LecturaGastoPropiedad | null>(null);
  const [cambio, setCambio] = useState(false);
  const cargar = async () => {
    setFilas(null);
    const r = await p.patrimonio.listarGastos(p.vista.id);
    setFilas(r.tipo === 'OK' ? r.datos.gastos : []);
  };
  const abrir = async (id: string) => {
    setNivel({ n: 'DETALLE', id });
    setLectura(null);
    const r = await p.patrimonio.leerGasto(p.vista.id, id);
    if (r.tipo === 'OK') setLectura(r.datos);
  };
  useEffect(() => { void cargar(); }, []);
  const res = useMemo(() => resumenGastos(filas ?? []), [filas]);
  const volver = (hubo: boolean) => {
    if (hubo) setCambio(true);
    setNivel({ n: 'LISTA' });
    void cargar();
  };
  if (nivel.n === 'NUEVO') return <GastoPropiedadScreen cliente={p.cliente} patrimonio={p.patrimonio} vista={p.vista} nuevoId={p.nuevoId} ahora={p.ahora} onCerrar={volver} />;
  if (nivel.n === 'HISTORICA') return <MejoraHistoricaScreen patrimonio={p.patrimonio} vista={p.vista} nuevoId={p.nuevoId} ahora={p.ahora} onCerrar={volver} />;
  if (nivel.n === 'MOVIMIENTOS' && p.patrimonio.movimientosCuenta)
    return <MovimientosCuentaScreen cargar={(pag) => p.patrimonio.movimientosCuenta!(nivel.cuentaId, pag)} resaltar={nivel.hechoId} onCerrar={() => void abrir(nivel.hechoId)} />;
  if (nivel.n === 'CORREGIR')
    return (
      <CorregirClaseScreen cliente={p.cliente} patrimonio={p.patrimonio} propiedadId={p.vista.id} lectura={nivel.l}
        onCerrar={(hubo) => { if (hubo) setCambio(true); void abrir(nivel.l.hecho_id); }} />
    );
  return (
    <View testID="gastos-propiedad" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={nivel.n === 'DETALLE' ? 'Gasto de la propiedad' : `Reformas y mejoras · ${p.vista.nombre}`} testIDCancelar="gastos-cerrar"
        onCancelar={() => (nivel.n === 'DETALLE' ? volver(false) : p.onCerrar(cambio))} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {nivel.n === 'DETALLE' ? (
          lectura ? <DetalleGastoPropiedad lectura={lectura} onCorregir={() => setNivel({ n: 'CORREGIR', l: lectura })}
            nombres={Object.fromEntries((p.vista.titularidad?.partes ?? []).map((x) => [x.actor_id, x.yo ? 'Tú' : x.nombre ?? 'Otra persona']))}
            onVerMovimientos={p.patrimonio.movimientosCuenta ? (cuentaId) => setNivel({ n: 'MOVIMIENTOS', cuentaId, hechoId: lectura.hecho_id }) : undefined} />
            : <EstadoDato testID="gprop-detalle-cargando" estado="CARGANDO" />
        ) : (
          <>
            <Tarjeta testID="gastos-resumen">
              <Linea testID="gastos-mejoras" etiqueta="Mejoras · suman al coste" valor={formatearEur(res.mejoras)} />
              <Linea testID="gastos-gastos" etiqueta="Reparaciones y gastos · gasto" valor={formatearEur(res.gastos)} />
              <Linea testID="gastos-total" etiqueta="Total pagado" valor={formatearEur(res.total)} fuerte />
            </Tarjeta>
            {filas === null ? <EstadoDato testID="gastos-cargando" estado="CARGANDO" /> : null}
            {filas && filas.length > 0 ? (
              <Tarjeta testID="gastos-lista">
                {filas.map((f, i) => (
                  <FilaLista key={f.hecho_id} testID={`gastos-fila-${f.hecho_id}`} ultima={i === filas.length - 1}
                    titulo={f.nota ?? (f.clase === 'MEJORA' ? 'Mejora' : 'Gasto')}
                    detalle={`${diaMesAnioIso(f.fecha)} · ${f.clase === 'MEJORA' ? 'Mejora' : 'Gasto'} · ${formatearEur(f.importe)}`} onPress={() => void abrir(f.hecho_id)} />
                ))}
              </Tarjeta>
            ) : null}
            <BotonPrimario testID="gastos-nuevo" titulo="Añadir una reforma o mejora" onPress={() => setNivel({ n: 'NUEVO' })} />
            <BotonTexto testID="gastos-historica" titulo="Anotar una mejora antigua" onPress={() => setNivel({ n: 'HISTORICA' })} />
          </>
        )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  linea: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.s },
  pad: { paddingHorizontal: espacio.m, paddingVertical: espacio.s },
});
