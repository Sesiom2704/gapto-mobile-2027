# ============================================================
# GAPTO MOBILE 2027
# Fichero: coherencia_posicion.py
# Ruta: backend/app/services/coherencia_posicion.py
# Descripcion: Guarda compartida de coherencia posicion <-> efecto (F04-D036).
#
#   UNA SOLA IMPLEMENTACION PARA TRES CAMINOS. La invariante es la misma en
#   los tres y por eso no se escribe tres veces:
#
#     1) NACIMIENTO   un efecto se vincula al saldo de una posicion
#                     (`posiciones_service._crear_delta`);
#     2) MUTACION     OP-02 corrige la moneda de un hecho cuyos efectos ya
#                     alimentan una posicion (`hechos_service`);
#     3) ESTADO FINAL OP-21 corrige el agregado y debe terminar sin dejar
#                     ningun vinculo invalido (`correcciones_service`).
#
#   Una posicion tiene moneda propia y ESTABLE. Su saldo se deriva como
#   `saldo_apertura + SUM(deltas vinculados)`. Si un delta procede de un hecho
#   en otra moneda, esa suma es una suma nominal de monedas distintas: FX
#   implicito por la puerta de atras. No se convierte, no se estima y no se
#   elige moneda dominante. Se rechaza.
#
#   La naturaleza viaja en la misma guarda porque se rompe por el mismo sitio:
#   un `tipo_efecto` corregido deja el vinculo apuntando a un delta que la
#   posicion ya no suma, y el saldo cae a CERO CONOCIDO sin cobro, sin
#   condonacion y sin cierre. Un derecho no se extingue por una correccion de
#   captura.
#
#   POR QUE NO ES UN CONSTRAINT. La comprobacion es cross-table entre
#   `hechos_financieros`, `hecho_efectos`, `hecho_entidades` y
#   `derechos_obligaciones_financieras`. 0330 no dispone de constraint fisica
#   para ella y un trigger nuevo caeria sobre la topologia H<->M que ya sufre
#   el ciclo residual de D-171. La garantia es SRV, y por eso la lectura
#   conserva su propia deteccion fail-closed.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid

from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor
from app.repositories import posiciones_repository as repo_pos

# Naturaleza admitida por tipo de posicion. Replica el contrato de F04-04:
# un DERECHO_COBRO se alimenta de efectos `DERECHO_COBRO` y una
# OBLIGACION_PAGO de efectos `DEUDA`.
EFECTO_ADMITIDO: dict[str, str] = {
    "DERECHO_COBRO": "DERECHO_COBRO",
    "OBLIGACION_PAGO": "DEUDA",
}


def exigir_moneda_de_vinculo(
    sesion: SesionMotor,
    *,
    hecho_id: uuid.UUID,
    moneda_posicion: str | None,
    entidad_id: uuid.UUID,
) -> None:
    """Camino 1. El efecto que nace ya vinculado debe ser de la moneda de la posicion."""
    moneda_hecho = repo_pos.moneda_de_hecho(sesion, hecho_id)
    if moneda_hecho is None or moneda_posicion is None:
        # Sin uno de los dos datos no se afirma compatibilidad: el llamante
        # que no puede demostrarla no puede escribir el vinculo.
        raise ErrorMotor(
            CodigoError.MONEDA_POSICION_INCOMPATIBLE,
            "No puede demostrarse que el efecto y la posicion compartan "
            "moneda.",
        )
    if moneda_hecho != moneda_posicion:
        raise ErrorMotor(
            CodigoError.MONEDA_POSICION_INCOMPATIBLE,
            f"El hecho esta en {moneda_hecho} y la posicion {entidad_id} en "
            f"{moneda_posicion}. Un efecto de otra moneda no puede entrar en "
            "su saldo: no existe conversion implicita.",
        )


def exigir_moneda_corregible(
    sesion: SesionMotor, *, hecho_id: uuid.UUID, moneda_candidata: str
) -> None:
    """Camino 2. OP-02 no puede dejar el agregado incoherente.

    Falla ANTES de mutar. No desvincula, no convierte y no arrastra la
    correccion a las posiciones alcanzadas: alterar un vinculo correcto para
    poder cambiar la moneda destruiria significado historico. Si de verdad
    hay que corregir varias piezas a la vez, eso ya no es una correccion
    escalar de captura.
    """
    incompatible = repo_pos.posicion_incompatible_por_moneda(
        sesion, hecho_id, moneda_candidata
    )
    if incompatible is not None:
        entidad_id, moneda_posicion = incompatible
        raise ErrorMotor(
            CodigoError.MONEDA_POSICION_INCOMPATIBLE,
            f"Corregir la moneda a {moneda_candidata} dejaria el efecto "
            f"vinculado a la posicion {entidad_id}, que esta en "
            f"{moneda_posicion}. La correccion escalar no puede dejar el "
            "agregado incoherente.",
        )


def exigir_vinculos_coherentes(sesion: SesionMotor, *, hecho_id: uuid.UUID) -> None:
    """Camino 3. Estado FINAL del agregado tras una correccion agregada.

    Se evalua al final y no paso a paso, igual que la guarda de D-187: una
    correccion puede pasar por estados intermedios que solo serian invalidos
    si se confirmasen.
    """
    incoherente = repo_pos.vinculo_incoherente_del_hecho(sesion, hecho_id)
    if incoherente is None:
        return
    _, entidad_id, tipo_posicion, tipo_efecto, moneda_hecho, moneda_posicion = (
        incoherente
    )
    if moneda_hecho != moneda_posicion:
        raise ErrorMotor(
            CodigoError.MONEDA_POSICION_INCOMPATIBLE,
            f"La correccion dejaria un efecto en {moneda_hecho} dentro del "
            f"saldo de la posicion {entidad_id}, que esta en "
            f"{moneda_posicion}.",
        )
    raise ErrorMotor(
        CodigoError.NATURALEZA_INCOMPATIBLE,
        f"La correccion dejaria la posicion {entidad_id} de tipo "
        f"{tipo_posicion} alimentada por un efecto {tipo_efecto}. Un derecho "
        "o una obligacion no se extinguen cambiando la naturaleza de su "
        "efecto: si la realidad fue otra, la via es la operacion de posicion "
        "que corresponda.",
    )


def exigir_saldo_calculable(
    sesion: SesionMotor, *, entidad_id: uuid.UUID, tipo_efecto: str
) -> None:
    """Defensa en profundidad de la LECTURA.

    Los write-paths ya no pueden producir este estado, pero la ausencia
    actual de datos incoherentes no es una garantia: un import, una
    correccion futura o un writer nuevo podrian introducirlo. Ante un delta
    de otra moneda la lectura FALLA CERRADA. Nunca ignora la fila, nunca la
    suma nominalmente y nunca devuelve un saldo parcial como si estuviese
    completo.
    """
    intruso = repo_pos.delta_de_otra_moneda(sesion, entidad_id, tipo_efecto)
    if intruso is None:
        return
    efecto_id, moneda_hecho, moneda_posicion = intruso
    raise ErrorMotor(
        CodigoError.INVARIANTE_MONETARIA_POSICION_VIOLADA,
        f"El saldo de la posicion {entidad_id} ({moneda_posicion}) no es "
        f"calculable: el efecto {efecto_id} procede de un hecho en "
        f"{moneda_hecho}. El estado guardado es invalido y no se resuelve "
        "reintentando.",
    )
