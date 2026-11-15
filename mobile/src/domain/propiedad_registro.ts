// ============================================================
// GAPTO MOBILE 2027
// Fichero: propiedad_registro.ts
// Ruta: mobile/src/domain/propiedad_registro.ts
// Descripción: CAT-VIV (T2-F06, bloque 3) · lógica pura del bloque «Propiedad» de «Registrar gasto» y de «Registrar desde la previsión» (mandato CAT-VIV §2.4–§2.5; OBL-VIV-01; lámina SET-CAT/REG-CAT v1.0 R01–R06):
//   - con una categoría «Asociada a vivienda» en un GASTO (ámbito GASTO o AMBOS), elegir propiedad es OBLIGATORIO; sin marca, el formulario no cambia (`exigePropiedad`; la marca no se hereda: cuenta la de la categoría elegida);
//   - el reparto se propone según la titularidad de la propiedad EN LA FECHA DEL GASTO (B3, propuesta-gasto), visible y marcado, con «No lo sé»; nunca 100 % mío por defecto;
//   - clase «Gasto corriente» (por defecto) o «Reparación»; nunca «Mejora» desde el registro (Q-CV-04); la clase no se persiste;
//   - «¿Quién pagó?» y la deuda de PAG (`quien_pago.ts`, sin reimplementarlo), sin «Desde una cuenta compartida»: con una vivienda la cuenta compartida aún no se admite (Q-PAG-03);
//   - wire del bloque `propiedad` de VS-01: { propiedad_id, clase, atribucion, pagos, saldos, posiciones_confirmadas }.
// Versión: 0.1.0 (F06 T2-F06 CAT-VIV N1 (L-04, lámina SET-CAT/REG-CAT v1.0))
// ============================================================

import type { AtribucionB3, PropuestaGasto } from '../api/patrimonio_b3';
import type { CategoriaNodo } from './categoria';
import { EleccionReparto, hayPropuesta, ParteEfectiva, partesEfectivas, repartirImporte, TEXTO_SIN_TITULARIDAD } from './gasto_propiedad';
import { formatearEur, parsearImporte } from './importe';
import {
  ajustarDeudas,
  DeudaElegida,
  EleccionPago,
  faltasPago,
  necesitaCuenta,
  opcionesPago,
  pagoInicial,
  PagoWire,
  pagosWire,
  PosicionWire,
  posicionesConfirmadas,
  propuestas,
  saldos,
  SaldoWire,
  textoPosicion,
} from './quien_pago';

export type ClaseRegistro = 'GASTO_CORRIENTE' | 'REPARACION';

export interface SeleccionPropiedad {
  propiedadId: string;
  nombre: string;
  /** Propuesta leída para la fecha del gasto (null = cargando). */
  propuesta: PropuestaGasto | null;
  reparto: EleccionReparto;
  repartoTocado: boolean;
  pago: EleccionPago;
  deudas: Record<string, DeudaElegida>;
  deudasTocadas: boolean;
  clase: ClaseRegistro;
}

export interface BloquePropiedadWire {
  propiedad_id: string;
  clase: ClaseRegistro;
  atribucion: AtribucionB3;
  pagos: PagoWire[];
  saldos: SaldoWire[];
  posiciones_confirmadas: PosicionWire[];
}

export const TEXTO_EXIGE_PROPIEDAD = 'Esta categoría está asociada a una vivienda: elige la propiedad.';
export const TEXTO_FALTA_PROPIEDAD = 'la propiedad';
export const TEXTO_CLASE_TITULO = '¿Qué tipo de gasto es?';
export const TEXTO_GASTO_CORRIENTE = 'Cuenta como gasto del mes. No suma al coste de la vivienda (las reformas se registran desde la ficha).';
export const TEXTO_SOLO_TUS_CUENTAS = 'Solo tus cuentas. Con una vivienda, la cuenta compartida aún no se admite.';
export const TEXTO_NO_LO_SE_PROPIEDAD = 'No lo sé · tu parte quedará «sin indicar»';
export const TEXTO_NO_SUMA_COSTE =
  'No suma al coste de la vivienda ni a «Invertido en viviendas este mes»: solo las obras que suben el valor (reformas, desde la ficha) son inversión.';
export const TEXTO_PREVISION_SIN_PROPIEDAD =
  'La previsión se creó sin propiedad. Para registrar el gasto, elige de qué vivienda es; la previsión no se modifica hasta que se registre.';
export const TEXTO_RETIRADO_VIVIENDA = 'Con una categoría de vivienda el reparto lo da la propiedad: se quita «Mío, pero me lo reembolsan».';
export const TEXTO_DE_OTROS = 'Esta propiedad no es tuya en esa fecha: no puedes registrar gastos en ella.';
export const NOMBRE_CLASE_REGISTRO: Record<ClaseRegistro, string> = { GASTO_CORRIENTE: 'Gasto corriente', REPARACION: 'Reparación' };
/** R07 (OBL-VIV-01.6): aviso de lectura de un gasto corregido a una categoría marcada, sin acción (D-CV-01). */
export const TEXTO_AVISO_VIVIENDA = 'Categoría asociada a vivienda, sin propiedad';
export const TEXTO_AVISO_VIVIENDA_DETALLE = 'Este gasto se registró antes. Cambiar la categoría no lo asocia a ninguna propiedad ni cambia su reparto.';

/** Rechazos del bloque `propiedad` en lenguaje llano (lo demás, con el mensaje del servidor). */
export const MOTIVO_RECHAZO_PROPIEDAD: Record<string, string> = {
  CATEGORIA_EXIGE_PROPIEDAD: 'Esta categoría está asociada a una vivienda: elige la propiedad.',
  OPERACION_NO_PERMITIDA_EN_ESTADO: TEXTO_DE_OTROS,
  PROPIEDAD_NO_DISPONIBLE: 'Esta propiedad ya no está disponible.',
  ATRIBUCION_PROPUESTA_DESFASADA: 'La titularidad ha cambiado: revisa el reparto.',
  TITULARIDAD_NO_DISPONIBLE_EN_FECHA: TEXTO_SIN_TITULARIDAD,
  PAGO_DESDE_CUENTA_COMPARTIDA: 'Con una vivienda, paga desde una cuenta solo tuya.',
};

/** La categoría elegida exige propiedad: solo en gastos (Q-CV-11) y por la marca de ESA categoría (Q-CV-03). */
export const exigePropiedad = (tipo: 'GASTO' | 'INGRESO', nodo: Pick<CategoriaNodo, 'asociada_vivienda'> | undefined | null): boolean =>
  tipo === 'GASTO' && nodo?.asociada_vivienda === true;

export function seleccionInicial(propiedadId: string, nombre: string): SeleccionPropiedad {
  return { propiedadId, nombre, propuesta: null, reparto: null, repartoTocado: false, pago: pagoInicial(), deudas: {}, deudasTocadas: false, clase: 'GASTO_CORRIENTE' };
}

/** Nueva propuesta (fecha, propiedad o cuenta): lo que el usuario no tocó se vuelve a proponer. */
export function conPropuesta(s: SeleccionPropiedad, prop: PropuestaGasto): SeleccionPropiedad {
  const reparto = s.repartoTocado ? s.reparto : hayPropuesta(prop) ? { modo: 'TITULARIDAD' as const } : null;
  // Sin cotitulares en la fecha solo cabe «Yo, todo» (no se pregunta); con cotitulares, nunca hay valor por defecto (D-PAG-1).
  const sinCotitulares = !prop.partes.some((x) => !x.yo);
  const antesSinCotitulares = s.propuesta !== null && !s.propuesta.partes.some((x) => !x.yo);
  const pago = sinCotitulares ? { ...pagoInicial(), modo: 'YO_TODO' as const } : antesSinCotitulares ? pagoInicial() : s.pago;
  return { ...s, propuesta: prop, reparto, pago };
}

export const partesDe = (s: SeleccionPropiedad): ParteEfectiva[] => partesEfectivas(s.reparto, s.propuesta, s.propuesta?.partes ?? []);
export const cotitularesDe = (s: SeleccionPropiedad) => (s.propuesta?.partes ?? []).filter((x) => !x.yo).map((x) => ({ actor_id: x.actor_id, nombre: x.nombre }));
/** DE_OTROS (M-8): hay titularidad en la fecha y ninguna parte es mía. */
export const esDeOtros = (s: SeleccionPropiedad) => hayPropuesta(s.propuesta) && !s.propuesta!.partes.some((x) => x.yo);

/** Opciones de «¿Quién pagó?» de PAG que muestra la lámina R03: «Yo, todo», «Cada uno su parte» y «<cotitular>, todo». */
export const opcionesPagoVivienda = (s: SeleccionPropiedad) => opcionesPago(cotitularesDe(s)).filter((o) => o.modo !== 'COMPARTIDA' && o.modo !== 'MIXTO');

/** Deudas propuestas, conservando lo que el usuario tocó (L-08: preseleccionadas, desmarcables). */
export function conDeudas(s: SeleccionPropiedad, importe: string): SeleccionPropiedad {
  return { ...s, deudas: ajustarDeudas(s.deudas, propuestas(s.pago, importe, partesDe(s)), s.deudasTocadas) };
}

export const pagaYo = (s: SeleccionPropiedad | null) => !!s && (s.pago.modo === null || necesitaCuenta(s.pago));

/** Lo que falta del bloque (el registro se para con «Falta: …»). `cuentaPropia`: la cuenta elegida si es solo tuya. */
export function faltasPropiedad(s: SeleccionPropiedad | null, importe: string, cuentaPropia: string | null): string[] {
  if (!s) return [TEXTO_FALTA_PROPIEDAD];
  if (s.propuesta === null) return ['esperar la propuesta de reparto'];
  if (esDeOtros(s)) return ['una propiedad tuya'];
  if (s.reparto === null) return ['de quién es el gasto'];
  if (s.reparto.modo === 'TITULARIDAD' && !hayPropuesta(s.propuesta)) return [TEXTO_SIN_TITULARIDAD];
  const n = (s.propuesta.partes ?? []).length;
  return faltasPago(s.pago, importe, partesDe(s), s.reparto.modo === 'NO_LO_SE', cuentaPropia, false, s.deudas, n);
}

function atribucionWire(s: SeleccionPropiedad, fecha: string): AtribucionB3 {
  const e = s.reparto;
  if (e === null || e.modo === 'NO_LO_SE') return { modo: 'NO_LO_SE' };
  if (e.modo === 'MANUAL') {
    return { modo: 'MANUAL', partes: Object.entries(e.partes).filter(([, v]) => v.trim() !== '').map(([actor_id, v]) => ({ actor_id, porcentaje: v.replace(',', '.') })) };
  }
  return {
    modo: 'SEGUN_TITULARIDAD_ACEPTADA',
    propuesta_vista: { criterio: 'TITULARIDAD_EN_FECHA_HECHO', fecha_referencia: fecha, partes: (s.propuesta?.partes ?? []).map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje })) },
  };
}

/** Bloque `propiedad` de VS-01. La confirmación visible (`posiciones_confirmadas`) son exactamente los saldos mostrados. */
export function bloqueWire(s: SeleccionPropiedad, importe: string, cuentaId: string | null, fecha: string): BloquePropiedadWire {
  const p = parsearImporte(importe);
  const total = p.ok ? p.valor : importe;
  const partes = partesDe(s);
  const sw = saldos(s.pago, total, partes, s.deudas);
  return {
    propiedad_id: s.propiedadId,
    clase: s.clase,
    atribucion: atribucionWire(s, fecha),
    pagos: pagosWire(s.pago, total, partes, cuentaId),
    saldos: sw,
    posiciones_confirmadas: posicionesConfirmadas(sw),
  };
}

/** «Tu parte: 60,00 € · Lucía: 60,00 €» (lo que se atribuirá). */
export function textoPartes(s: SeleccionPropiedad, importe: string): string | null {
  const partes = partesDe(s);
  if (partes.length === 0) return null;
  const rep = repartirImporte(importe, partes);
  if (Object.keys(rep).length === 0) return null;
  const orden = [...partes.filter((x) => x.yo), ...partes.filter((x) => !x.yo)];
  return orden.map((x) => `${x.yo ? 'Tu parte' : x.nombre ?? 'Otra persona'}: ${formatearEur(rep[x.actor_id] ?? '0.00')}`).join(' · ');
}

/** Mi parte del gasto (lo que cuenta en el mes) o null si el reparto queda sin indicar. */
export function miParte(s: SeleccionPropiedad, importe: string): string | null {
  const partes = partesDe(s);
  const yo = partes.find((x) => x.yo);
  if (!yo) return null;
  return repartirImporte(importe, partes)[yo.actor_id] ?? null;
}

/** Resumen visible antes de registrar (R03): «Tu gasto del mes: 60,00 € · Lucía te debe 60,00 €». */
export function resumenConfirmacion(s: SeleccionPropiedad, importe: string): string | null {
  const parte = miParte(s, importe);
  const sw = saldos(s.pago, importe, partesDe(s), s.deudas).filter((x) => x.sentido !== 'NADA');
  const nombre = (id: string) => s.propuesta?.partes.find((x) => x.actor_id === id)?.nombre ?? 'Otra persona';
  const piezas = [parte ? `Tu gasto del mes: ${formatearEur(parte)}` : 'Tu parte quedará sin indicar'];
  for (const x of sw) piezas.push(textoPosicion(x.sentido as 'ME_DEBE' | 'LE_DEBO', nombre(x.actor_id), x.importe!));
  return piezas.join(' · ');
}

/** Texto del reparto en el éxito (R05). */
export function textoRepartoExito(s: SeleccionPropiedad): string {
  if (s.reparto?.modo === 'TITULARIDAD' && s.propuesta) {
    const partes = [...s.propuesta.partes.filter((x) => x.yo), ...s.propuesta.partes.filter((x) => !x.yo)]
      .map((x) => `${x.yo ? 'tú' : x.nombre ?? 'otra persona'} ${Number(x.porcentaje).toLocaleString('es-ES', { maximumFractionDigits: 2 })} %`);
    return `Según titularidad: ${partes.join(', ')}`;
  }
  return 'Sin indicar';
}
