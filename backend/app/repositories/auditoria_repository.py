# ============================================================
# GAPTO MOBILE 2027
# Fichero: auditoria_repository.py
# Ruta: backend/app/repositories/auditoria_repository.py
# Descripcion: Unico punto de escritura de auditoria del motor.
#
#   El runtime NO inserta en gapto.auditoria: la migration 0180 le revoco el
#   INSERT y encamino la escritura por gapto.fn_registrar_auditoria, que es
#   SECURITY DEFINER bajo gapto_internal y deriva owner, actor_tipo,
#   actor_user_id y request_id del contexto transaccional. Ninguno de esos
#   cuatro valores es parametro: no son falsificables por el llamante.
#
#   Los snapshots se pasan como TEXTO JSON con cast explicito a jsonb, tal y
#   como salieron de PostgreSQL, para no alterar la representacion de numeric
#   ni de fechas en un round-trip por Python.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid

from app.core.unidad_trabajo import SesionMotor

ACCION_CREAR = "CREAR"
ACCION_ACTUALIZAR = "ACTUALIZAR"
ACCION_ANULAR = "ANULAR"


def registrar(
    sesion: SesionMotor,
    *,
    tabla: str,
    registro_id: uuid.UUID,
    accion: str,
    datos_antes_json: str | None = None,
    datos_despues_json: str | None = None,
    motivo: str | None = None,
) -> uuid.UUID:
    """Escribe la auditoria en la MISMA transaccion que la mutacion.

    Si esta llamada falla, la transaccion completa hace rollback y la mutacion
    desaparece con ella: no puede quedar un hecho modificado sin auditoria.
    """
    fila = sesion.uno(
        "SELECT gapto.fn_registrar_auditoria("
        "%s::varchar, %s::uuid, %s::varchar, %s::jsonb, %s::jsonb, %s::text)",
        (tabla, registro_id, accion, datos_antes_json, datos_despues_json, motivo),
    )
    assert fila is not None  # la funcion siempre devuelve un uuid o lanza
    return fila[0]
