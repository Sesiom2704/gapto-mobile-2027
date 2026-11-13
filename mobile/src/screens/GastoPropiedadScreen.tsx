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
// Versión: 0.2.1 (F06 T1-F06 B3 ajuste N3 · KO visual iPhone casilla 7): las fechas de B3 (alta de reforma y mejora antigua)
//   muestran los chips «Hoy · Ayer · Otra fecha» con el patrón de RegistroGasto/PropiedadValor (Hoy por defecto, ≤ hoy).
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
  muestraLimitacion, NOMBRE_CLASE, ofreceCorregir, ofreceDeuda, partesEfectivas, payloadCorreccion, payloadGastoPropiedad,
  payloadMejoraHistorica, repartirImporte, repartoInicial, resumenGastos, seleccionInicial, SeleccionCorreccion, TEXTO_CUENTA_COMPARTIDA,
  TEXTO_DESFASADA, TEXTO_IMPACTO_DESFASADO, TEXTO_INDETERMINADO, TEXTO_LIMITACION_8QUATER, TEXTO_SE_CREA_DERECHO,
  TEXTO_SIN_PAGO, TEXTO_SIN_TITULARIDAD, textoError, textoPropuesta,
} from '../domain/gasto_propiedad';
import { formatearEur, parsearImporte } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

/** Alta de B3 (decisión 2026-11-13): solo «Reforma o mejora». */
const TEXTO_CLASE_ALTA = 'Reforma o mejora (aumenta el valor)';
const TEXTO_GASTOS_EN_REGISTRAR = 'Los gastos corrientes y las reparaciones se registran desde «Registrar gasto».';

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
        <CampoTexto key={a.actor_id} testID={`${p.testID}-pct-${a.actor_id}`} etiqueta={`Porcentaje de ${a.yo ? 'ti' : a.nombre ?? 'otra persona'}`} marcador="%"
          valor={manual[a.actor_id] ?? ''} onCambiar={(t) => p.onCambiar({ modo: 'MANUAL', partes: { ...manual, [a.actor_id]: t } })} />
      )) : null}
      <Chip testID={`${p.testID}-no-lo-se`} etiqueta="No lo sé · tu parte quedará «sin indicar»" seleccionado={p.eleccion?.modo === 'NO_LO_SE'}
        onPress={() => p.onCambiar({ modo: 'NO_LO_SE' })} />
      {p.aviso ? <Text testID={`${p.testID}-aviso`} style={[tipo.footnote, { color: c.warningText }]}>{p.aviso}</Text> : null}
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>La propuesta sale de la titularidad de la propiedad en la fecha del gasto, nunca de la cuenta. Si la titularidad cambia más adelante, este reparto no cambia.</Text>
    </View>
  );
}

/** C-MEJ-01 · Gasto de una propiedad. */
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
  type Paso = 'DATOS' | 'REPARTO' | 'CONFIRMAR' | 'HECHO';
  const [paso, setPaso] = useState<Paso>('DATOS');
  // Decisión 2026-11-13: el alta solo registra reformas o mejoras; la clase va fijada (sin chip).
  const [b, setB] = useState<BorradorGastoPropiedad>(() => ({ ...borradorInicial(hoyIso), clase: 'MEJORA' }));
  const [cuentas, setCuentas] = useState<CuentaElegible[]>([]);
  const [prop, setProp] = useState<PropuestaGasto | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [avisoRep, setAvisoRep] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const intencion = useRef(p.nuevoId());
  const actores = actoresDe(p.vista, prop);

  useEffect(() => {
    if (!esFechaIso(b.fecha)) return;
    void p.cliente.cuentasElegibles('GASTO', b.fecha).then((r) => { if (r.tipo === 'OK') setCuentas(r.datos.cuentas); });
  }, [b.fecha]);
  const leerPropuesta = async () => {
    if (!esFechaIso(b.fecha)) return;
    setProp(null);
    const r = await p.patrimonio.propuestaGasto(p.vista.id, b.fecha, b.cuentaId);
    const nueva: PropuestaGasto = r.tipo === 'OK' ? r.datos : { fecha: b.fecha, propiedad_id: p.vista.id, nombre: p.vista.nombre, titularidad_disponible: false, partes: [], cuenta: null };
    setProp(nueva);
    setB((x) => alCambiarPropuesta(x, nueva, actoresDe(p.vista, nueva)));
  };
  // Relectura si cambian la fecha o la cuenta: lo que el usuario no tocó se vuelve a proponer.
  useEffect(() => { void leerPropuesta(); }, [b.fecha, b.cuentaId]);

  const concepto = b.nota.trim() || (b.clase ? NOMBRE_CLASE[b.clase].split(' (')[0] : 'Gasto');
  const mostrados: Derecho[] = derechos(b, prop, actores, `${concepto} · ${p.vista.nombre}`);
  const faltas = paso === 'DATOS' ? faltasDatos(b) : paso === 'REPARTO' ? faltasReparto(b, prop, actores) : [];
  const partes = partesEfectivas(b.reparto, prop, actores);
  const imp = repartirImporte(b.importe, partes);

  const cambiarReparto = (e: EleccionReparto) => {
    setAvisoRep(null);
    setB({ ...b, reparto: e, repartoTocado: true, deuda: completarDeuda(b.deuda, e, prop, actores) });
  };
  const cambiarDeuda = (actor: string, me: 'SI' | 'NO') => setB({ ...b, deudaTocada: true, deuda: { ...b.deuda, [actor]: { me_debe: me, importe: b.deuda[actor]?.importe ?? '' } } });
  const importeDeuda = (actor: string, t: string) => setB({ ...b, deudaTocada: true, deuda: { ...b.deuda, [actor]: { me_debe: 'SI', importe: t } } });

  const guardar = async () => {
    if (ocupado) return;
    setOcupado(true);
    setAviso(null);
    // `derechos_confirmados` = exactamente lo que muestra esta pantalla de confirmación (8bis).
    const r = await p.patrimonio.registrarGastoPropiedad(payloadGastoPropiedad(intencion.current, p.vista.id, b, prop, actores, mostrados));
    setOcupado(false);
    if (r.tipo === 'OK') return setPaso('HECHO');
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    if (r.codigo === 'ATRIBUCION_PROPUESTA_DESFASADA') {
      intencion.current = p.nuevoId();
      setB((x) => ({ ...x, repartoTocado: false, deudaTocada: false }));
      setAvisoRep(TEXTO_DESFASADA);
      setPaso('REPARTO');
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

  const titulo = paso === 'REPARTO' ? '¿De quién es el gasto?' : paso === 'CONFIRMAR' ? 'Revisar y confirmar' : 'Reforma o mejora';
  return (
    <View testID={`gprop-paso-${paso.toLowerCase()}`} style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={titulo} testIDCancelar="gprop-cancelar" onCancelar={() => p.onCerrar(false)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="gprop-aviso" aviso={aviso} /> : null}
        {paso === 'DATOS' ? (
          <>
            <Linea testID="gprop-propiedad" etiqueta="Propiedad" valor={p.vista.nombre} />
            <CampoTexto testID="gprop-importe" etiqueta="Importe" marcador="0,00" valor={b.importe} onCambiar={(t) => setB({ ...b, importe: t })} />
            <Campo etiqueta="Fecha del gasto y del pago">
              <Fecha testID="gprop-fecha" etiqueta="Fecha del gasto" iso={b.fecha} hoyIso={hoyIso} ayerIso={ayerIso} onCambiar={(iso) => setB({ ...b, fecha: iso })} />
            </Campo>
            <Campo etiqueta="Cuenta">
              {cuentas.length === 0 ? <EstadoDato testID="gprop-cuenta-sin" estado="NO_DISPONIBLE" detalle="Sin cuentas para pagar" /> : (
                <View style={ef.chips}>
                  {cuentas.map((x) => <Chip key={x.cuenta_id} testID={`gprop-cuenta-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={b.cuentaId === x.cuenta_id} onPress={() => setB({ ...b, cuentaId: x.cuenta_id })} />)}
                </View>
              )}
            </Campo>
            <CampoTexto testID="gprop-nota" etiqueta="Nota" marcador="Opcional" valor={b.nota} onCambiar={(t) => setB({ ...b, nota: t })} />
            <View testID="gprop-clase" style={{ gap: 2 }}>
              <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{TEXTO_CLASE_ALTA}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>{AYUDA_CLASE.MEJORA}</Text>
            </View>
            <Text testID="gprop-nota-registrar-gasto" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_GASTOS_EN_REGISTRAR}</Text>
          </>
        ) : null}
        {paso === 'REPARTO' ? (
          <>
            <Reparto testID="gprop-rep" propiedad={p.vista.nombre} prop={prop} eleccion={b.reparto} actores={actores} onCambiar={cambiarReparto} aviso={avisoRep} />
            {partes.some((x) => !x.yo) ? <RotuloGrupo texto="¿Te debe su parte?" /> : null}
            {cuentaCompartida(prop) && partes.some((x) => ofreceDeuda(x, imp[x.actor_id], prop, false)) ? (
              <Text testID="gprop-compartida" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CUENTA_COMPARTIDA}</Text>
            ) : null}
            {partes.filter((x) => !x.yo).map((x) => (
              ofreceDeuda(x, imp[x.actor_id], prop, false) ? (
                <Tarjeta key={x.actor_id} testID={`gprop-debe-${x.actor_id}`}>
                  <View style={{ padding: espacio.m, gap: espacio.s }}>
                    <Text style={[tipo.body, { color: c.textPrimary }]}>{`${x.nombre ?? 'Otra persona'} te debe su parte (${formatearEur(imp[x.actor_id] ?? '0')})`}</Text>
                    <View style={ef.chips}>
                      <Chip testID={`gprop-debe-${x.actor_id}-si`} etiqueta="Sí" seleccionado={b.deuda[x.actor_id]?.me_debe === 'SI'} onPress={() => cambiarDeuda(x.actor_id, 'SI')} />
                      <Chip testID={`gprop-debe-${x.actor_id}-no`} etiqueta="No, le invito" seleccionado={b.deuda[x.actor_id]?.me_debe === 'NO'} onPress={() => cambiarDeuda(x.actor_id, 'NO')} />
                    </View>
                    {cuentaCompartida(prop) && b.deuda[x.actor_id]?.me_debe === 'SI' ? (
                      <CampoTexto testID={`gprop-debe-${x.actor_id}-importe`} etiqueta={`¿Cuánto te debe ${x.nombre ?? 'esa persona'}?`} marcador="Indícalo tú"
                        valor={b.deuda[x.actor_id]?.importe ?? ''} onCambiar={(t) => importeDeuda(x.actor_id, t)} />
                    ) : null}
                  </View>
                </Tarjeta>
              ) : (
                <Text key={x.actor_id} testID={`gprop-no-debe-${x.actor_id}`} style={[tipo.footnote, { color: c.textSecondary }]}>
                  {`${x.nombre ?? 'Otra persona'}: ${x.naturaleza === 'EMPRESA' ? 'una empresa no genera aquí un derecho de cobro' : 'sin derecho de cobro'}`}
                </Text>
              )
            ))}
          </>
        ) : null}
        {paso === 'CONFIRMAR' ? (
          <>
            <Tarjeta testID="gprop-resumen">
              <Linea testID="gprop-res-clase" etiqueta="Clase" valor={TEXTO_CLASE_ALTA} />
              <Linea testID="gprop-res-importe" etiqueta="Importe" valor={formatearEur(parsearImporte(b.importe).ok ? (parsearImporte(b.importe) as { valor: string }).valor : '0')} fuerte />
              <Linea testID="gprop-res-fecha" etiqueta="Fecha" valor={esFechaIso(b.fecha) ? diaMesAnioIso(b.fecha) : b.fecha} />
              <Linea testID="gprop-res-gasto-mes" etiqueta="Cuenta como gasto del mes" valor={b.clase === 'MEJORA' ? 'No · suma al coste' : 'Sí'} />
            </Tarjeta>
            <RotuloGrupo texto="De quién es (lo que se guardará)" />
            <Tarjeta testID="gprop-atribucion">
              {atribucionTexto(b, prop, actores).map((x) => <Text key={x.actor_id} testID={`gprop-atr-${x.actor_id}`} style={[tipo.body, s.pad, { color: c.textPrimary }]}>{x.texto}</Text>)}
              {partes.length === 0 ? <Text testID="gprop-atr-sin" style={[tipo.body, s.pad, { color: c.textSecondary }]}>Tu parte quedará «sin indicar»</Text> : null}
            </Tarjeta>
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
            {mostrados.length > 0 ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>No es un movimiento: tus saldos y tu liquidez no cambian. Puedes volver atrás y cambiarlo a «No».</Text> : null}
          </>
        ) : null}
        {faltas.length > 0 ? <Text testID="gprop-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        {paso === 'CONFIRMAR' ? (
          <BotonPrimario testID="gprop-guardar" titulo="Confirmar y guardar" cargando={ocupado} onPress={() => void guardar()} />
        ) : (
          <BotonPrimario testID="gprop-continuar" titulo="Continuar" deshabilitado={faltas.length > 0} onPress={() => setPaso(paso === 'DATOS' ? 'REPARTO' : 'CONFIRMAR')} />
        )}
        {paso !== 'DATOS' ? <BotonTexto testID="gprop-atras" titulo="‹ Atrás" onPress={() => setPaso(paso === 'CONFIRMAR' ? 'REPARTO' : 'DATOS')} /> : null}
      </ScrollView>
    </View>
  );
}

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
        <CampoTexto testID="mh-importe" etiqueta="Importe" marcador="0,00" valor={importe} onCambiar={setImporte} />
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

/** Detalle del gasto: «Corregir la clase» solo con intención vigente; con deuda, la limitación literal (8quater). */
export function DetalleGastoPropiedad(p: { lectura: LecturaGastoPropiedad; onCorregir: () => void }) {
  const { c } = useTema();
  const l = p.lectura;
  return (
    <View testID="gprop-detalle" style={{ gap: espacio.m }}>
      <Tarjeta>
        <Linea testID="gprop-det-clase" etiqueta="Clase" valor={l.clase === 'MEJORA' ? 'Mejora · suma al coste' : 'Gasto'} />
        <Linea testID="gprop-det-importe" etiqueta="Importe" valor={formatearEur(l.importe)} fuerte />
        <Linea testID="gprop-det-fecha" etiqueta="Fecha" valor={diaMesAnioIso(l.fecha)} />
        {l.con_deuda ? <Linea testID="gprop-det-deuda" etiqueta="Derecho de cobro" valor="Sí" /> : null}
      </Tarjeta>
      {ofreceCorregir(l) ? <BotonTexto testID="gprop-corregir-clase" titulo="Corregir la clase" onPress={p.onCorregir} /> : null}
      {muestraLimitacion(l) ? <Text testID="gprop-limitacion" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_LIMITACION_8QUATER}</Text> : null}
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
  type Nivel = { n: 'LISTA' } | { n: 'DETALLE'; id: string } | { n: 'CORREGIR'; l: LecturaGastoPropiedad } | { n: 'NUEVO' } | { n: 'HISTORICA' };
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
          lectura ? <DetalleGastoPropiedad lectura={lectura} onCorregir={() => setNivel({ n: 'CORREGIR', l: lectura })} /> : <EstadoDato testID="gprop-detalle-cargando" estado="CARGANDO" />
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
