// ============================================================
// GAPTO MOBILE 2027
// Fichero: compra.ts
// Ruta: mobile/src/domain/compra.ts
// Descripción: Lógica pura de B2 · Compra (F06-01 B2; R1 v0.9.5 Parte II; lámina F06-01 v0.9 B1–B4, B6 y D1). Borrador de la compra (precio, fecha de escritura, valor de referencia, pagos propios sin hipoteca y gastos de la compra), validaciones de cada paso, resumen (coste = precio + gastos; lo que sale de tus cuentas aparte; gasto del mes 0), propuesta de atribución en la FECHA DE ESCRITURA para todas las raíces (AJ-TR1-10: «Según la titularidad de <propiedad> en la escritura (<fecha>)» y aviso para los gastos anteriores; nunca se marca sola ni se rellena con YO 100), payload de C-COMPRA-01 y C-COMPRA-03, textos de rechazo (ATRIBUCION_PROPUESTA_DESFASADA) y derivación de Día a día para los hechos patrimoniales (HF-14: la fuente es el `tipo` del hecho; «Coste de la compra · no es gasto del mes», importe con signo de cuenta). Consumidores de 0352 (declarar el coste completo): constante de código `CONSUMIDORES_0352_HABILITADOS`, true desde A3-0352 (0352 certificada por D-210; L-05); con false la interfaz no ofrece declarar nada.
// Versión: 0.1.0 (F06 T1-F06 B2 N1)
// Versión: 0.2.0 (F06 T2-F06 A3-0352 (L-05)): `CONSUMIDORES_0352_HABILITADOS = true`; R15-a en el cliente (contrato A3-0352 v1.1 §6): `puedeDeclararCompleto` (UX-1, solo con la fecha de adquisición conocida), `TEXTO_NOTA_SIN_FECHA` (UX-2), `MOTIVOS_COSTE_ADQUISICION` y `textoEstadoCoste` con SIN_FECHA_DE_ADQUISICION y LECTURA_NO_ESTABLE (UX-3) y `TEXTOS_ERROR` con COMPLETITUD_SIN_FECHA_DE_ADQUISICION, mismo texto que el servidor (UX-4).
// Versión: 0.3.0 (F06 T3-F06 bloque 2 F06-01H, paso 10): `TEXTO_SIN_HIPOTECA` deja de decir que la hipoteca no se registra (ya se registra dentro de la compra, bloque «Hipoteca» de CompraScreen). Nada más cambia: la lógica de la hipoteca vive en domain/hipoteca.ts.
// Versión: 0.4.0 (F06 T3-F06 · MANT N1 R-B2-06 (AJ-01), firma b88a3662…): `enviarCompraComprobando` (ante un INDETERMINADO reenvía la MISMA petición, replay idempotente sin duplicar, y devuelve el resultado real), `TEXTO_COMPROBANDO_COMPRA`, `TEXTO_COMPRA_SIN_CONFIRMAR` y `COMPROBACIONES_COMPRA`. La compra con hipoteca larga puede tardar más que el timeout general por la validación G2 de 0354 al COMMIT (≈ 35 ms por cuota; STOP_MANT_RB206_B).
// Versión: 0.5.0 (F06 T6 · S3 compra; F09 0.55 §12.107.2, DP-14, DT-02, DT-03, AJ-UX2-07): SOLO funciones de presentación nuevas (`faltasPagos` y el wire no cambian): `faltasDeUnPago` (lo que falta a un pago para confirmarlo en su línea, con las mismas reglas por pago de `faltasPagos`), `totalesPagos` («Pagado desde tus cuentas», «· de la hipoteca», «· resto, sin hipoteca» y «Falta por cuadrar», no persistidos), `importePorcentaje` (préstamo = round_half_up(precio_céntimos × pct / 100) en céntimos enteros, pct de hasta 2 decimales) y `prestamoSuperaPrecio` (ayuda de pantalla, no invariante).
// ============================================================

import type {
  AtribucionWire, ConceptoGasto, CosteAmbito, EstadoCoste, LineaGastoWire, ParteEnFecha, PayloadCompra, PayloadGastoCompra, RolPago,
} from '../api/patrimonio';
import { diaMesAnioIso, diaMesIso } from './fechas';
import { formatearEur, parsearImporte } from './importe';
import { esFechaIso } from './intencion';

/** O10.29-H: true desde A3-0352 (0352 certificada por D-210). Constante de código: solo cambia con un commit revisado; nunca por configuración. */
export const CONSUMIDORES_0352_HABILITADOS = true;

export const NOMBRE_CONCEPTO: Record<ConceptoGasto, string> = {
  ITP: 'ITP',
  IVA_AJD: 'IVA y AJD',
  NOTARIA_REGISTRO_GESTORIA: 'Notaría, registro y gestoría',
  AGENCIA: 'Agencia',
  OTRO: 'Otro gasto',
};
export const CONCEPTOS: ConceptoGasto[] = ['ITP', 'IVA_AJD', 'NOTARIA_REGISTRO_GESTORIA', 'AGENCIA', 'OTRO'];
export const NOMBRE_ROL: Record<RolPago, string> = { ARRAS: 'Arras', FIRMA: 'En la firma', OTRO: 'Otro pago' };
export const ROLES: RolPago[] = ['ARRAS', 'FIRMA', 'OTRO'];

export const TEXTO_VALOR_REFERENCIA = 'El valor de referencia se guarda como dato fiscal. No cambia el precio ni se usa para calcular nada aquí.';
export const TEXTO_GASTOS = 'Pon lo que pagaste de verdad (modelo 600, factura de notaría…). Cada pago se guarda como un registro propio y suma al coste de la vivienda.';
export const TEXTO_SIN_HIPOTECA = 'Sin hipoteca, la compra se guarda con lo que pagaste de tus cuentas. Si hay hipoteca, añádela aquí.';
export const TEXTO_NADIE_MARCADO = 'Ninguna opción viene marcada. La titularidad solo propone; decides tú. Si la titularidad cambia más adelante, este reparto no cambia.';
export const TEXTO_SIN_TITULARIDAD = 'No hay titularidad registrada en la fecha de la escritura: elige otro reparto o «No lo sé».';
export const TEXTO_DESFASADA = 'La titularidad ha cambiado: revisa el reparto.';
export const TEXTO_NO_GASTO_MES = 'Coste de la compra · no es gasto del mes';
export const TEXTO_INDETERMINADO_COMPRA = 'No se ha podido confirmar la compra. Revisa la propiedad antes de repetirla.';
/** R-B2-06 (AJ-01): mientras se comprueba, tras un timeout, si la compra se guardó (replay idempotente). */
export const TEXTO_COMPROBANDO_COMPRA = 'Comprobando si la compra se ha guardado…';
/** R-B2-06 (AJ-01): la comprobación tampoco ha podido confirmar; nunca se dice que ha fallado ni se invita a repetirla. */
export const TEXTO_COMPRA_SIN_CONFIRMAR =
  'Todavía no podemos confirmar si la compra se ha guardado. No la repitas: abre la propiedad dentro de unos minutos para comprobarlo.';
/** R-B2-06 (AJ-01): reenvíos de comprobación tras un INDETERMINADO (timeout o red). */
export const COMPROBACIONES_COMPRA = 2;

/**
 * R-B2-06 (AJ-01): envía la compra y, si la respuesta es INDETERMINADO (timeout, red o 5xx), NO la da por fallida: reenvía la
 * MISMA petición (`enviar` cierra sobre el mismo cuerpo, con la misma `intencion_id`) hasta `n` veces. El servidor resuelve el
 * reenvío como replay idempotente (`idempotente: true`, sin escribir) si la compra ya se guardó, o la guarda si no llegó; nunca
 * duplica (identidad de C-COMPRA-01). Devuelve la primera respuesta definitiva (OK o RECHAZADO) o el último INDETERMINADO.
 */
export async function enviarCompraComprobando<R extends { tipo: string }>(
  enviar: () => Promise<R>,
  alComprobar?: () => void,
  n: number = COMPROBACIONES_COMPRA,
): Promise<{ respuesta: R; comprobaciones: number }> {
  let respuesta = await enviar();
  let comprobaciones = 0;
  while (respuesta.tipo === 'INDETERMINADO' && comprobaciones < n) {
    comprobaciones += 1;
    alComprobar?.();
    respuesta = await enviar();
  }
  return { respuesta, comprobaciones };
}
/** UX-2 (A3-0352): sin fecha de adquisición no se ofrece declarar el coste completo. */
export const TEXTO_NOTA_SIN_FECHA = 'Para marcar que no faltan gastos, añade antes la fecha de adquisición en la ficha de la propiedad.';
/** UX-4 (A3-0352): mismo texto que `RECHAZOS` del servidor (backend/app/patrimonio/rutas.py). */
export const TEXTO_SIN_FECHA_ADQUISICION = 'Para marcar el coste como completo, indica antes la fecha de adquisición de la propiedad.';

/** UX-1 (R15-a): la declaración «no faltan gastos» solo se ofrece con los consumidores habilitados y la fecha de adquisición conocida. */
export const puedeDeclararCompleto = (fechaAdquisicion: string | null | undefined): boolean => CONSUMIDORES_0352_HABILITADOS && !!fechaAdquisicion;

export interface PagoBorrador { id: string; rol: RolPago; cuentaId: string | null; fecha: string; importe: string }
export interface GastoBorrador { id: string; concepto: ConceptoGasto; cuentaId: string | null; fechaEconomica: string; fechaPago: string; importe: string; nota: string }
export type EleccionAtribucion = null | { modo: 'TITULARIDAD' } | { modo: 'NO_LO_SE' } | { modo: 'MANUAL'; partes: Record<string, string> };

export interface BorradorCompra {
  precio: string;
  fechaEscritura: string;
  valorReferencia: string;
  pagos: PagoBorrador[];
  gastos: GastoBorrador[];
  atribucion: EleccionAtribucion;
  /** Solo con CONSUMIDORES_0352_HABILITADOS: «no faltan gastos» (declaración de la adquisición). */
  completo: boolean;
}

const D = (t: string): number => {
  const p = parsearImporte(t);
  return p.ok ? Math.round(Number(p.valor) * 100) : NaN;
};
const texto2 = (cent: number) => (cent / 100).toFixed(2);

export function borradorInicial(hoyIso: string): BorradorCompra {
  return { precio: '', fechaEscritura: hoyIso, valorReferencia: '', pagos: [], gastos: [], atribucion: null, completo: false };
}

export function faltasPrecio(b: BorradorCompra): string[] {
  const r: string[] = [];
  if (!parsearImporte(b.precio).ok) r.push('precio mayor que 0 con 2 decimales como mucho');
  if (!esFechaIso(b.fechaEscritura)) r.push('fecha de la escritura');
  if (b.valorReferencia.trim() && !parsearImporte(b.valorReferencia).ok) r.push('valor de referencia válido o vacío');
  return r;
}

export const sumaPagos = (b: BorradorCompra) => b.pagos.reduce((s, x) => s + D(x.importe), 0);
export const sumaGastos = (b: BorradorCompra) => b.gastos.reduce((s, x) => s + D(x.importe), 0);

/** «Pagado entre todo»: suma de los pagos con importe válido (los inválidos no suman). */
export function textoPagado(b: BorradorCompra): string {
  return texto2(b.pagos.reduce((s, x) => s + (Number.isNaN(D(x.importe)) ? 0 : D(x.importe)), 0));
}

export function faltasPagos(b: BorradorCompra): string[] {
  const r: string[] = [];
  if (b.pagos.length === 0) r.push('al menos un pago');
  for (const x of b.pagos) {
    if (!x.cuentaId) r.push('la cuenta de cada pago');
    if (!parsearImporte(x.importe).ok) r.push('el importe de cada pago');
    if (!esFechaIso(x.fecha)) r.push('la fecha de cada pago');
    if (x.rol === 'FIRMA' && esFechaIso(x.fecha) && x.fecha !== b.fechaEscritura) r.push('el pago de la firma va en la fecha de escritura');
    if (x.rol === 'ARRAS' && esFechaIso(x.fecha) && x.fecha > b.fechaEscritura) r.push('las arras no pueden ser posteriores a la escritura');
  }
  if (r.length === 0 && sumaPagos(b) !== D(b.precio)) r.push('los pagos tienen que sumar el precio');
  return [...new Set(r)];
}

export function faltasGasto(g: GastoBorrador): string[] {
  const r: string[] = [];
  if (!g.cuentaId) r.push('la cuenta');
  if (!parsearImporte(g.importe).ok) r.push('el importe');
  if (!esFechaIso(g.fechaEconomica)) r.push('la fecha del gasto');
  if (!esFechaIso(g.fechaPago)) r.push('la fecha de pago');
  if (g.nota.length > 0 && !g.nota.trim()) r.push('una nota con texto o vacía');
  return r;
}

export function faltasGastos(b: BorradorCompra): string[] {
  return [...new Set(b.gastos.flatMap(faltasGasto))];
}

export function faltasAtribucion(e: EleccionAtribucion, propuesta: ParteEnFecha[] | null): string[] {
  if (e === null) return ['elegir de quién es el coste'];
  if (e.modo === 'TITULARIDAD' && (!propuesta || propuesta.length === 0)) return [TEXTO_SIN_TITULARIDAD];
  if (e.modo === 'MANUAL') {
    const v = Object.values(e.partes).map((x) => Number(x.replace(',', '.')));
    if (v.some((x) => !(x > 0 && x <= 100)) || Math.round(v.reduce((s, x) => s + x, 0) * 10000) !== 1000000) return ['un reparto que sume 100 %'];
  }
  return [];
}

/** Resumen B4: coste (precio + gastos), lo que sale de tus cuentas y gasto del mes (siempre 0). */
export function resumen(b: BorradorCompra): { coste: string; sale: string; gastoMes: string; registros: number; pagos: number } {
  const coste = D(b.precio) + sumaGastos(b);
  return { coste: texto2(coste), sale: texto2(-(sumaPagos(b) + sumaGastos(b))), gastoMes: '0.00', registros: 1 + b.gastos.length, pagos: b.pagos.length + b.gastos.length };
}

const nombreParte = (x: ParteEnFecha) => (x.yo ? 'Tú' : x.nombre ?? 'Otra persona');
const pct = (p: string) => `${Number(p).toLocaleString('es-ES', { maximumFractionDigits: 4 })} %`;

/** AJ-TR1-10: «Según la titularidad de Piso Ejemplo en la escritura (20 mar 2027)». */
export const textoPropuestaEscritura = (propiedad: string, fechaEscritura: string) =>
  `Según la titularidad de ${propiedad} en la escritura (${diaMesAnioIso(fechaEscritura)})`;
/** «Tú 60 % · Ana 40 %»: tú primero y los demás en el orden del servidor. */
export const textoPartes = (partes: ParteEnFecha[]) =>
  [...partes.filter((x) => x.yo), ...partes.filter((x) => !x.yo)].map((x) => `${nombreParte(x)} ${pct(x.porcentaje)}`).join(' · ');

/** Aviso para los gastos con fecha anterior a la escritura (se usa la titularidad de la escritura, no la de cada gasto). */
export function avisoGastosAnteriores(b: BorradorCompra): string | null {
  const anteriores = b.gastos.filter((g) => esFechaIso(g.fechaEconomica) && g.fechaEconomica < b.fechaEscritura);
  if (anteriores.length === 0) return null;
  const fechas = [...new Set(anteriores.map((g) => diaMesIso(g.fechaEconomica)))].join(', ');
  return `Para ${anteriores.length === 1 ? 'el gasto' : 'los gastos'} del ${fechas} se usa la titularidad de la escritura, no la vigente en la fecha de ese gasto.`;
}

function atribucionWire(e: EleccionAtribucion, propuesta: ParteEnFecha[] | null, criterio: 'TITULARIDAD_EN_FECHA_ESCRITURA' | 'TITULARIDAD_EN_FECHA_ECONOMICA',
  fechaReferencia: string): AtribucionWire {
  if (e === null || e.modo === 'NO_LO_SE') return { modo: 'NO_LO_SE' };
  if (e.modo === 'MANUAL') return { modo: 'MANUAL', partes: Object.entries(e.partes).map(([actor_id, p]) => ({ actor_id, porcentaje: p.replace(',', '.') })) };
  return { modo: 'SEGUN_TITULARIDAD_ACEPTADA', propuesta_vista: { criterio, fecha_referencia: fechaReferencia, partes: (propuesta ?? []).map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje })) } };
}

const importeTexto = (t: string) => {
  const p = parsearImporte(t);
  return p.ok ? p.valor : t;
};

const lineaGasto = (g: GastoBorrador): LineaGastoWire => ({
  linea_id: g.id, concepto: g.concepto, cuenta_id: g.cuentaId!, fecha_economica: g.fechaEconomica, fecha_pago: g.fechaPago,
  importe: importeTexto(g.importe), ...(g.nota.trim() ? { nota: g.nota.trim() } : {}),
});

/** C-COMPRA-01. Una sola propuesta para todo el lote, en la fecha de escritura (AJ-TR1-10). Sin declaración mientras 0352 no esté habilitada. */
export function payloadCompra(intencionId: string, rowVersion: number, b: BorradorCompra, propuesta: ParteEnFecha[] | null): PayloadCompra {
  const p: PayloadCompra = {
    intencion_id: intencionId,
    row_version_esperada: rowVersion,
    fecha_escritura: b.fechaEscritura,
    precio: importeTexto(b.precio),
    pagos_propios: b.pagos.map((x) => ({ linea_id: x.id, rol: x.rol, cuenta_id: x.cuentaId!, fecha_pago: x.fecha, importe: importeTexto(x.importe) })),
    gastos: b.gastos.map(lineaGasto),
    atribucion: atribucionWire(b.atribucion, propuesta, 'TITULARIDAD_EN_FECHA_ESCRITURA', b.fechaEscritura),
  };
  if (b.valorReferencia.trim()) p.valor_referencia = importeTexto(b.valorReferencia);
  if (CONSUMIDORES_0352_HABILITADOS && b.completo) p.completitud_adquisicion = { completo: true, fecha_corte: b.fechaEscritura };
  return p;
}

/** C-COMPRA-03: la propuesta se lee en la fecha económica de SU efecto (sin excepción). */
export function payloadGastoCompra(intencionId: string, rowVersion: number, g: GastoBorrador, e: EleccionAtribucion,
  propuesta: ParteEnFecha[] | null): PayloadGastoCompra {
  return { intencion_id: intencionId, row_version_esperada: rowVersion, linea: lineaGasto(g),
    atribucion: atribucionWire(e, propuesta, 'TITULARIDAD_EN_FECHA_ECONOMICA', g.fechaEconomica) };
}

// ------------------------------------------------------------------ estado del coste (L-COSTE)
/** Motivos de L-COSTE (backend/app/patrimonio/coste.py) y su texto propio en ADQUISICION; null = texto general del estado (UX-3, O-A3-TXT). */
export const MOTIVOS_COSTE_ADQUISICION: Record<string, string | null> = {
  SIN_COMPONENTES: null,
  SIN_DECLARACION: null,
  SIN_FECHA_DE_ADQUISICION: 'Parcial · falta la fecha de adquisición',
  LECTURA_NO_ESTABLE: 'Parcial',
  LECTURA_ANTERIOR_AL_CORTE: null,
  DECLARACION_DESACTUALIZADA: null,
  COMPONENTE_POSTERIOR_AL_CORTE: null,
};

export function textoEstadoCoste(c: CosteAmbito | null, ambito: 'ADQUISICION' | 'MEJORAS'): string {
  if (!c || c.estado === 'NO_DISPONIBLE') return 'No disponible';
  if (c.estado === 'COMPLETO') return ambito === 'MEJORAS' && c.componentes === 0 ? 'Completo · sin mejoras' : 'Completo';
  if (ambito === 'ADQUISICION') return (c.motivo_estado ? MOTIVOS_COSTE_ADQUISICION[c.motivo_estado] : null) ?? 'Parcial · puedes añadir gastos';
  return 'Parcial';
}

export const etiquetaEstado = (e: EstadoCoste) => (e === 'COMPLETO' ? 'completo' : e === 'PARCIAL' ? 'parcial' : 'no disponible');

/** Hay compra registrada: la adquisición tiene componentes. */
export const hayCompra = (c: CosteAmbito | null | undefined) => !!c && c.componentes > 0;

// ------------------------------------------------------------------ textos de rechazo
const TEXTOS_ERROR: Record<string, string> = {
  ATRIBUCION_PROPUESTA_DESFASADA: TEXTO_DESFASADA,
  TITULARIDAD_NO_DISPONIBLE_EN_FECHA: TEXTO_SIN_TITULARIDAD,
  COMPRA_YA_REGISTRADA: 'Esta propiedad ya tiene su compra registrada.',
  COMPRA_NO_REGISTRADA: 'Primero registra la compra de esta propiedad.',
  FECHA_PAGO_INCOHERENTE: 'Las arras no pueden ser posteriores a la escritura y el pago de la firma va en la fecha de escritura.',
  SUMA_NO_CUADRA: 'Los pagos tienen que sumar el precio.',
  CUENTA_DESCONOCIDA: 'Una de las cuentas no se puede usar para pagar en esa fecha.',
  IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION: 'Esta compra ya se guardó con otros datos. No se ha guardado nada nuevo.',
  PROPIEDAD_NO_DISPONIBLE: 'Esta propiedad no está disponible.',
  COMPLETITUD_SIN_FECHA_DE_ADQUISICION: TEXTO_SIN_FECHA_ADQUISICION,
};
export const textoErrorCompra = (codigo: string, mensaje: string) => TEXTOS_ERROR[codigo] ?? (mensaje || TEXTO_INDETERMINADO_COMPRA);

// ------------------------------------------------------------------ Día a día (HF-14)
/** Fuente: el `tipo` del HECHO (nunca el del efecto). */
export const esPatrimonial = (tipoHecho: string) => tipoHecho === 'ADQUISICION_PATRIMONIAL' || tipoHecho === 'MEJORA_PATRIMONIAL';
export const etiquetaNoGastoMes = (tipoHecho: string): string | null =>
  tipoHecho === 'ADQUISICION_PATRIMONIAL' ? TEXTO_NO_GASTO_MES : tipoHecho === 'MEJORA_PATRIMONIAL' ? 'Mejora · no es gasto del mes' : null;
export const iconoPatrimonial = (tipoHecho: string): string | null => (esPatrimonial(tipoHecho) ? 'home-outline' : null);
/** Importe con signo de cuenta: sale dinero (−). */
export const importePatrimonial = (importe: string) => `−${formatearEur(importe)}`;

export interface FilaDia { clave: string; fecha: string; titulo: string; detalle: string; importe: string }

/** B6: cómo se verán los pagos en Día a día, por fecha de pago descendente. */
export function filasDiaADia(b: BorradorCompra, propiedad: string, nombreCuenta: (id: string | null) => string): FilaDia[] {
  const filas: FilaDia[] = [
    ...b.pagos.map((x) => ({ clave: x.id, fecha: x.fecha, titulo: `Compra ${propiedad} · ${NOMBRE_ROL[x.rol].toLowerCase()}`,
      detalle: `${nombreCuenta(x.cuentaId)} · ${TEXTO_NO_GASTO_MES}`, importe: importePatrimonial(importeTexto(x.importe)) })),
    ...b.gastos.map((g) => ({ clave: g.id, fecha: g.fechaPago, titulo: `${NOMBRE_CONCEPTO[g.concepto]} ${propiedad}`,
      detalle: `${nombreCuenta(g.cuentaId)} · ${TEXTO_NO_GASTO_MES}`, importe: importePatrimonial(importeTexto(g.importe)) })),
  ];
  return filas.sort((a, z) => (a.fecha < z.fecha ? 1 : a.fecha > z.fecha ? -1 : a.clave < z.clave ? -1 : 1));
}

export const formatearTotal = (cent: string) => formatearEur(cent);

// ------------------------------------------------------------------ F06 T6 · S3: presentación de «¿Cómo se pagó?» (no se persiste)

/** Lo que falta a UN pago para confirmarlo en su línea: las mismas reglas por pago de `faltasPagos`, sin la suma total. */
export function faltasDeUnPago(b: BorradorCompra, pago: PagoBorrador): string[] {
  return faltasPagos({ ...b, pagos: [pago] }).filter((x) => x !== 'los pagos tienen que sumar el precio');
}

/** Totales de presentación (DT-02): no se persisten ni crean atribuciones; «de la hipoteca» es el préstamo indicado. */
export function totalesPagos(b: BorradorCompra, prestamo: string | null): {
  precio: string; pagado: string; hipoteca: string | null; resto: string | null; falta: string;
} {
  const precio = Number.isNaN(D(b.precio)) ? 0 : D(b.precio);
  const pagado = b.pagos.reduce((s, x) => s + (Number.isNaN(D(x.importe)) ? 0 : D(x.importe)), 0);
  const hip = prestamo === null ? null : Number.isNaN(D(prestamo)) ? 0 : D(prestamo);
  return {
    precio: texto2(precio),
    pagado: texto2(pagado),
    hipoteca: hip === null ? null : texto2(hip),
    resto: hip === null ? null : texto2(Math.max(0, pagado - hip)),
    falta: texto2(precio - pagado),
  };
}

const PCT = /^\d{1,3}(?:[.,]\d{1,2})?$/;

/**
 * Préstamo por porcentaje del precio (AJ-UX2-07): round_half_up(precio_céntimos × pct / 100) en céntimos ENTEROS (BigInt),
 * pct con hasta 2 decimales. Devuelve el importe canónico «160000.00» o null si el precio o el porcentaje no valen.
 * Solo viaja el importe; el porcentaje no se guarda.
 */
export function importePorcentaje(precio: string, pct: string): string | null {
  const p = parsearImporte(precio);
  const q = pct.trim();
  if (!p.ok || !PCT.test(q)) return null;
  const [ent, dec = ''] = q.replace(',', '.').split('.');
  const pctCent = BigInt(ent) * 100n + BigInt((dec + '00').slice(0, 2));
  if (pctCent <= 0n || pctCent > 10000n) return null;
  const [pe, pd = ''] = p.valor.split('.');
  const precioCent = BigInt(pe) * 100n + BigInt((pd + '00').slice(0, 2));
  // round_half_up de precioCent × pctCent / 10000 (todo positivo): floor((2·n + d) / (2·d)).
  const cent = (2n * precioCent * pctCent + 10000n) / 20000n;
  const s = cent.toString().padStart(3, '0');
  return `${s.slice(0, -2)}.${s.slice(-2)}`;
}

/** DT-03: ayuda de pantalla «préstamo ≤ precio». No es invariante del sistema: el servidor no lo garantiza. */
export function prestamoSuperaPrecio(precio: string, prestamo: string): boolean {
  const a = D(precio);
  const h = D(prestamo);
  return !Number.isNaN(a) && !Number.isNaN(h) && h > a;
}
