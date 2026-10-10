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
#
#   v0.2.0 (F05-D003): codigo propio de la capa F05
#   PROPUESTA_FINANCIACION_OBSOLETA (409, definitivo): no forma parte de la
#   taxonomia F04.
#
#   v0.3.0 (F05-01, F05-D009): codigos de capa F05 CATEGORIA_NO_ELEGIBLE y
#   CATEGORIA_REQUIERE_MAGNITUDES (409, definitivos, sin escritura previa).
#   El segundo es un bloqueo TRANSITORIO hasta implementar C07.
#   AGREGADO_NO_ENCONTRADO -> 404 para las lecturas de categorias.
#
#   v0.4.0 (F05-01, S4): `rechazo_categoria` traduce los rechazos de la
#   gestion del arbol (codigos F05 y F04 reutilizados). Mensajes fijos; el
#   detalle solo se devuelve para CAMBIO_AMBITO_REQUIERE_CONFIRMACION (el
#   recuento vigente que el usuario debe confirmar).
#
#   v0.5.0 (F05-01, S6-C07; F05-D014 §28.2): se retira el bloqueo transitorio
#   CATEGORIA_REQUIERE_MAGNITUDES y se anaden los cuatro codigos F05 de C07
#   (409, definitivos, sin escritura previa): CATEGORIA_MAGNITUD_NO_DISPONIBLE,
#   MAGNITUD_NO_ADMITIDA, MAGNITUD_OBLIGATORIA_AUSENTE y
#   MAGNITUD_VALOR_NO_VALIDO. Los errores de forma del wire (null, repetida,
#   `unidad`, sintaxis) son 422 ENTRADA_INVALIDA del DTO.
#
#   v0.6.0 (F05-01 S6-ICONO (F05-D013), AJ-ICON-05): codigo F05
#   ICONO_CATEGORIA_NO_VALIDO (422: dato de entrada, como
#   CATEGORIA_PADRE_NO_VALIDO) para una clave fuera de la biblioteca v1, en
#   el alta y en el comando de icono. Sin escritura previa.
#
#   v0.7.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): codigo F05
#   CONJUNTO_HERMANOS_DESFASADO (409: el conjunto de hermanos persistido no
#   coincide con el enviado; no distingue falta, sobra, inexistente, ajena u
#   otro padre).
#
#   v0.8.0 (F05-01 S7-MAG (F05-D020 D-MAG-09)): `rechazo_magnitud` traduce los
#   rechazos de los comandos de magnitudes. Codigos F05 nuevos (409, sin
#   escritura previa): MAGNITUD_NOMBRE_DUPLICADO (detalle: magnitud_id y
#   enabled de la existente del owner), ASOCIACION_YA_EXISTE,
#   ASOCIACION_NO_EXISTE, CONJUNTO_MAGNITUDES_DESFASADO y
#   MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION (detalle:
#   categorias_no_capturables calculadas bajo lock). Reutilizados:
#   MAGNITUD_NO_ADMITIDA (409), AGREGADO_NO_ENCONTRADO (404),
#   VERSION_DESFASADA (409), IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION (409) y
#   ENTRADA_INVALIDA (422). Mensajes fijos; el detalle solo para los dos
#   codigos que lo definen.
#
#   v0.9.0 (F05-02 B1, F05-D026 §41.3): `rechazo_preferencia` traduce los
#   rechazos de los writers de preferencias. Codigos F05 nuevos, sin
#   escritura previa: PREFERENCIA_SIN_VALOR, PREFERENCIA_DIMENSION_DIFERIDA y
#   PREFERENCIA_PRIORIDAD_NO_ADMITIDA (422: dato de entrada);
#   PREFERENCIA_CUENTA_NO_ELEGIBLE, PREFERENCIA_CATEGORIA_NO_ELEGIBLE y
#   PREFERENCIA_EMPATE_CONTRADICTORIO (409; este ultimo con detalle
#   preferencia_conflicto_id, que la UI usa en S03/R07). Reutilizados:
#   AGREGADO_NO_ENCONTRADO (404), VERSION_DESFASADA (409),
#   IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION (409) y ENTRADA_INVALIDA (422).
#
#   v0.10.0 (F05-03/F05-04 J2 §1.5; F05 §46.4 R6, §46.5 E2/E3): codigos de
#   preferencia nuevos PREFERENCIA_SIN_TIPO y PREFERENCIA_AMBITO_NO_ADMITIDO
#   (422: dato de entrada) y PREFERENCIA_TERCERO_NO_ELEGIBLE (409). El mensaje
#   de PREFERENCIA_DIMENSION_DIFERIDA pasa a citar solo la entidad (el
#   tercero es operativo, E2).
#
#   v0.11.0 (F05-03/F05-04 J2 §1.2; F05-D032 C6): rechazo de integracion
#   FECHA_FUTURA (422, dato de entrada respecto del «hoy» del owner; el
#   mensaje nombra el campo fecha_hecho, como el 422 de forma).
# Version: 0.11.0
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
    # F05-01 (lecturas de categorias): el recurso no existe o es de otro
    # tenant; no se distingue para no revelar existencia ajena.
    CodigoError.AGREGADO_NO_ENCONTRADO: (404, "No encontrado.", False),
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


_RECHAZOS_INTEGRACION: dict[str, tuple[int, str]] = {
    "FECHA_FUTURA": (
        422,
        "Revisa los datos: fecha_hecho no puede ser futura (solo se registra lo ya ocurrido).",
    ),
    "PROPUESTA_FINANCIACION_OBSOLETA": (
        409,
        "La cuenta ha cambiado de titularidad desde que abriste el formulario. "
        "Revisa la financiación: no se ha guardado nada.",
    ),
    "CATEGORIA_NO_ELEGIBLE": (
        409,
        "Esa categoría ya no se puede elegir para este registro. "
        "Elige otra o «Sin categoría»: no se ha guardado nada.",
    ),
    "CATEGORIA_MAGNITUD_NO_DISPONIBLE": (
        409,
        "Esa categoría pide un dato que ya no está disponible. "
        "Elige otra o «Sin categoría»: no se ha guardado nada.",
    ),
    "MAGNITUD_NO_ADMITIDA": (
        409,
        "Uno de los datos adicionales no corresponde a esta categoría. "
        "Revísalos: no se ha guardado nada.",
    ),
    "MAGNITUD_OBLIGATORIA_AUSENTE": (
        409,
        "Falta un dato obligatorio de esta categoría. Complétalo, elige otra "
        "o «Sin categoría»: no se ha guardado nada.",
    ),
    "MAGNITUD_VALOR_NO_VALIDO": (
        409,
        "Un dato adicional tiene más decimales o es mayor de lo permitido. "
        "Revísalo: no se ha guardado nada.",
    ),
}


def rechazo_integracion(codigo: str) -> tuple[int, dict]:
    """Rechazo DEFINITIVO de la capa F05: repetir la misma intencion no puede
    tener exito; el cliente libera la edicion y usara identidad nueva."""
    status, mensaje = _RECHAZOS_INTEGRACION[codigo]
    return status, {"codigo": codigo, "mensaje": mensaje, "reintentable": False}


_RECHAZOS_CATEGORIA: dict[str, tuple[int, str]] = {
    "CATEGORIA_NOMBRE_DUPLICADO": (409, "Ya hay una categoría activa con ese nombre en el mismo nivel."),
    "CATEGORIA_PADRE_NO_VALIDO": (422, "La categoría superior elegida no es válida."),
    "CATEGORIA_PADRE_DESHABILITADO": (409, "La categoría superior (o alguna por encima) está desactivada."),
    "CATEGORIA_TIENE_HIJOS_ACTIVOS": (409, "Tiene subcategorías activas: desactiva la rama completa o desactívalas antes."),
    "CATEGORIA_MOVIMIENTO_BLOQUEADO_POR_PRESUPUESTO": (409, "No se puede mover: afecta a un presupuesto que ya no está en borrador."),
    "CAMBIO_AMBITO_REQUIERE_CONFIRMACION": (409, "El uso de la categoría ha cambiado. Revísalo y confirma de nuevo."),
    "AGREGADO_NO_ENCONTRADO": (404, "No encontrado."),
    "VERSION_DESFASADA": (409, "La categoría ha cambiado desde que la abriste. Vuelve a cargarla."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
    "ICONO_CATEGORIA_NO_VALIDO": (422, "Ese icono no está disponible. Elige otro o «Sin icono»."),
    "CONJUNTO_HERMANOS_DESFASADO": (409, "Las categorías de este nivel han cambiado. Vuelve a cargarlas."),
}


def rechazo_categoria(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_CATEGORIA[codigo]
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if codigo == "CAMBIO_AMBITO_REQUIERE_CONFIRMACION" and detalle is not None:
        cuerpo["detalle"] = detalle
    return status, cuerpo


_RECHAZOS_MAGNITUD: dict[str, tuple[int, str]] = {
    "MAGNITUD_NOMBRE_DUPLICADO": (409, "Ya tienes una magnitud con ese nombre. Puedes usar la existente."),
    "ASOCIACION_YA_EXISTE": (409, "Esa magnitud ya está en esta categoría con otra configuración. Vuelve a cargarla."),
    "ASOCIACION_NO_EXISTE": (409, "Las magnitudes de esta categoría han cambiado. Vuelve a cargarlas."),
    "CONJUNTO_MAGNITUDES_DESFASADO": (409, "Las magnitudes de esta categoría han cambiado. Vuelve a cargarlas."),
    "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION": (
        409, "Deshabilitarla afecta a categorías que la piden como obligatoria. Revísalas y confirma."),
    "MAGNITUD_NO_ADMITIDA": (409, "Esa magnitud no está disponible."),
    "AGREGADO_NO_ENCONTRADO": (404, "No encontrado."),
    "VERSION_DESFASADA": (409, "La magnitud ha cambiado desde que la abriste. Vuelve a cargarla."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
}
_CON_DETALLE_MAGNITUD = frozenset({"MAGNITUD_NOMBRE_DUPLICADO", "MAGNITUD_DESHABILITAR_REQUIERE_CONFIRMACION"})


def rechazo_magnitud(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_MAGNITUD[codigo]
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if codigo in _CON_DETALLE_MAGNITUD and detalle is not None:
        cuerpo["detalle"] = detalle
    return status, cuerpo


_RECHAZOS_PREFERENCIA: dict[str, tuple[int, str]] = {
    "PREFERENCIA_SIN_VALOR": (422, "La preferencia debe proponer una cuenta o si cuenta para el presupuesto."),
    "PREFERENCIA_DIMENSION_DIFERIDA": (422, "Las preferencias por entidad aún no están disponibles."),
    "PREFERENCIA_SIN_TIPO": (422, "Indica si la preferencia es para gastos o para ingresos."),
    "PREFERENCIA_AMBITO_NO_ADMITIDO": (422, "Una preferencia es para una categoría o para un tercero, no para los dos."),
    "PREFERENCIA_TERCERO_NO_ELEGIBLE": (409, "Ese tercero no está disponible. Elige otro."),
    "PREFERENCIA_PRIORIDAD_NO_ADMITIDA": (422, "La prioridad indicada no está admitida."),
    "PREFERENCIA_CUENTA_NO_ELEGIBLE": (409, "Esa cuenta no está disponible para registrar gastos. Elige otra."),
    "PREFERENCIA_CATEGORIA_NO_ELEGIBLE": (409, "Esa categoría no está disponible. Elige otra o «Sin categoría»."),
    "PREFERENCIA_EMPATE_CONTRADICTORIO": (
        409, "Ya hay otra preferencia para el mismo caso que propone un valor distinto. Revísala."),
    "AGREGADO_NO_ENCONTRADO": (404, "No encontrado."),
    "VERSION_DESFASADA": (409, "La preferencia ha cambiado desde que la abriste. Vuelve a cargarla."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
}


def rechazo_preferencia(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_PREFERENCIA[codigo]
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if codigo == "PREFERENCIA_EMPATE_CONTRADICTORIO" and detalle is not None:
        cuerpo["detalle"] = {k: str(v) for k, v in detalle.items()}
    return status, cuerpo
