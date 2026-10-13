// ============================================================
// GAPTO MOBILE 2027
// Fichero: FaltaCuenta.tsx
// Ruta: mobile/src/components/FaltaCuenta.tsx
// Descripción: Aviso B2 «¿Falta una cuenta? N sin configurar ›» al final de «Pagado con», «Cobrado en», «Desde» y «A» (F05-06 M4 §3; lámina CAP B2; D-CAP-06). Solo aparece si N > 0; N lo da el servidor (GET /v1/cuentas/sin-configurar, cuentas activas sin ninguna capacidad del registro). Abre la lista A1 encima del formulario (que sigue montado y conserva lo escrito); al volver, el formulario recarga sus cuentas y el número.
// Versión: 0.1.0 (F05-06 M4 F2)
// ============================================================

import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { ClienteApi } from '../api/cliente';
import { textoFaltaCuenta } from '../domain/capacidades';
import { CuentasCapacidadesScreen } from '../screens/CuentasCapacidadesScreen';
import { useTema } from '../theme/tema';
import { TACTIL_MIN, tipo } from '../theme/tokens';

/** Número de cuentas sin configurar (0 si no se puede leer: el aviso no aparece). */
export function useSinConfigurar(cliente: ClienteApi): { n: number; recargar: () => void } {
  const [n, setN] = useState(0);
  const recargar = useCallback(() => {
    void cliente.cuentasSinConfigurar().then((r) => setN(r.tipo === 'OK' ? r.datos.sin_configurar : 0));
  }, [cliente]);
  useEffect(() => {
    recargar();
  }, [recargar]);
  return { n, recargar };
}

export function AvisoFaltaCuenta(p: { n: number; onPress: () => void; testID: string }) {
  const { c } = useTema();
  const texto = textoFaltaCuenta(p.n);
  if (!texto) return null;
  return (
    <Pressable testID={p.testID} accessibilityRole="link" accessibilityLabel={texto} onPress={p.onPress} hitSlop={4} style={({ pressed }) => [s.aviso, { opacity: pressed ? 0.7 : 1 }]}>
      <Text style={[tipo.footnote, { color: c.accent, fontWeight: '600' }]}>{`${texto} ›`}</Text>
    </Pressable>
  );
}

/** Lista A1 superpuesta al formulario de registro; «‹ <formulario>» vuelve a él. */
export function PanelCuentas(p: { cliente: ClienteApi; etiquetaAtras: string; onCerrar: () => void }) {
  const { c } = useTema();
  return (
    <View testID="panel-cuentas" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CuentasCapacidadesScreen cliente={p.cliente} etiquetaAtras={p.etiquetaAtras} onAtras={p.onCerrar} />
    </View>
  );
}

const s = StyleSheet.create({
  aviso: { minHeight: TACTIL_MIN, justifyContent: 'center', alignSelf: 'flex-start' },
});
