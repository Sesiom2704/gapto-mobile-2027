// ============================================================
// GAPTO MOBILE 2027
// Fichero: edicion.ts
// Ruta: mobile/src/domain/edicion.ts
// Descripción: «Corregir» y «Anular por duplicado» (F05-06 M1; lámina EDIT-HECHO v0.1, D-EDIT-01..08 y P-EDIT-01..05; F05 §61.2 F05-D047; CONTRATO_M1 v0.1 §2). Lógica pura: motivos fijos más «Otro…» (P-EDIT-05, no configurables), textos de la lámina (solo errores, INV-07; anular no borra), cambios antes → después de la corrección (importe, fecha y cuenta de un pago simple; importe, fecha y cuentas de una transferencia: P-EDIT-03, el importe va siempre con su movimiento), lo que falta para revisar y los payloads de OP-21P, OP-21T y OP-03P. La declaración de duplicado es explícita y sin valor por defecto. La elegibilidad viene del servidor, que además revalida cada envío: aquí nada decide si algo es corregible.
// Versión: 0.1.0 (F05-06 M1)
// ============================================================

import type { EdicionHecho, PayloadAnularDuplicado, PayloadCorregirPago, PayloadCorregirTransferencia } from '../api/cliente';
import { parsearImporte } from './importe';

export const MOTIVOS_CORREGIR = ['Importe mal tecleado', 'Fecha equivocada', 'Otro dato mal elegido'] as const;
export const MOTIVOS_ANULAR = ['Lo registré dos veces', 'Era una prueba'] as const;
export const TEXTO_SOLO_ERRORES = 'Para datos que nunca fueron ciertos. Si algo cambió después (te devolvieron dinero, llegó un cargo extra), no lo corrijas aquí.';
export const TEXTO_SE_CORRIGE_EN_SITIO = 'El registro se corrige en el mismo sitio y queda anotado quién, cuándo y por qué. No se crea un registro nuevo.';
export const TEXTO_ANULAR = 'Úsalo solo si este registro está repetido. Queda guardado como anulado y su movimiento deja de contar en el saldo y en el Resultado. No se puede deshacer.';
export const TEXTO_ANULAR_DEVOLUCION = 'Si el gasto ocurrió y luego te devolvieron el dinero, usa «Registrar devolución».';
export const DECLARACION_DUPLICADO = 'Este registro está repetido; el cargo no ocurrió dos veces.';
export const TEXTO_ANULADO = 'Registro anulado: ya no cuenta en tus cuentas ni en el Resultado.';

export interface FormularioEdicion {
  importe: string;
  fecha: string; // ISO yyyy-mm-dd
  cuentaSalida: string | null;
  cuentaEntrada: string | null;
}

export type CampoEdicion = 'importe' | 'fecha' | 'cuenta' | 'cuenta_origen' | 'cuenta_destino';
export interface CambioEdicion {
  campo: CampoEdicion;
  antes: string;
  despues: string;
}

const salida = (e: EdicionHecho) => e.movimientos.find((m) => m.pata === 'SALIDA') ?? null;
const entrada = (e: EdicionHecho) => e.movimientos.find((m) => m.pata === 'ENTRADA') ?? null;

export const esTransferencia = (e: Pick<EdicionHecho, 'tipo'>) => e.tipo === 'TRANSFERENCIA';

/** Formulario precargado con lo registrado (D-EDIT-03). */
export function formularioInicial(e: EdicionHecho): FormularioEdicion {
  return {
    importe: (e.importe ?? '').replace('.', ','),
    fecha: e.fecha,
    cuentaSalida: salida(e)?.cuenta.id ?? null,
    cuentaEntrada: esTransferencia(e) ? entrada(e)?.cuenta.id ?? null : null,
  };
}

function importeDecimal(texto: string): string | null {
  const p = parsearImporte(texto);
  return p.ok ? p.valor : null;
}

/** Cambios antes → después (solo los que difieren); importes en decimal de dos cifras. */
export function cambiosEdicion(e: EdicionHecho, f: FormularioEdicion): CambioEdicion[] {
  const cambios: CambioEdicion[] = [];
  const importe = importeDecimal(f.importe);
  if (importe !== null && e.importe !== null && Number(importe) !== Number(e.importe)) {
    cambios.push({ campo: 'importe', antes: e.importe, despues: importe });
  }
  if (f.fecha && f.fecha !== e.fecha) cambios.push({ campo: 'fecha', antes: e.fecha, despues: f.fecha });
  const s = salida(e);
  if (s && f.cuentaSalida && f.cuentaSalida !== s.cuenta.id) {
    cambios.push({ campo: esTransferencia(e) ? 'cuenta_origen' : 'cuenta', antes: s.cuenta.id, despues: f.cuentaSalida });
  }
  const en = entrada(e);
  if (esTransferencia(e) && en && f.cuentaEntrada && f.cuentaEntrada !== en.cuenta.id) {
    cambios.push({ campo: 'cuenta_destino', antes: en.cuenta.id, despues: f.cuentaEntrada });
  }
  return cambios;
}

/** Lo que falta para revisar o para guardar, en lenguaje llano. */
export function faltaEdicion(e: EdicionHecho, f: FormularioEdicion, motivo: string | null): string[] {
  const falta: string[] = [];
  if (importeDecimal(f.importe) === null) falta.push('un importe mayor que cero');
  if (esTransferencia(e) && f.cuentaSalida && f.cuentaSalida === f.cuentaEntrada) falta.push('dos cuentas distintas');
  if (falta.length === 0 && cambiosEdicion(e, f).length === 0) falta.push('algún cambio');
  if (motivo !== null && !motivo.trim()) falta.push('el motivo');
  return falta;
}

/** Payload de OP-21P u OP-21T con SOLO lo que cambia; `error_de_registro` siempre explícito (INV-07). */
export function componerCorreccion(e: EdicionHecho, f: FormularioEdicion, motivo: string, intencionId: string):
  { ruta: 'PAGO'; payload: PayloadCorregirPago } | { ruta: 'TRANSFERENCIA'; payload: PayloadCorregirTransferencia } {
  const cambios = cambiosEdicion(e, f);
  const valor = (c: CampoEdicion) => cambios.find((x) => x.campo === c)?.despues;
  const comun = { intencion_id: intencionId, row_version: e.row_version, motivo: motivo.trim(), error_de_registro: true as const };
  const opcional = <K extends string>(k: K, v: string | undefined) => (v === undefined ? {} : { [k]: v } as Record<K, string>);
  if (esTransferencia(e)) {
    return {
      ruta: 'TRANSFERENCIA',
      payload: {
        ...comun,
        movimientos_row_version: Object.fromEntries(e.movimientos.map((m) => [m.movimiento_id, m.row_version])),
        ...opcional('importe', valor('importe')), ...opcional('fecha', valor('fecha')),
        ...opcional('cuenta_origen_id', valor('cuenta_origen')), ...opcional('cuenta_destino_id', valor('cuenta_destino')),
      },
    };
  }
  return {
    ruta: 'PAGO',
    payload: {
      ...comun,
      movimiento_row_version: salida(e)?.row_version ?? 0,
      ...opcional('importe', valor('importe')), ...opcional('fecha', valor('fecha')), ...opcional('cuenta_id', valor('cuenta')),
    },
  };
}

/** Payload de OP-03P: la declaración viaja tal cual la marcó el usuario (sin defecto). */
export function componerAnulacion(e: EdicionHecho, motivo: string, declarado: boolean, intencionId: string): PayloadAnularDuplicado {
  return {
    intencion_id: intencionId,
    row_version: e.row_version,
    movimientos_row_version: Object.fromEntries(e.movimientos.map((m) => [m.movimiento_id, m.row_version])),
    motivo: motivo.trim(),
    duplicado_declarado: declarado,
  };
}

/** Etiqueta de cada campo en la revisión (A3). */
export const ETIQUETA_CAMPO: Record<CampoEdicion, string> = {
  importe: 'Importe', fecha: 'Fecha', cuenta: 'Pagado con', cuenta_origen: 'Sale de', cuenta_destino: 'Entra en',
};
