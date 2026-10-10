// ============================================================
// GAPTO MOBILE 2027
// Fichero: App.tsx
// Ruta: mobile/App.tsx
// Descripción: Raíz del cliente. Navegación mínima propia de VS-01 (decisión de ejecución: sin librería de navegación hasta F11-00): cinco destinos persistentes montados (conservan su contexto al cambiar de pestaña) y una tarea inmersiva CREATE superpuesta que oculta la barra inferior (F09 BLOQUE A). Tras un registro confirmado, Inicio vuelve a leer del backend (sin optimistic update).
// v0.2.0 (F05-01 S6-WIRE+UI (este mandato); D-UI-03, F09 §12.91.1/§12.97.4): el destino MAS deja de ser territorio pendiente: Más → Ajustes (10 secciones; solo Categorías operativa) → Categorías. Las listas conservan la barra inferior; las tareas inmersivas de Ajustes (alta CREATE-M y selectores) la ocultan, igual que la tarea de registro. «Atrás» vuelve al nivel anterior real; la pila de Más conserva su contexto al cambiar de pestaña. Los otros tres territorios siguen pendientes.
// v0.3.0 (F05-02 B3, A1; D-B3-01): Ajustes › «Preferencias financieras» abre Ajustes › Preferencias (PreferenciasAjustesScreen) en la pila de Más, como Categorías; sus formularios y el selector de categoría son tareas inmersivas (ocultan la barra inferior).
// v0.4.0 (F05-03/F05-04 J2 §2.5): Ajustes › Terceros, Contextos y Plantillas en la pila de Más, como Preferencias; sus formularios y selectores son tareas inmersivas.
// v0.5.0 (F05-03/F05-04 J2+J3 §2.1–§2.4): «Registrar» de Inicio abre la hoja de tipos (sin preselección); Gasto e Ingreso abren el registro con ese tipo, «Entre cuentas» la pantalla de transferencia. Un acceso de Inicio abre el registro del tipo de su plantilla con la plantilla aplicada. El cambio de tipo antes del primer envío que cruza a/desde «Entre cuentas» cambia de pantalla conservando importe y fecha (y su aviso T02). «Editar» / «Añadir acceso» llevan a Ajustes › Plantillas.
// Versión: 0.5.0
// ============================================================

import * as Crypto from 'expo-crypto';
import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ClienteApi, crearCliente } from './src/api/cliente';
import { configApi } from './src/api/config';
import { BarraInferior, Destino } from './src/components/BarraInferior';
import { HojaTipos } from './src/components/HojaTipos';
import type { TipoRegistro } from './src/domain/registro';
import { CategoriasAjustesScreen } from './src/screens/CategoriasAjustesScreen';
import { ContextosAjustesScreen } from './src/screens/ContextosAjustesScreen';
import { PlantillasAjustesScreen } from './src/screens/PlantillasAjustesScreen';
import { TercerosAjustesScreen } from './src/screens/TercerosAjustesScreen';
import { PreferenciasAjustesScreen } from './src/screens/PreferenciasAjustesScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { AjustesScreen, MasScreen } from './src/screens/MasScreen';
import { RegistroGastoScreen } from './src/screens/RegistroGastoScreen';
import { TerritorioPendiente } from './src/screens/TerritorioPendiente';
import { TransferenciaScreen } from './src/screens/TransferenciaScreen';
import { ProveedorTema, useTema } from './src/theme/tema';

const TITULOS: Record<Exclude<Destino, 'INICIO' | 'MAS'>, string> = { DIA: 'Día a día', MES: 'Mes', PATRIMONIO: 'Patrimonio' };

type PantallaMas = 'MAS' | 'AJUSTES' | 'CATEGORIAS' | 'PREFERENCIAS' | 'TERCEROS' | 'CONTEXTOS' | 'PLANTILLAS';

/** Tarea inmersiva de registro (F05-04): tipo, plantilla del acceso y lo conservado de otro tipo. */
type TareaRegistro = {
  tipo: TipoRegistro;
  plantilla?: { id: string; nombre: string } | null;
  inicial?: { importeTexto: string; fechaHecho: string; aviso: string | null } | null;
  clave: number;
};

export function Raiz(p: { cliente: ClienteApi; nuevoId: () => string; ahora: () => Date }) {
  const { c, esquema } = useTema();
  const [destino, setDestino] = useState<Destino>('INICIO');
  const [tarea, setTarea] = useState<TareaRegistro | null>(null);
  const [hojaTipos, setHojaTipos] = useState(false);
  const [refresco, setRefresco] = useState(0);
  const [pantallaMas, setPantallaMas] = useState<PantallaMas>('MAS');
  const [inmersivaMas, setInmersivaMas] = useState(false);

  const cerrarTarea = useCallback((registrado: boolean) => {
    setTarea(null);
    setDestino('INICIO'); // Atrás vuelve al origen real (Home)
    if (registrado) setRefresco((n) => n + 1);
  }, []);

  return (
    <View style={[s.raiz, { backgroundColor: c.background }]}>
      <StatusBar style={esquema === 'dark' ? 'light' : 'dark'} />
      <View style={s.raiz}>
        <View style={[s.raiz, destino !== 'INICIO' && s.oculto]}>
          <HomeScreen
            cliente={p.cliente}
            ahora={p.ahora}
            refresco={refresco}
            onRegistrar={() => setHojaTipos(true)}
            onAcceso={(pl) => setTarea({ tipo: pl.tipo ?? 'GASTO', plantilla: { id: pl.id, nombre: pl.nombre }, clave: Date.now() })}
            onEditarAccesos={() => {
              setPantallaMas('PLANTILLAS');
              setDestino('MAS');
            }}
          />
        </View>
        {(Object.keys(TITULOS) as (keyof typeof TITULOS)[]).map((d) =>
          destino === d ? <TerritorioPendiente key={d} titulo={TITULOS[d]} /> : null,
        )}
        {/* Más: pila propia montada (conserva el nivel al cambiar de pestaña). */}
        <View style={[s.raiz, destino !== 'MAS' && s.oculto]}>
          {pantallaMas === 'MAS' ? <MasScreen onAjustes={() => setPantallaMas('AJUSTES')} /> : null}
          {pantallaMas === 'AJUSTES' ? (
            <AjustesScreen
              onAtras={() => setPantallaMas('MAS')}
              onCategorias={() => setPantallaMas('CATEGORIAS')}
              onPreferencias={() => setPantallaMas('PREFERENCIAS')}
              onTerceros={() => setPantallaMas('TERCEROS')}
              onContextos={() => setPantallaMas('CONTEXTOS')}
              onPlantillas={() => setPantallaMas('PLANTILLAS')}
            />
          ) : null}
          {pantallaMas === 'CATEGORIAS' ? (
            <CategoriasAjustesScreen
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              onAtras={() => setPantallaMas('AJUSTES')}
              onInmersiva={setInmersivaMas}
            />
          ) : null}
          {pantallaMas === 'TERCEROS' ? (
            <TercerosAjustesScreen cliente={p.cliente} nuevoId={p.nuevoId} onAtras={() => setPantallaMas('AJUSTES')} onInmersiva={setInmersivaMas} />
          ) : null}
          {pantallaMas === 'CONTEXTOS' ? (
            <ContextosAjustesScreen cliente={p.cliente} nuevoId={p.nuevoId} onAtras={() => setPantallaMas('AJUSTES')} onInmersiva={setInmersivaMas} />
          ) : null}
          {pantallaMas === 'PLANTILLAS' ? (
            <PlantillasAjustesScreen
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              onAtras={() => setPantallaMas('AJUSTES')}
              onInmersiva={setInmersivaMas}
            />
          ) : null}
          {pantallaMas === 'PREFERENCIAS' ? (
            <PreferenciasAjustesScreen
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              onAtras={() => setPantallaMas('AJUSTES')}
              onInmersiva={setInmersivaMas}
            />
          ) : null}
        </View>
        {tarea && tarea.tipo !== 'TRANSFERENCIA' ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <RegistroGastoScreen
              key={tarea.clave}
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              onCerrar={cerrarTarea}
              tipo={tarea.tipo}
              plantilla={tarea.plantilla ?? null}
              inicial={tarea.inicial ?? null}
              onCambiarTipo={(t, conservar) => setTarea({ tipo: t, inicial: conservar, clave: tarea.clave + 1 })}
            />
          </View>
        ) : null}
        {tarea && tarea.tipo === 'TRANSFERENCIA' ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <TransferenciaScreen
              key={tarea.clave}
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              onCerrar={cerrarTarea}
              inicial={tarea.inicial ?? null}
              onCambiarTipo={(t, conservar) => setTarea({ tipo: t, inicial: conservar, clave: tarea.clave + 1 })}
            />
          </View>
        ) : null}
        {hojaTipos ? (
          <HojaTipos
            onElegir={(t) => {
              setHojaTipos(false);
              setTarea({ tipo: t, clave: Date.now() });
            }}
            onCancelar={() => setHojaTipos(false)}
          />
        ) : null}
      </View>
      {tarea === null && !hojaTipos && !(destino === 'MAS' && inmersivaMas) ? <BarraInferior actual={destino} onCambiar={setDestino} /> : null}
    </View>
  );
}

// Funciones estables (identidad fija): evitan relecturas en bucle por dependencias de efectos.
const nuevoIdSeguro = () => Crypto.randomUUID();
const ahoraDispositivo = () => new Date();

export default function App() {
  const cliente = useMemo(() => crearCliente(configApi), []);
  return (
    <SafeAreaProvider>
      <ProveedorTema>
        <Raiz cliente={cliente} nuevoId={nuevoIdSeguro} ahora={ahoraDispositivo} />
      </ProveedorTema>
    </SafeAreaProvider>
  );
}

const s = StyleSheet.create({
  raiz: { flex: 1 },
  oculto: { display: 'none' },
});
