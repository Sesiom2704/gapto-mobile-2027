// ============================================================
// GAPTO MOBILE 2027
// Fichero: GuardarPlantilla.tsx
// Ruta: mobile/src/components/GuardarPlantilla.tsx
// Descripción: «Guardar como plantilla…» desde la pantalla de éxito del registro (F05-03 J2 §2.4; F05 §45.3; lámina SET-PLT / REG-PLT v0.2 R05/R06). Hoja «Nueva plantilla»: Nombre OBLIGATORIO y nunca autocompletado (marcador «Ej.: Compra semanal»); «Qué guardar» con una casilla por valor del registro (tercero, categoría, contexto, cuenta y presupuesto), marcadas por defecto; «Mostrar en Inicio» con los huecos libres; «Guardar plantilla» desactivado con «Falta: nombre» o si no se guarda nada. Escritura INDEPENDIENTE y posterior al hecho: el registro nunca se ve afectado. UUID de la plantilla y del acceso sellados al abrir la hoja (el reintento usa los MISMOS). Nombre repetido → S04; límite de Inicio → S03 (la plantilla queda guardada); fallo → aviso con «Reintentar».
// Versión: 0.1.0 (F05-03/F05-04 J2 §2.4)
// ============================================================

import React, { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { AccionRapida, ClienteApi, TiposRegistro } from '../api/cliente';
import { huecosLibres, textoHuecos } from '../domain/maestros';
import { LONGITUD_NOMBRE_PLANTILLA, nombreAcceso, TEXTO_LIMITE, textoNombreRepetido } from '../domain/plantillas';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, Segmentado } from './Basicos';
import { AvisoCaja, Caja, CampoTexto } from './Formulario';
import { Hoja } from './HojasCategoria';
import { BotonSecundario } from './SelectorCategorias';

export interface ValoresRegistro {
  categoriaId: string | null;
  categoriaNombre: string | null;
  cuentaId: string | null;
  cuentaNombre: string | null;
  presupuestable: boolean | null;
  terceroId: string | null;
  terceroNombre: string | null;
  contextoId: string | null;
  contextoNombre: string | null;
}

type Clave = 'tercero' | 'categoria' | 'contexto' | 'cuenta' | 'presupuestable';
/** DERIVADO. */
export const TEXTO_PLANTILLA_GUARDADA = 'Plantilla guardada';
/** DERIVADO. */
export const TEXTO_PLANTILLA_ERROR = 'No se pudo guardar la plantilla. El registro sí está guardado. Puedes reintentarlo o crearla en Ajustes › Plantillas.';

export function GuardarPlantilla(p: { cliente: ClienteApi; nuevoId: () => string; tipo: 'GASTO' | 'INGRESO'; valores: ValoresRegistro; onCerrar: () => void }) {
  const { c } = useTema();
  const v = p.valores;
  const ids = useRef({ plantilla: p.nuevoId(), accion: p.nuevoId() });
  const disponibles: { clave: Clave; texto: string }[] = [
    ...(v.terceroId ? [{ clave: 'tercero' as const, texto: `Tercero: ${v.terceroNombre ?? ''}` }] : []),
    ...(v.categoriaId ? [{ clave: 'categoria' as const, texto: `Categoría: ${v.categoriaNombre ?? ''}` }] : []),
    ...(v.contextoId ? [{ clave: 'contexto' as const, texto: `Contexto: ${v.contextoNombre ?? ''}` }] : []),
    ...(v.cuentaId ? [{ clave: 'cuenta' as const, texto: `${p.tipo === 'INGRESO' ? 'Cobrado en' : 'Pagar con'}: ${v.cuentaNombre ?? ''}` }] : []),
    ...(v.presupuestable !== null ? [{ clave: 'presupuestable' as const, texto: `Cuenta para el presupuesto: ${v.presupuestable ? 'Sí' : 'No'}` }] : []),
  ];
  const [nombre, setNombre] = useState('');
  const [marcadas, setMarcadas] = useState<Set<Clave>>(new Set(disponibles.map((x) => x.clave)));
  const [enInicio, setEnInicio] = useState(false);
  const [acciones, setAcciones] = useState<AccionRapida[] | null>(null);
  const [tipos, setTipos] = useState<TiposRegistro | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja & { reintentar?: boolean } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [hecha, setHecha] = useState<'PLANTILLA' | null>(null);

  useEffect(() => {
    void (async () => {
      const [l, pr] = await Promise.all([p.cliente.listarPlantillas(), p.cliente.listarPreferencias()]);
      if (l.tipo === 'OK') setAcciones(l.datos.acciones);
      if (pr.tipo === 'OK') setTipos(pr.datos.tipos);
    })();
  }, []);

  const falta = !nombre.trim() ? 'Falta: nombre' : marcadas.size === 0 ? 'Falta: elegir qué guardar' : null;
  const guardar = async () => {
    if (ocupado || falta || !tipos) return;
    setOcupado(true);
    setAviso(null);
    let plantillaOk = hecha === 'PLANTILLA';
    if (!plantillaOk) {
      const r = await p.cliente.altaPlantilla({
        id: ids.current.plantilla,
        nombre: nombre.trim(),
        tipo_hecho_id: tipos[p.tipo],
        tercero_id: marcadas.has('tercero') ? v.terceroId : null,
        categoria_id: marcadas.has('categoria') ? v.categoriaId : null,
        entidad_id: marcadas.has('contexto') ? v.contextoId : null,
        cuenta_default_id: marcadas.has('cuenta') ? v.cuentaId : null,
        presupuestable_default: marcadas.has('presupuestable') ? v.presupuestable : null,
      });
      if (r.tipo !== 'OK') {
        setOcupado(false);
        if (r.tipo === 'RECHAZADO' && r.codigo === 'PLANTILLA_NOMBRE_REPETIDO') return setAviso({ tipo: 'AVISO', texto: textoNombreRepetido(nombre.trim()) });
        return setAviso({ tipo: 'AVISO', texto: TEXTO_PLANTILLA_ERROR, reintentar: true });
      }
      plantillaOk = true;
      setHecha('PLANTILLA');
    }
    if (enInicio) {
      const ra = await p.cliente.altaAccion({ id: ids.current.accion, plantilla_registro_id: ids.current.plantilla, nombre: nombreAcceso({ nombre, nombreCorto: '' }), icono_key: null });
      setOcupado(false);
      if (ra.tipo !== 'OK') {
        if (ra.tipo === 'RECHAZADO' && ra.codigo === 'ACCION_LIMITE_ALCANZADO') return setAviso({ tipo: 'AVISO', texto: `${TEXTO_PLANTILLA_GUARDADA}. ${TEXTO_LIMITE}` });
        return setAviso({ tipo: 'AVISO', texto: `${TEXTO_PLANTILLA_GUARDADA}. No se pudo añadir a Inicio.`, reintentar: true });
      }
    }
    setOcupado(false);
    setAviso({ tipo: 'OK', texto: TEXTO_PLANTILLA_GUARDADA });
  };

  const libres = acciones ? huecosLibres(acciones) : null;
  const terminado = aviso?.tipo === 'OK';
  return (
    <Hoja titulo="Nueva plantilla" testID="guardar-plantilla">
      <ScrollView style={{ maxHeight: 520 }} keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: espacio.m }}>
        <CampoTexto testID="plantilla-nombre" etiqueta="Nombre" marcador="Ej.: Compra semanal" valor={nombre} maximo={LONGITUD_NOMBRE_PLANTILLA}
          onCambiar={(t) => { if (hecha) return; setNombre(t); }} />
        <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Qué guardar</Text>
        {disponibles.map((x) => (
          <Pressable
            key={x.clave}
            testID={`plantilla-casilla-${x.clave}`}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: marcadas.has(x.clave), disabled: !!hecha }}
            accessibilityLabel={x.texto}
            disabled={!!hecha}
            onPress={() => setMarcadas((m) => { const n = new Set(m); if (n.has(x.clave)) n.delete(x.clave); else n.add(x.clave); return n; })}
            style={s.casilla}
          >
            <View style={[s.caja18, { borderColor: marcadas.has(x.clave) ? c.accent : c.borderStandard, backgroundColor: marcadas.has(x.clave) ? c.accent : c.surfacePrimary }]}>
              {marcadas.has(x.clave) ? <Text style={[tipo.caption, { color: c.onAccent }]}>✓</Text> : null}
            </View>
            <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{x.texto}</Text>
          </Pressable>
        ))}
        <Text style={[tipo.footnote, { color: c.textSecondary, fontWeight: '600' }]}>Mostrar en Inicio</Text>
        <Segmentado<boolean>
          testIDBase="plantilla-inicio"
          etiquetaGrupo="Mostrar en Inicio"
          opciones={[{ valor: true, etiqueta: 'Sí' }, { valor: false, etiqueta: 'No' }]}
          valor={enInicio}
          onCambiar={setEnInicio}
        />
        {libres !== null ? <Text testID="plantilla-huecos" style={[tipo.footnote, { color: c.textSecondary }]}>{textoHuecos(libres)}</Text> : null}
        {aviso ? <Caja testID={aviso.tipo === 'OK' ? 'plantilla-aviso-ok' : 'plantilla-aviso'} aviso={aviso} /> : null}
        {falta && !terminado ? <Text testID="plantilla-falta" style={[tipo.footnote, { color: c.textSecondary }]}>{falta}</Text> : null}
        {terminado ? null : (
          <BotonPrimario testID="plantilla-guardar" titulo={aviso?.reintentar ? 'Reintentar' : ocupado ? 'Guardando…' : 'Guardar plantilla'} cargando={ocupado}
            deshabilitado={!!falta || !tipos} ayuda={falta ?? undefined} onPress={() => void guardar()} />
        )}
        <BotonSecundario testID="plantilla-cerrar" titulo={terminado ? 'Cerrar' : 'Cancelar'} onPress={p.onCerrar} />
      </ScrollView>
    </Hoja>
  );
}

const s = StyleSheet.create({
  casilla: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN },
  caja18: { width: 20, height: 20, borderRadius: radio.s, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
});
