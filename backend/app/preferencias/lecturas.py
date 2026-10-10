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
#
#   v0.2.0 (F05-02 B2; F05 §42.7, R-B1-03): la propuesta con una categoria
#   que no es elegible para GASTO (inexistente u oculta por RLS, de otro
#   owner, deshabilitada o de ambito incompatible) devuelve el codigo
#   CATEGORIA_NO_ELEGIBLE y nunca una propuesta. La decision es la de la
#   guarda UNICA C-a (elegibilidad_categoria.validar_seleccion_categoria),
#   reutilizada sin modificarla: el registro no convierte una categoria
#   incompatible en una propuesta valida. La guarda toma FOR SHARE sobre la
#   fila de la categoria durante esta transaccion de lectura (nunca el
#   advisory de categorias ni el de preferencias) y no escribe. Sin categoria
#   («Sin categoria») no se consulta la guarda.
#
#   v0.3.0 (F05-03/F05-04 J2 §1.5; F05 §46.4 R6, §46.5 E2/E3): `propuesta`
#   recibe el TIPO del registro (GASTO o INGRESO; la guarda C-a se evalua con
#   esa naturaleza) y el tercero del contexto (None = sin tercero), que pasa
#   a ser dimension operativa del resolver. `tipos_registro` expone los ids de
#   GASTO e INGRESO para que el cliente envie siempre el tipo (E3).
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.api.elegibilidad_categoria import validar_seleccion_categoria
from app.core.unidad_trabajo import SesionMotor
from app.preferencias import repositorio as repo
from app.preferencias.resolver import cuentas_elegibles_registro, resolver, tipo_hecho_registro

#: Naturaleza del registro VS-01 en la matriz C02 de la guarda C-a (por defecto).
NATURALEZA_REGISTRO = "GASTO"
#: Tipos de registro con preferencias (ambitos «Todos los gastos / ingresos», E3).
TIPOS_REGISTRO = ("GASTO", "INGRESO")


def tipos_registro(sesion: SesionMotor) -> dict[str, uuid.UUID]:
    return {codigo: tipo_hecho_registro(sesion, codigo) for codigo in TIPOS_REGISTRO}


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


def propuesta(sesion: SesionMotor, categoria_id: uuid.UUID | None, fecha: dt.date,
              tipo: str = NATURALEZA_REGISTRO, tercero_id: uuid.UUID | None = None) -> dict[str, Any] | str:
    """Propuesta por campo, o el codigo CATEGORIA_NO_ELEGIBLE si la categoria
    no es elegible para `tipo` (guarda C-a; nunca una propuesta en ese caso)."""
    if categoria_id is not None:
        rechazo = validar_seleccion_categoria(sesion, categoria_id, tipo)
        if rechazo is not None:
            return rechazo
    return resolver(
        sesion, tipo_hecho_id=tipo_hecho_registro(sesion, tipo), categoria_id=categoria_id, fecha=fecha,
        tercero_id=tercero_id,
    )
