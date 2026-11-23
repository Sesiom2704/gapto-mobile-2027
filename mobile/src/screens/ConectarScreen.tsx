// ============================================================
// GAPTO MOBILE 2027
// Fichero: ConectarScreen.tsx
// Ruta: mobile/src/screens/ConectarScreen.tsx
// Descripción: Pantalla técnica «Conectar con tu PC» (F06 T4 · token BETA_LOCAL, mandato 4f0e40af… §2.3; dictamen AJ-TOK-01/02/05). Se muestra mientras la credencial no está CONECTADA: CARGANDO (lectura del llavero), SIN_CREDENCIAL (campo para pegar o teclear el código y «Conectar»; con el aviso de su motivo), VALIDANDO (comprobando contra el PC), ERROR_DE_CONEXION (el PC no responde: «Reintentar» conserva el código guardado, «Desconectar este iPhone» lo borra; transporte no seguro: la app no se conecta). El código se escribe en un campo oculto, sin autocorrección ni sugerencias, y nunca se muestra ni se registra. Componentes y tokens existentes; sin lámina (mandato §2.3).
// Versión: 0.1.0 (F06 T4 · token BETA_LOCAL)
// ============================================================

import React, { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BotonPrimario, BotonTexto } from '../components/Basicos';
import { Caja, Campo } from '../components/Formulario';
import type { EstadoCredencial, MotivoErrorConexion, MotivoSinCredencial } from '../api/credencial';
import { useTema } from '../theme/tema';
import { espacio, radio, TACTIL_MIN, tipo } from '../theme/tokens';

export const TEXTO_PENDIENTE_SE_CONSERVA = 'Lo que tuvieras pendiente de enviar se conserva: al volver a conectar podrás enviarlo sin duplicarlo.';

export function textoMotivoSin(m: MotivoSinCredencial): string {
  switch (m) {
    case 'CODIGO_INCORRECTO':
      return 'El código no es correcto. No se ha guardado nada.';
    case 'CREDENCIAL_RECHAZADA':
      return `Tu PC ya no acepta el código de este iPhone (ha cambiado). Escribe el código nuevo. ${TEXTO_PENDIENTE_SE_CONSERVA}`;
    case 'NO_COMPROBADO':
      return 'Tu PC no responde y no se ha podido comprobar el código. No se ha guardado nada. Comprueba que el PC y el iPhone están en la misma red y vuelve a intentarlo.';
    case 'DESCONECTADO':
      return 'Este iPhone se ha desconectado de tu PC.';
    case 'LLAVERO_NO_DISPONIBLE':
      return 'No se ha podido usar el llavero de este iPhone. Vuelve a intentarlo.';
  }
}

export function textoMotivoError(m: MotivoErrorConexion): string {
  switch (m) {
    case 'SIN_RESPUESTA':
      return 'Tu PC no responde. El código guardado en este iPhone se conserva: comprueba la red y vuelve a intentarlo.';
    case 'TRANSPORTE_NO_SEGURO':
      return 'La dirección del servidor no es de tu red privada y no usa https. Por seguridad, la app no se conecta.';
    case 'LLAVERO_NO_DISPONIBLE':
      return 'No se ha podido leer el llavero de este iPhone. Vuelve a intentarlo.';
  }
}

export function ConectarScreen(p: {
  estado: EstadoCredencial;
  onConectar: (codigo: string) => void;
  onReintentar: () => void;
  onDesconectar: () => void;
}) {
  const { c } = useTema();
  const inset = useSafeAreaInsets();
  const [codigo, setCodigo] = useState('');
  const e = p.estado;

  if (e.tipo === 'CARGANDO_CREDENCIAL') {
    return (
      <View testID="conectar-cargando" style={[s.centro, { backgroundColor: c.background }]}>
        <ActivityIndicator color={c.textSecondary} />
        <Text style={[tipo.body, { color: c.textSecondary }]}>Preparando la conexión…</Text>
      </View>
    );
  }

  const validando = e.tipo === 'VALIDANDO_CREDENCIAL';
  const error = e.tipo === 'ERROR_DE_CONEXION' ? e : null;
  const motivoSin = e.tipo === 'SIN_CREDENCIAL' ? e.motivo : null;

  return (
    <ScrollView
      testID="pantalla-conectar"
      keyboardShouldPersistTaps="handled"
      style={{ backgroundColor: c.background }}
      contentContainerStyle={[s.contenido, { paddingTop: inset.top + espacio.l }]}
    >
      <Text accessibilityRole="header" style={[tipo.titleLarge, { color: c.textPrimary }]}>Conectar con tu PC</Text>
      {error ? (
        <>
          <Caja testID="conectar-error" aviso={{ tipo: 'AVISO', texto: textoMotivoError(error.motivo) }} />
          {error.motivo !== 'TRANSPORTE_NO_SEGURO' ? (
            <>
              <BotonPrimario testID="conectar-reintentar" titulo="Reintentar" onPress={p.onReintentar} />
              <BotonTexto testID="conectar-desconectar" titulo="Desconectar este iPhone" critico onPress={p.onDesconectar} />
            </>
          ) : null}
        </>
      ) : (
        <>
          <Text style={[tipo.body, { color: c.textSecondary }]}>
            Escribe o pega el código de conexión de tu PC. Se comprueba con el PC y solo entonces se guarda, en el llavero de este iPhone.
          </Text>
          {motivoSin ? <Caja testID="conectar-aviso" aviso={{ tipo: motivoSin === 'DESCONECTADO' ? 'OK' : 'AVISO', texto: textoMotivoSin(motivoSin) }} /> : null}
          <Campo etiqueta="Código de conexión">
            <TextInput
              testID="conectar-codigo"
              accessibilityLabel="Código de conexión"
              value={codigo}
              onChangeText={setCodigo}
              editable={!validando}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="off"
              spellCheck={false}
              textContentType="none"
              importantForAutofill="no"
              placeholder="Código de tu PC"
              placeholderTextColor={c.textSecondary}
              style={[tipo.body, s.input, { color: c.textPrimary, backgroundColor: c.surfacePrimary, borderColor: c.borderStandard }]}
            />
          </Campo>
          <BotonPrimario
            testID="conectar-boton"
            titulo={validando ? 'Comprobando…' : 'Conectar'}
            cargando={validando}
            deshabilitado={!codigo.trim()}
            ayuda={!codigo.trim() ? 'Falta el código.' : undefined}
            onPress={() => p.onConectar(codigo)}
          />
        </>
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  centro: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: espacio.m },
  contenido: { gap: espacio.l, paddingHorizontal: espacio.l, paddingBottom: espacio.xl },
  input: { borderWidth: 1, borderRadius: radio.s, paddingHorizontal: espacio.m, minHeight: TACTIL_MIN + 4 },
});
