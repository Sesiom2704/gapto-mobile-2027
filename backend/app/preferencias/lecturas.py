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
#
#   v0.4.0 (F05-03/F05-04 J2 §1.1; F05 §46.4 R1; F05-D032 C1):
#   `cuenta_disponible_hoy` se evalua con el contrato unico de elegibilidad
#   para la operacion del TIPO de cada preferencia.
#
#   v0.5.0 (F05-03/F05-04 J2 §1.2; F05-D032 C6): `listar` evalua «hoy» con
#   hoy_owner (zona del owner, reloj inyectable) y no con current_date de la
#   sesion (UTC). `propuesta` sigue usando la fecha que recibe.
#
#   v0.6.0 (F05-03/F05-04 J2 §1.9; F05 §46.3 A7): `listar` informa
#   `tercero_disponible` (None sin tercero; False si el tercero ya no es del
#   owner o esta desactivado): la preferencia deja de aplicarse en el
#   registro (el registro no admite ese tercero) y Ajustes lo avisa. Solo
#   lectura; desactivar un tercero no escribe preferencias.
# Version: 0.6.0
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.api.elegibilidad_categoria import validar_seleccion_categoria
from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.core.unidad_trabajo import SesionMotor
from app.preferencias import repositorio as repo
from app.preferencias.resolver import cuentas_elegibles_registro, operacion_de_tipo, resolver, tipo_hecho_registro

#: Naturaleza del registro VS-01 en la matriz C02 de la guarda C-a (por defecto).
NATURALEZA_REGISTRO = "GASTO"
#: Tipos de registro con preferencias (ambitos «Todos los gastos / ingresos», E3).
TIPOS_REGISTRO = ("GASTO", "INGRESO")


def tipos_registro(sesion: SesionMotor) -> dict[str, uuid.UUID]:
    return {codigo: tipo_hecho_registro(sesion, codigo) for codigo in TIPOS_REGISTRO}


def listar(sesion: SesionMotor, reloj: Reloj = reloj_sistema) -> list[dict[str, Any]]:
    hoy = hoy_owner(sesion, reloj)
    elegibles = {op: set(cuentas_elegibles_registro(sesion, hoy, op)) for op in ("GASTO", "INGRESO")}
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id FROM gapto.terceros WHERE enabled "
                    "AND owner_user_id = current_setting('gapto.owner_user_id')::uuid")
        terceros = {f[0] for f in cur.fetchall()}
    return [
        {
            **p,
            "cuenta_disponible_hoy": (
                None if p["cuenta_default_id"] is None
                else p["cuenta_default_id"] in elegibles[operacion_de_tipo(sesion, p["tipo_hecho_id"])]
            ),
            "tercero_disponible": None if p["tercero_id"] is None else p["tercero_id"] in terceros,
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
