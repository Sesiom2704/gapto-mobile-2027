// ============================================================
// GAPTO MOBILE 2027
// Fichero: registro.ts
// Ruta: mobile/src/domain/registro.ts
// Descripción: Lógica pura del registro por tipo de F05-04 (J2 §2.2/§2.3/§2.7; F05 §46.3 A1/A4/A8; lámina REG-DYN / SET-TH / SET-CTX v0.1 T01, T02, X01, N01, N02). (1) Hoja «¿Qué quieres registrar?» con los tres tipos, sin preselección. (2) Cambio de tipo ANTES del primer envío: conserva importe y fecha y QUITA, con aviso, lo que no encaja en el nuevo tipo (categoría de otro ámbito, cuenta sin la capacidad del nuevo tipo y, hacia «Entre cuentas», todo lo que no tiene). (3) Nota canónica: omitida, vacía o solo espacios → null (A8). (4) Título calculado, nunca persistido: nota o concepto histórico > «Tercero · Categoría» > categoría > tercero > «Tipo · importe»; nunca vacío ni «null».
// Versión: 0.1.0 (F05-03/F05-04 J2 §2)
// ============================================================

import { formatearEur } from './importe';

export type TipoRegistro = 'GASTO' | 'INGRESO' | 'TRANSFERENCIA';

/** Lámina T01: filas de la hoja de tipos, en su orden y sin preselección. */
export const TIPOS_REGISTRO: { tipo: TipoRegistro; titulo: string; subtitulo: string }[] = [
  { tipo: 'GASTO', titulo: 'Gasto', subtitulo: 'Compras, facturas, comidas...' },
  { tipo: 'INGRESO', titulo: 'Ingreso', subtitulo: 'Nómina, alquiler cobrado, venta...' },
  { tipo: 'TRANSFERENCIA', titulo: 'Entre cuentas', subtitulo: 'Mover dinero entre tus cuentas. No es gasto ni ingreso' },
];
export const NOTA_DEVOLUCION = '¿Te han devuelto dinero de una compra? Regístralo desde el gasto original.';
export const TEXTO_ENTRE_CUENTAS = 'No es un gasto ni un ingreso: tu dinero cambia de cuenta. ¿Hubo comisión? Regístrala aparte como gasto.';

export const TITULO_TAREA: Record<TipoRegistro, string> = { GASTO: 'Nuevo gasto', INGRESO: 'Nuevo ingreso', TRANSFERENCIA: 'Entre cuentas' };
export const NOMBRE_TIPO: Record<TipoRegistro, string> = { GASTO: 'Gasto', INGRESO: 'Ingreso', TRANSFERENCIA: 'Entre cuentas' };
const NOMBRE_TIPO_MIN: Record<TipoRegistro, string> = { GASTO: 'gasto', INGRESO: 'ingreso', TRANSFERENCIA: 'movimiento entre cuentas' };

/** Ámbitos de categoría admitidos por tipo (A12; matriz C02). */
export function ambitoAdmitido(tipo: TipoRegistro, ambito: 'GASTO' | 'INGRESO' | 'AMBOS'): boolean {
  if (tipo === 'TRANSFERENCIA') return false;
  return ambito === 'AMBOS' || ambito === tipo;
}

/** Ausencia canónica de la nota (A8): null si no hay texto real. */
export function notaCanonica(texto: string | null | undefined): string | null {
  const t = (texto ?? '').trim();
  return t === '' ? null : t;
}

export interface Quitado {
  campo: 'categoria' | 'cuenta' | 'tercero' | 'contexto' | 'presupuestable' | 'atribucion' | 'magnitudes';
  nombre?: string;
}

/** Lo que conserva y lo que quita un cambio de tipo (lámina T02). */
export function cambioDeTipo(
  desde: TipoRegistro,
  hacia: TipoRegistro,
  actual: { categoria?: { nombre: string; ambito: 'GASTO' | 'INGRESO' | 'AMBOS' } | null; cuenta?: { nombre: string; admitida: boolean } | null;
    tercero?: string | null; contexto?: string | null; presupuestable?: boolean | null; soloMio?: boolean },
): Quitado[] {
  const q: Quitado[] = [];
  if (desde === hacia) return q;
  if (actual.categoria && !ambitoAdmitido(hacia, actual.categoria.ambito)) q.push({ campo: 'categoria', nombre: actual.categoria.nombre });
  if (actual.cuenta && !actual.cuenta.admitida) q.push({ campo: 'cuenta', nombre: actual.cuenta.nombre });
  if (hacia === 'TRANSFERENCIA') {
    if (actual.tercero) q.push({ campo: 'tercero', nombre: actual.tercero });
    if (actual.contexto) q.push({ campo: 'contexto', nombre: actual.contexto });
    if (actual.presupuestable !== null && actual.presupuestable !== undefined) q.push({ campo: 'presupuestable' });
    if (actual.soloMio) q.push({ campo: 'atribucion' });
  }
  return q;
}

const MOTIVO_QUITADO: Record<TipoRegistro, { categoria: string; cuenta: string }> = {
  GASTO: { categoria: 'no admite gastos', cuenta: 'no se puede usar para pagar' },
  INGRESO: { categoria: 'no admite ingresos', cuenta: 'no se puede usar para cobrar' },
  TRANSFERENCIA: { categoria: 'no aplica entre cuentas', cuenta: 'no se puede usar para mover dinero' },
};

/** «Has cambiado de Gasto a Ingreso. Se mantienen el importe y la fecha. Se han quitado …» (T02). */
export function avisoCambioDeTipo(desde: TipoRegistro, hacia: TipoRegistro, quitados: Quitado[]): string {
  const base = `Has cambiado de ${NOMBRE_TIPO[desde]} a ${NOMBRE_TIPO[hacia]}. Se mantienen el importe y la fecha.`;
  if (quitados.length === 0) return base;
  const partes = quitados.map((x) => {
    if (x.campo === 'categoria') return `la categoría «${x.nombre}» (${MOTIVO_QUITADO[hacia].categoria})`;
    if (x.campo === 'cuenta') return `la cuenta «${x.nombre}» (${MOTIVO_QUITADO[hacia].cuenta})`;
    if (x.campo === 'tercero') return `el tercero «${x.nombre}»`;
    if (x.campo === 'contexto') return `el contexto «${x.nombre}»`;
    if (x.campo === 'presupuestable') return 'si cuenta para el presupuesto';
    if (x.campo === 'atribucion') return 'de quién es';
    return 'los datos de la categoría';
  });
  const lista = partes.length === 1 ? partes[0] : `${partes.slice(0, -1).join(', ')} y ${partes[partes.length - 1]}`;
  return `${base} Se han quitado ${lista}.`;
}

/** Título de presentación (A8): nunca se persiste ni sale vacío. */
export function tituloRegistro(r: {
  tipo: TipoRegistro;
  importe: string;
  nota?: string | null;
  concepto?: string | null;
  tercero?: string | null;
  categoria?: string | null;
}): string {
  const texto = notaCanonica(r.nota) ?? notaCanonica(r.concepto);
  if (texto) return texto;
  const tercero = notaCanonica(r.tercero);
  const categoria = notaCanonica(r.categoria);
  if (tercero && categoria) return `${tercero} · ${categoria}`;
  if (categoria) return categoria;
  if (tercero) return tercero;
  return `${NOMBRE_TIPO[r.tipo]} · ${formatearEur(r.importe)}`;
}

/** Título de la pantalla de éxito («Gasto registrado», «Ingreso registrado», «Movimiento registrado»). */
export function tituloExito(tipo: TipoRegistro): string {
  return tipo === 'TRANSFERENCIA' ? 'Movimiento registrado' : `${NOMBRE_TIPO[tipo]} registrado`;
}

export function nombreTipoMinuscula(tipo: TipoRegistro): string {
  return NOMBRE_TIPO_MIN[tipo];
}
