// ============================================================
// GAPTO MOBILE 2027
// Fichero: contratos_dominio.test.ts
// Ruta: mobile/__tests__/contratos_dominio.test.ts
// Descripción: Dominio puro de F06-02/03 (contrato N1 v1.1; lámina CON v0.8): solape simétrico y bloqueante para firmados con ocupación hasta el FIN REAL (O-2, O-25; el fin previsto no libera; un borrador no cuenta; OTRO no solapa), reglas de personas de D25 (principal solo en PROPIETARIO, GESTOR e INQUILINO; el usuario no es inquilino ni agencia ni administrador; AGENCIA y ADMINISTRADOR no cuentan para firmar; O-22..O-24), payload de C-CON-01 sin `renta` ni `fianza` (O-14) y «No lo sé» sin fila, porcentajes, ocupación de A1 (O-1b), códigos de error con texto (O-31: motivo de renta frente a motivo de regla de servicio), homónimos y uso en Gapto (O-30, O-32), propuesta de rol sin AGENCIA/ADMINISTRADOR (E3) y textos literales de la lámina.
// Versión: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 5 cliente)
// Versión: 0.1.1 (F06 T3-F06 Bloque 3, paso 6): oráculo de «para firmar hace falta un inquilino» (MC-CON-10 vivo).
// Versión: 0.1.2 (Bloque 3, paso 9): oráculo con la forma REAL de la respuesta del selector V-bis (sin `enabled`); mata MC-CON-23b.
// ============================================================

import type { FilaContrato } from '../src/api/contratos';
import {
  agruparContratos, borradorContrato, BorradorContrato, calcularSolapes, clausulaWire, desdeMesAnio, detalleFilaContrato, detalleHomonimo, faltasClausula, faltasFechas,
  faltasPersonas, faltasQue, faltasServicios, filasSelector, MENSAJES_ERROR, normalizarNombre, parsearPorcentaje, payloadAltaContrato, PersonaBorrador, resumenOcupacion,
  resumenServiciosContrato, rolPropuesto, solapadosDeDetalle, textoClausulaDetalle, textoCoincide, textoErrorContrato, textoOcupacionHabitacion, textoProponerRol, textoSinRol,
  textoUso, tratamientosWire, TEXTO_INQUILINO_NO_YO, TEXTO_RENTA_PENDIENTE, TEXTO_SERVICIO_BAJA_REGLA, textoSituacion, ROLES_TERCERO, NOMBRE_ROL_TERCERO,
} from '../src/domain/contratos';
import type { TerceroParaContrato } from '../src/api/contratos';
import { detalle, escenarioA1, fila, T_CARLOS, T_ELENA, T_LAURA, terceroUso } from './contratos_fixtures';

const per = (rol: PersonaBorrador['rol'], terceroId: string | null, principal = false, nombre = 'X'): PersonaBorrador => ({ clave: `${rol}-${terceroId ?? 'yo'}`, terceroId, nombre, rol, principal });
const borr = (p: Partial<BorradorContrato> = {}): BorradorContrato => ({
  ...borradorContrato('p1', 'Piso Ejemplo'), tipo: 'HABITACION', habitacion: 4, fechaInicio: '2026-11-01', estado: 'FORMALIZADO', nombre: '26-HAB4-ES', ...p,
});

// ------------------------------------------------------------------ O-25 / O-2 · solape
describe('solape (decisiones 3 y 6; INV-ALQ-08/09)', () => {
  const viv = fila({ contrato_id: 'viv', nombre: '26-VIV-JM', tipo: 'VIVIENDA_COMPLETA', habitacion: null, fecha_inicio: '2026-09-01', fecha_fin_prevista: '2027-08-31' });
  const hab2 = fila({ contrato_id: 'h2', nombre: '26-HAB2-AG', habitacion: 2, fecha_inicio: '2026-03-01', fecha_fin_prevista: '2027-08-31' });

  test('habitación contra vivienda completa firmada y al revés (O-25)', () => {
    expect(calcularSolapes([viv], { tipo: 'HABITACION', habitacion: 2, inicio: '2026-11-01' }).map((x) => x.contrato_id)).toEqual(['viv']);
    expect(calcularSolapes([hab2], { tipo: 'VIVIENDA_COMPLETA', habitacion: null, inicio: '2026-11-01' }).map((x) => x.contrato_id)).toEqual(['h2']);
  });

  test('habitación solo choca con la misma habitación; OTRO no choca con nada ni nadie choca con OTRO', () => {
    expect(calcularSolapes([hab2], { tipo: 'HABITACION', habitacion: 3, inicio: '2026-11-01' })).toEqual([]);
    expect(calcularSolapes([hab2], { tipo: 'HABITACION', habitacion: 2, inicio: '2026-11-01' })).toHaveLength(1);
    expect(calcularSolapes([viv, hab2], { tipo: 'OTRO', habitacion: null, inicio: '2026-11-01' })).toEqual([]);
    const otro = fila({ contrato_id: 'o', nombre: 'o', tipo: 'OTRO', habitacion: null });
    expect(calcularSolapes([otro], { tipo: 'VIVIENDA_COMPLETA', habitacion: null, inicio: '2026-11-01' })).toEqual([]);
  });

  test('el fin PREVISTO vencido no libera la habitación; solo el fin REAL (O-2, decisión 6)', () => {
    const vencido = fila({ contrato_id: 'v', nombre: '25-HAB5-LM', habitacion: 5, fecha_fin_prevista: '2026-10-31', fin_previsto_vencido: true, fecha_inicio: '2025-11-01' });
    expect(calcularSolapes([vencido], { tipo: 'HABITACION', habitacion: 5, inicio: '2026-11-18' })).toHaveLength(1);
    // con fin real anterior al inicio del nuevo, ya no solapa; el mismo día del fin real SÍ (inclusivo)
    const cerrado = { ...vencido, fecha_fin_real: '2026-11-17' };
    expect(calcularSolapes([cerrado], { tipo: 'HABITACION', habitacion: 5, inicio: '2026-11-18' })).toEqual([]);
    expect(calcularSolapes([{ ...vencido, fecha_fin_real: '2026-11-18' }], { tipo: 'HABITACION', habitacion: 5, inicio: '2026-11-18' })).toHaveLength(1);
  });

  test('un borrador y un cancelado no cuentan (INV-ALQ-09)', () => {
    const bor = fila({ contrato_id: 'b', nombre: 'b', habitacion: 4, estado_documental: 'BORRADOR', situacion: 'BORRADOR' });
    const can = fila({ contrato_id: 'c', nombre: 'c', habitacion: 4, estado_documental: 'CANCELADO', situacion: 'CANCELADO' });
    expect(calcularSolapes([bor, can], { tipo: 'HABITACION', habitacion: 4, inicio: '2026-11-01' })).toEqual([]);
  });

  test('el escenario A1: la habitación 4 (borrador) está libre; la 5 (fin previsto vencido) sigue ocupada', () => {
    const { contratos } = escenarioA1();
    expect(calcularSolapes(contratos, { tipo: 'HABITACION', habitacion: 4, inicio: '2026-11-18' })).toEqual([]);
    expect(calcularSolapes(contratos, { tipo: 'HABITACION', habitacion: 5, inicio: '2026-11-18' }).map((x) => x.nombre)).toEqual(['25-HAB5-LM']);
  });

  test('textos: «La habitación 2 desde el 1 nov 2026 coincide con este contrato firmado de la vivienda completa:»', () => {
    expect(textoCoincide({ tipo: 'HABITACION', habitacion: 2, inicio: '2026-11-01' }, { tipo: 'VIVIENDA_COMPLETA' }))
      .toBe('La habitación 2 desde el 1 nov 2026 coincide con este contrato firmado de la vivienda completa:');
  });

  test('el detalle del 409 se lee solo si viene bien formado', () => {
    expect(solapadosDeDetalle({ solapados: [{ id: 'a', nombre: 'n', tipo: 'HABITACION', habitacion: 2, desde: '2026-09-01', hasta: null }, { raro: 1 }] })).toHaveLength(1);
    expect(solapadosDeDetalle(undefined)).toEqual([]);
    expect(solapadosDeDetalle({ solapados: 'x' })).toEqual([]);
  });
});

// ------------------------------------------------------------------ D25 · personas
describe('personas (D25; O-22, O-23, O-24)', () => {
  test('«Tú» no puede ser inquilino ni agencia ni administrador (O-22)', () => {
    expect(faltasPersonas(borr({ personas: [per('INQUILINO', null, true, 'Tú')] }))).toContain(TEXTO_INQUILINO_NO_YO);
    expect(faltasPersonas(borr({ personas: [per('AGENCIA', null, false, 'Tú')] })).join(' ')).toMatch(/solo terceros/);
    expect(faltasPersonas(borr({ personas: [per('ADMINISTRADOR', null, false, 'Tú')] })).join(' ')).toMatch(/solo terceros/);
    // «Tú» sí puede ser propietario o gestor
    expect(faltasPersonas(borr({ estado: 'BORRADOR', personas: [per('PROPIETARIO', null, true, 'Tú'), per('GESTOR', null, true, 'Tú')] }))).toEqual([]);
  });

  test('para firmar hacen falta arrendador (o gestor) e inquilino; AGENCIA y ADMINISTRADOR no cuentan (O-23)', () => {
    const solo = borr({ personas: [per('AGENCIA', T_ELENA, true), per('INQUILINO', T_CARLOS, true)] });
    expect(faltasPersonas(solo).join(' ')).toMatch(/arrendador \(o gestor\)/);
    // arrendador sin inquilino: tampoco se firma (D25; mata MC-CON-10)
    const sinInquilino = borr({ personas: [per('PROPIETARIO', null, true), per('AVALISTA', T_ELENA)] });
    expect(faltasPersonas(sinInquilino)).toContain('Para firmar hace falta un inquilino.');
    const ok = borr({ personas: [per('PROPIETARIO', null, true), per('INQUILINO', T_CARLOS, true), per('AGENCIA', T_ELENA)] });
    expect(faltasPersonas(ok)).toEqual([]);
    // un gestor tercero sustituye al propietario
    expect(faltasPersonas(borr({ personas: [per('GESTOR', T_LAURA, true), per('INQUILINO', T_CARLOS, true)] }))).toEqual([]);
    // en borrador no hace falta nada
    expect(faltasPersonas(borr({ estado: 'BORRADOR', personas: [] }))).toEqual([]);
  });

  test('principal: obligatorio solo en arrendador, gestor e inquilino; avalista, agencia y administrador, opcional (O-24)', () => {
    expect(faltasPersonas(borr({ estado: 'BORRADOR', personas: [per('AVALISTA', T_ELENA), per('AGENCIA', T_LAURA), per('ADMINISTRADOR', T_CARLOS)] }))).toEqual([]);
    expect(faltasPersonas(borr({ estado: 'BORRADOR', personas: [per('INQUILINO', T_CARLOS, false)] })).join(' ')).toMatch(/principal entre los inquilinos/);
    expect(faltasPersonas(borr({ estado: 'BORRADOR', personas: [per('AGENCIA', T_ELENA, true), per('AGENCIA', T_LAURA, true)] })).join(' ')).toMatch(/Solo puede haber un principal/);
  });

  test('misma persona dos veces en el mismo rol', () => {
    expect(faltasPersonas(borr({ estado: 'BORRADOR', personas: [per('AVALISTA', T_ELENA, false, 'Elena'), per('AVALISTA', T_ELENA, false, 'Elena')] })).join(' ')).toMatch(/Elena está repetido/);
  });
});

// ------------------------------------------------------------------ pasos
describe('validaciones de pasos', () => {
  test('B1: habitación obligatoria, dentro de la ficha; ficha sin habitaciones (NULL o 0) no inventa', () => {
    expect(faltasQue(borr({ habitacion: null }), 5)).toContain('Elige la habitación.');
    expect(faltasQue(borr({ habitacion: 6 }), 5)[0]).toMatch(/no está en la ficha/);
    expect(faltasQue(borr({ habitacion: 1 }), null)[0]).toMatch(/no indica cuántas habitaciones/);
    expect(faltasQue(borr({ habitacion: 1 }), 0)[0]).toMatch(/no indica cuántas habitaciones/);
    expect(faltasQue(borr({ tipo: 'VIVIENDA_COMPLETA', habitacion: null }), null)).toEqual([]);
    expect(faltasQue(borradorContrato(), 5)).toEqual(['Elige la propiedad.', 'Elige qué se alquila.']);
  });

  test('B2: la fecha de inicio se pide siempre (también en borrador); fin previsto no anterior; estado sin valor por defecto', () => {
    expect(faltasFechas(borr({ fechaInicio: '' }))[0]).toMatch(/también en un borrador/);
    expect(faltasFechas(borr({ fechaFinPrevista: '2026-10-31' }))[0]).toMatch(/anterior al inicio/);
    expect(faltasFechas(borr({ estado: null }))).toEqual(['Indica si está firmado o aún no.']);
    expect(faltasFechas(borr({ fechaFinPrevista: '2027-10-31' }))).toEqual([]);
  });

  test('B4: nada viene elegido; porcentaje fijo exige % mayor que 0', () => {
    expect(faltasClausula({ eleccion: null, porcentaje: '', periodicidad: '', primeraRevision: '' })).toHaveLength(1);
    expect(faltasClausula({ eleccion: 'NO_SE', porcentaje: '', periodicidad: '', primeraRevision: '' })).toEqual([]);
    expect(faltasClausula({ eleccion: 'PORCENTAJE_FIJO', porcentaje: '0', periodicidad: '', primeraRevision: '' })).toHaveLength(1);
    expect(faltasClausula({ eleccion: 'PORCENTAJE_FIJO', porcentaje: '2,5', periodicidad: '', primeraRevision: '' })).toEqual([]);
    expect(faltasClausula({ eleccion: 'IPC', porcentaje: '', periodicidad: 'doce', primeraRevision: '' })).toHaveLength(1);
  });

  test('porcentajes: (0, 100], hasta 4 decimales', () => {
    expect(parsearPorcentaje('50')).toBe('50');
    expect(parsearPorcentaje('50,5 %')).toBe('50.5');
    expect(parsearPorcentaje('100')).toBe('100');
    expect(parsearPorcentaje('100,1')).toBeNull();
    expect(parsearPorcentaje('0')).toBeNull();
    expect(parsearPorcentaje('-5')).toBeNull();
    expect(parsearPorcentaje('1,23456')).toBeNull();
    expect(parsearPorcentaje('')).toBeNull();
  });

  test('B5: repercutir exige inquilino principal tercero y % mayor que 0', () => {
    const base = borr({ personas: [per('INQUILINO', T_CARLOS, true, 'Carlos')], servicios: { 's-luz': { modo: 'REPERCUTIDO_FIJO', porcentaje: '0' } } });
    expect(faltasServicios(base)).toHaveLength(1);
    expect(faltasServicios({ ...base, servicios: { 's-luz': { modo: 'REPERCUTIDO_FIJO', porcentaje: '50' } } })).toEqual([]);
    expect(faltasServicios({ ...base, personas: [], servicios: { 's-luz': { modo: 'POR_FACTURA', porcentaje: '' } } })).toHaveLength(1);
    expect(faltasServicios({ ...base, personas: [], servicios: { 's-int': { modo: 'INCLUIDO', porcentaje: '' } } })).toEqual([]);
  });
});

// ------------------------------------------------------------------ payload
describe('payload de C-CON-01 (sin renta; O-14)', () => {
  const completo = borr({
    personas: [per('PROPIETARIO', null, true, 'Tú'), per('INQUILINO', T_ELENA, true, 'Elena Sanz'), per('AGENCIA', T_LAURA, false, 'Inmobiliaria')],
    fechaFinPrevista: '2027-10-31',
    clausula: { eleccion: 'IPC', porcentaje: '', periodicidad: '12', primeraRevision: '2027-11-01' },
    servicios: { 's-int': { modo: 'INCLUIDO', porcentaje: '' }, 's-luz': { modo: 'POR_FACTURA', porcentaje: '' }, 's-agua': { modo: 'NO_REPERCUTIDO', porcentaje: '' }, 's-gas': { modo: 'SIN_INDICAR', porcentaje: '' }, 's-x': { modo: null, porcentaje: '' } },
  });

  test('nunca lleva renta ni fianza; «Tú» viaja como YO; la habitación solo en HABITACION', () => {
    const p = payloadAltaContrato('i1', completo);
    expect(p).not.toHaveProperty('renta');
    expect(p).not.toHaveProperty('fianza');
    expect(Object.keys(p).join(' ')).not.toMatch(/renta|fianza|cobro|ipc_aplicado/);
    expect(p.personas).toEqual([
      { actor: 'YO', rol: 'PROPIETARIO', principal: true },
      { actor: { tercero_id: T_ELENA }, rol: 'INQUILINO', principal: true },
      { actor: { tercero_id: T_LAURA }, rol: 'AGENCIA', principal: false },
    ]);
    expect(p.habitacion).toBe(4);
    expect(payloadAltaContrato('i2', { ...completo, tipo: 'VIVIENDA_COMPLETA', habitacion: null })).not.toHaveProperty('habitacion');
    expect(p.estado).toBe('FORMALIZADO');
    expect(p.fecha_fin_prevista).toBe('2027-10-31');
  });

  test('cláusula: IPC con parámetros desconocidos a NULL; «No lo sé» sin fila (nunca NINGUNA); NINGUNA sin parámetros', () => {
    expect(clausulaWire({ eleccion: 'IPC', porcentaje: '', periodicidad: '', primeraRevision: '' })).toEqual({ tipo: 'IPC', indice_referencia: 'IPC INE', periodicidad_meses: null, fecha_primera_revision: null });
    expect(clausulaWire({ eleccion: 'NO_SE', porcentaje: '', periodicidad: '', primeraRevision: '' })).toBeNull();
    expect(clausulaWire({ eleccion: 'NINGUNA', porcentaje: '9', periodicidad: '12', primeraRevision: '2027-01-01' })).toEqual({ tipo: 'NINGUNA' });
    expect(clausulaWire({ eleccion: 'PORCENTAJE_FIJO', porcentaje: '2,5', periodicidad: '', primeraRevision: '' })).toEqual({ tipo: 'PORCENTAJE_FIJO', porcentaje_fijo: '2.5' });
    expect(payloadAltaContrato('i3', { ...completo, clausula: { eleccion: 'NO_SE', porcentaje: '', periodicidad: '', primeraRevision: '' } })).not.toHaveProperty('clausula_revision');
  });

  test('servicios: SIN_INDICAR y sin elegir no viajan; POR_FACTURA con inquilino y sin %; FIJO con %', () => {
    const t = tratamientosWire(completo);
    expect(t.map((x) => x.servicio_id)).toEqual(['s-int', 's-luz', 's-agua']);
    expect(t.find((x) => x.servicio_id === 's-luz')).toEqual({ servicio_id: 's-luz', modo: 'POR_FACTURA', desde: '2026-11-01', actor: { tercero_id: T_ELENA } });
    expect(t.find((x) => x.servicio_id === 's-int')).not.toHaveProperty('actor');
    const fijo = tratamientosWire({ ...completo, servicios: { 's-luz': { modo: 'REPERCUTIDO_FIJO', porcentaje: '50' } } });
    expect(fijo[0]).toEqual({ servicio_id: 's-luz', modo: 'REPERCUTIDO_FIJO', desde: '2026-11-01', actor: { tercero_id: T_ELENA }, porcentaje: '50' });
  });
});

// ------------------------------------------------------------------ A1 / O-1b
describe('A1 · situación y ocupación derivadas (O-1b)', () => {
  test('3 ocupadas · 1 próxima · 1 libre; 2 finalizados; el borrador va a Borradores', () => {
    const e = escenarioA1();
    expect(resumenOcupacion(e.ocupacion)).toBe('3 ocupadas · 1 próxima · 1 libre');
    const g = agruparContratos(e.contratos);
    expect(g.vigentes.map((x) => x.nombre)).toEqual(['26-HAB1-CR', '26-HAB2-AG', '25-HAB5-LM']);
    expect(g.proximos.map((x) => x.nombre)).toEqual(['26-HAB3-PR']);
    expect(g.borradores.map((x) => x.nombre)).toEqual(['26-HAB4-ES']);
    expect(g.finalizados).toHaveLength(2);
    expect(resumenOcupacion([{ habitacion: 1, estado: 'OCUPADA', hasta: null, desde: null, contrato_id: null }])).toBe('1 ocupada · 0 próximas · 0 libres');
  });

  test('filas: desde, hasta, fin previsto vencido, empieza, sin firmar', () => {
    const e = escenarioA1().contratos;
    const por = (n: string) => detalleFilaContrato(e.find((x) => x.nombre === n) as FilaContrato);
    expect(por('26-HAB1-CR')).toBe('Habitación 1 · Carlos Ruiz · desde 1 sep 2026');
    expect(por('26-HAB2-AG')).toBe('Habitación 2 · Ana Gil · hasta 31 ago 2027');
    expect(por('25-HAB5-LM')).toBe('Habitación 5 · Luis Mora · fin previsto 31 oct 2026');
    expect(por('26-HAB3-PR')).toBe('Habitación 3 · Pablo Ros · empieza 1 dic');
    expect(por('26-HAB4-ES')).toBe('Habitación 4 · Elena Sanz · sin firmar');
  });

  test('habitaciones en B1: «Ocupada hasta 31 ago 2027», «Contrato desde 1 dic», «Libre»', () => {
    expect(textoOcupacionHabitacion({ estado: 'OCUPADA', hasta: '2027-08-31', desde: null })).toBe('Ocupada hasta 31 ago 2027');
    expect(textoOcupacionHabitacion({ estado: 'PROXIMA', hasta: null, desde: '2026-12-01' })).toBe('Contrato desde 1 dic');
    expect(textoOcupacionHabitacion({ estado: 'LIBRE', hasta: null, desde: null })).toBe('Libre');
  });

  test('A2: resumen de servicios, cláusula y situación', () => {
    const d = detalle();
    expect(resumenServiciosContrato(d)).toBe('Internet incluido · luz: reparto en cada factura');
    expect(textoClausulaDetalle(d.clausula)).toBe('Revisión anual por IPC');
    expect(textoClausulaDetalle(null)).toBe('Sin registrar');
    expect(textoSituacion(d)).toBe('Firmado · vigente');
    expect(desdeMesAnio('2027-03-01')).toBe('mar 2027');
  });
});

// ------------------------------------------------------------------ errores
describe('errores (contrato §1.4)', () => {
  const CODIGOS_NUEVOS = [
    'HABITACION_REQUERIDA', 'HABITACION_NO_ADMITIDA', 'HABITACION_FUERA_DE_FICHA', 'HABITACIONES_NO_INDICADAS', 'SOLAPE_CON_CONTRATO_FIRMADO', 'PROPIEDAD_FUERA_DE_PATRIMONIO',
    'FALTAN_PARTES_PARA_FORMALIZAR', 'PRINCIPAL_REQUERIDO', 'INQUILINO_NO_PUEDE_SER_YO', 'ROL_NO_ADMITIDO_PARA_YO', 'CONTRATO_SIN_INQUILINO', 'CONTRATO_SIN_ARRENDADOR',
    'PRINCIPAL_DUPLICADO', 'TRATAMIENTO_SOLAPADO', 'SERVICIO_YA_VINCULADO', 'CLAUSULA_SOLAPADA', 'DESDE_IGUAL_A_VERSION_ABIERTA', 'FECHA_FIN_ANTERIOR_A_VIGENCIA',
    'CONTRATO_NO_VIGENTE', 'SUCESOR_SOLAPADO', 'FECHA_INICIO_REQUERIDA', 'CLAUSULA_INCOMPLETA', 'SERVICIO_NO_VINCULADO_A_PROPIEDAD', 'ACTOR_NO_ES_INQUILINO',
    'TRATAMIENTO_INCOMPATIBLE', 'SERVICIO_DADO_DE_BAJA', 'ROL_DESCONOCIDO', 'CLASIFICACION_CICLO', 'CLASIFICACION_NOMBRE_REPETIDO', 'RETIRADA_NO_ADMITIDA', 'RENTA_NO_DISPONIBLE',
  ];
  const CODIGOS_EXISTENTES = [
    'AGREGADO_NO_ENCONTRADO', 'VERSION_DESFASADA', 'IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION', 'CONFLICTO_CONCURRENCIA', 'TERCERO_NO_DISPONIBLE', 'PARTICIPANTE_DUPLICADO',
    'FECHA_ANTERIOR_INICIO', 'MOTIVO_AUSENTE', 'CAMPO_INMUTABLE', 'OPERACION_NO_PERMITIDA_EN_ESTADO', 'SUMA_NO_CUADRA', 'HABITACIONES_EN_USO',
  ];

  test.each([...CODIGOS_NUEVOS, ...CODIGOS_EXISTENTES])('el código %s tiene mensaje propio, sin jerga', (codigo) => {
    const t = textoErrorContrato(codigo, 'mensaje del servidor');
    expect(t).toBe(MENSAJES_ERROR[codigo]);
    expect(t).not.toBe('mensaje del servidor');
    expect(t).not.toMatch(/[A-Z]{3,}_[A-Z_]+/);
  });

  test('el texto de la renta pendiente y el del usuario inquilino son los de la lámina', () => {
    expect(textoErrorContrato('OPERACION_NO_PERMITIDA_EN_ESTADO', '', { motivo: 'RENTA_PENDIENTE_DE_F06_04' }))
      .toBe('Este contrato tiene una renta registrada. Para terminarlo hay que cerrar también su renta, y eso llegará con la parte de cobros. De momento no se puede terminar.');
    expect(textoErrorContrato('INQUILINO_NO_PUEDE_SER_YO')).toBe('Tú no puedes ser inquilino de tu propio contrato.');
  });

  test('O-31: el motivo de regla de servicio nunca se confunde con el de la renta del contrato', () => {
    const t = textoErrorContrato('OPERACION_NO_PERMITIDA_EN_ESTADO', '', { motivo: 'REGLA_SERVICIO_PENDIENTE_DE_F06_04' });
    expect(t).toBe(TEXTO_SERVICIO_BAJA_REGLA);
    expect(t).toBe('Este servicio tiene un pago previsto registrado. Para darlo de baja hay que cerrar ese pago previsto, y eso llegará con la parte de cobros.');
    expect(t).not.toBe(TEXTO_RENTA_PENDIENTE);
    expect(textoErrorContrato('OPERACION_NO_PERMITIDA_EN_ESTADO', '', { motivo: 'RENTA_PENDIENTE_DE_F06_04' })).not.toBe(t);
  });

  test('un código desconocido muestra el mensaje del servidor; sin mensaje, un texto general', () => {
    expect(textoErrorContrato('CODIGO_NUEVO', 'Algo ha pasado')).toBe('Algo ha pasado');
    expect(textoErrorContrato('CODIGO_NUEVO', '')).toMatch(/No se ha podido guardar/);
  });
});

// ------------------------------------------------------------------ V-bis / E3
describe('V-bis · homónimos y uso en Gapto (O-30, O-32)', () => {
  const inq = (nombre: string): { tipo: 'CONTRATO'; rol: 'INQUILINO'; contrato_id: string; contrato_nombre: string; desde: string; hasta: null } =>
    ({ tipo: 'CONTRATO', rol: 'INQUILINO', contrato_id: 'c1', contrato_nombre: nombre, desde: '2026-09-01', hasta: null });

  test('normalización C06: sin acentos, minúsculas, espacios simples', () => {
    expect(normalizarNombre('  Carlos   RUÍZ ')).toBe('carlos ruiz');
  });

  test('dos «Empresa SL» activas: cada fila muestra naturaleza y su uso; la que no es homónima no muestra nada (O-32)', () => {
    const lista = [
      terceroUso('a', 'Empresa SL', inq('26-HAB1-CR'), { naturaleza: 'EMPRESA' }),
      terceroUso('b', 'Empresa SL', { tipo: 'SIN_USO' }, { naturaleza: 'EMPRESA' }),
      terceroUso('c', 'Carlos Martín', { tipo: 'SIN_USO' }),
    ];
    const f = filasSelector(lista);
    expect(f.map((x) => x.homonimo)).toEqual([true, true, false]);
    expect(f.map((x) => x.identica)).toEqual([false, false, false]);
    expect(detalleHomonimo(lista[0])).toBe('Empresa · inquilino en 26-HAB1-CR');
    expect(detalleHomonimo(lista[1])).toBe('Empresa · sin uso');
  });

  test('«último movimiento 12 oct» y «sin uso»', () => {
    expect(textoUso({ tipo: 'MOVIMIENTO', fecha: '2026-10-12' })).toBe('último movimiento 12 oct');
    expect(textoUso({ tipo: 'SIN_USO' })).toBe('sin uso');
  });

  test('filas aún idénticas (mismo nombre, naturaleza y uso) no se eligen directamente: ficha (O-30)', () => {
    const f = filasSelector([terceroUso('a', 'Carlos Ruiz', { tipo: 'SIN_USO' }), terceroUso('b', 'carlos ruíz', { tipo: 'SIN_USO' })]);
    expect(f.every((x) => x.homonimo && x.identica)).toBe(true);
  });

  test('forma REAL del servidor (V-bis, sin `enabled`): las filas se listan (defecto CON-B3c de las capturas del paso 9)', () => {
    // Claves exactas de lecturas.selector_asistente: id, nombre, naturaleza, row_version, homonimo, uso. Solo activos, sin `enabled`.
    const delServidor = JSON.parse(JSON.stringify([
      { id: 'a', nombre: 'Carlos Ruiz', naturaleza: 'PERSONA', row_version: 1, homonimo: true, uso: { tipo: 'SIN_USO' } },
      { id: 'b', nombre: 'Carlos Ruiz', naturaleza: 'PERSONA', row_version: 1, homonimo: true, uso: { tipo: 'MOVIMIENTO', fecha: '2026-10-12' } },
      { id: 'c', nombre: 'Elena Sanz', naturaleza: 'PERSONA', row_version: 2, homonimo: false, uso: { tipo: 'SIN_USO' } },
    ])) as TerceroParaContrato[];
    const f = filasSelector(delServidor);
    expect(f.map((x) => x.tercero.id)).toEqual(['a', 'b', 'c']);
    expect(f.map((x) => x.homonimo)).toEqual([true, true, false]);
  });

  test('los inactivos no se listan en el selector de participantes (O-30)', () => {
    const f = filasSelector([terceroUso('a', 'Carlos Ruiz', { tipo: 'SIN_USO' }), terceroUso('b', 'Carlos Ruiz', { tipo: 'SIN_USO' }, { enabled: false })]);
    expect(f.map((x) => x.tercero.id)).toEqual(['a']);
    expect(f[0].homonimo).toBe(false);
  });
});

describe('E3 · propuesta de rol de tercero', () => {
  test('inquilino, avalista y gestor proponen su rol si no lo tiene; agencia, administrador y propietario NO proponen nada (decisión 2)', () => {
    expect(rolPropuesto('INQUILINO', [])).toBe('INQUILINO');
    expect(rolPropuesto('INQUILINO', ['INQUILINO'])).toBeNull();
    expect(rolPropuesto('AVALISTA', ['COMERCIO'])).toBe('AVALISTA');
    expect(rolPropuesto('GESTOR', [])).toBe('GESTOR');
    expect(rolPropuesto('AGENCIA', [])).toBeNull();
    expect(rolPropuesto('ADMINISTRADOR', [])).toBeNull();
    expect(rolPropuesto('PROPIETARIO', [])).toBeNull();
  });

  test('textos: «Elena Sanz no tiene el rol «Inquilino»» y el aviso de que no se quita', () => {
    expect(textoSinRol('Elena Sanz', 'INQUILINO')).toBe('Elena Sanz no tiene el rol «Inquilino»');
    expect(textoProponerRol('INQUILINO')).toMatch(/Un rol añadido no se puede quitar\.$/);
  });

  test('el catálogo de roles de tercero no incluye AGENCIA ni ADMINISTRADOR y se muestran todos (Q-CON-12)', () => {
    expect(ROLES_TERCERO).toHaveLength(10);
    expect(ROLES_TERCERO as string[]).not.toContain('AGENCIA');
    expect(ROLES_TERCERO as string[]).not.toContain('ADMINISTRADOR');
    for (const r of ROLES_TERCERO) expect(NOMBRE_ROL_TERCERO[r]).toBeTruthy();
  });
});
