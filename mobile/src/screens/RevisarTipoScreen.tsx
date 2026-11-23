// ============================================================
// GAPTO MOBILE 2027
// Fichero: RevisarTipoScreen.tsx
// Ruta: mobile/src/screens/RevisarTipoScreen.tsx
// Descripción: Revisar el tipo de la hipoteca con fecha, hacia delante (F06-01H W-HIP-03/04; contrato v0.4 §3.5 y §8; Q-H-11). Condiciones vigentes; «Desde» y nuevo tipo anual (fijo/variable, índice y diferencial opcionales e informativos); alcance «Se recalculan N cuotas desde …; las M pagadas no cambian» (cuenta las cuotas, no calcula importes). Cubre la revisión del Euríbor y cada cambio de bonificación sin nombrarla: nunca «bonificación de X» (la versión solo dice el tipo). Rechazos: VERSION_DESFASADA vuelve a cargar la hipoteca; el resto con su texto, sin «ingreso» ni «cobro». Tras la revisión se pinta la hipoteca que devuelve el servidor.
// Versión: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 10)
// Versión: 0.2.0 (F06 T3 · MANT N1 de revisión del tipo, A3; dictamen MANT R-B2-06 punto 3 y AJ-03; decisión 14): revisar usa `enviarRevisionComprobando`: el cuerpo se construye UNA vez; ante un timeout no dice que ha fallado, muestra «Comprobando…» y reenvía el MISMO cuerpo (misma intención; replay idempotente sin duplicar); si sigue sin confirmarse, `TEXTO_REVISION_SIN_CONFIRMAR` (nunca «fallo» ni «repítela»). La hipoteca revisada solo se pinta con la confirmación del servidor.
// Versión: 0.3.0 (F06 T6 · S1 piezas comunes; F09 0.55 §12.107.1 punto 9): los campos de porcentaje, plazo y tipo abren el teclado decimal (`CampoTexto decimal`); sin otros cambios.
// ============================================================

import React, { useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import type { Hipoteca } from '../api/hipoteca';
import { BotonPrimario, Chip } from '../components/Basicos';
import { CampoFecha } from '../components/CampoFecha';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef } from '../components/Formulario';
import { ddmmaaaaAIso, diaMesAnioIso } from '../domain/fechas';
import {
  BorradorRevision, borradorRevision, condicionesVigentes, cuotasAfectadas, enviarRevisionComprobando, faltasRevision, NOMBRE_TIPO, nombreTipoInteres, payloadRevision, TEXTO_COMPROBANDO_REVISION, TEXTO_CONVENCION,
  TEXTO_REVISION, TEXTO_REVISION_SIN_CONFIRMAR, textoAlcance, textoErrorHipoteca, textoSeguro, textoTasa, TIPOS_INTERES,
} from '../domain/hipoteca';
import { formatearEur } from '../domain/importe';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

export function RevisarTipoScreen(p: {
  cliente: ClienteApi;
  hipoteca: Hipoteca;
  hoyIso: string;
  nuevoId: () => string;
  onCancelar: () => void;
  onRevisada: (h: Hipoteca) => void;
  onRecargar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [r, setR] = useState<BorradorRevision>(borradorRevision());
  const [desdeTexto, setDesdeTexto] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const intencion = useRef(p.nuevoId());
  const h = p.hipoteca;
  const vigente = condicionesVigentes(h);
  const faltas = faltasRevision(r, h);
  const alcance = faltas.length === 0 ? textoAlcance(cuotasAfectadas(h, r.desde).length, r.desde, h.cuotas_pagadas) : null;
  const tipoVigente = nombreTipoInteres(vigente?.tipo_interes);

  const revisar = async () => {
    if (ocupado || faltas.length > 0 || !p.cliente.revisarTipoHipoteca) return;
    setOcupado(true);
    setAviso(null);
    // MANT de revisión del tipo (A3): el cuerpo se construye UNA vez; ante un INDETERMINADO (timeout) se reenvía el MISMO (replay idempotente).
    const revisarTipo = p.cliente.revisarTipoHipoteca;
    const cuerpo = payloadRevision(r, h, intencion.current);
    const { respuesta: x } = await enviarRevisionComprobando(() => revisarTipo(h.financiacion_id, cuerpo),
      () => setAviso({ tipo: 'AVISO', texto: TEXTO_COMPROBANDO_REVISION }));
    setOcupado(false);
    if (x.tipo === 'OK') return p.onRevisada(x.datos.hipoteca);
    if (x.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_REVISION_SIN_CONFIRMAR });
    if (x.codigo === 'VERSION_DESFASADA') return p.onRecargar();
    setAviso({ tipo: 'AVISO', texto: textoErrorHipoteca(x.codigo, x.detalle) ?? textoSeguro(x.mensaje) });
  };

  return (
    <View testID="hip-revision" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo="Revisar el tipo" testIDCancelar="hip-rev-cancelar" onCancelar={p.onCancelar} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="hip-rev-aviso" aviso={aviso} /> : null}
        <Text testID="hip-rev-vigente" style={[tipo.footnote, { color: c.textSecondary }]}>
          {vigente
            ? `Ahora: ${textoTasa(vigente.tasa_anual)}${tipoVigente ? ` ${tipoVigente.toLowerCase()}` : ''} desde el ${diaMesAnioIso(vigente.vigente_desde)}${h.cuota_vigente ? ` · cuota ${formatearEur(h.cuota_vigente)}` : ''}.`
            : 'Sin condiciones vigentes.'}
        </Text>
        <Campo etiqueta="Desde">
          <CampoFecha testID="hip-rev-desde" etiqueta="Desde" hoyIso={p.hoyIso} texto={desdeTexto}
            onTexto={(t) => { setDesdeTexto(t); setR({ ...r, desde: ddmmaaaaAIso(t) ?? t }); }} />
        </Campo>
        <Campo etiqueta="Nuevo tipo anual (%)">
          <CampoTexto decimal testID="hip-rev-tasa" etiqueta="Nuevo tipo anual (%)" marcador="Por ejemplo, 2,95" valor={r.tasa} onCambiar={(t) => setR({ ...r, tasa: t })} />
        </Campo>
        <Campo etiqueta="Fijo o variable" opcional>
          <View style={ef.chips}>
            {TIPOS_INTERES.map((t) => (
              <Chip key={t} testID={`hip-rev-tipo-${t}`} etiqueta={NOMBRE_TIPO[t]} seleccionado={r.tipoInteres === t} onPress={() => setR({ ...r, tipoInteres: r.tipoInteres === t ? null : t })} />
            ))}
          </View>
        </Campo>
        <Campo etiqueta="Índice de referencia" opcional>
          <CampoTexto testID="hip-rev-indice" etiqueta="Índice de referencia" marcador="Por ejemplo, Euríbor 12 meses" valor={r.indice} onCambiar={(t) => setR({ ...r, indice: t })} />
        </Campo>
        <Campo etiqueta="Diferencial (%)" opcional>
          <CampoTexto decimal testID="hip-rev-diferencial" etiqueta="Diferencial (%)" marcador="Por ejemplo, 0,75" valor={r.diferencial} onCambiar={(t) => setR({ ...r, diferencial: t })} />
        </Campo>
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`${TEXTO_REVISION} ${TEXTO_CONVENCION}`}</Text>
        {alcance ? <Text testID="hip-rev-alcance" style={[tipo.body, { color: c.textPrimary }]}>{alcance}</Text> : null}
        {faltas.length > 0 ? <Text testID="hip-rev-faltas" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}.`}</Text> : null}
        <BotonPrimario testID="hip-rev-confirmar" titulo="Revisar el tipo" cargando={ocupado} deshabilitado={faltas.length > 0} onPress={() => void revisar()} />
      </ScrollView>
    </View>
  );
}
