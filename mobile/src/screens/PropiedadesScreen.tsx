// ============================================================
// GAPTO MOBILE 2027
// Fichero: PropiedadesScreen.tsx
// Ruta: mobile/src/screens/PropiedadesScreen.tsx
// Descripción: Territorio Patrimonio › Propiedades (F06-01 B1; láminas F06-01 v0.9 y v0.1, entradas PAT-02 «+» y PAT-03). Punto de entrada mínimo de B1: lista de propiedades (GET /v1/propiedades) con «+» (alta, A1–A3) y su ficha (D1/D2), y desde la ficha Titularidad (C1, C2), Revisar valor (D3), Histórico de valoraciones (B2) y Editar datos (D3, D4 de la v0.1). Pila propia montada de forma persistente, como Más: «Atrás» vuelve al nivel anterior real; las tareas (alta, nuevo reparto, valoración, edición) son inmersivas y ocultan la barra inferior. Tras una escritura la ficha muestra la vista que devuelve el servidor (sin optimistic update) y la lista se relee. El resto de Patrimonio (PAT-01, cuentas, inversiones) sigue fuera de este bloque.
// Versión: 0.1.0 (F06 Lote 12 · B1 Propiedad, N1)
// Versión: 0.2.0 (F06 T1-F06 B2 N1): la ficha lee también L-COSTE (cliente de patrimonio, por prop opcional; por defecto el de `configApi`) y abre las tareas inmersivas de B2: «Registrar la compra» (CompraScreen, B1–B6) y «Añadir un gasto de la compra» (GastoCompraScreen, C-COMPRA-03). Al cerrar con cambios, la ficha muestra la vista del servidor y relee el coste. Nada más cambia en B1.
// Versión: 0.3.0 (F06 T1-F06 B3 N1): SOLO aditivo: tarea inmersiva «Obras y gastos» (GastosPropiedadScreen de B3, con su cliente `patrimonioB3` por prop opcional; por defecto el de `configApi`). Al cerrar con cambios se relee el coste. Nada más cambia en B1 ni B2.
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi } from '../api/cliente';
import { configApi } from '../api/config';
import { ClientePatrimonio, Coste, crearClientePatrimonio } from '../api/patrimonio';
import { ClientePatrimonioB3, crearClientePatrimonioB3 } from '../api/patrimonio_b3';
import type { ClientePropiedades, FilaPropiedad, VistaPropiedad } from '../api/propiedades';
import { EstadoDato } from '../components/Basicos';
import { estilosFormulario as ef, FilaLista, Tarjeta } from '../components/Formulario';
import { formatearEur } from '../domain/importe';
import { etiquetaTipo, MODOS_TITULARIDAD } from '../domain/propiedad';
import { useTema } from '../theme/tema';
import { espacio, TACTIL_MIN, tipo } from '../theme/tokens';
import { CompraScreen, GastoCompraScreen } from './CompraScreen';
import { GastosPropiedadScreen } from './GastoPropiedadScreen';
import { PropiedadAltaScreen } from './PropiedadAltaScreen';
import { PropiedadEditarScreen } from './PropiedadEditarScreen';
import { PropiedadFichaScreen } from './PropiedadFichaScreen';
import { CambioTitularidadScreen, PropiedadTitularidadScreen } from './PropiedadTitularidadScreen';
import { HistoricoValoracionesScreen, ValoracionFormScreen } from './PropiedadValorScreen';

type Lista = { fase: 'CARGANDO' } | { fase: 'ERROR' } | { fase: 'OK'; filas: FilaPropiedad[] };
type Ficha = { fase: 'CARGANDO'; id: string } | { fase: 'ERROR'; id: string } | { fase: 'OK'; vista: VistaPropiedad };
type Nivel = 'LISTA' | 'FICHA' | 'TITULARIDAD' | 'HISTORICO';
type Tarea = { t: 'ALTA' } | { t: 'EDITAR' } | { t: 'REPARTO' } | { t: 'VALOR' } | { t: 'COMPRA' } | { t: 'GASTO_COMPRA' } | { t: 'GASTOS' };

/** Detalle de la fila de la lista: «Vivienda · Compartida · 245.000,00 €». */
export function detalleFila(f: FilaPropiedad): string {
  const modo = MODOS_TITULARIDAD.find((m) => m.valor === f.modo_titularidad)?.titulo ?? '';
  return [etiquetaTipo(f.tipo_propiedad), modo === 'Aún no lo sé' ? 'Titularidad sin indicar' : modo, f.valor_estimado ? formatearEur(f.valor_estimado.valor_total) : 'Valor no disponible'].join(' · ');
}

export function PropiedadesScreen(p: {
  cliente: ClienteApi;
  propiedades: ClientePropiedades;
  nuevoId: () => string;
  ahora: () => Date;
  onInmersiva: (x: boolean) => void;
  /** B2: cliente de compra y coste (por prop en tests; por defecto, el de `configApi`). */
  patrimonio?: ClientePatrimonio;
  /** B3: cliente de obras y gastos (por prop en tests; por defecto, el de `configApi`). */
  patrimonioB3?: ClientePatrimonioB3;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [lista, setLista] = useState<Lista>({ fase: 'CARGANDO' });
  const [nivel, setNivel] = useState<Nivel>('LISTA');
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [tarea, setTarea] = useState<Tarea | null>(null);
  const patrimonio = useMemo(() => p.patrimonio ?? crearClientePatrimonio(configApi), [p.patrimonio]);
  const patrimonioB3 = useMemo(() => p.patrimonioB3 ?? crearClientePatrimonioB3(configApi), [p.patrimonioB3]);
  const [coste, setCoste] = useState<Coste | null | undefined>(undefined);
  const cargarCoste = useCallback(
    async (id: string) => {
      setCoste(undefined);
      const r = await patrimonio.leerCoste(id);
      setCoste(r.tipo === 'OK' ? r.datos.coste : null);
    },
    [patrimonio],
  );

  const cargarLista = useCallback(
    async (silencioso = false) => {
      if (!silencioso) setLista({ fase: 'CARGANDO' });
      const r = await p.propiedades.listarPropiedades();
      if (r.tipo === 'OK') setLista({ fase: 'OK', filas: r.datos.propiedades });
      else if (!silencioso) setLista({ fase: 'ERROR' });
    },
    [p.propiedades],
  );
  const cargarFicha = useCallback(
    async (id: string) => {
      setFicha({ fase: 'CARGANDO', id });
      const r = await p.propiedades.leerPropiedad(id);
      setFicha(r.tipo === 'OK' ? { fase: 'OK', vista: r.datos.propiedad } : { fase: 'ERROR', id });
      void cargarCoste(id);
    },
    [p.propiedades, cargarCoste],
  );
  useEffect(() => {
    void cargarLista();
  }, [cargarLista]);
  useEffect(() => {
    p.onInmersiva(tarea !== null);
  }, [tarea]);
  useEffect(() => () => p.onInmersiva(false), []);

  const abrir = (id: string) => {
    setNivel('FICHA');
    void cargarFicha(id);
  };
  /** Cierre de una tarea: con la vista nueva del servidor, la ficha la muestra y la lista se relee. */
  const cerrarTarea = (actualizada: VistaPropiedad | null) => {
    setTarea(null);
    if (actualizada) {
      setFicha({ fase: 'OK', vista: actualizada });
      void cargarLista(true);
      void cargarCoste(actualizada.id);
    }
  };
  const recargar = () => {
    setTarea(null);
    if (ficha && ficha.fase === 'OK') void cargarFicha(ficha.vista.id);
  };
  const vista = ficha?.fase === 'OK' ? ficha.vista : null;

  let tareaVista: React.ReactNode = null;
  if (tarea?.t === 'ALTA') {
    tareaVista = (
      <PropiedadAltaScreen
        cliente={p.cliente}
        propiedades={p.propiedades}
        nuevoId={p.nuevoId}
        onCerrar={(creada) => {
          setTarea(null);
          if (creada) {
            void cargarLista(true);
            setFicha({ fase: 'OK', vista: creada });
            setNivel('FICHA');
          }
        }}
      />
    );
  } else if (tarea && vista) {
    if (tarea.t === 'EDITAR') tareaVista = <PropiedadEditarScreen propiedades={p.propiedades} vista={vista} nuevoId={p.nuevoId} onCerrar={cerrarTarea} onRecargar={recargar} />;
    if (tarea.t === 'REPARTO')
      tareaVista = <CambioTitularidadScreen cliente={p.cliente} propiedades={p.propiedades} vista={vista} nuevoId={p.nuevoId} onCerrar={cerrarTarea} onRecargar={recargar} />;
    if (tarea.t === 'VALOR')
      tareaVista = (
        <ValoracionFormScreen propiedades={p.propiedades} vista={vista} nuevoId={p.nuevoId} ahora={p.ahora} onCerrar={cerrarTarea} onRecargar={recargar} />
      );
    if (tarea.t === 'COMPRA')
      tareaVista = <CompraScreen cliente={p.cliente} patrimonio={patrimonio} vista={vista} nuevoId={p.nuevoId} ahora={p.ahora} onCerrar={cerrarTarea} onRecargar={recargar} />;
    if (tarea.t === 'GASTO_COMPRA')
      tareaVista = <GastoCompraScreen cliente={p.cliente} patrimonio={patrimonio} vista={vista} nuevoId={p.nuevoId} ahora={p.ahora} onCerrar={cerrarTarea} onRecargar={recargar} />;
    if (tarea.t === 'GASTOS')
      tareaVista = (
        <GastosPropiedadScreen cliente={p.cliente} patrimonio={patrimonioB3} vista={vista} nuevoId={p.nuevoId} ahora={p.ahora}
          onCerrar={(cambio) => { setTarea(null); if (cambio) void cargarCoste(vista.id); }} />
      );
  }
  if (tareaVista) return <View style={{ flex: 1 }}>{tareaVista}</View>;

  if (nivel !== 'LISTA' && ficha && ficha.fase !== 'OK') {
    return (
      <View testID="prop-ficha-estado" style={{ flex: 1, backgroundColor: c.background, paddingTop: inset.top + espacio.l, paddingHorizontal: espacio.l, gap: espacio.m }}>
        <Pressable testID="prop-ficha-volver" accessibilityRole="button" onPress={() => setNivel('LISTA')} style={{ minHeight: TACTIL_MIN, justifyContent: 'center' }}>
          <Text style={[tipo.body, { color: c.accentText }]}>‹ Propiedades</Text>
        </Pressable>
        {ficha.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
        {ficha.fase === 'ERROR' ? (
          <Pressable testID="prop-ficha-error" accessibilityRole="button" onPress={() => void cargarFicha(ficha.id)} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
      </View>
    );
  }
  if (vista && nivel === 'FICHA')
    return (
      <PropiedadFichaScreen
        vista={vista}
        onAtras={() => setNivel('LISTA')}
        onRevisarValor={() => setTarea({ t: 'VALOR' })}
        onHistorico={() => setNivel('HISTORICO')}
        onTitularidad={() => setNivel('TITULARIDAD')}
        onEditar={() => setTarea({ t: 'EDITAR' })}
        coste={coste}
        onRegistrarCompra={() => setTarea({ t: 'COMPRA' })}
        onGastoCompra={() => setTarea({ t: 'GASTO_COMPRA' })}
        onGastos={() => setTarea({ t: 'GASTOS' })}
      />
    );
  if (vista && nivel === 'TITULARIDAD') return <PropiedadTitularidadScreen vista={vista} onAtras={() => setNivel('FICHA')} onCambiar={() => setTarea({ t: 'REPARTO' })} />;
  if (vista && nivel === 'HISTORICO')
    return (
      <HistoricoValoracionesScreen
        vista={vista}
        onAtras={() => setNivel('FICHA')}
        onNueva={() => setTarea({ t: 'VALOR' })}
      />
    );

  const filas = lista.fase === 'OK' ? lista.filas : [];
  return (
    <View testID="pantalla-propiedades" style={{ flex: 1, backgroundColor: c.background }}>
      <View style={{ paddingTop: inset.top + espacio.l, paddingHorizontal: espacio.l, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text accessibilityRole="header" style={[tipo.titleLarge, { color: c.textPrimary }]}>Patrimonio</Text>
        <Pressable testID="prop-nueva" accessibilityRole="button" accessibilityLabel="Nueva propiedad" hitSlop={8} onPress={() => setTarea({ t: 'ALTA' })} style={ef.mas}>
          <Ionicons name="add" size={26} color={c.accentText} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={[ef.cuerpo, { paddingBottom: inset.bottom + espacio.xxl }]}>
        <Text style={[tipo.titleSmall, { color: c.textPrimary }]}>Propiedades</Text>
        {lista.fase === 'CARGANDO' ? <EstadoDato testID="prop-lista-cargando" estado="CARGANDO" /> : null}
        {lista.fase === 'ERROR' ? (
          <Pressable testID="prop-lista-error" accessibilityRole="button" onPress={() => void cargarLista()} style={{ minHeight: TACTIL_MIN }}>
            <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
          </Pressable>
        ) : null}
        {lista.fase === 'OK' && filas.length === 0 ? (
          <Text testID="prop-lista-vacia" style={[tipo.body, { color: c.textSecondary }]}>Aún no tienes propiedades. Añade la primera con «+».</Text>
        ) : null}
        {filas.length > 0 ? (
          <Tarjeta testID="prop-lista">
            {filas.map((f, i) => (
              <FilaLista key={f.id} testID={`prop-fila-${f.id}`} titulo={f.nombre} detalle={detalleFila(f)} apagada={!f.enabled} ultima={i === filas.length - 1} onPress={() => abrir(f.id)} />
            ))}
          </Tarjeta>
        ) : null}
      </ScrollView>
    </View>
  );
}
