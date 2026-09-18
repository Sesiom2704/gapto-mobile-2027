# ============================================================
# GAPTO MOBILE 2027
# Fichero: reglas_repository.py
# Ruta: backend/app/repositories/reglas_repository.py
# Descripcion: Acceso SQL a gapto.reglas_financieras, gapto.regla_versiones y
#   gapto.regla_excepciones.
#
#   LA PIEZA CRITICA DE ESTE MODULO ES `bloquear_regla`.
#
#   No existe UNIQUE ni EXCLUDE sobre la identidad logica de ocurrencia
#   (regla + fecha_objetivo_regla) en `previsiones` —y no podria anadirse
#   mecanicamente, porque `previsiones` guarda `regla_version_id`, no
#   `regla_id`, de modo que un UNIQUE por version permitiria duplicar la misma
#   ocurrencia logica al atravesar dos versiones—. R-F04-017.
#
#   Consecuencia: la unicidad de ocurrencia y la unicidad de la cabeza RODANTE
#   son invariantes de SERVICIO/TRANSACCION, y su unica autoridad es este lock.
#   El protocolo es SIEMPRE:
#
#       LOCK regla -> releer -> calcular identidad -> comprobar existente
#                  -> insertar
#
#   y NUNCA calcular el candidato antes de adquirir el lock. Si alguna ruta
#   futura omitiese ese orden, crearia duplicados que PostgreSQL 0310 no
#   detectaria.
#
#   `bloquear_regla` NO incrementa `row_version`: generar previsiones no
#   modifica la configuracion de la regla. El bump se reserva a los cambios de
#   configuracion, via `tocar_regla`.
#
#   Las invariantes que PostgreSQL ya garantiza se CONSUMEN, no se reimplementan:
#   `ex_regla_versiones__regla` es la autoridad del no-solapamiento y
#   `uq_regla_excepciones__regla_fecha` la de una excepcion por identidad.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA_REGLAS = "reglas_financieras"
TABLA_VERSIONES = "regla_versiones"
TABLA_EXCEPCIONES = "regla_excepciones"

TIPOS_SQL_REGLA: dict[str, str] = {
    "id": "uuid",
    "nombre": "varchar",
    "entidad_origen_id": "uuid",
}

TIPOS_SQL_VERSION: dict[str, str] = {
    "id": "uuid",
    "regla_id": "uuid",
    "vigente_desde": "date",
    "vigente_hasta": "date",
    "tipo_hecho_id": "uuid",
    "flujo_tesoreria_esperado": "varchar",
    "categoria_id": "uuid",
    "tercero_id": "uuid",
    "cuenta_salida_esperada_id": "uuid",
    "cuenta_entrada_esperada_id": "uuid",
    "moneda": "varchar",
    "importe_referencia_lado": "varchar",
    "periodicidad": "varchar",
    "intervalo": "smallint",
    "fecha_modo": "varchar",
    "dia_desde": "smallint",
    "dia_hasta": "smallint",
    "importe_modo": "varchar",
    "importe_fijo": "numeric",
    "cuenta_calculo_id": "uuid",
    "saldo_objetivo": "numeric",
    "meses_historico": "smallint",
    "presupuestable": "boolean",
    "anclaje_recurrencia": "varchar",
}

TIPOS_SQL_EXCEPCION: dict[str, str] = {
    "id": "uuid",
    "regla_id": "uuid",
    "fecha_objetivo": "date",
    "omitida": "boolean",
    "importe_override": "numeric",
    "fecha_override": "date",
    "motivo": "text",
}


def _snapshot(alias: str, columnas: dict[str, str]) -> sql.Composed:
    partes = [
        sql.SQL("{}, {}.{}").format(
            sql.Literal(columna), sql.Identifier(alias), sql.Identifier(columna)
        )
        for columna in columnas
    ]
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes))


def _jsonb_desde_valores(
    valores: dict[str, Any], columnas: dict[str, str]
) -> tuple[sql.Composed, list[Any]]:
    partes: list[sql.Composed] = []
    params: list[Any] = []
    for columna, valor in valores.items():
        partes.append(
            sql.SQL("{}, %s::{}").format(
                sql.Literal(columna), sql.SQL(columnas[columna])
            )
        )
        params.append(valor)
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes)), params


# ==================================================================
# Lock de regla — la autoridad de R-F04-017
# ==================================================================

def bloquear_regla(sesion: SesionMotor, regla_id: uuid.UUID) -> int | None:
    """Serializa sobre la fila de la regla y devuelve su row_version.

    `FOR UPDATE` sin incremento: generar no cambia la configuracion. Toda
    generacion —CALENDARIO o RODANTE— debe llamar a esto ANTES de calcular
    cualquier candidato. Devuelve None si la regla no existe o es de otro
    tenant.
    """
    fila = sesion.uno(
        "SELECT row_version FROM gapto.reglas_financieras "
        "WHERE id = %s::uuid FOR UPDATE",
        (regla_id,),
    )
    return None if fila is None else fila[0]


def tocar_regla(
    sesion: SesionMotor, regla_id: uuid.UUID, row_version_esperada: int
) -> int | None:
    """Incrementa la version de la regla. Solo para cambios de CONFIGURACION.

    Nombre, versionado, pausa/reanudacion y excepciones. Nunca generacion.
    """
    fila = sesion.uno(
        """
        UPDATE gapto.reglas_financieras AS r
           SET updated_at = CURRENT_TIMESTAMP,
               row_version = r.row_version + 1
         WHERE r.id = %s::uuid
           AND r.row_version = %s
        RETURNING r.row_version
        """,
        (regla_id, row_version_esperada),
    )
    return None if fila is None else fila[0]


# ==================================================================
# Reglas
# ==================================================================

def insertar_regla_si_no_existe(
    sesion: SesionMotor,
    *,
    regla_id: uuid.UUID,
    nombre: str,
    entidad_origen_id: uuid.UUID | None,
) -> tuple[int, str] | None:
    consulta = sql.SQL(
        """
        INSERT INTO gapto.reglas_financieras (
            id, owner_user_id, nombre, entidad_origen_id)
        VALUES (%s::uuid, current_setting('gapto.owner_user_id')::uuid,
                %s::varchar, %s::uuid)
        ON CONFLICT (id) DO NOTHING
        RETURNING row_version, ({})::text
        """
    ).format(_snapshot("reglas_financieras", TIPOS_SQL_REGLA))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (regla_id, nombre, entidad_origen_id))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


def leer_regla(sesion: SesionMotor, regla_id: uuid.UUID) -> dict[str, Any] | None:
    """Sin lock. Para lecturas que no generan."""
    consulta = sql.SQL(
        """
        SELECT r.row_version, r.nombre, r.entidad_origen_id, ({})::text
          FROM gapto.reglas_financieras r
         WHERE r.id = %s::uuid
        """
    ).format(_snapshot("r", TIPOS_SQL_REGLA))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (regla_id,))
        fila = cursor.fetchone()
    if fila is None:
        return None
    return {
        "row_version": fila[0],
        "nombre": fila[1],
        "entidad_origen_id": fila[2],
        "snapshot": fila[3],
    }


# ==================================================================
# Versiones
# ==================================================================

def insertar_version(sesion: SesionMotor, valores: dict[str, Any]) -> str | None:
    """Alta de version. El EXCLUDE fisico es la autoridad del no-solapamiento.

    Se deja que PostgreSQL lo rechace y el servicio traduce la violacion a
    VERSION_REGLA_SOLAPADA; comprobarlo tambien en Python crearia una segunda
    fuente de verdad que puede divergir.
    """
    columnas = list(TIPOS_SQL_VERSION.keys())
    destino = sql.SQL(", ").join(sql.Identifier(c) for c in columnas)
    marcas = sql.SQL(", ").join(
        sql.SQL("%s::{}").format(sql.SQL(TIPOS_SQL_VERSION[c])) for c in columnas
    )
    consulta = sql.SQL(
        """
        INSERT INTO gapto.regla_versiones ({})
        VALUES ({})
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(destino, marcas, _snapshot("regla_versiones", TIPOS_SQL_VERSION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, tuple(valores.get(c) for c in columnas))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def cerrar_version(
    sesion: SesionMotor, version_id: uuid.UUID, vigente_hasta: dt.date
) -> tuple[str, str] | None:
    """Cierra la vigencia de una version. (snapshot_antes, snapshot_despues).

    Cerrar una version NO la reescribe: su condicion funcional permanece. Solo
    deja de aplicarse a partir de la fecha indicada.
    """
    consulta = sql.SQL(
        """
        WITH previo AS (
            SELECT ({})::text AS snap FROM gapto.regla_versiones v
             WHERE v.id = %s::uuid
        )
        UPDATE gapto.regla_versiones AS v
           SET vigente_hasta = %s::date
         WHERE v.id = %s::uuid
        RETURNING (SELECT snap FROM previo), ({})::text
        """
    ).format(_snapshot("v", TIPOS_SQL_VERSION), _snapshot("v", TIPOS_SQL_VERSION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (version_id, vigente_hasta, version_id))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


def leer_version(sesion: SesionMotor, version_id: uuid.UUID) -> dict[str, Any] | None:
    consulta = sql.SQL(
        """
        SELECT v.regla_id, v.vigente_desde, v.vigente_hasta, v.periodicidad,
               v.intervalo, v.anclaje_recurrencia, v.fecha_modo, v.dia_desde,
               v.dia_hasta, v.importe_modo, v.importe_fijo, v.moneda,
               v.cuenta_calculo_id, v.saldo_objetivo, v.meses_historico,
               v.flujo_tesoreria_esperado, ({})::text
          FROM gapto.regla_versiones v
         WHERE v.id = %s::uuid
        """
    ).format(_snapshot("v", TIPOS_SQL_VERSION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (version_id,))
        fila = cursor.fetchone()
    if fila is None:
        return None
    nombres = (
        "regla_id",
        "vigente_desde",
        "vigente_hasta",
        "periodicidad",
        "intervalo",
        "anclaje_recurrencia",
        "fecha_modo",
        "dia_desde",
        "dia_hasta",
        "importe_modo",
        "importe_fijo",
        "moneda",
        "cuenta_calculo_id",
        "saldo_objetivo",
        "meses_historico",
        "flujo_tesoreria_esperado",
        "snapshot",
    )
    return dict(zip(nombres, fila))


def listar_versiones(sesion: SesionMotor, regla_id: uuid.UUID) -> list[dict[str, Any]]:
    """Versiones de la regla, en orden cronologico de vigencia.

    Sirve para detectar pausas —un hueco entre `vigente_hasta` de una y
    `vigente_desde` de la siguiente— y cambios de cadencia que rompen segmento.
    """
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, vigente_desde, vigente_hasta, periodicidad, intervalo,
                   anclaje_recurrencia
              FROM gapto.regla_versiones
             WHERE regla_id = %s::uuid
             ORDER BY vigente_desde, id
            """,
            (regla_id,),
        )
        return [
            {
                "id": f[0],
                "vigente_desde": f[1],
                "vigente_hasta": f[2],
                "periodicidad": f[3],
                "intervalo": f[4],
                "anclaje_recurrencia": f[5],
            }
            for f in cursor.fetchall()
        ]


def version_vigente_en(
    sesion: SesionMotor, regla_id: uuid.UUID, fecha: dt.date
) -> uuid.UUID | None:
    """Version que gobierna esa fecha. Vigencia INCLUSIVA en ambos extremos.

    Devuelve None cuando la fecha cae en una pausa: un hueco sin version no
    genera nada y no acumula backlog.
    """
    fila = sesion.uno(
        """
        SELECT id FROM gapto.regla_versiones
         WHERE regla_id = %s::uuid
           AND vigente_desde <= %s::date
           AND (vigente_hasta IS NULL OR vigente_hasta >= %s::date)
         ORDER BY vigente_desde DESC
         LIMIT 1
        """,
        (regla_id, fecha, fecha),
    )
    return None if fila is None else fila[0]


# ==================================================================
# Excepciones
# ==================================================================

def insertar_excepcion(sesion: SesionMotor, valores: dict[str, Any]) -> str | None:
    """Alta de excepcion. `uq_regla_excepciones__regla_fecha` es la autoridad
    de una sola fila por identidad."""
    consulta = sql.SQL(
        """
        INSERT INTO gapto.regla_excepciones (
            id, regla_id, fecha_objetivo, omitida, importe_override,
            fecha_override, motivo)
        VALUES (%s::uuid, %s::uuid, %s::date, %s::boolean, %s::numeric,
                %s::date, %s::text)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot("regla_excepciones", TIPOS_SQL_EXCEPCION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                valores["id"],
                valores["regla_id"],
                valores["fecha_objetivo"],
                valores["omitida"],
                valores["importe_override"],
                valores["fecha_override"],
                valores["motivo"],
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def leer_excepcion(
    sesion: SesionMotor, regla_id: uuid.UUID, fecha_objetivo: dt.date
) -> dict[str, Any] | None:
    """Excepcion por identidad de ocurrencia."""
    consulta = sql.SQL(
        """
        SELECT e.id, e.omitida, e.importe_override, e.fecha_override, e.motivo,
               ({})::text
          FROM gapto.regla_excepciones e
         WHERE e.regla_id = %s::uuid AND e.fecha_objetivo = %s::date
        """
    ).format(_snapshot("e", TIPOS_SQL_EXCEPCION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (regla_id, fecha_objetivo))
        fila = cursor.fetchone()
    if fila is None:
        return None
    return {
        "id": fila[0],
        "omitida": fila[1],
        "importe_override": fila[2],
        "fecha_override": fila[3],
        "motivo": fila[4],
        "snapshot": fila[5],
    }


def actualizar_excepcion(
    sesion: SesionMotor, excepcion_id: uuid.UUID, cambios: dict[str, Any]
) -> tuple[str, str] | None:
    """Correccion auditada de una excepcion. (snapshot_antes, despues)."""
    if not cambios:
        return None
    asignaciones = [
        sql.SQL("{} = %s::{}").format(
            sql.Identifier(columna), sql.SQL(TIPOS_SQL_EXCEPCION[columna])
        )
        for columna in cambios
    ]
    consulta = sql.SQL(
        """
        WITH previo AS (
            SELECT ({})::text AS snap FROM gapto.regla_excepciones e
             WHERE e.id = %s::uuid
        )
        UPDATE gapto.regla_excepciones AS e
           SET {}, updated_at = CURRENT_TIMESTAMP
         WHERE e.id = %s::uuid
        RETURNING (SELECT snap FROM previo), ({})::text
        """
    ).format(
        _snapshot("e", TIPOS_SQL_EXCEPCION),
        sql.SQL(", ").join(asignaciones),
        _snapshot("e", TIPOS_SQL_EXCEPCION),
    )
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta, (excepcion_id, *cambios.values(), excepcion_id)
        )
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


def creacion_previa_coincide(
    sesion: SesionMotor,
    tabla: str,
    registro_id: uuid.UUID,
    valores: dict[str, Any],
    columnas: dict[str, str],
) -> bool:
    """Compara la intencion contra el snapshot DE CREACION auditado."""
    snapshot_sql, params = _jsonb_desde_valores(valores, columnas)
    consulta = sql.SQL(
        """
        SELECT a.datos_despues @> ({})
          FROM gapto.auditoria a
         WHERE a.tabla = %s
           AND a.registro_id = %s::uuid
           AND a.accion = 'CREAR'
         ORDER BY a.created_at, a.id
         LIMIT 1
        """
    ).format(snapshot_sql)
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (*params, tabla, registro_id))
        fila = cursor.fetchone()
    return bool(fila is not None and fila[0])


def resolver_tipo_hecho(sesion: SesionMotor, codigo: str) -> uuid.UUID | None:
    fila = sesion.uno(
        "SELECT id FROM gapto.tipos_hecho WHERE codigo = %s", (codigo,)
    )
    return None if fila is None else fila[0]
