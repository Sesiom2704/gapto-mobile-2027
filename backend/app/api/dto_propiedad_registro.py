# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto_propiedad_registro.py
# Ruta: backend/app/api/dto_propiedad_registro.py
# Descripcion: F06 T2-F06 CAT-VIV · bloque OPCIONAL `propiedad` de los registros de gasto de F05 (L-04; Q-CV-02
#   variante (a), Q-CV-05, AJ-T2-07; mandato CAT-VIV v1.1 §2.4). API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   BloquePropiedadVs01 (POST /v1/intenciones/gasto-pagado): la forma de C-MEJ-01 v2 de PAG para lo que B3 y PAG
#     anaden al gasto: atribucion por la titularidad de la PROPIEDAD en la fecha del hecho (AtribucionB3:
#     SEGUN_TITULARIDAD_ACEPTADA con propuesta_vista, MANUAL o NO_LO_SE; nunca 100 % mio por defecto) y quien
#     pago y quien debe (pagos[], saldos[] y posiciones_confirmadas[], componedor patrimonio/pagos.py de PAG, que
#     no se modifica). `clase` GASTO_CORRIENTE (por defecto) o REPARACION: NO se persiste (B3 v0.8 AJ-11) y nunca
#     MEJORA desde el registro (Q-CV-04).
#   BloquePropiedadM3 (gasto-compartido y gasto-reembolsable): solo la propiedad y la propuesta vista de la
#     titularidad en la fecha. L-04b NO firmada: M3 conserva su modelo de un solo pagador, sus reglas de reparto y
#     posiciones; la titularidad PROPONE los participantes y partes (en el cliente) y el servidor solo exige que la
#     propuesta vista siga vigente ([PROPUESTA] del §2.4.2, aceptada en el literal). Sin el componedor de PAG.
#   Ninguno retira campos ni validaciones de VS-01 o M3 (Q-CV-05).
# Version: 0.1.0 (F06 T2-F06 CAT-VIV N1)
# ============================================================

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.patrimonio.dto_b3 import AtribucionB3, PagoGasto, PosicionConfirmada, PropuestaVistaB3, SaldoCotitular

ClaseRegistro = Literal["GASTO_CORRIENTE", "REPARACION"]


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BloquePropiedadVs01(_Estricto):
    propiedad_id: uuid.UUID
    clase: ClaseRegistro = "GASTO_CORRIENTE"
    atribucion: AtribucionB3
    pagos: list[PagoGasto] = Field(min_length=1, max_length=50)
    saldos: list[SaldoCotitular] = Field(default_factory=list, max_length=50)
    posiciones_confirmadas: list[PosicionConfirmada] = Field(default_factory=list, max_length=50)


class BloquePropiedadM3(_Estricto):
    propiedad_id: uuid.UUID
    # None = el usuario no vio propuesta (no hay titularidad en la fecha); con titularidad es obligatoria.
    propuesta_vista: PropuestaVistaB3 | None = None
