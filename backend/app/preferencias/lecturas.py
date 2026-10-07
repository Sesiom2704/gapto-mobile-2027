# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/preferencias/lecturas.py
# Descripcion: Lecturas de las preferencias de registro (F05-02, F05-D026).
#   Solo lectura, bajo gapto_runtime y RLS del tenant, sin locks.
#
#   - `listar`: TODAS las preferencias del owner (habilitadas y desactivadas)
#     en orden estable (created_at, id), con `cuenta_disponible_hoy`: si la
#     cuenta propuesta es elegible HOY para el registro (misma regla que el
#     resolver: cuentas_pago + moneda EUR). None si la preferencia no propone
#     cuenta. Es el dato del aviso de Ajustes (S01; R-F05-02-03): una cuenta
#     no elegible se ignora en el registro sin error.
#   - `propuesta`: expone el resolver para el contexto del registro VS-01
#     (tipo de hecho GASTO, categoria o «Sin categoria», fecha). No se conecta
#     todavia a REG-01 ni a la ejecucion (B2).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.preferencias import repositorio as repo
from app.preferencias.resolver import cuentas_elegibles_registro, resolver, tipo_hecho_registro


def listar(sesion: SesionMotor) -> list[dict[str, Any]]:
    hoy = sesion.uno("SELECT current_date")[0]
    elegibles = set(cuentas_elegibles_registro(sesion, hoy))
    return [
        {
            **p,
            "cuenta_disponible_hoy": (
                None if p["cuenta_default_id"] is None else p["cuenta_default_id"] in elegibles
            ),
        }
        for p in repo.todas(sesion)
    ]


def propuesta(sesion: SesionMotor, categoria_id: uuid.UUID | None, fecha: dt.date) -> dict[str, Any]:
    return resolver(
        sesion, tipo_hecho_id=tipo_hecho_registro(sesion), categoria_id=categoria_id, fecha=fecha
    )
