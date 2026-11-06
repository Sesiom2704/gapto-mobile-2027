// ============================================================
// GAPTO MOBILE 2027
// Fichero: PropiedadAltaScreen.tsx
// Ruta: mobile/src/screens/PropiedadAltaScreen.tsx
// Descripción: Alta de propiedad (F06-01 B1 · C-PROP-01; lámina F06-01 v0.9 A1–A3, desde Patrimonio «+»). Tarea inmersiva en tres pasos: A1 Datos (solo nombre y tipo obligatorios, tipo sin preseleccionar, fecha de adquisición opcional con «No la sé», «Más datos» plegados; garaje y trastero «No lo sé» = desconocido), A2 ¿De quién es? (cuatro modos, suma exacta del 100 %, «Desde» propuesta con la adquisición si se conoce) y A3 «Propiedad guardada» con los tres caminos (M-1): registrar la compra y la compra histórica llegan con B2 y aparecen como no disponibles; «Más tarde» deja el coste «no disponible». La `intencion_id` se sella al abrir: un reintento tras un resultado indeterminado reutiliza la MISMA (replay idéntico, sin duplicar). Sin dirección (B5 fuera de B1).
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import type { ClientePropiedades, VistaPropiedad } from '../api/propiedades';
import { BotonPrimario, Chip, EstadoDato } from '../components/Basicos';
import { AvisoCaja, CabeceraTarea, Caja, Campo, CampoTexto, estilosFormulario as ef } from '../components/Formulario';
import { EditorTitularidad } from '../components/Titularidad';
import { ddmmaaaaAIso } from '../domain/fechas';
import {
  datosWire,
  faltaDatos,
  faltaTitularidad,
  FORM_DATOS_VACIO,
  FormDatos,
  FormTitularidad,
  TEXTO_INDETERMINADO_PROP,
  textoErrorB1,
  TIPOS_PROPIEDAD,
  titularidadWire,
  TriEstado,
} from '../domain/propiedad';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

type Paso = 'DATOS' | 'TITULARIDAD' | 'GUARDADA';

export function PropiedadAltaScreen(p: {
  cliente: ClienteApi;
  propiedades: ClientePropiedades;
  nuevoId: () => string;
  onCerrar: (creada: VistaPropiedad | null) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [paso, setPaso] = useState<Paso>('DATOS');
  const [datos, setDatos] = useState<FormDatos>(FORM_DATOS_VACIO);
  const [masDatos, setMasDatos] = useState(false);
  const [tit, setTit] = useState<FormTitularidad>({ modo: null, partes: [], desde: '' });
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);
  const [creada, setCreada] = useState<VistaPropiedad | null>(null);
  /** Identidad del alta, sellada al abrir: el reintento usa la MISMA (C-PROP-01: intencion_id = entidades.id). */
  const idAlta = useRef<string>(p.nuevoId());
  const claves = useRef(0);
  const nuevaClave = () => `p${++claves.current}`;

  const faltasDatos = faltaDatos(datos);
  const adquisicion = datos.adquisicion.trim() ? ddmmaaaaAIso(datos.adquisicion) : null;
  const faltasTit = faltaTitularidad(tit, adquisicion);

  const continuarDatos = () => {
    if (faltasDatos.length > 0) return;
    // «Desde» se propone con la adquisición si se conoce (lámina A2: «fecha de adquisición»), a la vista y editable.
    if (!tit.desde.trim() && datos.adquisicion.trim()) setTit({ ...tit, desde: datos.adquisicion.trim() });
    setPaso('TITULARIDAD');
  };

  const guardar = async () => {
    if (ocupado || faltasTit.length > 0 || faltasDatos.length > 0) return;
    setOcupado(true);
    setAviso(null);
    const r = await p.propiedades.altaPropiedad({ intencion_id: idAlta.current, ...datosWire(datos), titularidad: titularidadWire(tit) });
    setOcupado(false);
    if (r.tipo === 'OK') {
      setCreada(r.datos.propiedad);
      return setPaso('GUARDADA');
    }
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: `${TEXTO_INDETERMINADO_PROP} Si vuelves a guardar sin cambiar nada, no se duplicará.` });
    setAviso({ tipo: 'AVISO', texto: textoErrorB1(r.codigo, r.mensaje) });
  };

  if (paso === 'GUARDADA' && creada) {
    return (
      <View testID="prop-alta-guardada" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Nueva propiedad" testIDCancelar="prop-alta-cerrar" onCancelar={() => p.onCerrar(creada)} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          <Text accessibilityRole="header" style={[tipo.titleMedium, { color: c.textPrimary }]}>Propiedad guardada</Text>
          <Text testID="prop-alta-guardada-texto" style={[tipo.body, { color: c.textPrimary }]}>{`«${creada.nombre}» ya está guardada.`}</Text>
          <Text style={[tipo.body, { color: c.textSecondary }]}>¿Quieres registrar ahora cómo la compraste?</Text>
          {[
            ['compra', 'Registrar la compra', 'Precio, cómo se pagó y gastos (impuestos, notaría…)'],
            ['historica', 'La compré hace tiempo', 'Anota el importe total sin detalle de pagos'],
          ].map(([k, t, d]) => (
            <View key={k} testID={`prop-alta-camino-${k}`} accessibilityState={{ disabled: true }} style={[s.camino, { borderColor: c.borderDefault, backgroundColor: c.surfacePrimary }]}>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={[tipo.body, { color: c.textSecondary }]}>{t}</Text>
                <Text style={[tipo.caption, { color: c.textSecondary }]}>{d}</Text>
              </View>
              <EstadoDato estado="NO_DISPONIBLE" detalle="Llega con la compra" />
            </View>
          ))}
          <View testID="prop-alta-camino-tarde" style={[s.camino, { borderColor: c.accent, backgroundColor: c.accentSurface }]}>
            <Ionicons name="radio-button-on" size={20} color={c.accentText} />
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[tipo.body, { color: c.textPrimary, fontWeight: '600' }]}>Más tarde</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>El coste quedará «no disponible»</Text>
            </View>
          </View>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>El valor de mercado o de tasación se añade aparte, en «Revisar valor».</Text>
          <BotonPrimario testID="prop-alta-continuar-final" titulo="Continuar" onPress={() => p.onCerrar(creada)} />
        </ScrollView>
      </View>
    );
  }

  const enDatos = paso === 'DATOS';
  return (
    <View testID="prop-alta" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
      {enDatos ? (
        <CabeceraTarea titulo="Nueva propiedad" testIDCancelar="prop-alta-cancelar" onCancelar={() => p.onCerrar(null)} />
      ) : (
        <CabeceraAtras titulo="Nueva propiedad" onAtras={() => setPaso('DATOS')} />
      )}
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]} keyboardShouldPersistTaps="handled">
        <Text testID="prop-alta-paso" style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>
          {enDatos ? 'Paso 1 de 2 · Datos' : 'Paso 2 de 2 · ¿De quién es?'}
        </Text>
        {aviso ? <Caja testID="prop-alta-aviso" aviso={aviso} /> : null}
        {enDatos ? (
          <>
            <CamposDatos f={datos} onCambiar={setDatos} masDatos={masDatos} onMasDatos={() => setMasDatos(!masDatos)} prefijo="prop-alta" />
            <BotonPrimario
              testID="prop-alta-continuar"
              titulo="Continuar"
              deshabilitado={faltasDatos.length > 0}
              ayuda={faltasDatos.length > 0 ? `Falta: ${faltasDatos.join(', ')}` : undefined}
              onPress={continuarDatos}
            />
            {faltasDatos.length > 0 ? <Text testID="prop-alta-falta" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltasDatos.join(', ')}`}</Text> : null}
          </>
        ) : (
          <>
            <EditorTitularidad cliente={p.cliente} form={tit} onCambiar={setTit} nuevaClave={nuevaClave} ayudaDesde={adquisicion ? 'fecha de adquisición' : undefined} />
            <BotonPrimario
              testID="prop-alta-guardar"
              titulo={ocupado ? 'Guardando…' : 'Guardar propiedad'}
              cargando={ocupado}
              deshabilitado={faltasTit.length > 0}
              ayuda={faltasTit.length > 0 ? `Falta: ${faltasTit.join(', ')}` : undefined}
              onPress={() => void guardar()}
            />
            {faltasTit.length > 0 ? <Text testID="prop-alta-falta-tit" style={[tipo.footnote, { color: c.textSecondary }]}>{`Falta: ${faltasTit.join(', ')}`}</Text> : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

/** Cabecera de un paso posterior de una tarea: «‹ Atrás» · título. */
export function CabeceraAtras(p: { titulo: string; onAtras: () => void; etiqueta?: string; testID?: string; derecha?: React.ReactNode }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  return (
    <View style={[s.cab, { paddingTop: inset.top + espacio.s, borderBottomColor: c.borderDefault }]}>
      <Pressable testID={p.testID ?? 'prop-atras'} accessibilityRole="button" accessibilityLabel={`Atrás: ${p.etiqueta ?? 'Atrás'}`} hitSlop={8} onPress={p.onAtras} style={s.atras}>
        <Ionicons name="chevron-back" size={18} color={c.accentText} />
        <Text style={[tipo.body, { color: c.accentText }]}>{p.etiqueta ?? 'Atrás'}</Text>
      </Pressable>
      <Text accessibilityRole="header" numberOfLines={1} style={[tipo.titleSmall, { color: c.textPrimary, flexShrink: 1 }]}>{p.titulo}</Text>
      <View style={{ minWidth: 72, alignItems: 'flex-end' }}>{p.derecha}</View>
    </View>
  );
}

/** Campos de datos de la propiedad (A1 y edición D3). «Más datos» pliega superficies, habitaciones, baños, garaje y trastero. */
export function CamposDatos(p: { f: FormDatos; onCambiar: (f: FormDatos) => void; masDatos: boolean; onMasDatos: () => void; prefijo: string; edicion?: boolean }) {
  const { c } = useTema();
  const f = p.f;
  const set = (x: Partial<FormDatos>) => p.onCambiar({ ...f, ...x });
  const sinFecha = !f.adquisicion.trim();
  return (
    <>
      <Campo etiqueta="Nombre">
        <CampoTexto testID={`${p.prefijo}-nombre`} etiqueta="Nombre" marcador="Ej.: Piso Calle Mayor" valor={f.nombre} maximo={160} onCambiar={(t) => set({ nombre: t })} />
      </Campo>
      <Campo etiqueta="Tipo">
        <View style={ef.chips}>
          {TIPOS_PROPIEDAD.map((t) => (
            <Chip key={t.valor} testID={`${p.prefijo}-tipo-${t.valor}`} etiqueta={t.etiqueta} seleccionado={f.tipo === t.valor} onPress={() => set({ tipo: t.valor })} />
          ))}
        </View>
      </Campo>
      <Campo etiqueta="Fecha de adquisición" opcional>
        <View style={{ flexDirection: 'row', gap: espacio.s, alignItems: 'center' }}>
          <View style={{ flex: 1 }}>
            <CampoTexto testID={`${p.prefijo}-adquisicion`} etiqueta="Fecha de adquisición" marcador="dd/mm/aaaa" valor={f.adquisicion} onCambiar={(t) => set({ adquisicion: t })} />
          </View>
          <Chip testID={`${p.prefijo}-adquisicion-nolase`} etiqueta="No la sé" seleccionado={sinFecha} onPress={() => set({ adquisicion: '' })} />
        </View>
      </Campo>
      <Pressable testID={`${p.prefijo}-mas-datos`} accessibilityRole="button" accessibilityState={{ expanded: p.masDatos }} onPress={p.onMasDatos} style={[s.mas, { borderColor: c.borderDefault, backgroundColor: c.surfacePrimary }]}>
        <View style={{ flex: 1 }}>
          <Text style={[tipo.body, { color: c.textPrimary }]}>Más datos</Text>
          <Text style={[tipo.caption, { color: c.textSecondary }]}>Superficies, habitaciones, baños, garaje, trastero</Text>
        </View>
        <Ionicons name={p.masDatos ? 'chevron-down' : 'chevron-forward'} size={18} color={c.textSecondary} />
      </Pressable>
      {p.masDatos ? (
        <View testID={`${p.prefijo}-mas-datos-cuerpo`} style={{ gap: espacio.l }}>
          <Campo etiqueta="Superficie útil (m²)" opcional>
            <CampoTexto testID={`${p.prefijo}-superficie`} etiqueta="Superficie útil" marcador="Ej.: 72,40" valor={f.superficie} onCambiar={(t) => set({ superficie: t })} />
          </Campo>
          <Campo etiqueta="Superficie construida (m²)" opcional>
            <CampoTexto testID={`${p.prefijo}-construida`} etiqueta="Superficie construida" marcador="Ej.: 85,00" valor={f.superficieConstruida} onCambiar={(t) => set({ superficieConstruida: t })} />
          </Campo>
          <View style={{ flexDirection: 'row', gap: espacio.m }}>
            <View style={{ flex: 1 }}>
              <Campo etiqueta="Habitaciones" opcional>
                <CampoTexto testID={`${p.prefijo}-habitaciones`} etiqueta="Habitaciones" marcador="—" valor={f.habitaciones} onCambiar={(t) => set({ habitaciones: t })} />
              </Campo>
            </View>
            <View style={{ flex: 1 }}>
              <Campo etiqueta="Baños" opcional>
                <CampoTexto testID={`${p.prefijo}-banos`} etiqueta="Baños" marcador="—" valor={f.banos} onCambiar={(t) => set({ banos: t })} />
              </Campo>
            </View>
          </View>
          <TriCampo etiqueta="Garaje" valor={f.garaje} onCambiar={(v) => set({ garaje: v })} testID={`${p.prefijo}-garaje`} />
          <TriCampo etiqueta="Trastero" valor={f.trastero} onCambiar={(v) => set({ trastero: v })} testID={`${p.prefijo}-trastero`} />
          {p.edicion ? (
            <Campo etiqueta="Referencia catastral" opcional>
              <CampoTexto testID={`${p.prefijo}-catastral`} etiqueta="Referencia catastral" marcador="20 caracteres" valor={f.referenciaCatastral} maximo={50} onCambiar={(t) => set({ referenciaCatastral: t })} />
            </Campo>
          ) : null}
        </View>
      ) : null}
    </>
  );
}

/** Sí / No / No lo sé: «No lo sé» se guarda como desconocido (null), no como «No». */
function TriCampo(p: { etiqueta: string; valor: TriEstado; onCambiar: (v: TriEstado) => void; testID: string }) {
  return (
    <Campo etiqueta={p.etiqueta} opcional>
      <View style={ef.chips}>
        {([[true, 'Sí'], [false, 'No'], [null, 'No lo sé']] as const).map(([v, e]) => (
          <Chip key={e} testID={`${p.testID}-${v === null ? 'nolose' : v ? 'si' : 'no'}`} etiqueta={e} seleccionado={p.valor === v} onPress={() => p.onCambiar(v)} />
        ))}
      </View>
    </Campo>
  );
}

const s = StyleSheet.create({
  camino: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.m, padding: espacio.m, minHeight: TACTIL_MIN + 8 },
  mas: { flexDirection: 'row', alignItems: 'center', gap: espacio.m, borderWidth: 1, borderRadius: radio.m, padding: espacio.m, minHeight: TACTIL_MIN + 8 },
  cab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: espacio.l, paddingBottom: espacio.s, borderBottomWidth: StyleSheet.hairlineWidth, gap: espacio.s },
  atras: { flexDirection: 'row', alignItems: 'center', minHeight: TACTIL_MIN, minWidth: 72 },
});
