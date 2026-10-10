# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_plantillas.py
# Ruta: backend/app/api/dto_plantillas.py
# Descripcion: Wire de plantillas de registro, acciones rapidas y propuesta
#   del registro con la capa plantilla (F05-03 J2 §1.6/§1.9; F05 §45.3
#   A1/A2/A3/A6, §46.3 A11). API DE INTEGRACION F05, rutas /v1 internas,
#   PENDIENTE DE CONSOLIDACION F10.
#   - Alta y edicion = contenido COMPLETO (la edicion incluye el renombrado);
#     sin concepto, nota, importe, atribucion ni magnitudes (no hay campos:
#     `extra="forbid"` los rechaza con 422).
#   - La propuesta devuelve, por campo, {valor, origen {capa, plantilla_id,
#     preferencia_id}} o null, y los avisos estructurados {campo, motivo}.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.6)
# ============================================================

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _ContenidoPlantilla(_Estricto):
    nombre: str
    tipo_hecho_id: uuid.UUID
    categoria_id: uuid.UUID | None = None
    tercero_id: uuid.UUID | None = None
    entidad_id: uuid.UUID | None = None
    cuenta_default_id: uuid.UUID | None = None
    presupuestable_default: bool | None = None


class AltaPlantilla(_ContenidoPlantilla):
    id: uuid.UUID


class EditarPlantilla(_ContenidoPlantilla):
    row_version: int = Field(ge=1)


class EstadoPlantilla(_Estricto):
    row_version: int = Field(ge=1)


class Aviso(_Estricto):
    campo: str
    motivo: str


class PlantillaNodo(_Estricto):
    id: uuid.UUID
    nombre: str
    tipo_hecho_id: uuid.UUID
    categoria_id: uuid.UUID | None
    tercero_id: uuid.UUID | None
    entidad_id: uuid.UUID | None
    cuenta_default_id: uuid.UUID | None
    presupuestable_default: bool | None
    enabled: bool
    row_version: int


class PlantillaLista(PlantillaNodo):
    tipo: str | None
    avisos: list[Aviso]


class AccionNodo(_Estricto):
    id: uuid.UUID
    nombre: str
    plantilla_registro_id: uuid.UUID
    orden: int
    icono_key: str | None
    enabled: bool
    row_version: int


class ListaPlantillas(_Estricto):
    plantillas: list[PlantillaLista]
    acciones: list[AccionNodo]


class ResultadoComandoPlantilla(_Estricto):
    plantilla: PlantillaNodo
    idempotente: bool
    modificadas: list[uuid.UUID]


class AltaAccion(_Estricto):
    id: uuid.UUID
    plantilla_registro_id: uuid.UUID
    nombre: str
    icono_key: str | None = None


class EditarAccion(_Estricto):
    row_version: int = Field(ge=1)
    nombre: str
    icono_key: str | None = None


class EstadoAccion(_Estricto):
    row_version: int = Field(ge=1)


class AccionVersion(_Estricto):
    id: uuid.UUID
    row_version: int = Field(ge=1)


class ReordenarAcciones(_Estricto):
    acciones: list[AccionVersion] = Field(min_length=1)


class ResultadoComandoAccion(_Estricto):
    accion: AccionNodo
    idempotente: bool
    modificadas: list[uuid.UUID]


class ResultadoReordenarAcciones(_Estricto):
    acciones: list[AccionNodo]
    idempotente: bool
    modificadas: list[uuid.UUID]


# ------------------------------------------------------------------ propuesta del registro
class OrigenCampo(_Estricto):
    capa: Literal["PLANTILLA", "PREFERENCIA", "DEFAULT_GENERAL"]
    plantilla_id: uuid.UUID | None
    preferencia_id: uuid.UUID | None


class CampoUuid(_Estricto):
    valor: uuid.UUID
    origen: OrigenCampo


class CampoBool(_Estricto):
    valor: bool
    origen: OrigenCampo


class CamposPropuesta(_Estricto):
    categoria: CampoUuid | None
    tercero: CampoUuid | None
    contexto: CampoUuid | None
    cuenta: CampoUuid | None
    presupuestable: CampoBool | None


class PropuestaRegistroTipo(_Estricto):
    tipo: Literal["GASTO", "INGRESO"]
    campos: CamposPropuesta
    avisos: list[Aviso]
