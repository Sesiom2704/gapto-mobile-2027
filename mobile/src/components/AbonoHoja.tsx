// ============================================================
// GAPTO MOBILE 2027
// Fichero: AbonoHoja.tsx
// Ruta: mobile/src/components/AbonoHoja.tsx
// Descripción: «Registrar abono» de una devolución pendiente (F05-06 M2-B §B1; lámina DEV B2, D-DEV-07, P-DEV-04; DAY-RULE-03). Hoja «¿Llegó el abono?» con la devolución y su importe, la cuenta (propuesta la de la compra si sigue pudiendo pagar gastos, P-DEV-02; «Otra cuenta» con las que pueden pagar gastos, PAGAR_GASTO) y la fecha (Hoy · Ayer · Otra fecha, nunca futura): siempre con confirmación consciente de cuenta y fecha, también desde el swipe «Cobrado». El importe es el de la devolución: «¿Llegó otro importe o en varias veces? Abrir el formulario completo» explica que eso no es este abono (no se cambia la devolución aquí). Mismo ciclo de envío que el registro (UUID sellado, doble toque ignorado, INDETERMINADO reintenta la MISMA identidad; YA_CONCILIADO y CUENTA_SIN_CAPACIDAD con el mensaje del servidor).
// Versión: 0.1.0 (F05-06 M2-B §B1)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { Text, TextInput, View } from 'react-native';

import type { ClienteApi, CuentaElegible, PayloadAbono } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from './Basicos';
import { BotonSecundario } from './SelectorCategorias';
import { Hoja } from './HojasCategoria';
import { ayer, ddmmaaaaAIso, fechaCortaIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

type Lista = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: CuentaElegible[] };
type Estado =
  | { fase: 'EDITANDO' }
  | { fase: 'ENVIANDO'; payload: PayloadAbono }
  | { fase: 'INDETERMINADO'; payload: PayloadAbono; mensaje: string }
  | { fase: 'RECHAZADO'; codigo: string; mensaje: string };

export const TEXTO_OTRO_IMPORTE =
  'Un abono por otro importe o en varias veces no es este abono: la devolución no cambia aquí. Si te devolvieron menos, registra el abono cuando llegue completo; si te abonaron más, la diferencia no es una devolución.';

export function AbonoHoja(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  devolucion: { id: string; titulo: string; importe: string; origenId: string };
  onCerrar: (registrado: boolean) => void;
}) {
  const { c } = useTema();
  const hoyIso = isoLocal(p.ahora());
  const ayerIso = isoLocal(ayer(p.ahora()));
  const [fecha, setFecha] = useState(hoyIso);
  const [otraFecha, setOtraFecha] = useState<string | null>(null);
  const [propuesta, setPropuesta] = useState<{ cuenta_id: string; nombre: string } | null>(null);
  const [cuentas, setCuentas] = useState<Lista>({ fase: 'CARGANDO' });
  const [cuenta, setCuenta] = useState<string | null>(null);
  const [otra, setOtra] = useState(false);
  const [completo, setCompleto] = useState(false);
  const [estado, setEstado] = useState<Estado>({ fase: 'EDITANDO' });
  const enVuelo = useRef(false);
  const sellada = useRef<PayloadAbono | null>(null);

  useEffect(() => {
    void (async () => {
      const r = await p.cliente.contextoDevolucion(p.devolucion.origenId);
      if (r.tipo === 'OK') setPropuesta(r.datos.cuenta_compra);
    })();
  }, [p.devolucion.origenId]);
  const cargarCuentas = async (f: string) => {
    setCuentas({ fase: 'CARGANDO' });
    const r = await p.cliente.cuentasElegibles('GASTO', f); // PAGAR_GASTO: el medio con que se pagan gastos
    const l: Lista = r.tipo === 'OK' ? { fase: 'OK', lista: r.datos.cuentas } : { fase: 'ERROR' };
    setCuentas(l);
    if (l.fase === 'OK') setCuenta((x) => (x && l.lista.some((y) => y.cuenta_id === x) ? x : null));
  };
  useEffect(() => {
    if (esFechaIso(fecha) && fecha <= hoyIso) void cargarCuentas(fecha);
  }, [fecha]);

  const propuestaElegible = !!propuesta && cuentas.fase === 'OK' && cuentas.lista.some((x) => x.cuenta_id === propuesta.cuenta_id);
  // P-DEV-02: la cuenta de la compra viene propuesta, visible y cambiable.
  useEffect(() => {
    if (propuestaElegible && cuenta === null && !otra) setCuenta(propuesta!.cuenta_id);
  }, [propuestaElegible]);
  const bloqueado = estado.fase === 'ENVIANDO' || estado.fase === 'INDETERMINADO';
  const fechaOk = esFechaIso(fecha) && fecha <= hoyIso;
  const listo = !!cuenta && fechaOk;
  const editar = (f: () => void) => {
    if (bloqueado) return;
    if (estado.fase === 'RECHAZADO') setEstado({ fase: 'EDITANDO' });
    sellada.current = null;
    f();
  };

  const enviar = async (payload: PayloadAbono) => {
    if (enVuelo.current) return;
    enVuelo.current = true;
    setEstado({ fase: 'ENVIANDO', payload });
    try {
      const r = await p.cliente.registrarAbono(p.devolucion.id, payload);
      if (r.tipo === 'OK') return p.onCerrar(true);
      if (r.tipo === 'RECHAZADO') {
        sellada.current = null;
        setEstado({ fase: 'RECHAZADO', codigo: r.codigo, mensaje: r.mensaje });
        if (r.codigo === 'CUENTA_SIN_CAPACIDAD') void cargarCuentas(payload.fecha);
      } else setEstado({ fase: 'INDETERMINADO', payload, mensaje: r.mensaje });
    } finally {
      enVuelo.current = false;
    }
  };
  const confirmar = () => {
    if (!listo || enVuelo.current) return;
    const payload = sellada.current ?? Object.freeze({ intencion_id: p.nuevoId(), cuenta_id: cuenta!, fecha });
    sellada.current = payload;
    void enviar(payload);
  };

  const elegibles = cuentas.fase === 'OK' ? cuentas.lista.filter((x) => otra || completo || x.cuenta_id !== propuesta?.cuenta_id) : [];
  return (
    <Hoja titulo="¿Llegó el abono?" testID="hoja-abono">
      <Text testID="abono-devolucion" style={[tipo.subheadline, { color: c.textSecondary }]}>{`Devolución de ${p.devolucion.titulo} · ${formatearEur(p.devolucion.importe)}`}</Text>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Cuenta</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s }}>
        {propuestaElegible ? (
          <Chip testID="abono-cuenta-compra" etiqueta={propuesta!.nombre} seleccionado={!otra && cuenta === propuesta!.cuenta_id}
            onPress={() => editar(() => { setOtra(false); setCuenta(propuesta!.cuenta_id); })} />
        ) : null}
        <Chip testID="abono-otra-cuenta" etiqueta="Otra cuenta" seleccionado={otra} onPress={() => editar(() => { setOtra(true); setCuenta(null); })} />
      </View>
      {otra || completo ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s }}>
          {cuentas.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
          {cuentas.fase === 'ERROR' ? <EstadoDato estado="ERROR_CARGA" detalle="No se han podido cargar las cuentas." /> : null}
          {elegibles.map((x) => (
            <Chip key={x.cuenta_id} testID={`abono-cuenta-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={cuenta === x.cuenta_id}
              onPress={() => editar(() => setCuenta(x.cuenta_id))} />
          ))}
        </View>
      ) : null}
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Fecha del abono</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s }}>
        <Chip testID="abono-fecha-hoy" etiqueta="Hoy" seleccionado={otraFecha === null && fecha === hoyIso} onPress={() => editar(() => { setOtraFecha(null); setFecha(hoyIso); })} />
        <Chip testID="abono-fecha-ayer" etiqueta="Ayer" seleccionado={otraFecha === null && fecha === ayerIso} onPress={() => editar(() => { setOtraFecha(null); setFecha(ayerIso); })} />
        <Chip testID="abono-fecha-otra" etiqueta="Otra fecha" seleccionado={otraFecha !== null} onPress={() => editar(() => setOtraFecha(isoADdmmaaaa(fecha)))} />
      </View>
      {otraFecha !== null ? (
        <TextInput testID="abono-campo-fecha" accessibilityLabel="Fecha del abono, día barra mes barra año" value={otraFecha}
          onChangeText={(t) => editar(() => { setOtraFecha(t); setFecha(ddmmaaaaAIso(t) ?? t); })} placeholder="dd/mm/aaaa"
          placeholderTextColor={c.textSecondary} inputMode="numeric" maxLength={10}
          style={[tipo.body, { color: c.textPrimary, backgroundColor: c.surfaceSecondary, borderRadius: radio.m, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN }]} />
      ) : null}
      <Text testID="abono-fecha" style={[tipo.footnote, { color: c.textSecondary }]}>
        {esFechaIso(fecha) ? (fecha > hoyIso ? 'La fecha no puede ser futura.' : fechaCortaIso(fecha)) : 'Escribe la fecha como dd/mm/aaaa.'}
      </Text>
      {completo ? (
        <Text testID="abono-otro-importe" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_OTRO_IMPORTE}</Text>
      ) : (
        <BotonTexto testID="abono-formulario-completo" titulo="¿Llegó otro importe o en varias veces? Abrir el formulario completo" onPress={() => setCompleto(true)} />
      )}
      {estado.fase === 'RECHAZADO' ? (
        <Text testID="abono-error" accessibilityRole="alert" style={[tipo.subheadline, { color: c.critical }]}>{estado.mensaje}</Text>
      ) : null}
      {estado.fase === 'INDETERMINADO' ? (
        <Text testID="abono-indeterminado" accessibilityRole="alert" style={[tipo.subheadline, { color: c.textPrimary }]}>{estado.mensaje}</Text>
      ) : null}
      {estado.fase === 'INDETERMINADO' ? (
        <BotonPrimario testID="abono-reintentar" titulo="Reintentar" onPress={() => void enviar(estado.payload)} />
      ) : (
        <BotonPrimario testID="abono-confirmar" titulo={estado.fase === 'ENVIANDO' ? 'Guardando…' : `Confirmar abono de ${formatearEur(p.devolucion.importe)}`}
          cargando={estado.fase === 'ENVIANDO'} deshabilitado={!listo} onPress={confirmar} />
      )}
      <BotonSecundario testID="abono-cancelar" titulo="Cancelar" onPress={() => (estado.fase === 'ENVIANDO' ? undefined : p.onCerrar(false))} />
    </Hoja>
  );
}
