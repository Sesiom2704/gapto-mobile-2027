# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_f05_05.py
# Ruta: backend/app/api/dto_f05_05.py
# Descripcion: Wire de F05-05 (F05 §49.4 A1-A10): senales, afinidades,
#   Actividad v0 y read models de Inicio. API DE INTEGRACION F05, PENDIENTE
#   DE CONSOLIDACION F10.
#   - Entradas con `extra="forbid"`: owner u otros campos colados -> 422.
#   - Las lecturas exponen `nota` (M5-08, A10): es la columna `concepto` del
#     hecho; el wire de ESCRITURA del gasto conserva `concepto` hasta F10.
#   - Importes como texto decimal con 2 decimales (sin floats).
# Version: 0.1.0 (F05-05 K2 §1.2-§1.6)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

MotivoSenal = Literal["AFINIDAD", "FRECUENTE_TERCERO", "FRECUENTE_TIPO", "RECIENTE"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ------------------------------------------------------------------ senales (§1.2)
class CandidataCategoria(_Estricto):
    categoria_id: uuid.UUID
    nombre: str
    ruta: str
    motivo: MotivoSenal
    fuente: Literal["AFINIDAD", "HISTORIAL"]
    usos: int
    ultimo_uso: dt.date | None


class SenalesCategorias(_Estricto):
    tipo: Literal["GASTO", "INGRESO"]
    fecha: dt.date
    tercero_id: uuid.UUID | None
    candidatas: list[CandidataCategoria]


class TerceroReciente(_Estricto):
    tercero_id: uuid.UUID
    nombre: str
    naturaleza: str | None
    usos: int
    ultimo_uso: dt.date
    motivo: Literal["RECIENTE", "FRECUENTE_TIPO"]


class SenalesTerceros(_Estricto):
    tipo: Literal["GASTO", "INGRESO"]
    fecha: dt.date
    terceros: list[TerceroReciente]


# ------------------------------------------------------------------ afinidades (§1.3)
class AltaAfinidad(_Estricto):
    id: uuid.UUID  # UUID del cliente: identidad idempotente
    tercero_id: uuid.UUID
    categoria_id: uuid.UUID


class AfinidadNodo(_Estricto):
    id: uuid.UUID
    tercero_id: uuid.UUID
    categoria_id: uuid.UUID


class ResultadoComandoAfinidad(_Estricto):
    afinidad: AfinidadNodo | None
    idempotente: bool
    aviso: Literal["AFINIDAD_YA_EXISTE"] | None = None


class AfinidadGuardada(_Estricto):
    id: uuid.UUID
    categoria_id: uuid.UUID
    nombre: str
    ruta: str
    disponible: bool


class CategoriaHistorial(_Estricto):
    categoria_id: uuid.UUID
    nombre: str
    ruta: str
    usos: int


class DetalleAfinidades(_Estricto):
    tercero_id: uuid.UUID
    tipo: Literal["GASTO", "INGRESO"]
    guardadas: list[AfinidadGuardada]
    segun_historial: list[CategoriaHistorial]
    total_registros: int
