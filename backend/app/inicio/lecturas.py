# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/inicio/lecturas.py
# Descripcion: Read models de Inicio (F05 §49.4 A9; D13; M5-06; AJ-F0505-03;
#   casos 25-27 y 32 de §49.9). Solo lectura, sin locks, gapto_runtime con RLS.
#   Identidad todavia de desarrollo (F10-01).
#
#   yo: `usuarios.nombre` del owner de la GUC.
#
#   resultado_mes(fecha) — CONTRATO LITERAL DE A9:
#   - Universo: hechos ACTIVOS del owner, fecha_hecho en el mes natural que
#     contiene la fecha funcional recibida ([inicio, fin), C6) y moneda EUR.
#     Las previsiones nunca entran (no son hechos).
#   - Efectos considerados: solo tipo_efecto GASTO e INGRESO (DEUDA,
#     DERECHO_COBRO, INVERSION y VALOR_ACTIVO fuera: un reembolso no es
#     ingreso; una transferencia propia no tiene efectos y cuenta 0).
#   - Signo: importe_delta firmado. Gastos propios = suma sobre GASTO;
#     ingresos propios = suma sobre INGRESO (una devolucion es un GASTO
#     negativo y reduce el gasto). Resultado = ingresos - gastos.
#   - Propio, por efecto: COMPLETA -> suma de importe_atribuido del actor
#     propio (actores_financieros.tercero_id IS NULL), que puede ser 0;
#     PARCIAL -> la parte atribuida al actor propio, y la diferencia
#     importe_delta - suma atribuida (todos los actores) va a «Sin indicar»;
#     NO_DISPONIBLE -> nada propio y el importe_delta completo a «Sin
#     indicar». Nunca se usa el total del hecho ni quien pago.
#   - «Sin indicar»: HECHOS (no efectos) con al menos un efecto GASTO (o
#     INGRESO) con parte no atribuida, por separado; el importe es la suma de
#     las partes no atribuidas (importe pendiente de atribucion, nunca
#     propio). Un hecho con un efecto PARCIAL cuenta una vez.
#   - Deduplicacion: se calcula por efecto (subconsultas por efecto) y se
#     agrega por hecho en Python; ningun join multiplica importes.
#   Importes como texto con 2 decimales.
# Version: 0.1.0 (F05-05 K2 §1.6)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from app.comun.fecha_funcional import limites_mes
from app.core.unidad_trabajo import SesionMotor

_CENT = decimal.Decimal("0.01")
_CERO = decimal.Decimal(0)

_EFECTOS_DEL_MES = (
    "SELECT e.hecho_id, e.tipo_efecto, e.importe_delta, e.estado_atribucion, "
    "(SELECT COALESCE(sum(a.importe_atribuido), 0) FROM gapto.efecto_atribuciones a WHERE a.efecto_id = e.id), "
    "(SELECT COALESCE(sum(a.importe_atribuido), 0) FROM gapto.efecto_atribuciones a "
    " WHERE a.efecto_id = e.id AND a.actor_id = %(actor)s) "
    "FROM gapto.hecho_efectos e JOIN gapto.hechos_financieros h ON h.id = e.hecho_id "
    "WHERE h.estado = 'ACTIVO' AND h.moneda = 'EUR' "
    "AND h.fecha_hecho >= %(inicio)s AND h.fecha_hecho < %(fin)s "
    "AND e.tipo_efecto IN ('GASTO', 'INGRESO')"
)


def yo(sesion: SesionMotor) -> dict[str, Any]:
    fila = sesion.uno("SELECT nombre FROM gapto.usuarios WHERE id = current_setting('gapto.owner_user_id')::uuid")
    return {"nombre": None if fila is None else fila[0]}


def _texto(valor: decimal.Decimal) -> str:
    return str(valor.quantize(_CENT))


def resultado_mes(sesion: SesionMotor, fecha: dt.date) -> dict[str, Any]:
    inicio, fin = limites_mes(fecha)
    actor = sesion.uno("SELECT id FROM gapto.actores_financieros WHERE tercero_id IS NULL")
    actor_self = actor[0] if actor else None
    propios = {"GASTO": _CERO, "INGRESO": _CERO}
    pendiente: dict[str, dict[uuid.UUID, decimal.Decimal]] = {"GASTO": {}, "INGRESO": {}}
    with sesion.conexion.cursor() as cur:
        cur.execute(_EFECTOS_DEL_MES, {"actor": actor_self, "inicio": inicio, "fin": fin})
        for hecho_id, tipo, delta, estado, atribuido, propio in cur.fetchall():
            delta, atribuido, propio = decimal.Decimal(delta), decimal.Decimal(atribuido), decimal.Decimal(propio)
            if estado == "COMPLETA":
                propios[tipo] += propio
                continue
            if estado == "PARCIAL":
                propios[tipo] += propio
                resto = delta - atribuido
            else:  # NO_DISPONIBLE
                resto = delta
            if resto != 0:
                pendiente[tipo][hecho_id] = pendiente[tipo].get(hecho_id, _CERO) + resto
    sin_indicar = {
        ("gastos" if tipo == "GASTO" else "ingresos"): {
            "n": len(por_hecho), "importe": _texto(sum(por_hecho.values(), _CERO))}
        for tipo, por_hecho in pendiente.items()
    }
    return {
        "mes": f"{inicio.year:04d}-{inicio.month:02d}",
        "moneda": "EUR",
        "ingresos_propios": _texto(propios["INGRESO"]),
        "gastos_propios": _texto(propios["GASTO"]),
        "resultado": _texto(propios["INGRESO"] - propios["GASTO"]),
        "sin_indicar": sin_indicar,
    }
