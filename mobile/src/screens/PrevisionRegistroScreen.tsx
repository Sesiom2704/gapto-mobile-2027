// ============================================================
// GAPTO MOBILE 2027
// Fichero: PrevisionRegistroScreen.tsx
// Ruta: mobile/src/screens/PrevisionRegistroScreen.tsx
// Descripción: Registrar desde la previsión (F05-06 M5 §B1; lámina PREV v0.2 A3/A4, C1/C2, D1/D2; D-PREV-03/04/05/15). Tarea inmersiva CREATE con los datos de la previsión como propuesta VISIBLE («De la previsión»): importe real (manda lo real, «Distinto de lo previsto»), tercero y categoría de la previsión (la categoría se puede quitar: «Sin categoría»), presupuesto, cuenta («Pagado con» / «Cobrado en» o «Desde» / «Hacia»), fecha (Hoy u otra, ≤ hoy) y «¿Queda cubierta la previsión?» SIN respuesta marcada: «Revisar» no se activa hasta elegir (P-PREV-02). La revisión separa «Se registra» (realidad y su movimiento) de «La previsión» (cubierta o pendiente) y dice que la previsión no mueve dinero (MONTH-RULE-06); en la transferencia, que no es gasto ni ingreso. Un envío sin respuesta se reintenta con la MISMA identidad (no duplica). Rechazos con el texto del servidor; «Ha cambiado; revisa» vuelve al detalle releído.
// Versión: 0.1.0 (F05-06 M5 §B1)
// ============================================================

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import type { ClienteApi, DetallePrevision, Respuesta } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato, Segmentado } from '../components/Basicos';
import { CabeceraTarea, Campo, estilosFormulario } from '../components/Formulario';
import { QuedaCubierta, usarIntencion } from '../components/Prevision';
import { ddmmaaaaAIso, diaMesIso, isoLocal } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import {
  componerRegistro,
  faltaRegistro,
  FormularioDesdePrevision,
  importeFila,
  intervaloTexto,
  textoEditable,
  TEXTO_SIN_DOBLE,
  TEXTO_TRANSFERENCIA_NEUTRA,
} from '../domain/prevision';
import { useTema } from '../theme/tema';
import { espacio, importe as estiloImporte, radio, tipo } from '../theme/tokens';

type Cuenta = { cuenta_id: string; nombre: string; propuesta?: boolean };
type Fase = 'EDITANDO' | 'REVISION' | 'ENVIANDO' | 'CONFIRMADO' | 'INDETERMINADO' | 'RECHAZADO';

const TITULO = { GASTO: 'Nuevo gasto', INGRESO: 'Nuevo ingreso', TRANSFERENCIA: 'Entre cuentas' } as const;
const BOTON = { GASTO: 'Registrar gasto', INGRESO: 'Registrar ingreso', TRANSFERENCIA: 'Registrar transferencia' } as const;

export function PrevisionRegistroScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  detalle: DetallePrevision;
  /** Desde el swipe «Abrir el formulario completo»: importe ya escrito. */
  importeInicial?: string | null;
  onCerrar: (registrado: boolean, releer?: boolean) => void;
}) {
  const { c } = useTema();
  const d = p.detalle;
  const tipoReg = (d.tipo === 'INGRESO' || d.tipo === 'TRANSFERENCIA' ? d.tipo : 'GASTO') as keyof typeof TITULO;
  const hoyIso = isoLocal(p.ahora());
  const intencion = usarIntencion(p.nuevoId);
  const [importeTexto, setImporteTexto] = useState(p.importeInicial ?? textoEditable(d.queda ?? d.importe_esperado));
  const [fechaOtra, setFechaOtra] = useState<string | null>(null);
  const [fechaOtraTexto, setFechaOtraTexto] = useState('');
  const [cuentaId, setCuentaId] = useState<string | null>(null);
  const [destinoId, setDestinoId] = useState<string | null>(null);
  const [presupuestable, setPresupuestable] = useState<boolean>(d.presupuestable);
  const [conCategoria, setConCategoria] = useState<boolean>(!!d.categoria);
  const [marcar, setMarcar] = useState<boolean | null>(null);
  const [cuentas, setCuentas] = useState<{ fase: 'CARGANDO' } | { fase: 'OK'; origen: Cuenta[]; destino: Cuenta[] } | { fase: 'ERROR' }>({ fase: 'CARGANDO' });
  const [fase, setFase] = useState<Fase>('EDITANDO');
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [codigo, setCodigo] = useState<string | null>(null);

  const fecha = fechaOtra ?? hoyIso;
  const prevista = tipoReg === 'INGRESO' ? d.cuenta_entrada : d.cuenta_salida;

  const cargarCuentas = useCallback(async () => {
    setCuentas({ fase: 'CARGANDO' });
    if (tipoReg === 'GASTO') {
      const r = await p.cliente.cuentasPago(fecha);
      if (r.tipo !== 'OK') return setCuentas({ fase: 'ERROR' });
      const lista = r.datos.cuentas.map((x) => ({ cuenta_id: x.cuenta_id, nombre: x.nombre, propuesta: x.propuesta_financiacion === 'SELF_100' }));
      return setCuentas({ fase: 'OK', origen: lista, destino: [] });
    }
    const [o, de] = await Promise.all([
      p.cliente.cuentasElegibles(tipoReg === 'INGRESO' ? 'INGRESO' : 'TRANSFERENCIA_ORIGEN', fecha),
      tipoReg === 'TRANSFERENCIA' ? p.cliente.cuentasElegibles('TRANSFERENCIA_DESTINO', fecha) : Promise.resolve(null),
    ]);
    if (o.tipo !== 'OK' || (de && de.tipo !== 'OK')) return setCuentas({ fase: 'ERROR' });
    setCuentas({ fase: 'OK', origen: o.datos.cuentas, destino: de && de.tipo === 'OK' ? de.datos.cuentas : [] });
  }, [p.cliente, fecha, tipoReg]);

  useEffect(() => {
    void cargarCuentas();
  }, [cargarCuentas]);

  // Propuesta visible «De la previsión»: la cuenta prevista si es elegible (nunca otra en silencio).
  useEffect(() => {
    if (cuentas.fase !== 'OK') return;
    if (cuentaId === null && prevista && cuentas.origen.some((x) => x.cuenta_id === prevista.id)) setCuentaId(prevista.id);
    if (tipoReg === 'TRANSFERENCIA' && destinoId === null && d.cuenta_entrada && cuentas.destino.some((x) => x.cuenta_id === d.cuenta_entrada!.id)) {
      setDestinoId(d.cuenta_entrada.id);
    }
  }, [cuentas]); // eslint-disable-line react-hooks/exhaustive-deps

  const imp = parsearImporte(importeTexto);
  const fechaValida = fecha <= hoyIso;
  const cuentaSel = cuentas.fase === 'OK' ? cuentas.origen.find((x) => x.cuenta_id === cuentaId) ?? null : null;
  const destinoSel = cuentas.fase === 'OK' ? cuentas.destino.find((x) => x.cuenta_id === destinoId) ?? null : null;
  const form: FormularioDesdePrevision = {
    importe: imp.ok ? imp.valor : null,
    fecha,
    cuentaId: cuentaSel ? cuentaId : null,
    cuentaDestinoId: tipoReg === 'TRANSFERENCIA' ? (destinoSel ? destinoId : null) : null,
    presupuestable,
    conCategoria,
    propuestaSelf100: !!cuentaSel?.propuesta,
    marcar,
  };
  const falta = faltaRegistro(d, form).concat(fechaValida ? [] : ['fecha (no puede ser futura)']);
  const distinto = imp.ok && d.importe_esperado !== null && imp.valor !== d.importe_esperado;

  const enviar = useCallback(async () => {
    const r = componerRegistro(d, form, intencion.actual());
    if (!r) return;
    setFase('ENVIANDO');
    let res: Respuesta<unknown>;
    if (r.ruta === 'GASTO') res = await p.cliente.registrarGastoPagado(r.payload as never);
    else if (r.ruta === 'INGRESO') res = await p.cliente.registrarIngresoCobrado(r.payload as never);
    else res = await p.cliente.registrarTransferencia(r.payload as never);
    if (res.tipo === 'OK') return setFase('CONFIRMADO');
    if (res.tipo === 'INDETERMINADO') {
      setMensaje(res.mensaje);
      return setFase('INDETERMINADO');
    }
    intencion.liberar();
    setCodigo(res.codigo);
    setMensaje(res.mensaje);
    setFase('RECHAZADO');
  }, [d, form, intencion, p.cliente]); // eslint-disable-line react-hooks/exhaustive-deps

  const cancelar = () => p.onCerrar(fase === 'CONFIRMADO');

  if (fase === 'CONFIRMADO') {
    return (
      <View testID="prevision-registro-exito" style={[s.raiz, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Registrado" onCancelar={() => p.onCerrar(true)} testIDCancelar="prevision-registro-cerrar" />
        <View style={estilosFormulario.cuerpo}>
          <Text style={[tipo.titleSmall, { color: c.textPrimary }]}>{`${formatearEur(form.importe ?? '0.00')} registrados`}</Text>
          <Text testID="prevision-registro-exito-prevision" style={[tipo.body, { color: c.textSecondary }]}>
            {marcar ? `La previsión «${d.concepto}» queda cubierta.` : `La previsión «${d.concepto}» sigue pendiente: falta una parte.`}
          </Text>
          <BotonPrimario testID="prevision-registro-listo" titulo="Listo" onPress={() => p.onCerrar(true)} />
        </View>
      </View>
    );
  }

  const revision = fase === 'REVISION' || fase === 'ENVIANDO' || fase === 'INDETERMINADO' || fase === 'RECHAZADO';
  return (
    <KeyboardAvoidingView style={[s.raiz, { backgroundColor: c.background }]} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <CabeceraTarea
        titulo={revision ? 'Revisar' : TITULO[tipoReg]}
        onCancelar={revision && fase !== 'ENVIANDO' && fase !== 'INDETERMINADO' ? () => setFase('EDITANDO') : cancelar}
        testIDCancelar="prevision-registro-cancelar"
      />
      <ScrollView contentContainerStyle={estilosFormulario.cuerpo} keyboardShouldPersistTaps="handled">
        {revision ? (
          <Revision d={d} form={form} cuenta={cuentaSel?.nombre ?? ''} destino={destinoSel?.nombre ?? null} />
        ) : (
          <>
            <View testID="de-la-prevision" style={[s.cabPrev, { backgroundColor: c.accentSurface }]}>
              <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{`${d.concepto} · previsión ${importeFila(d)}`}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>
                {[d.tercero?.nombre, intervaloTexto(d), prevista?.nombre].filter(Boolean).join(' · ')}
              </Text>
            </View>
            <Campo etiqueta="Importe real">
              <TextInput testID="prevision-importe" accessibilityLabel="Importe real" value={importeTexto} onChangeText={setImporteTexto}
                keyboardType="decimal-pad" style={[estiloImporte.secondary, s.input, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]} />
              {distinto ? <Text testID="prevision-distinto" style={[tipo.caption, { color: c.textSecondary }]}>Distinto de lo previsto</Text> : null}
            </Campo>
            {d.tercero && tipoReg !== 'TRANSFERENCIA' ? (
              <Campo etiqueta={tipoReg === 'INGRESO' ? 'De' : 'Tercero'}>
                <Text testID="prevision-tercero" style={[tipo.body, { color: c.textPrimary }]}>{`${d.tercero.nombre} · De la previsión`}</Text>
              </Campo>
            ) : null}
            {d.categoria && tipoReg !== 'TRANSFERENCIA' ? (
              <Campo etiqueta="Categoría">
                <View style={estilosFormulario.chips}>
                  <Chip testID="prevision-categoria" etiqueta={`${d.categoria.nombre} · De la previsión`} seleccionado={conCategoria} onPress={() => setConCategoria(true)} />
                  <Chip testID="prevision-sin-categoria" etiqueta="Sin categoría" seleccionado={!conCategoria} onPress={() => setConCategoria(false)} />
                </View>
              </Campo>
            ) : null}
            {tipoReg !== 'TRANSFERENCIA' ? (
              <Campo etiqueta="¿Cuenta para el presupuesto? · De la previsión">
                <Segmentado testIDBase="prevision-presupuestable" etiquetaGrupo="¿Cuenta para el presupuesto?" valor={presupuestable}
                  opciones={[{ valor: true, etiqueta: 'Sí' }, { valor: false, etiqueta: 'No' }]} onCambiar={setPresupuestable} />
              </Campo>
            ) : null}
            <Campo etiqueta={tipoReg === 'GASTO' ? 'Pagado con' : tipoReg === 'INGRESO' ? 'Cobrado en' : 'Desde'}>
              <ListaCuentas cuentas={cuentas} lista={cuentas.fase === 'OK' ? cuentas.origen : []} sel={cuentaId} prevista={prevista?.id ?? null}
                onElegir={setCuentaId} onReintentar={cargarCuentas} testIDBase="prevision-cuenta" />
            </Campo>
            {tipoReg === 'TRANSFERENCIA' ? (
              <Campo etiqueta="Hacia">
                <ListaCuentas cuentas={cuentas} lista={cuentas.fase === 'OK' ? cuentas.destino.filter((x) => x.cuenta_id !== cuentaId) : []} sel={destinoId}
                  prevista={d.cuenta_entrada?.id ?? null} onElegir={setDestinoId} onReintentar={cargarCuentas} testIDBase="prevision-destino" />
              </Campo>
            ) : null}
            <Campo etiqueta="Fecha">
              <View style={estilosFormulario.chips}>
                <Chip testID="prevision-fecha-hoy" etiqueta={`Hoy ${diaMesIso(hoyIso)}`} seleccionado={fechaOtra === null} onPress={() => setFechaOtra(null)} />
                <TextInput testID="prevision-fecha-otra" accessibilityLabel="Otra fecha (dd/mm/aaaa)" placeholder="Otra fecha dd/mm/aaaa" placeholderTextColor={c.textSecondary}
                  value={fechaOtraTexto} onChangeText={(t) => { setFechaOtraTexto(t); setFechaOtra(ddmmaaaaAIso(t)); }}
                  style={[tipo.body, s.input, s.fecha, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]} />
              </View>
            </Campo>
            <QuedaCubierta valor={marcar} onCambiar={setMarcar} />
          </>
        )}
        {fase === 'RECHAZADO' && mensaje ? (
          <View testID="prevision-registro-rechazo" accessibilityRole="alert" style={[s.caja, { backgroundColor: c.partialSurface, borderColor: c.warning }]}>
            <Text style={[tipo.footnote, { color: c.textPrimary }]}>{mensaje}</Text>
            {codigo === 'VERSION_DESFASADA' || codigo === 'ESTADO_PREVISION_INCOMPATIBLE' ? (
              <BotonTexto testID="prevision-registro-releer" titulo="Ver la previsión de nuevo" onPress={() => p.onCerrar(false, true)} />
            ) : null}
          </View>
        ) : null}
        {fase === 'INDETERMINADO' && mensaje ? (
          <View testID="prevision-registro-indeterminado" accessibilityRole="alert" style={[s.caja, { backgroundColor: c.partialSurface, borderColor: c.warning }]}>
            <Text style={[tipo.footnote, { color: c.textPrimary }]}>{mensaje}</Text>
          </View>
        ) : null}
        {!revision ? (
          <>
            {falta.length > 0 ? <Text testID="prevision-falta" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${falta.join(', ')}`}</Text> : null}
            <BotonPrimario testID="prevision-revisar" titulo="Revisar" deshabilitado={falta.length > 0} onPress={() => setFase('REVISION')} />
          </>
        ) : (
          <BotonPrimario
            testID="prevision-registrar"
            titulo={fase === 'INDETERMINADO' ? 'Reintentar' : fase === 'ENVIANDO' ? 'Guardando…' : BOTON[tipoReg]}
            cargando={fase === 'ENVIANDO'}
            deshabilitado={fase === 'RECHAZADO'}
            onPress={enviar}
          />
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function ListaCuentas(p: {
  cuentas: { fase: string };
  lista: Cuenta[];
  sel: string | null;
  prevista: string | null;
  onElegir: (id: string) => void;
  onReintentar: () => void;
  testIDBase: string;
}) {
  const { c } = useTema();
  if (p.cuentas.fase === 'CARGANDO') return <EstadoDato estado="CARGANDO" />;
  if (p.cuentas.fase === 'ERROR') return <BotonTexto testID={`${p.testIDBase}-reintentar`} titulo="No se pudieron cargar las cuentas · Reintentar" onPress={p.onReintentar} />;
  if (p.lista.length === 0) return <Text style={[tipo.footnote, { color: c.textSecondary }]}>No hay cuentas disponibles para esta operación.</Text>;
  return (
    <View style={estilosFormulario.chips}>
      {p.lista.map((x) => (
        <Chip key={x.cuenta_id} testID={`${p.testIDBase}-${x.cuenta_id}`} seleccionado={p.sel === x.cuenta_id} onPress={() => p.onElegir(x.cuenta_id)}
          etiqueta={x.cuenta_id === p.prevista ? `${x.nombre} · De la previsión` : x.nombre} />
      ))}
    </View>
  );
}

function Revision({ d, form, cuenta, destino }: { d: DetallePrevision; form: FormularioDesdePrevision; cuenta: string; destino: string | null }) {
  const { c } = useTema();
  const importe = form.importe ?? '0.00';
  const quien = [d.tercero?.nombre, form.conCategoria ? d.categoria?.nombre : null].filter(Boolean).join(' · ') || d.concepto;
  const realidad = d.tipo === 'INGRESO' ? 'Ingreso real' : d.tipo === 'TRANSFERENCIA' ? 'Entre cuentas' : 'Gasto real';
  const conMovimiento = useMemo(() => (d.tipo === 'INGRESO' ? `+${formatearEur(importe)}` : `−${formatearEur(importe)}`), [d.tipo, importe]);
  return (
    <View style={{ gap: espacio.l }}>
      <View testID="revision-se-registra" style={[s.bloque, { borderColor: c.borderDefault }]}>
        <Text accessibilityRole="header" style={[tipo.caption, { color: c.textSecondary, fontWeight: '600' }]}>SE REGISTRA</Text>
        {d.tipo === 'TRANSFERENCIA' ? (
          <>
            <FilaRev izq={`${cuenta} · Sale · ${diaMesIso(form.fecha)}`} der={`−${formatearEur(importe)}`} />
            <FilaRev izq={`${destino ?? ''} · Entra · ${diaMesIso(form.fecha)}`} der={`+${formatearEur(importe)}`} />
          </>
        ) : (
          <>
            <FilaRev izq={`${quien} · ${realidad} · ${diaMesIso(form.fecha)}`} der={formatearEur(importe)} />
            <FilaRev izq={`${cuenta} · Movimiento real`} der={conMovimiento} />
          </>
        )}
      </View>
      <View testID="revision-la-prevision" style={[s.bloque, { borderColor: c.borderDefault }]}>
        <Text accessibilityRole="header" style={[tipo.caption, { color: c.textSecondary, fontWeight: '600' }]}>LA PREVISIÓN</Text>
        <FilaRev izq={`${d.concepto} · esperado ${importeFila(d)}`} der={form.marcar ? 'Cubierta' : 'Pendiente'} />
        <Text testID="revision-consecuencia" style={[tipo.footnote, { color: c.textSecondary }]}>
          {form.marcar ? `Queda cubierta con ${d.tipo === 'TRANSFERENCIA' ? 'esta transferencia' : d.tipo === 'INGRESO' ? 'este cobro' : 'este pago'}.` : 'Sigue pendiente: falta una parte.'}
        </Text>
      </View>
      <Text testID="revision-sin-doble" style={[tipo.footnote, { color: c.textSecondary }]}>{d.tipo === 'TRANSFERENCIA' ? TEXTO_TRANSFERENCIA_NEUTRA : TEXTO_SIN_DOBLE}</Text>
    </View>
  );
}

function FilaRev({ izq, der }: { izq: string; der: string }) {
  const { c } = useTema();
  return (
    <View style={s.filaRev}>
      <Text style={[tipo.subheadline, { color: c.textPrimary, flex: 1 }]}>{izq}</Text>
      <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600', fontVariant: ['tabular-nums'] }]}>{der}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  raiz: { flex: 1 },
  cabPrev: { borderRadius: radio.m, padding: espacio.m, gap: 2 },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: 48 },
  fecha: { flex: 1, minWidth: 160 },
  caja: { borderRadius: radio.m, borderWidth: 1, padding: espacio.m, gap: espacio.s },
  bloque: { borderWidth: 1, borderRadius: radio.m, padding: espacio.m, gap: espacio.s },
  filaRev: { flexDirection: 'row', justifyContent: 'space-between', gap: espacio.m },
});
