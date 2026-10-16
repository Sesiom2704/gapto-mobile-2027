# ============================================================
# GAPTO MOBILE 2027
# Fichero: correcciones_repository.py
# Ruta: backend/app/repositories/correcciones_repository.py
# Descripcion: F04-06 / B5. Lecturas y borrados legitimos de OP-21.
#
#   0320 CONCEDE DELETE SOBRE DOCE TABLAS HIJAS Y PUENTE, Y SOBRE NINGUNA
#   RAIZ. `hechos_financieros` y `movimientos_tesoreria` quedaron fuera a
#   proposito. Este fichero expone una funcion por tabla, con nombre propio, en
#   vez de un borrador generico parametrizado por tabla: un `eliminar(tabla,
#   id)` aceptaria cualquier cadena y convertiria el GRANT de 0320 en una API
#   de borrado universal, que es justo lo que el mandato prohibe.
#
#   TODO DELETE DEVUELVE EL SNAPSHOT COMPLETO. Una fila borrada no deja rastro
#   en ningun sitio salvo en la auditoria, de modo que el snapshot no es un
#   adorno: es la unica prueba de que existio y de que decia.
#
#   EL ADVISORY DE D-080 VA PRIMERO. Los triggers de 0280 y 0290 toman
#   `pg_advisory_xact_lock('gapto:INVERSIONES', owner)` por su cuenta. Si el
#   servicio tomase antes sus row locks y el trigger pidiese despues el
#   advisory, dos correcciones concurrentes podrian invertir el orden. Por eso
#   se adquiere al principio de la transaccion, antes de cualquier fila.
# Version: 0.3.0
#   0.3.0 (F04-D060 · F04-R2 R2-A; contrato F04-R2 v0.6 §7.1-§7.2.1):
#   PERTENENCIA EN EL PROPIO DELETE/UPDATE. `actualizar_efecto`,
#   `eliminar_efecto`, `eliminar_conciliacion` y `aportaciones_de_conciliacion`
#   reciben el hecho raiz y filtran `AND hecho_id = <raiz>`; la relacion solo la
#   retira su ORIGEN (`AND hecho_origen_id = <raiz>`). Nunca hay una lectura
#   previa separada que autorice: 0 filas = no es del hecho. `leer_relacion`
#   relee SIN lock solo para elegir el codigo del rechazo.
# Version: 0.2.0
#   0.2.0 (F04-D039): superficie de atribuciones. UPDATE, DELETE y lectura
#   del estado final de los efectos tocados, para que OP-21 pueda alcanzar
#   atomicamente un estado valido cuando el reparto registrado era falso.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA_EFECTOS = "hecho_efectos"
TABLA_RELACIONES = "hecho_relaciones"
TABLA_CONCILIACIONES = "hecho_movimientos_tesoreria"

# Superficies gobernadas por D-080. Tocar cualquiera obliga al advisory root.
SUPERFICIES_INVERSION = frozenset(
    {"inversion_asignaciones_efecto", "hecho_entidades", "INVERSION"}
)


def tomar_advisory_inversiones(sesion: SesionMotor, owner_user_id: uuid.UUID) -> None:
    """Advisory root (INVERSIONES, owner) exigido por D-080.

    Es el MISMO que toman `fn_check_inversion_*` en 0280 y 0290. Tomarlo aqui
    no lo duplica: lo adelanta, de modo que la transaccion ya lo posee cuando
    el trigger lo pida al COMMIT. Los row locks genericos no lo sustituyen.
    """
    sesion.uno(
        "SELECT pg_advisory_xact_lock(hashtext('gapto:INVERSIONES'), "
        "hashtext(%s::text))",
        (str(owner_user_id),),
    )


def _snapshot(alias: str, columnas: dict[str, str]) -> sql.Composed:
    partes: list[sql.Composed] = []
    for columna in columnas:
        partes.append(
            sql.SQL("{}, to_jsonb({}.{})").format(
                sql.Literal(columna), sql.Identifier(alias), sql.Identifier(columna)
            )
        )
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes))


COLUMNAS_EFECTO = {
    "id": "uuid",
    "hecho_id": "uuid",
    "tipo_efecto": "varchar",
    "importe_delta": "numeric",
    "categoria_id": "uuid",
    "estado_atribucion": "varchar",
    "descripcion": "varchar",
}

COLUMNAS_RELACION = {
    "id": "uuid",
    "hecho_origen_id": "uuid",
    "hecho_destino_id": "uuid",
    "tipo_relacion": "varchar",
    "importe_relacionado": "numeric",
    "notas": "text",
}

COLUMNAS_CONCILIACION = {
    "id": "uuid",
    "hecho_id": "uuid",
    "movimiento_tesoreria_id": "uuid",
    "importe_asignado": "numeric",
}


def eliminar_efecto(
    sesion: SesionMotor, efecto_id: uuid.UUID, hecho_id: uuid.UUID
) -> str | None:
    """Retira un efecto DEL HECHO RAIZ que nunca debio existir. Devuelve su
    snapshot, o None si no es de ese hecho (o no existe o no es visible)."""
    consulta = sql.SQL(
        """
        DELETE FROM gapto.hecho_efectos e
         WHERE e.id = %s::uuid
           AND e.hecho_id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot("e", COLUMNAS_EFECTO))
    fila = sesion.uno(consulta, (efecto_id, hecho_id))
    return None if fila is None else fila[0]


def eliminar_relacion(
    sesion: SesionMotor, relacion_id: uuid.UUID, hecho_origen_id: uuid.UUID
) -> str | None:
    """F04-R2 §7.2.1: solo el ORIGEN retira su relacion. None si la raiz no
    es el origen (destino, ajena, inexistente o no visible)."""
    consulta = sql.SQL(
        """
        DELETE FROM gapto.hecho_relaciones r
         WHERE r.id = %s::uuid
           AND r.hecho_origen_id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot("r", COLUMNAS_RELACION))
    fila = sesion.uno(consulta, (relacion_id, hecho_origen_id))
    return None if fila is None else fila[0]


def leer_relacion(
    sesion: SesionMotor, relacion_id: uuid.UUID
) -> tuple[Any, ...] | None:
    """(hecho_origen_id, hecho_destino_id, estado del origen), SIN lock.

    F04-R2 §7.2.1: solo sirve para ELEGIR el codigo del rechazo cuando el
    DELETE filtrado por origen no borro nada; nunca autoriza una escritura.
    """
    return sesion.uno(
        """
        SELECT r.hecho_origen_id, r.hecho_destino_id, o.estado
          FROM gapto.hecho_relaciones r
          JOIN gapto.hechos_financieros o ON o.id = r.hecho_origen_id
         WHERE r.id = %s::uuid
        """,
        (relacion_id,),
    )


def eliminar_conciliacion(
    sesion: SesionMotor, conciliacion_id: uuid.UUID, hecho_id: uuid.UUID
) -> str | None:
    """Retira una conciliacion DEL HECHO RAIZ. None si no es de ese hecho."""
    consulta = sql.SQL(
        """
        DELETE FROM gapto.hecho_movimientos_tesoreria h
         WHERE h.id = %s::uuid
           AND h.hecho_id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot("h", COLUMNAS_CONCILIACION))
    fila = sesion.uno(consulta, (conciliacion_id, hecho_id))
    return None if fila is None else fila[0]


def actualizar_efecto(
    sesion: SesionMotor,
    efecto_id: uuid.UUID,
    hecho_id: uuid.UUID,
    cambios: dict[str, Any],
) -> tuple[str, str] | None:
    """UPDATE de un dato que nunca fue cierto. Devuelve (antes, despues).

    F04-R2 §7.2: solo un efecto DEL HECHO RAIZ; None si es de otro hecho.

    Los campos permitidos se enumeran explicitamente: aceptar cualquier
    columna convertiria la correccion en una via para reescribir la identidad
    del efecto o su pertenencia a otro hecho.
    """
    permitidos = {
        "importe_delta",
        "categoria_id",
        "descripcion",
        "tipo_efecto",
        # F04-D039. Corregible solo por OP-21; OP-05 conserva su progresion.
        "estado_atribucion",
    }
    columnas = [c for c in cambios if c in permitidos]
    if not columnas:
        return None
    asignaciones = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columnas
    )
    consulta = sql.SQL(
        """
        WITH antes AS (
            SELECT ({})::text AS snapshot FROM gapto.hecho_efectos e
             WHERE e.id = %s::uuid
        )
        UPDATE gapto.hecho_efectos e
           SET {}
          FROM antes
         WHERE e.id = %s::uuid
           AND e.hecho_id = %s::uuid
        RETURNING antes.snapshot, ({})::text
        """
    ).format(
        _snapshot("e", COLUMNAS_EFECTO),
        asignaciones,
        _snapshot("e", COLUMNAS_EFECTO),
    )
    parametros = (
        [efecto_id] + [cambios[c] for c in columnas] + [efecto_id, hecho_id]
    )
    fila = sesion.uno(consulta, tuple(parametros))
    return None if fila is None else (fila[0], fila[1])


def efectos_del_hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> int:
    fila = sesion.uno(
        "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s::uuid",
        (hecho_id,),
    )
    return 0 if fila is None else fila[0]


def tipo_de_hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> str | None:
    fila = sesion.uno(
        """
        SELECT t.codigo FROM gapto.hechos_financieros h
          JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id
         WHERE h.id = %s::uuid
        """,
        (hecho_id,),
    )
    return None if fila is None else fila[0]


def aportaciones_de_conciliacion(
    sesion: SesionMotor, conciliacion_id: uuid.UUID, hecho_id: uuid.UUID
) -> int:
    """Aportaciones vinculadas a una conciliacion DEL HECHO RAIZ.

    Retirar la conciliacion antes que sus aportaciones dejaria aportaciones
    apuntando al vacio, de modo que el servicio exige el orden inverso (D-169).
    F04-R2 §7.2: se cuenta solo si la conciliacion es del hecho raiz; la de
    otro hecho da 0 y la rechaza el DELETE filtrado, sin revelar que existe.
    """
    fila = sesion.uno(
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago a "
        "JOIN gapto.hecho_movimientos_tesoreria h "
        "ON h.id = a.hecho_movimiento_tesoreria_id "
        "WHERE a.hecho_movimiento_tesoreria_id = %s::uuid AND h.hecho_id = %s::uuid",
        (conciliacion_id, hecho_id),
    )
    return 0 if fila is None else fila[0]


# ==================================================================
# F04-D039 - superficie de atribuciones
# ==================================================================

COLUMNAS_ATRIBUCION = {
    "id": "uuid",
    "efecto_id": "uuid",
    "actor_id": "uuid",
    "importe_atribuido": "numeric",
    "porcentaje_aplicado": "numeric",
    "criterio_atribucion": "varchar",
}


def leer_atribucion(
    sesion: SesionMotor, atribucion_id: uuid.UUID
) -> tuple[Any, ...] | None:
    """Devuelve (efecto_id, hecho_id) o None si no es visible."""
    return sesion.uno(
        "SELECT a.efecto_id, e.hecho_id FROM gapto.efecto_atribuciones a "
        "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE a.id = %s::uuid",
        (atribucion_id,),
    )


def eliminar_atribucion(
    sesion: SesionMotor, atribucion_id: uuid.UUID
) -> str | None:
    """Retira una atribucion que nunca debio existir. Devuelve su snapshot."""
    consulta = sql.SQL(
        """
        DELETE FROM gapto.efecto_atribuciones a
         WHERE a.id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot("a", COLUMNAS_ATRIBUCION))
    fila = sesion.uno(consulta, (atribucion_id,))
    return None if fila is None else fila[0]


def actualizar_atribucion(
    sesion: SesionMotor, atribucion_id: uuid.UUID, cambios: dict[str, Any]
) -> tuple[str, str] | None:
    """UPDATE de un reparto que nunca fue cierto. Devuelve (antes, despues).

    `actor_id` NO es corregible: cambiar de persona no es corregir un importe.
    Un actor equivocado se expresa como DELETE de la fila falsa mas CREATE de
    la correcta, que deja una auditoria inequivoca de que eran dos realidades
    distintas y no una misma fila que "cambio de dueno".
    """
    permitidos = {"importe_atribuido", "porcentaje_aplicado", "criterio_atribucion"}
    columnas = [c for c in cambios if c in permitidos]
    if not columnas:
        return None
    asignaciones = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columnas
    )
    consulta = sql.SQL(
        """
        WITH antes AS (
            SELECT ({})::text AS snapshot FROM gapto.efecto_atribuciones a
             WHERE a.id = %s::uuid
        )
        UPDATE gapto.efecto_atribuciones a
           SET {}
          FROM antes
         WHERE a.id = %s::uuid
        RETURNING antes.snapshot, ({})::text
        """
    ).format(
        _snapshot("a", COLUMNAS_ATRIBUCION),
        asignaciones,
        _snapshot("a", COLUMNAS_ATRIBUCION),
    )
    parametros = [atribucion_id] + [cambios[c] for c in columnas] + [atribucion_id]
    fila = sesion.uno(consulta, tuple(parametros))
    return None if fila is None else (fila[0], fila[1])


def estado_de_efectos(
    sesion: SesionMotor, hecho_id: uuid.UUID, efecto_ids: list[uuid.UUID]
) -> list[tuple[Any, ...]]:
    """(efecto_id, importe_delta, estado_atribucion, filas, suma) del ESTADO FINAL.

    Se limita a los efectos que la correccion toca. Evaluar todo el hecho haria
    que OP-21 se negase a corregir un efecto por culpa de otro que ya estaba en
    un estado que nadie rechaza hoy: las reglas de residual real y de
    NO_DISPONIBLE sin filas son SRV y el trigger no las cubre.
    """
    consulta = """
        SELECT e.id, e.importe_delta, e.estado_atribucion,
               count(a.id), COALESCE(sum(a.importe_atribuido), 0)
          FROM gapto.hecho_efectos e
          LEFT JOIN gapto.efecto_atribuciones a ON a.efecto_id = e.id
         WHERE e.hecho_id = %s::uuid AND e.id = ANY(%s::uuid[])
         GROUP BY e.id, e.importe_delta, e.estado_atribucion
    """
    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (hecho_id, efecto_ids))
        return list(cursor.fetchall())
