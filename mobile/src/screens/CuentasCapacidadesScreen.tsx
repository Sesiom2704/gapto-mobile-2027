// ============================================================
// GAPTO MOBILE 2027
// Fichero: CuentasCapacidadesScreen.tsx
// Ruta: mobile/src/screens/CuentasCapacidadesScreen.tsx
// Descripción: Ajustes › Preferencias financieras › Cuentas: lo que puede hacer cada cuenta en el registro (F05-06 M4 §3; F09 §12.105 CAP, lámina CAP v0.1; entrada provisional, destino final PAT-07-D › Más, §12.72). A1 lista con «Sin configurar» arriba y «Tus cuentas», con el resumen de cada una. A2 detalle: cuatro interruptores con su efecto, «Otras» (Compras con tarjeta, Domiciliar recibos) en solo lectura e «Historial de cambios ›». B1: cuenta sin configurar, todo apagado, «Gapto no lo deduce del tipo de cuenta», sin ninguna sugerencia. A3/A4: un cambio = una hoja de confirmación con «Lo ya registrado no cambia»; en A4 se listan antes de confirmar las plantillas y preferencias que quedarán «No disponible» (las da el servidor; no se reasignan). Sin cambios en bloque. Conflicto de versión (VERSION_DESFASADA): aviso sin pisar y recarga del estado. Cuenta cerrada o desactivada: interruptores en solo lectura (PD-2). B4 historial desde la auditoría, sin presentarlo como versionado temporal completo. El interruptor no cambia hasta que el servidor confirma. Sin alta, cierre ni edición de datos generales de cuentas (P-CAP-05).
// Versión: 0.1.0 (F05-06 M4 F2)
// ============================================================

import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { CapacidadNodo, ClienteApi, CuentaCapacidades, EntradaHistorialCapacidad, ImpactoCapacidad, Respuesta } from '../api/cliente';
import { BotonPrimario, CabeceraNavegacion, EstadoDato } from '../components/Basicos';
import { AvisoCaja, Caja, estilosFormulario as ef, FilaLista, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { BotonCritico, Hoja } from '../components/HojasCategoria';
import { BotonSecundario } from '../components/SelectorCategorias';
import {
  agruparCuentas,
  avisoSinConfigurar,
  CapacidadRegistro,
  esCapacidadRegistro,
  lineaHistorial,
  lineasImpacto,
  resumenCuenta,
  TEXTO_DEJA_DE_FUNCIONAR,
  TEXTO_HISTORIAL_VACIO,
  TEXTO_INDETERMINADO_CUENTA,
  TEXTO_NO_DEDUCE,
  TEXTO_NO_EDITABLE_ESTADO,
  TEXTO_PIE_HISTORIAL,
  TEXTO_QUEDARAN,
  TEXTO_SIN_CONFIGURAR,
  TEXTO_SIN_CUENTAS,
  TEXTO_VERSION_CUENTA,
  TEXTO_YA_REGISTRADO,
  textosHoja,
} from '../domain/capacidades';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

type Carga<T> = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; datos: T };
type Vista = { v: 'LISTA' } | { v: 'DETALLE'; id: string } | { v: 'HISTORIAL'; id: string };
type HojaCambio = { capacidad: CapacidadRegistro; permitir: boolean; impacto: Carga<ImpactoCapacidad> | null };

export function CuentasCapacidadesScreen(p: {
  cliente: ClienteApi;
  onAtras: () => void;
  /** Etiqueta de «‹ Atrás» de la lista (Ajustes o el formulario de registro que la abrió, B2). */
  etiquetaAtras: string;
  onInmersiva?: (x: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [lista, setLista] = useState<Carga<CuentaCapacidades[]>>({ fase: 'CARGANDO' });
  const [vista, setVista] = useState<Vista>({ v: 'LISTA' });
  const [detalle, setDetalle] = useState<Carga<CuentaCapacidades>>({ fase: 'CARGANDO' });
  const [historial, setHistorial] = useState<Carga<EntradaHistorialCapacidad[]>>({ fase: 'CARGANDO' });
  const [hoja, setHoja] = useState<HojaCambio | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargarLista = useCallback(async (silencioso = false) => {
    if (!silencioso) setLista({ fase: 'CARGANDO' });
    const r = await p.cliente.listarCapacidades();
    if (r.tipo === 'OK') setLista({ fase: 'OK', datos: r.datos.cuentas });
    else if (!silencioso) setLista({ fase: 'ERROR' });
  }, [p.cliente]);
  useEffect(() => {
    void cargarLista();
  }, [cargarLista]);

  const cargarDetalle = async (id: string, silencioso = false): Promise<CuentaCapacidades | null> => {
    if (!silencioso) setDetalle({ fase: 'CARGANDO' });
    const r = await p.cliente.detalleCapacidades(id);
    if (r.tipo === 'OK') {
      setDetalle({ fase: 'OK', datos: r.datos });
      return r.datos;
    }
    if (!silencioso) setDetalle({ fase: 'ERROR' });
    return null;
  };

  useEffect(() => {
    p.onInmersiva?.(hoja !== null);
  }, [hoja]);
  useEffect(() => () => p.onInmersiva?.(false), []);

  const abrirDetalle = (id: string) => {
    setAviso(null);
    setHoja(null);
    setVista({ v: 'DETALLE', id });
    void cargarDetalle(id);
  };
  const abrirHistorial = async (id: string) => {
    setVista({ v: 'HISTORIAL', id });
    setHistorial({ fase: 'CARGANDO' });
    const r = await p.cliente.historialCapacidades(id);
    setHistorial(r.tipo === 'OK' ? { fase: 'OK', datos: r.datos.entradas } : { fase: 'ERROR' });
  };

  // ---------------------------------------------------------------- A3 / A4
  const abrirHoja = async (cuenta: CuentaCapacidades, k: CapacidadNodo) => {
    if (ocupado || !esCapacidadRegistro(k.codigo)) return;
    const capacidad = k.codigo;
    const permitir = !k.permitida;
    setAviso(null);
    setHoja({ capacidad, permitir, impacto: permitir ? null : { fase: 'CARGANDO' } });
    if (permitir) return;
    const r = await p.cliente.impactoCapacidad(cuenta.cuenta_id, capacidad);
    setHoja((h) => (h && h.capacidad === capacidad && !h.permitir ? { ...h, impacto: r.tipo === 'OK' ? { fase: 'OK', datos: r.datos } : { fase: 'ERROR' } } : h));
  };

  const avisoRechazo = (r: Respuesta<unknown>): NonNullable<AvisoCaja> => {
    if (r.tipo === 'INDETERMINADO') return { tipo: 'AVISO', texto: TEXTO_INDETERMINADO_CUENTA };
    if (r.tipo === 'RECHAZADO' && r.codigo === 'VERSION_DESFASADA') return { tipo: 'AVISO', texto: TEXTO_VERSION_CUENTA };
    return { tipo: 'AVISO', texto: (r.tipo === 'RECHAZADO' && r.mensaje) || TEXTO_INDETERMINADO_CUENTA };
  };

  const confirmar = async (cuenta: CuentaCapacidades, h: HojaCambio) => {
    if (ocupado) return;
    setOcupado(true);
    const r = await p.cliente.cambiarCapacidad(cuenta.cuenta_id, h.capacidad, h.permitir, cuenta.row_version);
    if (r.tipo === 'OK') {
      setDetalle({ fase: 'OK', datos: r.datos.cuenta });
      setAviso(null);
    } else {
      // Sin pisar: se recarga el estado actual y se avisa (sin reintento automático).
      await cargarDetalle(cuenta.cuenta_id, true);
      setAviso(avisoRechazo(r));
    }
    setHoja(null);
    setOcupado(false);
    void cargarLista(true);
  };

  // ---------------------------------------------------------------- B4 historial
  if (vista.v === 'HISTORIAL') {
    const nombre = detalle.fase === 'OK' ? detalle.datos.nombre : 'Cuenta';
    return (
      <View testID="cap-historial" style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraNavegacion titulo="Historial de cambios" atras={{ etiqueta: nombre, onPress: () => setVista({ v: 'DETALLE', id: vista.id }) }} testIDAtras="cap-historial-atras" />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          {historial.fase === 'CARGANDO' ? <EstadoDato testID="cap-historial-cargando" estado="CARGANDO" /> : null}
          {historial.fase === 'ERROR' ? (
            <Pressable testID="cap-historial-error" accessibilityRole="button" onPress={() => void abrirHistorial(vista.id)} style={{ minHeight: TACTIL_MIN }}>
              <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
            </Pressable>
          ) : null}
          {historial.fase === 'OK' && historial.datos.length === 0 ? (
            <Text testID="cap-historial-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_HISTORIAL_VACIO}</Text>
          ) : null}
          {historial.fase === 'OK' && historial.datos.length > 0 ? (
            <Tarjeta testID="cap-historial-lista">
              {historial.datos.map((e, i) => {
                const l = lineaHistorial(e);
                return (
                  <View key={`${e.cuando}-${i}`} testID={`cap-historial-${i}`} style={[s.fila, i < historial.datos.length - 1 && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
                    <Text style={[tipo.body, { color: c.textPrimary }]}>{l.titulo}</Text>
                    <Text style={[tipo.caption, { color: c.textSecondary }]}>{l.detalle}</Text>
                  </View>
                );
              })}
            </Tarjeta>
          ) : null}
          <Text testID="cap-historial-pie" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_PIE_HISTORIAL}</Text>
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- A2 / B1 detalle
  if (vista.v === 'DETALLE') {
    const x = detalle.fase === 'OK' ? detalle.datos : null;
    const editable = x?.estado === 'ACTIVA';
    const filaCapacidad = (k: CapacidadNodo, i: number, n: number, soloLectura: boolean) => (
      <View key={k.codigo} testID={`cap-${k.codigo}`} style={[s.filaCap, i < n - 1 && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={[tipo.body, { color: soloLectura ? c.textSecondary : c.textPrimary }]}>{k.etiqueta}</Text>
          <Text testID={`cap-${k.codigo}-efecto`} style={[tipo.caption, { color: c.textSecondary }]}>{k.efecto}</Text>
        </View>
        {soloLectura ? (
          <Text testID={`cap-${k.codigo}-estado`} style={[tipo.subheadline, { color: c.textSecondary }]}>{k.permitida ? 'Sí' : 'No'}</Text>
        ) : (
          <Switch
            testID={`cap-${k.codigo}-interruptor`}
            accessibilityLabel={k.etiqueta}
            accessibilityHint={k.efecto}
            value={k.permitida}
            disabled={!editable || ocupado}
            onValueChange={() => {
              if (x) void abrirHoja(x, k);
            }}
            trackColor={{ false: c.borderStandard, true: c.accent }}
            thumbColor={c.surfacePrimary}
            ios_backgroundColor={c.borderStandard}
          />
        )}
      </View>
    );
    const textos = hoja && x ? textosHoja(hoja.capacidad, x.nombre, hoja.permitir) : null;
    const impacto = hoja && x && hoja.impacto?.fase === 'OK' ? lineasImpacto(hoja.impacto.datos, hoja.capacidad, x.nombre) : [];
    const impactoListo = hoja ? hoja.permitir || hoja.impacto?.fase === 'OK' : false;
    return (
      <View testID="cap-detalle" style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraNavegacion titulo={x?.nombre ?? 'Cuenta'} atras={{ etiqueta: 'Cuentas', onPress: () => setVista({ v: 'LISTA' }) }} testIDAtras="cap-detalle-atras" />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          {detalle.fase === 'CARGANDO' ? <EstadoDato testID="cap-detalle-cargando" estado="CARGANDO" /> : null}
          {detalle.fase === 'ERROR' ? (
            <Pressable testID="cap-detalle-error" accessibilityRole="button" onPress={() => void cargarDetalle(vista.id)} style={{ minHeight: TACTIL_MIN }}>
              <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
            </Pressable>
          ) : null}
          {aviso ? <Caja testID="cap-aviso" aviso={aviso} /> : null}
          {x && x.sin_configurar ? (
            <View testID="cap-sin-configurar" style={[s.banda, { backgroundColor: c.surfaceSecondary }]}>
              <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{avisoSinConfigurar(x)}</Text>
            </View>
          ) : null}
          {x && !editable ? <Caja testID="cap-no-editable" aviso={{ tipo: 'AVISO', texto: TEXTO_NO_EDITABLE_ESTADO }} /> : null}
          {x ? (
            <>
              <View style={{ gap: espacio.s }}>
                <RotuloGrupo texto="Qué puede hacer" />
                <Tarjeta testID="cap-registro">{x.capacidades.map((k, i) => filaCapacidad(k, i, x.capacidades.length, false))}</Tarjeta>
                {x.sin_configurar ? <Text testID="cap-no-deduce" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NO_DEDUCE}</Text> : null}
              </View>
              <View style={{ gap: espacio.s }}>
                <RotuloGrupo texto="Otras" />
                <Tarjeta testID="cap-otras">{x.otras.map((k, i) => filaCapacidad(k, i, x.otras.length, true))}</Tarjeta>
              </View>
              <Tarjeta>
                <FilaLista testID="cap-abrir-historial" titulo="Historial de cambios" ultima onPress={() => void abrirHistorial(x.cuenta_id)} />
              </Tarjeta>
            </>
          ) : null}
        </ScrollView>

        {hoja && x && textos ? (
          <Hoja titulo={textos.titulo} testID={hoja.permitir ? 'cap-hoja-activar' : 'cap-hoja-desactivar'}>
            <Text testID="cap-hoja-consecuencia" style={[tipo.body, { color: c.textPrimary }]}>{`${textos.consecuencia} ${TEXTO_YA_REGISTRADO}`}</Text>
            {!hoja.permitir && hoja.impacto?.fase === 'CARGANDO' ? <EstadoDato testID="cap-impacto-cargando" estado="CARGANDO" /> : null}
            {!hoja.permitir && hoja.impacto?.fase === 'ERROR' ? (
              <Pressable testID="cap-impacto-error" accessibilityRole="button" onPress={() => { const k = x.capacidades.find((y) => y.codigo === hoja.capacidad); if (k) void abrirHoja(x, k); }} style={{ minHeight: TACTIL_MIN }}>
                <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
              </Pressable>
            ) : null}
            {impacto.length > 0 ? (
              <View testID="cap-impacto" style={[s.banda, { backgroundColor: c.partialSurface }]}>
                <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{TEXTO_DEJA_DE_FUNCIONAR}</Text>
                {impacto.map((l, i) => (
                  <Text key={i} testID={`cap-impacto-${i}`} style={[tipo.subheadline, { color: c.textPrimary }]}>{`· ${l}`}</Text>
                ))}
                <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_QUEDARAN}</Text>
              </View>
            ) : null}
            {hoja.permitir ? (
              <BotonPrimario testID="cap-hoja-confirmar" titulo={textos.boton} cargando={ocupado} deshabilitado={ocupado} onPress={() => void confirmar(x, hoja)} />
            ) : (
              <BotonCritico testID="cap-hoja-confirmar" titulo={textos.boton} deshabilitado={ocupado || !impactoListo} onPress={() => void confirmar(x, hoja)} />
            )}
            <BotonSecundario testID="cap-hoja-cancelar" titulo="Cancelar" onPress={() => setHoja(null)} />
          </Hoja>
        ) : null}
      </View>
    );
  }

  // ---------------------------------------------------------------- A1 lista
  const grupos = lista.fase === 'OK' ? agruparCuentas(lista.datos) : null;
  const filas = (xs: CuentaCapacidades[]) =>
    xs.map((x, i) => (
      <FilaLista
        key={x.cuenta_id}
        testID={`cap-fila-${x.cuenta_id}`}
        titulo={x.nombre}
        detalle={resumenCuenta(x)}
        apagada={x.estado !== 'ACTIVA'}
        ultima={i === xs.length - 1}
        derecha={x.sin_configurar ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{TEXTO_SIN_CONFIGURAR}</Text> : undefined}
        onPress={() => abrirDetalle(x.cuenta_id)}
      />
    ));
  return (
    <View testID="pantalla-cuentas" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo="Cuentas" atras={{ etiqueta: p.etiquetaAtras, onPress: p.onAtras }} testIDAtras="cap-atras" />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {lista.fase === 'CARGANDO' ? <EstadoDato testID="cap-cargando" estado="CARGANDO" /> : null}
        {lista.fase === 'ERROR' ? (
          <Pressable testID="cap-error" accessibilityRole="button" onPress={() => void cargarLista()} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {lista.fase === 'OK' && lista.datos.length === 0 ? <Text testID="cap-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_CUENTAS}</Text> : null}
        {grupos && grupos.sinConfigurar.length > 0 ? (
          <View testID="cap-grupo-sin-configurar" style={{ gap: espacio.s }}>
            <RotuloGrupo texto={TEXTO_SIN_CONFIGURAR} />
            <Tarjeta>{filas(grupos.sinConfigurar)}</Tarjeta>
          </View>
        ) : null}
        {grupos && grupos.configuradas.length > 0 ? (
          <View testID="cap-grupo-cuentas" style={{ gap: espacio.s }}>
            <RotuloGrupo texto="Tus cuentas" />
            <Tarjeta>{filas(grupos.configuradas)}</Tarjeta>
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  fila: { gap: 2, minHeight: TACTIL_MIN + 8, paddingHorizontal: espacio.m, paddingVertical: espacio.s, justifyContent: 'center' },
  filaCap: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, minHeight: TACTIL_MIN + 12, paddingHorizontal: espacio.m, paddingVertical: espacio.s },
  banda: { borderRadius: radio.m, padding: espacio.m, gap: espacio.xs },
});
