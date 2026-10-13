# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_capacidades.py
# Ruta: backend/app/api/dto_capacidades.py
# Descripcion: Contratos HTTP de capacidades de cuenta (F05-06 M4 §2.2/§2.4;
#   F09 §12.105 CAP). API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#   Ninguna respuesta lleva el tipo ni la naturaleza de la cuenta, ni
#   propuestas o valores por defecto de capacidades (D-CAP-04, H2).
# Version: 0.1.0 (F05-06 M4 F1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CambioCapacidad(_Estricto):
    """Activar o desactivar UNA capacidad; `row_version` es el de la cuenta (PD-1)."""

    row_version: int = Field(ge=1)


class CapacidadNodo(_Estricto):
    codigo: str
    etiqueta: str
    efecto: str
    permitida: bool
    editable: bool


class CuentaCapacidades(_Estricto):
    cuenta_id: uuid.UUID
    nombre: str
    estado: Literal["ACTIVA", "DESHABILITADA", "CERRADA"]
    row_version: int
    origen_v3: bool
    sin_configurar: bool
    capacidades: list[CapacidadNodo]
    otras: list[CapacidadNodo]


class ListaCuentasCapacidades(_Estricto):
    cuentas: list[CuentaCapacidades]
    sin_configurar: int


class SinConfigurar(_Estricto):
    sin_configurar: int


class PlantillaAfectada(_Estricto):
    plantilla_id: uuid.UUID
    nombre: str
    enabled: bool


class PreferenciaAfectada(_Estricto):
    preferencia_id: uuid.UUID
    enabled: bool
    categoria_id: uuid.UUID | None
    categoria_nombre: str | None
    tercero_id: uuid.UUID | None
    tercero_nombre: str | None


class ImpactoDesactivar(_Estricto):
    plantillas: list[PlantillaAfectada]
    preferencias: list[PreferenciaAfectada]


class EntradaHistorial(_Estricto):
    cuando: dt.datetime
    accion: Literal["ACTIVAR", "DESACTIVAR"]
    capacidad: str
    etiqueta: str
    actor_tipo: Literal["USUARIO", "SISTEMA"]
    actor_es_owner: bool


class HistorialCapacidades(_Estricto):
    entradas: list[EntradaHistorial]


class ResultadoComandoCapacidad(_Estricto):
    cuenta: CuentaCapacidades
    idempotente: bool
