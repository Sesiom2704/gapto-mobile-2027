# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f04_r2b.py
# Ruta: scripts/dev/mutantes_f04_r2b.py
# Descripcion: Arnes de mutacion de F04-R2 R2-B (mandato F04-R2B v1.0 §5;
#   contrato F04-R2 v0.8 §10.4: un mutante por guarda, 100 % muertos o
#   equivalentes documentados, bajo el rol real gapto_runtime con RLS).
#   Mismo motor que mutantes_f04_r2a.py (D-181, D-192, D-193, WM 12C.2):
#     - sustituciones de texto exacto (UNA ocurrencia) y sus discriminantes
#       (nodeid de pytest de tests/backend);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - veredicto: MUERTO | VIVO | NO_CLASIFICABLE (EQUIVALENTE si se declara).
#   Guardas: E-1..E-7 (E-4 por dimension: fecha, importe, cuenta), E-2 bis,
#   T-1..T-6 y T-1 bis; declaraciones (error_de_registro, motivo, request_id);
#   §2.5 fila a fila; periodo cerrado y ledger; reglas de la cuenta nueva;
#   cuentas: sin lock en el motor, cuenta despues del hecho (candidato B) y
#   antes del advisory (candidato A); §3.2 y §3.4 (sin revalidar el original,
#   sin su lock, original bloqueado despues sin el conjunto previo); reparto y
#   aportaciones deterministas; vinculos_a_corregir; auditoria (una llamada
#   omitida, request_id no exigido); capacidad del adaptador F05.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_F04R2B_CONCURRENCIA=1
#        python scripts/dev/mutantes_f04_r2b.py [--solo ID,ID]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F04-R2 R2-B)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f04_r2b.journal.json"

SERV = "backend/app/services/correccion_tesoreria_service.py"
CORR = "backend/app/services/correcciones_service.py"
ADAP = "backend/app/api/ejecucion_correccion.py"
T14C = "tests/backend/test_14c_f04_r2b_discriminantes.py::"
T14D = "tests/backend/test_14d_f04_r2b_concurrencia_serial.py::"


def c(nombre: str) -> str:
    return T14C + nombre


def d(nombre: str) -> str:
    return T14D + nombre


#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- E-1
    ("B01", "E-1 sin la guarda de tipo de hecho GASTO",
     [(SERV, '        if hecho["tipo"] != TIPO_GASTO:\n            raise _fuera("TIPO_NO_SOPORTADO")\n',
       '        if False:\n            raise _fuera("TIPO_NO_SOPORTADO")\n')],
     [c("test_e1_hecho_que_no_es_gasto")], None),
    ("B02", "E-1 sin excluir las devoluciones (§2.4)",
     [(SERV, "        if repo.es_origen_de_devolucion(sesion, datos.hecho_id):\n",
       "        if False:\n")],
     [c("test_devolucion_con_abono_no_se_corrige")], None),
    ("B03", "E-1 sin excluir las inversiones",
     [(SERV, "        if repo.tiene_entidad_de_inversion(sesion, datos.hecho_id):\n", "        if False:\n")],
     [c("test_e1_inversion_fuera_de_v1")], None),
    ("B04", "E-1 con varios efectos (toma el primero)",
     [(SERV, '        estado["efecto"] = estado["efectos"][0] if len(estado["efectos"]) == 1 else None\n',
       '        estado["efecto"] = estado["efectos"][0] if estado["efectos"] else None\n')],
     [c("test_e1_varios_efectos_fuera_de_v1")], None),
    # ---------------------------------------------------------------- E-2 / E-2 bis / E-3
    ("B05", "E-2 con varios movimientos",
     [(SERV, '        if len(lista) > 1:\n            raise _fuera("VARIOS_MOVIMIENTOS")\n        movimiento = estado["movimiento"]\n',
       '        movimiento = estado["movimiento"]\n'),
      (SERV, '        estado["conciliacion"] = lista[0] if len(lista) == 1 else None\n',
       '        estado["conciliacion"] = lista[0] if lista else None\n'),
      (SERV, '            repo.leer_movimiento(sesion, lista[0]["movimiento_id"]) if len(lista) == 1 else None\n',
       '            repo.leer_movimiento(sesion, lista[0]["movimiento_id"]) if lista else None\n')],
     [c("test_e2_varios_movimientos_fuera_de_v1")], None),
    ("B06", "E-2 sin exigir el movimiento ACTIVO",
     [(SERV, '        if movimiento is None or movimiento["estado"] != ESTADO_ACTIVO:\n            raise ErrorMotor(CodigoError.MOVIMIENTO_ANULADO, "El movimiento del pago no esta activo.")\n',
       '')],
     [c("test_c1_seis_dimensiones_en_sitio_con_saldo_y_auditoria")],
     "D-119 (0270 fn_check_movimiento_padre): un movimiento ANULADO no puede tener conciliaciones, asi que "
     "E-2 (una conciliacion) implica movimiento ACTIVO; la guarda es defensa en profundidad no alcanzable"),
    ("B07", "E-2 bis sin la cobertura completa",
     [(SERV, '        self._cobertura(estado["conciliacion"], movimiento, hecho["importe_total"])\n', '')],
     [c("test_e2_bis_conciliacion_parcial")], None),
    ("B08", "E-3 sin rechazar el movimiento compartido",
     [(SERV, '        if repo.hechos_conciliados(sesion, movimiento["id"]) != [hecho_id]:\n',
       '        if False:\n')],
     [c("test_movimiento_compartido_fuera_de_v1")], None),
    # ---------------------------------------------------------------- E-4 por dimension
    ("B09", "E-4 fecha: la reversion no bloquea el cambio de fecha (PRE M1)",
     [(SERV, "        if tiene_reversion and (cambia_importe or cambia_fecha or cambia_cuenta):\n",
       "        if tiene_reversion and (cambia_importe or cambia_cuenta):\n")],
     [c("test_reversion_existente_en_las_tres_dimensiones[ACTIVA-fecha]")], None),
    ("B10", "E-4 importe: la reversion no bloquea el cambio de importe (PRE M1)",
     [(SERV, "        if tiene_reversion and (cambia_importe or cambia_fecha or cambia_cuenta):\n",
       "        if tiene_reversion and (cambia_fecha or cambia_cuenta):\n")],
     [c("test_reversion_existente_en_las_tres_dimensiones[ACTIVA-importe]")], None),
    ("B11", "E-4 cuenta: la reversion no bloquea el cambio de cuenta (PRE M2: llegaria el 23503)",
     [(SERV, "        if tiene_reversion and (cambia_importe or cambia_fecha or cambia_cuenta):\n",
       "        if tiene_reversion and (cambia_importe or cambia_fecha):\n")],
     [c("test_reversion_existente_en_las_tres_dimensiones[ACTIVA-cuenta]")], None),
    ("B12", "E-4 reversion ANULADA no cuenta (solo ACTIVAS)",
     [(SERV, '        tiene_reversion = movimiento["reversiones"] > 0 or movimiento["reversion_de"] is not None\n',
       '        tiene_reversion = movimiento["reversion_de"] is not None or bool(sesion.uno("SELECT 1 FROM '
       'gapto.movimientos_tesoreria WHERE reversion_de_movimiento_id = %s AND estado = \'ACTIVO\'", '
       '(movimiento["id"],)))\n')],
     [c("test_reversion_existente_en_las_tres_dimensiones[ANULADA-fecha]")], None),
    ("B13", "E-4 sin excluir el movimiento de una transferencia en OP-21P",
     [(SERV, '        if movimiento["transferencia_id"] is not None:\n            raise _fuera("TIPO_NO_SOPORTADO")\n'
             '        cambia_cuenta = datos.cuenta_id',
       '        cambia_cuenta = datos.cuenta_id')],
     [c("test_c1_seis_dimensiones_en_sitio_con_saldo_y_auditoria")],
     "una pata de transferencia ya esta conciliada con el hecho TRANSFERENCIA: E-3 (MOVIMIENTO_COMPARTIDO) "
     "rechaza antes cualquier GASTO conciliado con ella, y la BD impide superar |importe| (0270)"),
    # ---------------------------------------------------------------- E-5 / E-6
    ("B14", "E-5 sin rechazar la multidivisa",
     [(SERV, '        if cuenta_actual is None or cuenta_actual["moneda"] != hecho["moneda"]:\n            raise _fuera("MULTIDIVISA")\n        if hecho["row_version"] != datos.row_version_esperada:\n            raise _desfasada("El hecho")\n        if movimiento["row_version"]',
       '        if hecho["row_version"] != datos.row_version_esperada:\n            raise _desfasada("El hecho")\n        if movimiento["row_version"]')],
     [c("test_e5_multidivisa_fuera_de_v1")], None),
    ("B15", "E-6 sin rechazar el origen importado (§2.5 fila 1)",
     [(SERV, "        if repo.importado(sesion, destinos):\n", "        if False:\n")],
     [c("test_origen_importado_rechazado[hechos_financieros]"),
      c("test_origen_importado_rechazado[movimientos_tesoreria]")], None),
    ("B16", "E-6 sin rechazar AJUSTE_SALDO (§2.5 fila 2)",
     [(SERV, '        if any(m["clase"] == CLASE_AJUSTE for m in movimientos):\n', "        if False:\n")],
     [c("test_ajuste_de_saldo_rechazado")], None),
    # ---------------------------------------------------------------- E-7 / §5
    ("B17", "§5.1 sin el periodo cerrado (§2.5 fila 3)",
     [(SERV, "        if repo.periodo_cerrado(sesion, fechas):\n", "        if False:\n")],
     [c("test_periodo_cerrado_con_cierres_sinteticos[cierres0-cambio0-True]"),
      c("test_op21t_cuenta_nueva_y_periodo[periodo_cerrado]")], None),
    ("B18", "§5.1 con la PRIMERA version del cierre en vez de la vigente",
     [("backend/app/repositories/correccion_tesoreria_repository.py",
       "                   SELECT max(u.version_cierre) FROM gapto.cierres_mensuales u\n",
       "                   SELECT min(u.version_cierre) FROM gapto.cierres_mensuales u\n")],
     [c("test_periodo_cerrado_con_cierres_sinteticos[cierres1-cambio1-False]")], None),
    ("B19", "§5.2 sin el ledger de la cuenta (§2.5 fila 4)",
     [(SERV, '            if cuenta is not None and cuenta["inicio_ledger"] is not None and fecha_final < cuenta["inicio_ledger"]:\n',
       "            if False:\n")],
     [c("test_ledger_de_la_cuenta")], None),
    # ---------------------------------------------------------------- cuenta nueva (§2.1.5)
    ("B20", "cuenta nueva no visible sin CUENTA_DESCONOCIDA",
     [(SERV, '        if cuenta is None:\n            raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA, "La cuenta indicada no existe o no es accesible.")\n',
       "")],
     [c("test_cuenta_nueva_no_valida_rechazada[otro_owner]")], None),
    ("B21", "cuenta nueva de otra moneda admitida",
     [(SERV, '        if cuenta["moneda"] != moneda:\n', "        if False:\n")],
     [c("test_cuenta_nueva_no_valida_rechazada[otra_moneda]")], None),
    ("B22", "cuenta nueva deshabilitada admitida",
     [(SERV, '        if not cuenta["enabled"]:\n', "        if False:\n")],
     [c("test_cuenta_nueva_no_valida_rechazada[deshabilitada]"),
      c("test_op21t_cuenta_nueva_y_periodo[deshabilitada]")], None),
    ("B23", "cuenta nueva cerrada antes de la fecha admitida",
     [(SERV, '        if cuenta["fecha_cierre"] is not None and cuenta["fecha_cierre"] < fecha:\n', "        if False:\n")],
     [c("test_cuenta_nueva_no_valida_rechazada[cerrada_antes]")],
     "ck_cuentas__cierre_deshabilita (BD): una cuenta con fecha_cierre esta siempre deshabilitada, asi que la "
     "guarda de enabled la rechaza antes; la de fecha_cierre es defensa en profundidad no alcanzable"),
    # ---------------------------------------------------------------- declaraciones (§1.5, §8.1)
    ("B24", "sin exigir error_de_registro = true",
     [(SERV, "    if error_de_registro is not True:\n", "    if False:\n")],
     [c("test_sin_error_de_registro_es_acontecimiento_posterior[None]"),
      c("test_sin_error_de_registro_es_acontecimiento_posterior[False]")], None),
    ("B25", "sin exigir el motivo",
     [(SERV, '    if not (motivo or "").strip():\n', "    if False:\n")],
     [c("test_motivo_ausente")], None),
    ("B26", "request_id no exigido",
     [(SERV, '    if getattr(contexto, "request_id", None) is None:\n', "    if False:\n")],
     [c("test_sin_request_id_rechazado")], None),
    # ---------------------------------------------------------------- OP-21T
    ("B27", "T-1 sin exigir una TRANSFERENCIA con sus dos patas",
     [(SERV, '        if hecho["tipo"] != TIPO_TRANSFERENCIA or salida is None or entrada is None:\n',
       "        if False:\n")],
     [c("test_op21t_sobre_un_gasto_no_aplica"), c("test_op21t_t1_transferencia_sin_su_fila")], None),
    ("B28", "T-1 bis sin la cobertura por pata",
     [(SERV, '            self._cobertura(conciliaciones[pata], movimiento, hecho["importe_total"])\n', "")],
     [c("test_op21t_t1_bis_cobertura_por_pata")], None),
    ("B29", "T-2 sin reversiones ni otros hechos en las patas",
     [(SERV, "            self._sin_compartir_ni_revertir(sesion, datos.hecho_id, movimiento,\n"
             "                                            cambia_importe=datos.importe is not None,\n"
             "                                            cambia_fecha=datos.fecha is not None, cambia_cuenta=cambia[pata])\n",
       "")],
     [c("test_op21t_con_reversion_de_una_pata")], None),
    ("B30", "T-3 sin rechazar la multidivisa",
     [(SERV, '            if cuenta_actual is None or cuenta_actual["moneda"] != hecho["moneda"]:\n                raise _fuera("MULTIDIVISA")\n',
       "")],
     [c("test_op21t_multidivisa_fuera_de_v1")], None),
    ("B31", "T-4 sin MISMA_CUENTA (la BD lo rechazaria con otro codigo)",
     [(SERV, '        if finales[salida["id"]] == finales[entrada["id"]]:\n', "        if False:\n")],
     [c("test_op21t_misma_cuenta")], None),
    # ---------------------------------------------------------------- locks de cuenta (§6.7.1)
    ("B32", "cuenta nueva SIN lock en el motor",
     [(SERV, "        repo.bloquear_cuentas(sesion, cuentas)\n", "")],
     [d("test_cuenta_nueva_frente_a_deshabilitarla[B-primero-OP-21P-motor]")], None),
    ("B33", "cuenta bloqueada DESPUES del hecho (candidato B)",
     [(SERV, "        repo.bloquear_cuentas(sesion, cuentas)\n"
             "        # 3-4. Hecho y posiciones que alimenta (sin advisory: ya tomado).\n"
             "        posiciones = integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id])\n",
       "        # 3-4. Hecho y posiciones que alimenta (sin advisory: ya tomado).\n"
       "        posiciones = integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id])\n"
       "        repo.bloquear_cuentas(sesion, cuentas)\n"),
      (ADAP, "    if plan.advisory:\n        tomar_inversiones(sesion)\n    if not plan.cuentas_nuevas:\n        return\n"
             "    bloquear_cuentas(sesion, *plan.cuentas_nuevas)\n",
       "    if plan.advisory:\n        tomar_inversiones(sesion)\n    if not plan.cuentas_nuevas:\n        return\n"
       "    sesion.uno(\"SELECT 1 FROM gapto.hechos_financieros WHERE id = %s FOR NO KEY UPDATE\", (plan.hecho_id,))\n"
       "    bloquear_cuentas(sesion, *plan.cuentas_nuevas)\n"),
      ("backend/app/services/correccion_tesoreria_service.py",
       "    advisory: bool\n    cuentas_nuevas: dict[uuid.UUID, str]  # cuenta -> operacion F05\n    fecha: dt.date | None\n",
       "    advisory: bool\n    cuentas_nuevas: dict[uuid.UUID, str]  # cuenta -> operacion F05\n    fecha: dt.date | None\n"
       "    hecho_id: uuid.UUID | None = None\n"),
      ("backend/app/services/correccion_tesoreria_service.py",
       "    return PlanCuentas(advisory=datos.importe is not None, cuentas_nuevas=nuevas, fecha=_fecha_previa(\n"
       "        sesion, datos.hecho_id, datos.fecha))\n",
       "    return PlanCuentas(advisory=datos.importe is not None, cuentas_nuevas=nuevas, fecha=_fecha_previa(\n"
       "        sesion, datos.hecho_id, datos.fecha), hecho_id=datos.hecho_id)\n")],
     [d("test_cuenta_nueva_frente_al_abono_m2[B-primero]")], None),
    ("B34", "cuenta bloqueada ANTES del advisory (candidato A)",
     [(SERV, "        if advisory:\n            repo_corr.tomar_advisory_inversiones(sesion, owner)\n"
             "        # 2 bis. Cuentas NUEVAS, conjunto completo y por UUID (§6.7.1).\n"
             "        repo.bloquear_cuentas(sesion, cuentas)\n",
       "        repo.bloquear_cuentas(sesion, cuentas)\n"
       "        if advisory:\n            repo_corr.tomar_advisory_inversiones(sesion, owner)\n"),
      (ADAP, "    if plan.advisory:\n        tomar_inversiones(sesion)\n    if not plan.cuentas_nuevas:\n        return\n"
             "    bloquear_cuentas(sesion, *plan.cuentas_nuevas)\n",
       "    if plan.cuentas_nuevas:\n        bloquear_cuentas(sesion, *plan.cuentas_nuevas)\n"
       "    if plan.advisory:\n        tomar_inversiones(sesion)\n    if not plan.cuentas_nuevas:\n        return\n")],
     [d("test_cuenta_nueva_frente_al_registro_f05_con_entidades[B-primero]")], None),
    ("B35", "capacidad del adaptador no comprobada",
     [(ADAP, "        if motivo_cuenta(sesion, cuenta_id, operacion, plan.fecha, bloquear=True) == SIN_CAPACIDAD:\n",
       "        if False:\n")],
     [c("test_adaptador_cuenta_sin_capacidad_sin_escritura")], None),
    # ---------------------------------------------------------------- §3.2 y §3.4
    ("B36", "§3.2 OP-21P por debajo de lo devuelto",
     [(SERV, "                exigir_devuelto_dentro_de_capacidad(sesion, datos.hecho_id)\n", "")],
     [c("test_bajar_la_compra_por_debajo_de_lo_devuelto")], None),
    ("B37", "§3.4 sin revalidar la capacidad del original",
     [(CORR, "            for _, original in originales:\n                self._exigir_capacidad_del_original(sesion, original)\n",
       "")],
     [c("test_34_sonda_r2a_devolucion_por_encima_de_la_capacidad"),
      c("test_34_segunda_devolucion_cuenta_en_el_acumulado")], None),
    ("B38", "§3.4 sin el lock del original",
     [(CORR, "                hechos=[datos.hecho_id, *(o for _, o in originales)],\n",
       "                hechos=[datos.hecho_id],\n")],
     [d("test_34_op21_devolucion_frente_a_op13_original[B-primero]")], None),
    ("B39", "§3.4.2 original bloqueado DESPUES de la devolucion, sin el conjunto previo",
     [(CORR, "            originales = self._originales_previos(sesion, datos)\n",
       "            originales = []\n"),
      (CORR, "            self._exigir_conjunto_devolucion(sesion, datos, originales)\n",
       "            originales = self._originales_previos(sesion, datos)\n"
       "            repo_rel.bloquear_hechos(sesion, [o for _, o in originales])\n"
       "            self._exigir_conjunto_devolucion(sesion, datos, originales)\n")],
     [d("test_34_conjunto_cambiado_reintenta_y_bloquea_las_dos_raices_juntas")], None),
    ("B40", "§3.4.1 varias DEVOLUCION_DE admitidas",
     [(CORR, '        if len(originales) > 1:\n            raise fuera("MULTIPLES_ORIGINALES")\n', "")],
     [c("test_34_1_casos_limite[multiples_originales]")], None),
    ("B41", "§3.4.1 cambio de naturaleza de la devolucion admitido",
     [(CORR, '        if any("tipo_efecto" in c for c in datos.efectos_a_actualizar.values()):\n            raise fuera("DEVOLUCION_NATURALEZA")\n',
       "")],
     [c("test_34_1_casos_limite[naturaleza]")], None),
    ("B42", "§3.4.1 retirar la relacion y cambiar el importe en la misma peticion",
     [(CORR, '        if {relacion for relacion, _ in originales} & set(datos.relaciones_a_eliminar):\n',
       "        if False:\n")],
     [c("test_34_1_casos_limite[combinacion]")], None),
    ("B43", "§3.4.1 original no ACTIVO admitido",
     [(CORR, '            if estado_original is None or estado_original[1] != "ACTIVO":\n', "            if False:\n")],
     [c("test_34_1_casos_limite[original_no_activo]")], None),
    # ---------------------------------------------------------------- reparto y aportaciones (§2.1.4)
    ("B44", "reparto no determinista reescalado en silencio",
     [(SERV, '        if len(filas) == 1 and D(filas[0]["importe"]) == delta:\n',
       "        if filas:\n")],
     [c("test_reparto_no_determinista_exige_decision")], None),
    ("B45", "residual de redondeo descartado",
     [(SERV, "        if residual:\n", "        if False:\n")],
     [c("test_residual_de_redondeo_en_la_de_mayor_porcentaje[porcentajes0-100.01-esperado0]")], None),
    ("B46", "residual en la de MENOR porcentaje",
     [(SERV, '            mayor = sorted(vinculadas, key=lambda a: (-D(a["porcentaje"]), str(a["id"])))[0]\n',
       '            mayor = sorted(vinculadas, key=lambda a: (D(a["porcentaje"]), str(a["id"])))[0]\n')],
     [c("test_residual_de_redondeo_en_la_de_mayor_porcentaje[porcentajes0-100.01-esperado0]")], None),
    ("B47", "cambio de cuenta con PARTICIPACION_CUENTA sin exigir decision",
     [(SERV, "        if cambia_cuenta and any(a[\"criterio\"] == PARTICIPACION_CUENTA for a in vinculadas):\n",
       "        if False:\n")],
     [c("test_cambio_de_cuenta_con_participacion_exige_aportaciones")], None),
    ("B48", "criterio no PARTICIPACION_CUENTA recalculado sin decision",
     [(SERV, '        if any(a["criterio"] != PARTICIPACION_CUENTA or a["porcentaje"] is None for a in vinculadas):\n',
       '        if any(a["porcentaje"] is None and a["criterio"] == "REGLA" for a in vinculadas):\n')],
     [c("test_aportacion_no_determinista_exige_decision")], None),
    ("B49", "aportacion no vinculada a la conciliacion ignorada",
     [(SERV, "        if len(vinculadas) != len(todas):\n", "        if False:\n")],
     [c("test_aportacion_no_vinculada_rechazada")], None),
    # ---------------------------------------------------------------- vinculos (§4.1)
    ("B50", "vinculos_a_corregir de otro hecho",
     [(SERV, '            if previo is None or previo["hecho_id"] != hecho_id:\n',
       "            if previo is None:\n")],
     [c("test_vinculos_a_corregir_de_otro_hecho_rechazado")], None),
    # ---------------------------------------------------------------- auditoria (§8.1)
    ("B51", "una llamada a auditoria.registrar omitida (conciliacion)",
     [(SERV, "        auditoria.registrar(sesion, tabla=repo.TABLA_CONCILIACIONES, registro_id=conciliacion_id,\n"
             "                            accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=par[0],\n"
             "                            datos_despues_json=par[1], motivo=motivo)\n",
       "")],
     [c("test_c1_seis_dimensiones_en_sitio_con_saldo_y_auditoria"),
      c("test_c1_reconstruccion_del_estado_previo_desde_la_auditoria")], None),
    ("B52", "idempotencia sin comparar la intencion auditada",
     [(SERV, "        if self._misma_intencion(auditadas, motivo, estado, datos):\n", "        if True:\n")],
     [c("test_repeticion_idempotente_y_request_id_con_otra_intencion")], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider"]
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode


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


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if os.getenv("GAPTO_F04R2B_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_F04R2B_CONCURRENCIA=1: los discriminantes seriales se omitirian.")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    elegidos = [m for m in MUTANTES if solo is None or m[0] in solo]
    preflight = sorted({t for m in elegidos for t in m[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, a, b in cambios:
            if textos[f].count(a) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(a, b)
        if not aplicable:
            veredictos.append((mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc))
            continue
        JOURNAL.write_text(
            json.dumps({"mutante": mid, "ficheros": [
                {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
            ]}),
            encoding="utf-8",
        )
        if hasattr(os, "sync"):
            os.sync()
        v = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            v = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if v == "VIVO" and equivalencia:
            v = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if v == "EQUIVALENTE" else desc
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE",
                           ",".join(sorted({pathlib.Path(t.split("::")[0]).name for t in tests})), nota))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    print(f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
          f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
