#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: lanzador_gate.py
# Ruta: scripts/gates/lanzador_gate.py
# Descripcion: Lanzador N1 de gates (Paso 0 del N1 de 0352; AJ-B1C-07, C1 del
#   dictamen de cierre de B1 v1.1; AJ-MOP21C-09; R-L19-C-01). Ejecuta en serie
#   los pasos de un plan JSON sobre una COPIA INMUTABLE del commit y registra
#   el resultado real de cada uno. Cubre los diez puntos de C1:
#   1) rc de cada ejecutable tomado del propio proceso (subprocess), nunca de
#      un comando posterior (`date` incluido);
#   2) resultado separado por tipo de paso: pytest (rc + resumen junit, y
#      coherencia entre ambos), script (rc) y verificacion (rc);
#   3) copia del commit con `git archive` (incluye mobile/), comprobada blob a
#      blob contra `git ls-tree` antes de ejecutar nada;
#   4) integridad de la copia (sha256, tamano y mtime por fichero) antes y
#      despues de CADA paso; __pycache__, *.pyc y .pytest_cache excluidos (se
#      fuerza PYTHONDONTWRITEBYTECODE=1 y -p no:cacheprovider);
#   5) si cambia el codigo bajo prueba: EJECUCION INVALIDADA (marcador
#      EJECUCION_INVALIDADA.txt), parada inmediata, nunca evidencia valida;
#   6) cerrojo de arneses de mutantes: rechaza arrancar (y parar entre pasos)
#      si hay un journal o marcador de arnes en la raiz de cualquier worktree
#      del repositorio (.mutante*_en_curso, .mutantes_*.journal*,
#      scripts/mutantes/*.journal*, .mutante_activo*) o en los directorios de
#      diario declarados (journal_en_sitio.json, *.journal*), que son los que
#      usan los arneses que escriben el journal FUERA del repositorio
#      (scripts/mutantes/f03_06_035x.py --diario);
#   7) nunca sobrescribe evidencia: la carpeta de salida no puede existir con
#      contenido; resultado.json, tiempos.txt, logs y junit por paso;
#   8) sustituye a la plantilla local defectuosa (rc de `date` en los pasos
#      replay y completar): ver plantilla_gate_local.sh;
#   9) sus pruebas negativas reales estan en tests/gates/test_lanzador_gate.py;
#   10) la revision del parche va en el cierre independiente de 0352.
#   Variables con secretos (DSN): se pasan por nombre en "heredar" y se toman
#   del entorno del proceso; su valor nunca se escribe en la evidencia.
# Uso:
#   python scripts/gates/lanzador_gate.py --plan plan.json --salida <dir_nuevo>
#   Plan: {"repo": ruta, "commit": sha, "diarios": [dirs], "ignorar": [globs],
#          "pasos": [{"etiqueta", "tipo": pytest|script|verificacion,
#                     "args": [...], "env": {...}, "heredar": [...],
#                     "parar_si_falla": bool}]}
#   En args y env, {COPIA} y {SALIDA} se sustituyen por las rutas reales.
#   Codigos de salida: 0 VERDE, 1 ROJO, 2 INVALIDADA, 3 STOP_CERROJO, 4 error
#   de preparacion (plan, copia o salida).
# Version: 0.1.0 (F03 · N1 de 0352, Paso 0)
# Version: 0.1.1 (Paso 0, prueba real 2): un plan ilegible sale con 4 (preparacion) y sin crear la salida; antes
#   salia con traza y codigo 1, el mismo que ROJO.
# ============================================================
from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

EXCLUIR_DIRS = {"__pycache__", ".pytest_cache"}
ENTORNO_FUERA = ("PGOPTIONS", "PGPASSWORD")
PATRONES_RAIZ = (".mutante*_en_curso*", ".mutantes_*.journal*", ".mutante_activo*")
PATRONES_DIARIO = ("journal_en_sitio.json", "*.journal*")


def ahora() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


class Registro:
    def __init__(self, salida: pathlib.Path) -> None:
        self.salida = salida
        self.tiempos = salida / "tiempos.txt"

    def linea(self, texto: str) -> None:
        with self.tiempos.open("a", encoding="utf-8", newline="\n") as f:
            f.write(texto + "\n")


# ---------------------------------------------------------------- cerrojo (punto 6)
def worktrees(repo: pathlib.Path) -> list[pathlib.Path]:
    r = subprocess.run(["git", "-C", str(repo), "worktree", "list", "--porcelain"], capture_output=True, text=True)
    rutas = [pathlib.Path(l[len("worktree "):]) for l in r.stdout.splitlines() if l.startswith("worktree ")]
    return rutas or [repo]


def cerrojo(repo: pathlib.Path, diarios: list[str]) -> list[str]:
    activos: list[str] = []
    for w in worktrees(repo):
        if not w.exists():
            continue
        for pat in PATRONES_RAIZ:
            activos += [str(p) for p in w.glob(pat)]
        activos += [str(p) for p in (w / "scripts" / "mutantes").glob("*.journal*")]
    for d in diarios:
        dd = pathlib.Path(d)
        if dd.exists():
            for pat in PATRONES_DIARIO:
                activos += [str(p) for p in dd.glob(pat)]
    return sorted(set(activos))


# ---------------------------------------------------------------- copia inmutable (puntos 3 y 4)
def blob_sha1(datos: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(datos) + datos).hexdigest()


def crear_copia(repo: pathlib.Path, commit: str, destino: pathlib.Path) -> dict:
    # sin conversion de finales de linea: la copia debe ser byte a byte el blob (la config global puede tener autocrlf=true)
    arch = subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", "archive", "--format=tar", commit], capture_output=True)
    if arch.returncode != 0:
        raise RuntimeError(f"git archive rc={arch.returncode}: {arch.stderr.decode(errors='replace')[:300]}")
    destino.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as tf:
        tf.extractall(destino, filter="data")
    arbol = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "-z", commit], capture_output=True)
    if arbol.returncode != 0:
        raise RuntimeError("git ls-tree fallo")
    esperados = {}
    for ent in arbol.stdout.split(b"\0"):
        if not ent:
            continue
        meta, ruta = ent.split(b"\t", 1)
        modo, tipo, obj = meta.split()
        if tipo != b"blob":
            raise RuntimeError(f"entrada no soportada en la copia: {ruta!r} ({tipo!r})")
        esperados[ruta.decode("utf-8")] = obj.decode()
    distintos = []
    for ruta, obj in esperados.items():
        f = destino / ruta
        if not f.is_file() or blob_sha1(f.read_bytes()) != obj:
            distintos.append(ruta)
    sobrantes = [str(p.relative_to(destino)).replace(os.sep, "/") for p in destino.rglob("*") if p.is_file()
                 and str(p.relative_to(destino)).replace(os.sep, "/") not in esperados]
    if distintos or sobrantes:
        raise RuntimeError(f"la copia no reproduce el commit: distintos={distintos[:5]} sobrantes={sobrantes[:5]}")
    return {"ficheros": len(esperados)}


def instantanea(copia: pathlib.Path, ignorar: list[str]) -> dict[str, list]:
    res: dict[str, list] = {}
    for raiz, dirs, ficheros in os.walk(copia):
        dirs[:] = [d for d in dirs if d not in EXCLUIR_DIRS]
        for nombre in ficheros:
            if nombre.endswith(".pyc"):
                continue
            p = pathlib.Path(raiz) / nombre
            rel = str(p.relative_to(copia)).replace(os.sep, "/")
            if any(fnmatch.fnmatch(rel, g) for g in ignorar):
                continue
            st = p.stat()
            res[rel] = [hashlib.sha256(p.read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns]
    return res


def diferencias(a: dict, b: dict) -> list[str]:
    cambios = [f"cambiado {k}" for k in a if k in b and a[k] != b[k]]
    cambios += [f"borrado {k}" for k in a if k not in b]
    cambios += [f"nuevo {k}" for k in b if k not in a]
    return sorted(cambios)


# ---------------------------------------------------------------- pasos (puntos 1 y 2)
def resumen_junit(ruta: pathlib.Path) -> dict | None:
    if not ruta.exists():
        return None
    raiz = ET.parse(ruta).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else list(raiz.iter("testsuite"))
    tot = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for k in tot:
            tot[k] += int(s.get(k, 0))
    tot["passed"] = tot["tests"] - tot["failures"] - tot["errors"] - tot["skipped"]
    return tot


def entorno(paso: dict, copia: pathlib.Path, salida: pathlib.Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GAPTO_") and k not in ENTORNO_FUERA}
    for nombre in paso.get("heredar", []):
        if nombre not in os.environ:
            raise RuntimeError(f"variable heredada ausente: {nombre}")
        env[nombre] = os.environ[nombre]
    for k, v in paso.get("env", {}).items():
        env[k] = sustituir(v, copia, salida)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def sustituir(v: str, copia: pathlib.Path, salida: pathlib.Path) -> str:
    return v.replace("{COPIA}", str(copia)).replace("{SALIDA}", str(salida))


def ejecutar_paso(paso: dict, copia: pathlib.Path, salida: pathlib.Path, reg: Registro) -> dict:
    et, tipo = paso["etiqueta"], paso["tipo"]
    if tipo not in ("pytest", "script", "verificacion"):
        raise RuntimeError(f"tipo de paso desconocido: {tipo}")
    args = [sustituir(a, copia, salida) for a in paso["args"]]
    junit = salida / f"{et}.xml"
    if tipo == "pytest":
        cmd = [sys.executable, "-m", "pytest", *args, "-p", "no:cacheprovider", f"--junitxml={junit}"]
    else:
        cmd = [sustituir(a, copia, salida) if a != "{PYTHON}" else sys.executable for a in paso["args"]]
    inicio = ahora()
    reg.linea(f"{et} inicio {inicio} tipo={tipo}")
    with (salida / f"{et}.log").open("wb") as log:
        proc = subprocess.run(cmd, cwd=copia, env=entorno(paso, copia, salida), stdout=log, stderr=subprocess.STDOUT)
    rc = proc.returncode                      # punto 1: rc del propio proceso
    fin = ahora()
    reg.linea(f"{et} fin {fin} tipo={tipo} rc={rc}")
    r = {"etiqueta": et, "tipo": tipo, "rc": rc, "inicio": inicio, "fin": fin}
    if tipo == "pytest":
        j = resumen_junit(junit)
        r["junit"] = j
        # punto 2: el rc de pytest y su resumen deben concordar
        if j is None:
            r["coherente"] = False
        else:
            r["coherente"] = (rc == 0) == (j["failures"] + j["errors"] == 0 and j["tests"] > 0)
        reg.linea(f"{et} junit {json.dumps(j)} coherente={r['coherente']}")
    return r


# ---------------------------------------------------------------- principal
def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    salida = pathlib.Path(a.salida).resolve()
    if salida.exists() and any(salida.iterdir()):           # punto 7
        print(f"STOP: la salida {salida} ya existe con contenido; no se sobrescribe evidencia", file=sys.stderr)
        return 4
    try:   # un plan ilegible es error de preparacion (4), nunca ROJO (1)
        plan = json.loads(pathlib.Path(a.plan).read_text(encoding="utf-8"))
        assert isinstance(plan.get("pasos"), list) and plan.get("repo") and plan.get("commit")
    except Exception as exc:  # noqa: BLE001
        print(f"STOP: plan ilegible o incompleto: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    salida.mkdir(parents=True, exist_ok=True)
    reg = Registro(salida)
    (salida / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    repo = pathlib.Path(plan["repo"]).resolve()
    commit = plan["commit"]
    diarios = plan.get("diarios", [])
    ignorar = plan.get("ignorar", [])
    resultado = {"commit": commit, "inicio": ahora(), "pasos": [], "veredicto": None}

    def cerrar(veredicto: str, codigo: int) -> int:
        resultado["veredicto"] = veredicto
        resultado["fin"] = ahora()
        (salida / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
        reg.linea(f"VEREDICTO {veredicto} {resultado['fin']}")
        return codigo

    reg.linea(f"lanzador_gate 0.1.1 inicio {resultado['inicio']} commit={commit}")
    activos = cerrojo(repo, diarios)
    if activos:
        resultado["cerrojo"] = activos
        reg.linea("STOP: arnes de mutantes activo: " + "; ".join(activos))
        return cerrar("STOP_CERROJO", 3)
    copia = salida / "copia"
    try:
        info = crear_copia(repo, commit, copia)
    except Exception as exc:  # noqa: BLE001
        reg.linea(f"STOP: copia: {exc}")
        return cerrar("ERROR_COPIA", 4)
    reg.linea(f"copia inmutable OK: {info['ficheros']} ficheros = git ls-tree {commit}")
    base = instantanea(copia, ignorar)
    (salida / "copia_sha256_inicio.json").write_text(json.dumps(base, indent=0), encoding="utf-8")
    hubo_fallo = False
    for paso in plan["pasos"]:
        activos = cerrojo(repo, diarios)
        if activos:
            resultado["cerrojo"] = activos
            reg.linea("STOP: arnes de mutantes activo antes de " + paso["etiqueta"] + ": " + "; ".join(activos))
            return cerrar("STOP_CERROJO", 3)
        try:
            r = ejecutar_paso(paso, copia, salida, reg)
        except Exception as exc:  # noqa: BLE001
            reg.linea(f"STOP: paso {paso.get('etiqueta')}: {exc}")
            return cerrar("ERROR_PLAN", 4)
        ahora_inst = instantanea(copia, ignorar)       # puntos 4 y 5
        cambios = diferencias(base, ahora_inst)
        r["copia_intacta"] = not cambios
        resultado["pasos"].append(r)
        if cambios:
            (salida / "EJECUCION_INVALIDADA.txt").write_text(
                f"EJECUCION INVALIDADA: la copia cambio durante el paso {r['etiqueta']}\n" + "\n".join(cambios) + "\n", encoding="utf-8")
            reg.linea(f"EJECUCION INVALIDADA tras {r['etiqueta']}: {len(cambios)} cambios")
            return cerrar("INVALIDADA", 2)
        if r["rc"] != 0 or not r.get("coherente", True):
            hubo_fallo = True
            if paso.get("parar_si_falla"):
                reg.linea(f"parada tras fallo de {r['etiqueta']}")
                break
    (salida / "copia_sha256_fin.json").write_text(json.dumps(instantanea(copia, ignorar), indent=0), encoding="utf-8")
    return cerrar("ROJO" if hubo_fallo else "VERDE", 1 if hubo_fallo else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
