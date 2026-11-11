#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: plan_gate_local.py
# Ruta: scripts/gates/plan_gate_local.py
# Descripcion: Plantilla del gate local EN SERIE (Paso 0 del N1 de 0352, punto 8 de C1): genera el plan JSON que
#   ejecuta scripts/gates/lanzador_gate.py sobre la copia inmutable del commit. Sustituye a los gate.sh/suite.sh de
#   las carpetas de evidencia (lotes 14, 18 y 19), cuyos pasos «replay» y «completar» registraban el rc de `date`:
#   aqui cada paso es un proceso del lanzador y su rc es el del propio proceso. Bloques:
#   - tz: comprueba que el cluster de laboratorio esta en UTC (SHOW timezone; AJ-0352-07);
#   - replay: plantilla lab_tpl_<head> desde 0002 (o desde 0001 con --roles-nuevos) + huellas;
#   - database: base completa por replay + huellas + tests/database + completar manifiesto + huellas fase 2;
#   - api: tests/backend + tests/api (--rootdir=tests/api) sobre un clon de la plantilla;
#   - migration: tests/migration (GAPTO_RV3_IMPORT_URL) sobre un clon;
#   - conc027: tests/database/test_027 sobre gapto2027_cleanroom LOCAL (clon de la plantilla);
#   - baterias: las baterias serie con su variable opt-in (las 18 de antes + test_236 de 0352), cada una sobre un
#     clon nuevo;
#   - b1: revalidacion de B1 como bloque SEPARADO (AJ-B1C-08; Alcance 5bis): test_231, test_233, test_235 (guarda
#     de C-PROP-02 y AJ-0352-08), test_232 con GAPTO_B1_CONCURRENCIA=1 y test_236 con GAPTO_0352_CONCURRENCIA=1,
#     sobre clones nuevos;
#   - gates: tests/gates (pruebas del propio lanzador; sin base de datos).
#   Solo bases de LABORATORIO en 127.0.0.1 (puertos 5460-5469) con el usuario postgres por confianza local: el plan
#   no contiene secretos. Nunca Neon, Supabase ni ENV-DEV.
# Uso: python scripts/gates/plan_gate_local.py --repo R --commit C --head 0352 --puerto 5461 --psql RUTA_PSQL
#        --bloques tz,replay,database,api,migration,conc027,baterias,gates [--roles-nuevos] [--diario DIR ...] > plan.json
# Version: 0.1.0 (F03 · N1 de 0352, Paso 0)
# Version: 0.2.0 (N1 de 0352, M5): bateria test_236 (GAPTO_0352_CONCURRENCIA) y bloque b1 con test_235 y test_236.
# ============================================================
from __future__ import annotations

import argparse
import json
import sys

BATERIAS = [
    ("GAPTO_F04R1_CONCURRENCIA", "tests/backend/test_139_f04_r1_concurrencia_serial.py"),
    ("GAPTO_F04R2A_CONCURRENCIA", "tests/backend/test_14b_f04_r2a_concurrencia_serial.py"),
    ("GAPTO_F04R2B_CONCURRENCIA", "tests/backend/test_14d_f04_r2b_concurrencia_serial.py"),
    ("GAPTO_F04R2C_CONCURRENCIA", "tests/backend/test_14f_f04_r2c_concurrencia_serial.py"),
    ("GAPTO_MANT_VINCULO_CONCURRENCIA", "tests/backend/test_14h_mant_vinculo_concurrencia_serial.py"),
    ("GAPTO_F04R3_CONCURRENCIA", "tests/backend/test_14k_f04_r3_il1b_advisory_serial.py"),
    ("GAPTO_J2J3_CONCURRENCIA", "tests/api/test_190_f05_j2j3_concurrencia_serial.py"),
    ("GAPTO_F0505_CONCURRENCIA", "tests/api/test_191_f05_05_concurrencia_serial.py"),
    ("GAPTO_M4_CONCURRENCIA", "tests/api/test_194_f05_06_m4_concurrencia_serial.py"),
    ("GAPTO_M2_CONCURRENCIA", "tests/api/test_197_f05_06_m2_concurrencia_serial.py"),
    ("GAPTO_M3_CONCURRENCIA", "tests/api/test_200_f05_06_m3_concurrencia_serial.py"),
    ("GAPTO_M3_CONCURRENCIA", "tests/api/test_201_f05_06_m3_orden_locks.py"),
    ("GAPTO_M5_CONCURRENCIA", "tests/api/test_205_f05_06_m5_concurrencia_serial.py"),
    ("GAPTO_M5_CONCURRENCIA", "tests/api/test_208_f05_06_m5b_concurrencia_serial.py"),
    ("GAPTO_F04R3_CONCURRENCIA", "tests/api/test_213_f04_r3_il1b_adaptadores_serial.py"),
    ("GAPTO_F04R3_CONCURRENCIA", "tests/api/test_214_f04_r3_c2_reabrir_serial.py"),
    ("GAPTO_C03_CONCURRENCIA", "tests/api/test_218_f05_d052_c03_concurrencia_serial.py"),
    ("GAPTO_B1_CONCURRENCIA", "tests/api/test_232_f06_01_b1_concurrencia_serial.py"),
    ("GAPTO_0352_CONCURRENCIA", "tests/api/test_236_f06_01_0352_guarda_concurrencia_serial.py"),
]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--puerto", type=int, required=True)
    ap.add_argument("--psql", required=True)
    ap.add_argument("--bloques", default="tz,replay,database,api,migration,conc027,baterias,gates")
    ap.add_argument("--roles-nuevos", action="store_true", help="el cluster no tiene los roles de instancia: la plantilla se crea desde 0001")
    ap.add_argument("--diario", action="append", default=[])
    a = ap.parse_args(argv)
    if not 5460 <= a.puerto <= 5469:
        raise SystemExit("solo clusters locales desechables en 5460-5469")
    bloques = a.bloques.split(",")
    url = lambda db: f"postgresql://postgres@127.0.0.1:{a.puerto}/{db}"  # noqa: E731
    tpl = f"lab_tpl_{a.head}"
    psql = lambda et, *sql: {"etiqueta": et, "tipo": "script", "args": [a.psql, "-h", "127.0.0.1", "-p", str(a.puerto), "-U", "postgres", "-v", "ON_ERROR_STOP=1", "-q",  # noqa: E731
                                                                         "-d", "postgres", *sum((["-c", s] for s in sql), [])], "parar_si_falla": True}
    huellas = lambda et, db: {"etiqueta": et, "tipo": "verificacion", "env": {"GAPTO_TEST_DATABASE_URL": url(db)},  # noqa: E731
                              "args": ["{PYTHON}", "scripts/gates/huellas_d111.py", "--dsn-var", "GAPTO_TEST_DATABASE_URL", "--head", a.head,
                                       "--salida", "{SALIDA}/" + et + ".json"]}
    clon = lambda db: psql(f"crear_{db}", f"DROP DATABASE IF EXISTS {db} WITH (FORCE)", f"CREATE DATABASE {db} TEMPLATE {tpl}")  # noqa: E731
    borrar = lambda db: {**psql(f"borrar_{db}", f"DROP DATABASE IF EXISTS {db} WITH (FORCE)"), "parar_si_falla": False}  # noqa: E731
    pasos: list[dict] = []
    if "tz" in bloques:
        pasos.append({"etiqueta": "timezone_utc", "tipo": "verificacion", "parar_si_falla": True,
                      "args": [a.psql, "-h", "127.0.0.1", "-p", str(a.puerto), "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-At",
                               "-c", "DO $$ BEGIN IF current_setting('TimeZone') NOT IN ('UTC','Etc/UTC') THEN RAISE EXCEPTION 'timezone % no es UTC', current_setting('TimeZone'); END IF; END $$",
                               "-c", "SHOW timezone"]})
    if "replay" in bloques:
        pasos.append(psql("crear_tpl", f"DROP DATABASE IF EXISTS {tpl} WITH (FORCE)", f"CREATE DATABASE {tpl}"))
        desde = [] if a.roles_nuevos else ["--desde", "0002"]
        pasos.append({"etiqueta": "replay_tpl", "tipo": "script", "parar_si_falla": True, "env": {"GAPTO_CLEANROOM_URL": url(tpl)},
                      "args": ["{PYTHON}", "scripts/postgres/run_clean_room.py", *desde, "--head", a.head, "--commit", a.commit,
                               "--manifiesto", "{SALIDA}/manifest_tpl.json"]})
        pasos.append(huellas("huellas_tpl", tpl))
    if "database" in bloques:
        full = f"lab_full_{a.head}"
        pasos.append(psql("crear_full", f"DROP DATABASE IF EXISTS {full} WITH (FORCE)", f"CREATE DATABASE {full}"))
        pasos.append({"etiqueta": "replay_full", "tipo": "script", "parar_si_falla": True, "env": {"GAPTO_CLEANROOM_URL": url(full)},
                      "args": ["{PYTHON}", "scripts/postgres/run_clean_room.py", "--desde", "0002", "--head", a.head, "--commit", a.commit,
                               "--manifiesto", "{SALIDA}/manifest_full.json"]})
        pasos.append(huellas("huellas_full_tras_replay", full))
        pasos.append({"etiqueta": "full_database", "tipo": "pytest", "env": {"GAPTO_TEST_DATABASE_URL": url(full)}, "args": ["tests/database", "-q"]})
        pasos.append({"etiqueta": "completar", "tipo": "script", "env": {"GAPTO_CLEANROOM_URL": url(full)},
                      "args": ["{PYTHON}", "scripts/postgres/run_clean_room.py", "--solo-verificar", "--head", a.head, "--junit", "{SALIDA}/full_database.xml",
                               "--completar-manifiesto", "{SALIDA}/manifest_full.json"]})
        pasos.append(huellas("huellas_full_fase2", full))
        pasos.append(borrar(full))
    if "api" in bloques:
        db = "m_full_api"
        pasos += [clon(db), {"etiqueta": "full_api", "tipo": "pytest", "env": {"GAPTO_TEST_DATABASE_URL": url(db)},
                             "args": ["tests/backend", "tests/api", "-q", "--rootdir=tests/api"]}, borrar(db)]
    if "migration" in bloques:
        db = "m_full_migration"
        pasos += [clon(db), {"etiqueta": "full_migration", "tipo": "pytest",
                             "env": {"GAPTO_RV3_IMPORT_URL": f"host=127.0.0.1 port={a.puerto} user=postgres dbname={db}"},
                             "args": ["tests/migration", "-q"]}, borrar(db)]
    if "conc027" in bloques:
        db = "gapto2027_cleanroom"
        pasos += [clon(db), {"etiqueta": "conc_027", "tipo": "pytest", "env": {"GAPTO_TEST_DATABASE_URL": url(db), "GAPTO_CONCURRENCY_URL": url(db)},
                             "args": ["tests/database/test_027_concurrencia.py", "-q"]}, borrar(db)]
    if "baterias" in bloques:
        for var, ruta in BATERIAS:
            et = "serie_" + ruta.rsplit("/", 1)[1][:-3]
            db = "m_" + et[:55]
            raiz = "tests/api" if ruta.startswith("tests/api") else "tests/backend"
            pasos += [clon(db), {"etiqueta": et, "tipo": "pytest", "env": {"GAPTO_TEST_DATABASE_URL": url(db), var: "1"},
                                 "args": [ruta, "-q", f"--rootdir={raiz}"]}, borrar(db)]
    if "b1" in bloques:
        for et, rutas, extra in [("b1_test_231", ["tests/api/test_231_f06_01_b1_propiedades.py"], {}),
                                 ("b1_test_233", ["tests/api/test_233_f06_01_b1_rls_acl.py"], {}),
                                 ("b1_test_235_guarda", ["tests/api/test_235_f06_01_0352_guarda_c_prop_02.py"], {}),
                                 ("b1_test_232_concurrencia", ["tests/api/test_232_f06_01_b1_concurrencia_serial.py"], {"GAPTO_B1_CONCURRENCIA": "1"}),
                                 ("b1_test_236_guarda_concurrencia", ["tests/api/test_236_f06_01_0352_guarda_concurrencia_serial.py"],
                                  {"GAPTO_0352_CONCURRENCIA": "1"})]:
            db = "m_" + et
            pasos += [clon(db), {"etiqueta": et, "tipo": "pytest", "env": {"GAPTO_TEST_DATABASE_URL": url(db), **extra},
                                 "args": [*rutas, "-q", "--rootdir=tests/api"]}, borrar(db)]
    if "gates" in bloques:
        pasos.append({"etiqueta": "gates_lanzador", "tipo": "pytest", "args": ["tests/gates", "-q", "--basetemp={SALIDA}/tmp_gates"]})
    plan = {"repo": a.repo, "commit": a.commit, "diarios": a.diario, "ignorar": [], "pasos": pasos}
    json.dump(plan, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
