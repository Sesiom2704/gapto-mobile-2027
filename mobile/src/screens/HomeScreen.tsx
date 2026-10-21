// ============================================================
// GAPTO MOBILE 2027
// Fichero: HomeScreen.tsx
// Ruta: mobile/src/screens/HomeScreen.tsx
// Descripción: HOME-01 (F09 §4) — esqueleto estructural completo en el orden aprobado: Cabecera, Liquidez, Acciones rápidas, Mes actual, [Requiere atención solo cuando exista], Próximos movimientos, Patrimonio total. Único dato real en VS-01: «Gastos» del mes vía lectura estrecha provisional (candidata F08). Los bloques sin read model autorizado muestran estado «No disponible» (DS-RULE-40) y NUNCA 0 € ni datos mock. Marcados internamente PENDIENTE_READ_MODEL.
// v0.2.0 (F05-D003 §16.6): el bloque canónico «Este mes» ya no muestra cifras (Ingresos, Gastos, Resultado y presupuesto «No disponible»); la única lectura real va en una tarjeta SEPARADA «Gasto atribuible registrado este mes · parcial», que no es gasto total, resultado, presupuesto ni liquidez.
// v0.3.0 (F05 — VS-01 · Alineación visual, A1): los bloques dejan de ser tarjetas blancas (F09 §6 «pocas tarjetas y pocos bordes», HOME-01): se asientan sobre el fondo y se separan con una línea estructural; «Acciones rápidas» usa el mismo bloque sin línea porque el hero ya delimita. El hero conserva su contrato (accentSurface, sin degradado ni ilustración: C3b fuera de alcance). La lectura parcial sigue en un bloque SEPARADO de «Este mes» (F05-D003 §16.6). Sin HEX ni tokens nuevos.
// v0.4.0 (F05-03/F05-04 J3 §2.1; lámina HOME-01 v0.3; AJUSTE A1 «Marca en Inicio», AJ-MARCA-04 cerrado): cabecera con el símbolo (34 × 34 pt) y el nombre (132,25 × 24 pt, contain) de la entrega F09-MARCA-AJ04_R0, a 8 pt, como UN solo elemento accesible «GaptoMobile» con rol de cabecera; sin «2027» ni lema. Ilustración de Liquidez (112 × 112 pt, a 8 pt del borde derecho, centrada en vertical), decorativa y oculta a VoiceOver. Claro/oscuro por el esquema del sistema (MARK-RULE-01), nunca por el acento; se retira FUENTE_MARCA del nombre. «Acciones rápidas»: «Registrar» (abre la hoja de tipos, sin preselección) y hasta 3 accesos de plantillas (nombre corto e icono, o el de la categoría, o la reserva); sin accesos, «Añadir acceso» y el texto H03; «Editar» lleva a Ajustes › Plantillas. «Resultado» se presentará en verde / rojo con signo (neutro en 0) cuando exista su lectura: los bloques PENDIENTE_READ_MODEL no cambian (siguen «No disponible»).
// v0.5.0 (F05-05 K3 §2.7; F05 §49.4 A9, D13, M5-06; lámina SRCH-ACT-AFI E1; HOME-01 v0.3, D-HOME-02/03): «Hola, <nombre>» en la cabecera (GET /v1/yo; sin nombre, no se muestra). «Este mes» con Ingresos, Gastos y Resultado reales (GET /v1/inicio/resultado-mes con la fecha del dispositivo): cifras tabulares, color SOLO en Resultado (verde, rojo o neutro con signo, `resultadoDelMes`), y debajo la línea «Solo lo que es tuyo. Sin indicar: …» con número e importe. Carga y error con su estado; nunca 0 € inventado. El presupuesto y el resto de Inicio no cambian.
// v0.6.0 (F05-06 M5 §B1; lámina HOME-01 v0.4, D-HOME-07; F09 §4.2, §4.5, §4.6): campana con contador junto al perfil (solo con pendientes; «!» si la lectura falla) que abre «Pendientes»; bloque «Requiere atención» con datos reales (GET /v1/inicio/previsiones): como mucho dos asuntos (vencidos por fecha y después los pagados en parte), recuento junto al título y «Ver todos ›», SIN importes sumados; con la lectura fallida, «No se pudieron cargar los pendientes · Reintentar» (nunca desaparece como si no hubiera nada); sin asuntos, ni campana ni bloque. «Próximos movimientos» con las tres siguientes previsiones (solo lectura, P-PREV-04). Cobros previstos con «+» neutro y «Cobro previsto»; pagos con «~». La línea de presupuesto no se pinta mientras F08 no la alimente. Lo previsto no suma a Liquidez ni al Resultado.
// Versión: 0.6.0
// ============================================================

import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { AccionRapida, ClienteApi, FilaPrevision, GastoMes, InicioPrevisiones, Plantilla, ResultadoMes } from '../api/cliente';
import { BotonTexto, EstadoDato, Seccion } from '../components/Basicos';
import { CampanaPendientes, FilaPrevisionVista } from '../components/Prevision';
import { useSwipePrevision } from '../components/SwipePrevision';
import { fechaCorta, isoLocal, mesLocal, nombreMes } from '../domain/fechas';
import { formatearEur } from '../domain/importe';
import { accesosDeInicio, resultadoDelMes, TEXTO_SIN_ACCESOS, textoSinIndicar } from '../domain/inicio';
import { admiteSwipe, contadorCampana, TEXTO_FALLO_PENDIENTES, TEXTO_FALLO_PENDIENTES_DETALLE } from '../domain/prevision';
import { glifoDe } from '../theme/iconosCategoria';
import { useTema } from '../theme/tema';
import { espacio, importe, radio, TACTIL_MIN, tipo } from '../theme/tokens';

// Assets de marca (entrega F09-MARCA-AJ04_R0; @2x/@3x los resuelve la plataforma, sin reescalar).
const MARCA = {
  light: {
    simbolo: require('../../assets/marca/gm-simbolo-cabecera-claro.png'),
    nombre: require('../../assets/marca/gm-nombre-claro.png'),
    ilustracion: require('../../assets/marca/gm-ilustracion-liquidez-claro.png'),
  },
  dark: {
    simbolo: require('../../assets/marca/gm-simbolo-cabecera-oscuro.png'),
    nombre: require('../../assets/marca/gm-nombre-oscuro.png'),
    ilustracion: require('../../assets/marca/gm-ilustracion-liquidez-oscuro.png'),
  },
} as const;

/** Bloques de HOME-01 cuyo read model no está autorizado en VS-01 (mandato §11). */
export const PENDIENTE_READ_MODEL = ['LIQUIDEZ', 'PATRIMONIO'] as const;

type Lectura = { fase: 'CARGANDO' } | { fase: 'OK'; datos: GastoMes } | { fase: 'ERROR' };
type LecturaMes = { fase: 'CARGANDO' } | { fase: 'OK'; datos: ResultadoMes } | { fase: 'ERROR' };
type LecturaPrevisiones = { fase: 'CARGANDO' } | { fase: 'OK'; datos: InicioPrevisiones } | { fase: 'ERROR' };

export function HomeScreen(p: {
  cliente: ClienteApi;
  ahora: () => Date;
  refresco: number;
  /** «Registrar»: abre la hoja de tipos. */
  onRegistrar: () => void;
  /** Acceso de una plantilla: registro de su tipo con la plantilla aplicada. */
  onAcceso?: (plantilla: Plantilla) => void;
  /** «Editar» / «Añadir acceso»: Ajustes › Plantillas. */
  onEditarAccesos?: () => void;
  /** F05-06 M5: campana y «Ver todos ›» abren «Pendientes»; una fila abre su detalle. */
  onPendientes?: () => void;
  onPrevision?: (fila: FilaPrevision) => void;
  onFormularioCompleto?: (fila: FilaPrevision, importe: string | null) => void;
  nuevoId?: () => string;
}) {
  const { c, esquema } = useTema();
  const inset = useSafeAreaInsets();
  const hoy = p.ahora();
  const [gasto, setGasto] = useState<Lectura>({ fase: 'CARGANDO' });
  const [mes, setMes] = useState<LecturaMes>({ fase: 'CARGANDO' });
  const [nombre, setNombre] = useState<string | null>(null);
  const [accesos, setAccesos] = useState<{ plantillas: Plantilla[]; acciones: AccionRapida[]; iconos: Map<string, string | null> } | null>(null);
  const [previsiones, setPrevisiones] = useState<LecturaPrevisiones>({ fase: 'CARGANDO' });
  const marca = MARCA[esquema === 'dark' ? 'dark' : 'light'];

  // F05-06 M5: lectura propia del bloque; si falla, el bloque lo dice (nunca «sin pendientes»).
  const cargarPrevisiones = useCallback(async () => {
    setPrevisiones({ fase: 'CARGANDO' });
    try {
      const r = await p.cliente.inicioPrevisiones();
      setPrevisiones(r.tipo === 'OK' ? { fase: 'OK', datos: r.datos } : { fase: 'ERROR' });
    } catch {
      setPrevisiones({ fase: 'ERROR' });
    }
  }, [p.cliente]);
  const swipe = useSwipePrevision({
    cliente: p.cliente, nuevoId: p.nuevoId ?? (() => ''), ahora: p.ahora,
    onRegistrado: () => void cargarPrevisiones(),
    onFormularioCompleto: (f, imp) => p.onFormularioCompleto?.(f, imp),
  });

  const cargar = useCallback(async () => {
    setGasto({ fase: 'CARGANDO' });
    setMes({ fase: 'CARGANDO' });
    const [r, pl, rm, yo] = await Promise.all([
      p.cliente.gastoMes(mesLocal(p.ahora())),
      p.cliente.listarPlantillas(),
      p.cliente.resultadoMes(isoLocal(p.ahora())),
      p.cliente.yo(),
    ]);
    setGasto(r.tipo === 'OK' ? { fase: 'OK', datos: r.datos } : { fase: 'ERROR' });
    setMes(rm.tipo === 'OK' ? { fase: 'OK', datos: rm.datos } : { fase: 'ERROR' });
    setNombre(yo.tipo === 'OK' ? yo.datos.nombre : null);
    if (pl.tipo !== 'OK') return setAccesos(null);
    // Icono de la categoría de cada plantilla (solo si algún acceso no tiene icono propio).
    let iconos = new Map<string, string | null>();
    if (pl.datos.acciones.some((x) => x.enabled && !x.icono_key)) {
      const a = await p.cliente.arbolCategorias();
      if (a.tipo === 'OK') iconos = new Map(a.datos.categorias.map((n) => [n.id, n.icon_key]));
    }
    setAccesos({ ...pl.datos, iconos });
  }, [p.cliente, p.ahora]);
  const lista = accesos ? accesosDeInicio(accesos.plantillas, accesos.acciones, (id) => accesos.iconos.get(id) ?? null) : [];

  useEffect(() => {
    void cargar();
  }, [cargar, p.refresco]);
  useEffect(() => {
    void cargarPrevisiones();
  }, [cargarPrevisiones, p.refresco]);
  const contador = contadorCampana(previsiones.fase === 'OK' ? { fase: 'OK', n: previsiones.datos.requiere_atencion.n } : previsiones);
  const atencion = previsiones.fase === 'OK' ? previsiones.datos.requiere_atencion : null;

  return (
    <ScrollView
      testID="home"
      style={{ backgroundColor: c.background }}
      contentContainerStyle={[s.contenido, { paddingTop: inset.top + espacio.l }]}
      refreshControl={<RefreshControl refreshing={false} onRefresh={() => { void cargar(); void cargarPrevisiones(); }} />}
    >
      {/* 1. Cabecera (§4.2): identidad, contexto discreto y perfil */}
      <View style={s.cabecera}>
        {/* Marca (A1): símbolo + nombre, UN elemento accesible «GaptoMobile» con rol de cabecera. */}
        <View testID="marca-inicio" accessible accessibilityRole="header" accessibilityLabel="GaptoMobile" style={s.marca}>
          <Image testID="marca-simbolo" source={marca.simbolo} style={s.simbolo} accessible={false} />
          <Image testID="marca-nombre" source={marca.nombre} style={s.nombre} resizeMode="contain" accessible={false} />
        </View>
        <View style={s.perfil}>
          <View style={{ alignItems: 'flex-end' }}>
            {nombre ? <Text testID="hola" style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{`Hola, ${nombre}`}</Text> : null}
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{fechaCorta(hoy)}</Text>
          </View>
          <CampanaPendientes contador={contador} onPress={() => p.onPendientes?.()} />
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
        {/* Ilustración decorativa (A1): oculta a VoiceOver y TalkBack. */}
        <View pointerEvents="none" style={s.ilustracionCaja} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          <Image testID="ilustracion-liquidez" source={marca.ilustracion} style={s.ilustracion} accessible={false} />
        </View>
      </View>

      {/* 3. Acciones rápidas (§4.4; HOME-QA H01–H03): «Registrar» + hasta 3 accesos de plantillas. */}
      <Seccion
        testID="bloque-acciones"
        titulo="Acciones rápidas"
        separada={false}
        derecha={p.onEditarAccesos ? <BotonTexto testID="accesos-editar" titulo="Editar" onPress={p.onEditarAccesos} /> : undefined}
      >
        <View style={s.fila}>
          <Pressable testID="accion-registrar" accessibilityRole="button" accessibilityLabel="Registrar. Nuevo" onPress={p.onRegistrar} style={s.accion}>
            <View style={[s.circulo, { backgroundColor: c.accentSurface }]}>
              <Ionicons name="add" size={26} color={c.accent} />
            </View>
            <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>Registrar</Text>
            <Text style={[tipo.caption, { color: c.textSecondary }]}>Nuevo</Text>
          </Pressable>
          {lista.map((a) => (
            <Pressable
              key={a.accion.id}
              testID={`acceso-${a.accion.id}`}
              accessibilityRole="button"
              accessibilityLabel={`${a.accion.nombre}. Plantilla`}
              onPress={() => p.onAcceso?.(a.plantilla)}
              style={s.accion}
            >
              <View style={[s.circulo, { backgroundColor: c.surfaceSecondary }]}>
                <Ionicons name={glifoDe(a.iconoKey)} size={24} color={c.textPrimary} />
              </View>
              <Text numberOfLines={1} style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>{a.accion.nombre}</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>Plantilla</Text>
            </Pressable>
          ))}
          {accesos && lista.length === 0 && p.onEditarAccesos ? (
            <Pressable testID="acceso-anadir" accessibilityRole="button" accessibilityLabel="Añadir acceso" onPress={p.onEditarAccesos} style={s.accion}>
              <View style={[s.circulo, { borderColor: c.borderStandard, borderWidth: 1, borderStyle: 'dashed' }]}>
                <Ionicons name="add" size={24} color={c.textSecondary} />
              </View>
              <Text style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>Añadir</Text>
              <Text style={[tipo.caption, { color: c.textSecondary }]}>acceso</Text>
            </Pressable>
          ) : null}
        </View>
        {accesos && lista.length === 0 ? (
          <Text testID="accesos-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_SIN_ACCESOS}</Text>
        ) : null}
      </Seccion>

      {/* 4. Mes actual (§4.5): Ingresos · Gastos · Resultado + presupuesto */}
      <Seccion testID="bloque-mes" titulo="Este mes" derecha={<Text style={[tipo.subheadline, { color: c.textSecondary }]}>{nombreMes(hoy)}</Text>}>
        <View style={[s.fila, s.tresColumnas]}>
          <Columna etiqueta="Ingresos">
            <CeldaMes lectura={mes} campo="ingresos" onReintentar={cargar} />
          </Columna>
          <View style={[s.divisor, { backgroundColor: c.borderDefault }]} />
          <Columna etiqueta="Gastos">
            <CeldaMes lectura={mes} campo="gastos" onReintentar={cargar} />
          </Columna>
          <View style={[s.divisor, { backgroundColor: c.borderDefault }]} />
          <Columna etiqueta="Resultado">
            <CeldaMes lectura={mes} campo="resultado" onReintentar={cargar} />
          </Columna>
        </View>
        {mes.fase === 'OK' ? (
          <Text testID="mes-sin-indicar" style={[tipo.footnote, { color: c.textSecondary }]}>{textoSinIndicar(mes.datos)}</Text>
        ) : null}
        {/* D-HOME-07 (§4.5): sin línea ni barra de presupuesto mientras F08 no la alimente. */}
      </Seccion>

      {/* Lectura PARCIAL de VS-01 (F05-D003 §16.6): bloque separado, fuera del
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

      {/* 5. Requiere atención (§4.6, HOME-01 v0.4): solo con asuntos; con la lectura fallida, su estado. */}
      {previsiones.fase === 'ERROR' ? (
        <Seccion testID="bloque-atencion" titulo="Requiere atención">
          <View testID="atencion-error" style={{ gap: espacio.xs }}>
            <Text style={[tipo.body, { color: c.textPrimary, fontWeight: '600' }]}>{TEXTO_FALLO_PENDIENTES}</Text>
            <Text style={[tipo.footnote, { color: c.textSecondary }]}>{TEXTO_FALLO_PENDIENTES_DETALLE}</Text>
            <BotonTexto testID="atencion-reintentar" titulo="Reintentar" onPress={() => void cargarPrevisiones()} />
          </View>
        </Seccion>
      ) : null}
      {atencion && atencion.n > 0 ? (
        <Seccion
          testID="bloque-atencion"
          titulo="Requiere atención"
          derecha={
            <View style={s.atencionDerecha}>
              <Text testID="atencion-n" style={[tipo.subheadline, { color: c.textSecondary, fontWeight: '600' }]}>{String(atencion.n)}</Text>
              <BotonTexto testID="atencion-ver-todos" titulo="Ver todos ›" onPress={() => p.onPendientes?.()} />
            </View>
          }
        >
          {atencion.primeras.map((f, i) => (
            <FilaPrevisionVista key={f.id} testID={`atencion-${f.id}`} fila={f} ultima={i === atencion.primeras.length - 1}
              onPress={() => p.onPrevision?.(f)} onSwipe={admiteSwipe(f) && p.nuevoId ? () => swipe.abrir(f) : undefined} />
          ))}
        </Seccion>
      ) : null}

      {/* 6. Próximos movimientos (§4.7): solo lectura (P-PREV-04). */}
      <Seccion testID="bloque-proximos" titulo="Próximos movimientos">
        {previsiones.fase === 'CARGANDO' ? <EstadoDato estado="CARGANDO" /> : null}
        {previsiones.fase === 'ERROR' ? <EstadoDato estado="ERROR_CARGA" detalle="Desliza hacia abajo para reintentar" /> : null}
        {previsiones.fase === 'OK' && previsiones.datos.proximos.length === 0 ? (
          <Text testID="proximos-vacio" style={[tipo.footnote, { color: c.textSecondary }]}>No hay movimientos previstos.</Text>
        ) : null}
        {previsiones.fase === 'OK'
          ? previsiones.datos.proximos.map((f, i) => (
              <FilaPrevisionVista key={f.id} testID={`proximo-${f.id}`} fila={f} enProximos ultima={i === previsiones.datos.proximos.length - 1}
                onPress={p.onPrevision ? () => p.onPrevision?.(f) : undefined} />
            ))
          : null}
      </Seccion>

      {/* 7. Patrimonio total (§4.8), al final */}
      <Seccion testID="bloque-patrimonio" titulo="Patrimonio total">
        <EstadoDato estado="NO_DISPONIBLE" detalle="Aún no se calcula en esta versión." />
      </Seccion>
      {swipe.hoja}
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

function CeldaMes({ lectura, campo, onReintentar }: { lectura: LecturaMes; campo: 'ingresos' | 'gastos' | 'resultado'; onReintentar: () => void }) {
  const { c } = useTema();
  if (lectura.fase === 'CARGANDO') return <EstadoDato testID={`mes-${campo}-cargando`} estado="CARGANDO" />;
  if (lectura.fase === 'ERROR')
    return (
      <Pressable testID={`mes-${campo}-error`} accessibilityRole="button" onPress={onReintentar} style={{ minHeight: TACTIL_MIN }}>
        <EstadoDato estado="ERROR_CARGA" detalle="Tocar para reintentar" />
      </Pressable>
    );
  const d = lectura.datos;
  if (campo === 'resultado') {
    const r = resultadoDelMes(d.resultado);
    const color = r.tono === 'positive' ? c.positive : r.tono === 'critical' ? c.critical : c.textPrimary;
    return (
      <Text testID="mes-resultado" style={[importe.secondary, { color, fontVariant: ['tabular-nums'] }]} adjustsFontSizeToFit numberOfLines={1}>
        {r.texto}
      </Text>
    );
  }
  // D-HOME-03: ingresos y gastos neutros (sin color de estado).
  return (
    <Text testID={`mes-${campo}`} style={[importe.secondary, { color: c.textPrimary, fontVariant: ['tabular-nums'] }]} adjustsFontSizeToFit numberOfLines={1}>
      {formatearEur(campo === 'ingresos' ? d.ingresos_propios : d.gastos_propios)}
    </Text>
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
  marca: { flexDirection: 'row', alignItems: 'center', gap: 8, flexShrink: 1 },
  simbolo: { width: 34, height: 34 },
  nombre: { width: 132.25, height: 24 },
  ilustracionCaja: { position: 'absolute', right: 8, top: 0, bottom: 0, justifyContent: 'center' },
  ilustracion: { width: 112, height: 112 },
  perfil: { flexDirection: 'row', alignItems: 'center', gap: espacio.s },
  avatar: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  hero: { borderRadius: radio.l, padding: espacio.l, paddingRight: 112 + 8 + espacio.s, gap: espacio.s, minHeight: 112 + 16, overflow: 'hidden' },
  fila: { flexDirection: 'row' },
  accion: { width: '25%', alignItems: 'center', gap: 2, minHeight: TACTIL_MIN },
  circulo: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center', marginBottom: espacio.xs },
  tresColumnas: { alignItems: 'stretch' },
  columna: { flex: 1, gap: espacio.xs, paddingHorizontal: espacio.xs },
  divisor: { width: StyleSheet.hairlineWidth },
  separador: { height: 1 },
  atencionDerecha: { flexDirection: 'row', alignItems: 'center', gap: espacio.s },
});
