# ============================================================
# GAPTO MOBILE 2027
# Fichero: previsiones_repository.py
# Ruta: backend/app/repositories/previsiones_repository.py
# Descripcion: Acceso SQL a gapto.previsiones y gapto.prevision_hechos.
#
#   IDENTIDAD LOGICA DE OCURRENCIA. Es `regla_id + fecha_objetivo_regla`, pero
#   `previsiones` guarda `regla_version_id`, NO `regla_id`. Toda consulta por
#   identidad tiene que pasar por `JOIN regla_versiones`. Eso no es un detalle
#   de implementacion: es la razon por la que un UNIQUE fisico por
#   (regla_version_id, fecha_objetivo_regla) NO seria equivalente —permitiria
#   duplicar la misma ocurrencia logica al atravesar dos versiones— y por la
#   que la unicidad la sostiene el lock de regla (R-F04-017).
#
#   EL SALDO DE REALIDAD NO SE PERSISTE. `resumen_realidad` lo deriva contando
#   solo hechos ACTIVOS. Los ANULADO quedan fuera por el propio WHERE, nunca
#   por un filtro posterior que alguien pueda olvidar: de eso depende AMB-009.
#
#   `importe_real` de una ocurrencia es SUM(prevision_hechos.importe_asignado)
#   sobre hechos ACTIVOS. Nunca `hechos_financieros.importe_total`, ni
#   movimientos, ni efectos, ni el importe esperado.
#
#   CORRECCION DE VINCULO (F04-D021). `actualizar_vinculo` conserva el mismo
#   `id` y el `created_at` original, y admite cambiar importe, hecho o
#   previsión. `borrar_vinculo` devuelve el snapshot completo antes de
#   eliminar, y se reserva al vinculo que nunca debio existir sin sustituto.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any, Sequence

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA_PREVISIONES = "previsiones"
TABLA_VINCULOS = "prevision_hechos"

TIPOS_SQL_PREVISION: dict[str, str] = {
    "id": "uuid",
    "regla_version_id": "uuid",
    "fecha_objetivo_regla": "date",
    "concepto": "varchar",
    "tipo_hecho_id": "uuid",
    "categoria_id": "uuid",
    "tercero_id": "uuid",
    "entidad_id": "uuid",
    "fecha_esperada_desde": "date",
    "fecha_esperada_hasta": "date",
    "flujo_tesoreria_esperado": "varchar",
    "moneda": "varchar",
    "importe_esperado": "numeric",
    "importe_referencia_lado": "varchar",
    "cuenta_salida_esperada_id": "uuid",
    "cuenta_entrada_esperada_id": "uuid",
    "presupuestable": "boolean",
    "estado": "varchar",
    "recalculo_automatico": "boolean",
    "motivo_ajuste": "text",
}

# Campos del snapshot que una nueva version de regla puede regobernar. NO
# incluye `fecha_objetivo_regla`: la identidad canonica es inmutable.
CAMPOS_REGOBERNABLES: tuple[str, ...] = (
    "regla_version_id",
    "concepto",
    "tipo_hecho_id",
    "categoria_id",
    "tercero_id",
    "entidad_id",
    "fecha_esperada_desde",
    "fecha_esperada_hasta",
    "flujo_tesoreria_esperado",
    "moneda",
    "importe_esperado",
    "importe_referencia_lado",
    "cuenta_salida_esperada_id",
    "cuenta_entrada_esperada_id",
    "presupuestable",
)

TIPOS_SQL_VINCULO: dict[str, str] = {
    "id": "uuid",
    "prevision_id": "uuid",
    "hecho_id": "uuid",
    "importe_asignado": "numeric",
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
# Previsiones
# ==================================================================

def insertar_prevision(sesion: SesionMotor, valores: dict[str, Any]) -> str | None:
    columnas = list(TIPOS_SQL_PREVISION.keys())
    destino = sql.SQL(", ").join(sql.Identifier(c) for c in columnas)
    marcas = sql.SQL(", ").join(
        sql.SQL("%s::{}").format(sql.SQL(TIPOS_SQL_PREVISION[c])) for c in columnas
    )
    consulta = sql.SQL(
        """
        INSERT INTO gapto.previsiones (owner_user_id, {})
        VALUES (current_setting('gapto.owner_user_id')::uuid, {})
        ON CONFLICT (id) DO NOTHING
        RETURNING row_version, ({})::text
        """
    ).format(destino, marcas, _snapshot("previsiones", TIPOS_SQL_PREVISION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, tuple(valores.get(c) for c in columnas))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


def leer_prevision(
    sesion: SesionMotor, prevision_id: uuid.UUID
) -> dict[str, Any] | None:
    """Estado completo, incluido el `regla_id` resuelto por JOIN."""
    consulta = sql.SQL(
        """
        SELECT p.row_version, p.estado, p.recalculo_automatico,
               p.fecha_objetivo_regla, p.regla_version_id, v.regla_id,
               p.moneda, p.importe_esperado, p.fecha_esperada_desde,
               p.fecha_esperada_hasta, ({})::text
          FROM gapto.previsiones p
          LEFT JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
         WHERE p.id = %s::uuid
        """
    ).format(_snapshot("p", TIPOS_SQL_PREVISION))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (prevision_id,))
        fila = cursor.fetchone()
    if fila is None:
        return None
    nombres = (
        "row_version",
        "estado",
        "recalculo_automatico",
        "fecha_objetivo_regla",
        "regla_version_id",
        "regla_id",
        "moneda",
        "importe_esperado",
        "fecha_esperada_desde",
        "fecha_esperada_hasta",
        "snapshot",
    )
    return dict(zip(nombres, fila))


def prevision_por_identidad(
    sesion: SesionMotor, regla_id: uuid.UUID, fecha_objetivo: dt.date
) -> dict[str, Any] | None:
    """Ocurrencia canonica de (regla, fecha_objetivo), atravesando versiones.

    Se busca por `v.regla_id`, no por `regla_version_id`: la misma identidad
    logica puede haber nacido bajo otra version de la regla y seguir siendo la
    misma ocurrencia. Buscar por version permitiria crear un duplicado tras un
    reversionado.
    """
    fila = sesion.uno(
        """
        SELECT p.id, p.estado, p.row_version, p.recalculo_automatico
          FROM gapto.previsiones p
          JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
         WHERE v.regla_id = %s::uuid
           AND p.fecha_objetivo_regla = %s::date
         ORDER BY p.created_at, p.id
         LIMIT 1
        """,
        (regla_id, fecha_objetivo),
    )
    if fila is None:
        return None
    return {
        "id": fila[0],
        "estado": fila[1],
        "row_version": fila[2],
        "recalculo_automatico": fila[3],
    }


def identidades_consumidas(
    sesion: SesionMotor, regla_id: uuid.UUID, estados: tuple[str, ...]
) -> set[dt.date]:
    """Fechas objetivo ya consumidas por la regla en los estados dados.

    Con `('CANCELADA',)` devuelve los tombstones: identidades que no se
    reutilizan ni en un retry ni al cambiar de segmento.
    """
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.fecha_objetivo_regla
              FROM gapto.previsiones p
              JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
             WHERE v.regla_id = %s::uuid
               AND p.estado = ANY(%s::varchar[])
               AND p.fecha_objetivo_regla IS NOT NULL
            """,
            (regla_id, list(estados)),
        )
        return {f[0] for f in cursor.fetchall()}


def cabeza_rodante(sesion: SesionMotor, regla_id: uuid.UUID) -> dict[str, Any] | None:
    """La unica previsión ABIERTA de la cadena, si existe.

    Se lee SIEMPRE despues de haber bloqueado la regla. Si devolviese dos
    filas habria un defecto grave de serializacion, asi que el servicio debe
    comprobar el recuento y no confiar en LIMIT 1.
    """
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.fecha_objetivo_regla, p.row_version,
                   p.recalculo_automatico
              FROM gapto.previsiones p
              JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
             WHERE v.regla_id = %s::uuid
               AND p.estado = 'ABIERTA'
               AND v.anclaje_recurrencia = 'RODANTE'
             ORDER BY p.fecha_objetivo_regla, p.id
            """,
            (regla_id,),
        )
        filas = cursor.fetchall()
    if not filas:
        return None
    return {
        "id": filas[0][0],
        "fecha_objetivo": filas[0][1],
        "row_version": filas[0][2],
        "recalculo_automatico": filas[0][3],
        "abiertas": len(filas),
    }


def ultima_terminal(
    sesion: SesionMotor, regla_id: uuid.UUID
) -> dict[str, Any] | None:
    """Ultima ocurrencia terminal de la regla, por identidad canonica.

    Sirve de ancla al pasar de CALENDARIO a RODANTE. Se ordena por
    `fecha_objetivo_regla`, no por `created_at`: lo que ordena la serie es la
    identidad, no cuando se capturo.
    """
    fila = sesion.uno(
        """
        SELECT p.id, p.fecha_objetivo_regla, p.estado
          FROM gapto.previsiones p
          JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
         WHERE v.regla_id = %s::uuid
           AND p.estado <> 'ABIERTA'
           AND p.fecha_objetivo_regla IS NOT NULL
         ORDER BY p.fecha_objetivo_regla DESC, p.id DESC
         LIMIT 1
        """,
        (regla_id,),
    )
    if fila is None:
        return None
    return {"id": fila[0], "fecha_objetivo": fila[1], "estado": fila[2]}


def tocar_prevision(
    sesion: SesionMotor, prevision_id: uuid.UUID, row_version_esperada: int
) -> int | None:
    """Incrementa la version de la previsión, con la guarda en SQL."""
    fila = sesion.uno(
        """
        UPDATE gapto.previsiones AS p
           SET updated_at = CURRENT_TIMESTAMP,
               row_version = p.row_version + 1
         WHERE p.id = %s::uuid
           AND p.row_version = %s
        RETURNING p.row_version
        """,
        (prevision_id, row_version_esperada),
    )
    return None if fila is None else fila[0]


def bloquear_prevision(
    sesion: SesionMotor, prevision_id: uuid.UUID
) -> int | None:
    """Serializa sobre la previsión sin incrementarla.

    Se usa cuando una operacion atraviesa DOS previsiones —reasignacion
    P1 -> P2— y hay que tomarlas en orden UUID antes de mutar cualquiera.
    """
    fila = sesion.uno(
        "SELECT row_version FROM gapto.previsiones WHERE id = %s::uuid FOR UPDATE",
        (prevision_id,),
    )
    return None if fila is None else fila[0]


def actualizar_prevision(
    sesion: SesionMotor, prevision_id: uuid.UUID, cambios: dict[str, Any]
) -> tuple[str, str] | None:
    """UPDATE auditado. (snapshot_antes, snapshot_despues).

    `fecha_objetivo_regla` NO esta en `CAMPOS_REGOBERNABLES` y el servicio lo
    rechaza: la identidad canonica es inmutable.
    """
    if not cambios:
        return None
    asignaciones = [
        sql.SQL("{} = %s::{}").format(
            sql.Identifier(columna), sql.SQL(TIPOS_SQL_PREVISION[columna])
        )
        for columna in cambios
    ]
    consulta = sql.SQL(
        """
        WITH previo AS (
            SELECT ({})::text AS snap FROM gapto.previsiones p
             WHERE p.id = %s::uuid
        )
        UPDATE gapto.previsiones AS p
           SET {}, updated_at = CURRENT_TIMESTAMP
         WHERE p.id = %s::uuid
        RETURNING (SELECT snap FROM previo), ({})::text
        """
    ).format(
        _snapshot("p", TIPOS_SQL_PREVISION),
        sql.SQL(", ").join(asignaciones),
        _snapshot("p", TIPOS_SQL_PREVISION),
    )
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (prevision_id, *cambios.values(), prevision_id))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


# ==================================================================
# Realidad vinculada
# ==================================================================

def resumen_realidad(
    sesion: SesionMotor, prevision_id: uuid.UUID
) -> dict[str, Any]:
    """Realidad ACTIVA vinculada: recuento, suma asignada y fecha real maxima.

    Solo hechos ACTIVOS. Los ANULADO se excluyen en el WHERE, que es de lo que
    depende AMB-009: si se filtrasen despues, una rama podria olvidarlo y una
    REALIZADA sin realidad activa pasaria por realizada de verdad.
    """
    fila = sesion.uno(
        """
        SELECT count(*),
               COALESCE(sum(pv.importe_asignado), 0),
               max(h.fecha_hecho)
          FROM gapto.prevision_hechos pv
          JOIN gapto.hechos_financieros h ON h.id = pv.hecho_id
         WHERE pv.prevision_id = %s::uuid
           AND h.estado = 'ACTIVO'
        """,
        (prevision_id,),
    )
    if fila is None:  # pragma: no cover - count(*) siempre devuelve fila
        return {"hechos_activos": 0, "suma_asignada": decimal.Decimal(0), "fecha_real_maxima": None}
    return {
        "hechos_activos": fila[0],
        "suma_asignada": fila[1],
        "fecha_real_maxima": fila[2],
    }


def historicos_de_regla(
    sesion: SesionMotor, regla_id: uuid.UUID, objetivo: dt.date
) -> list[dict[str, Any]]:
    """Ocurrencias anteriores REALIZADAS con realidad ACTIVA.

    La fuente NO son todos los hechos de la categoria: son las ocurrencias
    anteriores de LA MISMA regla. El importe real es la suma de
    `importe_asignado` sobre hechos ACTIVOS, y las ocurrencias sin realidad
    activa —AMB-009— quedan excluidas por el HAVING.
    """
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.fecha_objetivo_regla,
                   sum(pv.importe_asignado) AS importe_real,
                   p.moneda
              FROM gapto.previsiones p
              JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
              JOIN gapto.prevision_hechos pv ON pv.prevision_id = p.id
              JOIN gapto.hechos_financieros h ON h.id = pv.hecho_id
             WHERE v.regla_id = %s::uuid
               AND p.estado = 'REALIZADA'
               AND p.fecha_objetivo_regla IS NOT NULL
               AND p.fecha_objetivo_regla < %s::date
               AND h.estado = 'ACTIVO'
             GROUP BY p.id, p.fecha_objetivo_regla, p.moneda
            HAVING count(*) > 0
             ORDER BY p.fecha_objetivo_regla
            """,
            (regla_id, objetivo),
        )
        return [
            {"fecha_objetivo": f[0], "importe_real": f[1], "moneda": f[2]}
            for f in cursor.fetchall()
        ]


# ==================================================================
# Vinculos previsión <-> hecho
# ==================================================================

def insertar_vinculo(sesion: SesionMotor, valores: dict[str, Any]) -> str | None:
    """Alta de vinculo. `uq_prevision_hechos__prevision_hecho` es la autoridad
    de que la pareja sea unica."""
    consulta = sql.SQL(
        """
        INSERT INTO gapto.prevision_hechos (
            id, prevision_id, hecho_id, importe_asignado)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::numeric)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot("prevision_hechos", TIPOS_SQL_VINCULO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                valores["id"],
                valores["prevision_id"],
                valores["hecho_id"],
                valores["importe_asignado"],
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def leer_vinculo(sesion: SesionMotor, vinculo_id: uuid.UUID) -> dict[str, Any] | None:
    consulta = sql.SQL(
        """
        SELECT pv.prevision_id, pv.hecho_id, pv.importe_asignado, pv.created_at,
               ({})::text
          FROM gapto.prevision_hechos pv
         WHERE pv.id = %s::uuid
        """
    ).format(_snapshot("pv", TIPOS_SQL_VINCULO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (vinculo_id,))
        fila = cursor.fetchone()
    if fila is None:
        return None
    return {
        "prevision_id": fila[0],
        "hecho_id": fila[1],
        "importe_asignado": fila[2],
        "created_at": fila[3],
        "snapshot": fila[4],
    }


def vinculo_de_pareja(
    sesion: SesionMotor, prevision_id: uuid.UUID, hecho_id: uuid.UUID
) -> dict[str, Any] | None:
    """Vinculo ya existente para esa pareja, si lo hay."""
    fila = sesion.uno(
        "SELECT id, importe_asignado FROM gapto.prevision_hechos "
        "WHERE prevision_id = %s::uuid AND hecho_id = %s::uuid",
        (prevision_id, hecho_id),
    )
    return None if fila is None else {"id": fila[0], "importe_asignado": fila[1]}


def actualizar_vinculo(
    sesion: SesionMotor, vinculo_id: uuid.UUID, cambios: dict[str, Any]
) -> tuple[str, str] | None:
    """Correccion auditada CONSERVANDO el id y el created_at (F04-D021).

    Admite corregir `importe_asignado`, `hecho_id` y `prevision_id`. NO se usa
    DELETE + INSERT para reasignar: la fila es la misma realidad corregida y su
    identidad debe sobrevivir a la correccion.
    """
    if not cambios:
        return None
    asignaciones = [
        sql.SQL("{} = %s::{}").format(
            sql.Identifier(columna), sql.SQL(TIPOS_SQL_VINCULO[columna])
        )
        for columna in cambios
    ]
    consulta = sql.SQL(
        """
        WITH previo AS (
            SELECT ({})::text AS snap FROM gapto.prevision_hechos pv
             WHERE pv.id = %s::uuid
        )
        UPDATE gapto.prevision_hechos AS pv
           SET {}
         WHERE pv.id = %s::uuid
        RETURNING (SELECT snap FROM previo), ({})::text
        """
    ).format(
        _snapshot("pv", TIPOS_SQL_VINCULO),
        sql.SQL(", ").join(asignaciones),
        _snapshot("pv", TIPOS_SQL_VINCULO),
    )
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (vinculo_id, *cambios.values(), vinculo_id))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1])


def borrar_vinculo(sesion: SesionMotor, vinculo_id: uuid.UUID) -> str | None:
    """Retirada de un vinculo que NUNCA debio existir y no tiene sustituto.

    Devuelve el snapshot completo eliminado para que la auditoria lo conserve.
    No es la via ordinaria de correccion: reasignar usa `actualizar_vinculo` y
    conserva el id.
    """
    consulta = sql.SQL(
        """
        DELETE FROM gapto.prevision_hechos AS pv
         WHERE pv.id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot("pv", TIPOS_SQL_VINCULO))
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (vinculo_id,))
        fila = cursor.fetchone()
    return None if fila is None else fila[0]


def creacion_previa_coincide(
    sesion: SesionMotor,
    tabla: str,
    registro_id: uuid.UUID,
    valores: dict[str, Any],
    columnas: dict[str, str],
) -> bool:
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


def saldo_real_de_cuenta(
    sesion: SesionMotor, cuenta_id: uuid.UUID | None
) -> decimal.Decimal | None:
    """Saldo REAL de una cuenta, o None si es INDETERMINADO.

    Mismo patron que una posicion financiera: `cuentas.saldo_apertura` es
    nullable, y cuando es NULL el saldo sigue siendo indeterminado aunque haya
    movimientos. Devolver 0 en ese caso convertiria un desconocido en un
    numero y SALDO_OBJETIVO calcularia una necesidad inventada.

    Solo participan movimientos ACTIVOS: un apunte anulado no es dinero movido.
    Esta lectura vive aqui, y no en el repositorio de tesoreria, porque es
    especifica del algoritmo SALDO_OBJETIVO de F04-05 y no cambia ningun
    contrato cerrado de F04-03.
    """
    if cuenta_id is None:
        return None
    fila = sesion.uno(
        """
        SELECT c.saldo_apertura,
               COALESCE((SELECT sum(m.importe)
                           FROM gapto.movimientos_tesoreria m
                          WHERE m.cuenta_id = c.id
                            AND m.estado = 'ACTIVO'), 0)
          FROM gapto.cuentas c
         WHERE c.id = %s::uuid
        """,
        (cuenta_id,),
    )
    if fila is None or fila[0] is None:
        return None
    return decimal.Decimal(fila[0]) + decimal.Decimal(fila[1])


def ultima_terminal_de_versiones(
    sesion: SesionMotor, version_ids: Sequence[uuid.UUID]
) -> dict[str, Any] | None:
    """Ultima ocurrencia terminal entre un conjunto de versiones (F04-D023).

    Sirve para anclar la transicion CALENDARIO -> RODANTE en la ultima
    terminal del SEGMENTO ANTERIOR, no de la regla entera. `previsiones` no
    guarda a que segmento pertenece una ocurrencia —solo `regla_version_id`—,
    de modo que el segmento se reconstruye por contiguidad de cadencia y aqui
    se recibe ya resuelto como lista de versiones.

    Se ordena por `fecha_objetivo_regla`, no por `created_at`: lo que ordena
    la serie es la identidad de la ocurrencia.
    """
    if not version_ids:
        return None
    fila = sesion.uno(
        """
        SELECT p.id, p.fecha_objetivo_regla, p.estado
          FROM gapto.previsiones p
         WHERE p.regla_version_id = ANY(%s::uuid[])
           AND p.estado <> 'ABIERTA'
           AND p.fecha_objetivo_regla IS NOT NULL
         ORDER BY p.fecha_objetivo_regla DESC, p.id DESC
         LIMIT 1
        """,
        (list(version_ids),),
    )
    if fila is None:
        return None
    return {"id": fila[0], "fecha_objetivo": fila[1], "estado": fila[2]}


def terminal_posterior(
    sesion: SesionMotor, regla_id: uuid.UUID, fecha_objetivo: dt.date
) -> dict[str, Any] | None:
    """Primera ocurrencia TERMINAL de la regla posterior a una identidad.

    Sirve para rechazar la correccion de un estado terminal cuando la cadena
    ya avanzo mas alla: F04-D024 exige revision explicita en ese caso.
    """
    fila = sesion.uno(
        """
        SELECT p.id, p.fecha_objetivo_regla, p.estado
          FROM gapto.previsiones p
          JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
         WHERE v.regla_id = %s::uuid
           AND p.estado <> 'ABIERTA'
           AND p.fecha_objetivo_regla > %s::date
         ORDER BY p.fecha_objetivo_regla, p.id
         LIMIT 1
        """,
        (regla_id, fecha_objetivo),
    )
    if fila is None:
        return None
    return {"id": fila[0], "fecha_objetivo": fila[1], "estado": fila[2]}


def futuras_de_regla(
    sesion: SesionMotor, regla_id: uuid.UUID, desde_fecha: dt.date
) -> list[dict[str, Any]]:
    """Ocurrencias de la regla con identidad en o posterior a `desde_fecha`.

    Devuelve tambien el estado y `recalculo_automatico`, porque el recalculo
    trata distinto a una ABIERTA recalculable, a una ABIERTA congelada y a una
    terminal: nunca se reescribe el pasado ni una expectativa ya congelada.
    """
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, p.fecha_objetivo_regla, p.estado,
                   p.recalculo_automatico, p.regla_version_id
              FROM gapto.previsiones p
              JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
             WHERE v.regla_id = %s::uuid
               AND p.fecha_objetivo_regla IS NOT NULL
               AND p.fecha_objetivo_regla >= %s::date
             ORDER BY p.fecha_objetivo_regla, p.id
            """,
            (regla_id, desde_fecha),
        )
        return [
            {
                "id": f[0],
                "fecha_objetivo": f[1],
                "estado": f[2],
                "recalculo_automatico": f[3],
                "regla_version_id": f[4],
            }
            for f in cursor.fetchall()
        ]


def rodantes_realizadas_de_hecho(
    sesion: SesionMotor, hecho_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Ocurrencias RODANTE REALIZADAS que ese hecho ayuda a anclar.

    Devuelve tambien la cadencia de la version que las gobierna, para poder
    recalcular la ventana del sucesor sin volver a consultar.
    """
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id, v.regla_id, p.fecha_objetivo_regla,
                   v.periodicidad, v.intervalo, v.anclaje_recurrencia
              FROM gapto.prevision_hechos pv
              JOIN gapto.previsiones p ON p.id = pv.prevision_id
              JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
             WHERE pv.hecho_id = %s::uuid
               AND p.estado = 'REALIZADA'
               AND v.anclaje_recurrencia = 'RODANTE'
             ORDER BY p.fecha_objetivo_regla, p.id
            """,
            (hecho_id,),
        )
        return [
            {
                "prevision_id": f[0],
                "regla_id": f[1],
                "fecha_objetivo": f[2],
                "periodicidad": f[3],
                "intervalo": f[4],
                "anclaje_recurrencia": f[5],
            }
            for f in cursor.fetchall()
        ]


def realizada_sin_realidad_activa(
    sesion: SesionMotor, regla_id: uuid.UUID
) -> dict[str, Any] | None:
    """Primera ocurrencia RODANTE REALIZADA que perdio su realidad ACTIVA.

    F04-D018: mientras exista, la cadena entera queda bloqueada para generacion
    automatica. Se comprueba sobre la REGLA y no sobre la cabeza, porque una
    ocurrencia rota anterior invalida el ancla aunque su sucesor ya exista.
    """
    fila = sesion.uno(
        """
        SELECT p.id, p.fecha_objetivo_regla
          FROM gapto.previsiones p
          JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
         WHERE v.regla_id = %s::uuid
           AND p.estado = 'REALIZADA'
           AND v.anclaje_recurrencia = 'RODANTE'
           AND NOT EXISTS (
               SELECT 1
                 FROM gapto.prevision_hechos pv
                 JOIN gapto.hechos_financieros h ON h.id = pv.hecho_id
                WHERE pv.prevision_id = p.id
                  AND h.estado = 'ACTIVO')
         ORDER BY p.fecha_objetivo_regla, p.id
         LIMIT 1
        """,
        (regla_id,),
    )
    if fila is None:
        return None
    return {"id": fila[0], "fecha_objetivo": fila[1]}


def sucesor_inmediato(
    sesion: SesionMotor, regla_id: uuid.UUID, fecha_objetivo: dt.date
) -> dict[str, Any] | None:
    """Siguiente ocurrencia de la regla por identidad canonica."""
    fila = sesion.uno(
        """
        SELECT p.id, p.fecha_objetivo_regla, p.estado, p.recalculo_automatico
          FROM gapto.previsiones p
          JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
         WHERE v.regla_id = %s::uuid
           AND p.fecha_objetivo_regla > %s::date
         ORDER BY p.fecha_objetivo_regla, p.id
         LIMIT 1
        """,
        (regla_id, fecha_objetivo),
    )
    if fila is None:
        return None
    return {
        "id": fila[0],
        "fecha_objetivo": fila[1],
        "estado": fila[2],
        "recalculo_automatico": fila[3],
    }


def es_ancla_de_cadena_con_sucesor(
    sesion: SesionMotor, hecho_id: uuid.UUID
) -> bool:
    """True si el hecho ancla una ocurrencia RODANTE que ya tiene sucesor.

    Corregir la `fecha_hecho` de ese hecho moveria el ancla de una cadena que
    ya avanzo, y el sucesor quedaria calculado desde una fecha que dejo de ser
    cierta. Como no se puede propagar sin reescribir identidades ya
    materializadas, el write-path falla cerrado (F04-D022).
    """
    fila = sesion.uno(
        """
        SELECT EXISTS (
            SELECT 1
              FROM gapto.prevision_hechos pv
              JOIN gapto.previsiones p ON p.id = pv.prevision_id
              JOIN gapto.regla_versiones v ON v.id = p.regla_version_id
             WHERE pv.hecho_id = %s::uuid
               AND p.estado = 'REALIZADA'
               AND v.anclaje_recurrencia = 'RODANTE'
               AND EXISTS (
                   SELECT 1
                     FROM gapto.previsiones s
                     JOIN gapto.regla_versiones sv ON sv.id = s.regla_version_id
                    WHERE sv.regla_id = v.regla_id
                      AND s.fecha_objetivo_regla > p.fecha_objetivo_regla))
        """,
        (hecho_id,),
    )
    return bool(fila and fila[0])
