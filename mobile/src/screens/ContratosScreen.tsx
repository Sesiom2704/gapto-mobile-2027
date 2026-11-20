// ============================================================
// GAPTO MOBILE 2027
// Fichero: ContratosScreen.tsx
// Ruta: mobile/src/screens/ContratosScreen.tsx
// Descripción: Contratos de una propiedad y su vida (F06-02/03; lámina CON v0.8 validada; contrato N1 v1.1 L-CON-01/02, C-CON-02..05). A1 lista por situación DERIVADA (vigentes, próximos, borradores, finalizados) con la ocupación de hoy por habitación («3 ocupadas · 1 próxima · 1 libre»; un borrador no ocupa; un vigente con el fin previsto pasado y sin fin real sigue ocupando y lleva «Termina o prorroga»; decisión 6) y SIN importes (la renta llega con la parte de cobros); A3 sin contratos; A2 detalle (personas con agencia o administrador, condiciones, servicios, «Renta y fianza · Se añadirán con la parte de cobros»); C2 prórroga con motivo; C3 terminar (último día real; no se borra nada); C3b terminación BLOQUEADA y explicada para contratos de V3 con renta (`terminable = false`, motivo RENTA_PENDIENTE_DE_F06_04; el botón aparece desactivado y la explicación va antes; el servidor responde lo mismo); C4 borrador («Completar y firmar» repite el solape: si coincide con un firmado, B2b y sigue en borrador; «Cancelar borrador» con motivo); C1 cambio de inquilino en una habitación (termina el actual y crea el nuevo en una sola operación). `ContratosFlujo` encadena lista, detalle, asistente, servicios y ficha de tercero sin librería de navegación.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import type { ClienteContratos, ContratoDetalle, ContratosPropiedad, FilaContrato, ResultadoContrato } from '../api/contratos';
import { BotonPrimario, BotonTexto, CabeceraNavegacion, Chip, EstadoDato } from '../components/Basicos';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef, FilaLista, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { CampoFechaIso, FilaInfo, SolapeInfo } from '../components/OpcionesContrato';
import { BotonSecundario } from '../components/SelectorCategorias';
import {
  agruparContratos, detalleFilaContrato, etiquetaUnidad, resumenOcupacion, solapadosDeDetalle, textoClausulaDetalle, textoCoincide, textoErrorContrato,
  textoRolPersona, textoSituacion, textoSolapeDetalle, TEXTO_BORRADOR_AYUDA, TEXTO_FIN_VENCIDO, TEXTO_MIENTRAS_TANTO, TEXTO_PRORROGA_AYUDA, TEXTO_RENTA_FIANZA_FILA,
  TEXTO_RENTA_FIANZA_TITULO, TEXTO_RENTA_REGISTRADA, TEXTO_SIN_CONTRATOS, TEXTO_SIN_RENTA_LISTA, TEXTO_TERMINACION_BLOQUEADA_DETALLE,
  TEXTO_TERMINACION_BLOQUEADA_TITULO, TEXTO_TERMINAR_NADA_SE_BORRA, TEXTO_YA_ALQUILADA_AVISO, TEXTO_YA_ALQUILADA_TITULO, resumenServiciosContrato,
} from '../domain/contratos';
import { diaMesAnioIso, isoLocal } from '../domain/fechas';
import { esFechaIso } from '../domain/intencion';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { ContratoAltaScreen, PropiedadElegible } from './ContratoAltaScreen';
import { ContratoServiciosScreen, ServiciosFlujo } from './ServiciosScreens';
import { TerceroFichaScreen } from './TerceroFichaScreen';

const TEXTO_INDETERMINADO = 'No se ha podido confirmar el cambio. Vuelve a cargar el contrato antes de repetirlo.';

// ================================================================ A1 / A3 · lista
export function ContratosListaScreen(p: {
  contratos: ClienteContratos;
  propiedad: { id: string; nombre: string };
  /** Cambia para forzar la relectura tras un alta o un cambio. */
  refresco?: number;
  etiquetaAtras?: string;
  onAtras: () => void;
  onNuevo: () => void;
  onAbrir: (id: string) => void;
  onServicios?: () => void;
}) {
  const { c } = useTema();
  const [datos, setDatos] = useState<ContratosPropiedad | null>(null);
  const [error, setError] = useState(false);
  const [verFinalizados, setVerFinalizados] = useState(false);

  const cargar = useCallback(async () => {
    setError(false);
    const r = await p.contratos.contratosDePropiedad(p.propiedad.id);
    if (r.tipo === 'OK') setDatos(r.datos);
    else setError(true);
  }, [p.propiedad.id]);
  useEffect(() => { void cargar(); }, [cargar, p.refresco]);

  const fila = (f: FilaContrato) => (
    <FilaLista key={f.contrato_id} testID={`contrato-fila-${f.contrato_id}`} titulo={f.nombre}
      detalle={[detalleFilaContrato(f), f.renta_registrada ? TEXTO_RENTA_REGISTRADA : null].filter(Boolean).join('\n')}
      derecha={f.fin_previsto_vencido ? <Text testID={`contrato-fila-${f.contrato_id}-vencido`} style={[tipo.caption, { color: c.warningText }]}>{TEXTO_FIN_VENCIDO}</Text>
        : f.situacion === 'BORRADOR' ? <Text style={[tipo.caption, { color: c.textSecondary }]}>Borrador</Text> : undefined}
      onPress={() => p.onAbrir(f.contrato_id)} />
  );

  const g = datos ? agruparContratos(datos.contratos) : null;
  return (
    <View testID="contratos-lista" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo="Contratos" atras={{ etiqueta: p.etiquetaAtras ?? 'Propiedad', onPress: p.onAtras }} testIDAtras="contratos-atras" />
      <ScrollView contentContainerStyle={ef.cuerpo}>
        {datos === null && !error ? <EstadoDato estado="CARGANDO" testID="contratos-cargando" /> : null}
        {error ? (
          <BotonTexto testID="contratos-error" titulo="No se pudo cargar. Tocar para reintentar" onPress={() => void cargar()} />
        ) : null}
        {datos !== null && datos.contratos.length === 0 ? (
          <View testID="contratos-vacio" style={{ gap: espacio.m }}>
            <Text style={[tipo.titleSmall, { color: c.textPrimary }]}>Sin contratos</Text>
            <Text style={[tipo.body, { color: c.textSecondary }]}>{TEXTO_SIN_CONTRATOS}</Text>
          </View>
        ) : null}
        {datos !== null && g !== null && datos.contratos.length > 0 ? (
          <>
            {datos.ocupacion.length > 0 ? (
              <View testID="contratos-hoy" style={{ gap: 2 }}>
                <RotuloGrupo texto="Hoy · habitaciones (ficha)" />
                <Text testID="contratos-hoy-resumen" style={[tipo.body, { color: c.textPrimary }]}>{resumenOcupacion(datos.ocupacion)}</Text>
              </View>
            ) : null}
            {g.vigentes.length > 0 ? <RotuloGrupo texto="Vigentes" /> : null}
            {g.vigentes.map(fila)}
            {g.proximos.length > 0 ? <RotuloGrupo texto="Próximos" /> : null}
            {g.proximos.map(fila)}
            {g.borradores.length > 0 ? <RotuloGrupo texto="Borradores" /> : null}
            {g.borradores.map(fila)}
            {g.finalizados.length > 0 ? (
              <>
                <RotuloGrupo texto="Finalizados" />
                <BotonTexto testID="contratos-finalizados-ver" titulo={verFinalizados ? 'Ocultar' : `Ver ${g.finalizados.length}`} onPress={() => setVerFinalizados(!verFinalizados)} />
                {verFinalizados ? g.finalizados.map(fila) : null}
              </>
            ) : null}
            <Text testID="contratos-sin-importes" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_RENTA_LISTA}</Text>
          </>
        ) : null}
        {p.onServicios ? <FilaLista testID="contratos-servicios" titulo="Servicios de la propiedad" detalle="Luz, agua, internet y otros" onPress={p.onServicios} /> : null}
        <BotonPrimario testID="contratos-nuevo" titulo="Nuevo contrato" onPress={p.onNuevo} />
      </ScrollView>
    </View>
  );
}

// ================================================================ A2 / C2 / C3 / C3b / C4 / C1 · detalle y vida del contrato
type Tarea = null | 'PRORROGAR' | 'TERMINAR' | 'SUCESOR' | 'CANCELAR';

export function ContratoDetalleScreen(p: {
  contratos: ClienteContratos;
  contratoId: string;
  nuevoId: () => string;
  ahora: () => Date;
  etiquetaAtras?: string;
  onAtras: () => void;
  /** Hubo una escritura: la lista se relee. */
  onCambios?: () => void;
  onTercero?: (terceroId: string) => void;
  /** D3: tratamiento de los servicios en este contrato. */
  onTratamientos?: (c: ContratoDetalle) => void;
  /** C1: continuar con el contrato nuevo (asistente en modo sucesor). */
  onSucesor?: (s: { actual: ContratoDetalle; fechaFinReal: string; nuevoInicio: string; copiar: { clausula: boolean; servicios: boolean } }) => void;
  refresco?: number;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const [ct, setCt] = useState<ContratoDetalle | null>(null);
  const [error, setError] = useState(false);
  const [tarea, setTarea] = useState<Tarea>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);
  const [solape, setSolape] = useState<string[] | null>(null);
  // Campos de las tareas
  const [nuevoFin, setNuevoFin] = useState('');
  const [motivo, setMotivo] = useState('');
  const [ultimoDia, setUltimoDia] = useState('');
  const [nuevoInicio, setNuevoInicio] = useState('');
  const [copiarClausula, setCopiarClausula] = useState(false);
  const [copiarServicios, setCopiarServicios] = useState(false);
  const intenciones = useRef<Record<string, string>>({});

  const cargar = useCallback(async () => {
    setError(false);
    const r = await p.contratos.contrato(p.contratoId);
    if (r.tipo === 'OK') setCt(r.datos.contrato);
    else setError(true);
  }, [p.contratoId]);
  useEffect(() => { void cargar(); }, [cargar, p.refresco]);

  /** La intención es la misma mientras el contenido es el mismo (replay idempotente). */
  const intencion = (clave: string) => (intenciones.current[clave] ??= p.nuevoId());

  const resolver = async (clave: string, enviar: (id: string) => Promise<import('../api/cliente').Respuesta<ResultadoContrato>>) => {
    if (ocupado) return;
    setOcupado(true);
    setAviso(null);
    const r = await enviar(intencion(clave));
    setOcupado(false);
    if (r.tipo === 'OK') {
      setCt(r.datos.contrato);
      setTarea(null);
      setSolape(null);
      p.onCambios?.();
      return;
    }
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    delete intenciones.current[clave]; // un rechazo no escribió nada: el siguiente intento es una intención nueva
    if (r.codigo === 'VERSION_DESFASADA') {
      setAviso({ tipo: 'AVISO', texto: textoErrorContrato(r.codigo, r.mensaje, r.detalle) });
      return void cargar();
    }
    if (r.codigo === 'SOLAPE_CON_CONTRATO_FIRMADO') {
      const d = solapadosDeDetalle(r.detalle);
      setTarea(null);
      return setSolape(d.map(textoSolapeDetalle));
    }
    setAviso({ tipo: 'AVISO', texto: textoErrorContrato(r.codigo, r.mensaje, r.detalle) });
  };

  const unidad = ct ? etiquetaUnidad(ct, ct.propiedad_nombre) : '';
  const cerrarTarea = () => { setTarea(null); setAviso(null); };

  // ---------------- C2 · prórroga
  if (ct && tarea === 'PRORROGAR') {
    const faltas = !esFechaIso(nuevoFin) ? 'Indica el nuevo fin previsto.' : nuevoFin < ct.fecha_inicio ? 'El fin previsto no puede ser anterior al inicio.' : motivo.trim() === '' ? 'Indica el motivo.' : null;
    return (
      <View testID="contrato-prorrogar" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Prorrogar" testIDCancelar="contrato-prorrogar-cancelar" onCancelar={cerrarTarea} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {aviso ? <Caja testID="contrato-tarea-aviso" aviso={aviso} /> : null}
          <FilaInfo testID="contrato-prorrogar-actual" etiqueta="Fin previsto actual" valor={ct.fecha_fin_prevista ? diaMesAnioIso(ct.fecha_fin_prevista) : 'Sin fin previsto'} />
          <Campo etiqueta="Nuevo fin previsto"><CampoFechaIso testID="contrato-prorrogar-fin" etiqueta="Nuevo fin previsto, día barra mes barra año" iso={nuevoFin} hoyIso={hoyIso} onCambiar={setNuevoFin} /></Campo>
          <Campo etiqueta="Motivo"><CampoTexto testID="contrato-prorrogar-motivo" etiqueta="Motivo" marcador="Ej.: Prórroga anual" valor={motivo} onCambiar={setMotivo} /></Campo>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_PRORROGA_AYUDA}</Text>
          <BotonPrimario testID="contrato-prorrogar-guardar" titulo="Guardar" cargando={ocupado} deshabilitado={faltas !== null} ayuda={faltas ?? undefined}
            onPress={() => void resolver(`prorroga|${nuevoFin}|${motivo.trim()}`, (id) => p.contratos.editarContrato(ct.contrato_id, { intencion_id: id, row_version_esperada: ct.row_version, fecha_fin_prevista: nuevoFin, motivo: motivo.trim() }))} />
        </ScrollView>
      </View>
    );
  }

  // ---------------- C3 · terminar
  if (ct && tarea === 'TERMINAR') {
    const falta = !esFechaIso(ultimoDia) ? 'Indica el último día real.' : ultimoDia < ct.fecha_inicio ? 'El último día no puede ser anterior al inicio.' : null;
    return (
      <View testID="contrato-terminar" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Terminar contrato" testIDCancelar="contrato-terminar-cancelar" onCancelar={cerrarTarea} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {aviso ? <Caja testID="contrato-tarea-aviso" aviso={aviso} /> : null}
          <Campo etiqueta="Último día real"><CampoFechaIso testID="contrato-terminar-dia" etiqueta="Último día real, día barra mes barra año" iso={ultimoDia} hoyIso={hoyIso} onCambiar={setUltimoDia} /></Campo>
          <FilaInfo testID="contrato-terminar-personas" etiqueta="Personas" valor="Su vigencia acaba ese día" />
          <FilaInfo testID="contrato-terminar-servicios" etiqueta="Servicios del contrato" valor="Terminan ese día" />
          {ct.tipo === 'HABITACION' ? <FilaInfo testID="contrato-terminar-habitacion" etiqueta="Habitación" valor={esFechaIso(ultimoDia) ? `Libre desde el ${diaMesAnioIso(siguienteDia(ultimoDia))}` : 'Libre al día siguiente'} /> : null}
          <Text testID="contrato-terminar-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_TERMINAR_NADA_SE_BORRA}</Text>
          <BotonPrimario testID="contrato-terminar-confirmar" titulo="Terminar contrato" cargando={ocupado} deshabilitado={falta !== null} ayuda={falta ?? undefined}
            onPress={() => void resolver(`terminar|${ultimoDia}`, (id) => p.contratos.terminarContrato(ct.contrato_id, { intencion_id: id, row_version_esperada: ct.row_version, fecha_fin_real: ultimoDia }))} />
        </ScrollView>
      </View>
    );
  }

  // ---------------- C1 · cambio de inquilino en una habitación
  if (ct && tarea === 'SUCESOR') {
    const inq = ct.personas.find((x) => x.rol === 'INQUILINO' && x.vigente_hasta === null && x.principal) ?? ct.personas.find((x) => x.rol === 'INQUILINO' && x.vigente_hasta === null);
    const nombreInq = inq?.actor.nombre ?? 'el inquilino';
    const falta = !esFechaIso(ultimoDia) ? 'Indica el último día del inquilino actual.' : ultimoDia < ct.fecha_inicio ? 'El último día no puede ser anterior al inicio.'
      : !esFechaIso(nuevoInicio) ? 'Indica cuándo entra el nuevo inquilino.' : nuevoInicio <= ultimoDia ? 'El nuevo inquilino tiene que entrar después del último día del actual.' : null;
    return (
      <View testID="contrato-sucesor" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Cambio de inquilino" testIDCancelar="contrato-sucesor-cancelar" onCancelar={cerrarTarea} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          <FilaInfo testID="contrato-sucesor-actual" etiqueta="Contrato actual" valor={ct.nombre} />
          <FilaInfo testID="contrato-sucesor-habitacion" etiqueta="Habitación" valor={`${ct.habitacion ?? ''} · ${ct.propiedad_nombre}`} />
          <FilaInfo testID="contrato-sucesor-inquilino" etiqueta="Inquilino" valor={inq?.actor.nombre ?? ''} />
          <Campo etiqueta={`Último día de ${nombreInq}`}><CampoFechaIso testID="contrato-sucesor-fin" etiqueta="Último día del inquilino actual, día barra mes barra año" iso={ultimoDia} hoyIso={hoyIso} onCambiar={setUltimoDia} /></Campo>
          <Campo etiqueta="El nuevo inquilino entra el"><CampoFechaIso testID="contrato-sucesor-inicio" etiqueta="Inicio del contrato nuevo, día barra mes barra año" iso={nuevoInicio} hoyIso={hoyIso} onCambiar={setNuevoInicio} /></Campo>
          <RotuloGrupo texto="Copiar al contrato nuevo" />
          <View style={ef.chips}>
            <Chip testID="contrato-sucesor-copiar-clausula" etiqueta={`Revisión: ${textoClausulaDetalle(ct.clausula)}`} seleccionado={copiarClausula} onPress={() => setCopiarClausula(!copiarClausula)} />
            <Chip testID="contrato-sucesor-copiar-servicios" etiqueta={`Servicios: ${resumenServiciosContrato(ct) || 'ninguno'}`} seleccionado={copiarServicios} onPress={() => setCopiarServicios(!copiarServicios)} />
          </View>
          <Text testID="contrato-sucesor-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>Se termina el actual y se crea el nuevo juntos. La renta no se copia: todavía no existe en la app.</Text>
          <BotonPrimario testID="contrato-sucesor-continuar" titulo="Continuar con el contrato nuevo" deshabilitado={falta !== null} ayuda={falta ?? undefined}
            onPress={() => p.onSucesor?.({ actual: ct, fechaFinReal: ultimoDia, nuevoInicio, copiar: { clausula: copiarClausula, servicios: copiarServicios } })} />
        </ScrollView>
      </View>
    );
  }

  // ---------------- C4 · cancelar un borrador
  if (ct && tarea === 'CANCELAR') {
    return (
      <View testID="contrato-cancelar-borrador" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Cancelar borrador" testIDCancelar="contrato-cancelar-borrador-volver" onCancelar={cerrarTarea} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          {aviso ? <Caja testID="contrato-tarea-aviso" aviso={aviso} /> : null}
          <Campo etiqueta="Motivo"><CampoTexto testID="contrato-cancelar-motivo" etiqueta="Motivo" marcador="Ej.: no se llegó a firmar" valor={motivo} onCambiar={setMotivo} /></Campo>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>El registro se conserva; no se borra.</Text>
          <BotonPrimario testID="contrato-cancelar-confirmar" titulo="Cancelar borrador" cargando={ocupado} deshabilitado={motivo.trim() === ''}
            onPress={() => void resolver(`cancelar|${motivo.trim()}`, (id) => p.contratos.cancelarContrato(ct.contrato_id, { intencion_id: id, row_version_esperada: ct.row_version, motivo: motivo.trim() }))} />
        </ScrollView>
      </View>
    );
  }

  // ---------------- A2 / C4 / C3b · detalle
  const vigentes = ct?.personas.filter((x) => x.vigente_hasta === null) ?? [];
  const abierto = ct !== null && ct.estado_documental === 'FORMALIZADO' && ct.fecha_fin_real === null;
  return (
    <View testID="contrato-detalle" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo={ct?.nombre ?? 'Contrato'} atras={{ etiqueta: p.etiquetaAtras ?? 'Contratos', onPress: p.onAtras }} testIDAtras="contrato-detalle-atras" />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {ct === null && !error ? <EstadoDato estado="CARGANDO" testID="contrato-cargando" /> : null}
        {error ? <BotonTexto testID="contrato-error" titulo="No se pudo cargar. Tocar para reintentar" onPress={() => void cargar()} /> : null}
        {aviso ? <Caja testID="contrato-detalle-aviso" aviso={aviso} /> : null}
        {solape ? (
          <SolapeInfo testID="contrato-detalle-solape" titulo={TEXTO_YA_ALQUILADA_TITULO} intro={ct ? textoCoincide({ tipo: ct.tipo, habitacion: ct.habitacion, inicio: ct.fecha_inicio }, { tipo: 'VIVIENDA_COMPLETA' }) : ''}
            filas={solape} aviso={`${TEXTO_YA_ALQUILADA_AVISO} Sigue como borrador.`} />
        ) : null}
        {ct ? (
          <>
            <Text testID="contrato-unidad" style={[tipo.body, { color: c.textSecondary }]}>{unidad}</Text>
            <Text testID="contrato-situacion" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{textoSituacion(ct)}</Text>
            <FilaInfo testID="contrato-fechas" etiqueta="Del" valor={`${diaMesAnioIso(ct.fecha_inicio)}${ct.fecha_fin_real ? ` al ${diaMesAnioIso(ct.fecha_fin_real)}` : ct.fecha_fin_prevista ? ` al ${diaMesAnioIso(ct.fecha_fin_prevista)}` : ''}`} />
            {ct.fin_previsto_vencido ? <Text testID="contrato-fin-vencido" style={[tipo.footnote, { color: c.warningText }]}>Fin previsto vencido · termina o prorroga</Text> : null}
            {ct.renta_registrada ? <Text testID="contrato-renta-registrada" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_RENTA_REGISTRADA}</Text> : null}

            <RotuloGrupo texto="Personas" />
            {vigentes.map((x) => (
              <FilaLista key={x.persona_id} testID={`contrato-persona-${x.persona_id}`} titulo={x.actor.yo ? 'Tú' : x.actor.nombre ?? 'Persona'} detalle={textoRolPersona(x)}
                onPress={() => { if (x.actor.tercero_id) p.onTercero?.(x.actor.tercero_id); }} />
            ))}
            <RotuloGrupo texto="Condiciones" />
            <FilaInfo testID="contrato-clausula" etiqueta="Revisión" valor={textoClausulaDetalle(ct.clausula)} />
            {ct.clausula?.fecha_primera_revision ? <FilaInfo testID="contrato-clausula-primera" etiqueta="Primera" valor={diaMesAnioIso(ct.clausula.fecha_primera_revision)} /> : null}
            {p.onTratamientos && ct.estado_documental !== 'CANCELADO' && ct.fecha_fin_real === null ? (
              <FilaLista testID="contrato-servicios" titulo="Servicios" detalle={resumenServiciosContrato(ct) || 'Sin indicar'} onPress={() => p.onTratamientos?.(ct)} />
            ) : (
              <FilaInfo testID="contrato-servicios" etiqueta="Servicios" valor={resumenServiciosContrato(ct) || 'Sin indicar'} />
            )}
            <FilaInfo testID="contrato-renta-fianza" etiqueta={TEXTO_RENTA_FIANZA_TITULO} valor={TEXTO_RENTA_FIANZA_FILA} />

            {ct.estado_documental === 'BORRADOR' ? (
              <View testID="contrato-borrador" style={{ gap: espacio.m }}>
                <Text testID="contrato-borrador-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_BORRADOR_AYUDA}</Text>
                <BotonPrimario testID="contrato-firmar" titulo="Completar y firmar" cargando={ocupado}
                  onPress={() => void resolver('formalizar', (id) => p.contratos.formalizarContrato(ct.contrato_id, { intencion_id: id, row_version_esperada: ct.row_version }))} />
                <BotonSecundario testID="contrato-cancelar-borrador-abrir" titulo="Cancelar borrador" critico onPress={() => { setMotivo(''); setTarea('CANCELAR'); }} />
              </View>
            ) : null}

            {abierto ? (
              <View style={{ gap: espacio.m }}>
                <BotonSecundario testID="contrato-prorrogar-abrir" titulo="Prorrogar" onPress={() => { setNuevoFin(''); setMotivo(''); setTarea('PRORROGAR'); }} />
                {ct.tipo === 'HABITACION' && p.onSucesor ? (
                  <BotonSecundario testID="contrato-sucesor-abrir" titulo="Cambio de inquilino" onPress={() => { setUltimoDia(''); setNuevoInicio(''); setTarea('SUCESOR'); }} />
                ) : null}
                {ct.terminable.terminable ? (
                  <BotonSecundario testID="contrato-terminar-abrir" titulo="Terminar contrato" critico onPress={() => { setUltimoDia(''); setTarea('TERMINAR'); }} />
                ) : (
                  <View testID="contrato-terminacion-bloqueada" style={{ gap: espacio.s }}>
                    <Text testID="contrato-terminacion-bloqueada-titulo" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{TEXTO_TERMINACION_BLOQUEADA_TITULO}</Text>
                    <Text testID="contrato-terminacion-bloqueada-texto" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_TERMINACION_BLOQUEADA_DETALLE}</Text>
                    <BotonPrimario testID="contrato-terminar-bloqueado" titulo="Terminar contrato" deshabilitado ayuda={TEXTO_TERMINACION_BLOQUEADA_DETALLE} onPress={() => undefined} />
                    <Text testID="contrato-mientras-tanto" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_MIENTRAS_TANTO}</Text>
                  </View>
                )}
              </View>
            ) : null}
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

/** «2027-01-31» → «2027-02-01» (calendario civil, sin zonas horarias). */
export function siguienteDia(iso: string): string {
  const [a, m, d] = iso.split('-').map(Number);
  const f = new Date(Date.UTC(a, m - 1, d + 1));
  return `${String(f.getUTCFullYear()).padStart(4, '0')}-${String(f.getUTCMonth() + 1).padStart(2, '0')}-${String(f.getUTCDate()).padStart(2, '0')}`;
}

// ================================================================ flujo
type Destino =
  | { t: 'LISTA' }
  | { t: 'DETALLE'; id: string }
  | { t: 'ALTA' }
  | { t: 'SUCESOR'; s: NonNullable<Parameters<typeof ContratoAltaScreen>[0]['sucesor']> }
  | { t: 'SERVICIOS' }
  | { t: 'TRATAMIENTOS'; ct: ContratoDetalle }
  | { t: 'TERCERO'; id: string; volver: Destino };

/** Contratos de una propiedad: lista → detalle → asistente / sucesor → servicios → ficha de tercero. Sin librería de navegación. */
export function ContratosFlujo(p: {
  cliente: ClienteApi;
  contratos: ClienteContratos;
  propiedad: PropiedadElegible & { nombre: string };
  propiedades?: PropiedadElegible[];
  nuevoId: () => string;
  ahora: () => Date;
  etiquetaAtras?: string;
  onSalir: () => void;
  /** La pila es inmersiva (asistente, tareas): la barra inferior se oculta. */
  onInmersiva?: (i: boolean) => void;
}) {
  const [destino, setDestino] = useState<Destino>({ t: 'LISTA' });
  const [refresco, setRefresco] = useState(0);
  const inmersivo = destino.t === 'ALTA' || destino.t === 'SUCESOR';
  useEffect(() => { p.onInmersiva?.(inmersivo); }, [inmersivo]);
  const ir = (d: Destino) => setDestino(d);
  const volverLista = () => { setRefresco((n) => n + 1); ir({ t: 'LISTA' }); };

  if (destino.t === 'ALTA') {
    return <ContratoAltaScreen cliente={p.cliente} contratos={p.contratos} propiedad={p.propiedad} propiedades={p.propiedades} nuevoId={p.nuevoId} ahora={p.ahora}
      onCerrar={(g) => (g ? volverLista() : ir({ t: 'LISTA' }))} />;
  }
  if (destino.t === 'SUCESOR') {
    return <ContratoAltaScreen cliente={p.cliente} contratos={p.contratos} propiedad={p.propiedad} nuevoId={p.nuevoId} ahora={p.ahora} sucesor={destino.s}
      onCerrar={(g) => (g ? volverLista() : ir({ t: 'DETALLE', id: destino.s.actual.contrato_id }))} />;
  }
  if (destino.t === 'SERVICIOS') {
    return <ServiciosFlujo cliente={p.cliente} contratos={p.contratos} propiedad={p.propiedad} nuevoId={p.nuevoId} ahora={p.ahora} onAtras={() => ir({ t: 'LISTA' })} />;
  }
  if (destino.t === 'TRATAMIENTOS') {
    const ct = destino.ct;
    return <ContratoServiciosScreen contratos={p.contratos} contrato={ct} nuevoId={p.nuevoId} ahora={p.ahora} onAtras={() => ir({ t: 'DETALLE', id: ct.contrato_id })}
      onCambios={() => setRefresco((n) => n + 1)} />;
  }
  if (destino.t === 'TERCERO') {
    const volver = destino.volver;
    return <TerceroFichaScreen contratos={p.contratos} terceroId={destino.id} nuevoId={p.nuevoId} etiquetaAtras="Contrato" onAtras={() => ir(volver)}
      onContrato={(id) => ir({ t: 'DETALLE', id })} />;
  }
  if (destino.t === 'DETALLE') {
    const id = destino.id;
    return <ContratoDetalleScreen contratos={p.contratos} contratoId={id} nuevoId={p.nuevoId} ahora={p.ahora} refresco={refresco} onAtras={volverLista}
      onCambios={() => setRefresco((n) => n + 1)} onTercero={(t) => ir({ t: 'TERCERO', id: t, volver: { t: 'DETALLE', id } })}
      onTratamientos={(ct) => ir({ t: 'TRATAMIENTOS', ct })} onSucesor={(s) => ir({ t: 'SUCESOR', s })} />;
  }
  return <ContratosListaScreen contratos={p.contratos} propiedad={p.propiedad} refresco={refresco} etiquetaAtras={p.etiquetaAtras} onAtras={p.onSalir}
    onNuevo={() => ir({ t: 'ALTA' })} onAbrir={(id) => ir({ t: 'DETALLE', id })} onServicios={() => ir({ t: 'SERVICIOS' })} />;
}
