// ============================================================
// GAPTO MOBILE 2027
// Fichero: hipoteca_fixtures.ts
// Ruta: mobile/__tests__/hipoteca_fixtures.ts
// Descripción: Datos sintéticos de la hipoteca para los Jest del cliente (F06-01H): una L-HIP con 6 cuotas (2 pagadas, la 3 próxima), el reparto Tú 60 % · Ana 40 % y un cuadro previo de W-HIP-00. Los importes son los que daría el servidor: el cliente no los calcula (capital + intereses = cuota en cada fila).
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 10)
// ============================================================

import type { CuadroPrevio, CuotaHipoteca, Hipoteca } from '../src/api/hipoteca';
import type { ParteEnFecha } from '../src/api/patrimonio';

export const YO = 'f0000000-0000-4000-8000-0000000000ff';
export const ANA = 'a0000000-0000-4000-8000-0000000000a1';
export const CTA = 'c0000000-0000-4000-8000-0000000000c1';
export const CTA2 = 'c0000000-0000-4000-8000-0000000000c2';
export const BANCO = 'b0000000-0000-4000-8000-0000000000b1';
export const FID = 'e0000000-0000-4000-8000-0000000000e1';

export const PARTES: ParteEnFecha[] = [
  { actor_id: ANA, porcentaje: '40.0000', yo: false, tercero_id: 't-ana', nombre: 'Ana' },
  { actor_id: YO, porcentaje: '60.0000', yo: true, tercero_id: null, nombre: null },
];

const q = (numero: number, vencimiento: string, cuota: string, interes: string, capital: string, pendiente: string, estado: string): CuotaHipoteca => ({
  numero, vencimiento, cuota, interes, capital, pendiente, estado, version_id: 'v-alta', hecho_pago_id: estado === 'PAGADA' ? `h-${numero}` : null,
});

export function hipoteca(cambios: Partial<Hipoteca> = {}): Hipoteca {
  const cuotas = [
    q(1, '2026-04-20', '1000.00', '250.00', '750.00', '99250.00', 'PAGADA'),
    q(2, '2026-05-20', '1000.00', '248.13', '751.87', '98498.13', 'PAGADA'),
    q(3, '2026-06-20', '1000.00', '246.25', '753.75', '97744.38', 'VENCIDA'),
    q(4, '2026-07-20', '1000.00', '244.36', '755.64', '96988.74', 'PENDIENTE'),
    q(5, '2026-08-20', '1000.00', '242.47', '757.53', '96231.21', 'PENDIENTE'),
    q(6, '2026-09-20', '96471.79', '240.58', '96231.21', '0.00', 'PENDIENTE'),
  ];
  return {
    financiacion_id: FID, nombre: 'Hipoteca · Piso Ejemplo', row_version: 3, estado: 'ACTIVA', propiedad_id: 'p1', compra_hecho_id: 'h0',
    desembolso: { hecho_id: 'hd', cuenta_id: CTA, fecha: '2026-03-20', importe: '100000.00' }, aviso_reparto_distinto: false,
    financiador: { actor_id: 'act-banco', tercero_id: BANCO, nombre: 'Banco Ejemplo' }, capital: '100000.00', fecha_inicio: '2026-03-20',
    fecha_fin_prevista: '2026-09-20', convencion: 'MENSUAL_ANUAL_12', cuenta_cargo_id: CTA, tipo_vigente: '3', vigente_desde: '2026-03-20',
    cuota_vigente: '1000.00', deuda_pendiente: '98498.13', deuda_indeterminada: false, capital_amortizado: '1501.87', intereses_pagados: '498.13',
    cuotas_pagadas: 2, numero_cuotas: 6, proxima_cuota: cuotas[2],
    condiciones: [{ id: 'v-alta', vigente_desde: '2026-03-20', vigente_hasta: null, motivo: 'ALTA', tipo_interes: 'FIJO', tasa_anual: '3', indice_referencia: null,
      diferencial: null, cuota_referencia: '1000.00', numero_cuotas: 6, hecho_causa_id: 'hd' }],
    cuotas,
    ...cambios,
  };
}

export function cuadroPrevio(n = 20): CuadroPrevio {
  const cuotas = Array.from({ length: n }, (_, i) => ({
    n: i + 1, vencimiento: `2027-${String((i % 12) + 1).padStart(2, '0')}-20`, cuota: '500.00', interes: '100.00', capital: '400.00', comision: '0.00',
    pendiente: String(10000 - (i + 1) * 400) + '.00',
  }));
  return {
    sistema: 'FRANCES', periodicidad: 'MENSUAL', convencion: 'MENSUAL_ANUAL_12', capital: '160000.00', tasa_anual: '2.5', numero_cuotas: n, cuota_referencia: '500.00',
    suma_capital: '160000.00', suma_intereses: '2000.00', total_a_pagar: '162000.00', cuotas,
  };
}
