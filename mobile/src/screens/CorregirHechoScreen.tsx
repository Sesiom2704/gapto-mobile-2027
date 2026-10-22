// ============================================================
// GAPTO MOBILE 2027
// Fichero: CorregirHechoScreen.tsx
// Ruta: mobile/src/screens/CorregirHechoScreen.tsx
// Descripción: «Corregir» un registro (F05-06 M1; lámina EDIT-HECHO v0.1 A2, A3, B3, B4; D-EDIT-02..05, 07, 08; P-EDIT-03, 05; CONTRATO_M1 v0.1 §2; F05 §61.2). Solo para datos que nunca fueron ciertos (INV-07): la línea fija lo dice arriba. Formulario precargado con lo registrado: importe, fecha y cuenta de un pago simple, o importe, fecha y cuentas de una transferencia (el importe se corrige siempre con su movimiento, P-EDIT-03); cada campo cambiado lleva «Editado» y conserva el valor anterior a la vista. «Revisar cambios» enseña cada cambio antes → después y lo que arrastra (movimiento de la cuenta y, en un gasto, el Resultado del mes), con motivo obligatorio (opciones fijas más «Otro…») y «Guardar cambios». Un conflicto de versión (B3) no pisa nada: «Este registro ha cambiado mientras lo corregías» con lo que hay ahora, «Recargar y volver a corregir» o «Descartar». Sin respuesta del servidor, el reintento usa la MISMA intención (el motor no corrige dos veces). Si el registro no se puede corregir, se dice por qué (la elegibilidad viene del servidor, que además revalida al guardar).
// Versión: 0.1.0 (F05-06 M1)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaElegible, EdicionHecho, OperacionCuenta } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { Aviso, Bloque, CabeceraTarea, Campo, FilaRevision, s } from '../components/Reparto';
import { usarIntencion } from '../components/Prevision';
import {
  cambiosEdicion,
  componerCorreccion,
  ETIQUETA_CAMPO,
  esTransferencia,
  faltaEdicion,
  formularioInicial,
  MOTIVOS_CORREGIR,
  TEXTO_SE_CORRIGE_EN_SITIO,
  TEXTO_SOLO_ERRORES,
  type CambioEdicion,
  type FormularioEdicion,
} from '../domain/edicion';
import { ayer, ddmmaaaaAIso, diaMesAnioIso, isoLocal } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

type Carga = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; e: EdicionHecho };
type Envio =
  | { fase: 'EDITANDO' }
  | { fase: 'REVISANDO' }
  | { fase: 'ENVIANDO' }
  | { fase: 'INDETERMINADO'; mensaje: string }
  | { fase: 'RECHAZADO'; mensaje: string }
  | { fase: 'CONFLICTO'; ahora: EdicionHecho | null; querias: CambioEdicion[] }
  | { fase: 'CONFIRMADO' };

export function CorregirHechoScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  hechoId: string;
  titulo: string;
  onCerrar: (cambios: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [form, setForm] = useState<FormularioEdicion | null>(null);
  const [fechaTexto, setFechaTexto] = useState('');
  const [cuentas, setCuentas] = useState<{ salida: CuentaElegible[]; entrada: CuentaElegible[] }>({ salida: [], entrada: [] });
  const [motivo, setMotivo] = useState('');
  const [motivoOtro, setMotivoOtro] = useState(false);
  const [envio, setEnvio] = useState<Envio>({ fase: 'EDITANDO' });
  const intencion = usarIntencion(p.nuevoId);
  const enVuelo = useRef(false);

  const cargar = async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.edicionHecho(p.hechoId);
    if (r.tipo !== 'OK') return setCarga({ fase: 'ERROR' });
    const e = r.datos;
    setCarga({ fase: 'OK', e });
    setForm(formularioInicial(e));
    setFechaTexto('');
    const ops: [OperacionCuenta, OperacionCuenta | null] = esTransferencia(e) ? ['TRANSFERENCIA_ORIGEN', 'TRANSFERENCIA_DESTINO'] : ['GASTO', null];
    const [sal, ent] = await Promise.all([p.cliente.cuentasElegibles(ops[0], e.fecha), ops[1] ? p.cliente.cuentasElegibles(ops[1], e.fecha) : null]);
    setCuentas({ salida: sal.tipo === 'OK' ? sal.datos.cuentas : [], entrada: ent && ent.tipo === 'OK' ? ent.datos.cuentas : [] });
  };
  useEffect(() => {
    void cargar();
  }, [p.hechoId]);

  const cerrar = (cambios: boolean) => p.onCerrar(cambios);
  const cabecera = (titulo: string, izquierda: React.ReactNode) => <CabeceraTarea titulo={titulo} izquierda={izquierda} />;

  if (envio.fase === 'CONFIRMADO') {
    return (
      <View testID="corregir-hecho-exito" style={[s.pantalla, { backgroundColor: c.background, paddingTop: inset.top + espacio.xl, paddingBottom: inset.bottom + espacio.l }]}>
        <View style={[s.exito, { backgroundColor: c.surfacePrimary }]} accessibilityLiveRegion="polite">
          <Text style={{ fontSize: 40 }} accessibilityElementsHidden>✓</Text>
          <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>Registro corregido</Text>
          <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>{TEXTO_SE_CORRIGE_EN_SITIO}</Text>
        </View>
        <BotonPrimario testID="corregir-hecho-listo" titulo="Hecho" onPress={() => cerrar(true)} />
      </View>
    );
  }

  if (carga.fase !== 'OK' || !form) {
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        {cabecera('Corregir', <BotonTexto testID="corregir-hecho-cancelar" titulo="Cancelar" onPress={() => cerrar(false)} />)}
        <View style={s.form}>
          {carga.fase === 'ERROR' ? (
            <>
              <EstadoDato estado="ERROR_CARGA" detalle="No se ha podido cargar el registro." />
              <BotonTexto testID="corregir-hecho-reintentar" titulo="Reintentar" onPress={() => void cargar()} />
            </>
          ) : <EstadoDato estado="CARGANDO" />}
        </View>
      </View>
    );
  }
  const e = carga.e;
  const transferencia = esTransferencia(e);
  const nombreCuenta = (id: string) =>
    [...cuentas.salida, ...cuentas.entrada].find((x) => x.cuenta_id === id)?.nombre ?? e.movimientos.find((m) => m.cuenta.id === id)?.cuenta.nombre ?? 'Cuenta';
  const valorCambio = (x: CambioEdicion, v: string) =>
    x.campo === 'importe' ? formatearEur(v) : x.campo === 'fecha' ? diaMesAnioIso(v) : nombreCuenta(v);

  if (!e.acciones.corregir.disponible) {
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        {cabecera('Corregir', <BotonTexto testID="corregir-hecho-cancelar" titulo="‹ Atrás" onPress={() => cerrar(false)} />)}
        <View style={s.form}>
          <Aviso testID="corregir-hecho-no-corregible" texto={e.acciones.corregir.motivo ?? 'Este registro no se puede corregir desde aquí.'} />
        </View>
      </View>
    );
  }

  const cambios = cambiosEdicion(e, form);
  const faltanForm = faltaEdicion(e, form, null);
  const faltan = faltaEdicion(e, form, motivo);
  const bloqueado = envio.fase === 'ENVIANDO';

  const guardar = async () => {
    if (enVuelo.current || faltan.length > 0) return;
    enVuelo.current = true;
    setEnvio({ fase: 'ENVIANDO' });
    try {
      const comp = componerCorreccion(e, form, motivo, intencion.actual());
      const r = comp.ruta === 'PAGO' ? await p.cliente.corregirPago(e.hecho_id, comp.payload) : await p.cliente.corregirTransferencia(e.hecho_id, comp.payload);
      if (r.tipo === 'OK') {
        intencion.liberar();
        return setEnvio({ fase: 'CONFIRMADO' });
      }
      if (r.tipo === 'INDETERMINADO') return setEnvio({ fase: 'INDETERMINADO', mensaje: `${r.mensaje} Puedes reintentar: no se corregirá dos veces.` });
      intencion.liberar();
      if (r.codigo === 'VERSION_DESFASADA') {
        const ahora = ((r.detalle as { edicion?: EdicionHecho } | undefined)?.edicion) ?? null;
        return setEnvio({ fase: 'CONFLICTO', ahora, querias: cambios });
      }
      setEnvio({ fase: 'RECHAZADO', mensaje: r.mensaje });
    } finally {
      enVuelo.current = false;
    }
  };

  // ---------------------------------------------------------------- B3 · conflicto de versión
  if (envio.fase === 'CONFLICTO') {
    const ahora = envio.ahora;
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        {cabecera('Revisar cambios', <BotonTexto testID="corregir-hecho-descartar-arriba" titulo="‹ Atrás" onPress={() => cerrar(true)} />)}
        <ScrollView testID="corregir-hecho-conflicto" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Aviso testID="corregir-hecho-cambiado" critico texto="Este registro ha cambiado mientras lo corregías. Tus cambios no se han aplicado." />
          {ahora ? (
            <Bloque titulo="Ahora mismo" testID="corregir-hecho-ahora">
              <FilaRevision testID="corregir-hecho-ahora-importe" titulo="Importe" valor={ahora.importe ? formatearEur(ahora.importe) : '—'} />
              <FilaRevision testID="corregir-hecho-ahora-fecha" titulo="Fecha" valor={diaMesAnioIso(ahora.fecha)} />
            </Bloque>
          ) : null}
          <Bloque titulo="Lo que querías" testID="corregir-hecho-querias">
            {envio.querias.map((x) => (
              <FilaRevision key={x.campo} testID={`corregir-hecho-querias-${x.campo}`} titulo={ETIQUETA_CAMPO[x.campo]} valor={`${valorCambio(x, x.antes)} → ${valorCambio(x, x.despues)}`} />
            ))}
          </Bloque>
          <BotonPrimario testID="corregir-hecho-recargar" titulo="Recargar y volver a corregir" onPress={() => { setEnvio({ fase: 'EDITANDO' }); setMotivo(''); setMotivoOtro(false); void cargar(); }} />
          <BotonTexto testID="corregir-hecho-descartar" titulo="Descartar" onPress={() => cerrar(true)} />
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- A3 · revisión del impacto
  if (envio.fase !== 'EDITANDO') {
    const importe = cambios.find((x) => x.campo === 'importe');
    const delta = importe ? (Number(importe.despues) - Number(importe.antes)).toFixed(2) : null;
    return (
      <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        {cabecera('Revisar cambios', <BotonTexto testID="corregir-hecho-revision-atras" titulo="‹ Atrás" onPress={() => (bloqueado ? undefined : setEnvio({ fase: 'EDITANDO' }))} />)}
        <ScrollView testID="corregir-hecho-revision" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Bloque titulo="Vas a cambiar" testID="corregir-hecho-cambios">
            {cambios.map((x) => (
              <FilaRevision key={x.campo} testID={`corregir-hecho-cambio-${x.campo}`} titulo={ETIQUETA_CAMPO[x.campo]} valor={`${valorCambio(x, x.antes)} → ${valorCambio(x, x.despues)}`} />
            ))}
          </Bloque>
          {importe ? (
            <Bloque titulo="Esto también cambia" testID="corregir-hecho-impacto">
              {e.movimientos.map((m) => (
                <FilaRevision key={m.movimiento_id} testID={`corregir-hecho-impacto-${m.pata}`} titulo={`Movimiento en ${m.cuenta.nombre ?? 'la cuenta'}`}
                  valor={`${m.pata === 'SALIDA' ? '−' : '+'}${formatearEur(importe.antes)} → ${m.pata === 'SALIDA' ? '−' : '+'}${formatearEur(importe.despues)}`} />
              ))}
              {!transferencia && delta ? (
                <FilaRevision testID="corregir-hecho-impacto-resultado" titulo="Resultado del mes" valor={`Gastos ${Number(delta) > 0 ? '+' : ''}${formatearEur(delta)}`} />
              ) : null}
              {transferencia ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>Una transferencia entre tus cuentas no es gasto ni ingreso: el Resultado no cambia.</Text> : null}
            </Bloque>
          ) : null}
          <Campo etiqueta="Motivo obligatorio">
            <View style={s.chips}>
              {MOTIVOS_CORREGIR.map((m, i) => (
                <Chip key={m} testID={`corregir-hecho-motivo-${i}`} etiqueta={m} seleccionado={!motivoOtro && motivo === m}
                  onPress={() => { if (!bloqueado) { setMotivoOtro(false); setMotivo(m); if (envio.fase === 'RECHAZADO') setEnvio({ fase: 'REVISANDO' }); } }} />
              ))}
              <Chip testID="corregir-hecho-motivo-otro" etiqueta="Otro…" seleccionado={motivoOtro} onPress={() => { if (!bloqueado) { setMotivoOtro(true); setMotivo(''); } }} />
            </View>
            {motivoOtro ? (
              <TextInput testID="corregir-hecho-motivo-texto" accessibilityLabel="Motivo" value={motivo} onChangeText={setMotivo} editable={!bloqueado} maxLength={200}
                style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]} />
            ) : null}
          </Campo>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SE_CORRIGE_EN_SITIO}</Text>
          {envio.fase === 'RECHAZADO' ? <Aviso testID="corregir-hecho-error" critico texto={`No se ha guardado. ${envio.mensaje}`} /> : null}
          {envio.fase === 'INDETERMINADO' ? <Aviso testID="corregir-hecho-indeterminado" texto={envio.mensaje} /> : null}
          <BotonPrimario testID="corregir-hecho-guardar" titulo={envio.fase === 'ENVIANDO' ? 'Guardando…' : envio.fase === 'INDETERMINADO' ? 'Reintentar' : 'Guardar cambios'}
            cargando={envio.fase === 'ENVIANDO'} deshabilitado={faltan.length > 0} onPress={() => void guardar()} />
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  // ---------------------------------------------------------------- A2 · formulario precargado
  const hoy = isoLocal(p.ahora());
  const fechas = [...new Set([e.fecha, hoy, isoLocal(ayer(p.ahora()))])];
  const editado = (campo: CambioEdicion['campo']) => cambios.find((x) => x.campo === campo);
  const Editado = ({ campo }: { campo: CambioEdicion['campo'] }) => {
    const x = editado(campo);
    return x ? <Text testID={`corregir-hecho-editado-${campo}`} style={[tipo.caption, { color: c.accent }]}>{`Editado · antes ${valorCambio(x, x.antes)}`}</Text> : null;
  };
  const selector = (testBase: string, lista: CuentaElegible[], actual: string | null, elegir: (id: string) => void, original: string | null) => {
    const ids = new Map(lista.map((x) => [x.cuenta_id, x.nombre]));
    if (original && !ids.has(original)) ids.set(original, nombreCuenta(original));
    return (
      <View style={s.chips}>
        {[...ids.entries()].map(([id, nombre]) => (
          <Chip key={id} testID={`${testBase}-${id}`} etiqueta={nombre} seleccionado={actual === id} onPress={() => elegir(id)} />
        ))}
      </View>
    );
  };
  const salidaOriginal = e.movimientos.find((m) => m.pata === 'SALIDA')?.cuenta.id ?? null;
  const entradaOriginal = e.movimientos.find((m) => m.pata === 'ENTRADA')?.cuenta.id ?? null;
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {cabecera(transferencia ? 'Corregir transferencia' : 'Corregir gasto', <BotonTexto testID="corregir-hecho-cancelar" titulo="Cancelar" onPress={() => cerrar(false)} />)}
      <ScrollView testID="corregir-hecho-form" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Text testID="corregir-hecho-solo-errores" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SOLO_ERRORES}</Text>
        <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{p.titulo}</Text>
        <Campo etiqueta="Importe">
          <TextInput testID="corregir-hecho-importe" accessibilityLabel="Importe en euros" value={form.importe} onChangeText={(t) => setForm({ ...form, importe: t })}
            keyboardType="decimal-pad" inputMode="decimal" style={[tipo.body, s.input, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]} />
          <Editado campo="importe" />
        </Campo>
        <Campo etiqueta="Fecha">
          <View style={s.chips}>
            {fechas.map((f) => (
              <Chip key={f} testID={`corregir-hecho-fecha-${f}`} etiqueta={f === hoy ? 'Hoy' : f === isoLocal(ayer(p.ahora())) ? 'Ayer' : diaMesAnioIso(f)}
                seleccionado={form.fecha === f} onPress={() => { setFechaTexto(''); setForm({ ...form, fecha: f }); }} />
            ))}
          </View>
          <TextInput testID="corregir-hecho-fecha-texto" accessibilityLabel="Otra fecha (dd/mm/aaaa)" placeholder="Otra fecha (dd/mm/aaaa)" placeholderTextColor={c.textSecondary}
            value={fechaTexto} onChangeText={(t) => { setFechaTexto(t); const iso = ddmmaaaaAIso(t); if (iso && iso <= hoy) setForm({ ...form, fecha: iso }); }}
            style={[tipo.body, s.input, { color: c.textPrimary, borderColor: c.borderStandard, backgroundColor: c.surfacePrimary }]} />
          <Editado campo="fecha" />
        </Campo>
        <Campo etiqueta={transferencia ? 'Sale de' : 'Pagado con'}>
          {selector('corregir-hecho-cuenta-salida', cuentas.salida, form.cuentaSalida, (id) => setForm({ ...form, cuentaSalida: id }), salidaOriginal)}
          <Editado campo={transferencia ? 'cuenta_origen' : 'cuenta'} />
        </Campo>
        {transferencia ? (
          <Campo etiqueta="Entra en">
            {selector('corregir-hecho-cuenta-entrada', cuentas.entrada, form.cuentaEntrada, (id) => setForm({ ...form, cuentaEntrada: id }), entradaOriginal)}
            <Editado campo="cuenta_destino" />
          </Campo>
        ) : null}
        {faltanForm.length > 0 ? <Text testID="corregir-hecho-faltan" style={[tipo.footnote, { color: c.textSecondary }]}>{`Para revisar falta: ${faltanForm.join(', ')}.`}</Text> : null}
        <BotonPrimario testID="corregir-hecho-revisar" titulo="Revisar cambios" deshabilitado={faltanForm.length > 0}
          onPress={() => { if (faltanForm.length === 0) setEnvio({ fase: 'REVISANDO' }); }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
