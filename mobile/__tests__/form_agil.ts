// ============================================================
// GAPTO MOBILE 2027
// Fichero: form_agil.ts
// Ruta: mobile/__tests__/form_agil.ts
// Descripción: Ayuda de tests para FORM-AGIL (F06 T6 «UX ágil» S2; F09 0.55 §12.107.1). Con el exprés, los controles de
//   presupuesto, «¿De quién?», cuenta, fecha y «Más detalles» pueden vivir tras su línea de «Se registrará así» o en
//   «Más opciones»; los de importe, tercero, categoría y propiedad viven en el exprés. `ver(id)` hace lo que haría el
//   usuario para llegar al control y lo devuelve: si no está a la vista, toca su línea (o «Más opciones») o vuelve al
//   exprés, y lo busca de nuevo. Nunca crea ni oculta nada: si el control no existe tras navegar, falla como
//   `getByTestId`. Para comprobar AUSENCIAS se sigue usando `screen.queryByTestId` (sin navegar).
// Versión: 0.1.0 (F06 T6 · S2)
// ============================================================

import { act, fireEvent, screen, waitFor } from '@testing-library/react-native';

/** Línea del exprés (o entrada de «Más opciones») detrás de la que vive cada control. */
const LINEA: [RegExp, string][] = [
  [/^(presupuestable-|origen-presupuestable$|bloque-presupuestable$)/, 'linea-presupuesto'],
  [/^(cuenta-|origen-cuenta$|financiacion|falta-cuenta|cuentas-error$|otra-persona$|vivienda-solo-tus-cuentas$)/, 'linea-cuenta'],
  [/^(solo-mio|repartir|reembolsable|reembolso-|origen-atribucion)/, 'linea-quien'],
  [/^(fecha-|campo-fecha|fecha$)/, 'linea-fecha'],
  [/^(abrir-mas-detalles|mas-detalles|campo-nota|campo-contexto|contexto-valor|origen-contexto)/, 'mas-opciones'],
];

/** Controles del exprés (importe, tercero, categoría, magnitudes y propiedad). */
const EXPRES = /^(cancelar$|cambiar-tipo$|campo-(importe|tercero|categoria)|categoria-|chip-sugerida|chips-|magnitud-|no-lo-se|microcopy-|datos-categoria|vivienda|tercero-valor|origen-(tercero|categoria)|pendiente-)/;

const presente = (id: string) => screen.queryAllByTestId(id).length > 0;

/** `getByTestId` que primero navega como el usuario hasta el control (línea, «Más opciones» o «‹ Exprés»). */
export function ver(id: string) {
  if (presente(id)) return screen.getByTestId(id);
  const linea = LINEA.find(([re]) => re.test(id))?.[1];
  if (linea) {
    if (presente(linea)) {
      fireEvent.press(screen.getByTestId(linea));
    } else if (presente('mas-opciones')) {
      fireEvent.press(screen.getByTestId('mas-opciones'));
    } else if (presente('volver-expres')) {
      fireEvent.press(screen.getByTestId('volver-expres'));
      if (!presente(id) && presente(linea)) fireEvent.press(screen.getByTestId(linea));
    }
    if (id === 'campo-nota' || id === 'campo-contexto') {
      if (!presente(id) && presente('abrir-mas-detalles')) fireEvent.press(screen.getByTestId('abrir-mas-detalles'));
    }
  } else if (EXPRES.test(id) && presente('volver-expres')) {
    fireEvent.press(screen.getByTestId('volver-expres'));
  }
  return screen.getByTestId(id);
}

/** `findByTestId` con la misma navegación (espera a que el control aparezca). */
export const verPronto = (id: string) => waitFor(() => ver(id));

/** `act(fn)` que antes navega hasta el control FUERA del act (dentro, la navegación no se aplica hasta que termina). */
export async function actVer(id: string, fn: () => Promise<unknown> | unknown) {
  ver(id);
  await act(async () => {
    await fn();
  });
}
