// ============================================================
// GAPTO MOBILE 2027
// Fichero: RegistroGastoScreen.tsx
// Ruta: mobile/src/screens/RegistroGastoScreen.tsx
// Descripción: FORM-VS01 — implementación funcional PROVISIONAL sobre Design System F09 (no es mockup aprobado). Tarea inmersiva CREATE: cabecera de tarea, sin barra inferior (F09 BLOQUE A). Pantalla corta: importe, concepto, ¿cuenta para presupuesto? (Sí/No sin preselección), «Solo mío» explícito, cuenta de pago, fecha visible. Cada valor muestra su origen: decisión, inferido visible o pendiente (mandato §8).
// Versión: 0.1.0
// ============================================================

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaPago } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato, Segmentado } from '../components/Basicos';
import { fechaCorta, isoLocal } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import { Borrador, borradorInicial, Errores } from '../domain/intencion';
import { useEnvioGasto } from '../state/useEnvioGasto';
import { useTema } from '../theme/tema';
import { espacio, importe, radio, TACTIL_MIN, tipo } from '../theme/tokens';

type Cuentas = { fase: 'CARGANDO' } | { fase: 'OK'; lista: CuentaPago[] } | { fase: 'ERROR' };

export function RegistroGastoScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (registrado: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoy = useMemo(() => p.ahora(), [p.ahora]);
  const [b, setB] = useState<Borrador>(() => borradorInicial(isoLocal(hoy)));
  const [errores, setErrores] = useState<Errores>({});
  const [cuentas, setCuentas] = useState<Cuentas>({ fase: 'CARGANDO' });
  const [confirmarSalida, setConfirmarSalida] = useState(false);
  const { estado, enviar, reintentar, volverAEditar } = useEnvioGasto(p.cliente, p.nuevoId);
  const conceptoRef = useRef<TextInput>(null);

  const cargarCuentas = async () => {
    setCuentas({ fase: 'CARGANDO' });
    const r = await p.cliente.cuentasPago(isoLocal(hoy));
    if (r.tipo !== 'OK') return setCuentas({ fase: 'ERROR' });
    setCuentas({ fase: 'OK', lista: r.datos.cuentas });
    // Única cuenta: se preselecciona como valor INFERIDO y visible (no oculto).
    if (r.datos.cuentas.length === 1) {
      setB((x) => (x.cuentaId ? x : { ...x, cuentaId: r.datos.cuentas[0].cuenta_id, cuentaOrigen: 'INFERIDO' }));
    }
  };
  useEffect(() => {
    void cargarCuentas();
  }, []);

  const bloqueado = estado.fase === 'ENVIANDO' || estado.fase === 'INDETERMINADO' || estado.fase === 'CONFIRMADO';
  // Defaults inferidos (fecha, cuenta única) no cuentan como modificación (F09 BLOQUE A).
  const modificado = b.importeTexto.trim() !== '' || b.concepto.trim() !== '' || b.presupuestable !== null || b.soloMio || b.cuentaOrigen === 'USUARIO';
  const cuentaSel = cuentas.fase === 'OK' ? cuentas.lista.find((x) => x.cuenta_id === b.cuentaId) : undefined;

  const cambiar = (parche: Partial<Borrador>) => {
    if (bloqueado) return;
    if (estado.fase === 'RECHAZADO') volverAEditar();
    setB((x) => ({ ...x, ...parche }));
    setErrores((e) => {
      const n = { ...e };
      for (const k of Object.keys(parche)) {
        if (k === 'importeTexto') delete n.importe;
        if (k === 'cuentaId') delete n.cuenta;
        if (k in n) delete (n as any)[k];
      }
      return n;
    });
  };

  const onRegistrar = async () => {
    const e = await enviar(b);
    setErrores(e);
  };

  const cancelar = () => {
    if (estado.fase === 'CONFIRMADO') return p.onCerrar(true);
    if (modificado || estado.fase === 'INDETERMINADO') return setConfirmarSalida(true);
    p.onCerrar(false);
  };

  if (estado.fase === 'CONFIRMADO') {
    const r = estado.resultado;
    return (
      <View testID="registro-exito" style={[s.pantalla, { backgroundColor: c.background, paddingTop: inset.top + espacio.xl, paddingBottom: inset.bottom + espacio.l }]}>
        <View style={[s.exito, { backgroundColor: c.surfacePrimary }]} accessibilityLiveRegion="polite">
          <Text style={{ fontSize: 40 }} accessibilityElementsHidden>✓</Text>
          <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>Gasto registrado</Text>
          <Text style={[importe.primary, { color: c.textPrimary }]}>{formatearEur(r.importe)}</Text>
          <Text style={[tipo.body, { color: c.textSecondary }]}>{estado.sellada.payload.concepto}</Text>
          <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>
            {r.estado_atribucion === 'COMPLETA' ? 'Atribuido: solo tuyo.' : 'Reparto sin indicar: no cuenta en tu gasto atribuible.'}
          </Text>
        </View>
        <BotonPrimario testID="volver-inicio" titulo="Volver a Inicio" onPress={() => p.onCerrar(true)} />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {/* Cabecera de TAREA (F09): Cancelar · título. Sin barra inferior. */}
      <View style={[s.cabTarea, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault, backgroundColor: c.background }]}>
        <BotonTexto testID="cancelar" titulo="Cancelar" onPress={cancelar} />
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>Nuevo gasto</Text>
        <View style={{ width: 72 }} />
      </View>

      <ScrollView testID="registro-form" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {confirmarSalida ? (
          <View testID="confirmar-salida" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>
              {estado.fase === 'INDETERMINADO'
                ? 'Este gasto puede haberse registrado. Si sales, revisa Inicio antes de volver a registrarlo.'
                : '¿Descartar este gasto? Los datos introducidos se perderán.'}
            </Text>
            <View style={s.filaBotones}>
              <BotonTexto testID="seguir" titulo="Seguir aquí" onPress={() => setConfirmarSalida(false)} />
              <BotonTexto testID="descartar" titulo="Salir" critico onPress={() => p.onCerrar(false)} />
            </View>
          </View>
        ) : null}

        {/* Importe — DS-05 «Campo con icono €» */}
        <Campo etiqueta="Importe" error={errores.importe}>
          <View style={[s.importeCaja, { backgroundColor: c.surfacePrimary, borderColor: errores.importe ? c.critical : c.borderStandard }]}>
            <Text style={[importe.primary, { color: c.textSecondary }]}>€</Text>
            <TextInput
              testID="campo-importe"
              accessibilityLabel="Importe en euros"
              value={b.importeTexto}
              onChangeText={(t) => cambiar({ importeTexto: t })}
              editable={!bloqueado}
              keyboardType="decimal-pad"
              inputMode="decimal"
              placeholder="0,00"
              placeholderTextColor={c.textSecondary}
              returnKeyType="next"
              onSubmitEditing={() => conceptoRef.current?.focus()}
              autoFocus
              style={[importe.hero, s.inputImporte, { color: c.textPrimary }]}
            />
          </View>
        </Campo>

        <Campo etiqueta="Concepto" error={errores.concepto}>
          <TextInput
            ref={conceptoRef}
            testID="campo-concepto"
            accessibilityLabel="Concepto"
            value={b.concepto}
            onChangeText={(t) => cambiar({ concepto: t })}
            editable={!bloqueado}
            placeholder="Ej. Café"
            placeholderTextColor={c.textSecondary}
            maxLength={200}
            style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: errores.concepto ? c.critical : c.borderStandard }]}
          />
        </Campo>

        <Campo etiqueta="¿Cuenta para el presupuesto?" error={errores.presupuestable}>
          <Segmentado<boolean>
            testIDBase="presupuestable"
            etiquetaGrupo="¿Cuenta para el presupuesto?"
            opciones={[{ valor: true, etiqueta: 'Sí' }, { valor: false, etiqueta: 'No' }]}
            valor={b.presupuestable}
            onCambiar={(v) => cambiar({ presupuestable: v })}
          />
        </Campo>

        <Campo etiqueta="¿De quién es este gasto?">
          <Chip
            testID="solo-mio"
            etiqueta="Solo mío"
            seleccionado={b.soloMio}
            onPress={() => cambiar({ soloMio: !b.soloMio })}
          />
          <Text testID="origen-atribucion" style={[tipo.footnote, { color: c.textSecondary }]}>
            {b.soloMio ? 'Decisión tuya: el gasto es 100 % tuyo.' : 'Sin indicar: se guardará sin reparto y no contará en tu gasto atribuible.'}
          </Text>
        </Campo>

        <Campo etiqueta="Pagado con" error={errores.cuenta}>
          {cuentas.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
          {cuentas.fase === 'ERROR' ? (
            <Pressable testID="cuentas-error" accessibilityRole="button" onPress={cargarCuentas} style={{ minHeight: TACTIL_MIN }}>
              <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
            </Pressable>
          ) : null}
          {cuentas.fase === 'OK' && cuentas.lista.length === 0 ? (
            <Text style={[tipo.subheadline, { color: c.textSecondary }]}>No tienes cuentas disponibles. Configura primero una cuenta.</Text>
          ) : null}
          {cuentas.fase === 'OK' ? (
            <View style={s.chips}>
              {cuentas.lista.map((x) => (
                <Chip
                  key={x.cuenta_id}
                  testID={`cuenta-${x.cuenta_id}`}
                  etiqueta={x.nombre}
                  seleccionado={b.cuentaId === x.cuenta_id}
                  onPress={() => cambiar({ cuentaId: x.cuenta_id, cuentaOrigen: 'USUARIO' })}
                />
              ))}
            </View>
          ) : null}
          {cuentaSel ? (
            <Text testID="origen-cuenta" style={[tipo.footnote, { color: c.textSecondary }]}>
              {b.cuentaOrigen === 'INFERIDO' ? 'Propuesta: es tu única cuenta disponible. ' : ''}
              {cuentaSel.financiacion_derivable ? 'Pagado por ti (cuenta 100 % tuya).' : 'Quién financia el pago queda sin determinar.'}
            </Text>
          ) : null}
        </Campo>

        <Campo etiqueta="Fecha">
          <Text testID="fecha" style={[tipo.body, { color: c.textPrimary }]}>Hoy · {fechaCorta(hoy)}</Text>
        </Campo>

        {estado.fase === 'RECHAZADO' ? (
          <View testID="error-dominio" accessibilityLiveRegion="assertive" style={[s.aviso, { backgroundColor: c.surfacePrimary, borderColor: c.critical, borderWidth: 1 }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>No se ha registrado. {estado.mensaje}</Text>
          </View>
        ) : null}
        {estado.fase === 'INDETERMINADO' ? (
          <View testID="estado-indeterminado" accessibilityLiveRegion="assertive" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{estado.mensaje}</Text>
          </View>
        ) : null}

        {estado.fase === 'INDETERMINADO' ? (
          <BotonPrimario testID="reintentar" titulo="Reintentar" onPress={reintentar} />
        ) : (
          <BotonPrimario
            testID="registrar"
            titulo={estado.fase === 'ENVIANDO' ? 'Guardando…' : 'Registrar gasto'}
            cargando={estado.fase === 'ENVIANDO'}
            onPress={onRegistrar}
          />
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Campo({ etiqueta, error, children }: { etiqueta: string; error?: string; children: React.ReactNode }) {
  const { c } = useTema();
  return (
    <View style={{ gap: espacio.s }}>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>{etiqueta}</Text>
      {children}
      {error ? (
        <Text accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  pantalla: { flex: 1, paddingHorizontal: espacio.l, justifyContent: 'space-between' },
  exito: { borderRadius: radio.l, padding: espacio.xl, alignItems: 'center', gap: espacio.s },
  cabTarea: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth },
  form: { padding: espacio.l, gap: espacio.xl },
  importeCaja: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: radio.m, paddingHorizontal: espacio.l, gap: espacio.s, minHeight: 64 },
  // minWidth 0: sin él, el TextInput impone su ancho intrínseco y desborda en pantallas estrechas (detectado en E2E web).
  inputImporte: { flex: 1, minWidth: 0, paddingVertical: espacio.s },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4, minWidth: 0 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: espacio.s },
  aviso: { borderRadius: radio.m, padding: espacio.m, gap: espacio.s },
  filaBotones: { flexDirection: 'row', justifyContent: 'flex-end', gap: espacio.l },
});
