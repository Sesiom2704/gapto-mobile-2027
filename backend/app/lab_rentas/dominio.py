# ============================================================
# GAPTO MOBILE 2027 · LABORATORIO (rama lab-t5; no es implementacion de T5)
# Fichero: dominio.py
# Ruta: backend/app/lab_rentas/dominio.py
# Descripcion: L1 · reglas PURAS de F06-04 Rentas e IPC para probar en codigo las decisiones de Moises del
#   2026-11-23 (F06-00_Decisiones_Moises_2026-11-23_T5_negocio_v1.0.md, c1c1f467…). Sin base de datos ni efectos.
#   Cada funcion cita su decision (R4..R18). Los supuestos que el laboratorio ha tenido que tomar estan marcados
#   «SUPUESTO» y van a LAB_T5_INFORME.md para el diseno N1.
# Version: 0.1.0 (LAB T5 · L1)
# ============================================================

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
DIAS_VALIDOS_CONTRATO = (1, 15)          # R8: un contrato empieza o termina solo el 1 o el 15


class ReglaRenta(ValueError):
    """Entrada que viola una decision de negocio (el servicio la traduce a un rechazo)."""


def _mas_meses(f: dt.date, meses: int) -> dt.date:
    m = f.month - 1 + meses
    a, m = f.year + m // 12, m % 12 + 1
    return dt.date(a, m, min(f.day, calendar.monthrange(a, m)[1]))


# ------------------------------------------------------------------ R8 · R14 · calendario de cobros previstos
@dataclass(frozen=True)
class Cobro:
    fecha: dt.date            # mes de devengo (dia 1); el cobro se espera en la ventana del 1 al 5 (R2)
    importe: Decimal
    medio_mes: bool


def calendario_cobros(inicio: dt.date, renta: Decimal, hasta: dt.date, fin: dt.date | None = None) -> list[Cobro]:
    """Cobros previstos mensuales desde `inicio` hasta `hasta` y NUNCA despues de `fin` (R14).
    Inicio o fin el 15 -> ese mes cuenta medio mes (R8), editable despues. SUPUESTO: medio mes = renta/2 redondeado
    al centimo hacia arriba (ROUND_HALF_UP)."""
    if inicio.day not in DIAS_VALIDOS_CONTRATO or (fin is not None and fin.day not in DIAS_VALIDOS_CONTRATO):
        raise ReglaRenta("Un contrato empieza o termina el dia 1 o el 15 (R8).")
    if renta <= 0:
        raise ReglaRenta("La renta tiene que ser mayor que 0.")
    if fin is not None and fin <= inicio:
        raise ReglaRenta("El fin tiene que ser posterior al inicio.")
    medio = (renta / 2).quantize(CENT, ROUND_HALF_UP)
    limite = min(hasta, fin) if fin is not None else hasta
    cobros: list[Cobro] = []
    mes = inicio.replace(day=1)
    while mes <= limite:
        primero = mes == inicio.replace(day=1) and inicio.day == 15
        ultimo = fin is not None and mes == fin.replace(day=1)
        if ultimo and fin.day == 1:
            break                                  # termina el dia 1: ese mes no se devenga
        medio_mes = primero or (ultimo and fin.day == 15)
        cobros.append(Cobro(mes, medio if medio_mes else renta.quantize(CENT), medio_mes))
        mes = _mas_meses(mes, 1)
    return cobros


# ------------------------------------------------------------------ R5 · revision con redondeo a la baja
@dataclass(frozen=True)
class PropuestaRevision:
    renta_anterior: Decimal
    porcentaje: Decimal
    exacta: Decimal           # con 4 decimales, lo que se muestra «exacto»
    propuesta: Decimal        # el euro a la baja (R5), editable


def proponer_revision(renta_anterior: Decimal, porcentaje: Decimal) -> PropuestaRevision:
    """R4-A/R5: renta nueva = anterior x (1 + indice/100). Se muestra la exacta y se propone el euro a la baja.
    Un indice negativo baja la renta (SUPUESTO: se aplica igual; el N1 decide si se admite)."""
    if renta_anterior <= 0:
        raise ReglaRenta("La renta anterior tiene que ser mayor que 0.")
    exacta = (renta_anterior * (1 + porcentaje / 100)).quantize(Decimal("0.0001"), ROUND_HALF_EVEN)
    return PropuestaRevision(renta_anterior, porcentaje, exacta, exacta.quantize(Decimal("1"), ROUND_DOWN))


# ------------------------------------------------------------------ R6 · tope con receptor del exceso
@dataclass(frozen=True)
class ResultadoTope:
    renta_contrato: Decimal
    renta_receptor: Decimal
    exceso: Decimal


def aplicar_tope(renta_contrato_anterior: Decimal, renta_contrato_nueva: Decimal, renta_receptor_anterior: Decimal,
                 renta_receptor_nueva: Decimal, porcentaje_tope: Decimal) -> ResultadoTope:
    """R6 (SAAV vivienda 600 -> garaje; «% sobre el total; una tarea»). SUPUESTO del laboratorio: el tope limita la
    subida del contrato al `porcentaje_tope` del TOTAL anterior (contrato + receptor); lo que la exceda pasa al
    receptor, de modo que el total cobrado no cambia. Pregunta abierta en el informe."""
    total_anterior = renta_contrato_anterior + renta_receptor_anterior
    subida_max = (total_anterior * porcentaje_tope / 100).quantize(CENT, ROUND_DOWN)
    subida = renta_contrato_nueva - renta_contrato_anterior
    if subida <= subida_max:
        return ResultadoTope(renta_contrato_nueva, renta_receptor_nueva, Decimal("0.00"))
    exceso = (subida - subida_max).quantize(CENT)
    return ResultadoTope(renta_contrato_anterior + subida_max, renta_receptor_nueva + exceso, exceso)


# ------------------------------------------------------------------ R10 · R11 · avisos y aviso tardio
def avisos(aniversario: dt.date) -> tuple[dt.date, dt.date]:
    """R10: primer aviso dos meses antes del aniversario y segundo un mes antes."""
    return _mas_meses(aniversario, -2), _mas_meses(aniversario, -1)


def fecha_efecto(aniversario: dt.date, fecha_aviso: dt.date) -> dt.date:
    """R11: rige el primer dia 1 que quede al menos a un mes del aviso, y nunca antes del aniversario
    («si aviso el 10, el problema es mio y pasariamos a octubre»)."""
    minimo = max(_mas_meses(fecha_aviso, 1), aniversario)
    return minimo if minimo.day == 1 else _mas_meses(minimo.replace(day=1), 1)


# ------------------------------------------------------------------ R14b · prorroga y limites 5 + 3
def prorrogar_un_anio(fin: dt.date) -> dt.date:
    return _mas_meses(fin, 12)


def limites_legales(inicio: dt.date) -> tuple[dt.date, dt.date]:
    """R14b (A8): prorroga obligatoria hasta 5 anios y tacita hasta 3 mas (SUPUESTO: contados desde el inicio)."""
    return _mas_meses(inicio, 60), _mas_meses(inicio, 96)


def antiguedad_meses(inicio: dt.date, hoy: dt.date) -> int:
    return (hoy.year - inicio.year) * 12 + hoy.month - inicio.month - (1 if hoy.day < inicio.day else 0)


# ------------------------------------------------------------------ R7 · atribucion por participacion
def repartir(importe: Decimal, partes: dict[str, Decimal]) -> dict[str, Decimal]:
    """R7: la renta se reparte segun la participacion en la vivienda. Centimos exactos (suma = total) con el residuo
    al de mayor parte y desempate por clave (determinista)."""
    total_pct = sum(partes.values())
    if total_pct != 100:
        raise ReglaRenta("Las participaciones tienen que sumar 100.")
    base = {k: (importe * v / 100).quantize(CENT, ROUND_DOWN) for k, v in partes.items()}
    resto = int(((importe - sum(base.values())) / CENT).to_integral_value())
    for k in sorted(partes, key=lambda x: (-partes[x], x))[:resto]:
        base[k] += CENT
    return base


# ------------------------------------------------------------------ R4-B · R15 · diferencias y perdon
def pendiente_por_renta_antigua(cobrado: Decimal, renta_vigente: Decimal) -> Decimal:
    """R4-B: si paga la renta antigua, la diferencia queda pendiente con el inquilino (sin atrasos retroactivos)."""
    return max(Decimal("0.00"), (renta_vigente - cobrado).quantize(CENT))


def perdonar_lo_que_falta(esperado: Decimal, cobrado: Decimal) -> Decimal:
    """R15: «Perdonar lo que falta» (CONDONACION) por lo que queda; nunca por gesto. 0 si no falta nada."""
    return max(Decimal("0.00"), (esperado - cobrado).quantize(CENT))


# ------------------------------------------------------------------ R16 · R18 · tareas
@dataclass(frozen=True)
class Tarea:
    clave: str
    texto: str
    fecha: dt.date | None = None


def tareas_contrato(nombre: str, *, tipo_revision: str | None, renta_registrada: bool, renta_completa: bool,
                    aniversario: dt.date | None, hoy: dt.date) -> list[Tarea]:
    """R16 (cláusula «No lo sé»), R18 (renta de V3 sin completar) y R10 (aviso de aniversario a 2 y a 1 mes)."""
    out: list[Tarea] = []
    if tipo_revision is None or tipo_revision == "OTRO":
        out.append(Tarea("INDICAR_REVISION", f"Indica cómo se revisa la renta de {nombre}"))
    if renta_registrada and not renta_completa:
        out.append(Tarea("COMPLETAR_RENTA", f"Completa la renta de {nombre}"))
    if aniversario is not None and tipo_revision not in (None, "NINGUNA", "OTRO"):
        primero, segundo = avisos(aniversario)
        if primero <= hoy < aniversario:
            out.append(Tarea("REVISAR_RENTA", f"Revisa la renta de {nombre}: aniversario el {aniversario:%d/%m/%Y}",
                             segundo if hoy >= segundo else primero))
    return out
