# ============================================================
# GAPTO MOBILE 2027
# Fichero: calculadora.py
# Ruta: backend/app/hipotecas/calculadora.py
# Descripcion: Calculadora del cuadro de amortizacion de la hipoteca (F06-01H; contrato v0.4 §2, cerrado por
#   Q-25 y Q-H-07; mandato T3-F06 bloque 2 v1.1 §2.2). Funciones puras, sin base de datos:
#     - Solo FRANCES y pago MENSUAL. i = tasa_anual / 12 / 100, sin dias reales. Otro sistema u otra
#       periodicidad -> CondicionesIncompletas (SISTEMA_NO_SOPORTADO / PERIODICIDAD_NO_SOPORTADA). LINEAL,
#       comisiones periodicas, pago DISTINTO y amortizacion anticipada quedan fuera de v1 (D15).
#     - cuota = r2(P*i / (1 - (1+i)^-n)); con i = 0, cuota = r2(P/n).
#     - Por cuota: interes_k = r2(pendiente_k * i); capital_k = cuota - interes_k; la ULTIMA absorbe el
#       residuo (capital = pendiente restante, cuota = capital + interes): Σ capital = P exacto.
#     - HALF_UP a centimos por componente; el calculo intermedio va con 50 digitos de precision.
#     - Vencimientos: el dia del mes de la primera cuota, acotado al ultimo dia de los meses cortos.
#     - Comprobaciones: Σ capital = pendiente del tramo, pendiente final 0, componentes >= 0 y en centimos,
#       total > 0. Si fallan -> CuadroNoCuadra (CUADRO_NO_CUADRA): DEFECTO, nunca respuesta normal; quien
#       escribe lo convierte en VIOLACION_INVARIANTE_FISICA con ROLLBACK.
#     - `cuadro_frances` calcula el cuadro completo (vista previa W-HIP-00 y alta); `tramo_desde` calcula un
#       tramo desde un pendiente sobre numeros y vencimientos dados (revision del tipo, O-H4).
#   Fuente independiente de los oraculos: `oraculos.json` y los CSV del paso 12 (tests/api/oraculos_f06h);
#   esta calculadora NO importa `cuadro.py` del paso 12 ni nada del laboratorio (contrato §2).
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 4)
# ============================================================

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Sequence

CENT = Decimal("0.01")
CERO = Decimal("0")
PRECISION = 50
SISTEMA = "FRANCES"
PERIODICIDAD = "MENSUAL"
#: Codigo de la convencion de calculo (contrato §3.3): mensual, tipo anual entre 12.
CONVENCION = "MENSUAL_ANUAL_12"
MAX_CUOTAS = 600
MAX_TASA = Decimal("30")
MAX_CAPITAL = Decimal("100000000000000")

CONDICIONES_INCOMPLETAS = "CONDICIONES_INCOMPLETAS"
CUADRO_NO_CUADRA = "CUADRO_NO_CUADRA"
SISTEMA_NO_SOPORTADO = "SISTEMA_NO_SOPORTADO"
PERIODICIDAD_NO_SOPORTADA = "PERIODICIDAD_NO_SOPORTADA"
VALORES_FUERA_DE_RANGO = "VALORES_FUERA_DE_RANGO"


class CondicionesIncompletas(Exception):
    """Condiciones no soportadas o fuera de rango: rechazo de negocio (422)."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.codigo = CONDICIONES_INCOMPLETAS
        self.motivo = motivo


class CuadroNoCuadra(Exception):
    """Defecto de calculo: el cuadro no cumple sus comprobaciones. Nunca es una respuesta normal."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.codigo = CUADRO_NO_CUADRA
        self.motivo = motivo


@dataclass(frozen=True, slots=True)
class Cuota:
    numero: int
    vencimiento: dt.date | None
    cuota: Decimal
    interes: Decimal
    capital: Decimal
    comision: Decimal
    pendiente: Decimal


def r2(valor: Decimal) -> Decimal:
    """Redondeo HALF_UP a centimos."""
    return valor.quantize(CENT, rounding=ROUND_HALF_UP)


def tasa_periodo(tasa_anual: Decimal) -> Decimal:
    """i = tasa_anual / 12 / 100 con precision completa."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return Decimal(tasa_anual) / Decimal(12) / Decimal(100)


def cuota_francesa(principal: Decimal, tasa_anual: Decimal, numero_cuotas: int) -> Decimal:
    """Cuota constante redondeada: r2(P*i / (1 - (1+i)^-n)); con i = 0, r2(P/n)."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        i = tasa_periodo(tasa_anual)
        p = Decimal(principal)
        if i == 0:
            return r2(p / Decimal(numero_cuotas))
        return r2(p * i / (Decimal(1) - (Decimal(1) + i) ** (-numero_cuotas)))


def vencimiento(primera: dt.date, k: int) -> dt.date:
    """Vencimiento de la cuota k (0 = la primera): dia de la primera, acotado al ultimo dia del mes."""
    meses = primera.month - 1 + k
    anio, mes = primera.year + meses // 12, meses % 12 + 1
    return dt.date(anio, mes, min(primera.day, calendar.monthrange(anio, mes)[1]))


def validar_condiciones(*, sistema: str, periodicidad: str) -> None:
    if periodicidad != PERIODICIDAD:
        raise CondicionesIncompletas(PERIODICIDAD_NO_SOPORTADA)
    if sistema != SISTEMA:
        raise CondicionesIncompletas(SISTEMA_NO_SOPORTADO)


def validar_valores(*, capital: Decimal, tasa_anual: Decimal, numero_cuotas: int) -> None:
    capital, tasa = Decimal(capital), Decimal(tasa_anual)
    if not capital.is_finite() or capital <= 0 or capital >= MAX_CAPITAL or capital != r2(capital):
        raise CondicionesIncompletas(VALORES_FUERA_DE_RANGO)
    if not tasa.is_finite() or tasa < 0 or tasa > MAX_TASA or tasa != tasa.quantize(Decimal("0.000001")):
        raise CondicionesIncompletas(VALORES_FUERA_DE_RANGO)
    if isinstance(numero_cuotas, bool) or not isinstance(numero_cuotas, int) or not 1 <= numero_cuotas <= MAX_CUOTAS:
        raise CondicionesIncompletas(VALORES_FUERA_DE_RANGO)


def _comprobar(filas: list[Cuota], pendiente: Decimal) -> None:
    """Comprobaciones del contrato §2; cualquier fallo es un defecto (CUADRO_NO_CUADRA)."""
    for f in filas:
        for valor in (f.cuota, f.interes, f.capital, f.pendiente):
            if valor != r2(valor):
                raise CuadroNoCuadra(f"COMPONENTE_SIN_CENTIMOS_{f.numero}")
        if f.capital < 0 or f.interes < 0 or f.comision < 0 or f.pendiente < 0:
            raise CuadroNoCuadra(f"COMPONENTE_NEGATIVO_{f.numero}")
        if f.cuota <= 0 or f.cuota != f.capital + f.interes + f.comision:
            raise CuadroNoCuadra(f"TOTAL_{f.numero}")
    if sum((f.capital for f in filas), CERO) != pendiente:
        raise CuadroNoCuadra("SUMA_CAPITAL")
    if filas[-1].pendiente != 0:
        raise CuadroNoCuadra("PENDIENTE_FINAL")


def tramo_desde(pendiente: Decimal, tasa_anual: Decimal, numeros: Sequence[int],
                vencimientos: Sequence[dt.date | None]) -> list[Cuota]:
    """Tramo FRANCES desde un pendiente (alta: tramo completo; revision: pendiente a la fecha efectiva con
    los numeros y vencimientos que ya existen). La cuota se recalcula sobre len(numeros) cuotas."""
    pendiente = Decimal(pendiente)
    n = len(numeros)
    if n < 1 or n != len(vencimientos) or pendiente <= 0:
        raise CuadroNoCuadra("TRAMO_VACIO")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        i = tasa_periodo(tasa_anual)
        cuota = cuota_francesa(pendiente, tasa_anual, n)
        filas: list[Cuota] = []
        resto = pendiente
        for k, (numero, venc) in enumerate(zip(numeros, vencimientos), start=1):
            interes = r2(resto * i)
            capital = resto if k == n else cuota - interes        # la ultima absorbe el residuo
            resto = resto - capital
            filas.append(Cuota(numero=numero, vencimiento=venc, cuota=capital + interes, interes=interes,
                               capital=capital, comision=CERO.quantize(CENT), pendiente=resto))
    _comprobar(filas, pendiente)
    return filas


def cuadro_frances(capital: Decimal, tasa_anual: Decimal, numero_cuotas: int, primera_cuota: dt.date | None = None,
                   *, sistema: str = SISTEMA, periodicidad: str = PERIODICIDAD) -> list[Cuota]:
    """Cuadro completo 1..n. Sin primera cuota, los vencimientos son None."""
    validar_condiciones(sistema=sistema, periodicidad=periodicidad)
    validar_valores(capital=capital, tasa_anual=tasa_anual, numero_cuotas=numero_cuotas)
    vencimientos = [None if primera_cuota is None else vencimiento(primera_cuota, k) for k in range(numero_cuotas)]
    return tramo_desde(Decimal(capital), Decimal(tasa_anual), list(range(1, numero_cuotas + 1)), vencimientos)


def resumen(filas: list[Cuota]) -> dict[str, Decimal]:
    """Sumas del cuadro: cuota de referencia (la primera), Σ capital, Σ intereses y total a pagar."""
    return {"cuota_referencia": filas[0].cuota, "suma_capital": sum((f.capital for f in filas), CERO),
            "suma_intereses": sum((f.interes for f in filas), CERO),
            "total_a_pagar": sum((f.cuota for f in filas), CERO)}
