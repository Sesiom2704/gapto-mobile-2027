# ============================================================
# GAPTO MOBILE 2027
# Fichero: errores.py
# Ruta: backend/app/contratos/errores.py
# Descripcion: Familia de errores de contratos, servicios y terceros (F06-02/03;
#   contrato v1.1 §1.4 y §1.5, PC-CON-05, D-A-06). Mapa PROPIO (patron
#   _RECHAZOS_PROPIEDAD): codigo -> (HTTP, mensaje) con `detalle` y `motivo`.
#   Traduccion de violaciones fisicas por IDENTIDAD de la constraint
#   (nombre exacto + SQLSTATE) o por la FIRMA de la funcion del trigger en
#   `diag.context` (nunca por el texto localizable; R-LOCALE).
#   POLITICA DE EXCLUSION (AJ-COMP-04): toda constraint que no figura en
#   MAPA_FISICO NO se traduce; `traducir_fisico` devuelve None y el error sale
#   como 500 generico registrado (sin codigo de dominio ficticio).
#   C-31 CERRADO (decision de Moises del 19-11; contrato v1.2 §1.5, bbceffda…): el trigger
#   `no_ciclo` ya no existe; el vigente es trg_clasificaciones_tercero__aciclica
#   (P0001) y se traduce por la firma de gapto.fn_check_jerarquia_aciclica(),
#   como en categorias/servicio.py.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 3)
# ============================================================

from __future__ import annotations

import re
from typing import Any

import psycopg

# ---------------------------------------------------------------- codigos
AGREGADO_NO_ENCONTRADO = "AGREGADO_NO_ENCONTRADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
TERCERO_NO_DISPONIBLE = "TERCERO_NO_DISPONIBLE"
PARTICIPANTE_DUPLICADO = "PARTICIPANTE_DUPLICADO"
FECHA_ANTERIOR_INICIO = "FECHA_ANTERIOR_INICIO"
MOTIVO_AUSENTE = "MOTIVO_AUSENTE"
CAMPO_INMUTABLE = "CAMPO_INMUTABLE"
NO_PERMITIDA_EN_ESTADO = "OPERACION_NO_PERMITIDA_EN_ESTADO"
ACTOR_DESCONOCIDO = "ACTOR_DESCONOCIDO"
HABITACION_REQUERIDA = "HABITACION_REQUERIDA"
HABITACION_NO_ADMITIDA = "HABITACION_NO_ADMITIDA"
HABITACION_FUERA_DE_FICHA = "HABITACION_FUERA_DE_FICHA"
HABITACIONES_NO_INDICADAS = "HABITACIONES_NO_INDICADAS"
SOLAPE_CON_CONTRATO_FIRMADO = "SOLAPE_CON_CONTRATO_FIRMADO"
PROPIEDAD_FUERA_DE_PATRIMONIO = "PROPIEDAD_FUERA_DE_PATRIMONIO"
FALTAN_PARTES_PARA_FORMALIZAR = "FALTAN_PARTES_PARA_FORMALIZAR"
PRINCIPAL_REQUERIDO = "PRINCIPAL_REQUERIDO"
INQUILINO_NO_PUEDE_SER_YO = "INQUILINO_NO_PUEDE_SER_YO"
ROL_NO_ADMITIDO_PARA_YO = "ROL_NO_ADMITIDO_PARA_YO"
CONTRATO_SIN_INQUILINO = "CONTRATO_SIN_INQUILINO"
CONTRATO_SIN_ARRENDADOR = "CONTRATO_SIN_ARRENDADOR"
PRINCIPAL_DUPLICADO = "PRINCIPAL_DUPLICADO"
TRATAMIENTO_SOLAPADO = "TRATAMIENTO_SOLAPADO"
SERVICIO_YA_VINCULADO = "SERVICIO_YA_VINCULADO"
CLAUSULA_SOLAPADA = "CLAUSULA_SOLAPADA"
DESDE_IGUAL_A_VERSION_ABIERTA = "DESDE_IGUAL_A_VERSION_ABIERTA"
FECHA_FIN_ANTERIOR_A_VIGENCIA = "FECHA_FIN_ANTERIOR_A_VIGENCIA"
CONTRATO_NO_VIGENTE = "CONTRATO_NO_VIGENTE"
SUCESOR_SOLAPADO = "SUCESOR_SOLAPADO"
FECHA_INICIO_REQUERIDA = "FECHA_INICIO_REQUERIDA"
CLAUSULA_INCOMPLETA = "CLAUSULA_INCOMPLETA"
SERVICIO_NO_VINCULADO_A_PROPIEDAD = "SERVICIO_NO_VINCULADO_A_PROPIEDAD"
ACTOR_NO_ES_INQUILINO = "ACTOR_NO_ES_INQUILINO"
TRATAMIENTO_INCOMPATIBLE = "TRATAMIENTO_INCOMPATIBLE"
SERVICIO_DADO_DE_BAJA = "SERVICIO_DADO_DE_BAJA"
ROL_DESCONOCIDO = "ROL_DESCONOCIDO"
CLASIFICACION_CICLO = "CLASIFICACION_CICLO"
CLASIFICACION_NOMBRE_REPETIDO = "CLASIFICACION_NOMBRE_REPETIDO"
RETIRADA_NO_ADMITIDA = "RETIRADA_NO_ADMITIDA"
RENTA_NO_DISPONIBLE = "RENTA_NO_DISPONIBLE"
HABITACIONES_EN_USO = "HABITACIONES_EN_USO"
TERCERO_NO_ENCONTRADO = "TERCERO_NO_ENCONTRADO"

#: Motivos de OPERACION_NO_PERMITIDA_EN_ESTADO (409).
RENTA_PENDIENTE = "RENTA_PENDIENTE_DE_F06_04"
REGLA_SERVICIO_PENDIENTE = "REGLA_SERVICIO_PENDIENTE_DE_F06_04"

MENSAJE_RENTA_PENDIENTE = ("Este contrato tiene una renta registrada. Para terminarlo hay que cerrar también su "
                           "renta, y eso llegará con la parte de cobros. De momento no se puede terminar.")
MENSAJE_REGLA_SERVICIO = ("Este servicio tiene un pago previsto registrado. Para darlo de baja hay que cerrar ese "
                          "pago previsto, y eso llegará con la parte de cobros.")

#: codigo -> (HTTP, mensaje de usuario). Mensajes propios de la familia (los de titularidad o reparto no valen).
RECHAZOS: dict[str, tuple[int, str]] = {
    AGREGADO_NO_ENCONTRADO: (404, "No encontrado."),
    TERCERO_NO_ENCONTRADO: (404, "No encontrado."),
    VERSION_DESFASADA: (409, "Este dato ha cambiado desde que lo abriste. Vuelve a cargarlo."),
    IDENTIDAD_REUTILIZADA: (409, "Este registro ya existe con otros datos. No se ha guardado nada nuevo."),
    ENTRADA_INVALIDA: (422, "Revisa los datos."),
    TERCERO_NO_DISPONIBLE: (409, "Esa persona o empresa ya no está disponible. Elige otra: no se ha guardado nada."),
    PARTICIPANTE_DUPLICADO: (422, "La misma persona aparece dos veces en el mismo papel del contrato."),
    FECHA_ANTERIOR_INICIO: (422, "La fecha no puede ser anterior al inicio."),
    MOTIVO_AUSENTE: (422, "Indica el motivo del cambio."),
    CAMPO_INMUTABLE: (422, "Ese dato no se puede cambiar una vez creado el contrato."),
    NO_PERMITIDA_EN_ESTADO: (409, "No se puede hacer en el estado actual."),
    ACTOR_DESCONOCIDO: (409, "No se ha podido identificar tu perfil. No se ha guardado nada."),
    HABITACION_REQUERIDA: (422, "Indica el número de habitación."),
    HABITACION_NO_ADMITIDA: (422, "Solo un contrato de habitación lleva número de habitación."),
    HABITACION_FUERA_DE_FICHA: (422, "Ese número de habitación es mayor que las habitaciones de la ficha."),
    HABITACIONES_NO_INDICADAS: (422, "La ficha de la propiedad no indica cuántas habitaciones tiene. Complétala primero."),
    SOLAPE_CON_CONTRATO_FIRMADO: (409, "Esa habitación o vivienda ya está alquilada en esas fechas. "
                                       "Solo se puede guardar como borrador."),
    PROPIEDAD_FUERA_DE_PATRIMONIO: (422, "La propiedad ya había salido de tu patrimonio en esa fecha."),
    FALTAN_PARTES_PARA_FORMALIZAR: (422, "Para formalizar hace falta un propietario o gestor y un inquilino principal."),
    PRINCIPAL_REQUERIDO: (422, "Marca quién es el principal."),
    INQUILINO_NO_PUEDE_SER_YO: (422, "Tú no puedes ser inquilino de tu propio contrato."),
    ROL_NO_ADMITIDO_PARA_YO: (422, "Una agencia o un administrador tiene que ser otra persona o empresa, no tú."),
    CONTRATO_SIN_INQUILINO: (409, "Un contrato vigente necesita al menos un inquilino."),
    CONTRATO_SIN_ARRENDADOR: (409, "Un contrato firmado necesita al menos un propietario o gestor."),
    PRINCIPAL_DUPLICADO: (422, "Solo puede haber un principal en cada papel."),
    TRATAMIENTO_SOLAPADO: (409, "Ese servicio ya tiene un tratamiento en esas fechas en este contrato."),
    SERVICIO_YA_VINCULADO: (409, "Ese servicio ya está vinculado a la propiedad en esas fechas."),
    CLAUSULA_SOLAPADA: (409, "Ya hay una cláusula de revisión en esas fechas."),
    DESDE_IGUAL_A_VERSION_ABIERTA: (422, "Esa fecha coincide con la del dato actual: es una corrección, no un cambio."),
    FECHA_FIN_ANTERIOR_A_VIGENCIA: (422, "La fecha de fin no puede ser anterior al inicio de algo que sigue abierto."),
    CONTRATO_NO_VIGENTE: (409, "El contrato no está vigente."),
    SUCESOR_SOLAPADO: (422, "El nuevo contrato tiene que empezar después de que termine el anterior."),
    FECHA_INICIO_REQUERIDA: (422, "Indica la fecha de inicio."),
    CLAUSULA_INCOMPLETA: (422, "Revisa los datos de la cláusula de revisión."),
    SERVICIO_NO_VINCULADO_A_PROPIEDAD: (422, "Ese servicio no está vinculado a la propiedad del contrato en esa fecha."),
    ACTOR_NO_ES_INQUILINO: (422, "Solo se puede repercutir a un inquilino del contrato."),
    TRATAMIENTO_INCOMPATIBLE: (422, "Revisa el tratamiento del servicio: no puede estar incluido y repercutido a la vez, "
                                    "y el porcentaje tiene que ser coherente con el reparto."),
    SERVICIO_DADO_DE_BAJA: (409, "Ese servicio está dado de baja."),
    ROL_DESCONOCIDO: (422, "Ese papel no existe."),
    CLASIFICACION_CICLO: (422, "Una clasificación no puede colgar de una de sus descendientes."),
    CLASIFICACION_NOMBRE_REPETIDO: (409, "Ya hay una clasificación con ese nombre en ese nivel."),
    RETIRADA_NO_ADMITIDA: (409, "En esta versión se puede añadir y editar, pero no quitar."),
    RENTA_NO_DISPONIBLE: (422, "La renta y la fianza llegarán con la parte de cobros. De momento el contrato se crea sin ellas."),
    HABITACIONES_EN_USO: (409, "Hay contratos que usan esas habitaciones. Revisa el número de habitaciones."),
}

_MENSAJE_MOTIVO = {RENTA_PENDIENTE: MENSAJE_RENTA_PENDIENTE, REGLA_SERVICIO_PENDIENTE: MENSAJE_REGLA_SERVICIO}


def rechazo_http(codigo: str, detalle: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    """(status, cuerpo) de un rechazo. `motivo` sube al primer nivel cuando existe (contrato §1.4)."""
    status, mensaje = RECHAZOS[codigo]
    detalle = detalle or {}
    motivo = detalle.get("motivo") if codigo == NO_PERMITIDA_EN_ESTADO else None
    cuerpo: dict[str, Any] = {"codigo": codigo, "mensaje": _MENSAJE_MOTIVO.get(motivo, mensaje), "reintentable": False}
    if motivo is not None:
        cuerpo["motivo"] = motivo
    if detalle:
        cuerpo["detalle"] = detalle
    return status, cuerpo


# ---------------------------------------------------------------- traduccion fisica (§1.5)
#: constraint -> (SQLSTATE, codigo). SOLO lo que una constraint puede producir de verdad.
MAPA_FISICO: dict[str, tuple[str, str]] = {
    "ex_contrato_participantes__contrato_actor_rol": ("23P01", PARTICIPANTE_DUPLICADO),
    "ex_contrato_participantes__principal_por_rol": ("23P01", PRINCIPAL_DUPLICADO),
    "ex_contrato_servicios__contrato_servicio": ("23P01", TRATAMIENTO_SOLAPADO),
    "ex_propiedad_servicios__propiedad_servicio": ("23P01", SERVICIO_YA_VINCULADO),
    "ex_contrato_revision_renta_versiones__contrato": ("23P01", CLAUSULA_SOLAPADA),
    "ck_contratos__habitacion": ("23514", HABITACION_NO_ADMITIDA),
    "ck_contrato_servicios__repercusion_coherente": ("23514", TRATAMIENTO_INCOMPATIBLE),
    "ck_contrato_participantes__rol": ("23514", ROL_DESCONOCIDO),
    "ck_tercero_roles__rol_codigo": ("23514", ROL_DESCONOCIDO),
    "ck_contrato_servicios__renta_repercutible_excl": ("23514", TRATAMIENTO_INCOMPATIBLE),
    "ck_contrato_servicios__porcentaje": ("23514", TRATAMIENTO_INCOMPATIBLE),
    "ck_contrato_revision_renta_versiones__porcentaje_fijo_exigido": ("23514", CLAUSULA_INCOMPLETA),
    "ck_contrato_revision_renta_versiones__ninguna_sin_parametros": ("23514", CLAUSULA_INCOMPLETA),
    "ck_contratos__fin_prevista_no_anterior": ("23514", FECHA_ANTERIOR_INICIO),
    "ck_contratos__fin_real_no_anterior": ("23514", FECHA_ANTERIOR_INICIO),
    "uq_clasificaciones_tercero__owner_parent_nombre": ("23505", CLASIFICACION_NOMBRE_REPETIDO),
}
#: Funciones de trigger traducibles por su FIRMA (P0001). Fila final de §1.5 (C-31 CERRADO (decision de Moises del 19-11; contrato v1.2 §1.5, bbceffda…)).
FUNCIONES_TRIGGER: dict[str, str] = {"gapto.fn_check_jerarquia_aciclica()": CLASIFICACION_CICLO}
_PATRONES_TRIGGER = tuple(
    (re.compile(r"(?<![\w$.])" + re.escape(firma)), codigo) for firma, codigo in FUNCIONES_TRIGGER.items()
)


def traducir_fisico(exc: psycopg.Error) -> str | None:
    """Codigo de dominio de una violacion fisica del mapa; None = fuera del mapa (error generico, sin disfraz)."""
    diag = exc.diag
    previsto = MAPA_FISICO.get(diag.constraint_name or "")
    if previsto is not None and exc.sqlstate == previsto[0]:
        return previsto[1]
    if exc.sqlstate == "P0001" and diag.context:
        for patron, codigo in _PATRONES_TRIGGER:
            if patron.search(diag.context):
                return codigo
    return None
