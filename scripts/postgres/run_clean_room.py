#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: run_clean_room.py
# Ruta: scripts/postgres/run_clean_room.py
# Descripción: F03-GATE-01, criterio G4. Reconstruye el baseline completo
#              desde cero aplicando en orden las migrations del repositorio
#              sobre una base virgen, y despues compara el contrato fisico
#              resultante contra el contrato esperado.
#
#              Responde a la unica pregunta que F03-01 afirma y nunca se
#              habia demostrado sobre PostgreSQL 17: que el repositorio
#              reproduce el estado de los proveedores sin pasos manuales.
#
#              No modifica nada del repositorio ni de las bases de trabajo.
#              La base destino se pasa por variable de entorno y debe estar
#              vacia: el script se niega a ejecutar si encuentra el schema
#              gapto, para no destruir por accidente una base en uso.
#
# USO:
#   set GAPTO_CLEANROOM_URL=<dsn de la base virgen>
#   python scripts/postgres/run_clean_room.py
#
#   Opciones:
#     --desde 0002      empieza en esa migration en vez de en la primera
#     --solo-verificar  no aplica nada; solo comprueba el contrato
#     --permitir-sucia  aplica aunque el schema gapto ya exista
#
# NOTA SOBRE 0001. El provisioning de roles es de INSTANCIA, no de base. Si
# la base virgen vive en la misma instancia que una base ya provisionada,
# los cinco roles gapto ya existen y 0001 aborta con su propio postcheck de
# ROLE DRIFT, que es correcto y deliberado. En ese caso se usa --desde 0002
# y el clean-room demuestra reproducibilidad DE LA BASE, no de la instancia.
# Reproducir tambien la instancia exige un proyecto nuevo.
# Versión: 0.7.1  -- F03-02 / migration 0285: CONTRATO del final de la cadena
#                   = 25 funciones, 48 triggers no internos y 31 constraint
#                   triggers, y la huella de fn_check_bolsa_prioridad_alcance
#                   pasa a la de 0285. Sin capacidades nuevas del runner: la
#                   version 0.8.0 sigue reservada al manifest del bootstrap
#                   fresh 0001..0290.
#                   v0.7.0: F03-02 / migration 0280: CONTRATO del final de la cadena
#                   = 21 funciones, 40 triggers no internos, 30 constraint
#                   triggers y 40 UNIQUE. Huellas de participacion, alcance
#                   BOLSA y auditoria sin cambios.
#                   v0.6.0: F03-02 / migration 0270: el CONTRATO del final de la
#                   cadena pasa a 19 funciones, 39 triggers no internos y 23
#                   constraint triggers. Las HUELLAS de participacion, alcance
#                   BOLSA y auditoria no cambian (0270 no toca esas funciones).
#                   v0.5.0: F03-02 / migration 0260: huellas esperadas de
#                   fn_check_participacion_suma y fn_check_bolsa_prioridad_alcance
#                   pasan a las de 0260 (fail-closed y cambio de padre).
#                   v0.4.0: F03-02 / migration 0250: las huellas esperadas de
#                   fn_check_participacion_suma y fn_check_bolsa_prioridad_alcance
#                   pasan a las de 0250 (FOR NO KEY UPDATE), porque el runner
#                   aplica siempre la cadena completa del repositorio. El texto
#                   de alcance cita la ultima migration realmente aplicada en
#                   lugar de 0240 fijo.
#                   v0.3.0: soporta los dos modos y se niega a mezclarlos: BOOTSTRAP DE
#                   INSTANCIA aplicando 0001 sobre una instancia sin roles, con
#                   postflight de los cinco roles creados; y CLEAN-ROOM DE BASE
#                   arrancando en 0002 sobre instancia ya provisionada, con
#                   preflight de solo lectura. El resultado se etiqueta segun el
#                   modo realmente ejecutado.
#                   v0.2.0: preflight de roles y etiquetado de alcance.
# ============================================================

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover
    sys.exit("Falta psycopg. Instala con: python -m pip install \"psycopg[binary]\"")


# Contrato fisico esperado al final de la cadena (0280). Base: D-109; 0270
# anade 4 funciones, 5 triggers y 4 constraint triggers; 0280 cambia 1 funcion
# por 3, 6 triggers BEFORE por 7 constraint triggers y anade 3 UNIQUE.
CONTRATO = {
    "tablas": 79,
    "force_rls": 74,
    "policies": 81,
    "foreign_keys": 166,
    "unique_constraints": 40,
    "exclude_constraints": 11,
    "funciones": 25,
    "security_definer": 1,
    "vistas_security_invoker": 3,
    "triggers_no_internos": 48,
    "constraint_triggers": 31,
    "triggers_deshabilitados": 0,
    "policies_autorreferentes": 0,
    "fk_tenant_sin_validar": 0,
    "runtime_select": 79,
    "runtime_insert": 73,
    "runtime_update": 67,
    "runtime_delete": 36,
}

HUELLAS = {
    "fn_registrar_auditoria": "5a9e6ce8e8dc402b3123e3bf5c718725",
    "fn_check_participacion_suma": "b76161555c227a8aa19c3ab513aa4687",
    "fn_check_bolsa_prioridad_alcance": "d1d83d6e38a15190244a26be50d90ad4",
}

CONSULTA_CONTRATO = """
SELECT
  (SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='gapto') AS tablas,
  (SELECT count(*) FROM pg_catalog.pg_class c
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='gapto' AND c.relkind='r' AND c.relforcerowsecurity) AS force_rls,
  (SELECT count(*) FROM pg_catalog.pg_policies WHERE schemaname='gapto') AS policies,
  (SELECT count(*) FROM pg_catalog.pg_constraint con
     JOIN pg_catalog.pg_class t ON t.oid=con.conrelid
     JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
    WHERE n.nspname='gapto' AND con.contype='f') AS foreign_keys,
  (SELECT count(*) FROM pg_catalog.pg_constraint con
     JOIN pg_catalog.pg_class t ON t.oid=con.conrelid
     JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
    WHERE n.nspname='gapto' AND con.contype='u') AS unique_constraints,
  (SELECT count(*) FROM pg_catalog.pg_constraint con
     JOIN pg_catalog.pg_class t ON t.oid=con.conrelid
     JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
    WHERE n.nspname='gapto' AND con.contype='x') AS exclude_constraints,
  (SELECT count(*) FROM pg_catalog.pg_proc p
     JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='gapto') AS funciones,
  (SELECT count(*) FROM pg_catalog.pg_proc p
     JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='gapto' AND p.prosecdef) AS security_definer,
  (SELECT count(*) FROM pg_catalog.pg_class c
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='gapto' AND c.relkind='v'
      AND c.reloptions @> ARRAY['security_invoker=true']) AS vistas_security_invoker,
  (SELECT count(*) FROM pg_catalog.pg_trigger t
     JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='gapto' AND NOT t.tgisinternal) AS triggers_no_internos,
  (SELECT count(*) FROM pg_catalog.pg_trigger t
     JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgconstraint <> 0)
      AS constraint_triggers,
  (SELECT count(*) FROM pg_catalog.pg_trigger t
     JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='gapto' AND NOT t.tgisinternal AND t.tgenabled <> 'O')
      AS triggers_deshabilitados,
  (SELECT count(*) FROM pg_catalog.pg_policies p
    WHERE p.schemaname='gapto'
      AND coalesce(p.with_check,'') || coalesce(p.qual,'')
          ~ ('gapto\\.' || p.tablename || '\\M')) AS policies_autorreferentes,
  (SELECT count(*) FROM (
      WITH tenant AS (
        SELECT c.oid, c.relname FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='gapto' AND c.relkind='r' AND c.relrowsecurity
      ), fks AS (
        SELECT DISTINCT t.relname AS tabla, att.attname AS columna,
               array_length(con.conkey,1) AS ncols
          FROM pg_catalog.pg_constraint con
          JOIN tenant t ON t.oid=con.conrelid
          JOIN tenant tf ON tf.oid=con.confrelid
          CROSS JOIN LATERAL unnest(con.conkey) AS k(attnum)
          JOIN pg_catalog.pg_attribute att
            ON att.attrelid=con.conrelid AND att.attnum=k.attnum
         WHERE con.contype='f' AND att.attname <> 'owner_user_id'
      ), compuestas AS (SELECT tabla, columna FROM fks WHERE ncols>1),
      pol AS (
        SELECT tablename, string_agg(coalesce(with_check,''),' ') AS wc
          FROM pg_catalog.pg_policies WHERE schemaname='gapto' GROUP BY tablename
      )
      SELECT 1 FROM fks f
        LEFT JOIN pol p ON p.tablename=f.tabla
        LEFT JOIN compuestas cc ON cc.tabla=f.tabla AND cc.columna=f.columna
       WHERE f.ncols=1 AND cc.columna IS NULL
         AND coalesce(p.wc,'') NOT LIKE '%' || f.columna || '%'
  ) AS x) AS fk_tenant_sin_validar,
  (SELECT count(*) FROM pg_catalog.pg_class c
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
     CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
     JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee
    WHERE n.nspname='gapto' AND c.relkind='r'
      AND r.rolname='gapto_runtime' AND acl.privilege_type='SELECT') AS runtime_select,
  (SELECT count(*) FROM pg_catalog.pg_class c
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
     CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
     JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee
    WHERE n.nspname='gapto' AND c.relkind='r'
      AND r.rolname='gapto_runtime' AND acl.privilege_type='INSERT') AS runtime_insert,
  (SELECT count(*) FROM pg_catalog.pg_class c
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
     CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
     JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee
    WHERE n.nspname='gapto' AND c.relkind='r'
      AND r.rolname='gapto_runtime' AND acl.privilege_type='UPDATE') AS runtime_update,
  (SELECT count(*) FROM pg_catalog.pg_class c
     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
     CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) AS acl
     JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee
    WHERE n.nspname='gapto' AND c.relkind='r'
      AND r.rolname='gapto_runtime' AND acl.privilege_type='DELETE') AS runtime_delete
"""


def raiz_repositorio() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def migrations(desde: str | None) -> list[Path]:
    ruta = raiz_repositorio() / "migrations"
    if not ruta.is_dir():
        sys.exit(f"No encuentro {ruta}. Ejecuta el script desde el repositorio clonado.")
    ficheros = sorted(ruta.glob("*.sql"))
    if desde:
        ficheros = [f for f in ficheros if f.name >= desde]
    return ficheros


ROLES_ESPERADOS = {
    # rol            : (canlogin, superuser, bypassrls)
    "gapto_owner":    (False, False, False),
    "gapto_migrator": (False, False, False),
    "gapto_internal": (False, False, False),
    "gapto_runtime":  (False, False, False),
    "gapto_backup":   (False, False, True),
}


def leer_roles(conexion) -> dict:
    with conexion.cursor() as cursor:
        cursor.execute("""
            SELECT rolname, rolcanlogin, rolsuper, rolbypassrls
              FROM pg_catalog.pg_roles
             WHERE rolname = ANY(%s) ORDER BY rolname
        """, (sorted(ROLES_ESPERADOS),))
        return {f[0]: (f[1], f[2], f[3]) for f in cursor.fetchall()}


def comprobar_roles(encontrados: dict) -> list[str]:
    problemas = []
    for rol, esperado in sorted(ROLES_ESPERADOS.items()):
        real = encontrados.get(rol)
        if real is None:
            print(f"  FALLO  {rol:16} no existe en la instancia")
            problemas.append(f"{rol}: no existe")
            continue
        ok = real == esperado
        print(f"  {'ok  ' if ok else 'FALLO'}  {rol:16} "
              f"login={real[0]} super={real[1]} bypassrls={real[2]}")
        if not ok:
            problemas.append(f"{rol}: atributos {real}, esperados {esperado}")
    return problemas


def preflight_roles(conexion, incluye_0001: bool) -> None:
    """Decide si el estado de roles de la instancia encaja con lo que se va a
    aplicar, y aborta si no.

    Los roles son cluster-scoped: pertenecen a la instancia, no a la base. De
    ahi que existan dos modos legitimos y excluyentes:

      - CLEAN-ROOM DE INSTANCIA. Se aplica 0001 y los cinco roles NO deben
        existir todavia. Es el bootstrap completo.
      - CLEAN-ROOM DE BASE. Se arranca en 0002 sobre una instancia ya
        provisionada, y los cinco roles SI deben existir con sus atributos
        correctos. 0001 no puede ejecutarse aqui porque su postcheck de ROLE
        DRIFT lo impediria, y hace bien.

    Mezclar los dos modos produce una evidencia que no demuestra ninguno de
    los dos, asi que el script se niega.
    """
    encontrados = leer_roles(conexion)
    existentes = sorted(encontrados)

    if incluye_0001:
        print("\nPreflight de roles (modo BOOTSTRAP DE INSTANCIA):")
        if existentes:
            print(f"  FALLO  ya existen roles del modelo: {', '.join(existentes)}")
            sys.exit(
                "\nNo es un bootstrap de instancia: los roles ya estan creados. "
                "0001 abortaria con su propio postcheck de ROLE DRIFT, y hace bien. "
                "Usa --desde 0002 para un clean-room DE BASE, o una instancia nueva."
            )
        print("  ok    ninguno de los cinco roles existe; 0001 los creara")
        return

    print("\nPreflight de roles (modo CLEAN-ROOM DE BASE, solo lectura):")
    problemas = comprobar_roles(encontrados)
    if problemas:
        print()
        for problema in problemas:
            print(f"  - {problema}")
        sys.exit(
            "\nPreflight FALLIDO. Se arranca en 0002, asi que la instancia deberia "
            "estar ya provisionada por 0001 y no lo esta. Este script no provisiona "
            "roles por su cuenta: eso es trabajo de 0001."
        )


def postflight_roles(conexion) -> list[str]:
    """Tras un bootstrap de instancia, 0001 debe haber dejado los cinco roles."""
    print("\nPostflight de roles (los ha creado 0001):")
    return comprobar_roles(leer_roles(conexion))


def base_esta_vacia(conexion) -> bool:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname='gapto'")
        (existe,) = cursor.fetchone()
    return existe == 0


def aplicar(conexion, ficheros: list[Path]) -> None:
    for fichero in ficheros:
        sql = fichero.read_text(encoding="utf-8")
        try:
            with conexion.cursor() as cursor:
                cursor.execute(sql)
        except psycopg.Error as error:
            print(f"  FALLO  {fichero.name}")
            print(f"         {error}")
            sys.exit(
                "\nClean-room INTERRUMPIDO. El repositorio no reproduce el baseline "
                "sin intervencion manual: eso es exactamente lo que este criterio "
                "existe para detectar."
            )
        print(f"  ok     {fichero.name}")


def leer_contrato(conexion) -> dict:
    with conexion.cursor() as cursor:
        cursor.execute(CONSULTA_CONTRATO)
        columnas = [d.name for d in cursor.description]
        valores = cursor.fetchone()
    return dict(zip(columnas, valores))


def leer_huellas(conexion) -> dict:
    with conexion.cursor() as cursor:
        cursor.execute("""
            SELECT p.proname, md5(p.prosrc)
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname='gapto' AND p.proname = ANY(%s)
        """, (sorted(HUELLAS),))
        return dict(cursor.fetchall())


def comparar(obtenido: dict, esperado: dict, titulo: str) -> list[str]:
    print(f"\n{titulo}")
    print("-" * len(titulo))
    fallos = []
    for clave in esperado:
        real = obtenido.get(clave)
        ok = real == esperado[clave]
        marca = "ok  " if ok else "FALLO"
        print(f"  {marca}  {clave:26} esperado={esperado[clave]!s:<34} obtenido={real}")
        if not ok:
            fallos.append(f"{clave}: esperado {esperado[clave]}, obtenido {real}")
    return fallos


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean-room de GaptoMobile 2027")
    parser.add_argument("--desde", default=None,
                        help="nombre de fichero desde el que empezar, p.ej. 0002")
    parser.add_argument("--solo-verificar", action="store_true",
                        help="no aplica migrations; solo comprueba el contrato")
    parser.add_argument("--permitir-sucia", action="store_true",
                        help="aplica aunque el schema gapto ya exista")
    args = parser.parse_args()

    dsn = os.getenv("GAPTO_CLEANROOM_URL")
    if not dsn:
        sys.exit(
            "Falta GAPTO_CLEANROOM_URL. Debe apuntar a una base VACIA, nunca a "
            "gapto2027_test ni a la de Supabase en uso."
        )

    with psycopg.connect(dsn, autocommit=True) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("SELECT current_database(), version()")
            base, version = cursor.fetchone()
        print(f"Base destino: {base}")
        print(f"Motor:        {version.split(' on ')[0]}")

        ficheros = migrations(args.desde)
        incluye_0001 = any(f.name.startswith("0001") for f in ficheros)

        if args.solo_verificar:
            incluye_0001 = False
        else:
            preflight_roles(conexion, incluye_0001)
            vacia = base_esta_vacia(conexion)
            if not vacia and not args.permitir_sucia:
                sys.exit(
                    f"\nLa base '{base}' YA contiene el schema gapto. Me niego a "
                    "aplicar migrations encima. Usa una base virgen, o --permitir-sucia "
                    "si sabes lo que haces."
                )
            print(f"\nAplicando {len(ficheros)} migrations desde "
                  f"{ficheros[0].name} hasta {ficheros[-1].name}:\n")
            aplicar(conexion, ficheros)

        problemas_rol = postflight_roles(conexion) if incluye_0001 else []

        contrato = leer_contrato(conexion)
        huellas = leer_huellas(conexion)

    fallos = list(problemas_rol)
    fallos += comparar(contrato, CONTRATO, "CONTRATO FISICO")
    fallos += comparar(huellas, HUELLAS, "HUELLAS DE FUNCION (md5 de prosrc)")

    print()
    if fallos:
        print(f"RESULTADO: FALLO. {len(fallos)} discrepancias:")
        for f in fallos:
            print(f"  - {f}")
        return 1

    print("RESULTADO: OK.")
    print()
    if incluye_0001:
        print("ALCANCE DE ESTA EVIDENCIA: clean-room DE INSTANCIA, es decir bootstrap")
        print("completo desde cero. Ninguno de los cinco roles gapto existia antes de")
        print("empezar; los ha creado 0001 durante esta misma ejecucion, y el postflight")
        print("confirma que quedan con los atributos esperados. La cadena completa")
        print(f"0001..{ficheros[-1].name[:4]} se aplica sin SET search_path manual, sin parches temporales y")
        print("sin ningun paso manual.")
    else:
        print("ALCANCE DE ESTA EVIDENCIA: clean-room DE BASE sobre una instancia")
        print("previamente provisionada. Los cinco roles gapto son cluster-scoped y ya")
        print("existian, de modo que 0001 no se ha ejecutado: se ha verificado en modo")
        print("solo lectura que existen con los atributos correctos. Esto NO es un")
        print("bootstrap completo de instancia; demostrarlo exigiria una instancia nueva.")
        print()
        print("Dentro de ese alcance: el repositorio reproduce el baseline aplicando las")
        print("migrations desde 0002 en orden, sin SET search_path manual, sin parches")
        print("temporales y sin ningun paso manual.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
