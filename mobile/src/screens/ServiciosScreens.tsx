// ============================================================
// GAPTO MOBILE 2027
// Fichero: ServiciosScreens.tsx
// Ruta: mobile/src/screens/ServiciosScreens.tsx
// Descripción: Servicios de una propiedad (F06-02/03; lámina CON v0.8 D1, D2, D3 y D5; contrato N1 v1.1 C-SRV-01..04, L-SRV-01). D1 lista de servicios con anteriores; D2 alta («Importe esperado» sale: llega con la parte de cobros; categoría opcional «al registrar sus pagos»); D3 tratamiento en el contrato (M-9: incluida, repercutida con % fijo —mayor que 0—, se reparte en cada factura —el % se decide en cada gasto— o la pagas tú; solo anota, no crea cobros; `desde` obligatoria; «Sin indicar» cierra el tratamiento vigente, nunca borra); D5 vida del servicio (la compañía real vive en cada pago: sin botón «Cambiar de compañía», solo la explicación; «Dar de baja» pone fecha de fin y no borra pagos; si el servidor responde REGLA_SERVICIO_PENDIENTE_DE_F06_04 se muestra su texto propio, nunca el de la renta del contrato).
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// Versión: 0.2.0 (F06 T6 · S1 piezas comunes; F09 0.55 §12.107.1 punto 9): los campos de porcentaje, plazo y tipo abren el teclado decimal (`CampoTexto decimal`); sin otros cambios.
// ============================================================

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import type { ClienteContratos, ContratoDetalle, ModoTratamiento, ServicioPropiedad, ServiciosPropiedad, TipoServicio } from '../api/contratos';
import { BotonPrimario, BotonTexto, CabeceraNavegacion, Chip, EstadoDato } from '../components/Basicos';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoSelector, CampoTexto, estilosFormulario as ef, FilaLista, RotuloGrupo } from '../components/Formulario';
import { Hoja } from '../components/HojasCategoria';
import { CampoFechaIso, FilaInfo, OpcionFila } from '../components/OpcionesContrato';
import { BotonSecundario } from '../components/SelectorCategorias';
import { construirArbol, elegibleParaGasto, rutaTexto } from '../domain/categoria';
import type { CategoriaNodo } from '../domain/categoria';
import {
  detalleFilaServicio, desdeMesAnio, NOMBRE_TIPO_SERVICIO, OPCIONES_TRATAMIENTO, parsearPorcentaje, textoErrorContrato, textoTratamiento, TEXTO_COMPANIA_AYUDA,
  TEXTO_TRATAMIENTO_AYUDA, TIPOS_SERVICIO, TEXTO_SERVICIO_NO_CREA_COBROS,
} from '../domain/contratos';
import { diaMesAnioIso, isoLocal } from '../domain/fechas';
import { esFechaIso } from '../domain/intencion';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

const TEXTO_INDETERMINADO = 'No se ha podido confirmar el cambio. Vuelve a cargar antes de repetirlo.';

/** Hoja de categoría de gasto (opcional) para «Categoría al registrar sus pagos». */
function HojaCategoriaServicio(p: { cliente: ClienteApi; onElegir: (c: { id: string; ruta: string } | null) => void; onCerrar: () => void }) {
  const [lista, setLista] = useState<CategoriaNodo[] | null>(null);
  useEffect(() => { void p.cliente.arbolCategorias().then((r) => setLista(r.tipo === 'OK' ? r.datos.categorias : [])); }, []);
  const arbol = lista ? construirArbol(lista) : null;
  const elegibles = lista && arbol ? lista.filter((n) => n.enabled && elegibleParaGasto(n)) : [];
  return (
    <Hoja titulo="Categoría" testID="servicio-categorias">
      {lista === null ? <EstadoDato estado="CARGANDO" /> : null}
      <ScrollView style={{ maxHeight: 340 }}>
        <OpcionFila testID="servicio-categoria-ninguna" titulo="Sin categoría" seleccionada={false} onPress={() => p.onElegir(null)} />
        {elegibles.map((n) => (
          <OpcionFila key={n.id} testID={`servicio-categoria-${n.id}`} titulo={arbol ? rutaTexto(arbol, n.id) : n.nombre} seleccionada={false}
            onPress={() => p.onElegir({ id: n.id, ruta: arbol ? rutaTexto(arbol, n.id) : n.nombre })} />
        ))}
      </ScrollView>
      <BotonSecundario testID="servicio-categorias-cerrar" titulo="Cerrar" onPress={p.onCerrar} />
    </Hoja>
  );
}

type DestinoSrv = { t: 'LISTA' } | { t: 'ALTA' } | { t: 'DETALLE'; s: ServicioPropiedad };

export function ServiciosFlujo(p: {
  cliente: ClienteApi;
  contratos: ClienteContratos;
  propiedad: { id: string; nombre: string };
  nuevoId: () => string;
  ahora: () => Date;
  etiquetaAtras?: string;
  onAtras: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const [destino, setDestino] = useState<DestinoSrv>({ t: 'LISTA' });
  const [datos, setDatos] = useState<ServiciosPropiedad | null>(null);
  const [error, setError] = useState(false);
  const [verAnteriores, setVerAnteriores] = useState(false);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);
  // D2
  const [tipoSrv, setTipoSrv] = useState<TipoServicio | null>(null);
  const [nombre, setNombre] = useState('');
  const [categoria, setCategoria] = useState<{ id: string; ruta: string } | null>(null);
  const [hojaCategoria, setHojaCategoria] = useState(false);
  const [desde, setDesde] = useState('');
  // D5
  const [bajando, setBajando] = useState(false);
  const [fin, setFin] = useState('');
  const intencion = useRef<Record<string, string>>({});
  const idDe = (k: string) => (intencion.current[k] ??= p.nuevoId());

  const cargar = useCallback(async () => {
    setError(false);
    const r = await p.contratos.serviciosDePropiedad(p.propiedad.id);
    if (r.tipo === 'OK') setDatos(r.datos);
    else setError(true);
  }, [p.propiedad.id]);
  useEffect(() => { void cargar(); }, [cargar]);

  const volver = () => { setAviso(null); setBajando(false); setDestino({ t: 'LISTA' }); };

  // ---------------- D2 · alta
  if (destino.t === 'ALTA') {
    const falta = !tipoSrv ? 'Elige el tipo.' : nombre.trim() === '' ? 'Ponle un nombre.' : nombre.trim().length > 160 ? 'El nombre admite hasta 160 caracteres.' : !esFechaIso(desde) ? 'Indica desde cuándo.' : null;
    const guardar = async () => {
      if (ocupado || falta || !tipoSrv) return;
      setOcupado(true);
      setAviso(null);
      const clave = `alta|${tipoSrv}|${nombre.trim()}|${categoria?.id ?? ''}|${desde}`;
      const r = await p.contratos.altaServicio({ intencion_id: idDe(clave), tipo_servicio: tipoSrv, nombre: nombre.trim(), categoria_default_id: categoria?.id ?? null, propiedad_id: p.propiedad.id, desde });
      setOcupado(false);
      if (r.tipo === 'OK') { setTipoSrv(null); setNombre(''); setCategoria(null); setDesde(''); await cargar(); return volver(); }
      if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: 'No se ha podido confirmar el alta. Vuelve a pulsar «Guardar servicio»: no se duplicará.' });
      delete intencion.current[clave];
      setAviso({ tipo: 'AVISO', texto: textoErrorContrato(r.codigo, r.mensaje, r.detalle) });
    };
    return (
      <View testID="servicio-alta" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Nuevo servicio" testIDCancelar="servicio-alta-cancelar" onCancelar={volver} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {aviso ? <Caja testID="servicio-aviso" aviso={aviso} /> : null}
          <Campo etiqueta="Tipo">
            <View style={ef.chips}>
              {TIPOS_SERVICIO.map((t) => (
                <Chip key={t} testID={`servicio-tipo-${t}`} etiqueta={NOMBRE_TIPO_SERVICIO[t]} seleccionado={tipoSrv === t}
                  onPress={() => { if (nombre.trim() === '' || (tipoSrv && nombre === NOMBRE_TIPO_SERVICIO[tipoSrv])) setNombre(NOMBRE_TIPO_SERVICIO[t]); setTipoSrv(t); }} />
              ))}
            </View>
          </Campo>
          <Campo etiqueta="Nombre"><CampoTexto testID="servicio-nombre" etiqueta="Nombre del servicio" maximo={160} valor={nombre} onCambiar={setNombre} /></Campo>
          <Campo etiqueta="Categoría al registrar sus pagos" opcional>
            <CampoSelector testID="servicio-categoria" etiqueta="Categoría" valor={categoria?.ruta ?? null} marcador="Sin categoría" onPress={() => setHojaCategoria(true)} />
          </Campo>
          <FilaInfo testID="servicio-propiedad" etiqueta="Propiedad" valor={p.propiedad.nombre} />
          <Campo etiqueta="Desde"><CampoFechaIso testID="servicio-desde" etiqueta="Desde, día barra mes barra año" iso={desde} hoyIso={hoyIso} onCambiar={setDesde} /></Campo>
          <BotonPrimario testID="servicio-guardar" titulo="Guardar servicio" cargando={ocupado} deshabilitado={falta !== null} ayuda={falta ?? undefined} onPress={() => void guardar()} />
        </ScrollView>
        {hojaCategoria ? <HojaCategoriaServicio cliente={p.cliente} onElegir={(x) => { setCategoria(x); setHojaCategoria(false); }} onCerrar={() => setHojaCategoria(false)} /> : null}
      </View>
    );
  }

  // ---------------- D5 · vida del servicio
  if (destino.t === 'DETALLE') {
    const s = destino.s;
    const falta = !esFechaIso(fin) ? 'Indica el último día del servicio.' : s.desde && fin < s.desde ? 'El fin no puede ser anterior al inicio.' : null;
    const darDeBaja = async () => {
      if (ocupado || falta) return;
      setOcupado(true);
      setAviso(null);
      const clave = `baja|${s.servicio_id}|${fin}`;
      const r = await p.contratos.bajaServicio(s.servicio_id, { intencion_id: idDe(clave), row_version_esperada: s.row_version, fecha_fin_real: fin });
      setOcupado(false);
      if (r.tipo === 'OK') { setFin(''); await cargar(); return volver(); }
      if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
      delete intencion.current[clave];
      setAviso({ tipo: 'AVISO', texto: textoErrorContrato(r.codigo, r.mensaje, r.detalle) });
    };
    return (
      <View testID="servicio-detalle" style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraNavegacion titulo={s.nombre} atras={{ etiqueta: 'Servicios', onPress: volver }} testIDAtras="servicio-detalle-atras" />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {aviso ? <Caja testID="servicio-aviso" aviso={aviso} /> : null}
          <FilaInfo testID="servicio-detalle-desde" etiqueta="Desde" valor={s.desde ? diaMesAnioIso(s.desde) : 'Sin indicar'} />
          {s.hasta ? <FilaInfo testID="servicio-detalle-hasta" etiqueta="Hasta" valor={diaMesAnioIso(s.hasta)} /> : null}
          <FilaInfo testID="servicio-detalle-compania" etiqueta="Compañía de los últimos pagos" valor={s.compania_ultimos_pagos ?? 'Sin pagos todavía'} />
          <Text testID="servicio-compania-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_COMPANIA_AYUDA}</Text>
          {s.hasta === null && !bajando ? <BotonSecundario testID="servicio-baja-abrir" titulo="Dar de baja el servicio" critico onPress={() => setBajando(true)} /> : null}
          {bajando ? (
            <>
              <Campo etiqueta="Último día del servicio"><CampoFechaIso testID="servicio-baja-fin" etiqueta="Último día del servicio, día barra mes barra año" iso={fin} hoyIso={hoyIso} onCambiar={setFin} /></Campo>
              <BotonPrimario testID="servicio-baja-confirmar" titulo="Dar de baja" cargando={ocupado} deshabilitado={falta !== null} ayuda={falta ?? undefined} onPress={() => void darDeBaja()} />
            </>
          ) : null}
        </ScrollView>
      </View>
    );
  }

  // ---------------- D1 · lista
  const fila = (s: ServicioPropiedad) => (
    <FilaLista key={s.servicio_id} testID={`servicio-fila-${s.servicio_id}`} titulo={s.nombre} detalle={detalleFilaServicio(s)} apagada={s.hasta !== null}
      onPress={() => { setFin(''); setAviso(null); setDestino({ t: 'DETALLE', s }); }} />
  );
  return (
    <View testID="servicios-lista" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo="Servicios" atras={{ etiqueta: p.etiquetaAtras ?? 'Contratos', onPress: p.onAtras }} testIDAtras="servicios-atras" />
      <ScrollView contentContainerStyle={ef.cuerpo}>
        {datos === null && !error ? <EstadoDato estado="CARGANDO" testID="servicios-cargando" /> : null}
        {error ? <BotonTexto testID="servicios-error" titulo="No se pudo cargar. Tocar para reintentar" onPress={() => void cargar()} /> : null}
        {datos ? datos.vigentes.map(fila) : null}
        {datos && datos.vigentes.length === 0 ? <Text testID="servicios-vacio" style={[tipo.body, { color: c.textSecondary }]}>Esta propiedad todavía no tiene servicios.</Text> : null}
        {datos && datos.anteriores.length > 0 ? (
          <>
            <RotuloGrupo texto="Anteriores" />
            <BotonTexto testID="servicios-anteriores-ver" titulo={verAnteriores ? 'Ocultar' : `Ver ${datos.anteriores.length}`} onPress={() => setVerAnteriores(!verAnteriores)} />
            {verAnteriores ? datos.anteriores.map(fila) : null}
          </>
        ) : null}
        <BotonPrimario testID="servicios-nuevo" titulo="Nuevo servicio" onPress={() => { setAviso(null); setDestino({ t: 'ALTA' }); }} />
      </ScrollView>
    </View>
  );
}

// ================================================================ D3 · tratamiento en el contrato
export function ContratoServiciosScreen(p: {
  contratos: ClienteContratos;
  contrato: ContratoDetalle;
  nuevoId: () => string;
  ahora: () => Date;
  onAtras: () => void;
  onCambios: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const [servicios, setServicios] = useState<ServiciosPropiedad | null>(null);
  const [elegido, setElegido] = useState<ServicioPropiedad | null>(null);
  const [modo, setModo] = useState<ModoTratamiento | null>(null);
  const [porcentaje, setPorcentaje] = useState('');
  const [desde, setDesde] = useState('');
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);
  const [ct, setCt] = useState(p.contrato);
  const intencion = useRef<Record<string, string>>({});

  useEffect(() => { void p.contratos.serviciosDePropiedad(p.contrato.propiedad_id).then((r) => { if (r.tipo === 'OK') setServicios(r.datos); }); }, [p.contrato.propiedad_id]);

  const inq = ct.personas.find((x) => x.rol === 'INQUILINO' && x.vigente_hasta === null && x.principal && x.actor.tercero_id) ?? null;
  const vigente = (id: string) => ct.servicios.find((x) => x.servicio_id === id && x.vigente_hasta === null) ?? null;

  if (elegido) {
    const necesitaInq = modo === 'REPERCUTIDO_FIJO' || modo === 'POR_FACTURA';
    const falta = modo === null ? 'Elige cómo se trata.' : !esFechaIso(desde) ? 'Indica desde cuándo.' : modo === 'REPERCUTIDO_FIJO' && parsearPorcentaje(porcentaje) === null ? 'El % fijo debe ser mayor que 0.'
      : necesitaInq && !inq ? 'Para repercutir hace falta un inquilino principal.' : null;
    const guardar = async () => {
      if (ocupado || falta || modo === null) return;
      setOcupado(true);
      setAviso(null);
      const clave = `${elegido.servicio_id}|${modo}|${porcentaje}|${desde}`;
      intencion.current[clave] ??= p.nuevoId();
      const r = await p.contratos.tratamientoServicio(ct.contrato_id, elegido.servicio_id, {
        intencion_id: intencion.current[clave], row_version_esperada: ct.row_version,
        tratamiento: {
          servicio_id: elegido.servicio_id, modo, desde,
          ...(necesitaInq ? { actor: { tercero_id: inq?.actor.tercero_id as string } } : {}),
          ...(modo === 'REPERCUTIDO_FIJO' ? { porcentaje: parsearPorcentaje(porcentaje) } : {}),
        },
      });
      setOcupado(false);
      if (r.tipo === 'OK') { setCt(r.datos.contrato); p.onCambios(); setElegido(null); setModo(null); setPorcentaje(''); setDesde(''); return; }
      if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
      delete intencion.current[clave];
      setAviso({ tipo: 'AVISO', texto: textoErrorContrato(r.codigo, r.mensaje, r.detalle) });
    };
    return (
      <View testID="tratamiento" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo={`${elegido.nombre} en ${ct.nombre}`} testIDCancelar="tratamiento-cancelar" onCancelar={() => { setElegido(null); setAviso(null); }} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {aviso ? <Caja testID="tratamiento-aviso" aviso={aviso} /> : null}
          <Text style={[tipo.titleSmall, { color: c.textPrimary }]}>¿Cómo se trata en este contrato?</Text>
          {OPCIONES_TRATAMIENTO.map((o) => (
            <OpcionFila key={o.modo} testID={`tratamiento-${o.modo}`} titulo={o.titulo} detalle={o.detalle} seleccionada={modo === o.modo} onPress={() => setModo(o.modo)} />
          ))}
          <OpcionFila testID="tratamiento-SIN_INDICAR" titulo="Sin indicar" detalle="Cierra el tratamiento vigente; no se borra nada" seleccionada={modo === 'SIN_INDICAR'} onPress={() => setModo('SIN_INDICAR')} />
          {modo === 'REPERCUTIDO_FIJO' ? (
            <Campo etiqueta="Porcentaje"><CampoTexto decimal testID="tratamiento-porcentaje" etiqueta="Porcentaje" marcador="% (mayor que 0)" valor={porcentaje} onCambiar={setPorcentaje} /></Campo>
          ) : null}
          {necesitaInq ? <FilaInfo testID="tratamiento-inquilino" etiqueta="Inquilino" valor={inq?.actor.nombre ?? 'Sin inquilino principal'} /> : null}
          <Campo etiqueta="Desde"><CampoFechaIso testID="tratamiento-desde" etiqueta="Desde, día barra mes barra año" iso={desde} hoyIso={hoyIso} onCambiar={setDesde} /></Campo>
          <Text testID="tratamiento-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_TRATAMIENTO_AYUDA}</Text>
          <BotonPrimario testID="tratamiento-guardar" titulo="Guardar" cargando={ocupado} deshabilitado={falta !== null} ayuda={falta ?? undefined} onPress={() => void guardar()} />
        </ScrollView>
      </View>
    );
  }

  return (
    <View testID="contrato-servicios-lista" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo="Servicios del contrato" atras={{ etiqueta: 'Contrato', onPress: p.onAtras }} testIDAtras="contrato-servicios-atras" />
      <ScrollView contentContainerStyle={ef.cuerpo}>
        {servicios === null ? <EstadoDato estado="CARGANDO" /> : null}
        {servicios?.vigentes.map((s) => {
          const v = vigente(s.servicio_id);
          return (
            <FilaLista key={s.servicio_id} testID={`contrato-servicio-fila-${s.servicio_id}`} titulo={s.nombre}
              detalle={v ? `${textoTratamiento(v.modo, v.porcentaje)}${v.vigente_desde ? ` · desde ${desdeMesAnio(v.vigente_desde)}` : ''}` : 'Sin indicar'}
              onPress={() => { setModo(null); setPorcentaje(''); setDesde(''); setAviso(null); setElegido(s); }} />
          );
        })}
        <Text testID="contrato-servicios-no-cobros" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SERVICIO_NO_CREA_COBROS}</Text>
      </ScrollView>
    </View>
  );
}
