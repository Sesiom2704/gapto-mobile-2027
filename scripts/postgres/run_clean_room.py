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
#   Manifest del bootstrap fresh de instancia (D-131 refinada por D-136):
#     --head 0290           migration final declarada; compone el veredicto
#     --junit RUTA.xml      JUnit de la suite completa ejecutada contra la base
#     --proyecto ID         identificador del proyecto Neon nuevo (declarado)
#     --commit SHA          commit candidato al cierre de fase (declarado)
#     --manifiesto RUTA.json  escribe el manifest con el veredicto
#     --completar-manifiesto RUTA.json  segunda fase: adjunta el JUnit
#
#   El bootstrap tiene dos fases porque la suite no existe hasta que la cadena
#   esta aplicada. Fase 1: se aplica 0001..HEAD y se escribe el manifest con
#   resultado PENDIENTE_SUITE, dejando constancia observada de que los roles
#   los creo esta ejecucion y de que la base estaba virgen. Fase 2: se ejecuta
#   la suite y se completa el mismo manifest con --completar-manifiesto, que
#   vuelve a leer el catalogo y exige que las ocho huellas no hayan cambiado
#   entre ambas fases. Sin esa comprobacion, la fase 2 no probaria que la suite
#   se ejecuto contra el estado certificado en la fase 1.
#
#   El manifest separa SIEMPRE lo observado de lo declarado. Observado es lo
#   que este script lee del catalogo y del JUnit. Declarado es lo que el
#   operador afirma y el script NO puede comprobar: que el proyecto es nuevo,
#   cual es su identificador y sobre que commit se ejecuta. Esa separacion es
#   el requisito explicito de D-136 y evita que el manifest parezca probar mas
#   de lo que prueba.
#
# NOTA SOBRE 0001. El provisioning de roles es de INSTANCIA, no de base. Si
# la base virgen vive en la misma instancia que una base ya provisionada,
# los cinco roles gapto ya existen y 0001 aborta con su propio postcheck de
# ROLE DRIFT, que es correcto y deliberado. En ese caso se usa --desde 0002
# y el clean-room demuestra reproducibilidad DE LA BASE, no de la instancia.
# Reproducir tambien la instancia exige un proyecto nuevo.
# Versión: 0.10.2 -- D-177 §3 (durabilidad de evidencia). K2 ocurrio porque cuatro
#                    ejecuciones distintas reutilizaron el mismo nombre de fichero
#                    y cada una sobrescribio la anterior, y porque los artefactos
#                    se escribian en logs/, dentro del repositorio, que esta en
#                    .gitignore y desaparece con cada descarga. Ahora el runner:
#                      - SE NIEGA a sobrescribir un manifest existente;
#                      - SE NIEGA a escribir evidencia DENTRO del repositorio;
#                      - registra run_id y marca UTC en el propio manifest;
#                      - avisa si el JUnit que se le pasa vive en el repositorio.
#                    La politica deja de depender de que el operador se acuerde.
# Versión: 0.10.1 -- D-177 §2 (K7). La comprobacion de virginidad miraba UNICAMENTE
#                    el schema gapto. Un residuo en gapto_ext, o las extensiones
#                    btree_gist / pg_trgm ya instaladas, pasaban el preflight y
#                    hacian fallar 0002, que crea ambos schemas con CREATE SCHEMA
#                    sin IF NOT EXISTS y las extensiones WITH SCHEMA gapto_ext.
#                    La frontera correcta NO es "gapto_ext siempre ausente": es
#                    condicional al tramo que se va a aplicar.
#                      cadena que INCLUYE 0002 -> gapto y gapto_ext deben estar
#                        AUSENTES, y btree_gist / pg_trgm no deben existir en
#                        ninguna parte de la base;
#                      cadena que EMPIEZA DESPUES de 0002 -> ambos schemas deben
#                        estar PRESENTES, porque 0002 ya los creo.
#                    --permitir-sucia conserva exactamente su semantica: sigue
#                    siendo la unica forma de saltarse la comprobacion, y no se
#                    debilita.
# Versión: 0.10.0 -- D-172 / migration 0310. El contrato deja de ser un unico dict
#                    global y pasa a estar indexado por HEAD, conservando el
#                    historico: --head 0300 compara contra el contrato de 0300 y
#                    --head 0310 contra el de 0310 (28 funciones, 58 triggers no
#                    internos, 41 constraint triggers), MEDIDO en Neon
#                    gapto2027_test y no previsto. Sin --head se usa el contrato
#                    del head vigente de la cadena, que es 0310.
#                    Un head sin contrato declarado ABORTA con mensaje explicito
#                    en lugar de compararse contra un contrato ajeno: es un
#                    cambio de comportamiento deliberado frente a v0.9.0, donde
#                    cualquier head se comparaba contra el unico contrato global.
#                    El diccionario HUELLAS no se toca: es un sondeo curado de 5
#                    funciones criticas para diagnostico temprano, no un contrato
#                    exhaustivo; la cobertura completa de prosrc vive en la
#                    huella h6_funciones de D-111.
# Versión: 0.9.0  -- F03 REABIERTA / D-168 + D-169 / migration 0300: el CONTRATO
#                    del final de la cadena pasa a 175 FK. No cambian funciones
#                    (26), triggers (54), constraint triggers (37), UNIQUE (41),
#                    EXCLUDE (11), policies (82), vistas (3) ni la matriz de
#                    runtime, porque 0300 es integridad declarativa pura. El
#                    diccionario HUELLAS no cambia: 0300 no toca el prosrc de
#                    ninguna funcion. Usar --head 0300.
#                    ATENCION: 0310 (segunda invariante de D-169) NO esta
#                    autorizada; cuando lo este, este contrato volvera a moverse.
#                    v0.8.0: F03-02 / migration 0290: el CONTRATO del final de la cadena
#                    pasa a 26 funciones, 54 triggers no internos y 37
#                    constraint triggers (D-080: una funcion y seis constraint
#                    triggers). Se anade la huella de fn_check_inversion_principal
#                    y se actualiza la de fn_check_inversion_asignacion_suma tras
#                    la reescritura de P4. Ademas, manifest del bootstrap fresh de
#                    instancia 0001..0290
#                    (D-131 refinada por D-136): --head, --junit, --proyecto,
#                    --commit y --manifiesto. Anade la lectura de las ocho
#                    huellas D-111 y del JUnit de la suite, y compone el
#                    veredicto unico PASS_INSTANCE_BOOTSTRAP_F03_0001_<head>.
#                    Respecto de v0.7.3 cambia el contrato por 0290.
# Versión: 0.7.3  -- F03-02 / migration 0288: el CONTRATO sube a 174 FK.
# Versión: 0.7.2  -- F03-02 / migration 0286: CONTRATO del final de la cadena
#                    pasa a 80 tablas, 82 policies, 169 FK y 41 UNIQUE.
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
import json
import uuid
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import os
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover
    sys.exit("Falta psycopg. Instala con: python -m pip install \"psycopg[binary]\"")


# Contrato fisico esperado al final de la cadena (0290). Base: D-109; 0270
# anade 4 funciones, 5 triggers y 4 constraint triggers; 0280 cambia 1 funcion
# por 3, 6 triggers BEFORE por 7 constraint triggers y anade 3 UNIQUE; 0286
# anade la tabla puente efecto_cuentas (+1 tabla, +1 policy, +3 FK, +1 UNIQUE,
# +1 SELECT/INSERT/UPDATE de runtime, sin funciones ni triggers); 0288 sube a
# 174 FK sin tocar funciones ni triggers; 0290 anade la funcion
# fn_check_inversion_principal y seis constraint triggers de D-080, y reescribe
# fn_check_inversion_asignacion_suma dejando el advisory como unico lock root;
# 0300 (D-168/D-169) repara la FK compuesta de pertenencia hecho<->conciliacion
# aprobada por D-057 y nunca materializada, subiendo a 175 FK sin tocar
# funciones, triggers, policies ni columnas. El indice compuesto que 0300 anade
# no figura aqui porque este CONTRATO no cuenta indices; lo cubre la huella h3.
# Desde v0.10.0 el contrato esta indexado por head: ver CONTRATOS_POR_HEAD.
CONTRATO_0300 = {
    "tablas": 80,
    "force_rls": 75,
    "policies": 82,
    "foreign_keys": 175,
    "unique_constraints": 41,
    "exclude_constraints": 11,
    "funciones": 26,
    "security_definer": 1,
    "vistas_security_invoker": 3,
    "triggers_no_internos": 54,
    "constraint_triggers": 37,
    "triggers_deshabilitados": 0,
    "policies_autorreferentes": 0,
    "fk_tenant_sin_validar": 0,
    "runtime_select": 80,
    "runtime_insert": 74,
    "runtime_update": 68,
    "runtime_delete": 36,
}

# 0310 (D-169/D-170/D-171) materializa la invariante agregada de aportaciones
# frente a porcion conciliada: dos funciones nuevas y cuatro constraint
# triggers diferidos. No toca tablas, FK, UNIQUE, EXCLUDE, policies, vistas,
# GRANTs ni la matriz runtime. Contrato MEDIDO, no previsto.
CONTRATO_0310 = {**CONTRATO_0300, "funciones": 28,
                 "triggers_no_internos": 58, "constraint_triggers": 41}

# Conjunto EXPLICITO Y FINITO de heads con contrato declarado. No se acepta
# "cualquier sucesor": un head desconocido aborta en lugar de compararse
# contra un contrato que no es el suyo.
CONTRATOS_POR_HEAD = {
    "0300": CONTRATO_0300,
    "0310": CONTRATO_0310,
}

# Head vigente de la cadena cuando no se declara --head.
CONTRATO_POR_DEFECTO = CONTRATO_0310


def contrato_de(head):
    """Contrato fisico esperado para el head declarado."""
    if head is None:
        return CONTRATO_POR_DEFECTO
    if head not in CONTRATOS_POR_HEAD:
        sys.exit(
            f"--head {head} no tiene contrato fisico declarado en este runner. "
            f"Heads con contrato: {', '.join(sorted(CONTRATOS_POR_HEAD))}. "
            "Declarar uno nuevo es una decision arquitectonica, no un ajuste del runner."
        )
    return CONTRATOS_POR_HEAD[head]

HUELLAS = {
    "fn_registrar_auditoria": "5a9e6ce8e8dc402b3123e3bf5c718725",
    "fn_check_participacion_suma": "b76161555c227a8aa19c3ab513aa4687",
    "fn_check_bolsa_prioridad_alcance": "d1d83d6e38a15190244a26be50d90ad4",
    "fn_check_inversion_asignacion_suma": "3ffd4236dea6f3ad75ad5ffacc5dd247",
    "fn_check_inversion_principal": "1f2cbd5647ae5a013121bdadc41b6c8a",
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


# Identidad unica de esta ejecucion (D-177 §3). Se registra en el manifest para
# que dos ejecuciones nunca sean confundibles aunque compartan entorno y head.
RUN_ID = uuid.uuid4().hex[:12]
AHORA_UTC = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def raiz_repositorio() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def problemas_de_ruta_de_evidencia(ruta: Path, raiz: Path, debe_existir: bool) -> list[str]:
    """Discrepancias de una ruta de artefacto frente a la politica de D-177 §3.

    Lista vacia = la ruta es aceptable. Funcion pura sobre rutas: no toca disco
    salvo para resolver y comprobar existencia, de modo que es verificable.

    Dos reglas, y ninguna es cosmetica:
      1. la evidencia se escribe FUERA del repositorio. Escribirla dentro y
         moverla despues fue exactamente lo que perdio cuatro artefactos del
         clean-room: logs/ esta en .gitignore y se borra con cada descarga.
      2. un manifest nuevo NO puede sobrescribir uno existente. Reutilizar un
         nombre fijo para ejecuciones distintas fue lo que borro el log de la
         ejecucion anomala de R7.
    """
    problemas: list[str] = []
    resuelta = ruta.resolve()
    if resuelta.is_relative_to(raiz.resolve()):
        problemas.append(
            f"{resuelta} esta DENTRO del repositorio ({raiz}); la evidencia del gate "
            "se escribe directamente fuera, no se mueve despues")
    if debe_existir:
        if not resuelta.is_file():
            problemas.append(f"{resuelta} no existe y se esperaba un manifest de fase 1")
    elif resuelta.exists():
        problemas.append(
            f"{resuelta} YA existe; un artefacto de evidencia nunca se sobrescribe. "
            "Usa un nombre unico (marca UTC + run_id + entorno + tipo)")
    return problemas


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


# Frontera de provisioning. 0002 crea gapto_ext, instala btree_gist y pg_trgm
# dentro de el, y crea gapto. Todo con CREATE ... sin IF NOT EXISTS, de modo que
# cualquier residuo hace fallar la migration.
NAMESPACES_DE_APLICACION = ("gapto", "gapto_ext")
EXTENSIONES_DE_APLICACION = ("btree_gist", "pg_trgm")


def estado_de_provisioning(conexion) -> dict:
    """Lee la frontera real, no solo el schema gapto."""
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname = ANY(%s)",
            (list(NAMESPACES_DE_APLICACION),))
        presentes = {fila[0] for fila in cursor.fetchall()}
        cursor.execute(
            "SELECT e.extname, n.nspname FROM pg_catalog.pg_extension e "
            "  JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace "
            " WHERE e.extname = ANY(%s)",
            (list(EXTENSIONES_DE_APLICACION),))
        extensiones = dict(cursor.fetchall())
    return {
        "schemas": {nombre: (nombre in presentes) for nombre in NAMESPACES_DE_APLICACION},
        "extensiones": {nombre: extensiones.get(nombre) for nombre in EXTENSIONES_DE_APLICACION},
    }


def problemas_de_frontera(estado: dict, incluye_0002: bool) -> list[str]:
    """Discrepancias entre el estado observado y el esperado en ese punto.

    Lista vacia = la base esta en la frontera contractual correcta.

    NO se impone "gapto_ext siempre ausente": si el tramo empieza despues de
    0002, ambos schemas DEBEN existir ya, y su ausencia es tan sospechosa como
    su presencia cuando 0002 va a crearlos.
    """
    problemas: list[str] = []
    for nombre, presente in estado["schemas"].items():
        if incluye_0002 and presente:
            problemas.append(
                f"el schema {nombre} YA existe y 0002 lo crea con CREATE SCHEMA "
                "sin IF NOT EXISTS")
        if not incluye_0002 and not presente:
            problemas.append(
                f"el schema {nombre} NO existe y el tramo empieza despues de 0002, "
                "que es quien lo crea")
    if incluye_0002:
        for nombre, schema in estado["extensiones"].items():
            if schema is not None:
                problemas.append(
                    f"la extension {nombre} ya esta instalada en el schema {schema} "
                    "y 0002 la crea WITH SCHEMA gapto_ext")
    return problemas


def base_esta_vacia(conexion) -> bool:
    """Compatibilidad: virginidad para un tramo que incluye 0002."""
    return not problemas_de_frontera(estado_de_provisioning(conexion), True)


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


def leer_huellas_d111(conexion) -> dict:
    """Las ocho huellas D-111, calculadas con el mismo script canonico que se
    usa contra los proveedores. Son OBSERVADAS: salen del catalogo."""
    fichero = raiz_repositorio() / "scripts" / "postgres" / "huellas_d111.sql"
    with conexion.cursor() as cursor:
        cursor.execute(fichero.read_text(encoding="utf-8"))
        fila = cursor.fetchone()
        nombres = [d.name for d in cursor.description]
    return dict(zip(nombres, fila))


def leer_junit(ruta: Path) -> dict:
    """Resultado de la suite completa. Es OBSERVADO, pero de segunda mano: lo
    produjo pytest, no este script. Se registra tal cual, sin interpretarlo."""
    raiz = ET.parse(ruta).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else list(raiz.iter("testsuite"))
    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for clave in total:
            total[clave] += int(s.get(clave, 0) or 0)
    total["fichero"] = ruta.name
    return total


def veredicto(head: str, fallos: list[str], incluye_0001: bool,
              junit: dict | None, base_virgen: bool) -> tuple[str, list[str]]:
    """Un unico resultado, y las razones exactas si no es PASS. No se emite
    PASS si falta cualquiera de las condiciones de D-136."""
    razones = list(fallos)
    if not incluye_0001:
        razones.append("la cadena no incluyo 0001: esto no es bootstrap de instancia")
    if not base_virgen:
        razones.append("la base no estaba virgen al empezar")
    faltan_junit = junit is None
    if faltan_junit:
        razones.append("no se aporto el JUnit de la suite completa (--junit)")
    if not faltan_junit:
        if junit["tests"] == 0:
            razones.append("el JUnit no contiene ningun test")
        if junit["failures"] or junit["errors"]:
            razones.append(
                f"la suite no esta verde: failures={junit['failures']} errors={junit['errors']}")
    etiqueta = f"PASS_INSTANCE_BOOTSTRAP_F03_0001_{head}"
    return (etiqueta if not razones else f"FALLO_INSTANCE_BOOTSTRAP_F03_0001_{head}"), razones


def escribir_manifiesto(ruta: Path, observado: dict, declarado: dict,
                        resultado: str, razones: list[str]) -> None:
    contenido = {
        "artefacto": "run_clean_room.py",
        "version": "0.10.2",
        "decision": "D-131 refinada por D-136, D-172, D-177",
        "run_id": RUN_ID,
        "generado_utc": AHORA_UTC,
        "resultado": resultado,
        "razones": razones,
        "observado": observado,
        "declarado": declarado,
        "nota": ("declarado = afirmaciones del operador que este script no puede "
                 "verificar; observado = leido del catalogo de la base y del JUnit"),
    }
    ruta.write_text(json.dumps(contenido, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean-room de GaptoMobile 2027")
    parser.add_argument("--desde", default=None,
                        help="nombre de fichero desde el que empezar, p.ej. 0002")
    parser.add_argument("--solo-verificar", action="store_true",
                        help="no aplica migrations; solo comprueba el contrato")
    parser.add_argument("--permitir-sucia", action="store_true",
                        help="aplica aunque el schema gapto ya exista")
    parser.add_argument("--head", default=None,
                        help="migration final declarada, p.ej. 0290; activa el manifest")
    parser.add_argument("--junit", default=None,
                        help="JUnit de la suite completa ejecutada contra esta base")
    parser.add_argument("--proyecto", default=None,
                        help="identificador del proyecto nuevo (declarado)")
    parser.add_argument("--commit", default=None,
                        help="commit candidato al cierre de fase (declarado)")
    parser.add_argument("--manifiesto", default=None,
                        help="ruta del manifest JSON a escribir (fase 1)")
    parser.add_argument("--completar-manifiesto", default=None, dest="completar",
                        help="ruta de un manifest de fase 1 al que adjuntar el JUnit")
    args = parser.parse_args()

    if args.manifiesto and not args.head:
        sys.exit("--manifiesto exige --head: el veredicto se compone con la migration final declarada.")

    raiz = raiz_repositorio()
    for etiqueta, ruta, debe_existir in (
            ("--manifiesto", args.manifiesto, False),
            ("--completar-manifiesto", args.completar, True)):
        if not ruta:
            continue
        problemas = problemas_de_ruta_de_evidencia(Path(ruta), raiz, debe_existir)
        if problemas:
            detalle = "".join(f"\n  - {p}" for p in problemas)
            sys.exit(f"\nRuta de evidencia no aceptable para {etiqueta}:{detalle}")
    if args.junit and Path(args.junit).resolve().is_relative_to(raiz.resolve()):
        print(f"AVISO: el JUnit {args.junit} vive dentro del repositorio. Se leera "
              "igualmente, pero no sobrevivira a una descarga limpia: conservalo "
              "fuera antes de cerrar el paquete de evidencia.")

    if args.completar:
        if not args.junit:
            sys.exit("--completar-manifiesto exige --junit con la suite completa.")
        args.solo_verificar = True
        args.head = args.head or json.loads(
            Path(args.completar).read_text(encoding="utf-8"))["declarado"]["head_declarado"]

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

        vacia = False
        if args.solo_verificar:
            incluye_0001 = False
        else:
            preflight_roles(conexion, incluye_0001)
            incluye_0002 = any(f.name.startswith("0002") for f in ficheros)
            estado = estado_de_provisioning(conexion)
            problemas_frontera = problemas_de_frontera(estado, incluye_0002)
            vacia = not problemas_frontera
            print("\nFrontera de provisioning "
                  f"({'la cadena incluye 0002' if incluye_0002 else 'el tramo empieza despues de 0002'}):")
            for nombre, presente in estado["schemas"].items():
                print(f"  schema {nombre:<10} {'presente' if presente else 'ausente'}")
            for nombre, schema in estado["extensiones"].items():
                print(f"  extension {nombre:<10} {schema or 'ausente'}")
            if problemas_frontera and not args.permitir_sucia:
                detalle = "".join(f"\n  - {p}" for p in problemas_frontera)
                sys.exit(
                    f"\nLa base '{base}' NO esta en la frontera contractual esperada:{detalle}"
                    "\n\nUsa una base virgen, o --permitir-sucia si sabes lo que haces."
                )
            print(f"\nAplicando {len(ficheros)} migrations desde "
                  f"{ficheros[0].name} hasta {ficheros[-1].name}:\n")
            aplicar(conexion, ficheros)

        problemas_rol = postflight_roles(conexion) if incluye_0001 else []

        contrato = leer_contrato(conexion)
        huellas = leer_huellas(conexion)
        huellas_d111 = leer_huellas_d111(conexion) if args.head else None

    fallos = list(problemas_rol)
    fallos += comparar(contrato, contrato_de(args.head), "CONTRATO FISICO")
    fallos += comparar(huellas, HUELLAS, "HUELLAS DE FUNCION (md5 de prosrc)")

    print()
    if fallos:
        print(f"RESULTADO: FALLO. {len(fallos)} discrepancias:")
        for f in fallos:
            print(f"  - {f}")
        return 1

    print("RESULTADO: OK.")
    print()

    if args.head:
        junit = leer_junit(Path(args.junit)) if args.junit else None
        fase1 = None
        if args.completar:
            fase1 = json.loads(Path(args.completar).read_text(encoding="utf-8"))
            if fase1["observado"]["huellas_d111"] != huellas_d111:
                print("VEREDICTO: FALLO_INSTANCE_BOOTSTRAP_F03_0001_" + args.head)
                print("  - las ocho huellas han cambiado entre la fase 1 y la fase 2")
                return 1
        creo_roles = (fase1["observado"]["roles_creados_en_esta_ejecucion"] if fase1
                      else incluye_0001)
        virgen = fase1["observado"]["base_virgen_al_empezar"] if fase1 else vacia
        resultado, razones = veredicto(args.head, fallos, creo_roles, junit, virgen)
        observado = {
            "base": base,
            "motor": version.split(" on ")[0],
            "migrations_aplicadas": (fase1["observado"]["migrations_aplicadas"] if fase1
                                     else [f.name for f in ficheros]),
            "head_observado": (fase1["observado"]["head_observado"] if fase1
                               else ficheros[-1].name[:4]),
            "contrato_fisico": contrato,
            "huellas_d111": huellas_d111,
            "huellas_prosrc": huellas,
            "roles_creados_en_esta_ejecucion": creo_roles,
            "base_virgen_al_empezar": virgen,
            "suite": junit,
        }
        declarado = {
            "head_declarado": args.head,
            "proyecto": args.proyecto or (fase1["declarado"]["proyecto"] if fase1 else None),
            "commit": args.commit or (fase1["declarado"]["commit"] if fase1 else None),
            "proyecto_nuevo_sin_roles_gapto_previos": bool(
                args.proyecto or (fase1 and fase1["declarado"]["proyecto"])) and creo_roles,
        }
        if not args.completar and args.manifiesto and junit is None:
            resultado, razones = "PENDIENTE_SUITE", [
                "fase 1 completada; falta ejecutar la suite y completar el manifest "
                "con --completar-manifiesto y --junit"]
        if observado["head_observado"] != args.head:
            razones.append(
                f"head observado {observado['head_observado']} != head declarado {args.head}")
            resultado = f"FALLO_INSTANCE_BOOTSTRAP_F03_0001_{args.head}"
        print(f"VEREDICTO: {resultado}")
        for r in razones:
            print(f"  - {r}")
        destino = args.completar or args.manifiesto
        if destino:
            escribir_manifiesto(Path(destino), observado, declarado, resultado, razones)
            print(f"Manifest escrito en {destino}")
        if razones and resultado != "PENDIENTE_SUITE":
            return 1
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
