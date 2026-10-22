// ============================================================
// GAPTO MOBILE 2027
// Fichero: PrevisionDetalleScreen.tsx
// Ruta: mobile/src/screens/PrevisionDetalleScreen.tsx
// Descripción: Detalle de una previsión y sus tres salidas (F05-06 M5 §B1; lámina PREV v0.2 A2, B2–B7; D-PREV-02/06/07/09/11/13/14). Lee GET /v1/previsiones/{id} en CUALQUIER estado: las terminales y las que necesitan revisión se ven solo en lectura y sin acciones. Muestra importe esperado («Desconocido», nunca 0), cuándo, cuenta, categoría, origen, cobertura («Pagado 40,00 € · 1 pago», «Queda 80,00 €») o desviación («10,00 € más de lo previsto») y «Es una previsión: no ha movido dinero.». Acciones: «Registrar pago/cobro» (PrevisionRegistroScreen), «Ya lo registré» (candidatos SIN preselección, «Buscar en más fechas», «Se vinculará X €» con toda la porción libre, «¿Queda cubierta?» sin respuesta y «Enlazar»; un cambio concurrente relee y lo vuelve a mostrar) y «No hubo este mes» (motivo opcional). Lo no disponible va atenuado con su motivo. Tras un 409 o un fallo de conexión se enseña el estado actual y nunca «hecho»; un reintento usa la MISMA identidad. En parciales: «Para cubrirla, registra o enlaza el resto.» (sin darla por cubierta, DEU-M5-CERRAR-PARCIAL).
// Versión: 0.1.0 (F05-06 M5 §B1)
// Versión: 0.2.0 (F05-06 M5-B; F04-D065, F05-D047; contrato M5-B §5): «Dar por cubierta» en una PARCIAL (hoja con Esperado / Registrado / Queda sin cubrir ±X €, motivo con sugerencias y confirmación explícita) y «Más» › «Reabrir» en REALIZADA, REALIZADA_SIN_REALIDAD_ACTIVA y OMITIDA (motivo obligatorio; envía la versión del sucesor cuando la lectura lo trae). Sin swipe. PREVISION_SIN_REALIDAD_ACTIVA y TRAMO_RODANTE_REQUIERE_REVISION se explican en la hoja con el texto del servidor (el primero informa de «No hubo este mes» sin ejecutarlo) y se relee el detalle; 409 de estado o versión y el reintento incierto acaban en el estado actual, como «No hubo». Un reintento tras un fallo de conexión usa la MISMA identidad.
// ============================================================

import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { CandidatoPrevision, CandidatosPrevision, ClienteApi, DetallePrevision } from '../api/cliente';
import { BotonPrimario, BotonTexto, CabeceraNavegacion, EstadoDato } from '../components/Basicos';
import { estilosFormulario } from '../components/Formulario';
import { Ionicons } from '@expo/vector-icons';

import {
  AccionPrevision,
  AvisoEstadoActual,
  HojaDarPorCubierta,
  HojaMas,
  HojaOmitir,
  HojaReabrir,
  QuedaCubierta,
  usarIntencion,
} from '../components/Prevision';
import { diaMesIso } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import {
  coberturaTexto,
  desviacionTexto,
  estadoLegible,
  importeFila,
  intervaloTexto,
  ofreceDarPorCubierta,
  ofreceMas,
  TEXTO_CUBRIR_RESTO,
  TEXTO_DESCONOCIDO,
  TEXTO_NO_MUEVE,
  TEXTO_SOLO_ENLAZA,
  textoSeVinculara,
} from '../domain/prevision';
import { useTema } from '../theme/tema';
import { espacio, importe as estiloImporte, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { PrevisionRegistroScreen } from './PrevisionRegistroScreen';

type Carga = { fase: 'CARGANDO' } | { fase: 'OK'; d: DetallePrevision } | { fase: 'ERROR' };
type Aviso = { estado: string; derivado: string | null; incierto: boolean; mensaje: string } | null;
type Transicion = { tipo: 'CUBIERTA' | 'REABRIR'; motivo: string; enviando: boolean; error: string | null } | null;
/** Rechazos que se explican en la propia hoja y obligan a releer (sin reintento automático). */
const RECHAZOS_EN_HOJA = new Set(['PREVISION_SIN_REALIDAD_ACTIVA', 'TRAMO_RODANTE_REQUIERE_REVISION', 'ENTRADA_INVALIDA', 'MOTIVO_AUSENTE']);

const ORIGEN = { MANUAL: 'Previsión manual', REGLA: 'Regla recurrente', V3: 'De la versión anterior (V3)' } as const;

export function PrevisionDetalleScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  previsionId: string;
  /** Abrir directamente el formulario (desde el swipe «Abrir el formulario completo»). */
  abrirRegistro?: { importe: string | null } | null;
  etiquetaAtras?: string;
  onCerrar: (cambios: boolean) => void;
}) {
  const { c } = useTema();
  const [carga, setCarga] = useState<Carga>({ fase: 'CARGANDO' });
  const [vista, setVista] = useState<'DETALLE' | 'REGISTRO' | 'YA'>(p.abrirRegistro ? 'REGISTRO' : 'DETALLE');
  const [omitir, setOmitir] = useState<{ motivo: string; enviando: boolean; error: string | null } | null>(null);
  const [aviso, setAviso] = useState<Aviso>(null);
  const [cambios, setCambios] = useState(false);
  const intencionOmitir = usarIntencion(p.nuevoId);
  const [transicion, setTransicion] = useState<Transicion>(null);
  const [mas, setMas] = useState(false);
  const intencionTransicion = usarIntencion(p.nuevoId);
  const [fueIncierto, setFueIncierto] = useState(false);

  const cargar = useCallback(async () => {
    setCarga({ fase: 'CARGANDO' });
    const r = await p.cliente.detallePrevision(p.previsionId);
    setCarga(r.tipo === 'OK' ? { fase: 'OK', d: r.datos } : { fase: 'ERROR' });
  }, [p.cliente, p.previsionId]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const cerrar = () => p.onCerrar(cambios);

  if (carga.fase !== 'OK') {
    return (
      <View testID="prevision-detalle" style={[s.raiz, { backgroundColor: c.background }]}>
        <CabeceraNavegacion titulo="Previsión" atras={{ etiqueta: p.etiquetaAtras ?? 'Inicio', onPress: cerrar }} testIDAtras="prevision-detalle-atras" />
        <View style={estilosFormulario.cuerpo}>
          {carga.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : (
            <Pressable testID="prevision-detalle-error" accessibilityRole="button" onPress={cargar} style={{ minHeight: TACTIL_MIN }}>
              <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
            </Pressable>
          )}
        </View>
      </View>
    );
  }
  const d = carga.d;

  if (vista === 'REGISTRO') {
    return (
      <PrevisionRegistroScreen
        cliente={p.cliente}
        nuevoId={p.nuevoId}
        ahora={p.ahora}
        detalle={d}
        importeInicial={p.abrirRegistro?.importe ?? null}
        onCerrar={(registrado, releer) => {
          if (registrado) return p.onCerrar(true);
          setVista('DETALLE');
          if (releer) void cargar();
        }}
      />
    );
  }
  if (vista === 'YA') {
    return (
      <YaLoRegistre
        cliente={p.cliente}
        nuevoId={p.nuevoId}
        detalle={d}
        onVolver={(enlazado) => {
          if (enlazado) return p.onCerrar(true);
          setVista('DETALLE');
          void cargar();
        }}
      />
    );
  }

  const confirmarOmitir = async () => {
    if (!omitir) return;
    setOmitir({ ...omitir, enviando: true, error: null });
    const r = await p.cliente.omitirPrevision(d.id, { intencion_id: intencionOmitir.actual(), row_version: d.row_version, motivo: omitir.motivo.trim() || null });
    if (r.tipo === 'OK') {
      intencionOmitir.liberar();
      setOmitir(null);
      setCambios(true);
      return p.onCerrar(true);
    }
    if (r.tipo === 'INDETERMINADO') {
      setFueIncierto(true);
      return setOmitir({ ...omitir, enviando: false, error: `${r.mensaje} Puedes reintentar.` });
    }
    intencionOmitir.liberar();
    const actual = (r.detalle?.estado_actual ?? null) as { estado: string; estado_derivado: string | null } | null;
    setOmitir(null);
    if (actual && (r.codigo === 'ESTADO_PREVISION_INCOMPATIBLE' || r.codigo === 'VERSION_DESFASADA')) {
      setAviso({ estado: actual.estado, derivado: actual.estado_derivado, incierto: fueIncierto, mensaje: r.mensaje });
    } else {
      setAviso({ estado: d.estado, derivado: d.estado_derivado, incierto: false, mensaje: r.mensaje });
    }
  };

  const confirmarTransicion = async () => {
    if (!transicion || !transicion.motivo.trim()) return;
    const t = transicion;
    setTransicion({ ...t, enviando: true, error: null });
    const base = { intencion_id: intencionTransicion.actual(), row_version: d.row_version, motivo: t.motivo.trim() };
    const r = t.tipo === 'CUBIERTA'
      ? await p.cliente.darPorCubiertaPrevision(d.id, base)
      : await p.cliente.reabrirPrevision(d.id, { ...base, sucesor_row_version: d.sucesor?.row_version ?? null });
    if (r.tipo === 'OK') {
      intencionTransicion.liberar();
      setTransicion(null);
      setCambios(true);
      return p.onCerrar(true);
    }
    if (r.tipo === 'INDETERMINADO') {
      setFueIncierto(true);
      return setTransicion({ ...t, enviando: false, error: `${r.mensaje} Puedes reintentar.` });
    }
    intencionTransicion.liberar();
    if (RECHAZOS_EN_HOJA.has(r.codigo)) {
      // Se explica en la hoja y se relee: el botón vuelve a enviar con los datos nuevos, nunca solo.
      setTransicion({ ...t, enviando: false, error: r.mensaje });
      setCambios(true);
      void p.cliente.detallePrevision(d.id).then((x) => { if (x.tipo === 'OK') setCarga({ fase: 'OK', d: x.datos }); });
      return;
    }
    const actual = (r.detalle?.estado_actual ?? null) as { estado: string; estado_derivado: string | null } | null;
    setTransicion(null);
    if (actual && (r.codigo === 'ESTADO_PREVISION_INCOMPATIBLE' || r.codigo === 'VERSION_DESFASADA')) {
      setAviso({ estado: actual.estado, derivado: actual.estado_derivado, incierto: fueIncierto, mensaje: r.mensaje });
    } else {
      setAviso({ estado: d.estado, derivado: d.estado_derivado, incierto: false, mensaje: r.mensaje });
    }
  };

  const cobertura = coberturaTexto(d);
  const desviacion = desviacionTexto(d);
  const terminal = d.estado !== 'ABIERTA' || d.estado_derivado !== null;
  const cuenta = d.tipo === 'INGRESO' ? d.cuenta_entrada : d.cuenta_salida;
  const fecha = d.fecha_hasta ?? d.fecha_desde;
  return (
    <View testID="prevision-detalle" style={[s.raiz, { backgroundColor: c.background }]}>
      <CabeceraNavegacion titulo="Previsión" atras={{ etiqueta: p.etiquetaAtras ?? 'Inicio', onPress: cerrar }} testIDAtras="prevision-detalle-atras"
        derecha={ofreceMas(d) ? (
          <Pressable testID="prevision-mas" accessibilityRole="button" accessibilityLabel="Más" hitSlop={8} onPress={() => setMas(true)} style={s.mas}>
            <Ionicons name="ellipsis-horizontal" size={22} color={c.accent} />
          </Pressable>
        ) : null} />
      <ScrollView contentContainerStyle={estilosFormulario.cuerpo}>
        <View style={{ gap: espacio.xs }}>
          <View style={s.titulo}>
            <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary, flexShrink: 1 }]}>{d.concepto}</Text>
            <View style={[s.etiqueta, { backgroundColor: c.unknownSurface }]}>
              <Text testID="prevision-estado" style={[tipo.caption, { color: c.textPrimary }]}>{terminal ? estadoLegible(d.estado, d.estado_derivado) : 'Previsto'}</Text>
            </View>
          </View>
          <Text style={[tipo.subheadline, { color: c.textSecondary }]}>
            {[d.tercero?.nombre, fecha ? (d.vencida ? `venció el ${diaMesIso(fecha)}` : `vence el ${diaMesIso(fecha)}`) : null].filter(Boolean).join(' · ')}
          </Text>
        </View>
        <View style={[s.bloque, { borderColor: c.borderDefault }]}>
          <Fila etiqueta="Importe esperado" valor={d.importe_esperado === null ? TEXTO_DESCONOCIDO : importeFila(d)} testID="detalle-esperado" />
          {cobertura ? <Fila etiqueta={d.tipo === 'INGRESO' ? 'Cobrado' : 'Pagado'} valor={`${formatearEur(d.cubierto)} · ${d.pagos} ${d.pagos === 1 ? 'pago' : 'pagos'}`} testID="detalle-cubierto" /> : null}
          {d.queda !== null && d.con_realidad ? <Fila etiqueta="Queda" valor={formatearEur(d.queda)} testID="detalle-queda" /> : null}
          {desviacion ? <Fila etiqueta="Diferencia" valor={desviacion} testID="detalle-desviacion" /> : null}
          <Fila etiqueta="Cuándo" valor={intervaloTexto(d)} />
          {cuenta ? <Fila etiqueta={d.tipo === 'INGRESO' ? 'En' : 'Desde'} valor={cuenta.nombre} /> : null}
          {d.tipo === 'TRANSFERENCIA' && d.cuenta_entrada ? <Fila etiqueta="Hacia" valor={d.cuenta_entrada.nombre} /> : null}
          {d.categoria ? <Fila etiqueta="Categoría" valor={d.categoria.ruta} /> : null}
          <Fila etiqueta="Origen" valor={ORIGEN[d.origen] ?? d.origen} />
        </View>
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NO_MUEVE}</Text>
        {d.importe_esperado === null && !terminal ? (
          <Text testID="detalle-sin-esperado" style={[tipo.footnote, { color: c.textSecondary }]}>Sin importe esperado no hay confirmación rápida: indica el importe real en el formulario.</Text>
        ) : null}
        {d.con_realidad && !terminal && d.queda !== null ? <Text testID="detalle-cubrir-resto" style={[tipo.footnote, { color: c.textPrimary }]}>{TEXTO_CUBRIR_RESTO}</Text> : null}
        {d.con_realidad && !terminal && d.desviacion !== null ? (
          <Text testID="detalle-sigue-pendiente" style={[tipo.footnote, { color: c.textSecondary }]}>Dijiste que aún falta una parte, así que sigue pendiente hasta que registres o enlaces lo que falte.</Text>
        ) : null}
        <AccionPrevision testID="prevision-accion-registrar" primaria titulo={d.tipo === 'INGRESO' ? 'Registrar cobro' : d.tipo === 'TRANSFERENCIA' ? 'Registrar transferencia' : 'Registrar pago'}
          disponible={d.acciones.registrar.disponible} motivo={d.acciones.registrar.motivo} onPress={() => setVista('REGISTRO')} />
        <AccionPrevision testID="prevision-accion-ya" titulo="Ya lo registré" disponible={d.acciones.ya_lo_registre.disponible}
          motivo={d.acciones.ya_lo_registre.motivo} onPress={() => setVista('YA')} />
        <AccionPrevision testID="prevision-accion-omitir" titulo="No hubo este mes" disponible={d.acciones.omitir.disponible}
          motivo={d.acciones.omitir.motivo} onPress={() => setOmitir({ motivo: '', enviando: false, error: null })} />
        {ofreceDarPorCubierta(d) ? (
          <AccionPrevision testID="prevision-accion-dar-por-cubierta" titulo="Dar por cubierta" disponible={d.acciones.dar_por_cubierta.disponible}
            motivo={d.acciones.dar_por_cubierta.motivo} onPress={() => setTransicion({ tipo: 'CUBIERTA', motivo: '', enviando: false, error: null })} />
        ) : null}
      </ScrollView>
      {mas ? (
        <HojaMas reabrir={d.acciones.reabrir} onCerrar={() => setMas(false)}
          onReabrir={() => { setMas(false); setTransicion({ tipo: 'REABRIR', motivo: '', enviando: false, error: null }); }} />
      ) : null}
      {transicion?.tipo === 'CUBIERTA' ? (
        <HojaDarPorCubierta detalle={d} motivo={transicion.motivo} onMotivo={(t) => setTransicion({ ...transicion, motivo: t })} enviando={transicion.enviando}
          error={transicion.error} onConfirmar={confirmarTransicion} onCerrar={() => setTransicion(null)} />
      ) : null}
      {transicion?.tipo === 'REABRIR' ? (
        <HojaReabrir detalle={d} motivo={transicion.motivo} onMotivo={(t) => setTransicion({ ...transicion, motivo: t })} enviando={transicion.enviando}
          error={transicion.error} onConfirmar={confirmarTransicion} onCerrar={() => setTransicion(null)} />
      ) : null}
      {omitir ? (
        <HojaOmitir fila={d} motivo={omitir.motivo} onMotivo={(t) => setOmitir({ ...omitir, motivo: t })} enviando={omitir.enviando}
          error={omitir.error} onConfirmar={confirmarOmitir} onCerrar={() => setOmitir(null)} />
      ) : null}
      {aviso ? (
        <AvisoEstadoActual concepto={d.concepto} intervalo={intervaloTexto(d)} estado={aviso.estado} derivado={aviso.derivado} incierto={aviso.incierto}
          mensaje={aviso.mensaje} onEntendido={() => { setAviso(null); setFueIncierto(false); setCambios(true); void cargar(); }} />
      ) : null}
    </View>
  );
}

function Fila({ etiqueta, valor, testID }: { etiqueta: string; valor: string; testID?: string }) {
  const { c } = useTema();
  return (
    <View style={s.fila}>
      <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{etiqueta}</Text>
      <Text testID={testID} style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600', flexShrink: 1, textAlign: 'right' }]}>{valor}</Text>
    </View>
  );
}

// ------------------------------------------------------------------ «Ya lo registré» (B2)
function YaLoRegistre(p: { cliente: ClienteApi; nuevoId: () => string; detalle: DetallePrevision; onVolver: (enlazado: boolean) => void }) {
  const { c } = useTema();
  const d = p.detalle;
  const [ampliado, setAmpliado] = useState(false);
  const [lista, setLista] = useState<{ fase: 'CARGANDO' } | { fase: 'OK'; datos: CandidatosPrevision } | { fase: 'ERROR' }>({ fase: 'CARGANDO' });
  const [elegido, setElegido] = useState<CandidatoPrevision | null>(null); // sin preselección
  const [marcar, setMarcar] = useState<boolean | null>(null);
  const [envio, setEnvio] = useState<{ fase: 'LIBRE' } | { fase: 'ENVIANDO' } | { fase: 'ERROR'; mensaje: string; incierto: boolean; codigo?: string }>({ fase: 'LIBRE' });
  const intencion = usarIntencion(p.nuevoId);

  const cargar = useCallback(async (amp: boolean) => {
    setLista({ fase: 'CARGANDO' });
    const r = await p.cliente.candidatosPrevision(d.id, amp);
    setLista(r.tipo === 'OK' ? { fase: 'OK', datos: r.datos } : { fase: 'ERROR' });
  }, [p.cliente, d.id]);

  useEffect(() => {
    void cargar(ampliado);
  }, [cargar, ampliado]);

  const enlazar = async () => {
    if (!elegido || marcar === null) return;
    setEnvio({ fase: 'ENVIANDO' });
    const r = await p.cliente.vincularPrevision(d.id, {
      intencion_id: intencion.actual(), row_version: d.row_version, hecho_id: elegido.hecho_id,
      importe_a_vincular: elegido.porcion_disponible, marcar_realizada: marcar,
    });
    if (r.tipo === 'OK') {
      intencion.liberar();
      return p.onVolver(true);
    }
    if (r.tipo === 'INDETERMINADO') return setEnvio({ fase: 'ERROR', mensaje: `${r.mensaje} Puedes reintentar: no se enlazará dos veces.`, incierto: true });
    intencion.liberar();
    // Un cambio concurrente: se relee y se vuelve a mostrar antes de enlazar (nunca otra cantidad en silencio).
    setElegido(null);
    setEnvio({ fase: 'ERROR', mensaje: r.mensaje, incierto: false, codigo: r.codigo });
    void cargar(ampliado);
  };

  const vinc = elegido ? textoSeVinculara(elegido.porcion_disponible, d) : null;
  return (
    <View testID="ya-lo-registre" style={[s.raiz, { backgroundColor: c.background }]}>
      <CabeceraNavegacion titulo="Ya lo registré" atras={{ etiqueta: 'Atrás', onPress: () => p.onVolver(false) }} testIDAtras="ya-atras" />
      <ScrollView contentContainerStyle={estilosFormulario.cuerpo}>
        <Text style={[tipo.body, { color: c.textPrimary }]}>
          {`Elige el registro que corresponde a ${d.concepto} (${importeFila(d)}, ${intervaloTexto(d)}). Así no se cuenta dos veces.`}
        </Text>
        {lista.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
        {lista.fase === 'ERROR' ? <BotonTexto testID="ya-reintentar" titulo="No se pudieron cargar · Reintentar" onPress={() => cargar(ampliado)} /> : null}
        {lista.fase === 'OK' && lista.datos.mensaje ? <Text testID="ya-mensaje" style={[tipo.footnote, { color: c.textSecondary }]}>{lista.datos.mensaje}</Text> : null}
        {lista.fase === 'OK' && !lista.datos.mensaje && lista.datos.candidatos.length === 0 ? (
          <Text testID="ya-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>{`No hay registros cercanos (±${lista.datos.ventana_dias} días) con su mismo tercero o categoría.`}</Text>
        ) : null}
        {lista.fase === 'OK' ? (
          <View>
            {lista.datos.candidatos.map((x) => {
              const sel = elegido?.hecho_id === x.hecho_id;
              return (
                <Pressable key={x.hecho_id} testID={`candidato-${x.hecho_id}`} accessibilityRole="radio" accessibilityState={{ selected: sel, checked: sel }}
                  onPress={() => setElegido(x)} style={[s.candidato, { borderColor: sel ? c.accent : c.borderDefault, backgroundColor: sel ? c.accentSurface : c.surfacePrimary }]}>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={[tipo.body, { color: c.textPrimary, fontWeight: '600' }]}>{[x.tercero, x.categoria].filter(Boolean).join(' · ') || x.concepto || 'Registro'}</Text>
                    <Text style={[tipo.caption, { color: c.textSecondary }]}>{[diaMesIso(x.fecha_hecho), x.cuenta, `libre ${formatearEur(x.porcion_disponible).replace(' €', '')}`].filter(Boolean).join(' · ')}</Text>
                  </View>
                  <Text style={[estiloImporte.secondary, { color: c.textPrimary, fontSize: 17 }]}>{`${d.tipo === 'INGRESO' ? '+' : d.tipo === 'TRANSFERENCIA' ? '' : '−'}${formatearEur(x.importe_total)}`}</Text>
                </Pressable>
              );
            })}
          </View>
        ) : null}
        {!ampliado ? <BotonTexto testID="ya-mas-fechas" titulo="Buscar en más fechas" onPress={() => { setElegido(null); setAmpliado(true); }} /> : null}
        {vinc ? (
          <View testID="ya-se-vinculara" style={[s.bloque, { borderColor: c.borderDefault }]}>
            <Text style={[tipo.body, { color: c.textPrimary, fontWeight: '600' }]}>{vinc.titulo}</Text>
            {vinc.detalle ? <Text style={[tipo.footnote, { color: c.textSecondary }]}>{vinc.detalle}</Text> : null}
          </View>
        ) : null}
        {elegido ? <QuedaCubierta valor={marcar} onCambiar={setMarcar} testIDBase="ya-cubierta" /> : null}
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SOLO_ENLAZA}</Text>
        {envio.fase === 'ERROR' ? <Text testID="ya-error" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{envio.mensaje}</Text> : null}
        {envio.fase === 'ERROR' && (envio.codigo === 'VERSION_DESFASADA' || envio.codigo === 'ESTADO_PREVISION_INCOMPATIBLE') ? (
          <BotonTexto testID="ya-volver-prevision" titulo="Ver la previsión de nuevo" onPress={() => p.onVolver(false)} />
        ) : null}
        <BotonPrimario testID="ya-enlazar" titulo={envio.fase === 'ERROR' && envio.incierto ? 'Reintentar' : 'Enlazar'} cargando={envio.fase === 'ENVIANDO'}
          deshabilitado={!elegido || marcar === null} onPress={enlazar} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  raiz: { flex: 1 },
  mas: { minWidth: TACTIL_MIN, minHeight: TACTIL_MIN, alignItems: 'center', justifyContent: 'center' },
  titulo: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, flexWrap: 'wrap' },
  etiqueta: { borderRadius: radio.pill, paddingHorizontal: espacio.s, paddingVertical: 2 },
  bloque: { borderWidth: 1, borderRadius: radio.m, padding: espacio.m, gap: espacio.s },
  fila: { flexDirection: 'row', justifyContent: 'space-between', gap: espacio.m },
  candidato: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.m, padding: espacio.m, marginBottom: espacio.s, minHeight: TACTIL_MIN + 12 },
});
