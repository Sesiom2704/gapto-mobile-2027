# ============================================================
# GAPTO MOBILE 2027
# Fichero: contexto.py
# Ruta: backend/app/core/contexto.py
# Descripcion: Contexto de ejecucion de una operacion del motor: tenant, actor
#   y request de correlacion.
#
#   El owner NUNCA llega como parametro de negocio desde el cliente: llega en
#   este contexto, el backend lo fija dentro de la transaccion como GUC
#   `gapto.owner_user_id` y PostgreSQL lo impone mediante RLS + FORCE RLS
#   (migration 0120). Un DTO de caso de uso que aceptase `owner_user_id`
#   reintroduciria un parametro falsificable.
#
#   `request_id` es CORRELACION. No es clave universal de idempotencia. Se usa
#   como evidencia acotada de que un reintento pertenece a la misma operacion,
#   nunca como permiso para dar por buena una escritura no demostrada.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from app.core.errores import CodigoError, ErrorMotor

ActorTipo = Literal["USUARIO", "SISTEMA"]

ACTOR_USUARIO: ActorTipo = "USUARIO"
ACTOR_SISTEMA: ActorTipo = "SISTEMA"


@dataclass(frozen=True, slots=True)
class ContextoOperacion:
    """Tenant + actor + request de una operacion del motor.

    La coherencia actor_tipo/actor_user_id se valida aqui Y en
    `gapto.fn_registrar_auditoria`. La duplicacion es deliberada: en Python
    produce un error legible antes de abrir transaccion; en PostgreSQL es la
    que realmente garantiza la invariante aunque se escriba por otra via.
    """

    owner_user_id: uuid.UUID
    actor_tipo: ActorTipo
    request_id: uuid.UUID
    actor_user_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.owner_user_id is None:
            raise ErrorMotor(
                CodigoError.TENANT_AUSENTE,
                "El contexto de operacion exige owner_user_id.",
            )
        if self.request_id is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "El contexto de operacion exige request_id de correlacion.",
            )
        if self.actor_tipo not in ("USUARIO", "SISTEMA"):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "actor_tipo debe ser USUARIO o SISTEMA.",
            )
        if self.actor_tipo == ACTOR_USUARIO and self.actor_user_id is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "actor_tipo=USUARIO exige actor_user_id; no se inventa un actor.",
            )
        if self.actor_tipo == ACTOR_SISTEMA and self.actor_user_id is not None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "actor_tipo=SISTEMA no admite actor_user_id.",
            )

    @classmethod
    def de_usuario(
        cls,
        owner_user_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None = None,
        request_id: uuid.UUID | None = None,
    ) -> "ContextoOperacion":
        """Contexto de un usuario que opera sobre su propio tenant.

        `actor_user_id` se omite solo cuando coincide con el owner: es el caso
        mono-usuario vigente, donde el actor ES el titular. Cuando un actor
        distinto opere sobre el tenant debera pasarse explicitamente.
        """
        return cls(
            owner_user_id=owner_user_id,
            actor_tipo=ACTOR_USUARIO,
            actor_user_id=actor_user_id if actor_user_id is not None else owner_user_id,
            request_id=request_id if request_id is not None else uuid.uuid4(),
        )

    @classmethod
    def de_sistema(
        cls,
        owner_user_id: uuid.UUID,
        *,
        request_id: uuid.UUID | None = None,
    ) -> "ContextoOperacion":
        """Contexto de un proceso interno (importacion, tareas programadas)."""
        return cls(
            owner_user_id=owner_user_id,
            actor_tipo=ACTOR_SISTEMA,
            actor_user_id=None,
            request_id=request_id if request_id is not None else uuid.uuid4(),
        )
