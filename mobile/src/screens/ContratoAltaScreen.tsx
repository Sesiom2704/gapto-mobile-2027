// ============================================================
// GAPTO MOBILE 2027
// Fichero: ContratoAltaScreen.tsx
// Ruta: mobile/src/screens/ContratoAltaScreen.tsx
// Descripción: Asistente «Nuevo contrato» de F06-02/03 (lámina CON v0.8 validada; contrato N1 v1.1 C-CON-01; SIN renta ni fianza: 5 pasos). B1 Qué se alquila (+ B1b selector de propiedad), B2 Fechas y estado, B2b «Ya está alquilada en esas fechas» (decisiones 3 y 6: si coincide con un contrato FIRMADO —en los dos sentidos habitación ↔ vivienda completa; el fin previsto no libera— solo se puede guardar como borrador; un borrador no cuenta), B3 Personas (arrendadores o gestores, inquilinos, avalistas, agencia o administrador; «Tú» no es inquilino, agencia ni administrador; principal solo en arrendadores, gestores e inquilinos), B3b agencia o administrador (sin propuesta de rol), B3c elegir persona con homónimos distinguidos (V-bis), B3d posible duplicado (V-ter, la hoja existente de F05), B4 Cláusula de revisión, B5 Servicios (M-9) y B6 Resumen. Se guarda TODO en una sola operación (POST /v1/intenciones/contrato-alquiler) con la misma intención en el reintento (replay). Después de guardar, E3: propuesta de rol de tercero como escritura INDEPENDIENTE y opcional (ninguna opción marcada; no hay propuesta para agencia ni administrador); si falla, el contrato ya está guardado. Ninguna pantalla pide ni muestra renta, fianza, cobro ni IPC aplicado.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, Tercero } from '../api/cliente';
import type {
  ClienteContratos, ContratoDetalle, ContratosPropiedad, ModoTratamiento, OcupacionHabitacion, TipoClausula, RolParticipante, RolTercero, ServiciosPropiedad,
} from '../api/contratos';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoSelector, CampoTexto, estilosFormulario as ef, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { CampoFechaIso, FilaInfo, IndicadorPasos, OpcionFila, SolapeInfo } from '../components/OpcionesContrato';
import { Hoja } from '../components/HojasCategoria';
import { BotonSecundario } from '../components/SelectorCategorias';
import { SelectorParticipante } from '../components/SelectorParticipante';
import {
  BorradorContrato, borradorContrato, calcularSolapes, faltasContrato, faltasPaso, NOMBRE_ROL_PARTICIPANTE, NOMBRE_TIPO, OPCIONES_CLAUSULA,
  OPCIONES_TRATAMIENTO, PASOS_CONTRATO, PasoContrato, payloadAltaContrato, PersonaBorrador, proponeRol, rolPropuesto, ROLES_CON_PRINCIPAL, textoClausulaResumen,
  textoCoincide, textoErrorContrato, textoOcupacionHabitacion, textoPersonasResumen, textoProponerRol, textoSinRol, textoSolape, textoSolapeDetalle,
  textoTratamiento, TEXTO_AGENCIA_AYUDA, TEXTO_BORRADOR_AYUDA, TEXTO_PERSONAS_AYUDA, TEXTO_QUE_ALQUILAS, TEXTO_RESUMEN_SIN_RENTA, TEXTO_REVISION_AYUDA,
  TEXTO_SERVICIOS_AYUDA, TEXTO_UNA_OPERACION, TEXTO_YA_ALQUILADA_AVISO, TEXTO_YA_ALQUILADA_TITULO, solapadosDeDetalle, tratamientosWire,
  TEXTO_ACTUAL_SIN_HABITACIONES,
} from '../domain/contratos';
import { diaMesAnioIso, isoLocal } from '../domain/fechas';
import { esFechaIso } from '../domain/intencion';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

type Grupo = 'ARRENDADOR' | 'INQUILINO' | 'AVALISTA' | 'INTERMEDIARIO';
const TEXTO_INDETERMINADO = 'No se ha podido confirmar si el contrato se guardó. Pulsa de nuevo «Guardar contrato»: no se duplicará.';
/** Borrador del contrato sucesor: hereda propiedad, tipo y habitación; arrendadores y, si se pide, cláusula y servicios del actual. */
function borradorSucesor(s: NonNullable<Parameters<typeof ContratoAltaScreen>[0]['sucesor']>): BorradorContrato {
  const a = s.actual;
  const b = borradorContrato(a.propiedad_id, a.propiedad_nombre);
  const arrendadores: PersonaBorrador[] = a.personas
    .filter((x) => x.vigente_hasta === null && (x.rol === 'PROPIETARIO' || x.rol === 'GESTOR'))
    .map((x) => ({ clave: `${x.rol}-${x.actor.tercero_id ?? 'yo'}`, terceroId: x.actor.yo ? null : x.actor.tercero_id, nombre: x.actor.yo ? 'Tú' : x.actor.nombre ?? 'Titular', rol: x.rol, principal: x.principal }));
  const cl = a.clausula;
  return {
    ...b, tipo: a.tipo, habitacion: a.habitacion, fechaInicio: s.nuevoInicio, estado: 'FORMALIZADO', personas: arrendadores,
    clausula: s.copiar.clausula && cl
      ? { eleccion: cl.tipo === 'INDICE' || cl.tipo === 'OTRO' ? 'MANUAL' : cl.tipo, porcentaje: cl.porcentaje_fijo ?? '', periodicidad: cl.periodicidad_meses ? String(cl.periodicidad_meses) : '', primeraRevision: cl.fecha_primera_revision ?? '' }
      : b.clausula,
    servicios: s.copiar.servicios
      ? Object.fromEntries(a.servicios.filter((x) => x.vigente_hasta === null && x.modo !== 'SIN_INDICAR').map((x) => [x.servicio_id, { modo: x.modo, porcentaje: x.porcentaje ?? '' }]))
      : {},
  };
}

const TEXTO_PROPIEDADES_AYUDA = 'Solo propiedades en tu patrimonio. Las vendidas no aparecen.';

const Fecha = CampoFechaIso;

/** Lo mínimo de una propiedad para elegirla en B1b (sirve la vista completa o una fila de la lista). */
export interface PropiedadElegible { id: string; nombre: string; enabled: boolean; habitaciones?: number | null }

export function ContratoAltaScreen(p: {
  cliente: ClienteApi;
  contratos: ClienteContratos;
  /** Propiedad desde la que se abre (desde su ficha). `null` = se elige en B1b. */
  propiedad: PropiedadElegible | null;
  /** Propiedades elegibles en B1b (solo las del patrimonio). */
  propiedades?: PropiedadElegible[];
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (guardado: ContratoDetalle | null) => void;
  /** C-CON-05 / lámina C1: cambio de inquilino en una habitación. Hereda propiedad, tipo y habitación; empieza en Personas; guarda con POST …/sucesor. */
  sucesor?: { actual: ContratoDetalle; fechaFinReal: string; nuevoInicio: string; copiar: { clausula: boolean; servicios: boolean } };
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoyIso = isoLocal(p.ahora());
  const [paso, setPaso] = useState<PasoContrato | 'HECHO'>(p.sucesor ? 'PERSONAS' : 'QUE');
  const [b, setB] = useState<BorradorContrato>(() => (p.sucesor ? borradorSucesor(p.sucesor) : borradorContrato(p.propiedad?.id ?? null, p.propiedad?.nombre ?? '')));
  const [vistaProp, setVistaProp] = useState<PropiedadElegible | null>(p.propiedad);
  const [datos, setDatos] = useState<ContratosPropiedad | null>(null);
  const [servicios, setServicios] = useState<ServiciosPropiedad | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [solape, setSolape] = useState<string[] | null>(null);
  const [solapeTipo, setSolapeTipo] = useState<'VIVIENDA_COMPLETA' | 'HABITACION' | 'OTRO'>('VIVIENDA_COMPLETA');
  const [elegirPropiedad, setElegirPropiedad] = useState(false);
  const [anadiendo, setAnadiendo] = useState<{ grupo: Grupo; rol: RolParticipante | null; selector: boolean } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [guardado, setGuardado] = useState<ContratoDetalle | null>(null);
  const [propuestasRol, setPropuestasRol] = useState<{ terceroId: string; nombre: string; rol: RolTercero; rowVersion: number }[]>([]);
  const [avisoRol, setAvisoRol] = useState<AvisoCaja>(null);
  const [prerrellenado, setPrerrellenado] = useState(!!p.sucesor);
  const [abierto, setAbierto] = useState<string | null>(null);
  const ultimo = useRef<{ id: string; huella: string } | null>(null);
  const idRol = useRef<Record<string, string>>({});

  const habitacionesFicha = datos?.habitaciones_ficha ?? vistaProp?.habitaciones ?? null;

  // Lecturas de la propiedad elegida (L-CON-01 y L-SRV-01).
  useEffect(() => {
    if (!b.propiedadId) return;
    setDatos(null);
    setServicios(null);
    void p.contratos.contratosDePropiedad(b.propiedadId).then((r) => { if (r.tipo === 'OK') setDatos(r.datos); });
    void p.contratos.serviciosDePropiedad(b.propiedadId).then((r) => { if (r.tipo === 'OK') setServicios(r.datos); });
  }, [b.propiedadId]);

  const ocupacion = (): OcupacionHabitacion[] => {
    if (datos && datos.ocupacion.length > 0) return datos.ocupacion;
    const n = habitacionesFicha ?? 0;
    return Array.from({ length: n }, (_, i) => ({ habitacion: i + 1, estado: 'LIBRE' as const, hasta: null, desde: null, contrato_id: null }));
  };

  const set = (x: Partial<BorradorContrato>) => setB((v) => ({ ...v, ...x }));
  const indice = PASOS_CONTRATO.indexOf(paso === 'HECHO' ? 'RESUMEN' : paso);
  const faltas = paso === 'HECHO' ? [] : faltasPaso(paso, b, habitacionesFicha);

  const irAPaso = async (destino: PasoContrato) => {
    setAviso(null);
    if (destino === 'PERSONAS' && !prerrellenado && b.personas.length === 0 && b.propiedadId && b.tipo) {
      setPrerrellenado(true);
      const r = await p.contratos.propuestaContrato(b.propiedadId, { tipo: b.tipo, habitacion: b.habitacion, inicio: b.fechaInicio });
      if (r.tipo === 'OK') {
        const arr: PersonaBorrador[] = r.datos.arrendadores.map((a, i) => ({
          clave: `PROPIETARIO-${a.yo ? 'yo' : a.tercero_id}`, terceroId: a.yo ? null : a.tercero_id, nombre: a.yo ? 'Tú' : a.nombre ?? 'Titular', rol: 'PROPIETARIO', principal: i === 0,
        }));
        setB((v) => (v.personas.length === 0 ? { ...v, personas: arr } : v));
      }
    }
    if (destino === 'RESUMEN' && !b.nombreEditado && b.propiedadId && b.tipo) {
      const inq = b.personas.find((x) => x.rol === 'INQUILINO' && x.principal && x.terceroId !== null);
      const r = await p.contratos.propuestaContrato(b.propiedadId, { tipo: b.tipo, habitacion: b.habitacion, inicio: b.fechaInicio, inquilinoId: inq?.terceroId ?? null });
      if (r.tipo === 'OK') setB((v) => (v.nombreEditado ? v : { ...v, nombre: r.datos.nombre_propuesto }));
    }
    setPaso(destino);
  };

  const continuar = async () => {
    if (paso === 'HECHO' || faltas.length > 0) return;
    const sig = PASOS_CONTRATO[indice + 1];
    if (paso === 'FECHAS' && b.estado === 'FORMALIZADO' && b.tipo) {
      const s = calcularSolapes(datos?.contratos ?? [], { tipo: b.tipo, habitacion: b.habitacion, inicio: b.fechaInicio });
      if (s.length > 0) {
        setSolapeTipo(s[0].tipo);
        return setSolape(s.map(textoSolape));
      }
    }
    await irAPaso(sig);
  };

  const atras = () => {
    setAviso(null);
    if (paso === 'HECHO') return;
    if (indice > 0 && !(p.sucesor && paso === 'PERSONAS')) return setPaso(PASOS_CONTRATO[indice - 1]);
    p.onCerrar(null);
  };

  // ---------------- personas
  const agregar = (terceroId: string | null, nombre: string, rol: RolParticipante) => {
    setB((v) => {
      if (v.personas.some((x) => x.terceroId === terceroId && x.rol === rol)) return v;
      const principal = ROLES_CON_PRINCIPAL.includes(rol) && !v.personas.some((x) => x.rol === rol && x.principal);
      return { ...v, personas: [...v.personas, { clave: `${rol}-${terceroId ?? 'yo'}`, terceroId, nombre, rol, principal }] };
    });
    setAnadiendo(null);
  };
  const marcarPrincipal = (clave: string) =>
    setB((v) => {
      const x = v.personas.find((q) => q.clave === clave);
      if (!x) return v;
      return { ...v, personas: v.personas.map((q) => (q.rol !== x.rol ? q : { ...q, principal: q.clave === clave ? !q.principal : false })) };
    });
  const quitarPersona = (clave: string) => setB((v) => ({ ...v, personas: v.personas.filter((q) => q.clave !== clave) }));
  const abrirAnadir = (grupo: Grupo) => {
    const rol: RolParticipante | null = grupo === 'INQUILINO' ? 'INQUILINO' : grupo === 'AVALISTA' ? 'AVALISTA' : null;
    setAnadiendo({ grupo, rol, selector: rol !== null });
  };

  // ---------------- servicios
  const setTrat = (id: string, x: Partial<{ modo: ModoTratamiento | null; porcentaje: string }>) =>
    setB((v) => ({ ...v, servicios: { ...v.servicios, [id]: { ...{ modo: null, porcentaje: '' }, ...v.servicios[id], ...x } } }));

  // ---------------- guardar (una sola operación)
  const guardar = async () => {
    if (ocupado || paso !== 'RESUMEN') return;
    const todas = faltasContrato(b, habitacionesFicha);
    if (todas.length > 0 || b.nombre.trim() === '' || b.nombre.trim().length > 160) {
      return setAviso({ tipo: 'AVISO', texto: b.nombre.trim() === '' ? 'Ponle un nombre al contrato.' : b.nombre.trim().length > 160 ? 'El nombre admite hasta 160 caracteres.' : todas[0] });
    }
    setOcupado(true);
    setAviso(null);
    const cuerpo = payloadAltaContrato('', b);
    const huella = JSON.stringify({ ...cuerpo, intencion_id: '' });
    // Misma intención solo con el MISMO contenido (replay); si el contenido cambió, intención nueva.
    if (!ultimo.current || ultimo.current.huella !== huella) ultimo.current = { id: p.nuevoId(), huella };
    const intencion = ultimo.current.id;
    const r = p.sucesor
      ? await p.contratos.sucesorContrato(p.sucesor.actual.contrato_id, {
          intencion_id: intencion, row_version_esperada: p.sucesor.actual.row_version, fecha_fin_real: p.sucesor.fechaFinReal,
          nuevo: (({ intencion_id: _i, propiedad_id: _p, tipo: _t, habitacion: _h, ...resto }) => resto)(cuerpo),
        })
      : await p.contratos.altaContrato({ ...cuerpo, intencion_id: intencion });
    setOcupado(false);
    if (r.tipo === 'OK') {
      setGuardado(r.datos.contrato);
      setPaso('HECHO');
      void prepararPropuestasRol(r.datos.contrato);
      return;
    }
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    if (r.codigo === 'SOLAPE_CON_CONTRATO_FIRMADO') {
      const d = solapadosDeDetalle(r.detalle);
      setSolapeTipo(d[0]?.tipo ?? 'VIVIENDA_COMPLETA');
      setPaso('FECHAS');
      return setSolape(d.length > 0 ? d.map(textoSolapeDetalle) : [textoErrorContrato(r.codigo, r.mensaje, r.detalle)]);
    }
    setAviso({ tipo: 'AVISO', texto: textoErrorContrato(r.codigo, r.mensaje, r.detalle) });
  };

  // ---------------- E3: propuesta de rol de tercero (escritura independiente, tras guardar)
  const prepararPropuestasRol = async (ct: ContratoDetalle) => {
    const vistos = new Set<string>();
    const cola: { terceroId: string; nombre: string; rol: RolTercero; rowVersion: number }[] = [];
    for (const x of ct.personas) {
      const tid = x.actor.tercero_id;
      if (!tid || x.actor.yo || !proponeRol(x.rol) || vistos.has(`${tid}|${x.rol}`)) continue;
      vistos.add(`${tid}|${x.rol}`);
      const f = await p.contratos.fichaTercero(tid);
      if (f.tipo !== 'OK') continue;
      const r = rolPropuesto(x.rol, f.datos.roles);
      if (r) cola.push({ terceroId: tid, nombre: f.datos.tercero.nombre, rol: r, rowVersion: f.datos.tercero.row_version });
    }
    setPropuestasRol(cola);
  };
  const resolverRol = async (aceptar: boolean) => {
    const q = propuestasRol[0];
    if (!q) return;
    if (aceptar) {
      const k = `${q.terceroId}|${q.rol}`;
      if (!idRol.current[k]) idRol.current[k] = p.nuevoId();
      const r = await p.contratos.anadirRoles(q.terceroId, { intencion_id: idRol.current[k], row_version_esperada: q.rowVersion, anadir: [q.rol] });
      if (r.tipo !== 'OK') {
        setAvisoRol({ tipo: 'AVISO', texto: r.tipo === 'INDETERMINADO' ? 'No se ha podido confirmar el rol. El contrato ya está guardado.' : `${textoErrorContrato(r.codigo, r.mensaje, r.detalle)} El contrato ya está guardado.` });
        return setPropuestasRol((l) => l.slice(1));
      }
    }
    setAvisoRol(null);
    setPropuestasRol((l) => l.slice(1));
  };

  // ================================================================ vistas
  const titulo = paso === 'RESUMEN' ? 'Revisar contrato' : p.sucesor ? 'Cambio de inquilino' : 'Nuevo contrato';

  if (paso === 'HECHO' && guardado) {
    const q = propuestasRol[0];
    return (
      <View testID="contrato-hecho" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Contrato guardado" testIDCancelar="contrato-hecho-cerrar" onCancelar={() => p.onCerrar(guardado)} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Caja testID="contrato-hecho-aviso" aviso={{ tipo: 'OK', texto: `${guardado.nombre} · ${guardado.estado_documental === 'BORRADOR' ? 'borrador' : 'firmado'}` }} />
          {q ? (
            <Tarjeta testID="contrato-rol-propuesta">
              <View style={{ padding: espacio.m, gap: espacio.s }}>
                <Text testID="contrato-rol-propuesta-titulo" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{textoSinRol(q.nombre, q.rol)}</Text>
                <Text testID="contrato-rol-propuesta-texto" style={[tipo.footnote, { color: c.textSecondary }]}>{textoProponerRol(q.rol)}</Text>
                <BotonPrimario testID="contrato-rol-si" titulo="Sí, añadir el rol" onPress={() => void resolverRol(true)} />
                <BotonSecundario testID="contrato-rol-no" titulo="No" onPress={() => void resolverRol(false)} />
              </View>
            </Tarjeta>
          ) : null}
          {avisoRol ? <Caja testID="contrato-rol-aviso" aviso={avisoRol} /> : null}
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_RESUMEN_SIN_RENTA}</Text>
          <BotonPrimario testID="contrato-listo" titulo="Listo" onPress={() => p.onCerrar(guardado)} />
        </ScrollView>
      </View>
    );
  }
  if (paso === 'HECHO') return null;

  // B1b · selector de propiedad
  if (elegirPropiedad) {
    const lista = (p.propiedades ?? (vistaProp ? [vistaProp] : [])).filter((x) => x.enabled);
    return (
      <Hoja titulo="Propiedad" testID="contrato-selector-propiedad">
        <ScrollView style={{ maxHeight: 360 }}>
          {lista.map((x) => (
            <OpcionFila key={x.id} testID={`contrato-propiedad-${x.id}`} titulo={x.nombre} detalle={x.habitaciones ? `${x.habitaciones} habitaciones` : undefined} seleccionada={b.propiedadId === x.id}
              onPress={() => { setVistaProp(x); setB({ ...borradorContrato(x.id, x.nombre) }); setPrerrellenado(false); setElegirPropiedad(false); }} />
          ))}
        </ScrollView>
        <Text testID="contrato-propiedad-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_PROPIEDADES_AYUDA}</Text>
        <BotonSecundario testID="contrato-propiedad-cerrar" titulo="Cerrar" onPress={() => setElegirPropiedad(false)} />
      </Hoja>
    );
  }

  // B2b · ya está alquilada en esas fechas
  if (solape) {
    return (
      <View testID="contrato-solape" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo={titulo} testIDCancelar="contrato-solape-cancelar" onCancelar={() => p.onCerrar(null)} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <SolapeInfo testID="contrato-solape-info" titulo={TEXTO_YA_ALQUILADA_TITULO}
            intro={b.tipo ? textoCoincide({ tipo: b.tipo, habitacion: b.habitacion, inicio: b.fechaInicio }, { tipo: solapeTipo }) : ''}
            filas={solape} aviso={TEXTO_YA_ALQUILADA_AVISO} />
          <BotonPrimario testID="contrato-solape-borrador" titulo="Guardar como borrador"
            onPress={() => { setB((v) => ({ ...v, estado: 'BORRADOR' })); setSolape(null); void irAPaso('PERSONAS'); }} />
          <BotonSecundario testID="contrato-solape-revisar" titulo="Revisar fechas" onPress={() => setSolape(null)} />
        </ScrollView>
      </View>
    );
  }

  // B3b · agencia o administrador / rol de arrendador
  if (anadiendo && anadiendo.grupo !== 'INQUILINO' && anadiendo.grupo !== 'AVALISTA' && !anadiendo.selector) {
    const inter = anadiendo.grupo === 'INTERMEDIARIO';
    const roles: { rol: RolParticipante; titulo: string; detalle: string }[] = inter
      ? [{ rol: 'AGENCIA', titulo: 'Agencia', detalle: 'Ha intermediado el alquiler' }, { rol: 'ADMINISTRADOR', titulo: 'Administrador', detalle: 'Gestiona el contrato o la finca' }]
      : [{ rol: 'PROPIETARIO', titulo: 'Arrendador', detalle: 'Es titular o arrendador del contrato' }, { rol: 'GESTOR', titulo: 'Gestor', detalle: 'Gestiona el contrato en nombre del titular' }];
    return (
      <View testID="contrato-anadir" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo={inter ? 'Agencia o administrador' : 'Arrendador o gestor'} testIDCancelar="contrato-anadir-cancelar" onCancelar={() => setAnadiendo(null)} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
          <RotuloGrupo texto="¿Qué papel tiene?" />
          {roles.map((r) => (
            <OpcionFila key={r.rol} testID={`contrato-anadir-rol-${r.rol}`} titulo={r.titulo} detalle={r.detalle} seleccionada={anadiendo.rol === r.rol}
              onPress={() => setAnadiendo({ ...anadiendo, rol: r.rol })} />
          ))}
          {anadiendo.rol ? (
            <>
              <RotuloGrupo texto="¿Quién es?" />
              <CampoSelector testID="contrato-quien" etiqueta="¿Quién es?" valor={null} marcador="Buscar en tus terceros" onPress={() => setAnadiendo({ ...anadiendo, selector: true })} />
              {!inter && !b.personas.some((x) => x.terceroId === null && x.rol === anadiendo.rol) ? (
                <BotonSecundario testID="contrato-anadir-yo" titulo="Añadirme a mí" onPress={() => agregar(null, 'Tú', anadiendo.rol as RolParticipante)} />
              ) : null}
              {inter ? <Text testID="contrato-agencia-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_AGENCIA_AYUDA}</Text> : null}
            </>
          ) : null}
        </ScrollView>
      </View>
    );
  }

  const selectorPersona =
    anadiendo && anadiendo.selector && anadiendo.rol ? (
      <SelectorParticipante contratos={p.contratos} cliente={p.cliente} nuevoId={p.nuevoId}
        titulo={anadiendo.rol === 'INQUILINO' ? 'Inquilino' : NOMBRE_ROL_PARTICIPANTE[anadiendo.rol]}
        onElegir={(t: Tercero) => agregar(t.id, t.nombre, anadiendo.rol as RolParticipante)}
        onCerrar={() => setAnadiendo(anadiendo.grupo === 'INQUILINO' || anadiendo.grupo === 'AVALISTA' ? null : { ...anadiendo, selector: false })} />
    ) : null;

  const filasPersonas = (roles: RolParticipante[]) =>
    b.personas.filter((x) => roles.includes(x.rol)).map((x) => (
      <Tarjeta key={x.clave} testID={`contrato-persona-${x.clave}`}>
        <View style={{ padding: espacio.m, gap: espacio.s }}>
          <Text style={[tipo.body, { color: c.textPrimary }]}>{`${x.nombre} · ${NOMBRE_ROL_PARTICIPANTE[x.rol]}`}</Text>
          <View style={ef.chips}>
            <Chip testID={`contrato-persona-${x.clave}-principal`} etiqueta="Principal" seleccionado={x.principal} onPress={() => marcarPrincipal(x.clave)} />
            <BotonTexto testID={`contrato-persona-${x.clave}-quitar`} titulo="Quitar" critico onPress={() => quitarPersona(x.clave)} />
          </View>
        </View>
      </Tarjeta>
    ));

  const unidad = b.tipo === 'HABITACION' && b.habitacion !== null ? `Habitación ${b.habitacion}` : b.tipo ? NOMBRE_TIPO[b.tipo] : '';

  return (
    <View testID={`contrato-paso-${paso.toLowerCase()}`} style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={titulo} testIDCancelar={indice === 0 ? 'contrato-cancelar' : 'contrato-atras'} onCancelar={atras} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {indice < 5 && !p.sucesor ? <IndicadorPasos paso={paso} /> : null}
        {aviso ? <Caja testID="contrato-aviso" aviso={aviso} /> : null}

        {paso === 'QUE' ? (
          <>
            <Campo etiqueta="Propiedad">
              <CampoSelector testID="contrato-propiedad" etiqueta="Propiedad" valor={b.propiedadNombre || null} marcador="Elige la propiedad" onPress={() => setElegirPropiedad(true)} />
            </Campo>
            <Campo etiqueta="Tipo">
              <View style={ef.chips}>
                {(['VIVIENDA_COMPLETA', 'HABITACION', 'OTRO'] as const).map((t) => (
                  <Chip key={t} testID={`contrato-tipo-${t}`} etiqueta={NOMBRE_TIPO[t]} seleccionado={b.tipo === t} onPress={() => set({ tipo: t, habitacion: t === 'HABITACION' ? b.habitacion : null })} />
                ))}
              </View>
            </Campo>
            {b.tipo === 'HABITACION' ? (
              <Campo etiqueta="Habitación">
                {datos === null && b.propiedadId ? <EstadoDato estado="CARGANDO" /> : null}
                {ocupacion().map((o) => (
                  <OpcionFila key={o.habitacion} testID={`contrato-habitacion-${o.habitacion}`} titulo={`Habitación ${o.habitacion}`} detalle={textoOcupacionHabitacion(o)}
                    seleccionada={b.habitacion === o.habitacion} onPress={() => set({ habitacion: o.habitacion })} />
                ))}
                {ocupacion().length === 0 ? <Text testID="contrato-sin-habitaciones" style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_ACTUAL_SIN_HABITACIONES}</Text> : null}
              </Campo>
            ) : null}
            <Text testID="contrato-que-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_QUE_ALQUILAS}</Text>
          </>
        ) : null}

        {paso === 'FECHAS' ? (
          <>
            <Campo etiqueta="Inicio">
              <Fecha testID="contrato-inicio" etiqueta="Fecha de inicio, día barra mes barra año" iso={b.fechaInicio} hoyIso={hoyIso} onCambiar={(iso) => set({ fechaInicio: iso })} />
            </Campo>
            <Campo etiqueta="Fin previsto" opcional>
              <Fecha testID="contrato-fin-previsto" etiqueta="Fin previsto, día barra mes barra año" iso={b.fechaFinPrevista} hoyIso={hoyIso} onCambiar={(iso) => set({ fechaFinPrevista: iso })} />
            </Campo>
            <Campo etiqueta="¿Está firmado?">
              <OpcionFila testID="contrato-estado-FORMALIZADO" titulo="Sí, firmado" detalle="Queda «Firmado»" seleccionada={b.estado === 'FORMALIZADO'} onPress={() => set({ estado: 'FORMALIZADO' })} />
              <OpcionFila testID="contrato-estado-BORRADOR" titulo="Aún no" detalle="Queda como borrador; puedes completarlo después" seleccionada={b.estado === 'BORRADOR'} onPress={() => set({ estado: 'BORRADOR' })} />
            </Campo>
            {b.estado === 'BORRADOR' ? <Text testID="contrato-borrador-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_BORRADOR_AYUDA}</Text> : null}
          </>
        ) : null}

        {paso === 'PERSONAS' ? (
          <>
            <RotuloGrupo texto="Arrendadores" />
            {filasPersonas(['PROPIETARIO', 'GESTOR'])}
            <BotonTexto testID="contrato-anadir-arrendador" titulo="+ Añadir arrendador o gestor" onPress={() => abrirAnadir('ARRENDADOR')} />
            <RotuloGrupo texto="Inquilinos" />
            {filasPersonas(['INQUILINO'])}
            <BotonTexto testID="contrato-anadir-inquilino" titulo="+ Añadir inquilino" onPress={() => abrirAnadir('INQUILINO')} />
            <RotuloGrupo texto="Otras personas · opcional" />
            {filasPersonas(['AVALISTA', 'AGENCIA', 'ADMINISTRADOR'])}
            <BotonTexto testID="contrato-anadir-avalista" titulo="+ Añadir avalista" onPress={() => abrirAnadir('AVALISTA')} />
            <BotonTexto testID="contrato-anadir-agencia" titulo="+ Añadir agencia o administrador" onPress={() => abrirAnadir('INTERMEDIARIO')} />
            <Text testID="contrato-personas-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_PERSONAS_AYUDA}</Text>
          </>
        ) : null}

        {paso === 'REVISION' ? (
          <>
            {OPCIONES_CLAUSULA.map((o) => (
              <OpcionFila key={o.tipo} testID={`contrato-clausula-${o.tipo}`} titulo={o.titulo} detalle={o.detalle || undefined} seleccionada={b.clausula.eleccion === o.tipo}
                onPress={() => set({ clausula: { ...b.clausula, eleccion: o.tipo as TipoClausula | 'NO_SE' } })} />
            ))}
            {b.clausula.eleccion === 'PORCENTAJE_FIJO' ? (
              <Campo etiqueta="Porcentaje fijo">
                <CampoTexto testID="contrato-clausula-porcentaje" etiqueta="Porcentaje fijo" marcador="Ej.: 2" valor={b.clausula.porcentaje} onCambiar={(t) => set({ clausula: { ...b.clausula, porcentaje: t } })} />
              </Campo>
            ) : null}
            {b.clausula.eleccion === 'IPC' || b.clausula.eleccion === 'MANUAL' ? (
              <>
                <Campo etiqueta="Cada cuántos meses" opcional>
                  <CampoTexto testID="contrato-clausula-periodicidad" etiqueta="Cada cuántos meses" marcador="Ej.: 12" valor={b.clausula.periodicidad} onCambiar={(t) => set({ clausula: { ...b.clausula, periodicidad: t } })} />
                </Campo>
                <Campo etiqueta="Primera revisión" opcional>
                  <Fecha testID="contrato-clausula-primera" etiqueta="Primera revisión, día barra mes barra año" iso={b.clausula.primeraRevision} hoyIso={hoyIso} onCambiar={(iso) => set({ clausula: { ...b.clausula, primeraRevision: iso } })} />
                </Campo>
              </>
            ) : null}
            <Text testID="contrato-revision-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_REVISION_AYUDA}</Text>
          </>
        ) : null}

        {paso === 'SERVICIOS' ? (
          <>
            <RotuloGrupo texto="Servicios de la propiedad" />
            {servicios === null ? <EstadoDato estado="CARGANDO" /> : null}
            {servicios !== null && servicios.vigentes.length === 0 ? <Text testID="contrato-sin-servicios" style={[tipo.footnote, { color: c.textSecondary }]}>Esta propiedad todavía no tiene servicios.</Text> : null}
            {(servicios?.vigentes ?? []).map((s) => {
              const t = b.servicios[s.servicio_id] ?? { modo: null, porcentaje: '' };
              return (
                <Tarjeta key={s.servicio_id} testID={`contrato-servicio-${s.servicio_id}`}>
                  <View style={{ padding: espacio.m, gap: espacio.s }}>
                    <BotonTexto testID={`contrato-servicio-${s.servicio_id}-abrir`} titulo={`${s.nombre} · ${textoTratamiento(t.modo, t.porcentaje)}`}
                      onPress={() => setAbierto(abierto === s.servicio_id ? null : s.servicio_id)} />
                    {abierto === s.servicio_id ? (
                      <>
                        {OPCIONES_TRATAMIENTO.map((o) => (
                          <OpcionFila key={o.modo} testID={`contrato-servicio-${s.servicio_id}-${o.modo}`} titulo={o.titulo} detalle={o.detalle} seleccionada={t.modo === o.modo}
                            onPress={() => setTrat(s.servicio_id, { modo: o.modo })} />
                        ))}
                        {t.modo === 'REPERCUTIDO_FIJO' ? (
                          <CampoTexto testID={`contrato-servicio-${s.servicio_id}-porcentaje`} etiqueta={`Porcentaje de ${s.nombre}`} marcador="% (mayor que 0)" valor={t.porcentaje}
                            onCambiar={(x) => setTrat(s.servicio_id, { porcentaje: x })} />
                        ) : null}
                      </>
                    ) : null}
                  </View>
                </Tarjeta>
              );
            })}
            <Text testID="contrato-servicios-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SERVICIOS_AYUDA}</Text>
          </>
        ) : null}

        {paso === 'RESUMEN' ? (
          <>
            <Campo etiqueta="Nombre del contrato">
              <CampoTexto testID="contrato-nombre" etiqueta="Nombre del contrato" maximo={160} valor={b.nombre} onCambiar={(t) => set({ nombre: t, nombreEditado: true })} />
            </Campo>
            {!b.nombreEditado ? <Text testID="contrato-nombre-propuesto" style={[tipo.footnote, { color: c.textSecondary }]}>Propuesto. Año de inicio · habitación · iniciales del inquilino principal. Puedes cambiarlo.</Text> : null}
            <Tarjeta testID="contrato-resumen">
              <View style={{ padding: espacio.m, gap: espacio.xs }}>
                <FilaInfo testID="contrato-res-unidad" etiqueta={unidad} valor={b.propiedadNombre} />
                <FilaInfo testID="contrato-res-estado" etiqueta={b.estado === 'FORMALIZADO' ? 'Firmado' : 'Borrador'} valor={`${esFechaIso(b.fechaInicio) ? diaMesAnioIso(b.fechaInicio) : ''}${b.fechaFinPrevista ? ` → ${diaMesAnioIso(b.fechaFinPrevista)}` : ''}`} />
                {textoPersonasResumen(b.personas, ['PROPIETARIO', 'GESTOR']) ? <FilaInfo testID="contrato-res-arrendadores" etiqueta="Arrendadores" valor={textoPersonasResumen(b.personas, ['PROPIETARIO', 'GESTOR'])} /> : null}
                {textoPersonasResumen(b.personas, 'INQUILINO') ? <FilaInfo testID="contrato-res-inquilinos" etiqueta="Inquilinos" valor={textoPersonasResumen(b.personas, 'INQUILINO')} /> : null}
                {textoPersonasResumen(b.personas, 'AGENCIA') ? <FilaInfo testID="contrato-res-agencia" etiqueta="Agencia" valor={textoPersonasResumen(b.personas, 'AGENCIA')} /> : null}
                {textoPersonasResumen(b.personas, 'ADMINISTRADOR') ? <FilaInfo testID="contrato-res-administrador" etiqueta="Administrador" valor={textoPersonasResumen(b.personas, 'ADMINISTRADOR')} /> : null}
                <FilaInfo testID="contrato-res-revision" etiqueta="Revisión" valor={textoClausulaResumen(b.clausula)} />
                <FilaInfo testID="contrato-res-servicios" etiqueta="Servicios" valor={String(tratamientosWire(b).length)} />
              </View>
            </Tarjeta>
            <Text testID="contrato-res-sin-renta" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_RESUMEN_SIN_RENTA}</Text>
            <Text testID="contrato-res-una-operacion" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_UNA_OPERACION}</Text>
          </>
        ) : null}

        {faltas.length > 0 && paso !== 'QUE' ? <Text testID="contrato-faltas" style={[tipo.footnote, { color: c.warningText }]}>{faltas[0]}</Text> : null}
        {paso === 'RESUMEN' ? (
          <BotonPrimario testID="contrato-guardar" titulo="Guardar contrato" cargando={ocupado} onPress={() => void guardar()} />
        ) : (
          <BotonPrimario testID="contrato-continuar" titulo="Continuar" deshabilitado={faltas.length > 0} ayuda={faltas[0]} onPress={() => void continuar()} />
        )}
      </ScrollView>
      {selectorPersona}
    </View>
  );
}
