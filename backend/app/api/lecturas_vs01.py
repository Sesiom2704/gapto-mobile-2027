# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas_vs01.py
# Ruta: backend/app/api/lecturas_vs01.py
# Descripcion: Lecturas ESTRECHAS del vertical slice VS-01.
#   CONTRATO PROVISIONAL VS-01 — candidato a sustitucion/consolidacion por
#   F08 (F08-07 read models). No es el read model oficial de Home.
#
#   gasto_mes: "gasto atribuible confirmado del actor self durante un mes
#   natural, en EUR" (mandato F05-00-B v0.2 §6):
#     - efectos GASTO (delta con signo: una devolucion registrada como GASTO
#       negativo reduce el total, como en el motor);
#     - hechos ACTIVOS; mes por fecha_hecho (fecha economica);
#     - suma de efecto_atribuciones del actor self (HOME-RULE-01: perspectiva
#       personal; en un reparto COMPLETO sin fila del self su parte es 0);
#     - moneda distinta de EUR: NO se convierte ni se suma; se cuenta aparte;
#     - efectos con reparto no COMPLETO: su parte self es desconocida; se
#       cuentan aparte y el estado pasa a PARCIAL (nunca se suman como 0).
#   Todas las lecturas corren como gapto_runtime bajo RLS del tenant.
#   v0.2.0 (F05-D003): cuentas_pago recibe la fecha del pago y devuelve una
#   propuesta de financiacion explicita en vez de un booleano derivable.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal

from app.api.traductor_gasto_pagado import leer_actor_self, participacion_self_100
from app.core.unidad_trabajo import SesionMotor

CONTRATO_GASTO_MES = "PROVISIONAL_VS01_CANDIDATO_F08"


def rango_mes(mes: str) -> tuple[dt.date, dt.date]:
    anio, m = (int(p) for p in mes.split("-"))
    inicio = dt.date(anio, m, 1)
    fin = dt.date(anio + (m == 12), 1 if m == 12 else m + 1, 1)
    return inicio, fin


def gasto_mes(sesion: SesionMotor, mes: str) -> dict:
    inicio, fin = rango_mes(mes)
    actor = leer_actor_self(sesion)
    fila = sesion.uno(
        """
        WITH ef AS (
            SELECT e.id, e.estado_atribucion, h.moneda
              FROM gapto.hecho_efectos e
              JOIN gapto.hechos_financieros h ON h.id = e.hecho_id
             WHERE e.tipo_efecto = 'GASTO'
               AND h.estado = 'ACTIVO'
               AND h.fecha_hecho >= %s AND h.fecha_hecho < %s
        )
        SELECT
          (SELECT COALESCE(SUM(a.importe_atribuido), 0)
             FROM gapto.efecto_atribuciones a
             JOIN ef ON ef.id = a.efecto_id
            WHERE ef.moneda = 'EUR' AND ef.estado_atribucion = 'COMPLETA'
              AND a.actor_id = %s),
          (SELECT count(*) FROM ef WHERE moneda = 'EUR' AND estado_atribucion <> 'COMPLETA'),
          (SELECT count(*) FROM ef WHERE moneda <> 'EUR')
        """,
        (inicio, fin, actor),
    )
    total, sin_reparto, otra_moneda = fila
    total = decimal.Decimal(total).quantize(decimal.Decimal("0.01"))
    return {
        "mes": mes,
        "moneda": "EUR",
        "gasto_atribuible": str(total),
        "estado": "PARCIAL" if (sin_reparto or otra_moneda) else "CONFIRMADO",
        "gastos_sin_reparto": int(sin_reparto),
        "gastos_otra_moneda": int(otra_moneda),
        "contrato": CONTRATO_GASTO_MES,
    }


def cuentas_pago(sesion: SesionMotor, fecha: dt.date) -> list[dict]:
    """Cuentas habilitadas, ACTIVO y abiertas en `fecha` (fecha comun de gasto
    y pago, §16.3), con la PROPUESTA de financiacion para esa fecha (§16.4):
    SELF_100 solo si hay una unica participacion vigente, del self, al 100 %.
    Es una propuesta para mostrar; la ejecucion la revalida bajo lock."""
    actor = leer_actor_self(sesion)
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, nombre, moneda FROM gapto.cuentas "
            "WHERE enabled AND (fecha_cierre IS NULL OR fecha_cierre > %s) "
            "AND naturaleza = 'ACTIVO' ORDER BY orden, nombre, id",
            (fecha,),
        )
        filas = cur.fetchall()
    return [
        {
            "cuenta_id": f[0],
            "nombre": f[1],
            "moneda": f[2],
            "propuesta_financiacion": (
                "SELF_100" if participacion_self_100(sesion, f[0], actor, fecha) else "NO_DETERMINADA"
            ),
        }
        for f in filas
    ]
