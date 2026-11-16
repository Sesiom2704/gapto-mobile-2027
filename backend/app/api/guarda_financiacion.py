# ============================================================
# GAPTO MOBILE 2027
# Fichero: guarda_financiacion.py
# Ruta: backend/app/api/guarda_financiacion.py
# Descripcion: Frontera F05 sobre hechos y previsiones de financiacion
#   (T3-F06 · F04-R-HIP, subhito F05; literal F05 v1.2, S1-S10; D-08 de la
#   adenda v1.3 del mandato). API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   Dos guardas unicas, patron `exigir_propiedad` (una funcion, llamada por
#   todo writer F05 de la superficie):
#     - «hecho vinculado a una financiacion»: el hecho tiene un vinculo de
#       hecho_entidades a una entidad FINANCIACION de NIVEL EFECTO (pago de
#       una cuota, DEUDA -capital; desembolso Hd, DEUDA +P). Predicado unico
#       del motor: hechos_repository.vinculos_de_financiacion (el mismo de
#       A1/A9). El vinculo de nivel hecho no cuenta.
#     - «prevision de cuota»: existe una fila de financiacion_cuotas con
#       prevision_id = la prevision (previsiones/lecturas.es_prevision_de_cuota).
#   Ambas son SELECT sin lock: se evaluan antes de cualquier lock de escritura
#   de la transaccion. El predicado de la prevision es inmutable en runtime
#   (ningun codigo de backend/app escribe financiacion_cuotas; si apareciera un
#   writer de prevision_id seria STOP 9 del mandato).
#
#   Codigos (D-08): el reparto usa el vigente REPARTO_NO_CORREGIBLE con motivo
#   HECHO_DE_FINANCIACION (lo decide ejecucion_reparto); el resto de superficies
#   sobre hechos, HECHO_DE_FINANCIACION (409); las de previsiones (S7 y S10),
#   PREVISION_DE_CUOTA (409). Distintos del codigo de motor de A9
#   (ANULACION_FINANCIACION_SIN_REVERSION). Ningun codigo existente cambia.
# Version: 0.1.0 (F06 T3-F06 · F04-R-HIP, subhito F05)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.previsiones.lecturas import es_prevision_de_cuota
from app.repositories import hechos_repository as repo_hechos

#: Codigos de rechazo de la frontera F05 (y motivos de las lecturas).
HECHO_DE_FINANCIACION = "HECHO_DE_FINANCIACION"
PREVISION_DE_CUOTA = "PREVISION_DE_CUOTA"


def es_hecho_de_financiacion(sesion: SesionMotor, hecho_id: uuid.UUID) -> bool:
    """Guarda «hecho vinculado a una financiacion» (nivel efecto)."""
    return any(efecto_id is not None
               for _vinculo, efecto_id, _importe in repo_hechos.vinculos_de_financiacion(sesion, hecho_id))


def rechazo_hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> str | None:
    """HECHO_DE_FINANCIACION si el hecho es de financiacion; None si no."""
    return HECHO_DE_FINANCIACION if es_hecho_de_financiacion(sesion, hecho_id) else None


def rechazo_prevision(sesion: SesionMotor, prevision_id: uuid.UUID) -> str | None:
    """PREVISION_DE_CUOTA si la prevision es la de una cuota; None si no."""
    return PREVISION_DE_CUOTA if es_prevision_de_cuota(sesion, prevision_id) else None


def rechazo_bloque_prevision(sesion: SesionMotor, bloque: Any) -> str | None:
    """S10: bloque `prevision` del registro (gasto-pagado, gasto-compartido,
    ingreso-cobrado, transferencia). None sin bloque."""
    if bloque is None:
        return None
    return rechazo_prevision(sesion, bloque.prevision_id)
