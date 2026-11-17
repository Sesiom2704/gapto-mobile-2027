#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_01h_0354.py
# Ruta: scripts/mutantes/f06_01h_0354.py
# Descripcion: Mutation gate SQL de la migration 0354 (MIG-HIP-GAR; T3-F06 bloque 2 F06-01H; mandato v1.1
#   §12.1/§12.2; contrato v0.4 §10.1.7). Catalogo CERRADO MS-01..MS-16, cada mutante con una o varias
#   sustituciones de texto EXACTO aplicadas en secuencia sobre los bytes aprobados de la 0354 (cada texto viejo
#   debe aparecer UNA sola vez en el texto vigente en ese momento, o el mutante es INVALIDO) y oraculo declarado:
#     MS-01 sin T4 (P cambia sin tocar cuotas)            -> B-G2-01
#     MS-02 sin T3                                         -> B-G2-03
#     MS-03 G2 sin comprobacion de numeracion              -> B-G2-04
#     MS-04 G2 con capital NULL aceptado                   -> B-G2-02
#     MS-05 G1 con prevision_id NULL editable              -> B-G1-02
#     MS-06 G1 que solo rechaza REALIZADA                  -> B-G1-03
#     MS-07 G1 sin inmutabilidad de prevision_id           -> B-G1-04
#     MS-08 sin T2 (G1-R)                                  -> B-G1R-01
#     MS-09 sin T6 (G2-E)                                  -> B-G2E-01
#     MS-10 sin T5                                         -> B-G2-05
#     MS-11 G2 sin el lock de la financiacion              -> IC-12 (3 pasadas; MUERTO solo si muere en las 3)
#     MS-12 G3 que admite un segundo cambio de vigencia    -> B-G3-02
#     MS-13 G3 que solo mira vigente_hasta                 -> B-G3-03
#     MS-14 G2 ampliada a toda financiacion con cuotas     -> N-01
#     MS-15 G3 ampliada a toda version                     -> N-02
#     MS-16 G1-R ampliada a toda prevision                 -> N-04
#   Mecanica (motor de f03_06_0352.py): la variante se aplica SIN su bloque de postcheck (los mutantes que
#   retiran triggers romperian PO-02/PO-04 y no llegarian al oraculo) sobre una base NUEVA clonada de la
#   plantilla en 0353; despues corren los nodos oraculo. Autocomprobacion informativa: la migration mutada
#   COMPLETA sobre otra base (se registra si el postcheck la aborta). PASS = preflight verde (SHA-256 aprobado,
#   16 patrones aplicables, arbol limpio en la 0354, control sin mutacion: 0354 completa aplicada y oraculos
#   verdes sin saltos) + todos MUERTOS.
#   Guardas D-181/D-192: E/S byte a byte; journal JSON durable (fsync + os.replace) FUERA del repositorio ANTES
#   de tocar el primer byte; journal pendiente al arrancar -> restaura, verifica SHA-256 y aborta con NO-PASS;
#   restauracion verificada tras cada mutante; veredictos a disco (JSONL con fsync) en --salida; bases
#   desechables de laboratorio en loopback (nunca proveedor: rechaza hosts no locales).
# Requisitos:
#   - Cluster PostgreSQL LOCAL desechable (p. ej. 5460, loopback) con los cinco roles de instancia (0001) y una
#     base plantilla con la cadena aplicada hasta 0353 (por defecto «ref0353»), sin conexiones abiertas (CREATE
#     DATABASE ... TEMPLATE lo exige). El arnes crea y borra m0354_ctl, m0354_mut y m0354_auto.
#   - --admin-dsn (o GAPTO_MS0354_ADMIN_URL) en formato URL postgresql://, rol superusuario (la 0354 exige
#     BYPASSRLS en PC-01 y los oraculos de tests/api leen pg_locks/pg_stat_activity). De ella se deriva, por
#     base, GAPTO_TEST_DATABASE_URL en formato URL (tests/api lo exige; el formato clave=valor rompe test_160).
#   - Para MS-11 el arnes fija en el subproceso GAPTO_F06HIP_CONCURRENCIA=1 (sin ella IC-12 se salta y el
#     control falla) y GAPTO_F06HIP_EVIDENCIA=<salida>/<id>_pasadaN (JSON por caso). El resto de GAPTO_* del
#     entorno se retira del subproceso.
# Uso:
#   python scripts/mutantes/f06_01h_0354.py --admin-dsn "postgresql://postgres@127.0.0.1:5460/postgres"
#     --plantilla ref0353 --salida C:\DEV\evidencia_<bloque>\ms0354_<yyyyMMdd-HHmmss> [--solo MS-01 MS-11 ...]
# Version: 0.1.0 (T3-F06 F06-01H paso 12 (mandato v1.1 §12.1/§12.2; contrato v0.4 §10.1.7))
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
MIG = "migrations/0354_f06_01h_garantias_hipoteca.sql"
T049 = "tests/database/test_049_f06_01h_0354_garantias.py"
T295 = "tests/api/test_295_f06_01h_concurrencia_serial.py"
APROBADO = "503018f2ab35a8ea9c60a3e21cb347bbd89b1e2cf11f82b2c83e84d342130c11"   # 0354 v0.1.1 (HEAD 814b0d2)
POST_INI = "DO $postcheck_0354$\n"
POST_FIN = "$postcheck_0354$;\n"
HOSTS_LAB = {"127.0.0.1", "localhost", "::1"}
TIMEOUT_PYTEST = 3600


def n049(nombre: str) -> str:
    return f"{T049}::{nombre}"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    cambios: tuple[tuple[str, str], ...]   # (viejo, nuevo) en secuencia; cada viejo, una sola vez
    oraculos: tuple[str, ...]
    pasadas: int = 1                        # MS-11: 3 (MUERTO solo si muere en todas)
    concurrencia: bool = False              # oraculo en tests/api con GAPTO_F06HIP_CONCURRENCIA=1


def _trigger(nombre: str, cuerpo: str) -> str:
    return f"CREATE CONSTRAINT TRIGGER {nombre}\n{cuerpo}"


T3 = _trigger("trg_financiacion_cuotas__cuadro_hipoteca",
              "    AFTER INSERT OR UPDATE OF capital_previsto, numero_cuota, financiacion_entidad_id OR DELETE\n"
              "    ON gapto.financiacion_cuotas\n"
              "    DEFERRABLE INITIALLY DEFERRED\n"
              "    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cuadro_hipoteca();\n\n")
T4 = _trigger("trg_financiaciones__cuadro_hipoteca",
              "    AFTER UPDATE OF capital_original_contratado, tipo_financiacion\n"
              "    ON gapto.financiaciones\n"
              "    DEFERRABLE INITIALLY DEFERRED\n"
              "    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cuadro_hipoteca();\n\n")
T5 = _trigger("trg_financiacion_condiciones_versiones__cuadro_hipoteca",
              "    AFTER INSERT OR UPDATE OF motivo_version, hecho_causa_id, financiacion_entidad_id\n"
              "    ON gapto.financiacion_condiciones_versiones\n"
              "    DEFERRABLE INITIALLY DEFERRED\n"
              "    FOR EACH ROW EXECUTE FUNCTION gapto.fn_check_cuadro_hipoteca();\n\n")
T2 = ("CREATE TRIGGER trg_previsiones__cuota_no_reabrible\n"
      "    BEFORE UPDATE OF estado ON gapto.previsiones\n"
      "    FOR EACH ROW\n"
      "    WHEN (OLD.estado <> 'ABIERTA' AND NEW.estado = 'ABIERTA')\n"
      "    EXECUTE FUNCTION gapto.fn_guard_prevision_cuota_no_reabrible();\n")
T6 = ("CREATE TRIGGER trg_financiaciones__ambito_hipoteca\n"
      "    BEFORE UPDATE OF tipo_financiacion ON gapto.financiaciones\n"
      "    FOR EACH ROW\n"
      "    WHEN (OLD.tipo_financiacion = 'HIPOTECA' AND NEW.tipo_financiacion <> 'HIPOTECA')\n"
      "    EXECUTE FUNCTION gapto.fn_guard_financiacion_ambito_hipoteca();\n")
G2_NUMERACION = ("        IF NOT (v_r.mn = 1 AND v_r.mx = v_r.n AND v_r.nd = v_r.n) THEN\n"
                 "            RAISE EXCEPTION 'INV-0354-G2: la numeracion de las cuotas de la hipoteca % no es 1..%', "
                 "v_r.entidad_id, v_r.n;\n"
                 "        END IF;\n")
G3_PRIMER_CIERRE = "        IF NOT (OLD.vigente_hasta IS NULL AND NEW.vigente_hasta IS NOT NULL) THEN\n"
G3_RESTO_COLUMNAS = ("        IF (pg_catalog.to_jsonb(NEW) - 'vigente_hasta') IS DISTINCT FROM "
                     "(pg_catalog.to_jsonb(OLD) - 'vigente_hasta') THEN\n"
                     "            RAISE EXCEPTION 'INV-0354-G3: la version % de una hipoteca con cuadro calculado es "
                     "historica; solo cambia vigente_hasta', OLD.id;\n"
                     "        END IF;\n")
G3_AMBITO_M = ("    IF EXISTS (SELECT 1 FROM gapto.financiaciones f\n"
               "                WHERE f.entidad_id = OLD.financiacion_entidad_id\n"
               "                  AND f.tipo_financiacion = 'HIPOTECA'\n"
               "                  AND EXISTS (SELECT 1 FROM gapto.financiacion_condiciones_versiones v\n"
               "                               WHERE v.financiacion_entidad_id = f.entidad_id\n"
               "                                 AND v.motivo_version = 'ALTA'\n"
               "                                 AND v.hecho_causa_id IS NOT NULL)) THEN\n")

MUTANTES = (
    Mutante("MS-01", "G2 dispara al cambiar P sin tocar cuotas (T4)", ((T4, ""),),
            (n049("test_b_g2_01_modificar_p_sin_tocar_cuotas"),)),
    Mutante("MS-02", "G2 dispara al cambiar cuotas (T3)", ((T3, ""),),
            (n049("test_b_g2_03_capital_de_cuota_abierta_rompe_suma"),)),
    Mutante("MS-03", "G2 exige numeracion exactamente 1..N", ((G2_NUMERACION, ""),),
            (n049("test_b_g2_04_cuota_duplicada_capital_cero"),)),
    Mutante("MS-04", "G2 rechaza capital NULL en H",
            (("        IF v_r.capital IS NULL OR v_r.capital <= 0 THEN\n", "        IF v_r.capital <= 0 THEN\n"),),
            (n049("test_b_g2_02_p_a_null"),)),
    Mutante("MS-05", "G1: prevision_id NULL bloquea la cuota",
            (("        RAISE EXCEPTION 'INV-0354-G1: la cuota % no tiene prevision; su cuadro no se modifica', OLD.id;\n",
              "        RETURN NEW;\n"),),
            (n049("test_b_g1_02_cuota_sin_prevision"),)),
    Mutante("MS-06", "G1 rechaza toda prevision no ABIERTA (no solo REALIZADA)",
            (("    IF v_estado <> 'ABIERTA' THEN\n", "    IF v_estado = 'REALIZADA' THEN\n"),),
            (n049("test_b_g1_03_cuota_con_prevision_omitida_o_cancelada"),)),
    Mutante("MS-07", "G1: prevision_id inmutable",
            (("    IF NEW.prevision_id IS DISTINCT FROM OLD.prevision_id\n"
              "       OR NEW.financiacion_entidad_id IS DISTINCT FROM OLD.financiacion_entidad_id THEN\n",
              "    IF NEW.financiacion_entidad_id IS DISTINCT FROM OLD.financiacion_entidad_id THEN\n"),),
            (n049("test_b_g1_04_cambio_de_prevision_en_cuota_abierta"),)),
    Mutante("MS-08", "G1-R presente (T2)", ((T2, ""),),
            (n049("test_b_g1r_01_reabrir_prevision_de_cuota"),)),
    Mutante("MS-09", "G2-E presente (T6)", ((T6, ""),),
            (n049("test_b_g2e_01_hipoteca_a_prestamo_con_cuotas"),)),
    Mutante("MS-10", "G2 dispara al nacer M (T5)", ((T5, ""),),
            (n049("test_b_g2_05_version_alta_con_hecho_sin_cuotas"),)),
    Mutante("MS-11", "G2 bloquea la financiacion FOR NO KEY UPDATE antes de releer",
            (("      ORDER BY f.entidad_id\n        FOR NO KEY UPDATE;\n", "      ORDER BY f.entidad_id;\n"),),
            (f"{T295}::test_ic12_update_de_capital_frente_a_revision",
             f"{T295}::test_ic12b_cuota_de_mas_concurrente_numeracion"), pasadas=3, concurrencia=True),
    Mutante("MS-12", "G3: solo el primer cierre de vigente_hasta",
            ((G3_PRIMER_CIERRE, "        IF OLD.vigente_hasta IS NULL AND NEW.vigente_hasta IS NULL THEN\n"),),
            (n049("test_b_g3_02_segundo_cambio_de_vigencia"),)),
    Mutante("MS-13", "G3: las demas columnas de la version no cambian",
            ((G3_PRIMER_CIERRE, "        IF NEW.vigente_hasta IS DISTINCT FROM OLD.vigente_hasta\n"
                                "           AND NOT (OLD.vigente_hasta IS NULL AND NEW.vigente_hasta IS NOT NULL) THEN\n"),
             (G3_RESTO_COLUMNAS, "")),
            (n049("test_b_g3_03_cambio_de_condicion_historica"),)),
    Mutante("MS-14", "G2: ambito solo HIPOTECA",
            (("           AND f.tipo_financiacion = 'HIPOTECA' AND (\n", "           AND (\n"),),
            (n049("test_n_01_prestamo_con_cuotas_y_suma_distinta"),)),
    Mutante("MS-15", "G3: ambito solo M", ((G3_AMBITO_M, "    IF true THEN\n"),),
            (n049("test_n_02_version_fuera_de_m"),)),
    Mutante("MS-16", "G1-R: ambito solo previsiones de cuota",
            (("    IF EXISTS (SELECT 1 FROM gapto.financiacion_cuotas q WHERE q.prevision_id = OLD.id) THEN\n",
              "    IF true THEN\n"),),
            (n049("test_n_04_prevision_de_regla_reabierta"),)),
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


class Lab:
    def __init__(self, admin: str, plantilla: str) -> None:
        p = urlsplit(admin)
        if p.scheme not in ("postgresql", "postgres"):
            raise SystemExit("--admin-dsn debe ser una URL postgresql:// (tests/api exige formato URL)")
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


def pytest_nodos(url: str, nodos: tuple[str, ...], concurrencia: bool, evidencia: pathlib.Path | None) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GAPTO_")}
    env.update({"GAPTO_TEST_DATABASE_URL": url, "PYTHONDONTWRITEBYTECODE": "1"})
    extra = []
    if concurrencia:
        env["GAPTO_F06HIP_CONCURRENCIA"] = "1"
        if evidencia is not None:
            env["GAPTO_F06HIP_EVIDENCIA"] = str(evidencia)
        extra = ["--rootdir=tests/api"]
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider", "-rfEs", *extra],
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
    ap.add_argument("--admin-dsn", default=os.environ.get("GAPTO_MS0354_ADMIN_URL"))
    ap.add_argument("--plantilla", default="ref0353")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--solo", nargs="+", default=None)
    a = ap.parse_args(argv)
    if not a.admin_dsn:
        raise SystemExit("falta --admin-dsn (o GAPTO_MS0354_ADMIN_URL)")
    salida = pathlib.Path(a.salida).resolve()
    if salida.is_relative_to(RAIZ.resolve()):
        raise SystemExit("--salida debe vivir fuera del repositorio")
    salida.mkdir(parents=True, exist_ok=True)
    journal = salida / "journal_0354.json"
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
    if estado_mig():
        raise SystemExit(f"NO_PASS: la 0354 tiene cambios locales: {estado_mig().strip()}")
    texto = original.decode("utf-8")
    malos = []
    for m in seleccion:
        mutado, rec = aplicar_cambios(texto, m.cambios)
        if mutado is None or mutado == texto:
            malos.append(f"{m.ident}: recuentos {rec}")
    if malos:
        raise SystemExit("NO_PASS: patrones no aplicables: " + " | ".join(malos))
    lab = Lab(a.admin_dsn, a.plantilla)
    res: dict = {"migration_sha": APROBADO, "plantilla": a.plantilla, "controles": {}, "mutantes": []}
    a_disco(veredictos, {"evento": "inicio", "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "seleccion": [m.ident for m in seleccion]})

    for conc in (False, True):
        nodos = tuple(dict.fromkeys(o for m in seleccion if m.concurrencia == conc for o in m.oraculos))
        if not nodos:
            continue
        clave = "IC-12" if conc else "test_049"
        url = lab.crear("m0354_ctl")
        try:
            err = aplicar(url, texto)
            rc, out = (pytest_nodos(url, nodos, conc, salida / f"control_{clave}") if err is None else (99, err))
        finally:
            lab.borrar("m0354_ctl")
        guardar_log(salida, f"control_{clave}", out)
        ok = err is None and rc == 0 and " skipped" not in out
        res["controles"][clave] = {"aplicada_completa": err is None, "rc": rc, "verde_sin_saltos": ok}
        a_disco(veredictos, {"evento": "control", "clave": clave, **res["controles"][clave]})
        if not ok:
            print(out[-3000:])
            raise SystemExit(f"NO_PASS: el control {clave} no esta verde (o tiene saltos); nada se ha mutado")
    print("=== F06-01H · 0354 · MUTANTES SQL ===  controles:", json.dumps(res["controles"], ensure_ascii=False), flush=True)

    # ---- mutantes
    muertos = 0
    for m in seleccion:
        mutado, rec = aplicar_cambios(texto, m.cambios)
        pasadas: list[dict] = []
        escribir_durable(journal, {"mutante": m.ident, "original_hex": original.hex()})
        try:
            ruta.write_bytes(mutado.encode("utf-8"))
            for k in range(1, m.pasadas + 1):
                url = lab.crear("m0354_mut")
                try:
                    err = aplicar(url, sin_postcheck(mutado))
                    if err is not None:
                        v, d = "INVALIDO", f"la variante sin postcheck no se aplica: {err}"
                    else:
                        rc, out = pytest_nodos(url, m.oraculos, m.concurrencia, salida / f"{m.ident}_pasada{k}")
                        guardar_log(salida, f"{m.ident}_pasada{k}", out)
                        v, d = clasificar(rc, out)
                finally:
                    lab.borrar("m0354_mut")
                pasadas.append({"pasada": k, "veredicto": v, "detalle": d})
                a_disco(veredictos, {"evento": "pasada", "id": m.ident, "pasada": k, "veredicto": v, "detalle": d})
                print(f"  {m.ident} pasada {k}/{m.pasadas}: {v} {d}", flush=True)
            auto_url = lab.crear("m0354_auto")
            try:
                auto = aplicar(auto_url, mutado)
            finally:
                lab.borrar("m0354_auto")
        finally:
            ruta.write_bytes(original)
            if sha(ruta.read_bytes()) != APROBADO:
                raise SystemExit("RESTAURACION FALLIDA: el journal se conserva para recuperar")
            journal.unlink()
        if all(p["veredicto"] == "MUERTO" for p in pasadas):
            veredicto = "MUERTO"
        elif any(p["veredicto"] == "INVALIDO" for p in pasadas):
            veredicto = "INVALIDO"
        elif any(p["veredicto"] == "VIVO" for p in pasadas):
            veredicto = "VIVO"
        else:
            veredicto = "DUDOSO"
        muertos += veredicto == "MUERTO"
        reg = {"evento": "mutante", "id": m.ident, "invariante": m.invariante, "recuentos_viejo": rec,
               "veredicto": veredicto, "pasadas": pasadas,
               "autocomprobacion": ("aborta: " + auto) if auto else "NO aborta (migration completa mutada)"}
        res["mutantes"].append(reg)
        a_disco(veredictos, reg)
        print(f"  {m.ident:6} {veredicto:8} [{m.invariante}] autocomprobacion: {reg['autocomprobacion']}", flush=True)

    if estado_mig():
        raise SystemExit(f"NO_PASS: la 0354 quedo con cambios tras la tirada: {estado_mig().strip()}")
    res["resultado"] = f"{muertos}/{len(seleccion)} muertos"
    res["pass"] = muertos == len(seleccion)
    escribir_durable(salida / "resultado.json", res)
    a_disco(veredictos, {"evento": "fin", "resultado": res["resultado"], "pass": res["pass"]})
    print("RESULTADO:", res["resultado"], "PASS" if res["pass"] else "NO_PASS")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
