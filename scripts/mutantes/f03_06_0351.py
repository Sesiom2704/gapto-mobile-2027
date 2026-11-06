#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f03_06_0351.py
# Ruta: scripts/mutantes/f03_06_0351.py
# Descripcion: Mutation gate de F06-01 B0 / 0351 (F06-D002; dictamen B0
#   implementacion PB0I-09, AJ-B0I-10; WM 12C.2, D-181, D-192). Catalogo
#   CERRADO en tres grupos, cada mutante con transformacion de texto exacto y
#   discriminante declarado:
#     HEREDADOS  H1..H8: los M1..M8 de f03_06_0350.py portados a la cadena
#                0351 (su supuesto de head fijo -- plantilla 0340 + 0350 y
#                test_017 con el SHA de 2467267 -- impide ejecutarlo sobre
#                0351: aborta por SHA). La variante de 0350 se aplica sobre
#                una plantilla en 0340 y despues 0351 con sus bloques de
#                precheck y postcheck retirados (si no, 0351 abortaria antes
#                de que los tests vieran la mutacion); discriminan test_045 y
#                test_017 del head 0351.
#     NUEVOS_V02 S1..S8, P1..P6: los catorce de B0 v0.2 (CHECK de 0351,
#                REVOKE, writer de causa, OP-21 por UPDATE, P5 D10-K).
#     NUEVOS_V03 B1a..B1c (guarda de conversion logica de OP-21, PB0I-06),
#                R1 (P5b con head explicito, PB0I-03) y Q1..Q3 (precheck
#                estructural y de datos de 0351, que en v0.2 no tenian
#                mutante).
#     NUEVOS_N1  Q2t, Q3t: las mismas mutaciones de Q2 y Q3, discriminadas
#                ahora por los tests permanentes de test_046 (N1-E; dictamen
#                de reconsulta RB0-10). Los escenarios Q2/Q3 se conservan.
#                B1a y B1b anaden como discriminantes los tests W8 de
#                precedencia (RB0-06).
#
#   MODELO (el de f03_06_0350.py). Cada variante parte de los bytes
#   aprobados (SHA-256 fijados abajo); cada sustitucion debe aparecer
#   EXACTAMENTE una vez o el mutante es INVALIDO. Las variantes de SQL que
#   miden a los TESTS retiran el bloque de postcheck (control incluido) y
#   registran aparte si la migration COMPLETA mutada habria abortado
#   ("autocomprobacion", informativa). Los mutantes de escenario (Q2, Q3) no
#   tienen test pytest propio (en N1 los cubren Q2t/Q3t): su discriminante es un escenario de datos declarado
#   (0350 con VALOR_ACTIVO previo, o con residuo de repercusion) cuya
#   aplicacion COMPLETA debe abortar con el mensaje de su guarda; si aborta
#   por otra defensa (el CHECK al validar), el discriminante de la guarda
#   FALLA y el mutante queda MUERTO, con la otra defensa registrada.
#
#   VEREDICTOS: MUERTO si falla al menos uno de sus discriminantes; VIVO si
#   no falla ninguno; INVALIDO si la sustitucion no es unica o la variante no
#   se aplica. Cada modo tiene su control sin mutacion, que debe quedar VERDE
#   y SIN saltos. PASS = controles verdes + todos MUERTOS. Un mutante que no
#   llego a ejecutarse NUNCA cuenta como detectado (PB0I-09).
#
#   GUARDAS D-181/D-192: E/S byte a byte; journal JSON durable (os.replace)
#   FUERA del repositorio ANTES de tocar el primer byte; al arrancar, journal
#   pendiente -> restaura, verifica SHA-256 y aborta (NO_PASS); tras cada
#   mutante restaura y verifica identidad. Bases desechables, recreadas antes
#   y eliminadas despues. No es evidencia de proveedor.
# Uso:
#   python scripts/mutantes/f03_06_0351.py --admin-dsn "host=127.0.0.1
#     port=5460 user=postgres dbname=postgres" --plantilla-0340 lab_ref0340
#     --plantilla-0350 lab_ref --diario /ruta/fuera [H1 S1 ...]
# Version: 0.4.0  -- F06-01 B0 N1 (LOTE9 C2): Q2t y Q3t (N1-E), W8 como
#                   discriminantes de B1a/B1b (RB0-06) y SHA aprobado de
#                   correcciones_service.py 0.16.0 (solo documentacion, N1-F).
# Version: 0.3.0  -- CANDIDATO B0 v0.3 (pendiente de dictamen y decision).
# ============================================================
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

RAIZ = pathlib.Path(__file__).resolve().parents[2]

M0350 = "migrations/0350_f03_06_tipo_hecho_condonacion.sql"
M0351 = "migrations/0351_f06_01_b0_base_patrimonial.sql"
T017F = "tests/database/test_017_seeds_sistema.py"
EFREPO = "backend/app/repositories/efectos_repository.py"
EFSERV = "backend/app/services/efectos_service.py"
MODEF = "backend/app/core/modelos_efectos.py"
CORR = "backend/app/services/correcciones_service.py"
P5F = "scripts/migration_v3/rv3_p5_transformacion.py"
P5BF = "scripts/migration_v3/rv3_p5b_rf04015.py"

#: Bytes aprobados del candidato v0.3. Si alguno cambia, el gate no corre.
APROBADOS = {
    M0350: "1615a4bd7eb3de8919a85e653e86e15c15088659fc589e77a00d288d003c2461",
    M0351: "e549c2b98ec0db3508e7e252795b13dc997b13f5af326c4b5ad5ad09de494cc6",
    T017F: "17b28c42f1b3520299634e04849ac6f81fdd53ae97703de29fbcc10e6a3f82c5",
    EFREPO: "f963b2c1b518bd44a7f07234f2ea48d1a16ca7f3693eb7b8baaa5dc59251c547",
    EFSERV: "62afe78ab2a054dfe2023731ff96fae50bcd4af378212d535f463c493e140b51",
    MODEF: "f6d4bbb69782b7638a4368f278cc5676f538336229ecae82cea1ee440cda9b26",
    CORR: "e02a328d3d82f5d6197e7cfcc7eec02a4f22894c4f7f05c2f481d36659e4f270",
    P5F: "f7c138796e156a244ab763bea7e4f95432b1d77f0dc916850fdcd5770a628181",
    P5BF: "cccda3c7ed4a0461ebc3fa1927eaefe44715ac15d01e9c215f57f7000d46b7f9",
}

T45 = "test_045_f03_06_0350_tipo_hecho_condonacion"
T17 = "test_017_seeds_sistema"
T46 = "test_046_f06_01_0351_base_patrimonial"
T14L = "test_14l_f06_01_b0_causa_valor_activo"
T104 = "test_104_op04_registrar_efectos"
TR36 = "test_rv3_036_p5_d10k_modo_reparto"
TR37 = "test_rv3_037_p5b_head_explicito"

FICHEROS_TEST = {
    T45: "tests/database/test_045_f03_06_0350_tipo_hecho_condonacion.py",
    T17: "tests/database/test_017_seeds_sistema.py",
    T46: "tests/database/test_046_f06_01_0351_base_patrimonial.py",
    T14L: "tests/backend/test_14l_f06_01_b0_causa_valor_activo.py",
    T104: "tests/backend/test_104_op04_registrar_efectos.py",
    TR36: "tests/migration/test_rv3_036_p5_d10k_modo_reparto.py",
    TR37: "tests/migration/test_rv3_037_p5b_head_explicito.py",
}

# ---- anclas de los heredados (las de f03_06_0350.py) ----
INSERT_0350 = "    ('0d216df5-59eb-56c8-998e-7d47953b9351', 'CONDONACION', 'Condonacion de derecho u obligacion', true);"
RESET = "\nRESET ROLE;\n"
ASERCION_017 = ('    assert found in TIPOS_HECHO_POR_HEAD.values(), '
                'f"tipos_hecho fuera de los estados autorizados: {sorted(found)}"')
BLOQUE = "<bloque>"  # marcador: el viejo texto es un bloque DO $etiqueta$ completo (se resuelve en ejecucion)


@dataclass(frozen=True)
class Mutante:
    ident: str
    grupo: str
    modo: str  # HEREDADO | SQL | SQL_POST | ESCENARIO | PY | RV3
    guarda: str
    cambios: tuple[tuple[str, str, str], ...]  # (fichero, viejo, nuevo); viejo puede ser BLOQUE:<etiqueta>
    discriminantes: tuple[str, ...]
    sql_post: str | None = None
    escenario: str | None = None


def _b(etiqueta: str) -> str:
    return f"{BLOQUE}:{etiqueta}"


CATALOGO: tuple[Mutante, ...] = (
    # ------------------------------------------------ HEREDADOS (M1..M8 de 0350)
    Mutante("H1", "HEREDADO", "HEREDADO", "0350 sin precheck", ((M0350, _b("precheck_0350"), ""),),
            (f"{T45}::test_0350_reaplicar_rechazado_por_precheck",
             f"{T45}::test_0350_precheck_rechaza_seed_distinto_de_0150")),
    Mutante("H2", "HEREDADO", "HEREDADO", "0350 UUID distinto",
            ((M0350, INSERT_0350, INSERT_0350.replace("9351'", "9352'")),),
            (f"{T45}::test_0350_fila_con_contrato_d201", f"{T17}::test_tipos_hecho_ids_are_deterministic_uuidv5")),
    Mutante("H3", "HEREDADO", "HEREDADO", "0350 codigo distinto",
            ((M0350, INSERT_0350, INSERT_0350.replace("'CONDONACION'", "'CONDONACIONES'")),),
            (f"{T45}::test_0350_fila_con_contrato_d201", f"{T17}::test_tipos_hecho_exactly_7_expected_codes")),
    Mutante("H4", "HEREDADO", "HEREDADO", "0350 enabled=false",
            ((M0350, INSERT_0350, INSERT_0350.replace("true);", "false);")),),
            (f"{T45}::test_0350_fila_con_contrato_d201", f"{T17}::test_tipos_hecho_all_enabled")),
    Mutante("H5", "HEREDADO", "HEREDADO", "0350 fila duplicada",
            ((M0350, INSERT_0350, INSERT_0350[:-1] + ",\n    ('9e2dd703-6e1f-50c4-bd03-67c7de92b6ae', "
              "'CONDONACION_OBLIGACION', 'Condonacion de obligacion', true);"),),
            (f"{T45}::test_0350_exactamente_ocho_tipos", f"{T17}::test_tipos_hecho_exactly_7_expected_codes")),
    Mutante("H6", "HEREDADO", "HEREDADO", "0350 DDL colado",
            ((M0350, RESET, "\nCREATE INDEX ix_mut_0350 ON gapto.tipos_hecho (nombre);" + RESET),),
            (f"{T45}::test_0350_estructura_sin_ddl",)),
    Mutante("H7", "HEREDADO", "HEREDADO", "test_017 sin parametrizar por head",
            ((T017F, ASERCION_017, "    assert found == TIPOS_HECHO_ESPERADOS"),),
            (f"{T17}::test_tipos_hecho_exactly_7_expected_codes",)),
    Mutante("H8", "HEREDADO", "HEREDADO", "0350 toca una fila ajena",
            ((M0350, RESET, "\nUPDATE gapto.tipos_hecho SET nombre = nombre WHERE codigo = 'GASTO';" + RESET),),
            (f"{T45}::test_0350_datos_preexistentes_intactos",)),
    # ------------------------------------------------ NUEVOS v0.2 (los catorce)
    Mutante("S1", "NUEVO_V02", "SQL", "CHECK causa_solo_valor_activo",
            ((M0351, "CHECK ((tipo_efecto = 'VALOR_ACTIVO') = (causa_valor_activo IS NOT NULL));",
              "CHECK (causa_valor_activo IS NULL OR tipo_efecto = 'VALOR_ACTIVO');"),),
            (f"{T46}::test_0351_causa_valor_activo",)),
    Mutante("S2", "NUEVO_V02", "SQL", "CHECK causa_valor_activo_dominio",
            ((M0351, "            'REDUCCION_ESTRUCTURAL'));", "            'REDUCCION_ESTRUCTURAL', 'TASACION'));"),),
            (f"{T46}::test_0351_causa_valor_activo",)),
    Mutante("S3", "NUEVO_V02", "SQL", "CHECK contratos__habitacion",
            ((M0351, "CHECK (habitacion IS NULL OR (habitacion >= 1 AND tipo_contrato = 'HABITACION'));",
              "CHECK (habitacion IS NULL OR (habitacion >= 0 AND tipo_contrato = 'HABITACION'));"),),
            (f"{T46}::test_0351_habitacion",)),
    Mutante("S4", "NUEVO_V02", "SQL", "CHECK modo_reparto_dominio",
            ((M0351, "CHECK (modo_reparto IS NULL OR modo_reparto IN ('FIJO', 'POR_FACTURA'));",
              "CHECK (modo_reparto IS NULL OR modo_reparto IN ('FIJO', 'POR_FACTURA', 'VARIABLE'));"),),
            (f"{T46}::test_0351_modo_reparto",)),
    Mutante("S5", "NUEVO_V02", "SQL", "CHECK repercusion_coherente: POR_FACTURA prohibe porcentaje",
            ((M0351, "OR (modo_reparto = 'POR_FACTURA' AND porcentaje_repercutible IS NULL)))",
              "OR (modo_reparto = 'POR_FACTURA')))"),),
            (f"{T46}::test_0351_modo_reparto",)),
    Mutante("S6", "NUEVO_V02", "SQL", "CHECK repercusion_coherente: no repercutible sin residuos",
            ((M0351, "            AND modo_reparto IS NULL\n            AND actor_repercusion_id IS NULL\n"
                     "            AND porcentaje_repercutible IS NULL)", "            AND modo_reparto IS NULL)"),),
            (f"{T46}::test_0351_modo_reparto",)),
    Mutante("S7", "NUEVO_V02", "SQL", "REVOKE DELETE (sin el de entidad_relaciones)",
            ((M0351, "REVOKE DELETE ON gapto.entidad_relaciones      FROM gapto_runtime;\n", ""),),
            (f"{T46}::test_0351_delete_denegado_a_runtime", f"{T46}::test_0351_acl_completo_de_las_siete")),
    Mutante("S8", "NUEVO_V02", "SQL_POST", "REVOKE DELETE, defensa 2 (GRANT tras 0351 correcta)", (),
            (f"{T46}::test_0351_delete_denegado_a_runtime", f"{T46}::test_0351_acl_completo_de_las_siete"),
            sql_post="SET ROLE gapto_owner; GRANT DELETE ON gapto.entidad_relaciones TO gapto_runtime; RESET ROLE;"),
    Mutante("P1", "NUEVO_V02", "PY", "writer: guarda de causa en el INSERT",
            ((EFREPO, "    exigir_causa_valor_activo(tipo_efecto, causa_valor_activo)\n", ""),),
            (f"{T14L}::test_w3_op21_alta_valor_activo_sin_acontecimiento",
             f"{T14L}::test_w3_op21_alta_gasto_con_acontecimiento")),
    Mutante("P2", "NUEVO_V02", "PY", "writer: OP-04 persiste la causa declarada",
            ((EFSERV, "                    causa_valor_activo=efecto.causa_valor_activo,\n",
              "                    causa_valor_activo=None,\n"),),
            (f"{T14L}::test_w1_op04_persiste_la_causa", f"{T104}::")),
    Mutante("P3", "NUEVO_V02", "PY", "writer: causa prohibida fuera de VALOR_ACTIVO",
            ((MODEF, "    elif causa is not None:\n", "    elif False:\n"),),
            (f"{T14L}::test_w3_guarda_rechaza",)),
    Mutante("P4", "NUEVO_V02", "PY", "OP-21: rechazo por UPDATE desde VALOR_ACTIVO",
            ((CORR, "            self._exigir_sin_conversion_desde_valor_activo(sesion, datos)\n", ""),),
            (f"{T14L}::test_w4_op21_desde_valor_activo",)),
    Mutante("P5", "NUEVO_V02", "PY", "OP-21: rechazo por UPDATE hacia VALOR_ACTIVO",
            ((CORR, "            if cambios.get(\"tipo_efecto\") == TIPO_VALOR_ACTIVO:\n", "            if False:\n"),),
            (f"{T14L}::test_w4_op21_hacia_valor_activo",)),
    Mutante("P6", "NUEVO_V02", "RV3", "P5 D10-K: modo_reparto FIJO",
            ((P5F, "                                          \"modo_reparto\": \"FIJO\",  # F06-D002 (0351)\n", ""),),
            (f"{TR36}::",)),
    # ------------------------------------------------ NUEVOS v0.3
    Mutante("B1a", "NUEVO_V03", "PY", "OP-21 conversion logica: la guarda no mira las retiradas",
            ((CORR, "        retirados = repo_corr.naturaleza_de_efectos(\n"
                    "            sesion, datos.hecho_id, list(datos.efectos_a_eliminar)\n        )\n",
              "        retirados = []\n"),),
            (f"{T14L}::test_w7a_retira_valor_activo_y_crea_otro_tipo",
             f"{T14L}::test_w7b_retira_otro_tipo_y_crea_valor_activo",
             f"{T14L}::test_w7c_retira_y_crea_valor_activo_con_otra_causa",
             f"{T14L}::test_w8_conversion_logica_precede_a_causa_requerida",
             f"{T14L}::test_w8_conversion_logica_precede_a_causa_no_admitida",
             f"{T14L}::test_w8_reemplazo_valor_activo_sin_causa_es_conversion")),
    Mutante("B1b", "NUEVO_V03", "PY", "OP-21 conversion logica: la guarda no se invoca",
            ((CORR, "            self._exigir_sin_conversion_logica_valor_activo(sesion, datos)\n", ""),),
            (f"{T14L}::test_w7a_retira_valor_activo_y_crea_otro_tipo",
             f"{T14L}::test_w7b_retira_otro_tipo_y_crea_valor_activo",
             f"{T14L}::test_w8_conversion_logica_precede_a_causa_requerida",
             f"{T14L}::test_w8_conversion_logica_precede_a_causa_no_admitida",
             f"{T14L}::test_w8_reemplazo_valor_activo_sin_causa_es_conversion")),
    Mutante("B1c", "NUEVO_V03", "PY", "OP-21 conversion logica: sin el caso (c) cambio de causa",
            ((CORR, "            or (retira_va and crea_va and causas_creadas != causas_retiradas)\n", ""),),
            (f"{T14L}::test_w7c_retira_y_crea_valor_activo_con_otra_causa",)),
    Mutante("R1", "NUEVO_V03", "RV3", "P5b: auditar ignora el head declarado",
            ((P5BF, "    sin_delete = RUNTIME_SIN_DELETE_POR_HEAD[head]\n",
              "    sin_delete = RUNTIME_SIN_DELETE_POR_HEAD[\"0330\"]\n"),),
            (f"{TR37}::test_head_0351_aplica_sus_mapas",)),
    Mutante("Q1", "NUEVO_V03", "SQL", "0351 precheck: sin el rechazo de reaplicacion",
            ((M0351, "    IF v_n <> 0 THEN\n        RAISE EXCEPTION 'F06-01-0351 PRECHECK: 0351 ya esta aplicada",
              "    IF false THEN\n        RAISE EXCEPTION 'F06-01-0351 PRECHECK: 0351 ya esta aplicada"),),
            (f"{T46}::test_0351_reaplicar_rechazado_por_precheck",)),
    Mutante("Q2", "NUEVO_V03", "ESCENARIO", "0351 precheck de datos: sin el recuento de VALOR_ACTIVO previo",
            ((M0351, "      FROM gapto.hecho_efectos e WHERE e.tipo_efecto = 'VALOR_ACTIVO';\n    IF v_n <> 0 THEN",
              "      FROM gapto.hecho_efectos e WHERE e.tipo_efecto = 'VALOR_ACTIVO';\n    IF false THEN"),),
            ("escenario::valor_activo_previo",), escenario="valor_activo"),
    Mutante("Q3", "NUEVO_V03", "ESCENARIO", "0351 precheck de datos: sin el recuento de residuos de repercusion",
            ((M0351, "       AND (s.actor_repercusion_id IS NOT NULL OR s.porcentaje_repercutible IS NOT NULL);\n"
                     "    IF v_n <> 0 THEN",
              "       AND (s.actor_repercusion_id IS NOT NULL OR s.porcentaje_repercutible IS NOT NULL);\n"
              "    IF false THEN"),),
            ("escenario::residuo_repercusion",), escenario="residuo"),
    # ------------------------------------------------ NUEVOS_N1 (N1-E: Q2/Q3 con test permanente)
    Mutante("Q2t", "NUEVO_N1", "SQL", "0351 precheck de datos: sin el recuento de VALOR_ACTIVO previo (test)",
            ((M0351, "      FROM gapto.hecho_efectos e WHERE e.tipo_efecto = 'VALOR_ACTIVO';\n    IF v_n <> 0 THEN",
              "      FROM gapto.hecho_efectos e WHERE e.tipo_efecto = 'VALOR_ACTIVO';\n    IF false THEN"),),
            (f"{T46}::test_0351_precheck_datos_valor_activo_previo",)),
    Mutante("Q3t", "NUEVO_N1", "SQL", "0351 precheck de datos: sin el recuento de residuos de repercusion (test)",
            ((M0351, "       AND (s.actor_repercusion_id IS NOT NULL OR s.porcentaje_repercutible IS NOT NULL);\n"
                     "    IF v_n <> 0 THEN",
              "       AND (s.actor_repercusion_id IS NOT NULL OR s.porcentaje_repercutible IS NOT NULL);\n"
              "    IF false THEN"),),
            (f"{T46}::test_0351_precheck_datos_residuo_repercusion",)),
)

#: Tests que corre cada modo (los discriminantes salen de aqui).
TESTS_POR_MODO = {
    "HEREDADO": (T45, T17),
    "SQL": (T46,),
    "SQL_POST": (T46,),
    "PY": (T14L, T104),
    "RV3": (TR36, TR37),
}
#: Mensaje de la guarda que cada escenario debe ver al aplicar 0351 COMPLETA.
ESCENARIOS = {
    "valor_activo": "PRECHECK DATOS: no se aplica, nada se limpia ni se rellena: 1 efectos VALOR_ACTIVO preexistentes",
    "residuo": "PRECHECK DATOS: no se aplica, nada se limpia ni se rellena: 1 servicios no repercutibles con actor",
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def bloque(sql: str, etiqueta: str) -> str:
    patron = re.compile(r"DO \$" + etiqueta + r"\$.*?\$" + etiqueta + r"\$;?(?: LANGUAGE plpgsql;)?\n", re.S)
    hallados = patron.findall(sql)
    if len(hallados) != 1:
        raise SystemExit(f"bloque ${etiqueta}$ no encontrado exactamente una vez")
    return hallados[0]


def aplicar_cambios(textos: dict[str, str], cambios) -> dict[str, str]:
    nuevos = dict(textos)
    for fichero, viejo, nuevo in cambios:
        if viejo.startswith(BLOQUE + ":"):
            viejo = bloque(nuevos[fichero], viejo.split(":", 1)[1])
        n = nuevos[fichero].count(viejo)
        if n != 1:
            raise ValueError(f"{fichero}: patron presente {n} veces")
        nuevos[fichero] = nuevos[fichero].replace(viejo, nuevo)
    return nuevos


def dsn_base(admin_dsn: str, base: str) -> str:
    partes = conninfo_to_dict(admin_dsn)
    partes["dbname"] = base
    return make_conninfo(**partes)


def recrear(admin_dsn: str, base: str, plantilla: str | None) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {base} WITH (FORCE)")
        if plantilla:
            c.execute(f"CREATE DATABASE {base} TEMPLATE {plantilla}")


def ejecutar_sql(admin_dsn: str, base: str, *sqls: str) -> str | None:
    try:
        with psycopg.connect(dsn_base(admin_dsn, base), autocommit=True) as c:
            for s in sqls:
                c.execute(s)
        return None
    except psycopg.Error as e:
        return str(e).splitlines()[0]


def sembrar(admin_dsn: str, base: str, caso: str) -> None:
    """Datos sinteticos (estado 0350) del escenario, como el admin del laboratorio."""
    import uuid

    owner, actor = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(dsn_base(admin_dsn, base)) as c:
        c.execute("INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, 'mut0351')",
                  (owner, f"{owner}@example.invalid"))
        c.execute("INSERT INTO gapto.actores_financieros (id, owner_user_id) VALUES (%s, %s)", (actor, owner))
        if caso == "valor_activo":
            th = c.execute("SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'").fetchone()[0]
            h = uuid.uuid4()
            c.execute("INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, moneda, "
                      "presupuestable, estado_localizacion, importe_total, concepto) VALUES "
                      "(%s, %s, %s, current_date, 'EUR', false, 'NO_APLICA', 100, 'mut0351')", (h, owner, th))
            c.execute("INSERT INTO gapto.hecho_efectos (hecho_id, tipo_efecto, importe_delta, estado_atribucion) "
                      "VALUES (%s, 'VALOR_ACTIVO', 100, 'NO_DISPONIBLE')", (h,))
        else:
            ids = {k: uuid.uuid4() for k in ("prop", "serv", "con")}
            for k, tipo in (("prop", "PROPIEDAD"), ("serv", "SERVICIO"), ("con", "CONTRATO")):
                c.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                          "VALUES (%s, %s, %s, 'mut0351')", (ids[k], owner, tipo))
            c.execute("INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) VALUES (%s, 'VIVIENDA')", (ids["prop"],))
            c.execute("INSERT INTO gapto.servicios (entidad_id, tipo_servicio) VALUES (%s, 'SUMINISTRO')", (ids["serv"],))
            c.execute("INSERT INTO gapto.contratos (entidad_id, propiedad_entidad_id, tipo_contrato) "
                      "VALUES (%s, %s, 'HABITACION')", (ids["con"], ids["prop"]))
            c.execute("INSERT INTO gapto.contrato_servicios (contrato_entidad_id, servicio_entidad_id, repercutible, "
                      "actor_repercusion_id, vigente_desde) VALUES (%s, %s, false, %s, current_date)",
                      (ids["con"], ids["serv"], actor))
        c.commit()


def correr_tests(modulos: tuple[str, ...], entorno_extra: dict[str, str]) -> dict:
    rutas = [FICHEROS_TEST[m] for m in modulos]
    extra = ["--rootdir=tests/backend"] if any(r.startswith("tests/backend") for r in rutas) else []
    with tempfile.TemporaryDirectory() as d:
        junit = pathlib.Path(d) / "j.xml"
        entorno = dict(os.environ, **entorno_extra)
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *rutas, *extra,
                        f"--junitxml={junit}"], cwd=RAIZ, env=entorno,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        res: dict[str, list[str]] = {"pass": [], "fail": [], "skip": []}
        if not junit.exists():
            return res
        for t in ET.parse(junit).getroot().iter("testcase"):
            modulo = t.get("classname", "").split(".")[-1]
            if modulo not in modulos:
                continue
            estado = ("fail" if t.find("failure") is not None or t.find("error") is not None
                      else "skip" if t.find("skipped") is not None else "pass")
            res[estado].append(f"{modulo}::{t.get('name')}")
        return {k: sorted(v) for k, v in res.items()}


def caidos(discriminantes: tuple[str, ...], fallos: list[str]) -> list[str]:
    """Un discriminante `mod::test` cubre sus parametrizaciones; `mod::` cubre todo el modulo."""
    salida = []
    for f in fallos:
        for d in discriminantes:
            if d.endswith("::") and f.startswith(d) or f == d or f.startswith(d + "["):
                salida.append(f)
                break
    return sorted(set(salida))


def escribir_atomico(ruta: pathlib.Path, contenido: dict) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(contenido, indent=1, ensure_ascii=False).encode("utf-8"))
    os.replace(tmp, ruta)


def recuperar_si_pendiente(journal: pathlib.Path) -> bool:
    if not journal.exists():
        return False
    j = json.loads(journal.read_text(encoding="utf-8"))
    for f in j["ficheros"]:
        ruta = RAIZ / f["fichero"]
        ruta.write_bytes(bytes.fromhex(f["original_hex"]))
        if sha(ruta.read_bytes()) != f["sha256"]:
            raise SystemExit(f"RECUPERACION FALLIDA: identidad no verificada en {f['fichero']}")
    journal.unlink()
    return True


@dataclass
class Contexto:
    admin: str
    p0340: str
    p0350: str
    p0351: str
    diario: pathlib.Path
    journal: pathlib.Path
    brutos: dict[str, bytes] = field(default_factory=dict)
    textos: dict[str, str] = field(default_factory=dict)


def _sin(sql: str, *etiquetas: str) -> str:
    for e in etiquetas:
        sql = sql.replace(bloque(sql, e), "")
    return sql


def preparar_base(ctx: Contexto, m: Mutante, variantes: dict[str, str], bd: str) -> tuple[str | None, str, dict]:
    """Devuelve (error_de_aplicacion, autocomprobacion, entorno_de_tests)."""
    entorno = {"GAPTO_TEST_DATABASE_URL": dsn_base(ctx.admin, bd)}
    if m.modo == "HEREDADO":
        completa = (variantes[M0350], ctx.textos[M0351])
        recrear(ctx.admin, bd, ctx.p0340)
        auto = ejecutar_sql(ctx.admin, bd, *completa) or "no aborta"
        recrear(ctx.admin, bd, ctx.p0340)
        err = ejecutar_sql(ctx.admin, bd, _sin(variantes[M0350], "postcheck_0350"),
                           _sin(ctx.textos[M0351], "precheck_0351", "postcheck_0351"))
        return err, auto, entorno
    if m.modo == "SQL":
        recrear(ctx.admin, bd, ctx.p0350)
        auto = ejecutar_sql(ctx.admin, bd, variantes[M0351]) or "no aborta"
        recrear(ctx.admin, bd, ctx.p0350)
        err = ejecutar_sql(ctx.admin, bd, _sin(variantes[M0351], "postcheck_0351"))
        return err, auto, entorno
    if m.modo == "SQL_POST":
        recrear(ctx.admin, bd, ctx.p0351)
        err = ejecutar_sql(ctx.admin, bd, m.sql_post) if m.sql_post else None
        return err, "no aplica", entorno
    if m.modo in ("PY", "RV3"):
        recrear(ctx.admin, bd, ctx.p0351)
        if m.modo == "RV3":
            p = conninfo_to_dict(ctx.admin)
            entorno = {"GAPTO_RV3_IMPORT_URL": f"host={p.get('host')} port={p.get('port')} user={p.get('user')} dbname={bd}"}
        return None, "no aplica", entorno
    raise ValueError(m.modo)


def ejecutar_mutante(ctx: Contexto, m: Mutante, es_control: bool) -> dict:
    entrada: dict = {"mutante": m.ident, "grupo": m.grupo, "modo": m.modo, "guarda": m.guarda,
                     "transformacion": [{"fichero": f, "antes": a, "despues": d} for f, a, d in m.cambios],
                     "discriminantes": list(m.discriminantes)}
    try:
        variantes = aplicar_cambios(ctx.textos, m.cambios)
    except (ValueError, SystemExit) as e:
        entrada.update(veredicto="INVALIDO", motivo=str(e))
        return entrada
    tocados = sorted({f for f, _, _ in m.cambios})
    entrada["sha256_variante"] = sha("\x00".join(variantes[f] for f in sorted(variantes)).encode("utf-8"))
    bd = f"mut0351_{m.ident.lower()}"
    if m.modo == "ESCENARIO":
        recrear(ctx.admin, bd, ctx.p0350)
        sembrar(ctx.admin, bd, m.escenario)
        error = ejecutar_sql(ctx.admin, bd, variantes[M0351])
        recrear(ctx.admin, bd, None)
        esperado = ESCENARIOS[m.escenario]
        entrada["aplicacion_completa"] = error or "APLICADA"
        detecta = bool(error) and esperado in error
        if es_control:
            entrada["veredicto"] = "CONTROL_VERDE" if detecta else "CONTROL_ROJO"
        else:
            entrada["discriminantes_caidos"] = [] if detecta else list(m.discriminantes)
            entrada["otra_defensa"] = (error if error and not detecta else None)
            entrada["veredicto"] = "VIVO" if detecta else "MUERTO"
        entrada["restaurado_sha256"] = True  # el escenario no escribe en el repositorio
        return entrada

    error, auto, entorno = preparar_base(ctx, m, variantes, bd)
    entrada["autocomprobacion"] = auto
    if error:
        recrear(ctx.admin, bd, None)
        entrada.update(veredicto="INVALIDO", motivo=f"la variante no se aplica: {error}")
        return entrada
    escribir_atomico(ctx.journal, {"mutante": m.ident, "ficheros": [
        {"fichero": f, "original_hex": ctx.brutos[f].hex(), "sha256": sha(ctx.brutos[f])} for f in tocados]})
    try:
        for f in tocados:
            (RAIZ / f).write_bytes(variantes[f].encode("utf-8"))
        res = correr_tests(TESTS_POR_MODO[m.modo], entorno)
    finally:
        for f in tocados:
            (RAIZ / f).write_bytes(ctx.brutos[f])
        if any(sha((RAIZ / f).read_bytes()) != APROBADOS[f] for f in tocados):
            raise SystemExit("RESTAURACION FALLIDA: el journal se conserva para recuperar")
        if ctx.journal.exists():
            ctx.journal.unlink()
    recrear(ctx.admin, bd, None)
    entrada["resultado_tests"] = {"pass": len(res["pass"]), "fail": res["fail"], "skip": res["skip"]}
    entrada["restaurado_sha256"] = True
    if es_control:
        ok = not res["fail"] and not res["skip"] and len(res["pass"]) > 0
        entrada["veredicto"] = "CONTROL_VERDE" if ok else "CONTROL_ROJO"
    else:
        c = caidos(m.discriminantes, res["fail"])
        entrada["discriminantes_caidos"] = c
        entrada["veredicto"] = "MUERTO" if c else "VIVO"
    return entrada


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-dsn", required=True)
    ap.add_argument("--plantilla-0340", required=True, help="base en head 0340 (solo lectura)")
    ap.add_argument("--plantilla-0350", required=True, help="base en head 0350 (solo lectura)")
    ap.add_argument("--diario", required=True, help="directorio FUERA del repositorio")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)

    diario = pathlib.Path(a.diario).resolve()
    if diario.is_relative_to(RAIZ.resolve()):
        raise SystemExit("el diario debe vivir fuera del repositorio")
    diario.mkdir(parents=True, exist_ok=True)
    journal = diario / "journal_en_sitio.json"
    if recuperar_si_pendiente(journal):
        raise SystemExit("Habia una mutacion en sitio pendiente: restaurada y verificada. NO_PASS; relanzar.")

    ctx = Contexto(a.admin_dsn, a.plantilla_0340, a.plantilla_0350, "mut0351_t0351", diario, journal)
    for f, esperado in APROBADOS.items():
        b = (RAIZ / f).read_bytes()
        if sha(b) != esperado:
            raise SystemExit(f"{f} no coincide con el SHA-256 aprobado: {sha(b)}")
        ctx.brutos[f] = b
        ctx.textos[f] = b.decode("utf-8", errors="strict")
    # Plantilla 0351 del gate: 0350 + 0351 aprobada COMPLETA (con su postcheck).
    recrear(ctx.admin, ctx.p0351, ctx.p0350)
    err = ejecutar_sql(ctx.admin, ctx.p0351, ctx.textos[M0351])
    if err:
        raise SystemExit(f"la 0351 aprobada no se aplica sobre la plantilla 0350: {err}")

    seleccion = [m for m in CATALOGO if not a.ids or m.ident in a.ids]
    modos = sorted({m.modo for m in seleccion})
    controles = []
    for modo in modos:
        if modo == "ESCENARIO":
            for caso in sorted({m.escenario for m in seleccion if m.modo == "ESCENARIO"}):
                controles.append(Mutante(f"C_ESC_{caso}", "CONTROL", "ESCENARIO", "control sin mutacion", (),
                                         (), escenario=caso))
        else:
            controles.append(Mutante(f"C_{modo}", "CONTROL", modo, "control sin mutacion", (), ()))

    veredictos: dict[str, str] = {}
    for m in [*controles, *seleccion]:
        es_control = m.grupo == "CONTROL"
        entrada = ejecutar_mutante(ctx, m, es_control)
        escribir_atomico(diario / f"{m.ident}.json", entrada)
        veredictos[m.ident] = entrada["veredicto"]
        print(f"{m.ident:12} {entrada['veredicto']:13} {entrada.get('discriminantes_caidos', '')}", flush=True)

    recrear(ctx.admin, ctx.p0351, None)
    for f, esperado in APROBADOS.items():
        if sha((RAIZ / f).read_bytes()) != esperado:
            raise SystemExit(f"IDENTIDAD FINAL NO VERIFICADA: {f}")
    ctrl_ok = all(v == "CONTROL_VERDE" for k, v in veredictos.items() if k.startswith("C_"))
    por_grupo: dict[str, dict[str, int]] = {}
    for m in seleccion:
        g = por_grupo.setdefault(m.grupo, {})
        g[veredictos[m.ident]] = g.get(veredictos[m.ident], 0) + 1
    muertos = sum(1 for m in seleccion if veredictos[m.ident] == "MUERTO")
    gate = ctrl_ok and muertos == len(seleccion) == len(CATALOGO)
    resumen = {"veredictos": veredictos, "por_grupo": por_grupo, "muertos": muertos, "seleccion": len(seleccion),
               "catalogo": len(CATALOGO), "controles_verdes": ctrl_ok, "gate": "PASS" if gate else "NO_PASS",
               "aprobados_sha256": APROBADOS}
    escribir_atomico(diario / "RESUMEN.json", resumen)
    print(json.dumps({k: v for k, v in resumen.items() if k != "aprobados_sha256"}, ensure_ascii=False))
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
