// ============================================================
// GAPTO MOBILE 2027
// Fichero: CorregirRepartoScreen.tsx
// Ruta: mobile/src/screens/CorregirRepartoScreen.tsx
// Descripción: «Corregir reparto» desde el detalle (F05-06 M3; lámina REP v0.2 E6, P-REP-04; F05 §57 F05-D043, que manda sobre la lámina). Solo cambia los importes de quien ya está en el reparto y, con ellos, la deuda que corresponde a esa parte (AJ-M3-DEC-01/09); el total del gasto no cambia y las partes suman lo mismo. Lo que esta versión no hace se ve atenuado con su motivo en lenguaje llano (§57.1.1): añadir o quitar a alguien, pasar de invitado a que te deba o al revés, y «Le debo esto» (E1, AJ-M3-DEC-04). Si el gasto no se puede corregir (otro tipo, viene de V3, sin reparto o no activo), se dice por qué y no se ofrece ninguna alternativa que el motor no admita (no se promete «anular y registrar de nuevo»). Revisión de impacto (patrón EDIT-HECHO A3): parte a parte antes → después, lo que cambia en las deudas y en tu gasto, y motivo obligatorio. Guardar es un cambio con `row_version`: un INDETERMINADO pide volver a cargar antes de repetir; un rechazo se explica sin texto técnico y, si el gasto cambió, se recarga.
// Versión: 0.1.0 (F05-06 M3 §B1)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { Aviso, Bloque, CabeceraTarea, Campo, FilaRevision, Inicial, OpcionAtenuada, s } from '../components/Reparto';
import { formatearEur } from '../domain/importe';
import {
  cambiosCorreccion,
  componerCorreccion,
  deltaTuParte,
  EXCLUIDO_CORRECCION,
  faltaCorreccion,
  MOTIVO_NO_CORREGIBLE,
  motivoRechazoCorreccion,
  RepartoDeHecho,
  textoCambioDeuda,
  textoDe,
  textoSaldo,
} from '../domain/reparto';
import { useTema } from '../theme/tema';
import { espacio, importe, tipo } from '../theme/tokens';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; r: RepartoDeHecho };
type Envio =
  | { fase: 'EDITANDO' }
  | { fase: 'REVISANDO' }
  | { fase: 'ENVIANDO' }
  | { fase: 'INDETERMINADO'; mensaje: string }
  | { fase: 'RECHAZADO'; mensaje: string }
  | { fase: 'CONFIRMADO'; tuParte: string | null };

export const MOTIVOS_CORRECCION = ['Me equivoqué al repartir', 'Otro dato mal elegido'];

export function CorregirRepartoScreen(p: { cliente: ClienteApi; hechoId: string; titulo?: string; onCerrar: (cambios: boolean) => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [textos, setTextos] = useState<Record<string, string>>({});
  const [motivo, setMotivo] = useState('');
  const [motivoOtro, setMotivoOtro] = useState(false);
  const [envio, setEnvio] = useState<Envio>({ fase: 'EDITANDO' });
  /** El gasto cambió mientras se editaba: se recarga y se vuelve a la edición avisando. */
  const [recargado, setRecargado] = useState(false);
  const enVuelo = useRef(false);

  const cargar = async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.repartoDeHecho(p.hechoId);
    if (r.tipo !== 'OK') return setCarga({ fase: 'ERROR' });
    setCarga({ fase: 'OK', r: r.datos });
    setTextos(Object.fromEntries(r.datos.partes.map((x) => [x.atribucion_id, textoDe(x.importe)])));
  };
  useEffect(() => {
    void cargar();
  }, [p.hechoId]);

  const bloqueado = envio.fase === 'ENVIANDO' || envio.fase === 'INDETERMINADO' || envio.fase === 'CONFIRMADO';
  const editar = (f: () => void) => {
    if (bloqueado) return;
    if (envio.fase === 'RECHAZADO') setEnvio({ fase: 'REVISANDO' }); // el rechazo llega en la revisión: se sigue en ella
    f();
  };

  const guardar = async (r: RepartoDeHecho) => {
    if (enVuelo.current || faltaCorreccion(r, textos, motivo).length > 0) return;
    enVuelo.current = true;
    setEnvio({ fase: 'ENVIANDO' });
    try {
      const res = await p.cliente.corregirReparto(p.hechoId, componerCorreccion(r, textos, motivo));
      if (res.tipo === 'OK') setEnvio({ fase: 'CONFIRMADO', tuParte: res.datos.tu_parte });
      else if (res.tipo === 'RECHAZADO') {
        if (res.codigo === 'VERSION_DESFASADA') {
          setRecargado(true);
          setEnvio({ fase: 'EDITANDO' });
          void cargar();
        } else setEnvio({ fase: 'RECHAZADO', mensaje: motivoRechazoCorreccion(res.codigo, res.detalle) });
      } else setEnvio({ fase: 'INDETERMINADO', mensaje: res.mensaje });
    } finally {
      enVuelo.current = false;
    }
  };

  const cabecera = (titulo: string, izquierda: React.ReactNode) => <CabeceraTarea titulo={titulo} izquierda={izquierda} />;

  if (envio.fase === 'CONFIRMADO') {
    return (
      <View testID="corregir-exito" style={[s.pantalla, { backgroundColor: c.background, paddingTop: inset.top + espacio.xl, paddingBottom: inset.bottom + espacio.l }]}>
        <View style={[s.exito, { backgroundColor: c.surfacePrimary }]} accessibilityLiveRegion="polite">
          <Text style={{ fontSize: 40 }} accessibilityElementsHidden>✓</Text>
          <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>Reparto corregido</Text>
          <Text testID="corregir-exito-tu-parte" style={[importe.secondary, { color: c.textPrimary }]}>
            {envio.tuParte ? `Tu parte: ${formatearEur(envio.tuParte)}` : 'Tu parte: sin indicar'}
          </Text>
        </View>
        <BotonPrimario testID="corregir-hecho" titulo="Hecho" onPress={() => p.onCerrar(true)} />
      </View>
    );
  }

  if (carga.fase !== 'OK') {
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        {cabecera('Corregir reparto', <BotonTexto testID="corregir-cancelar" titulo="Cancelar" onPress={() => p.onCerrar(false)} />)}
        <View style={s.form}>
          {carga.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
          {carga.fase === 'ERROR' ? (
            <>
              <EstadoDato estado="ERROR_CARGA" detalle="No se ha podido cargar el reparto." />
              <BotonTexto testID="corregir-reintentar-carga" titulo="Reintentar" onPress={() => void cargar()} />
            </>
          ) : null}
        </View>
      </View>
    );
  }
  const r = carga.r;

  if (!r.corregible) {
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        {cabecera('Corregir reparto', <BotonTexto testID="corregir-cancelar" titulo="‹ Atrás" onPress={() => p.onCerrar(false)} />)}
        <View style={s.form}>
          <Aviso testID="corregir-no-corregible" texto={MOTIVO_NO_CORREGIBLE[r.motivo ?? ''] ?? 'El reparto de este gasto no se puede corregir.'} />
        </View>
      </View>
    );
  }

  const cambios = cambiosCorreccion(r, textos);
  const faltan = faltaCorreccion(r, textos, motivo);
  const faltanEdicion = faltan.filter((x) => x !== 'el motivo');

  // ---------------------------------------------------------------- revisión de impacto (E6)
  if (envio.fase !== 'EDITANDO') {
    const delta = deltaTuParte(cambios, r);
    const deudas = cambios.map(textoCambioDeuda).filter((x): x is string => x !== null);
    return (
      <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {cabecera('Revisar cambios', <BotonTexto testID="corregir-revision-atras" titulo="‹ Atrás" onPress={() => (bloqueado ? undefined : setEnvio({ fase: 'EDITANDO' }))} />)}
        <ScrollView testID="corregir-revision" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Bloque titulo="Vas a cambiar el reparto" testID="corregir-cambios">
            {cambios.map((x) => (
              <FilaRevision key={x.atribucionId} testID={`corregir-cambio-${x.atribucionId}`} titulo={x.nombre} valor={`${formatearEur(x.antes)} → ${formatearEur(x.despues)}`} />
            ))}
          </Bloque>
          <Bloque titulo="Esto también cambia" testID="corregir-impacto">
            {deudas.map((d) => (
              <Text key={d} testID="corregir-impacto-deuda" style={[tipo.body, { color: c.textPrimary }]}>{d}</Text>
            ))}
            <FilaRevision testID="corregir-impacto-tu-gasto" titulo="Tu gasto en el Resultado" valor={delta ?? 'Sin cambios'} />
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`El total del gasto sigue siendo ${formatearEur(r.importe)}. No se mueve dinero.`}</Text>
          </Bloque>
          <Campo etiqueta="Motivo obligatorio">
            <View style={s.chips}>
              {MOTIVOS_CORRECCION.map((m) => (
                <Chip key={m} testID={`corregir-motivo-${MOTIVOS_CORRECCION.indexOf(m)}`} etiqueta={m} seleccionado={!motivoOtro && motivo === m}
                  onPress={() => editar(() => { setMotivoOtro(false); setMotivo(m); })} />
              ))}
              <Chip testID="corregir-motivo-otro" etiqueta="Otro…" seleccionado={motivoOtro} onPress={() => editar(() => { setMotivoOtro(true); setMotivo(''); })} />
            </View>
            {motivoOtro ? (
              <TextInput testID="corregir-motivo-texto" accessibilityLabel="Motivo" value={motivo} onChangeText={(t) => editar(() => setMotivo(t))} editable={!bloqueado}
                maxLength={500} style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]} />
            ) : null}
          </Campo>
          {envio.fase === 'RECHAZADO' ? <Aviso testID="corregir-error" critico texto={`No se ha guardado. ${envio.mensaje}`} /> : null}
          {envio.fase === 'INDETERMINADO' ? (
            <>
              <Aviso testID="corregir-indeterminado" texto={envio.mensaje} />
              <BotonPrimario testID="corregir-recargar" titulo="Volver a cargar" onPress={() => { setEnvio({ fase: 'EDITANDO' }); void cargar(); }} />
            </>
          ) : (
            <BotonPrimario testID="corregir-guardar" titulo={envio.fase === 'ENVIANDO' ? 'Guardando…' : 'Guardar cambios'} cargando={envio.fase === 'ENVIANDO'}
              deshabilitado={faltan.length > 0} onPress={() => void guardar(r)} />
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  // ---------------------------------------------------------------- edición (B2 sobre lo registrado)
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {cabecera('Corregir reparto', <BotonTexto testID="corregir-cancelar" titulo="Cancelar" onPress={() => p.onCerrar(false)} />)}
      <ScrollView testID="corregir-form" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <View style={s.kv}>
          <Text style={[tipo.body, { color: c.textSecondary }]}>{p.titulo ?? 'Total del hecho'}</Text>
          <Text testID="corregir-total" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{formatearEur(r.importe)}</Text>
        </View>
        {r.partes.map((x) => (
          <View key={x.atribucion_id} testID={`corregir-parte-${x.atribucion_id}`} style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
            <View style={s.kv}>
              <Inicial nombre={x.es_yo ? 'Yo' : x.nombre} />
              <View style={{ flex: 1 }}>
                <Text style={[tipo.body, { color: c.textPrimary }]}>{x.nombre}</Text>
                {x.posicion ? (
                  <Text style={[tipo.footnote, { color: c.textSecondary }]}>
                    {x.posicion.tipo === 'DERECHO_COBRO' ? `Te debe · pendiente ${textoSaldo(x.posicion.saldo)}` : `Le debes · pendiente ${textoSaldo(x.posicion.saldo)}`}
                  </Text>
                ) : !x.es_yo ? (
                  <Text style={[tipo.footnote, { color: c.textSecondary }]}>No te debe nada</Text>
                ) : null}
              </View>
              <TextInput testID={`corregir-importe-${x.atribucion_id}`} accessibilityLabel={`Parte de ${x.nombre} en euros`} value={textos[x.atribucion_id] ?? ''}
                onChangeText={(t) => editar(() => setTextos((y) => ({ ...y, [x.atribucion_id]: t })))} editable={!bloqueado}
                keyboardType="decimal-pad" inputMode="decimal" style={[tipo.body, s.inputImporte, { color: c.textPrimary, borderColor: c.borderStandard }]} />
            </View>
            {!x.es_yo ? (
              <View style={{ gap: espacio.s }}>
                <OpcionAtenuada testID={`corregir-quitar-${x.atribucion_id}`} {...EXCLUIDO_CORRECCION.QUITAR_PERSONA} />
                {x.posicion?.tipo === 'DERECHO_COBRO' ? (
                  <OpcionAtenuada testID={`corregir-deudor-a-invitado-${x.atribucion_id}`} {...EXCLUIDO_CORRECCION.DEUDOR_A_INVITADO} />
                ) : !x.posicion ? (
                  <OpcionAtenuada testID={`corregir-invitado-a-deudor-${x.atribucion_id}`} {...EXCLUIDO_CORRECCION.INVITADO_A_DEUDOR} />
                ) : null}
              </View>
            ) : null}
          </View>
        ))}
        <OpcionAtenuada testID="corregir-anadir" {...EXCLUIDO_CORRECCION.ANADIR_PERSONA} />
        {!r.partes.some((x) => x.es_yo && x.posicion) ? <OpcionAtenuada testID="corregir-le-debo" {...EXCLUIDO_CORRECCION.LE_DEBO_ESTO} /> : null}
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>Si alguien ya te ha pagado parte, su deuda no puede quedar por debajo de lo pagado.</Text>
        {recargado ? <Aviso testID="corregir-recargado" texto={motivoRechazoCorreccion('VERSION_DESFASADA')} /> : null}
        {faltanEdicion.length > 0 ? (
          <Text testID="corregir-faltan" style={[tipo.footnote, { color: c.textSecondary }]}>{`Para revisar falta: ${faltanEdicion.join(', ')}.`}</Text>
        ) : null}
        <BotonPrimario testID="corregir-revisar" titulo="Revisar cambios" deshabilitado={faltanEdicion.length > 0}
          onPress={() => { if (faltanEdicion.length === 0) setEnvio({ fase: 'REVISANDO' }); }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
