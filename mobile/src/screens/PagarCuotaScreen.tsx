// ============================================================
// GAPTO MOBILE 2027
// Fichero: PagarCuotaScreen.tsx
// Ruta: mobile/src/screens/PagarCuotaScreen.tsx
// Descripción: Pagar una cuota de la hipoteca con un BOTÓN, nunca swipe (F06-01H W-HIP-02; contrato v0.4 §3.4 y §8; n.º 133). Desglose tal como lo da el servidor: «Capital · reduce lo que debes», «Intereses · gasto del mes» y «Sale de tu cuenta»; el cliente solo comprueba capital + intereses = cuota (si no cuadra, no deja pagar). Fecha del cargo (≤ hoy), cuenta (la de cargo propuesta) y reparto de los intereses: la propuesta (titularidad del préstamo en el vencimiento) visible y modificable («Otro reparto»); `propuesta_vista` viaja siempre. Rechazos: VERSION_DESFASADA vuelve a cargar la hipoteca; ATRIBUCION_PROPUESTA_DESFASADA relee la propuesta con intención nueva; el resto con su texto, sin «ingreso» ni «cobro». Solo se abre si la exposición de código lo permite (HipotecaCuadroScreen).
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 10)
// Versión: 0.2.0 (F06 T3-F06 bloque 2 F06-01H; N-30, firma 0f3e5633…): la propuesta del reparto de los intereses es la titularidad DEL PRÉSTAMO de L-HIP en el vencimiento (`titularidadPrestamoEnFecha`, Q-T3D-08); `leerPropuesta` (titularidad de la propiedad) solo si el servidor no da el campo. Con el campo, ATRIBUCION_PROPUESTA_DESFASADA vuelve a cargar la hipoteca.
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaElegible } from '../api/cliente';
import type { CuotaHipoteca, Hipoteca } from '../api/hipoteca';
import type { ParteEnFecha } from '../api/patrimonio';
import { BotonPrimario, Chip, EstadoDato } from '../components/Basicos';
import { CampoFecha } from '../components/CampoFecha';
import { AvisoCaja, CabeceraTarea, Caja, Campo, estilosFormulario as ef, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { ddmmaaaaAIso, diaMesAnioIso, isoADdmmaaaa } from '../domain/fechas';
import {
  desglosePago, EleccionReparto, eleccionPropuesta, ETIQUETA_CAPITAL, ETIQUETA_INTERESES, ETIQUETA_SALIDA, faltasPago, payloadPago, TEXTO_INDETERMINADO, TEXTO_NO_CUADRA,
  TEXTO_REPARTO_INTERESES, TEXTO_SIN_TITULARIDAD_CUOTA, textoErrorHipoteca, textoSeguro, titularidadPrestamoEnFecha,
} from '../domain/hipoteca';
import { formatearEur } from '../domain/importe';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { EleccionRepartoVista, Linea } from './HipotecaCuadroScreen';

export function PagarCuotaScreen(p: {
  cliente: ClienteApi;
  hipoteca: Hipoteca;
  cuota: CuotaHipoteca;
  hoyIso: string;
  nuevoId: () => string;
  leerPropuesta?: (fecha: string) => Promise<ParteEnFecha[] | null>;
  onCancelar: () => void;
  onPagada: (h: Hipoteca) => void;
  onRecargar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const q = p.cuota;
  const d = desglosePago(q);
  const [fecha, setFecha] = useState<string>(isoADdmmaaaa(q.vencimiento <= p.hoyIso ? q.vencimiento : p.hoyIso));
  const fechaIso = ddmmaaaaAIso(fecha);
  const [cuenta, setCuenta] = useState<string | null>(p.hipoteca.cuenta_cargo_id);
  const [cuentas, setCuentas] = useState<CuentaElegible[] | null>(null);
  const [propuesta, setPropuesta] = useState<ParteEnFecha[] | null>(null);
  const [eleccion, setEleccion] = useState<EleccionReparto>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const intencion = useRef(p.nuevoId());

  const cargarPropuesta = async () => {
    setPropuesta(null);
    // N-30: titularidad DEL PRÉSTAMO de L-HIP en el vencimiento; la de la propiedad solo si el servidor no la da.
    const delPrestamo = titularidadPrestamoEnFecha(p.hipoteca, q.vencimiento);
    const x = delPrestamo ?? (p.leerPropuesta ? await p.leerPropuesta(q.vencimiento) : []);
    const partes = x ?? [];
    setPropuesta(partes);
    setEleccion(eleccionPropuesta(partes));
  };
  useEffect(() => {
    void cargarPropuesta();
  }, []);
  useEffect(() => {
    let vivo = true;
    void p.cliente.cuentasElegibles('GASTO', fechaIso ?? p.hoyIso).then((r) => vivo && setCuentas(r.tipo === 'OK' ? r.datos.cuentas : []));
    return () => {
      vivo = false;
    };
  }, [fechaIso]);

  const faltas = faltasPago(fechaIso, p.hoyIso, cuenta, eleccion, propuesta);

  const pagar = async () => {
    if (ocupado || faltas.length > 0 || !d.cuadra || !p.cliente.pagarCuotaHipoteca) return;
    setOcupado(true);
    setAviso(null);
    const r = await p.cliente.pagarCuotaHipoteca(p.hipoteca.financiacion_id, q.numero, payloadPago(p.hipoteca, cuenta!, fechaIso!, eleccion, propuesta, intencion.current));
    setOcupado(false);
    if (r.tipo === 'OK') return p.onPagada(r.datos.hipoteca);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    if (r.codigo === 'VERSION_DESFASADA') return p.onRecargar();
    // N-30: con la titularidad del préstamo en L-HIP, la propuesta nueva llega releyendo la hipoteca.
    if (r.codigo === 'ATRIBUCION_PROPUESTA_DESFASADA' && p.hipoteca.titularidad_prestamo) return p.onRecargar();
    if (r.codigo === 'ATRIBUCION_PROPUESTA_DESFASADA') {
      // La petición rechazada no escribió nada; el contenido cambia con la propuesta releída: intención nueva.
      intencion.current = p.nuevoId();
      void cargarPropuesta();
    }
    setAviso({ tipo: 'AVISO', texto: textoErrorHipoteca(r.codigo, r.detalle) ?? textoSeguro(r.mensaje) });
  };

  return (
    <View testID="hip-pago" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={`Cuota ${q.numero} de ${p.hipoteca.numero_cuotas}`} testIDCancelar="hip-pago-cancelar" onCancelar={p.onCancelar} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="hip-pago-aviso" aviso={aviso} /> : null}
        <Text testID="hip-pago-vence" style={[tipo.footnote, { color: c.textSecondary }]}>{`Vence el ${diaMesAnioIso(q.vencimiento)}.`}</Text>
        <Tarjeta testID="hip-desglose">
          <Linea testID="hip-desglose-capital" etiqueta={ETIQUETA_CAPITAL} valor={formatearEur(d.capital)} />
          <Linea testID="hip-desglose-intereses" etiqueta={ETIQUETA_INTERESES} valor={formatearEur(d.intereses)} />
          <Linea testID="hip-desglose-salida" etiqueta={ETIQUETA_SALIDA} valor={formatearEur(d.salida)} fuerte ultima />
        </Tarjeta>
        {!d.cuadra ? <Text testID="hip-desglose-no-cuadra" style={[tipo.footnote, { color: c.criticalText }]}>{TEXTO_NO_CUADRA}</Text> : null}
        <Campo etiqueta="Fecha del cargo">
          <CampoFecha testID="hip-pago-fecha" etiqueta="Fecha del cargo" hoyIso={p.hoyIso} max={p.hoyIso} texto={fecha} onTexto={setFecha} />
        </Campo>
        <Campo etiqueta="Cuenta">
          {cuentas === null ? <EstadoDato testID="hip-pago-cuentas-cargando" estado="CARGANDO" /> : cuentas.length === 0 ? (
            <EstadoDato testID="hip-pago-sin-cuentas" estado="NO_DISPONIBLE" detalle="Sin cuentas para pagar en esa fecha" />
          ) : (
            <View style={ef.chips}>
              {cuentas.map((x) => <Chip key={x.cuenta_id} testID={`hip-pago-cuenta-${x.cuenta_id}`} etiqueta={x.nombre} seleccionado={cuenta === x.cuenta_id} onPress={() => setCuenta(x.cuenta_id)} />)}
            </View>
          )}
        </Campo>
        <RotuloGrupo texto="Reparto de los intereses" />
        <EleccionRepartoVista testID="hip-pago-reparto" propuesta={propuesta} eleccion={eleccion} onCambiar={setEleccion}
          textoPropuesta={`Según la titularidad del préstamo el ${diaMesAnioIso(q.vencimiento)}`} textoSinPropuesta={TEXTO_SIN_TITULARIDAD_CUOTA} />
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_REPARTO_INTERESES}</Text>
        {faltas.length > 0 ? <Text testID="hip-pago-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        <BotonPrimario testID="hip-pago-confirmar" titulo={`Pagar ${formatearEur(d.salida)}`} cargando={ocupado} deshabilitado={faltas.length > 0 || !d.cuadra}
          onPress={() => void pagar()} />
      </ScrollView>
    </View>
  );
}
