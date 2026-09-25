// ============================================================
// GAPTO MOBILE 2027
// Fichero: App.tsx
// Ruta: mobile/App.tsx
// Descripción: Raíz del cliente. Navegación mínima propia de VS-01 (decisión de ejecución: sin librería de navegación hasta F11-00): cinco destinos persistentes montados (conservan su contexto al cambiar de pestaña) y una tarea inmersiva CREATE superpuesta que oculta la barra inferior (F09 BLOQUE A). Tras un registro confirmado, Inicio vuelve a leer del backend (sin optimistic update).
// Versión: 0.1.0
// ============================================================

import * as Crypto from 'expo-crypto';
import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ClienteApi, crearCliente } from './src/api/cliente';
import { configApi } from './src/api/config';
import { BarraInferior, Destino } from './src/components/BarraInferior';
import { HomeScreen } from './src/screens/HomeScreen';
import { RegistroGastoScreen } from './src/screens/RegistroGastoScreen';
import { TerritorioPendiente } from './src/screens/TerritorioPendiente';
import { ProveedorTema, useTema } from './src/theme/tema';

const TITULOS: Record<Exclude<Destino, 'INICIO'>, string> = { DIA: 'Día a día', MES: 'Mes', PATRIMONIO: 'Patrimonio', MAS: 'Más' };

export function Raiz(p: { cliente: ClienteApi; nuevoId: () => string; ahora: () => Date }) {
  const { c, esquema } = useTema();
  const [destino, setDestino] = useState<Destino>('INICIO');
  const [tarea, setTarea] = useState<'REGISTRO_GASTO' | null>(null);
  const [refresco, setRefresco] = useState(0);

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
        {tarea === 'REGISTRO_GASTO' ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <RegistroGastoScreen cliente={p.cliente} nuevoId={p.nuevoId} ahora={p.ahora} onCerrar={cerrarTarea} />
          </View>
        ) : null}
      </View>
      {tarea === null ? <BarraInferior actual={destino} onCambiar={setDestino} /> : null}
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
