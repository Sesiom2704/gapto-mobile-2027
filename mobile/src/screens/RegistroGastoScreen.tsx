// ============================================================
// GAPTO MOBILE 2027
// Fichero: RegistroGastoScreen.tsx
// Ruta: mobile/src/screens/RegistroGastoScreen.tsx
// Descripción: FORM-VS01 — implementación funcional PROVISIONAL sobre Design System F09 (no es mockup aprobado). Tarea inmersiva CREATE: cabecera de tarea, sin barra inferior (F09 BLOQUE A). Pantalla corta: importe, concepto, ¿cuenta para presupuesto? (Sí/No sin preselección), «Solo mío» explícito, cuenta de pago, fecha visible. Cada valor muestra su origen: decisión, inferido visible o pendiente (mandato §8).
// v0.2.0 (F05-D003 REG-01): fecha común gasto/pago editable (Hoy · Ayer · Otra, ≤ hoy) con propuesta recargada por fecha; financiación visible y sellada: «Financiado por ti · cuenta 100 % tuya» (aceptación implícita, con vía «No es así») o «Financiación no determinada»; un rechazo por propuesta obsoleta recarga la propuesta.
// v0.3.0 (F05 — VS-01 · Alineación visual, A2 — aplicación prospectiva de REG-SPEC-01 SPEC-08, no corrección retrospectiva de VS-01): «Registrar gasto» permanece desactivado mientras falte una decisión bloqueante de REG-01 (importe válido, concepto, presupuestable, cuenta de pago —incluido «Cargando…»— o fecha válida ≤ hoy) y la pantalla indica, de forma visible y accesible, qué falta sin necesidad de pulsar. Los errores de formato de importe y fecha se muestran al escribir. La atribución sin respuesta no bloquea. Payload, API y validación del servidor sin cambios.
// v0.4.0 (F05-01 S6-WIRE+UI (este mandato); F09 §12.97.1–12.97.3, lámina REG-CAT v1.0 R01–R10): campo «Categoría» inmediatamente después de «Concepto» con tres estados visibles (Pendiente «Elige categoría» · Categoría con icono, nombre y ruta · «Sin categoría»), sin preselección; mientras esté Pendiente «Registrar gasto» sigue desactivado y `faltan` lo nombra (misma `validar` del sellado). El árbol se carga al abrir el formulario y el selector jerárquico filtra con `visibleEnRegistro`; un error de carga nunca selecciona «Sin categoría» (AJ-09). Sección «Datos de <categoría>» con las magnitudes habilitadas: obligatorias sin valor por defecto y con unidad, opcionales «(opcional)», teclado decimal, coma o punto. Al cambiar de categoría se conservan las magnitudes comunes y se confirma antes de descartar valores informados (también al elegir «Sin categoría»). `presupuestable_default` NO rellena «¿Cuenta para el presupuesto?». Rechazo definitivo de categoría o magnitudes tras confirmar: la intención sellada no se reenvía; se conservan las demás decisiones, se recarga el árbol, la categoría queda marcada como no válida con texto y se pide otra; la nueva intención tendrá UUID nuevo.
// v0.5.0 (F05-02 B2; F05-D026 §41.3/§41.4, E1/E2/E3; F05-D027 §42.7; lámina SET-PREF / REG-PREF v0.1 R01–R07): propuesta de preferencias por campo. Tras cargar las cuentas, y en cada cambio de categoría o de fecha, se pide GET /v1/preferencias/propuesta (categoría o «Sin categoría»; con categoría pendiente, el contexto «Sin categoría») y se aplica SOLO a los campos no tocados, con su origen visible («Propuesta: tu preferencia para <categoría>.» / «… general.» / «Propuesta: es tu única cuenta disponible.»); un campo tocado muestra «Elegida por ti.» y no se recalcula (D-PREF-03). Se ELIMINA el fallback de cuenta única del cliente (AJ-B1-09): la única fuente de la propuesta de cuenta es el resolver, y nunca se preselecciona una cuenta fuera de la lista (AJ-B1-11). `presupuestable` se preselecciona solo con propuesta (E1). El sellado no cambia: el reintento no vuelve a pedir la propuesta y no hay sondeo. Pantalla de éxito: «Guardar como preferencia» (GuardarPreferencia) solo con categoría y si hay algo que recordar (D-PREF-05/06).
// v0.6.0 (F05-03/F05-04 J2 §2.2–§2.4; F05 §46.3 A1–A9, §45.3; láminas REG-DYN G01–G03/I01/T02/N01 y REG-PLT R01–R06): el formulario sirve a Gasto e Ingreso cobrado (`tipo`). Cabecera «Cancelar · Nuevo gasto | Nuevo ingreso · Tipo»: el cambio de tipo solo antes del primer envío, conserva importe y fecha y quita con aviso lo que no encaja (T02); «Entre cuentas» lo resuelve la raíz. Tercero opcional («Tercero» / «De») con alta mínima y duplicados; «Más detalles» con contexto (alta «Crear y usar») y, en ingresos, nota. Selector de categorías por tipo (A12). «No lo sé» en magnitudes obligatorias (A9). Plantilla: chip «Plantilla: <nombre> ×» con «Quitar», origen por campo («De tu plantilla …»), campos tocados nunca se pisan y avisos de lo que no aplica. Ingresos: cuentas elegibles para cobrar («Cobrado en»), sin financiación. Con tercero, plantilla o en ingresos la propuesta es la del registro por tipo (GET /v1/registro/propuesta); el gasto sin ellos conserva la de F05-02. FECHA_FUTURA con su mensaje. Éxito: «Guardar como preferencia» para el tercero O la categoría y «Guardar como plantilla…».
// Versión: 0.6.0
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaPago } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato, Segmentado, Velo } from '../components/Basicos';
import { FormularioContexto, SelectorContexto } from '../components/Contextos';
import { GuardarPlantilla } from '../components/GuardarPlantilla';
import { GuardarPreferencia } from '../components/GuardarPreferencia';
import { HojaTipos } from '../components/HojaTipos';
import { SelectorTercero } from '../components/SelectorTercero';
import { BotonSecundario, CargaArbol, IconoCategoriaVista, SelectorCategorias } from '../components/SelectorCategorias';
import {
  CategoriaNodo,
  MagnitudCategoria,
  construirArbol,
  elegible,
  elegibleParaGasto,
  magnitudesPedibles,
  motivoNoSeleccionable,
  rutaTexto,
  visibleEnRegistro,
} from '../domain/categoria';
import { ayer, ddmmaaaaAIso, fechaCortaIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import { Borrador, borradorInicial, Errores, esDesconocida, esFechaIso, SeleccionCategoria, validar } from '../domain/intencion';
import { conservarMagnitudes, descartadas } from '../domain/magnitud';
import type { IndicePreferencias, PropuestaVista } from '../domain/preferencias';
import {
  aplicarPropuesta,
  datosRecordables,
  datosRecordablesTipo,
  faltanPreferencias,
  faltanPreferenciasTipo,
  indexar,
  propuestaAplicable,
  propuestaAplicableTipo,
  SIN_PROPUESTA,
  TEXTO_ELEGIDA,
  textoOrigen,
  valoresPropuestos,
} from '../domain/preferencias';
import {
  aplicarCamposPlantilla,
  avisoCambioDeTipo,
  avisosPlantilla,
  borradorTrasCambioDeTipo,
  cambioDeTipo,
  categoriaDePlantilla,
  notaCanonica,
  quitarPlantilla,
  TipoRegistro,
  tituloExito,
  tituloRegistro,
  TITULO_TAREA,
} from '../domain/registro';
import { useEnvioGasto } from '../state/useEnvioGasto';
import { useTema } from '../theme/tema';
import { espacio, importe, radio, TACTIL_MIN, tipo } from '../theme/tokens';

type Cuentas = { fase: 'CARGANDO' } | { fase: 'OK'; lista: CuentaPago[] } | { fase: 'ERROR' };

/** Mensaje del rechazo FECHA_FUTURA (F05-D032 C6: el «hoy» es el del owner en el servidor). */
export const TEXTO_FECHA_FUTURA = 'La fecha es posterior a hoy. Elige hoy o una fecha anterior.';
/** «No lo sé» (lámina G02): «Se registrará sin litros. Podrás añadirlos después.» */
export const textoNoLoSe = (nombre: string) => `Se registrará sin ${nombre.toLowerCase()}. Podrás añadirlo después.`;

/** Rechazos definitivos del servidor que invalidan la categoría elegida (F05 §28.2; F09 §12.97.1). */
export const RECHAZOS_CATEGORIA = new Set([
  'CATEGORIA_NO_ELEGIBLE',
  'CATEGORIA_MAGNITUD_NO_DISPONIBLE',
  'MAGNITUD_NO_ADMITIDA',
  'MAGNITUD_OBLIGATORIA_AUSENTE',
  'MAGNITUD_VALOR_NO_VALIDO',
]);

/** Cambio de categoría pendiente de confirmar porque descartaría valores informados (C07). */
type CambioPendiente = { destino: SeleccionCategoria; perdidas: MagnitudCategoria[]; etiqueta: string };

export function RegistroGastoScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (registrado: boolean) => void;
  /** F05-04: tipo con el que se abre (GASTO por defecto: VS-01). */
  tipo?: 'GASTO' | 'INGRESO';
  /** F05-04: plantilla con la que se abre (acceso de Inicio). */
  plantilla?: { id: string; nombre: string } | null;
  /** F05-04: importe y fecha que se conservan al venir de otro tipo, y su aviso T02. */
  inicial?: { importeTexto: string; fechaHecho: string; aviso: string | null } | null;
  /** F05-04: cambio a «Entre cuentas» (otra pantalla) antes del primer envío. */
  onCambiarTipo?: (hacia: TipoRegistro, conservar: { importeTexto: string; fechaHecho: string; aviso: string }) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoy = useMemo(() => p.ahora(), [p.ahora]);
  const hoyIso = isoLocal(hoy);
  const ayerIso = isoLocal(ayer(hoy));
  const [b, setB] = useState<Borrador>(() => borradorInicial(hoyIso));
  const [tipoReg, setTipoReg] = useState<'GASTO' | 'INGRESO'>(p.tipo ?? 'GASTO');
  const tipoRef = useRef(tipoReg);
  tipoRef.current = tipoReg;
  const bRef = useRef(b);
  bRef.current = b;
  const [hojaTipos, setHojaTipos] = useState(false);
  const [avisos, setAvisos] = useState<string[]>(p.inicial?.aviso ? [p.inicial.aviso] : []);
  const [selectorTercero, setSelectorTercero] = useState(false);
  const [selectorContexto, setSelectorContexto] = useState<'LISTA' | 'NUEVO' | null>(null);
  const [masDetalles, setMasDetalles] = useState(false);
  const [nota, setNota] = useState('');
  const [guardarPlantilla, setGuardarPlantilla] = useState(false);
  /** Primer envío hecho: desde entonces el tipo no se puede cambiar. */
  const [enviado, setEnviado] = useState(false);
  /** Plantilla cuyos campos aún no se han aplicado (se aplican con la primera propuesta). */
  const plantillaPendiente = useRef<{ id: string; nombre: string } | null>(p.plantilla ?? null);  const [errores, setErrores] = useState<Errores>({});
  const [cuentas, setCuentas] = useState<Cuentas>({ fase: 'CARGANDO' });
  const [confirmarSalida, setConfirmarSalida] = useState(false);
  const [otraFecha, setOtraFecha] = useState<string | null>(null); // texto dd/mm/aaaa en edición
  const notaRef = useRef<string | null>(null);
  notaRef.current = notaCanonica(nota);
  const { estado, enviar, reintentar, volverAEditar } = useEnvioGasto(p.cliente, p.nuevoId, tipoReg, () => notaRef.current);
  const conceptoRef = useRef<TextInput>(null);
  const peticion = useRef(0);
  const [arbol, setArbol] = useState<CargaArbol>({ fase: 'CARGANDO' });
  const [selectorAbierto, setSelectorAbierto] = useState(false);
  const [cambioPendiente, setCambioPendiente] = useState<CambioPendiente | null>(null);
  /** Categoría que el servidor rechazó tras confirmar (se pide otra). */
  const [categoriaInvalida, setCategoriaInvalida] = useState<{ nombre: string; codigo: string } | null>(null);

  useEffect(() => {
    if (p.inicial) setB((x) => ({ ...x, importeTexto: p.inicial!.importeTexto, fechaHecho: p.inicial!.fechaHecho, fechaOrigen: p.inicial!.fechaHecho === hoyIso ? 'INFERIDO' : 'USUARIO' }));
  }, []);

  // Árbol de categorías: se carga al abrir el formulario. Reintentar nunca crea intención.
  // F05-04: árbol vigente y su carga en curso, legibles desde la propuesta (la plantilla espera al árbol).
  const arbolActual = useRef<CargaArbol>({ fase: 'CARGANDO' });
  const arbolCarga = useRef<Promise<void> | null>(null);
  const cargarArbol = useCallback(async () => {
    setArbol({ fase: 'CARGANDO' });
    let fin: () => void = () => undefined;
    arbolCarga.current = new Promise<void>((resolver) => (fin = resolver));
    const r = await p.cliente.arbolCategorias();
    arbolActual.current = r.tipo === 'OK' ? { fase: 'OK', arbol: construirArbol(r.datos.categorias) } : { fase: 'ERROR' };
    fin();
    if (r.tipo !== 'OK') return setArbol({ fase: 'ERROR' });
    setArbol({ fase: 'OK', arbol: construirArbol(r.datos.categorias) });
  }, [p.cliente]);
  useEffect(() => {
    void cargarArbol();
  }, [cargarArbol]);

  // F05-02: preferencias conocidas (para explicar el origen), última propuesta vista
  // (para «Guardar como preferencia») y contexto vigente de la propuesta.
  const prefs = useRef<IndicePreferencias | null>(null);
  const vista = useRef<PropuestaVista | null>(null);
  const peticionPropuesta = useRef(0);
  const categoriaActual = useRef<string | null>(null);
  categoriaActual.current = b.categoria.estado === 'CATEGORIA' ? b.categoria.id : null;
  // Tras sellar (enviando, indeterminado o confirmado) ninguna propuesta toca el borrador.
  const editable = useRef(true);
  editable.current = estado.fase === 'EDITANDO' || estado.fase === 'RECHAZADO';

  // Propuesta por campo del resolver: tras cargar las cuentas y en cada cambio de categoría
  // o de fecha. Nunca por sondeo ni en un reintento (la intención sellada no se recalcula).
  const pedirPropuesta = async (fecha: string, categoriaId: string | null, lista: CuentaPago[]) => {
    const n = ++peticionPropuesta.current;
    const caducada = () => n !== peticionPropuesta.current || !editable.current;
    const actual = bRef.current;
    const plantilla = plantillaPendiente.current ?? actual.plantilla ?? null;
    if (tipoRef.current !== 'GASTO' || plantilla || actual.terceroId) {
      // F05-04: propuesta del registro por tipo (plantilla → preferencias → default).
      const r2 = await p.cliente.propuestaRegistro({
        tipo: tipoRef.current,
        fecha,
        plantillaId: plantilla?.id ?? null,
        ...(categoriaId ? { categoriaId } : { sinCategoria: true }),
        ...(actual.terceroId ? { terceroId: actual.terceroId } : { sinTercero: true }),
      });
      if (caducada()) return;
      if (r2.tipo !== 'OK') {
        vista.current = null;
        return setB((x) => aplicarPropuesta(x, SIN_PROPUESTA, lista));
      }
      vista.current = {
        fecha,
        categoriaId,
        terceroId: actual.terceroId ?? null,
        plantillaId: plantilla?.id ?? null,
        valores: { cuenta: r2.datos.campos.cuenta?.valor ?? null, presupuestable: r2.datos.campos.presupuestable?.valor ?? null },
      };
      if (faltanPreferenciasTipo(r2.datos, prefs.current)) {
        const l = await p.cliente.listarPreferencias();
        if (caducada()) return;
        if (l.tipo === 'OK') prefs.current = indexar(l.datos.preferencias);
      }
      const ap2 = propuestaAplicableTipo(r2.datos, prefs.current, lista);
      const pendiente = plantillaPendiente.current;
      if (pendiente) {
        // La plantilla necesita el árbol (categoría) y los nombres de terceros y contextos.
        await Promise.all([arbolCarga.current, maestrosCarga.current]);
        if (caducada()) return;
      }
      plantillaPendiente.current = null;
      let nuevos: string[] = [];
      setB((x) => {
        let y = x;
        if (pendiente) {
          const r3 = aplicarCamposPlantilla(x, pendiente, r2.datos.campos, {
            arbol: arbolActual.current.fase === 'OK' ? arbolActual.current.arbol : null,
            tipo: tipoRef.current,
            tercero: (id) => (terceros.current.get(id) ?? null),
            contexto: (id) => (contextos.current.get(id) ?? null),
          });
          y = r3.b;
          nuevos = r3.avisos;
        }
        return aplicarPropuesta(y, ap2, lista);
      });
      if (pendiente) setAvisos((a) => [...a, ...nuevos, ...avisosPlantilla(r2.datos.avisos)]);
      return;
    }
    const r = await p.cliente.propuestaPreferencias(fecha, categoriaId);
    if (caducada()) return;
    let ap = SIN_PROPUESTA;
    if (r.tipo === 'OK') {
      vista.current = { fecha, categoriaId, valores: valoresPropuestos(r.datos) };
      if (faltanPreferencias(r.datos, prefs.current)) {
        const l = await p.cliente.listarPreferencias();
        if (caducada()) return;
        if (l.tipo === 'OK') prefs.current = indexar(l.datos.preferencias);
      }
      ap = propuestaAplicable(r.datos, prefs.current, lista);
    } else {
      vista.current = null; // sin propuesta (incluida una categoría no elegible): nada que aplicar
    }
    setB((x) => aplicarPropuesta(x, ap, lista));
  };

  // Cuentas y propuesta de financiación SIEMPRE para la fecha elegida (§16.4):
  // la propuesta se evalúa en la fecha del pago.
  const cargarCuentas = async (fecha: string) => {
    const n = ++peticion.current;
    ++peticionPropuesta.current; // una propuesta en vuelo de otra fecha ya no se aplica
    setCuentas({ fase: 'CARGANDO' });
    setB((x) => ({ ...x, propuesta: null }));
    const r =
      tipoRef.current === 'INGRESO'
        ? await cuentasDeIngreso(fecha) // «Cobrado en»: elegibles para cobrar (servidor)
        : await p.cliente.cuentasPago(fecha);
    if (n !== peticion.current) return; // respuesta de una fecha anterior: se ignora
    if (r.tipo !== 'OK') return setCuentas({ fase: 'ERROR' });
    const lista = r.datos.cuentas;
    setCuentas({ fase: 'OK', lista });
    setB((x) => {
      const sel = lista.find((c2) => c2.cuenta_id === x.cuentaId);
      // La cuenta elegida por el usuario se conserva si sigue en la lista (lo explícito gana).
      if (sel && x.cuentaOrigen === 'USUARIO') return { ...x, propuesta: sel.propuesta_financiacion };
      // Sin fallback del cliente (AJ-B1-09): la propuesta de cuenta solo la da el resolver.
      return { ...x, cuentaId: null, cuentaOrigen: 'PENDIENTE', cuentaPropuesta: null, propuesta: null, propuestaRechazada: false };
    });
    void pedirPropuesta(fecha, categoriaActual.current, lista);
  };
  useEffect(() => {
    if (esFechaIso(b.fechaHecho) && b.fechaHecho <= hoyIso) void cargarCuentas(b.fechaHecho);
  }, [b.fechaHecho]);

  // F05-04: nombres de terceros y contextos (para los valores que pone la plantilla).
  const terceros = useRef<Map<string, string>>(new Map());
  const contextos = useRef<Map<string, string>>(new Map());
  const maestrosCarga = useRef<Promise<void> | null>(null);
  if (p.plantilla && maestrosCarga.current === null) {
    maestrosCarga.current = (async () => {
      const [t, x] = await Promise.all([p.cliente.listarTerceros(), p.cliente.listarContextos()]);
      if (t.tipo === 'OK') terceros.current = new Map(t.datos.terceros.filter((y) => y.enabled).map((y) => [y.id, y.nombre]));
      if (x.tipo === 'OK') contextos.current = new Map(x.datos.contextos.filter((y) => y.enabled).map((y) => [y.id, y.nombre]));
    })();
  }

  /** Cuentas para cobrar en el formato de la lista del formulario (sin financiación: no aplica al ingreso). */
  const cuentasDeIngreso = async (fecha: string) => {
    const r = await p.cliente.cuentasElegibles('INGRESO', fecha);
    if (r.tipo !== 'OK') return r;
    return { tipo: 'OK' as const, datos: { cuentas: r.datos.cuentas.map((x): CuentaPago => ({ ...x, propuesta_financiacion: 'NO_DETERMINADA' })) } };
  };

  // F05-04: tercero o tipo cambiados → se vuelve a resolver la propuesta (sin pisar lo tocado).
  const reResolver = () => {
    if (!bloqueado && cuentas.fase === 'OK') void pedirPropuesta(bRef.current.fechaHecho, categoriaActual.current, cuentas.lista);
  };

  // Propuesta obsoleta: la cuenta cambió; se recarga para mostrar la realidad actual.
  useEffect(() => {
    if (estado.fase === 'RECHAZADO' && estado.codigo === 'PROPUESTA_FINANCIACION_OBSOLETA') void cargarCuentas(b.fechaHecho);
    // Categoría o magnitudes rechazadas tras confirmar: la intención sellada ya se liberó
    // (useEnvioGasto); se conservan las demás decisiones, se recarga el árbol y se pide otra.
    if (estado.fase === 'RECHAZADO' && RECHAZOS_CATEGORIA.has(estado.codigo) && b.categoria.estado === 'CATEGORIA') {
      setCategoriaInvalida({ nombre: b.categoria.nombre, codigo: estado.codigo });
      setB((x) => ({ ...x, categoria: { estado: 'PENDIENTE' } }));
      void cargarArbol();
    }
  }, [estado]);

  const bloqueado = estado.fase === 'ENVIANDO' || estado.fase === 'INDETERMINADO' || estado.fase === 'CONFIRMADO';
  const esIngreso = tipoReg === 'INGRESO';
  // Defaults inferidos (fecha, propuestas de cuenta y de presupuesto) no cuentan como modificación (F09 BLOQUE A; E2).
  const modificado =
    b.importeTexto.trim() !== '' || b.concepto.trim() !== '' || b.presupuestableOrigen === 'USUARIO' || b.soloMio || b.cuentaOrigen === 'USUARIO' || b.fechaOrigen === 'USUARIO' || b.propuestaRechazada ||
    b.categoria.estado !== 'PENDIENTE' || Object.values(b.magnitudesTexto).some((v) => v.trim() !== '') ||
    b.terceroOrigen === 'USUARIO' || b.contextoOrigen === 'USUARIO' || nota.trim() !== '';
  const cuentaSel = cuentas.fase === 'OK' ? cuentas.lista.find((x) => x.cuenta_id === b.cuentaId) : undefined;
  const nombreCategoria = b.categoria.estado === 'CATEGORIA' ? b.categoria.nombre : null;

  // SPEC-08: decisiones bloqueantes de REG-01 que faltan, calculadas en cada render
  // con la MISMA validación que protege el sellado (sin duplicar reglas).
  const pendientes = validar(b, hoyIso, tipoReg);
  const listo = Object.keys(pendientes).length === 0;
  const faltan = textoFaltan(pendientes, b, tipoReg);
  // Errores de formato visibles al escribir (no requieren pulsar un botón desactivado).
  const vivos: Errores = {};
  if (b.importeTexto.trim() !== '' && pendientes.importe) vivos.importe = pendientes.importe;
  if (pendientes.fecha && (otraFecha === null || otraFecha.length >= 10)) vivos.fecha = pendientes.fecha;
  // Magnitudes: el formato inválido se ve al escribir; la obligatoria vacía solo en `faltan`.
  const magnitudesVivas: Record<string, string> = {};
  for (const [id, msg] of Object.entries(pendientes.magnitudes ?? {})) if ((b.magnitudesTexto[id] ?? '').trim() !== '') magnitudesVivas[id] = msg;
  const visibles: Errores = { ...errores, ...vivos, magnitudes: { ...(errores.magnitudes ?? {}), ...magnitudesVivas } };

  const cambiar = (parche: Partial<Borrador>) => {
    if (bloqueado) return;
    if (estado.fase === 'RECHAZADO') volverAEditar();
    setB((x) => ({ ...x, ...parche }));
    setErrores((e) => {
      const n = { ...e };
      for (const k of Object.keys(parche)) {
        if (k === 'importeTexto') delete n.importe;
        if (k === 'cuentaId') delete n.cuenta;
        if (k === 'fechaHecho') delete n.fecha;
        if (k === 'magnitudesTexto' || k === 'categoria') delete n.magnitudes;
        if (k in n) delete (n as any)[k];
      }
      return n;
    });
  };

  // ------------------------------------------------------------ categoría
  const actuales: MagnitudCategoria[] = b.categoria.estado === 'CATEGORIA' ? b.categoria.magnitudes : [];

  const aplicarCategoria = (destino: SeleccionCategoria) => {
    const nuevas = destino.estado === 'CATEGORIA' ? destino.magnitudes : [];
    setCategoriaInvalida(null);
    setCambioPendiente(null);
    setSelectorAbierto(false);
    cambiar({ categoria: destino, magnitudesTexto: conservarMagnitudes(b.magnitudesTexto, nuevas) });
    // Cambio de categoría: se vuelve a resolver sin pisar los campos tocados (R03).
    categoriaActual.current = destino.estado === 'CATEGORIA' ? destino.id : null;
    if (!bloqueado && cuentas.fase === 'OK') void pedirPropuesta(b.fechaHecho, categoriaActual.current, cuentas.lista);
  };

  /** Pide confirmación si el cambio descartaría valores informados (C07; lámina R07). */
  const proponerCategoria = (destino: SeleccionCategoria) => {
    if (bloqueado) return;
    const nuevas = destino.estado === 'CATEGORIA' ? destino.magnitudes : null;
    const perdidas = descartadas(b.magnitudesTexto, actuales, nuevas);
    if (perdidas.length === 0) return aplicarCategoria(destino);
    setSelectorAbierto(false);
    setCambioPendiente({ destino, perdidas, etiqueta: destino.estado === 'CATEGORIA' ? destino.nombre : 'Sin categoría' });
  };

  const elegirNodo = (n: CategoriaNodo) => {
    if (arbol.fase !== 'OK') return;
    proponerCategoria({
      estado: 'CATEGORIA',
      id: n.id,
      nombre: n.nombre,
      ruta: rutaTexto(arbol.arbol, n.id),
      icon_key: n.icon_key,
      magnitudes: magnitudesPedibles(n),
    });
  };

  const onRegistrar = async () => {
    editable.current = false; // desde el sellado, ninguna propuesta en vuelo toca el borrador
    if (Object.keys(validar(b, hoyIso, tipoReg)).length === 0) setEnviado(true); // primer envío: el tipo queda fijado
    const e = await enviar(b, hoyIso);
    setErrores(e);
  };

  // ------------------------------------------------------------ tipo (T02), plantilla, tercero y contexto
  const cambiarTipo = (hacia: TipoRegistro) => {
    setHojaTipos(false);
    if (hacia === tipoReg || enviado || bloqueado) return;
    const nodoActual = b.categoria.estado === 'CATEGORIA' && arbol.fase === 'OK' ? arbol.arbol.porId.get(b.categoria.id) : undefined;
    const cuenta = cuentaSel ? { nombre: cuentaSel.nombre, admitida: false } : null; // otra operación: la cuenta se vuelve a elegir
    const quitados = cambioDeTipo(tipoReg, hacia, {
      categoria: nodoActual ? { nombre: nodoActual.nombre, ambito: nodoActual.ambito } : null,
      cuenta,
      tercero: b.terceroNombre ?? null,
      contexto: b.contextoNombre ?? null,
      presupuestable: b.presupuestableOrigen === 'USUARIO' ? b.presupuestable : null,
      soloMio: b.soloMio,
    });
    const aviso = avisoCambioDeTipo(tipoReg, hacia, quitados);
    if (hacia === 'TRANSFERENCIA') return p.onCambiarTipo?.('TRANSFERENCIA', { importeTexto: b.importeTexto, fechaHecho: b.fechaHecho, aviso });
    const categoriaAdmitida = !!nodoActual && elegible(nodoActual, hacia);
    tipoRef.current = hacia;
    setTipoReg(hacia);
    setAvisos([aviso]);
    plantillaPendiente.current = null;
    setB((x) => borradorTrasCambioDeTipo(x, false, categoriaAdmitida));
    if (esFechaIso(b.fechaHecho)) void cargarCuentas(b.fechaHecho);
  };

  const quitarPlantillaAplicada = () => {
    if (bloqueado) return;
    setB((x) => quitarPlantilla(x));
    setAvisos([]);
    setTimeout(reResolver, 0);
  };

  const elegirTercero = (t: { id: string; nombre: string } | null) => {
    setSelectorTercero(false);
    cambiar(t ? { terceroId: t.id, terceroNombre: t.nombre, terceroOrigen: 'USUARIO' } : { terceroId: null, terceroNombre: null, terceroOrigen: 'USUARIO' });
    setTimeout(reResolver, 0);
  };

  const elegirContexto = (x: { id: string; nombre: string } | null) => {
    setSelectorContexto(null);
    cambiar(x ? { contextoId: x.id, contextoNombre: x.nombre, contextoOrigen: 'USUARIO' } : { contextoId: null, contextoNombre: null, contextoOrigen: 'USUARIO' });
  };

  const alternarNoLoSe = (m: MagnitudCategoria) => {
    const actual = b.desconocidas ?? [];
    const marcada = actual.includes(m.magnitud_id);
    cambiar({
      desconocidas: marcada ? actual.filter((x) => x !== m.magnitud_id) : [...actual, m.magnitud_id],
      magnitudesTexto: marcada ? b.magnitudesTexto : { ...b.magnitudesTexto, [m.magnitud_id]: '' },
    });
  };

  /** Texto de origen visible con el contexto del registro por tipo. */
  const origen = (o: Parameters<typeof textoOrigen>[0]) =>
    textoOrigen(o, nombreCategoria, { tercero: b.terceroNombre ?? null, plantilla: b.plantilla?.nombre ?? null, tipo: tipoReg });

  const cancelar = () => {
    if (estado.fase === 'CONFIRMADO') return p.onCerrar(true);
    if (modificado || estado.fase === 'INDETERMINADO') return setConfirmarSalida(true);
    p.onCerrar(false);
  };

  if (estado.fase === 'CONFIRMADO') {
    const r = estado.resultado;
    // «Guardar como preferencia» (R05): solo con categoría y si algo difiere de lo propuesto.
    // F05-04: con tercero o en ingresos, para el tercero O la categoría (N01).
    const porTipo = esIngreso || !!b.terceroId;
    const recordar = porTipo ? null : datosRecordables(estado.sellada.payload, vista.current);
    const recordarTipo = porTipo
      ? datosRecordablesTipo(
          {
            fecha: estado.sellada.payload.fecha_hecho,
            categoriaId: b.categoria.estado === 'CATEGORIA' ? b.categoria.id : null,
            terceroId: b.terceroId ?? null,
            cuenta: estado.sellada.payload.cuenta_id,
            presupuestable: estado.sellada.payload.presupuestable,
          },
          { categoria: nombreCategoria, tercero: b.terceroNombre ?? null },
          vista.current,
        )
      : null;
    const titulo = tituloRegistro({
      tipo: tipoReg,
      importe: r.importe,
      nota: notaRef.current,
      concepto: esIngreso ? null : (estado.sellada.payload as { concepto?: string }).concepto ?? null,
      tercero: b.terceroNombre ?? null,
      categoria: nombreCategoria,
    });
    return (
      <View testID="registro-exito" style={[s.pantalla, { backgroundColor: c.background, paddingTop: inset.top + espacio.xl, paddingBottom: inset.bottom + espacio.l }]}>
        <View style={[s.exito, { backgroundColor: c.surfacePrimary }]} accessibilityLiveRegion="polite">
          <Text style={{ fontSize: 40 }} accessibilityElementsHidden>✓</Text>
          <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>{tituloExito(tipoReg)}</Text>
          <Text style={[importe.primary, { color: c.textPrimary }]}>{formatearEur(r.importe)}</Text>
          <Text testID="exito-titulo" style={[tipo.body, { color: c.textSecondary }]}>{titulo}</Text>
          <Text style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>
            {r.estado_atribucion === 'COMPLETA' ? 'Atribuido: solo tuyo.' : 'Reparto sin indicar: no cuenta en tu gasto atribuible.'}
          </Text>
          {esIngreso ? null : (
            <Text testID="exito-financiacion" style={[tipo.footnote, { color: c.textSecondary, textAlign: 'center' }]}>
              {r.financiacion === 'PROPUESTA_ACEPTADA' ? 'Financiado por ti.' : 'Financiación no determinada.'}
            </Text>
          )}
        </View>
        {recordar ? (
          <GuardarPreferencia
            cliente={p.cliente}
            nuevoId={p.nuevoId}
            categoriaId={recordar.categoriaId}
            nombre={b.categoria.estado === 'CATEGORIA' ? b.categoria.nombre : textoCategoria(b.categoria)}
            finales={recordar.finales}
            casillas={recordar.casillas}
            cuentas={cuentas.fase === 'OK' ? cuentas.lista : []}
          />
        ) : null}
        {recordarTipo ? (
          <GuardarPreferencia
            cliente={p.cliente}
            nuevoId={p.nuevoId}
            categoriaId={null}
            nombre={recordarTipo.ambitos[0].nombre}
            ambitos={recordarTipo.ambitos}
            tipo={tipoReg}
            finales={recordarTipo.finales}
            casillas={recordarTipo.casillas}
            cuentas={cuentas.fase === 'OK' ? cuentas.lista : []}
          />
        ) : null}
        <BotonTexto testID="guardar-como-plantilla" titulo="Guardar como plantilla…" onPress={() => setGuardarPlantilla(true)} />
        <View style={{ flex: 1 }} />
        <BotonPrimario testID="volver-inicio" titulo="Volver a Inicio" onPress={() => p.onCerrar(true)} />
        {guardarPlantilla ? (
          <GuardarPlantilla
            cliente={p.cliente}
            nuevoId={p.nuevoId}
            tipo={tipoReg}
            valores={{
              categoriaId: b.categoria.estado === 'CATEGORIA' ? b.categoria.id : null,
              categoriaNombre: nombreCategoria,
              cuentaId: estado.sellada.payload.cuenta_id,
              cuentaNombre: cuentaSel?.nombre ?? null,
              presupuestable: estado.sellada.payload.presupuestable,
              terceroId: b.terceroId ?? null,
              terceroNombre: b.terceroNombre ?? null,
              contextoId: b.contextoId ?? null,
              contextoNombre: b.contextoNombre ?? null,
            }}
            onCerrar={() => setGuardarPlantilla(false)}
          />
        ) : null}
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {/* Cabecera de TAREA (F09): Cancelar · título. Sin barra inferior. */}
      <View style={[s.cabTarea, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault, backgroundColor: c.background }]}>
        <BotonTexto testID="cancelar" titulo="Cancelar" onPress={cancelar} />
        <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{TITULO_TAREA[tipoReg]}</Text>
        <View style={{ width: 72, alignItems: 'flex-end' }}>
          {!enviado && !bloqueado ? <BotonTexto testID="cambiar-tipo" titulo="Tipo" onPress={() => setHojaTipos(true)} /> : null}
        </View>
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

        {avisos.length > 0 ? (
          <View testID="avisos-registro" accessibilityRole="alert" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            {avisos.map((a, i) => (
              <Text key={i} testID={`aviso-registro-${i}`} style={[tipo.subheadline, { color: c.textPrimary }]}>{a}</Text>
            ))}
          </View>
        ) : null}
        {b.plantilla ? (
          <View testID="chip-plantilla" style={[s.chipPlantilla, { backgroundColor: c.accentSurface }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{`Plantilla: ${b.plantilla.nombre}`}</Text>
            <Pressable testID="quitar-plantilla" accessibilityRole="button" accessibilityLabel="Quitar plantilla" hitSlop={8} onPress={quitarPlantillaAplicada}>
              <Ionicons name="close" size={18} color={c.textSecondary} />
            </Pressable>
          </View>
        ) : null}

        {/* Importe — DS-05 «Campo con icono €» */}
        <Campo etiqueta="Importe" error={visibles.importe}>
          <View style={[s.importeCaja, { backgroundColor: c.surfacePrimary, borderColor: visibles.importe ? c.critical : c.borderStandard }]}>
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

        <Campo etiqueta={esIngreso ? 'De' : 'Tercero'} opcional>
          <Pressable
            testID="campo-tercero"
            accessibilityRole="button"
            accessibilityLabel={`${esIngreso ? 'De' : 'Tercero'}: ${b.terceroNombre ?? 'Sin tercero'}`}
            disabled={bloqueado}
            onPress={() => setSelectorTercero(true)}
            style={[s.campoCategoria, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
          >
            <Text testID="tercero-valor" style={[tipo.body, { flex: 1, color: b.terceroNombre ? c.textPrimary : c.textSecondary }]}>{b.terceroNombre ?? 'Elige tercero'}</Text>
            <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
          </Pressable>
          {b.terceroNombre && b.terceroOrigen === 'INFERIDO' && b.plantilla ? (
            <Text testID="origen-tercero" style={[tipo.footnote, { color: c.textSecondary }]}>{origen('PLANTILLA')}</Text>
          ) : null}
        </Campo>

        {esIngreso ? null : (
        <Campo etiqueta="Concepto" error={visibles.concepto}>
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
            style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: visibles.concepto ? c.critical : c.borderStandard }]}
          />
        </Campo>
        )}

        <Campo etiqueta="Categoría" error={visibles.categoria && !categoriaInvalida ? visibles.categoria : undefined}>
          <Pressable
            testID="campo-categoria"
            accessibilityRole="button"
            accessibilityLabel={`Categoría: ${textoCategoria(b.categoria)}`}
            accessibilityHint="Abre el selector de categorías"
            disabled={bloqueado}
            onPress={() => setSelectorAbierto(true)}
            style={[s.campoCategoria, { backgroundColor: c.surfacePrimary, borderColor: categoriaInvalida ? c.critical : c.borderStandard }]}
          >
            {b.categoria.estado === 'CATEGORIA' ? <IconoCategoriaVista iconKey={b.categoria.icon_key} /> : null}
            <View style={{ flex: 1 }}>
              <Text testID="categoria-valor" style={[tipo.body, { color: b.categoria.estado === 'PENDIENTE' ? c.textSecondary : c.textPrimary }]}>
                {b.categoria.estado === 'PENDIENTE' ? (categoriaInvalida ? 'Elige otra categoría' : 'Elige categoría') : textoCategoria(b.categoria)}
              </Text>
              {b.categoria.estado === 'CATEGORIA' ? (
                <Text testID="categoria-ruta" style={[tipo.caption, { color: c.textSecondary }]}>{rutaVisible(b.categoria.ruta, b.categoria.nombre)}</Text>
              ) : null}
            </View>
            <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
          </Pressable>
          {categoriaDePlantilla(b) ? (
            <Text testID="origen-categoria" style={[tipo.footnote, { color: c.textSecondary }]}>{origen('PLANTILLA')}</Text>
          ) : null}
          {categoriaInvalida ? (
            <Text testID="categoria-invalida" accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>
              {categoriaInvalida.codigo === 'CATEGORIA_NO_ELEGIBLE'
                ? `«${categoriaInvalida.nombre}» ya no está disponible.`
                : `Los datos de «${categoriaInvalida.nombre}» han cambiado. Elige de nuevo la categoría.`}
            </Text>
          ) : null}
        </Campo>

        {b.categoria.estado === 'CATEGORIA' && b.categoria.magnitudes.length > 0 ? (
          <View testID="datos-categoria" style={[s.datos, { backgroundColor: c.surfaceSecondary }]}>
            <Text accessibilityRole="header" style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>Datos de {b.categoria.nombre}</Text>
            {b.categoria.magnitudes.map((m, i, todas) => {
              const err = visibles.magnitudes?.[m.magnitud_id];
              const primeraObligatoria = m.obligatoria && todas.findIndex((x) => x.obligatoria) === i;
              return (
                <View key={m.magnitud_id} style={{ gap: espacio.xs }}>
                  <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>
                    {m.nombre}
                    {m.obligatoria ? '' : <Text style={{ fontWeight: '400' }}> (opcional)</Text>}
                  </Text>
                  <View style={[s.magnitudCaja, { backgroundColor: c.surfacePrimary, borderColor: err ? c.critical : c.borderStandard }]}>
                    <TextInput
                      testID={`magnitud-${m.magnitud_id}`}
                      accessibilityLabel={`${m.nombre} en ${m.unidad_default}${m.obligatoria ? ', obligatorio' : ', opcional'}`}
                      value={b.magnitudesTexto[m.magnitud_id] ?? ''}
                      onChangeText={(texto) => cambiar({ magnitudesTexto: { ...b.magnitudesTexto, [m.magnitud_id]: texto } })}
                      editable={!bloqueado}
                      keyboardType="decimal-pad"
                      inputMode="decimal"
                      style={[tipo.body, { flex: 1, minWidth: 0, color: c.textPrimary, paddingVertical: espacio.s }]}
                    />
                    <Text style={[tipo.body, { color: c.textSecondary }]}>{m.unidad_default}</Text>
                  </View>
                  {err ? <Text accessibilityRole="alert" style={[tipo.footnote, { color: c.critical }]}>{err}</Text> : null}
                  {m.obligatoria ? (
                    <Chip
                      testID={`no-lo-se-${m.magnitud_id}`}
                      etiqueta="No lo sé"
                      seleccionado={esDesconocida(b, m.magnitud_id)}
                      onPress={() => alternarNoLoSe(m)}
                    />
                  ) : null}
                  {m.obligatoria && esDesconocida(b, m.magnitud_id) ? (
                    <Text testID={`no-lo-se-texto-${m.magnitud_id}`} style={[tipo.caption, { color: c.textSecondary }]}>{textoNoLoSe(m.nombre)}</Text>
                  ) : null}
                  {primeraObligatoria ? (
                    <Text testID="microcopy-obligatoria" style={[tipo.caption, { color: c.textSecondary }]}>
                      Este dato es obligatorio para usar esta categoría. Puedes completarlo, cambiar de categoría o registrar sin categoría.
                    </Text>
                  ) : null}
                </View>
              );
            })}
          </View>
        ) : null}

        <Campo etiqueta="¿Cuenta para el presupuesto?" error={visibles.presupuestable}>
          <Segmentado<boolean>
            testIDBase="presupuestable"
            etiquetaGrupo="¿Cuenta para el presupuesto?"
            opciones={[{ valor: true, etiqueta: 'Sí' }, { valor: false, etiqueta: 'No' }]}
            valor={b.presupuestable}
            onCambiar={(v) => cambiar({ presupuestable: v, presupuestableOrigen: 'USUARIO', presupuestablePropuesta: null })}
          />
          {b.presupuestable !== null && (b.presupuestableOrigen === 'USUARIO' || b.presupuestablePropuesta) ? (
            <Text testID="origen-presupuestable" style={[tipo.footnote, { color: c.textSecondary }]}>
              {b.presupuestableOrigen === 'USUARIO' ? TEXTO_ELEGIDA : origen(b.presupuestablePropuesta!)}
            </Text>
          ) : null}
        </Campo>

        <Campo etiqueta={esIngreso ? '¿De quién es este ingreso?' : '¿De quién es este gasto?'} opcional>
          <Chip
            testID="solo-mio"
            etiqueta="Solo mío"
            seleccionado={b.soloMio}
            onPress={() => cambiar({ soloMio: !b.soloMio })}
          />
          <Text testID="origen-atribucion" style={[tipo.footnote, { color: c.textSecondary }]}>
            {esIngreso
              ? b.soloMio ? 'Decisión tuya: el ingreso es 100 % tuyo.' : 'Sin indicar: se guardará sin reparto.'
              : b.soloMio ? 'Decisión tuya: el gasto es 100 % tuyo.' : 'Sin indicar: se guardará sin reparto y no contará en tu gasto atribuible.'}
          </Text>
        </Campo>

        <Campo etiqueta={esIngreso ? 'Cobrado en' : 'Pagado con'} error={visibles.cuenta}>
          {cuentas.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
          {cuentas.fase === 'ERROR' ? (
            <Pressable testID="cuentas-error" accessibilityRole="button" onPress={() => cargarCuentas(b.fechaHecho)} style={{ minHeight: TACTIL_MIN }}>
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
                  onPress={() => cambiar({ cuentaId: x.cuenta_id, cuentaOrigen: 'USUARIO', cuentaPropuesta: null, propuesta: x.propuesta_financiacion, propuestaRechazada: false })}
                />
              ))}
            </View>
          ) : null}
          {cuentaSel && (b.cuentaOrigen === 'USUARIO' || (b.cuentaOrigen === 'INFERIDO' && b.cuentaPropuesta)) ? (
            <Text testID="origen-cuenta" style={[tipo.footnote, { color: c.textSecondary }]}>
              {b.cuentaOrigen === 'USUARIO' ? TEXTO_ELEGIDA : origen(b.cuentaPropuesta!)}
            </Text>
          ) : null}
          {cuentaSel && b.propuesta && !esIngreso ? (
            <View testID="financiacion" style={s.filaFinanciacion}>
              <Text testID="financiacion-texto" style={[tipo.footnote, { color: c.textSecondary, flexShrink: 1 }]}>
                {b.propuesta === 'SELF_100' && !b.propuestaRechazada
                  ? 'Financiado por ti · cuenta 100 % tuya'
                  : 'Financiación no determinada'}
              </Text>
              {b.propuesta === 'SELF_100' ? (
                <BotonTexto
                  testID={b.propuestaRechazada ? 'financiacion-usar-propuesta' : 'financiacion-no-es-asi'}
                  titulo={b.propuestaRechazada ? 'Usar propuesta' : 'No es así'}
                  onPress={() => cambiar({ propuestaRechazada: !b.propuestaRechazada })}
                />
              ) : null}
            </View>
          ) : null}
        </Campo>

        {/* Fecha común del gasto y del pago (REG-01): propuesta «Hoy», editable, nunca futura. */}
        <Campo etiqueta="Fecha" error={visibles.fecha}>
          <View style={s.chips}>
            <Chip testID="fecha-hoy" etiqueta="Hoy" seleccionado={otraFecha === null && b.fechaHecho === hoyIso}
              onPress={() => { if (bloqueado) return; setOtraFecha(null); cambiar({ fechaHecho: hoyIso, fechaOrigen: 'INFERIDO' }); }} />
            <Chip testID="fecha-ayer" etiqueta="Ayer" seleccionado={otraFecha === null && b.fechaHecho === ayerIso}
              onPress={() => { if (bloqueado) return; setOtraFecha(null); cambiar({ fechaHecho: ayerIso, fechaOrigen: 'USUARIO' }); }} />
            <Chip testID="fecha-otra" etiqueta="Otra fecha" seleccionado={otraFecha !== null}
              onPress={() => { if (!bloqueado) setOtraFecha(isoADdmmaaaa(b.fechaHecho)); }} />
          </View>
          {otraFecha !== null ? (
            <TextInput
              testID="campo-fecha"
              accessibilityLabel="Fecha del gasto, día barra mes barra año"
              value={otraFecha}
              editable={!bloqueado}
              onChangeText={(texto) => {
                setOtraFecha(texto);
                cambiar({ fechaHecho: ddmmaaaaAIso(texto) ?? texto, fechaOrigen: 'USUARIO' });
              }}
              placeholder="dd/mm/aaaa"
              placeholderTextColor={c.textSecondary}
              inputMode="numeric"
              maxLength={10}
              style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: visibles.fecha ? c.critical : c.borderStandard }]}
            />
          ) : null}
          <Text testID="fecha" style={[tipo.footnote, { color: c.textSecondary }]}>
            {esFechaIso(b.fechaHecho)
              ? `${b.fechaOrigen === 'INFERIDO' ? 'Propuesta: hoy · ' : ''}${fechaCortaIso(b.fechaHecho)} · fecha del gasto y del pago`
              : 'Escribe la fecha como dd/mm/aaaa.'}
          </Text>
        </Campo>

        {/* G03 «Más detalles»: contexto y (en ingresos) nota. */}
        {masDetalles ? (
          <View testID="mas-detalles" style={{ gap: espacio.l }}>
            <Text accessibilityRole="header" style={[tipo.caption, { color: c.textSecondary, letterSpacing: 0.6 }]}>MÁS DETALLES</Text>
            <Campo etiqueta="Contexto" opcional>
              <Pressable
                testID="campo-contexto"
                accessibilityRole="button"
                accessibilityLabel={`Contexto: ${b.contextoNombre ?? 'Sin contexto'}`}
                disabled={bloqueado}
                onPress={() => setSelectorContexto('LISTA')}
                style={[s.campoCategoria, { backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
              >
                <Text testID="contexto-valor" style={[tipo.body, { flex: 1, color: b.contextoNombre ? c.textPrimary : c.textSecondary }]}>{b.contextoNombre ?? 'Sin contexto'}</Text>
                <Ionicons name="chevron-forward" size={18} color={c.textSecondary} />
              </Pressable>
              {b.contextoNombre && b.contextoOrigen === 'INFERIDO' && b.plantilla ? (
                <Text testID="origen-contexto" style={[tipo.footnote, { color: c.textSecondary }]}>{origen('PLANTILLA')}</Text>
              ) : null}
            </Campo>
            {esIngreso ? (
              <Campo etiqueta="Nota" opcional>
                <TextInput
                  testID="campo-nota"
                  accessibilityLabel="Nota"
                  value={nota}
                  onChangeText={setNota}
                  editable={!bloqueado}
                  maxLength={200}
                  style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
                />
              </Campo>
            ) : null}
          </View>
        ) : (
          <BotonTexto testID="abrir-mas-detalles" titulo={esIngreso ? '+ Más detalles (contexto, nota)' : '+ Más detalles (contexto)'} onPress={() => setMasDetalles(true)} />
        )}

        {estado.fase === 'RECHAZADO' ? (
          <View testID="error-dominio" accessibilityLiveRegion="assertive" style={[s.aviso, { backgroundColor: c.surfacePrimary, borderColor: c.critical, borderWidth: 1 }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>
              {categoriaInvalida
                ? `No se ha registrado: «${categoriaInvalida.nombre}» ya no se puede usar así. Elige otra categoría; el resto de datos se conserva.`
                : estado.codigo === 'FECHA_FUTURA'
                  ? `No se ha registrado. ${TEXTO_FECHA_FUTURA}`
                  : `No se ha registrado. ${estado.mensaje}`}
            </Text>
          </View>
        ) : null}
        {estado.fase === 'INDETERMINADO' ? (
          <View testID="estado-indeterminado" accessibilityLiveRegion="assertive" style={[s.aviso, { backgroundColor: c.partialSurface }]}>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>{estado.mensaje}</Text>
          </View>
        ) : null}

        {!listo && estado.fase !== 'INDETERMINADO' && estado.fase !== 'ENVIANDO' ? (
          <Text testID="faltan" accessibilityLiveRegion="polite" style={[tipo.footnote, { color: c.textSecondary }]}>
            {faltan}
          </Text>
        ) : null}
        {estado.fase === 'INDETERMINADO' ? (
          <BotonPrimario testID="reintentar" titulo="Reintentar" onPress={reintentar} />
        ) : (
          <BotonPrimario
            testID="registrar"
            titulo={estado.fase === 'ENVIANDO' ? 'Guardando…' : esIngreso ? 'Registrar ingreso' : 'Registrar gasto'}
            cargando={estado.fase === 'ENVIANDO'}
            deshabilitado={!listo}
            ayuda={listo ? undefined : faltan}
            onPress={onRegistrar}
          />
        )}
      </ScrollView>

      {cambioPendiente ? (
        <View testID="confirmar-descarte" style={[StyleSheet.absoluteFill, { justifyContent: 'flex-end' }]}>
          <Velo />
          <View style={[s.hoja, { backgroundColor: c.surfacePrimary, paddingBottom: inset.bottom + espacio.l }]}>
            <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>
              {cambioPendiente.destino.estado === 'CATEGORIA' ? `¿Cambiar a ${cambioPendiente.etiqueta}?` : '¿Registrar sin categoría?'}
            </Text>
            <Text style={[tipo.subheadline, { color: c.textPrimary }]}>
              {cambioPendiente.perdidas.length === 1 ? 'Se descartará este dato' : 'Se descartarán estos datos'}
              {b.categoria.estado === 'CATEGORIA' ? ` de ${b.categoria.nombre}` : ''}
              {cambioPendiente.destino.estado === 'CATEGORIA' ? `, que ${cambioPendiente.etiqueta} no usa:` : ':'}
            </Text>
            {cambioPendiente.perdidas.map((m) => (
              <View key={m.magnitud_id} testID={`descarte-${m.magnitud_id}`} style={s.filaDescarte}>
                <Text style={[tipo.body, { color: c.textPrimary }]}>{m.nombre}</Text>
                <Text style={[tipo.body, { color: c.textPrimary }]}>{`${b.magnitudesTexto[m.magnitud_id]} ${m.unidad_default}`}</Text>
              </View>
            ))}
            <BotonPrimario testID="descarte-confirmar" titulo="Cambiar y descartar" onPress={() => aplicarCategoria(cambioPendiente.destino)} />
            <BotonSecundario
              testID="descarte-mantener"
              titulo={b.categoria.estado === 'CATEGORIA' ? `Mantener ${b.categoria.nombre}` : 'Mantener'}
              onPress={() => setCambioPendiente(null)}
            />
          </View>
        </View>
      ) : null}

      {selectorAbierto ? (
        <SelectorCategorias
          titulo="Elegir categoría"
          modo="REGISTRO"
          carga={arbol}
          esVisible={(n) => (arbol.fase === 'OK' ? visibleEnRegistro(arbol.arbol, n, tipoReg) : false)}
          esSeleccionable={esIngreso ? (n) => elegible(n, 'INGRESO') : elegibleParaGasto}
          motivo={(n) => motivoNoSeleccionable(n, tipoReg)}
          naturaleza={tipoReg}
          seleccionadaId={b.categoria.estado === 'CATEGORIA' ? b.categoria.id : null}
          opcionRaiz={{
            etiqueta: 'Sin categoría',
            subtitulo: 'Registrar sin clasificar',
            seleccionada: b.categoria.estado === 'SIN_CATEGORIA',
            onPress: () => proponerCategoria({ estado: 'SIN_CATEGORIA' }),
            testID: 'selector-sin-categoria',
          }}
          onElegir={elegirNodo}
          onCerrar={() => setSelectorAbierto(false)}
          onReintentar={() => void cargarArbol()}
          onContinuarSinCategoria={() => proponerCategoria({ estado: 'SIN_CATEGORIA' })}
        />
      ) : null}

      {selectorTercero ? (
        <SelectorTercero
          cliente={p.cliente}
          nuevoId={p.nuevoId}
          titulo={esIngreso ? 'De' : 'Tercero'}
          seleccionadoId={b.terceroId ?? null}
          onElegir={elegirTercero}
          onCerrar={() => setSelectorTercero(false)}
        />
      ) : null}
      {selectorContexto === 'LISTA' ? (
        <SelectorContexto
          cliente={p.cliente}
          seleccionadoId={b.contextoId ?? null}
          onElegir={elegirContexto}
          onNuevo={() => setSelectorContexto('NUEVO')}
          onCerrar={() => setSelectorContexto(null)}
        />
      ) : null}
      {selectorContexto === 'NUEVO' ? (
        <FormularioContexto
          cliente={p.cliente}
          nuevoId={p.nuevoId}
          existente={null}
          tituloBoton="Crear y usar"
          onHecho={elegirContexto}
          onCancelar={() => setSelectorContexto('LISTA')}
        />
      ) : null}
      {hojaTipos ? <HojaTipos actual={tipoReg} onElegir={cambiarTipo} onCancelar={() => setHojaTipos(false)} /> : null}
    </KeyboardAvoidingView>
  );
}

function textoCategoria(sel: SeleccionCategoria): string {
  if (sel.estado === 'PENDIENTE') return 'Elige categoría';
  if (sel.estado === 'SIN_CATEGORIA') return 'Sin categoría';
  return sel.nombre;
}

/** Ruta bajo el nombre en el campo (lámina R06: «Hogar › Suministros», sin «Todas»); en la raíz, «Todas». */
function rutaVisible(ruta: string, _nombre: string): string {
  const partes = ruta.split(' › ');
  return partes.length > 1 ? partes.slice(1).join(' › ') : ruta;
}

type ClaveFalta = 'importe' | 'concepto' | 'categoria' | 'presupuestable' | 'cuenta' | 'fecha';

const NOMBRE_FALTA: Record<ClaveFalta, string> = {
  importe: 'importe',
  concepto: 'concepto',
  categoria: 'categoría',
  presupuestable: 'si cuenta para el presupuesto',
  cuenta: 'cuenta de pago',
  fecha: 'fecha válida',
};

/** «Para registrar falta: importe, categoría y consumo eléctrico (kWh).» (orden del formulario). */
export function textoFaltan(e: Errores, b: Pick<Borrador, 'importeTexto' | 'categoria' | 'magnitudesTexto'>, tipoReg: 'GASTO' | 'INGRESO' = 'GASTO'): string {
  const partes: string[] = [];
  const nombre = (k: ClaveFalta) =>
    k === 'importe' && b.importeTexto.trim() !== '' ? 'importe válido' : k === 'cuenta' && tipoReg === 'INGRESO' ? 'dónde lo cobraste' : NOMBRE_FALTA[k];
  for (const k of ['importe', 'concepto', 'categoria'] as const) if (e[k]) partes.push(nombre(k));
  if (e.magnitudes && b.categoria.estado === 'CATEGORIA') {
    for (const m of b.categoria.magnitudes) {
      if (!e.magnitudes[m.magnitud_id]) continue;
      const escrito = (b.magnitudesTexto[m.magnitud_id] ?? '').trim() !== '';
      partes.push(`${escrito ? `${m.nombre.toLowerCase()} válido` : m.nombre.toLowerCase()} (${m.unidad_default})`);
    }
  }
  for (const k of ['presupuestable', 'cuenta', 'fecha'] as const) if (e[k]) partes.push(nombre(k));
  if (partes.length === 0) return '';
  const lista = partes.length === 1 ? partes[0] : `${partes.slice(0, -1).join(', ')} y ${partes[partes.length - 1]}`;
  return `Para registrar falta: ${lista}.`;
}

function Campo({ etiqueta, error, opcional, children }: { etiqueta: string; error?: string; opcional?: boolean; children: React.ReactNode }) {
  const { c } = useTema();
  return (
    <View style={{ gap: espacio.s }}>
      <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>
        {etiqueta}
        {opcional ? <Text style={{ fontWeight: '400' }}> opcional</Text> : null}
      </Text>
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
  filaFinanciacion: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.s, flexWrap: 'wrap' },
  campoCategoria: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 8 },
  datos: { borderRadius: radio.m, padding: espacio.m, gap: espacio.m },
  magnitudCaja: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, gap: espacio.s, minHeight: TACTIL_MIN + 4 },
  hoja: { borderTopLeftRadius: radio.xl, borderTopRightRadius: radio.xl, padding: espacio.l, gap: espacio.m },
  filaDescarte: { flexDirection: 'row', justifyContent: 'space-between' },
  chipPlantilla: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.s, borderRadius: radio.pill, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN },
});
