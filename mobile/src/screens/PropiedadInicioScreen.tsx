// ============================================================
// GAPTO MOBILE 2027
// Fichero: PropiedadInicioScreen.tsx
// Ruta: mobile/src/screens/PropiedadInicioScreen.tsx
// Descripción: B1-R · «Corregir desde cuándo» (C-PROP-03bis, POST /v1/propiedades/{id}/titularidad/inicio; mandato §4.6). Tarea inmersiva desde la ficha: muestra el inicio vigente de la titularidad (primera versión) y su reparto; pide la fecha real con el CampoFecha de UX-1 (chips «Hoy · Ayer · Otra fecha» y, si se conoce, «Desde la adquisición»); explica que solo corrige un error (las partes no cambian y lo registrado no se recalcula); con la adquisición «No la sé» avisa de que la fecha no se puede comprobar (no se presenta como verificada); lista los gastos ya registrados del periodo (GET …/afectados, solo lectura) y exige una CONFIRMACIÓN visible antes de enviar (de <inicio> a <nuevo>, mismas partes, N gastos no cambian). Envía `inicio_visto` y `primera_version_vista` tal como los dio el servidor. La `intencion_id` se sella al abrir: un resultado indeterminado se reintenta con la MISMA (replay) y un rechazo de dominio la renueva y muestra el texto del servidor.
// Versión: 0.1.0 (F06 T2-F06 · B1-R (L-01/L-01b); reescrita sobre la del laboratorio lab-t2 45736ad: ruta y payload del §4.3.1, oferta decidida por el servidor, confirmación visible, aviso de adquisición desconocida y gastos afectados)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Afectados, ClientePropiedades, VistaPropiedad } from '../api/propiedades';
import { BotonPrimario, BotonTexto, EstadoDato } from '../components/Basicos';
import { CampoFecha } from '../components/CampoFecha';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef, Tarjeta } from '../components/Formulario';
import { ayer, ddmmaaaaAIso, diaMesAnioIso, isoADdmmaaaa, isoLocal } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import {
  faltasInicio,
  TEXTO_ADQUISICION_DESCONOCIDA,
  TEXTO_AFECTADOS,
  TEXTO_EXPLICACION,
  textoConfirmacion,
} from '../domain/inicio_titularidad';
import { esFechaIso } from '../domain/intencion';
import { formatearPorcentaje } from '../domain/propiedad';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

type Lectura = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; a: Afectados };

const ATRIBUCION: Record<string, string> = { TITULARIDAD: 'según titularidad', MANUAL: 'reparto manual', NO_LO_SE: 'sin reparto', OTRO: 'otro reparto' };

export function PropiedadInicioScreen(p: {
  propiedades: ClientePropiedades;
  vista: VistaPropiedad;
  nuevoId: () => string;
  ahora: () => Date;
  onCerrar: (actualizada: VistaPropiedad | null) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const v = p.vista;
  const it = v.inicio_titularidad!;
  const inicio = it.inicio!;
  const adquisicion = v.fecha_adquisicion;
  const hoyIso = isoLocal(p.ahora());
  const ayerIso = isoLocal(ayer(p.ahora()));
  /** Fecha elegida (ISO) con un chip; con «Otra fecha», el texto dd/mm/aaaa del campo. */
  const [chip, setChip] = useState<string | null>(null);
  const [otra, setOtra] = useState<string | null>(null);
  const [motivo, setMotivo] = useState('');
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [lectura, setLectura] = useState<Lectura>({ fase: 'CARGANDO' });
  /** Identidad de la corrección, sellada al abrir (C-PROP-03bis). */
  const intencion = useRef('');
  if (!intencion.current) intencion.current = p.nuevoId();

  const nuevo = otra !== null ? ddmmaaaaAIso(otra.trim()) : chip;
  const faltas = faltasInicio(nuevo, inicio, hoyIso, adquisicion);
  const valida = faltas.length === 0 && !!nuevo && esFechaIso(nuevo);
  const nuevoValido = valida ? nuevo : null;

  useEffect(() => {
    let vivo = true;
    setLectura({ fase: 'CARGANDO' });
    if (!p.propiedades.gastosAfectados) return setLectura({ fase: 'ERROR' });
    void p.propiedades.gastosAfectados(v.id, nuevoValido).then((r) => {
      if (vivo) setLectura(r.tipo === 'OK' ? { fase: 'OK', a: r.datos.afectados } : { fase: 'ERROR' });
    });
    return () => {
      vivo = false;
    };
  }, [nuevoValido]);

  const elegir = (iso: string | null, texto: string | null) => {
    setChip(iso);
    setOtra(texto);
    setConfirmando(false);
  };

  /** «Continuar» solo abre la confirmación visible; el único envío es «Confirmar la corrección» (dentro de ella). */
  const revisar = () => { if (valida) setConfirmando(true); };

  const enviar = async () => {
    if (ocupado || !nuevoValido || !p.propiedades.corregirInicio) return;
    setOcupado(true);
    setAviso(null);
    const r = await p.propiedades.corregirInicio(v.id, {
      intencion_id: intencion.current,
      row_version_esperada: v.row_version,
      nuevo_desde: nuevoValido,
      inicio_visto: inicio,
      primera_version_vista: it.primera_version.map((x) => ({ actor_id: x.actor_id, porcentaje: x.porcentaje })),
      motivo: motivo.trim() || null,
    });
    setOcupado(false);
    if (r.tipo === 'OK') return p.onCerrar(r.datos.propiedad);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: `${r.mensaje} Si vuelves a confirmar sin cambiar nada, no se duplicará.` });
    intencion.current = p.nuevoId();
    setConfirmando(false);
    setAviso({ tipo: 'AVISO', texto: r.mensaje || 'No se ha podido guardar.' });
  };

  const partes = it.primera_version
    .map((x) => {
      const parte = v.titularidad.partes.find((y) => y.actor_id === x.actor_id);
      return `${parte?.yo ? 'Tú' : parte?.nombre ?? 'Otro titular'} ${formatearPorcentaje(x.porcentaje)}`;
    })
    .join(' · ');
  const recuento = lectura.fase === 'OK' && nuevoValido && lectura.a.nuevo_desde === nuevoValido ? lectura.a.recuento : null;

  return (
    <View testID="prop-inicio" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo="Corregir desde cuándo" testIDCancelar="prop-inicio-cancelar" onCancelar={() => p.onCerrar(null)} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="prop-inicio-aviso" aviso={aviso} /> : null}
        <Text testID="prop-inicio-actual" style={[tipo.body, { color: c.textPrimary }]}>
          {`La titularidad (${partes}) empieza ahora el ${diaMesAnioIso(inicio)}.`}
        </Text>
        <Text testID="prop-inicio-explicacion" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_EXPLICACION}</Text>
        {adquisicion ? null : (
          <Text testID="prop-inicio-adquisicion-desconocida" style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_ADQUISICION_DESCONOCIDA}</Text>
        )}
        <Campo etiqueta="Desde cuándo (fecha real)">
          <CampoFecha
            testID="prop-inicio-fecha"
            etiqueta="Desde cuándo (fecha real)"
            hoyIso={hoyIso}
            max={hoyIso}
            texto={otra}
            onTexto={(t) => elegir(null, t)}
            opciones={[
              { testID: 'prop-inicio-fecha-hoy', etiqueta: 'Hoy', seleccionado: otra === null && chip === hoyIso, onPress: () => elegir(hoyIso, null) },
              { testID: 'prop-inicio-fecha-ayer', etiqueta: 'Ayer', seleccionado: otra === null && chip === ayerIso, onPress: () => elegir(ayerIso, null) },
              { testID: 'prop-inicio-fecha-otra', etiqueta: 'Otra fecha', seleccionado: otra !== null, onPress: () => elegir(null, chip ? isoADdmmaaaa(chip) : '') },
              ...(adquisicion
                ? [{ testID: 'prop-inicio-usar-adquisicion', etiqueta: 'Desde la adquisición', seleccionado: otra === null && chip === adquisicion, onPress: () => elegir(adquisicion, null) }]
                : []),
            ]}
          />
        </Campo>
        {nuevo !== null && faltas.length > 0 ? (
          <Text testID="prop-inicio-faltas" style={[tipo.footnote, { color: c.warningText }]}>{`Falta: ${faltas.join(', ')}.`}</Text>
        ) : null}
        <CampoTexto testID="prop-inicio-motivo" etiqueta="Motivo" marcador="Opcional (p. ej., «Puse mal la fecha»)" valor={motivo} maximo={200} onCambiar={setMotivo} />
        <Text style={[tipo.titleSmall, { color: c.textPrimary }]}>Gastos ya registrados en ese periodo</Text>
        <Text testID="prop-inicio-afectados-texto" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_AFECTADOS}</Text>
        {lectura.fase === 'CARGANDO' ? <EstadoDato testID="prop-inicio-afectados-cargando" estado="CARGANDO" /> : null}
        {lectura.fase === 'ERROR' ? <EstadoDato testID="prop-inicio-afectados-error" estado="ERROR_CARGA" /> : null}
        {lectura.fase === 'OK' ? (
          lectura.a.hechos.length === 0 ? (
            <Text testID="prop-inicio-afectados-vacio" style={[tipo.body, { color: c.textSecondary }]}>Ninguno.</Text>
          ) : (
            <Tarjeta testID="prop-inicio-afectados">
              {lectura.a.hechos.map((h) => (
                <View key={h.hecho_id} testID={`prop-inicio-afectado-${h.hecho_id}`} style={s.fila}>
                  <Text style={[tipo.body, { color: c.textPrimary, flex: 1 }]}>
                    {`${diaMesAnioIso(h.fecha)} · ${h.concepto ?? 'Sin concepto'} · ${ATRIBUCION[h.atribucion] ?? h.atribucion}`}
                  </Text>
                  <Text style={[tipo.bodyEmphasis, { color: c.textPrimary }]}>{h.importe ? formatearEur(h.importe) : '—'}</Text>
                </View>
              ))}
            </Tarjeta>
          )
        ) : null}
        {confirmando && nuevoValido ? (
          <View testID="prop-inicio-confirmacion" style={{ gap: espacio.s }}>
            <Caja testID="prop-inicio-resumen" aviso={{ tipo: 'AVISO', texto: recuento === null
              ? `El inicio pasa del ${diaMesAnioIso(inicio)} al ${diaMesAnioIso(nuevoValido)}. Mismas partes. Los gastos ya registrados no cambian.`
              : textoConfirmacion(inicio, nuevoValido, recuento) }} />
            <BotonPrimario testID="prop-inicio-confirmar" titulo={ocupado ? 'Guardando…' : 'Confirmar la corrección'} cargando={ocupado} onPress={() => void enviar()} />
            <BotonTexto testID="prop-inicio-volver" titulo="Volver" onPress={() => setConfirmando(false)} />
          </View>
        ) : (
          <BotonPrimario
            testID="prop-inicio-revisar"
            titulo="Continuar"
            deshabilitado={!valida}
            ayuda={!valida ? `Falta: ${faltas.join(', ')}` : undefined}
            onPress={revisar}
          />
        )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  fila: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.m },
});
