// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos.ts
// Ruta: mobile/src/domain/contratos.ts
// Descripción: Lógica pura de F06-02/03 · Contratos de alquiler, servicios y terceros, SIN renta (contrato N1 v1.1; lámina CON v0.8 validada): textos literales de la lámina, borrador del asistente de 5 pasos (qué, fechas, personas, revisión, servicios), validaciones previas de cada paso con las MISMAS reglas que el servidor (D25: principal solo en PROPIETARIO, GESTOR e INQUILINO; el usuario no es inquilino ni agencia ni administrador; partes para firmar; AGENCIA y ADMINISTRADOR nunca cuentan como parte), solape simétrico y bloqueante para firmados con ocupación hasta el FIN REAL (decisiones 3 y 6; el fin previsto no libera; un borrador no cuenta), payload de C-CON-01 (nunca `renta` ni `fianza`), situación/ocupación para A1, tratamientos de servicio (M-9), «uso en Gapto» de V-bis con homónimos y la propuesta de rol de E3 (sin propuesta para agencia ni administrador), y la traducción de TODOS los códigos de error del contrato a texto. El servidor sigue siendo la autoridad: esta capa solo evita enviar lo que se sabe que se rechaza.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// Versión: 0.1.1 (Bloque 3, paso 9): filasSelector no exige `enabled` (la respuesta del servidor no lo trae; selector vacío en CON-B3c).
// ============================================================

import type {
  ClausulaWire, ContratoDetalle, FilaContrato, ModoTratamiento, OcupacionHabitacion, PayloadAltaContrato, PersonaWire, RolParticipante, RolTercero,
  ServicioPropiedad, SolapadoDetalle, TerceroParaContrato, TipoClausula, TipoContrato, TipoServicio, TratamientoWire, UsoTercero,
} from '../api/contratos';
import type { NaturalezaTercero } from '../api/cliente';
import { diaMesAnioIso, diaMesIso } from './fechas';
import { esFechaIso } from './intencion';

// ------------------------------------------------------------------ textos de la lámina CON v0.8
export const TEXTO_SIN_RENTA_LISTA = 'Sin importes: la renta todavía no existe en la app (llega con la parte de cobros).';
export const TEXTO_RENTA_FIANZA_FILA = 'Se añadirán con la parte de cobros';
export const TEXTO_RENTA_FIANZA_TITULO = 'Renta y fianza';
export const TEXTO_RENTA_REGISTRADA = 'Renta registrada · se gestiona en la parte de cobros';
export const TEXTO_FIN_VENCIDO = 'Termina o prorroga';
export const TEXTO_QUE_ALQUILAS =
  'Se ofrecen las habitaciones de la ficha. Si en esas fechas ya está alquilada (esa habitación o la vivienda completa), solo podrás guardarlo como borrador; lo verás en el paso 2.';
export const TEXTO_SIN_CONTRATOS = 'Si alquilas esta propiedad o una parte (por habitaciones), crea aquí cada contrato.';
export const TEXTO_YA_ALQUILADA_TITULO = 'Ya está alquilada en esas fechas';
export const TEXTO_YA_ALQUILADA_AVISO =
  'No se puede guardar como firmado. Puedes guardarlo como borrador y firmarlo cuando registres el fin real de ese contrato, o revisar las fechas.';
export const TEXTO_BORRADOR_AYUDA =
  'Un borrador se completa o se cancela; no se borra. No ocupa la habitación. Solo se puede firmar si en esas fechas no hay otro contrato firmado.';
export const TEXTO_PERSONAS_AYUDA =
  'Hace falta un principal solo en arrendadores e inquilinos. Para firmar hacen falta un arrendador (o gestor) y un inquilino; la agencia o el administrador no cuentan para eso. «Tú» no aparece entre los inquilinos.';
export const TEXTO_AGENCIA_AYUDA = 'Queda como persona del contrato. No sustituye al arrendador ni al inquilino.';
export const TEXTO_HOMONIMOS_AYUDA =
  'Si hay dos con el mismo nombre, se muestra al lado si es persona o empresa y su uso en Gapto. Nada viene elegido.';
export const TEXTO_DUPLICADO_ASISTENTE = 'Si es uno de ellos, úsalo. Uno desactivado hay que reactivarlo antes. Si es otra persona, créala igualmente.';
export const TEXTO_REVISION_AYUDA = 'Aquí se guarda lo que dice el contrato. Aplicar la revisión a la renta llegará con la parte de cobros.';
export const TEXTO_SERVICIOS_AYUDA = 'Cómo se trata cada servicio en este contrato. No crea cobros: solo lo deja anotado.';
export const TEXTO_RESUMEN_SIN_RENTA = 'La renta y la fianza las añadirás desde el contrato cuando llegue la parte de cobros.';
export const TEXTO_UNA_OPERACION = 'Se guarda todo en una sola operación: o se guarda el contrato entero o no se guarda nada.';
export const TEXTO_TERMINACION_BLOQUEADA_TITULO = 'No se puede terminar todavía.';
export const TEXTO_RENTA_PENDIENTE =
  'Este contrato tiene una renta registrada. Para terminarlo hay que cerrar también su renta, y eso llegará con la parte de cobros. De momento no se puede terminar.';
export const TEXTO_TERMINACION_BLOQUEADA_DETALLE =
  'Este contrato tiene una renta registrada (viene de la versión anterior de la app). Para terminarlo hay que cerrar también su renta, y eso llegará con la parte de cobros.';
export const TEXTO_MIENTRAS_TANTO = 'Mientras tanto puedes prorrogarlo, cambiar personas y servicios.';
export const TEXTO_PRORROGA_AYUDA = 'Cambia la fecha prevista y queda registrado el cambio.';
export const TEXTO_TERMINAR_NADA_SE_BORRA = 'No se borra nada: lo registrado se conserva.';
export const TEXTO_SERVICIO_BAJA_REGLA =
  'Este servicio tiene un pago previsto registrado. Para darlo de baja hay que cerrar ese pago previsto, y eso llegará con la parte de cobros.';
export const TEXTO_INQUILINO_NO_YO = 'Tú no puedes ser inquilino de tu propio contrato.';
export const TEXTO_SERVICIO_NO_CREA_COBROS = 'Cómo se trata cada servicio en este contrato. No crea cobros: solo lo deja anotado.';
export const TEXTO_TRATAMIENTO_AYUDA =
  'Con «% fijo» se pide inquilino y porcentaje (mayor que 0). Con «en cada factura» se guarda el inquilino y el porcentaje se decidirá en cada gasto, cuando llegue esa parte.';
export const TEXTO_COMPANIA_AYUDA =
  'Si cambias de compañía no hace falta tocar nada aquí: cada pago lleva su compañía. Dar de baja pone fecha de fin y no borra pagos.';
export const TEXTO_ROLES_FIJOS = 'Los roles se pueden añadir, no quitar.';
export const TEXTO_ROL_NO_SE_QUITA = 'Revisa antes de guardar. En esta versión un rol añadido no se puede quitar.';
export const TEXTO_CLASIFICACION_AYUDA =
  'Tu forma de agruparlos. Una clasificación asignada no se puede quitar a una persona; si la desactivas en la lista de clasificaciones, deja de usarse para todos.';
export const TEXTO_NADA_MARCADO = 'Las opciones marcadas solo ilustran; en la app nada viene marcado de antemano.';
export const TEXTO_ACTUAL_SIN_HABITACIONES = 'La ficha de esta propiedad no indica cuántas habitaciones tiene: indícalo en la ficha para alquilar por habitaciones.';

// ------------------------------------------------------------------ catálogos
export const NOMBRE_TIPO: Record<TipoContrato, string> = { VIVIENDA_COMPLETA: 'Vivienda completa', HABITACION: 'Habitación', OTRO: 'Otro' };
export const TIPOS: TipoContrato[] = ['VIVIENDA_COMPLETA', 'HABITACION', 'OTRO'];
export const NOMBRE_ROL_PARTICIPANTE: Record<RolParticipante, string> = {
  PROPIETARIO: 'Titular', INQUILINO: 'Inquilino', AVALISTA: 'Avalista', GESTOR: 'Gestor', AGENCIA: 'Agencia', ADMINISTRADOR: 'Administrador',
};
export const NOMBRE_ROL_MIN: Record<RolParticipante, string> = {
  PROPIETARIO: 'propietario', INQUILINO: 'inquilino', AVALISTA: 'avalista', GESTOR: 'gestor', AGENCIA: 'agencia', ADMINISTRADOR: 'administrador',
};
/** Roles que exigen un principal cuando hay personas (D25). AVALISTA, AGENCIA y ADMINISTRADOR no lo exigen (como mucho uno). */
export const ROLES_CON_PRINCIPAL: RolParticipante[] = ['PROPIETARIO', 'GESTOR', 'INQUILINO'];
export const ROLES_ARRENDADOR: RolParticipante[] = ['PROPIETARIO', 'GESTOR'];
export const ROLES_INTERMEDIARIO: RolParticipante[] = ['AGENCIA', 'ADMINISTRADOR'];

/** Roles de TERCERO en el orden de la lámina E2 (catálogo completo, Q-CON-12). */
export const ROLES_TERCERO: RolTercero[] = [
  'INQUILINO', 'AVALISTA', 'GESTOR', 'COMERCIO', 'SUMINISTRADOR', 'ASEGURADORA', 'EMPLEADOR', 'ENTIDAD_FINANCIERA', 'FINANCIADOR', 'OBLIGADO_REEMBOLSO',
];
export const NOMBRE_ROL_TERCERO: Record<RolTercero, string> = {
  COMERCIO: 'Comercio', ENTIDAD_FINANCIERA: 'Entidad financiera', FINANCIADOR: 'Financiador', INQUILINO: 'Inquilino', AVALISTA: 'Avalista', EMPLEADOR: 'Empleador',
  SUMINISTRADOR: 'Suministrador', OBLIGADO_REEMBOLSO: 'Obligado a reembolsar', GESTOR: 'Gestor', ASEGURADORA: 'Aseguradora',
};

export const NOMBRE_TIPO_SERVICIO: Record<TipoServicio, string> = {
  LUZ: 'Luz', AGUA: 'Agua', GAS: 'Gas', INTERNET: 'Internet', LIMPIEZA: 'Limpieza', COMUNIDAD: 'Comunidad', SEGURO: 'Seguro', OTRO: 'Otro',
};
export const TIPOS_SERVICIO: TipoServicio[] = ['LUZ', 'AGUA', 'GAS', 'INTERNET', 'LIMPIEZA', 'COMUNIDAD', 'SEGURO', 'OTRO'];
export const FAMILIA_TIPO_SERVICIO: Record<TipoServicio, string> = {
  LUZ: 'Suministro', AGUA: 'Suministro', GAS: 'Suministro', INTERNET: 'Telecomunicaciones', LIMPIEZA: 'Limpieza', COMUNIDAD: 'Comunidad', SEGURO: 'Seguro', OTRO: 'Otro',
};

export const OPCIONES_CLAUSULA: { tipo: TipoClausula | 'NO_SE'; titulo: string; detalle: string }[] = [
  { tipo: 'IPC', titulo: 'Por IPC', detalle: 'Índice INE' },
  { tipo: 'PORCENTAJE_FIJO', titulo: 'Porcentaje fijo', detalle: 'Por ejemplo, 2 % al año' },
  { tipo: 'MANUAL', titulo: 'Otro índice o manual', detalle: '' },
  { tipo: 'NINGUNA', titulo: 'Sin revisión', detalle: 'Sabemos que no se revisa' },
  { tipo: 'NO_SE', titulo: 'No lo sé', detalle: 'Queda sin registrar' },
];

export const OPCIONES_TRATAMIENTO: { modo: Exclude<ModoTratamiento, 'SIN_INDICAR'>; titulo: string; detalle: string }[] = [
  { modo: 'INCLUIDO', titulo: 'Incluida en la renta', detalle: 'No se cobra aparte' },
  { modo: 'REPERCUTIDO_FIJO', titulo: 'Repercutida con un % fijo', detalle: 'Siempre el mismo porcentaje' },
  { modo: 'POR_FACTURA', titulo: 'Se reparte en cada factura', detalle: 'El % se decide en cada gasto' },
  { modo: 'NO_REPERCUTIDO', titulo: 'La pagas tú', detalle: 'Sin repercutir' },
];

// ------------------------------------------------------------------ fechas y nombres
const norm = (t: string) => t.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/\s+/g, ' ').trim();
/** Normalización C06 de `candidatos` (sin acentos, minúsculas, espacios simples): clave de homónimos. */
export const normalizarNombre = norm;

/** «2027-03-01» → «mar 2027». */
export const desdeMesAnio = (iso: string) => diaMesAnioIso(iso).split(' ').slice(1).join(' ');

export function textoOcupacionHabitacion(o: { estado: 'OCUPADA' | 'PROXIMA' | 'LIBRE'; hasta: string | null; desde: string | null }): string {
  if (o.estado === 'OCUPADA') return o.hasta ? `Ocupada hasta ${diaMesAnioIso(o.hasta)}` : 'Ocupada';
  if (o.estado === 'PROXIMA') return o.desde ? `Contrato desde ${diaMesIso(o.desde)}` : 'Contrato próximo';
  return 'Libre';
}

/** «3 ocupadas · 1 próxima · 1 libre» (A1, «Hoy»). */
export function resumenOcupacion(oc: OcupacionHabitacion[]): string {
  const n = (e: OcupacionHabitacion['estado']) => oc.filter((x) => x.estado === e).length;
  const o = n('OCUPADA');
  const p = n('PROXIMA');
  const l = n('LIBRE');
  return [`${o} ${o === 1 ? 'ocupada' : 'ocupadas'}`, `${p} ${p === 1 ? 'próxima' : 'próximas'}`, `${l} ${l === 1 ? 'libre' : 'libres'}`].join(' · ');
}

export function etiquetaUnidad(c: { tipo: TipoContrato; habitacion: number | null }, propiedadNombre?: string): string {
  const base = c.tipo === 'HABITACION' && c.habitacion != null ? `Habitación ${c.habitacion}` : NOMBRE_TIPO[c.tipo];
  return propiedadNombre ? `${base} · ${propiedadNombre}` : base;
}

/** Segunda línea de la fila de A1: unidad · inquilino · fechas según la situación (derivada por el servidor). */
export function detalleFilaContrato(f: FilaContrato): string {
  const unidad = f.tipo === 'HABITACION' && f.habitacion != null ? `Habitación ${f.habitacion}` : NOMBRE_TIPO[f.tipo];
  const quien = f.inquilino_principal;
  let fecha: string;
  if (f.situacion === 'BORRADOR') fecha = 'sin firmar';
  else if (f.situacion === 'PROXIMO') fecha = `empieza ${diaMesIso(f.fecha_inicio)}`;
  else if (f.situacion === 'FINALIZADO') fecha = f.fecha_fin_real ? `terminó ${diaMesAnioIso(f.fecha_fin_real)}` : 'terminado';
  else if (f.situacion === 'CANCELADO') fecha = 'cancelado';
  else if (f.fin_previsto_vencido && f.fecha_fin_prevista) fecha = `fin previsto ${diaMesAnioIso(f.fecha_fin_prevista)}`;
  else if (f.fecha_fin_prevista) fecha = `hasta ${diaMesAnioIso(f.fecha_fin_prevista)}`;
  else fecha = `desde ${diaMesAnioIso(f.fecha_inicio)}`;
  return [unidad, quien, fecha].filter(Boolean).join(' · ');
}

export interface GruposContratos {
  vigentes: FilaContrato[];
  proximos: FilaContrato[];
  borradores: FilaContrato[];
  finalizados: FilaContrato[];
}
export function agruparContratos(filas: FilaContrato[]): GruposContratos {
  const por = (s: FilaContrato['situacion']) => filas.filter((f) => f.situacion === s);
  return { vigentes: por('VIGENTE'), proximos: por('PROXIMO'), borradores: por('BORRADOR'), finalizados: por('FINALIZADO') };
}

export const textoSituacion = (c: { estado_documental: string; situacion: string }): string =>
  c.situacion === 'BORRADOR' ? 'Borrador' : c.situacion === 'CANCELADO' ? 'Cancelado' : c.situacion === 'PROXIMO' ? 'Firmado · próximo' : c.situacion === 'FINALIZADO' ? 'Firmado · finalizado' : 'Firmado · vigente';

// ------------------------------------------------------------------ solape (decisiones 3 y 6; INV-ALQ-08/09)
export interface NuevoIntervalo { tipo: TipoContrato; habitacion: number | null; inicio: string }

/**
 * Contratos FORMALIZADOS de la propiedad con los que coincidiría un FORMALIZADO nuevo (§I paso 6): ocupación
 * [inicio, fin_real ?? ∞] inclusiva; el fin previsto NO libera; el borrador y el cancelado no cuentan.
 * HABITACION n choca con la misma n y con VIVIENDA_COMPLETA; VIVIENDA_COMPLETA choca con todos; OTRO no choca con nada.
 */
export function calcularSolapes(existentes: FilaContrato[], n: NuevoIntervalo, excluirId?: string): FilaContrato[] {
  if (n.tipo === 'OTRO' || !esFechaIso(n.inicio)) return [];
  return existentes.filter((e) => {
    if (e.contrato_id === excluirId || e.estado_documental !== 'FORMALIZADO' || e.tipo === 'OTRO') return false;
    if (e.fecha_fin_real !== null && e.fecha_fin_real < n.inicio) return false;
    if (n.tipo === 'VIVIENDA_COMPLETA') return true;
    return e.tipo === 'VIVIENDA_COMPLETA' || (e.tipo === 'HABITACION' && e.habitacion === n.habitacion);
  });
}

export function textoSolape(s: Pick<FilaContrato, 'nombre' | 'tipo' | 'habitacion' | 'fecha_inicio' | 'fecha_fin_real'>): string {
  const unidad = s.tipo === 'HABITACION' && s.habitacion != null ? `Habitación ${s.habitacion}` : NOMBRE_TIPO[s.tipo];
  return `${s.nombre} · ${unidad} · ${diaMesAnioIso(s.fecha_inicio)} → ${s.fecha_fin_real ? diaMesAnioIso(s.fecha_fin_real) : 'sin fin real'}`;
}

export function textoSolapeDetalle(d: SolapadoDetalle): string {
  const unidad = d.tipo === 'HABITACION' && d.habitacion != null ? `Habitación ${d.habitacion}` : NOMBRE_TIPO[d.tipo];
  return `${d.nombre} · ${unidad} · ${diaMesAnioIso(d.desde)} → ${d.hasta ? diaMesAnioIso(d.hasta) : 'sin fin real'}`;
}

/** Lista de contratos solapados que el servidor devuelve en el 409 (detalle.solapados), si viene bien formada. */
export function solapadosDeDetalle(detalle?: Record<string, unknown>): SolapadoDetalle[] {
  const l = detalle?.solapados;
  if (!Array.isArray(l)) return [];
  return l.filter((x): x is SolapadoDetalle => !!x && typeof x === 'object' && typeof (x as SolapadoDetalle).id === 'string' && typeof (x as SolapadoDetalle).desde === 'string');
}

/** B2b: «La habitación 2 desde el 1 nov 2026 coincide con este contrato firmado de la vivienda completa:». */
export function textoCoincide(n: NuevoIntervalo, s: Pick<FilaContrato, 'tipo'>): string {
  const mia = n.tipo === 'HABITACION' && n.habitacion != null ? `La habitación ${n.habitacion}` : n.tipo === 'VIVIENDA_COMPLETA' ? 'La vivienda completa' : 'Este contrato';
  const suya = s.tipo === 'VIVIENDA_COMPLETA' ? 'de la vivienda completa' : s.tipo === 'HABITACION' ? 'de una habitación' : '';
  return `${mia} desde el ${diaMesAnioIso(n.inicio)} coincide con este contrato firmado ${suya}`.trim() + ':';
}

// ------------------------------------------------------------------ borrador del asistente
export interface PersonaBorrador {
  clave: string;
  /** `null` = «Tú» (YO). */
  terceroId: string | null;
  nombre: string;
  rol: RolParticipante;
  principal: boolean;
}

export interface ClausulaBorrador {
  /** `null` = sin elegir (nada viene marcado); 'NO_SE' = «No lo sé» (sin fila). */
  eleccion: TipoClausula | 'NO_SE' | null;
  porcentaje: string;
  periodicidad: string;
  primeraRevision: string;
}

export interface TratamientoBorrador {
  modo: ModoTratamiento | null;
  porcentaje: string;
}

export interface BorradorContrato {
  propiedadId: string | null;
  propiedadNombre: string;
  tipo: TipoContrato | null;
  habitacion: number | null;
  fechaInicio: string;
  fechaFinPrevista: string;
  estado: 'FORMALIZADO' | 'BORRADOR' | null;
  personas: PersonaBorrador[];
  clausula: ClausulaBorrador;
  /** Por servicio_id. */
  servicios: Record<string, TratamientoBorrador>;
  nombre: string;
  nombreEditado: boolean;
}

export function borradorContrato(propiedadId: string | null = null, propiedadNombre = ''): BorradorContrato {
  return {
    propiedadId, propiedadNombre, tipo: null, habitacion: null, fechaInicio: '', fechaFinPrevista: '', estado: null, personas: [],
    clausula: { eleccion: null, porcentaje: '', periodicidad: '', primeraRevision: '' }, servicios: {}, nombre: '', nombreEditado: false,
  };
}

export type PasoContrato = 'QUE' | 'FECHAS' | 'PERSONAS' | 'REVISION' | 'SERVICIOS' | 'RESUMEN';
export const PASOS_CONTRATO: PasoContrato[] = ['QUE', 'FECHAS', 'PERSONAS', 'REVISION', 'SERVICIOS', 'RESUMEN'];
export const NOMBRE_PASO: Record<PasoContrato, string> = { QUE: 'Qué', FECHAS: 'Fechas', PERSONAS: 'Personas', REVISION: 'Revisión', SERVICIOS: 'Servicios', RESUMEN: 'Resumen' };

/** Porcentaje en (0, 100], hasta 4 decimales; «50», «50,5» → «50», «50.5»; si no, `null`. */
export function parsearPorcentaje(t: string): string | null {
  const x = t.trim().replace('%', '').trim().replace(',', '.');
  if (!/^\d{1,3}(\.\d{1,4})?$/.test(x)) return null;
  const v = Number(x);
  return v > 0 && v <= 100 ? x : null;
}

export function faltasQue(b: BorradorContrato, habitacionesFicha: number | null): string[] {
  const f: string[] = [];
  if (!b.propiedadId) f.push('Elige la propiedad.');
  if (!b.tipo) f.push('Elige qué se alquila.');
  if (b.tipo === 'HABITACION') {
    if (habitacionesFicha === null || habitacionesFicha === 0) f.push(TEXTO_ACTUAL_SIN_HABITACIONES);
    else if (b.habitacion === null) f.push('Elige la habitación.');
    else if (b.habitacion < 1 || b.habitacion > habitacionesFicha) f.push('Esa habitación no está en la ficha de la propiedad.');
  }
  return f;
}

export function faltasFechas(b: BorradorContrato): string[] {
  const f: string[] = [];
  if (!esFechaIso(b.fechaInicio)) f.push('La fecha de inicio se pide siempre, también en un borrador.');
  if (b.fechaFinPrevista !== '') {
    if (!esFechaIso(b.fechaFinPrevista)) f.push('El fin previsto no es una fecha válida.');
    else if (esFechaIso(b.fechaInicio) && b.fechaFinPrevista < b.fechaInicio) f.push('El fin previsto no puede ser anterior al inicio.');
  }
  if (!b.estado) f.push('Indica si está firmado o aún no.');
  return f;
}

export function faltasPersonas(b: BorradorContrato): string[] {
  const f: string[] = [];
  const vistos = new Set<string>();
  for (const p of b.personas) {
    if (p.terceroId === null && p.rol === 'INQUILINO') f.push(TEXTO_INQUILINO_NO_YO);
    if (p.terceroId === null && ROLES_INTERMEDIARIO.includes(p.rol)) f.push('La agencia o el administrador son solo terceros: «Tú» no puede serlo.');
    const k = `${p.terceroId ?? 'YO'}|${p.rol}`;
    if (vistos.has(k)) f.push(`${p.nombre} está repetido como ${NOMBRE_ROL_MIN[p.rol]}.`);
    vistos.add(k);
  }
  for (const rol of Object.keys(NOMBRE_ROL_PARTICIPANTE) as RolParticipante[]) {
    const del = b.personas.filter((p) => p.rol === rol);
    if (del.filter((p) => p.principal).length > 1) f.push(`Solo puede haber un principal entre los ${NOMBRE_ROL_MIN[rol]}s.`);
    if (ROLES_CON_PRINCIPAL.includes(rol) && del.length > 0 && !del.some((p) => p.principal)) f.push(`Marca un principal entre los ${NOMBRE_ROL_MIN[rol]}s.`);
  }
  if (b.estado === 'FORMALIZADO') {
    if (!b.personas.some((p) => ROLES_ARRENDADOR.includes(p.rol))) f.push('Para firmar hace falta un arrendador (o gestor).');
    if (!b.personas.some((p) => p.rol === 'INQUILINO')) f.push('Para firmar hace falta un inquilino.');
  }
  return [...new Set(f)];
}

export function faltasClausula(c: ClausulaBorrador): string[] {
  const f: string[] = [];
  if (c.eleccion === null) f.push('Elige cómo se revisa la renta, o «No lo sé».');
  if (c.eleccion === 'PORCENTAJE_FIJO' && parsearPorcentaje(c.porcentaje) === null) f.push('Indica el porcentaje fijo (mayor que 0).');
  if (c.eleccion === 'IPC' || c.eleccion === 'MANUAL') {
    if (c.periodicidad.trim() !== '' && !/^[1-9]\d{0,2}$/.test(c.periodicidad.trim())) f.push('La periodicidad son meses, en número entero.');
    if (c.primeraRevision !== '' && !esFechaIso(c.primeraRevision)) f.push('La primera revisión no es una fecha válida.');
  }
  return f;
}

export function inquilinoPrincipal(b: Pick<BorradorContrato, 'personas'>): PersonaBorrador | null {
  return b.personas.find((p) => p.rol === 'INQUILINO' && p.principal && p.terceroId !== null) ?? null;
}

export function faltasServicios(b: BorradorContrato): string[] {
  const f: string[] = [];
  for (const [id, t] of Object.entries(b.servicios)) {
    if (t.modo === 'REPERCUTIDO_FIJO' && parsearPorcentaje(t.porcentaje) === null) f.push(`El % fijo de un servicio debe ser mayor que 0 (${id}).`);
    if ((t.modo === 'REPERCUTIDO_FIJO' || t.modo === 'POR_FACTURA') && !inquilinoPrincipal(b)) f.push('Para repercutir un servicio hace falta un inquilino principal (tercero).');
  }
  return f;
}

export function faltasPaso(paso: PasoContrato, b: BorradorContrato, habitacionesFicha: number | null): string[] {
  switch (paso) {
    case 'QUE': return faltasQue(b, habitacionesFicha);
    case 'FECHAS': return faltasFechas(b);
    case 'PERSONAS': return faltasPersonas(b);
    case 'REVISION': return faltasClausula(b.clausula);
    case 'SERVICIOS': return faltasServicios(b);
    default: return [];
  }
}

export function faltasContrato(b: BorradorContrato, habitacionesFicha: number | null): string[] {
  return [...faltasQue(b, habitacionesFicha), ...faltasFechas(b), ...faltasPersonas(b), ...faltasClausula(b.clausula), ...faltasServicios(b)];
}

export function clausulaWire(c: ClausulaBorrador): ClausulaWire | null {
  if (c.eleccion === null || c.eleccion === 'NO_SE') return null; // «No lo sé»: sin fila (nunca NINGUNA)
  if (c.eleccion === 'NINGUNA') return { tipo: 'NINGUNA' };
  if (c.eleccion === 'PORCENTAJE_FIJO') return { tipo: 'PORCENTAJE_FIJO', porcentaje_fijo: parsearPorcentaje(c.porcentaje) };
  const w: ClausulaWire = { tipo: c.eleccion };
  if (c.eleccion === 'IPC') w.indice_referencia = 'IPC INE';
  w.periodicidad_meses = c.periodicidad.trim() === '' ? null : Number(c.periodicidad.trim());
  w.fecha_primera_revision = c.primeraRevision === '' ? null : c.primeraRevision;
  return w;
}

export function tratamientosWire(b: BorradorContrato): TratamientoWire[] {
  const inq = inquilinoPrincipal(b);
  return Object.entries(b.servicios)
    .filter(([, t]) => t.modo !== null && t.modo !== 'SIN_INDICAR')
    .map(([servicio_id, t]) => {
      const modo = t.modo as ModoTratamiento;
      const w: TratamientoWire = { servicio_id, modo, desde: b.fechaInicio };
      if (modo === 'REPERCUTIDO_FIJO' || modo === 'POR_FACTURA') w.actor = inq ? { tercero_id: inq.terceroId as string } : null;
      if (modo === 'REPERCUTIDO_FIJO') w.porcentaje = parsearPorcentaje(t.porcentaje);
      return w;
    });
}

export const personasWire = (b: Pick<BorradorContrato, 'personas'>): PersonaWire[] =>
  b.personas.map((p) => ({ actor: p.terceroId === null ? 'YO' : { tercero_id: p.terceroId }, rol: p.rol, principal: p.principal }));

/** Cuerpo de C-CON-01. NUNCA lleva `renta` ni `fianza` (R-E-01). */
export function payloadAltaContrato(intencionId: string, b: BorradorContrato): PayloadAltaContrato {
  const p: PayloadAltaContrato = {
    intencion_id: intencionId,
    propiedad_id: b.propiedadId as string,
    tipo: b.tipo as TipoContrato,
    nombre: b.nombre.trim(),
    fecha_inicio: b.fechaInicio,
    estado: b.estado as 'FORMALIZADO' | 'BORRADOR',
    personas: personasWire(b),
    servicios: tratamientosWire(b),
  };
  if (b.tipo === 'HABITACION') p.habitacion = b.habitacion;
  if (b.fechaFinPrevista !== '') p.fecha_fin_prevista = b.fechaFinPrevista;
  const c = clausulaWire(b.clausula);
  if (c) p.clausula_revision = c;
  return p;
}

// ------------------------------------------------------------------ resumen B6
export function textoPersonasResumen(personas: PersonaBorrador[], rol: RolParticipante | RolParticipante[]): string {
  const roles = Array.isArray(rol) ? rol : [rol];
  const nombres = personas.filter((p) => roles.includes(p.rol)).map((p) => (p.terceroId === null ? 'Tú' : p.nombre));
  if (nombres.length <= 1) return nombres.join('');
  return `${nombres.slice(0, -1).join(', ')} y ${nombres[nombres.length - 1]}`;
}

export function textoClausulaResumen(c: ClausulaBorrador): string {
  switch (c.eleccion) {
    case 'IPC': return c.primeraRevision ? `IPC anual · ${diaMesAnioIso(c.primeraRevision)}` : 'IPC · fecha sin indicar';
    case 'PORCENTAJE_FIJO': return `${c.porcentaje.trim()} % fijo`;
    case 'NINGUNA': return 'Sin revisión';
    case 'NO_SE': return 'Sin registrar';
    case null: return 'Sin elegir';
    default: return 'Otro índice o manual';
  }
}

export function textoTratamiento(modo: ModoTratamiento | null, porcentaje: string | null): string {
  switch (modo) {
    case 'INCLUIDO': return 'Incluido en la renta';
    case 'REPERCUTIDO_FIJO': return `Repercutido ${porcentaje ?? ''} %`.replace('  ', ' ');
    case 'POR_FACTURA': return 'Reparto en cada factura';
    case 'NO_REPERCUTIDO': return 'La pagas tú';
    default: return 'Sin indicar';
  }
}

/** A2 «Servicios»: «Internet incluido · luz: reparto en cada factura». */
export function resumenServiciosContrato(c: Pick<ContratoDetalle, 'servicios'>): string {
  return c.servicios
    .filter((s) => s.vigente_hasta === null && s.modo !== 'SIN_INDICAR')
    .map((s) => {
      const n = s.servicio_nombre;
      if (s.modo === 'INCLUIDO') return `${n} incluido`;
      if (s.modo === 'POR_FACTURA') return `${n.toLowerCase()}: reparto en cada factura`;
      if (s.modo === 'REPERCUTIDO_FIJO') return `${n.toLowerCase()}: ${s.porcentaje ?? ''} % fijo`;
      return `${n.toLowerCase()}: la pagas tú`;
    })
    .join(' · ');
}

export function textoClausulaDetalle(c: ContratoDetalle['clausula']): string {
  if (!c) return 'Sin registrar';
  if (c.tipo === 'IPC') return 'Revisión anual por IPC';
  if (c.tipo === 'PORCENTAJE_FIJO') return `Revisión con ${c.porcentaje_fijo ?? ''} % fijo`;
  if (c.tipo === 'NINGUNA') return 'Sin revisión';
  return 'Revisión por otro índice o manual';
}

export function textoRolPersona(p: { rol: RolParticipante; principal: boolean }): string {
  if (p.rol === 'PROPIETARIO' || p.rol === 'GESTOR') return p.rol === 'GESTOR' ? 'Gestor' : 'Arrendador';
  return p.principal && ROLES_CON_PRINCIPAL.includes(p.rol) ? `${NOMBRE_ROL_PARTICIPANTE[p.rol]} · principal` : NOMBRE_ROL_PARTICIPANTE[p.rol];
}

// ------------------------------------------------------------------ V-bis · uso en Gapto y homónimos
export const NOMBRE_NATURALEZA: Record<NaturalezaTercero, string> = { PERSONA: 'Persona', EMPRESA: 'Empresa', ORGANISMO: 'Organismo', OTRO: 'Otro' };
export const textoNaturaleza = (n: NaturalezaTercero | null): string => (n ? NOMBRE_NATURALEZA[n] : 'Naturaleza sin indicar');

export function textoUso(u: UsoTercero): string {
  if (u.tipo === 'CONTRATO') return `${NOMBRE_ROL_MIN[u.rol]} en ${u.contrato_nombre}`;
  if (u.tipo === 'MOVIMIENTO') return `último movimiento ${diaMesIso(u.fecha)}`;
  return 'sin uso';
}

/** Segunda línea de una fila de homónimos: «Persona · inquilino en 26-HAB1-CR». */
export const detalleHomonimo = (t: TerceroParaContrato): string => `${textoNaturaleza(t.naturaleza)} · ${textoUso(t.uso)}`;

export type TerceroDelSelector = TerceroParaContrato & { enabled: boolean };

export interface FilaSelector {
  /** Activo por construcción: `enabled` se fija a true al filtrar (el servidor no lo manda). */
  tercero: TerceroDelSelector;
  /** Hay otro activo con el mismo nombre normalizado: se muestra naturaleza y uso. */
  homonimo: boolean;
  /** Sigue idéntica a otra (mismo nombre, naturaleza y uso): no se elige directamente, se abre su ficha (B3c). */
  identica: boolean;
}

/** V-bis: solo ACTIVOS; los homónimos muestran naturaleza y uso; las filas aún idénticas exigen pasar por la ficha. Nada viene elegido. */
export function filasSelector(lista: TerceroParaContrato[]): FilaSelector[] {
  const activos: TerceroDelSelector[] = lista.filter((t) => t.enabled !== false).map((t) => ({ ...t, enabled: true })); // el servidor solo manda activos y sin `enabled`
  const porNombre = new Map<string, TerceroDelSelector[]>();
  for (const t of activos) porNombre.set(norm(t.nombre), [...(porNombre.get(norm(t.nombre)) ?? []), t]);
  return activos.map((t) => {
    const grupo = porNombre.get(norm(t.nombre)) ?? [];
    const homonimo = grupo.length > 1;
    const identica = homonimo && grupo.some((o) => o.id !== t.id && o.naturaleza === t.naturaleza && textoUso(o.uso) === textoUso(t.uso));
    return { tercero: t, homonimo, identica };
  });
}

// ------------------------------------------------------------------ E3 · propuesta de rol (sin propuesta para agencia ni administrador)
const ROL_TERCERO_DE: Partial<Record<RolParticipante, RolTercero>> = { INQUILINO: 'INQUILINO', AVALISTA: 'AVALISTA', GESTOR: 'GESTOR' };

/** ¿Este papel del contrato puede dar lugar a una propuesta de rol de tercero? (no AGENCIA, ADMINISTRADOR ni PROPIETARIO). */
export const proponeRol = (rol: RolParticipante): boolean => ROL_TERCERO_DE[rol] !== undefined;

/** Rol de tercero que se PROPONE al añadir una persona al contrato; `null` si no hay propuesta (AGENCIA, ADMINISTRADOR, PROPIETARIO) o ya lo tiene. */
export function rolPropuesto(rol: RolParticipante, rolesDelTercero: RolTercero[]): RolTercero | null {
  const r = ROL_TERCERO_DE[rol];
  return r && !rolesDelTercero.includes(r) ? r : null;
}
export const textoSinRol = (nombre: string, rol: RolTercero): string => `${nombre} no tiene el rol «${NOMBRE_ROL_TERCERO[rol]}»`;
export const textoProponerRol = (rol: RolTercero): string =>
  `La añades como ${NOMBRE_ROL_TERCERO[rol].toLowerCase()} en un contrato. ¿Quieres marcarle también el rol para encontrarla antes? Un rol añadido no se puede quitar.`;

// ------------------------------------------------------------------ servicios (D1..D5)
export const detalleFilaServicio = (s: Pick<ServicioPropiedad, 'tipo_servicio' | 'desde'>): string =>
  [FAMILIA_TIPO_SERVICIO[s.tipo_servicio], s.desde ? `desde ${desdeMesAnio(s.desde)}` : null].filter(Boolean).join(' · ');

// ------------------------------------------------------------------ errores (contrato v1.1 §1.4)
export const MENSAJES_ERROR: Record<string, string> = {
  AGREGADO_NO_ENCONTRADO: 'No se ha encontrado. Recarga e inténtalo de nuevo.',
  VERSION_DESFASADA: 'Este contrato ha cambiado mientras lo editabas. Recarga para ver la última versión.',
  IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION: 'Esta operación ya se usó con otro contenido. Vuelve a empezar para guardarla.',
  CONFLICTO_CONCURRENCIA: 'El servidor está ocupado. Vuelve a intentarlo en un momento: no se duplicará.',
  TERCERO_NO_DISPONIBLE: 'Esa persona no está disponible (está desactivada o no existe). Reactívala o elige otra.',
  PARTICIPANTE_DUPLICADO: 'Esa persona ya figura en ese papel del contrato.',
  FECHA_ANTERIOR_INICIO: 'La fecha no puede ser anterior al inicio.',
  MOTIVO_AUSENTE: 'Indica el motivo del cambio.',
  CAMPO_INMUTABLE: 'La propiedad y el tipo de un contrato no se pueden cambiar.',
  OPERACION_NO_PERMITIDA_EN_ESTADO: 'En el estado actual no se puede hacer esto.',
  SUMA_NO_CUADRA: 'Las cifras no cuadran.',
  HABITACIONES_EN_USO: 'Hay contratos en las habitaciones que quieres quitar de la ficha.',
  HABITACION_REQUERIDA: 'Elige la habitación.',
  HABITACION_NO_ADMITIDA: 'Solo un contrato por habitaciones lleva habitación.',
  HABITACION_FUERA_DE_FICHA: 'Esa habitación no está en la ficha de la propiedad.',
  HABITACIONES_NO_INDICADAS: TEXTO_ACTUAL_SIN_HABITACIONES,
  SOLAPE_CON_CONTRATO_FIRMADO: `${TEXTO_YA_ALQUILADA_TITULO}. ${TEXTO_YA_ALQUILADA_AVISO}`,
  PROPIEDAD_FUERA_DE_PATRIMONIO: 'Esa propiedad ya había salido de tu patrimonio en la fecha de inicio.',
  FALTAN_PARTES_PARA_FORMALIZAR: 'Para firmar hacen falta un arrendador (o gestor) y un inquilino principal. La agencia o el administrador no cuentan.',
  PRINCIPAL_REQUERIDO: 'Marca un principal entre los arrendadores, los gestores y los inquilinos.',
  INQUILINO_NO_PUEDE_SER_YO: TEXTO_INQUILINO_NO_YO,
  ROL_NO_ADMITIDO_PARA_YO: 'La agencia o el administrador son solo terceros: «Tú» no puede serlo.',
  CONTRATO_SIN_INQUILINO: 'Un contrato vigente no se puede quedar sin inquilino. Añade otro antes de cerrar al último.',
  CONTRATO_SIN_ARRENDADOR: 'Un contrato firmado no se puede quedar sin arrendador (o gestor). Añade otro antes de cerrar al último.',
  PRINCIPAL_DUPLICADO: 'Solo puede haber un principal por papel.',
  TRATAMIENTO_SOLAPADO: 'Ese servicio ya tiene un tratamiento vigente en este contrato.',
  SERVICIO_YA_VINCULADO: 'Ese servicio ya está vinculado a la propiedad en esas fechas.',
  CLAUSULA_SOLAPADA: 'Esa versión de la cláusula se solapa con otra.',
  DESDE_IGUAL_A_VERSION_ABIERTA: 'Esa fecha es la misma de la versión vigente: eso es una corrección, no un cambio nuevo.',
  FECHA_FIN_ANTERIOR_A_VIGENCIA: 'El fin es anterior al inicio de alguna persona, servicio o cláusula vigente del contrato.',
  CONTRATO_NO_VIGENTE: 'Esto solo se puede hacer con un contrato firmado y sin terminar.',
  SUCESOR_SOLAPADO: 'El contrato nuevo tiene que empezar después del último día del actual.',
  FECHA_INICIO_REQUERIDA: 'Falta la fecha de inicio.',
  CLAUSULA_INCOMPLETA: 'La cláusula está incompleta: el porcentaje fijo exige porcentaje y «Sin revisión» no lleva parámetros.',
  SERVICIO_NO_VINCULADO_A_PROPIEDAD: 'Ese servicio no pertenece a la propiedad del contrato en esa fecha.',
  ACTOR_NO_ES_INQUILINO: 'Solo se puede repercutir a un inquilino vigente del contrato.',
  TRATAMIENTO_INCOMPATIBLE: 'Ese tratamiento no es coherente: incluido y repercutido a la vez, o el porcentaje no encaja con el modo.',
  SERVICIO_DADO_DE_BAJA: 'Ese servicio está dado de baja.',
  ROL_DESCONOCIDO: 'Ese rol no existe.',
  CLASIFICACION_CICLO: 'Una clasificación no puede quedar dentro de una de sus descendientes.',
  CLASIFICACION_NOMBRE_REPETIDO: 'Ya hay una clasificación con ese nombre en ese nivel.',
  RETIRADA_NO_ADMITIDA: 'En esta versión un rol o una clasificación añadidos no se pueden quitar.',
  RENTA_NO_DISPONIBLE: 'La renta y la fianza llegarán con la parte de cobros. De momento no se pueden registrar.',
};

export const MOTIVO_RENTA_PENDIENTE = 'RENTA_PENDIENTE_DE_F06_04';
export const MOTIVO_REGLA_SERVICIO_PENDIENTE = 'REGLA_SERVICIO_PENDIENTE_DE_F06_04';

/**
 * Texto de un rechazo. `OPERACION_NO_PERMITIDA_EN_ESTADO` con motivo de renta o de regla de servicio usa su texto propio
 * (nunca se confunden: la baja de un servicio no habla de la renta del contrato). Un código desconocido muestra el mensaje del servidor.
 */
export function textoErrorContrato(codigo: string, mensaje?: string, detalle?: Record<string, unknown>): string {
  if (codigo === 'OPERACION_NO_PERMITIDA_EN_ESTADO') {
    const motivo = detalle?.motivo;
    if (motivo === MOTIVO_RENTA_PENDIENTE) return TEXTO_RENTA_PENDIENTE;
    if (motivo === MOTIVO_REGLA_SERVICIO_PENDIENTE) return TEXTO_SERVICIO_BAJA_REGLA;
  }
  return MENSAJES_ERROR[codigo] ?? (mensaje && mensaje.trim() !== '' ? mensaje : 'No se ha podido guardar. Inténtalo de nuevo.');
}
