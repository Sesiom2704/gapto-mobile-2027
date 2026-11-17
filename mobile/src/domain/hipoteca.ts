// ============================================================
// GAPTO MOBILE 2027
// Fichero: hipoteca.ts
// Ruta: mobile/src/domain/hipoteca.ts
// Descripción: Lógica pura de la hipoteca de la compra en el cliente (F06-01H; contrato v0.4 §3.2.1, §3.2.7-5, §3.3, §3.4, §3.5 y §8; mandato T3-F06 bloque 2 v1.1 §15). Bloque «Hipoteca» de la compra: borrador, validaciones (tipo anual 0–30 % con hasta 4 decimales, plazo en años o meses → 1–600 cuotas, primera cuota posterior a la escritura, cuentas, banco y titularidad del préstamo propuesta y modificable) y bloque `hipoteca` de la petición (nunca con campos de modalidad no representable). Cuadro: filas visibles. Pago de una cuota: desglose que presenta lo que da el servidor y SOLO comprueba capital + intereses = cuota, reparto de los intereses (propuesta visible y modificable) y payload de W-HIP-02. Revisión del tipo: cuotas afectadas, texto «Se recalculan N cuotas desde …; las M pagadas no cambian» (nunca «bonificación») y payload de W-HIP-03/04. Textos de error propios, sin «ingreso» ni «cobro» (R-1). El cliente NO calcula importes. Exposición del pago de una cuota: constante de código `PAGO_CUOTA_EXPUESTO` (firma de Moisés del 2026-11-17, e446b4c3…), nunca entorno ni configuración.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 10)
// Versión: 0.2.0 (F06 T3-F06 bloque 2 F06-01H; N-31, firma 0f3e5633…): constante de código propia `REVISION_TIPO_EXPUESTA = true` y `ofreceRevisionTipo` (revisión solo expuesta, ACTIVA y con deuda conocida).
// Versión: 0.3.0 (F06 T3-F06 bloque 2 F06-01H; N-30, firma 0f3e5633…, enmienda 52ef5511…): `titularidadPrestamoEnFecha`: la propuesta del reparto de los intereses sale de la titularidad DEL PRÉSTAMO de L-HIP vigente en el vencimiento (Q-T3D-08), no de la de la propiedad.
// ============================================================

import type {
  BloqueHipotecaWire, CondicionesHipoteca, CuotaHipoteca, FilaCuadroPrevio, Hipoteca, PayloadCuadroPrevio, PayloadPagoCuota, PayloadRevisionTipo,
  TipoInteresHipoteca,
} from '../api/hipoteca';
import type { ParteAtribucion, ParteEnFecha, PayloadCompra } from '../api/patrimonio';
import { diaMesAnioIso } from './fechas';
import { formatearEur, parsearImporte } from './importe';
import { esFechaIso } from './intencion';

/**
 * Exposición del pago de una cuota en la app (firma de Moisés del 2026-11-17, `F06-00_Decisiones_Moises_2026-11-17_exposicion_pago_cuota_v1.0.md`,
 * e446b4c3…): «expuesto» solo si al terminar el bloque se cumplen #96 (D17), bloque 1 verde, Q3 verde, botón y no swipe. Con el STOP de Q3 abierto
 * queda NO EXPUESTO. Constante de código: solo cambia con un commit revisado; nunca por entorno ni configuración.
 */
export const PAGO_CUOTA_EXPUESTO = false;

/**
 * Exposición de la revisión del tipo en la app (N-31; firma de Moisés del 2026-11-17, 0f3e5633…): constante propia, mismo mecanismo que el pago.
 * Vale true; si al final del bloque falla cualquiera de sus tests, mutantes o la concurrencia, vuelve a false sin nueva firma.
 * Constante de código: solo cambia con un commit revisado; nunca por entorno ni configuración.
 */
export const REVISION_TIPO_EXPUESTA = true;

/** La revisión del tipo se ofrece solo expuesta, en una hipoteca ACTIVA con deuda conocida. */
export const ofreceRevisionTipo = (h: Hipoteca, expuesta: boolean): boolean =>
  expuesta && h.estado === 'ACTIVA' && !h.deuda_indeterminada;

export const MAX_CUOTAS = 600;
export const TASA_MAXIMA = 30;

export const ROTULO_CUENTA_DESEMBOLSO = 'Cuenta en la que el banco deja el préstamo';
export const TEXTO_CUENTA_DESEMBOLSO = 'El banco deja el préstamo en esta cuenta; desde ella pagas la compra.';
export const TEXTO_SIN_CUENTAS_DESEMBOLSO = 'Ninguna cuenta puede recibir dinero en la fecha de la escritura.';
export const TEXTO_SIN_CUENTAS_CARGO = 'Ninguna cuenta puede pagar en la fecha de la primera cuota.';
export const TEXTO_CONVENCION = 'Cálculo mensual: tipo anual entre 12.';
export const TEXTO_PRESTAMO = 'El préstamo no es gasto ni coste de la compra: es la deuda con el banco. Las cuotas se pagan después, una a una.';
export const TEXTO_TITULARIDAD_PRESTAMO = 'Se propone la titularidad de la propiedad en la escritura. Puedes cambiarla.';
export const TEXTO_SIN_TITULARIDAD_PRESTAMO = 'No hay titularidad registrada en la fecha de la escritura: indica cuánto del préstamo es de cada uno.';
/** O-H30 (contrato §3.2.7-5): texto propuesto del aviso cuando las dos distribuciones difieren. */
export const TEXTO_AVISO_REPARTO =
  'El préstamo y la cuenta en la que entra no se reparten igual entre vosotros. Gapto lo registra así; no corrige lo que os debéis entre personas.';
export const ETIQUETA_CAPITAL = 'Capital · reduce lo que debes';
export const ETIQUETA_INTERESES = 'Intereses · gasto del mes';
export const ETIQUETA_SALIDA = 'Sale de tu cuenta';
export const TEXTO_NO_CUADRA = 'El desglose no cuadra con la cuota. Vuelve a cargar la hipoteca.';
export const TEXTO_RECARGADA = 'La hipoteca había cambiado y se ha vuelto a cargar. Revisa los datos antes de repetir.';
export const TEXTO_REPARTO_INTERESES = 'Los intereses se reparten según la titularidad del préstamo en el vencimiento. Puedes cambiarlo.';
export const TEXTO_SIN_TITULARIDAD_CUOTA = 'No hay titularidad del préstamo en el vencimiento: no se puede proponer el reparto.';
export const TEXTO_REVISION = 'Las cuotas ya pagadas no cambian. Se recalculan, con el mismo plazo, las que vencen desde esa fecha.';
export const TEXTO_INDETERMINADO = 'No se ha podido confirmar. Vuelve a cargar la hipoteca antes de repetir.';
export const TEXTO_GENERICO = 'No se ha podido guardar. Revisa los datos.';

export const NOMBRE_TIPO: Record<TipoInteresHipoteca, string> = { FIJO: 'Fijo', VARIABLE: 'Variable' };
export const TIPOS_INTERES: TipoInteresHipoteca[] = ['FIJO', 'VARIABLE'];
export const nombreTipoInteres = (t: string | null | undefined): string | null => (t === 'FIJO' || t === 'VARIABLE' ? NOMBRE_TIPO[t] : null);
export const ETIQUETA_ESTADO: Record<string, string> = {
  PENDIENTE: 'Pendiente', VENCIDA: 'Vencida', PAGADA: 'Pagada', SIN_PREVISION: 'Sin previsión', OMITIDA: 'Omitida', CANCELADA: 'Cancelada',
};

export type UnidadPlazo = 'ANIOS' | 'MESES';
/** Reparto propuesto y modificable (titularidad del préstamo en el alta; reparto de los intereses en el pago). */
export type EleccionReparto = null | { modo: 'TITULARIDAD' } | { modo: 'MANUAL'; partes: Record<string, string> };

export interface BorradorHipoteca {
  financiadorId: string | null;
  importe: string;
  cuentaDesembolsoId: string | null;
  /** Sin valor por defecto (v0.7). */
  tipoInteres: TipoInteresHipoteca | null;
  tasa: string;
  plazo: string;
  unidadPlazo: UnidadPlazo;
  /** ISO o el texto tal como se escribió. */
  primeraCuota: string;
  cuentaCargoId: string | null;
  titularidad: EleccionReparto;
}

export const borradorHipoteca = (): BorradorHipoteca => ({
  financiadorId: null, importe: '', cuentaDesembolsoId: null, tipoInteres: null, tasa: '', plazo: '', unidadPlazo: 'ANIOS', primeraCuota: '',
  cuentaCargoId: null, titularidad: null,
});

/** La propuesta se ofrece marcada si existe; sin titularidad no se marca nada (nunca «100 % tuyo» inventado). */
export const eleccionPropuesta = (propuesta: ParteEnFecha[] | null): EleccionReparto =>
  propuesta && propuesta.length > 0 ? { modo: 'TITULARIDAD' } : null;

/**
 * N-30 (Q-T3D-08): propuesta del reparto de los intereses = titularidad DEL PRÉSTAMO vigente en el vencimiento (`fechaIso`), leída de L-HIP
 * (`titularidad_prestamo`), con el mismo criterio que W-HIP-02 relee (vigente_desde ≤ fecha ≤ vigente_hasta). null si el servidor no la da.
 */
export function titularidadPrestamoEnFecha(h: Hipoteca, fechaIso: string): ParteEnFecha[] | null {
  if (!h.titularidad_prestamo) return null;
  return h.titularidad_prestamo
    .filter((t) => t.vigente_desde <= fechaIso && (t.vigente_hasta === null || fechaIso <= t.vigente_hasta))
    .map((t) => ({ actor_id: t.actor_id, porcentaje: t.porcentaje, yo: t.yo, tercero_id: t.tercero_id, nombre: t.nombre }));
}

/** «2,5» → «2.5»; null si no es un tipo anual válido (0 a 30 %, hasta 4 decimales). */
export function normalizarTasa(t: string): string | null {
  const x = t.trim().replace(',', '.');
  if (!/^\d{1,2}(\.\d{1,4})?$/.test(x)) return null;
  return Number(x) <= TASA_MAXIMA ? x : null;
}

/** Plazo → número de cuotas mensuales (1 a 600); null si no vale. */
export function numeroCuotas(plazo: string, unidad: UnidadPlazo): number | null {
  if (!/^\d{1,3}$/.test(plazo.trim())) return null;
  const n = Number(plazo.trim()) * (unidad === 'ANIOS' ? 12 : 1);
  return n >= 1 && n <= MAX_CUOTAS ? n : null;
}

const pct = (t: string) => Number(t.replace(',', '.'));

/** Lo que falta en un reparto (propuesta o «otro reparto» que sume 100 %). */
export function faltasReparto(e: EleccionReparto, propuesta: ParteEnFecha[] | null): string[] {
  if (e === null) return ['elegir el reparto'];
  if (e.modo === 'TITULARIDAD') return propuesta && propuesta.length > 0 ? [] : ['una titularidad registrada o indica otro reparto'];
  const v = Object.values(e.partes).map(pct);
  if (v.length === 0 || v.some((x) => !(x > 0 && x <= 100)) || Math.round(v.reduce((s, x) => s + x, 0) * 10000) !== 1000000) return ['un reparto que sume 100 %'];
  return [];
}

/** Lo que falta en el bloque «Hipoteca», en el orden del formulario. */
export function faltasHipoteca(b: BorradorHipoteca, escrituraIso: string, propuesta: ParteEnFecha[] | null): string[] {
  const r: string[] = [];
  if (!b.financiadorId) r.push('el banco');
  if (!parsearImporte(b.importe).ok) r.push('el importe del préstamo');
  if (!b.cuentaDesembolsoId) r.push('la cuenta en la que el banco deja el préstamo');
  if (b.tipoInteres === null) r.push('tipo fijo o variable');
  if (normalizarTasa(b.tasa) === null) r.push('el tipo anual (0 a 30 %, hasta 4 decimales)');
  if (numeroCuotas(b.plazo, b.unidadPlazo) === null) r.push('el plazo (hasta 600 cuotas)');
  if (!esFechaIso(b.primeraCuota)) r.push('la fecha de la primera cuota');
  else if (esFechaIso(escrituraIso) && b.primeraCuota <= escrituraIso) r.push('una primera cuota posterior a la escritura');
  if (!b.cuentaCargoId) r.push('la cuenta de cargo de las cuotas');
  return [...r, ...faltasReparto(b.titularidad, propuesta).map((x) => `${x} del préstamo`)];
}

/** Se puede pedir el cuadro (W-HIP-00): importe, tipo y plazo válidos. */
export const puedeVerCuadro = (b: BorradorHipoteca) =>
  parsearImporte(b.importe).ok && normalizarTasa(b.tasa) !== null && numeroCuotas(b.plazo, b.unidadPlazo) !== null;

const importeTexto = (t: string) => {
  const p = parsearImporte(t);
  return p.ok ? p.valor : t;
};

/** W-HIP-00 · vista previa sin escritura. */
export function payloadCuadroPrevio(b: BorradorHipoteca): PayloadCuadroPrevio {
  const p: PayloadCuadroPrevio = { capital: importeTexto(b.importe), tasa_anual: normalizarTasa(b.tasa) ?? b.tasa, numero_cuotas: numeroCuotas(b.plazo, b.unidadPlazo) ?? 0 };
  if (esFechaIso(b.primeraCuota)) p.primera_cuota = b.primeraCuota;
  return p;
}

/** Partes del reparto elegido: la propuesta tal cual o «otro reparto» con el porcentaje en texto decimal. */
export function partesReparto(e: EleccionReparto, propuesta: ParteEnFecha[] | null): ParteAtribucion[] {
  if (e?.modo === 'MANUAL') return Object.entries(e.partes).map(([actor_id, x]) => ({ actor_id, porcentaje: x.trim().replace(',', '.') }));
  return (propuesta ?? []).map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje }));
}

/** Bloque `hipoteca` de C-COMPRA-01 (contrato §3.2.1). Titularidad del préstamo: propuesta de la escritura aceptada u otro reparto. */
export function bloqueHipoteca(b: BorradorHipoteca, propuesta: ParteEnFecha[] | null, escrituraIso: string): BloqueHipotecaWire {
  return {
    financiador: { tercero_id: b.financiadorId! },
    importe_prestamo: importeTexto(b.importe),
    cuenta_desembolso_id: b.cuentaDesembolsoId!,
    titularidad: b.titularidad?.modo === 'MANUAL'
      ? { modo: 'MANUAL', partes: partesReparto(b.titularidad, propuesta) }
      : { modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_ESCRITURA', fecha_referencia: escrituraIso, partes: partesReparto(b.titularidad, propuesta) } },
    tipo_interes: b.tipoInteres!,
    tasa_anual_pct: normalizarTasa(b.tasa) ?? b.tasa,
    numero_cuotas: numeroCuotas(b.plazo, b.unidadPlazo) ?? 0,
    fecha_primera_cuota: b.primeraCuota,
    cuenta_cargo_id: b.cuentaCargoId!,
  };
}

/** La petición de la compra con su hipoteca; sin hipoteca, la petición no cambia (ni siquiera la clave). */
export function conHipoteca(p: PayloadCompra, b: BorradorHipoteca | null, propuesta: ParteEnFecha[] | null): PayloadCompra {
  if (b === null) return p;
  return { ...p, hipoteca: bloqueHipoteca(b, propuesta, p.fecha_escritura) };
}

// ------------------------------------------------------------------ cuadro
/** Vista previa: las 12 primeras y la última, o todas. */
export function filasPrevioVisibles(cuotas: FilaCuadroPrevio[], todas: boolean, n = 12): FilaCuadroPrevio[] {
  if (todas || cuotas.length <= n + 1) return cuotas;
  return [...cuotas.slice(0, n), cuotas[cuotas.length - 1]];
}

/** Hipoteca registrada: ventana alrededor de la próxima cuota (3 antes y 8 después) y la última; o todas. */
export function cuotasVisibles(h: Hipoteca, todas: boolean): CuotaHipoteca[] {
  if (todas) return h.cuotas;
  const prox = h.proxima_cuota ? h.cuotas.findIndex((q) => q.numero === h.proxima_cuota!.numero) : h.cuotas.length - 1;
  const desde = Math.max(0, prox - 3);
  const ventana = h.cuotas.slice(desde, desde + 12);
  const ultima = h.cuotas[h.cuotas.length - 1];
  return ultima === undefined || ventana.includes(ultima) ? ventana : [...ventana, ultima];
}

export const condicionesVigentes = (h: Hipoteca): CondicionesHipoteca | null =>
  h.condiciones.find((v) => v.vigente_hasta === null) ?? h.condiciones[h.condiciones.length - 1] ?? null;

/** «2,5 %». */
export const textoTasa = (t: string | null) => (t === null ? 'Sin tipo' : `${t.replace('.', ',')} %`);

/** Lo que queda por pagar: el del servidor; legacy sin saldo conocido → null (se pinta «No disponible», nunca 0). */
export const deudaConocida = (h: Hipoteca): string | null => (h.deuda_indeterminada ? null : h.deuda_pendiente);

/** Detalle de la fila «Hipoteca» de la ficha. */
export function detalleFichaHipoteca(h: Hipoteca): string {
  const deuda = deudaConocida(h);
  const queda = deuda === null ? 'Lo que queda por pagar: no disponible' : `Te queda ${formatearEur(deuda)}`;
  return h.cuota_vigente ? `${queda} · cuota ${formatearEur(h.cuota_vigente)}` : queda;
}

// ------------------------------------------------------------------ pago de una cuota
const centimos = (x: string): number => {
  const m = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(x.trim());
  if (!m) return NaN;
  return (m[1] ? -1 : 1) * (Number(m[2]) * 100 + Number((m[3] ?? '').padEnd(2, '0')));
};

/** Desglose de la cuota tal como lo da el servidor. El cliente solo comprueba capital + intereses = cuota. */
export function desglosePago(q: CuotaHipoteca): { capital: string; intereses: string; salida: string; cuadra: boolean } {
  const cap = centimos(q.capital);
  const int = centimos(q.interes);
  const total = centimos(q.cuota);
  return { capital: q.capital, intereses: q.interes, salida: q.cuota, cuadra: !Number.isNaN(cap + int + total) && cap + int === total };
}

/** Botón «Pagar la cuota»: solo con la exposición de código, una próxima cuota, la hipoteca activa y la deuda conocida. Nunca swipe. */
export const ofrecePagoCuota = (h: Hipoteca, expuesto: boolean): boolean =>
  expuesto && h.proxima_cuota !== null && h.estado === 'ACTIVA' && !h.deuda_indeterminada;

export function faltasPago(fechaIso: string | null, hoyIso: string, cuentaId: string | null, e: EleccionReparto, propuesta: ParteEnFecha[] | null): string[] {
  const r: string[] = [];
  if (!fechaIso || !esFechaIso(fechaIso)) r.push('la fecha del cargo');
  else if (fechaIso > hoyIso) r.push('una fecha del cargo que no sea futura');
  if (!cuentaId) r.push('la cuenta');
  return [...r, ...faltasReparto(e, propuesta).map((x) => `${x} de los intereses`)];
}

/** W-HIP-02: `propuesta_vista` = la propuesta mostrada; `partes` = la elegida (la propuesta u otro reparto). */
export function payloadPago(h: Hipoteca, cuentaId: string, fechaIso: string, e: EleccionReparto, propuesta: ParteEnFecha[] | null, intencionId: string): PayloadPagoCuota {
  return {
    intencion_id: intencionId, row_version_esperada: h.row_version, cuenta_id: cuentaId, fecha_pago: fechaIso,
    atribucion: { propuesta_vista: { partes: partesReparto({ modo: 'TITULARIDAD' }, propuesta) }, partes: partesReparto(e, propuesta) },
  };
}

// ------------------------------------------------------------------ revisión del tipo
export interface BorradorRevision { desde: string; tasa: string; tipoInteres: TipoInteresHipoteca | null; indice: string; diferencial: string }
export const borradorRevision = (): BorradorRevision => ({ desde: '', tasa: '', tipoInteres: null, indice: '', diferencial: '' });

const ABIERTAS = ['PENDIENTE', 'VENCIDA'];

/** Cuotas que se recalculan con una revisión desde `desdeIso` (vencimiento ≥ desde). */
export const cuotasAfectadas = (h: Hipoteca, desdeIso: string): CuotaHipoteca[] => h.cuotas.filter((q) => q.vencimiento >= desdeIso);

/** «Se recalculan N cuotas desde el …; las M pagadas no cambian.» (nunca «bonificación»). */
export function textoAlcance(n: number, desdeIso: string, pagadas: number): string {
  const recalculo = n === 1 ? 'Se recalcula 1 cuota' : `Se recalculan ${n} cuotas`;
  const quedan = pagadas === 1 ? 'la 1 pagada no cambia' : `las ${pagadas} pagadas no cambian`;
  return `${recalculo} desde el ${diaMesAnioIso(desdeIso)}; ${quedan}.`;
}

export function faltasRevision(r: BorradorRevision, h: Hipoteca): string[] {
  const out: string[] = [];
  const vigente = condicionesVigentes(h);
  if (!esFechaIso(r.desde)) out.push('la fecha desde la que aplica');
  else if (vigente && r.desde <= vigente.vigente_desde) out.push('una fecha posterior a las condiciones vigentes');
  else {
    const afectadas = cuotasAfectadas(h, r.desde);
    if (afectadas.length === 0) out.push('una fecha con cuotas por vencer');
    else if (afectadas.some((q) => !ABIERTAS.includes(q.estado))) out.push('una fecha posterior a la última cuota pagada');
  }
  if (normalizarTasa(r.tasa) === null) out.push('el nuevo tipo anual (0 a 30 %, hasta 4 decimales)');
  if (r.diferencial.trim() && !/^-?\d{1,2}([.,]\d{1,4})?$/.test(r.diferencial.trim())) out.push('un diferencial válido o vacío');
  return out;
}

export function payloadRevision(r: BorradorRevision, h: Hipoteca, intencionId: string): PayloadRevisionTipo {
  const p: PayloadRevisionTipo = { intencion_id: intencionId, row_version_esperada: h.row_version, vigente_desde: r.desde, tasa_anual: normalizarTasa(r.tasa) ?? r.tasa };
  if (r.tipoInteres) p.tipo_interes = r.tipoInteres;
  if (r.indice.trim()) p.indice_referencia = r.indice.trim();
  if (r.diferencial.trim()) p.diferencial = r.diferencial.trim().replace(',', '.');
  return p;
}

// ------------------------------------------------------------------ textos de rechazo (R-1: sin «ingreso» ni «cobro»)
const PALABRAS_PROHIBIDAS = /ingres|cobr/i;

/** Un texto que llega del servidor solo se muestra si no dice «ingreso» ni «cobro»; si no, el genérico. */
export const textoSeguro = (t: string | null | undefined, alternativo = TEXTO_GENERICO): string => (t && !PALABRAS_PROHIBIDAS.test(t) ? t : alternativo);

const MOTIVOS: Record<string, string> = {
  PRIMERA_CUOTA_NO_POSTERIOR_A_LA_ESCRITURA: 'La primera cuota tiene que ser posterior a la escritura.',
  VALORES_FUERA_DE_RANGO: 'Revisa el importe del préstamo, el tipo anual (0 a 30 %) y el plazo (hasta 600 cuotas).',
  DATO_OBLIGATORIO_AUSENTE: 'Faltan datos de la hipoteca.',
  PERIODICIDAD_NO_SOPORTADA: 'Solo se admite el pago mensual.',
  SISTEMA_NO_SOPORTADO: 'Solo se admite la cuota constante (sistema francés).',
};

const ERRORES: Record<string, string> = {
  CUENTA_SIN_CAPACIDAD: 'Esta cuenta no puede recibir dinero en la fecha de la escritura.',
  HIPOTECA_YA_REGISTRADA: 'Esta propiedad ya tiene una hipoteca activa.',
  TERCERO_NO_DISPONIBLE: 'El banco elegido no está disponible.',
  CUOTA_NO_PENDIENTE: 'Esta cuota ya no está pendiente.',
  CUOTA_ANTERIOR_PENDIENTE: 'Hay una cuota anterior sin pagar.',
  FECHA_PAGO_INCOHERENTE: 'La fecha del cargo no puede ser futura.',
  EXCEDE_SALDO_POSICION: 'El capital supera lo que queda por pagar.',
  CUENTA_DESCONOCIDA: 'Esa cuenta no se puede usar para pagar en esa fecha.',
  ATRIBUCION_PROPUESTA_DESFASADA: 'La titularidad del préstamo ha cambiado. Revisa el reparto de los intereses.',
  SALDO_PRINCIPAL_INDETERMINADO: 'No se conoce lo que quedaba por pagar de esta hipoteca: no se puede pagar ni revisar.',
  OPERACION_NO_PERMITIDA_EN_ESTADO: 'La hipoteca no está activa.',
  REVISION_SOBRE_CUOTA_PAGADA: 'La revisión afecta a una cuota que ya no está pendiente.',
  SIN_CUOTAS_FUTURAS: 'No quedan cuotas desde esa fecha.',
  FECHA_REVISION_INCOHERENTE: 'La fecha de la revisión debe ser posterior a la de las condiciones vigentes.',
  IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION: 'Este registro ya existe con otros datos. No se ha guardado nada nuevo.',
  SUMA_NO_CUADRA: 'El reparto no suma el 100 %.',
};

/** Texto de un rechazo de la hipoteca; null si el código no es de la hipoteca (lo resuelve quien llama). */
export function textoErrorHipoteca(codigo: string, detalle?: Record<string, unknown>): string | null {
  if (codigo === 'CONDICIONES_INCOMPLETAS') {
    const motivo = typeof detalle?.motivo === 'string' ? detalle.motivo : null;
    return (motivo && MOTIVOS[motivo]) || 'Revisa los datos de la hipoteca.';
  }
  return ERRORES[codigo] ?? null;
}
