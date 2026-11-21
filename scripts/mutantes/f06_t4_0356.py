#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_t4_0356.py
# Ruta: scripts/mutantes/f06_t4_0356.py
# Descripcion: Mutation gate SQL de la migration 0356 (F06 T4 · P-RB206-1, deduplicacion de G2 con memo de
#   transaccion; mandato MANDATO_F06-T4_G2_0356_v1.0 (753bebb2…) §3 y enmienda 01 (257be460…); ajuste 1 del
#   dictamen DICTAMEN_T4_G2_v1.0). Catalogo CERRADO MG-01..MG-06 (los seis del mandato), cada mutante con una
#   sustitucion de texto EXACTO sobre los bytes aprobados de la 0356 (el texto viejo debe aparecer UNA sola vez,
#   o el mutante es INVALIDO) y su oraculo declarado en tests/database/test_051:
#     MG-01 memo nunca invalidado                 -> test_b_immediate_valida_y_la_dml_posterior_se_rechaza_al_commit
#     MG-02 sin invalidacion de OLD               -> test_a_t3_update_mueve_cuota_old_rompe
#     MG-03 sin invalidacion de NEW               -> test_a_t3_update_mueve_cuota_new_rompe
#     MG-04 sin invalidacion en DELETE            -> test_a_t3_delete_tras_validar
#     MG-05 memo no ligado al xact id             -> test_e_guc_manual_no_valido_se_valida[otra_transaccion]
#     MG-06 GUC mal formado tratado como validado -> test_e_guc_manual_no_valido_se_valida[mal_formado]
#   Mecanica (motor de f06_02_03_0355.py): BASE LIMPIA POR MUTANTE, clonada de una plantilla con la cadena
#   aplicada hasta 0355; la migration mutada se aplica COMPLETA (los mutantes son de comportamiento: el postcheck
#   estructural de 0356 no los ve; si abortara, el mutante seria INVALIDO). Una pasada por mutante: los oraculos
#   no dependen de orden ni de tiempo (fechas fijas, transacciones revertidas o COMMIT rechazado).
#   PASS = preflight verde (SHA-256 aprobado, 6 patrones aplicables, 0356 versionada y sin cambios locales,
#   control sin mutacion: 0356 aplicada y oraculos verdes sin saltos) + todos MUERTOS.
#   Guardas D-181/D-192: E/S byte a byte; journal JSON durable (fsync + os.replace) FUERA del repositorio ANTES de
#   tocar el primer byte; journal pendiente al arrancar -> restaura, verifica SHA-256 y aborta con NO-PASS;
#   restauracion verificada tras cada mutante; veredictos a disco (JSONL con fsync) en --salida; bases
#   desechables de laboratorio en loopback (nunca proveedor: rechaza hosts no locales).
# Requisitos:
#   - Cluster PostgreSQL LOCAL desechable (loopback) con los cinco roles de instancia (0001) y una base plantilla
#     con la cadena aplicada hasta 0355, sin conexiones abiertas. El arnes crea y borra m0356_ctl y m0356_mut.
#   - --admin-dsn (o GAPTO_MG0356_ADMIN_URL) en formato URL postgresql://, rol con CREATEDB.
# Uso:
#   python scripts/mutantes/f06_t4_0356.py --admin-dsn "postgresql://postgres@127.0.0.1:5467/postgres"
#     --plantilla t4_base_0355b --salida <dir_evidencia>/mg0356_<yyyyMMdd-HHmmss> [--solo MG-01 ...]
# Version: 0.1.0 (F06 T4 P-RB206-1; mandato 753bebb2… §3 y enmienda 01 257be460…)
# ============================================================
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIG = "migrations/0356_f06_t4_g2_dedup.sql"
T051 = "tests/database/test_051_f06_t4_0356_g2_dedup.py"
APROBADO = "3b47da0ccbc79ef82aff71b3becacb4c1e0b3d0f403fa2c8bfea01db1b439668"   # 0356 v0.1.0 (commit 618ab6d)
POST_INI = "DO $postcheck_0356$\n"
POST_FIN = "$postcheck_0356$;\n"
HOSTS_LAB = {"127.0.0.1", "localhost", "::1"}
TIMEOUT_PYTEST = 1800


def n051(nombre: str) -> str:
    return f"{T051}::{nombre}"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    cambios: tuple[tuple[str, str], ...]   # (viejo, nuevo) en secuencia; cada viejo, una sola vez
    oraculos: tuple[str, ...]


ANCLA_INV = ("    v_memo := pg_catalog.current_setting('gapto_g2.validadas', true);\n"
             "    v_xid := pg_catalog.pg_current_xact_id()::text;\n"
             "    IF v_memo IS NULL OR")
ANCLA_XID = "       AND pg_catalog.split_part(v_memo, ':', 1) = v_xid THEN\n"
RX = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
BLOQUE_MEMO = ("    IF v_memo IS NOT NULL\n"
               "       AND v_memo ~ '^[0-9]+:(" + RX + "(," + RX + ")*)?$'\n"
               "       AND pg_catalog.split_part(v_memo, ':', 1) = v_xid THEN\n"
               "        v_hechas := coalesce(pg_catalog.string_to_array(pg_catalog.split_part(v_memo, ':', 2), ',')"
               "::uuid[], '{}');\n"
               "    END IF;\n")

MUTANTES = (
    Mutante("MG-01", "el memo se invalida tras la DML (mutante: memo nunca invalidado)",
            (("    v_resto uuid[];\nBEGIN\n", "    v_resto uuid[];\nBEGIN\n    RETURN NULL;\n"),),
            (n051("test_b_immediate_valida_y_la_dml_posterior_se_rechaza_al_commit"),)),
    Mutante("MG-02", "la invalidacion cubre OLD en UPDATE (mutante: sin OLD)",
            ((ANCLA_INV, "    IF TG_OP = 'UPDATE' THEN v_fs := v_fs[1:1]; END IF;\n" + ANCLA_INV),),
            (n051("test_a_t3_update_mueve_cuota_old_rompe"),)),
    Mutante("MG-03", "la invalidacion cubre NEW en INSERT y UPDATE (mutante: sin NEW)",
            ((ANCLA_INV, "    IF TG_OP = 'UPDATE' THEN v_fs := v_fs[2:2]; ELSIF TG_OP = 'INSERT' THEN v_fs := '{}'; "
                         "END IF;\n" + ANCLA_INV),),
            (n051("test_a_t3_update_mueve_cuota_new_rompe"),)),
    Mutante("MG-04", "la invalidacion cubre DELETE (mutante: sin DELETE)",
            ((ANCLA_INV, "    IF TG_OP = 'DELETE' THEN RETURN NULL; END IF;\n" + ANCLA_INV),),
            (n051("test_a_t3_delete_tras_validar"),)),
    Mutante("MG-05", "el memo esta ligado al xact id de la transaccion (mutante: no ligado)",
            ((ANCLA_XID, "       THEN\n"),),
            (n051("test_e_guc_manual_no_valido_se_valida[otra_transaccion]"),)),
    Mutante("MG-06", "un GUC mal formado no cuenta como validado (mutante: tratado como validado)",
            ((BLOQUE_MEMO, "    IF v_memo IS NOT NULL THEN\n"
                           "        v_hechas := ARRAY(SELECT (pg_catalog.regexp_matches(v_memo, '" + RX + "', 'g'))[1]::uuid);\n"
                           "    END IF;\n"),),
            (n051("test_e_guc_manual_no_valido_se_valida[mal_formado]"),)),
)


# ------------------------------------------------------------------ utilidades
def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def aplicar_cambios(texto: str, cambios: tuple[tuple[str, str], ...]) -> tuple[str | None, list[int]]:
    """Sustitucion secuencial; devuelve (mutado o None si algun viejo no aparece exactamente una vez, recuentos)."""
    recuentos = []
    for viejo, nuevo in cambios:
        k = texto.count(viejo)
        recuentos.append(k)
        if k != 1:
            return None, recuentos
        texto = texto.replace(viejo, nuevo, 1)
    return texto, recuentos


def escribir_durable(ruta: pathlib.Path, datos: dict) -> None:
    tmp = ruta.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(datos, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)


def a_disco(ruta: pathlib.Path, registro: dict) -> None:
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def recuperar_si_pendiente(journal: pathlib.Path) -> None:
    if journal.exists():
        j = json.loads(journal.read_text(encoding="utf-8"))
        (RAIZ / MIG).write_bytes(bytes.fromhex(j["original_hex"]))
        if sha((RAIZ / MIG).read_bytes()) != APROBADO:
            raise SystemExit("RESTAURACION FALLIDA tras journal pendiente; el journal se conserva")
        journal.unlink()
        raise SystemExit(f"NO_PASS: habia una mutacion a medias ({j['mutante']}); restaurada y verificada. "
                         "Repite la tirada.")


def sin_postcheck(texto: str) -> str:
    i = texto.index(POST_INI)
    j = texto.index(POST_FIN, i) + len(POST_FIN)
    return texto[:i] + texto[j:]


def estado_mig() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--", MIG], cwd=RAIZ, capture_output=True,
                          text=True).stdout


def mig_versionada() -> bool:
    """La 0356 debe estar en el indice de git (si no, estado_mig no detectaria cambios locales)."""
    return subprocess.run(["git", "ls-files", "--error-unmatch", "--", MIG], cwd=RAIZ, capture_output=True,
                          text=True).returncode == 0


class Lab:
    def __init__(self, admin: str, plantilla: str) -> None:
        p = urlsplit(admin)
        if p.scheme not in ("postgresql", "postgres"):
            raise SystemExit("--admin-dsn debe ser una URL postgresql:// (formato URL para los oraculos)")
        if (p.hostname or "") not in HOSTS_LAB:
            raise SystemExit(f"host {p.hostname!r} no es de laboratorio local; el arnes nunca apunta a proveedor")
        self.admin, self.plantilla = admin, plantilla

    def url(self, db: str) -> str:
        p = urlsplit(self.admin)
        return urlunsplit((p.scheme, p.netloc, "/" + db, p.query, ""))

    def crear(self, db: str) -> str:
        import psycopg
        with psycopg.connect(self.admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
            c.execute(f'CREATE DATABASE "{db}" TEMPLATE "{self.plantilla}"')
        return self.url(db)

    def borrar(self, db: str) -> None:
        import psycopg
        with psycopg.connect(self.admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')


def aplicar(url: str, texto: str) -> str | None:
    """Aplica el SQL completo; None si termina, o la primera linea del error si aborta."""
    import psycopg
    try:
        with psycopg.connect(url, autocommit=True) as c:
            c.execute(texto)
        return None
    except psycopg.Error as exc:
        return str(exc).splitlines()[0]


def pytest_nodos(url: str, nodos: tuple[str, ...]) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GAPTO_")}
    env.update({"GAPTO_TEST_DATABASE_URL": url, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider", "-rfEs"],
                           cwd=RAIZ, capture_output=True, text=True, env=env, timeout=TIMEOUT_PYTEST)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, f"TIMEOUT {TIMEOUT_PYTEST}s\n{exc.stdout or ''}{exc.stderr or ''}"


def clasificar(rc: int, salida: str) -> tuple[str, str]:
    fallos = [l for l in salida.splitlines() if l.startswith(("FAILED", "ERROR"))]
    if rc == 0 and " skipped" not in salida:
        return "VIVO", "ningun oraculo cae"
    if rc == 0:
        return "DUDOSO", "verde con saltos (el oraculo no se ejecuto)"
    if rc == 124:
        return "DUDOSO", "timeout del oraculo"
    if fallos:
        return "MUERTO", f"fallos={len(fallos)}: " + "; ".join(f.split(" - ")[0][-90:] for f in fallos[:6])
    return "DUDOSO", f"pytest rc={rc} sin FAILED/ERROR"


def guardar_log(salida_dir: pathlib.Path, nombre: str, texto: str) -> None:
    with open(salida_dir / f"{nombre}.log", "w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())


# ------------------------------------------------------------------ principal
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--admin-dsn", default=os.environ.get("GAPTO_MG0356_ADMIN_URL"))
    ap.add_argument("--plantilla", default="t4_base_0355b")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--solo", nargs="+", default=None)
    a = ap.parse_args(argv)
    if not a.admin_dsn:
        raise SystemExit("falta --admin-dsn (o GAPTO_MG0356_ADMIN_URL)")
    salida = pathlib.Path(a.salida).resolve()
    if salida.is_relative_to(RAIZ.resolve()):
        raise SystemExit("--salida debe vivir fuera del repositorio")
    salida.mkdir(parents=True, exist_ok=True)
    journal = salida / "journal_0356.json"
    veredictos = salida / "veredictos.jsonl"
    recuperar_si_pendiente(journal)

    ids = {m.ident for m in MUTANTES}
    if a.solo and set(a.solo) - ids:
        raise SystemExit(f"--solo con identificadores desconocidos: {sorted(set(a.solo) - ids)}")
    seleccion = [m for m in MUTANTES if not a.solo or m.ident in a.solo]

    # ---- preflight (nada se muta si algo no esta verde)
    ruta = RAIZ / MIG
    original = ruta.read_bytes()
    if sha(original) != APROBADO:
        raise SystemExit(f"NO_PASS: la migration no es la aprobada ({sha(original)})")
    if not mig_versionada():
        raise SystemExit("NO_PASS: la 0356 no esta en el indice de git")
    if estado_mig():
        raise SystemExit(f"NO_PASS: la 0356 tiene cambios locales: {estado_mig().strip()}")
    texto = original.decode("utf-8")
    malos = []
    for m in seleccion:
        mutado, rec = aplicar_cambios(texto, m.cambios)
        if mutado is None or mutado == texto:
            malos.append(f"{m.ident}: recuentos {rec}")
    if malos:
        raise SystemExit("NO_PASS: patrones no aplicables: " + " | ".join(malos))
    lab = Lab(a.admin_dsn, a.plantilla)
    res: dict = {"migration_sha": APROBADO, "plantilla": a.plantilla, "control": {}, "mutantes": []}
    a_disco(veredictos, {"evento": "inicio", "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
                         "seleccion": [m.ident for m in seleccion]})

    nodos = tuple(dict.fromkeys(o for m in seleccion for o in m.oraculos))
    url = lab.crear("m0356_ctl")
    try:
        err = aplicar(url, texto)
        rc, out = pytest_nodos(url, nodos) if err is None else (99, err)
    finally:
        lab.borrar("m0356_ctl")
    guardar_log(salida, "control_test_051", out)
    ok = err is None and rc == 0 and " skipped" not in out
    res["control"] = {"aplicada_completa": err is None, "rc": rc, "verde_sin_saltos": ok}
    a_disco(veredictos, {"evento": "control", **res["control"]})
    if not ok:
        print(out[-3000:])
        raise SystemExit("NO_PASS: el control no esta verde (o tiene saltos); nada se ha mutado")
    print("=== F06 T4 · 0356 · MUTANTES SQL ===  control:", json.dumps(res["control"], ensure_ascii=False),
          flush=True)

    # ---- mutantes
    muertos = 0
    for m in seleccion:
        mutado, rec = aplicar_cambios(texto, m.cambios)
        escribir_durable(journal, {"mutante": m.ident, "original_hex": original.hex()})
        try:
            ruta.write_bytes(mutado.encode("utf-8"))
            url = lab.crear("m0356_mut")
            try:
                err = aplicar(url, mutado)
                if err is not None:
                    veredicto, detalle = "INVALIDO", f"la migration mutada no se aplica: {err}"
                else:
                    rc, out = pytest_nodos(url, m.oraculos)
                    guardar_log(salida, m.ident, out)
                    veredicto, detalle = clasificar(rc, out)
            finally:
                lab.borrar("m0356_mut")
        finally:
            ruta.write_bytes(original)
            if sha(ruta.read_bytes()) != APROBADO:
                raise SystemExit("RESTAURACION FALLIDA: el journal se conserva para recuperar")
            journal.unlink()
        muertos += veredicto == "MUERTO"
        reg = {"evento": "mutante", "id": m.ident, "invariante": m.invariante, "recuentos_viejo": rec,
               "veredicto": veredicto, "detalle": detalle, "oraculos": list(m.oraculos)}
        res["mutantes"].append(reg)
        a_disco(veredictos, reg)
        print(f"  {m.ident:6} {veredicto:8} [{m.invariante}] {detalle}", flush=True)

    if estado_mig():
        raise SystemExit(f"NO_PASS: la 0356 quedo con cambios tras la tirada: {estado_mig().strip()}")
    res["resultado"] = f"{muertos}/{len(seleccion)} muertos"
    res["pass"] = muertos == len(seleccion)
    escribir_durable(salida / "resultado.json", res)
    a_disco(veredictos, {"evento": "fin", "resultado": res["resultado"], "pass": res["pass"]})
    print("RESULTADO:", res["resultado"], "PASS" if res["pass"] else "NO_PASS")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
