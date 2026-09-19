# ============================================================
# GAPTO MOBILE 2027
# Fichero: relaciones_repository.py
# Ruta: backend/app/repositories/relaciones_repository.py
# Descripcion: F04-06 / B3. Acceso a `gapto.hecho_relaciones` y lecturas de
#   capacidad reversible para OP-13.
#
#   LA TABLA NO ES UNA RAIZ DE AGREGADO. No tiene `owner_user_id`, ni
#   `created_at`, ni `updated_at`, ni `row_version`, y su unica unicidad es la
#   clave primaria. Consecuencias que gobiernan todo este fichero:
#
#   - el tenant llega SOLO por la policy RLS, que exige que AMBOS extremos
#     pertenezcan al mismo owner;
#   - la concurrencia no se serializa sobre la relacion sino sobre los dos
#     hechos que une;
#   - no hay UNIQUE sobre (origen, destino, tipo): dos filas identicas son
#     fisicamente posibles y solo el protocolo de F04-D028 lo impide.
#     Ese es el riesgo R-F04-020, aceptado de forma deliberada.
#
#   LA RELACION UNE HECHOS, NO EFECTOS. `hecho_relaciones` no puede apuntar a
#   un `hecho_efectos.id`, de modo que la porcion devuelta NO es trazable a un
#   efecto concreto. F04-D030 lo resuelve agregando por NATURALEZA, y esa es
#   la razon de que aqui se lea la capacidad como suma firmada por
#   `tipo_efecto` y no efecto a efecto. Es el limite R-F04-021.
# Version: 0.3.0
#   0.3.0 (F04-06 B5): `naturalezas_devueltas`, que OP-21 usa para revalidar
#   que una correccion no deja la capacidad por debajo de lo ya devuelto.
# Version: 0.2.0
#   0.2.0 (F04-06 B4): `fecha_de_hecho`, que OP-18 usa para distinguir un
#   ajuste real posterior de un error de captura.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from psycopg import sql

from app.core.unidad_trabajo import SesionMotor

TABLA = "hecho_relaciones"

TIPOS_SQL_RELACION: dict[str, str] = {
    "id": "uuid",
    "hecho_origen_id": "uuid",
    "hecho_destino_id": "uuid",
    "tipo_relacion": "varchar",
    "importe_relacionado": "numeric",
    "notas": "text",
}


def _snapshot_desde_fila(alias: str) -> sql.Composed:
    partes: list[sql.Composed] = []
    for columna in TIPOS_SQL_RELACION:
        partes.append(
            sql.SQL("{}, to_jsonb({}.{})").format(
                sql.Literal(columna), sql.Identifier(alias), sql.Identifier(columna)
            )
        )
    return sql.SQL("jsonb_build_object({})").format(sql.SQL(", ").join(partes))


def bloquear_hechos(sesion: SesionMotor, ids: list[uuid.UUID]) -> bool:
    """Bloquea los hechos indicados en orden de UUID con FOR NO KEY UPDATE.

    F04-D028 exige este orden: dos operaciones que toquen la misma pareja en
    sentidos opuestos se cruzarian si cada una bloquease en el orden en que le
    resultan comodos. Ordenar por UUID hace la espera determinista.

    Devuelve False si alguno no es visible: para este tenant, un hecho ajeno
    simplemente no existe.
    """
    visibles = 0
    for hecho_id in sorted(set(ids), key=str):
        fila = sesion.uno(
            "SELECT 1 FROM gapto.hechos_financieros WHERE id = %s::uuid "
            "FOR NO KEY UPDATE",
            (hecho_id,),
        )
        if fila is not None:
            visibles += 1
    return visibles == len(set(ids))


def leer_relacion_logica(
    sesion: SesionMotor,
    *,
    hecho_origen_id: uuid.UUID,
    hecho_destino_id: uuid.UUID,
    tipo_relacion: str,
) -> dict[str, Any] | None:
    """Relacion existente para la terna (origen, destino, tipo).

    Se relee SIEMPRE despues de haber bloqueado los dos hechos, nunca antes:
    sin UNIQUE fisica, una lectura previa al lock no prueba nada.
    """
    fila = sesion.uno(
        """
        SELECT r.id, r.importe_relacionado, r.notas
          FROM gapto.hecho_relaciones r
         WHERE r.hecho_origen_id = %s::uuid
           AND r.hecho_destino_id = %s::uuid
           AND r.tipo_relacion = %s
        """,
        (hecho_origen_id, hecho_destino_id, tipo_relacion),
    )
    if fila is None:
        return None
    return {"id": fila[0], "importe_relacionado": fila[1], "notas": fila[2]}


def leer_relacion(sesion: SesionMotor, relacion_id: uuid.UUID) -> dict[str, Any] | None:
    fila = sesion.uno(
        """
        SELECT r.hecho_origen_id, r.hecho_destino_id, r.tipo_relacion,
               r.importe_relacionado
          FROM gapto.hecho_relaciones r
         WHERE r.id = %s::uuid
        """,
        (relacion_id,),
    )
    if fila is None:
        return None
    return {
        "hecho_origen_id": fila[0],
        "hecho_destino_id": fila[1],
        "tipo_relacion": fila[2],
        "importe_relacionado": fila[3],
    }


def insertar_relacion_si_no_existe(
    sesion: SesionMotor,
    *,
    relacion_id: uuid.UUID,
    hecho_origen_id: uuid.UUID,
    hecho_destino_id: uuid.UUID,
    tipo_relacion: str,
    importe_relacionado: Any,
    notas: str | None,
) -> str | None:
    consulta = sql.SQL(
        """
        INSERT INTO gapto.hecho_relaciones (
            id, hecho_origen_id, hecho_destino_id, tipo_relacion,
            importe_relacionado, notas)
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s::varchar, %s::numeric, %s)
        ON CONFLICT (id) DO NOTHING
        RETURNING ({})::text
        """
    ).format(_snapshot_desde_fila(TABLA))
    fila = sesion.uno(
        consulta,
        (
            relacion_id,
            hecho_origen_id,
            hecho_destino_id,
            tipo_relacion,
            importe_relacionado,
            notas,
        ),
    )
    return None if fila is None else fila[0]


def capacidad_por_naturaleza(
    sesion: SesionMotor, hecho_id: uuid.UUID, tipo_efecto: str
) -> dict[str, Any] | None:
    """Capacidad reversible del hecho para una naturaleza (F04-D030).

    Devuelve la suma FIRMADA de los deltas de esa naturaleza, cuantos efectos
    la componen y si todos comparten signo. La suma firmada es la capacidad
    solo cuando los signos son coherentes: con signos mezclados, la base no
    determina univocamente cuanto puede revertirse y el servicio falla cerrado.

    No se devuelve ningun `hecho_efectos.id`: la relacion es fact-level y
    elegir uno seria fabricar una trazabilidad que el modelo no conserva.
    """
    fila = sesion.uno(
        """
        SELECT COALESCE(sum(e.importe_delta), 0) AS neto,
               count(*) AS efectos,
               count(DISTINCT sign(e.importe_delta)) AS signos
          FROM gapto.hecho_efectos e
         WHERE e.hecho_id = %s::uuid
           AND e.tipo_efecto = %s
        """,
        (hecho_id, tipo_efecto),
    )
    if fila is None or fila[1] == 0:
        return None
    return {"neto": fila[0], "efectos": fila[1], "signos_distintos": fila[2]}


def devuelto_acumulado(
    sesion: SesionMotor, hecho_id: uuid.UUID, tipo_efecto: str
) -> Any:
    """Suma en valor absoluto de las devoluciones ACTIVAS de esa naturaleza.

    Solo cuentan los hechos de devolucion ACTIVOS: una devolucion anulada deja
    de consumir capacidad, igual que un hecho anulado deja de ser realidad.

    La direccion es la de F04-D030: la relacion va del hecho NUEVO de
    devolucion (origen) al hecho ORIGINAL reducido (destino). Por eso se busca
    por `hecho_destino_id`.
    """
    fila = sesion.uno(
        """
        SELECT COALESCE(sum(abs(e.importe_delta)), 0)
          FROM gapto.hecho_relaciones r
          JOIN gapto.hechos_financieros d ON d.id = r.hecho_origen_id
          JOIN gapto.hecho_efectos e ON e.hecho_id = d.id
         WHERE r.hecho_destino_id = %s::uuid
           AND r.tipo_relacion = 'DEVOLUCION_DE'
           AND d.estado = 'ACTIVO'
           AND e.tipo_efecto = %s
        """,
        (hecho_id, tipo_efecto),
    )
    return 0 if fila is None else fila[0]


def fecha_de_hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> Any:
    """Fecha economica del hecho, o None si no es visible.

    OP-18 la necesita para sostener la frontera entre un ajuste REAL posterior
    y un error de captura disfrazado: lo posterior ocurre despues.
    """
    fila = sesion.uno(
        "SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s::uuid",
        (hecho_id,),
    )
    return None if fila is None else fila[0]


def naturalezas_devueltas(
    sesion: SesionMotor, hecho_id: uuid.UUID
) -> list[str]:
    """Naturalezas con devoluciones ACTIVAS contra este hecho.

    OP-21 la necesita para revalidar el estado final: retirar o reducir un
    efecto puede dejar la capacidad por debajo de lo ya devuelto, y ninguna
    constraint fisica lo impide.
    """
    with sesion.conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT e.tipo_efecto
              FROM gapto.hecho_relaciones r
              JOIN gapto.hechos_financieros d ON d.id = r.hecho_origen_id
              JOIN gapto.hecho_efectos e ON e.hecho_id = d.id
             WHERE r.hecho_destino_id = %s::uuid
               AND r.tipo_relacion = 'DEVOLUCION_DE'
               AND d.estado = 'ACTIVO'
            """,
            (hecho_id,),
        )
        return [f[0] for f in cursor.fetchall()]


def moneda_de_hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> str | None:
    fila = sesion.uno(
        "SELECT moneda FROM gapto.hechos_financieros WHERE id = %s::uuid",
        (hecho_id,),
    )
    return None if fila is None else fila[0]


def vinculos_de_prevision(sesion: SesionMotor, hecho_id: uuid.UUID) -> int:
    """Cuantas previsiones materializa este hecho.

    OP-13 no toca `prevision_hechos` (F04-D033); esta lectura existe solo para
    que el resultado pueda informar de la coexistencia sin modificarla.
    """
    fila = sesion.uno(
        "SELECT count(*) FROM gapto.prevision_hechos WHERE hecho_id = %s::uuid",
        (hecho_id,),
    )
    return 0 if fila is None else fila[0]
