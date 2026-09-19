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


def eliminar_efecto(sesion: SesionMotor, efecto_id: uuid.UUID) -> str | None:
    """Retira un efecto que nunca debio existir. Devuelve su snapshot."""
    consulta = sql.SQL(
        """
        DELETE FROM gapto.hecho_efectos e
         WHERE e.id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot("e", COLUMNAS_EFECTO))
    fila = sesion.uno(consulta, (efecto_id,))
    return None if fila is None else fila[0]


def eliminar_relacion(sesion: SesionMotor, relacion_id: uuid.UUID) -> str | None:
    consulta = sql.SQL(
        """
        DELETE FROM gapto.hecho_relaciones r
         WHERE r.id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot("r", COLUMNAS_RELACION))
    fila = sesion.uno(consulta, (relacion_id,))
    return None if fila is None else fila[0]


def eliminar_conciliacion(
    sesion: SesionMotor, conciliacion_id: uuid.UUID
) -> str | None:
    consulta = sql.SQL(
        """
        DELETE FROM gapto.hecho_movimientos_tesoreria h
         WHERE h.id = %s::uuid
        RETURNING ({})::text
        """
    ).format(_snapshot("h", COLUMNAS_CONCILIACION))
    fila = sesion.uno(consulta, (conciliacion_id,))
    return None if fila is None else fila[0]


def actualizar_efecto(
    sesion: SesionMotor, efecto_id: uuid.UUID, cambios: dict[str, Any]
) -> tuple[str, str] | None:
    """UPDATE de un dato que nunca fue cierto. Devuelve (antes, despues).

    Los campos permitidos se enumeran explicitamente: aceptar cualquier
    columna convertiria la correccion en una via para reescribir la identidad
    del efecto o su pertenencia a otro hecho.
    """
    permitidos = {"importe_delta", "categoria_id", "descripcion", "tipo_efecto"}
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
        RETURNING antes.snapshot, ({})::text
        """
    ).format(
        _snapshot("e", COLUMNAS_EFECTO),
        asignaciones,
        _snapshot("e", COLUMNAS_EFECTO),
    )
    parametros = [efecto_id] + [cambios[c] for c in columnas] + [efecto_id]
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
    sesion: SesionMotor, conciliacion_id: uuid.UUID
) -> int:
    """Aportaciones vinculadas a una conciliacion.

    Retirar la conciliacion antes que sus aportaciones dejaria aportaciones
    apuntando al vacio, de modo que el servicio exige el orden inverso (D-169).
    """
    fila = sesion.uno(
        "SELECT count(*) FROM gapto.hecho_aportaciones_pago "
        "WHERE hecho_movimiento_tesoreria_id = %s::uuid",
        (conciliacion_id,),
    )
    return 0 if fila is None else fila[0]
