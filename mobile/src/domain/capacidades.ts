// ============================================================
// GAPTO MOBILE 2027
// Fichero: capacidades.ts
// Ruta: mobile/src/domain/capacidades.ts
// Descripción: Lógica pura y textos de las capacidades de cuenta (F05-06 M4 §3; F09 §12.105 CAP, lámina CAP v0.1 A1–A4, B1–B4; D-CAP-01..08). Resumen de la fila de A1, textos de las hojas de activar (A3) y desactivar (A4) con «Lo ya registrado no cambia», lista de lo que deja de funcionar (plantillas y preferencias que da el servidor; no se reasignan), aviso de cuenta sin configurar (B1, «De V3» solo si el servidor lo sabe, PD-4), entradas del historial (B4) y aviso «¿Falta una cuenta?» (B2). Nada se deduce del tipo ni del nombre de la cuenta (D-CAP-04): todo sale de lo que devuelve el servidor. Los textos marcados DERIVADO no están literalmente en la lámina.
// Versión: 0.1.0 (F05-06 M4 F2)
// ============================================================

import type { CodigoCapacidad, CuentaCapacidades, EntradaHistorialCapacidad, ImpactoCapacidad } from '../api/cliente';
import { diaMesAnioIso, isoLocal } from './fechas';

export type CapacidadRegistro = 'PAGAR_GASTO' | 'RECIBIR_INGRESO' | 'TRANSFERIR_SALIDA' | 'TRANSFERIR_ENTRADA';

/** Forma corta para el resumen de A1 (lámina: «Pagar · Recibir · Enviar · Recibir de tus cuentas»). */
const CORTA: Record<CapacidadRegistro, string> = {
  PAGAR_GASTO: 'Pagar',
  RECIBIR_INGRESO: 'Recibir',
  TRANSFERIR_SALIDA: 'Enviar',
  TRANSFERIR_ENTRADA: 'Recibir de tus cuentas',
};

/** Campo del registro donde se nota cada capacidad (D-CAP-01). */
export const CAMPO_REGISTRO: Record<CapacidadRegistro, string> = {
  PAGAR_GASTO: 'Pagado con',
  RECIBIR_INGRESO: 'Cobrado en',
  TRANSFERIR_SALIDA: 'Desde',
  TRANSFERIR_ENTRADA: 'A',
};

export const TEXTO_SIN_CONFIGURAR = 'Sin configurar';
export const TEXTO_YA_REGISTRADO = 'Lo ya registrado no cambia.';
export const TEXTO_NO_DEDUCE = 'Todo empieza desactivado: Gapto no lo deduce del tipo de cuenta.';
export const TEXTO_PIE_HISTORIAL = 'Cada cambio afecta a lo que registres a partir de ese momento. Lo registrado antes se conserva tal cual.';
export const TEXTO_QUEDARAN = 'Quedarán como «No disponible» hasta que elijas otra cuenta o vuelvas a permitirlo.';
export const TEXTO_DEJA_DE_FUNCIONAR = 'Esto deja de funcionar:';
/** DERIVADO. */
export const TEXTO_HISTORIAL_VACIO = 'Aún no hay cambios en lo que puede hacer esta cuenta.';
/** DERIVADO (PD-2). */
export const TEXTO_NO_EDITABLE_ESTADO = 'Esta cuenta está cerrada o desactivada: no se puede cambiar lo que puede hacer.';
/** DERIVADO (conflicto de versión, §3). */
export const TEXTO_VERSION_CUENTA = 'Esta cuenta ha cambiado mientras la mirabas. Hemos cargado su estado actual. Revisa y vuelve a intentarlo.';
/** DERIVADO. */
export const TEXTO_INDETERMINADO_CUENTA = 'No se ha podido confirmar el cambio. Revisa el estado actual antes de repetirlo.';
/** DERIVADO: la lista de A1 sin cuentas (el alta de cuentas no es de M4, P-CAP-05). */
export const TEXTO_SIN_CUENTAS = 'Aún no tienes cuentas.';
/** B3: complemento del mensaje del servidor. */
export const TEXTO_FORMULARIO_SE_CONSERVA = 'El resto del formulario se conserva.';

export const esCapacidadRegistro = (c: CodigoCapacidad): c is CapacidadRegistro => c in CORTA;

/** Subtítulo de la fila de A1: lo que puede hacer o, sin configurar, «(De V3 ·) aún no puede hacer nada». */
export function resumenCuenta(x: CuentaCapacidades): string {
  if (x.sin_configurar) return x.origen_v3 ? 'De V3 · aún no puede hacer nada' : 'Aún no puede hacer nada';
  return x.capacidades.filter((k) => k.permitida && esCapacidadRegistro(k.codigo)).map((k) => CORTA[k.codigo as CapacidadRegistro]).join(' · ');
}

/** Grupos de A1 en el orden del servidor: «Sin configurar» arriba y «Tus cuentas» (D-CAP-05). */
export function agruparCuentas(lista: CuentaCapacidades[]): { sinConfigurar: CuentaCapacidades[]; configuradas: CuentaCapacidades[] } {
  return { sinConfigurar: lista.filter((x) => x.sin_configurar), configuradas: lista.filter((x) => !x.sin_configurar) };
}

/** Aviso de B1 para una cuenta sin configurar. */
export function avisoSinConfigurar(x: CuentaCapacidades): string {
  const inicio = x.origen_v3 ? 'Esta cuenta viene de V3 sin capacidades declaradas.' : 'Esta cuenta aún no puede hacer nada.';
  return `${inicio} Mientras no elijas qué puede hacer, no aparece al registrar. Lo que ya tiene registrado se conserva.`;
}

const PREGUNTA: Record<CapacidadRegistro, { permitir: (n: string) => string; dejar: (n: string) => string; desde: string }> = {
  PAGAR_GASTO: { permitir: (n) => `¿Permitir pagar gastos con ${n}?`, dejar: (n) => `¿Dejar de pagar gastos con ${n}?`, desde: 'al registrar un gasto' },
  RECIBIR_INGRESO: { permitir: (n) => `¿Permitir recibir ingresos en ${n}?`, dejar: (n) => `¿Dejar de recibir ingresos en ${n}?`, desde: 'al registrar un ingreso' },
  TRANSFERIR_SALIDA: {
    permitir: (n) => `¿Permitir enviar desde ${n} a otras cuentas tuyas?`,
    dejar: (n) => `¿Dejar de enviar desde ${n} a otras cuentas tuyas?`,
    desde: 'al registrar un movimiento entre cuentas',
  },
  TRANSFERIR_ENTRADA: {
    permitir: (n) => `¿Permitir recibir en ${n} desde otras cuentas tuyas?`,
    dejar: (n) => `¿Dejar de recibir en ${n} desde otras cuentas tuyas?`,
    desde: 'al registrar un movimiento entre cuentas',
  },
};

/** Título y consecuencia de la hoja A3 (permitir) o A4 (dejar de permitir). */
export function textosHoja(capacidad: CapacidadRegistro, cuenta: string, permitir: boolean): { titulo: string; consecuencia: string; boton: string } {
  const q = PREGUNTA[capacidad];
  const campo = CAMPO_REGISTRO[capacidad];
  return permitir
    ? { titulo: q.permitir(cuenta), consecuencia: `Desde ahora podrás elegirla en «${campo}» ${q.desde}.`, boton: 'Permitir' }
    : { titulo: q.dejar(cuenta), consecuencia: `Dejará de aparecer en «${campo}».`, boton: 'Dejar de permitir' };
}

/** Lo que deja de funcionar (A4), tal como lo da el servidor; nunca se reasigna. */
export function lineasImpacto(imp: ImpactoCapacidad, capacidad: CapacidadRegistro, cuenta: string): string[] {
  const naturaleza = capacidad === 'RECIBIR_INGRESO' ? 'Ingresos' : 'Gastos';
  const todos = capacidad === 'RECIBIR_INGRESO' ? 'Todos los ingresos' : 'Todos los gastos';
  const plantillas = imp.plantillas.map((x) => `Plantilla «${x.nombre}»${x.enabled ? '' : ' (desactivada)'}`);
  const preferencias = imp.preferencias.map((x) => {
    const ambito = [x.categoria_nombre ? `${naturaleza} de ${x.categoria_nombre}` : null, x.tercero_nombre].filter(Boolean).join(' · ') || todos;
    return `Preferencia «${ambito} → ${cuenta}»${x.enabled ? '' : ' (desactivada)'}`;
  });
  return [...plantillas, ...preferencias];
}

/** Entrada del historial (B4): «Permitido: <capacidad>» y «<fecha> · tú». */
export function lineaHistorial(e: EntradaHistorialCapacidad): { titulo: string; detalle: string } {
  const quien = e.actor_tipo === 'SISTEMA' ? 'sistema' : e.actor_es_owner ? 'tú' : 'otra persona';
  return {
    titulo: `${e.accion === 'ACTIVAR' ? 'Permitido' : 'Ya no permitido'}: ${e.etiqueta}`,
    detalle: `${diaMesAnioIso(isoLocal(new Date(e.cuando)))} · ${quien}`,
  };
}

/** Aviso B2 al final de «Pagado con», «Cobrado en», «Desde» y «A»; solo si N > 0. */
export function textoFaltaCuenta(n: number): string | null {
  return n > 0 ? `¿Falta una cuenta? ${n} sin configurar` : null;
}
