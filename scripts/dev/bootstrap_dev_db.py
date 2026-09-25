# ============================================================
# GAPTO MOBILE 2027
# Fichero: bootstrap_dev_db.py
# Ruta: scripts/dev/bootstrap_dev_db.py
# Descripcion: Crea/recrea la base LOCAL de desarrollo de F05-00-B
#   (`gapto2027_dev`) aplicando la cadena 0001..0330 del repositorio y
#   carga FIXTURES SINTETICOS minimos para VS-01 (sin PII, sin datos V3):
#     - usuario sintetico (email @example.invalid);
#     - actor self;
#     - una cuenta CORRIENTE EUR con participacion vigente 100 % del self.
#   Solo para PostgreSQL LOCAL de desarrollo. Protecciones:
#     - rechaza cualquier host que no sea socket local o localhost/127.0.0.1;
#     - la base destino se llama SIEMPRE `gapto2027_dev`;
#     - `--recrear` es obligatorio para destruir una base existente.
#   Nunca usar contra Neon ni Supabase (D-179; Neon dev no autorizado).
#   No es un runner de certificacion (no sustituye a run_clean_room.py).
#
#   Uso:
#     python scripts/dev/bootstrap_dev_db.py --admin-dsn "host=/tmp port=5433 user=postgres" [--recrear]
#   Imprime GAPTO_DEV_OWNER_USER_ID para configurar el adaptador.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import argparse
import pathlib
import sys
import uuid

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

BASE_DEV = "gapto2027_dev"
RAIZ = pathlib.Path(__file__).resolve().parents[2]
NS = uuid.UUID("6f1c9a52-5f0e-4b8b-9a51-0b2a3d6c7e01")  # namespace fijo de fixtures dev
OWNER = uuid.uuid5(NS, "vs01.owner")
ACTOR_SELF = uuid.uuid5(NS, "vs01.actor.self")
CUENTA = uuid.uuid5(NS, "vs01.cuenta.corriente")
PARTICIPACION = uuid.uuid5(NS, "vs01.cuenta.corriente.participacion")
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


def _exigir_local(dsn: str) -> dict:
    partes = conninfo_to_dict(dsn)
    host = partes.get("host", "")
    if not (host.startswith("/") or host in HOSTS_LOCALES):
        sys.exit(f"RECHAZADO: host '{host}' no es local. Este script solo opera en PostgreSQL local.")
    return partes


def _crear_base(admin_dsn: str, recrear: bool) -> None:
    partes = _exigir_local(admin_dsn)
    partes["dbname"] = partes.get("dbname") or "postgres"
    with psycopg.connect(make_conninfo(**partes), autocommit=True) as c:
        existe = c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (BASE_DEV,)).fetchone()
        if existe and not recrear:
            sys.exit(f"{BASE_DEV} ya existe. Usa --recrear para destruirla y rehacerla.")
        if existe:
            c.execute(f"DROP DATABASE {BASE_DEV} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {BASE_DEV}")
        roles = c.execute("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'gapto\\_%'").fetchone()[0]
    return roles


def _aplicar_cadena(dsn_dev: str, roles_existentes: int) -> str:
    ficheros = sorted((RAIZ / "migrations").glob("0*.sql"))
    with psycopg.connect(dsn_dev, autocommit=True) as c:
        for f in ficheros:
            if f.name.startswith("0001_") and roles_existentes:
                # Roles de instancia ya provisionados (cluster-scoped): 0001 no se repite.
                continue
            c.execute(f.read_text(encoding="utf-8"))
    return ficheros[-1].name


def _fixtures(dsn_dev: str) -> None:
    with psycopg.connect(dsn_dev) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_owner")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(OWNER),))
            cur.execute(
                "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, %s)",
                (OWNER, "vs01.dev@example.invalid", "Usuario sintetico VS-01"),
            )
            cur.execute(
                "INSERT INTO gapto.actores_financieros (id, owner_user_id) VALUES (%s, %s)",
                (ACTOR_SELF, OWNER),
            )
            cur.execute(
                "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
                "computa_liquidez, computa_patrimonio, permite_negativo) "
                "VALUES (%s, %s, 'Cuenta corriente (sintética)', 'CORRIENTE', 'ACTIVO', 'EUR', "
                "true, true, false)",
                (CUENTA, OWNER),
            )
            cur.execute(
                "INSERT INTO gapto.cuenta_participaciones (id, cuenta_id, actor_id, porcentaje, "
                "vigente_desde) VALUES (%s, %s, %s, 100, DATE '2026-01-01')",
                (PARTICIPACION, CUENTA, ACTOR_SELF),
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--admin-dsn", required=True, help="DSN administrativo LOCAL (sin dbname o con postgres)")
    ap.add_argument("--recrear", action="store_true")
    a = ap.parse_args()
    roles = _crear_base(a.admin_dsn, a.recrear)
    partes = _exigir_local(a.admin_dsn)
    partes["dbname"] = BASE_DEV
    dsn_dev = make_conninfo(**partes)
    head = _aplicar_cadena(dsn_dev, roles)
    _fixtures(dsn_dev)
    print(f"OK {BASE_DEV} head={head}")
    print(f"GAPTO_DEV_OWNER_USER_ID={OWNER}")
    print(f"CUENTA_SINTETICA={CUENTA}")


if __name__ == "__main__":
    main()
