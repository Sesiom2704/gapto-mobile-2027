#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f03_06_0352.py
# Ruta: scripts/mutantes/f03_06_0352.py
# Descripcion: Mutation gate de la migration 0352 (N1 de 0352, mandato v1.4, Alcance 7; dictamen de diseno
#   0352 AJ-0352-01..12; WM 12C.2, D-181, D-192). Catalogo CERRADO, cada mutante con sustitucion de texto
#   EXACTO (una sola aparicion o INVALIDO) sobre los bytes aprobados de la migration y discriminante declarado:
#     TEST (CHECK y DDL; la variante se aplica SIN su bloque de postcheck sobre una base nueva clonada de una
#           plantilla en 0351, y deben caer sus nodos de test_047/test_046):
#       M-CK-01  ck adquisicion sin «conjunto IS NOT NULL» (el hueco NULL; obligatorio, P0352-02)
#       M-CK-02  ck mejoras sin «conjunto IS NOT NULL»
#       M-CK-03  ck adquisicion admite completo = false (IS TRUE -> IS NOT NULL)
#       M-CK-04  ck mejoras admite completas = false
#       M-CK-05  ck corte con frontera estricta (>= -> >)
#       M-CK-06  sin ck de corte
#       M-DDL-01 FORCE RLS de propiedades no restaurado
#     ESCENARIO (precheck y postcheck; la variante COMPLETA se aplica sobre un estado provocado y debe abortar con
#           el mensaje de SU guarda; si aborta por otra defensa o no aborta, el discriminante falla: MUERTO, con la
#           otra defensa registrada):
#       Q-REAP   precheck de reaplicacion retirado        (base ya en 0352)
#       Q-ROL    precheck de rol retirado                 (rol de login sin SET sobre gapto_owner)
#       Q-COLS   precheck de 781 columnas retirado        (base 0351 con una columna de mas)
#       P-CHK    postcheck de 3 CHECK validados retirado  (variante que deja un CHECK NOT VALID)
#       P-FORCE  postcheck de FORCE de propiedades retirado (variante que no restaura FORCE)
#   Cada modo tiene su CONTROL sin mutacion (TEST verde; ESCENARIO abortando con el mensaje de su guarda). PASS =
#   controles verdes + todos MUERTOS. Guardas D-181/D-192: E/S byte a byte; journal JSON (os.replace) FUERA del
#   repositorio ANTES de tocar el primer byte; journal pendiente al arrancar -> restaura, verifica SHA-256 y
#   aborta; restauracion verificada tras cada mutante; bases desechables (lab, nunca proveedor).
# Uso:
#   python scripts/mutantes/f03_06_0352.py --admin-dsn "postgresql://postgres@127.0.0.1:5461/postgres"
#     --plantilla-0351 lab_tpl_0351 --diario C:\fuera\del\repo [--json salida.json] [M-CK-01 ...]
# Version: 0.1.0 (F03 · N1 de 0352, mandato v1.4)
# ============================================================
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIG = "migrations/0352_f06_01_b2_completitud_coste.sql"
T047 = "tests/database/test_047_f06_01_0352_completitud_coste.py"
T046 = "tests/database/test_046_f06_01_0351_base_patrimonial.py"
APROBADO = "0b9607e01b7771148a6ff3aa683da92eb4b972ec392d9f64ca745d99e52824a1"   # migration 0352 1.0.0 (M4)
POST_INI = "DO $postcheck_0352$\n"
POST_FIN = "$postcheck_0352$;\n"


def n(nombre: str) -> str:
    return f"{T047}::{nombre}"


NEG = n("test_0352_negativos_y_positivos")


@dataclass(frozen=True)
class Mutante:
    ident: str
    modo: str            # TEST | ESCENARIO
    invariante: str
    viejo: str
    nuevo: str
    discriminantes: tuple[str, ...] = ()
    escenario: str = ""  # REAP | ROL | COLS | CHK | FORCE
    mensaje: str = ""    # mensaje de la guarda que debe abortar en el escenario


ADQ_NN = ("            AND coste_adquisicion_conjunto_declarado IS NOT NULL\n"
          "            AND pg_catalog.jsonb_typeof(coste_adquisicion_conjunto_declarado) = 'array')),\n")
MEJ_NN = ("            AND mejoras_conjunto_declarado IS NOT NULL\n"
          "            AND pg_catalog.jsonb_typeof(mejoras_conjunto_declarado) = 'array')),\n")
CORTE = ("    ADD CONSTRAINT ck_propiedades__coste_adquisicion_corte_no_anterior CHECK (\n"
         "        coste_adquisicion_declarado_en IS NULL OR fecha_adquisicion IS NULL\n"
         "        OR coste_adquisicion_declarado_en >= fecha_adquisicion);\n")
MUTANTES = (
    Mutante("M-CK-01", "TEST", "ck adquisicion exige conjunto IS NOT NULL (hueco NULL)", ADQ_NN,
            "            AND pg_catalog.jsonb_typeof(coste_adquisicion_conjunto_declarado) = 'array')),\n",
            (NEG, n("test_0352_checks_exactos_y_validados"))),
    Mutante("M-CK-02", "TEST", "ck mejoras exige conjunto IS NOT NULL", MEJ_NN,
            "            AND pg_catalog.jsonb_typeof(mejoras_conjunto_declarado) = 'array')),\n",
            (NEG, n("test_0352_checks_exactos_y_validados"))),
    Mutante("M-CK-03", "TEST", "ck adquisicion: completo solo TRUE", "        OR (coste_adquisicion_declarado_completo IS TRUE AND",
            "        OR (coste_adquisicion_declarado_completo IS NOT NULL AND", (NEG, n("test_0352_checks_exactos_y_validados"))),
    Mutante("M-CK-04", "TEST", "ck mejoras: completas solo TRUE", "        OR (mejoras_declaradas_completas IS TRUE AND",
            "        OR (mejoras_declaradas_completas IS NOT NULL AND", (NEG, n("test_0352_checks_exactos_y_validados"))),
    Mutante("M-CK-05", "TEST", "ck corte: frontera inclusiva (corte = adquisicion admitido)",
            "        OR coste_adquisicion_declarado_en >= fecha_adquisicion);\n", "        OR coste_adquisicion_declarado_en > fecha_adquisicion);\n",
            (NEG, n("test_0352_checks_exactos_y_validados"))),
    Mutante("M-CK-06", "TEST", "ck corte presente", "            AND pg_catalog.jsonb_typeof(mejoras_conjunto_declarado) = 'array')),\n" + CORTE,
            "            AND pg_catalog.jsonb_typeof(mejoras_conjunto_declarado) = 'array'));\n",
            (NEG, n("test_0352_checks_exactos_y_validados"), n("test_0352_n7_fecha_adquisicion_posterior_al_corte"))),
    Mutante("M-DDL-01", "TEST", "FORCE RLS de propiedades restaurado en la misma transaccion",
            "ALTER TABLE gapto.propiedades FORCE ROW LEVEL SECURITY;\n", "",
            (n("test_0352_force_rls_restaurado"), n("test_0352_huella_d111_current"))),
    Mutante("Q-REAP", "ESCENARIO", "precheck: 0352 no se reaplica", "    IF v_n <> 0 THEN\n        RAISE EXCEPTION 'F06-01-0352 PRECHECK: 0352 ya esta aplicada",
            "    IF false THEN\n        RAISE EXCEPTION 'F06-01-0352 PRECHECK: 0352 ya esta aplicada", escenario="REAP", mensaje="0352 ya esta aplicada"),
    Mutante("Q-ROL", "ESCENARIO", "precheck: el rol de conexion debe poder asumir gapto_owner",
            "    IF NOT pg_catalog.pg_has_role(current_user, 'gapto_owner', 'SET') THEN\n", "    IF false THEN\n",
            escenario="ROL", mensaje="no puede asumir gapto_owner"),
    Mutante("Q-COLS", "ESCENARIO", "precheck: 781 columnas de partida", "    IF v_n <> 781 THEN\n", "    IF false THEN\n",
            escenario="COLS", mensaje="esperadas 781 en 0351"),
    Mutante("P-CHK", "ESCENARIO", "postcheck: los 3 CHECK nuevos validados", "    IF v_n <> 3 THEN\n", "    IF false THEN\n",
            escenario="CHK", mensaje="CHECK nuevos validados"),
    Mutante("P-FORCE", "ESCENARIO", "postcheck: propiedades con FORCE RLS",
            "    IF NOT (SELECT c.relforcerowsecurity FROM pg_catalog.pg_class c WHERE c.oid = 'gapto.propiedades'::pg_catalog.regclass) THEN\n",
            "    IF false THEN\n", escenario="FORCE", mensaje="propiedades sin FORCE RLS"),
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def escribir_atomico(ruta: pathlib.Path, datos: dict) -> None:
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ruta)


def recuperar_si_pendiente(journal: pathlib.Path) -> None:
    if journal.exists():
        j = json.loads(journal.read_text(encoding="utf-8"))
        (RAIZ / MIG).write_bytes(bytes.fromhex(j["original_hex"]))
        if sha((RAIZ / MIG).read_bytes()) != APROBADO:
            raise SystemExit("RESTAURACION FALLIDA tras journal pendiente; el journal se conserva")
        journal.unlink()
        raise SystemExit(f"NO_PASS: habia una mutacion a medias ({j['mutante']}); restaurada y verificada. Repite la tirada.")


def sin_postcheck(texto: str) -> str:
    i = texto.index(POST_INI)
    j = texto.index(POST_FIN, i) + len(POST_FIN)
    return texto[:i] + texto[j:]


class Lab:
    def __init__(self, admin: str, plantilla: str) -> None:
        self.admin, self.plantilla = admin, plantilla

    def dsn(self, db: str) -> str:
        return make_conninfo(**{**conninfo_to_dict(self.admin), "dbname": db})

    def crear(self, db: str, plantilla: str | None = None) -> str:
        with psycopg.connect(self.admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
            c.execute(f'CREATE DATABASE "{db}" TEMPLATE "{plantilla or self.plantilla}"')
        return self.dsn(db)

    def borrar(self, db: str) -> None:
        with psycopg.connect(self.admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')


def aplicar(dsn: str, texto: str) -> str | None:
    """Aplica el SQL completo; devuelve None si termina o el mensaje del error si aborta."""
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(texto)
        return None
    except psycopg.Error as exc:
        return str(exc).splitlines()[0]


def pytest_nodos(dsn: str, nodos: tuple[str, ...]) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GAPTO_")}
    env.update({"GAPTO_TEST_DATABASE_URL": dsn, "PYTHONDONTWRITEBYTECODE": "1"})
    p = subprocess.run([sys.executable, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider", "-rf"], cwd=RAIZ,
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout + p.stderr


def escenario(lab: Lab, tipo: str, texto: str) -> str | None:
    """Prepara el estado provocado del escenario, aplica `texto` (migration completa) y devuelve el error o None."""
    db = f"m0352_esc_{tipo.lower()}"
    dsn = lab.crear(db)
    try:
        if tipo == "REAP":
            original = (RAIZ / MIG).read_bytes().decode("utf-8")
            err = aplicar(dsn, original if texto is None else original)
            if err:
                return "PREPARACION: " + err
            return aplicar(dsn, texto)
        if tipo == "ROL":
            with psycopg.connect(lab.admin, autocommit=True) as c:
                c.execute("DROP ROLE IF EXISTS m0352_sin_owner")
                c.execute("CREATE ROLE m0352_sin_owner LOGIN")
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute("GRANT USAGE ON SCHEMA gapto TO m0352_sin_owner")
                c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA gapto TO m0352_sin_owner")
            dsn_rol = make_conninfo(**{**conninfo_to_dict(dsn), "user": "m0352_sin_owner"})
            return aplicar(dsn_rol, texto)
        if tipo == "COLS":
            with psycopg.connect(dsn, autocommit=True) as c:
                c.execute("ALTER TABLE gapto.tipos_hecho ADD COLUMN m0352_columna_de_mas integer")
            return aplicar(dsn, texto)
        if tipo in ("CHK", "FORCE"):
            return aplicar(dsn, texto)
        raise SystemExit(f"escenario desconocido {tipo}")
    finally:
        lab.borrar(db)
        if tipo == "ROL":
            with psycopg.connect(lab.admin, autocommit=True) as c:
                c.execute("DROP ROLE IF EXISTS m0352_sin_owner")


def variante_escenario(texto: str, tipo: str) -> str:
    """Fallo provocado que la guarda del postcheck debe detectar (CHK: un CHECK NOT VALID; FORCE: sin FORCE)."""
    if tipo == "CHK":
        a = "        OR coste_adquisicion_declarado_en >= fecha_adquisicion);\n"
        assert texto.count(a) == 1
        return texto.replace(a, "        OR coste_adquisicion_declarado_en >= fecha_adquisicion) NOT VALID;\n")
    if tipo == "FORCE":
        a = "ALTER TABLE gapto.propiedades FORCE ROW LEVEL SECURITY;\n"
        assert texto.count(a) == 1
        return texto.replace(a, "")
    return texto


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-dsn", required=True)
    ap.add_argument("--plantilla-0351", required=True)
    ap.add_argument("--diario", required=True)
    ap.add_argument("--json")
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)
    diario = pathlib.Path(a.diario).resolve()
    if diario.is_relative_to(RAIZ.resolve()):
        raise SystemExit("el diario debe vivir fuera del repositorio")
    diario.mkdir(parents=True, exist_ok=True)
    journal = diario / "journal_en_sitio.json"
    recuperar_si_pendiente(journal)
    ruta = RAIZ / MIG
    original = ruta.read_bytes()
    if sha(original) != APROBADO:
        raise SystemExit(f"NO_PASS: la migration no es la aprobada ({sha(original)})")
    texto = original.decode("utf-8")
    lab = Lab(a.admin_dsn, a.plantilla_0351)
    seleccion = [m for m in MUTANTES if not a.ids or m.ident in a.ids]
    res: dict = {"migration_sha": APROBADO, "controles": {}, "mutantes": []}

    # controles sin mutacion
    nodos_test = tuple(dict.fromkeys(d for m in seleccion if m.modo == "TEST" for d in m.discriminantes))
    if nodos_test:
        dsn = lab.crear("m0352_control")
        err = aplicar(dsn, sin_postcheck(texto))
        rc, salida = pytest_nodos(dsn, nodos_test) if err is None else (99, err)
        lab.borrar("m0352_control")
        res["controles"]["TEST"] = {"aplicada": err is None, "rc": rc, "skipped": "skipped" in salida}
        if err is not None or rc != 0 or "skipped" in salida:
            print(salida[-3000:])
            raise SystemExit("NO_PASS: el control TEST no esta verde (o tiene saltos)")
    for tipo in sorted({m.escenario for m in seleccion if m.modo == "ESCENARIO"}):
        msj = next(m.mensaje for m in MUTANTES if m.escenario == tipo)
        err = escenario(lab, tipo, variante_escenario(texto, tipo))
        ok = err is not None and msj in err
        res["controles"][tipo] = {"error": err, "aborta_con_su_guarda": ok}
        if not ok:
            raise SystemExit(f"NO_PASS: control de escenario {tipo} no aborta con su guarda: {err}")
    print("=== F03 · 0352 · MUTANTES ===  controles:", json.dumps(res["controles"], ensure_ascii=False), flush=True)

    muertos = 0
    for m in seleccion:
        if texto.count(m.viejo) != 1:
            veredicto, detalle = "INVALIDO", f"patron {texto.count(m.viejo)} veces"
        else:
            mutado = texto.replace(m.viejo, m.nuevo, 1)
            escribir_atomico(journal, {"mutante": m.ident, "original_hex": original.hex()})
            try:
                ruta.write_bytes(mutado.encode("utf-8"))
                if m.modo == "TEST":
                    dsn = lab.crear("m0352_mut")
                    err = aplicar(dsn, sin_postcheck(mutado))
                    if err is not None:
                        veredicto, detalle = "MUERTO", f"la variante sin postcheck no se aplica: {err}"
                    else:
                        rc, salida = pytest_nodos(dsn, m.discriminantes)
                        fallos = [l for l in salida.splitlines() if l.startswith("FAILED")]
                        if rc == 0:
                            veredicto, detalle = "VIVO", "ningun discriminante cae"
                        elif fallos:
                            veredicto, detalle = "MUERTO", f"fallos={len(fallos)}: " + "; ".join(f.split(" - ")[0][-90:] for f in fallos[:4])
                        else:
                            veredicto, detalle = "DUDOSO", "pytest no reporto fallos"
                    lab.borrar("m0352_mut")
                    auto = aplicar(lab.crear("m0352_auto"), mutado)
                    lab.borrar("m0352_auto")
                    detalle += f" | autocomprobacion (migration completa mutada): {'aborta: ' + auto if auto else 'NO aborta'}"
                else:
                    err = escenario(lab, m.escenario, variante_escenario(mutado, m.escenario))
                    if err is not None and m.mensaje in err:
                        veredicto, detalle = "VIVO", f"aborta igualmente con el mensaje de su guarda: {err}"
                    else:
                        veredicto, detalle = "MUERTO", f"sin el mensaje de su guarda; otra defensa: {err or 'NINGUNA (se aplica)'}"
            finally:
                ruta.write_bytes(original)
                if sha(ruta.read_bytes()) != APROBADO:
                    raise SystemExit("RESTAURACION FALLIDA: el journal se conserva para recuperar")
                journal.unlink()
        muertos += veredicto == "MUERTO"
        res["mutantes"].append({"id": m.ident, "modo": m.modo, "invariante": m.invariante, "veredicto": veredicto, "detalle": detalle})
        print(f"  {m.ident:9} {veredicto:8} [{m.invariante}] {detalle}", flush=True)
    res["resultado"] = f"{muertos}/{len(seleccion)} muertos"
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("RESULTADO:", res["resultado"])
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
