// ============================================================
// GAPTO MOBILE 2027
// Fichero: propiedad.ts
// Ruta: mobile/src/domain/propiedad.ts
// Descripción: Lógica pura de B1 · Propiedad (F06-01; contratos C-PROP-01..04 y L-PROP del candidato R1 v0.8 Parte I y v0.7 Parte I; láminas F06-01 v0.9 A1–A3, D1–D3 y v0.1 C1–C2, D3–D4). Tipos de propiedad, formulario de titularidad (cuatro modos), porcentajes como texto exacto con 4 decimales y suma EXACTA del 100 % en diezmilésimas enteras (sin float: nunca se reparte el resto automáticamente), validaciones previas al envío, construcción de las peticiones y textos de usuario de los códigos ★ de B1. El servidor revalida todo: estas comprobaciones solo evitan envíos que sabemos que se rechazarán.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1; mandato F06-LOTE12 Parte B punto 3)
// Versión: 0.2.0 (F06 T1 UX-1 · M-07): la adquisición y «Desde» tienen que existir en el calendario (31/02 no; `esFechaIso`), con los mismos textos; el servidor ya las rechaza (dto_propiedades: dt.date). Vacía = desconocida (null) y el resto de reglas no cambian.
// ============================================================

import type { TitularidadVista, Valoracion, VistaPropiedad } from '../api/propiedades';
import { ddmmaaaaAIso, isoADdmmaaaa } from './fechas';
import { esFechaIso } from './intencion';
import { parsearImporte } from './importe';

export type TipoPropiedad = 'VIVIENDA' | 'LOCAL' | 'GARAJE' | 'TERRENO' | 'OTRO';
export const TIPOS_PROPIEDAD: { valor: TipoPropiedad; etiqueta: string }[] = [
  { valor: 'VIVIENDA', etiqueta: 'Vivienda' },
  { valor: 'LOCAL', etiqueta: 'Local' },
  { valor: 'GARAJE', etiqueta: 'Garaje' },
  { valor: 'TERRENO', etiqueta: 'Terreno' },
  { valor: 'OTRO', etiqueta: 'Otro' },
];
export const etiquetaTipo = (t: TipoPropiedad): string => TIPOS_PROPIEDAD.find((x) => x.valor === t)?.etiqueta ?? t;

export type ModoTitularidad = 'SOLO_MIA' | 'COMPARTIDA' | 'DE_OTROS' | 'DESCONOCIDA';
export const MODOS_TITULARIDAD: { valor: ModoTitularidad; titulo: string; detalle: string }[] = [
  { valor: 'SOLO_MIA', titulo: 'Solo mía', detalle: '100 % tuya' },
  { valor: 'COMPARTIDA', titulo: 'Compartida', detalle: 'Indica el porcentaje de cada persona' },
  { valor: 'DE_OTROS', titulo: 'Es de otra persona', detalle: 'No es tuya, aunque pagues gastos de ella' },
  { valor: 'DESCONOCIDA', titulo: 'Aún no lo sé', detalle: 'Tu parte quedará «sin indicar»' },
];

export type MetodoValoracion = 'MERCADO' | 'TASACION' | 'MANUAL' | 'FISCAL_REFERENCIA' | 'COMPRA';
/** Métodos que el usuario puede elegir (lámina D3: ya no ofrece «Compra»; la crea solo la compra, C-COMPRA-01). */
export const METODOS_ELEGIBLES: { valor: Exclude<MetodoValoracion, 'COMPRA'>; etiqueta: string }[] = [
  { valor: 'MERCADO', etiqueta: 'Mercado' },
  { valor: 'TASACION', etiqueta: 'Tasación' },
  { valor: 'MANUAL', etiqueta: 'Manual' },
  { valor: 'FISCAL_REFERENCIA', etiqueta: 'Valor de referencia' },
];
export const etiquetaMetodo = (m: MetodoValoracion): string =>
  m === 'COMPRA' ? 'Compra' : m === 'FISCAL_REFERENCIA' ? 'Referencia fiscal' : METODOS_ELEGIBLES.find((x) => x.valor === m)?.etiqueta ?? m;

// ------------------------------------------------------------------ porcentajes (texto exacto)

export type ParseoPorcentaje =
  | { ok: true; valor: string; diezmilesimas: number }
  | { ok: false; motivo: 'VACIO' | 'FORMATO' | 'NO_POSITIVO' | 'DECIMALES' | 'MAYOR_100' };

/** «33,3333» | «33.3333» | «50» → «33.3333» | «50.0000» (texto canónico de 4 decimales) y su valor entero en diezmilésimas. */
export function parsearPorcentaje(texto: string): ParseoPorcentaje {
  const t = texto.trim().replace(/\s|%/g, '').replace(',', '.');
  if (!t) return { ok: false, motivo: 'VACIO' };
  if (!/^\d+(\.\d*)?$/.test(t)) return { ok: false, motivo: 'FORMATO' };
  const [ent, dec = ''] = t.split('.');
  if (dec.length > 4) return { ok: false, motivo: 'DECIMALES' };
  const diez = Number(ent) * 10000 + Number(dec.padEnd(4, '0'));
  if (diez <= 0) return { ok: false, motivo: 'NO_POSITIVO' };
  if (diez > 1000000) return { ok: false, motivo: 'MAYOR_100' };
  return { ok: true, valor: `${Number(ent)}.${dec.padEnd(4, '0')}`, diezmilesimas: diez };
}

/** «50.0000» → «50 %»; «33.3333» → «33,3333 %» (sin ceros finales). */
export function formatearPorcentaje(decimal: string): string {
  const [ent, dec = ''] = decimal.split('.');
  const d = dec.replace(/0+$/, '');
  return `${ent}${d ? `,${d}` : ''} %`;
}

/** Diezmilésimas → texto «90 %» / «33,3333 %». */
const diezATexto = (n: number) => formatearPorcentaje(`${Math.floor(n / 10000)}.${String(n % 10000).padStart(4, '0')}`);

// ------------------------------------------------------------------ formulario de titularidad

export type ParteForm = { clave: string; yo: true; nombre: string; porcentaje: string } | { clave: string; yo: false; terceroId: string; nombre: string; porcentaje: string };

export interface FormTitularidad {
  modo: ModoTitularidad | null;
  partes: ParteForm[];
  /** dd/mm/aaaa. */
  desde: string;
}

export const ESTADO_SUMA_OK = 'OK';
export type EstadoSuma = { ok: true; texto: string } | { ok: false; texto: string; motivo: 'FALTA' | 'SOBRA' | 'PORCENTAJE' };

/** Total visible (lámina A2/A3): «Total 100 % ✓» o «Total 90 % · falta un 10 %». Nunca reparte el resto. */
export function estadoSuma(partes: ParteForm[]): EstadoSuma {
  let total = 0;
  for (const x of partes) {
    const r = parsearPorcentaje(x.porcentaje);
    if (!r.ok) return { ok: false, motivo: 'PORCENTAJE', texto: textoPorcentaje(r.motivo) };
    total += r.diezmilesimas;
  }
  if (total === 1000000) return { ok: true, texto: 'Total 100 % ✓' };
  if (total < 1000000) return { ok: false, motivo: 'FALTA', texto: `Total ${diezATexto(total)} · falta un ${diezATexto(1000000 - total)}` };
  return { ok: false, motivo: 'SOBRA', texto: `Total ${diezATexto(total)} · sobra un ${diezATexto(total - 1000000)}` };
}

export function textoPorcentaje(m: Exclude<ParseoPorcentaje, { ok: true }>['motivo']): string {
  return {
    VACIO: 'Escribe el porcentaje de cada persona.',
    FORMATO: 'Escribe el porcentaje como 50 o 33,3333.',
    NO_POSITIVO: 'Si alguien no participa, no lo añadas: no se guardan personas con 0 %.',
    DECIMALES: 'Como mucho 4 decimales.',
    MAYOR_100: 'Ningún porcentaje puede pasar del 100 %.',
  }[m];
}

export const TEXTO_SUMA = 'Debe sumar exactamente 100 %. Si alguien no participa, no lo añadas: no se guardan personas con 0 %.';
export const TEXTO_TITULARIDAD_DIMENSION = 'Este reparto es la titularidad del inmueble. No decide quién paga cada gasto ni el reparto de una cuenta: son dimensiones independientes.';

/** Partes iniciales al elegir un modo (lámina A2): «Solo mía» = Tú 100 %; «Compartida» = Tú y un hueco; «De otra persona» = sin ti. */
export function partesParaModo(modo: ModoTitularidad, actuales: ParteForm[], claveNueva: () => string): ParteForm[] {
  const terceros = actuales.filter((x) => !x.yo);
  const yo = actuales.find((x) => x.yo);
  if (modo === 'SOLO_MIA') return [{ clave: yo?.clave ?? claveNueva(), yo: true, nombre: 'Tú', porcentaje: '100' }];
  if (modo === 'COMPARTIDA') return [yo ?? { clave: claveNueva(), yo: true, nombre: 'Tú', porcentaje: '' }, ...terceros];
  if (modo === 'DE_OTROS') return terceros;
  return [];
}

/** Lo que falta o está mal en la titularidad (en su orden); vacío = se puede continuar. `adquisicion` en ISO o null. */
export function faltaTitularidad(f: FormTitularidad, adquisicion: string | null): string[] {
  const r: string[] = [];
  if (f.modo === null) return ['elige de quién es'];
  if (f.modo === 'DESCONOCIDA') return r;
  // M-07: «Desde» tiene que existir en el calendario (31/02 no); el servidor ya la rechaza (dto_propiedades: desde dt.date).
  const leida = f.desde.trim() ? ddmmaaaaAIso(f.desde) : null;
  const desde = leida && esFechaIso(leida) ? leida : null;
  if (!f.desde.trim()) r.push('la fecha «Desde»');
  else if (!desde) r.push('la fecha «Desde» como dd/mm/aaaa');
  else if (adquisicion && desde < adquisicion) r.push('una fecha «Desde» igual o posterior a la adquisición');
  if (f.modo === 'COMPARTIDA') {
    if (!f.partes.some((x) => x.yo)) r.push('tu parte');
    if (f.partes.filter((x) => !x.yo).length < 1) r.push('al menos otra persona');
  }
  if (f.modo === 'DE_OTROS' && f.partes.length < 1) r.push('al menos una persona');
  if (f.modo === 'DE_OTROS' && f.partes.some((x) => x.yo)) r.push('quitarte (no es tuya)');
  const ids = f.partes.filter((x): x is Extract<ParteForm, { yo: false }> => !x.yo).map((x) => x.terceroId);
  if (new Set(ids).size !== ids.length) r.push('no repetir personas');
  if (f.partes.length > 0 && !estadoSuma(f.partes).ok) r.push('que el total sea 100 %');
  return r;
}

/** Parte tal como viaja en la petición (contrato C-PROP-01 §I.1). */
export type ParteWire = { yo: true; porcentaje: string } | { tercero_id: string; porcentaje: string };
export interface TitularidadWire {
  modo: ModoTitularidad;
  desde?: string;
  partes?: ParteWire[];
}

/** Titularidad de la petición: DESCONOCIDA sin `desde` ni `partes`; SOLO_MIA solo con `desde`; el resto con sus partes canónicas. */
export function titularidadWire(f: FormTitularidad): TitularidadWire {
  if (f.modo === null) throw new Error('titularidad sin modo');
  if (f.modo === 'DESCONOCIDA') return { modo: 'DESCONOCIDA' };
  const desde = ddmmaaaaAIso(f.desde)!;
  if (f.modo === 'SOLO_MIA') return { modo: 'SOLO_MIA', desde };
  const partes = f.partes.map((x): ParteWire => {
    const r = parsearPorcentaje(x.porcentaje);
    const porcentaje = r.ok ? r.valor : x.porcentaje;
    return x.yo ? { yo: true, porcentaje } : { tercero_id: x.terceroId, porcentaje };
  });
  return { modo: f.modo, desde, partes };
}

// ------------------------------------------------------------------ datos de la propiedad (alta y edición)

export type TriEstado = true | false | null;

export interface FormDatos {
  nombre: string;
  tipo: TipoPropiedad | null;
  /** dd/mm/aaaa o vacío (= desconocida, «No la sé»). */
  adquisicion: string;
  superficie: string;
  superficieConstruida: string;
  habitaciones: string;
  banos: string;
  garaje: TriEstado;
  trastero: TriEstado;
  referenciaCatastral: string;
  notas: string;
}

export const FORM_DATOS_VACIO: FormDatos = {
  nombre: '', tipo: null, adquisicion: '', superficie: '', superficieConstruida: '', habitaciones: '', banos: '',
  garaje: null, trastero: null, referenciaCatastral: '', notas: '',
};

export interface DatosWire {
  nombre: string;
  tipo_propiedad: TipoPropiedad;
  fecha_adquisicion: string | null;
  superficie_m2: string | null;
  superficie_construida_m2: string | null;
  habitaciones: number | null;
  banos: number | null;
  tiene_garaje: TriEstado;
  tiene_trastero: TriEstado;
  referencia_catastral: string | null;
  notas: string | null;
}

/** «72,40» → «72.40» (> 0, 2 decimales); vacío → null; mal → undefined. */
function superficie(t: string): string | null | undefined {
  if (!t.trim()) return null;
  const r = parsearImporte(t);
  return r.ok ? r.valor : undefined;
}
function entero(t: string): number | null | undefined {
  if (!t.trim()) return null;
  return /^\d{1,3}$/.test(t.trim()) ? Number(t.trim()) : undefined;
}

/** Lo que falta o está mal en los datos (A1, D3); vacío = se puede continuar. */
export function faltaDatos(f: FormDatos): string[] {
  const r: string[] = [];
  if (!f.nombre.trim()) r.push('nombre');
  if (f.tipo === null) r.push('tipo');
  // M-07: la adquisición, si se escribe, tiene que existir (31/02 no; dto_propiedades: fecha_adquisicion dt.date). Vacía = desconocida (null), como antes.
  const adq = f.adquisicion.trim() ? ddmmaaaaAIso(f.adquisicion) : null;
  if (f.adquisicion.trim() && !(adq && esFechaIso(adq))) r.push('fecha de adquisición como dd/mm/aaaa');
  if (superficie(f.superficie) === undefined) r.push('superficie útil mayor que 0');
  if (superficie(f.superficieConstruida) === undefined) r.push('superficie construida mayor que 0');
  if (entero(f.habitaciones) === undefined) r.push('habitaciones como número entero');
  if (entero(f.banos) === undefined) r.push('baños como número entero');
  return r;
}

export function datosWire(f: FormDatos): DatosWire {
  const txt = (t: string) => (t.trim() ? t.trim() : null);
  return {
    nombre: f.nombre.trim(),
    tipo_propiedad: f.tipo!,
    fecha_adquisicion: f.adquisicion.trim() ? ddmmaaaaAIso(f.adquisicion) : null,
    superficie_m2: superficie(f.superficie) ?? null,
    superficie_construida_m2: superficie(f.superficieConstruida) ?? null,
    habitaciones: entero(f.habitaciones) ?? null,
    banos: entero(f.banos) ?? null,
    tiene_garaje: f.garaje,
    tiene_trastero: f.trastero,
    referencia_catastral: txt(f.referenciaCatastral),
    notas: txt(f.notas),
  };
}

/** «72.40» → «72,40». */
export const decimalEs = (d: string | null): string => (d === null ? '' : d.replace('.', ','));

// ------------------------------------------------------------------ errores de B1 (códigos ★ y existentes)

/** Texto de usuario por código (contrato v0.8 §1.6). Los códigos sin texto propio usan el mensaje del servidor. */
export const TEXTOS_ERROR_B1: Record<string, string> = {
  SUMA_NO_CUADRA: TEXTO_SUMA,
  PARTICIPACION_NO_POSITIVA: 'Si alguien no participa, no lo añadas: no se guardan personas con 0 %.',
  PARTICIPANTE_DUPLICADO: 'Hay una persona repetida en el reparto.',
  NATURALEZA_NO_ADMITIDA_EN_TITULARIDAD: 'Solo pueden ser titulares personas o empresas. Indica qué es en Ajustes › Terceros.',
  TERCERO_NO_DISPONIBLE: 'Una de las personas ya no está disponible. Revisa el reparto.',
  FECHA_ANTERIOR_INICIO: 'La fecha «Desde» no puede ser anterior a la adquisición.',
  ADQUISICION_POSTERIOR_A_TITULARIDAD: 'La fecha de adquisición no puede ser posterior al inicio de la titularidad.',
  CAMBIO_RETROACTIVO_SIN_POLITICA: 'El nuevo reparto no puede empezar antes de hoy: cambiaría lo ya registrado.',
  CAMBIO_PROGRAMADO_EXISTENTE: 'Ya hay un cambio de reparto programado. Espera a que empiece para hacer otro.',
  REPARTO_ANTERIOR_AL_VIGENTE: 'El nuevo reparto debe empezar después del inicio del reparto actual.',
  METODO_RESERVADO_A_LA_COMPRA: 'El valor de compra sale de la compra registrada.',
  OPERACION_NO_PERMITIDA_EN_ESTADO: 'Este cambio no se puede hacer en el estado actual de la propiedad.',
  VERSION_DESFASADA: 'Esta propiedad ha cambiado desde que la abriste (por ejemplo, en otro dispositivo). Recarga para ver la versión actual y vuelve a hacer el cambio.',
  AGREGADO_NO_ENCONTRADO: 'Esta propiedad ya no existe.',
  IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION: 'No se ha guardado: este envío ya se usó con otros datos. Vuelve a empezar.',
  CAMPO_INMUTABLE: 'Ese dato no se puede cambiar aquí.',
};
export const TEXTO_INDETERMINADO_PROP = 'No se ha podido confirmar el cambio. Revisa el estado actual antes de repetirlo.';

export function textoErrorB1(codigo: string, mensaje: string): string {
  return TEXTOS_ERROR_B1[codigo] ?? (mensaje || TEXTO_INDETERMINADO_PROP);
}

// ------------------------------------------------------------------ lecturas (L-PROP) para la ficha

/** Titularidad legible: «Tú 50 % · Laura Pérez 50 %»; DESCONOCIDA → «Sin indicar» (nunca 0 ni 100 %). */
export function textoTitularidad(t: TitularidadVista): string {
  if (t.modo === 'DESCONOCIDA' || t.partes.length === 0) return 'Sin indicar';
  return t.partes.map((x) => `${x.yo ? 'Tú' : x.nombre ?? 'Sin nombre'} ${formatearPorcentaje(x.porcentaje)}`).join(' · ');
}

/** Tu participación vigente («50 %»), o null si no eres titular o no se sabe. */
export function tuParticipacion(t: TitularidadVista): string | null {
  const yo = t.partes.find((x) => x.yo);
  return yo ? formatearPorcentaje(yo.porcentaje) : null;
}

/** «Mercado · 15 jun 2028 · Portal inmobiliario»; sin fecha: «Referencia fiscal · Sin fecha». */
export function detalleValoracion(v: Valoracion, fechaLarga: (iso: string) => string): string {
  return [etiquetaMetodo(v.metodo), v.fecha_valoracion ? fechaLarga(v.fecha_valoracion) : 'Sin fecha', v.fuente].filter(Boolean).join(' · ');
}

/** Formulario de datos con lo que devolvió la lectura (edición D3). */
export function formDatosDe(v: VistaPropiedad): FormDatos {
  return {
    nombre: v.nombre,
    tipo: v.tipo_propiedad,
    adquisicion: v.fecha_adquisicion ? isoADdmmaaaa(v.fecha_adquisicion) : '',
    superficie: decimalEs(v.superficie_m2),
    superficieConstruida: decimalEs(v.superficie_construida_m2),
    habitaciones: v.habitaciones === null ? '' : String(v.habitaciones),
    banos: v.banos === null ? '' : String(v.banos),
    garaje: v.tiene_garaje,
    trastero: v.tiene_trastero,
    referenciaCatastral: v.referencia_catastral ?? '',
    notas: v.notas ?? '',
  };
}

/** Diferencias de la edición: solo los campos cambiados (omitido = no cambia; null = borrar). Vacío = nada que guardar. */
export function cambiosDatos(v: VistaPropiedad, f: FormDatos): Partial<DatosWire> {
  const nuevo = datosWire(f);
  const actual: DatosWire = {
    nombre: v.nombre, tipo_propiedad: v.tipo_propiedad, fecha_adquisicion: v.fecha_adquisicion, superficie_m2: v.superficie_m2,
    superficie_construida_m2: v.superficie_construida_m2, habitaciones: v.habitaciones, banos: v.banos, tiene_garaje: v.tiene_garaje,
    tiene_trastero: v.tiene_trastero, referencia_catastral: v.referencia_catastral, notas: v.notas,
  };
  const r: Partial<DatosWire> = {};
  for (const k of Object.keys(nuevo) as (keyof DatosWire)[]) {
    if (nuevo[k] !== actual[k]) (r as Record<string, unknown>)[k] = nuevo[k];
  }
  return r;
}

/** Formulario de un nuevo reparto (C2) partiendo del vigente; sin fecha (la elige el usuario, ≥ hoy). */
export function formCambioDe(t: TitularidadVista, claveNueva: () => string): FormTitularidad {
  if (t.modo === 'DESCONOCIDA') return { modo: null, partes: [], desde: '' };
  return {
    modo: t.modo,
    desde: '',
    partes: t.partes.map((x): ParteForm =>
      x.yo
        ? { clave: claveNueva(), yo: true, nombre: 'Tú', porcentaje: formatearPorcentaje(x.porcentaje).replace(' %', '') }
        : { clave: claveNueva(), yo: false, terceroId: x.tercero_id ?? '', nombre: x.nombre ?? 'Sin nombre', porcentaje: formatearPorcentaje(x.porcentaje).replace(' %', '') },
    ),
  };
}

/** Día anterior a una fecha ISO (el reparto actual termina el día antes del nuevo, C2). */
export function diaAnteriorIso(iso: string): string {
  const [a, m, d] = iso.split('-').map(Number);
  const x = new Date(Date.UTC(a, m - 1, d - 1));
  return `${x.getUTCFullYear()}-${String(x.getUTCMonth() + 1).padStart(2, '0')}-${String(x.getUTCDate()).padStart(2, '0')}`;
}

/** «2028-01-15» → «ene 2028» (procedencia de un valor, lámina D1). */
export function mesCortoAnioIso(iso: string): string {
  const [a, m] = iso.split('-').map(Number);
  return `${['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'][m - 1]} ${a}`;
}
