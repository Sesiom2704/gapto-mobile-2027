# ============================================================
# GAPTO MOBILE 2027
# Fichero: contexto_repository.py
# Ruta: backend/app/repositories/contexto_repository.py
# Descripcion: F04-D048 R3 (A18). SQL de las cuatro dimensiones contextuales
#   del hecho: `hecho_terceros`, `hecho_entidades`, `hecho_magnitudes` y
#   `hecho_etiquetas`.
#
#   NO ES UN WRITER GENERICO. Cada superficie tiene sus propias funciones con
#   sus columnas fijas; no existe ninguna funcion que acepte un nombre de tabla
#   arbitrario para escribir. La unica lectura parametrizada por tabla
#   (`leer_registro`) valida el nombre contra un conjunto CERRADO y solo lee.
#
#   Same-owner y tenant los garantiza 0330: RLS `tenant_isolation` con
#   WITH CHECK sobre el hecho Y sobre el objeto referenciado (tercero,
#   entidad, magnitud, etiqueta), mas FK compuestas en `hecho_entidades`. El
#   repositorio no lo reimplementa: lee y escribe siempre bajo el rol runtime
#   con la GUC de tenant ya fijada por la unidad de trabajo.
#
#   Los INSERT usan ON CONFLICT (id) DO NOTHING: si el UUID reservado ya
#   existe, devuelven None y es el servicio quien decide si es replay o reuso
#   de identidad. Una colision de la UNIQUE semantica (p. ej. mismo tercero y
#   rol en el mismo hecho con OTRO uuid) NO se silencia: aflora como violacion
#   fisica.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import json
import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor

TABLA_TERCEROS = "hecho_terceros"
TABLA_ENTIDADES = "hecho_entidades"
TABLA_MAGNITUDES = "hecho_magnitudes"
TABLA_ETIQUETAS = "hecho_etiquetas"
TABLAS_CONTEXTO = frozenset(
    {TABLA_TERCEROS, TABLA_ENTIDADES, TABLA_MAGNITUDES, TABLA_ETIQUETAS}
)


def _json(texto: str | None) -> dict[str, Any] | None:
    if texto is None:
        return None
    return json.loads(texto, parse_float=decimal.Decimal)


# ----------------------------------------------------------------------
# Lectura
# ----------------------------------------------------------------------
def leer_registro(
    sesion: SesionMotor, tabla: str, registro_id: uuid.UUID
) -> tuple[dict[str, Any], str] | None:
    """Fila contextual por id (dict, snapshot texto). Conjunto cerrado."""
    if tabla not in TABLAS_CONTEXTO:
        raise ValueError(f"tabla contextual no soportada: {tabla}")
    fila = sesion.uno(
        f"SELECT row_to_json(t)::text FROM gapto.{tabla} t WHERE t.id = %s::uuid",
        (registro_id,),
    )
    if fila is None:
        return None
    return _json(fila[0]), fila[0]


def leer_tercero(sesion: SesionMotor, tercero_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT enabled FROM gapto.terceros WHERE id = %s::uuid", (tercero_id,)
    )
    return None if fila is None else {"enabled": fila[0]}


def leer_entidad(sesion: SesionMotor, entidad_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT tipo_entidad, enabled FROM gapto.entidades WHERE id = %s::uuid",
        (entidad_id,),
    )
    return None if fila is None else {"tipo_entidad": fila[0], "enabled": fila[1]}


def leer_magnitud(sesion: SesionMotor, magnitud_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT unidad_default, enabled FROM gapto.magnitudes WHERE id = %s::uuid",
        (magnitud_id,),
    )
    return None if fila is None else {"unidad_default": fila[0], "enabled": fila[1]}


def leer_etiqueta(sesion: SesionMotor, etiqueta_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        "SELECT enabled FROM gapto.etiquetas WHERE id = %s::uuid", (etiqueta_id,)
    )
    return None if fila is None else {"enabled": fila[0]}


def efecto_del_hecho(
    sesion: SesionMotor, hecho_id: uuid.UUID, efecto_id: uuid.UUID
) -> bool:
    fila = sesion.uno(
        "SELECT 1 FROM gapto.hecho_efectos WHERE id = %s::uuid AND hecho_id = %s::uuid",
        (efecto_id, hecho_id),
    )
    return fila is not None


# ----------------------------------------------------------------------
# Alta (una funcion por superficie)
# ----------------------------------------------------------------------
def insertar_tercero(
    sesion: SesionMotor,
    *,
    registro_id: uuid.UUID,
    hecho_id: uuid.UUID,
    tercero_id: uuid.UUID,
    rol_en_hecho: str,
    principal: bool,
) -> str | None:
    fila = sesion.uno(
        """
        INSERT INTO gapto.hecho_terceros (id, hecho_id, tercero_id, rol_en_hecho, principal)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::varchar, %s::boolean)
        ON CONFLICT (id) DO NOTHING
        RETURNING row_to_json(hecho_terceros)::text
        """,
        (registro_id, hecho_id, tercero_id, rol_en_hecho, principal),
    )
    return None if fila is None else fila[0]


def insertar_entidad(
    sesion: SesionMotor,
    *,
    registro_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    hecho_id: uuid.UUID,
    efecto_id: uuid.UUID | None,
    entidad_id: uuid.UUID,
    tipo_relacion: str,
    principal: bool,
) -> str | None:
    fila = sesion.uno(
        """
        INSERT INTO gapto.hecho_entidades
            (id, owner_user_id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::varchar, %s::boolean)
        ON CONFLICT (id) DO NOTHING
        RETURNING row_to_json(hecho_entidades)::text
        """,
        (registro_id, owner_user_id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal),
    )
    return None if fila is None else fila[0]


def insertar_magnitud(
    sesion: SesionMotor,
    *,
    registro_id: uuid.UUID,
    hecho_id: uuid.UUID,
    magnitud_id: uuid.UUID,
    valor: decimal.Decimal,
    unidad: str,
) -> str | None:
    fila = sesion.uno(
        """
        INSERT INTO gapto.hecho_magnitudes (id, hecho_id, magnitud_id, valor, unidad)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::numeric, %s::varchar)
        ON CONFLICT (id) DO NOTHING
        RETURNING row_to_json(hecho_magnitudes)::text
        """,
        (registro_id, hecho_id, magnitud_id, valor, unidad),
    )
    return None if fila is None else fila[0]


def insertar_etiqueta(
    sesion: SesionMotor,
    *,
    registro_id: uuid.UUID,
    hecho_id: uuid.UUID,
    etiqueta_id: uuid.UUID,
) -> str | None:
    fila = sesion.uno(
        """
        INSERT INTO gapto.hecho_etiquetas (id, hecho_id, etiqueta_id)
        VALUES (%s::uuid, %s::uuid, %s::uuid)
        ON CONFLICT (id) DO NOTHING
        RETURNING row_to_json(hecho_etiquetas)::text
        """,
        (registro_id, hecho_id, etiqueta_id),
    )
    return None if fila is None else fila[0]


# ----------------------------------------------------------------------
# Correccion (OP-21): baja por superficie y actualizacion de magnitud
# ----------------------------------------------------------------------
def eliminar_tercero(sesion: SesionMotor, registro_id: uuid.UUID) -> str | None:
    fila = sesion.uno(
        "DELETE FROM gapto.hecho_terceros t WHERE t.id = %s::uuid RETURNING row_to_json(t)::text",
        (registro_id,),
    )
    return None if fila is None else fila[0]


def eliminar_entidad(sesion: SesionMotor, registro_id: uuid.UUID) -> str | None:
    fila = sesion.uno(
        "DELETE FROM gapto.hecho_entidades t WHERE t.id = %s::uuid RETURNING row_to_json(t)::text",
        (registro_id,),
    )
    return None if fila is None else fila[0]


def eliminar_magnitud(sesion: SesionMotor, registro_id: uuid.UUID) -> str | None:
    fila = sesion.uno(
        "DELETE FROM gapto.hecho_magnitudes t WHERE t.id = %s::uuid RETURNING row_to_json(t)::text",
        (registro_id,),
    )
    return None if fila is None else fila[0]


def eliminar_etiqueta(sesion: SesionMotor, registro_id: uuid.UUID) -> str | None:
    fila = sesion.uno(
        "DELETE FROM gapto.hecho_etiquetas t WHERE t.id = %s::uuid RETURNING row_to_json(t)::text",
        (registro_id,),
    )
    return None if fila is None else fila[0]


def actualizar_magnitud(
    sesion: SesionMotor,
    registro_id: uuid.UUID,
    valor: decimal.Decimal,
    unidad: str,
) -> tuple[str, str] | None:
    """UPDATE de valor/unidad. Devuelve (snapshot_antes, snapshot_despues)."""
    antes = sesion.uno(
        "SELECT row_to_json(t)::text FROM gapto.hecho_magnitudes t WHERE t.id = %s::uuid",
        (registro_id,),
    )
    if antes is None:
        return None
    despues = sesion.uno(
        """
        UPDATE gapto.hecho_magnitudes t
           SET valor = %s::numeric, unidad = %s::varchar
         WHERE t.id = %s::uuid
        RETURNING row_to_json(t)::text
        """,
        (valor, unidad, registro_id),
    )
    if despues is None:
        return None
    return antes[0], despues[0]
