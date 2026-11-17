// ============================================================
// GAPTO MOBILE 2027
// Fichero: HipotecaCuadroScreen.tsx
// Ruta: mobile/src/screens/HipotecaCuadroScreen.tsx
// Descripción: Cuadro de la hipoteca (F06-01H; contrato v0.4 §3.1, §3.3 y §8; mandato T3-F06 bloque 2 v1.1 §15). Dos vistas con la misma fila: (1) `CuadroPrevioScreen`, la vista previa de W-HIP-00 que abre «Ver el cuadro» del bloque «Hipoteca» de la compra (sin escritura), y (2) `HipotecaCuadroScreen`, la hipoteca registrada (L-HIP) desde la fila «Hipoteca» de la ficha: resumen (te queda por pagar —«No disponible» si el saldo es desconocido, nunca 0—, cuota actual, tipo vigente y desde cuándo, pagadas X de N, intereses pagados, prestado), aviso `aviso_reparto_distinto` (O-H30) si el servidor lo devuelve, ventana de cuotas alrededor de la próxima y la última, «Ver las N cuotas». Filas de DOS líneas con cifras tabulares (VP-3) y SIN swipe. Cabecera «Cerrar», no «Cancelar». «Pagar la cuota» es un BOTÓN (nunca swipe) y solo aparece con la constante de exposición `PAGO_CUOTA_EXPUESTO` (firma del 2026-11-17); «Revisar el tipo» abre W-HIP-03/04. `VERSION_DESFASADA` en el pago o la revisión vuelve a cargar la hipoteca. Tras cada escritura se pinta la hipoteca que devuelve el servidor. El cliente no calcula importes.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 10)
// ============================================================

import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import type { CuadroPrevio, CuotaHipoteca, FilaCuadroPrevio, Hipoteca } from '../api/hipoteca';
import type { ParteEnFecha } from '../api/patrimonio';
import { BotonPrimario, BotonTexto, CabeceraNavegacion, Chip, EstadoDato } from '../components/Basicos';
import { AvisoCaja, Caja, CampoTexto, estilosFormulario as ef, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { textoPartes } from '../domain/compra';
import { diaMesAnioIso, isoLocal } from '../domain/fechas';
import {
  condicionesVigentes, cuotasVisibles, deudaConocida, EleccionReparto, ETIQUETA_ESTADO, filasPrevioVisibles, nombreTipoInteres, ofrecePagoCuota, PAGO_CUOTA_EXPUESTO,
  TEXTO_AVISO_REPARTO, TEXTO_CONVENCION, TEXTO_RECARGADA, textoTasa,
} from '../domain/hipoteca';
import { formatearEur } from '../domain/importe';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { PagarCuotaScreen } from './PagarCuotaScreen';
import { RevisarTipoScreen } from './RevisarTipoScreen';

/** Cabecera de las vistas del cuadro: «Cerrar» a la derecha (hallazgo de captura b: no «Cancelar»). */
export function CabeceraCerrar(p: { titulo: string; testID: string; onCerrar: () => void }) {
  return <CabeceraNavegacion titulo={p.titulo} derecha={<BotonTexto testID={p.testID} titulo="Cerrar" onPress={p.onCerrar} />} />;
}

/** Fila del cuadro en DOS líneas (VP-3): «n/N · vencimiento · estado · cuota» y «Intereses · Capital · Queda». Cifras tabulares. Sin swipe. */
export function FilaCuota(p: { n: number; total: number; vencimiento: string | null; cuota: string; interes: string; capital: string; pendiente: string | null; estado?: string; ultima?: boolean }) {
  const { c } = useTema();
  const pagada = p.estado === 'PAGADA';
  return (
    <View testID={`hip-fila-${p.n}`} style={[s.fila, !p.ultima && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
      <View style={s.filaArriba}>
        <Text testID={`hip-fila-${p.n}-titulo`} style={[tipo.body, s.cifra, { color: c.textPrimary, flex: 1 }]} numberOfLines={1}>
          {`${p.n}/${p.total}${p.vencimiento ? ` · ${diaMesAnioIso(p.vencimiento)}` : ''}`}
        </Text>
        {p.estado ? <Text testID={`hip-fila-${p.n}-estado`} style={[tipo.caption, { color: pagada ? c.textSecondary : c.accentText }]}>{ETIQUETA_ESTADO[p.estado] ?? p.estado}</Text> : null}
        <Text testID={`hip-fila-${p.n}-cuota`} style={[tipo.bodyEmphasis, s.cifra, { color: c.textPrimary }]}>{formatearEur(p.cuota)}</Text>
      </View>
      <Text testID={`hip-fila-${p.n}-detalle`} style={[tipo.caption, s.cifra, { color: c.textSecondary }]} numberOfLines={2}>
        {`Intereses ${formatearEur(p.interes)} · Capital ${formatearEur(p.capital)} · Queda ${p.pendiente === null ? 'no disponible' : formatearEur(p.pendiente)}`}
      </Text>
    </View>
  );
}

export function Linea(p: { testID: string; etiqueta: string; valor: string | null; fuerte?: boolean; ultima?: boolean }) {
  const { c } = useTema();
  return (
    <View testID={p.testID} style={[s.linea, !p.ultima && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
      <Text style={[p.fuerte ? tipo.bodyEmphasis : tipo.body, { color: c.textPrimary, flex: 1 }]}>{p.etiqueta}</Text>
      {p.valor === null ? (
        <EstadoDato testID={`${p.testID}-nd`} estado="NO_DISPONIBLE" />
      ) : (
        <Text testID={`${p.testID}-valor`} style={[p.fuerte ? tipo.bodyEmphasis : tipo.body, s.cifra, { color: c.textPrimary }]}>{p.valor}</Text>
      )}
    </View>
  );
}

/** Reparto propuesto y modificable (titularidad del préstamo en el alta; reparto de los intereses en el pago). */
export function EleccionRepartoVista(p: {
  testID: string;
  propuesta: ParteEnFecha[] | null;
  textoPropuesta: string;
  eleccion: EleccionReparto;
  onCambiar: (e: EleccionReparto) => void;
  textoSinPropuesta: string;
}) {
  const { c } = useTema();
  const sin = p.propuesta !== null && p.propuesta.length === 0;
  const manual = p.eleccion?.modo === 'MANUAL' ? p.eleccion.partes : null;
  const actores = (p.propuesta ?? []).map((x) => ({ actor_id: x.actor_id, nombre: x.yo ? 'ti' : x.nombre ?? 'otra persona' }));
  return (
    <View testID={p.testID} style={{ gap: espacio.s }}>
      {p.propuesta === null ? <EstadoDato testID={`${p.testID}-cargando`} estado="CARGANDO" /> : null}
      {p.propuesta !== null && !sin ? (
        <Chip testID={`${p.testID}-propuesta`} etiqueta={`${p.textoPropuesta}: ${textoPartes(p.propuesta)}`} seleccionado={p.eleccion?.modo === 'TITULARIDAD'}
          onPress={() => p.onCambiar({ modo: 'TITULARIDAD' })} />
      ) : null}
      {sin ? <Text testID={`${p.testID}-sin`} style={[tipo.footnote, { color: c.warningText }]}>{p.textoSinPropuesta}</Text> : null}
      {actores.length > 0 ? (
        <Chip testID={`${p.testID}-manual`} etiqueta="Otro reparto · indica cuánto es de cada uno" seleccionado={p.eleccion?.modo === 'MANUAL'}
          onPress={() => p.onCambiar({ modo: 'MANUAL', partes: Object.fromEntries(actores.map((a) => [a.actor_id, ''])) })} />
      ) : null}
      {manual ? actores.map((a) => (
        <CampoTexto key={a.actor_id} testID={`${p.testID}-pct-${a.actor_id}`} etiqueta={`Porcentaje de ${a.nombre}`} marcador="%"
          valor={manual[a.actor_id] ?? ''} onCambiar={(t) => p.onCambiar({ modo: 'MANUAL', partes: { ...manual, [a.actor_id]: t } })} />
      )) : null}
    </View>
  );
}

/** (1) Vista previa de W-HIP-00 (sin escritura) desde el bloque «Hipoteca» de la compra. */
export function CuadroPrevioScreen(p: { cuadro: CuadroPrevio; onCerrar: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [todas, setTodas] = useState(false);
  const q = p.cuadro;
  const filas = filasPrevioVisibles(q.cuotas, todas);
  return (
    <View testID="hip-previo" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraCerrar titulo="Cuadro de la hipoteca" testID="hip-previo-cerrar" onCerrar={p.onCerrar} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Tarjeta testID="hip-previo-resumen">
          <Linea testID="hip-previo-cuota" etiqueta="Cuota mensual" valor={formatearEur(q.cuota_referencia)} fuerte />
          <Linea testID="hip-previo-prestado" etiqueta="Prestado" valor={formatearEur(q.capital)} />
          <Linea testID="hip-previo-intereses" etiqueta="Intereses en total" valor={formatearEur(q.suma_intereses)} />
          <Linea testID="hip-previo-total" etiqueta="Total a pagar" valor={formatearEur(q.total_a_pagar)} ultima />
        </Tarjeta>
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`${q.numero_cuotas} cuotas mensuales al ${textoTasa(q.tasa_anual)} anual. ${TEXTO_CONVENCION}`}</Text>
        <RotuloGrupo texto="Cuadro de amortización" />
        <Tarjeta testID="hip-previo-lista">
          {filas.map((f: FilaCuadroPrevio, i) => (
            <FilaCuota key={f.n} n={f.n} total={q.numero_cuotas} vencimiento={f.vencimiento} cuota={f.cuota} interes={f.interes} capital={f.capital} pendiente={f.pendiente}
              ultima={i === filas.length - 1} />
          ))}
        </Tarjeta>
        {q.cuotas.length > filas.length || todas ? (
          <BotonTexto testID="hip-previo-todas" titulo={todas ? 'Ver menos' : `Ver las ${q.cuotas.length} cuotas`} onPress={() => setTodas(!todas)} />
        ) : null}
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>Vista previa: todavía no se ha guardado nada.</Text>
      </ScrollView>
    </View>
  );
}

type Vista = { v: 'CARGANDO' } | { v: 'ERROR' } | { v: 'SIN' } | { v: 'CUADRO' } | { v: 'PAGO'; cuota: CuotaHipoteca } | { v: 'REVISION' };

/** (2) Hipoteca registrada (L-HIP) desde la ficha de la propiedad. */
export function HipotecaCuadroScreen(p: {
  cliente: ClienteApi;
  propiedadId: string;
  ahora: () => Date;
  nuevoId: () => string;
  /** Propuesta del reparto de los intereses en el vencimiento de una cuota (null si no se pudo leer). */
  leerPropuesta?: (fecha: string) => Promise<ParteEnFecha[] | null>;
  onCerrar: (cambios: boolean) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const [vista, setVista] = useState<Vista>({ v: 'CARGANDO' });
  const [hip, setHip] = useState<Hipoteca | null>(null);
  const [cambios, setCambios] = useState(false);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [todas, setTodas] = useState(false);

  const cargar = useCallback(async (avisoTras: AvisoCaja = null) => {
    if (!p.cliente.hipotecaDePropiedad) return setVista({ v: 'ERROR' });
    setVista({ v: 'CARGANDO' });
    const r = await p.cliente.hipotecaDePropiedad(p.propiedadId);
    if (r.tipo !== 'OK') return setVista({ v: 'ERROR' });
    setHip(r.datos.hipoteca);
    setAviso(avisoTras);
    setVista({ v: r.datos.hipoteca ? 'CUADRO' : 'SIN' });
  }, [p.cliente, p.propiedadId]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  /** VERSION_DESFASADA: se vuelve a leer la hipoteca y se avisa. */
  const recargar = () => void cargar({ tipo: 'AVISO', texto: TEXTO_RECARGADA });
  const escrita = (h: Hipoteca, texto: string) => {
    setHip(h);
    setCambios(true);
    setAviso({ tipo: 'OK', texto });
    setVista({ v: 'CUADRO' });
  };
  const cerrar = () => p.onCerrar(cambios);

  if (vista.v === 'PAGO' && hip && p.cliente.pagarCuotaHipoteca) {
    return (
      <PagarCuotaScreen cliente={p.cliente} hipoteca={hip} cuota={vista.cuota} hoyIso={hoyIso} nuevoId={p.nuevoId} leerPropuesta={p.leerPropuesta}
        onCancelar={() => setVista({ v: 'CUADRO' })} onPagada={(h) => escrita(h, `Cuota ${vista.cuota.numero} pagada.`)} onRecargar={recargar} />
    );
  }
  if (vista.v === 'REVISION' && hip && p.cliente.revisarTipoHipoteca) {
    return (
      <RevisarTipoScreen cliente={p.cliente} hipoteca={hip} hoyIso={hoyIso} nuevoId={p.nuevoId} onCancelar={() => setVista({ v: 'CUADRO' })}
        onRevisada={(h) => escrita(h, 'Tipo revisado. Las cuotas pendientes se han recalculado.')} onRecargar={recargar} />
    );
  }
  if (vista.v !== 'CUADRO' || !hip) {
    return (
      <View testID="hip-cuadro-estado" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraCerrar titulo="Hipoteca" testID="hip-cerrar" onCerrar={cerrar} />
        <View style={ef.cuerpo}>
          {vista.v === 'SIN' ? (
            <Text testID="hip-sin" style={[tipo.body, { color: c.textSecondary }]}>Esta propiedad no tiene hipoteca registrada.</Text>
          ) : (
            <EstadoDato testID="hip-estado" estado={vista.v === 'ERROR' ? 'ERROR_CARGA' : 'CARGANDO'} />
          )}
          {vista.v === 'ERROR' ? <BotonTexto testID="hip-reintentar" titulo="Reintentar" onPress={() => void cargar()} /> : null}
        </View>
      </View>
    );
  }

  const vigente = condicionesVigentes(hip);
  const filas = cuotasVisibles(hip, todas);
  const pagar = ofrecePagoCuota(hip, PAGO_CUOTA_EXPUESTO) && !!p.cliente.pagarCuotaHipoteca;
  const revisar = hip.estado === 'ACTIVA' && !hip.deuda_indeterminada && !!p.cliente.revisarTipoHipoteca;
  const tipoNombre = nombreTipoInteres(vigente?.tipo_interes);
  return (
    <View testID="hip-cuadro" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraCerrar titulo={hip.nombre} testID="hip-cerrar" onCerrar={cerrar} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {aviso ? <Caja testID="hip-aviso" aviso={aviso} /> : null}
        {hip.aviso_reparto_distinto ? <Text testID="hip-aviso-reparto" style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_AVISO_REPARTO}</Text> : null}
        <Tarjeta testID="hip-resumen">
          <Linea testID="hip-res-deuda" etiqueta="Te queda por pagar" valor={deudaConocida(hip) === null ? null : formatearEur(deudaConocida(hip)!)} fuerte />
          <Linea testID="hip-res-cuota" etiqueta="Cuota actual" valor={hip.cuota_vigente ? formatearEur(hip.cuota_vigente) : null} />
          <Linea testID="hip-res-tipo" etiqueta={tipoNombre ? `Tipo ${tipoNombre.toLowerCase()}` : 'Tipo'} valor={`${textoTasa(hip.tipo_vigente)}${hip.vigente_desde ? ` · desde el ${diaMesAnioIso(hip.vigente_desde)}` : ''}`} />
          <Linea testID="hip-res-pagadas" etiqueta="Cuotas pagadas" valor={`${hip.cuotas_pagadas} de ${hip.numero_cuotas}`} />
          <Linea testID="hip-res-intereses" etiqueta="Intereses pagados" valor={formatearEur(hip.intereses_pagados)} />
          <Linea testID="hip-res-prestado" etiqueta="Prestado" valor={hip.capital === null ? null : formatearEur(hip.capital)} ultima />
        </Tarjeta>
        {pagar && hip.proxima_cuota ? (
          <BotonPrimario testID="hip-pagar" titulo={`Pagar la cuota ${hip.proxima_cuota.numero} · ${formatearEur(hip.proxima_cuota.cuota)}`}
            onPress={() => { setAviso(null); setVista({ v: 'PAGO', cuota: hip.proxima_cuota! }); }} />
        ) : null}
        {revisar ? <BotonTexto testID="hip-revisar" titulo="Revisar el tipo" onPress={() => { setAviso(null); setVista({ v: 'REVISION' }); }} /> : null}
        <RotuloGrupo texto="Cuadro de amortización" />
        <Tarjeta testID="hip-lista">
          {filas.map((q, i) => (
            <FilaCuota key={q.numero} n={q.numero} total={hip.numero_cuotas} vencimiento={q.vencimiento} cuota={q.cuota} interes={q.interes} capital={q.capital}
              pendiente={q.pendiente} estado={q.estado} ultima={i === filas.length - 1} />
          ))}
        </Tarjeta>
        {hip.cuotas.length > filas.length || todas ? (
          <BotonTexto testID="hip-ver-todas" titulo={todas ? 'Ver menos' : `Ver las ${hip.cuotas.length} cuotas`} onPress={() => setTodas(!todas)} />
        ) : null}
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CONVENCION}</Text>
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  linea: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.s },
  fila: { paddingHorizontal: espacio.m, paddingVertical: espacio.s, gap: 2 },
  filaArriba: { flexDirection: 'row', alignItems: 'center', gap: espacio.s },
  cifra: { fontVariant: ['tabular-nums'] },
});
