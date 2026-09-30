# ============================================================
# GAPTO MOBILE 2027
# Fichero: evidencia_neon_inicio.py
# Ruta: scripts/dev/evidencia_neon_inicio.py
# Descripcion: inicio.txt de una evidencia de proveedor sobre la clean-room
#   de Neon (WM 12C.3). Versionado por R-EVID-RUNNER (AJ-RLOCALE-02, F05
#   §31.5): sustituye al auxiliar no versionado neon_inicio_rl.py.
#   Emite, ANTES del replay:
#     - inicio_utc (reloj del servidor), base, motor;
#     - HEAD, git status --porcelain y la formula de estado Git de F05 §30.4
#       (arbol limpio, o baseline + ficheros del perimetro sin commit ligados
#       por SHA-256);
#     - SHA-256 de los ficheros del perimetro (--fichero, repetible);
#     - virginidad: 0 schemas gapto/gapto_ext, 0 extensiones salvo plpgsql,
#       0 tablas de usuario y los 5 roles de instancia; VIRGEN: SI|NO;
#     - SHOW lc_messages y si el rol de conexion puede fijarlo.
#   Solo lectura sobre la base. La DSN se toma de la variable de entorno que
#   indica --env (en Windows, si el proceso no la hereda, del valor de
#   usuario persistido por setx en HKCU\Environment); nunca se imprime ni
#   se escribe. Sin rutas absolutas: el repositorio es el que contiene este
#   fichero. Codigo de salida 0 solo si VIRGEN: SI.
#   Uso:
#     python scripts/dev/evidencia_neon_inicio.py --env GAPTO_CLEANROOM_URL \
#       --salida <carpeta>/inicio.txt --bloque "F05-01 S6-ORDEN" \
#       --fichero backend/app/categorias/servicio.py [--fichero ...] \
#       [--nota "recreada por MCP ..."]
# Version: 0.1.0 (F05-01 R-EVID-RUNNER, AJ-RLOCALE-02)
# ============================================================

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import subprocess
import sys

import psycopg

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ROLES_INSTANCIA = ("gapto_backup", "gapto_internal", "gapto_migrator", "gapto_owner", "gapto_runtime")


def dsn_desde_entorno(variable: str) -> str:
    valor = os.environ.get(variable)
    if not valor and sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                valor = winreg.QueryValueEx(k, variable)[0]
        except OSError:
            valor = None
    if not valor:
        sys.exit(f"Falta la variable de entorno {variable}.")
    return valor


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(RAIZ), *args], capture_output=True, text=True, check=True).stdout


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True, help="variable de entorno con la DSN (nunca se imprime)")
    p.add_argument("--salida", required=True)
    p.add_argument("--bloque", required=True, help="etiqueta del bloque, p. ej. 'F05-01 S6-ORDEN'")
    p.add_argument("--fichero", action="append", default=[], help="fichero del perimetro (relativo a la raiz)")
    p.add_argument("--nota", action="append", default=[], help="linea declarativa adicional")
    a = p.parse_args()

    with psycopg.connect(dsn_desde_entorno(a.env), autocommit=True) as c:
        def q(sql: str):
            return c.execute(sql).fetchone()[0]

        inicio = q("SELECT clock_timestamp()")
        base = q("SELECT current_database()")
        motor = q("SELECT version()").split(" on ")[0]
        schemas = q("SELECT count(*) FROM pg_namespace WHERE nspname IN ('gapto','gapto_ext')")
        ext = q("SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql'")
        tablas = q("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                   "WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema') "
                   "AND n.nspname NOT LIKE 'pg_toast%'")
        roles = q("SELECT coalesce(string_agg(rolname, ',' ORDER BY rolname), '') FROM pg_roles WHERE rolname IN "
                  "('gapto_owner','gapto_migrator','gapto_internal','gapto_runtime','gapto_backup')")
        lcm = q("SHOW lc_messages")
        puede_lc = q("SELECT r.rolsuper OR has_parameter_privilege(current_user, 'lc_messages', 'SET') "
                     "FROM pg_roles r WHERE r.rolname = current_user")
    virgen = schemas == 0 and ext == 0 and tablas == 0 and roles == ",".join(ROLES_INSTANCIA)

    head = git("rev-parse", "HEAD").strip()
    estado = git("status", "--porcelain").rstrip()
    perimetro_sucio = [f for f in a.fichero if git("status", "--porcelain", "--", f).strip()]
    if not perimetro_sucio:
        formula = f"arbol de trabajo = HEAD {head} (perimetro sin cambios respecto de HEAD)"
    else:
        formula = (f"arbol de trabajo = baseline {head} + {len(perimetro_sucio)} fichero(s) del perimetro SIN commit, "
                   "ligados por SHA-256 (formula F05 §30.4; no es git status limpio)")
    lineas = [
        f"{a.bloque}: evidencia de proveedor (Neon {base})",
        f"inicio_utc: {inicio.isoformat()}",
        f"HEAD: {head}",
        f"estado Git: {formula}",
        *a.nota,
        "",
        "git status --porcelain:",
        estado or "(vacio)",
        "",
        "SHA-256 del contenido certificado:",
    ]
    for f in a.fichero:
        lineas.append(f"{hashlib.sha256((RAIZ / f).read_bytes()).hexdigest()}  {f}")
    lineas += [
        "",
        "Verificacion de clean-room virgen (antes del replay):",
        f"  base: {base}",
        f"  motor: {motor}",
        f"  schemas gapto/gapto_ext: {schemas}",
        f"  extensiones (excluida plpgsql): {ext}",
        f"  tablas de usuario: {tablas}",
        f"  roles gapto de instancia: {roles}",
        f"  VIRGEN: {'SI' if virgen else 'NO'}",
        f"  SHOW lc_messages del servidor: {lcm}",
        f"  el rol de conexion puede fijar lc_messages: {'SI' if puede_lc else 'NO'}",
    ]
    with open(a.salida, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lineas) + "\n")
    print("\n".join(lineas[-9:]))
    return 0 if virgen else 1


if __name__ == "__main__":
    sys.exit(main())
