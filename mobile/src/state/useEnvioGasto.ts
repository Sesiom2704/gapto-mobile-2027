// ============================================================
// GAPTO MOBILE 2027
// Fichero: useEnvioGasto.ts
// Ruta: mobile/src/state/useEnvioGasto.ts
// Descripción: Máquina de estados del envío VS-01. Separa edición, envío, resultado confirmado por servidor e indeterminado. Reglas: (1) la identidad se genera ANTES de enviar y se sella con el payload; (2) doble tap no duplica (guarda síncrona); (3) ante timeout/red/5xx la intención queda INDETERMINADA: payload sellado inmutable y reintento con la MISMA identidad (UUID quemado, F05-00-A); (4) un RECHAZO definitivo (4xx) libera la edición y el siguiente envío usa identidad nueva; (5) no hay optimistic update: el éxito solo existe tras respuesta del servidor.
// v0.2.0 (F05-D003): la validación local recibe la fecha de hoy (fecha no futura) y un rechazo PROPUESTA_FINANCIACION_OBSOLETA se expone para recargar la propuesta.
// v0.3.0 (F05-03/F05-04 J2 §2.3; D-DYN-08): el mismo ciclo sirve al ingreso cobrado: con `tipo` INGRESO se valida con las reglas del ingreso, se sella con `sellarIngreso` y se envía a POST /v1/intenciones/ingreso-cobrado. GASTO (por defecto) no cambia.
// v0.3.1 (F05-03/F05-04 J3 §2.7): la nota del ingreso sale del borrador (campo «Nota»); el parámetro `nota` queda como fuente externa opcional.
// Versión: 0.3.1
// ============================================================

import { useCallback, useRef, useState } from 'react';

import type { ClienteApi, ResultadoRegistro, ResultadoRegistroTipo } from '../api/cliente';
import { Borrador, IntencionIngresoSellada, IntencionSellada, sellar, sellarIngreso, TipoConCategoria, validar } from '../domain/intencion';

/** Intención sellada del gasto (VS-01) o del ingreso (F05-04); `tipo` la distingue. */
export type Sellada = IntencionSellada | (IntencionIngresoSellada & { readonly ingreso: true });

export type EstadoEnvio =
  | { fase: 'EDITANDO' }
  | { fase: 'ENVIANDO'; sellada: IntencionSellada }
  | { fase: 'INDETERMINADO'; sellada: IntencionSellada; mensaje: string }
  | { fase: 'RECHAZADO'; codigo: string; mensaje: string }
  | { fase: 'CONFIRMADO'; sellada: IntencionSellada; resultado: ResultadoRegistro };

export function useEnvioGasto(cliente: ClienteApi, nuevoId: () => string, tipo: TipoConCategoria = 'GASTO', nota: () => string | null = () => null) {
  const [estado, setEstado] = useState<EstadoEnvio>({ fase: 'EDITANDO' });
  const enVuelo = useRef(false);
  const selladaRef = useRef<IntencionSellada | null>(null);

  const enviarSellada = useCallback(
    async (sellada: IntencionSellada) => {
      if (enVuelo.current) return; // doble tap: ignorado, nunca un segundo POST
      enVuelo.current = true;
      setEstado({ fase: 'ENVIANDO', sellada });
      try {
        const s2 = sellada as unknown as Sellada;
        const r = 'ingreso' in s2
          ? await cliente.registrarIngresoCobrado(s2.payload as never)
          : await cliente.registrarGastoPagado(sellada.payload);
        if (r.tipo === 'OK') {
          setEstado({ fase: 'CONFIRMADO', sellada, resultado: r.datos as ResultadoRegistro & Partial<ResultadoRegistroTipo> });
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
    async (b: Borrador, hoyIso: string) => {
      if (enVuelo.current) return {};
      if (selladaRef.current) {
        // Intención ya sellada e indeterminada: solo se puede reintentar tal cual.
        await enviarSellada(selladaRef.current);
        return {};
      }
      const errores = validar(b, hoyIso, tipo);
      if (Object.keys(errores).length > 0) return errores;
      // El ingreso viaja con su propio payload; la máquina de estados es la misma.
      const sellada: IntencionSellada =
        tipo === 'INGRESO' ? (Object.freeze({ ...sellarIngreso(b, nuevoId(), nota()), ingreso: true }) as unknown as IntencionSellada) : sellar(b, nuevoId());
      selladaRef.current = sellada;
      await enviarSellada(sellada);
      return {};
    },
    [enviarSellada, nuevoId, tipo, nota],
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
