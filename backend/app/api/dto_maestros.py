# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_maestros.py
# Ruta: backend/app/api/dto_maestros.py
# Descripcion: Wire de los maestros minimos del registro: terceros y
#   contextos (F05-04 J2 §1.3/§1.4/§1.9; F05 §46.3 A5/A6/A7). API DE
#   INTEGRACION F05, rutas /v1 internas, PENDIENTE DE CONSOLIDACION F10.
#   - Altas con UUID de cliente (R5); ediciones = reemplazo COMPLETO con
#     row_version; desactivar/reactivar con row_version.
#   - El DTO solo valida la forma (422); el dominio decide (409/404).
#   - `extra="forbid"`: owner u otros campos colados -> 422.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.3)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NaturalezaTercero = Literal["PERSONA", "EMPRESA", "ORGANISMO", "OTRO"]
TipoContexto = Literal["VIAJE", "REFORMA", "EVENTO", "SOCIAL", "PROYECTO", "OTRO"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _ConVersion(_Estricto):
    row_version: int = Field(ge=1)


# ------------------------------------------------------------------ terceros
class AltaTercero(_Estricto):
    id: uuid.UUID
    nombre: str
    naturaleza: NaturalezaTercero | None = None  # None = «No lo sé»


class EditarTercero(_ConVersion):
    nombre: str
    naturaleza: NaturalezaTercero | None = None


class EstadoTercero(_ConVersion):
    pass


class TerceroNodo(_Estricto):
    id: uuid.UUID
    nombre: str
    naturaleza: str | None
    enabled: bool
    row_version: int


class TerceroLista(TerceroNodo):
    usos: int


class ListaTerceros(_Estricto):
    terceros: list[TerceroLista]


class ResultadoComandoTercero(_Estricto):
    tercero: TerceroNodo
    idempotente: bool
    modificadas: list[uuid.UUID]


# ------------------------------------------------------------------ contextos
class AltaContexto(_Estricto):
    id: uuid.UUID
    nombre: str
    tipo_contexto: TipoContexto
    fecha_inicio: dt.date | None = None
    fecha_fin: dt.date | None = None


class EditarContexto(_ConVersion):
    nombre: str
    tipo_contexto: TipoContexto
    fecha_inicio: dt.date | None = None
    fecha_fin: dt.date | None = None


class EstadoContexto(_ConVersion):
    pass


class ContextoNodo(_Estricto):
    id: uuid.UUID
    nombre: str
    tipo_contexto: str
    fecha_inicio: dt.date | None
    fecha_fin: dt.date | None
    enabled: bool
    row_version: int


class ListaContextos(_Estricto):
    contextos: list[ContextoNodo]


class ResultadoComandoContexto(_Estricto):
    contexto: ContextoNodo
    idempotente: bool
    modificadas: list[uuid.UUID]
