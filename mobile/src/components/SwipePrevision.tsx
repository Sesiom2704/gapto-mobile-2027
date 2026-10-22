// ============================================================
// GAPTO MOBILE 2027
// Fichero: SwipePrevision.tsx
// Ruta: mobile/src/components/SwipePrevision.tsx
// Descripción: Swipe «Pagado» / «Cobrado» de una fila de previsión (F05-06 M5 §B1; lámina PREV v0.2 B1; D-PREV-08/12; DAY-RULE-03), compartido por Inicio y «Pendientes». El gesto solo ABRE la hoja: resumen (previsión, esperado, consecuencia «Quedará cubierta»), importe real propuesto y marcado «Revisa», cuenta prevista y fecha (la prevista si ya pasó, si no hoy). «Confirmar pago y cubrir» registra con OP-22 y `marcar_realizada = true`: es la declaración explícita. «Abrir el formulario completo» lleva al registro desde la previsión con el importe escrito. Un envío sin respuesta se reintenta con la MISMA identidad.
// Versión: 0.1.0 (F05-06 M5 §B1)
// Versión: 0.2.0 (F05-06 M5 SWIPE; regla de Moisés del 2026-10-22, sustituye a DAY-RULE-03 y D-PREV-08/12 en lo que contradigan): el swipe es una acción rápida de un solo gesto cuando `planRapidoPrevision` lo admite (esperado conocido, EUR, una sola cuenta prevista con la capacidad de hoy, sin realidad previa): la fila sale, el aviso «<Nombre> pagada/cobrada · Deshacer» dura 5 s y después se registra el esperado en la cuenta prevista con fecha de hoy y `marcar_realizada = true`, por la misma ruta y el mismo bloque `prevision` que la hoja (useAccionRapida). Las capacidades se leen al cargar las filas, para que el gesto y «Deshacer» no toquen el servidor. Si falta algo o no se pudieron leer, el gesto abre la hoja de siempre.
// ============================================================

import React, { useCallback, useEffect, useState } from 'react';

import type { ClienteApi, FilaPrevision, Respuesta } from '../api/cliente';
import { diaMesIso, isoLocal } from '../domain/fechas';
import { parsearImporte } from '../domain/importe';
import { admiteSwipe, componerRegistro, planRapidoPrevision, textoAvisoRapido, textoEditable, type CapacidadesHoy } from '../domain/prevision';
import { useAccionRapida } from './AccionRapida';
import { HojaSwipe, usarIntencion } from './Prevision';

export function useSwipePrevision(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  /** Filas visibles: con ellas se leen las capacidades de hoy antes de cualquier gesto. */
  filas: FilaPrevision[];
  onRegistrado: () => void | Promise<void>;
  onFormularioCompleto: (fila: FilaPrevision, importe: string | null) => void;
}) {
  const [fila, setFila] = useState<FilaPrevision | null>(null);
  const [importeTexto, setImporteTexto] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intencion = usarIntencion(p.nuevoId);
  const hoy = isoLocal(p.ahora());
  const [capacidades, setCapacidades] = useState<CapacidadesHoy | null>(null);
  const rapida = useAccionRapida({ nuevoId: p.nuevoId, onHecha: () => p.onRegistrado() });

  // Capacidades de hoy de las cuentas previstas, leídas con las filas (nunca en el gesto ni en «Deshacer»).
  const conGesto = p.filas.filter(admiteSwipe);
  const hayGasto = conGesto.some((f) => f.tipo === 'GASTO');
  const hayIngreso = conGesto.some((f) => f.tipo === 'INGRESO');
  const claveFilas = conGesto.map((f) => `${f.id}:${f.row_version}`).join('|');
  useEffect(() => {
    let vigente = true;
    setCapacidades(null);
    if (!hayGasto && !hayIngreso) return;
    void (async () => {
      try {
        const [pg, ig] = await Promise.all([
          hayGasto ? p.cliente.cuentasPago(hoy) : Promise.resolve(null),
          hayIngreso ? p.cliente.cuentasElegibles('INGRESO', hoy) : Promise.resolve(null),
        ]);
        if (vigente) setCapacidades({ pago: pg?.tipo === 'OK' ? pg.datos.cuentas : null, ingreso: ig?.tipo === 'OK' ? ig.datos.cuentas : null });
      } catch {
        if (vigente) setCapacidades(null);
      }
    })();
    return () => {
      vigente = false;
    };
  }, [claveFilas, hoy, p.cliente]);

  const abrir = useCallback((f: FilaPrevision) => {
    intencion.liberar();
    setFila(f);
    setImporteTexto(textoEditable(f.importe_esperado));
    setError(null);
  }, [intencion]);

  /** Gesto o acción accesible: acción rápida si es inequívoca; si no, la hoja. */
  const deslizar = (f: FilaPrevision) => {
    const plan = planRapidoPrevision(f, capacidades, hoy);
    if (!plan) return abrir(f);
    rapida.lanzar({
      clave: f.id,
      texto: textoAvisoRapido(f),
      enviar: async (id) => {
        const r = componerRegistro(f, plan, id);
        if (!r) return { tipo: 'RECHAZADO', codigo: 'INCOMPLETO', mensaje: 'Faltan datos: ábrelo y regístralo desde el formulario.' };
        return r.ruta === 'INGRESO' ? p.cliente.registrarIngresoCobrado(r.payload as never) : p.cliente.registrarGastoPagado(r.payload as never);
      },
    });
  };

  const cerrar = () => setFila(null);
  const fecha = fila && fila.fecha_hasta && fila.fecha_hasta < hoy ? fila.fecha_hasta : hoy;
  const cuenta = fila ? (fila.tipo === 'INGRESO' ? fila.cuenta_entrada : fila.cuenta_salida) : null;

  const confirmar = async () => {
    if (!fila || !cuenta) return;
    const imp = parsearImporte(importeTexto);
    if (!imp.ok) return setError('Revisa el importe real.');
    setEnviando(true);
    setError(null);
    let self100 = false;
    if (fila.tipo === 'GASTO') {
      const cs = await p.cliente.cuentasPago(fecha);
      self100 = cs.tipo === 'OK' && cs.datos.cuentas.some((x) => x.cuenta_id === cuenta.id && x.propuesta_financiacion === 'SELF_100');
    }
    const r = componerRegistro(fila, {
      importe: imp.valor, fecha, cuentaId: cuenta.id, cuentaDestinoId: null, presupuestable: fila.presupuestable,
      conCategoria: !!fila.categoria, propuestaSelf100: self100, marcar: true,
    }, intencion.actual());
    if (!r) return setEnviando(false);
    const res: Respuesta<unknown> = r.ruta === 'INGRESO'
      ? await p.cliente.registrarIngresoCobrado(r.payload as never)
      : await p.cliente.registrarGastoPagado(r.payload as never);
    setEnviando(false);
    if (res.tipo === 'OK') {
      intencion.liberar();
      setFila(null);
      return p.onRegistrado();
    }
    if (res.tipo === 'INDETERMINADO') return setError(`${res.mensaje}`);
    intencion.liberar();
    setError(res.mensaje);
  };

  const hoja = fila ? (
    <HojaSwipe
      fila={fila}
      importeTexto={importeTexto}
      onImporte={setImporteTexto}
      cuenta={cuenta}
      fecha={fecha}
      fechaTexto={diaMesIso(fecha)}
      enviando={enviando}
      error={error}
      onConfirmar={confirmar}
      onFormularioCompleto={() => {
        const imp = parsearImporte(importeTexto);
        const f = fila;
        setFila(null);
        p.onFormularioCompleto(f, imp.ok ? textoEditable(imp.valor) : null);
      }}
      onCerrar={cerrar}
    />
  ) : null;
  return { abrir, deslizar, oculta: rapida.oculta, avisos: rapida.avisos, hoja };
}
