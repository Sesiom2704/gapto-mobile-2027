// ============================================================
// GAPTO MOBILE 2027
// Fichero: inicio.ts
// Ruta: mobile/src/domain/inicio.ts
// Descripción: Lógica pura de Inicio (F05-04 J3 §2.1; lámina HOME-01 v0.3 y HOME-QA v0.2 H01–H03). (1) Accesos de «Acciones rápidas»: los accesos HABILITADOS de plantillas habilitadas, en el orden de Inicio, máximo 3; icono = el del acceso, si no el de la categoría de la plantilla (lo resuelve el glifo con su reserva `pricetag-outline`). (2) «Resultado» del mes: signo explícito y tono (positivo verde, negativo rojo, cero neutro); excepción de color de D-HOME, solo para «Resultado». No hay lectura de «Resultado» en esta versión (PENDIENTE_READ_MODEL): la función queda lista y probada.
// Versión: 0.1.0 (F05-03/F05-04 J3 §2.1)
// ============================================================

import type { AccionRapida, Plantilla } from '../api/cliente';
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
