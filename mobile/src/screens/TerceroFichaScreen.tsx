// ============================================================
// GAPTO MOBILE 2027
// Fichero: TerceroFichaScreen.tsx
// Ruta: mobile/src/screens/TerceroFichaScreen.tsx
// Descripción: Ficha de tercero con roles, clasificación y «Uso en Gapto» (F06-02/03; lámina CON v0.8 E1, E2 y E6; contrato N1 v1.1 L-TER-01, C-TER-01 y C-TER-03; Q-CON-13: se pueden AÑADIR y editar, NO retirar). E1 muestra los roles fijos (sin «Quitar»), la naturaleza y el uso (contratos en los que participa, con rol y vigencia; navega, no suma importes). E2 «Añadir roles»: los que ya tiene salen bloqueados y aparece el aviso «En esta versión un rol añadido no se puede quitar» antes de guardar; todos los roles del catálogo son visibles (Q-CON-12); nada viene marcado. E6 clasificación: se añade, no se quita («Una clasificación asignada no se puede quitar a una persona»; desactivarla en la lista afecta a todos). Sin direcciones: C-TER-02 y E4/E5 quedan fuera de este bloque. AGENCIA y ADMINISTRADOR no son roles de tercero.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClasificacionTercero, ClienteContratos, FichaTercero, RolTercero } from '../api/contratos';
import { BotonPrimario, BotonTexto, CabeceraNavegacion, Chip, EstadoDato } from '../components/Basicos';
import { AvisoCaja, CabeceraTarea, Caja, estilosFormulario as ef, FilaLista, RotuloGrupo } from '../components/Formulario';
import { FilaInfo, OpcionFila } from '../components/OpcionesContrato';
import {
  NOMBRE_ROL_MIN, NOMBRE_ROL_TERCERO, ROLES_TERCERO, textoErrorContrato, textoNaturaleza, TEXTO_CLASIFICACION_AYUDA, TEXTO_ROL_NO_SE_QUITA, TEXTO_ROLES_FIJOS,
} from '../domain/contratos';
import { diaMesAnioIso } from '../domain/fechas';
import { useTema } from '../theme/tema';
import { espacio, tipo } from '../theme/tokens';

const TEXTO_INDETERMINADO = 'No se ha podido confirmar el cambio. Vuelve a cargar la ficha antes de repetirlo.';

export function TerceroFichaScreen(p: {
  contratos: ClienteContratos;
  terceroId: string;
  nuevoId: () => string;
  etiquetaAtras?: string;
  onAtras: () => void;
  onContrato?: (contratoId: string) => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [f, setF] = useState<FichaTercero | null>(null);
  const [error, setError] = useState(false);
  const [vista, setVista] = useState<'FICHA' | 'ROLES' | 'CLASIFICACION'>('FICHA');
  const [rolesElegidos, setRolesElegidos] = useState<RolTercero[]>([]);
  const [lista, setLista] = useState<ClasificacionTercero[] | null>(null);
  const [clasifElegidas, setClasifElegidas] = useState<string[]>([]);
  const [principal, setPrincipal] = useState<string | null>(null);
  const [aviso, setAviso] = useState<AvisoCaja>(null);
  const [ocupado, setOcupado] = useState(false);
  const intencion = useRef<Record<string, string>>({});

  const cargar = useCallback(async () => {
    setError(false);
    const r = await p.contratos.fichaTercero(p.terceroId);
    if (r.tipo === 'OK') setF(r.datos);
    else setError(true);
  }, [p.terceroId]);
  useEffect(() => { void cargar(); }, [cargar]);

  const volver = () => { setVista('FICHA'); setAviso(null); };
  const enviar = async (clave: string, hacer: (id: string) => Promise<import('../api/cliente').Respuesta<unknown>>) => {
    if (ocupado) return;
    setOcupado(true);
    setAviso(null);
    intencion.current[clave] ??= p.nuevoId();
    const r = await hacer(intencion.current[clave]);
    setOcupado(false);
    if (r.tipo === 'OK') {
      setRolesElegidos([]); setClasifElegidas([]); setPrincipal(null);
      await cargar();
      return volver();
    }
    if (r.tipo === 'INDETERMINADO') return setAviso({ tipo: 'AVISO', texto: TEXTO_INDETERMINADO });
    delete intencion.current[clave];
    setAviso({ tipo: 'AVISO', texto: textoErrorContrato(r.codigo, r.mensaje, r.detalle) });
    if (r.codigo === 'VERSION_DESFASADA') void cargar();
  };

  // ---------------- E2 · añadir roles
  if (f && vista === 'ROLES') {
    const tiene = f.roles;
    const posibles = ROLES_TERCERO.filter((r) => !tiene.includes(r));
    return (
      <View testID="tercero-roles" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Añadir roles" testIDCancelar="tercero-roles-cancelar" onCancelar={volver} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          {aviso ? <Caja testID="tercero-aviso" aviso={aviso} /> : null}
          <Text style={[tipo.titleSmall, { color: c.textPrimary }]}>{f.tercero.nombre}</Text>
          <RotuloGrupo texto="Ya tiene" />
          {tiene.map((r) => (
            <View key={r} testID={`tercero-rol-tiene-${r}`} style={s.fijo}>
              <Text style={[tipo.body, { color: c.textSecondary, flex: 1 }]}>{NOMBRE_ROL_TERCERO[r]}</Text>
              <Ionicons name="lock-closed-outline" size={16} color={c.textSecondary} />
            </View>
          ))}
          <RotuloGrupo texto="Puedes añadir" />
          <View style={ef.chips}>
            {posibles.map((r) => (
              <Chip key={r} testID={`tercero-rol-${r}`} etiqueta={NOMBRE_ROL_TERCERO[r]} seleccionado={rolesElegidos.includes(r)}
                onPress={() => setRolesElegidos((l) => (l.includes(r) ? l.filter((x) => x !== r) : [...l, r]))} />
            ))}
          </View>
          <Text testID="tercero-roles-aviso" style={[tipo.footnote, { color: c.warningText }]}>{TEXTO_ROL_NO_SE_QUITA}</Text>
          <BotonPrimario testID="tercero-roles-guardar" titulo={rolesElegidos.length === 1 ? 'Añadir 1 rol' : `Añadir ${rolesElegidos.length} roles`} cargando={ocupado} deshabilitado={rolesElegidos.length === 0}
            onPress={() => void enviar(`roles|${[...rolesElegidos].sort().join(',')}`, (id) => p.contratos.anadirRoles(f.tercero.id, { intencion_id: id, row_version_esperada: f.tercero.row_version, anadir: rolesElegidos }))} />
        </ScrollView>
      </View>
    );
  }

  // ---------------- E6 · añadir clasificación
  if (f && vista === 'CLASIFICACION') {
    const asignadas = f.clasificaciones.map((x) => x.clasificacion_id);
    const posibles = (lista ?? []).filter((x) => x.enabled && !asignadas.includes(x.clasificacion_id));
    const unica = clasifElegidas.length === 1 ? clasifElegidas[0] : null;
    return (
      <View testID="tercero-clasificacion" style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
        <CabeceraTarea titulo="Clasificación" testIDCancelar="tercero-clasificacion-cancelar" onCancelar={volver} />
        <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
          {aviso ? <Caja testID="tercero-aviso" aviso={aviso} /> : null}
          {lista === null ? <EstadoDato estado="CARGANDO" /> : null}
          {posibles.map((x) => (
            <OpcionFila key={x.clasificacion_id} testID={`tercero-clasificacion-${x.clasificacion_id}`} titulo={x.nombre} seleccionada={clasifElegidas.includes(x.clasificacion_id)}
              onPress={() => setClasifElegidas((l) => { const n = l.includes(x.clasificacion_id) ? l.filter((q) => q !== x.clasificacion_id) : [...l, x.clasificacion_id]; if (principal && !n.includes(principal)) setPrincipal(null); return n; })} />
          ))}
          {lista !== null && posibles.length === 0 ? <Text testID="tercero-clasificacion-vacia" style={[tipo.footnote, { color: c.textSecondary }]}>No hay más clasificaciones que añadir.</Text> : null}
          {unica ? <Chip testID="tercero-clasificacion-principal" etiqueta="Marcar como principal" seleccionado={principal === unica} onPress={() => setPrincipal(principal === unica ? null : unica)} /> : null}
          <Text testID="tercero-clasificacion-ayuda" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CLASIFICACION_AYUDA}</Text>
          <BotonPrimario testID="tercero-clasificacion-guardar" titulo="Añadir" cargando={ocupado} deshabilitado={clasifElegidas.length === 0}
            onPress={() => void enviar(`clasif|${[...clasifElegidas].sort().join(',')}|${principal ?? ''}`, (id) => p.contratos.anadirClasificacion(f.tercero.id, { intencion_id: id, row_version_esperada: f.tercero.row_version, anadir: clasifElegidas, principal }))} />
        </ScrollView>
      </View>
    );
  }

  // ---------------- E1 · ficha
  return (
    <View testID="tercero-ficha" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraNavegacion titulo={f?.tercero.nombre ?? 'Tercero'} atras={{ etiqueta: p.etiquetaAtras ?? 'Terceros', onPress: p.onAtras }} testIDAtras="tercero-ficha-atras" />
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        {f === null && !error ? <EstadoDato estado="CARGANDO" testID="tercero-cargando" /> : null}
        {error ? <BotonTexto testID="tercero-error" titulo="No se pudo cargar. Tocar para reintentar" onPress={() => void cargar()} /> : null}
        {f ? (
          <>
            <RotuloGrupo texto="Identidad" />
            <FilaInfo testID="tercero-naturaleza" etiqueta="Naturaleza" valor={textoNaturaleza(f.tercero.naturaleza)} />
            <View style={s.cabRoles}>
              <RotuloGrupo texto="Roles" />
              <BotonTexto testID="tercero-roles-abrir" titulo="+ Añadir" onPress={() => { setAviso(null); setRolesElegidos([]); setVista('ROLES'); }} />
            </View>
            <View style={ef.chips}>
              {f.roles.map((r) => (
                <View key={r} testID={`tercero-rol-fijo-${r}`} style={[s.rolFijo, { backgroundColor: c.surfaceSecondary }]}>
                  <Text style={[tipo.subheadline, { color: c.textSecondary }]}>{NOMBRE_ROL_TERCERO[r]}</Text>
                </View>
              ))}
              {f.roles.length === 0 ? <Text testID="tercero-sin-roles" style={[tipo.footnote, { color: c.textSecondary }]}>Sin roles todavía.</Text> : null}
            </View>
            <Text testID="tercero-roles-fijos" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_ROLES_FIJOS}</Text>

            <View style={s.cabRoles}>
              <RotuloGrupo texto="Clasificación" />
              <BotonTexto testID="tercero-clasificacion-abrir" titulo="+ Añadir" onPress={() => {
                setAviso(null); setClasifElegidas([]); setPrincipal(null); setVista('CLASIFICACION');
                if (lista === null) void p.contratos.clasificacionesTercero().then((r) => setLista(r.tipo === 'OK' ? r.datos.clasificaciones : []));
              }} />
            </View>
            {f.clasificaciones.map((x) => (
              <FilaInfo key={x.clasificacion_id} testID={`tercero-clasif-${x.clasificacion_id}`} etiqueta={x.nombre} valor={x.principal ? 'Principal' : ''} />
            ))}
            <Text testID="tercero-clasificacion-nota" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_CLASIFICACION_AYUDA}</Text>

            <RotuloGrupo texto="Uso en Gapto" />
            {f.uso.length === 0 ? <Text testID="tercero-sin-uso" style={[tipo.body, { color: c.textSecondary }]}>Sin uso</Text> : null}
            {f.uso.map((u) => (
              <FilaLista key={`${u.contrato_id}-${u.rol}`} testID={`tercero-uso-${u.contrato_id}`} titulo={`Contrato ${u.contrato_nombre}`}
                detalle={`${NOMBRE_ROL_MIN[u.rol][0].toUpperCase()}${NOMBRE_ROL_MIN[u.rol].slice(1)} · desde ${diaMesAnioIso(u.desde)}${u.hasta ? ` hasta ${diaMesAnioIso(u.hasta)}` : ''}`}
                onPress={() => p.onContrato?.(u.contrato_id)} />
            ))}
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  fijo: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, paddingVertical: espacio.xs },
  cabRoles: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  rolFijo: { borderRadius: 999, paddingHorizontal: espacio.m, paddingVertical: espacio.xs, minHeight: 32, justifyContent: 'center' },
});
