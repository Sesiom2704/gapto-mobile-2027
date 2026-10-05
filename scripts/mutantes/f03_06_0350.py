#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f03_06_0350.py
# Ruta: scripts/mutantes/f03_06_0350.py
# Descripcion: Mutation gate de F03-06 / 0350 (D-201): catalogo CERRADO
#   M1..M8 contra test_045_f03_06_0350_tipo_hecho_condonacion.py y
#   test_017_seeds_sistema.py.
#
#   MODELO. Cada variante se construye a partir de los bytes aprobados de la
#   migration 0350 y de test_017 (SHA-256 fijados abajo). Cada sustitucion
#   debe aparecer EXACTAMENTE una vez; si no, el mutante es INVALIDO y el gate
#   no pasa. La variante de 0350 se aplica sobre una base DESECHABLE clonada
#   de una plantilla en head 0340 (CREATE DATABASE ... TEMPLATE). Como
#   test_045 ejecuta el cuerpo REAL de 0350 leido del fichero (reaplicar,
#   datos preexistentes, seed distinto), la variante se escribe ademas EN
#   SITIO en el repositorio mientras corren los tests, y se restaura despues
#   verificando el SHA-256 (mismo modelo que mutantes_vs01 y mutantes_f05_01).
#   M7 muta test_017, no la migration.
#
#   AUTOCOMPROBACIONES. Para medir el poder discriminante de los tests el
#   bloque $postcheck_0350$ se RETIRA de todas las variantes, control
#   incluido (si no, la propia migration abortaria varios mutantes antes de
#   que el test los viera). Por separado se registra si la migration
#   COMPLETA mutada habria abortado ("autocomprobacion"), como dato
#   informativo que no cuenta para el gate.
#
#   VEREDICTOS (uno por mutante): MUERTO si falla al menos uno de sus
#   discriminantes declarados; VIVO si no falla ninguno; INVALIDO si la
#   sustitucion no es unica o la variante no se puede aplicar. El control M0
#   (sin mutacion, postcheck retirado) debe dejar test_045 y test_017 VERDES y
#   SIN saltos. PASS del gate = control verde + 8/8 MUERTOS.
#
#   GUARDAS D-181/D-192. E/S byte a byte (UTF-8 estricto, sin normalizar
#   finales de linea); journal JSON durable (os.replace) FUERA del
#   repositorio ANTES de tocar el primer byte; al arrancar, si hay journal
#   pendiente: restaura, verifica el SHA-256 y aborta (NO_PASS, relanzar);
#   tras cada mutante se restaura y se verifica identidad byte a byte. Diario
#   por mutante reutilizable solo con el mismo SHA-256 de variante. Cada base
#   desechable se elimina antes y despues de usarla.
#   Requiere un --admin-dsn con CREATEDB y propietario de la plantilla (rol NO
#   superusuario de la topologia D-189). No es evidencia de proveedor.
# Uso:
#   python scripts/mutantes/f03_06_0350.py --admin-dsn "host=127.0.0.1
#     port=5460 user=gapto_bootstrap dbname=postgres" --plantilla b1_t0340
#     --diario /ruta/fuera [M1 ...]
# Version: 0.1.0  -- F03-06 / D-201 / 0350 (B1, Fase A).
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
MIGRATION = RAIZ / "migrations" / "0350_f03_06_tipo_hecho_condonacion.sql"
MIGRATION_SHA256 = "1615a4bd7eb3de8919a85e653e86e15c15088659fc589e77a00d288d003c2461"
TEST017 = RAIZ / "tests" / "database" / "test_017_seeds_sistema.py"
TEST017_SHA256 = "bb5ea16560c2d110f1967e44e8ddac66d84a55aea5667c43abcc0811f0d2f017"
TESTS = ("tests/database/test_045_f03_06_0350_tipo_hecho_condonacion.py",
         "tests/database/test_017_seeds_sistema.py")
T45 = "test_045_f03_06_0350_tipo_hecho_condonacion"
T17 = "test_017_seeds_sistema"

INSERT = "    ('0d216df5-59eb-56c8-998e-7d47953b9351', 'CONDONACION', 'Condonacion de derecho u obligacion', true);"
RESET = "\nRESET ROLE;\n"
ASERCION_017 = ('    assert found in TIPOS_HECHO_POR_HEAD.values(), '
                'f"tipos_hecho fuera de los estados autorizados: {sorted(found)}"')
PRECHECK = "<bloque $precheck_0350$>"  # se resuelve al texto exacto del bloque en tiempo de ejecucion


@dataclass(frozen=True)
class Mutante:
    ident: str
    descripcion: str
    cambios_sql: tuple[tuple[str, str], ...]
    cambios_017: tuple[tuple[str, str], ...]
    discriminantes: tuple[str, ...]


CATALOGO = (
    Mutante("M1", "sin precheck", ((PRECHECK, ""),), (),
            (f"{T45}::test_0350_reaplicar_rechazado_por_precheck",
             f"{T45}::test_0350_precheck_rechaza_seed_distinto_de_0150")),
    Mutante("M2", "UUID distinto", ((INSERT, INSERT.replace("9351'", "9352'")),), (),
            (f"{T45}::test_0350_fila_con_contrato_d201", f"{T17}::test_tipos_hecho_ids_are_deterministic_uuidv5")),
    Mutante("M3", "codigo distinto", ((INSERT, INSERT.replace("'CONDONACION'", "'CONDONACIONES'")),), (),
            (f"{T45}::test_0350_fila_con_contrato_d201", f"{T17}::test_tipos_hecho_exactly_7_expected_codes")),
    Mutante("M4", "enabled=false", ((INSERT, INSERT.replace("true);", "false);")),), (),
            (f"{T45}::test_0350_fila_con_contrato_d201", f"{T17}::test_tipos_hecho_all_enabled")),
    Mutante("M5", "fila duplicada (segundo arquetipo de condonacion)",
            ((INSERT, INSERT[:-1] + ",\n    ('9e2dd703-6e1f-50c4-bd03-67c7de92b6ae', 'CONDONACION_OBLIGACION', "
                                    "'Condonacion de obligacion', true);"),), (),
            (f"{T45}::test_0350_exactamente_ocho_tipos", f"{T17}::test_tipos_hecho_exactly_7_expected_codes")),
    Mutante("M6", "DDL colado (indice en tipos_hecho)",
            ((RESET, "\nCREATE INDEX ix_mut_0350 ON gapto.tipos_hecho (nombre);" + RESET),), (),
            (f"{T45}::test_0350_estructura_sin_ddl",)),
    Mutante("M7", "test_017 sin parametrizar por head", (),
            ((ASERCION_017, "    assert found == TIPOS_HECHO_ESPERADOS"),),
            (f"{T17}::test_tipos_hecho_exactly_7_expected_codes",)),
    Mutante("M8", "toca una fila ajena (UPDATE sin cambio de valor sobre el seed de 0150)",
            ((RESET, "\nUPDATE gapto.tipos_hecho SET nombre = nombre WHERE codigo = 'GASTO';" + RESET),), (),
            (f"{T45}::test_0350_datos_preexistentes_intactos",)),
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def bloque(sql: str, etiqueta: str) -> str:
    patron = re.compile(r"DO \$" + etiqueta + r"\$.*?\$" + etiqueta + r"\$ LANGUAGE plpgsql;\n", re.S)
    hallados = patron.findall(sql)
    if len(hallados) != 1:
        raise SystemExit(f"bloque ${etiqueta}$ no encontrado exactamente una vez")
    return hallados[0]


def aplicar_cambios(texto: str, cambios, precheck: str, ident: str) -> str:
    for viejo, nuevo in cambios:
        viejo = precheck if viejo == PRECHECK else viejo
        if texto.count(viejo) != 1:
            raise ValueError(f"{ident}: patron presente {texto.count(viejo)} veces")
        texto = texto.replace(viejo, nuevo)
    return texto


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


def correr_tests(admin_dsn: str, base: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        junit = pathlib.Path(d) / "j.xml"
        entorno = dict(os.environ, GAPTO_TEST_DATABASE_URL=dsn_base(admin_dsn, base))
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *TESTS,
                        f"--junitxml={junit}"], cwd=RAIZ, env=entorno,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        res = {"pass": [], "fail": [], "skip": []}
        if not junit.exists():
            return res
        for t in ET.parse(junit).getroot().iter("testcase"):
            modulo = t.get("classname", "").split(".")[-1]
            if modulo not in (T45, T17):
                continue
            estado = ("fail" if t.find("failure") is not None or t.find("error") is not None
                      else "skip" if t.find("skipped") is not None else "pass")
            res[estado].append(f"{modulo}::{t.get('name')}")
        return {k: sorted(v) for k, v in res.items()}


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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-dsn", required=True)
    ap.add_argument("--plantilla", required=True, help="base en head 0340, solo lectura")
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

    bruto_sql, bruto_017 = MIGRATION.read_bytes(), TEST017.read_bytes()
    if sha(bruto_sql) != MIGRATION_SHA256:
        raise SystemExit(f"0350 no coincide con el SHA-256 aprobado: {sha(bruto_sql)}")
    if sha(bruto_017) != TEST017_SHA256:
        raise SystemExit(f"test_017 no coincide con el SHA-256 aprobado: {sha(bruto_017)}")
    original_sql = bruto_sql.decode("utf-8", errors="strict")
    original_017 = bruto_017.decode("utf-8", errors="strict")
    precheck = bloque(original_sql, "precheck_0350")
    base_sql = original_sql.replace(bloque(original_sql, "postcheck_0350"), "")

    seleccion = [m for m in CATALOGO if not a.ids or m.ident in a.ids]
    control = Mutante("M0", "control sin mutacion", (), (), ())
    veredictos: dict[str, str] = {}
    for m in [control, *seleccion]:
        entrada: dict = {"mutante": m.ident, "descripcion": m.descripcion, "discriminantes": list(m.discriminantes)}
        try:
            variante = aplicar_cambios(base_sql, m.cambios_sql, precheck, m.ident)
            completa = aplicar_cambios(original_sql, m.cambios_sql, precheck, m.ident)
            variante_017 = aplicar_cambios(original_017, m.cambios_017, precheck, m.ident)
        except ValueError as e:
            entrada.update(veredicto="INVALIDO", motivo=str(e))
            escribir_atomico(diario / f"{m.ident}.json", entrada)
            veredictos[m.ident] = "INVALIDO"
            continue
        entrada["sha256_variante"] = sha((variante + "\x00" + variante_017).encode("utf-8"))
        previo = diario / f"{m.ident}.json"
        if previo.exists():
            viejo = json.loads(previo.read_text(encoding="utf-8"))
            if viejo.get("sha256_variante") == entrada["sha256_variante"] and "veredicto" in viejo:
                veredictos[m.ident] = viejo["veredicto"]
                print(f"{m.ident:4} {viejo['veredicto']:8} (reutilizado del diario)")
                continue

        bd = f"mut_f0306_{m.ident.lower()}"
        recrear(a.admin_dsn, bd, a.plantilla)
        entrada["autocomprobacion"] = aplicar(a.admin_dsn, bd, completa) or "no aborta"
        recrear(a.admin_dsn, bd, a.plantilla)
        error = aplicar(a.admin_dsn, bd, variante)
        if error:
            entrada.update(veredicto="INVALIDO", motivo=f"la variante no se aplica: {error}")
        else:
            escribir_atomico(journal, {"mutante": m.ident, "ficheros": [
                {"fichero": str(p.relative_to(RAIZ)), "original_hex": b.hex(), "sha256": sha(b)}
                for p, b in ((MIGRATION, bruto_sql), (TEST017, bruto_017))]})
            try:
                MIGRATION.write_bytes(variante.encode("utf-8"))
                TEST017.write_bytes(variante_017.encode("utf-8"))
                res = correr_tests(a.admin_dsn, bd)
            finally:
                MIGRATION.write_bytes(bruto_sql)
                TEST017.write_bytes(bruto_017)
                if sha(MIGRATION.read_bytes()) != MIGRATION_SHA256 or sha(TEST017.read_bytes()) != TEST017_SHA256:
                    raise SystemExit("RESTAURACION FALLIDA: el journal se conserva para recuperar")
                journal.unlink()
            entrada["resultado_tests"] = res
            entrada["restaurado_sha256"] = True
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
               "gate": "PASS" if gate else "NO_PASS", "migration_sha256": MIGRATION_SHA256,
               "test017_sha256": TEST017_SHA256}
    escribir_atomico(diario / "RESUMEN.json", resumen)
    print(json.dumps(resumen, ensure_ascii=False))
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
