// ============================================================
// GAPTO MOBILE 2027
// Fichero: App.tsx
// Ruta: mobile/App.tsx
// Descripción: Raíz del cliente. Navegación mínima propia de VS-01 (decisión de ejecución: sin librería de navegación hasta F11-00): cinco destinos persistentes montados (conservan su contexto al cambiar de pestaña) y una tarea inmersiva CREATE superpuesta que oculta la barra inferior (F09 BLOQUE A). Tras un registro confirmado, Inicio vuelve a leer del backend (sin optimistic update).
// v0.2.0 (F05-01 S6-WIRE+UI (este mandato); D-UI-03, F09 §12.91.1/§12.97.4): el destino MAS deja de ser territorio pendiente: Más → Ajustes (10 secciones; solo Categorías operativa) → Categorías. Las listas conservan la barra inferior; las tareas inmersivas de Ajustes (alta CREATE-M y selectores) la ocultan, igual que la tarea de registro. «Atrás» vuelve al nivel anterior real; la pila de Más conserva su contexto al cambiar de pestaña. Los otros tres territorios siguen pendientes.
// v0.3.0 (F05-02 B3, A1; D-B3-01): Ajustes › «Preferencias financieras» abre Ajustes › Preferencias (PreferenciasAjustesScreen) en la pila de Más, como Categorías; sus formularios y el selector de categoría son tareas inmersivas (ocultan la barra inferior).
// v0.4.0 (F05-03/F05-04 J2 §2.5): Ajustes › Terceros, Contextos y Plantillas en la pila de Más, como Preferencias; sus formularios y selectores son tareas inmersivas.
// v0.5.0 (F05-03/F05-04 J2+J3 §2.1–§2.4): «Registrar» de Inicio abre la hoja de tipos (sin preselección); Gasto e Ingreso abren el registro con ese tipo, «Entre cuentas» la pantalla de transferencia. Un acceso de Inicio abre el registro del tipo de su plantilla con la plantilla aplicada. El cambio de tipo antes del primer envío que cruza a/desde «Entre cuentas» cambia de pantalla conservando importe y fecha (y su aviso T02). «Editar» / «Añadir acceso» llevan a Ajustes › Plantillas.
// v0.6.0 (F05-05 K3 §2.5/§2.6; F05 §49.4 A7/A8, D-SRCH-06/12): «Día a día» deja de ser territorio pendiente: monta la Actividad v0 (ActividadScreen) de forma PERSISTENTE, como Más (conserva periodo, filtros y scroll al cambiar de pestaña); sus hojas son inmersivas (el velo cubre la barra inferior). Tras un registro confirmado la Actividad vuelve a leer. Ajustes › Terceros › «Ver sus registros» abre en la pila de Más la Actividad filtrada por el tercero con todo el historial («‹ <tercero>» vuelve a la ficha). Mes y Patrimonio siguen pendientes.
// v0.7.0 (F05-06 M4 §3; F09 §12.105 CAP): Ajustes › «Cuentas» (capacidades de cuenta, entrada provisional junto a Preferencias financieras) en la pila de Más; su hoja de confirmación es inmersiva (oculta la barra inferior).
// v0.8.0 (F05-06 M2-B §B1; lámina DEV, D-DEV-01/06): «Registrar devolución» del detalle de un gasto en la Actividad abre la tarea inmersiva de devolución (DevolucionScreen) sobre la compra; al terminar, Día a día y Inicio vuelven a leer y «Ver la devolución» / «Ver la compra» abren ese detalle en Día a día (ida y vuelta). La Actividad recibe `nuevoId` para «Registrar abono».
// v0.9.0 (F05-06 M3 §B1; lámina REP v0.2): «Repartir» u «Otra persona» en el registro de un gasto abren el gasto compartido (GastoCompartidoScreen) ENCIMA del registro, que sigue montado y conserva lo común («Cambiar» vuelve a él). «Pendiente con <persona>» (PendienteConScreen) se abre desde el éxito del gasto compartido, el detalle de un gasto en la Actividad y la ficha del tercero; «Corregir reparto» (CorregirRepartoScreen), desde el detalle. Todas son tareas inmersivas (ocultan la barra inferior); al terminar con cambios, Día a día e Inicio vuelven a leer.
// v0.10.0 (F05-06 M5 §B1; láminas PREV v0.2 y HOME-01 v0.4): la campana y «Ver todos ›» de Inicio abren «Pendientes» (PendientesScreen) y una fila de Inicio o de la lista abre el detalle de la previsión (PrevisionDetalleScreen), que contiene sus salidas («Registrar pago/cobro», «Ya lo registré», «No hubo este mes»); el swipe «Abrir el formulario completo» abre el detalle directamente en el registro con el importe escrito. Son tareas superpuestas (ocultan la barra inferior); al terminar con cambios, Inicio, «Pendientes» y Día a día vuelven a leer.
// v0.11.0 (F05-06 M1; lámina EDIT-HECHO v0.1): «Corregir» desde «Más» del detalle de un hecho en Día a día abre la tarea inmersiva CorregirHechoScreen; al terminar con cambios, Día a día e Inicio vuelven a leer y el detalle se reabre (rastro visible). «Anular por duplicado» vive en la propia Actividad.
// Versión: 0.11.0
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
import type { BaseCompartido } from './src/domain/reparto';
import { CategoriasAjustesScreen } from './src/screens/CategoriasAjustesScreen';
import { ContextosAjustesScreen } from './src/screens/ContextosAjustesScreen';
import { CuentasCapacidadesScreen } from './src/screens/CuentasCapacidadesScreen';
import { PlantillasAjustesScreen } from './src/screens/PlantillasAjustesScreen';
import { TercerosAjustesScreen } from './src/screens/TercerosAjustesScreen';
import { PreferenciasAjustesScreen } from './src/screens/PreferenciasAjustesScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { AjustesScreen, MasScreen } from './src/screens/MasScreen';
import { ActividadScreen } from './src/screens/ActividadScreen';
import { CorregirHechoScreen } from './src/screens/CorregirHechoScreen';
import { CorregirRepartoScreen } from './src/screens/CorregirRepartoScreen';
import { DevolucionScreen } from './src/screens/DevolucionScreen';
import { GastoCompartidoScreen } from './src/screens/GastoCompartidoScreen';
import { PendienteConScreen } from './src/screens/PendienteConScreen';
import { PendientesScreen } from './src/screens/PendientesScreen';
import { PrevisionDetalleScreen } from './src/screens/PrevisionDetalleScreen';
import { RegistroGastoScreen } from './src/screens/RegistroGastoScreen';
import { TerritorioPendiente } from './src/screens/TerritorioPendiente';
import { TransferenciaScreen } from './src/screens/TransferenciaScreen';
import { ProveedorTema, useTema } from './src/theme/tema';

const TITULOS: Record<Exclude<Destino, 'INICIO' | 'MAS' | 'DIA'>, string> = { MES: 'Mes', PATRIMONIO: 'Patrimonio' };

type PantallaMas = 'MAS' | 'AJUSTES' | 'CATEGORIAS' | 'PREFERENCIAS' | 'TERCEROS' | 'CONTEXTOS' | 'PLANTILLAS' | 'CUENTAS' | 'REGISTROS_TERCERO';

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
  const [inmersivaDia, setInmersivaDia] = useState(false);
  /** C4: tercero cuyos registros se ven desde Ajustes › Terceros. */
  const [registrosDe, setRegistrosDe] = useState<{ id: string; nombre: string } | null>(null);
  /** F05-06 M2: tarea de devolución sobre una compra y detalle que abrir en Día a día al volver. */
  const [devolucionDe, setDevolucionDe] = useState<{ origenId: string; clave: number } | null>(null);
  const [abrirEnDia, setAbrirEnDia] = useState<{ id: string; clave: number } | null>(null);
  const registrarDevolucion = useCallback((origenId: string) => setDevolucionDe({ origenId, clave: Date.now() }), []);
  /** F05-06 M3: gasto compartido encima del registro; «Pendiente con» y «Corregir reparto». */
  const [compartido, setCompartido] = useState<{ base: BaseCompartido; inicial: { repartir: boolean; otraPersona: boolean }; clave: number } | null>(null);
  const [pendienteDe, setPendienteDe] = useState<{ terceroId: string; nombre: string; clave: number } | null>(null);
  const [corregirDe, setCorregirDe] = useState<{ hechoId: string; clave: number } | null>(null);
  const abrirPendiente = useCallback((t: { terceroId: string; nombre: string }) => setPendienteDe({ ...t, clave: Date.now() }), []);
  const abrirCorregir = useCallback((hechoId: string) => setCorregirDe({ hechoId, clave: Date.now() }), []);
  /** F05-06 M1: «Corregir» un registro (OP-21P / OP-21T). */
  const [corregirHecho, setCorregirHecho] = useState<{ hechoId: string; titulo: string; clave: number } | null>(null);
  const abrirCorregirHecho = useCallback((hechoId: string, titulo: string) => setCorregirHecho({ hechoId, titulo, clave: Date.now() }), []);
  /** F05-06 M5: lista «Pendientes» y detalle de una previsión (con su registro, «Ya lo registré» y omitir). */
  const [pendientes, setPendientes] = useState(false);
  const [prevision, setPrevision] = useState<{ id: string; abrirRegistro: { importe: string | null } | null; desde: string; clave: number } | null>(null);
  const abrirPrevision = useCallback((id: string, desde: string, abrirRegistro: { importe: string | null } | null = null) =>
    setPrevision({ id, abrirRegistro, desde, clave: Date.now() }), []);

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
            nuevoId={p.nuevoId}
            onPendientes={() => setPendientes(true)}
            onPrevision={(f) => abrirPrevision(f.id, 'Inicio')}
            onFormularioCompleto={(f, importe) => abrirPrevision(f.id, 'Inicio', { importe })}
          />
        </View>
        {/* Día a día: Actividad v0 montada de forma persistente (conserva periodo, filtros y scroll). */}
        <View style={[s.raiz, destino !== 'DIA' && s.oculto]}>
          <ActividadScreen cliente={p.cliente} ahora={p.ahora} refresco={refresco} onRegistrar={() => setHojaTipos(true)} onInmersiva={setInmersivaDia}
            onRegistrarDevolucion={registrarDevolucion} nuevoId={p.nuevoId} abrir={abrirEnDia} onCorregirReparto={abrirCorregir} onPendienteCon={abrirPendiente} onCorregirHecho={abrirCorregirHecho} />
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
              onCuentas={() => setPantallaMas('CUENTAS')}
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
            <TercerosAjustesScreen
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              onAtras={() => setPantallaMas('AJUSTES')}
              onInmersiva={setInmersivaMas}
              volverA={registrosDe?.id ?? null}
              onPendienteCon={abrirPendiente}
              onVerRegistros={(t) => {
                setRegistrosDe(t);
                setPantallaMas('REGISTROS_TERCERO');
              }}
            />
          ) : null}
          {pantallaMas === 'REGISTROS_TERCERO' && registrosDe ? (
            <ActividadScreen
              cliente={p.cliente}
              ahora={p.ahora}
              refresco={refresco}
              onInmersiva={setInmersivaMas}
              onRegistrarDevolucion={registrarDevolucion}
              nuevoId={p.nuevoId}
              tercero={{
                ...registrosDe,
                onAtras: () => setPantallaMas('TERCEROS'),
                onLimpiar: () => {
                  setPantallaMas('TERCEROS');
                  setDestino('DIA');
                },
              }}
            />
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
          {pantallaMas === 'CUENTAS' ? (
            <CuentasCapacidadesScreen cliente={p.cliente} etiquetaAtras="Ajustes" onAtras={() => setPantallaMas('AJUSTES')} onInmersiva={setInmersivaMas} />
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
              onGastoCompartido={(base, inicial) => setCompartido({ base, inicial, clave: Date.now() })}
            />
          </View>
        ) : null}
        {tarea && compartido ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <GastoCompartidoScreen
              key={compartido.clave}
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              base={compartido.base}
              inicial={compartido.inicial}
              onVolver={() => setCompartido(null)}
              onCerrar={(registrado, ver) => {
                setCompartido(null);
                if (registrado || !ver) cerrarTarea(registrado);
                if (ver) abrirPendiente(ver);
              }}
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
        {devolucionDe ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <DevolucionScreen
              key={devolucionDe.clave}
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              origenId={devolucionDe.origenId}
              onCerrar={(registrado, ver) => {
                setDevolucionDe(null);
                if (registrado) setRefresco((n) => n + 1);
                if (ver) {
                  setDestino('DIA');
                  setAbrirEnDia({ id: ver, clave: Date.now() });
                }
              }}
            />
          </View>
        ) : null}
        {corregirDe ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <CorregirRepartoScreen
              key={corregirDe.clave}
              cliente={p.cliente}
              hechoId={corregirDe.hechoId}
              onCerrar={(cambios) => {
                const id = corregirDe.hechoId;
                setCorregirDe(null);
                if (cambios) {
                  setRefresco((n) => n + 1);
                  setAbrirEnDia({ id, clave: Date.now() });
                }
              }}
            />
          </View>
        ) : null}
        {corregirHecho ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <CorregirHechoScreen
              key={corregirHecho.clave}
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              hechoId={corregirHecho.hechoId}
              titulo={corregirHecho.titulo}
              onCerrar={(cambios) => {
                const id = corregirHecho.hechoId;
                setCorregirHecho(null);
                if (cambios) {
                  setRefresco((n) => n + 1);
                  setAbrirEnDia({ id, clave: Date.now() });
                }
              }}
            />
          </View>
        ) : null}
        {pendienteDe ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <PendienteConScreen
              key={pendienteDe.clave}
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              terceroId={pendienteDe.terceroId}
              nombre={pendienteDe.nombre}
              onCerrar={(cambios) => {
                setPendienteDe(null);
                if (cambios) setRefresco((n) => n + 1);
              }}
              onVerHecho={(id) => {
                setPendienteDe(null);
                setDestino('DIA');
                setAbrirEnDia({ id, clave: Date.now() });
              }}
            />
          </View>
        ) : null}
        {pendientes ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <PendientesScreen
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              refresco={refresco}
              onAtras={() => setPendientes(false)}
              onDetalle={(f) => abrirPrevision(f.id, 'Pendientes')}
              onFormularioCompleto={(f, importe) => abrirPrevision(f.id, 'Pendientes', { importe })}
              onCambios={() => setRefresco((n) => n + 1)}
            />
          </View>
        ) : null}
        {prevision ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: c.background }]}>
            <PrevisionDetalleScreen
              key={prevision.clave}
              cliente={p.cliente}
              nuevoId={p.nuevoId}
              ahora={p.ahora}
              previsionId={prevision.id}
              abrirRegistro={prevision.abrirRegistro}
              etiquetaAtras={prevision.desde}
              onCerrar={(cambios) => {
                setPrevision(null);
                if (cambios) setRefresco((n) => n + 1);
              }}
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
      {tarea === null && devolucionDe === null && pendienteDe === null && corregirDe === null && corregirHecho === null && !pendientes && prevision === null && !hojaTipos && !(destino === 'MAS' && inmersivaMas) && !(destino === 'DIA' && inmersivaDia) ? <BarraInferior actual={destino} onCambiar={setDestino} /> : null}
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
