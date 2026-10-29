// ============================================================
// GAPTO MOBILE 2027
// Fichero: textosCola.ts
// Ruta: mobile/src/domain/textosCola.ts
// Descripción: Mensajes veraces de COLA-AR (F05 §70.A.5) por acción financiera. Antes de la confirmación solo el verbo de la acción en curso («Cobrando…», «Pagando…», «Confirmando…», «Registrando…»), nunca un resultado; tras la confirmación, el resultado pertinente («Cobro registrado», «Electricidad pagada»); durante la reconciliación, «Comprobando el cobro…»; tras una ausencia, la pregunta «Cobro pendiente: …». «Saldado · no cuenta como ingreso» lo decide la cola con la respuesta del servidor, nunca estos textos.
// Versión: 0.1.0 (F05-D056 paso 2, COLA-AR v1.0)
// ============================================================

import type { FilaActividad, FilaPrevision } from '../api/cliente';
import type { TextosCola } from '../state/colaAccionRapida';
import { formatearEur } from './importe';

const eur = (v: string | null) => (v === null ? '' : ` · ${formatearEur(v)}`);

/** F1 «Pendiente con»: cobro (derecho) o pago (obligación) del saldo entero. */
export function textosCobroPago(derecho: boolean, nombre: string, importe: string): TextosCola {
  const i = eur(importe);
  return derecho
    ? { enCurso: `Cobrando… · ${nombre}${i}`, confirmada: `Cobro registrado · ${nombre}${i}`, comprobando: 'Comprobando el cobro…',
        pendiente: `Cobro pendiente: Cobrado de ${nombre}${i}` }
    : { enCurso: `Pagando… · ${nombre}${i}`, confirmada: `Pago registrado · ${nombre}${i}`, comprobando: 'Comprobando el pago…',
        pendiente: `Pago pendiente: Pagado a ${nombre}${i}` };
}

/** F2 «Recibido»: abono de una devolución. */
export function textosAbono(compra: string, importe: string): TextosCola {
  const i = eur(importe);
  return { enCurso: `Registrando el abono… · ${compra}${i}`, confirmada: `Abono de ${compra} recibido${i}`, comprobando: 'Comprobando el abono…',
    pendiente: `Abono pendiente: ${compra}${i}` };
}

/** F3 «Repetir hoy». */
export function textosRepetir(titulo: string, f: Pick<FilaActividad, 'importe_total'>): TextosCola {
  const i = eur(f.importe_total ?? '0');
  return { enCurso: `Registrando… · ${titulo}${i}`, confirmada: `Repetido hoy: ${titulo}${i}`, comprobando: 'Comprobando el registro…',
    pendiente: `Registro pendiente: ${titulo}${i}` };
}

/** F4 previsión «Pagado» / «Cobrado» / «Hecha». */
export function textosPrevision(f: Pick<FilaPrevision, 'concepto' | 'tipo' | 'importe_esperado'>): TextosCola {
  const i = eur(f.importe_esperado);
  const cobro = f.tipo === 'INGRESO';
  return { enCurso: `${cobro ? 'Cobrando…' : 'Pagando…'} · ${f.concepto}${i}`, confirmada: `${f.concepto} ${cobro ? 'cobrada' : 'pagada'}${i}`,
    comprobando: cobro ? 'Comprobando el cobro…' : 'Comprobando el pago…', pendiente: `${cobro ? 'Cobro' : 'Pago'} pendiente: ${f.concepto}${i}` };
}

/** F5 previsión «No hubo». */
export function textosNoHubo(f: Pick<FilaPrevision, 'concepto'>): TextosCola {
  return { enCurso: `Confirmando… · ${f.concepto} · no hubo este mes`, confirmada: `${f.concepto} · no hubo este mes`,
    comprobando: 'Comprobando «No hubo»…', pendiente: `«No hubo» pendiente: ${f.concepto}` };
}
