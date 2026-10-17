// ============================================================
// GAPTO MOBILE 2027
// Fichero: GastoCompartidoScreen.tsx
// Ruta: mobile/src/screens/GastoCompartidoScreen.tsx
// Descripción: Gasto con reparto o pagado por otra persona (F05-06 M3; lámina REP v0.2 A1, A2, B1–B4, D1, E7, E8). Parte del registro, que conserva lo común (importe, fecha, comercio, categoría, presupuesto y nota) y se muestra fijo arriba con «Cambiar» para volver. A1: «Pagado con» admite «Otra persona» (D-REP-01): se pregunta quién pagó y «¿Le debes este dinero a X?» con «Sí, le debo X €» / «No» / «No lo sé» (D-REP-02; solo el «Sí» crea la obligación, INV-04; «No lo sé» no la crea, P-REP-01). B1/B2: «Repartir» abre el reparto por personas con importes (D-REP-03): el total nunca cambia, «Repartido» y «Falta por repartir» a la vista, lo vacío queda sin indicar (PARCIAL, G3) y nunca se completa solo; «A partes iguales» es un botón y el céntimo sobrante va a la última fila (D-REP-04). B3: «¿Te deben su parte?» persona a persona («Sí, me lo debe» / «No, invitado»; D-REP-05). A2/B4: revisión en cuatro bloques (D-REP-06): el gasto y su total, tu parte, el dinero (movimiento real o «No sale dinero de tus cuentas») y quién debe a quién. Se guarda en una sola operación (OP-22). Ciclo de envío del registro: UUID y payload sellados antes de enviar; doble toque ignorado; INDETERMINADO reintenta con la MISMA identidad; un rechazo definitivo libera la edición. Éxito con «Pendiente con <persona>» (P-REP-03).
// Versión: 0.1.0 (F05-06 M3 §B1)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaElegible } from '../api/cliente';
import { BotonPrimario, BotonTexto, Chip, EstadoDato } from '../components/Basicos';
import { Aviso, Bloque, CabeceraTarea, Campo, FilaRevision, Inicial, s, SelectorPersona } from '../components/Reparto';
import { TEXTO_FORMULARIO_SE_CONSERVA } from '../domain/capacidades';
import { diaMesAnioIso } from '../domain/fechas';
import { formatearEur, parsearImporte } from '../domain/importe';
import {
  BaseCompartido,
  componerPayload,
  deudasPrevistas,
  faltaCompartido,
  FilaReparto,
  FormularioCompartido,
  miParte,
  partesIguales,
  PayloadGastoCompartido,
  RespuestaLeDebo,
  ResultadoGastoCompartido,
  resumenFila,
  resumenReparto,
  TEXTO_FALTA_SIN_INDICAR,
  TEXTO_NO_LO_SE,
  TEXTO_NO_SALE_DINERO,
  TEXTO_OTRA_PERSONA,
  TEXTO_TE_DEBEN,
  textoDe,
  textoFalta,
} from '../domain/reparto';
import { useTema } from '../theme/tema';
import { espacio, importe, tipo } from '../theme/tokens';

type Paso = 'FORM' | 'REPARTO' | 'TE_DEBEN' | 'REVISION';
type Envio =
  | { fase: 'EDITANDO' }
  | { fase: 'ENVIANDO'; payload: PayloadGastoCompartido }
  | { fase: 'INDETERMINADO'; payload: PayloadGastoCompartido; mensaje: string }
  | { fase: 'RECHAZADO'; codigo: string; mensaje: string }
  | { fase: 'CONFIRMADO'; payload: PayloadGastoCompartido; resultado: ResultadoGastoCompartido };
type Cuentas = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; lista: CuentaElegible[] };

const YO: FilaReparto = { terceroId: null, nombre: 'Tú', importeTexto: '', meDebe: null };

export function GastoCompartidoScreen(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  base: BaseCompartido;
  /** Con qué se abre: «Repartir» o «Otra persona». */
  inicial: { repartir: boolean; otraPersona: boolean };
  /** Vuelve al registro conservando lo común. */
  onVolver: () => void;
  /** registrado: hubo escritura; ver: persona cuyo «Pendiente con» abrir. */
  onCerrar: (registrado: boolean, ver?: { terceroId: string; nombre: string }) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const total = p.base.importe;
  const [f, setF] = useState<FormularioCompartido>(() => ({
    modo: p.inicial.repartir ? 'REPARTIR' : 'SOLO_MIO',
    filas: [YO],
    pagador: p.inicial.otraPersona
      ? { tipo: 'PERSONA', terceroId: null, nombre: null, leDebo: null }
      : { tipo: 'CUENTA', cuentaId: p.base.cuentaId },
  }));
  const [paso, setPaso] = useState<Paso>(p.inicial.repartir ? 'REPARTO' : 'FORM');
  const [selector, setSelector] = useState<'REPARTO' | 'PAGADOR' | null>(null);
  const [cuentas, setCuentas] = useState<Cuentas>({ fase: 'CARGANDO' });
  const [envio, setEnvio] = useState<Envio>({ fase: 'EDITANDO' });
  const enVuelo = useRef(false);
  const sellada = useRef<PayloadGastoCompartido | null>(null);

  const cargarCuentas = async () => {
    setCuentas({ fase: 'CARGANDO' });
    const r = await p.cliente.cuentasElegibles('GASTO', p.base.fechaHecho);
    setCuentas(r.tipo === 'OK' ? { fase: 'OK', lista: r.datos.cuentas } : { fase: 'ERROR' });
    if (r.tipo === 'OK') {
      setF((x) => (x.pagador.tipo === 'CUENTA' && x.pagador.cuentaId && !r.datos.cuentas.some((y) => y.cuenta_id === (x.pagador as { cuentaId: string }).cuentaId)
        ? { ...x, pagador: { tipo: 'CUENTA', cuentaId: null } } : x));
    }
  };
  useEffect(() => {
    void cargarCuentas();
  }, []);

  const bloqueado = envio.fase === 'ENVIANDO' || envio.fase === 'INDETERMINADO' || envio.fase === 'CONFIRMADO';
  const editar = (cambio: (x: FormularioCompartido) => FormularioCompartido) => {
    if (bloqueado) return;
    sellada.current = null; // cualquier cambio: identidad nueva
    if (envio.fase === 'RECHAZADO') setEnvio({ fase: 'EDITANDO' });
    setF(cambio);
  };
  const faltan = faltaCompartido(total, f);
  const pagueYo = f.pagador.tipo === 'CUENTA';
  const personas = f.filas.filter((x) => x.terceroId !== null);
  const nombreCuenta = (id: string | null) => (cuentas.fase === 'OK' ? cuentas.lista.find((x) => x.cuenta_id === id)?.nombre ?? 'la cuenta' : 'la cuenta');

  const enviarPayload = async (payload: PayloadGastoCompartido) => {
    if (enVuelo.current) return; // doble toque: nunca un segundo POST
    enVuelo.current = true;
    setEnvio({ fase: 'ENVIANDO', payload });
    try {
      const r = await p.cliente.registrarGastoCompartido(payload);
      if (r.tipo === 'OK') setEnvio({ fase: 'CONFIRMADO', payload, resultado: r.datos });
      else if (r.tipo === 'RECHAZADO') {
        sellada.current = null; // definitivo: el siguiente envío lleva identidad nueva
        setEnvio({ fase: 'RECHAZADO', codigo: r.codigo, mensaje: r.mensaje });
        if (r.codigo === 'CUENTA_SIN_CAPACIDAD') {
          setF((x) => ({ ...x, pagador: { tipo: 'CUENTA', cuentaId: null } }));
          void cargarCuentas();
        }
      } else setEnvio({ fase: 'INDETERMINADO', payload, mensaje: r.mensaje });
    } finally {
      enVuelo.current = false;
    }
  };
  const registrar = async () => {
    if (enVuelo.current || faltan.length > 0) return;
    if (!sellada.current) sellada.current = componerPayload(p.base, f, p.nuevoId());
    await enviarPayload(sellada.current);
  };

  const resumenComun = (
    <View testID="compartido-base" style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
      <View style={s.kv}>
        <View style={{ flex: 1 }}>
          <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{p.base.terceroNombre ?? p.base.nota ?? 'Gasto'}</Text>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`${p.base.categoriaNombre} · ${diaMesAnioIso(p.base.fechaHecho)}`}</Text>
        </View>
        <Text testID="compartido-total" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{formatearEur(total)}</Text>
      </View>
      {!bloqueado ? <BotonTexto testID="compartido-cambiar" titulo="Cambiar" onPress={p.onVolver} /> : null}
    </View>
  );

  const avisos = (
    <>
      {envio.fase === 'RECHAZADO' ? (
        <Aviso testID="compartido-error" critico
          texto={envio.codigo === 'CUENTA_SIN_CAPACIDAD' ? `${envio.mensaje} ${TEXTO_FORMULARIO_SE_CONSERVA}` : `No se ha registrado. ${envio.mensaje}`} />
      ) : null}
      {envio.fase === 'INDETERMINADO' ? <Aviso testID="compartido-indeterminado" texto={envio.mensaje} /> : null}
    </>
  );

  const textoFaltan = (l: string[]) =>
    l.length > 0 ? (
      <Text testID="compartido-faltan" accessibilityLiveRegion="polite" style={[tipo.footnote, { color: c.textSecondary }]}>
        {`Para revisar falta: ${l.length === 1 ? l[0] : `${l.slice(0, -1).join(', ')} y ${l[l.length - 1]}`}.`}
      </Text>
    ) : null;

  // ---------------------------------------------------------------- éxito
  if (envio.fase === 'CONFIRMADO') {
    const r = envio.resultado;
    const nombreDe = (tid: string) => f.filas.find((x) => x.terceroId === tid)?.nombre ?? (f.pagador.tipo === 'PERSONA' ? f.pagador.nombre : null) ?? 'esa persona';
    return (
      <View testID="compartido-exito" style={[s.pantalla, { backgroundColor: c.background, paddingTop: inset.top + espacio.xl, paddingBottom: inset.bottom + espacio.l }]}>
        <View style={[s.exito, { backgroundColor: c.surfacePrimary }]} accessibilityLiveRegion="polite">
          <Text style={{ fontSize: 40 }} accessibilityElementsHidden>✓</Text>
          <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>Gasto registrado</Text>
          <Text style={[importe.primary, { color: c.textPrimary }]}>{formatearEur(r.importe)}</Text>
          <Text testID="compartido-exito-tu-parte" style={[tipo.body, { color: c.textSecondary }]}>
            {r.tu_parte ? `Tu parte: ${formatearEur(r.tu_parte)}` : 'Tu parte: sin indicar'}
          </Text>
          <Text testID="compartido-exito-dinero" style={[tipo.footnote, { color: c.textSecondary }]}>
            {r.movimiento ? `Movimiento real: ${formatearEur(r.movimiento)}` : TEXTO_NO_SALE_DINERO}
          </Text>
        </View>
        <View style={{ gap: espacio.s }}>
          {r.posiciones.map((x) => {
            const tid = envio.payload.pagado_por.tipo === 'PERSONA' && x.tipo === 'OBLIGACION_PAGO'
              ? envio.payload.pagado_por.tercero_id
              : envio.payload.reparto.modo === 'REPARTIR'
                ? envio.payload.reparto.partes.find((q) => q.me_debe === 'SI' && q.importe === x.importe)?.tercero_id ?? null
                : null;
            if (!tid) return null;
            const nombre = nombreDe(tid);
            return (
              <BotonTexto key={x.entidad_id} testID={`compartido-ver-pendiente-${tid}`} titulo={`Pendiente con ${nombre}`}
                onPress={() => p.onCerrar(true, { terceroId: tid, nombre })} />
            );
          })}
          <BotonPrimario testID="compartido-hecho" titulo="Hecho" onPress={() => p.onCerrar(true)} />
        </View>
      </View>
    );
  }

  // ---------------------------------------------------------------- A2/B4 revisión
  if (paso === 'REVISION' || envio.fase === 'ENVIANDO' || envio.fase === 'INDETERMINADO') {
    const mia = miParte(total, f);
    const deudas = deudasPrevistas(p.base, f);
    const otros = personas.map((x) => {
      const r = parsearImporte(x.importeTexto);
      return `${x.nombre} ${r.ok ? textoDe(r.valor) : 'sin indicar'}`;
    });
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraTarea titulo="Revisar" izquierda={<BotonTexto testID="compartido-revision-atras" titulo="‹ Atrás"
          onPress={() => (bloqueado ? undefined : setPaso(f.modo === 'REPARTIR' && pagueYo ? 'TE_DEBEN' : 'FORM'))} />} />
        <ScrollView testID="compartido-revision" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Bloque titulo="El gasto" testID="revision-gasto">
            <FilaRevision testID="revision-total" titulo={`${p.base.terceroNombre ?? p.base.nota ?? 'Gasto'} · ${p.base.categoriaNombre}`}
              detalle="Total del hecho" valor={formatearEur(total)} />
          </Bloque>
          <Bloque titulo="Tu parte" testID="revision-tu-parte">
            <FilaRevision testID="revision-mia" titulo={f.modo === 'SOLO_MIO' ? 'Solo tuyo' : otros.join(' · ')}
              detalle={mia === null ? 'Sin indicar: no cuenta como tuyo en el Resultado' : undefined}
              valor={mia === null ? 'Sin indicar' : formatearEur(mia)} />
            {f.modo === 'REPARTIR' && resumenReparto(total, f.filas).sinIndicar ? (
              <Text testID="revision-sin-indicar" style={[tipo.footnote, { color: c.textSecondary }]}>
                {`${formatearEur(resumenReparto(total, f.filas).falta)} sin indicar: no cuenta como tuyo ni como de nadie.`}
              </Text>
            ) : null}
          </Bloque>
          <Bloque titulo="El dinero" testID="revision-dinero">
            {f.pagador.tipo === 'CUENTA' ? (
              <FilaRevision testID="revision-movimiento" titulo={nombreCuenta(f.pagador.cuentaId)} detalle="Movimiento real" valor={`−${formatearEur(total)}`} />
            ) : (
              <FilaRevision testID="revision-movimiento" titulo={`Pagó ${f.pagador.nombre}`} detalle={TEXTO_NO_SALE_DINERO} valor={formatearEur(total)} />
            )}
          </Bloque>
          <Bloque titulo="Quién debe a quién" testID="revision-deudas">
            {deudas.length === 0 ? (
              <Text testID="revision-sin-deudas" style={[tipo.subheadline, { color: c.textSecondary }]}>Nadie debe nada por este gasto.</Text>
            ) : (
              deudas.map((d) => (
                <View key={`${d.quien}-${d.sentido}`} style={s.kv}>
                  <Inicial nombre={d.quien} />
                  <FilaRevision testID={`revision-deuda-${d.sentido}`} titulo={d.sentido === 'TE_DEBE' ? `${d.quien} te debe` : `Le debes a ${d.quien}`}
                    valor={formatearEur(d.importe)} etiqueta={d.sentido === 'TE_DEBE' ? 'Nuevo derecho de cobro' : 'Nueva obligación'} />
                </View>
              ))
            )}
          </Bloque>
          {avisos}
          {envio.fase === 'INDETERMINADO' ? (
            <BotonPrimario testID="compartido-reintentar" titulo="Reintentar" onPress={() => void enviarPayload(envio.payload)} />
          ) : (
            <BotonPrimario testID="registrar-compartido" titulo={envio.fase === 'ENVIANDO' ? 'Guardando…' : 'Registrar gasto'}
              cargando={envio.fase === 'ENVIANDO'} onPress={() => void registrar()} />
          )}
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- B3 ¿Te deben su parte?
  if (paso === 'TE_DEBEN') {
    return (
      <View style={{ flex: 1, backgroundColor: c.background }}>
        <CabeceraTarea titulo="¿Te deben su parte?" izquierda={<BotonTexto testID="te-deben-atras" titulo="‹ Atrás" onPress={() => setPaso('FORM')} />} />
        <ScrollView testID="compartido-te-deben" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Text style={[tipo.body, { color: c.textPrimary }]}>{`Pagaste tú los ${formatearEur(total)}. ${TEXTO_TE_DEBEN}`}</Text>
          {personas.map((x) => {
            const r = parsearImporte(x.importeTexto);
            return (
              <View key={x.terceroId} testID={`te-debe-${x.terceroId}`} style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
                <View style={s.kv}>
                  <Inicial nombre={x.nombre} />
                  <Text style={[tipo.bodyEmphasis, { color: c.textPrimary, flex: 1 }]}>{`${x.nombre} · ${r.ok ? formatearEur(r.valor) : 'sin indicar'}`}</Text>
                </View>
                <View style={s.chips}>
                  <Chip testID={`te-debe-${x.terceroId}-si`} etiqueta="Sí, me lo debe" seleccionado={x.meDebe === 'SI'}
                    onPress={() => editar((y) => ({ ...y, filas: y.filas.map((q) => (q.terceroId === x.terceroId ? { ...q, meDebe: 'SI' } : q)) }))} />
                  <Chip testID={`te-debe-${x.terceroId}-no`} etiqueta="No, invitado" seleccionado={x.meDebe === 'NO'}
                    onPress={() => editar((y) => ({ ...y, filas: y.filas.map((q) => (q.terceroId === x.terceroId ? { ...q, meDebe: 'NO' } : q)) }))} />
                </View>
                {x.meDebe === 'SI' && !r.ok ? (
                  <Text style={[tipo.footnote, { color: c.critical }]}>Para que te deba su parte, indica cuánto es en el reparto.</Text>
                ) : null}
              </View>
            );
          })}
          {textoFaltan(faltan)}
          <BotonPrimario testID="te-deben-revisar" titulo="Revisar" deshabilitado={faltan.length > 0} onPress={() => { if (faltan.length === 0) setPaso('REVISION'); }} />
        </ScrollView>
      </View>
    );
  }

  // ---------------------------------------------------------------- B2 reparto (D1 en oscuro)
  if (paso === 'REPARTO') {
    const res = resumenReparto(total, f.filas);
    const cambiarImporte = (i: number, t: string) => editar((y) => ({ ...y, filas: y.filas.map((q, j) => (j === i ? { ...q, importeTexto: t } : q)) }));
    return (
      <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <CabeceraTarea titulo="Reparto" izquierda={<BotonTexto testID="reparto-atras" titulo="‹ Atrás" onPress={() => setPaso('FORM')} />}
          derecha={<BotonTexto testID="reparto-listo" titulo="Listo" onPress={() => setPaso('FORM')} />} />
        <ScrollView testID="compartido-reparto" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <View style={s.kv}>
            <Text style={[tipo.body, { color: c.textSecondary }]}>Total del hecho</Text>
            <Text testID="reparto-total" style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{formatearEur(total)}</Text>
          </View>
          <View style={{ gap: espacio.s }}>
            {f.filas.map((x, i) => (
              <View key={x.terceroId ?? 'yo'} testID={`reparto-fila-${x.terceroId ?? 'yo'}`} style={[s.fila, { backgroundColor: c.surfacePrimary }]}>
                <Inicial nombre={x.terceroId === null ? 'Yo' : x.nombre} />
                <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{x.nombre}</Text>
                <TextInput testID={`reparto-importe-${x.terceroId ?? 'yo'}`} accessibilityLabel={`Parte de ${x.nombre} en euros`} value={x.importeTexto}
                  onChangeText={(t) => cambiarImporte(i, t)} editable={!bloqueado} keyboardType="decimal-pad" inputMode="decimal" placeholder="—"
                  placeholderTextColor={c.textSecondary} style={[tipo.body, s.inputImporte, { color: c.textPrimary, borderColor: c.borderStandard }]} />
                {x.terceroId !== null ? (
                  <BotonTexto testID={`reparto-quitar-${x.terceroId}`} titulo="Quitar" onPress={() => editar((y) => ({ ...y, filas: y.filas.filter((q) => q.terceroId !== x.terceroId) }))} />
                ) : null}
              </View>
            ))}
          </View>
          <BotonTexto testID="reparto-anadir" titulo="+ Añadir persona" onPress={() => setSelector('REPARTO')} />
          <BotonTexto testID="reparto-iguales" titulo="A partes iguales"
            onPress={() => {
              const iguales = partesIguales(total, f.filas.length);
              editar((y) => ({ ...y, filas: y.filas.map((q, j) => ({ ...q, importeTexto: textoDe(iguales[j]) })) }));
            }} />
          <View style={[s.tarjeta, { backgroundColor: c.surfacePrimary }]}>
            <View style={s.kv}>
              <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Repartido</Text>
              <Text testID="reparto-repartido" style={[tipo.subheadline, { color: c.textPrimary }]}>{formatearEur(res.repartido)}</Text>
            </View>
            <View style={s.kv}>
              <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Falta por repartir</Text>
              <Text testID="reparto-falta" style={[tipo.subheadline, { color: res.excede ? c.critical : c.textPrimary, fontWeight: '600' }]}>
                {res.excede ? 'Supera el total' : textoFalta(res)}
              </Text>
            </View>
          </View>
          <Text testID="reparto-texto" style={[tipo.footnote, { color: c.textSecondary }]}>
            {res.sinIndicar && f.filas.some((x) => !x.importeTexto.trim())
              ? `La parte de ${f.filas.filter((x) => !x.importeTexto.trim()).map((x) => x.nombre).join(' y ')} queda sin indicar. No cuenta como tuya ni como suya.`
              : TEXTO_FALTA_SIN_INDICAR}
          </Text>
        </ScrollView>
        {selector === 'REPARTO' ? (
          <SelectorPersona cliente={p.cliente} nuevoId={p.nuevoId} excluir={[...personas.map((x) => x.terceroId!), ...(p.base.terceroId ? [p.base.terceroId] : [])]}
            onCancelar={() => setSelector(null)}
            onElegir={(t) => {
              setSelector(null);
              editar((y) => ({ ...y, filas: [...y.filas, { terceroId: t.id, nombre: t.nombre, importeTexto: '', meDebe: null }] }));
            }} />
        ) : null}
      </KeyboardAvoidingView>
    );
  }

  // ---------------------------------------------------------------- A1/B1 formulario
  const leDebo = (v: RespuestaLeDebo) => editar((y) => (y.pagador.tipo === 'PERSONA' ? { ...y, pagador: { ...y.pagador, leDebo: v } } : y));
  const mia = miParte(total, f);
  // B3 se pregunta en su propia pantalla: aquí no bloquea.
  const faltanAqui = faltan.filter((x) => !(x.startsWith('si ') && x.endsWith(' te debe su parte')));
  const siguiente = () => {
    if (faltanAqui.length > 0) return;
    setPaso(f.modo === 'REPARTIR' && pagueYo ? 'TE_DEBEN' : 'REVISION');
  };
  return (
    <View style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraTarea titulo="Nuevo gasto" izquierda={<BotonTexto testID="compartido-cancelar" titulo="Cancelar" onPress={() => p.onCerrar(false)} />} />
      <ScrollView testID="compartido-form" keyboardShouldPersistTaps="handled" contentContainerStyle={[s.form, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {resumenComun}
        <Campo etiqueta="¿De quién es este gasto?">
          <View style={s.chips}>
            <Chip testID="modo-solo-mio" etiqueta="Solo mío" seleccionado={f.modo === 'SOLO_MIO'} onPress={() => editar((y) => ({ ...y, modo: 'SOLO_MIO' }))} />
            <Chip testID="modo-repartir" etiqueta="Repartir" seleccionado={f.modo === 'REPARTIR'}
              onPress={() => { editar((y) => ({ ...y, modo: 'REPARTIR' })); setPaso('REPARTO'); }} />
          </View>
          {f.modo === 'REPARTIR' ? (
            <Pressable testID="modo-repartir-resumen" accessibilityRole="button" onPress={() => setPaso('REPARTO')} style={[s.fila, { backgroundColor: c.surfacePrimary }]}>
              <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>{resumenFila(f.filas)}</Text>
              <Text style={[tipo.body, { color: c.textSecondary }]}>›</Text>
            </Pressable>
          ) : null}
        </Campo>
        <Campo etiqueta="Pagado con">
          {cuentas.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
          {cuentas.fase === 'ERROR' ? (
            <Pressable testID="compartido-cuentas-error" accessibilityRole="button" onPress={() => void cargarCuentas()}>
              <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
            </Pressable>
          ) : null}
          <View style={s.chips}>
            {cuentas.fase === 'OK'
              ? cuentas.lista.map((x) => (
                  <Chip key={x.cuenta_id} testID={`compartido-cuenta-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={f.pagador.tipo === 'CUENTA' && f.pagador.cuentaId === x.cuenta_id}
                    onPress={() => editar((y) => ({ ...y, pagador: { tipo: 'CUENTA', cuentaId: x.cuenta_id } }))} />
                ))
              : null}
            <Chip testID="pagado-otra-persona" etiqueta={TEXTO_OTRA_PERSONA} seleccionado={f.pagador.tipo === 'PERSONA'}
              onPress={() => editar((y) => (y.pagador.tipo === 'PERSONA' ? y : { ...y, pagador: { tipo: 'PERSONA', terceroId: null, nombre: null, leDebo: null }, filas: y.filas.map((q) => ({ ...q, meDebe: null })) }))} />
          </View>
        </Campo>
        {f.pagador.tipo === 'PERSONA' ? (
          <>
            <Campo etiqueta="¿Quién lo pagó?">
              <Pressable testID="pagador-persona" accessibilityRole="button" onPress={() => setSelector('PAGADOR')} style={[s.fila, { backgroundColor: c.surfacePrimary }]}>
                {f.pagador.nombre ? <Inicial nombre={f.pagador.nombre} /> : null}
                <Text style={[tipo.body, { color: f.pagador.nombre ? c.textPrimary : c.textSecondary, flex: 1 }]}>{f.pagador.nombre ?? 'Elige quién lo pagó'}</Text>
                <Text style={[tipo.body, { color: c.textSecondary }]}>›</Text>
              </Pressable>
              <Text testID="pagador-no-sale-dinero" style={[tipo.footnote, { color: c.textSecondary }]}>{`${TEXTO_NO_SALE_DINERO} ni se crea un movimiento.`}</Text>
            </Campo>
            {f.pagador.nombre ? (
              <Campo etiqueta={`¿Le debes este dinero a ${f.pagador.nombre}?`}>
                <View style={s.chips}>
                  <Chip testID="le-debo-si" etiqueta={mia ? `Sí, le debo ${formatearEur(mia)}` : 'Sí, le debo mi parte'} seleccionado={f.pagador.leDebo === 'SI'} onPress={() => leDebo('SI')} />
                  <Chip testID="le-debo-no" etiqueta="No" seleccionado={f.pagador.leDebo === 'NO'} onPress={() => leDebo('NO')} />
                  <Chip testID="le-debo-no-lo-se" etiqueta="No lo sé" seleccionado={f.pagador.leDebo === 'NO_LO_SE'} onPress={() => leDebo('NO_LO_SE')} />
                </View>
                {f.pagador.leDebo === 'NO_LO_SE' ? <Text testID="le-debo-no-lo-se-texto" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_NO_LO_SE}</Text> : null}
                {f.pagador.leDebo === 'NO' ? <Text testID="le-debo-no-texto" style={[tipo.footnote, { color: c.textSecondary }]}>Pagar por otro no crea deudas por sí solo.</Text> : null}
              </Campo>
            ) : null}
          </>
        ) : null}
        {avisos}
        {textoFaltan(faltanAqui)}
        <BotonPrimario testID="compartido-revisar" titulo="Revisar" deshabilitado={faltanAqui.length > 0} onPress={siguiente} />
      </ScrollView>
      {selector === 'PAGADOR' ? (
        <SelectorPersona cliente={p.cliente} nuevoId={p.nuevoId} titulo="¿Quién lo pagó?" excluir={p.base.terceroId ? [p.base.terceroId] : []}
          onCancelar={() => setSelector(null)}
          onElegir={(t) => {
            setSelector(null);
            editar((y) => ({ ...y, pagador: { tipo: 'PERSONA', terceroId: t.id, nombre: t.nombre, leDebo: null } }));
          }} />
      ) : null}
    </View>
  );
}
