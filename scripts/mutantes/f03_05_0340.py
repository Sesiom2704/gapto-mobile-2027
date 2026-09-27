#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f03_05_0340.py
# Ruta: scripts/mutantes/f03_05_0340.py
# Descripcion: Mutation gate de F03-05 / 0340 (D-197, Q-3): catalogo
#   CERRADO M1..M10 contra test_043_f03_05_0340_categoria_icon_key.py.
#
#   MODELO. No se toca ningun fichero del repositorio: cada mutante se
#   construye EN MEMORIA a partir de los bytes de la migration 0340, cuyo
#   SHA-256 debe coincidir con el aprobado (MIGRATION_SHA256), y se aplica
#   sobre una base DESECHABLE clonada de una plantilla en head 0330
#   (CREATE DATABASE ... TEMPLATE). Cada sustitucion debe aparecer
#   EXACTAMENTE una vez; si no, el mutante es INVALIDO y el gate no pasa.
#
#   AUTOCOMPROBACIONES. Para medir el poder discriminante de test_043 los
#   bloques $filas_0340$ y $postcheck_0340$ se RETIRAN de todas las
#   variantes, control incluido (si no, la propia migration abortaria varios
#   mutantes antes de que el test los viera). Por separado se registra si la
#   migration COMPLETA mutada habria abortado ("autocomprobacion"), como
#   dato informativo que no cuenta para el gate.
#
#   VEREDICTOS (uno por mutante): MUERTO si falla al menos uno de sus
#   discriminantes declarados; VIVO si no falla ninguno; INVALIDO si la
#   sustitucion no es unica o la variante no se puede aplicar. El control
#   M0 (sin mutacion, mismos bloques retirados) debe dejar test_043 VERDE y
#   SIN saltos. PASS del gate = control verde + 10/10 MUERTOS.
#
#   GUARDAS D-181/D-192. E/S byte a byte (UTF-8 estricto, sin
#   normalizar finales de linea); diario JSON por mutante escrito de forma
#   atomica (os.replace) fuera del repositorio; al arrancar se reutilizan
#   solo entradas con el mismo SHA-256 de variante; cada base desechable se
#   elimina antes y despues de usarla, de modo que una caida a mitad deja,
#   como mucho, una base mut_* que la siguiente ejecucion borra.
# Uso:
#   python scripts/mutantes/f03_05_0340.py --admin-dsn "host=/tmp port=5433
#     user=exec_d189 dbname=postgres" --plantilla t0330 --diario /ruta/fuera
#     [M1 ...]
# Version: 0.1.0
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
from dataclasses import dataclass

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "migrations" / "0340_f03_05_categoria_icon_key.sql"
MIGRATION_SHA256 = "3fc9c87d95e70c0a6838df3b841b663d89c9374b4d7ecd90db42b489dda08ee5"
TEST = "tests/database/test_043_f03_05_0340_categoria_icon_key.py"
MODULO = "test_043_f03_05_0340_categoria_icon_key"

ADD = "    ADD COLUMN icon_key varchar(80);"
CHECK = "    CHECK (icon_key IS NULL OR (icon_key <> '' AND icon_key = btrim(icon_key)));"
CHECK_COMPLETO = ("ALTER TABLE gapto.categorias_financieras\n"
                  "    ADD CONSTRAINT ck_categorias_financieras__icon_key_no_vacia_recortada\n" + CHECK + "\n")
FORCE = "ALTER TABLE gapto.categorias_financieras FORCE ROW LEVEL SECURITY;\n"


@dataclass(frozen=True)
class Mutante:
    ident: str
    descripcion: str
    cambios: tuple[tuple[str, str], ...]
    discriminantes: tuple[str, ...]


RECHAZOS = tuple(f"test_0340_rechaza[{i}]" for i in (
    "vacia", "un_espacio", "solo_espacios", "espacio_inicial", "espacio_final", "ambos_extremos"))

CATALOGO = (
    Mutante("M1", "sin CHECK", ((CHECK_COMPLETO, ""),), RECHAZOS),
    Mutante("M2", "CHECK solo <> ''",
            ((CHECK, "    CHECK (icon_key IS NULL OR icon_key <> '');"),),
            ("test_0340_rechaza[un_espacio]", "test_0340_rechaza[solo_espacios]",
             "test_0340_rechaza[espacio_inicial]", "test_0340_rechaza[espacio_final]",
             "test_0340_rechaza[ambos_extremos]")),
    Mutante("M3", "ltrim en vez de btrim", ((CHECK, CHECK.replace("btrim", "ltrim")),),
            ("test_0340_rechaza[espacio_final]",)),
    Mutante("M4", "rtrim en vez de btrim", ((CHECK, CHECK.replace("btrim", "rtrim")),),
            ("test_0340_rechaza[espacio_inicial]",)),
    Mutante("M5", "DEFAULT 'x'", ((ADD, "    ADD COLUMN icon_key varchar(80) DEFAULT 'x';"),),
            ("test_0340_columna_con_tipo_exacto", "test_0340_alta_sin_icono_queda_null")),
    Mutante("M6", "NOT NULL", ((ADD, "    ADD COLUMN icon_key varchar(80) NOT NULL;"),),
            ("test_0340_columna_con_tipo_exacto", "test_0340_alta_sin_icono_queda_null")),
    Mutante("M7", "CHECK NOT VALID", ((CHECK, CHECK[:-1] + " NOT VALID;"),),
            ("test_0340_check_validado_e_inmediato",)),
    Mutante("M8", "UNIQUE (owner_user_id, icon_key)",
            ((CHECK_COMPLETO, CHECK_COMPLETO + "\nALTER TABLE gapto.categorias_financieras\n"
              "    ADD CONSTRAINT uq_mut_m8 UNIQUE (owner_user_id, icon_key);\n"),),
            ("test_0340_sin_unique_fk_ni_indice", "test_0340_icono_repetido_admitido")),
    Mutante("M9", "varchar(100)", ((ADD, "    ADD COLUMN icon_key varchar(100);"),),
            ("test_0340_columna_con_tipo_exacto", "test_0340_longitud_81_rechazada")),
    Mutante("M10", "FORCE RLS no restaurado", ((FORCE, ""),), ("test_0340_force_rls_intacto",)),
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sin_autocomprobaciones(sql: str) -> str:
    for etiqueta in ("filas_0340", "postcheck_0340"):
        patron = re.compile(r"DO \$" + etiqueta + r"\$.*?\$" + etiqueta + r"\$;\n", re.S)
        sql, n = patron.subn("", sql)
        if n != 1:
            raise SystemExit(f"bloque ${etiqueta}$ no encontrado exactamente una vez")
    return sql


def aplicar_cambios(sql: str, m: Mutante) -> str:
    for viejo, nuevo in m.cambios:
        if sql.count(viejo) != 1:
            raise ValueError(f"{m.ident}: patron presente {sql.count(viejo)} veces")
        sql = sql.replace(viejo, nuevo)
    return sql


def dsn_base(admin_dsn: str, base: str) -> str:
    partes = conninfo_to_dict(admin_dsn)
    partes["dbname"] = base
    return make_conninfo(**partes)


def recrear(admin_dsn: str, base: str, plantilla: str | None) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {base} WITH (FORCE)")
        if plantilla:
            c.execute(f"CREATE DATABASE {base} TEMPLATE {plantilla}")


def aplicar(admin_dsn: str, base: str, sql: str) -> str | None:
    try:
        with psycopg.connect(dsn_base(admin_dsn, base), autocommit=True) as c:
            c.execute(sql)
        return None
    except psycopg.Error as e:
        return str(e).splitlines()[0]


def correr_test(admin_dsn: str, base: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        junit = pathlib.Path(d) / "j.xml"
        entorno = dict(os.environ, GAPTO_TEST_DATABASE_URL=dsn_base(admin_dsn, base))
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST,
                        f"--junitxml={junit}"], cwd=RAIZ, env=entorno,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        res = {"pass": [], "fail": [], "skip": []}
        for t in ET.parse(junit).getroot().iter("testcase"):
            if t.get("classname", "").split(".")[-1] != MODULO:
                continue
            estado = ("fail" if t.find("failure") is not None or t.find("error") is not None
                      else "skip" if t.find("skipped") is not None else "pass")
            res[estado].append(t.get("name"))
        return {k: sorted(v) for k, v in res.items()}


def escribir_atomico(ruta: pathlib.Path, contenido: dict) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(contenido, indent=1, ensure_ascii=False).encode("utf-8"))
    os.replace(tmp, ruta)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-dsn", required=True)
    ap.add_argument("--plantilla", required=True, help="base en head 0330, solo lectura")
    ap.add_argument("--diario", required=True, help="directorio FUERA del repositorio")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)

    diario = pathlib.Path(a.diario).resolve()
    if diario.is_relative_to(RAIZ.resolve()):
        raise SystemExit("el diario debe vivir fuera del repositorio")
    diario.mkdir(parents=True, exist_ok=True)

    bruto = MIGRATION.read_bytes()
    if sha(bruto) != MIGRATION_SHA256:
        raise SystemExit(f"0340 no coincide con el SHA-256 aprobado: {sha(bruto)}")
    original = bruto.decode("utf-8", errors="strict")
    base_sql = sin_autocomprobaciones(original)

    seleccion = [m for m in CATALOGO if not a.ids or m.ident in a.ids]
    control = Mutante("M0", "control sin mutacion", (), ())
    veredictos: dict[str, str] = {}
    for m in [control, *seleccion]:
        entrada: dict = {"mutante": m.ident, "descripcion": m.descripcion,
                         "discriminantes": list(m.discriminantes)}
        try:
            variante = aplicar_cambios(base_sql, m)
            completa = aplicar_cambios(original, m)
        except ValueError as e:
            entrada.update(veredicto="INVALIDO", motivo=str(e))
            escribir_atomico(diario / f"{m.ident}.json", entrada)
            veredictos[m.ident] = "INVALIDO"
            continue
        entrada["sha256_variante"] = sha(variante.encode("utf-8"))
        previo = diario / f"{m.ident}.json"
        if previo.exists():
            viejo = json.loads(previo.read_text(encoding="utf-8"))
            if viejo.get("sha256_variante") == entrada["sha256_variante"] and "veredicto" in viejo:
                veredictos[m.ident] = viejo["veredicto"]
                print(f"{m.ident:4} {viejo['veredicto']:8} (reutilizado del diario)")
                continue

        bd = f"mut_f0305_{m.ident.lower()}"
        recrear(a.admin_dsn, bd, a.plantilla)
        entrada["autocomprobacion"] = aplicar(a.admin_dsn, bd, completa) or "no aborta"
        recrear(a.admin_dsn, bd, a.plantilla)
        error = aplicar(a.admin_dsn, bd, variante)
        if error:
            entrada.update(veredicto="INVALIDO", motivo=f"la variante no se aplica: {error}")
        else:
            res = correr_test(a.admin_dsn, bd)
            entrada["resultado_test_043"] = res
            if m is control:
                ok = not res["fail"] and not res["skip"] and len(res["pass"]) > 0
                entrada["veredicto"] = "CONTROL_VERDE" if ok else "CONTROL_ROJO"
            else:
                caidos = sorted(set(m.discriminantes) & set(res["fail"]))
                entrada["discriminantes_caidos"] = caidos
                entrada["veredicto"] = "MUERTO" if caidos else "VIVO"
        recrear(a.admin_dsn, bd, None)
        escribir_atomico(diario / f"{m.ident}.json", entrada)
        veredictos[m.ident] = entrada["veredicto"]
        print(f"{m.ident:4} {entrada['veredicto']:13} {entrada.get('discriminantes_caidos', '')}")

    muertos = sum(1 for k, v in veredictos.items() if k != "M0" and v == "MUERTO")
    gate = veredictos.get("M0") == "CONTROL_VERDE" and muertos == len(seleccion) == len(CATALOGO)
    resumen = {"veredictos": veredictos, "muertos": muertos, "catalogo": len(CATALOGO),
               "gate": "PASS" if gate else "NO_PASS", "migration_sha256": MIGRATION_SHA256}
    escribir_atomico(diario / "RESUMEN.json", resumen)
    print(json.dumps(resumen, ensure_ascii=False))
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
