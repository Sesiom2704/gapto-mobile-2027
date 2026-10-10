// ============================================================
// GAPTO MOBILE 2027
// Fichero: GuardarPreferencia.tsx
// Ruta: mobile/src/components/GuardarPreferencia.tsx
// Descripción: «Guardar como preferencia» en la pantalla de éxito de «Nuevo gasto» (F05-02 B2; F05-D026 §41.3, AJ-P02-05; lámina SET-PREF / REG-PREF v0.1 R05–R07, D-PREF-05/06). Escritura INDEPENDIENTE y posterior al hecho: el hecho nunca se ve afectado. Tarjeta «¿Recordarlo para <categoría>?» con una casilla por campo (marcada si el valor final difiere de lo propuesto). Al guardar se relee la lista y se decide: sin preferencia de la categoría → alta con el UUID generado al abrir la tarjeta (el reintento usa el MISMO); con preferencia que no contradice → edición con el ESTADO COMPLETO (E05); si contradice (o el servidor responde PREFERENCIA_EMPATE_CONTRADICTORIO) → hoja R07 «Sustituir / Mantener»; VERSION_DESFASADA → se recarga y se vuelve a preguntar. Fallo → aviso R06 con «Reintentar»; éxito → «Preferencia guardada». Ninguna escritura sin acción del usuario.
// Versión: 0.1.0 (F05-02 B2)
// Versión: 0.2.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E3): la preferencia de la categoría lleva el tipo GASTO que informa la lista (`tipos.GASTO`).
// Versión: 0.3.0 (F05-03/F05-04 J2 §2.4; lámina REG-DYN N01): con `ambitos` (registro por tipo) la tarjeta pregunta «¿Recordarlo para la próxima vez?» y ofrece «Para <tercero>» / «Para <categoría>» (uno solo: nunca ambos); la preferencia lleva el tipo del registro (GASTO o INGRESO) y la clave del ámbito elegido. En ingresos, «Cobrado en». Sin `ambitos`, el comportamiento de F05-02 no cambia.
// ============================================================

import React, { useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ClienteApi, CuentaPago, Respuesta, ResultadoComandoPreferencia } from '../api/cliente';
import { AmbitoRecordable, Casillas, PlanGuardado, planificarGuardadoClave, siNo, ValoresFinales } from '../domain/preferencias';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';
import { BotonPrimario, Segmentado, Velo } from './Basicos';
import { BotonSecundario } from './SelectorCategorias';

type Conflicto = Extract<PlanGuardado, { tipo: 'CONFLICTO' }>;

type Fase = { f: 'EDITANDO' } | { f: 'GUARDANDO' } | { f: 'ERROR' } | { f: 'CONFLICTO'; plan: Conflicto } | { f: 'GUARDADA' };

export function GuardarPreferencia(p: {
  cliente: ClienteApi;
  nuevoId: () => string;
  categoriaId: string | null;
  nombre: string;
  finales: ValoresFinales;
  casillas: Casillas;
  cuentas: CuentaPago[] | { cuenta_id: string; nombre: string }[];
  /** F05-04: ámbitos posibles (tercero y/o categoría); se guarda UNO. */
  ambitos?: AmbitoRecordable[];
  tipo?: 'GASTO' | 'INGRESO';
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  // UUID del alta generado al abrir la tarjeta: un reintento reutiliza el MISMO (R06).
  const [idAlta] = useState(() => p.nuevoId());
  const [casillas, setCasillas] = useState<Casillas>(p.casillas);
  const [fase, setFase] = useState<Fase>({ f: 'EDITANDO' });
  /** Casillas del intento en curso: «Reintentar» repite exactamente la misma escritura. */
  const intento = useRef<Casillas | null>(null);
  const [ambito, setAmbito] = useState<AmbitoRecordable | null>(p.ambitos?.[0] ?? null);
  const tipoReg = p.tipo ?? 'GASTO';
  const clave = ambito
    ? { categoriaId: ambito.clave === 'CATEGORIA' ? ambito.id : null, terceroId: ambito.clave === 'TERCERO' ? ambito.id : null }
    : { categoriaId: p.categoriaId, terceroId: null };
  const nombre = ambito ? ambito.nombre : p.nombre;
  const verboCuenta = tipoReg === 'INGRESO' ? 'Cobrado en' : 'Pagar con';

  const nombreCuenta = (id: string | null) => (p.cuentas as { cuenta_id: string; nombre: string }[]).find((x) => x.cuenta_id === id)?.nombre ?? 'una cuenta no disponible';

  const volverAPreguntar = (plan: PlanGuardado) => {
    if (plan.tipo === 'CONFLICTO') return setFase({ f: 'CONFLICTO', plan });
    intento.current = null;
    setFase({ f: 'EDITANDO' });
  };

  const tras = async (r: Respuesta<ResultadoComandoPreferencia>) => {
    if (r.tipo === 'OK') return setFase({ f: 'GUARDADA' });
    if (r.tipo === 'RECHAZADO' && (r.codigo === 'PREFERENCIA_EMPATE_CONTRADICTORIO' || r.codigo === 'VERSION_DESFASADA')) {
      // Cambió mientras tanto: se recarga y se vuelve a preguntar (R07), sin escribir.
      const l = await p.cliente.listarPreferencias();
      if (l.tipo !== 'OK') return setFase({ f: 'ERROR' });
      return volverAPreguntar(planificarGuardadoClave(l.datos.preferencias, clave, p.finales, intento.current ?? casillas, l.datos.tipos[tipoReg]));
    }
    setFase({ f: 'ERROR' });
  };

  const guardar = async () => {
    const elegidas = intento.current ?? casillas;
    intento.current = elegidas;
    setFase({ f: 'GUARDANDO' });
    const l = await p.cliente.listarPreferencias();
    if (l.tipo !== 'OK') return setFase({ f: 'ERROR' });
    const plan = planificarGuardadoClave(l.datos.preferencias, clave, p.finales, elegidas, l.datos.tipos[tipoReg]);
    if (plan.tipo === 'NADA' || plan.tipo === 'CONFLICTO') return volverAPreguntar(plan);
    if (plan.tipo === 'ALTA') return tras(await p.cliente.altaPreferencia({ id: idAlta, ...plan.contenido }));
    return tras(await p.cliente.editarPreferencia(plan.existente.id, { row_version: plan.existente.row_version, ...plan.contenido }));
  };

  const sustituir = async (plan: Conflicto) => {
    setFase({ f: 'GUARDANDO' });
    await tras(await p.cliente.editarPreferencia(plan.existente.id, { row_version: plan.existente.row_version, ...plan.contenido }));
  };

  const mantener = () => {
    intento.current = null;
    setFase({ f: 'EDITANDO' });
  };

  if (fase.f === 'GUARDADA') {
    return (
      <View testID="pref-guardada" accessibilityLiveRegion="polite" style={[s.aviso, { backgroundColor: c.textPrimary }]}>
        <Text style={[tipo.footnote, { color: c.background, textAlign: 'center' }]}>Preferencia guardada</Text>
      </View>
    );
  }

  if (fase.f === 'ERROR') {
    return (
      <View style={{ gap: espacio.s }}>
        <View testID="pref-error" accessibilityRole="alert" style={[s.caja, { backgroundColor: c.partialSurface, borderColor: c.warning }]}>
          <Text style={[tipo.footnote, { color: c.textPrimary }]}>
            <Text style={{ fontWeight: '600', color: c.warning }}>No se pudo guardar la preferencia.</Text> {tipoReg === 'INGRESO' ? 'El ingreso' : 'El gasto'} sí está registrado. Puedes
            reintentarlo o crearla luego en Ajustes › Preferencias.
          </Text>
        </View>
        <BotonSecundario testID="pref-reintentar" titulo="Reintentar" onPress={() => void guardar()} />
      </View>
    );
  }

  const guardando = fase.f === 'GUARDANDO';
  const actual = fase.f === 'CONFLICTO' ? fase.plan.existente : null;
  return (
    <>
      <View testID="pref-tarjeta" style={[s.tarjeta, { backgroundColor: c.surfacePrimary, borderColor: c.borderDefault }]}>
        <Text accessibilityRole="header" style={[tipo.subheadline, { color: c.textPrimary, fontWeight: '600' }]}>
          {p.ambitos ? '¿Recordarlo para la próxima vez?' : `¿Recordarlo para ${p.nombre}?`}
        </Text>
        {p.ambitos && p.ambitos.length > 1 ? (
          <Segmentado<string>
            testIDBase="pref-ambito"
            etiquetaGrupo="Recordar para"
            opciones={p.ambitos.map((a) => ({ valor: a.clave, etiqueta: `Para ${a.nombre}` }))}
            valor={ambito?.clave ?? null}
            onCambiar={(v) => {
              if (guardando) return;
              intento.current = null;
              setAmbito(p.ambitos!.find((a) => a.clave === v) ?? null);
            }}
          />
        ) : null}
        <Casilla
          testID="pref-casilla-cuenta"
          marcada={casillas.cuenta}
          deshabilitada={guardando}
          onPress={() => setCasillas((x) => ({ ...x, cuenta: !x.cuenta }))}
          accesibilidad={`${verboCuenta} ${nombreCuenta(p.finales.cuenta)}`}
        >
          {verboCuenta} <Text style={{ fontWeight: '600' }}>{nombreCuenta(p.finales.cuenta)}</Text>
        </Casilla>
        <Casilla
          testID="pref-casilla-presupuestable"
          marcada={casillas.presupuestable}
          deshabilitada={guardando}
          onPress={() => setCasillas((x) => ({ ...x, presupuestable: !x.presupuestable }))}
          accesibilidad={`Cuenta para el presupuesto: ${siNo(p.finales.presupuestable)}`}
        >
          Cuenta para el presupuesto: <Text style={{ fontWeight: '600' }}>{siNo(p.finales.presupuestable)}</Text>
        </Casilla>
        <Text style={[tipo.caption, { color: c.textSecondary }]}>{`Se propondrá en tus próximos ${tipoReg === 'INGRESO' ? 'ingresos' : 'gastos'} de ${nombre}. Podrás cambiarlo siempre.`}</Text>
        <BotonSecundario
          testID="pref-guardar"
          titulo={guardando ? 'Guardando…' : 'Guardar preferencia'}
          onPress={() => {
            if (!guardando && (casillas.cuenta || casillas.presupuestable)) void guardar();
          }}
        />
      </View>

      {fase.f === 'CONFLICTO' && actual ? (
        // Por encima de lo que la pantalla pinta después (espaciador y «Volver a Inicio»): detectado en E2E web.
        <View testID="pref-conflicto" style={[StyleSheet.absoluteFill, s.capa, { justifyContent: 'flex-end' }]}>
          <Velo />
          <View style={[s.hoja, { backgroundColor: c.surfacePrimary, paddingBottom: inset.bottom + espacio.l }]}>
            <Text accessibilityRole="header" style={[tipo.titleSmall, { color: c.textPrimary }]}>{`Ya tienes una preferencia para ${nombre}`}</Text>
            <Text testID="pref-conflicto-texto" style={[tipo.footnote, { color: c.textSecondary }]}>
              {'Ahora propone '}
              {fase.plan.campos.map((campo, i) => (
                <Text key={campo}>
                  {i > 0 ? ' y ' : ''}
                  {campo === 'cuenta' ? 'pagar con ' : 'que cuenta para el presupuesto: '}
                  <Text style={{ fontWeight: '600' }}>{campo === 'cuenta' ? nombreCuenta(actual.cuenta_default_id) : siNo(actual.presupuestable_default!)}</Text>
                </Text>
              ))}
              {'. ¿Quieres que proponga '}
              {fase.plan.campos.map((campo, i) => (
                <Text key={campo}>
                  {i > 0 ? ' y ' : ''}
                  {campo === 'cuenta' ? '' : 'que cuenta para el presupuesto: '}
                  <Text style={{ fontWeight: '600' }}>{campo === 'cuenta' ? nombreCuenta(p.finales.cuenta) : siNo(p.finales.presupuestable)}</Text>
                </Text>
              ))}
              {' a partir de ahora?'}
            </Text>
            <BotonPrimario testID="pref-sustituir" titulo="Sustituir" onPress={() => void sustituir(fase.plan)} />
            <BotonSecundario
              testID="pref-mantener"
              titulo={fase.plan.campos.length === 1 && fase.plan.campos[0] === 'cuenta' ? `Mantener ${nombreCuenta(actual.cuenta_default_id)}` : 'Mantener la actual'}
              onPress={mantener}
            />
          </View>
        </View>
      ) : null}
    </>
  );
}

function Casilla(p: { marcada: boolean; deshabilitada: boolean; onPress: () => void; accesibilidad: string; testID: string; children: React.ReactNode }) {
  const { c } = useTema();
  return (
    <Pressable
      testID={p.testID}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: p.marcada, disabled: p.deshabilitada }}
      aria-checked={p.marcada}
      accessibilityLabel={p.accesibilidad}
      disabled={p.deshabilitada}
      onPress={p.onPress}
      style={s.casilla}
    >
      <View style={[s.caja18, { borderColor: p.marcada ? c.accent : c.borderStandard, backgroundColor: p.marcada ? c.accent : c.surfacePrimary }]}>
        {p.marcada ? <Text style={[tipo.caption, { color: c.onAccent }]}>✓</Text> : null}
      </View>
      <Text style={[tipo.subheadline, { color: c.textPrimary, flexShrink: 1 }]}>{p.children}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  tarjeta: { borderRadius: radio.m, borderWidth: 1, padding: espacio.m, gap: espacio.m },
  casilla: { flexDirection: 'row', alignItems: 'center', gap: espacio.s, minHeight: TACTIL_MIN },
  caja18: { width: 20, height: 20, borderRadius: radio.s, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
  caja: { borderRadius: radio.m, borderWidth: 1, padding: espacio.m },
  aviso: { borderRadius: radio.m, padding: espacio.m },
  capa: { zIndex: 10, elevation: 10 },
  hoja: { borderTopLeftRadius: radio.xl, borderTopRightRadius: radio.xl, padding: espacio.l, gap: espacio.m },
});
