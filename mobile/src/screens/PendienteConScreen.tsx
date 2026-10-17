// ============================================================
// GAPTO MOBILE 2027
// Fichero: PendienteConScreen.tsx
// Ruta: mobile/src/screens/PendienteConScreen.tsx
// Descripción: «Pendiente con <persona>» y cómo se salda (F05-06 M3; lámina REP v0.2 C1–C4, D2, E2, E8). C1: lo que te debe y lo que le debes por separado, cada cosa con su origen; el neto es un dato secundario que «no salda nada» (D-REP-07, OP-20); sin «Compensar» (P-REP-02, opción A). C4: con algún saldo desconocido el neto es «Sin determinar», nunca 0,00 € (D-REP-09). C2: sobre una posición, «Registrar cobro» (derecho) o «Registrar pago» (obligación) y, aparte, «Perdonar», que no mueve dinero (D-REP-08, F04-D052). C3/E8: importe (parcial permitido, sin superar lo pendiente), cuenta Gapto obligatoria (Efectivo incluido; las que pueden recibir o pagar dinero) y fecha; dice que no es un ingreso ni un gasto nuevo, y que pagar tu deuda por un tercero no está disponible. Mismo ciclo de envío que el registro: identidad sellada antes de enviar, doble toque ignorado, INDETERMINADO reintenta la MISMA identidad, rechazo definitivo libera la edición. Al terminar se recarga la lista.
// Versión: 0.1.0 (F05-06 M3 §B1)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaElegible } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { Aviso, Bloque, CabeceraTarea, Campo, Inicial, s } from '../components/Reparto';
import { ayer, ddmmaaaaAIso, diaMesIso, fechaCortaIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import {
  activasDe,
  faltaCobroPago,
  motivoRechazoPosicion,
  origenPosicion,
  PendienteConPersona,
  PosicionPendiente,
  ResultadoPosicion,
  TEXTO_ACCIONES,
  TEXTO_ACCIONES_OBLIGACION,
  TEXTO_NO_ES_GASTO,
  TEXTO_NO_ES_INGRESO,
  TEXTO_PAT08,
  TEXTO_PERDONAR,
  TEXTO_SIN_TERCERO_PAGA,
  textoDe,
  textoNeto,
  textoSaldo,
} from '../domain/reparto';
import { useTema } from '../theme/tema';
import { espacio, importe, tipo } from '../theme/tokens';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; p: PendienteConPersona };
type Accion = 'COBRO' | 'PAGO' | 'PERDON';
type Envio =
  | { fase: 'EDITANDO' }
  | { fase: 'ENVIANDO'; id: string }
  | { fase: 'INDETERMINADO'; id: string; mensaje: string }
  | { fase: 'RECHAZADO'; mensaje: string }
  | { fase: 'CONFIRMADO'; resultado: ResultadoPosicion };

export function PendienteConScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  terceroId: string;
  nombre: string;
  /** Vuelve atrás; `cambios`: se registró algo. */
  onCerrar: (cambios: boolean) => void;
  onVerHecho?: (hechoId: string) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoy = p.ahora();
  const hoyIso = isoLocal(hoy);
  const ayerIso = isoLocal(ayer(hoy));
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [sel, setSel] = useState<PosicionPendiente | null>(null);
  const [accion, setAccion] = useState<Accion | null>(null);
  const [importeTexto, setImporte] = useState('');
  const [cuentaId, setCuenta] = useState<string | null>(null);
  const [fecha, setFecha] = useState(hoyIso);
  const [otraFecha, setOtraFecha] = useState<string | null>(null);
  const [cuentas, setCuentas] = useState<{ fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: CuentaElegible[] }>({ fase: 'CARGANDO' });
  const [envio, setEnvio] = useState<Envio>({ fase: 'EDITANDO' });
  const [cambios, setCambios] = useState(false);
  const enVuelo = useRef(false);
  const sellada = useRef<string | null>(null);

  const cargar = async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.pendienteCon(p.terceroId);
    setCarga(r.tipo === 'OK' ? { fase: 'OK', p: r.datos } : { fase: 'ERROR' });
  };
  useEffect(() => {
    void cargar();
  }, [p.terceroId]);
  const cargarCuentas = async (a: Accion, f: string) => {
    setCuentas({ fase: 'CARGANDO' });
    // El cobro entra dinero (RECIBIR_INGRESO); el pago sale (PAGAR_GASTO). Ninguno es un ingreso ni un gasto nuevo.
    const r = await p.cliente.cuentasElegibles(a === 'COBRO' ? 'INGRESO' : 'GASTO', f);
    setCuentas(r.tipo === 'OK' ? { fase: 'OK', lista: r.datos.cuentas } : { fase: 'ERROR' });
    if (r.tipo === 'OK') setCuenta((x) => (x && r.datos.cuentas.some((y) => y.cuenta_id === x) ? x : null));
  };
  useEffect(() => {
    if (accion && accion !== 'PERDON' && esFechaIso(fecha) && fecha <= hoyIso) void cargarCuentas(accion, fecha);
  }, [accion, fecha]);

  const bloqueado = envio.fase === 'ENVIANDO' || envio.fase === 'INDETERMINADO';
  const editar = (f: () => void) => {
    if (bloqueado) return;
    sellada.current = null;
    if (envio.fase === 'RECHAZADO') setEnvio({ fase: 'EDITANDO' });
    f();
  };
  const abrirAccion = (a: Accion, x: PosicionPendiente) => {
    setAccion(a);
    setImporte(x.saldo ? textoDe(x.saldo) : '');
    setCuenta(null);
    setFecha(hoyIso);
    setOtraFecha(null);
    sellada.current = null;
    setEnvio({ fase: 'EDITANDO' });
  };
  const cerrarAccion = () => {
    setAccion(null);
    setSel(null);
    setEnvio({ fase: 'EDITANDO' });
  };

  const enviar = async () => {
    if (enVuelo.current || !sel || !accion) return;
    const imp = parsearImporte(importeTexto);
    if (!imp.ok) return;
    if (!sellada.current) sellada.current = p.nuevoId();
    const id = sellada.current;
    enVuelo.current = true;
    setEnvio({ fase: 'ENVIANDO', id });
    try {
      const r =
        accion === 'PERDON'
          ? await p.cliente.perdonarPosicion(sel.entidad_id, { intencion_id: id, importe: imp.valor, fecha })
          : await (accion === 'COBRO' ? p.cliente.cobrarPosicion : p.cliente.pagarPosicion)(sel.entidad_id, { intencion_id: id, importe: imp.valor, cuenta_id: cuentaId!, fecha });
      if (r.tipo === 'OK') {
        setCambios(true);
        setEnvio({ fase: 'CONFIRMADO', resultado: r.datos });
        void cargar();
      } else if (r.tipo === 'RECHAZADO') {
        sellada.current = null;
        setEnvio({ fase: 'RECHAZADO', mensaje: motivoRechazoPosicion(r.codigo) });
        if (r.codigo === 'CUENTA_SIN_CAPACIDAD') {
          setCuenta(null);
          void cargarCuentas(accion, fecha);
        }
        if (r.codigo.startsWith('EXCEDE') || r.codigo === 'POSICION_CERRADA') void cargar();
      } else setEnvio({ fase: 'INDETERMINADO', id, mensaje: r.mensaje });
    } finally {
      enVuelo.current = false;
    }
  };

  const nombre = carga.fase === 'OK' ? carga.p.nombre : p.nombre;
  const origen = (x: PosicionPendiente) =>
    [origenPosicion(x), x.origen_fecha ? diaMesIso(x.origen_fecha) : null].filter(Boolean).join(' · ');

  // ---------------------------------------------------------------- C3/E8 cobro, pago y perdón
  if (sel && accion) {
    const esCobro = accion === 'COBRO';
    const titulo = accion === 'PERDON' ? 'Perdonar' : esCobro ? 'Registrar cobro' : 'Registrar pago';
    const faltan = faltaCobroPago({ importeTexto, cuentaId, fecha, conCuenta: accion !== 'PERDON' }, sel.saldo, hoyIso);
    if (envio.fase === 'CONFIRMADO') {
      const r = envio.resultado;
      return (
        <View testID="posicion-exito" style={[s.pantalla, { backgroundColor: c.background, paddingTop: inset.top + espacio.xl, paddingBottom: inset.bottom + espacio.l }]}>
          <View style={[s.exito, { backgroundColor: c.surfacePrimary }]} accessibilityLiveRegion="polite">
            <Text style={{ fontSize: 40 }} accessibilityElementsHidden>✓</Text>
            <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>
              {accion === 'PERDON' ? 'Perdonado' : esCobro ? 'Cobro registrado' : 'Pago registrado'}
            </Text>
            <Text style={[importe.primary, { color: c.textPrimary }]}>{formatearEur(r.importe)}</Text>
            <Text testID="posicion-exito-saldo" style={[tipo.body, { color: c.textSecondary }]}>
              {r.estado === 'CERRADA' ? 'Ya no queda nada pendiente.' : `Sigue pendiente: ${textoSaldo(r.saldo)}`}
            </Text>
          </View>
          <BotonPrimario testID="posicion-exito-volver" titulo={`Volver a Pendiente con ${nombre}`} onPress={cerrarAccion} />
        </View>
      );
    }
    return (
      <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <CabeceraTarea titulo={titulo} izquierda={<BotonTexto testID="accion-cancelar" titulo="Cancelar" onPress={() => (bloqueado ? undefined : cerrarAccion())} />} />
        <ScrollView testID={`accion-${accion.toLowerCase()}`} keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Text testID="accion-origen" style={[tipo.subheadline, { color: c.textSecondary }]}>
            {`${sel.tipo === 'DERECHO_COBRO' ? `${nombre} te debe` : `Le debes a ${nombre}`} ${textoSaldo(sel.saldo)} · ${origen(sel)}`}
          </Text>
          <Campo etiqueta={accion === 'PERDON' ? 'Importe que perdonas' : esCobro ? 'Importe cobrado' : 'Importe pagado'}>
            <View style={[s.fila, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard, borderWidth: 1 }]}>
              <Text style={[importe.primary, { color: c.textSecondary }]}>€</Text>
              <TextInput testID="accion-importe" accessibilityLabel={`${titulo}, importe en euros`} value={importeTexto} editable={!bloqueado}
                onChangeText={(t) => editar(() => setImporte(t))} keyboardType="decimal-pad" inputMode="decimal" placeholder="0,00"
                placeholderTextColor={c.textSecondary} style={[importe.primary, { flex: 1, minWidth: 0, color: c.textPrimary }]} />
            </View>
          </Campo>
          {accion !== 'PERDON' ? (
            <Campo etiqueta={esCobro ? '¿Dónde entró el dinero?' : '¿Desde qué cuenta?'}>
              {cuentas.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
              {cuentas.fase === 'ERROR' ? <EstadoDato estado="ERROR_CARGA" detalle="No se han podido cargar las cuentas." /> : null}
              {cuentas.fase === 'OK' && cuentas.lista.length === 0 ? (
                <Text style={[tipo.subheadline, { color: c.textSecondary }]}>No tienes cuentas que lo admitan en esa fecha.</Text>
              ) : null}
              {cuentas.fase === 'OK' ? (
                <View style={s.chips}>
                  {cuentas.lista.map((x) => (
                    <Chip key={x.cuenta_id} testID={`accion-cuenta-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={cuentaId === x.cuenta_id}
                      onPress={() => editar(() => setCuenta(x.cuenta_id))} />
                  ))}
                </View>
              ) : null}
            </Campo>
          ) : null}
          <Campo etiqueta="Fecha">
            <View style={s.chips}>
              <Chip testID="accion-fecha-hoy" etiqueta="Hoy" seleccionado={otraFecha === null && fecha === hoyIso} onPress={() => editar(() => { setOtraFecha(null); setFecha(hoyIso); })} />
              <Chip testID="accion-fecha-ayer" etiqueta="Ayer" seleccionado={otraFecha === null && fecha === ayerIso} onPress={() => editar(() => { setOtraFecha(null); setFecha(ayerIso); })} />
              <Chip testID="accion-fecha-otra" etiqueta="Otra fecha" seleccionado={otraFecha !== null} onPress={() => editar(() => setOtraFecha(isoADdmmaaaa(fecha)))} />
            </View>
            {otraFecha !== null ? (
              <TextInput testID="accion-campo-fecha" accessibilityLabel="Fecha, día barra mes barra año" value={otraFecha} editable={!bloqueado}
                onChangeText={(t) => editar(() => { setOtraFecha(t); setFecha(ddmmaaaaAIso(t) ?? t); })} placeholder="dd/mm/aaaa"
                placeholderTextColor={c.textSecondary} inputMode="numeric" maxLength={10}
                style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]} />
            ) : null}
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>
              {esFechaIso(fecha) ? (fecha > hoyIso ? 'La fecha no puede ser futura.' : fechaCortaIso(fecha)) : 'Escribe la fecha como dd/mm/aaaa.'}
            </Text>
          </Campo>
          <Text testID="accion-explicacion" style={[tipo.footnote, { color: c.textSecondary }]}>
            {accion === 'PERDON' ? TEXTO_PERDONAR : esCobro ? TEXTO_NO_ES_INGRESO(nombre) : TEXTO_NO_ES_GASTO(nombre)}
          </Text>
          {accion === 'PAGO' ? <Text testID="accion-sin-tercero" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_TERCERO_PAGA}</Text> : null}
          {envio.fase === 'RECHAZADO' ? <Aviso testID="accion-error" critico texto={`No se ha registrado. ${envio.mensaje}`} /> : null}
          {envio.fase === 'INDETERMINADO' ? <Aviso testID="accion-indeterminado" texto={envio.mensaje} /> : null}
          {faltan.length > 0 ? (
            <Text testID="accion-faltan" style={[tipo.footnote, { color: c.textSecondary }]}>{`Para continuar falta: ${faltan.join(', ')}.`}</Text>
          ) : null}
          <BotonPrimario testID="accion-enviar" titulo={envio.fase === 'ENVIANDO' ? 'Guardando…' : envio.fase === 'INDETERMINADO' ? 'Reintentar' : titulo}
            cargando={envio.fase === 'ENVIANDO'} deshabilitado={faltan.length > 0} onPress={() => void enviar()} />
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  // ---------------------------------------------------------------- C2 acciones sobre una posición
  if (sel) {
    const derecho = sel.tipo === 'DERECHO_COBRO';
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraTarea titulo={nombre} izquierda={<BotonTexto testID="posicion-atras" titulo="‹ Atrás" onPress={() => setSel(null)} />} />
        <ScrollView testID="posicion-acciones" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
            <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{derecho ? `${nombre} te debe ${textoSaldo(sel.saldo)}` : `Le debes a ${nombre} ${textoSaldo(sel.saldo)}`}</Text>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{origen(sel)}</Text>
            {sel.origen_hecho_id && p.onVerHecho ? <BotonTexto testID="posicion-ver-origen" titulo="Ver el gasto" onPress={() => p.onVerHecho!(sel.origen_hecho_id!)} /> : null}
          </View>
          <BotonPrimario testID={derecho ? 'posicion-cobrar' : 'posicion-pagar'} titulo={derecho ? 'Registrar cobro' : 'Registrar pago'}
            onPress={() => abrirAccion(derecho ? 'COBRO' : 'PAGO', sel)} />
          <BotonTexto testID="posicion-perdonar" titulo="Perdonar" onPress={() => abrirAccion('PERDON', sel)} />
          <Text testID="posicion-explicacion" style={[tipo.footnote, { color: c.textSecondary }]}>{derecho ? TEXTO_ACCIONES : TEXTO_ACCIONES_OBLIGACION}</Text>
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- C1/C4 lista
  const lista = (titulo: string, xs: PosicionPendiente[], testID: string) =>
    xs.length === 0 ? null : (
      <Bloque titulo={titulo} testID={testID}>
        {xs.map((x) => (
          <Pressable key={x.entidad_id} testID={`posicion-${x.entidad_id}`} accessibilityRole="button" onPress={() => setSel(x)} style={[s.kv, { minHeight: 44 }]}>
            <View style={{ flex: 1 }}>
              <Text style={[tipo.body, { color: c.textPrimary }]}>{origenPosicion(x)}</Text>
              <Text style={[tipo.footnote, { color: c.textSecondary }]}>
                {x.saldo === null
                  ? 'Saldo inicial desconocido'
                  : [x.origen_concepto && x.origen_tercero ? x.origen_tercero : null, x.origen_fecha ? diaMesIso(x.origen_fecha) : null].filter(Boolean).join(' · ')}
              </Text>
            </View>
            <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{textoSaldo(x.saldo)}</Text>
            <Text style={[tipo.body, { color: c.textSecondary }]}>›</Text>
          </Pressable>
        ))}
      </Bloque>
    );
  // Sin posiciones el servidor no informa importes: es 0,00 €, no «Sin determinar» (que solo vale con un saldo desconocido).
  const sinNada = carga.fase === 'OK' && (carga.p.neto_estado === 'SIN_POSICIONES' || carga.p.posiciones.every((x) => x.estado !== 'ACTIVA'));
  return (
    <View style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraTarea titulo={`Pendiente con ${nombre}`} izquierda={<BotonTexto testID="pendiente-atras" titulo={`‹ ${nombre}`} onPress={() => p.onCerrar(cambios)} />} />
      <ScrollView testID="pendiente-con" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {carga.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
        {carga.fase === 'ERROR' ? (
          <View style={{ gap: espacio.s }}>
            <EstadoDato estado="ERROR_CARGA" detalle="No se ha podido cargar lo pendiente." />
            <BotonTexto testID="pendiente-reintentar" titulo="Reintentar" onPress={() => void cargar()} />
          </View>
        ) : null}
        {carga.fase === 'OK' ? (
          <>
            <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
              <View style={s.kv}>
                <Inicial nombre={nombre} />
                <Text style={[tipo.body, { color: c.textSecondary, flex: 1 }]}>Te debe</Text>
                <Text testID="pendiente-te-debe" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{sinNada ? formatearEur('0.00') : textoSaldo(carga.p.te_debe)}</Text>
              </View>
              <View style={s.kv}>
                <View style={{ width: 32 }} />
                <Text style={[tipo.body, { color: c.textSecondary, flex: 1 }]}>Le debes</Text>
                <Text testID="pendiente-le-debes" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{sinNada ? formatearEur('0.00') : textoSaldo(carga.p.le_debes)}</Text>
              </View>
            </View>
            {sinNada ? (
              <Text testID="pendiente-nada" style={[tipo.body, { color: c.textSecondary }]}>{`No tienes nada pendiente con ${nombre}.`}</Text>
            ) : (
              <>
                {lista('Te debe', activasDe(carga.p, 'DERECHO_COBRO'), 'pendiente-lista-te-debe')}
                {lista('Le debes', activasDe(carga.p, 'OBLIGACION_PAGO'), 'pendiente-lista-le-debes')}
                <Text testID="pendiente-neto" style={[tipo.footnote, { color: c.textSecondary }]}>{textoNeto(carga.p)}</Text>
              </>
            )}
            <Text style={[tipo.caption, { color: c.textSecondary }]}>{TEXTO_PAT08}</Text>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}
