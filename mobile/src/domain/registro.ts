// ============================================================
// GAPTO MOBILE 2027
// Fichero: registro.ts
// Ruta: mobile/src/domain/registro.ts
// Descripción: Lógica pura del registro por tipo de F05-04 (J2 §2.2/§2.3/§2.7; F05 §46.3 A1/A4/A8; lámina REG-DYN / SET-TH / SET-CTX v0.1 T01, T02, X01, N01, N02). (1) Hoja «¿Qué quieres registrar?» con los tres tipos, sin preselección. (2) Cambio de tipo ANTES del primer envío: conserva importe y fecha y QUITA, con aviso, lo que no encaja en el nuevo tipo (categoría de otro ámbito, cuenta sin la capacidad del nuevo tipo y, hacia «Entre cuentas», todo lo que no tiene). (3) Nota canónica: omitida, vacía o solo espacios → null (A8). (4) Título calculado, nunca persistido: nota o concepto histórico > «Tercero · Categoría» > categoría > tercero > «Tipo · importe»; nunca vacío ni «null».
// Versión: 0.1.0 (F05-03/F05-04 J2 §2)
// Versión: 0.2.0 (F05-03/F05-04 J2 §2.4): plantilla en el registro: aplica categoría, tercero y contexto propuestos SOLO a los campos no tocados (la categoría, si existe y admite el tipo), avisos R04 de lo que no aplica, «Quitar» que retira lo que puso; cambio de tipo Gasto ↔ Ingreso sobre el borrador.
// ============================================================

import { Arbol, CategoriaNodo, elegible, magnitudesPedibles, rutaTexto } from './categoria';
import { formatearEur } from './importe';
import type { Borrador, PlantillaAplicada, SeleccionCategoria } from './intencion';
import { conservarMagnitudes } from './magnitud';

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

// ------------------------------------------------------------------ plantilla en el registro (F05-04 J2 §2.4; §45.3; lámina REG-PLT R01–R04)
/** Selección categorial de un nodo del árbol (misma forma que la elección en el selector). */
export function seleccionDeNodo(a: Arbol, n: CategoriaNodo): SeleccionCategoria {
  return { estado: 'CATEGORIA', id: n.id, nombre: n.nombre, ruta: rutaTexto(a, n.id), icon_key: n.icon_key, magnitudes: magnitudesPedibles(n) };
}

/** ¿La categoría vigente la puso la plantilla y el usuario no la ha cambiado? */
export function categoriaDePlantilla(b: Pick<Borrador, 'categoria' | 'categoriaPlantillaId' | 'plantilla'>): boolean {
  return !!b.plantilla && b.categoria.estado === 'CATEGORIA' && b.categoria.id === (b.categoriaPlantillaId ?? null);
}

export const TEXTO_AVISO_CAMPO: Record<string, string> = {
  categoria: 'La categoría de esta plantilla ya no está disponible. Elige otra; puedes cambiar la plantilla en Ajustes.',
  cuenta: 'La cuenta de esta plantilla ya no está disponible. Elige la cuenta; puedes cambiar la plantilla en Ajustes.',
  tercero: 'El tercero de esta plantilla ya no está disponible. Puedes elegir otro o cambiar la plantilla en Ajustes.',
  contexto: 'El contexto de esta plantilla ya no está disponible. Puedes elegir otro o cambiar la plantilla en Ajustes.',
};

/** Avisos de los campos que la plantilla no puede aplicar hoy (dato del servidor; texto R04). */
export function avisosPlantilla(avisos: { campo: string }[]): string[] {
  return avisos.map((a) => TEXTO_AVISO_CAMPO[a.campo]).filter((x): x is string => !!x);
}

/**
 * Aplica los campos categoría, tercero y contexto que propone la PLANTILLA, SOLO en los campos que el usuario no
 * ha tocado (A7: lo explícito gana). La categoría solo si existe en el árbol y admite el tipo; si no, aviso. Cuenta y
 * presupuesto van por la propuesta (aplicarPropuesta) con origen PLANTILLA.
 */
export function aplicarCamposPlantilla(
  b: Borrador,
  plantilla: PlantillaAplicada,
  campos: { categoria: { valor: string; origen: { capa: string } } | null; tercero: { valor: string; origen: { capa: string } } | null; contexto: { valor: string; origen: { capa: string } } | null },
  ctx: { arbol: Arbol | null; tipo: 'GASTO' | 'INGRESO'; tercero: (id: string) => string | null; contexto: (id: string) => string | null },
): { b: Borrador; avisos: string[] } {
  const avisos: string[] = [];
  let x: Borrador = { ...b, plantilla };
  const cat = campos.categoria;
  if (cat && cat.origen.capa === 'PLANTILLA' && (b.categoria.estado === 'PENDIENTE' || categoriaDePlantilla(b))) {
    const n = ctx.arbol?.porId.get(cat.valor);
    if (ctx.arbol && n && elegible(n, ctx.tipo)) {
      const sel = seleccionDeNodo(ctx.arbol, n);
      const nuevas = sel.estado === 'CATEGORIA' ? sel.magnitudes : [];
      x = { ...x, categoria: sel, magnitudesTexto: conservarMagnitudes(b.magnitudesTexto, nuevas), categoriaPlantillaId: n.id };
    } else avisos.push(TEXTO_AVISO_CAMPO.categoria);
  }
  const ter = campos.tercero;
  if (ter && ter.origen.capa === 'PLANTILLA' && b.terceroOrigen !== 'USUARIO') {
    const nombre = ctx.tercero(ter.valor);
    if (nombre) x = { ...x, terceroId: ter.valor, terceroNombre: nombre, terceroOrigen: 'INFERIDO' };
    else avisos.push(TEXTO_AVISO_CAMPO.tercero);
  }
  const con = campos.contexto;
  if (con && con.origen.capa === 'PLANTILLA' && b.contextoOrigen !== 'USUARIO') {
    const nombre = ctx.contexto(con.valor);
    if (nombre) x = { ...x, contextoId: con.valor, contextoNombre: nombre, contextoOrigen: 'INFERIDO' };
    else avisos.push(TEXTO_AVISO_CAMPO.contexto);
  }
  return { b: x, avisos };
}

/** «Quitar» la plantilla: se retiran los valores que puso (los tocados por el usuario se conservan). */
export function quitarPlantilla(b: Borrador): Borrador {
  let x: Borrador = { ...b, plantilla: null, categoriaPlantillaId: null };
  if (categoriaDePlantilla(b)) x = { ...x, categoria: { estado: 'PENDIENTE' }, magnitudesTexto: {}, desconocidas: [] };
  if (b.terceroOrigen === 'INFERIDO') x = { ...x, terceroId: null, terceroNombre: null, terceroOrigen: 'PENDIENTE' };
  if (b.contextoOrigen === 'INFERIDO') x = { ...x, contextoId: null, contextoNombre: null, contextoOrigen: 'PENDIENTE' };
  return x;
}

/** Cambio de tipo GASTO ↔ INGRESO antes del primer envío (T02): conserva importe y fecha y quita lo que no encaja. */
export function borradorTrasCambioDeTipo(b: Borrador, cuentaAdmitida: boolean, categoriaAdmitida: boolean): Borrador {
  let x: Borrador = { ...b, plantilla: null, categoriaPlantillaId: null };
  // La categoría se conserva solo si su ámbito admite el nuevo tipo (A12; lo decide el llamador con el árbol).
  if (b.categoria.estado === 'CATEGORIA' && !categoriaAdmitida) x = { ...x, categoria: { estado: 'PENDIENTE' }, magnitudesTexto: {}, desconocidas: [] };
  if (!cuentaAdmitida) x = { ...x, cuentaId: null, cuentaOrigen: 'PENDIENTE', cuentaPropuesta: null, propuesta: null, propuestaRechazada: false };
  if (x.presupuestableOrigen !== 'USUARIO') x = { ...x, presupuestable: null, presupuestableOrigen: 'PENDIENTE', presupuestablePropuesta: null };
  return x;
}
