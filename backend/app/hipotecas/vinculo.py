# ============================================================
# GAPTO MOBILE 2027
# Fichero: vinculo.py
# Ruta: backend/app/hipotecas/vinculo.py
# Descripcion: Writer propio del vinculo AFECTA_A de NIVEL EFECTO entre un efecto DEUDA y una financiacion
#   (F06-01H; contrato v0.4 §5.1, D12; INV-HIP-13). La ruta generica de contexto (contexto_service) NO cambia y
#   sigue rechazando ese vinculo con OWNERSHIP_F07 (O-H8). Aqui se escribe sobre el writer contractual de
#   hecho_entidades (contexto_repository.insertar_entidad) solo con una CAPACIDAD explicita: un objeto privado
#   del modulo que unicamente construyen W-HIP-01 (alta) y W-HIP-02 (pago). Ningun DTO puede pedirla: no es un
#   tipo serializable ni tiene constructor publico (el token de modulo es privado y se comprueba por identidad).
#   El efecto tiene que ser DEUDA del propio hecho y la entidad una FINANCIACION visible del owner.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 5)
# ============================================================

from __future__ import annotations

import uuid

from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor
from app.repositories import contexto_repository as repo_ctx

_TOKEN = object()


class Capacidad:
    """Capacidad privada de escribir UN vinculo de nivel efecto con la financiacion (id determinista)."""

    __slots__ = ("_token", "operacion", "registro_id")

    def __init__(self, token: object, operacion: str, registro_id: uuid.UUID) -> None:
        if token is not _TOKEN:
            raise ErrorMotor(CodigoError.OWNERSHIP_F07, "El vinculo de financiacion de nivel efecto es de F06-01H.")
        self._token, self.operacion, self.registro_id = token, operacion, registro_id


def capacidad_alta(registro_id: uuid.UUID) -> Capacidad:
    return Capacidad(_TOKEN, "W-HIP-01", registro_id)


def capacidad_pago(registro_id: uuid.UUID) -> Capacidad:
    return Capacidad(_TOKEN, "W-HIP-02", registro_id)


def escribir(sesion: SesionMotor, capacidad: Capacidad, *, hecho_id: uuid.UUID, efecto_id: uuid.UUID,
             financiacion_id: uuid.UUID) -> None:
    if not isinstance(capacidad, Capacidad) or capacidad._token is not _TOKEN:
        raise ErrorMotor(CodigoError.OWNERSHIP_F07, "El vinculo de financiacion de nivel efecto es de F06-01H.")
    efecto = sesion.uno("SELECT tipo_efecto FROM gapto.hecho_efectos WHERE id = %s AND hecho_id = %s",
                        (efecto_id, hecho_id))
    entidad = sesion.uno("SELECT tipo_entidad FROM gapto.entidades WHERE id = %s", (financiacion_id,))
    if efecto is None or efecto[0] != "DEUDA" or entidad is None or entidad[0] != "FINANCIACION":
        raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "Vinculo de financiacion fuera de su contrato.")
    if repo_ctx.insertar_entidad(sesion, registro_id=capacidad.registro_id,
                                 owner_user_id=uuid.UUID(sesion.uno(
                                     "SELECT current_setting('gapto.owner_user_id')")[0]),
                                 hecho_id=hecho_id, efecto_id=efecto_id, entidad_id=financiacion_id,
                                 tipo_relacion="AFECTA_A", principal=False) is None:
        raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION, "Vinculo ya existente.")
