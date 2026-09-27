# ============================================================
# GAPTO MOBILE 2027
# Fichero: bootstrap_dev_db.py
# Ruta: scripts/dev/bootstrap_dev_db.py
# Descripcion: Crea/recrea la base LOCAL de desarrollo de F05-00-B
#   (`gapto2027_dev`) aplicando la cadena 0001..HEAD_AUTORIZADO_ENVDEV del
#   repositorio y
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
#   HEAD AUTORIZADO (revision del P0 de 0340, D-197). Publicar una migration en
#   main NO la autoriza en ENV-DEV. La cadena se corta SIEMPRE en
#   HEAD_AUTORIZADO_ENVDEV; las migrations posteriores presentes en el
#   repositorio no se aplican y se listan en la salida. Subir el head de
#   ENV-DEV exige cambiar esa constante en un commit revisado: no hay opcion de
#   linea de comandos para superarlo. La cadena se valida ANTES de crear o
#   destruir la base, de modo que un repositorio incoherente (head ausente o
#   duplicado, nombre de migration fuera de patron) aborta sin tocar nada.
#
#   Uso:
#     python scripts/dev/bootstrap_dev_db.py --admin-dsn "host=/tmp port=5433 user=postgres" [--recrear]
#   Imprime GAPTO_DEV_OWNER_USER_ID para configurar el adaptador.
# Version: 0.2.0  -- D-197 / revision P0 0340 (hallazgo 1): techo de head
#                   fail-closed HEAD_AUTORIZADO_ENVDEV = "0330"; validacion de la
#                   cadena antes de CREATE/DROP DATABASE; la salida lista las
#                   migrations omitidas y el head aplicado.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import argparse
import pathlib
import re
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

# Head maximo que ENV-DEV puede materializar. Cambiarlo es una decision
# revisada (commit propio), nunca un efecto lateral de publicar migrations.
HEAD_AUTORIZADO_ENVDEV = "0330"
PATRON_MIGRATION = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def seleccionar_cadena(ficheros: list[pathlib.Path], head: str = HEAD_AUTORIZADO_ENVDEV
                       ) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Devuelve (a_aplicar, omitidas). Fail-closed: aborta si algun nombre no
    sigue el patron NNNN_nombre.sql, si un numero se repite o si el head
    autorizado no existe exactamente una vez."""
    numeros: dict[str, pathlib.Path] = {}
    for f in ficheros:
        m = PATRON_MIGRATION.match(f.name)
        if not m:
            sys.exit(f"RECHAZADO: migration con nombre fuera de patron: {f.name}")
        if m.group(1) in numeros:
            sys.exit(f"RECHAZADO: numero de migration duplicado {m.group(1)}: "
                     f"{numeros[m.group(1)].name} y {f.name}")
        numeros[m.group(1)] = f
    if head not in numeros:
        sys.exit(f"RECHAZADO: el head autorizado {head} no esta en migrations/.")
    ordenadas = [numeros[n] for n in sorted(numeros)]
    a_aplicar = [f for f in ordenadas if PATRON_MIGRATION.match(f.name).group(1) <= head]
    omitidas = [f for f in ordenadas if PATRON_MIGRATION.match(f.name).group(1) > head]
    return a_aplicar, omitidas


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


def _aplicar_cadena(dsn_dev: str, roles_existentes: int, ficheros: list[pathlib.Path]) -> str:
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
    # Validacion de la cadena ANTES de tocar ninguna base.
    a_aplicar, omitidas = seleccionar_cadena(sorted((RAIZ / "migrations").glob("0*.sql")))
    roles = _crear_base(a.admin_dsn, a.recrear)
    partes = _exigir_local(a.admin_dsn)
    partes["dbname"] = BASE_DEV
    dsn_dev = make_conninfo(**partes)
    head = _aplicar_cadena(dsn_dev, roles, a_aplicar)
    _fixtures(dsn_dev)
    print(f"OK {BASE_DEV} head={head} (autorizado {HEAD_AUTORIZADO_ENVDEV})")
    for f in omitidas:
        print(f"OMITIDA por encima del head autorizado: {f.name}")
    print(f"GAPTO_DEV_OWNER_USER_ID={OWNER}")
    print(f"CUENTA_SINTETICA={CUENTA}")


if __name__ == "__main__":
    main()
