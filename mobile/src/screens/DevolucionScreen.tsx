// ============================================================
// GAPTO MOBILE 2027
// Fichero: DevolucionScreen.tsx
// Ruta: mobile/src/screens/DevolucionScreen.tsx
// Descripción: «Registrar devolución» desde una compra (F05-06 M2-B §B1; F05 §14, §51.2; lámina DEV v0.1 A1, A2, B3, B4, C1, C2). Tarea inmersiva «Cancelar · Registrar devolución». A1: compra origen fija arriba con lo ya devuelto y lo que queda (D-DEV-02); importe, fecha (Hoy · Ayer · Otra, nunca futura), categoría de la compra marcada «De la compra» (no editable), «¿De quién es lo devuelto?» (P-DEV-01: «Tuya» propuesta solo si el servidor la demuestra; si no, «Sin indicar» por defecto y «Todo mío» atenuado con su motivo, B4), «¿Ya te han abonado el dinero?» (D-DEV-03: «Sí, en <cuenta original>» solo si la compra tiene cuenta original demostrable, «En otra cuenta» con las cuentas que pueden recibir dinero (RECIBIR_INGRESO), «Todavía no»; sin respuesta por defecto) y nota opcional. Límite visible (B3, D-DEV-08): un importe mayor que lo que queda se explica y no deja revisar. A2: revisión con la relación visible, lo que se registra, el abono (real o pendiente: sin liquidez, C2) y lo que no cambia, y el neto derivado (D-DEV-05). Confirmación con ida y vuelta (D-DEV-06): «Ver la devolución» y «Ver la compra». Mismo ciclo de envío que el registro: UUID y payload sellados antes de enviar; doble toque ignorado; INDETERMINADO reintenta con la MISMA identidad; rechazo definitivo libera la edición. Nunca se ofrece «Ingreso» (D-DEV-04).
// Versión: 0.1.0 (F05-06 M2-B §B1)
// Versión: 0.2.0 (F05-06 M2-D §2; decisión R-M2A-02 opción b): «Sí, en <cuenta>» solo cuando `cuenta_compra` (cuenta ORIGINAL demostrable) no es null, sin exigir que esté en la lista (el servidor no le exige capacidad); «En otra cuenta» con las de RECIBIR_INGRESO (operación INGRESO). CUENTA_SIN_CAPACIDAD sigue con el mensaje del servidor, que nombra la capacidad del detalle.
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, ContextoDevolucion, CuentaElegible, PayloadDevolucion, ResultadoDevolucion } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { TEXTO_FORMULARIO_SE_CONSERVA } from '../domain/capacidades';
import {
  atribucionInicial,
  AtribucionDevolucion,
  faltaDevolucion,
  motivoNoDisponible,
  netoTras,
  RespuestaAbono,
  superaLoQueQueda,
  TEXTO_NETO,
  TEXTO_PREGUNTA_ABONO,
  TEXTO_SIN_REPARTO,
  TEXTO_TODAVIA_NO,
  TEXTO_TODO_MIO_NO_DISPONIBLE,
  textoDevolucionDe,
  textoSupera,
  tituloOrigen,
} from '../domain/devolucion';
import { ayer, ddmmaaaaAIso, diaMesAnioIso, diaMesIso, fechaCortaIso, isoADdmmaaaa, isoLocal, mesAnioIso } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import { notaCanonica } from '../domain/registro';
import { useTema } from '../theme/tema';
import { espacio, importe, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { TEXTO_FECHA_FUTURA } from './RegistroGastoScreen';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; ctx: ContextoDevolucion };
type Lista = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: CuentaElegible[] };
type Estado =
  | { fase: 'EDITANDO' }
  | { fase: 'REVISANDO' }
  | { fase: 'ENVIANDO'; payload: PayloadDevolucion }
  | { fase: 'INDETERMINADO'; payload: PayloadDevolucion; mensaje: string }
  | { fase: 'RECHAZADO'; codigo: string; mensaje: string }
  | { fase: 'CONFIRMADO'; payload: PayloadDevolucion; resultado: ResultadoDevolucion };

export const TITULO_DEVOLUCION = 'Registrar devolución';

export function DevolucionScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  origenId: string;
  /** registrado: hubo escritura; ver: id del hecho que abrir en la Actividad (ida y vuelta). */
  onCerrar: (registrado: boolean, ver?: string) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoy = p.ahora();
  const hoyIso = isoLocal(hoy);
  const ayerIso = isoLocal(ayer(hoy));
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [importeTexto, setImporte] = useState('');
  const [fecha, setFecha] = useState(hoyIso);
  const [otraFecha, setOtraFecha] = useState<string | null>(null);
  const [atribucion, setAtribucion] = useState<AtribucionDevolucion>('SIN_INDICAR');
  const [abono, setAbono] = useState<RespuestaAbono | null>(null);
  const [cuentaOtra, setCuentaOtra] = useState<string | null>(null);
  const [cuentas, setCuentas] = useState<Lista>({ fase: 'CARGANDO' });
  const [nota, setNota] = useState('');
  const [estado, setEstado] = useState<Estado>({ fase: 'EDITANDO' });
  const enVuelo = useRef(false);
  const sellada = useRef<PayloadDevolucion | null>(null);
  const primeraCarga = useRef(true);

  const cargarContexto = async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.contextoDevolucion(p.origenId);
    if (r.tipo !== 'OK') return setCarga({ fase: 'ERROR' });
    setCarga({ fase: 'OK', ctx: r.datos });
    // P-DEV-01: la propuesta solo al abrir; al recargar, «Tuya» se retira si ya no es demostrable.
    if (primeraCarga.current) setAtribucion(atribucionInicial(r.datos));
    else if (!r.datos.tuya_disponible) setAtribucion('SIN_INDICAR');
    primeraCarga.current = false;
  };
  const cargarCuentas = async (f: string) => {
    setCuentas({ fase: 'CARGANDO' });
    // M2-D: otra cuenta que no es la original exige recibir dinero (RECIBIR_INGRESO); el abono nunca es un «ingreso».
    const r = await p.cliente.cuentasElegibles('INGRESO', f);
    const l: Lista = r.tipo === 'OK' ? { fase: 'OK', lista: r.datos.cuentas } : { fase: 'ERROR' };
    setCuentas(l);
    if (l.fase === 'OK') setCuentaOtra((x) => (x && l.lista.some((y) => y.cuenta_id === x) ? x : null));
  };
  useEffect(() => {
    void cargarContexto();
  }, [p.origenId]);
  useEffect(() => {
    if (esFechaIso(fecha) && fecha <= hoyIso) void cargarCuentas(fecha);
  }, [fecha]);

  const ctx = carga.fase === 'OK' ? carga.ctx : null;
  // M2-D: la cuenta original demostrable se ofrece siempre que exista; no tiene que estar en la lista de RECIBIR_INGRESO.
  const compraElegible = !!ctx?.cuenta_compra;
  const cuentaAbono = abono === 'COMPRA' && compraElegible ? ctx!.cuenta_compra!.cuenta_id : abono === 'OTRA' ? cuentaOtra : null;
  const nombreCuenta = (id: string | null) =>
    id === null ? null : ctx?.cuenta_compra?.cuenta_id === id ? ctx.cuenta_compra.nombre : cuentas.fase === 'OK' ? cuentas.lista.find((x) => x.cuenta_id === id)?.nombre ?? null : null;
  const bloqueado = estado.fase === 'ENVIANDO' || estado.fase === 'INDETERMINADO' || estado.fase === 'CONFIRMADO';
  const faltan = ctx ? faltaDevolucion({ importeTexto, fecha, abono, cuentaAbono, queda: ctx.queda }, hoyIso) : ['la compra'];
  const supera = ctx ? superaLoQueQueda(importeTexto, ctx.queda) : false;
  const editar = (f: () => void) => {
    if (bloqueado) return;
    if (estado.fase === 'RECHAZADO') setEstado({ fase: 'EDITANDO' });
    f();
  };

  const enviarPayload = async (payload: PayloadDevolucion) => {
    if (enVuelo.current) return; // doble toque: nunca un segundo POST
    enVuelo.current = true;
    setEstado({ fase: 'ENVIANDO', payload });
    try {
      const r = await p.cliente.registrarDevolucion(p.origenId, payload);
      if (r.tipo === 'OK') setEstado({ fase: 'CONFIRMADO', payload, resultado: r.datos });
      else if (r.tipo === 'RECHAZADO') {
        sellada.current = null; // definitivo: el siguiente envío lleva identidad nueva
        setEstado({ fase: 'RECHAZADO', codigo: r.codigo, mensaje: r.mensaje });
        if (r.codigo === 'EXCEDE_CAPACIDAD_REVERSIBLE' || r.codigo === 'DEVOLUCION_ATRIBUCION_NO_DEMOSTRABLE') void cargarContexto();
        if (r.codigo === 'CUENTA_SIN_CAPACIDAD') void cargarCuentas(payload.fecha_hecho);
      } else setEstado({ fase: 'INDETERMINADO', payload, mensaje: r.mensaje });
    } finally {
      enVuelo.current = false;
    }
  };

  const registrar = async () => {
    if (enVuelo.current || faltan.length > 0 || !ctx) return;
    if (sellada.current) return enviarPayload(sellada.current);
    const imp = parsearImporte(importeTexto);
    if (!imp.ok) return;
    const n = notaCanonica(nota);
    const payload: PayloadDevolucion = Object.freeze({
      intencion_id: p.nuevoId(),
      importe: imp.valor,
      moneda: 'EUR' as const,
      fecha_hecho: fecha,
      atribucion,
      abono: abono === 'TODAVIA_NO' || !cuentaAbono ? { estado: 'PENDIENTE' as const } : { estado: 'COBRADO' as const, cuenta_id: cuentaAbono, fecha },
      ...(n ? { nota: n } : {}),
    });
    sellada.current = payload;
    await enviarPayload(payload);
  };

  // ---------------------------------------------------------------- confirmación (D-DEV-06)
  if (estado.fase === 'CONFIRMADO' && ctx) {
    const r = estado.resultado;
    return (
      <View testID="devolucion-exito" style={[s.pantalla, { backgroundColor: c.background, paddingTop: inset.top + espacio.xl, paddingBottom: inset.bottom + espacio.l }]}>
        <View style={[s.exito, { backgroundColor: c.surfacePrimary }]} accessibilityLiveRegion="polite">
          <Text style={{ fontSize: 40 }} accessibilityElementsHidden>✓</Text>
          <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>Devolución registrada</Text>
          <Text style={[importe.primary, { color: c.textPrimary }]}>{formatearEur(r.importe)}</Text>
          <Text testID="devolucion-exito-relacion" style={[tipo.body, { color: c.textSecondary, textAlign: 'center' }]}>
            {`Devolución de ${textoDevolucionDe(ctx)}`}
          </Text>
          <Text testID="devolucion-exito-abono" style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>
            {r.abono === 'COBRADO' ? `Abono recibido en ${nombreCuenta(estado.payload.abono.estado === 'COBRADO' ? estado.payload.abono.cuenta_id : null) ?? 'la cuenta'}` : 'Abono pendiente'}
          </Text>
          <Text testID="devolucion-exito-queda" style={[tipo.footnote, { color: c.textSecondary }]}>{`Queda por devolver ${formatearEur(r.queda)}`}</Text>
        </View>
        <View style={{ flex: 1 }} />
        <View style={{ gap: espacio.s }}>
          <BotonPrimario testID="devolucion-hecho" titulo="Hecho" onPress={() => p.onCerrar(true)} />
          <BotonTexto testID="devolucion-ver-devolucion" titulo="Ver la devolución" onPress={() => p.onCerrar(true, r.hecho_id)} />
          <BotonTexto testID="devolucion-ver-compra" titulo="Ver la compra" onPress={() => p.onCerrar(true, p.origenId)} />
        </View>
      </View>
    );
  }

  const cabecera = (titulo: string, izquierda: React.ReactNode) => (
    <View style={[s.cabTarea, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
      {izquierda}
      <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{titulo}</Text>
      <View style={{ width: 72 }} />
    </View>
  );

  const avisos = (
    <>
      {estado.fase === 'RECHAZADO' ? (
        <View testID="error-dominio" accessibilityLiveRegion="assertive" style={[s.aviso, { backgroundColor: c.surfacePrimary, borderColor: c.critical, borderWidth: 1 }]}>
          <Text style={[tipo.subheadline, { color: c.textPrimary }]}>
            {estado.codigo === 'CUENTA_SIN_CAPACIDAD'
              ? `${estado.mensaje} ${TEXTO_FORMULARIO_SE_CONSERVA}`
              : `No se ha registrado. ${estado.codigo === 'FECHA_FUTURA' ? TEXTO_FECHA_FUTURA : estado.mensaje}`}
          </Text>
        </View>
      ) : null}
      {estado.fase === 'INDETERMINADO' ? (
        <View testID="estado-indeterminado" accessibilityLiveRegion="assertive" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
          <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{estado.mensaje}</Text>
        </View>
      ) : null}
    </>
  );

  // ---------------------------------------------------------------- A2 revisión
  if ((estado.fase === 'REVISANDO' || estado.fase === 'ENVIANDO' || estado.fase === 'INDETERMINADO') && ctx) {
    const imp = parsearImporte(importeTexto);
    const valor = imp.ok ? imp.valor : '0';
    const mes = mesAnioIso(fecha).split(' ')[0].toLowerCase();
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        {cabecera('Revisar devolución', <BotonTexto testID="revision-atras" titulo="‹ Atrás" onPress={() => (bloqueado ? undefined : setEstado({ fase: 'EDITANDO' }))} />)}
        <ScrollView testID="devolucion-revision" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <View style={{ gap: espacio.s }}>
            <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Devolución de</Text>
            <View testID="revision-origen" style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
              <View style={s.kv}>
                <View style={{ flex: 1 }}>
                  <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{tituloOrigen(ctx)}</Text>
                  <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`Compra del ${diaMesAnioIso(ctx.fecha_hecho)}${ctx.categoria ? ` · ${ctx.categoria}` : ''}`}</Text>
                </View>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{formatearEur(ctx.importe_total)}</Text>
              </View>
            </View>
          </View>
          <View style={{ gap: espacio.s }}>
            <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Qué se registra</Text>
            <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
              <FilaRevision testID="revision-devolucion" titulo={`Devolución el ${diaMesIso(fecha)}`}
                detalle={`Reduce ${atribucion === 'SOLO_MIO' ? 'tu gasto' : 'el gasto'} en ${ctx.categoria ?? 'Sin categoría'} de ${mes}${atribucion === 'SIN_INDICAR' ? ' · reparto sin indicar' : ''}`}
                valor={formatearEur(valor)} />
              {cuentaAbono ? (
                <FilaRevision testID="revision-abono" titulo={`Abono en ${nombreCuenta(cuentaAbono) ?? 'la cuenta'}`} detalle={`Entra dinero real el ${diaMesIso(fecha)}`} valor={`+${formatearEur(valor)}`} />
              ) : (
                <FilaRevision testID="revision-abono" titulo="Abono" detalle="Pendiente: no cuenta como dinero disponible" valor="Pendiente" />
              )}
            </View>
          </View>
          <View style={{ gap: espacio.s }}>
            <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Lo que no cambia</Text>
            <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
              <FilaRevision testID="revision-no-cambia" titulo={`La compra de ${mesAnioIso(ctx.fecha_hecho).split(' ')[0].toLowerCase()}`}
                detalle={`Sigue siendo de ${formatearEur(ctx.importe_total)}`} valor="" />
            </View>
          </View>
          <Text testID="revision-neto" style={[tipo.footnote, { color: c.textSecondary }]}>
            {`Después de esta devolución, el neto de la compra es ${formatearEur(netoTras(ctx, valor))}. ${TEXTO_NETO}`}
          </Text>
          {avisos}
          {estado.fase === 'INDETERMINADO' ? (
            <BotonPrimario testID="reintentar" titulo="Reintentar" onPress={() => void enviarPayload(estado.payload)} />
          ) : (
            <BotonPrimario testID="registrar-devolucion" titulo={estado.fase === 'ENVIANDO' ? 'Guardando…' : TITULO_DEVOLUCION}
              cargando={estado.fase === 'ENVIANDO'} onPress={() => void registrar()} />
          )}
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- A1 formulario
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {cabecera(TITULO_DEVOLUCION, <BotonTexto testID="cancelar" titulo="Cancelar" onPress={() => p.onCerrar(false)} />)}
      <ScrollView testID="devolucion-form" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {carga.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
        {carga.fase === 'ERROR' ? (
          <View style={{ gap: espacio.s }}>
            <EstadoDato estado="ERROR_CARGA" detalle="No se ha podido cargar la compra." />
            <BotonTexto testID="devolucion-reintentar-carga" titulo="Reintentar" onPress={() => void cargarContexto()} />
          </View>
        ) : null}
        {ctx ? (
          <>
            <View testID="devolucion-origen" style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
              <View style={s.kv}>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary, flex: 1 }]}>{tituloOrigen(ctx)}</Text>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{formatearEur(ctx.importe_total)}</Text>
              </View>
              <Text style={[tipo.footnote, { color: c.textSecondary }]}>
                {`Compra del ${diaMesAnioIso(ctx.fecha_hecho)}${ctx.categoria ? ` · ${ctx.categoria}` : ''}${ctx.cuenta_compra ? ` · ${ctx.cuenta_compra.nombre}` : ''}`}
              </Text>
              <View testID="devolucion-ya-devuelto" style={s.kv}>
                <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Ya devuelto</Text>
                <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{formatearEur(ctx.devuelto)}</Text>
              </View>
              <View testID="devolucion-queda" style={s.kv}>
                <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Queda por devolver</Text>
                <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{formatearEur(ctx.queda)}</Text>
              </View>
            </View>
            {!ctx.disponible ? (
              <View testID="devolucion-no-disponible" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
                <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{motivoNoDisponible(ctx.motivo)}</Text>
              </View>
            ) : (
              <>
                <Campo etiqueta="Importe devuelto">
                  <View style={[s.importeCaja, { backgroundColor: c.surfacePrimary, borderColor: supera ? c.critical : c.borderStandard }]}>
                    <Text style={[importe.primary, { color: c.textSecondary }]}>€</Text>
                    <TextInput testID="campo-importe" accessibilityLabel="Importe devuelto en euros" value={importeTexto}
                      onChangeText={(t) => editar(() => setImporte(t))} editable={!bloqueado} keyboardType="decimal-pad" inputMode="decimal"
                      placeholder="0,00" placeholderTextColor={c.textSecondary}
                      style={[importe.hero, { flex: 1, minWidth: 0, color: c.textPrimary, paddingVertical: espacio.s }]} />
                  </View>
                  {supera ? (
                    <Text testID="devolucion-supera" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{textoSupera(ctx.queda)}</Text>
                  ) : null}
                </Campo>
                <Campo etiqueta="Fecha de la devolución">
                  <View style={s.chips}>
                    <Chip testID="fecha-hoy" etiqueta="Hoy" seleccionado={otraFecha === null && fecha === hoyIso} onPress={() => editar(() => { setOtraFecha(null); setFecha(hoyIso); })} />
                    <Chip testID="fecha-ayer" etiqueta="Ayer" seleccionado={otraFecha === null && fecha === ayerIso} onPress={() => editar(() => { setOtraFecha(null); setFecha(ayerIso); })} />
                    <Chip testID="fecha-otra" etiqueta="Otra fecha" seleccionado={otraFecha !== null} onPress={() => editar(() => setOtraFecha(isoADdmmaaaa(fecha)))} />
                  </View>
                  {otraFecha !== null ? (
                    <TextInput testID="campo-fecha" accessibilityLabel="Fecha, día barra mes barra año" value={otraFecha} editable={!bloqueado}
                      onChangeText={(t) => editar(() => { setOtraFecha(t); setFecha(ddmmaaaaAIso(t) ?? t); })} placeholder="dd/mm/aaaa"
                      placeholderTextColor={c.textSecondary} inputMode="numeric" maxLength={10}
                      style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]} />
                  ) : null}
                  <Text testID="fecha" style={[tipo.footnote, { color: c.textSecondary }]}>
                    {esFechaIso(fecha) ? (fecha > hoyIso ? 'La fecha no puede ser futura.' : fechaCortaIso(fecha)) : 'Escribe la fecha como dd/mm/aaaa.'}
                  </Text>
                </Campo>
                <Campo etiqueta="Categoría">
                  <View testID="devolucion-categoria" style={[s.kv, s.filaFija, { backgroundColor: c.surfacePrimary }]}>
                    <Text style={[tipo.body, { color: c.textPrimary }]}>{ctx.categoria ?? 'Sin categoría'}</Text>
                    <Text style={[tipo.footnote, { color: c.textSecondary }]}>De la compra</Text>
                  </View>
                </Campo>
                <Campo etiqueta="¿De quién es lo devuelto?">
                  <View style={s.chips}>
                    {ctx.tuya_disponible ? (
                      <Chip testID="atribucion-tuya" etiqueta="Tuya" seleccionado={atribucion === 'SOLO_MIO'} onPress={() => editar(() => setAtribucion('SOLO_MIO'))} />
                    ) : (
                      <View testID="atribucion-todo-mio-no-disponible" accessibilityState={{ disabled: true }} style={[s.chipApagado, { borderColor: c.borderDefault }]}>
                        <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Todo mío</Text>
                      </View>
                    )}
                    <Chip testID="atribucion-sin-indicar" etiqueta="Sin indicar" seleccionado={atribucion === 'SIN_INDICAR'} onPress={() => editar(() => setAtribucion('SIN_INDICAR'))} />
                  </View>
                  {!ctx.tuya_disponible ? (
                    <Text testID="atribucion-motivo" style={[tipo.footnote, { color: c.textSecondary }]}>{`${TEXTO_SIN_REPARTO} «Todo mío»: ${TEXTO_TODO_MIO_NO_DISPONIBLE.toLowerCase()}`}</Text>
                  ) : null}
                </Campo>
                <Campo etiqueta={TEXTO_PREGUNTA_ABONO}>
                  <View style={s.chips}>
                    {compraElegible ? (
                      <Chip testID="abono-compra" etiqueta={`Sí, en ${ctx.cuenta_compra!.nombre}`} seleccionado={abono === 'COMPRA'} onPress={() => editar(() => setAbono('COMPRA'))} />
                    ) : null}
                    <Chip testID="abono-otra" etiqueta={compraElegible ? 'En otra cuenta' : 'Sí, en una cuenta'} seleccionado={abono === 'OTRA'} onPress={() => editar(() => setAbono('OTRA'))} />
                    <Chip testID="abono-todavia-no" etiqueta="Todavía no" seleccionado={abono === 'TODAVIA_NO'} onPress={() => editar(() => setAbono('TODAVIA_NO'))} />
                  </View>
                  {abono === 'OTRA' ? (
                    <>
                      {cuentas.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
                      {cuentas.fase === 'ERROR' ? <EstadoDato estado="ERROR_CARGA" detalle="No se han podido cargar las cuentas." /> : null}
                      {cuentas.fase === 'OK' && cuentas.lista.length === 0 ? (
                        <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Ninguna cuenta puede recibir el abono en esa fecha.</Text>
                      ) : null}
                      {cuentas.fase === 'OK' ? (
                        <View style={s.chips}>
                          {cuentas.lista.map((x) => (
                            <Chip key={x.cuenta_id} testID={`abono-cuenta-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={cuentaOtra === x.cuenta_id}
                              onPress={() => editar(() => setCuentaOtra(x.cuenta_id))} />
                          ))}
                        </View>
                      ) : null}
                    </>
                  ) : null}
                  {abono === 'TODAVIA_NO' ? <Text testID="abono-todavia-no-texto" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_TODAVIA_NO}</Text> : null}
                </Campo>
                <Campo etiqueta="Nota (opcional)">
                  <TextInput testID="campo-nota" accessibilityLabel="Nota" value={nota} onChangeText={(t) => editar(() => setNota(t))} editable={!bloqueado}
                    maxLength={200} style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]} />
                </Campo>
                {avisos}
                {faltan.length > 0 ? (
                  <Text testID="faltan" accessibilityLiveRegion="polite" style={[tipo.footnote, { color: c.textSecondary }]}>
                    {`Para revisar falta: ${faltan.length === 1 ? faltan[0] : `${faltan.slice(0, -1).join(', ')} y ${faltan[faltan.length - 1]}`}.`}
                  </Text>
                ) : null}
                <BotonPrimario testID="revisar" titulo="Revisar" deshabilitado={faltan.length > 0}
                  onPress={() => { if (faltan.length === 0) setEstado({ fase: 'REVISANDO' }); }} />
              </>
            )}
          </>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Campo({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  const { c } = useTema();
  return (
    <View style={{ gap: espacio.s }}>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{etiqueta}</Text>
      {children}
    </View>
  );
}

function FilaRevision(p: { testID: string; titulo: string; detalle: string; valor: string }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={[s.kv, { paddingVertical: espacio.xs }]}>
      <View style={{ flex: 1 }}>
        <Text style={[tipo.body, { color: c.textPrimary }]}>{p.titulo}</Text>
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{p.detalle}</Text>
      </View>
      {p.valor ? <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{p.valor}</Text> : null}
    </View>
  );
}

const s = StyleSheet.create({
  pantalla: { flex: 1, paddingHorizontal: espacio.l, justifyContent: 'space-between' },
  exito: { borderRadius: radio.l, padding: espacio.xl, alignItems: 'center', gap: espacio.s },
  cabTarea: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  form: { padding: espacio.l, gap: espacio.xl },
  tarjeta: { borderRadius: radio.m, padding: espacio.m, gap: espacio.s },
  kv: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: espacio.m },
  filaFija: { borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN },
  importeCaja: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: radio.m, paddingHorizontal: espacio.l, gap: espacio.s, minHeight: 64 },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4, minWidth: 0 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  chipApagado: { borderWidth: 1, borderRadius: radio.pill, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN, justifyContent: 'center', opacity: 0.5 },
  aviso: { borderRadius: radio.m, padding: espacio.m, gap: espacio.s },
});
