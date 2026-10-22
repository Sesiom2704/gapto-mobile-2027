// ============================================================
// GAPTO MOBILE 2027
// Fichero: PendientesScreen.tsx
// Ruta: mobile/src/screens/PendientesScreen.tsx
// Descripción: Lista «Pendientes» (F05-06 M5 §B1; HOME-01 v0.4 I04; lámina PREV v0.2 B; D-PREV-10). Se abre desde la campana o «Ver todos». Arriba «Por pagar» y «Por cobrar» POR SEPARADO (nunca un total único; las transferencias no suman; «Desconocido» si solo hay importes desconocidos). Secciones «Vencidas», «Con pago parcial» y «Sin fecha» (vacía con el head físico vigente). Cada fila se toca para ver el detalle o se desliza para «Pagado» / «Cobrado» cuando lo admite. Carga y fallo con su estado; nunca «sin pendientes» si la lectura falla.
// Versión: 0.1.0 (F05-06 M5 §B1)
// Versión: 0.2.0 (F05-06 M5 SWIPE; regla de Moisés del 2026-10-22): deslizar una fila es una acción rápida con «Deshacer» cuando es inequívoca (useSwipePrevision › useAccionRapida); la fila sale mientras espera. Si falta algo, abre la hoja.
// Versión: 0.3.0 (F05-06 M5 SWIPE2; lámina SWIPE-01 v0.2): filas en tarjeta con los dos lados (derecha «Pagado» / «Cobrado», izquierda «No hubo» sin pagos enlazados).
// Versión: 0.4.0 (swipe (F05-06 M5 SWIPE3; lámina SWIPE-01 v0.3): lados `principal` / `alternativa` del componente común (principal a la izquierda); la raíz y el scroll cierran la fila abierta a medias (`propsZonaSwipe`, `propsScrollSwipe`).)
// Versión: 0.5.0 (F05-06 M5-B v1.1; HANDOFF_M5BM1 §6): al final, «Resueltas este mes» con su recuento, plegado por defecto. Cada fila dice cómo se resolvió («Pagada», «Cobrada», «Cubierta», «No hubo») y cuándo, y al tocarla abre el detalle (desde ahí, «Más › Reabrir»). Sin swipe en estas filas. No suma a «Por pagar» ni a «Por cobrar».
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { ClienteApi, FilaPrevision, FilaResuelta, PendientesPrevisiones } from '../api/cliente';
import { CabeceraNavegacion, EstadoDato } from '../components/Basicos';
import { FilaPrevisionVista } from '../components/Prevision';
import { propsScrollSwipe, propsZonaSwipe } from '../components/AccionRapida';
import { useSwipePrevision } from '../components/SwipePrevision';
import { admiteSwipe, lineaResuelta, textoNaturaleza } from '../domain/prevision';
import { formatearEur } from '../domain/importe';
import { useTema } from '../theme/tema';
import { espacio, importe as estiloImporte, TACTIL_MIN, tipo } from '../theme/tokens';

type Carga = { fase: 'CARGANDO' } | { fase: 'OK'; datos: PendientesPrevisiones } | { fase: 'ERROR' };

export function PendientesScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  refresco: number;
  onAtras: () => void;
  onDetalle: (fila: FilaPrevision) => void;
  onFormularioCompleto: (fila: FilaPrevision, importe: string | null) => void;
  onCambios: () => void;
}) {
  const { c } = useTema();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [resueltasAbiertas, setResueltasAbiertas] = useState(false);
  const cargar = useCallback(async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.pendientesPrevisiones();
    setCarga(r.tipo === 'OK' ? { fase: 'OK', datos: r.datos } : { fase: 'ERROR' });
  }, [p.cliente]);
  useEffect(() => {
    void cargar();
  }, [cargar, p.refresco]);
  const filas = carga.fase === 'OK' ? [...carga.datos.secciones.vencidas, ...carga.datos.secciones.con_pago_parcial, ...carga.datos.secciones.sin_fecha] : [];
  const swipe = useSwipePrevision({
    cliente: p.cliente, nuevoId: p.nuevoId, ahora: p.ahora, filas,
    onRegistrado: () => { p.onCambios(); return cargar(); },
    onFormularioCompleto: p.onFormularioCompleto,
  });

  const seccion = (titulo: string, todas: FilaPrevision[], clave: string) => {
    const filas = todas.filter((f) => !swipe.oculta(f.id));
    return filas.length === 0 ? null : (
      <View testID={`pendientes-${clave}`} style={{ gap: espacio.s }}>
        <Text accessibilityRole="header" style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{titulo}</Text>
        {filas.map((f, i) => (
          <FilaPrevisionVista key={f.id} testID={`pendiente-${f.id}`} fila={f} usarQueda ultima={i === filas.length - 1}
            onPress={() => p.onDetalle(f)} {...swipe.lados(f)} />
        ))}
      </View>
    );
  };

  const resuelta = (f: FilaResuelta, ultima: boolean) => (
    <Pressable key={f.id} testID={`resuelta-${f.id}`} accessibilityRole="button" accessibilityLabel={`${f.concepto}. ${lineaResuelta(f)}`}
      onPress={() => p.onDetalle(f)}
      style={({ pressed }) => [s.resuelta, !ultima && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }, { opacity: pressed ? 0.7 : 1 }]}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text numberOfLines={1} style={[tipo.body, { color: c.textPrimary }]}>{f.concepto}</Text>
        <Text testID={`resuelta-${f.id}-linea`} style={[tipo.caption, { color: c.textSecondary }]}>{lineaResuelta(f)}</Text>
      </View>
      {f.importe_esperado !== null ? (
        <Text style={[tipo.caption, { color: c.textSecondary, fontVariant: ['tabular-nums'] }]}>{formatearEur(f.importe_esperado)}</Text>
      ) : null}
    </Pressable>
  );
  const resueltas = (datos: PendientesPrevisiones) => {
    const r = datos.resueltas_mes;
    if (!r || r.n === 0) return null;
    return (
      <View testID="pendientes-resueltas" style={{ gap: espacio.s }}>
        <Pressable testID="resueltas-cabecera" accessibilityRole="button" accessibilityState={{ expanded: resueltasAbiertas }}
          accessibilityLabel={`Resueltas este mes, ${r.n}`} onPress={() => setResueltasAbiertas(!resueltasAbiertas)} style={s.cabecera}>
          <Text accessibilityRole="header" style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600', flex: 1 }]}>Resueltas este mes</Text>
          <Text testID="resueltas-recuento" style={[tipo.footnote, { color: c.textSecondary, fontVariant: ['tabular-nums'] }]}>{r.n}</Text>
          <Ionicons name={resueltasAbiertas ? 'chevron-up' : 'chevron-down'} size={16} color={c.textSecondary} />
        </Pressable>
        {resueltasAbiertas ? r.filas.map((f, i) => resuelta(f, i === r.filas.length - 1)) : null}
      </View>
    );
  };

  return (
    <View testID="pendientes" style={[s.raiz, { backgroundColor: c.background }]} {...propsZonaSwipe}>
      <CabeceraNavegacion titulo="Pendientes" atras={{ etiqueta: 'Inicio', onPress: p.onAtras }} testIDAtras="pendientes-atras" />
      <ScrollView {...propsScrollSwipe} contentContainerStyle={s.cuerpo} refreshControl={<RefreshControl refreshing={false} onRefresh={cargar} />}>
        {carga.fase === 'CARGANDO' ? <EstadoDato testID="pendientes-cargando" estado="CARGANDO" /> : null}
        {carga.fase === 'ERROR' ? (
          <Pressable testID="pendientes-error" accessibilityRole="button" onPress={cargar} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="No se pudieron cargar los pendientes. Tocar para reintentar" />
          </Pressable>
        ) : null}
        {carga.fase === 'OK' ? (
          <>
            <View style={s.naturalezas}>
              <View style={s.naturaleza}>
                <Text style={[tipo.footnote, { color: c.textSecondary }]}>Por pagar</Text>
                <Text testID="por-pagar" style={[estiloImporte.secondary, { color: c.textPrimary, fontVariant: ['tabular-nums'] }]}>{textoNaturaleza(carga.datos.por_pagar, 'POR_PAGAR')}</Text>
              </View>
              <View style={s.naturaleza}>
                <Text style={[tipo.footnote, { color: c.textSecondary }]}>Por cobrar</Text>
                <Text testID="por-cobrar" style={[estiloImporte.secondary, { color: c.textPrimary, fontVariant: ['tabular-nums'] }]}>{textoNaturaleza(carga.datos.por_cobrar, 'POR_COBRAR')}</Text>
              </View>
            </View>
            {carga.datos.n === 0 && carga.datos.secciones.sin_fecha.length === 0 ? (
              <Text testID="pendientes-vacio" style={[tipo.body, { color: c.textSecondary }]}>No hay nada pendiente.</Text>
            ) : null}
            {seccion('Vencidas', carga.datos.secciones.vencidas, 'vencidas')}
            {seccion('Con pago parcial', carga.datos.secciones.con_pago_parcial, 'parciales')}
            {seccion('Sin fecha', carga.datos.secciones.sin_fecha, 'sin-fecha')}
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>Desliza a la izquierda para «Pagado» o «Cobrado» y a la derecha para «No hubo»; o toca la fila para ver sus opciones.</Text>
            {resueltas(carga.datos)}
          </>
        ) : null}
      </ScrollView>
      {swipe.hoja}
      {swipe.avisos}
    </View>
  );
}

const s = StyleSheet.create({
  raiz: { flex: 1 },
  cuerpo: { padding: espacio.l, gap: espacio.l },
  naturalezas: { flexDirection: 'row', gap: espacio.l },
  naturaleza: { flex: 1, gap: espacio.xs },
  cabecera: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN },
  resuelta: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN, paddingVertical: espacio.xs },
});
