# ============================================================
# GAPTO MOBILE 2027
# Fichero: run_clean_room.py
# Ruta: scripts/postgres/run_clean_room.py
# Descripción: Reproducibilidad clean-room y certificación del contrato físico.
#
#              Hace dos cosas, por separado o encadenadas:
#
#              --apply   aplica en orden todas las migrations de migrations/
#                        contra la base indicada. Se detiene en el primer
#                        fallo y dice exactamente en que fichero y por que.
#
#              --verify  extrae el contrato fisico completo de la base y lo
#                        compara contra los valores esperados. Sale con codigo
#                        distinto de cero si hay una sola diferencia.
#
#              Existe porque el sandbox no puede alimentar 27 ficheros SQL a los
#              conectores HTTP, y porque un clean-room que se ejecuta a mano no
#              es reproducible. Sirve tambien para cualquier entorno futuro y
#              para el cutover, asi que no es trabajo desechable.
#
#              NO imprime nunca la cadena de conexion ni la contrasena.
#
# Uso:
#   set GAPTO_CLEANROOM_DATABASE_URL=<dsn>
#   python scripts\postgres\run_clean_room.py --apply --verify
#
#   python scripts\postgres\run_clean_room.py --verify --dsn-env GAPTO_TEST_DATABASE_URL
#
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parents[2]
MIGRATIONS = RAIZ / "migrations"

# Contrato fisico esperado tras aplicar hasta 0240 (F03-01-B22).
# Certificado identico en Neon 17.11 y Supabase 17.6 por D-109.
CONTRATO = {
    "tablas": 79,
    "tablas_force_rls": 74,
    "policies": 81,
    "policies_autorreferentes": 0,
    "foreign_keys": 166,
    "unique_constraints": 37,
    "exclude_constraints": 11,
    "vistas_security_invoker": 3,
    "funciones": 15,
    "funciones_security_definer": 1,
    "triggers_no_internos": 34,
    "constraint_triggers": 19,
    "guards_append_only": 7,
    "triggers_deshabilitados": 0,
    "runtime_select": 79,
    "runtime_insert": 73,
    "runtime_update": 67,
    "runtime_delete": 36,
    "backup_select": 79,
    "backup_escritura": 0,
    "fk_tenant_sin_validar": 0,
}

HUELLAS = {
    "fn_registrar_auditoria": ("5a9e6ce8e8dc402b3123e3bf5c718725", 5902),
    "fn_check_participacion_suma": ("c909c04f4e0131a32c6552efe601d370", 2436),
    "fn_check_bolsa_prioridad_alcance": ("0eb39ed53b28a3c4657e032f3aaaa037", 1524),
}

SQL_CONTRATO = """
SELECT
 (SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='gapto'),
 (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='gapto' AND c.relkind='r' AND c.relforcerowsecurity),
 (SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='gapto'),
 (SELECT count(*) FROM pg_catalog.pg_policies p WHERE p.schemaname='gapto'
    AND coalesce(p.with_check,'')||coalesce(p.qual,'') ~ ('gapto\\.'||p.tablename||'\\M')),
 (SELECT count(*) FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='gapto' AND c.contype='f'),
 (SELECT count(*) FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='gapto' AND c.contype='u'),
 (SELECT count(*) FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='gapto' AND c.contype='x'),
 (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='gapto' AND c.relkind='v' AND c.reloptions @> ARRAY['security_invoker=true']),
 (SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='gapto'),
 (SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='gapto' AND p.prosecdef),
 (SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='gapto' AND NOT t.tgisinternal),
 (SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgconstraint <> 0),
 (SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgname LIKE '%guard%'),
 (SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgenabled <> 'O'),
 (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
   WHERE n.nspname='gapto' AND c.relkind='r' AND r.rolname='gapto_runtime' AND a.privilege_type='SELECT'),
 (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
   WHERE n.nspname='gapto' AND c.relkind='r' AND r.rolname='gapto_runtime' AND a.privilege_type='INSERT'),
 (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
   WHERE n.nspname='gapto' AND c.relkind='r' AND r.rolname='gapto_runtime' AND a.privilege_type='UPDATE'),
 (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
   WHERE n.nspname='gapto' AND c.relkind='r' AND r.rolname='gapto_runtime' AND a.privilege_type='DELETE'),
 (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
   WHERE n.nspname='gapto' AND c.relkind='r' AND r.rolname='gapto_backup' AND a.privilege_type='SELECT'),
 (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
   WHERE n.nspname='gapto' AND c.relkind='r' AND r.rolname='gapto_backup'
     AND a.privilege_type IN ('INSERT','UPDATE','DELETE')),
 (SELECT count(*) FROM (
     WITH tenant AS (
       SELECT c.oid, c.relname FROM pg_catalog.pg_class c
         JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='gapto' AND c.relkind='r' AND c.relrowsecurity
     ), fks AS (
       SELECT DISTINCT t.relname AS tabla, att.attname AS columna, array_length(con.conkey,1) AS ncols
         FROM pg_catalog.pg_constraint con
         JOIN tenant t ON t.oid=con.conrelid
         JOIN tenant tf ON tf.oid=con.confrelid
         CROSS JOIN LATERAL unnest(con.conkey) AS k(attnum)
         JOIN pg_catalog.pg_attribute att ON att.attrelid=con.conrelid AND att.attnum=k.attnum
        WHERE con.contype='f' AND att.attname <> 'owner_user_id'
     ), compuestas AS (SELECT tabla, columna FROM fks WHERE ncols>1),
     pol AS (SELECT tablename, string_agg(coalesce(with_check,''),' ') AS wc
               FROM pg_catalog.pg_policies WHERE schemaname='gapto' GROUP BY tablename)
     SELECT 1 FROM fks f
       LEFT JOIN pol p ON p.tablename=f.tabla
       LEFT JOIN compuestas cc ON cc.tabla=f.tabla AND cc.columna=f.columna
      WHERE f.ncols=1 AND cc.columna IS NULL
        AND coalesce(p.wc,'') NOT LIKE '%'||f.columna||'%'
 ) AS gaps)
"""

CLAVES = list(CONTRATO.keys())


def _dsn(nombre_variable: str) -> str:
    dsn = os.getenv(nombre_variable)
    if not dsn:
        print(f"ERROR: falta la variable de entorno {nombre_variable}.", file=sys.stderr)
        print("No se asume ninguna base por defecto: un clean-room contra la base "
              "equivocada es peor que no hacerlo.", file=sys.stderr)
        sys.exit(2)
    return dsn


def _destino(conexion: psycopg.Connection) -> str:
    """Identifica la base SIN revelar credenciales."""
    with conexion.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user, "
                       "substring(version() from 'PostgreSQL [0-9.]+')")
        base, usuario, version = cursor.fetchone()
    return f"{base} / {usuario} / {version}"


def aplicar(dsn: str) -> bool:
    ficheros = sorted(MIGRATIONS.glob("*.sql"))
    if not ficheros:
        print(f"ERROR: no hay migrations en {MIGRATIONS}", file=sys.stderr)
        return False

    with psycopg.connect(dsn, autocommit=True) as conexion:
        print(f"Destino: {_destino(conexion)}")
        print(f"Migrations: {len(ficheros)} ficheros\n")
        for fichero in ficheros:
            try:
                with conexion.cursor() as cursor:
                    cursor.execute(fichero.read_text(encoding="utf-8"))
                print(f"  OK    {fichero.name}")
            except psycopg.Error as error:
                print(f"  FALLO {fichero.name}")
                print(f"        {type(error).__name__}: {str(error).splitlines()[0]}")
                print("\nSe detiene aqui: aplicar el resto sobre un estado incompleto "
                      "no demuestra nada.")
                return False
    print("\nTodas las migrations aplicadas sin desviaciones.")
    return True


def verificar(dsn: str) -> bool:
    with psycopg.connect(dsn, autocommit=True) as conexion:
        print(f"Destino: {_destino(conexion)}\n")
        with conexion.cursor() as cursor:
            cursor.execute(SQL_CONTRATO)
            valores = cursor.fetchone()
        obtenido = dict(zip(CLAVES, valores))

        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT p.proname, md5(p.prosrc), length(p.prosrc)
                  FROM pg_catalog.pg_proc p
                  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname='gapto' AND p.proname = ANY(%s)
            """, (sorted(HUELLAS),))
            huellas = {n: (h, b) for n, h, b in cursor.fetchall()}

    diferencias = []
    print(f"{'COMPROBACION':<32} {'ESPERADO':>10} {'OBTENIDO':>10}")
    print("-" * 56)
    for clave in CLAVES:
        esperado, real = CONTRATO[clave], obtenido[clave]
        marca = "" if esperado == real else "   <-- DIFIERE"
        if esperado != real:
            diferencias.append(f"{clave}: esperado {esperado}, obtenido {real}")
        print(f"{clave:<32} {esperado:>10} {real:>10}{marca}")

    print()
    for nombre in sorted(HUELLAS):
        esperado = HUELLAS[nombre]
        real = huellas.get(nombre)
        if real is None:
            diferencias.append(f"{nombre}: la funcion no existe")
            print(f"{nombre:<34} AUSENTE   <-- DIFIERE")
        elif real != esperado:
            diferencias.append(f"{nombre}: huella {real} != {esperado}")
            print(f"{nombre:<34} {real[0]} {real[1]}   <-- DIFIERE")
        else:
            print(f"{nombre:<34} {real[0]} {real[1]}")

    print()
    if diferencias:
        print(f"CONTRATO NO CONFORME: {len(diferencias)} diferencia(s)")
        for linea in diferencias:
            print(f"  - {linea}")
        return False
    print("CONTRATO CONFORME: la base reproduce exactamente el estado esperado.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean-room y certificacion del contrato fisico de GaptoMobile 2027."
    )
    parser.add_argument("--apply", action="store_true",
                        help="aplica todas las migrations en orden")
    parser.add_argument("--verify", action="store_true",
                        help="compara el contrato fisico contra el esperado")
    parser.add_argument("--dsn-env", default="GAPTO_CLEANROOM_DATABASE_URL",
                        help="variable de entorno con el DSN (por defecto "
                             "GAPTO_CLEANROOM_DATABASE_URL)")
    argumentos = parser.parse_args()

    if not (argumentos.apply or argumentos.verify):
        parser.error("indica al menos --apply o --verify")

    dsn = _dsn(argumentos.dsn_env)

    if argumentos.apply:
        print("=== APLICACION DE MIGRATIONS ===")
        if not aplicar(dsn):
            return 1
        print()

    if argumentos.verify:
        print("=== CONTRATO FISICO ===")
        if not verificar(dsn):
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
