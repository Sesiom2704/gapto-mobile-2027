// ============================================================
// GAPTO MOBILE 2027
// Fichero: inicio.ts
// Ruta: mobile/src/domain/inicio.ts
// Descripción: Lógica pura de Inicio (F05-04 J3 §2.1; lámina HOME-01 v0.3 y HOME-QA v0.2 H01–H03). (1) Accesos de «Acciones rápidas»: los accesos HABILITADOS de plantillas habilitadas, en el orden de Inicio, máximo 3; icono = el del acceso, si no el de la categoría de la plantilla (lo resuelve el glifo con su reserva `pricetag-outline`). (2) «Resultado» del mes: signo explícito y tono (positivo verde, negativo rojo, cero neutro); excepción de color de D-HOME, solo para «Resultado». No hay lectura de «Resultado» en esta versión (PENDIENTE_READ_MODEL): la función queda lista y probada.
// Versión: 0.1.0 (F05-03/F05-04 J3 §2.1)
// Versión: 0.2.0 (F05-05 K3 §2.7; F05 §49.4 A9, M5-06; lámina SRCH-ACT-AFI E1): `textoSinIndicar`, la línea bajo «Este mes»: «Solo lo que es tuyo. Sin indicar: N gastos (X €) y M ingresos (Y €).» (importe pendiente de atribución, nunca propio). `resultadoDelMes` sigue siendo solo el formateador de signo y tono.
// ============================================================

import type { AccionRapida, Plantilla, ResultadoMes } from '../api/cliente';
import { formatearEur } from './importe';

export const MAX_ACCESOS_INICIO = 3;
export const TEXTO_SIN_ACCESOS = 'Guarda como plantilla los gastos que repites y aparecerán aquí.';

export interface AccesoInicio {
  accion: AccionRapida;
  plantilla: Plantilla;
  /** Clave del icono: la del acceso o, sin ella, null (el glifo usa la reserva). */
  iconoKey: string | null;
}

export function accesosDeInicio(plantillas: Plantilla[], acciones: AccionRapida[], iconoCategoria: (id: string) => string | null = () => null): AccesoInicio[] {
  const porId = new Map(plantillas.map((p) => [p.id, p]));
  return acciones
    .filter((a) => a.enabled)
    .sort((a, b) => a.orden - b.orden || (a.id < b.id ? -1 : 1))
    .flatMap((a) => {
      const p = porId.get(a.plantilla_registro_id);
      if (!p || !p.enabled) return [];
      return [{ accion: a, plantilla: p, iconoKey: a.icono_key ?? (p.categoria_id ? iconoCategoria(p.categoria_id) : null) }];
    })
    .slice(0, MAX_ACCESOS_INICIO);
}

export type TonoResultado = 'positive' | 'critical' | 'neutral';

/** «+120,00 €» verde, «−35,50 €» rojo, «0,00 €» neutro. `valor` en texto decimal con punto. */
export function resultadoDelMes(valor: string): { texto: string; tono: TonoResultado } {
  const n = Number(valor);
  if (!Number.isFinite(n) || n === 0) return { texto: formatearEur('0'), tono: 'neutral' };
  const abs = valor.replace(/^[-+]/, '');
  return n > 0 ? { texto: `+${formatearEur(abs)}`, tono: 'positive' } : { texto: `−${formatearEur(abs)}`, tono: 'critical' };
}

/** Línea de lo sin indicar bajo «Este mes» (M5-06): se cuenta y se suma aparte, nunca como propio. */
export function textoSinIndicar(r: ResultadoMes): string {
  const g = r.sin_indicar.gastos;
  const i = r.sin_indicar.ingresos;
  const partes = [
    ...(g.n > 0 ? [`${g.n} ${g.n === 1 ? 'gasto' : 'gastos'} (${formatearEur(g.importe)})`] : []),
    ...(i.n > 0 ? [`${i.n} ${i.n === 1 ? 'ingreso' : 'ingresos'} (${formatearEur(i.importe)})`] : []),
  ];
  return partes.length === 0 ? 'Solo lo que es tuyo.' : `Solo lo que es tuyo. Sin indicar: ${partes.join(' y ')}.`;
}
