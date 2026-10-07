// ============================================================
// GAPTO MOBILE 2027
// Fichero: vs01.test.tsx
// Ruta: mobile/__tests__/vs01.test.tsx
// Descripción: Tests de cliente VS-01 (mandato §22): Home, acción rápida, validación, «Solo mío» explícito, presupuestable no inventado, intención correcta, doble tap, timeout conserva identidad, error no muestra éxito, éxito refresca Home desde backend.
// v0.2.0 (F05-D003): tarjeta parcial de Home fuera de «Este mes», fecha editable ≤ hoy, financiación visible y sellada, rechazo por propuesta obsoleta.
// v0.3.0 (F05 — VS-01 · Alineación visual): A1 — los bloques de Home no son tarjetas; A2 — SPEC-08: «Registrar gasto» desactivado mientras falte una decisión bloqueante, con indicación visible de lo que falta. Los tests de validación (antes: pulsar y leer errores) comprueban ahora el estado disabled de forma discriminante y conservan la propiedad «ante cualquier condición bloqueante no se produce ninguna petición ni mutación».
// v0.4.0 (F05-01 S6-WIRE+UI (este mandato)): el estado categorial es una decisión bloqueante más (S6-WIRE, F09 §12.97.1). El cliente simulado sirve el árbol de categorías; `rellenar()` elige por defecto «Sin categoría» en el selector (decisión explícita); `faltan` nombra la categoría y la intención sellada lleva {estado:'SIN_CATEGORIA'}. Las pruebas de REG-CAT viven en regcat.test.tsx.
// v0.5.0 (F05-02 B2): el cliente simulado sirve la propuesta del resolver con la única cuenta (DEFAULT_GENERAL); el fallback del cliente se retira (AJ-B1-09). Los casos VS-01 no cambian; los de preferencias viven en preferencias_registro.test.tsx.
// Versión: 0.5.0
// ============================================================

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';
import React from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Raiz } from '../App';
import type { ClienteApi, CuentaPago, GastoMes, Respuesta, ResultadoRegistro } from '../src/api/cliente';
import type { CategoriaNodo } from '../src/domain/categoria';
import type { PayloadGastoPagado } from '../src/domain/intencion';
import { ProveedorTema } from '../src/theme/tema';

import { clienteCategoriasStub, propuestaUnica } from './fixtures_categorias';

const CUENTA = 'c0000000-0000-4000-8000-000000000001';
const AHORA = () => new Date(2026, 8, 24, 10, 0, 0);

function gasto(valor: string, estado: 'CONFIRMADO' | 'PARCIAL' = 'CONFIRMADO', sinReparto = 0): Respuesta<GastoMes> {
  return { tipo: 'OK', datos: { mes: '2026-09', moneda: 'EUR', gasto_atribuible: valor, estado, gastos_sin_reparto: sinReparto, gastos_otra_moneda: 0, contrato: 'PROVISIONAL_VS01_CANDIDATO_F08' } };
}

function ok(p: PayloadGastoPagado): Respuesta<ResultadoRegistro> {
  return { tipo: 'OK', datos: { hecho_id: p.intencion_id, idempotente: false, importe: p.importe, estado_atribucion: p.atribucion === 'SOLO_MIO' ? 'COMPLETA' : 'NO_DISPONIBLE', aportacion_criterio: p.financiacion.estado === 'PROPUESTA_ACEPTADA' ? 'PARTICIPACION_CUENTA' : null, financiacion: p.financiacion.estado, estado_categorial: p.categoria.estado } };
}

type Propuesta = CuentaPago['propuesta_financiacion'];

function crearFake(
  opciones: {
    registrar?: (p: PayloadGastoPagado) => Promise<Respuesta<ResultadoRegistro>>;
    gastos?: Respuesta<GastoMes>[];
    propuesta?: (fecha: string) => Propuesta;
    categorias?: CategoriaNodo[];
  } = {},
) {
  const enviados: PayloadGastoPagado[] = [];
  const fechasConsultadas: string[] = [];
  const colaGastos = [...(opciones.gastos ?? [gasto('0.00'), gasto('3.50')])];
  let lecturasHome = 0;
  const cliente: ClienteApi = {
    registrarGastoPagado: jest.fn(async (p) => {
      enviados.push(p);
      return (opciones.registrar ?? (async (x) => ok(x)))(p);
    }),
    cuentasPago: jest.fn(async (fecha: string) => {
      fechasConsultadas.push(fecha);
      const propuesta = (opciones.propuesta ?? (() => 'SELF_100' as Propuesta))(fecha);
      return { tipo: 'OK', datos: { cuentas: [{ cuenta_id: CUENTA, nombre: 'Cuenta corriente (sintética)', moneda: 'EUR', propuesta_financiacion: propuesta }] } } as Respuesta<{ cuentas: CuentaPago[] }>;
    }),
    gastoMes: jest.fn(async () => {
      lecturasHome += 1;
      return colaGastos.length > 1 ? colaGastos.shift()! : colaGastos[0];
    }),
    ...clienteCategoriasStub(opciones.categorias ?? []),
    propuestaPreferencias: propuestaUnica(CUENTA), // el resolver propone la única cuenta (DEFAULT_GENERAL)
  };
  return { cliente, enviados, fechasConsultadas, lecturas: () => lecturasHome };
}

/** Ninguna petición de escritura ni mutación: ni llamadas al cliente ni payloads. */
function sinEscritura(f: ReturnType<typeof crearFake>) {
  expect(f.cliente.registrarGastoPagado).not.toHaveBeenCalled();
  expect(f.enviados).toHaveLength(0);
}

/** Pulsa «Registrar gasto» estando desactivado y comprueba que no escribe nada. */
async function pulsarBloqueado(f: ReturnType<typeof crearFake>) {
  expect(screen.getByTestId('registrar')).toBeDisabled();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  sinEscritura(f);
}

let contadorIds = 0;
const nuevoId = () => `00000000-0000-4000-8000-${String(++contadorIds).padStart(12, '0')}`;

function montar(cliente: ClienteApi) {
  return render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 393, height: 852 }, insets: { top: 59, left: 0, right: 0, bottom: 34 } }}>
      <ProveedorTema forzar="light">
        <Raiz cliente={cliente} nuevoId={nuevoId} ahora={AHORA} />
      </ProveedorTema>
    </SafeAreaProvider>,
  );
}

async function abrirFormulario() {
  fireEvent.press(await screen.findByTestId('accion-gasto'));
  await screen.findByTestId('registro-form');
  await screen.findByTestId('origen-cuenta'); // cuentas cargadas (única -> inferida visible)
  await screen.findByTestId('financiacion'); // propuesta conocida para la fecha
}

function rellenar({ importe = '3,50', concepto = 'Café', presupuestable = true as boolean | null, soloMio = true, sinCategoria = true } = {}) {
  fireEvent.changeText(screen.getByTestId('campo-importe'), importe);
  fireEvent.changeText(screen.getByTestId('campo-concepto'), concepto);
  if (sinCategoria) elegirSinCategoria();
  if (presupuestable !== null) fireEvent.press(screen.getByTestId(`presupuestable-${presupuestable}`));
  if (soloMio) fireEvent.press(screen.getByTestId('solo-mio'));
}

/** Decisión explícita «Sin categoría» desde el selector (S6-WIRE: la categoría ya no es opcional). */
function elegirSinCategoria() {
  fireEvent.press(screen.getByTestId('campo-categoria'));
  fireEvent.press(screen.getByTestId('selector-sin-categoria'));
}

beforeEach(() => {
  contadorIds = 0;
});

test('Home renderiza el esqueleto HOME-01 sin cifras inventadas', async () => {
  const f = crearFake({ gastos: [gasto('12.40')] });
  montar(f.cliente);
  expect(await screen.findByText('12,40 €')).toBeTruthy();
  for (const id of ['bloque-liquidez', 'accion-gasto', 'bloque-mes', 'bloque-gasto-parcial', 'bloque-proximos', 'bloque-patrimonio', 'tab-INICIO', 'tab-MAS']) {
    expect(screen.getByTestId(id)).toBeTruthy();
  }
  // Ningún bloque sin read model muestra un importe
  expect(screen.queryAllByText(/€$/).length).toBe(1);
  expect(screen.getAllByText('No disponible').length).toBeGreaterThanOrEqual(6);
});

test('Home (F05-D003 §16.6): la cifra real va en tarjeta PARCIAL separada, nunca en «Este mes»', async () => {
  const f = crearFake({ gastos: [gasto('12.40')] });
  montar(f.cliente);
  await screen.findByText('12,40 €');
  expect(within(screen.getByTestId('bloque-mes')).queryAllByText(/€/)).toHaveLength(0);
  expect(within(screen.getByTestId('bloque-mes')).getAllByText('No disponible').length).toBe(4);
  const tarjeta = within(screen.getByTestId('bloque-gasto-parcial'));
  expect(tarjeta.getByText('12,40 €')).toBeTruthy();
  expect(tarjeta.getByTestId('gastos-parcial')).toBeTruthy(); // siempre marcada como parcial
  expect(tarjeta.getByTestId('gasto-parcial-aviso').props.children).toMatch(/No es tu gasto total/);
});

test('Home: gasto PARCIAL se marca y no se presenta como total confirmado', async () => {
  const f = crearFake({ gastos: [gasto('3.50', 'PARCIAL', 2)] });
  montar(f.cliente);
  expect(await screen.findByTestId('gastos-parcial')).toBeTruthy();
  expect(screen.getByText('2 sin reparto conocido')).toBeTruthy();
});

test('Home: fallo de lectura es parcial y reintentable, no 0 €', async () => {
  const f = crearFake({ gastos: [{ tipo: 'INDETERMINADO', mensaje: 'x' }, gasto('1.00')] });
  montar(f.cliente);
  expect(await screen.findByTestId('gastos-error')).toBeTruthy();
  expect(screen.queryByText('0,00 €')).toBeNull();
  fireEvent.press(screen.getByTestId('gastos-error'));
  expect(await screen.findByText('1,00 €')).toBeTruthy();
});

test('la acción rápida abre el registro y oculta la barra inferior (tarea CREATE)', async () => {
  montar(crearFake().cliente);
  await abrirFormulario();
  expect(screen.queryByTestId('tab-INICIO')).toBeNull();
});

test('validación local de importe y concepto: botón desactivado, errores al escribir, nada se envía', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  fireEvent.changeText(screen.getByTestId('campo-importe'), '3,505');
  fireEvent.press(screen.getByTestId('presupuestable-true'));
  // El error de formato se ve sin pulsar nada (SPEC-08: no depende del botón desactivado).
  expect(screen.getByText('Máximo dos decimales.')).toBeTruthy();
  expect(screen.getByTestId('faltan').props.children).toBe('Para registrar falta: importe válido, concepto y categoría.');
  await pulsarBloqueado(f);
  fireEvent.changeText(screen.getByTestId('campo-importe'), '0');
  expect(screen.getByText('El importe debe ser mayor que 0.')).toBeTruthy();
  await pulsarBloqueado(f);
  // Discriminante inverso: completar lo que falta habilita el botón.
  fireEvent.changeText(screen.getByTestId('campo-importe'), '3,50');
  fireEvent.changeText(screen.getByTestId('campo-concepto'), 'Café');
  expect(screen.getByTestId('faltan').props.children).toBe('Para registrar falta: categoría.');
  await pulsarBloqueado(f);
  elegirSinCategoria();
  expect(screen.getByTestId('registrar')).toBeEnabled();
  expect(screen.queryByTestId('faltan')).toBeNull();
  sinEscritura(f);
});

test('presupuestable no se inventa: sin elección el botón está desactivado y no hay envío', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  rellenar({ presupuestable: null });
  expect(screen.getByTestId('faltan').props.children).toBe('Para registrar falta: si cuenta para el presupuesto.');
  await pulsarBloqueado(f);
  fireEvent.press(screen.getByTestId('presupuestable-false'));
  expect(screen.getByTestId('registrar')).toBeEnabled();
  sinEscritura(f);
});

test('«Solo mío» exige acción explícita: sin tocarlo se envía SIN_INDICAR', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  expect(screen.getByTestId('origen-atribucion').props.children).toMatch(/Sin indicar/);
  rellenar({ soloMio: false });
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[0].atribucion).toBe('SIN_INDICAR');
});

test('submit construye la intención correcta (magnitud positiva, decisiones explícitas, fecha local)', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  rellenar({ importe: '3,50', concepto: '  Café ', presupuestable: false });
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados).toEqual([
    {
      intencion_id: '00000000-0000-4000-8000-000000000001', concepto: 'Café', importe: '3.50', moneda: 'EUR', fecha_hecho: '2026-09-24', cuenta_id: CUENTA, presupuestable: false, atribucion: 'SOLO_MIO',
      financiacion: { estado: 'PROPUESTA_ACEPTADA', actor: 'SELF', criterio: 'PARTICIPACION_CUENTA', porcentaje: '100', importe: '3.50' },
      categoria: { estado: 'SIN_CATEGORIA' },
    },
  ]);
});

test('doble tap no duplica el envío', async () => {
  let liberar: () => void = () => {};
  const f = crearFake({ registrar: (p) => new Promise((res) => { liberar = () => res(ok(p)); }) });
  montar(f.cliente);
  await abrirFormulario();
  rellenar();
  await act(async () => {
    fireEvent.press(screen.getByTestId('registrar'));
    fireEvent.press(screen.getByTestId('registrar'));
    fireEvent.press(screen.getByTestId('registrar'));
  });
  expect(f.enviados).toHaveLength(1);
  await act(async () => liberar());
  expect(await screen.findByTestId('registro-exito')).toBeTruthy();
  expect(f.enviados).toHaveLength(1);
});

test('timeout: estado indeterminado, payload sellado y reintento con la MISMA identidad', async () => {
  let n = 0;
  const f = crearFake({ registrar: async (p) => (++n === 1 ? { tipo: 'INDETERMINADO', mensaje: 'No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.' } : ok(p)) });
  montar(f.cliente);
  await abrirFormulario();
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  expect(await screen.findByTestId('estado-indeterminado')).toBeTruthy();
  expect(screen.queryByTestId('registro-exito')).toBeNull();
  // El payload está sellado: editar no altera lo que se reintenta
  fireEvent.changeText(screen.getByTestId('campo-importe'), '99');
  await act(async () => fireEvent.press(screen.getByTestId('reintentar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados).toHaveLength(2);
  expect(f.enviados[1]).toEqual(f.enviados[0]);
});

test('error de dominio no muestra éxito ni vuelve a Home; el siguiente envío usa identidad nueva', async () => {
  let n = 0;
  const f = crearFake({ registrar: async (p) => (++n === 1 ? { tipo: 'RECHAZADO', codigo: 'CUENTA_DESCONOCIDA', mensaje: 'La cuenta seleccionada no está disponible.' } : ok(p)) });
  montar(f.cliente);
  await abrirFormulario();
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  expect(await screen.findByTestId('error-dominio')).toBeTruthy();
  expect(screen.queryByTestId('registro-exito')).toBeNull();
  expect(screen.getByTestId('registro-form')).toBeTruthy();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[1].intencion_id).not.toBe(f.enviados[0].intencion_id);
});

test('éxito: confirmación inequívoca y Home refrescada desde el backend (sin optimistic update)', async () => {
  const f = crearFake({ gastos: [gasto('0.00'), gasto('3.50')] });
  montar(f.cliente);
  expect(await screen.findByText('0,00 €')).toBeTruthy();
  await abrirFormulario();
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  expect(await screen.findByText('Gasto registrado')).toBeTruthy();
  const antes = f.lecturas();
  fireEvent.press(screen.getByTestId('volver-inicio'));
  await waitFor(() => expect(f.lecturas()).toBe(antes + 1));
  expect(await screen.findByText('3,50 €')).toBeTruthy();
  expect(screen.getByTestId('tab-INICIO')).toBeTruthy();
});

test('cancelar con datos pide confirmación; sin datos sale directamente', async () => {
  montar(crearFake().cliente);
  await abrirFormulario();
  fireEvent.press(screen.getByTestId('cancelar')); // cuenta única inferida no cuenta como modificación
  expect(await screen.findByTestId('tab-INICIO')).toBeTruthy();
  await abrirFormulario();
  fireEvent.changeText(screen.getByTestId('campo-concepto'), 'x');
  fireEvent.press(screen.getByTestId('cancelar'));
  expect(screen.getByTestId('confirmar-salida')).toBeTruthy();
});

// ------------------------------------------------ F05-D003 REG-01 / §16.4
test('financiación: cuenta 100 % propia se propone visible y se sella sin toque adicional', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  expect(screen.getByTestId('financiacion-texto').props.children).toBe('Financiado por ti · cuenta 100 % tuya');
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[0].financiacion.estado).toBe('PROPUESTA_ACEPTADA');
  expect(screen.getByTestId('exito-financiacion').props.children).toBe('Financiado por ti.');
});

test('financiación: «No es así» sella NO_DETERMINADA y cuenta como modificación', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  fireEvent.press(screen.getByTestId('financiacion-no-es-asi'));
  expect(screen.getByTestId('financiacion-texto').props.children).toBe('Financiación no determinada');
  fireEvent.press(screen.getByTestId('cancelar'));
  expect(screen.getByTestId('confirmar-salida')).toBeTruthy();
  fireEvent.press(screen.getByTestId('seguir'));
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[0].financiacion).toEqual({ estado: 'NO_DETERMINADA' });
});

test('financiación: cuenta sin propuesta muestra «no determinada», sin opción de aceptar nada', async () => {
  const f = crearFake({ propuesta: () => 'NO_DETERMINADA' });
  montar(f.cliente);
  await abrirFormulario();
  expect(screen.getByTestId('financiacion-texto').props.children).toBe('Financiación no determinada');
  expect(screen.queryByTestId('financiacion-no-es-asi')).toBeNull();
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[0].financiacion).toEqual({ estado: 'NO_DETERMINADA' });
});

test('fecha: «Ayer» recarga la propuesta de ESA fecha y se sella como fecha del gasto y del pago', async () => {
  // La cuenta pasa a compartida desde hoy: ayer era 100 % propia.
  const f = crearFake({ propuesta: (fecha) => (fecha < '2026-09-24' ? 'SELF_100' : 'NO_DETERMINADA') });
  montar(f.cliente);
  await abrirFormulario();
  expect(screen.getByTestId('financiacion-texto').props.children).toBe('Financiación no determinada');
  fireEvent.press(screen.getByTestId('fecha-ayer'));
  await waitFor(() => expect(f.fechasConsultadas).toContain('2026-09-23'));
  await waitFor(() => expect(screen.getByTestId('financiacion-texto').props.children).toBe('Financiado por ti · cuenta 100 % tuya'));
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[0].fecha_hecho).toBe('2026-09-23');
  expect(f.enviados[0].financiacion.estado).toBe('PROPUESTA_ACEPTADA');
});

test('fecha: otra fecha futura o inválida desactiva el botón y no se envía', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  rellenar();
  expect(screen.getByTestId('registrar')).toBeEnabled();
  fireEvent.press(screen.getByTestId('fecha-otra'));
  fireEvent.changeText(screen.getByTestId('campo-fecha'), '25/09/2026');
  expect(screen.getByText('Solo gastos ya ocurridos: la fecha no puede ser futura.')).toBeTruthy();
  expect(screen.getByTestId('faltan').props.children).toBe('Para registrar falta: fecha válida.');
  await pulsarBloqueado(f);
  fireEvent.changeText(screen.getByTestId('campo-fecha'), '31/02/2026');
  expect(screen.getByText('Fecha no válida (dd/mm/aaaa).')).toBeTruthy();
  await pulsarBloqueado(f);
  expect(f.fechasConsultadas).not.toContain('2026-09-25'); // una fecha futura ni siquiera pide propuesta
});

test('propuesta obsoleta: rechazo definitivo, se recarga la propuesta y el siguiente envío usa identidad nueva', async () => {
  let n = 0;
  let compartida = false;
  const f = crearFake({
    propuesta: () => (compartida ? 'NO_DETERMINADA' : 'SELF_100'),
    registrar: async (p) => {
      if (++n === 1) {
        compartida = true; // la cuenta cambió entre abrir el formulario y confirmar
        return { tipo: 'RECHAZADO', codigo: 'PROPUESTA_FINANCIACION_OBSOLETA', mensaje: 'La cuenta ha cambiado de titularidad desde que abriste el formulario. Revisa la financiación: no se ha guardado nada.' };
      }
      return ok(p);
    },
  });
  montar(f.cliente);
  await abrirFormulario();
  rellenar();
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  expect(await screen.findByTestId('error-dominio')).toBeTruthy();
  await waitFor(() => expect(screen.getByTestId('financiacion-texto').props.children).toBe('Financiación no determinada'));
  await act(async () => fireEvent.press(screen.getByTestId('registrar')));
  await screen.findByTestId('registro-exito');
  expect(f.enviados[1].intencion_id).not.toBe(f.enviados[0].intencion_id);
  expect(f.enviados[1].financiacion).toEqual({ estado: 'NO_DETERMINADA' });
});

// ------------------------------------------------ SPEC-08 (REG-SPEC-01), aplicación prospectiva
test('SPEC-08: al abrir, todo lo bloqueante pendiente se indica y el botón está desactivado', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  expect(screen.getByTestId('registrar')).toBeDisabled();
  expect(screen.getByTestId('faltan').props.children).toBe('Para registrar falta: importe, concepto, categoría y si cuenta para el presupuesto.');
  expect(screen.getByTestId('registrar').props.accessibilityHint).toBe('Para registrar falta: importe, concepto, categoría y si cuenta para el presupuesto.');
  await pulsarBloqueado(f);
});

test('SPEC-08: «Pagado con» cargando bloquea aunque el resto esté completo', async () => {
  let liberar: () => void = () => {};
  const f = crearFake();
  const original = f.cliente.cuentasPago as jest.Mock;
  const impl = original.getMockImplementation()!;
  original.mockImplementation((fecha: string) => new Promise((res) => { liberar = () => res(impl(fecha)); }));
  montar(f.cliente);
  fireEvent.press(await screen.findByTestId('accion-gasto'));
  await screen.findByTestId('registro-form');
  rellenar();
  expect(screen.getByText('Cargando…')).toBeTruthy();
  expect(screen.getByTestId('faltan').props.children).toBe('Para registrar falta: cuenta de pago.');
  await pulsarBloqueado(f);
  await act(async () => liberar());
  await screen.findByTestId('financiacion');
  expect(screen.getByTestId('registrar')).toBeEnabled();
  sinEscritura(f);
});

test('SPEC-08: la atribución sin respuesta NO bloquea', async () => {
  const f = crearFake();
  montar(f.cliente);
  await abrirFormulario();
  rellenar({ soloMio: false });
  expect(screen.getByTestId('registrar')).toBeEnabled();
  expect(screen.queryByTestId('faltan')).toBeNull();
});

// ------------------------------------------------ A1 (F09 §6): bloques sin tarjeta
test('A1: los bloques de Home no son tarjetas (sin superficie propia ni radio) y se separan con línea estructural', async () => {
  const f = crearFake({ gastos: [gasto('12.40')] });
  montar(f.cliente);
  await screen.findByText('12,40 €');
  for (const id of ['bloque-acciones', 'bloque-mes', 'bloque-gasto-parcial', 'bloque-proximos', 'bloque-patrimonio']) {
    const st = StyleSheet.flatten(screen.getByTestId(id).props.style);
    expect(st.backgroundColor).toBeUndefined();
    expect(st.borderRadius).toBeUndefined();
  }
  expect(StyleSheet.flatten(screen.getByTestId('bloque-acciones').props.style).borderTopWidth).toBeUndefined(); // el hero ya delimita
  expect(StyleSheet.flatten(screen.getByTestId('bloque-mes').props.style).borderTopWidth).toBe(1);
  // La lectura parcial sigue siendo un bloque DISTINTO de «Este mes» (F05-D003 §16.6).
  expect(within(screen.getByTestId('bloque-mes')).queryByTestId('bloque-gasto-parcial')).toBeNull();
});
