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
#
#   v0.12.0 (F05-03/F05-04 J2 §1.3/§1.4): `rechazo_tercero` y
#   `rechazo_contexto` traducen los writers de maestros: *_NO_ENCONTRADO
#   (404), VERSION_DESFASADA e IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION (409),
#   TERCERO_NATURALEZA_NO_ADMITIDA (409), ENTRADA_INVALIDA (422).
#
#   v0.13.0 (F05-03/F05-04 J2 §1.6): `rechazo_plantilla` traduce los writers
#   de plantillas y acciones rapidas (422 entrada/tipo/sin valor/icono; 404 no
#   encontrada; 409 el resto). PLANTILLA_NOMBRE_REPETIDO lleva el detalle
#   plantilla_id (S04 «Ir a la plantilla»).
#
#   v0.14.0 (F05-03/F05-04 J2 §1.7): rechazos de integracion
#   TERCERO_NO_DISPONIBLE y CONTEXTO_NO_DISPONIBLE (409, sin escritura); el
#   codigo F04 MISMA_CUENTA (OP-10) con mensaje de campo (422).
#
#   v0.15.0 (F05-03 J2 §1.8): ONBOARDING_NO_APLICABLE (409) en los rechazos
#   de categoria (el owner ya tiene categorias).
#   v0.16.0 (F05-05 K2 §1.2-§1.6): rechazos de afinidades (TERCERO_NO_ELEGIBLE,
#   CATEGORIA_NO_ELEGIBLE, REFERENCIA_NO_DISPONIBLE con el sqlstate en el
#   detalle, IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION) y de las lecturas de
#   F05-05 (TERCERO_NO_ENCONTRADO 404, FECHA_FUTURA 422; sin «no se ha
#   guardado nada», porque son lecturas).
#   v0.18.0 (F04-R1 G-R1-C; F04-D058): PORCION_DE_REALIDAD_EXCEDIDA -> 409,
#   mensaje fijo; el detalle de contexto_extra no se serializa (como el resto
#   del catalogo F04).
#   v0.17.0 (F05-06 M4 §2.3/§2.4; D-CAP-08; PD-2/PD-3): rechazo de
#   integracion CUENTA_SIN_CAPACIDAD (409, sin escritura) con el texto de B3,
#   compuesto con el detalle (nombre de la cuenta propia y operacion), que se
#   devuelve tambien en `detalle`. `rechazo_capacidad` traduce el writer de
#   capacidades: CUENTA_NO_ENCONTRADA (404), CAPACIDAD_NO_EDITABLE,
#   OPERACION_NO_PERMITIDA_EN_ESTADO y VERSION_DESFASADA (409),
#   ENTRADA_INVALIDA (422).
#   v0.19.0 (F05-06 M2 §A2-§A3; nota de impacto de F04-R1 F5): devolucion
#   contextual. _MAPA: HECHO_CON_REALIDAD_ASOCIADA (409; G-R1-A, un origen con
#   devolucion activa no se anula), YA_CONCILIADO (409; no hay abono doble) y
#   EXCEDE_CAPACIDAD_REVERSIBLE (409; limite acumulado de OP-13). Ninguna ruta
#   previa los alcanzaba (caian en el 422 por defecto). Rechazos de
#   integracion F05 nuevos (409, sin escritura): DEVOLUCION_ORIGEN_NO_ACTIVO,
#   DEVOLUCION_ORIGEN_NO_GASTO, DEVOLUCION_ORIGEN_V3_VARIOS_EFECTOS,
#   DEVOLUCION_ORIGEN_MULTICATEGORIA, DEVOLUCION_ATRIBUCION_NO_DEMOSTRABLE,
#   HECHO_NO_ES_DEVOLUCION y DEVOLUCION_NO_ACTIVA; EXCEDE_CAPACIDAD_REVERSIBLE
#   como rechazo con detalle {queda} (texto de B3 con «lo que queda»);
#   CUENTA_SIN_CAPACIDAD con la operacion ABONO_DEVOLUCION (capacidad
#   PAGAR_GASTO: «recibir devoluciones de gastos», nunca «ingreso», D-DEV-04).
#   v0.20.0 (F05-06 M2-D §1-§2): CUENTA_SIN_CAPACIDAD de ABONO_DEVOLUCION
#   nombra la capacidad que llega en el detalle (RECIBIR_INGRESO: «recibir
#   dinero», nunca «ingreso», D-DEV-04); el resto de operaciones no cambia.
#   v0.21.0 (F05-06 M3 §A2-§A5; lamina REP v0.2): codigos del reparto y de
#   las posiciones en lenguaje llano. _MAPA (aditivo): CORRECCION_AGREGADA_
#   REQUERIDA, VERSION_DESFASADA, EXCEDE_SALDO_DEL_DERECHO, EXCEDE_SALDO_
#   POSICION, INTEGRIDAD_POSICION_VIOLADA, POSICION_CERRADA (409) y CUENTA_
#   GAPTO_REQUERIDA (422). Rechazos de capa F05: TERCERO_NO_PERSONA, POSICION_
#   NO_ENCONTRADA, POSICION_NO_ADMITE_OPERACION, REPARTO_NO_CORREGIBLE (con su
#   detalle {motivo}), REPARTO_NO_DEMOSTRABLE y HECHO_NO_ENCONTRADO. El resto
#   de codigos y respuestas no cambia.
# Version: 0.21.0
#   v0.22.0 (F05-06 M5 §A5; F05 §59 F05-D044; D-M5-15): confirmacion de
#   previsiones. _MAPA (aditivo): ESTADO_PREVISION_INCOMPATIBLE y
#   PREVISION_YA_MATERIALIZADA_POR_ESTA_REALIDAD (409); ninguna ruta previa los
#   alcanzaba. `rechazo_prevision`: textos llanos PROPIOS de las rutas de
#   prevision y del registro con bloque `prevision` (PORCION_DE_REALIDAD_
#   EXCEDIDA en EXCEDE y NO_DETERMINABLE, PORCION_CAMBIADA, PREVISION_YA_
#   MATERIALIZADA, ESTADO_PREVISION_INCOMPATIBLE, VERSION_DESFASADA «Ha
#   cambiado; revisa», OPERACION_NO_PERMITIDA_EN_ESTADO (hecho anulado),
#   IDENTIDAD_REUTILIZADA, PREVISION_TIPO_DISTINTO); el texto global de
#   VERSION_DESFASADA (M3) no cambia. Rechazo de integracion nuevo:
#   PREVISION_TIPO_DISTINTO (409, sin escritura).
# Version: 0.22.0
#   0.23.0 (F05-06 M5-B; F04-D065; AJ-M5BM1-03): codigo nuevo
#   PREVISION_SIN_REALIDAD_ACTIVA (409; informa de «No hubo este mes» sin
#   ofrecerlo) en _MAPA y en las rutas de prevision; en estas ultimas, ademas,
#   TRAMO_RODANTE_REQUIERE_REVISION (409, sin reintento automatico),
#   MOTIVO_AUSENTE (422) y ENTRADA_INVALIDA (409, la cadena cambio). Ningun
#   codigo existente cambia de texto ni de estado.
# Version: 0.23.0
#   0.24.0 (F05-06 M1; F05 §61.2; lamina EDIT-HECHO v0.1): MOTIVOS_EDICION, el
#   texto llano de cada motivo de elegibilidad o de rechazo de OP-21P, OP-21T y
#   OP-03P (contexto_extra.motivo o .detalle del motor), y rechazo_edicion, que
#   conserva el status y el codigo de _MAPA y solo sustituye el mensaje cuando
#   el motor dice por que. Ningun codigo existente cambia de status.
# Version: 0.24.0
#   0.25.0 (F05-06 M1 v1.1; Q9 opcion (a)): rechazo de integracion nuevo
#   CATEGORIA_V3_NO_CORREGIBLE (409, con detalle {motivo} y el texto de
#   MOTIVOS_EDICION); MOTIVOS_EDICION anade NO_IMPORTADO y VARIOS_EFECTOS, y
#   ORIGEN_IMPORTADO dice que en V3 solo se corrige la categoria. Ningun codigo
#   existente cambia de status.
# Version: 0.25.0
# ============================================================

from __future__ import annotations

from app.core.errores import CodigoError

#: F05-06 M5-B (F04-D065): dar por cubierta sin realidad; informa de «No hubo» sin ofrecerlo.
MENSAJE_SIN_REALIDAD = ("Esta previsión no tiene nada registrado: no se puede dar por cubierta. Si este mes no "
                        "hubo, existe «No hubo este mes». No se ha guardado nada.")

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
    CodigoError.PORCION_DE_REALIDAD_EXCEDIDA: (
        409,
        "Esa realidad ya está asignada a otras previsiones por su importe completo. No se ha guardado nada.",
        False,
    ),
    # F05-06 M2 (devolucion contextual).
    CodigoError.HECHO_CON_REALIDAD_ASOCIADA: (
        409,
        "No se puede anular: tiene una devolución u otra operación registrada. No se ha cambiado nada.",
        False,
    ),
    CodigoError.YA_CONCILIADO: (409, "Esta devolución ya tiene su abono registrado. No se ha guardado nada.", False),
    CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE: (
        409,
        "Supera lo que queda por devolver de esta compra. No se ha guardado nada.",
        False,
    ),
    CodigoError.MISMA_CUENTA: (422, "Elige dos cuentas distintas: origen y destino no pueden coincidir.", False),
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
    # F05-06 M3 (reparto y posiciones; lamina REP v0.2).
    CodigoError.CORRECCION_AGREGADA_REQUERIDA: (
        409,
        "Este cambio alteraría quién debe a quién: en esta versión solo se pueden cambiar los "
        "importes de quienes ya están en el reparto. No se ha cambiado nada.",
        False,
    ),
    CodigoError.VERSION_DESFASADA: (
        409, "Este registro ha cambiado mientras lo corregías. Tus cambios no se han aplicado.", False),
    CodigoError.EXCEDE_SALDO_DEL_DERECHO: (409, "Es más de lo que te debe. No se ha guardado nada.", False),
    CodigoError.EXCEDE_SALDO_POSICION: (409, "Es más de lo que debes. No se ha guardado nada.", False),
    CodigoError.INTEGRIDAD_POSICION_VIOLADA: (
        409,
        "No puede quedar por debajo de lo ya cobrado o perdonado. No se ha cambiado nada.",
        False,
    ),
    CodigoError.POSICION_CERRADA: (409, "Esto ya está saldado. No se ha guardado nada.", False),
    CodigoError.CUENTA_GAPTO_REQUERIDA: (
        422, "Elige en qué cuenta entró o de qué cuenta salió el dinero (Efectivo incluido).", False),
    # F05-06 M5 (confirmacion de previsiones; lamina PREV v0.2).
    CodigoError.ESTADO_PREVISION_INCOMPATIBLE: (
        409, "Esta previsión ya no está pendiente. No se ha guardado nada.", False),
    CodigoError.PREVISION_YA_MATERIALIZADA_POR_ESTA_REALIDAD: (
        409, "Ese registro ya está enlazado a esta previsión. No se ha guardado nada.", False),
    # F05-06 M5-B (F04-D065).
    CodigoError.PREVISION_SIN_REALIDAD_ACTIVA: (409, MENSAJE_SIN_REALIDAD, False),
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
    "TERCERO_NO_DISPONIBLE": (
        409, "Ese tercero ya no está disponible. Elige otro o quítalo: no se ha guardado nada."),
    "CONTEXTO_NO_DISPONIBLE": (
        409, "Ese contexto ya no está disponible. Elige otro o quítalo: no se ha guardado nada."),
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
    # F05-06 M3: reparto y posiciones (lamina REP v0.2).
    "TERCERO_NO_PERSONA": (
        409, "Solo se reparte con personas. Empresas y organismos no entran en un reparto. No se ha guardado nada."),
    "POSICION_NO_ENCONTRADA": (404, "No encontrado."),
    "POSICION_NO_ADMITE_OPERACION": (
        409, "Esta operación no corresponde: un cobro es de lo que te deben y un pago, de lo que debes. "
             "No se ha guardado nada."),
    "REPARTO_NO_CORREGIBLE": (
        409, "Este reparto no se puede corregir así. No se ha cambiado nada."),
    "REPARTO_NO_DEMOSTRABLE": (
        409, "No se puede comprobar que la deuda coincida con su parte: corrígelo desde lo que te debe. "
             "No se ha cambiado nada."),
    "HECHO_NO_ENCONTRADO": (404, "No encontrado."),
    # F05-06 M2: devolucion contextual (D-DEV, P-DEV).
    "DEVOLUCION_ORIGEN_NO_ACTIVO": (
        409, "Esta compra ya no está activa: no se puede registrar una devolución. No se ha guardado nada."),
    "DEVOLUCION_ORIGEN_NO_GASTO": (
        409, "Solo se pueden registrar devoluciones de gastos. No se ha guardado nada."),
    "DEVOLUCION_ORIGEN_V3_VARIOS_EFECTOS": (
        409, "Esta compra viene de la versión anterior con varias partes: no se puede saber qué se devuelve. "
             "No se ha guardado nada."),
    "DEVOLUCION_ORIGEN_MULTICATEGORIA": (
        409, "Esta compra tiene varias categorías: aún no se puede registrar su devolución. No se ha guardado nada."),
    "DEVOLUCION_ATRIBUCION_NO_DEMOSTRABLE": (
        409, "La compra no era 100 % tuya: la devolución no puede quedar como tuya. Déjala «Sin indicar». "
             "No se ha guardado nada."),
    "HECHO_NO_ES_DEVOLUCION": (409, "Solo se registra un abono sobre una devolución. No se ha guardado nada."),
    "DEVOLUCION_NO_ACTIVA": (409, "Esta devolución ya no está activa. No se ha guardado nada."),
    # F05-06 M5: registro desde la prevision.
    "PREVISION_TIPO_DISTINTO": (
        409, "Ese registro no es del mismo tipo que la previsión. No se ha guardado nada."),
}


#: F05-06 M5: textos de las rutas de prevision y del registro con bloque `prevision`.
_RECHAZOS_PREVISION: dict[str, tuple[int, str]] = {
    "PORCION_DE_REALIDAD_EXCEDIDA": (
        409, "Ese registro ya está enlazado a otras previsiones por su importe completo. No se ha guardado nada."),
    "PORCION_CAMBIADA": (
        409, "Ese registro ha cambiado mientras lo elegías: revisa cuánto se vinculará. No se ha guardado nada."),
    "PREVISION_YA_MATERIALIZADA_POR_ESTA_REALIDAD": (
        409, "Ese registro ya está enlazado a esta previsión. No se ha guardado nada."),
    "ESTADO_PREVISION_INCOMPATIBLE": (409, "Esta previsión ya no está pendiente. No se ha guardado nada."),
    "VERSION_DESFASADA": (409, "Ha cambiado; revisa. No se ha guardado nada."),
    "OPERACION_NO_PERMITIDA_EN_ESTADO": (
        409, "Ese registro está anulado: no puede cubrir una previsión. No se ha guardado nada."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (
        409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "PREVISION_TIPO_DISTINTO": (
        409, "Ese registro no es del mismo tipo que la previsión. No se ha guardado nada."),
    "AGREGADO_NO_ENCONTRADO": (404, "No encontrado."),
    # F05-06 M5-B (dar por cubierta y reabrir).
    "PREVISION_SIN_REALIDAD_ACTIVA": (409, MENSAJE_SIN_REALIDAD),
    "TRAMO_RODANTE_REQUIERE_REVISION": (
        409, "La siguiente previsión de esta serie ya tiene algo registrado o está cerrada: no se puede reabrir "
             "desde aquí. No se ha cambiado nada."),
    "MOTIVO_AUSENTE": (422, "Escribe el motivo. No se ha guardado nada."),
    "ENTRADA_INVALIDA": (409, "La serie de esta previsión ha cambiado: vuelve a abrirla. No se ha cambiado nada."),
}
_PORCION_NO_DETERMINABLE = ("El importe de ese registro no se puede comparar con lo ya enlazado: "
                            "no se puede enlazar así. No se ha guardado nada.")
CODIGOS_PREVISION = frozenset(_RECHAZOS_PREVISION)


def rechazo_prevision(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    """F05-06 M5: rechazo de una ruta de prevision (motor o capa F05), con su
    detalle (motivo de la porcion, porcion releida o estado actual)."""
    status, mensaje = _RECHAZOS_PREVISION[codigo]
    if codigo == "PORCION_DE_REALIDAD_EXCEDIDA" and (detalle or {}).get("motivo") == "NO_DETERMINABLE":
        mensaje = _PORCION_NO_DETERMINABLE
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if detalle:
        cuerpo["detalle"] = dict(detalle)
    return status, cuerpo


#: CUENTA_SIN_CAPACIDAD (B3): operacion -> (lo que la cuenta ya no puede hacer, lo que no se ha guardado).
_SIN_CAPACIDAD: dict[str, tuple[str, str]] = {
    "GASTO": ("pagar gastos", "El gasto"),
    "INGRESO": ("recibir ingresos", "El ingreso"),
    "TRANSFERENCIA_ORIGEN": ("enviar a otras cuentas tuyas", "La transferencia"),
    "TRANSFERENCIA_DESTINO": ("recibir de otras cuentas tuyas", "La transferencia"),
    "ABONO_DEVOLUCION": ("recibir dinero", "El abono"),
}
#: ABONO_DEVOLUCION: lo que la cuenta ya no puede hacer, segun la capacidad del detalle (M2-D; nunca «ingreso»).
_SIN_CAPACIDAD_ABONO: dict[str, str] = {"RECIBIR_INGRESO": "recibir dinero"}


def _mensaje_sin_capacidad(detalle: dict) -> str:
    verbo, sujeto = _SIN_CAPACIDAD[detalle["operacion"]]
    if detalle["operacion"] == "ABONO_DEVOLUCION":
        verbo = _SIN_CAPACIDAD_ABONO[detalle["capacidad"]]
    return (f"{detalle['cuenta']} ya no puede {verbo}. Se cambió mientras registrabas. "
            f"{sujeto} no se ha guardado: elige otra cuenta.")


def rechazo_integracion(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    """Rechazo DEFINITIVO de la capa F05: repetir la misma intencion no puede
    tener exito; el cliente libera la edicion y usara identidad nueva."""
    if codigo == "CUENTA_SIN_CAPACIDAD":
        return 409, {"codigo": codigo, "mensaje": _mensaje_sin_capacidad(detalle), "reintentable": False,
                     "detalle": dict(detalle)}
    if codigo == "EXCEDE_CAPACIDAD_REVERSIBLE":
        queda = detalle["queda"].replace(".", ",")
        return 409, {"codigo": codigo,
                     "mensaje": (f"Supera lo que queda por devolver de esta compra ({queda} €). Si te han abonado "
                                 "más, la diferencia no es una devolución. No se ha guardado nada."),
                     "reintentable": False, "detalle": dict(detalle)}
    if codigo == "CATEGORIA_V3_NO_CORREGIBLE":
        return 409, {"codigo": codigo, "mensaje": f"{MOTIVOS_EDICION[detalle['motivo']]} No se ha cambiado nada.",
                     "reintentable": False, "detalle": dict(detalle)}
    status, mensaje = _RECHAZOS_INTEGRACION[codigo]
    if codigo in _CON_DETALLE and detalle:
        return status, {"codigo": codigo, "mensaje": mensaje, "reintentable": False, "detalle": dict(detalle)}
    return status, {"codigo": codigo, "mensaje": mensaje, "reintentable": False}


#: F05-06 M3: rechazos cuyo detalle necesita la UI para el texto atenuado.
_CON_DETALLE = frozenset({"REPARTO_NO_CORREGIBLE", "TERCERO_NO_PERSONA"})


_RECHAZOS_CAPACIDAD: dict[str, tuple[int, str]] = {
    "CUENTA_NO_ENCONTRADA": (404, "No encontrado."),
    "CAPACIDAD_NO_EDITABLE": (409, "Esta capacidad aún no se usa en el registro y no se puede cambiar."),
    "OPERACION_NO_PERMITIDA_EN_ESTADO": (
        409, "Esta cuenta está cerrada o desactivada: no se puede cambiar lo que puede hacer."),
    "VERSION_DESFASADA": (409, "La cuenta ha cambiado desde que la abriste. Vuelve a cargarla."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
}


def rechazo_capacidad(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_CAPACIDAD[codigo]
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
    "ONBOARDING_NO_APLICABLE": (409, "Ya tienes categorías: las sugeridas solo se ofrecen si aún no tienes ninguna."),
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


_RECHAZOS_TERCERO: dict[str, tuple[int, str]] = {
    "TERCERO_NO_ENCONTRADO": (404, "No encontrado."),
    "TERCERO_NATURALEZA_NO_ADMITIDA": (
        409, "Este tercero tiene datos de persona: su naturaleza debe seguir siendo «Persona»."),
    "VERSION_DESFASADA": (409, "El tercero ha cambiado desde que lo abriste. Vuelve a cargarlo."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
}
_RECHAZOS_CONTEXTO: dict[str, tuple[int, str]] = {
    "CONTEXTO_NO_ENCONTRADO": (404, "No encontrado."),
    "VERSION_DESFASADA": (409, "El contexto ha cambiado desde que lo abriste. Vuelve a cargarlo."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
}


_RECHAZOS_PLANTILLA: dict[str, tuple[int, str]] = {
    "PLANTILLA_TIPO_NO_ADMITIDO": (422, "Una plantilla solo puede ser de gasto o de ingreso."),
    "PLANTILLA_SIN_VALOR": (
        422, "Tiene que guardar al menos una cosa: categoría, cuenta, presupuesto, tercero o contexto."),
    "PLANTILLA_CATEGORIA_NO_ELEGIBLE": (409, "Esa categoría no está disponible para este tipo. Elige otra."),
    "PLANTILLA_TERCERO_NO_ELEGIBLE": (409, "Ese tercero no está disponible. Elige otro."),
    "PLANTILLA_ENTIDAD_NO_CONTEXTO": (409, "Ese contexto no está disponible. Elige otro."),
    "PLANTILLA_CUENTA_NO_ELEGIBLE": (409, "Esa cuenta no está disponible para este tipo. Elige otra o «No proponer»."),
    "PLANTILLA_NOMBRE_REPETIDO": (409, "Ya tienes una plantilla con ese nombre. Usa otro nombre o edita la existente."),
    "PLANTILLA_NO_ENCONTRADA": (404, "No encontrado."),
    "ACCION_NO_ENCONTRADA": (404, "No encontrado."),
    "ACCION_PLANTILLA_NO_DISPONIBLE": (409, "Esa plantilla no está disponible para Inicio."),
    "ACCION_PLANTILLA_YA_EN_INICIO": (409, "Esa plantilla ya está en Inicio."),
    "ACCION_LIMITE_ALCANZADO": (409, "Inicio ya muestra 3 plantillas. Quita una para añadir esta."),
    "ICONO_ACCION_NO_VALIDO": (422, "Ese icono no está disponible. Elige otro o el de la categoría."),
    "CONJUNTO_ACCIONES_DESFASADO": (409, "Los accesos de Inicio han cambiado. Vuelve a cargarlos."),
    "REFERENCIA_NO_DISPONIBLE": (409, "Alguno de los datos elegidos ya no está disponible. Revísalos."),
    "VERSION_DESFASADA": (409, "La plantilla ha cambiado desde que la abriste. Vuelve a cargarla."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
}


def rechazo_plantilla(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_PLANTILLA[codigo]
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if codigo == "PLANTILLA_NOMBRE_REPETIDO" and detalle is not None:
        cuerpo["detalle"] = {k: str(v) for k, v in detalle.items()}
    return status, cuerpo


def rechazo_tercero(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_TERCERO[codigo]
    return status, {"codigo": codigo, "mensaje": mensaje, "reintentable": False}


def rechazo_contexto(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_CONTEXTO[codigo]
    return status, {"codigo": codigo, "mensaje": mensaje, "reintentable": False}


def rechazo_preferencia(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_PREFERENCIA[codigo]
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if codigo == "PREFERENCIA_EMPATE_CONTRADICTORIO" and detalle is not None:
        cuerpo["detalle"] = {k: str(v) for k, v in detalle.items()}
    return status, cuerpo


_RECHAZOS_AFINIDAD: dict[str, tuple[int, str]] = {
    "TERCERO_NO_ELEGIBLE": (409, "Ese tercero no está disponible. Elige otro."),
    "CATEGORIA_NO_ELEGIBLE": (409, "Esa categoría no está disponible. Elige otra."),
    "REFERENCIA_NO_DISPONIBLE": (409, "Alguno de los datos elegidos no está disponible. Revísalos."),
    "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION": (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
}


def rechazo_afinidad(codigo: str, detalle: dict | None = None) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_AFINIDAD[codigo]
    cuerpo = {"codigo": codigo, "mensaje": mensaje, "reintentable": False}
    if codigo == "REFERENCIA_NO_DISPONIBLE" and detalle is not None:
        cuerpo["detalle"] = {k: str(v) for k, v in detalle.items()}
    return status, cuerpo


_RECHAZOS_LECTURA: dict[str, tuple[int, str]] = {
    "TERCERO_NO_ENCONTRADO": (404, "No encontrado."),
    "HECHO_NO_ENCONTRADO": (404, "No encontrado."),
    "FECHA_FUTURA": (422, "Revisa los datos: la fecha no puede ser futura."),
    "ENTRADA_INVALIDA": (422, "Revisa los datos."),
}


def rechazo_lectura(codigo: str) -> tuple[int, dict]:
    status, mensaje = _RECHAZOS_LECTURA[codigo]
    return status, {"codigo": codigo, "mensaje": mensaje, "reintentable": False}


# ------------------------------------------------------------------ F05-06 M1 (EDIT-HECHO v0.1)
#: Motivo del motor (o de la lectura de elegibilidad) -> texto llano. Lo no
#: corregible se explica; nunca se oculta en silencio (D-EDIT-07).
MOTIVOS_EDICION: dict[str, str] = {
    "HECHO_ANULADO": "Este registro está anulado.",
    "ORIGEN_IMPORTADO": "Registro migrado de la versión anterior (V3): en esta versión solo se corrige su categoría, con «Corregir categoría».",
    "NO_IMPORTADO": "Solo los registros migrados de la versión anterior (V3) se corrigen por esta vía. Usa «Corregir».",
    "VARIOS_EFECTOS": "Tiene varias partes con su propia categoría: no se corrige aquí en esta versión.",
    "TIPO_NO_SOPORTADO": "Este tipo de registro no se corrige ni se anula desde aquí en esta versión.",
    "DEVOLUCION": "Tiene una devolución registrada: no se corrige en esta versión.",
    "DEPENDENCIAS_ACTIVAS": "No se puede anular: tiene una devolución u otra operación registrada. Si la compra no existió, anula antes esa operación.",
    "INVERSION": "Pertenece a una inversión: no se corrige ni se anula desde aquí.",
    "SIN_TESORERIA": "No tiene un movimiento de cuenta registrado: no se corrige ni se anula por esta vía.",
    "VARIOS_MOVIMIENTOS": "Se pagó en varias partes o desde varias cuentas: no se corrige aquí en esta versión.",
    "REPARTO": "Tiene reparto con otras personas: en esta versión no se corrige aquí. El reparto se corrige con «Corregir reparto».",
    "MOVIMIENTO_COMPARTIDO": "El movimiento de la cuenta cubre también otros registros: no se corrige ni se anula desde aquí.",
    "REVERSION_EXISTENTE": "El movimiento tiene una reversión: lo que pasó después se registra con su operación.",
    "MOVIMIENTO_ANULADO": "El movimiento de la cuenta ya no está activo.",
    "CONCILIACION_PARCIAL": "El movimiento de la cuenta no cubre el registro completo: no se corrige aquí en esta versión.",
    "MULTIDIVISA": "La cuenta no está en la misma moneda que el registro.",
    "MOVIMIENTO_REAL_NO_ANULABLE": "Solo se anula si confirmas que está repetido y el cargo no ocurrió dos veces. No se ha cambiado nada.",
    "ACONTECIMIENTO_POSTERIOR": "Corregir es solo para datos que nunca fueron ciertos. Si algo cambió después, regístralo con su operación. No se ha cambiado nada.",
    "FECHA_ANTERIOR_INICIO": "Un movimiento es anterior al inicio de la cuenta en la app: su saldo inicial ya lo incluye. No se ha cambiado nada.",
}


def rechazo_edicion(codigo: CodigoError, contexto_extra: dict | None) -> tuple[int, dict]:
    """Rechazo del motor en una ruta de M1: status y codigo de _MAPA; el
    mensaje, el del motivo concreto cuando el motor lo da."""
    status, cuerpo = traducir_error_motor(codigo)
    extra = contexto_extra or {}
    motivo = extra.get("detalle") if extra.get("motivo") == "FUERA_DE_ALCANCE_V1" else extra.get("motivo")
    if motivo in MOTIVOS_EDICION:
        cuerpo = {**cuerpo, "mensaje": MOTIVOS_EDICION[motivo]}
    if motivo is not None:
        cuerpo = {**cuerpo, "detalle": {"motivo": motivo}}
    return status, cuerpo
