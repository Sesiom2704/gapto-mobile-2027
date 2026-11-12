# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_b3.py
# Ruta: backend/app/patrimonio/dto_b3.py
# Descripcion: DTO estrictos de B3 (extra=forbid; R1 v0.8 §1.1 y Parte III; v0.9 §III.1 y §III.3; v0.9.5
#   §III.1bis 8, 8bis y 8ter):
#   - GastoPropiedad (C-MEJ-01, POST /v1/intenciones/gasto-propiedad): clase MEJORA | REPARACION |
#     GASTO_CORRIENTE sin valor por defecto (ausente -> CLASE_GASTO_PROPIEDAD_AUSENTE en la capa, no 422 de tipo);
#     `deuda` con el valor EXPLICITO `me_debe` por cada parte de cotitular (INV-04: el servidor nunca infiere);
#     `aportacion_indicada` (MANUAL solo con cuenta compartida, 8ter) y `derechos_confirmados` (8bis).
#     `servicio_id` y `contexto_id` NO se admiten (extra=forbid): no hay writer de SERVICIO vinculado a una
#     propiedad ni contrato construible de DIAG-5 en el tren 1 (duda declarada en el handoff de B3).
#   - MejoraHistorica (C-MEJ-02, POST /v1/propiedades/{id}/mejoras-historicas): sin pago; `deuda` opcional y
#     cualquier SI se rechaza en la capa (O9.20).
#   - CorregirClase (C-MEJ-03): campos del §III.3 de la v0.9; `motivo` vacio -> MOTIVO_AUSENTE en la capa;
#     `comparacion_vista` como texto (§III.3.5).
#   Importes EUR > 0 con 2 decimales; porcentajes con 4; nunca float en las respuestas.
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.patrimonio.dto import Importe, Parte

Clase = Literal["MEJORA", "REPARACION", "GASTO_CORRIENTE"]
ModoB3 = Literal["SEGUN_TITULARIDAD_ACEPTADA", "MANUAL", "NO_LO_SE"]
CriterioB3 = Literal["TITULARIDAD_EN_FECHA_HECHO"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PropuestaVistaB3(_Estricto):
    criterio: CriterioB3
    fecha_referencia: dt.date
    partes: list[Parte] = Field(min_length=1, max_length=50)


class AtribucionB3(_Estricto):
    modo: ModoB3
    partes: list[Parte] | None = Field(default=None, max_length=50)
    propuesta_vista: PropuestaVistaB3 | None = None


class DeudaParte(_Estricto):
    actor_id: uuid.UUID
    me_debe: Literal["SI", "NO"]


class DerechoConfirmado(_Estricto):
    actor_id: uuid.UUID
    importe: Importe


class GastoPropiedad(_Estricto):
    intencion_id: uuid.UUID
    propiedad_id: uuid.UUID
    clase: Clase | None = None
    importe: Importe
    fecha_hecho: dt.date
    cuenta_id: uuid.UUID
    nota: str | None = Field(default=None, max_length=200)
    categoria_id: uuid.UUID | None = None
    presupuestable: bool | None = None
    atribucion: AtribucionB3
    deuda: list[DeudaParte] = Field(default_factory=list, max_length=50)
    aportacion_indicada: Literal["MANUAL"] | None = None
    derechos_confirmados: list[DerechoConfirmado] = Field(default_factory=list, max_length=50)


class MejoraHistorica(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    descripcion: str = Field(min_length=1, max_length=200)
    importe: Importe
    fecha: dt.date
    atribucion: AtribucionB3
    deuda: list[DeudaParte] = Field(default_factory=list, max_length=50)


class ComparacionVista(_Estricto):
    mes: str = Field(min_length=7, max_length=7)
    resultado_mes_delta_antes: str
    resultado_mes_delta_despues: str
    mejoras_antes: str
    mejoras_despues: str
    presupuesto_delta_despues: str


class CorregirClase(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    clase_nueva: Clase
    motivo: str | None = Field(default=None, max_length=500)
    categoria_id: uuid.UUID | None = None
    presupuestable: bool | None = None
    comparacion_vista: ComparacionVista
