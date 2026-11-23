// ============================================================
// GAPTO MOBILE 2027 · LABORATORIO (rama lab-t5; no es implementación de T5)
// Fichero: LabRentaRevisionScreen.tsx
// Ruta: mobile/src/screens/LabRentaRevisionScreen.tsx
// Descripción: L1 · tarea del aniversario de la renta (R4-A, R5, R10, R11; lámina F06-04 v0.6, formato REG-AGIL). Marca «LAB»
//   visible. Se teclea el índice; se ve la renta EXACTA con céntimos y se propone el euro a la baja (editable). «Aplicar»
//   registra la revisión con la renta elegida; «No aplicar este año» la registra sin cambio. Todo por las rutas /v1/lab.
//   SUPUESTO: «Aplicar» solo registra; la versión de la regla y el recálculo de previstos dependen de L2 (RVRX-REGLA).
// Versión: 0.1.0 (LAB T5 · L1)
// ============================================================

import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { BotonPrimario, BotonSecundario } from '../components/Basicos';
import { CabeceraTarea, Campo, CampoTexto } from '../components/Formulario';
import { formatearEur, parsearImporte } from '../domain/importe';
import { useTema } from '../theme/tema';
import { espacio, radio, tipo } from '../theme/tokens';

export interface ClienteLabRentas {
  registrarRevision(contratoId: string, c: {
    aniversario: string; renta_anterior: string; indice_texto: string | null; indice_porcentaje: string | null;
    decision: 'APLICADA' | 'NO_APLICADA'; renta_aplicada?: string; motivo?: string;
  }): Promise<{ ok: boolean; mensaje?: string }>;
}

/** R5: exacta con 4 decimales y propuesta = euro a la baja (mismo cálculo que el servidor de laboratorio). */
export function propuestaRevision(rentaAnterior: number, porcentaje: number): { exacta: number; propuesta: number } {
  const exacta = Math.round(rentaAnterior * (1 + porcentaje / 100) * 10000) / 10000;
  return { exacta, propuesta: Math.floor(exacta) };
}

export function LabRentaRevisionScreen(p: {
  cliente: ClienteLabRentas;
  contratoId: string;
  nombre: string;
  aniversario: string;
  rentaAnterior: string;
  onCerrar: (hecho: boolean) => void;
}) {
  const { c } = useTema();
  const [indice, setIndice] = useState('');
  const [renta, setRenta] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const pct = Number(indice.replace(',', '.'));
  const valido = indice.trim() !== '' && Number.isFinite(pct);
  const calc = valido ? propuestaRevision(Number(p.rentaAnterior), pct) : null;
  const elegida = renta ?? (calc ? String(calc.propuesta) : '');

  const enviar = async (decision: 'APLICADA' | 'NO_APLICADA') => {
    const imp = parsearImporte(elegida);
    if (decision === 'APLICADA' && !imp.ok) return setAviso('Indica la renta que se aplica.');
    const r = await p.cliente.registrarRevision(p.contratoId, {
      aniversario: p.aniversario, renta_anterior: p.rentaAnterior, indice_texto: valido ? 'IPC INE' : null,
      indice_porcentaje: valido ? String(pct) : null, decision,
      ...(decision === 'APLICADA' && imp.ok ? { renta_aplicada: imp.valor } : { motivo: 'No aplicar este año' }),
    });
    if (r.ok) return p.onCerrar(true);
    setAviso(r.mensaje ?? 'No se ha podido registrar.');
  };

  return (
    <View testID="lab-renta-revision" style={{ flex: 1, backgroundColor: c.background }}>
      <CabeceraTarea titulo={`Revisa la renta de ${p.nombre}`} testIDCancelar="lab-cancelar" onCancelar={() => p.onCerrar(false)} />
      <ScrollView contentContainerStyle={{ padding: espacio.l, gap: espacio.l }}>
        <View testID="lab-marca" style={[s.marca, { backgroundColor: c.partialSurface }]}>
          <Text style={[tipo.caption, { color: c.warningText, fontWeight: '700' }]}>LAB · laboratorio de T5, no es la app</Text>
        </View>
        <Text style={[tipo.body, { color: c.textPrimary }]}>{`Renta actual: ${formatearEur(p.rentaAnterior)} · aniversario ${p.aniversario}`}</Text>
        <Campo etiqueta="Índice (IPC, %)">
          <CampoTexto decimal testID="lab-indice" etiqueta="Índice (IPC, %)" marcador="Ej.: 2,0" valor={indice} onCambiar={(t) => { setIndice(t); setRenta(null); }} />
        </Campo>
        {calc ? (
          <Text testID="lab-exacta" style={[tipo.footnote, { color: c.textSecondary }]}>
            {`Exacta: ${calc.exacta.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} € · se propone ${calc.propuesta} € (a la baja)`}
          </Text>
        ) : null}
        <Campo etiqueta="Renta nueva">
          <CampoTexto importe testID="lab-renta" etiqueta="Renta nueva" marcador="0,00" valor={elegida} onCambiar={setRenta} />
        </Campo>
        {aviso ? <Text testID="lab-aviso" style={[tipo.footnote, { color: c.criticalText }]}>{aviso}</Text> : null}
        <BotonPrimario testID="lab-aplicar" titulo="Aplicar" onPress={() => void enviar('APLICADA')} />
        <BotonSecundario testID="lab-no-aplicar" titulo="No aplicar este año" onPress={() => void enviar('NO_APLICADA')} />
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  marca: { borderRadius: radio.s, paddingHorizontal: espacio.m, paddingVertical: espacio.xs, alignSelf: 'flex-start' },
});
