# ============================================================
# GAPTO MOBILE 2027
# Fichero: fecha_funcional.py
# Ruta: backend/app/comun/fecha_funcional.py
# Descripcion: Fecha funcional del owner en la capa F05 (F05-D032 C6,
#   politica A+B; F05 §46.4 R1 «fecha del registro»). API DE INTEGRACION F05,
#   PENDIENTE DE CONSOLIDACION F10.
#
#   - «Hoy» es la fecha civil del owner: el instante del reloj convertido a
#     la zona `gapto.usuarios.timezone` del owner (default de 0010:
#     Europe/Madrid). Si la zona no existe o no se reconoce, Europe/Madrid
#     (fallback). La base sigue en UTC (0002) y la UdT de F04 no se toca: la
#     conversion vive aqui.
#   - El reloj es INYECTABLE (devuelve un instante con zona); por defecto, el
#     reloj del sistema en UTC. Los tests fijan instantes (00:30 Madrid,
#     cambio de hora, UTC+3/UTC-5).
#   - Lecturas: usan la fecha que reciben (la del formulario); nunca
#     current_date de la sesion (UTC). Writers: usan hoy_owner.
#   - FECHA_FUTURA: una fecha funcional posterior a hoy_owner se rechaza en
#     la intencion nueva (registro de hechos ya ocurridos). Codigo de capa F05.
#   El owner no es parametro: se lee de la GUC del tenant (convencion del
#   backend: nunca se pasa el owner).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.2)
# ============================================================

from __future__ import annotations

import datetime as dt
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.unidad_trabajo import SesionMotor

ZONA_POR_DEFECTO = "Europe/Madrid"
CODIGO_FECHA_FUTURA = "FECHA_FUTURA"

#: Reloj: devuelve el instante actual CON zona.
Reloj = Callable[[], dt.datetime]


def reloj_sistema() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def zona(nombre: str | None) -> ZoneInfo:
    """Zona IANA; fallback Europe/Madrid si falta o no se reconoce."""
    if nombre:
        try:
            return ZoneInfo(nombre)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return ZoneInfo(ZONA_POR_DEFECTO)


def zona_owner(sesion: SesionMotor) -> ZoneInfo:
    fila = sesion.uno(
        "SELECT timezone FROM gapto.usuarios WHERE id = current_setting('gapto.owner_user_id')::uuid"
    )
    return zona(None if fila is None else fila[0])


def hoy_en(zona_owner_: ZoneInfo, reloj: Reloj = reloj_sistema) -> dt.date:
    instante = reloj()
    if instante.tzinfo is None:
        raise ValueError("el reloj debe devolver un instante con zona")
    return instante.astimezone(zona_owner_).date()


def hoy_owner(sesion: SesionMotor, reloj: Reloj = reloj_sistema) -> dt.date:
    """Fecha civil de hoy del owner del contexto (zona leida en la transaccion)."""
    return hoy_en(zona_owner(sesion), reloj)


def es_futura(sesion: SesionMotor, fecha: dt.date, reloj: Reloj = reloj_sistema) -> bool:
    return fecha > hoy_owner(sesion, reloj)
