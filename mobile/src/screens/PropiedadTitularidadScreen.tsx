// ============================================================
// GAPTO MOBILE 2027
// Fichero: PropiedadTitularidadScreen.tsx
// Ruta: mobile/src/screens/PropiedadTitularidadScreen.tsx
// Descripción: Titularidad de una propiedad (F06-01 B1 · C-PROP-03 y L-PROP; lámina F06-01 v0.1 C1–C2). C1: reparto vigente hoy con su fecha «Desde», cambio programado aparte y la acción «Cambiar el reparto desde una fecha». «Corregir un error en este reparto» (C3) NO se implementa: su contrato sigue abierto (D-PROP-06). C2: nuevo reparto desde una fecha ≥ hoy (no se vuelve a «Aún no lo sé»), resumen «Reparto actual termina el <día anterior>» y «Lo registrado antes no cambia» (M-2: no reatribuye). Envía `titularidad_vista` = el conjunto COMPLETO de partes vigentes que se vio (PR1-04); si cambió entretanto, el servidor responde VERSION_DESFASADA y se pide recargar (D4), sin mezclar cambios.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// ============================================================

import React, { useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import { ClientePropiedades, titularidadVista, VistaPropiedad } from '../api/propiedades';
import { BotonPrimario, CabeceraNavegacion } from '../components/Basicos';
import { AvisoCaja, CabeceraTarea, Caja, estilosFormulario as ef, FilaLista, RotuloGrupo, Tarjeta } from '../components/Formulario';
import { EditorTitularidad } from '../components/Titularidad';
import { ddmmaaaaAIso, diaMesAnioIso } from '../domain/fechas';
import {
  diaAnteriorIso,
  faltaTitularidad,
  formatearPorcentaje,
  formCambioDe,
  FormTitularidad,
  TEXTO_INDETERMINADO_PROP,
  textoErrorB1,
  textoTitularidad,
  titularidadWire,
} from '../domain/propiedad';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { ConflictoPropiedad } from './PropiedadEditarScreen';

export const TEXTO_TITULARIDAD_PAGOS = 'La titularidad no cambia quién pagó cada gasto: eso lo dice cada registro.';

/** C1 · Titularidad vigente y anteriores (solo la vigente y la programada: el historial completo no lo devuelve L-PROP). */
export function PropiedadTitularidadScreen(p: { vista: VistaPropiedad; onAtras: () => void; onCambiar: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const t = p.vista.titularidad;
  return (
    <View testID="prop-titularidad" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo="Titularidad" atras={{ etiqueta: 'Resumen', onPress: p.onAtras }} testIDAtras="prop-tit-atras" />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <RotuloGrupo texto="Vigente" />
        <Tarjeta testID="prop-tit-vigente">
          {t.partes.length === 0 ? (
            <View style={s.fila}>
              <Text testID="prop-tit-sin-indicar" style={[tipo.body, { color: c.textSecondary }]}>Sin indicar</Text>
            </View>
          ) : (
            t.partes.map((x, i) => (
              <View key={x.actor_id} testID={`prop-tit-parte-${x.yo ? 'yo' : x.tercero_id}`} style={[s.fila, i < t.partes.length - 1 && { borderBottomColor: c.borderDefault, borderBottomWidth: StyleSheet.hairlineWidth }]}>
                <View style={{ flex: 1 }}>
                  <Text style={[tipo.body, { color: c.textPrimary }]}>{x.yo ? 'Tú' : x.nombre ?? 'Sin nombre'}</Text>
                  {t.desde ? <Text style={[tipo.caption, { color: c.textSecondary }]}>{`Desde ${diaMesAnioIso(t.desde)}`}</Text> : null}
                </View>
                <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{formatearPorcentaje(x.porcentaje)}</Text>
              </View>
            ))
          )}
        </Tarjeta>
        {p.vista.cambio_programado ? (
          <>
            <RotuloGrupo texto="Programado" />
            <Text testID="prop-tit-programado" style={[tipo.body, { color: c.textPrimary }]}>
              {`Desde el ${diaMesAnioIso(p.vista.cambio_programado.desde!)}: ${textoTitularidad(p.vista.cambio_programado)}`}
            </Text>
          </>
        ) : null}
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_TITULARIDAD_PAGOS}</Text>
        <Tarjeta>
          <FilaLista testID="prop-tit-cambiar" titulo="Cambiar el reparto desde una fecha" ultima onPress={p.onCambiar} />
        </Tarjeta>
      </ScrollView>
    </View>
  );
}

/** C2 · Nuevo reparto desde una fecha (C-PROP-03). */
export function CambioTitularidadScreen(p: {
  cliente: ClienteApi;
  propiedades: ClientePropiedades;
  vista: VistaPropiedad;
  nuevoId: () => string;
  onCerrar: (actualizada: VistaPropiedad | null) => void;
  onRecargar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const claves = useRef(0);
  const nuevaClave = () => `c${++claves.current}`;
  const [f, setF] = useState<FormTitularidad>(() => formCambioDe(p.vista.titularidad, nuevaClave));
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [conflicto, setConflicto] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const id = useRef(p.nuevoId());
  const hoy = p.vista.fecha_consulta;
  const desde = f.desde.trim() ? ddmmaaaaAIso(f.desde) : null;
  const faltas = [...faltaTitularidad(f, p.vista.fecha_adquisicion)];
  if (desde && desde < hoy) faltas.push(`una fecha «Desde» igual o posterior a hoy (${diaMesAnioIso(hoy)})`);
  if (desde && p.vista.titularidad.desde && desde <= p.vista.titularidad.desde) faltas.push('una fecha posterior al inicio del reparto actual');

  const guardar = async () => {
    if (ocupado || faltas.length > 0 || f.modo === null || f.modo === 'DESCONOCIDA') return;
    setOcupado(true);
    setAviso(null);
    const w = titularidadWire(f);
    const r = await p.propiedades.cambiarTitularidad(p.vista.id, {
      intencion_id: id.current,
      row_version_esperada: p.vista.row_version,
      modo: f.modo,
      desde: w.desde!,
      partes: w.partes ?? null,
      titularidad_vista: titularidadVista(p.vista.titularidad),
    });
    setOcupado(false);
    if (r.tipo === 'OK') return p.onCerrar(r.datos.propiedad);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO_PROP });
    if (r.codigo === 'VERSION_DESFASADA') return setConflicto(true);
    setAviso({ tipo: 'AVISO', texto: textoErrorB1(r.codigo, r.mensaje) });
  };

  if (conflicto) return <ConflictoPropiedad titulo="Nuevo reparto" onCancelar={() => p.onCerrar(null)} onRecargar={p.onRecargar} />;

  return (
    <View testID="prop-tit-nuevo" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo="Nuevo reparto" testIDCancelar="prop-tit-nuevo-cancelar" onCancelar={() => p.onCerrar(null)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="prop-tit-aviso" aviso={aviso} /> : null}
        <EditorTitularidad cliente={p.cliente} form={f} onCambiar={setF} nuevaClave={nuevaClave} modos={['SOLO_MIA', 'COMPARTIDA', 'DE_OTROS']} ayudaDesde={`No antes de hoy (${diaMesAnioIso(hoy)})`} />
        {desde && faltas.length === 0 ? (
          <View testID="prop-tit-resumen" style={{ gap: espacio.xs }}>
            {p.vista.titularidad.partes.length > 0 ? (
              <Text style={[tipo.footnote, { color: c.textPrimary }]}>{`Reparto actual termina el ${diaMesAnioIso(diaAnteriorIso(desde))}`}</Text>
            ) : null}
            <Text style={[tipo.footnote, { color: c.textPrimary }]}>{`Nuevo reparto desde el ${diaMesAnioIso(desde)}`}</Text>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{`Lo registrado antes del ${diaMesAnioIso(desde)} no cambia.`}</Text>
          </View>
        ) : null}
        <BotonPrimario
          testID="prop-tit-guardar"
          titulo={ocupado ? 'Guardando…' : 'Guardar nuevo reparto'}
          cargando={ocupado}
          deshabilitado={faltas.length > 0}
          ayuda={faltas.length > 0 ? `Falta: ${faltas.join(', ')}` : undefined}
          onPress={() => void guardar()}
        />
        {faltas.length > 0 ? <Text testID="prop-tit-falta" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}`}</Text> : null}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.m },
});
