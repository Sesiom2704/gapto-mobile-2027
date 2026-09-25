# ============================================================
# GAPTO MOBILE 2027
# Fichero: errores_http.py
# Ruta: backend/app/api/errores_http.py
# Descripcion: Traduccion de errores del motor a respuestas HTTP estables del
#   adaptador F05-00-B. El cliente recibe {codigo, mensaje, reintentable}:
#     - `codigo` es el CodigoError del motor (contrato cerrado F04) o un codigo
#       propio del adaptador (BACKEND_NO_DISPONIBLE, NO_AUTORIZADO, INTERNO);
#     - `mensaje` es un texto de usuario FIJO por codigo, nunca el texto de
#       PostgreSQL ni el mensaje interno (pueden revelar constraints o datos);
#     - `reintentable` solo es true cuando repetir la MISMA intencion es seguro
#       y puede tener exito (concurrencia agotada, backend caido).
#   API DE INTEGRACION F05-00-B, PENDIENTE DE CONSOLIDACION F10 (F10-05).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

from app.core.errores import CodigoError

# (status HTTP, mensaje de usuario, reintentable)
_MAPA: dict[CodigoError, tuple[int, str, bool]] = {
    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION: (
        409,
        "Este registro ya existe con otros datos. No se ha guardado nada nuevo.",
        False,
    ),
    CodigoError.CONFLICTO_CONCURRENCIA: (
        503,
        "El servidor estaba ocupado y no ha guardado nada. Puedes reintentar.",
        True,
    ),
    CodigoError.CUENTA_DESCONOCIDA: (422, "La cuenta seleccionada no está disponible.", False),
    CodigoError.MONEDA_INVALIDA: (
        422,
        "La cuenta debe estar en la misma moneda que el gasto.",
        False,
    ),
    # BD caida o conexion perdida: puede haber ocurrido durante el COMMIT, asi
    # que el resultado es INDETERMINADO. Nunca se afirma "no se ha guardado":
    # se pide reintentar la MISMA intencion, que OP-22 hace idempotente.
    CodigoError.BD_NO_DISPONIBLE: (
        503,
        "No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.",
        True,
    ),
    CodigoError.TENANT_AUSENTE: (500, "Error interno de configuración.", False),
    CodigoError.ACTOR_DESCONOCIDO: (500, "Error interno de configuración.", False),
}
_POR_DEFECTO_DOMINIO = (422, "No se ha podido registrar: los datos no son válidos para esta operación.", False)
_INTERNOS = {CodigoError.INTERNO, CodigoError.VIOLACION_INVARIANTE_FISICA}


def traducir_error_motor(codigo: CodigoError) -> tuple[int, dict]:
    if codigo in _INTERNOS:
        status, mensaje, reintentable = 500, "Error interno. No se ha confirmado el registro.", False
    else:
        status, mensaje, reintentable = _MAPA.get(codigo, _POR_DEFECTO_DOMINIO)
    return status, {"codigo": codigo.value, "mensaje": mensaje, "reintentable": reintentable}


def backend_no_disponible() -> tuple[int, dict]:
    """Fallo tecnico fuera del motor (p. ej. al abrir conexion). Indeterminado."""
    return 503, {
        "codigo": "BACKEND_NO_DISPONIBLE",
        "mensaje": "No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.",
        "reintentable": True,
    }


def no_autorizado() -> tuple[int, dict]:
    return 401, {"codigo": "NO_AUTORIZADO", "mensaje": "Sesión de desarrollo no válida.", "reintentable": False}


def interno() -> tuple[int, dict]:
    return 500, {"codigo": "INTERNO", "mensaje": "Error interno. No se ha confirmado el registro.", "reintentable": False}
