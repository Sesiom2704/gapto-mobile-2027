# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_preferencias.py
# Ruta: backend/app/api/dto_preferencias.py
# Descripcion: Wire de las preferencias de registro (F05-02 B1, F05-D026).
#   API DE INTEGRACION F05, rutas /v1 internas y provisionales, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   - Alta y edicion aceptan tercero_id y entidad_id (default null) SOLO para
#     poder rechazarlos con PREFERENCIA_DIMENSION_DIFERIDA (AJ-D026-12), y
#     `prioridad` (default 100) para rechazar otro valor con
#     PREFERENCIA_PRIORIDAD_NO_ADMITIDA (AJ-D026-04). El dominio decide; el
#     DTO solo valida la forma (422 ENTRADA_INVALIDA).
#   - La edicion sustituye el contenido completo: los campos ausentes valen
#     null (comodin o «no propone»).
#   - `PropuestaRegistro`: por campo, {valor, origen: {capa,
#     preferencia_id}} o null («sin propuesta»).
#
#   v0.1.1 (F05-02 B1-C, AJ-B1-03): solo documentacion de `EditarPreferencia`
#   (E05: reemplazo completo; el cliente envia siempre el estado completo).
#
#   v0.2.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E2/E3): `tercero_id` es
#   operativo (el dominio lo valida); `entidad_id` sigue aceptandose solo para
#   rechazarlo con PREFERENCIA_DIMENSION_DIFERIDA. `ListaPreferencias` anade
#   `tipos` (TiposRegistro: ids de GASTO e INGRESO), campo aditivo.
#   v0.3.0 (F05-03/F05-04 J2 §1.9): PreferenciaLista anade
#   `tercero_disponible` (aviso de Ajustes, A7).
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Contenido(_Estricto):
    tipo_hecho_id: uuid.UUID | None = None
    categoria_id: uuid.UUID | None = None
    tercero_id: uuid.UUID | None = None
    entidad_id: uuid.UUID | None = None
    cuenta_default_id: uuid.UUID | None = None
    presupuestable_default: bool | None = None
    prioridad: int = 100


class AltaPreferencia(_Contenido):
    id: uuid.UUID


class _ConVersion(_Estricto):
    row_version: int = Field(ge=1)


class EditarPreferencia(_Contenido):
    """Editar = REEMPLAZO COMPLETO del contenido (E05). Un campo ausente vale
    NULL (comodin en las claves de contexto; «no propone» en los valores
    propuestos). El cliente envia SIEMPRE el
    estado completo de la preferencia, nunca un parche parcial."""

    row_version: int = Field(ge=1)


class DesactivarPreferencia(_ConVersion):
    pass


class ReactivarPreferencia(_ConVersion):
    pass


class PreferenciaNodo(_Estricto):
    id: uuid.UUID
    tipo_hecho_id: uuid.UUID | None
    categoria_id: uuid.UUID | None
    tercero_id: uuid.UUID | None
    entidad_id: uuid.UUID | None
    cuenta_default_id: uuid.UUID | None
    presupuestable_default: bool | None
    prioridad: int
    enabled: bool
    row_version: int


class PreferenciaLista(PreferenciaNodo):
    cuenta_disponible_hoy: bool | None
    tercero_disponible: bool | None


class TiposRegistro(_Estricto):
    GASTO: uuid.UUID
    INGRESO: uuid.UUID


class ListaPreferencias(_Estricto):
    preferencias: list[PreferenciaLista]
    tipos: TiposRegistro


class ResultadoComandoPreferencia(_Estricto):
    preferencia: PreferenciaNodo
    idempotente: bool
    modificadas: list[uuid.UUID]


class OrigenPropuesta(_Estricto):
    capa: Literal["PREFERENCIA", "DEFAULT_GENERAL"]
    preferencia_id: uuid.UUID | None


class CuentaPropuesta(_Estricto):
    valor: uuid.UUID
    origen: OrigenPropuesta


class PresupuestablePropuesto(_Estricto):
    valor: bool
    origen: OrigenPropuesta


class PropuestaRegistro(_Estricto):
    cuenta: CuentaPropuesta | None
    presupuestable: PresupuestablePropuesto | None
