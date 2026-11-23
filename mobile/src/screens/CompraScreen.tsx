// ============================================================
// GAPTO MOBILE 2027
// Fichero: CompraScreen.tsx
// Ruta: mobile/src/screens/CompraScreen.tsx
// Descripción: Registrar la compra de una propiedad (F06-01 B2 · C-COMPRA-01, sin hipoteca; lámina F06-01 v0.9 B1 Precio, B2 Cómo se pagó, B3 Gastos de la compra, B3b ¿De quién es el coste?, B4 Resumen y B6 Así se ve en Día a día) y añadir un gasto de la compra después (C-COMPRA-03, `GastoCompraScreen`, desde el detalle). Tarea inmersiva por pasos. Todas las fechas usan el `CampoFecha` de UX-1 (D-UX1-B2-01). B3b: ninguna opción viene marcada; «Según la titularidad» propone la titularidad de la propiedad EN LA ESCRITURA para todos los registros (AJ-TR1-10) y avisa de que los gastos anteriores no usan la titularidad de su fecha; «Otro reparto» y «No lo sé» siempre disponibles; nunca YO 100 por defecto. B4 separa el coste (precio + gastos), lo que sale de tus cuentas y el gasto del mes (0,00 €); «Se guarda todo junto o nada». Rechazos: ATRIBUCION_PROPUESTA_DESFASADA vuelve a B3b con la propuesta releída; VERSION_DESFASADA → Recargar. Sin hipoteca (B2b/B2c), sin desglose (D4) y sin «Repetir hoy». La declaración «no faltan gastos» (consumidor de 0352) solo aparece con CONSUMIDORES_0352_HABILITADOS.
// Versión: 0.1.0 (F06 T1-F06 B2 N1)
// Versión: 0.2.0 (F06 T2-F06 A3-0352 (L-05); contrato A3-0352 v1.1 §6): UX-1 el chip «No faltan gastos» de B4 solo con la fecha de adquisición conocida (`puedeDeclararCompleto`), y «Completo» como PROPUESTA del resumen; UX-2 sin fecha, nota y la compra se guarda sin declaración; UX-4 COMPLETITUD_SIN_FECHA_DE_ADQUISICION muestra el texto del servidor, no guarda nada y recupera B4 sin el chip (intención nueva) para guardar sin declaración. GastoCompraScreen no cambia.
// Versión: 0.3.0 (F06 T3-F06 bloque 2 F06-01H, paso 10; contrato v0.4 §3.2 y §8; mandato v1.1 §15): bloque «Hipoteca» dentro de la compra, en B2 «¿Cómo se pagó el precio?», opcional («+ Añadir la hipoteca de esta compra»; sin ella la compra y su petición no cambian): banco, importe del préstamo, cuenta en la que el banco lo deja (texto sin «ingreso»; cuentas que pueden recibir dinero en la escritura), fijo o variable (sin valor por defecto), tipo anual, plazo en años o meses → n.º de cuotas, primera cuota (posterior a la escritura), cuenta de cargo, titularidad del préstamo propuesta (la de la propiedad en la escritura) y modificable, aviso «Cálculo mensual: tipo anual entre 12» y «Ver el cuadro» (W-HIP-00, sin escritura; CuadroPrevioScreen). B4 añade la hipoteca al resumen; B6 muestra el aviso `aviso_reparto_distinto` (O-H30) si el servidor lo devuelve. Rechazos de la hipoteca con texto propio, sin «ingreso» ni «cobro». La regla «los pagos suman el precio» no cambia.
// Versión: 0.4.0 (F06 T3-F06 · MANT N1 R-B2-06 (AJ-01), firma b88a3662…): guardar la compra usa `enviarCompraComprobando`: ante un timeout no dice que ha fallado, muestra «Comprobando…» y reenvía el MISMO cuerpo (misma intención; replay idempotente sin duplicar); si sigue sin confirmarse, `TEXTO_COMPRA_SIN_CONFIRMAR` (nunca «fallo» ni «repítela»). El gasto posterior (C-COMPRA-03) no cambia.
// Versión: 0.5.0 (F06 T3 · cadena de noche 21->22-11, T-D MANT N3 cliente; D-C7-07): los campos de importe ponen los puntos de miles al teclear (`formatearImporteAlTeclear`). D-C7-08 (OBS-02): el banco de la hipoteca se elige con un buscador de terceros (`bancosVisibles`): sin escribir no se lista ninguno; el elegido se ve siempre.
// Versión: 0.6.0 (F06 T6 · S1 piezas comunes; F09 0.55 §12.107.1 puntos 5 y 9): «Banco» de la hipoteca usa el mismo selector común de terceros que Registrar gasto (`CampoSelector` + `SelectorTercero` a pantalla completa, título «Banco»; sustituye al buscador con chips de D-C7-08 y a `bancosVisibles`); se envía el identificador del tercero elegido como `financiador.tercero_id`, igual que antes. Los campos de porcentaje, plazo y tipo abren el teclado decimal (`CampoTexto decimal`).
// Versión: 0.7.0 (F06 T6 · S3 compra; F09 0.55 §12.107.2 y lámina REG-AGIL v0.8 C1–C4): en «¿Cómo se pagó?», primero la hipoteca y después los pagos desde tus cuentas: cada pago se edita en su tarjeta («Confirmar pago» / «Cancelar») y queda en una línea con Editar y Eliminar; totales de presentación (Precio, Pagado desde tus cuentas, · de la hipoteca, · resto, sin hipoteca, Falta por cuadrar; DT-02, no se persisten); importe del préstamo con 80 % · 90 % · Otro % · Otro importe (DP-14, AJ-UX2-07: céntimos enteros con round_half_up; el importe se ve y se edita; el % no viaja) y ayuda «préstamo ≤ precio» (DT-03, solo pantalla). `faltasPagos`, «Lo deja en» y el payload no cambian.
// Versión: 0.8.0 (F06 T6 · S7-A N2; DP-09, DT-04): «Banco» de la hipoteca usa el selector común en modo `soloBancos`: lista solo los terceros marcados como banco o entidad financiera y «+ Crear banco» crea el tercero ya marcado (rol ENTIDAD_FINANCIERA con `anadirRoles`). El payload no cambia (`financiador.tercero_id`).
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaElegible, Tercero } from '../api/cliente';
import { configApi } from '../api/config';
import { type ClienteContratos, crearClienteContratos } from '../api/contratos';
import type { CuadroPrevio } from '../api/hipoteca';
import type { ClientePatrimonio, ParteEnFecha } from '../api/patrimonio';
import type { VistaPropiedad } from '../api/propiedades';
import { BotonPrimario, BotonSecundario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { CampoFecha } from '../components/CampoFecha';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { CampoSelector } from '../components/PantallaSelector';
import { SelectorTercero } from '../components/SelectorTercero';
import {
  avisoGastosAnteriores, BorradorCompra, textoPagado, borradorInicial, CONCEPTOS, EleccionAtribucion, faltasAtribucion, faltasGasto,
  faltasGastos, faltasPagos, faltasPrecio, filasDiaADia, GastoBorrador, NOMBRE_CONCEPTO, NOMBRE_ROL, PagoBorrador, payloadCompra,
  enviarCompraComprobando, payloadGastoCompra, puedeDeclararCompleto, resumen, ROLES, TEXTO_COMPRA_SIN_CONFIRMAR, TEXTO_COMPROBANDO_COMPRA, TEXTO_DESFASADA, TEXTO_GASTOS, TEXTO_INDETERMINADO_COMPRA, TEXTO_NADIE_MARCADO, TEXTO_NOTA_SIN_FECHA, TEXTO_SIN_HIPOTECA,
  TEXTO_SIN_TITULARIDAD, TEXTO_VALOR_REFERENCIA, textoErrorCompra, textoPartes, textoPropuestaEscritura,
  faltasDeUnPago, importePorcentaje, prestamoSuperaPrecio, totalesPagos,
} from '../domain/compra';
import { ddmmaaaaAIso, diaMesAnioIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import { formatearEur, formatearImporteAlTeclear, parsearImporte } from '../domain/importe';
import {
  BorradorHipoteca, borradorHipoteca, conHipoteca, eleccionPropuesta, faltasHipoteca, NOMBRE_TIPO, numeroCuotas, payloadCuadroPrevio, puedeVerCuadro,
  ROTULO_CUENTA_DESEMBOLSO, TEXTO_AVISO_REPARTO, TEXTO_CONVENCION, TEXTO_CUENTA_DESEMBOLSO, TEXTO_PRESTAMO, TEXTO_SIN_CUENTAS_CARGO, TEXTO_SIN_CUENTAS_DESEMBOLSO,
  TEXTO_SIN_TITULARIDAD_PRESTAMO, TEXTO_TITULARIDAD_PRESTAMO, textoErrorHipoteca, textoSeguro, TIPOS_INTERES,
} from '../domain/hipoteca';
import { esFechaIso } from '../domain/intencion';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { CuadroPrevioScreen, EleccionRepartoVista } from './HipotecaCuadroScreen';
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
        <CampoTexto key={a.actor_id} decimal testID={`${p.testID}-pct-${a.actor_id}`} etiqueta={`Porcentaje de ${a.nombre}`} marcador="%"
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
  /** F06 T6 · S7-A: cliente de roles de tercero para «+ Crear banco» (por defecto, el de `configApi`). */
  contratos?: ClienteContratos;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const [paso, setPaso] = useState<Paso>('PRECIO');
  const contratosApi = useRef(p.contratos ?? crearClienteContratos(configApi)).current;
  /** S7-A: marca el banco recién creado con el rol ENTIDAD_FINANCIERA (ruta de roles de siempre). */
  const marcarBanco = async (t: Tercero): Promise<boolean> => {
    const r = await contratosApi.anadirRoles(t.id, { intencion_id: p.nuevoId(), row_version_esperada: t.row_version, anadir: ['ENTIDAD_FINANCIERA'] });
    return r.tipo === 'OK';
  };
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
  // UX-4: el servidor dijo que falta la fecha de adquisición (R15-a): B4 deja de ofrecer el chip.
  const [sinFechaServidor, setSinFechaServidor] = useState(false);
  const ofreceCompleto = puedeDeclararCompleto(sinFechaServidor ? null : p.vista.fecha_adquisicion);
  const intencion = useRef(p.nuevoId());
  // F06-01H: hipoteca de la compra (null = sin hipoteca: la compra no cambia).
  const [hip, setHip] = useState<BorradorHipoteca | null>(null);
  const [propuestaHip, setPropuestaHip] = useState<ParteEnFecha[] | null>(null);
  const [previo, setPrevio] = useState<CuadroPrevio | null>(null);
  const [selectorBanco, setSelectorBanco] = useState(false);
  const [bancoNombre, setBancoNombre] = useState<string | null>(null);
  const [avisoReparto, setAvisoReparto] = useState(false);
  // F06 T6 · S3 (F09 0.55 §12.107.2): un pago se edita en su tarjeta y, al confirmarlo, queda en una línea con Editar y Eliminar.
  // `copiaPago` permite «Cancelar»: vuelve a lo confirmado o, si el pago es nuevo, lo quita. Solo presentación.
  const [pagoAbierto, setPagoAbierto] = useState<string | null>(() => b.pagos[0]?.id ?? null);
  const [copiaPago, setCopiaPago] = useState<PagoBorrador | null>(null);

  useEffect(() => {
    void p.cliente.cuentasElegibles('GASTO', hoyIso).then((r) => { if (r.tipo === 'OK') setCuentas(r.datos.cuentas); });
  }, []);
  // Titularidad del préstamo propuesta: la de la propiedad en la escritura (D13), solo con hipoteca.
  const conHip = hip !== null;
  useEffect(() => {
    if (!conHip || !esFechaIso(b.fechaEscritura)) return;
    setPropuestaHip(null);
    void p.patrimonio.titularidadEnFecha(p.vista.id, b.fechaEscritura).then((r) => {
      const partes = r.tipo === 'OK' ? r.datos.partes : [];
      setPropuestaHip(partes);
      setHip((h) => (h && h.titularidad?.modo !== 'MANUAL' ? { ...h, titularidad: eleccionPropuesta(partes) } : h));
    });
  }, [conHip, b.fechaEscritura]);
  const cargarPropuesta = async () => {
    setPropuesta(null);
    const r = await p.patrimonio.titularidadEnFecha(p.vista.id, b.fechaEscritura);
    setPropuesta(r.tipo === 'OK' ? r.datos.partes : []);
  };
  useEffect(() => {
    if (paso === 'ATRIBUCION') void cargarPropuesta();
  }, [paso]);

  const faltas = paso === 'PRECIO' ? faltasPrecio(b) : paso === 'PAGOS' ? [...faltasPagos(b), ...(hip ? faltasHipoteca(hip, b.fechaEscritura, propuestaHip) : []),
      ...(hip && prestamoSuperaPrecio(b.precio, hip.importe) ? [TEXTO_FALTA_PRESTAMO_PRECIO] : [])] : paso === 'GASTOS' ? faltasGastos(b)
    : paso === 'ATRIBUCION' ? faltasAtribucion(b.atribucion, propuesta) : [];
  const nombreCuenta = (id: string | null) => cuentas.find((x) => x.cuenta_id === id)?.nombre ?? 'Cuenta';
  const r = resumen(b);
  const indice = PASOS.indexOf(paso);
  const atras = () => (indice > 0 ? setPaso(PASOS[indice - 1]) : p.onCerrar(null));
  const setPago = (i: number, x: Partial<PagoBorrador>) => setB({ ...b, pagos: b.pagos.map((y, j) => (j === i ? { ...y, ...x } : y)) });
  const abrirPago = (x: PagoBorrador) => {
    if (pagoAbierto && pagoAbierto !== x.id) return;
    setCopiaPago({ ...x });
    setPagoAbierto(x.id);
  };
  const confirmarPago = (x: PagoBorrador) => {
    if (faltasDeUnPago(b, x).length > 0) return;
    setPagoAbierto(null);
    setCopiaPago(null);
  };
  const cancelarPago = (x: PagoBorrador) => {
    const antes = copiaPago;
    setB({ ...b, pagos: antes ? b.pagos.map((y) => (y.id === x.id ? antes : y)) : b.pagos.filter((y) => y.id !== x.id) });
    setPagoAbierto(null);
    setCopiaPago(null);
  };
  const anadirPago = () => {
    if (pagoAbierto) return;
    const id = p.nuevoId();
    setB({ ...b, pagos: [...b.pagos, { id, rol: 'ARRAS', cuentaId: null, fecha: b.fechaEscritura, importe: '' }] });
    setCopiaPago(null);
    setPagoAbierto(id);
  };
  const totales = totalesPagos(b, hip ? hip.importe : null);
  const setGasto = (i: number, x: Partial<GastoBorrador>) => setB({ ...b, gastos: b.gastos.map((y, j) => (j === i ? { ...y, ...x } : y)) });

  const guardar = async () => {
    if (ocupado) return;
    setOcupado(true);
    setAviso(null);
    // R-B2-06 (AJ-01): el cuerpo se construye UNA vez; ante un INDETERMINADO (timeout) se reenvía el MISMO (replay idempotente).
    const cuerpo = conHipoteca(payloadCompra(intencion.current, p.vista.row_version, { ...b, completo: ofreceCompleto && b.completo }, propuesta), hip, propuestaHip);
    const { respuesta: res } = await enviarCompraComprobando(() => p.patrimonio.registrarCompra(p.vista.id, cuerpo),
      () => setAviso({ tipo: 'AVISO', texto: TEXTO_COMPROBANDO_COMPRA }));
    setOcupado(false);
    if (res.tipo === 'OK') {
      setResultado(res.datos.propiedad);
      setAvisoReparto(res.datos.aviso_reparto_distinto === true);
      return setPaso('HECHO');
    }
    if (res.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_COMPRA_SIN_CONFIRMAR });
    if (res.codigo === 'VERSION_DESFASADA') return setConflicto(true);
    if (res.codigo === 'ATRIBUCION_PROPUESTA_DESFASADA') {
      // Intención nueva: la petición rechazada no escribió nada; el contenido cambia al elegir otra vez.
      intencion.current = p.nuevoId();
      setB({ ...b, atribucion: null });
      setAvisoAtr(TEXTO_DESFASADA);
      return setPaso('ATRIBUCION');
    }
    if (res.codigo === 'COMPLETITUD_SIN_FECHA_DE_ADQUISICION') {
      // UX-4: no se guardó nada; B4 sin el chip y con intención nueva para guardar sin declaración.
      intencion.current = p.nuevoId();
      setB({ ...b, completo: false });
      setSinFechaServidor(true);
    }
    if (hip) return setAviso({ tipo: 'AVISO', texto: textoErrorHipoteca(res.codigo, res.detalle) ?? textoSeguro(textoErrorCompra(res.codigo, res.mensaje)) });
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
          {avisoReparto ? <Text testID="compra-hip-aviso-reparto" style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_AVISO_REPARTO}</Text> : null}
          <BotonPrimario testID="compra-listo" titulo="Listo" onPress={() => p.onCerrar(resultado)} />
        </ScrollView>
      </View>
    );
  }

  if (previo) return <CuadroPrevioScreen cuadro={previo} onCerrar={() => setPrevio(null)} />;

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
              <CampoTexto importe testID="compra-precio" etiqueta="Precio de compra" marcador="Ej.: 200.000,00" valor={b.precio} onCambiar={(t) => setB({ ...b, precio: t })} />
            </Campo>
            <Campo etiqueta="Fecha de la escritura">
              <Fecha testID="compra-escritura" etiqueta="Fecha de la escritura, día barra mes barra año" iso={b.fechaEscritura} hoyIso={hoyIso}
                onCambiar={(iso) => setB({ ...b, fechaEscritura: iso, pagos: b.pagos.map((x) => (x.rol === 'FIRMA' ? { ...x, fecha: iso } : x)) })} />
            </Campo>
            <Campo etiqueta="Valor de referencia del Catastro" opcional>
              <CampoTexto importe testID="compra-referencia" etiqueta="Valor de referencia" marcador="Ej.: 210.000,00" valor={b.valorReferencia} onCambiar={(t) => setB({ ...b, valorReferencia: t })} />
            </Campo>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_VALOR_REFERENCIA}</Text>
          </>
        ) : null}
        {paso === 'PAGOS' ? (
          <>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>2 de 3 · ¿Cómo se pagó el precio?</Text>
            {/* F06 T6 · S3 (lámina C1–C4): primero la hipoteca; después los pagos desde tus cuentas, cada uno en su línea. */}
            {hip ? (
              <BloqueHipoteca cliente={p.cliente} hip={hip} escrituraIso={b.fechaEscritura} hoyIso={hoyIso} propuesta={propuestaHip}
                onCambiar={(x) => setHip({ ...hip, ...x })} onQuitar={() => setHip(null)} onAviso={setAviso} onCuadro={setPrevio} precio={b.precio}
                bancoNombre={bancoNombre} onElegirBanco={() => setSelectorBanco(true)} />
            ) : (
              <>
                <Text testID="compra-sin-hipoteca" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_HIPOTECA}</Text>
                <BotonTexto testID="compra-hip-anadir" titulo="+ Añadir la hipoteca de esta compra" onPress={() => setHip(borradorHipoteca())} />
              </>
            )}
            <RotuloGrupo texto="Pagos desde tus cuentas" />
            {b.pagos.length === 0 ? <Text testID="compra-sin-pagos" style={[tipo.footnote, { color: c.textSecondary }]}>Sin pagos todavía</Text> : null}
            {b.pagos.map((x, i) => (pagoAbierto === x.id ? (
              <Tarjeta key={x.id} testID={`compra-pago-${i}`}>
                <View style={{ padding: espacio.m, gap: espacio.s }}>
                  <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{copiaPago ? 'Editar pago' : 'Nuevo pago'}</Text>
                  <View style={ef.chips}>
                    {ROLES.map((rol) => <Chip key={rol} testID={`compra-pago-${i}-rol-${rol}`} etiqueta={NOMBRE_ROL[rol]} seleccionado={x.rol === rol} onPress={() => setPago(i, { rol, ...(rol === 'FIRMA' ? { fecha: b.fechaEscritura } : {}) })} />)}
                  </View>
                  <Cuentas testID={`compra-pago-${i}-cuenta`} cuentas={cuentas} valor={x.cuentaId} onCambiar={(id) => setPago(i, { cuentaId: id })} />
                  <Fecha testID={`compra-pago-${i}-fecha`} etiqueta="Fecha del pago" iso={x.fecha} hoyIso={hoyIso} onCambiar={(iso) => setPago(i, { fecha: iso })} />
                  <CampoTexto importe testID={`compra-pago-${i}-importe`} etiqueta="Importe del pago" marcador="0,00" valor={x.importe} onCambiar={(t) => setPago(i, { importe: t })} />
                  {hip && hip.cuentaDesembolsoId && x.cuentaId === hip.cuentaDesembolsoId && parsearImporte(hip.importe).ok && parsearImporte(x.importe).ok ? (
                    <Text testID={`compra-pago-${i}-hip`} style={[tipo.footnote, { color: c.textSecondary }]}>
                      {textoDeLaHipoteca(x.importe, hip.importe, nombreCuenta(x.cuentaId))}
                    </Text>
                  ) : null}
                  <BotonPrimario testID={`compra-pago-${i}-confirmar`} titulo="Confirmar pago" deshabilitado={faltasDeUnPago(b, x).length > 0}
                    ayuda={faltasDeUnPago(b, x).length > 0 ? `Falta: ${faltasDeUnPago(b, x).join(', ')}.` : undefined} onPress={() => confirmarPago(x)} />
                  <BotonSecundario testID={`compra-pago-${i}-cancelar`} titulo="Cancelar" onPress={() => cancelarPago(x)} />
                </View>
              </Tarjeta>
            ) : (
              <View key={x.id} testID={`compra-pago-${i}-linea`} style={[s.lineaPago, { borderBottomColor: c.borderDefault }]}>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text testID={`compra-pago-${i}-linea-titulo`} style={[tipo.body, { color: c.textPrimary }]}>{`${NOMBRE_ROL[x.rol]} · ${formatearEur(parsearImporte(x.importe).ok ? (parsearImporte(x.importe) as { valor: string }).valor : '0')}`}</Text>
                  <Text style={[tipo.caption, { color: c.textSecondary }]}>{`${nombreCuenta(x.cuentaId)} · ${esFechaIso(x.fecha) ? isoADdmmaaaa(x.fecha) : x.fecha}`}</Text>
                </View>
                <BotonTexto testID={`compra-pago-${i}-editar`} titulo="Editar" onPress={() => abrirPago(x)} />
                <BotonTexto testID={`compra-pago-${i}-eliminar`} titulo="Eliminar" critico onPress={() => setB({ ...b, pagos: b.pagos.filter((_, j) => j !== i) })} />
              </View>
            )))}
            {pagoAbierto ? null : <BotonTexto testID="compra-pago-anadir" titulo="+ Añadir pago" onPress={anadirPago} />}
            <Tarjeta testID="compra-totales">
              <Linea testID="compra-tot-precio" etiqueta="Precio" valor={formatearEur(totales.precio)} />
              <Linea testID="compra-pagado" etiqueta="Pagado desde tus cuentas" valor={formatearEur(totales.pagado)} fuerte />
              {totales.hipoteca !== null ? <Linea testID="compra-tot-hipoteca" etiqueta="· de la hipoteca" valor={formatearEur(totales.hipoteca)} /> : null}
              {totales.resto !== null ? <Linea testID="compra-tot-resto" etiqueta="· resto, sin hipoteca" valor={formatearEur(totales.resto)} /> : null}
              <Linea testID="compra-tot-falta" etiqueta="Falta por cuadrar" valor={`${formatearEur(totales.falta)}${totales.falta === '0.00' ? ' ✓' : ''}`} />
            </Tarjeta>
            {hip ? <Text testID="compra-tot-nota" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_TOTALES_HIPOTECA}</Text> : null}
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
              <Linea testID="compra-res-estado" etiqueta="Estado" valor={ofreceCompleto && b.completo ? 'Completo' : 'Parcial · puedes añadir gastos'} />
              <Linea testID="compra-res-sale" etiqueta="Sale de tus cuentas" valor={formatearEur(r.sale.replace('-', ''))} />
              <Linea testID="compra-res-gasto-mes" etiqueta="Cuenta como gasto del mes" valor={formatearEur(r.gastoMes)} />
            </Tarjeta>
            {hip ? (
              <>
                <RotuloGrupo texto="Hipoteca" />
                <Tarjeta testID="compra-res-hipoteca">
                  <Linea testID="compra-res-hip-prestamo" etiqueta="Préstamo del banco" valor={formatearEur(parsearImporte(hip.importe).ok ? (parsearImporte(hip.importe) as { valor: string }).valor : '0')} />
                  <Linea testID="compra-res-hip-cuenta" etiqueta="Lo deja en" valor={nombreCuenta(hip.cuentaDesembolsoId)} />
                  <Linea testID="compra-res-hip-cuotas" etiqueta="Cuotas" valor={`${numeroCuotas(hip.plazo, hip.unidadPlazo) ?? '—'} mensuales desde el ${esFechaIso(hip.primeraCuota) ? diaMesAnioIso(hip.primeraCuota) : '—'}`} />
                </Tarjeta>
                <Text testID="compra-res-hip-nota" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_PRESTAMO}</Text>
              </>
            ) : null}
            {ofreceCompleto ? (
              <Chip testID="compra-completo" etiqueta="No faltan gastos: el coste de la compra está completo" seleccionado={b.completo} onPress={() => setB({ ...b, completo: !b.completo })} />
            ) : (
              <Text testID="compra-nota-sin-fecha" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NOTA_SIN_FECHA}</Text>
            )}
            <Text testID="compra-registros" style={[tipo.footnote, { color: c.textSecondary }]}>
              {`Se crean ${r.registros} ${r.registros === 1 ? 'registro' : 'registros'} con ${r.pagos} ${r.pagos === 1 ? 'pago' : 'pagos'}. Se guarda todo junto o nada.`}
            </Text>
          </>
        ) : null}
        {faltas.length > 0 ? <Text testID="compra-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        {paso === 'RESUMEN' ? (
          <BotonPrimario testID="compra-guardar" titulo="Guardar la compra" cargando={ocupado} onPress={() => void guardar()} />
        ) : (
          <BotonPrimario testID="compra-continuar" titulo="Continuar" deshabilitado={faltas.length > 0}
            onPress={() => { if (paso === 'PAGOS') { setPagoAbierto(null); setCopiaPago(null); } setPaso(PASOS[indice + 1]); }} />
        )}
        {indice > 0 ? <BotonTexto testID="compra-atras" titulo="‹ Atrás" onPress={atras} /> : null}
      </ScrollView>
      {selectorBanco && hip ? (
        <SelectorTercero
          cliente={p.cliente}
          nuevoId={p.nuevoId}
          titulo="Banco"
          soloBancos={{ marcar: marcarBanco }}
          seleccionadoId={hip.financiadorId}
          onElegir={(t) => {
            setSelectorBanco(false);
            setBancoNombre(t ? t.nombre : null);
            setHip({ ...hip, financiadorId: t ? t.id : null });
          }}
          onCerrar={() => setSelectorBanco(false)}
        />
      ) : null}
    </View>
  );
}

function EditorGasto(p: { prefijo: string; g: GastoBorrador; cuentas: CuentaElegible[]; hoyIso: string; onCambiar: (x: Partial<GastoBorrador>) => void; onQuitar?: () => void }) {
  return (
    <View style={{ padding: espacio.m, gap: espacio.s }}>
      <View style={ef.chips}>
        {CONCEPTOS.map((k) => <Chip key={k} testID={`${p.prefijo}-concepto-${k}`} etiqueta={NOMBRE_CONCEPTO[k]} seleccionado={p.g.concepto === k} onPress={() => p.onCambiar({ concepto: k })} />)}
      </View>
      <CampoTexto importe testID={`${p.prefijo}-importe`} etiqueta="Importe del gasto" marcador="0,00" valor={p.g.importe} onCambiar={(t) => p.onCambiar({ importe: t })} />
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

/** Chips de cuentas del bloque «Hipoteca» con su propio texto de lista vacía. */
function CuentasHip(p: { testID: string; cuentas: CuentaElegible[] | null; valor: string | null; vacio: string; onCambiar: (id: string) => void }) {
  if (p.cuentas === null) return <EstadoDato testID={`${p.testID}-cargando`} estado="CARGANDO" />;
  if (p.cuentas.length === 0) return <EstadoDato testID={`${p.testID}-sin`} estado="NO_DISPONIBLE" detalle={p.vacio} />;
  return (
    <View style={ef.chips}>
      {p.cuentas.map((c) => (
        <Chip key={c.cuenta_id} testID={`${p.testID}-${c.cuenta_id}`} etiqueta={c.nombre} seleccionado={p.valor === c.cuenta_id} onPress={() => p.onCambiar(c.cuenta_id)} />
      ))}
    </View>
  );
}

/** F06 T6 · S3: textos de presentación de «¿Cómo se pagó?» (DT-02, DT-03). */
export const TEXTO_FALTA_PRESTAMO_PRECIO = 'un préstamo que no supere el precio';
export const TEXTO_PRESTAMO_SUPERA = 'El préstamo es mayor que el precio de compra. Es una ayuda de pantalla: revísalo antes de seguir.';
export const TEXTO_TOTALES_HIPOTECA = 'El préstamo entra en tu cuenta y sale en la firma, como siempre. Solo cambia cómo se ve: cuánto de lo pagado cubre la hipoteca y cuánto queda sin ella.';
/** «De este pago, 160.000,00 € vienen de la hipoteca que entró en Cuenta…» (lámina C2; como mucho, el préstamo). */
export function textoDeLaHipoteca(pago: string, prestamo: string, cuenta: string): string {
  const a = parsearImporte(pago);
  const h = parsearImporte(prestamo);
  if (!a.ok || !h.ok) return '';
  const menor = Number(a.valor) <= Number(h.valor) ? a.valor : h.valor;
  return `De este pago, ${formatearEur(menor)} vienen de la hipoteca que entró en ${cuenta}.`;
}
/** Importe canónico («160000.00») al texto del campo («160.000,00»). */
const aTextoCampo = (canonico: string) => formatearImporteAlTeclear(canonico.replace('.', ','));

/** F06-01H · bloque «Hipoteca» de la compra (contrato v0.4 §3.2.1 y §8). El cliente no calcula importes: «Ver el cuadro» lo pide al servidor (W-HIP-00). */
function BloqueHipoteca(p: {
  cliente: ClienteApi;
  hip: BorradorHipoteca;
  escrituraIso: string;
  hoyIso: string;
  propuesta: ParteEnFecha[] | null;
  onCambiar: (x: Partial<BorradorHipoteca>) => void;
  onQuitar: () => void;
  onAviso: (a: AvisoCaja) => void;
  onCuadro: (c: CuadroPrevio) => void;
  /** F06 T6 · S1: nombre del banco elegido y apertura del selector común de terceros (lo pinta la pantalla, a pantalla completa). */
  bancoNombre: string | null;
  onElegirBanco: () => void;
  /** F06 T6 · S3: precio de compra para el importe por porcentaje y la ayuda «préstamo ≤ precio». */
  precio: string;
}) {
  const { c } = useTema();
  const h = p.hip;
  // Solo presentación: el porcentaje sirve para calcular el importe y no se guarda ni viaja (AJ-UX2-07).
  const [modoImporte, setModoImporte] = useState<'80' | '90' | 'OTRO_PCT' | 'OTRO_IMPORTE' | null>(null);
  const [pctTexto, setPctTexto] = useState('');
  const aplicarPct = (pct: string) => {
    const imp = importePorcentaje(p.precio, pct);
    if (imp) p.onCambiar({ importe: aTextoCampo(imp) });
  };
  const prestamoOk = parsearImporte(h.importe);
  const precioOk = parsearImporte(p.precio);
  const [cuentasDesembolso, setCuentasDesembolso] = useState<CuentaElegible[] | null>(null);
  const [cuentasCargo, setCuentasCargo] = useState<CuentaElegible[] | null>(null);
  const [pidiendo, setPidiendo] = useState(false);
  const fechaCargo = esFechaIso(h.primeraCuota) ? h.primeraCuota : p.escrituraIso;
  useEffect(() => {
    // La cuenta en la que el banco deja el préstamo tiene que poder recibir dinero en la fecha de la escritura.
    setCuentasDesembolso(null);
    void p.cliente.cuentasElegibles('INGRESO', p.escrituraIso).then((r) => setCuentasDesembolso(r.tipo === 'OK' ? r.datos.cuentas : []));
  }, [p.escrituraIso]);
  useEffect(() => {
    setCuentasCargo(null);
    void p.cliente.cuentasElegibles('GASTO', fechaCargo).then((r) => setCuentasCargo(r.tipo === 'OK' ? r.datos.cuentas : []));
  }, [fechaCargo]);
  const n = numeroCuotas(h.plazo, h.unidadPlazo);

  const verCuadro = async () => {
    if (pidiendo || !p.cliente.cuadroHipoteca) return;
    if (!puedeVerCuadro(h)) return p.onAviso({ tipo: 'AVISO', texto: 'Para ver el cuadro indica el importe del préstamo, el tipo anual y el plazo.' });
    setPidiendo(true);
    p.onAviso(null);
    const r = await p.cliente.cuadroHipoteca(payloadCuadroPrevio(h));
    setPidiendo(false);
    if (r.tipo === 'OK') return p.onCuadro(r.datos);
    p.onAviso({ tipo: 'AVISO', texto: r.tipo === 'RECHAZADO' ? textoErrorHipoteca(r.codigo, r.detalle) ?? textoSeguro(r.mensaje) : 'No se ha podido calcular el cuadro. Vuelve a intentarlo.' });
  };

  return (
    <View testID="compra-hip" style={{ gap: espacio.m }}>
      <RotuloGrupo texto="Hipoteca" />
      <Campo etiqueta="Banco">
        {/* F06 T6 · S1 (F09 0.55 §12.107.1 punto 5): el mismo selector de terceros que Registrar gasto; se envía su identificador */}
        <CampoSelector testID="compra-hip-banco" etiqueta="Banco" valor={h.financiadorId ? p.bancoNombre : null} marcador="Elige el banco" onAbrir={p.onElegirBanco} />
      </Campo>
      <Campo etiqueta="Importe del préstamo">
        {/* F06 T6 · S3 (DP-14): 80 % · 90 % · Otro % · Otro importe; el importe se ve y se puede corregir antes de seguir. */}
        <View style={ef.chips}>
          {(['80', '90'] as const).map((x) => (
            <Chip key={x} testID={`compra-hip-pct-${x}`} etiqueta={`${x} %`} seleccionado={modoImporte === x} onPress={() => { setModoImporte(x); aplicarPct(x); }} />
          ))}
          <Chip testID="compra-hip-pct-otro" etiqueta="Otro %" seleccionado={modoImporte === 'OTRO_PCT'} onPress={() => setModoImporte('OTRO_PCT')} />
          <Chip testID="compra-hip-otro-importe" etiqueta="Otro importe" seleccionado={modoImporte === 'OTRO_IMPORTE'} onPress={() => setModoImporte('OTRO_IMPORTE')} />
        </View>
        {modoImporte === 'OTRO_PCT' ? (
          <CampoTexto decimal testID="compra-hip-pct" etiqueta="Porcentaje del precio" marcador="Ej.: 75,5" valor={pctTexto}
            onCambiar={(t) => { setPctTexto(t); aplicarPct(t); }} />
        ) : null}
        <CampoTexto importe testID="compra-hip-importe" etiqueta="Importe del préstamo" marcador="Ej.: 160.000,00" valor={h.importe}
          onCambiar={(t) => { if (modoImporte !== 'OTRO_IMPORTE') setModoImporte('OTRO_IMPORTE'); p.onCambiar({ importe: t }); }} />
        {prestamoOk.ok && precioOk.ok ? (
          <Text testID="compra-hip-importe-texto" style={[tipo.footnote, { color: c.textSecondary }]}>
            {`Préstamo ${formatearEur(prestamoOk.valor)} · precio ${formatearEur(precioOk.valor)}. Se guarda el importe; el porcentaje solo sirve para calcularlo.`}
          </Text>
        ) : null}
        {prestamoSuperaPrecio(p.precio, h.importe) ? (
          <Text testID="compra-hip-supera" accessibilityRole="alert" style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_PRESTAMO_SUPERA}</Text>
        ) : null}
      </Campo>
      <Campo etiqueta={ROTULO_CUENTA_DESEMBOLSO}>
        <CuentasHip testID="compra-hip-desembolso" cuentas={cuentasDesembolso} valor={h.cuentaDesembolsoId} vacio={TEXTO_SIN_CUENTAS_DESEMBOLSO}
          onCambiar={(id) => p.onCambiar({ cuentaDesembolsoId: id })} />
      </Campo>
      <Text testID="compra-hip-desembolso-texto" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CUENTA_DESEMBOLSO}</Text>
      <Campo etiqueta="Tipo de interés">
        <View style={ef.chips}>
          {TIPOS_INTERES.map((t) => <Chip key={t} testID={`compra-hip-tipo-${t}`} etiqueta={NOMBRE_TIPO[t]} seleccionado={h.tipoInteres === t} onPress={() => p.onCambiar({ tipoInteres: t })} />)}
        </View>
      </Campo>
      <Campo etiqueta="Tipo anual (%)">
        <CampoTexto decimal testID="compra-hip-tasa" etiqueta="Tipo anual (%)" marcador="Ej.: 2,5" valor={h.tasa} onCambiar={(t) => p.onCambiar({ tasa: t })} />
      </Campo>
      <Campo etiqueta="Plazo">
        <CampoTexto decimal testID="compra-hip-plazo" etiqueta="Plazo" marcador={h.unidadPlazo === 'ANIOS' ? 'Años' : 'Meses'} valor={h.plazo} onCambiar={(t) => p.onCambiar({ plazo: t })} />
        <View style={ef.chips}>
          <Chip testID="compra-hip-plazo-anios" etiqueta="En años" seleccionado={h.unidadPlazo === 'ANIOS'} onPress={() => p.onCambiar({ unidadPlazo: 'ANIOS' })} />
          <Chip testID="compra-hip-plazo-meses" etiqueta="En meses" seleccionado={h.unidadPlazo === 'MESES'} onPress={() => p.onCambiar({ unidadPlazo: 'MESES' })} />
        </View>
      </Campo>
      {n !== null ? <Text testID="compra-hip-n-cuotas" style={[tipo.footnote, { color: c.textSecondary }]}>{`${n} ${n === 1 ? 'cuota mensual' : 'cuotas mensuales'}`}</Text> : null}
      <Campo etiqueta="Primera cuota">
        <Fecha testID="compra-hip-primera" etiqueta="Primera cuota, día barra mes barra año" iso={h.primeraCuota} hoyIso={p.hoyIso} onCambiar={(iso) => p.onCambiar({ primeraCuota: iso })} />
      </Campo>
      <Campo etiqueta="Cuenta de cargo de las cuotas">
        <CuentasHip testID="compra-hip-cargo" cuentas={cuentasCargo} valor={h.cuentaCargoId} vacio={TEXTO_SIN_CUENTAS_CARGO} onCambiar={(id) => p.onCambiar({ cuentaCargoId: id })} />
      </Campo>
      <Campo etiqueta="¿De quién es el préstamo?">
        <EleccionRepartoVista testID="compra-hip-titularidad" propuesta={p.propuesta} eleccion={h.titularidad} onCambiar={(e) => p.onCambiar({ titularidad: e })}
          textoPropuesta="Según la titularidad en la escritura" textoSinPropuesta={TEXTO_SIN_TITULARIDAD_PRESTAMO} />
      </Campo>
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_TITULARIDAD_PRESTAMO}</Text>
      <Text testID="compra-hip-convencion" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CONVENCION}</Text>
      {p.cliente.cuadroHipoteca ? (
        <BotonTexto testID="compra-hip-ver-cuadro" titulo={pidiendo ? 'Calculando el cuadro…' : 'Ver el cuadro'} onPress={() => void verCuadro()} />
      ) : null}
      <BotonTexto testID="compra-hip-quitar" titulo="Quitar la hipoteca" critico onPress={p.onQuitar} />
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
  lineaPago: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: espacio.s },
});
