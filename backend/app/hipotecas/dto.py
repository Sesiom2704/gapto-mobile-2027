# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto.py
# Ruta: backend/app/hipotecas/dto.py
# Descripcion: DTO estrictos de la hipoteca (F06-01H; contrato v0.4 §3.1; extra=forbid como patrimonio/dto.py).
#   CuadroPrevio (W-HIP-00): capital, tasa_anual, numero_cuotas, primera_cuota opcional y, para poder responder
#   SISTEMA_NO_SOPORTADO / PERIODICIDAD_NO_SOPORTADA con su motivo (contrato §3.1), sistema y periodicidad como
#   texto libre con FRANCES / MENSUAL por defecto. Los rangos (capital > 0 con 2 decimales, tasa 0..30 con
#   hasta 6 decimales, 1..600 cuotas) los valida la calculadora: fuera de rango -> 422 CONDICIONES_INCOMPLETAS
#   con motivo VALORES_FUERA_DE_RANGO. Un campo que falta o con tipo invalido es 422 ENTRADA_INVALIDA (patron
#   vigente de la API). Nunca float: los importes viajan como texto o numero decimal exacto.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 4)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.hipotecas import calculadora as calc


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CuadroPrevio(_Estricto):
    capital: decimal.Decimal
    tasa_anual: decimal.Decimal
    numero_cuotas: StrictInt
    primera_cuota: dt.date | None = None
    sistema: str = Field(default=calc.SISTEMA, max_length=30)
    periodicidad: str = Field(default=calc.PERIODICIDAD, max_length=20)
