# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f04_r_hip.py
# Ruta: scripts/dev/mutantes_f04_r_hip.py
# Descripcion: Arnes de mutacion de T3-F06 · F04-R-HIP (mandato v1.2 §10 y
#   adenda v1.3 con D-04 y D-07): un mutante por guarda nueva y por modalidad.
#     MF04-01..04  guarda FINANCIACION de OP-21 sin la modalidad (a)..(d);
#     MF04-05      guarda que solo mira cuotas (Hd fuera);
#     MF04-06      guarda ampliada al vinculo de nivel hecho;
#     MF04-07..09  H-B-01 (guarda INVERSION): sin `efecto_id is not None`, sin
#                  `principal`, eliminada;
#     MF04-10a/b   guarda evaluada despues de la primera escritura (tras
#                  tocar_raiz: la mata O-PREC-21, D-07) o tras 3b (la mata la
#                  propia baja conjunta, D-07);
#     MF04-11..15  A9: eliminada en OP-03, eliminada en OP-03P, solo cuotas
#                  (muere tambien por O-A9-03-Hd, D-04), en OP-03P despues de
#                  W1 (la mata O-PREC-03P, D-07), ampliada al nivel hecho;
#     MF05-S1..S7  guarda F05 eliminada en cada writer (S6: un constructor de
#                  SuplementosService fuera de compuesto_service); S8 y S9 no
#                  tienen guarda nueva (no regresion / ningun escritor);
#     MF05-S10-*   guarda S10 eliminada por ruta (GP, GC, IC, TR);
#     MF05-L-*     lectura que vuelve a decir corregible/disponible = true;
#     MF05-INV-*   inventario sin una superficie y guarda S10 tras el advisory.
#   Mismo motor que mutantes_f04_r3.py (D-181, D-192, D-193, WM 12C.2):
#   sustitucion de texto exacto (UNA ocurrencia), journal durable ANTES del
#   primer byte, recuperacion si hay journal pendiente, preflight verde de los
#   discriminantes, restauracion verificada por SHA-256 y veredicto a disco
#   (append + fsync) en cuanto se conoce.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable postgresql://...>
#        GAPTO_F04RHIP_CONCURRENCIA=1
#        python scripts/dev/mutantes_f04_r_hip.py [--solo ID,ID] [--salida fichero]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F06 T3-F06 · F04-R-HIP, paso 6)
# Version: 0.1.1 (firma del STOP n.º 2): MF05-L-candidatos-cuota se discrimina tambien con el fixture de
#   prevision de cuota con tercero y categoria (candidatos NO vacios sin la guarda).
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f04_r_hip.journal.json"

COR = "backend/app/services/correcciones_service.py"
HEC = "backend/app/services/hechos_service.py"
ANT = "backend/app/services/anulacion_tesoreria_service.py"
REP = "backend/app/api/ejecucion_reparto.py"
DEV = "backend/app/api/ejecucion_devolucion.py"
ANU = "backend/app/api/ejecucion_anulacion.py"
CRR = "backend/app/api/ejecucion_correccion.py"
CV3 = "backend/app/api/ejecucion_categoria_v3.py"
PRV = "backend/app/api/ejecucion_prevision.py"
GP = "backend/app/api/ejecucion_gasto_pagado.py"
REG = "backend/app/api/ejecucion_registro.py"
EDI = "backend/app/actividad/edicion.py"
LEC = "backend/app/previsiones/lecturas.py"
INV = "tests/api/test_286_f04_r_hip_inventario_f05.py"

T14N = "tests/backend/test_14n_f04_r_hip_guardas.py::"
T285 = "tests/api/test_285_f04_r_hip_frontera_f05.py::"
T286 = "tests/api/test_286_f04_r_hip_inventario_f05.py::"
T287 = "tests/api/test_287_f04_r_hip_concurrencia_serial.py::"
H13 = T14N + "test_o_h13_op21_rechaza_la_modalidad_con_estado_identico"
PREC = T14N + "test_o_prec_21_la_guarda_precede_a_version_desfasada"
HB01 = T14N + "test_h_b_01_guarda_inversion"
S10 = T285 + "test_o_h22_s10_registrar_desde_la_prevision_de_una_cuota"

GUARDA_A1 = ("            # F04-R-HIP A1: efectos vinculados a una FINANCIACION a nivel de\n"
             "            # efecto. Bajo la raiz y antes de la primera escritura (D-07).\n"
             "            self._exigir_sin_financiacion(sesion, datos)\n")
LLAMADA_A1 = "            self._exigir_sin_financiacion(sesion, datos)\n"
A9_OP03 = ("            # F04-R-HIP A9: antes de cualquier otra guarda y de toda escritura.\n"
           "            exigir_anulacion_sin_financiacion(sesion, hecho_id)\n")
A9_OP03P = ("        # F04-R-HIP A9 (D-04): tras ACTIVO y antes del tipo, para cubrir Hd sea cual sea su tipo.\n"
            "        exigir_anulacion_sin_financiacion(sesion, hecho_id)\n")
A9_SI = ("        if efecto_id is not None:\n            raise ErrorMotor(\n"
         "                CodigoError.ANULACION_FINANCIACION_SIN_REVERSION,\n")


def _sin(fichero: str, texto: str) -> tuple[str, str, str]:
    return (fichero, texto, "")


def _guarda_s10(nombre_rechazo: str, objeto: str) -> str:
    return (f"        rechazo = gf.rechazo_bloque_prevision(sesion, {objeto})\n"
            f"        if rechazo is not None:\n            return {nombre_rechazo}(rechazo)\n")


#: (id, descripcion, [(fichero, texto, sustituto)], discriminantes, equivalencia o None)
MUTANTES = [
    # ---------------------------------------------------------------- A1 (OP-21)
    ("MF04-01", "A1 sin la modalidad (a) baja conjunta",
     [_sin(COR, "        if any(e in efectos for e in datos.efectos_a_eliminar):  # (a) baja conjunta\n"
                "            modalidades.append(\"BAJA_CONJUNTA\")\n")],
     [H13 + "[cuota-a]", H13 + "[hd-a]"], None),
    ("MF04-02", "A1 sin la modalidad (b) baja aislada del vinculo",
     [_sin(COR, "        if any(v in vinculos and vinculos[v] not in datos.efectos_a_eliminar\n"
                "               for v in datos.entidades_a_eliminar):  # (b) baja aislada del vinculo\n"
                "            modalidades.append(\"BAJA_VINCULO\")\n")],
     [H13 + "[cuota-b]", H13 + "[hd-b]"], None),
    ("MF04-03", "A1 sin la modalidad (c) importe_delta",
     [_sin(COR, "        if any(e in efectos and \"importe_delta\" in c for e, c in datos.efectos_a_actualizar.items()):  # (c)\n"
                "            modalidades.append(\"IMPORTE_DELTA\")\n")],
     [H13 + "[cuota-c]", H13 + "[hd-c]"], None),
    ("MF04-04", "A1 sin la modalidad (d) tipo_efecto",
     [_sin(COR, "        if any(e in efectos and \"tipo_efecto\" in c for e, c in datos.efectos_a_actualizar.items()):  # (d)\n"
                "            modalidades.append(\"TIPO_EFECTO\")\n")],
     [H13 + "[cuota-d]", H13 + "[hd-d]"], None),
    ("MF04-05", "A1 que solo mira efectos de cuota (DEUDA -capital): Hd fuera",
     [(COR, "            if efecto_id is not None:\n                vinculos[vinculo_id] = efecto_id\n",
       "            if efecto_id is not None and _importe is not None and _importe < 0:\n"
       "                vinculos[vinculo_id] = efecto_id\n")],
     [H13 + "[hd-a]", H13 + "[hd-b]", H13 + "[hd-c]", H13 + "[hd-d]"], None),
    ("MF04-06", "A1 ampliada al vinculo FINANCIACION de nivel hecho",
     [(COR, "            if efecto_id is not None:\n                vinculos[vinculo_id] = efecto_id\n",
       "            if True:\n                vinculos[vinculo_id] = efecto_id\n")],
     [T14N + "test_o_h13_nh_vinculo_de_nivel_hecho_se_sigue_retirando"], None),
    # ---------------------------------------------------------------- A4 (H-B-01)
    ("MF04-07", "H-B-01: guarda INVERSION sin `efecto_id is not None`",
     [(COR, "            and (fila[\"efecto_id\"] is not None or fila[\"principal\"])\n",
       "            and (fila[\"principal\"])\n")],
     [HB01 + "[baja_conjunta]", HB01 + "[baja_aislada]"], None),
    ("MF04-08", "H-B-01: guarda INVERSION sin `principal`",
     [(COR, "            and (fila[\"efecto_id\"] is not None or fila[\"principal\"])\n",
       "            and (fila[\"efecto_id\"] is not None)\n")],
     [HB01 + "[principal_de_hecho]"], None),
    ("MF04-09", "H-B-01: guarda INVERSION eliminada",
     [(COR, "            entidad is not None\n            and entidad[\"tipo_entidad\"] == TIPO_ENTIDAD_INVERSION\n",
       "            False\n            and entidad[\"tipo_entidad\"] == TIPO_ENTIDAD_INVERSION\n")],
     [HB01 + "[baja_conjunta]", HB01 + "[baja_aislada]", HB01 + "[principal_de_hecho]"], None),
    # ---------------------------------------------------------------- D-07 (precedencia)
    ("MF04-10a", "A1 evaluada despues de la primera escritura (tras tocar_raiz)",
     [_sin(COR, GUARDA_A1),
      (COR, "            # F04-D046 R2 · A08-bis. Estado de naturalezas ANTES de mutar.\n",
       LLAMADA_A1 + "            # F04-D046 R2 · A08-bis. Estado de naturalezas ANTES de mutar.\n")],
     [PREC + "[cuota-b]", PREC + "[cuota-c]", PREC + "[cuota-d]", PREC + "[hd-b]", PREC + "[hd-c]",
      PREC + "[hd-d]"], None),
    ("MF04-10b", "A1 evaluada despues de 3b (vinculos de nivel efecto ya retirados)",
     [_sin(COR, GUARDA_A1),
      (COR, "            vinculos_de_efecto = self._eliminar_vinculos_de_efecto(sesion, datos)\n",
       "            vinculos_de_efecto = self._eliminar_vinculos_de_efecto(sesion, datos)\n" + LLAMADA_A1)],
     [H13 + "[cuota-a]", H13 + "[hd-a]"], None),
    # ---------------------------------------------------------------- A9 (OP-03 / OP-03P)
    ("MF04-11", "A9 eliminada en OP-03 (anular_hecho)", [_sin(HEC, A9_OP03)],
     [T14N + "test_o_a9_03_op03_rechaza_sin_conciliacion[cuota]",
      T14N + "test_o_a9_03_op03_rechaza_sin_conciliacion[hd]"], None),
    ("MF04-12", "A9 eliminada en OP-03P (_elegibilidad)", [_sin(ANT, A9_OP03P)],
     [T14N + "test_o_a9_03p_op03p_rechaza_con_conciliacion[cuota]",
      T14N + "test_o_a9_03p_op03p_rechaza_con_conciliacion[hd]"], None),
    ("MF04-13", "A9 que solo mira cuotas (Hd fuera)",
     [(HEC, A9_SI, A9_SI.replace("if efecto_id is not None:",
                                 "if efecto_id is not None and importe is not None and importe < 0:"))],
     [T14N + "test_o_a9_03_op03_rechaza_sin_conciliacion[hd]",
      T14N + "test_o_a9_03p_op03p_rechaza_con_conciliacion[hd]"], None),
    ("MF04-14", "A9 de OP-03P evaluada despues de W1 (primera escritura)",
     [_sin(ANT, A9_OP03P),
      (ANT, "            for conciliacion_id, _ in sorted(previo[\"conciliaciones\"], key=lambda c: str(c[0])):  # W2\n",
       "            exigir_anulacion_sin_financiacion(sesion, hecho_id)\n"
       "            for conciliacion_id, _ in sorted(previo[\"conciliaciones\"], key=lambda c: str(c[0])):  # W2\n")],
     [T14N + "test_o_prec_03p_la_guarda_precede_a_version_desfasada"], None),
    ("MF04-15", "A9 ampliada al vinculo FINANCIACION de nivel hecho",
     [(HEC, A9_SI, A9_SI.replace("if efecto_id is not None:", "if True:"))],
     [T14N + "test_o_a9_nh_op03_y_op03p_anulan_como_hoy[financiacion_nivel_hecho]"], None),
    # ---------------------------------------------------------------- F05 writers
    ("MF05-S1", "S1 reparto sin guarda",
     [_sin(REP, "        if gf.es_hecho_de_financiacion(sesion, hecho_id):\n"
                "            return RechazoRegistro(REPARTO_NO_CORREGIBLE, {\"motivo\": gf.HECHO_DE_FINANCIACION})\n")],
     [T285 + "test_o_h22_s1_reparto_rechaza_y_la_lectura_es_veraz[cuota]",
      T285 + "test_o_h22_s1_reparto_rechaza_y_la_lectura_es_veraz[hd]"], None),
    ("MF05-S2", "S2 devolucion sin guarda",
     [_sin(DEV, "        rechazo = gf.rechazo_hecho(sesion, origen_id)  # F04-R-HIP S2: antes de cualquier lock\n"
                "        if rechazo is not None:\n            return RechazoRegistro(rechazo)\n")],
     [T285 + "test_o_h22_s2_devolucion_rechaza_y_la_lectura_es_veraz[cuota]",
      T285 + "test_o_h22_s2_devolucion_rechaza_y_la_lectura_es_veraz[hd]"], None),
    ("MF05-S2b", "S2 abono sin guarda",
     [_sin(DEV, "        if origen is not None and gf.es_hecho_de_financiacion(sesion, origen[0]):\n"
                "            return RechazoRegistro(gf.HECHO_DE_FINANCIACION)\n")],
     [T285 + "test_o_h22_s2_abono_de_una_devolucion_de_cuota"], None),
    ("MF05-S3", "S3 anular por duplicado sin guarda de frontera (A9 de motor la enmascararia por codigo)",
     [_sin(ANU, "        rechazo = gf.rechazo_hecho(sesion, hecho_id)  # F04-R-HIP S3: frontera, antes del motor (A9 aparte)\n"
                "        if rechazo is not None:\n            return RechazoRegistro(rechazo)\n")],
     [T285 + "test_o_h22_s3_anular_duplicado_rechaza_en_la_frontera[cuota]",
      T285 + "test_o_h22_s3_anular_duplicado_rechaza_en_la_frontera[hd]"], None),
    ("MF05-S4a", "S4 corregir pago sin guarda",
     [(CRR, "        rechazo = gf.rechazo_hecho(sesion, datos.hecho_id)  # F04-R-HIP S4: antes de cualquier lock\n"
            "        if rechazo is not None:\n            return RechazoRegistro(rechazo)\n"
            "        _capacidad_bajo_lock(sesion, plan_cuentas_pago(sesion, datos))\n",
       "        _capacidad_bajo_lock(sesion, plan_cuentas_pago(sesion, datos))\n")],
     [T285 + "test_o_h22_s4_corregir_pago_y_transferencia_rechazan[cuota]",
      T285 + "test_o_h22_s4_corregir_pago_y_transferencia_rechazan[hd]"], None),
    ("MF05-S4b", "S4 corregir transferencia sin guarda",
     [(CRR, "        rechazo = gf.rechazo_hecho(sesion, datos.hecho_id)  # F04-R-HIP S4: antes de cualquier lock\n"
            "        if rechazo is not None:\n            return RechazoRegistro(rechazo)\n"
            "        _capacidad_bajo_lock(sesion, plan_cuentas_transferencia(sesion, datos))\n",
       "        _capacidad_bajo_lock(sesion, plan_cuentas_transferencia(sesion, datos))\n")],
     [T285 + "test_o_h22_s4_corregir_pago_y_transferencia_rechazan[cuota]",
      T285 + "test_o_h22_s4_corregir_pago_y_transferencia_rechazan[hd]"], None),
    ("MF05-S5", "S5 corregir categoria sin guarda",
     [_sin(CV3, "        if gf.es_hecho_de_financiacion(sesion, hecho_id):  # F04-R-HIP S5: antes de OP-21\n"
                "            return RechazoRegistro(gf.HECHO_DE_FINANCIACION)\n")],
     [T285 + "test_o_h22_s5_corregir_categoria_rechaza[cuota]", T285 + "test_o_h22_s5_corregir_categoria_rechaza[hd]",
      T285 + "test_o_h22_s5_corregir_categoria_rechaza[v3]"], None),
    ("MF05-S6", "S6: SuplementosService construido fuera de compuesto_service",
     [(DEV, "# ------------------------------------------------------------------ abono posterior\n",
       "def _suplemento(unidad):  # mutante MF05-S6\n"
       "    from app.services.suplementos_service import SuplementosService\n"
       "    return SuplementosService(unidad)\n\n\n"
       "# ------------------------------------------------------------------ abono posterior\n")],
     [T286 + "test_s6_suplementos_sin_ruta_propia"], None),
    ("MF05-S7a", "S7 vincular sin guarda (prevision de cuota y hecho de financiacion)",
     [(PRV, "        rechazo = gf.rechazo_prevision(sesion, prevision_id) or gf.rechazo_hecho(sesion, intencion.hecho_id)\n",
       "        rechazo = None\n")],
     [T285 + "test_o_h22_s7_acciones_sobre_la_prevision_de_una_cuota[vincular]",
      T285 + "test_o_h22_s7_vincular_un_hecho_de_financiacion_a_otra_prevision"], None),
    ("MF05-S7b", "S7 vincular sin la guarda de hecho (solo la de prevision)",
     [(PRV, "        rechazo = gf.rechazo_prevision(sesion, prevision_id) or gf.rechazo_hecho(sesion, intencion.hecho_id)\n",
       "        rechazo = gf.rechazo_prevision(sesion, prevision_id)\n")],
     [T285 + "test_o_h22_s7_vincular_un_hecho_de_financiacion_a_otra_prevision"], None),
    ("MF05-S7c", "S7 omitir sin guarda",
     [(PRV, "        # F04-R-HIP S7: devuelve un RechazoRegistro (PREVISION_DE_CUOTA) antes del motor.\n"
            "        rechazo = gf.rechazo_prevision(sesion, prevision_id)\n",
       "        rechazo = None\n")],
     [T285 + "test_o_h22_s7_acciones_sobre_la_prevision_de_una_cuota[omitir]"], None),
    ("MF05-S7d", "S7 dar por cubierta sin guarda",
     [(PRV, "        rechazo = gf.rechazo_prevision(sesion, prevision_id)  # F04-R-HIP S7\n"
            "        if rechazo is not None:\n            return RechazoRegistro(rechazo)\n"
            "        r = _previsiones(sesion).dar_por_realizada(",
       "        r = _previsiones(sesion).dar_por_realizada(")],
     [T285 + "test_o_h22_s7_acciones_sobre_la_prevision_de_una_cuota[dar_por_cubierta]"], None),
    ("MF05-S7e", "S7 reabrir sin guarda (O-H35)",
     [(PRV, "        rechazo = gf.rechazo_prevision(sesion, prevision_id)  # F04-R-HIP S7\n"
            "        if rechazo is not None:\n            return RechazoRegistro(rechazo)\n"
            "        # F05-D047: una CANCELADA",
       "        # F05-D047: una CANCELADA")],
     [T285 + "test_o_h22_s7_acciones_sobre_la_prevision_de_una_cuota[reabrir]"], None),
    # ---------------------------------------------------------------- S10
    ("MF05-S10-GP", "S10 sin guarda en gasto-pagado",
     [_sin(GP, _guarda_s10("RechazoIntegracion", "intencion.prevision"))],
     [S10 + "[GP-T]", S10 + "[GP-F]", T287 + "test_c1_07_s10_no_espera_a_la_prevision_retenida"], None),
    ("MF05-S10-GC", "S10 sin guarda en gasto-compartido",
     [_sin(REP, _guarda_s10("RechazoRegistro", "intencion.prevision"))],
     [S10 + "[GC-T]", S10 + "[GC-F]", T287 + "test_c1_08_s10_gc_frente_a_s7_dar_por_cubierta"], None),
    ("MF05-S10-IC", "S10 sin guarda en ingreso-cobrado (discrimina por codigo)",
     [_sin(REG, _guarda_s10("RechazoRegistro", "intencion.prevision"))],
     [S10 + "[IC-T]", S10 + "[IC-F]"], None),
    ("MF05-S10-TR", "S10 sin guarda en transferencia (discrimina por codigo)",
     [_sin(PRV, _guarda_s10("RechazoRegistro", "bloque"))],
     [S10 + "[TR-T]", S10 + "[TR-F]"], None),
    # ---------------------------------------------------------------- MF05-L (lecturas)
    ("MF05-L-reparto", "lectura del reparto vuelve a decir corregible",
     [(REP, "    if gf.es_hecho_de_financiacion(sesion, hecho_id):  # F04-R-HIP S1\n", "    if False:\n")],
     [T285 + "test_o_h22_s1_reparto_rechaza_y_la_lectura_es_veraz[cuota]"], None),
    ("MF05-L-devolucion", "lectura de devoluciones vuelve a decir disponible",
     [(DEV, "    if gf.es_hecho_de_financiacion(sesion, origen_id):  # F04-R-HIP S2\n", "    if False:\n")],
     [T285 + "test_o_h22_s2_devolucion_rechaza_y_la_lectura_es_veraz[cuota]"], None),
    ("MF05-L-anulacion", "lectura de anulacion sin el motivo de financiacion",
     [_sin(REP, "    if gf.es_hecho_de_financiacion(sesion, hecho_id):  # F04-R-HIP S3 (lectura)\n"
                "        motivos.append(gf.HECHO_DE_FINANCIACION)\n")],
     [T285 + "test_o_h22_s3_anular_duplicado_rechaza_en_la_frontera[cuota]"], None),
    ("MF05-L-edicion", "lectura de edicion sin el motivo de financiacion",
     [_sin(EDI, "    if gf.es_hecho_de_financiacion(sesion, hecho_id):  # F04-R-HIP S3/S4\n"
                "        return gf.HECHO_DE_FINANCIACION\n")],
     [T285 + "test_o_h22_s4_corregir_pago_y_transferencia_rechazan[cuota]"], None),
    ("MF05-L-categoria", "lectura de «Corregir categoria» V3 sin el motivo de financiacion",
     [_sin(EDI, "    if gf.es_hecho_de_financiacion(sesion, hecho_id):  # F04-R-HIP S5 (V3 con vinculo de nivel efecto)\n"
                "        return gf.HECHO_DE_FINANCIACION, None\n")],
     [T285 + "test_o_h22_s5_corregir_categoria_rechaza[v3]"], None),
    ("MF05-L-prevision", "detalle de la prevision de una cuota vuelve a ofrecer registrar/ya_lo_registre/swipe",
     [(LEC, "acciones(fila, derivado, de_cuota=es_prevision_de_cuota(sesion, prevision_id))",
       "acciones(fila, derivado, de_cuota=False)")],
     [T285 + "test_o_h22_s7_s10_l_lectura_de_la_prevision_de_una_cuota[ABIERTA]",
      T285 + "test_o_h22_s7_s10_l_lectura_de_la_prevision_de_una_cuota[REALIZADA]"], None),
    ("MF05-L-candidatos", "un hecho de financiacion vuelve a ser candidato",
     [_sin(LEC, "    \"AND NOT EXISTS (SELECT 1 FROM gapto.hecho_entidades fv JOIN gapto.entidades fn ON fn.id = fv.entidad_id \"\n"
                "    \"                WHERE fv.hecho_id = h.id AND fv.efecto_id IS NOT NULL AND fn.tipo_entidad = 'FINANCIACION') \"\n")],
     [T285 + "test_o_h22_s7_un_hecho_de_financiacion_no_es_candidato"], None),
    ("MF05-L-candidatos-cuota", "la prevision de una cuota vuelve a proponer candidatos",
     [(LEC, "    if es_prevision_de_cuota(sesion, prevision_id):  # F04-R-HIP S7\n", "    if False:\n")],
     [T285 + "test_o_h22_s7_candidatos_de_una_prevision_de_cuota_con_criterio",
      T285 + "test_o_h22_s7_s10_l_lectura_de_la_prevision_de_una_cuota[ABIERTA]"], None),
    # ---------------------------------------------------------------- MF05-INV
    ("MF05-INV-S10", "inventario sin la superficie S10",
     [(INV, "    \"S10\": [(\"api/ejecucion_gasto_pagado.py\"", "    \"S10_FUERA\": [(\"api/ejecucion_gasto_pagado.py\""),
      (INV, "S10_RUTAS = {", "S10_RUTAS_OLVIDADAS = {"),
      (INV, "    objetivo = {r for r in rutas if _sobre_existente(r)} | (S10_RUTAS & rutas)\n",
       "    S10_RUTAS = S10_RUTAS_OLVIDADAS\n    objetivo = {r for r in rutas if _sobre_existente(r)} | (S10_RUTAS & rutas)\n"),
      (INV, "    inventariadas = {ruta for filas in INVENTARIO.values() for _, _, ruta in filas}\n",
       "    inventariadas = {ruta for k, filas in INVENTARIO.items() if k != \"S10_FUERA\" for _, _, ruta in filas}\n")],
     [T286 + "test_inventario_completo_de_writers_f05_sobre_hechos_y_previsiones"], None),
    ("MF05-INV-S1", "inventario sin la superficie S1",
     [(INV, "    \"S1\": [(\"api/ejecucion_reparto.py\", \"corregir_reparto\", \"/v1/hechos/{hecho_id}/reparto\")],\n", "")],
     [T286 + "test_inventario_completo_de_writers_f05_sobre_hechos_y_previsiones"], None),
    ("MF05-INV-ORD-GP", "guarda S10 de gasto-pagado DESPUES del advisory por raiz",
     [_sin(GP, _guarda_s10("RechazoIntegracion", "intencion.prevision")),
      (GP, "        con_propiedad = intencion.propiedad is not None\n",
       _guarda_s10("RechazoIntegracion", "intencion.prevision") + "        con_propiedad = intencion.propiedad is not None\n")],
     [T286 + "test_la_guarda_precede_al_primer_lock[S10-registrar_gasto_pagado]"], None),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    rc = 0
    for grupo, extra in (("tests/backend/", []), ("tests/api/", ["--rootdir=tests/api"])):
        ids = [t for t in tests if t.startswith(grupo)]
        if ids:
            cmd = [sys.executable, "-m", "pytest", *ids, "-q", "-x", "-p", "no:cacheprovider", *extra]
            rc = rc or subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode
    return rc


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


def anotar(salida: pathlib.Path | None, linea: str) -> None:
    print(linea, flush=True)
    if salida is not None:
        with salida.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if os.getenv("GAPTO_F04RHIP_CONCURRENCIA") != "1":
        sys.exit("Falta GAPTO_F04RHIP_CONCURRENCIA=1: los discriminantes seriales se omitirian.")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    elegidos = [mu for mu in MUTANTES if solo is None or mu[0] in solo]
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    anotar(salida, f"PREFLIGHT VERDE {len(preflight)} discriminantes; {len(elegidos)} mutantes")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia in elegidos:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, texto, sustituto in cambios:
            if textos[f].count(texto) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(texto, sustituto)
        if not aplicable:
            v = (mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc)
            veredictos.append(v)
            anotar(salida, " | ".join(v))
            continue
        JOURNAL.write_text(json.dumps({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
        ]}), encoding="utf-8")
        resultado = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            resultado = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if resultado == "VIVO" and equivalencia:
            resultado = "EQUIVALENTE"
        v = (mid, resultado if ok else "NO_CLASIFICABLE",
             ",".join(sorted({pathlib.Path(t.split("::")[0]).name for t in tests})), desc)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}")
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
