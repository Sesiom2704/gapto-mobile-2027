// ============================================================
// GAPTO MOBILE 2027
// Fichero: prevision.ts
// Ruta: mobile/src/domain/prevision.ts
// Descripción: Confirmación de previsiones (F05-06 M5; F05 §59 F05-D044; láminas PREV v0.2 y HOME-01 v0.4). Lógica pura: importes de fila por naturaleza («~74,00 €» por pagar, «+2.100,00 €» cobro previsto en color neutro, transferencias sin signo), «Desconocido» y nunca 0 (D-PREV-08), línea de la fila (vencida, pago parcial, próximo, «Entre cuentas»), cobertura («Pagado 40,00 de 120,00 · queda 80,00») y desviación («10,00 € más de lo previsto», nunca un «queda» negativo, D-PREV-13), «Por pagar» / «Por cobrar» por separado (D-PREV-10), contador de la campana (número, nada o «!» si la lectura falla; HOME-01 I03/I05), «Se vinculará X €» (D-PREV-11), consecuencia del swipe (D-PREV-12) y el bloque `prevision` del registro, que exige una respuesta explícita a «¿Queda cubierta?» (D-PREV-04, P-PREV-02). Sin estado ni red.
// Versión: 0.1.0 (F05-06 M5 §B1)
// Versión: 0.2.0 (F05-06 M5 SWIPE; regla de Moisés del 2026-10-22): `planRapidoPrevision` decide si el swipe es una acción rápida de un solo gesto (gasto o ingreso abierto, esperado conocido, EUR, una sola cuenta prevista que hoy tiene la capacidad, sin realidad previa): registra el esperado en esa cuenta con fecha de hoy y `marcar_realizada = true`, por la misma composición que la hoja. Si falta algo, null y el gesto abre la hoja. `textoAvisoRapido`: «<Nombre> pagada / cobrada».
// Versión: 0.3.0 (F05-06 M5 SWIPE2; lámina SWIPE-01 v0.2): el aviso lleva el importe («Nómina cobrada · 2.100,00 €»). Izquierda «No hubo este mes»: `admiteNoHubo` (abierta y sin pagos enlazados ni realidad) y su aviso. `importeFormulario`: el importe con el que el gesto abre el formulario cuando hay dudas (lo que queda, o el esperado; nada si es desconocido).
// Versión: 0.4.0 (F05-06 M5-B; F04-D065, F05-D047): «Dar por cubierta» solo en una PARCIAL (`ofreceDarPorCubierta`), «Queda sin cubrir ±X €» con el pendiente derivado (`quedaSinCubrirTexto`; nunca se guarda), «Más» en las terminales (`ofreceMas`, para «Reabrir») y las sugerencias de motivo de las dos hojas.
// ============================================================

import type { BloquePrevisionWire, CuentaElegible, CuentaPago, DetallePrevision, FilaPrevision, ImportePorNaturaleza } from '../api/cliente';
import { diaMesAnioIso, diaMesIso } from './fechas';
import { formatearEur } from './importe';

export const TEXTO_DESCONOCIDO = 'Desconocido';
export const TEXTO_CUBRIR_RESTO = 'Para cubrirla, registra o enlaza el resto.';
export const TEXTO_NO_MUEVE = 'Es una previsión: no ha movido dinero.';
export const TEXTO_NO_SABEMOS = 'No sabemos si se guardó tu acción anterior. Este es el estado actual.';
export const TEXTO_FALLO_PENDIENTES = 'No se pudieron cargar los pendientes';
export const TEXTO_FALLO_PENDIENTES_DETALLE = 'El resto de Inicio sí se ha cargado. Puede que tengas algo pendiente.';
export const TEXTO_SOLO_ENLAZA = 'Solo se enlazan. El registro elegido no cambia. Si ha cambiado mientras tanto, te lo mostramos de nuevo antes de enlazar.';
export const TEXTO_SIN_DOBLE = 'La previsión no mueve dinero; el pago sí. En el mes cuentan los importes reales, no la previsión.';
/** M5-B «Dar por cubierta» y «Reabrir»: sugerencias rápidas del motivo (el texto sigue siendo editable). */
export const MOTIVOS_DAR_POR_CUBIERTA = ['La factura definitiva fue menor', 'Se pagó el resto por otra vía', 'El importe era una estimación'] as const;
export const MOTIVOS_REABRIR = ['La marqué por error', 'Sí hubo este mes', 'Falta registrar una parte'] as const;
export const TEXTO_DAR_POR_CUBIERTA = 'Deja de estar pendiente con lo ya registrado. No se registra nada nuevo ni se mueve dinero: la diferencia solo se muestra, no se guarda.';
export const TEXTO_REABRIR = 'Vuelve a estar pendiente. Lo ya registrado sigue enlazado; no se borra nada ni se mueve dinero.';
export const TEXTO_TRANSFERENCIA_NEUTRA = 'Es dinero que pasa entre tus cuentas: no es gasto ni ingreso y no cambia el Resultado del mes.';

/** «1.234,50» sin símbolo (texto de cobertura). */
export function numeroEur(decimal: string): string {
  return formatearEur(decimal).replace(' €', '');
}

/** Importe de una fila: «~74,00 €» (pago), «+2.100,00 €» (cobro, color neutro), «500,00 €» (entre cuentas). */
export function importeFila(f: Pick<FilaPrevision, 'tipo' | 'importe_esperado' | 'queda'>, usarQueda = false): string {
  const base = usarQueda && f.queda !== null ? f.queda : f.importe_esperado;
  if (base === null) return TEXTO_DESCONOCIDO;
  if (f.tipo === 'INGRESO') return `+${formatearEur(base)}`;
  if (f.tipo === 'TRANSFERENCIA') return formatearEur(base);
  return `~${formatearEur(base)}`;
}

/** Cobertura: «Pagado 40,00 de 120,00 · queda 80,00»; sin esperado, «Pagado 40,00»; sin realidad, null. */
export function coberturaTexto(f: Pick<FilaPrevision, 'tipo' | 'cubierto' | 'importe_esperado' | 'queda' | 'con_realidad'>): string | null {
  if (!f.con_realidad) return null;
  const verbo = f.tipo === 'INGRESO' ? 'Cobrado' : f.tipo === 'TRANSFERENCIA' ? 'Transferido' : 'Pagado';
  if (f.importe_esperado === null) return `${verbo} ${numeroEur(f.cubierto)}`;
  const base = `${verbo} ${numeroEur(f.cubierto)} de ${numeroEur(f.importe_esperado)}`;
  return f.queda !== null ? `${base} · queda ${numeroEur(f.queda)}` : base;
}

/** D-PREV-13: «10,00 € más de lo previsto»; nunca un «queda» negativo. */
export function desviacionTexto(f: Pick<FilaPrevision, 'desviacion'>): string | null {
  return f.desviacion === null ? null : `${formatearEur(f.desviacion)} más de lo previsto`;
}

/** Línea secundaria de una fila (Inicio, Pendientes y Próximos). */
export function lineaFila(f: FilaPrevision, enProximos = false): string {
  const fecha = f.fecha_hasta ?? f.fecha_desde;
  if (enProximos) {
    const base = fecha ? `Previsto ${diaMesAnioIso(fecha)}` : 'Previsto';
    return f.tipo === 'TRANSFERENCIA' ? `${base} · Entre cuentas` : f.tipo === 'INGRESO' ? `Cobro previsto · ${base.toLowerCase()}` : base;
  }
  const cuando = fecha ? (f.vencida ? `venció el ${diaMesIso(fecha)}` : `vence el ${diaMesIso(fecha)}`) : 'sin fecha';
  const cobertura = coberturaTexto(f);
  if (cobertura) return `${cobertura} · ${cuando}`;
  if (f.tipo === 'INGRESO') return `Cobro previsto · ${cuando}`;
  if (f.tipo === 'TRANSFERENCIA') return `Entre cuentas · ${cuando}`;
  const capital = cuando.charAt(0).toUpperCase() + cuando.slice(1);
  return f.vencida ? `${capital} · Falta confirmar` : capital;
}

/** Intervalo esperado: «1–5 oct 2026» o «5 oct 2026». */
export function intervaloTexto(f: Pick<FilaPrevision, 'fecha_desde' | 'fecha_hasta'>): string {
  const { fecha_desde: d, fecha_hasta: h } = f;
  if (!d && !h) return 'Sin fecha';
  if (!d || !h || d === h) return diaMesAnioIso((d ?? h) as string);
  const [ad, md] = d.split('-');
  const [ah, mh] = h.split('-');
  if (ad === ah && md === mh) return `${Number(d.split('-')[2])}–${diaMesAnioIso(h)}`;
  return `${diaMesIso(d)} – ${diaMesAnioIso(h)}`;
}

/** «Por pagar» / «Por cobrar» (D-PREV-10): nunca un total único; desconocido nunca es 0. */
export function textoNaturaleza(n: ImportePorNaturaleza, tipo: 'POR_PAGAR' | 'POR_COBRAR'): string {
  if (n.n === 0) return formatearEur('0.00');
  if (n.importe === null) return TEXTO_DESCONOCIDO;
  const base = tipo === 'POR_COBRAR' ? `+${formatearEur(n.importe)}` : `~${formatearEur(n.importe)}`;
  return n.desconocidos > 0 ? `${base} + ${n.desconocidos} sin importe` : base;
}

/** Campana de Inicio: nada sin pendientes, el número con ellos y «!» si la lectura falla (HOME-01 I03/I05). */
export function contadorCampana(lectura: { fase: 'CARGANDO' } | { fase: 'OK'; n: number } | { fase: 'ERROR' }): string | null {
  if (lectura.fase === 'ERROR') return '!';
  if (lectura.fase === 'CARGANDO' || lectura.n === 0) return null;
  return String(lectura.n);
}

/** D-PREV-11: lo que se vinculará es toda la porción libre del registro, aunque supere lo previsto. */
export function textoSeVinculara(porcion: string, f: Pick<FilaPrevision, 'tipo' | 'importe_esperado' | 'queda'>): { titulo: string; detalle: string | null } {
  const titulo = `Se vinculará ${formatearEur(porcion)} de este registro`;
  if (f.importe_esperado === null) return { titulo, detalle: 'Es todo lo que tiene libre.' };
  const supera = Number(porcion) > Number(f.importe_esperado);
  return { titulo, detalle: supera ? `Es todo lo que tiene libre, aunque supere los ${importeFila(f)} previstos.` : 'Es todo lo que tiene libre.' };
}

/** Consecuencia del registro sobre la previsión (D-PREV-05 / D-PREV-12). */
export function consecuencia(marcar: boolean): string {
  return marcar ? 'Quedará cubierta' : 'Seguirá pendiente';
}

/** Bloque `prevision` del registro: sin respuesta a «¿Queda cubierta?» no hay bloque (D-M5-04). */
export function bloquePrevision(p: Pick<DetallePrevision, 'id' | 'row_version'>, marcar: boolean | null): BloquePrevisionWire | null {
  if (marcar === null) return null;
  return { prevision_id: p.id, row_version: p.row_version, marcar_realizada: marcar };
}

/** Texto del swipe según el tipo. */
export function verboSwipe(tipo: string): string {
  return tipo === 'INGRESO' ? 'Cobrado' : 'Pagado';
}

/** Título de la pantalla del estado actual tras un rechazo de omitir (D-PREV-14). */
export function estadoLegible(estado: string, derivado: string | null): string {
  if (derivado === 'REQUIERE_REVISION') return 'Necesita revisión';
  if (derivado === 'REALIZADA_SIN_REALIDAD_ACTIVA') return 'Cubierta sin registro activo';
  return { ABIERTA: 'Pendiente', REALIZADA: 'Cubierta', OMITIDA: 'Omitida', CANCELADA: 'Cancelada' }[estado] ?? estado;
}

// ------------------------------------------------------------------ registro desde la previsión (D-PREV-03)
export interface FormularioDesdePrevision {
  importe: string | null; // canónico «81.37» o null si no es válido
  fecha: string;
  cuentaId: string | null; // gasto: «Pagado con»; ingreso: «Cobrado en»; transferencia: «Desde»
  cuentaDestinoId: string | null; // solo transferencia: «Hacia»
  presupuestable: boolean;
  conCategoria: boolean; // la de la previsión, o «Sin categoría» si el usuario la quita
  propuestaSelf100: boolean; // gasto: la cuenta es 100 % tuya en la fecha (financiación sellada)
  marcar: boolean | null; // «¿Queda cubierta?»: sin respuesta no se registra
}

export type RegistroCompuesto =
  | { ruta: 'GASTO'; payload: Record<string, unknown> }
  | { ruta: 'INGRESO'; payload: Record<string, unknown> }
  | { ruta: 'TRANSFERENCIA'; payload: Record<string, unknown> };

/** Lo que falta para «Revisar» (nunca un valor por defecto en «¿Queda cubierta?»). */
export function faltaRegistro(d: Pick<FilaPrevision, 'tipo'>, f: FormularioDesdePrevision): string[] {
  const falta: string[] = [];
  if (f.importe === null) falta.push('importe');
  if (f.cuentaId === null) falta.push(d.tipo === 'TRANSFERENCIA' ? 'cuenta de origen' : 'cuenta');
  if (d.tipo === 'TRANSFERENCIA' && f.cuentaDestinoId === null) falta.push('cuenta de destino');
  if (f.marcar === null) falta.push('¿queda cubierta?');
  return falta;
}

/** Payload del registro con el bloque `prevision`; null si falta algo. */
export function componerRegistro(d: FilaPrevision, f: FormularioDesdePrevision, intencionId: string): RegistroCompuesto | null {
  const bloque = bloquePrevision(d, f.marcar);
  if (!bloque || faltaRegistro(d, f).length > 0) return null;
  const importe = f.importe as string;
  if (d.tipo === 'TRANSFERENCIA') {
    return { ruta: 'TRANSFERENCIA', payload: { intencion_id: intencionId, importe, moneda: 'EUR', fecha_hecho: f.fecha, cuenta_origen_id: f.cuentaId, cuenta_destino_id: f.cuentaDestinoId, nota: null, prevision: bloque } };
  }
  const categoria = f.conCategoria && d.categoria ? { estado: 'CATEGORIA', categoria_id: d.categoria.id, magnitudes: [] } : { estado: 'SIN_CATEGORIA' };
  const comun: Record<string, unknown> = { intencion_id: intencionId, importe, moneda: 'EUR', fecha_hecho: f.fecha, cuenta_id: f.cuentaId, presupuestable: f.presupuestable, atribucion: 'SOLO_MIO', categoria, prevision: bloque };
  if (d.tercero) comun.tercero_id = d.tercero.id;
  if (d.tipo === 'INGRESO') return { ruta: 'INGRESO', payload: comun };
  const financiacion = f.propuestaSelf100
    ? { estado: 'PROPUESTA_ACEPTADA', actor: 'SELF', criterio: 'PARTICIPACION_CUENTA', porcentaje: '100', importe }
    : { estado: 'NO_DETERMINADA' };
  return { ruta: 'GASTO', payload: { ...comun, financiacion } };
}

/** «74.00» → «74,00» (texto editable del importe real propuesto). */
export function textoEditable(decimal: string | null): string {
  return decimal === null ? '' : decimal.replace('.', ',');
}

/** Swipe «Pagado» / «Cobrado» (D-PREV-08): gasto o ingreso, esperado conocido, EUR, cuenta prevista y sin pagos previos.
 *  Espejo de las acciones del detalle; la autoridad sigue siendo el servidor al registrar. */
export function admiteSwipe(f: FilaPrevision): boolean {
  if (f.estado !== 'ABIERTA' || f.moneda !== 'EUR' || f.con_realidad || f.importe_esperado === null) return false;
  if (f.tipo === 'GASTO') return f.cuenta_salida !== null;
  if (f.tipo === 'INGRESO') return f.cuenta_entrada !== null;
  return false;
}

/** Cuentas que hoy tienen la capacidad: pagar (gasto) y recibir dinero (ingreso). null = no se sabe (no se pudo leer). */
export interface CapacidadesHoy {
  pago: CuentaPago[] | null;
  ingreso: CuentaElegible[] | null;
}

/** Swipe como acción rápida (regla del 2026-10-22): solo si la acción es inequívoca; si falta algo, null (abre la hoja).
 *  Comprueba cada condición por sí misma, sin apoyarse en `admiteSwipe`. */
export function planRapidoPrevision(f: FilaPrevision, cap: CapacidadesHoy | null, hoy: string): FormularioDesdePrevision | null {
  if (!cap || f.estado !== 'ABIERTA' || f.moneda !== 'EUR' || f.con_realidad || f.pagos > 0) return null;
  if (f.importe_esperado === null) return null;
  if (f.tipo !== 'GASTO' && f.tipo !== 'INGRESO') return null;
  const cuenta = f.tipo === 'GASTO' ? f.cuenta_salida : f.cuenta_entrada;
  if (!cuenta) return null;
  const lista: { cuenta_id: string }[] | null = f.tipo === 'GASTO' ? cap.pago : cap.ingreso;
  if (!lista || !lista.some((x) => x.cuenta_id === cuenta.id)) return null;
  const self100 = f.tipo === 'GASTO' && !!cap.pago?.some((x) => x.cuenta_id === cuenta.id && x.propuesta_financiacion === 'SELF_100');
  return {
    importe: f.importe_esperado, fecha: hoy, cuentaId: cuenta.id, cuentaDestinoId: null, presupuestable: f.presupuestable,
    conCategoria: !!f.categoria, propuestaSelf100: self100, marcar: true,
  };
}

/** Texto del aviso de la acción rápida: «Nómina cobrada · 2.100,00 €», «Electricidad pagada · 74,00 €». */
/** «Queda sin cubrir ±X €» (M5-B): el pendiente derivado con su signo; negativo = registrado de más. */
export function quedaSinCubrirTexto(d: Pick<DetallePrevision, 'pendiente'>): string {
  if (d.pendiente === null) return TEXTO_DESCONOCIDO;
  const n = Number(d.pendiente);
  if (n === 0) return formatearEur('0.00');
  const abs = d.pendiente.replace(/^[-+]/, '');
  return `${n < 0 ? '−' : '+'}${formatearEur(abs)}`;
}

/** «Dar por cubierta» solo en una PARCIAL: abierta, sin estado derivado y con realidad (contrato M5-B §5). */
export function ofreceDarPorCubierta(d: Pick<DetallePrevision, 'estado' | 'estado_derivado' | 'con_realidad'>): boolean {
  return d.estado === 'ABIERTA' && d.estado_derivado === null && d.con_realidad;
}

/** «Más» del detalle (Reabrir): en las terminales, con la acción atenuada y su motivo cuando no se puede. */
export function ofreceMas(d: Pick<DetallePrevision, 'estado'>): boolean {
  return d.estado !== 'ABIERTA';
}

export function textoAvisoRapido(f: Pick<FilaPrevision, 'concepto' | 'tipo' | 'importe_esperado'>): string {
  const base = `${f.concepto} ${f.tipo === 'INGRESO' ? 'cobrada' : 'pagada'}`;
  return f.importe_esperado === null ? base : `${base} · ${formatearEur(f.importe_esperado)}`;
}

/** Izquierda «No hubo este mes» (omitir): solo una previsión abierta sin pagos enlazados ni realidad. */
export function admiteNoHubo(f: Pick<FilaPrevision, 'estado' | 'pagos' | 'con_realidad'>): boolean {
  return f.estado === 'ABIERTA' && f.pagos === 0 && !f.con_realidad;
}

/** Aviso de «No hubo»: «Alquiler · no hubo este mes». */
export function textoAvisoNoHubo(f: Pick<FilaPrevision, 'concepto'>): string {
  return `${f.concepto} · no hubo este mes`;
}

/** Importe con el que el gesto abre el formulario cuando hay dudas: lo que queda, el esperado o nada. */
export function importeFormulario(f: Pick<FilaPrevision, 'queda' | 'importe_esperado'>): string | null {
  const v = f.queda ?? f.importe_esperado;
  return v === null ? null : textoEditable(v);
}
