// ============================================================
// GAPTO MOBILE 2027
// Fichero: App.tsx
// Ruta: mobile/App.tsx
// Descripción: Raíz del cliente. Navegación mínima propia de VS-01 (decisión de ejecución: sin librería de navegación hasta F11-00): cinco destinos persistentes montados (conservan su contexto al cambiar de pestaña) y una tarea inmersiva CREATE superpuesta que oculta la barra inferior (F09 BLOQUE A). Tras un registro confirmado, Inicio vuelve a leer del backend (sin optimistic update).
// v0.2.0 (F05-01 S6-WIRE+UI (este mandato); D-UI-03, F09 §12.91.1/§12.97.4): el destino MAS deja de ser territorio pendiente: Más → Ajustes (10 secciones; solo Categorías operativa) → Categorías. Las listas conservan la barra inferior; las tareas inmersivas de Ajustes (alta CREATE-M y selectores) la ocultan, igual que la tarea de registro. «Atrás» vuelve al nivel anterior real; la pila de Más conserva su contexto al cambiar de pestaña. Los otros tres territorios siguen pendientes.
// v0.3.0 (F05-02 B3, A1; D-B3-01): Ajustes › «Preferencias financieras» abre Ajustes › Preferencias (PreferenciasAjustesScreen) en la pila de Más, como Categorías; sus formularios y el selector de categoría son tareas inmersivas (ocultan la barra inferior).
// Versión: 0.3.0
// ============================================================

import * as Crypto from 'expo-crypto';
import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ClienteApi, crearCliente } from './src/api/cliente';
import { configApi } from './src/api/config';
import { BarraInferior, Destino } from './src/components/BarraInferior';
import { CategoriasAjustesScreen } from './src/screens/CategoriasAjustesScreen';
import { PreferenciasAjustesScreen } from './src/screens/PreferenciasAjustesScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { AjustesScreen, MasScreen } from './src/screens/MasScreen';
import { RegistroGastoScreen } from './src/screens/RegistroGastoScreen';
import { TerritorioPendiente } from './src/screens/TerritorioPendiente';
import { ProveedorTema, useTema } from './src/theme/tema';

const TITULOS: Record<Exclude<Destino, 'INICIO' | 'MAS'>, string> = { DIA: 'Día a día', MES: 'Mes', PATRIMONIO: 'Patrimonio' };

type PantallaMas = 'MAS' | 'AJUSTES' | 'CATEGORIAS' | 'PREFERENCIAS';

export function Raiz(p: { cliente: ClienteApi; nuevoId: () => string; ahora: () => Date }) {
  const { c, esquema } = useTema();
  const [destino, setDestino] = useState<Destino>('INICIO');
  const [tarea, setTarea] = useState<'REGISTRO_GASTO' | null>(null);
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
          <HomeScreen cliente={p.cliente} ahora={p.ahora} refresco={refresco} onRegistrarGasto={() => setTarea('REGISTRO_GASTO')} />
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
        {tarea === 'REGISTRO_GASTO' ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <RegistroGastoScreen cliente={p.cliente} nuevoId={p.nuevoId} ahora={p.ahora} onCerrar={cerrarTarea} />
          </View>
        ) : null}
      </View>
      {tarea === null && !(destino === 'MAS' && inmersivaMas) ? <BarraInferior actual={destino} onCambiar={setDestino} /> : null}
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
