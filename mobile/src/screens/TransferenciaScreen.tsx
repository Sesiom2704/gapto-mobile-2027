// ============================================================
// GAPTO MOBILE 2027
// Fichero: TransferenciaScreen.tsx
// Ruta: mobile/src/screens/TransferenciaScreen.tsx
// Descripción: «Entre cuentas» (F05-04 J2 §2.3; D-DYN-09; lámina REG-DYN X01). Tarea inmersiva «Cancelar · Entre cuentas · Tipo»: «Desde» y «A» (cuentas elegibles que da el servidor para salida y entrada en la fecha), importe, fecha (Hoy · Ayer · Otra, nunca futura), «+ Añadir nota» y la nota fija de la lámina. Misma cuenta en «Desde» y «A»: aviso en el campo y no se puede registrar. Mismo ciclo de envío que el registro: UUID y payload sellados antes de enviar; doble toque ignorado; INDETERMINADO reintenta con la MISMA identidad; rechazo definitivo libera la edición (FECHA_FUTURA con su mensaje). El tipo solo se puede cambiar antes del primer envío. Sin categoría, tercero, presupuesto ni atribución: no es gasto ni ingreso.
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.3)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaElegible, PayloadTransferencia, ResultadoRegistroTipo } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { HojaTipos } from '../components/HojaTipos';
import { ayer, ddmmaaaaAIso, fechaCortaIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import { esFechaIso } from '../domain/intencion';
import { avisoCambioDeTipo, notaCanonica, TEXTO_ENTRE_CUENTAS, TipoRegistro, tituloExito, tituloRegistro } from '../domain/registro';
import { useTema } from '../theme/tema';
import { espacio, importe, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { TEXTO_FECHA_FUTURA } from './RegistroGastoScreen';

type Lista = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: CuentaElegible[] };
type Estado =
  | { fase: 'EDITANDO' }
  | { fase: 'ENVIANDO'; payload: PayloadTransferencia }
  | { fase: 'INDETERMINADO'; payload: PayloadTransferencia; mensaje: string }
  | { fase: 'RECHAZADO'; codigo: string; mensaje: string }
  | { fase: 'CONFIRMADO'; payload: PayloadTransferencia; resultado: ResultadoRegistroTipo };

export const TEXTO_MISMA_CUENTA = 'Elige dos cuentas distintas.';

/** Lo que falta para registrar (orden del formulario); vacío = se puede. */
export function faltaTransferencia(f: { desde: string | null; hacia: string | null; importeTexto: string; fecha: string }, hoyIso: string): string[] {
  const r: string[] = [];
  if (!f.desde) r.push('desde qué cuenta');
  if (!f.hacia) r.push('a qué cuenta');
  if (f.desde && f.hacia && f.desde === f.hacia) r.push('dos cuentas distintas');
  if (!parsearImporte(f.importeTexto).ok) r.push(f.importeTexto.trim() ? 'importe válido' : 'importe');
  if (!esFechaIso(f.fecha) || f.fecha > hoyIso) r.push('fecha válida');
  return r;
}

export function TransferenciaScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (registrado: boolean) => void;
  inicial?: { importeTexto: string; fechaHecho: string; aviso: string | null } | null;
  onCambiarTipo?: (hacia: TipoRegistro, conservar: { importeTexto: string; fechaHecho: string; aviso: string }) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoy = p.ahora();
  const hoyIso = isoLocal(hoy);
  const ayerIso = isoLocal(ayer(hoy));
  const [importeTexto, setImporte] = useState(p.inicial?.importeTexto ?? '');
  const [fecha, setFecha] = useState(p.inicial?.fechaHecho ?? hoyIso);
  const [otraFecha, setOtraFecha] = useState<string | null>(p.inicial && p.inicial.fechaHecho !== hoyIso && p.inicial.fechaHecho !== ayerIso ? isoADdmmaaaa(p.inicial.fechaHecho) : null);
  const [desde, setDesde] = useState<string | null>(null);
  const [hacia, setHacia] = useState<string | null>(null);
  const [nota, setNota] = useState('');
  const [conNota, setConNota] = useState(false);
  const [origen, setOrigen] = useState<Lista>({ fase: 'CARGANDO' });
  const [destino, setDestino] = useState<Lista>({ fase: 'CARGANDO' });
  const [estado, setEstado] = useState<Estado>({ fase: 'EDITANDO' });
  const [hojaTipos, setHojaTipos] = useState(false);
  const [aviso] = useState<string | null>(p.inicial?.aviso ?? null);
  const enVuelo = useRef(false);
  const sellada = useRef<PayloadTransferencia | null>(null);
  const [enviado, setEnviado] = useState(false);

  const cargar = async (f: string) => {
    setOrigen({ fase: 'CARGANDO' });
    setDestino({ fase: 'CARGANDO' });
    const [o, d] = await Promise.all([p.cliente.cuentasElegibles('TRANSFERENCIA_ORIGEN', f), p.cliente.cuentasElegibles('TRANSFERENCIA_DESTINO', f)]);
    const lo: Lista = o.tipo === 'OK' ? { fase: 'OK', lista: o.datos.cuentas } : { fase: 'ERROR' };
    const ld: Lista = d.tipo === 'OK' ? { fase: 'OK', lista: d.datos.cuentas } : { fase: 'ERROR' };
    setOrigen(lo);
    setDestino(ld);
    // Una cuenta elegida que deja de ser elegible en la nueva fecha se quita (sin preselección).
    if (lo.fase === 'OK') setDesde((x) => (x && lo.lista.some((y) => y.cuenta_id === x) ? x : null));
    if (ld.fase === 'OK') setHacia((x) => (x && ld.lista.some((y) => y.cuenta_id === x) ? x : null));
  };
  useEffect(() => {
    if (esFechaIso(fecha) && fecha <= hoyIso) void cargar(fecha);
  }, [fecha]);

  const bloqueado = estado.fase === 'ENVIANDO' || estado.fase === 'INDETERMINADO' || estado.fase === 'CONFIRMADO';
  const faltan = faltaTransferencia({ desde, hacia, importeTexto, fecha }, hoyIso);
  const listo = faltan.length === 0;
  const editar = (f: () => void) => {
    if (bloqueado) return;
    if (estado.fase === 'RECHAZADO') setEstado({ fase: 'EDITANDO' });
    f();
  };

  const enviarPayload = async (payload: PayloadTransferencia) => {
    if (enVuelo.current) return; // doble toque: nunca un segundo POST
    enVuelo.current = true;
    setEstado({ fase: 'ENVIANDO', payload });
    try {
      const r = await p.cliente.registrarTransferencia(payload);
      if (r.tipo === 'OK') setEstado({ fase: 'CONFIRMADO', payload, resultado: r.datos });
      else if (r.tipo === 'RECHAZADO') {
        sellada.current = null; // definitivo: el siguiente envío lleva identidad nueva
        setEstado({ fase: 'RECHAZADO', codigo: r.codigo, mensaje: r.mensaje });
      } else setEstado({ fase: 'INDETERMINADO', payload, mensaje: r.mensaje });
    } finally {
      enVuelo.current = false;
    }
  };

  const registrar = async () => {
    if (enVuelo.current || !listo) return;
    if (sellada.current) return enviarPayload(sellada.current);
    const imp = parsearImporte(importeTexto);
    if (!imp.ok || !desde || !hacia) return;
    const n = notaCanonica(nota);
    const payload: PayloadTransferencia = Object.freeze({
      intencion_id: p.nuevoId(),
      importe: imp.valor,
      moneda: 'EUR' as const,
      fecha_hecho: fecha,
      cuenta_origen_id: desde,
      cuenta_destino_id: hacia,
      ...(n ? { nota: n } : {}),
    });
    sellada.current = payload;
    setEnviado(true);
    await enviarPayload(payload);
  };

  const cambiarTipo = (t: TipoRegistro) => {
    setHojaTipos(false);
    if (t === 'TRANSFERENCIA' || enviado) return;
    p.onCambiarTipo?.(t, { importeTexto, fechaHecho: fecha, aviso: avisoCambioDeTipo('TRANSFERENCIA', t, []) });
  };

  const nombre = (l: Lista, id: string | null) => (l.fase === 'OK' ? l.lista.find((x) => x.cuenta_id === id)?.nombre ?? null : null);

  if (estado.fase === 'CONFIRMADO') {
    const r = estado.resultado;
    return (
      <View testID="transferencia-exito" style={[s.pantalla, { backgroundColor: c.background, paddingTop: inset.top + espacio.xl, paddingBottom: inset.bottom + espacio.l }]}>
        <View style={[s.exito, { backgroundColor: c.surfacePrimary }]} accessibilityLiveRegion="polite">
          <Text style={{ fontSize: 40 }} accessibilityElementsHidden>✓</Text>
          <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>{tituloExito('TRANSFERENCIA')}</Text>
          <Text style={[importe.primary, { color: c.textPrimary }]}>{formatearEur(r.importe)}</Text>
          <Text testID="transferencia-exito-titulo" style={[tipo.body, { color: c.textSecondary }]}>
            {tituloRegistro({ tipo: 'TRANSFERENCIA', importe: r.importe, nota: estado.payload.nota ?? null })}
          </Text>
          <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>
            {`${nombre(origen, estado.payload.cuenta_origen_id) ?? ''} → ${nombre(destino, estado.payload.cuenta_destino_id) ?? ''}`}
          </Text>
        </View>
        <View style={{ flex: 1 }} />
        <BotonPrimario testID="volver-inicio" titulo="Volver a Inicio" onPress={() => p.onCerrar(true)} />
      </View>
    );
  }

  const chips = (l: Lista, sel: string | null, otra: string | null, prefijo: string, onElegir: (id: string) => void) => (
    <>
      {l.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
      {l.fase === 'ERROR' ? (
        <Pressable testID={`${prefijo}-error`} accessibilityRole="button" onPress={() => void cargar(fecha)} style={{ minHeight: TACTIL_MIN }}>
          <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
        </Pressable>
      ) : null}
      {l.fase === 'OK' && l.lista.length === 0 ? <Text style={[tipo.subheadline, { color: c.textSecondary }]}>No hay cuentas disponibles para esta operación.</Text> : null}
      {l.fase === 'OK' ? (
        <View style={s.chips}>
          {l.lista.map((x) => (
            <Chip key={x.cuenta_id} testID={`${prefijo}-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={sel === x.cuenta_id} onPress={() => editar(() => onElegir(x.cuenta_id))} />
          ))}
        </View>
      ) : null}
      {sel && otra && sel === otra ? (
        <Text testID={`${prefijo}-misma`} accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{TEXTO_MISMA_CUENTA}</Text>
      ) : null}
    </>
  );

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.cabTarea, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
        <BotonTexto testID="cancelar" titulo="Cancelar" onPress={() => p.onCerrar(false)} />
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>Entre cuentas</Text>
        <View style={{ width: 72, alignItems: 'flex-end' }}>
          {!enviado ? <BotonTexto testID="cambiar-tipo" titulo="Tipo" onPress={() => setHojaTipos(true)} /> : null}
        </View>
      </View>
      <ScrollView testID="transferencia-form" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {aviso ? (
          <View testID="avisos-registro" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{aviso}</Text>
          </View>
        ) : null}
        <Campo etiqueta="Desde">{chips(origen, desde, hacia, 'desde', setDesde)}</Campo>
        <Campo etiqueta="A">{chips(destino, hacia, desde, 'a', setHacia)}</Campo>
        <Campo etiqueta="Importe">
          <View style={[s.importeCaja, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}>
            <Text style={[importe.primary, { color: c.textSecondary }]}>€</Text>
            <TextInput
              testID="campo-importe"
              accessibilityLabel="Importe en euros"
              value={importeTexto}
              onChangeText={(t) => editar(() => setImporte(t))}
              editable={!bloqueado}
              keyboardType="decimal-pad"
              inputMode="decimal"
              placeholder="0,00"
              placeholderTextColor={c.textSecondary}
              style={[importe.hero, { flex: 1, minWidth: 0, color: c.textPrimary, paddingVertical: espacio.s }]}
            />
          </View>
        </Campo>
        <Campo etiqueta="Fecha">
          <View style={s.chips}>
            <Chip testID="fecha-hoy" etiqueta="Hoy" seleccionado={otraFecha === null && fecha === hoyIso} onPress={() => editar(() => { setOtraFecha(null); setFecha(hoyIso); })} />
            <Chip testID="fecha-ayer" etiqueta="Ayer" seleccionado={otraFecha === null && fecha === ayerIso} onPress={() => editar(() => { setOtraFecha(null); setFecha(ayerIso); })} />
            <Chip testID="fecha-otra" etiqueta="Otra fecha" seleccionado={otraFecha !== null} onPress={() => editar(() => setOtraFecha(isoADdmmaaaa(fecha)))} />
          </View>
          {otraFecha !== null ? (
            <TextInput
              testID="campo-fecha"
              accessibilityLabel="Fecha, día barra mes barra año"
              value={otraFecha}
              editable={!bloqueado}
              onChangeText={(t) => editar(() => { setOtraFecha(t); setFecha(ddmmaaaaAIso(t) ?? t); })}
              placeholder="dd/mm/aaaa"
              placeholderTextColor={c.textSecondary}
              inputMode="numeric"
              maxLength={10}
              style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
            />
          ) : null}
          <Text testID="fecha" style={[tipo.footnote, { color: c.textSecondary }]}>
            {esFechaIso(fecha) ? (fecha > hoyIso ? 'La fecha no puede ser futura.' : fechaCortaIso(fecha)) : 'Escribe la fecha como dd/mm/aaaa.'}
          </Text>
        </Campo>
        {conNota ? (
          <Campo etiqueta="Nota (opcional)">
            <TextInput
              testID="campo-nota"
              accessibilityLabel="Nota"
              value={nota}
              onChangeText={(t) => editar(() => setNota(t))}
              editable={!bloqueado}
              maxLength={200}
              style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
            />
          </Campo>
        ) : (
          <BotonTexto testID="anadir-nota" titulo="+ Añadir nota" onPress={() => setConNota(true)} />
        )}
        <Text testID="nota-entre-cuentas" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_ENTRE_CUENTAS}</Text>

        {estado.fase === 'RECHAZADO' ? (
          <View testID="error-dominio" accessibilityLiveRegion="assertive" style={[s.aviso, { backgroundColor: c.surfacePrimary, borderColor: c.critical, borderWidth: 1 }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>
              {`No se ha registrado. ${estado.codigo === 'FECHA_FUTURA' ? TEXTO_FECHA_FUTURA : estado.mensaje}`}
            </Text>
          </View>
        ) : null}
        {estado.fase === 'INDETERMINADO' ? (
          <View testID="estado-indeterminado" accessibilityLiveRegion="assertive" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{estado.mensaje}</Text>
          </View>
        ) : null}
        {!listo && estado.fase !== 'INDETERMINADO' && estado.fase !== 'ENVIANDO' ? (
          <Text testID="faltan" accessibilityLiveRegion="polite" style={[tipo.footnote, { color: c.textSecondary }]}>
            {`Para registrar falta: ${faltan.length === 1 ? faltan[0] : `${faltan.slice(0, -1).join(', ')} y ${faltan[faltan.length - 1]}`}.`}
          </Text>
        ) : null}
        {estado.fase === 'INDETERMINADO' ? (
          <BotonPrimario testID="reintentar" titulo="Reintentar" onPress={() => void enviarPayload(estado.payload)} />
        ) : (
          <BotonPrimario
            testID="registrar"
            titulo={estado.fase === 'ENVIANDO' ? 'Guardando…' : 'Registrar movimiento'}
            cargando={estado.fase === 'ENVIANDO'}
            deshabilitado={!listo}
            onPress={() => void registrar()}
          />
        )}
      </ScrollView>
      {hojaTipos ? <HojaTipos actual="TRANSFERENCIA" onElegir={cambiarTipo} onCancelar={() => setHojaTipos(false)} /> : null}
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

const s = StyleSheet.create({
  pantalla: { flex: 1, paddingHorizontal: espacio.l, justifyContent: 'space-between' },
  exito: { borderRadius: radio.l, padding: espacio.xl, alignItems: 'center', gap: espacio.s },
  cabTarea: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  form: { padding: espacio.l, gap: espacio.xl },
  importeCaja: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: radio.m, paddingHorizontal: espacio.l, gap: espacio.s, minHeight: 64 },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4, minWidth: 0 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  aviso: { borderRadius: radio.m, padding: espacio.m, gap: espacio.s },
});
