# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_01h.py
# Ruta: scripts/dev/mutantes_f06_01h.py
# Descripcion: Arnes de mutacion M-H del bloque T3-F06 F06-01H (hipoteca), parte SERVIDOR y lista del CLIENTE
#   (mandato T3-F06 bloque 2 v1.1 §12.1; contrato F06-01H consolidado v0.4 §9.2). Mismo motor que
#   mutantes_f06_01h_f05_q3_hd.py (journal durable, restauracion verificada por SHA-256, journal previo -> se
#   restaura y se aborta NO-PASS, preflight verde, veredicto a disco con fsync en cuanto se conoce, --solo).
#   Catalogo del servidor: M-H-01..M-H-22, M-H-25..M-H-32, M-H-34..M-H-36, M-H-39..M-H-46 y M-N30-S (N-30).
#   M-H-23, M-H-33, M-H-37 y M-H-38 van al arnes de la compra (f06_01h_b2_mb2.py); M-H-24 es alias de MB2-08 y no
#   se cuenta. M-H-10..12 reescritos para el alta dentro de la compra con Hd (D6, D7). Una guarda por mutante:
#   M-H-41 y M-H-43 se parten en a/b(/c), una por guarda del codigo.
#   Formato de cada mutante: (id, desc, [(fichero, viejo, nuevo), ...], [tests], equivalencia_o_None, repeticiones).
#   Las sustituciones se aplican en orden sobre el texto ya sustituido; cada `viejo` debe aparecer EXACTAMENTE una
#   vez en ese momento (si no, NO_CLASIFICABLE sin tocar el arbol). `repeticiones` (por defecto 1): el mutante se
#   ejecuta n pasadas con el arbol mutado; MUERTO solo si muere en todas (cada pasada se anota en --salida). 3 en
#   los que dependen de orden o tiempo (lección M-CV-04; AJ-T2C-C04): M-H-42, M-H-44 y todo el que use test_295.
#   Tests: "tests/<ruta>.py::<nombre>" (pytest; tests/api con --rootdir=tests/api; test_295 en subproceso propio con
#   GAPTO_F06HIP_CONCURRENCIA=1) y "jest:__tests__/<fichero>::<patron -t>" (npx jest en mobile/).
#   Un test OMITIDO (skipped/xfail) no es verde: en el preflight lo pone ROJO y en un mutante da NO_CLASIFICABLE
#   (evita VIVOS falsos por la marca skipif de test_295).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable con la cadena hasta 0354>
#        python -u scripts/dev/mutantes_f06_01h.py [--grupo servidor|cliente|todos] [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (T3-F06 F06-01H paso 12; mandato v1.1 §12.1; contrato v0.4 §9.2)
# Version: 0.2.0 (T3-F06 F06-01H; H3, N-10 rama A, firma b7dbf079…): M-H-45 (deuda sin apertura) y M-H-46 (deuda
#   sin la frontera F04-D053 A1), con discriminantes en test_288 y test_293. Ningun texto anterior cambia.
# Version: 0.2.1 (H3, N-10): descripcion de M-H-45 sin caracteres fuera de cp1252 (la consola de Windows abortaba
#   el arnes al imprimirla); ningun texto de mutante ni discriminante cambia.
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f06_01h.journal.json"

ALTA = "backend/app/hipotecas/alta.py"
CALC = "backend/app/hipotecas/calculadora.py"
LECT = "backend/app/hipotecas/lecturas.py"
PAGO = "backend/app/hipotecas/pago.py"
REVI = "backend/app/hipotecas/revision.py"
VINC = "backend/app/hipotecas/vinculo.py"
PREV = "backend/app/services/previsiones_service.py"
CTXS = "backend/app/services/contexto_service.py"
COMP = "backend/app/patrimonio/compra.py"

T14O = "tests/backend/test_14o_f06_01h_calculadora.py::"
T288 = "tests/api/test_288_f06_01h_cuadro_y_lectura.py::"
T289 = "tests/api/test_289_f06_01h_alta_en_compra.py::"
T293 = "tests/api/test_293_f06_01h_pago_cuota.py::"
T294 = "tests/api/test_294_f06_01h_revision_tipo.py::"
T295 = "tests/api/test_295_f06_01h_concurrencia_serial.py::"
CONCURRENCIA = "tests/api/test_295_f06_01h_concurrencia_serial.py"

O_H26 = T289 + "test_o_h26_o1_o2_composicion_de_hd_y_h0"
O_H6 = T293 + "test_o_h6_pago_de_la_primera_cuota"
O_H4 = T294 + "test_o_h4_o_h19_revision_tras_12_cuotas_al_2_95"

MUTANTES = [
    # ------------------------------------------------------------ pago (W-HIP-02)
    ("M-H-01", "pago: el capital de la cuota se registra como GASTO (no reduce la deuda)",
     [(PAGO, 'm2.filas(i["efecto_deuda"], -capital,', 'm2.filas(i["efecto_deuda"], capital,'),
      (PAGO, 'tipo_efecto="DEUDA", importe_delta=-capital,', 'tipo_efecto="GASTO", importe_delta=capital,')],
     [O_H6], None, 1),
    ("M-H-02", "pago: los intereses reducen la deuda (DEUDA -intereses en lugar de GASTO)",
     [(PAGO, 'm2.filas(i["efecto_gasto"], interes,', 'm2.filas(i["efecto_gasto"], -interes,'),
      (PAGO, 'tipo_efecto="GASTO", importe_delta=interes,', 'tipo_efecto="DEUDA", importe_delta=-interes,')],
     [O_H6], None, 1),
    ("M-H-03", "pago: conciliacion parcial (la salida no se concilia entera)",
     [(PAGO, 'movimiento_tesoreria_id=i["movimiento"], importe_asignado=-total))],',
       'movimiento_tesoreria_id=i["movimiento"], importe_asignado=-total + CENT))],')],
     [O_H6], None, 1),
    ("M-H-04", "pago doble: la prevision no ABIERTA no rechaza (CUOTA_NO_PENDIENTE solo sin prevision)",
     [(PAGO, '    if prev is None or prev[0] != "ABIERTA":\n        return Rechazo(CUOTA_NO_PENDIENTE)\n',
       '    if prev is None:\n        return Rechazo(CUOTA_NO_PENDIENTE)\n')],
     [T293 + "test_o_h7_pago_doble_cuota_no_pendiente"], None, 1),
    ("M-H-13", "pago sin comprobar la version (VERSION_DESFASADA eliminada)",
     [(PAGO, '    if row_version != peticion["row_version_esperada"]:\n        return Rechazo(VERSION_DESFASADA)\n',
       '    if False:\n        return Rechazo(VERSION_DESFASADA)\n')],
     [T293 + "test_guardas_sin_escrituras"], None, 1),
    ("M-H-14", "pago fuera de orden (CUOTA_ANTERIOR_PENDIENTE eliminada, D14)",
     [(PAGO, '    if anterior is not None:\n        return Rechazo(CUOTA_ANTERIOR_PENDIENTE)\n',
       '    if False:\n        return Rechazo(CUOTA_ANTERIOR_PENDIENTE)\n')],
     [T293 + "test_o_h21_cuota_anterior_pendiente"], None, 1),
    ("M-H-15", "pago: la prevision de la cuota no queda REALIZADA",
     [(PAGO, '                                          marcar_realizada=True),',
       '                                          marcar_realizada=False),')],
     [O_H6, T293 + "test_o_h7_pago_doble_cuota_no_pendiente"], None, 1),
    ("M-H-42", "orden de locks del pago invertido: la cuenta (FNKU + FOR SHARE de PAGAR_GASTO) tras la financiacion",
     [(PAGO, '    sesion.uno("SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE", (cuenta,))          # cuenta FNKU\n'
             '    sesion.uno("SELECT id FROM gapto.cuenta_capacidades WHERE cuenta_id = %s AND capacidad_codigo = \'PAGAR_GASTO\' "\n'
             '               "FOR SHARE", (cuenta,))\n', ''),
      (PAGO, '    if fin is None:\n        return Rechazo(NO_ENCONTRADA)\n',
       '    if fin is None:\n        return Rechazo(NO_ENCONTRADA)\n'
       '    sesion.uno("SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE", (cuenta,))          # cuenta FNKU\n'
       '    sesion.uno("SELECT id FROM gapto.cuenta_capacidades WHERE cuenta_id = %s AND capacidad_codigo = \'PAGAR_GASTO\' "\n'
       '               "FOR SHARE", (cuenta,))\n')],
     [T293 + "test_o_h_orden_locks_pago_cuenta_antes_que_financiacion",
      T295 + "test_ic02_revision_primero_pago_despues", T295 + "test_ic03_pago_frente_a_pago_de_la_misma_cuota",
      T295 + "test_ic10_compra_con_hipoteca_frente_a_pago_de_otra_hipoteca_misma_cuenta"], None, 3),
    ("M-H-43b", "pago: saldo indeterminado (apertura NULL) tratado como 0: SALDO_PRINCIPAL_INDETERMINADO eliminada",
     [(PAGO, '    if apertura is None:\n        return Rechazo(INDETERMINADO)\n',
       '    if False:\n        return Rechazo(INDETERMINADO)\n')],
     [T293 + "test_o_h10_legacy_indeterminado"], None, 1),
    # ------------------------------------------------------------ revision (W-HIP-03/04)
    ("M-H-05", "revision sobre cuota pagada: sin REVISION_SOBRE_CUOTA_PAGADA (comprobacion y relectura bajo lock)",
     [(REVI, '    if any(q[4] is None or estados.get(q[4], ("", 0))[0] != "ABIERTA" for q in afectadas):\n'
             '        return Rechazo(SOBRE_CUOTA_PAGADA)\n', ''),
      (REVI, '    if any(estados[q[4]][0] != "ABIERTA" for q in afectadas):                          # relectura bajo lock\n'
             '        return Rechazo(SOBRE_CUOTA_PAGADA)\n', '')],
     [T294 + "test_o_h9_revision_sobre_cuota_pagada"], None, 1),
    ("M-H-06", "revision: recalculo sobre el capital entero (sin restar el capital de las anteriores)",
     [(REVI, '    pendiente = Decimal(capital) - sum((Decimal(q[3]) for q in anteriores), Decimal(0))\n',
       '    pendiente = Decimal(capital)\n')],
     [O_H4], None, 1),
    ("M-H-16", "revision: la version vigente no se cierra (sin vigente_hasta)",
     [(REVI, '    sesion.ejecutar("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s WHERE id = %s",\n'
             '                    (desde - dt.timedelta(days=1), vigente["id"]))\n', '')],
     [O_H4], None, 1),
    ("M-H-17", "revision: las previsiones futuras no se ajustan (sin ajustar_importe_cuota_hipoteca)",
     [(REVI, '        previsiones.ajustar_importe_cuota_hipoteca(\n', '        (lambda *a, **k: None)(\n')],
     [O_H4], None, 1),
    ("M-H-18", "revision: periodicidad no MENSUAL aceptada (se ignora la pedida)",
     [(REVI, 'periodicidad=p.get("periodicidad") or calc.PERIODICIDAD)', 'periodicidad=calc.PERIODICIDAD)')],
     [T294 + "test_o_h12_periodicidad_distinta"], None, 1),
    ("M-H-19", "revision anterior o igual a las condiciones vigentes admitida (FECHA_REVISION_INCOHERENTE eliminada)",
     [(REVI, '    if not desfasada and desde <= vigente["desde"]:\n', '    if False:\n')],
     [T294 + "test_o_h25_revision_anterior_a_las_condiciones_vigentes"], None, 1),
    ("M-H-34", "revision: auditoria por cuota omitida (O-H20)",
     [(REVI, '        auditoria.registrar(sesion, tabla="financiacion_cuotas",',
       '        (lambda *a, **k: None)(sesion, tabla="financiacion_cuotas",')],
     [T294 + "test_o_h20_auditoria_por_cuota_y_reconstruccion"], None, 1),
    ("M-H-35", "revision: datos_antes de la auditoria por cuota sin condicion_version_id (O-H20)",
     [(REVI, 'datos_antes_json=antes, datos_despues_json=_fila_cuota(sesion, q[0]),',
       'datos_antes_json=json.dumps({k: v for k, v in json.loads(antes).items() if k != "condicion_version_id"}), '
       'datos_despues_json=_fila_cuota(sesion, q[0]),')],
     [T294 + "test_o_h20_auditoria_por_cuota_y_reconstruccion"], None, 1),
    ("M-H-43c", "revision: saldo indeterminado (apertura NULL) tratado como 0: SALDO_PRINCIPAL_INDETERMINADO eliminada",
     [(REVI, '    if apertura is None:\n        return Rechazo(INDETERMINADO)\n',
       '    if False:\n        return Rechazo(INDETERMINADO)\n')],
     [T294 + "test_o_h25_otro_owner_y_legacy"], None, 1),
    ("M-H-44", "revision v0.2.0 con el orden anterior: VERSION_DESFASADA antes de mirar la cuota pagada (IC-01, N-38)",
     [(REVI, '    desfasada = row_version != peticion["row_version_esperada"]\n',
       '    desfasada = row_version != peticion["row_version_esperada"]\n'
       '    if desfasada:\n        return Rechazo(VERSION_DESFASADA)\n')],
     [T294 + "test_o_h9_cuota_pagada_precede_a_version_desfasada",
      T295 + "test_ic01_pago_primero_revision_despues"], None, 3),
    # ------------------------------------------------------------ calculadora
    ("M-H-07", "calculadora: tipo del periodo distinto de anual/12 (dias reales 30/365)",
     [(CALC, '        return Decimal(tasa_anual) / Decimal(12) / Decimal(100)\n',
       '        return Decimal(tasa_anual) * Decimal(30) / Decimal(365) / Decimal(100)\n')],
     [T14O + "test_tasa_del_periodo_es_anual_entre_12", T14O + "test_o_h1_frances_160000_25_360"], None, 1),
    ("M-H-08", "calculadora: la ultima cuota no absorbe el residuo",
     [(CALC, '            capital = resto if k == n else cuota - interes        # la ultima absorbe el residuo\n',
       '            capital = cuota - interes\n')],
     [T14O + "test_o_h3c_dos_cuotas_con_residuo", T14O + "test_o_h1_frances_160000_25_360"], None, 1),
    ("M-H-09", "calculadora: redondeo HALF_EVEN en lugar de HALF_UP",
     [(CALC, '    return valor.quantize(CENT, rounding=ROUND_HALF_UP)\n',
       '    return valor.quantize(CENT, rounding="ROUND_HALF_EVEN")\n')],
     [T14O + "test_o_h18_empate_half_up"], None, 1),
    # ------------------------------------------------------------ alta dentro de la compra (W-HIP-01, Hd)
    ("M-H-10", "alta sin Hd causal: la version ALTA sin hecho_causa_id (la hipoteca no nace de la compra; reescrito D6/D7)",
     [(ALTA, '(pl.version, pl.financiacion_id, pl.escritura, pl.hd, c["tipo_interes"]',
       '(pl.version, pl.financiacion_id, pl.escritura, None, c["tipo_interes"]')],
     [O_H26], None, 1),
    ("M-H-11", "alta sin enlace a la compra: sin PARTE_DE Hd -> H0 (reescrito D6/D7)",
     [(ALTA, '    sesion.ejecutar("INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, hecho_destino_id, tipo_relacion) "\n'
             '                    "VALUES (%s, %s, %s, \'PARTE_DE\')", (pl.parte_de, pl.hd, pl.h0))\n', '')],
     [O_H26], None, 1),
    ("M-H-12", "identidad del alta: la financiacion no se deriva de H0 (uuid4 en lugar de uuid5; reescrito D6/D7)",
     [(ALTA, '    f = uuid.uuid5(h0, "gapto.f06.hipoteca.financiacion")\n', '    f = uuid.uuid4()\n')],
     [T289 + "test_o_h14_replay_exacto_idempotente"], None, 1),
    ("M-H-20", "desembolso como INGRESO: el efecto de Hd es INGRESO en lugar de DEUDA",
     [(ALTA, 'efectos=[DatosEfecto(efecto_id=pl.efecto_deuda, tipo_efecto="DEUDA", importe_delta=pl.p,',
       'efectos=[DatosEfecto(efecto_id=pl.efecto_deuda, tipo_efecto="INGRESO", importe_delta=pl.p,')],
     [O_H26], None, 1),
    ("M-H-21", "desembolso conciliado con resto (importe_asignado = P - 0,01)",
     [(ALTA, 'movimiento_tesoreria_id=pl.movimiento, importe_asignado=pl.p))],',
       'movimiento_tesoreria_id=pl.movimiento, importe_asignado=pl.p - CENT))],')],
     [O_H26], None, 1),
    ("M-H-22", "desembolso en los ingresos del mes / presupuesto: Hd presupuestable",
     [(ALTA, 'hecho=DatosCreacionHecho(hecho_id=pl.hd, fecha_hecho=pl.escritura, moneda=EUR, presupuestable=False,',
       'hecho=DatosCreacionHecho(hecho_id=pl.hd, fecha_hecho=pl.escritura, moneda=EUR, presupuestable=True,')],
     [O_H26], None, 1),
    ("M-H-25", "Hd fusionado en H0: el desembolso usa la identidad de H0 (DEUDA +P en H0)",
     [(ALTA, '    hd = uuid.uuid5(h0, MARCA_DESEMBOLSO)\n', '    hd = h0\n')],
     [O_H26], None, 1),
    ("M-H-26", "vinculo de nivel hecho en lugar de nivel efecto (efecto_id NULL en hecho_entidades)",
     [(VINC, 'hecho_id=hecho_id, efecto_id=efecto_id, entidad_id=financiacion_id,',
       'hecho_id=hecho_id, efecto_id=None, entidad_id=financiacion_id,')],
     [O_H26], None, 1),
    ("M-H-27", "la atribucion de la deuda se iguala a la de la cuenta de desembolso (D13)",
     [(ALTA, 'estado, filas = m2.filas(pl.efecto_deuda, pl.p, prestamo, modo,',
       'estado, filas = m2.filas(pl.efecto_deuda, pl.p, cuenta, modo,')],
     [T289 + "test_o_h30_distribuciones_distintas_aviso_y_atribuciones_conservadas"], None, 1),
    ("M-H-28", "aviso_reparto_distinto omitido con distribuciones distintas",
     [(ALTA, '    if not prestamo:\n        return False\n', '    if True:\n        return False\n')],
     [T289 + "test_o_h30_distribuciones_distintas_aviso_y_atribuciones_conservadas"], None, 1),
    ("M-H-29", "capacidad de la cuenta de desembolso no comprobada (CUENTA_SIN_CAPACIDAD eliminada)",
     [(COMP, '    if motivo is not None:\n        nombre = sesion.uno(', '    if False:\n        nombre = sesion.uno(')],
     [T289 + "test_o4_cuenta_de_desembolso_sin_recibir_ingreso",
      T289 + "test_o_h31_cuenta_de_desembolso_cerrada_ledger_posterior_o_deshabilitada"], None, 1),
    ("M-H-30", "movimiento del desembolso por P - comision (1.000,00) en lugar de P",
     [(ALTA, 'fecha_movimiento=pl.escritura, importe=pl.p,',
       'fecha_movimiento=pl.escritura, importe=pl.p - Decimal("1000.00"),')],
     [O_H26], None, 1),
    ("M-H-31", "fecha_desembolso aceptada e ignorada (fuera de MODALIDAD)",
     [(ALTA, 'MODALIDAD = ("fecha_desembolso", "pago_directo_vendedor", "tramos")',
       'MODALIDAD = ("pago_directo_vendedor", "tramos")')],
     [T289 + "test_o_h32_o_h33_o_h11_condiciones_incompletas_sin_escrituras"], None, 1),
    ("M-H-32", "Hd con tipo INGRESO en lugar de GENERACION_DERECHO_OBLIGACION",
     [(ALTA, 'TIPO_HD = "GENERACION_DERECHO_OBLIGACION"', 'TIPO_HD = "INGRESO"')],
     [O_H26, T289 + "test_o4_o5_positivo_con_solo_recibir_ingreso_y_sin_efecto_ingreso"], None, 1),
    # ------------------------------------------------------------ frontera F05 / OP-22 / capacidad privada
    ("M-H-36", "corregir_estado_terminal sin la guarda de prevision de cuota (O-H35, G1-R)",
     [(PREV, '            ) is not None:                                     # F06-01H (M-H-36): nunca reabrir una cuota\n',
       '            ) is not None and False:                           # F06-01H (M-H-36): nunca reabrir una cuota\n')],
     [T293 + "test_o_h35_servicio_corregir_estado_terminal_rechaza_la_prevision_de_una_cuota"], None, 1),
    ("M-H-39", "capacidad privada del vinculo construida desde fuera (sin comprobar el token; §5.1)",
     [(VINC, '        if token is not _TOKEN:\n            raise', '        if False:\n            raise')],
     [T293 + "test_capacidad_privada_no_se_construye_desde_fuera"], None, 1),
    ("M-H-40", "negativo de OP-22 eliminado: la ruta generica acepta el vinculo FINANCIACION de nivel efecto (O-H8)",
     [(CTXS, '    elif tipo == TIPO_ENTIDAD_FINANCIACION:\n        if e.efecto_id is not None:\n',
       '    elif tipo == TIPO_ENTIDAD_FINANCIACION:\n        if False:\n')],
     [T293 + "test_o_h8_op22_generico_con_vinculo_de_financiacion_rechazado"], None, 1),
    ("M-H-41a", "ajustar_importe_cuota_hipoteca admite una prevision con regla (PREVISION_CON_REGLA eliminada)",
     [(PREV, '            if prevision["regla_version_id"] is not None:\n                raise incompatible("PREVISION_CON_REGLA")\n',
       '')],
     [T294 + "test_i3_rechaza_la_prevision_con_regla"], None, 1),
    ("M-H-41b", "ajustar_importe_cuota_hipoteca admite una prevision no ABIERTA (PREVISION_NO_ABIERTA eliminada)",
     [(PREV, '            if prevision["estado"] != ABIERTA:\n                raise incompatible("PREVISION_NO_ABIERTA")\n',
       '')],
     [T294 + "test_i3_rechaza_la_prevision_no_abierta"], None, 1),
    # ------------------------------------------------------------ L-HIP (lectura)
    ("M-H-43a", "L-HIP: saldo indeterminado (apertura NULL) tratado como 0 (deuda_pendiente calculada, O-H10)",
     [(LECT, '    indeterminada = apertura is None\n', '    indeterminada = False\n')],
     [T288 + "test_l_hip_o_h10_legacy_indeterminada_nunca_cero"], None, 1),
    ("M-N30-S", "N-30 servidor: _titularidad_prestamo lee las participaciones de la PROPIEDAD (GARANTIZADA_POR)",
     [(LECT, 'LEFT JOIN gapto.terceros t ON t.id = a.tercero_id WHERE x.entidad_id = %s "',
       'LEFT JOIN gapto.terceros t ON t.id = a.tercero_id WHERE x.entidad_id = (SELECT r.entidad_destino_id '
       'FROM gapto.entidad_relaciones r WHERE r.entidad_origen_id = %s AND r.tipo_relacion = \'GARANTIZADA_POR\' '
       'ORDER BY r.id LIMIT 1) "')],
     [T288 + "test_l_hip_n30_titularidad_vigente_del_prestamo"], None, 1),
    # ------------------------------------------------------------ N-10 rama A (firma b7dbf079…; F04-D053 A1)
    ("M-H-45", "N-10: la deuda pendiente ignora saldo_principal_apertura (solo la suma de DEUDA desde el seguimiento)",
     [(LECT, '"SELECT f.saldo_principal_apertura + coalesce((SELECT sum(e.importe_delta) FROM gapto.hecho_efectos e "',
       '"SELECT 0 * f.saldo_principal_apertura + coalesce((SELECT sum(e.importe_delta) FROM gapto.hecho_efectos e "')],
     [T288 + "test_l_hip_n10_apertura_conocida_y_frontera",
      T293 + "test_n10_pago_con_apertura_conocida_suma_apertura_y_frontera"], None, 1),
    ("M-H-46", "N-10: la deuda pendiente cuenta los DEUDA anteriores a fecha_inicio_seguimiento (sin frontera A1)",
     [(LECT, '"AND h.fecha_hecho >= f.fecha_inicio_seguimiento "', '')],
     [T288 + "test_l_hip_n10_apertura_conocida_y_frontera",
      T293 + "test_n10_pago_con_apertura_conocida_suma_apertura_y_frontera",
      T293 + "test_n10_pago_capital_supera_la_deuda_con_apertura"], None, 1),
]

#: Lista del CLIENTE (mobile/src/...), mismo formato. La redacta otra persona en un fichero aparte y se incorpora aqui.
# --- cliente (mobile/; 14 del laboratorio MC-H + candidatos del paso 10 M-HC + N-30/N-31) ---
DOMH = "mobile/src/domain/hipoteca.ts"
PCUA = "mobile/src/screens/HipotecaCuadroScreen.tsx"
PPAG = "mobile/src/screens/PagarCuotaScreen.tsx"
PREVT = "mobile/src/screens/RevisarTipoScreen.tsx"
PCOM = "mobile/src/screens/CompraScreen.tsx"
JDOM = "jest:__tests__/hipoteca_dominio.test.ts::"
JPAN = "jest:__tests__/hipoteca_pantallas.test.tsx::"

# Patrones (subcadena literal del nombre del test; cada uno selecciona solo los tests discriminantes)
D_EXPO_PAGO = JDOM + "PAGO_CUOTA_EXPUESTO es una constante de"
D_BOTON = JDOM + "de pago solo con exposici"
D_TASA = JDOM + "tipo anual: 0 a 30"
D_CUOTAS = JDOM + "de cuotas mensuales"
D_FALTAS = JDOM + "cada dato obligatorio falta por separado"
D_POSTERIOR = JDOM + "tiene que ser POSTERIOR a la escritura"
D_CUADRO = JDOM + "la registrada, la ventana de la pr"
D_DESGLOSE = JDOM + "el cliente solo comprueba capital"
D_FALTAS_PAGO = JDOM + "fecha del cargo no futura, cuenta y reparto"
D_PROPUESTA = JDOM + "es SIEMPRE la propuesta mostrada"
D_AFECTADAS = JDOM + "afectadas = vencimiento"
D_REV_FECHA = JDOM + "la fecha tiene que ser posterior a las condiciones vigentes"
D_R1_TEXTOS = JDOM + "texto de la hipoteca dice"
D_R1_SEGURO = JDOM + "R-1: CONDICIONES_INCOMPLETAS con su motivo"
D_N30 = JDOM + "N-30: titularidadPrestamoEnFecha"
D_N31 = JDOM + "N-31: REVISION_TIPO_EXPUESTA"
P_COMPRA = JPAN + "campos, avisos, R-1"
P_SIN_AVISO = JPAN + "no hay aviso"
P_RECHAZO = JPAN + "un rechazo del servidor con"
P_NO_EXPUESTO = JPAN + "con false el cuadro NO ofrece"
P_BOTON = JPAN + "el pago es un BOT"
P_N31 = JPAN + "N-31 exposici"
P_LHIP_AVISO = JPAN + "solo si el servidor lo devuelve"
P_PAGAR = JPAN + "desglose del servidor"
P_N30 = JPAN + "N-30 pagar cuota: la propuesta es la titularidad"
P_NO_CUADRA = JPAN + "no se puede pagar"
P_PAGO_RECHAZOS = JPAN + "relee la propuesta con intenci"
P_REVISAR = JPAN + "las M pagadas no cambian"
P_REV_DESFASADA = JPAN + "revisar el tipo: VERSION_DESFASADA"

MUTANTES_CLIENTE = [
    # ---------------------------------------------------------------- laboratorio (MC-H-01..14, paso 1)
    ("MC-H-01", "la primera cuota puede ser la de la escritura o anterior (sin la guarda de posterioridad)",
     [(DOMH, "  else if (esFechaIso(escrituraIso) && b.primeraCuota <= escrituraIso) r.push(",
       "  else if (false) r.push(")],
     [D_POSTERIOR, P_COMPRA], None, 1),
    ("MC-H-02", "plazo sin el limite de 600 cuotas",
     [(DOMH, "  return n >= 1 && n <= MAX_CUOTAS ? n : null;", "  return n >= 1 ? n : null;")],
     [D_CUOTAS, D_FALTAS], None, 1),
    ("MC-H-03", "el tipo anual no normaliza la coma decimal (2,5 no se acepta)",
     [(DOMH, "  const x = t.trim().replace(',', '.');", "  const x = t.trim();")],
     [D_TASA], None, 1),
    ("MC-H-05", "«Ver el cuadro» guarda la compra (W-HIP-00 deja de ser vista previa sin escritura)",
     [(PCOM, "onCuadro={setPrevio} />", "onCuadro={(x) => { setPrevio(x); void guardar(); }} />")],
     [P_COMPRA], None, 1),
    ("MC-H-06", "el desglose siempre cuadra (= candidato 4 del paso 10, `cuadra: true`)",
     [(DOMH, "cuadra: !Number.isNaN(cap + int + total) && cap + int === total }", "cuadra: true }")],
     [D_DESGLOSE, P_NO_CUADRA], None, 1),
    ("MC-H-07", "el pago muestra la cuota como capital",
     [(PPAG, "etiqueta={ETIQUETA_CAPITAL} valor={formatearEur(d.capital)}", "etiqueta={ETIQUETA_CAPITAL} valor={formatearEur(d.salida)}")],
     [P_PAGAR], None, 1),
    ("MC-H-08", "el pago no envia la version de la financiacion",
     [(DOMH, "intencion_id: intencionId, row_version_esperada: h.row_version, cuenta_id: cuentaId",
       "intencion_id: intencionId, row_version_esperada: 0, cuenta_id: cuentaId")],
     [D_PROPUESTA, P_PAGAR], None, 1),
    ("MC-H-09", "la revision admite cuotas no ABIERTAS afectadas (= candidato 15 del paso 10)",
     [(DOMH, "    else if (afectadas.some((q) => !ABIERTAS.includes(q.estado))) out.push(",
       "    else if (false && afectadas.some((q) => !ABIERTAS.includes(q.estado))) out.push(")],
     [D_REV_FECHA, P_REVISAR], None, 1),
    ("MC-H-10", "la revision no exige fecha posterior a las condiciones vigentes",
     [(DOMH, "  else if (vigente && r.desde <= vigente.vigente_desde) out.push(", "  else if (false) out.push(")],
     [D_REV_FECHA], None, 1),
    ("MC-H-11", "cuotas afectadas = solo las PAGADAS que vencen desde la fecha",
     [(DOMH, "h.cuotas.filter((q) => q.vencimiento >= desdeIso);",
       "h.cuotas.filter((q) => q.vencimiento >= desdeIso && q.estado === 'PAGADA');")],
     [D_AFECTADAS, P_REVISAR], None, 1),
    ("MC-H-12", "el cuadro registrado no anade la ultima cuota a la ventana",
     [(DOMH, "  return ultima === undefined || ventana.includes(ultima) ? ventana : [...ventana, ultima];", "  return ventana;")],
     [D_CUADRO], None, 1),
    ("MC-H-13", "fila del cuadro con intereses y capital intercambiados (VP-3)",
     [(PCUA, "{`Intereses ${formatearEur(p.interes)} · Capital ${formatearEur(p.capital)}",
       "{`Intereses ${formatearEur(p.capital)} · Capital ${formatearEur(p.interes)}")],
     [P_COMPRA], None, 1),
    ("MC-H-14", "tras escribir no se pinta la hipoteca devuelta por el servidor",
     [(PCUA, "    setHip(h);\n    setCambios(true);", "    setCambios(true);")],
     [P_PAGAR, P_REVISAR], None, 1),
    # ---------------------------------------------------------------- informe del paso 10 (M-HC-01..19)
    ("M-HC-01", "PAGO_CUOTA_EXPUESTO cambia de valor (true -> false; N-40 lo fijo a true)",
     [(DOMH, "export const PAGO_CUOTA_EXPUESTO = true;", "export const PAGO_CUOTA_EXPUESTO = false;")],
     [D_EXPO_PAGO, P_NO_EXPUESTO], None, 1),
    ("M-HC-02", "el cuadro ofrece el pago sin la constante (ofrecePagoCuota(hip, true))",
     [(PCUA, "ofrecePagoCuota(hip, PAGO_CUOTA_EXPUESTO)", "ofrecePagoCuota(hip, true)")],
     [P_NO_EXPUESTO, P_N31], None, 1),
    ("M-HC-03", "ofrecePagoCuota sin `expuesto &&`",
     [(DOMH, "  expuesto && h.proxima_cuota !== null && h.estado === 'ACTIVA' && !h.deuda_indeterminada;",
       "  h.proxima_cuota !== null && h.estado === 'ACTIVA' && !h.deuda_indeterminada;")],
     [D_BOTON, P_NO_EXPUESTO], None, 1),
    ("M-HC-05", "el boton de pago no se deshabilita si el desglose no cuadra",
     [(PPAG, "deshabilitado={faltas.length > 0 || !d.cuadra}", "deshabilitado={faltas.length > 0}")],
     [P_NO_CUADRA], None, 1),
    ("M-HC-06", "tipo anual sin el maximo del 30 %",
     [(DOMH, "  return Number(x) <= TASA_MAXIMA ? x : null;", "  return x;")],
     [D_TASA, D_FALTAS], None, 1),
    ("M-HC-07", "primera cuota: `<=` -> `<` (el mismo dia de la escritura vale)",
     [(DOMH, "b.primeraCuota <= escrituraIso", "b.primeraCuota < escrituraIso")],
     [D_POSTERIOR, P_COMPRA], None, 1),
    ("M-HC-08", "textoSeguro sin el filtro de «ingreso»/«cobro»",
     [(DOMH, "(t && !PALABRAS_PROHIBIDAS.test(t) ? t : alternativo)", "(t ? t : alternativo)")],
     [D_R1_SEGURO, P_RECHAZO], None, 1),
    ("M-HC-09", "aviso O-H30 del cuadro siempre visible",
     [(PCUA, "{hip.aviso_reparto_distinto ? <Text testID=\"hip-aviso-reparto\"", "{true ? <Text testID=\"hip-aviso-reparto\"")],
     [P_LHIP_AVISO], None, 1),
    ("M-HC-10", "la compra marca siempre el aviso de reparto (setAvisoReparto(true))",
     [(PCOM, "setAvisoReparto(res.datos.aviso_reparto_distinto === true);", "setAvisoReparto(true);")],
     [P_SIN_AVISO], None, 1),
    ("M-HC-11", "el pago no recarga ante VERSION_DESFASADA",
     [(PPAG, "    if (r.codigo === 'VERSION_DESFASADA') return p.onRecargar();\n", "")],
     [P_PAGO_RECHAZOS], None, 1),
    ("M-HC-12", "la revision no recarga ante VERSION_DESFASADA",
     [(PREVT, "    if (x.codigo === 'VERSION_DESFASADA') return p.onRecargar();\n", "")],
     [P_REV_DESFASADA], None, 1),
    ("M-HC-13", "propuesta_vista = partes elegidas (no la propuesta mostrada)",
     [(DOMH, "propuesta_vista: { partes: partesReparto({ modo: 'TITULARIDAD' }, propuesta) }",
       "propuesta_vista: { partes: partesReparto(e, propuesta) }")],
     [D_PROPUESTA, P_PAGAR], None, 1),
    ("M-HC-14", "sin intencion nueva tras ATRIBUCION_PROPUESTA_DESFASADA",
     [(PPAG, "      intencion.current = p.nuevoId();\n      void cargarPropuesta();", "      void cargarPropuesta();")],
     [P_PAGO_RECHAZOS], None, 1),
    ("M-HC-16", "la cuenta de desembolso se elige entre las de GASTO (no las que reciben dinero)",
     [(PCOM, "p.cliente.cuentasElegibles('INGRESO', p.escrituraIso)", "p.cliente.cuentasElegibles('GASTO', p.escrituraIso)")],
     [P_COMPRA], None, 1),
    ("M-HC-17", "cabecera del cuadro «Cerrar» -> «Cancelar»",
     [(PCUA, "titulo=\"Cerrar\"", "titulo=\"Cancelar\"")],
     [P_COMPRA, P_NO_EXPUESTO], None, 1),
    ("M-HC-18", "cifras del cuadro sin tabular-nums",
     [(PCUA, "  cifra: { fontVariant: ['tabular-nums'] },", "  cifra: {},")],
     [P_COMPRA, P_BOTON], None, 1),
    ("M-HC-19", "sin el texto propio de CUENTA_SIN_CAPACIDAD",
     [(DOMH, "  CUENTA_SIN_CAPACIDAD: 'Esta cuenta no puede recibir dinero en la fecha de la escritura.',\n", "")],
     [D_R1_TEXTOS, P_RECHAZO], None, 1),
    # ---------------------------------------------------------------- reparto de los intereses del pago (§12.1)
    ("M-HC-20", "el pago envia siempre la propuesta como partes (ignora el reparto elegido)",
     [(DOMH, "}, partes: partesReparto(e, propuesta) },", "}, partes: partesReparto({ modo: 'TITULARIDAD' }, propuesta) },")],
     [D_PROPUESTA, P_PAGAR], None, 1),
    ("M-HC-21", "faltasPago no exige el reparto de los intereses",
     [(DOMH, "  return [...r, ...faltasReparto(e, propuesta).map((x) => `${x} de los intereses`)];", "  return r;")],
     [D_FALTAS_PAGO], None, 1),
    # ---------------------------------------------------------------- N-30 y N-31 (f412b11)
    ("M-HC-N30", "titularidadPrestamoEnFecha ignora vigente_hasta",
     [(DOMH, ".filter((t) => t.vigente_desde <= fechaIso && (t.vigente_hasta === null || fechaIso <= t.vigente_hasta))",
       ".filter((t) => t.vigente_desde <= fechaIso)")],
     [D_N30, P_N30], None, 1),
    ("M-HC-N31a", "ofreceRevisionTipo sin `expuesta &&`",
     [(DOMH, "  expuesta && h.estado === 'ACTIVA' && !h.deuda_indeterminada;", "  h.estado === 'ACTIVA' && !h.deuda_indeterminada;")],
     [D_N31, P_N31], None, 1),
    ("M-HC-N31b", "el cuadro ofrece la revision sin la constante (ofreceRevisionTipo(hip, true))",
     [(PCUA, "ofreceRevisionTipo(hip, REVISION_TIPO_EXPUESTA)", "ofreceRevisionTipo(hip, true)")],
     [P_N31], None, 1),
]

# Apartados (no entran en el arnes sin decision): superficie existente pero sin oraculo Jest que la discrimine.
CANDIDATOS_APARTADOS = [
    # MC-H-04 del laboratorio («el alta envia la version de la PROPIEDAD»): en el bloque real el alta va dentro de
    # C-COMPRA-01 y la version es la de la propiedad (payloadCompra). Ningun Jest fija row_version_esperada de la
    # compra (compra.test.tsx y hipoteca_pantallas solo comparan el bloque `hipoteca`): previsiblemente SOBREVIVE.
    ("MC-H-04", "la compra con hipoteca no envia la version de la propiedad",
     [(PCOM, "payloadCompra(intencion.current, p.vista.row_version,", "payloadCompra(intencion.current, 0,")],
     [JPAN + "con el bloque"], None, 1),
]

# MC-H-04 sale de CANDIDATOS_APARTADOS: oraculo Jest propio anadido en el paso 12 (hipoteca_pantallas v0.5.0).
MUTANTES_CLIENTE.append(
    ("MC-H-04", "la compra con hipoteca no envia la version de la propiedad (row_version_esperada 0)",
     [(PCOM, "payloadCompra(intencion.current, p.vista.row_version,", "payloadCompra(intencion.current, 0,")],
     [JPAN + "MC-H-04 row_version_esperada"], None, 1))

GRUPOS = {"servidor": MUTANTES, "cliente": MUTANTES_CLIENTE}


def normalizar(mu: tuple) -> tuple:
    """(id, desc, cambios, tests, equivalencia, repeticiones); admite la forma de 5 campos (repeticiones = 1)."""
    if len(mu) == 5:
        return (*mu, 1)
    if len(mu) != 6 or not isinstance(mu[5], int) or mu[5] < 1:
        sys.exit(f"Mutante mal formado: {mu[0] if mu else mu!r}")
    return tuple(mu)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


_OMITIDOS = re.compile(r"\b\d+ (skipped|xfailed|xpassed)\b")


def correr(tests: list[str]) -> tuple[int, bool]:
    """pytest por grupo (tests/api con su rootdir; test_295 aparte con GAPTO_F06HIP_CONCURRENCIA=1; el resto de
    tests/ sin rootdir) y Jest en mobile/. Devuelve (rc, hubo_omitidos): rc != 0 si alguno falla."""
    conc = [t for t in tests if t.startswith(CONCURRENCIA)]
    api = [t for t in tests if t.startswith("tests/api/") and t not in conc]
    resto = [t for t in tests if t.startswith("tests/") and not t.startswith("tests/api/")]
    jest = [t[len("jest:"):] for t in tests if t.startswith("jest:")]
    rc, omitidos = 0, False
    base = dict(os.environ)
    for grupo, extra, entorno in ((api, ["--rootdir=tests/api"], base),
                                  (conc, ["--rootdir=tests/api"], {**base, "GAPTO_F06HIP_CONCURRENCIA": "1"}),
                                  (resto, [], base)):
        if not grupo:
            continue
        cmd = [sys.executable, "-m", "pytest", *grupo, "-q", "-x", "-p", "no:cacheprovider", "-rsx", *extra]
        p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, env=entorno)
        salida = p.stdout.decode("utf-8", "replace")
        omitidos = omitidos or bool(_OMITIDOS.search(salida))
        rc = rc or p.returncode
    npx = "npx.cmd" if os.name == "nt" else "npx"
    for t in jest:
        fichero, patron = t.split("::", 1)
        cmd = [npx, "jest", fichero, "-t", patron, "--silent"]
        p = subprocess.run(cmd, cwd=RAIZ / "mobile", capture_output=True)
        texto = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
        # con -t, un patron que no selecciona nada termina con rc 0 y sin «N passed»: eso no es verde
        omitidos = omitidos or (p.returncode == 0 and not re.search(r"Tests:.*\b[1-9]\d* passed", texto))
        rc = rc or p.returncode
    return rc, omitidos


def recuperar_si_pendiente() -> bool:
    if not JOURNAL.exists():
        return False
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    for f in j["ficheros"]:
        ruta = RAIZ / f["fichero"]
        ruta.write_bytes(bytes.fromhex(f["original_hex"]))
        if sha(ruta.read_bytes()) != f["sha256"]:
            sys.exit(f"RECUPERACION FALLIDA: identidad no verificada en {f['fichero']}")
    JOURNAL.unlink()
    return True


def escribir_journal(datos: dict) -> None:
    with JOURNAL.open("w", encoding="utf-8") as f:
        f.write(json.dumps(datos))
        f.flush()
        os.fsync(f.fileno())


def anotar(salida: pathlib.Path | None, linea: str) -> None:
    print(linea, flush=True)
    if salida is not None:
        with salida.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def aplicar(cambios: list[tuple[str, str, str]]) -> tuple[dict[str, bytes], dict[str, str]] | None:
    """Sustitucion secuencial; None si algun texto viejo no aparece exactamente una vez."""
    ficheros = sorted({c[0] for c in cambios})
    originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
    textos = {f: b.decode("utf-8") for f, b in originales.items()}
    for f, texto, sustituto in cambios:
        if textos[f].count(texto) != 1:
            return None
        textos[f] = textos[f].replace(texto, sustituto)
    return originales, textos


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    grupo = sys.argv[sys.argv.index("--grupo") + 1] if "--grupo" in sys.argv else "todos"
    if grupo not in ("servidor", "cliente", "todos"):
        sys.exit("--grupo servidor|cliente|todos")
    lista = [normalizar(mu) for mu in (MUTANTES + MUTANTES_CLIENTE if grupo == "todos" else GRUPOS[grupo])]
    ids = [mu[0] for mu in lista]
    if len(set(ids)) != len(ids):
        sys.exit("IDs de mutante repetidos.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
        desconocidos = solo - set(ids)
        if desconocidos:
            sys.exit(f"--solo con IDs fuera del grupo {grupo}: {sorted(desconocidos)}")
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    elegidos = [mu for mu in lista if solo is None or mu[0] in solo]
    if not elegidos:
        sys.exit("Ningun mutante elegido.")
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    rc, omitidos = correr(preflight)
    if rc != 0 or omitidos:
        sys.exit("PREFLIGHT ROJO" + (" (tests omitidos: no son verdes)" if omitidos else "") + ": no se muta nada.")
    anotar(salida, f"PREFLIGHT VERDE grupo={grupo} mutantes={len(elegidos)} tests={len(preflight)}")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia, repeticiones in elegidos:
        aplicado = aplicar(cambios)
        if aplicado is None:
            v = (mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc)
            veredictos.append(v)
            anotar(salida, " | ".join(v))
            continue
        originales, textos = aplicado
        ficheros = sorted(originales)
        escribir_journal({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros]})
        resultado = "NO_CLASIFICABLE"
        motivo_nc = ""
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            muertes = 0
            for k in range(1, repeticiones + 1):
                rc, omitidos = correr(tests)
                pasada = "OMITIDO" if (rc == 0 and omitidos) else ("MUERTO" if rc != 0 else "VIVO")
                anotar(salida, f"  PASADA {mid} {k}/{repeticiones}: {pasada} (rc={rc})")
                if pasada == "OMITIDO":
                    motivo_nc = "tests omitidos en la pasada"
                    break
                muertes += pasada == "MUERTO"
            else:
                resultado = "MUERTO" if muertes == repeticiones else (
                    "VIVO" if muertes == 0 else f"INESTABLE_{muertes}de{repeticiones}")
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if resultado == "VIVO" and equivalencia:
            resultado = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if resultado == "EQUIVALENTE" else desc
        if motivo_nc:
            nota = f"{desc} [{motivo_nc}]"
        if not ok:
            resultado, nota = "NO_CLASIFICABLE", f"{desc} [restauracion no verificada]"
        v = (mid, resultado, f"x{repeticiones}",
             ",".join(sorted({pathlib.Path(t.split("::")[0].replace("jest:", "")).name for t in tests})), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
        if not ok:
            sys.exit(f"RESTAURACION NO VERIFICADA en {mid}: se detiene el arnes. Resultado NO-PASS.")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN grupo={grupo}: {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
