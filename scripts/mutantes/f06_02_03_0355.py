#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_02_03_0355.py
# Ruta: scripts/mutantes/f06_02_03_0355.py
# Descripcion: Mutation gate SQL de la migration 0355 (MIG-ALQ-ROLES; T3-F06 bloque 3 F06-02/03; mandato
#   v1.2 §8 y §9; contrato N1 v1.1 §IX). Catalogo CERRADO MS-01..MS-04, cada mutante con una sustitucion de
#   texto EXACTO sobre los bytes aprobados de la 0355 (el texto viejo debe aparecer UNA sola vez, o el mutante
#   es INVALIDO) y oraculo declarado en tests/database/test_050:
#     MS-01 CHECK sin AGENCIA                          -> test_0355_runtime_admite_los_seis_roles[AGENCIA]
#     MS-02 CHECK que admite un rol inventado          -> test_0355_runtime_rechaza_rol_inventado[ARRENDADOR]
#     MS-03 FORCE RLS no restaurado                    -> test_0355_force_rls_restaurado
#     MS-04 precheck sin comparar la definicion        -> test_0355_precheck_bloquea_definicion_distinta
#           literal (adicional a los tres del mandato; fail-closed del precheck, STOP 8 del contrato)
#   Los oraculos no dependen de orden ni de tiempo (fechas fijas, transacciones revertidas): una pasada por
#   mutante (L-06-T3 cond. 5 no exige tres).
#   Mecanica (motor de f06_01h_0354.py): la variante se aplica SIN su bloque de postcheck (el postcheck de
#   0355 aborta MS-01..MS-03 y no llegarian al oraculo) sobre una base NUEVA clonada de la plantilla en 0354;
#   despues corren los nodos oraculo con el fichero mutado en disco (MS-04 se ejerce por el cuerpo literal
#   que test_050 lee del fichero). Autocomprobacion informativa: la migration mutada COMPLETA sobre otra base
#   (se espera que el postcheck aborte MS-01..MS-03; MS-04 no aborta sobre una base sana, por diseno). PASS =
#   preflight verde (SHA-256 aprobado, 4 patrones aplicables, arbol limpio en la 0355, control sin mutacion:
#   0355 completa aplicada y oraculos verdes sin saltos) + todos MUERTOS.
#   Guardas D-181/D-192: E/S byte a byte; journal JSON durable (fsync + os.replace) FUERA del repositorio ANTES
#   de tocar el primer byte; journal pendiente al arrancar -> restaura, verifica SHA-256 y aborta con NO-PASS;
#   restauracion verificada tras cada mutante; veredictos a disco (JSONL con fsync) en --salida; bases
#   desechables de laboratorio en loopback (nunca proveedor: rechaza hosts no locales).
# Requisitos:
#   - Cluster PostgreSQL LOCAL desechable (p. ej. 5460, loopback) con los cinco roles de instancia (0001) y una
#     base plantilla con la cadena aplicada hasta 0354 (por defecto «ref0354»), sin conexiones abiertas (CREATE
#     DATABASE ... TEMPLATE lo exige). El arnes crea y borra m0355_ctl, m0355_mut y m0355_auto.
#   - --admin-dsn (o GAPTO_MS0355_ADMIN_URL) en formato URL postgresql://, rol con CREATEDB y con permiso para
#     asumir gapto_owner, gapto_runtime (los oraculos los usan con SET ROLE). De ella se deriva, por base,
#     GAPTO_TEST_DATABASE_URL en formato URL. El resto de GAPTO_* del entorno se retira del subproceso.
#   - APROBADO es el SHA-256 de la 0355 v0.1.0 tal como quedo preparada (paso 2, sin replay). Si el replay
#     obliga a cambiar la migration (STOP B), APROBADO y los textos de los mutantes se revisan en el mismo cambio.
# Uso:
#   python scripts/mutantes/f06_02_03_0355.py --admin-dsn "postgresql://postgres@127.0.0.1:5460/postgres"
#     --plantilla ref0354 --salida <dir_evidencia>\ms0355_<yyyyMMdd-HHmmss> [--solo MS-01 MS-03 ...]
# Version: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03 paso 2 (mandato v1.2 §8/§9; contrato v1.1 §IX)): arnes nuevo,
#   preparado y NO ejecutado (turno de noche sin clusters).
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
MIG = "migrations/0355_f06_02_03_alq_roles_participante.sql"
T050 = "tests/database/test_050_f06_02_03_0355_roles_participante.py"
APROBADO = "c6f01286b8f0ac893e014eb72429785440dfde8a9ed602471e15babc97c460e4"   # 0355 v0.1.0 (paso 2 preparado; ver NOTAS_PASO2_PREP)
POST_INI = "DO $postcheck_0355$\n"
POST_FIN = "$postcheck_0355$;\n"
HOSTS_LAB = {"127.0.0.1", "localhost", "::1"}
TIMEOUT_PYTEST = 1800


def n050(nombre: str) -> str:
    return f"{T050}::{nombre}"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    cambios: tuple[tuple[str, str], ...]   # (viejo, nuevo) en secuencia; cada viejo, una sola vez
    oraculos: tuple[str, ...]


CHECK_0355 = "        CHECK (rol IN ('PROPIETARIO','INQUILINO','AVALISTA','GESTOR','AGENCIA','ADMINISTRADOR'));\n"

MUTANTES = (
    Mutante("MS-01", "AGENCIA admitida por ck_contrato_participantes__rol",
            ((CHECK_0355, "        CHECK (rol IN ('PROPIETARIO','INQUILINO','AVALISTA','GESTOR','ADMINISTRADOR'));\n"),),
            (n050("test_0355_runtime_admite_los_seis_roles[AGENCIA]"),)),
    Mutante("MS-02", "un rol fuera de catalogo sigue rechazado",
            ((CHECK_0355, "        CHECK (rol IN ('PROPIETARIO','INQUILINO','AVALISTA','GESTOR','AGENCIA','ADMINISTRADOR',"
                          "'ARRENDADOR'));\n"),),
            (n050("test_0355_runtime_rechaza_rol_inventado[ARRENDADOR]"),)),
    Mutante("MS-03", "FORCE RLS restaurado en contrato_participantes",
            (("ALTER TABLE gapto.contrato_participantes FORCE ROW LEVEL SECURITY;\n", ""),),
            (n050("test_0355_force_rls_restaurado"),)),
    Mutante("MS-04", "precheck fail-closed: definicion vigente = literal de 0050",
            (("    ELSIF v_def IS DISTINCT FROM v_def_0354 THEN\n", "    ELSIF false THEN\n"),),
            (n050("test_0355_precheck_bloquea_definicion_distinta"),)),
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
    """La 0355 debe estar en el indice de git (si no, estado_mig no detectaria cambios locales)."""
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
    ap.add_argument("--admin-dsn", default=os.environ.get("GAPTO_MS0355_ADMIN_URL"))
    ap.add_argument("--plantilla", default="ref0354")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--solo", nargs="+", default=None)
    a = ap.parse_args(argv)
    if not a.admin_dsn:
        raise SystemExit("falta --admin-dsn (o GAPTO_MS0355_ADMIN_URL)")
    salida = pathlib.Path(a.salida).resolve()
    if salida.is_relative_to(RAIZ.resolve()):
        raise SystemExit("--salida debe vivir fuera del repositorio")
    salida.mkdir(parents=True, exist_ok=True)
    journal = salida / "journal_0355.json"
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
        raise SystemExit("NO_PASS: la 0355 no esta en el indice de git (commit del paso 2 pendiente)")
    if estado_mig():
        raise SystemExit(f"NO_PASS: la 0355 tiene cambios locales: {estado_mig().strip()}")
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
    url = lab.crear("m0355_ctl")
    try:
        err = aplicar(url, texto)
        rc, out = pytest_nodos(url, nodos) if err is None else (99, err)
    finally:
        lab.borrar("m0355_ctl")
    guardar_log(salida, "control_test_050", out)
    ok = err is None and rc == 0 and " skipped" not in out
    res["control"] = {"aplicada_completa": err is None, "rc": rc, "verde_sin_saltos": ok}
    a_disco(veredictos, {"evento": "control", **res["control"]})
    if not ok:
        print(out[-3000:])
        raise SystemExit("NO_PASS: el control no esta verde (o tiene saltos); nada se ha mutado")
    print("=== F06-02/03 · 0355 · MUTANTES SQL ===  control:", json.dumps(res["control"], ensure_ascii=False),
          flush=True)

    # ---- mutantes
    muertos = 0
    for m in seleccion:
        mutado, rec = aplicar_cambios(texto, m.cambios)
        escribir_durable(journal, {"mutante": m.ident, "original_hex": original.hex()})
        try:
            ruta.write_bytes(mutado.encode("utf-8"))
            url = lab.crear("m0355_mut")
            try:
                err = aplicar(url, sin_postcheck(mutado))
                if err is not None:
                    veredicto, detalle = "INVALIDO", f"la variante sin postcheck no se aplica: {err}"
                else:
                    rc, out = pytest_nodos(url, m.oraculos)
                    guardar_log(salida, m.ident, out)
                    veredicto, detalle = clasificar(rc, out)
            finally:
                lab.borrar("m0355_mut")
            auto_url = lab.crear("m0355_auto")
            try:
                auto = aplicar(auto_url, mutado)
            finally:
                lab.borrar("m0355_auto")
        finally:
            ruta.write_bytes(original)
            if sha(ruta.read_bytes()) != APROBADO:
                raise SystemExit("RESTAURACION FALLIDA: el journal se conserva para recuperar")
            journal.unlink()
        muertos += veredicto == "MUERTO"
        reg = {"evento": "mutante", "id": m.ident, "invariante": m.invariante, "recuentos_viejo": rec,
               "veredicto": veredicto, "detalle": detalle,
               "autocomprobacion": ("aborta: " + auto) if auto else "NO aborta (migration completa mutada)"}
        res["mutantes"].append(reg)
        a_disco(veredictos, reg)
        print(f"  {m.ident:6} {veredicto:8} [{m.invariante}] {detalle} | autocomprobacion: {reg['autocomprobacion']}",
              flush=True)

    if estado_mig():
        raise SystemExit(f"NO_PASS: la 0355 quedo con cambios tras la tirada: {estado_mig().strip()}")
    res["resultado"] = f"{muertos}/{len(seleccion)} muertos"
    res["pass"] = muertos == len(seleccion)
    escribir_durable(salida / "resultado.json", res)
    a_disco(veredictos, {"evento": "fin", "resultado": res["resultado"], "pass": res["pass"]})
    print("RESULTADO:", res["resultado"], "PASS" if res["pass"] else "NO_PASS")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
