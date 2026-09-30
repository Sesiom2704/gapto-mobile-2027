# ============================================================
# GAPTO MOBILE 2027
# Fichero: evidencia_neon_post.py
# Ruta: scripts/dev/evidencia_neon_post.py
# Descripcion: Postcomprobacion READ ONLY de una evidencia de proveedor sobre
#   la clean-room de Neon. Versionado por R-EVID-RUNNER (AJ-RLOCALE-02, F05
#   §31.5): sustituye al auxiliar no versionado neon_post.py.
#   Con inicio_utc leido de inicio.txt (--inicio) comprueba:
#     - 0 filas de gapto.auditoria y 0 de gapto.categorias_financieras con
#       created_at <= inicio_utc (la suite corrio sobre la base recien
#       creada, no sobre una consumida);
#     - para cada --motivo (repetible), filas de auditoria con ese motivo:
#       > 0 y todas posteriores a inicio_utc;
#     - icon_key vacio o sin recortar = 0 (defensa residual de 0340).
#   Transaccion READ ONLY con ROLLBACK. DSN desde la variable de entorno
#   indicada por --env (en Windows, si el proceso no la hereda, del valor de
#   usuario en HKCU\Environment); nunca se imprime. Codigo de salida 0 solo
#   si todo lo anterior se cumple.
#   Uso:
#     python scripts/dev/evidencia_neon_post.py --env GAPTO_CLEANROOM_URL \
#       --inicio <carpeta>/inicio.txt --salida <carpeta>/postcomprobacion.txt \
#       --motivo "F05-01 REORDENAR" [--motivo ...]
# Version: 0.1.0 (F05-01 R-EVID-RUNNER, AJ-RLOCALE-02)
# ============================================================

from __future__ import annotations

import argparse
import os
import re
import sys

import psycopg


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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", required=True)
    p.add_argument("--inicio", required=True, help="inicio.txt con la linea 'inicio_utc: ...'")
    p.add_argument("--salida", required=True)
    p.add_argument("--motivo", action="append", default=[], help="motivo de auditoria a contar (repetible)")
    a = p.parse_args()

    with open(a.inicio, encoding="utf-8") as fh:
        m = re.search(r"^inicio_utc: (.+)$", fh.read(), re.M)
    if not m:
        sys.exit("inicio.txt sin linea inicio_utc.")
    inicio = m.group(1).strip()

    ok = True
    with psycopg.connect(dsn_desde_entorno(a.env)) as c:
        c.execute("SET TRANSACTION READ ONLY")

        def q(sql: str, params: tuple = ()):
            return c.execute(sql, params).fetchone()

        base = q("SELECT current_database()")[0]
        rol, bypass = q("SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        aud_total = q("SELECT count(*) FROM gapto.auditoria")[0]
        aud_prev = q("SELECT count(*) FROM gapto.auditoria WHERE created_at <= %s::timestamptz", (inicio,))[0]
        cat_prev = q("SELECT count(*) FROM gapto.categorias_financieras WHERE created_at <= %s::timestamptz",
                     (inicio,))[0]
        vacias = q("SELECT count(*) FROM gapto.categorias_financieras WHERE icon_key IS NOT NULL "
                   "AND (icon_key = '' OR icon_key <> btrim(icon_key))")[0]
        lineas = [
            f"Postcomprobacion (solo lectura, transaccion READ ONLY) de {base}",
            f"inicio_utc: {inicio}",
            f"rol de lectura: {rol} (bypassrls={bypass})",
            f"auditoria total: {aud_total}; con created_at <= inicio_utc: {aud_prev}",
            f"categorias con created_at <= inicio_utc: {cat_prev}",
            f"icon_key vacios o sin recortar: {vacias}",
        ]
        ok = aud_prev == 0 and cat_prev == 0 and vacias == 0
        for motivo in a.motivo:
            n, mn, mx = q("SELECT count(*), min(created_at), max(created_at) FROM gapto.auditoria WHERE motivo = %s",
                          (motivo,))
            prev = q("SELECT count(*) FROM gapto.auditoria WHERE motivo = %s AND created_at <= %s::timestamptz",
                     (motivo, inicio))[0]
            lineas.append(f"auditoria motivo '{motivo}': {n} filas; min created_at {mn}; max {mx}; "
                          f"con created_at <= inicio_utc: {prev}")
            ok = ok and n > 0 and prev == 0
        c.rollback()
    lineas.append(f"RESULTADO: {'OK' if ok else 'FALLO'}")
    with open(a.salida, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lineas) + "\n")
    print("\n".join(lineas))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
