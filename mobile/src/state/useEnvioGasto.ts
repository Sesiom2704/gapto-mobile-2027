// ============================================================
// GAPTO MOBILE 2027
// Fichero: useEnvioGasto.ts
// Ruta: mobile/src/state/useEnvioGasto.ts
// Descripción: Máquina de estados del envío VS-01. Separa edición, envío, resultado confirmado por servidor e indeterminado. Reglas: (1) la identidad se genera ANTES de enviar y se sella con el payload; (2) doble tap no duplica (guarda síncrona); (3) ante timeout/red/5xx la intención queda INDETERMINADA: payload sellado inmutable y reintento con la MISMA identidad (UUID quemado, F05-00-A); (4) un RECHAZO definitivo (4xx) libera la edición y el siguiente envío usa identidad nueva; (5) no hay optimistic update: el éxito solo existe tras respuesta del servidor.
// Versión: 0.1.0
// ============================================================

import { useCallback, useRef, useState } from 'react';

import type { ClienteApi, ResultadoRegistro } from '../api/cliente';
import { Borrador, IntencionSellada, sellar, validar } from '../domain/intencion';

export type EstadoEnvio =
  | { fase: 'EDITANDO' }
  | { fase: 'ENVIANDO'; sellada: IntencionSellada }
  | { fase: 'INDETERMINADO'; sellada: IntencionSellada; mensaje: string }
  | { fase: 'RECHAZADO'; codigo: string; mensaje: string }
  | { fase: 'CONFIRMADO'; sellada: IntencionSellada; resultado: ResultadoRegistro };

export function useEnvioGasto(cliente: ClienteApi, nuevoId: () => string) {
  const [estado, setEstado] = useState<EstadoEnvio>({ fase: 'EDITANDO' });
  const enVuelo = useRef(false);
  const selladaRef = useRef<IntencionSellada | null>(null);

  const enviarSellada = useCallback(
    async (sellada: IntencionSellada) => {
      if (enVuelo.current) return; // doble tap: ignorado, nunca un segundo POST
      enVuelo.current = true;
      setEstado({ fase: 'ENVIANDO', sellada });
      try {
        const r = await cliente.registrarGastoPagado(sellada.payload);
        if (r.tipo === 'OK') {
          setEstado({ fase: 'CONFIRMADO', sellada, resultado: r.datos });
        } else if (r.tipo === 'RECHAZADO') {
          selladaRef.current = null; // definitivo: la identidad no se reutiliza para otra intención
          setEstado({ fase: 'RECHAZADO', codigo: r.codigo, mensaje: r.mensaje });
        } else {
          setEstado({ fase: 'INDETERMINADO', sellada, mensaje: r.mensaje });
        }
      } finally {
        enVuelo.current = false;
      }
    },
    [cliente],
  );

  /** Primer envío desde el borrador. Devuelve errores de validación local si los hay. */
  const enviar = useCallback(
    async (b: Borrador) => {
      if (enVuelo.current) return {};
      if (selladaRef.current) {
        // Intención ya sellada e indeterminada: solo se puede reintentar tal cual.
        await enviarSellada(selladaRef.current);
        return {};
      }
      const errores = validar(b);
      if (Object.keys(errores).length > 0) return errores;
      const sellada = sellar(b, nuevoId());
      selladaRef.current = sellada;
      await enviarSellada(sellada);
      return {};
    },
    [enviarSellada, nuevoId],
  );

  const reintentar = useCallback(async () => {
    if (selladaRef.current) await enviarSellada(selladaRef.current);
  }, [enviarSellada]);

  const volverAEditar = useCallback(() => {
    // Solo tras rechazo definitivo; en INDETERMINADO la intención sigue sellada.
    if (!selladaRef.current) setEstado({ fase: 'EDITANDO' });
  }, []);

  return { estado, enviar, reintentar, volverAEditar };
}
