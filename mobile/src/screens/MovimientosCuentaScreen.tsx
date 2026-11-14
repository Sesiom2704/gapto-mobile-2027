// ============================================================
// GAPTO MOBILE 2027
// Fichero: MovimientosCuentaScreen.tsx
// Ruta: mobile/src/screens/MovimientosCuentaScreen.tsx
// Descripción: T2-F06 PAG · «Movimientos de la cuenta» (L-MOV-CUENTA; L-09, Q-VP-01; mandato PAG §1.3.3 y §1.4.5). Pantalla nueva de F06, de SOLO LECTURA, que se abre desde el detalle de un gasto de la propiedad («Ver el movimiento en la cuenta») para ver el movimiento real (−750 si pagaste tu parte, −1.500 si pagaste todo): los movimientos de esa cuenta en orden cronológico, cada uno con el hecho al que está asociado, y el del gasto resaltado. Sin estado de punteo ni acciones de conciliación (el punteo es de un bloque propio de tesorería). No toca pantallas de F05; el acceso desde Cuentas va a otro bloque.
// Versión: 0.1.0 (F06 T2-F06 PAG N1)
// ============================================================

import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Respuesta } from '../api/cliente';
import type { MovimientosCuenta } from '../api/patrimonio_b3';
import { BotonTexto, EstadoDato } from '../components/Basicos';
import { CabeceraTarea, estilosFormulario as ef, Tarjeta } from '../components/Formulario';
import { diaMesAnioIso } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

export const TEXTO_SIN_MOVIMIENTOS = 'Esta cuenta no tiene movimientos.';

/** Importe firmado del movimiento («−750,00 €» si sale, «+…» si entra). */
export const importeMovimiento = (importe: string) => (importe.startsWith('-') ? `−${formatearEur(importe.slice(1))}` : `+${formatearEur(importe)}`);

export function MovimientosCuentaScreen(p: {
  cargar: (pagina: number) => Promise<Respuesta<MovimientosCuenta>>;
  /** Hecho cuyo movimiento se resalta (el gasto desde el que se abre). */
  resaltar?: string | null;
  onCerrar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [datos, setDatos] = useState<MovimientosCuenta | null>(null);
  const [error, setError] = useState(false);
  const [pagina, setPagina] = useState(0);
  useEffect(() => {
    setDatos(null);
    setError(false);
    void p.cargar(pagina).then((r) => (r.tipo === 'OK' ? setDatos(r.datos) : setError(true)));
  }, [pagina]);
  const movs = datos?.movimientos ?? [];
  return (
    <View testID="movimientos-cuenta" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={datos ? `Movimientos · ${datos.nombre}` : 'Movimientos de la cuenta'} testIDCancelar="movs-cerrar" onCancelar={p.onCerrar} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {error ? <EstadoDato testID="movs-error" estado="NO_DISPONIBLE" detalle="No se pudieron cargar los movimientos" /> : null}
        {!error && datos === null ? <EstadoDato testID="movs-cargando" estado="CARGANDO" /> : null}
        {datos && movs.length === 0 ? <Text testID="movs-vacio" style={[tipo.body, { color: c.textSecondary }]}>{TEXTO_SIN_MOVIMIENTOS}</Text> : null}
        {movs.length > 0 ? (
          <Tarjeta testID="movs-lista">
            {movs.map((m, i) => {
              const delGasto = !!p.resaltar && m.hechos.some((h) => h.hecho_id === p.resaltar);
              const concepto = m.hechos.map((h) => h.concepto ?? h.tipo_hecho).join(' · ') || m.descripcion || 'Movimiento';
              return (
                <View key={m.movimiento_id} testID={`movs-fila-${m.movimiento_id}`}
                  style={[s.fila, i < movs.length - 1 ? { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.borderDefault } : null]}>
                  <Text testID={`movs-fila-${m.movimiento_id}-concepto`} style={[delGasto ? tipo.bodyEmphasis : tipo.body, { color: c.textPrimary, flex: 1 }]}>
                    {`${delGasto ? '▶ ' : ''}${concepto}`}
                  </Text>
                  <Text style={[tipo.caption, { color: c.textSecondary }]}>{diaMesAnioIso(m.fecha)}</Text>
                  <Text testID={`movs-fila-${m.movimiento_id}-importe`} style={[tipo.body, { color: c.textPrimary }]}>{importeMovimiento(m.importe)}</Text>
                </View>
              );
            })}
          </Tarjeta>
        ) : null}
        <View style={{ flexDirection: 'row', gap: espacio.m }}>
          {pagina > 0 ? <BotonTexto testID="movs-anteriores" titulo="‹ Anteriores" onPress={() => setPagina(pagina - 1)} /> : null}
          {datos?.hay_mas ? <BotonTexto testID="movs-siguientes" titulo="Siguientes ›" onPress={() => setPagina(pagina + 1)} /> : null}
        </View>
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.s },
});
