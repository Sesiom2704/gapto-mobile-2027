// ============================================================
// GAPTO MOBILE 2027
// Fichero: CompraScreen.tsx
// Ruta: mobile/src/screens/CompraScreen.tsx
// Descripción: Registrar la compra de una propiedad (F06-01 B2 · C-COMPRA-01, sin hipoteca; lámina F06-01 v0.9 B1 Precio, B2 Cómo se pagó, B3 Gastos de la compra, B3b ¿De quién es el coste?, B4 Resumen y B6 Así se ve en Día a día) y añadir un gasto de la compra después (C-COMPRA-03, `GastoCompraScreen`, desde el detalle). Tarea inmersiva por pasos. Todas las fechas usan el `CampoFecha` de UX-1 (D-UX1-B2-01). B3b: ninguna opción viene marcada; «Según la titularidad» propone la titularidad de la propiedad EN LA ESCRITURA para todos los registros (AJ-TR1-10) y avisa de que los gastos anteriores no usan la titularidad de su fecha; «Otro reparto» y «No lo sé» siempre disponibles; nunca YO 100 por defecto. B4 separa el coste (precio + gastos), lo que sale de tus cuentas y el gasto del mes (0,00 €); «Se guarda todo junto o nada». Rechazos: ATRIBUCION_PROPUESTA_DESFASADA vuelve a B3b con la propuesta releída; VERSION_DESFASADA → Recargar. Sin hipoteca (B2b/B2c), sin desglose (D4) y sin «Repetir hoy». La declaración «no faltan gastos» (consumidor de 0352) solo aparece con CONSUMIDORES_0352_HABILITADOS (hoy false).
// Versión: 0.1.0 (F06 T1-F06 B2 N1)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaElegible } from '../api/cliente';
import type { ClientePatrimonio, ParteEnFecha } from '../api/patrimonio';
import type { VistaPropiedad } from '../api/propiedades';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { CampoFecha } from '../components/CampoFecha';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef, RotuloGrupo, Tarjeta } from '../components/Formulario';
import {
  avisoGastosAnteriores, BorradorCompra, textoPagado, borradorInicial, CONCEPTOS, CONSUMIDORES_0352_HABILITADOS, EleccionAtribucion, faltasAtribucion, faltasGasto,
  faltasGastos, faltasPagos, faltasPrecio, filasDiaADia, GastoBorrador, NOMBRE_CONCEPTO, NOMBRE_ROL, PagoBorrador, payloadCompra,
  payloadGastoCompra, resumen, ROLES, TEXTO_DESFASADA, TEXTO_GASTOS, TEXTO_INDETERMINADO_COMPRA, TEXTO_NADIE_MARCADO, TEXTO_SIN_HIPOTECA,
  TEXTO_SIN_TITULARIDAD, TEXTO_VALOR_REFERENCIA, textoErrorCompra, textoPartes, textoPropuestaEscritura,
} from '../domain/compra';
import { ddmmaaaaAIso, diaMesAnioIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { ConflictoPropiedad } from './PropiedadEditarScreen';

type Paso = 'PRECIO' | 'PAGOS' | 'GASTOS' | 'ATRIBUCION' | 'RESUMEN' | 'HECHO';
const PASOS: Paso[] = ['PRECIO', 'PAGOS', 'GASTOS', 'ATRIBUCION', 'RESUMEN'];

/** Fecha con el CampoFecha único de UX-1: campo dd/mm/aaaa con máscara y calendario. */
function Fecha(p: { testID: string; etiqueta: string; iso: string; hoyIso: string; onCambiar: (iso: string) => void }) {
  const [texto, setTexto] = useState<string>(esFechaIso(p.iso) ? isoADdmmaaaa(p.iso) : p.iso);
  return (
    <CampoFecha testID={p.testID} etiqueta={p.etiqueta} hoyIso={p.hoyIso} texto={texto}
      onTexto={(t) => { setTexto(t); p.onCambiar(ddmmaaaaAIso(t) ?? t); }} />
  );
}

function Cuentas(p: { testID: string; cuentas: CuentaElegible[]; valor: string | null; onCambiar: (id: string) => void }) {
  if (p.cuentas.length === 0) return <EstadoDato testID={`${p.testID}-sin`} estado="NO_DISPONIBLE" detalle="Sin cuentas para pagar" />;
  return (
    <View style={ef.chips}>
      {p.cuentas.map((c) => (
        <Chip key={c.cuenta_id} testID={`${p.testID}-${c.cuenta_id}`} etiqueta={c.nombre} seleccionado={p.valor === c.cuenta_id} onPress={() => p.onCambiar(c.cuenta_id)} />
      ))}
    </View>
  );
}

/** B3b · ¿De quién es el coste? Ninguna opción marcada de antemano. */
export function EleccionCoste(p: {
  testID: string;
  propuesta: ParteEnFecha[] | null;
  textoPropuesta: string;
  eleccion: EleccionAtribucion;
  actores: { actor_id: string; nombre: string }[];
  onCambiar: (e: EleccionAtribucion) => void;
  aviso?: string | null;
}) {
  const { c } = useTema();
  const sinTitularidad = p.propuesta !== null && p.propuesta.length === 0;
  const manual = p.eleccion?.modo === 'MANUAL' ? p.eleccion.partes : null;
  return (
    <View testID={p.testID} style={{ gap: espacio.m }}>
      {p.propuesta === null ? <EstadoDato testID={`${p.testID}-cargando`} estado="CARGANDO" /> : null}
      {p.propuesta !== null && !sinTitularidad ? (
        <Chip testID={`${p.testID}-titularidad`} etiqueta={`${p.textoPropuesta}: ${textoPartes(p.propuesta)}`} seleccionado={p.eleccion?.modo === 'TITULARIDAD'}
          onPress={() => p.onCambiar({ modo: 'TITULARIDAD' })} />
      ) : null}
      {sinTitularidad ? <Text testID={`${p.testID}-sin-titularidad`} style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_SIN_TITULARIDAD}</Text> : null}
      <Chip testID={`${p.testID}-manual`} etiqueta="Otro reparto · indica cuánto es de cada uno" seleccionado={p.eleccion?.modo === 'MANUAL'}
        onPress={() => p.onCambiar({ modo: 'MANUAL', partes: Object.fromEntries(p.actores.map((a) => [a.actor_id, ''])) })} />
      {manual ? p.actores.map((a) => (
        <CampoTexto key={a.actor_id} testID={`${p.testID}-pct-${a.actor_id}`} etiqueta={`Porcentaje de ${a.nombre}`} marcador="%"
          valor={manual[a.actor_id] ?? ''} onCambiar={(t) => p.onCambiar({ modo: 'MANUAL', partes: { ...manual, [a.actor_id]: t } })} />
      )) : null}
      <Chip testID={`${p.testID}-no-lo-se`} etiqueta="No lo sé · tu parte quedará «sin indicar»" seleccionado={p.eleccion?.modo === 'NO_LO_SE'}
        onPress={() => p.onCambiar({ modo: 'NO_LO_SE' })} />
      {p.aviso ? <Text testID={`${p.testID}-aviso`} style={[tipo.footnote, { color: c.warningText }]}>{p.aviso}</Text> : null}
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NADIE_MARCADO}</Text>
    </View>
  );
}

const actoresDe = (v: VistaPropiedad, propuesta: ParteEnFecha[] | null) => {
  const base = propuesta && propuesta.length > 0 ? propuesta : v.titularidad.partes;
  return base.map((x) => ({ actor_id: x.actor_id, nombre: x.yo ? 'ti' : x.nombre ?? 'otra persona' }));
};

function Linea(p: { testID: string; etiqueta: string; valor: string; fuerte?: boolean }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={s.linea}>
      <Text style={[p.fuerte ? tipo.bodyEmphasis : tipo.body, { color: c.textPrimary, flex: 1 }]}>{p.etiqueta}</Text>
      <Text testID={`${p.testID}-valor`} style={[p.fuerte ? tipo.bodyEmphasis : tipo.body, { color: c.textPrimary }]}>{p.valor}</Text>
    </View>
  );
}

export function CompraScreen(p: {
  cliente: ClienteApi;
  patrimonio: ClientePatrimonio;
  vista: VistaPropiedad;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (actualizada: VistaPropiedad | null) => void;
  onRecargar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const [paso, setPaso] = useState<Paso>('PRECIO');
  const [b, setB] = useState<BorradorCompra>(() => ({
    ...borradorInicial(hoyIso),
    pagos: [{ id: p.nuevoId(), rol: 'FIRMA', cuentaId: null, fecha: hoyIso, importe: '' }],
  }));
  const [cuentas, setCuentas] = useState<CuentaElegible[]>([]);
  const [propuesta, setPropuesta] = useState<ParteEnFecha[] | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [avisoAtr, setAvisoAtr] = useState<string | null>(null);
  const [conflicto, setConflicto] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [resultado, setResultado] = useState<VistaPropiedad | null>(null);
  const intencion = useRef(p.nuevoId());

  useEffect(() => {
    void p.cliente.cuentasElegibles('GASTO', hoyIso).then((r) => { if (r.tipo === 'OK') setCuentas(r.datos.cuentas); });
  }, []);
  const cargarPropuesta = async () => {
    setPropuesta(null);
    const r = await p.patrimonio.titularidadEnFecha(p.vista.id, b.fechaEscritura);
    setPropuesta(r.tipo === 'OK' ? r.datos.partes : []);
  };
  useEffect(() => {
    if (paso === 'ATRIBUCION') void cargarPropuesta();
  }, [paso]);

  const faltas = paso === 'PRECIO' ? faltasPrecio(b) : paso === 'PAGOS' ? faltasPagos(b) : paso === 'GASTOS' ? faltasGastos(b)
    : paso === 'ATRIBUCION' ? faltasAtribucion(b.atribucion, propuesta) : [];
  const nombreCuenta = (id: string | null) => cuentas.find((x) => x.cuenta_id === id)?.nombre ?? 'Cuenta';
  const r = resumen(b);
  const indice = PASOS.indexOf(paso);
  const atras = () => (indice > 0 ? setPaso(PASOS[indice - 1]) : p.onCerrar(null));
  const setPago = (i: number, x: Partial<PagoBorrador>) => setB({ ...b, pagos: b.pagos.map((y, j) => (j === i ? { ...y, ...x } : y)) });
  const setGasto = (i: number, x: Partial<GastoBorrador>) => setB({ ...b, gastos: b.gastos.map((y, j) => (j === i ? { ...y, ...x } : y)) });

  const guardar = async () => {
    if (ocupado) return;
    setOcupado(true);
    setAviso(null);
    const res = await p.patrimonio.registrarCompra(p.vista.id, payloadCompra(intencion.current, p.vista.row_version, b, propuesta));
    setOcupado(false);
    if (res.tipo === 'OK') {
      setResultado(res.datos.propiedad);
      return setPaso('HECHO');
    }
    if (res.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO_COMPRA });
    if (res.codigo === 'VERSION_DESFASADA') return setConflicto(true);
    if (res.codigo === 'ATRIBUCION_PROPUESTA_DESFASADA') {
      // Intención nueva: la petición rechazada no escribió nada; el contenido cambia al elegir otra vez.
      intencion.current = p.nuevoId();
      setB({ ...b, atribucion: null });
      setAvisoAtr(TEXTO_DESFASADA);
      return setPaso('ATRIBUCION');
    }
    setAviso({ tipo: 'AVISO', texto: textoErrorCompra(res.codigo, res.mensaje) });
  };

  if (conflicto) return <ConflictoPropiedad titulo="La compra" onCancelar={() => p.onCerrar(null)} onRecargar={p.onRecargar} />;

  if (paso === 'HECHO') {
    return (
      <View testID="compra-hecho" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Compra guardada" testIDCancelar="compra-hecho-cerrar" onCancelar={() => p.onCerrar(resultado)} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <RotuloGrupo texto="Así se ve en Día a día" />
          <Tarjeta testID="compra-dia">
            {filasDiaADia(b, p.vista.nombre, nombreCuenta).map((f) => (
              <View key={f.clave} testID={`compra-dia-${f.clave}`} style={s.fila}>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={[tipo.body, { color: c.textPrimary }]}>{f.titulo}</Text>
                  <Text style={[tipo.caption, { color: c.textSecondary }]}>{`${diaMesAnioIso(f.fecha)} · ${f.detalle}`}</Text>
                </View>
                <Text testID={`compra-dia-${f.clave}-importe`} style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{f.importe}</Text>
              </View>
            ))}
          </Tarjeta>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>Cada pago aparece como lo que es, con su importe de cuenta. No suma al gasto del mes.</Text>
          <BotonPrimario testID="compra-listo" titulo="Listo" onPress={() => p.onCerrar(resultado)} />
        </ScrollView>
      </View>
    );
  }

  const titulo = paso === 'ATRIBUCION' ? '¿De quién es este coste?' : paso === 'RESUMEN' ? 'Revisar la compra' : 'La compra';
  return (
    <View testID={`compra-paso-${paso.toLowerCase()}`} style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={titulo} testIDCancelar="compra-cancelar" onCancelar={() => p.onCerrar(null)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="compra-aviso" aviso={aviso} /> : null}
        {paso === 'PRECIO' ? (
          <>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>1 de 3 · Precio</Text>
            <Campo etiqueta="Precio de compra (escritura)">
              <CampoTexto testID="compra-precio" etiqueta="Precio de compra" marcador="Ej.: 200.000,00" valor={b.precio} onCambiar={(t) => setB({ ...b, precio: t })} />
            </Campo>
            <Campo etiqueta="Fecha de la escritura">
              <Fecha testID="compra-escritura" etiqueta="Fecha de la escritura, día barra mes barra año" iso={b.fechaEscritura} hoyIso={hoyIso}
                onCambiar={(iso) => setB({ ...b, fechaEscritura: iso, pagos: b.pagos.map((x) => (x.rol === 'FIRMA' ? { ...x, fecha: iso } : x)) })} />
            </Campo>
            <Campo etiqueta="Valor de referencia del Catastro" opcional>
              <CampoTexto testID="compra-referencia" etiqueta="Valor de referencia" marcador="Ej.: 210.000,00" valor={b.valorReferencia} onCambiar={(t) => setB({ ...b, valorReferencia: t })} />
            </Campo>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_VALOR_REFERENCIA}</Text>
          </>
        ) : null}
        {paso === 'PAGOS' ? (
          <>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>2 de 3 · ¿Cómo se pagó el precio?</Text>
            <RotuloGrupo texto="Con tu dinero" />
            {b.pagos.map((x, i) => (
              <Tarjeta key={x.id} testID={`compra-pago-${i}`}>
                <View style={{ padding: espacio.m, gap: espacio.s }}>
                  <View style={ef.chips}>
                    {ROLES.map((rol) => <Chip key={rol} testID={`compra-pago-${i}-rol-${rol}`} etiqueta={NOMBRE_ROL[rol]} seleccionado={x.rol === rol} onPress={() => setPago(i, { rol, ...(rol === 'FIRMA' ? { fecha: b.fechaEscritura } : {}) })} />)}
                  </View>
                  <Cuentas testID={`compra-pago-${i}-cuenta`} cuentas={cuentas} valor={x.cuentaId} onCambiar={(id) => setPago(i, { cuentaId: id })} />
                  <Fecha testID={`compra-pago-${i}-fecha`} etiqueta="Fecha del pago" iso={x.fecha} hoyIso={hoyIso} onCambiar={(iso) => setPago(i, { fecha: iso })} />
                  <CampoTexto testID={`compra-pago-${i}-importe`} etiqueta="Importe del pago" marcador="0,00" valor={x.importe} onCambiar={(t) => setPago(i, { importe: t })} />
                  {b.pagos.length > 1 ? <BotonTexto testID={`compra-pago-${i}-quitar`} titulo="Quitar este pago" critico onPress={() => setB({ ...b, pagos: b.pagos.filter((_, j) => j !== i) })} /> : null}
                </View>
              </Tarjeta>
            ))}
            <BotonTexto testID="compra-pago-anadir" titulo="+ Añadir pago" onPress={() => setB({ ...b, pagos: [...b.pagos, { id: p.nuevoId(), rol: 'ARRAS', cuentaId: null, fecha: b.fechaEscritura, importe: '' }] })} />
            <Linea testID="compra-pagado" etiqueta="Pagado entre todo" valor={formatearEur(textoPagado(b))} fuerte />
            <Text testID="compra-sin-hipoteca" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_HIPOTECA}</Text>
          </>
        ) : null}
        {paso === 'GASTOS' ? (
          <>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>3 de 3 · Gastos de la compra</Text>
            {b.gastos.map((g, i) => (
              <Tarjeta key={g.id} testID={`compra-gasto-${i}`}>
                <EditorGasto prefijo={`compra-gasto-${i}`} g={g} cuentas={cuentas} hoyIso={hoyIso} onCambiar={(x) => setGasto(i, x)}
                  onQuitar={() => setB({ ...b, gastos: b.gastos.filter((_, j) => j !== i) })} />
              </Tarjeta>
            ))}
            <BotonTexto testID="compra-gasto-anadir" titulo="+ Añadir gasto de la compra"
              onPress={() => setB({ ...b, gastos: [...b.gastos, { id: p.nuevoId(), concepto: 'ITP', cuentaId: null, fechaEconomica: b.fechaEscritura, fechaPago: b.fechaEscritura, importe: '', nota: '' }] })} />
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_GASTOS}</Text>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>Si no los tienes todos, puedes añadirlos después desde la propiedad.</Text>
          </>
        ) : null}
        {paso === 'ATRIBUCION' ? (
          <EleccionCoste testID="compra-atr" propuesta={propuesta} textoPropuesta={textoPropuestaEscritura(p.vista.nombre, b.fechaEscritura)}
            eleccion={b.atribucion} actores={actoresDe(p.vista, propuesta)} onCambiar={(e) => { setAvisoAtr(null); setB({ ...b, atribucion: e }); }}
            aviso={avisoAtr ?? (b.atribucion?.modo === 'TITULARIDAD' ? avisoGastosAnteriores(b) : null)} />
        ) : null}
        {paso === 'RESUMEN' ? (
          <>
            <RotuloGrupo texto="Coste de adquisición" />
            <Tarjeta testID="compra-resumen">
              <Linea testID="compra-res-precio" etiqueta="Precio" valor={formatearEur(parsearImporte(b.precio).ok ? (parsearImporte(b.precio) as { valor: string }).valor : '0')} />
              {b.gastos.map((g) => <Linea key={g.id} testID={`compra-res-${g.id}`} etiqueta={NOMBRE_CONCEPTO[g.concepto]} valor={formatearEur((parsearImporte(g.importe) as { valor: string }).valor)} />)}
              <Linea testID="compra-res-total" etiqueta="Total" valor={formatearEur(r.coste)} fuerte />
              <Linea testID="compra-res-estado" etiqueta="Estado" valor={CONSUMIDORES_0352_HABILITADOS && b.completo ? 'Completo' : 'Parcial · puedes añadir gastos'} />
              <Linea testID="compra-res-sale" etiqueta="Sale de tus cuentas" valor={formatearEur(r.sale.replace('-', ''))} />
              <Linea testID="compra-res-gasto-mes" etiqueta="Cuenta como gasto del mes" valor={formatearEur(r.gastoMes)} />
            </Tarjeta>
            {CONSUMIDORES_0352_HABILITADOS ? (
              <Chip testID="compra-completo" etiqueta="No faltan gastos: el coste de la compra está completo" seleccionado={b.completo} onPress={() => setB({ ...b, completo: !b.completo })} />
            ) : null}
            <Text testID="compra-registros" style={[tipo.footnote, { color: c.textSecondary }]}>
              {`Se crean ${r.registros} ${r.registros === 1 ? 'registro' : 'registros'} con ${r.pagos} ${r.pagos === 1 ? 'pago' : 'pagos'}. Se guarda todo junto o nada.`}
            </Text>
          </>
        ) : null}
        {faltas.length > 0 ? <Text testID="compra-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        {paso === 'RESUMEN' ? (
          <BotonPrimario testID="compra-guardar" titulo="Guardar la compra" cargando={ocupado} onPress={() => void guardar()} />
        ) : (
          <BotonPrimario testID="compra-continuar" titulo="Continuar" deshabilitado={faltas.length > 0} onPress={() => setPaso(PASOS[indice + 1])} />
        )}
        {indice > 0 ? <BotonTexto testID="compra-atras" titulo="‹ Atrás" onPress={atras} /> : null}
      </ScrollView>
    </View>
  );
}

function EditorGasto(p: { prefijo: string; g: GastoBorrador; cuentas: CuentaElegible[]; hoyIso: string; onCambiar: (x: Partial<GastoBorrador>) => void; onQuitar?: () => void }) {
  return (
    <View style={{ padding: espacio.m, gap: espacio.s }}>
      <View style={ef.chips}>
        {CONCEPTOS.map((k) => <Chip key={k} testID={`${p.prefijo}-concepto-${k}`} etiqueta={NOMBRE_CONCEPTO[k]} seleccionado={p.g.concepto === k} onPress={() => p.onCambiar({ concepto: k })} />)}
      </View>
      <CampoTexto testID={`${p.prefijo}-importe`} etiqueta="Importe del gasto" marcador="0,00" valor={p.g.importe} onCambiar={(t) => p.onCambiar({ importe: t })} />
      <Cuentas testID={`${p.prefijo}-cuenta`} cuentas={p.cuentas} valor={p.g.cuentaId} onCambiar={(id) => p.onCambiar({ cuentaId: id })} />
      <Campo etiqueta="Fecha del gasto">
        <Fecha testID={`${p.prefijo}-fecha`} etiqueta="Fecha del gasto" iso={p.g.fechaEconomica} hoyIso={p.hoyIso} onCambiar={(iso) => p.onCambiar({ fechaEconomica: iso })} />
      </Campo>
      <Campo etiqueta="Fecha de pago">
        <Fecha testID={`${p.prefijo}-pago`} etiqueta="Fecha de pago" iso={p.g.fechaPago} hoyIso={p.hoyIso} onCambiar={(iso) => p.onCambiar({ fechaPago: iso })} />
      </Campo>
      <CampoTexto testID={`${p.prefijo}-nota`} etiqueta="Nota" marcador="Opcional" valor={p.g.nota} onCambiar={(t) => p.onCambiar({ nota: t })} />
      {p.onQuitar ? <BotonTexto testID={`${p.prefijo}-quitar`} titulo="Quitar este gasto" critico onPress={p.onQuitar} /> : null}
    </View>
  );
}

/** C-COMPRA-03 · Añadir un gasto de la compra después (desde el detalle). La propuesta se lee en la fecha del gasto. */
export function GastoCompraScreen(p: {
  cliente: ClienteApi;
  patrimonio: ClientePatrimonio;
  vista: VistaPropiedad;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (actualizada: VistaPropiedad | null) => void;
  onRecargar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const [g, setG] = useState<GastoBorrador>(() => ({ id: p.nuevoId(), concepto: 'OTRO', cuentaId: null, fechaEconomica: hoyIso, fechaPago: hoyIso, importe: '', nota: '' }));
  const [eleccion, setEleccion] = useState<EleccionAtribucion>(null);
  const [cuentas, setCuentas] = useState<CuentaElegible[]>([]);
  const [propuesta, setPropuesta] = useState<ParteEnFecha[] | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [conflicto, setConflicto] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const intencion = useRef(p.nuevoId());
  useEffect(() => {
    void p.cliente.cuentasElegibles('GASTO', hoyIso).then((r) => { if (r.tipo === 'OK') setCuentas(r.datos.cuentas); });
  }, []);
  useEffect(() => {
    if (!esFechaIso(g.fechaEconomica)) return;
    setPropuesta(null);
    setEleccion((e) => (e?.modo === 'TITULARIDAD' ? null : e));
    void p.patrimonio.titularidadEnFecha(p.vista.id, g.fechaEconomica).then((r) => setPropuesta(r.tipo === 'OK' ? r.datos.partes : []));
  }, [g.fechaEconomica]);
  const faltas = [...faltasGasto(g), ...faltasAtribucion(eleccion, propuesta)];

  const guardar = async () => {
    if (ocupado || faltas.length > 0) return;
    setOcupado(true);
    setAviso(null);
    const r = await p.patrimonio.gastoCompraPosterior(p.vista.id, payloadGastoCompra(intencion.current, p.vista.row_version, g, eleccion, propuesta));
    setOcupado(false);
    if (r.tipo === 'OK') return p.onCerrar(r.datos.propiedad);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO_COMPRA });
    if (r.codigo === 'VERSION_DESFASADA') return setConflicto(true);
    if (r.codigo === 'ATRIBUCION_PROPUESTA_DESFASADA') {
      intencion.current = p.nuevoId();
      setEleccion(null);
      void p.patrimonio.titularidadEnFecha(p.vista.id, g.fechaEconomica).then((x) => setPropuesta(x.tipo === 'OK' ? x.datos.partes : []));
    }
    setAviso({ tipo: 'AVISO', texto: textoErrorCompra(r.codigo, r.mensaje) });
  };

  if (conflicto) return <ConflictoPropiedad titulo="Gasto de la compra" onCancelar={() => p.onCerrar(null)} onRecargar={p.onRecargar} />;
  return (
    <View testID="compra03" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo="Gasto de la compra" testIDCancelar="compra03-cancelar" onCancelar={() => p.onCerrar(null)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="compra03-aviso" aviso={aviso} /> : null}
        <Tarjeta testID="compra03-gasto">
          <EditorGasto prefijo="compra03" g={g} cuentas={cuentas} hoyIso={hoyIso} onCambiar={(x) => setG({ ...g, ...x })} />
        </Tarjeta>
        <RotuloGrupo texto="¿De quién es este coste?" />
        <EleccionCoste testID="compra03-atr" propuesta={propuesta}
          textoPropuesta={esFechaIso(g.fechaEconomica) ? `Según la titularidad de ${p.vista.nombre} el ${diaMesAnioIso(g.fechaEconomica)}` : 'Según la titularidad'}
          eleccion={eleccion} actores={actoresDe(p.vista, propuesta)} onCambiar={setEleccion} />
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>Suma al coste de la compra. No es gasto del mes.</Text>
        {faltas.length > 0 ? <Text testID="compra03-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        <BotonPrimario testID="compra03-guardar" titulo="Guardar el gasto" cargando={ocupado} deshabilitado={faltas.length > 0} onPress={() => void guardar()} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  linea: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.s },
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.m },
});
