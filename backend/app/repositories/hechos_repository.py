# ============================================================
# GAPTO MOBILE 2027
# Fichero: hechos_repository.py
# Ruta: backend/app/repositories/hechos_repository.py
# Descripcion: Acceso SQL a gapto.hechos_financieros para OP-01, OP-02 y OP-03.
#
#   Decisiones estructurales:
#
#   1) El owner NUNCA se pasa como parametro: se toma de
#      `current_setting('gapto.owner_user_id')` dentro de la misma transaccion.
#      Asi la fila insertada y la policy WITH CHECK leen exactamente el mismo
#      valor y no existe ventana para falsificarlo.
#
#   2) Los snapshots funcionales viajan como TEXTO JSON, no como dict de
#      Python. Se generan en PostgreSQL y se devuelven a PostgreSQL sin pasar
#      por float ni por `json.dumps`: cualquier round-trip por Python
#      arriesgaria la exactitud de numeric(18,4) y la normalizacion de fechas,
#      y la comparacion de idempotencia dejaria de ser fiable.
#
#   3) La comparacion de idempotencia se hace CON jsonb EN SQL. `jsonb` compara
#      numeros por valor numerico (12.5000 = 12.50) y admite contencion con
#      valores NULL, cosa que una comparacion en Python no daria gratis.
#
#   4) El snapshot EXCLUYE created_at, updated_at y row_version: son volatiles
#      y romperian la comparabilidad entre el snapshot solicitado y el
#      auditado. Exclusion deliberada.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.unidad_trabajo import SesionMotor

TABLA = "hechos_financieros"

# Tipo SQL de cada columna funcional. Se usa para castear explicitamente los
# parametros y garantizar que el jsonb construido desde parametros es
# identico, tipo a tipo, al construido desde la fila.
TIPOS_SQL: dict[str, str] = {
    "id": "uuid",
    "owner_user_id": "uuid",
    "tipo_hecho_id": "uuid",
    "fecha_hecho": "date",
    "concepto": "varchar",
    "importe_total": "numeric",
    "numero_participantes_total": "smallint",
    "moneda": "varchar",
    "localidad_id": "uuid",
    "estado_localizacion": "varchar",
    "estado": "varchar",
    "presupuestable": "boolean",
    "notas": "text",
    "anulado_at": "timestamptz",
    "motivo_anulacion": "text",
}

COLUMNAS_SNAPSHOT: tuple[str, ...] = (
    "id",
    "owner_user_id",
    "tipo_hecho_id",
    "fecha_hecho",
    "concepto",
    "importe_total",
    "numero_participantes_total",
    "moneda",
    "localidad_id",
    "estado_localizacion",
    "estado",
    "presupuestable",
    "notas",
    "anulado_at",
    "motivo_anulacion",
)


def _snapshot_desde_fila(alias: str) -> sql.Composed:
    partes = [
        sql.SQL("{}, {}.{}").format(
            sql.Literal(columna), sql.Identifier(alias), sql.Identifier(columna)
        )
        for columna in COLUMNAS_SNAPSHOT
    ]
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes))


def _jsonb_desde_valores(valores: dict[str, Any]) -> tuple[sql.Composed, list[Any]]:
    """Construye un jsonb en SQL desde valores Python, casteando cada columna."""
    partes: list[sql.Composed] = []
    params: list[Any] = []
    for columna, valor in valores.items():
        partes.append(
            sql.SQL("{}, %s::{}").format(
                sql.Literal(columna), sql.SQL(TIPOS_SQL[columna])
            )
        )
        params.append(valor)
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes)), params


def exigir_contexto(sesion: SesionMotor) -> uuid.UUID:
    """Falla cerrado si la transaccion no tiene contexto de tenant.

    Se comprueba explicitamente en vez de dejar que PostgreSQL lance un error
    de GUC inexistente: asi el error funcional es TENANT_AUSENTE y no un
    generico que habria que adivinar por SQLSTATE.
    """
    fila = sesion.uno(
        "SELECT NULLIF(current_setting('gapto.owner_user_id', true), '')::uuid"
    )
    if fila is None or fila[0] is None:
        raise ErrorMotor(
            CodigoError.TENANT_AUSENTE,
            "La transaccion no tiene contexto de tenant establecido.",
        )
    return fila[0]


def resolver_tipo_hecho(
    sesion: SesionMotor,
    *,
    codigo: str | None,
    tipo_hecho_id: uuid.UUID | None,
) -> uuid.UUID:
    """Resuelve el tipo de hecho por codigo o por id.

    No se filtra por `enabled`: que un tipo deshabilitado pueda o no usarse en
    un alta nueva es una regla de ciclo de vida que no esta fijada en ningun
    contrato aprobado, y F04-01 no la inventa.
    """
    if tipo_hecho_id is not None:
        fila = sesion.uno(
            "SELECT id FROM gapto.tipos_hecho WHERE id = %s::uuid", (tipo_hecho_id,)
        )
    elif codigo is not None:
        fila = sesion.uno(
            "SELECT id FROM gapto.tipos_hecho WHERE codigo = %s", (codigo,)
        )
    else:
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            "Debe indicarse tipo_hecho_codigo o tipo_hecho_id.",
        )

    if fila is None:
        raise ErrorMotor(
            CodigoError.TIPO_HECHO_DESCONOCIDO,
            "El tipo de hecho indicado no existe en el catalogo.",
        )
    return fila[0]


def insertar_si_no_existe(
    sesion: SesionMotor,
    datos: DatosCreacionHecho,
    tipo_hecho_id: uuid.UUID,
) -> tuple[int, str, str] | None:
    """INSERT idempotente por identidad reservada.

    Devuelve (row_version, estado, snapshot_json) si la fila se creo en esta
    llamada; None si el UUID ya estaba ocupado.

    `ON CONFLICT DO NOTHING` no necesita leer la fila en conflicto, de modo que
    funciona incluso cuando esa fila pertenece a otro tenant y RLS la oculta.
    Esa es justamente la propiedad que impide distinguir "no existe" de "es de
    otro" mediante una lectura cross-tenant.
    """
    consulta = sql.SQL(
        """
        INSERT INTO gapto.hechos_financieros (
            id, owner_user_id, tipo_hecho_id, fecha_hecho, concepto,
            importe_total, numero_participantes_total, moneda, localidad_id,
            estado_localizacion, presupuestable, notas)
        VALUES (
            %s::uuid,
            current_setting('gapto.owner_user_id')::uuid,
            %s::uuid, %s::date, %s::varchar, %s::numeric, %s::smallint,
            %s::varchar, %s::uuid, %s::varchar, %s::boolean, %s::text)
        ON CONFLICT (id) DO NOTHING
        RETURNING row_version, estado, ({})::text
        """
    ).format(_snapshot_desde_fila("hechos_financieros"))

    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (
                datos.hecho_id,
                tipo_hecho_id,
                datos.fecha_hecho,
                datos.concepto,
                datos.importe_total,
                datos.numero_participantes_total,
                datos.moneda,
                datos.localidad_id,
                datos.estado_localizacion,
                datos.presupuestable,
                datos.notas,
            ),
        )
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1], fila[2])


def creacion_previa_coincide(
    sesion: SesionMotor,
    datos: DatosCreacionHecho,
    tipo_hecho_id: uuid.UUID,
) -> bool:
    """True si la auditoria CREAR de ese UUID corresponde a la misma intencion.

    Se compara contra el snapshot DE CREACION auditado, no contra el estado
    actual de la fila. Si se comparase contra el estado actual, un reintento
    tardio de un alta que entretanto fue corregida por OP-02 daria un conflicto
    falso, y el llamante duplicaria el hecho con otro UUID.
    """
    valores: dict[str, Any] = {
        "id": datos.hecho_id,
        "tipo_hecho_id": tipo_hecho_id,
        "fecha_hecho": datos.fecha_hecho,
        "concepto": datos.concepto,
        "importe_total": datos.importe_total,
        "numero_participantes_total": datos.numero_participantes_total,
        "moneda": datos.moneda,
        "localidad_id": datos.localidad_id,
        "estado_localizacion": datos.estado_localizacion,
        "estado": "ACTIVO",
        "presupuestable": datos.presupuestable,
        "notas": datos.notas,
        "anulado_at": None,
        "motivo_anulacion": None,
    }
    snapshot_sql, params = _jsonb_desde_valores(valores)

    consulta = sql.SQL(
        """
        SELECT a.datos_despues
               = ({} || jsonb_build_object(
                     'owner_user_id',
                     current_setting('gapto.owner_user_id')::uuid))
          FROM gapto.auditoria a
         WHERE a.tabla = 'hechos_financieros'
           AND a.registro_id = %s::uuid
           AND a.accion = 'CREAR'
         ORDER BY a.created_at, a.id
         LIMIT 1
        """
    ).format(snapshot_sql)

    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (*params, datos.hecho_id))
        fila = cursor.fetchone()
    return bool(fila is not None and fila[0])


def leer_estado(
    sesion: SesionMotor, hecho_id: uuid.UUID
) -> tuple[int, str, str] | None:
    """Devuelve (row_version, estado, snapshot_json) o None si no es visible.

    "No visible" incluye deliberadamente "de otro tenant": RLS lo oculta y el
    motor no intenta distinguirlo.
    """
    consulta = sql.SQL(
        """
        SELECT h.row_version, h.estado, ({})::text
          FROM gapto.hechos_financieros h
         WHERE h.id = %s::uuid
        """
    ).format(_snapshot_desde_fila("h"))

    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (hecho_id,))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1], fila[2])


def actualizar_campos(
    sesion: SesionMotor,
    hecho_id: uuid.UUID,
    row_version_esperada: int,
    cambios: dict[str, Any],
) -> tuple[int, str, str] | None:
    """UPDATE con guarda de version. None si no caso ninguna fila."""
    if not cambios:
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            "Una correccion debe modificar al menos un campo.",
        )

    asignaciones = [
        sql.SQL("{} = %s::{}").format(
            sql.Identifier(columna), sql.SQL(TIPOS_SQL[columna])
        )
        for columna in cambios
    ]
    consulta = sql.SQL(
        """
        UPDATE gapto.hechos_financieros AS h
           SET {},
               updated_at = CURRENT_TIMESTAMP,
               row_version = h.row_version + 1
         WHERE h.id = %s::uuid
           AND h.row_version = %s
           AND h.estado = 'ACTIVO'
        RETURNING h.row_version, h.estado, ({})::text
        """
    ).format(sql.SQL(", ").join(asignaciones), _snapshot_desde_fila("h"))

    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta, (*cambios.values(), hecho_id, row_version_esperada)
        )
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1], fila[2])


def anular(
    sesion: SesionMotor,
    hecho_id: uuid.UUID,
    row_version_esperada: int,
    motivo_anulacion: str,
) -> tuple[int, str, str] | None:
    """Transicion ACTIVO -> ANULADO. Nunca DELETE.

    gapto_runtime ni siquiera conserva DELETE sobre la tabla (migration 0200),
    de modo que un borrado fisico por error de programacion es imposible.
    """
    consulta = sql.SQL(
        """
        UPDATE gapto.hechos_financieros AS h
           SET estado = 'ANULADO',
               anulado_at = CURRENT_TIMESTAMP,
               motivo_anulacion = %s::text,
               updated_at = CURRENT_TIMESTAMP,
               row_version = h.row_version + 1
         WHERE h.id = %s::uuid
           AND h.row_version = %s
           AND h.estado = 'ACTIVO'
        RETURNING h.row_version, h.estado, ({})::text
        """
    ).format(_snapshot_desde_fila("h"))

    with sesion.conexion.cursor() as cursor:
        cursor.execute(consulta, (motivo_anulacion, hecho_id, row_version_esperada))
        fila = cursor.fetchone()
    return None if fila is None else (fila[0], fila[1], fila[2])


def tiene_efectos(sesion: SesionMotor, hecho_id: uuid.UUID) -> bool:
    fila = sesion.uno(
        "SELECT EXISTS (SELECT 1 FROM gapto.hecho_efectos e WHERE e.hecho_id = %s::uuid)",
        (hecho_id,),
    )
    return bool(fila and fila[0])


def tiene_realidad_asociada(sesion: SesionMotor, hecho_id: uuid.UUID) -> bool:
    """True si el hecho ya tiene tesoreria o financiacion real vinculada.

    Ambas son realidad ocurrida. Si existen, el hecho no es "algo que nunca
    debio existir" y OP-03 no es la operacion adecuada: corresponde devolucion
    o reversion, que pertenecen a F04-06.
    """
    fila = sesion.uno(
        """
        SELECT EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria m
                        WHERE m.hecho_id = %s::uuid)
            OR EXISTS (SELECT 1 FROM gapto.hecho_aportaciones_pago p
                        WHERE p.hecho_id = %s::uuid)
        """,
        (hecho_id, hecho_id),
    )
    return bool(fila and fila[0])


def correccion_ya_aplicada(
    sesion: SesionMotor,
    hecho_id: uuid.UUID,
    request_id: uuid.UUID,
    cambios: dict[str, Any],
    snapshot_actual_json: str,
) -> bool:
    """Demostracion estricta de que ESTA correccion ya quedo aplicada.

    Exige simultaneamente:
      1) existe auditoria ACTUALIZAR de este registro con EL MISMO request_id;
      2) su `datos_despues` contiene exactamente los valores solicitados;
      3) fuera de los campos solicitados, `datos_antes` y `datos_despues` son
         identicos, es decir aquella escritura no cambio nada mas;
      4) el estado actual de la fila sigue siendo ese `datos_despues`.

    La condicion 1 es la que impide que una segunda edicion manual legitima se
    trague en silencio como "ya aplicada": vendria con otro request_id y
    obtendria VERSION_DESFASADA, que es lo correcto. row_version sigue sin ser
    clave de idempotencia.
    """
    cambios_sql, params = _jsonb_desde_valores(cambios)
    claves = list(cambios.keys())

    consulta = sql.SQL(
        """
        SELECT EXISTS (
            SELECT 1
              FROM gapto.auditoria a
             WHERE a.tabla = 'hechos_financieros'
               AND a.registro_id = %s::uuid
               AND a.accion = 'ACTUALIZAR'
               AND a.request_id = %s::uuid
               AND a.datos_despues @> ({})
               AND (a.datos_antes - %s::text[]) = (a.datos_despues - %s::text[])
               AND a.datos_despues = %s::jsonb
        )
        """
    ).format(cambios_sql)

    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            consulta,
            (hecho_id, request_id, *params, claves, claves, snapshot_actual_json),
        )
        fila = cursor.fetchone()
    return bool(fila and fila[0])


def anulacion_ya_registrada(
    sesion: SesionMotor, hecho_id: uuid.UUID, request_id: uuid.UUID
) -> bool:
    """True si ESTA misma peticion ya anulo el hecho.

    Solo el mismo request_id cuenta. Una segunda anulacion con otro request_id
    se rechaza: transporta su propio motivo_anulacion y tratarla como
    idempotente descartaria ese motivo en silencio.
    """
    fila = sesion.uno(
        """
        SELECT EXISTS (
            SELECT 1 FROM gapto.auditoria a
             WHERE a.tabla = 'hechos_financieros'
               AND a.registro_id = %s::uuid
               AND a.accion = 'ANULAR'
               AND a.request_id = %s::uuid)
        """,
        (hecho_id, request_id),
    )
    return bool(fila and fila[0])
