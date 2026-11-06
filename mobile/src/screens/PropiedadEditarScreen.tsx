// ============================================================
// GAPTO MOBILE 2027
// Fichero: PropiedadEditarScreen.tsx
// Ruta: mobile/src/screens/PropiedadEditarScreen.tsx
// Descripción: Editar datos de una propiedad (F06-01 B1 · C-PROP-02; lámina F06-01 v0.1 D3 Editar datos y D4 Conflicto). Corrige nombre, tipo, fecha de adquisición, superficies, habitaciones, baños, garaje, trastero y referencia catastral; la titularidad y el valor tienen su propia pantalla. Solo se envían los campos cambiados (omitido = no cambia; vacío = borrar el dato, null). Con la `row_version` que se vio: si otra sesión cambió la propiedad, D4 «No se ha guardado» con «Recargar», sin mezclar cambios ni sobrescribir en silencio. También exporta `ConflictoPropiedad`, que reutilizan la titularidad y las valoraciones.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// ============================================================

import React, { useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClientePropiedades, VistaPropiedad } from '../api/propiedades';
import { BotonPrimario, BotonTexto } from '../components/Basicos';
import { AvisoCaja, CabeceraTarea, Caja, estilosFormulario as ef } from '../components/Formulario';
import { cambiosDatos, faltaDatos, FormDatos, formDatosDe, TEXTO_INDETERMINADO_PROP, TEXTOS_ERROR_B1, textoErrorB1 } from '../domain/propiedad';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';
import { CamposDatos } from './PropiedadAltaScreen';

export function PropiedadEditarScreen(p: {
  propiedades: ClientePropiedades;
  vista: VistaPropiedad;
  nuevoId: () => string;
  onCerrar: (actualizada: VistaPropiedad | null) => void;
  onRecargar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [f, setF] = useState<FormDatos>(() => formDatosDe(p.vista));
  const [masDatos, setMasDatos] = useState(true);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [conflicto, setConflicto] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const id = useRef(p.nuevoId());
  const faltas = faltaDatos(f);
  const cambios = faltas.length === 0 ? cambiosDatos(p.vista, f) : {};
  const sinCambios = Object.keys(cambios).length === 0;

  const guardar = async () => {
    if (ocupado || faltas.length > 0 || sinCambios) return;
    setOcupado(true);
    setAviso(null);
    const r = await p.propiedades.editarPropiedad(p.vista.id, { intencion_id: id.current, row_version_esperada: p.vista.row_version, ...cambios });
    setOcupado(false);
    if (r.tipo === 'OK') return p.onCerrar(r.datos.propiedad);
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO_PROP });
    if (r.codigo === 'VERSION_DESFASADA') return setConflicto(true);
    setAviso({ tipo: 'AVISO', texto: textoErrorB1(r.codigo, r.mensaje) });
  };

  if (conflicto) return <ConflictoPropiedad titulo="Editar datos" onCancelar={() => p.onCerrar(null)} onRecargar={p.onRecargar} />;

  return (
    <View testID="prop-editar" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea
        titulo="Editar datos"
        testIDCancelar="prop-editar-cancelar"
        onCancelar={() => p.onCerrar(null)}
        derecha={!sinCambios && faltas.length === 0 && !ocupado ? <BotonTexto testID="prop-editar-guardar-cab" titulo="Guardar" onPress={() => void guardar()} /> : null}
      />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        {aviso ? <Caja testID="prop-editar-aviso" aviso={aviso} /> : null}
        <CamposDatos f={f} onCambiar={setF} masDatos={masDatos} onMasDatos={() => setMasDatos(!masDatos)} prefijo="prop-editar" edicion />
        <Text style={[tipo.footnote, { color: c.textSecondary }]}>Corrige datos del inmueble. La titularidad y el valor tienen su propia pantalla.</Text>
        <BotonPrimario
          testID="prop-editar-guardar"
          titulo={ocupado ? 'Guardando…' : 'Guardar'}
          cargando={ocupado}
          deshabilitado={faltas.length > 0 || sinCambios}
          ayuda={faltas.length > 0 ? `Falta: ${faltas.join(', ')}` : sinCambios ? 'No has cambiado nada' : undefined}
          onPress={() => void guardar()}
        />
        {faltas.length > 0 ? <Text testID="prop-editar-falta" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltas.join(', ')}`}</Text> : null}
      </ScrollView>
    </View>
  );
}

/** D4 · Conflicto (D-PROP-08): no se ha guardado; recargar para ver la versión actual. */
export function ConflictoPropiedad(p: { titulo: string; onCancelar: () => void; onRecargar: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View testID="prop-conflicto" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      <CabeceraTarea titulo={p.titulo} testIDCancelar="prop-conflicto-cancelar" onCancelar={p.onCancelar} />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>No se ha guardado</Text>
        <Text testID="prop-conflicto-texto" style={[tipo.body, { color: c.textPrimary }]}>{TEXTOS_ERROR_B1.VERSION_DESFASADA}</Text>
        <BotonPrimario testID="prop-conflicto-recargar" titulo="Recargar" onPress={p.onRecargar} />
      </ScrollView>
    </View>
  );
}
