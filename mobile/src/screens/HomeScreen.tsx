// ============================================================
// GAPTO MOBILE 2027
// Fichero: HomeScreen.tsx
// Ruta: mobile/src/screens/HomeScreen.tsx
// Descripción: HOME-01 (F09 §4) — esqueleto estructural completo en el orden aprobado: Cabecera, Liquidez, Acciones rápidas, Mes actual, [Requiere atención solo cuando exista], Próximos movimientos, Patrimonio total. Único dato real en VS-01: «Gastos» del mes vía lectura estrecha provisional (candidata F08). Los bloques sin read model autorizado muestran estado «No disponible» (DS-RULE-40) y NUNCA 0 € ni datos mock. Marcados internamente PENDIENTE_READ_MODEL.
// v0.2.0 (F05-D003 §16.6): el bloque canónico «Este mes» ya no muestra cifras (Ingresos, Gastos, Resultado y presupuesto «No disponible»); la única lectura real va en una tarjeta SEPARADA «Gasto atribuible registrado este mes · parcial», que no es gasto total, resultado, presupuesto ni liquidez.
// Versión: 0.2.0
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, GastoMes } from '../api/cliente';
import { EstadoDato, Seccion } from '../components/Basicos';
import { fechaCorta, mesLocal, nombreMes } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import { useTema } from '../theme/tema';
import { espacio, FUENTE_MARCA, importe, radio, TACTIL_MIN, tipo } from '../theme/tokens';

/** Bloques de HOME-01 cuyo read model no está autorizado en VS-01 (mandato §11). */
export const PENDIENTE_READ_MODEL = ['LIQUIDEZ', 'MES_INGRESOS', 'MES_GASTOS', 'MES_RESULTADO', 'MES_PRESUPUESTO', 'ATENCION', 'PROXIMOS', 'PATRIMONIO'] as const;

type Lectura = { fase: 'CARGANDO' } | { fase: 'OK'; datos: GastoMes } | { fase: 'ERROR' };

export function HomeScreen(p: { cliente: ClienteApi; ahora: () => Date; refresco: number; onRegistrarGasto: () => void }) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const hoy = p.ahora();
  const [gasto, setGasto] = useState<Lectura>({ fase: 'CARGANDO' });

  const cargar = useCallback(async () => {
    setGasto({ fase: 'CARGANDO' });
    const r = await p.cliente.gastoMes(mesLocal(p.ahora()));
    setGasto(r.tipo === 'OK' ? { fase: 'OK', datos: r.datos } : { fase: 'ERROR' });
  }, [p.cliente, p.ahora]);

  useEffect(() => {
    void cargar();
  }, [cargar, p.refresco]);

  return (
    <ScrollView
      testID="home"
      style={{ backgroundColor: c.background }}
      contentContainerStyle={[s.contenido, { paddingTop: inset.top + espacio.l }]}
      refreshControl={<RefreshControl refreshing={false} onRefresh={cargar} />}
    >
      {/* 1. Cabecera (§4.2): identidad, contexto discreto y perfil */}
      <View style={s.cabecera}>
        <View style={{ flexShrink: 1 }}>
          <Text accessibilityRole="header" style={[s.marca, { color: c.textPrimary }]}>
            GaptoMobile <Text style={{ color: c.textSecondary }}>2027</Text>
          </Text>
          <Text style={[tipo.caption, s.lema, { color: c.textSecondary }]}>TUS FINANZAS, EN EQUILIBRIO</Text>
        </View>
        <View style={s.perfil}>
          <Text style={[tipo.footnote, { color: c.textSecondary }]}>{fechaCorta(hoy)}</Text>
          <View accessibilityLabel="Perfil" style={[s.avatar, { backgroundColor: c.surfaceSecondary }]}>
            <Ionicons name="person-outline" size={18} color={c.textSecondary} />
          </View>
        </View>
      </View>

      {/* 2. Liquidez — hero (§4.3). Sin read model: no se muestra cifra. */}
      <View testID="bloque-liquidez" style={[s.hero, { backgroundColor: c.accentSurface }]}>
        <Text style={[tipo.titleSmall, { color: c.textPrimary, fontSize: 19 }]}>Liquidez actual</Text>
        <Text style={[tipo.subheadline, { color: c.textSecondary }]}>Solo pagos y cobros reales confirmados.</Text>
        <EstadoDato estado="NO_DISPONIBLE" detalle="Aún no se calcula en esta versión." />
      </View>

      {/* 3. Acciones rápidas (§4.4): máx. 4, una fila. VS-01 implementa solo «Gasto». */}
      <View style={{ gap: espacio.m }}>
        <Text style={[tipo.titleSmall, { color: c.textPrimary, fontSize: 19 }]}>Acciones rápidas</Text>
        <View style={s.fila}>
          <Pressable
            testID="accion-gasto"
            accessibilityRole="button"
            accessibilityLabel="Registrar gasto"
            onPress={p.onRegistrarGasto}
            style={s.accion}
          >
            <View style={[s.circulo, { backgroundColor: c.accentSurface }]}>
              <Ionicons name="add" size={26} color={c.accent} />
            </View>
            <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>Gasto</Text>
            <Text style={[tipo.caption, { color: c.textSecondary }]}>Registrar</Text>
          </Pressable>
        </View>
      </View>

      {/* 4. Mes actual (§4.5): Ingresos · Gastos · Resultado + presupuesto */}
      <Seccion testID="bloque-mes" titulo="Este mes" derecha={<Text style={[tipo.subheadline, { color: c.textSecondary }]}>{nombreMes(hoy)}</Text>}>
        <View style={[s.fila, s.tresColumnas]}>
          <Columna etiqueta="Ingresos">
            <EstadoDato estado="NO_DISPONIBLE" />
          </Columna>
          <View style={[s.divisor, { backgroundColor: c.borderDefault }]} />
          <Columna etiqueta="Gastos">
            <EstadoDato estado="NO_DISPONIBLE" />
          </Columna>
          <View style={[s.divisor, { backgroundColor: c.borderDefault }]} />
          <Columna etiqueta="Resultado">
            <EstadoDato estado="NO_DISPONIBLE" />
          </Columna>
        </View>
        <View style={[s.separador, { backgroundColor: c.separator }]} />
        <View style={s.estadoFilaPres}>
          <Text style={[tipo.footnote, { color: c.textPrimary }]}>Presupuesto de gasto</Text>
          <EstadoDato estado="NO_DISPONIBLE" />
        </View>
      </Seccion>

      {/* Lectura PARCIAL de VS-01 (F05-D003 §16.6): tarjeta separada, fuera del
             bloque «Este mes». Solo gasto atribuible a ti ya registrado. */}
      <Seccion
        testID="bloque-gasto-parcial"
        titulo="Gasto atribuible registrado"
        derecha={<Text style={[tipo.subheadline, { color: c.textSecondary }]}>{nombreMes(hoy)}</Text>}
      >
        <CeldaGastos lectura={gasto} onReintentar={cargar} />
        <Text testID="gasto-parcial-aviso" style={[tipo.footnote, { color: c.textSecondary }]}>
          Lectura parcial: solo lo registrado y atribuible a ti. No es tu gasto total, ni el resultado del mes, ni el presupuesto.
        </Text>
      </Seccion>

      {/* 5. Requiere atención: solo aparece si existen asuntos; VS-01 no puede
             determinarlo, así que no se renderiza (ver handoff, desviación F09-5). */}

      {/* 6. Próximos movimientos (§4.7) */}
      <Seccion testID="bloque-proximos" titulo="Próximos movimientos">
        <EstadoDato estado="NO_DISPONIBLE" detalle="Las previsiones aún no se muestran en esta versión." />
      </Seccion>

      {/* 7. Patrimonio total (§4.8), al final */}
      <Seccion testID="bloque-patrimonio" titulo="Patrimonio total">
        <EstadoDato estado="NO_DISPONIBLE" detalle="Aún no se calcula en esta versión." />
      </Seccion>
    </ScrollView>
  );
}

function Columna({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  const { c } = useTema();
  return (
    <View style={s.columna}>
      <Text style={[tipo.footnote, { color: c.textSecondary }]}>{etiqueta}</Text>
      {children}
    </View>
  );
}

function CeldaGastos({ lectura, onReintentar }: { lectura: Lectura; onReintentar: () => void }) {
  const { c } = useTema();
  if (lectura.fase === 'CARGANDO') return <EstadoDato testID="gastos-cargando" estado="CARGANDO" />;
  if (lectura.fase === 'ERROR')
    return (
      <Pressable testID="gastos-error" accessibilityRole="button" onPress={onReintentar} style={{ minHeight: TACTIL_MIN }}>
        <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
      </Pressable>
    );
  const d = lectura.datos;
  const pendientes = d.gastos_sin_reparto + d.gastos_otra_moneda;
  return (
    <View style={{ gap: espacio.xs }}>
      {/* DS-RULE-36: el gasto no se pinta como estado crítico por su naturaleza */}
      <Text testID="gastos-valor" style={[importe.secondary, { color: c.textPrimary }]} adjustsFontSizeToFit numberOfLines={1}>
        {formatearEur(d.gasto_atribuible)}
      </Text>
      {/* La tarjeta es SIEMPRE parcial; si además hay gastos sin reparto u otra moneda, se cuenta cuántos. */}
      <EstadoDato
        testID="gastos-parcial"
        estado="PARCIAL"
        detalle={pendientes > 0 ? `${pendientes} sin reparto conocido` : 'Lectura provisional de esta versión'}
      />
    </View>
  );
}

const s = StyleSheet.create({
  contenido: { paddingHorizontal: espacio.l, paddingBottom: espacio.xxl, gap: espacio.xl },
  cabecera: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: espacio.m },
  marca: { fontFamily: FUENTE_MARCA, fontSize: 24 },
  lema: { letterSpacing: 1.5, marginTop: 2, fontSize: 10 },
  perfil: { flexDirection: 'row', alignItems: 'center', gap: espacio.s },
  avatar: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  hero: { borderRadius: radio.l, padding: espacio.l, gap: espacio.s },
  fila: { flexDirection: 'row' },
  accion: { width: '25%', alignItems: 'center', gap: 2, minHeight: TACTIL_MIN },
  circulo: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center', marginBottom: espacio.xs },
  tresColumnas: { alignItems: 'stretch' },
  columna: { flex: 1, gap: espacio.xs, paddingHorizontal: espacio.xs },
  divisor: { width: StyleSheet.hairlineWidth },
  separador: { height: 1 },
  estadoFilaPres: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: espacio.s, flexWrap: 'wrap' },
});
