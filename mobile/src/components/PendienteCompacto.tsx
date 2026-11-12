// ============================================================
// GAPTO MOBILE 2027
// Fichero: PendienteCompacto.tsx
// Ruta: mobile/src/components/PendienteCompacto.tsx
// Descripción: «Pendiente con <persona>» en pequeño (F06-M M-09; T1-F06 UX-1, TR1-05). LECTURA CERTIFICADA, sin cálculo: una sola llamada a GET /v1/terceros/{id}/pendiente (OP-20 de lectura, la misma de «Pendiente con X») y se pinta TAL CUAL: «Te debe» = `te_debe` y «Le debes» = `le_debes` de la respuesta (null = «Sin determinar»), y cada partida con su `saldo` literal, su concepto (`origenPosicion`) y su `origen_fecha`. Ordenar por fecha y recortar a las 3 más recientes es presentación; PROHIBIDO sumar, compensar, restar o recalcular importes en el cliente. Con `SIN_POSICIONES`, sin partidas o con error de lectura no se muestra nada (y nunca bloquea al que lo contiene). Sin escrituras. Al pulsarlo (o «Ver todo», con más de 3) se abre «Pendiente con X». Los textos largos (nombre, concepto) saltan de línea: no se truncan ni se salen de la tarjeta.
// Versión: 0.1.0 (F06 T1 UX-1 · M-09)
// ============================================================

import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { ClienteApi } from '../api/cliente';
import { diaMesAnioIso } from '../domain/fechas';
import { origenPosicion, textoSaldo, type PendienteConPersona, type PosicionPendiente } from '../domain/reparto';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

export const MAX_PARTIDAS_COMPACTO = 3;

/** Las partidas más recientes por `origen_fecha` (sin fecha, al final; empate: el orden del servidor). Solo ordena y recorta. */
export function partidasRecientes(posiciones: PosicionPendiente[], n: number = MAX_PARTIDAS_COMPACTO): PosicionPendiente[] {
  const conIndice = posiciones.map((x, i) => ({ x, i }));
  conIndice.sort((a, b) => {
    const fa = a.x.origen_fecha;
    const fb = b.x.origen_fecha;
    if (fa && fb && fa !== fb) return fa < fb ? 1 : -1;
    if (fa && !fb) return -1;
    if (!fa && fb) return 1;
    return a.i - b.i;
  });
  return conIndice.slice(0, n).map((y) => y.x);
}

/** ¿Hay algo que enseñar? Sin posiciones (SIN_POSICIONES o lista vacía) el componente no aparece. */
export function hayPendiente(p: PendienteConPersona): boolean {
  return p.neto_estado !== 'SIN_POSICIONES' && p.posiciones.length > 0;
}

type Carga = { fase: 'CARGANDO' } | { fase: 'OK'; p: PendienteConPersona } | { fase: 'NADA' };

export function PendienteCompacto(p: {
  cliente: Pick<ClienteApi, 'pendienteCon'>;
  terceroId: string;
  nombre: string;
  /** Abre «Pendiente con X». */
  onAbrir: () => void;
  /** testID de la tarjeta pulsable (por defecto `pendiente-compacto-<id>`). */
  testID?: string;
  /** Se avisa cuando se sabe si hay algo que enseñar (para que el contenedor ofrezca otro acceso si no). */
  onVisible?: (visible: boolean) => void;
}) {
  const { c } = useTema();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const base = `pendiente-compacto-${p.terceroId}`;

  useEffect(() => {
    let vivo = true;
    setCarga({ fase: 'CARGANDO' });
    (async () => {
      try {
        const r = await p.cliente.pendienteCon(p.terceroId);
        if (!vivo) return;
        const ok = r.tipo === 'OK' && hayPendiente(r.datos);
        setCarga(ok && r.tipo === 'OK' ? { fase: 'OK', p: r.datos } : { fase: 'NADA' });
        p.onVisible?.(ok);
      } catch {
        if (!vivo) return;
        setCarga({ fase: 'NADA' });
        p.onVisible?.(false);
      }
    })();
    return () => {
      vivo = false;
    };
  }, [p.terceroId]);

  if (carga.fase !== 'OK') return null;
  const d = carga.p;
  const visibles = partidasRecientes(d.posiciones);
  const masDeTres = d.posiciones.length > MAX_PARTIDAS_COMPACTO;

  return (
    <Pressable
      testID={p.testID ?? base}
      accessibilityRole="button"
      accessibilityLabel={`Pendiente con ${p.nombre}. Te debe ${textoSaldo(d.te_debe)}. Le debes ${textoSaldo(d.le_debes)}. Abre «Pendiente con ${p.nombre}».`}
      onPress={p.onAbrir}
      style={({ pressed }) => [s.tarjeta, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault, opacity: pressed ? 0.7 : 1 }]}
    >
      <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{`Pendiente con ${p.nombre}`}</Text>
      <View style={s.totales}>
        <View style={s.total}>
          <Text style={[tipo.caption, { color: c.textSecondary }]}>Te debe</Text>
          <Text testID={`${base}-te-debe`} style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{textoSaldo(d.te_debe)}</Text>
        </View>
        <View style={s.total}>
          <Text style={[tipo.caption, { color: c.textSecondary }]}>Le debes</Text>
          <Text testID={`${base}-le-debes`} style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{textoSaldo(d.le_debes)}</Text>
        </View>
      </View>
      {visibles.map((x) => (
        <View key={x.entidad_id} testID={`${base}-partida-${x.entidad_id}`} style={[s.partida, { borderTopColor: c.borderDefault }]}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={[tipo.footnote, { color: c.textPrimary }]}>{origenPosicion(x)}</Text>
            <Text style={[tipo.caption, { color: c.textSecondary }]}>
              {`${x.origen_fecha ? diaMesAnioIso(x.origen_fecha) : 'Sin fecha'} · ${x.tipo === 'DERECHO_COBRO' ? 'te debe' : 'le debes'}`}
            </Text>
          </View>
          <Text testID={`${base}-partida-${x.entidad_id}-saldo`} style={[tipo.footnote, { color: c.textPrimary, fontWeight: '600' }]}>{textoSaldo(x.saldo)}</Text>
        </View>
      ))}
      {masDeTres ? (
        <Text testID={`${base}-ver-todo`} style={[tipo.footnote, { color: c.accentText, fontWeight: '600' }]}>Ver todo</Text>
      ) : null}
    </Pressable>
  );
}

const s = StyleSheet.create({
  tarjeta: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radio.m, padding: espacio.m, gap: espacio.s, minHeight: TACTIL_MIN },
  totales: { flexDirection: 'row', gap: espacio.l },
  total: { gap: 2 },
  partida: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, borderTopWidth: StyleSheet.hairlineWidth, paddingTop: espacio.xs },
});
