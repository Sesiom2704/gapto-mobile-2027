// ============================================================
// GAPTO MOBILE 2027
// Fichero: RecordarAfinidad.tsx
// Ruta: mobile/src/components/RecordarAfinidad.tsx
// Descripción: Tarjeta «¿Recordar <categoría> para <tercero>?» de la pantalla de éxito (F05 §49.4 A5, D-SRCH-05; lámina SRCH-ACT-AFI A5). Aparece solo si el registro tiene tercero y categoría y esa pareja aún no está guardada (lo consulta al servidor; si la consulta falla, no se ofrece). Es una escritura INDEPENDIENTE del hecho: si falla, el gasto ya está guardado. El UUID de la afinidad se fija al montar: el reintento y el doble toque reutilizan el MISMO (idempotente; con el par ya guardado, AFINIDAD_YA_EXISTE también es éxito). Nunca elige la categoría: solo se sugerirá primero (C01).
// Versión: 0.1.0 (F05-05 K3 §2.4)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { ClienteApi } from '../api/cliente';
import { useTema } from '../theme/tema';
import { espacio, radio, tipo } from '../theme/tokens';
import { BotonTexto } from './Basicos';

type Estado = 'COMPROBANDO' | 'OFRECER' | 'GUARDANDO' | 'GUARDADA' | 'NADA' | { error: string };

export function RecordarAfinidad(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  fecha: string;
  tercero: { id: string; nombre: string };
  categoria: { id: string; nombre: string };
}) {
  const { c } = useTema();
  const [estado, setEstado] = useState<Estado>('COMPROBANDO');
  const id = useRef<string>(p.nuevoId());

  useEffect(() => {
    let vivo = true;
    void (async () => {
      const r = await p.cliente.afinidadesTercero(p.tercero.id, p.fecha);
      if (!vivo) return;
      if (r.tipo !== 'OK') return setEstado('NADA');
      setEstado(r.datos.guardadas.some((g) => g.categoria_id === p.categoria.id) ? 'NADA' : 'OFRECER');
    })();
    return () => {
      vivo = false;
    };
  }, []);

  const recordar = async () => {
    if (estado === 'GUARDANDO' || estado === 'GUARDADA') return;
    setEstado('GUARDANDO');
    const r = await p.cliente.altaAfinidad({ id: id.current, tercero_id: p.tercero.id, categoria_id: p.categoria.id });
    if (r.tipo === 'OK') return setEstado('GUARDADA');
    setEstado({
      error: r.tipo === 'INDETERMINADO' ? 'No se ha podido confirmar. Vuelve a intentarlo: no se duplicará.' : r.mensaje,
    });
  };

  if (estado === 'COMPROBANDO' || estado === 'NADA') return null;
  return (
    <View testID="recordar-afinidad" style={[s.tarjeta, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault }]}>
      {estado === 'GUARDADA' ? (
        <Text testID="recordar-hecho" accessibilityLiveRegion="polite" style={[tipo.subheadline, { color: c.textPrimary }]}>
          {`Hecho: se sugerirá primero cuando elijas ${p.tercero.nombre}.`}
        </Text>
      ) : (
        <>
          <Text accessibilityRole="header" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>
            {`¿Recordar ${p.categoria.nombre} para ${p.tercero.nombre}?`}
          </Text>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>
            {`Se sugerirá primero cuando elijas ${p.tercero.nombre}. Nunca se elegirá sola.`}
          </Text>
          {typeof estado === 'object' ? (
            <Text testID="recordar-error" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{estado.error}</Text>
          ) : null}
          <BotonTexto testID="recordar" titulo={estado === 'GUARDANDO' ? 'Guardando…' : 'Recordar'} onPress={() => void recordar()} />
        </>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  tarjeta: { borderRadius: radio.m, borderWidth: StyleSheet.hairlineWidth, padding: espacio.m, gap: espacio.xs },
});
