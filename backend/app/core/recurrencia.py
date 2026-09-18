# ============================================================
# GAPTO MOBILE 2027
# Fichero: recurrencia.py
# Ruta: backend/app/core/recurrencia.py
# Descripcion: Aritmetica pura de recurrencia, ventanas, segmentos,
#   transiciones de anclaje y estimacion de importe.
#
#   TODO en este modulo es PURO: no toca base de datos, no lee reloj y no
#   depende de estado. Se hizo asi a proposito, porque es donde vive F04-D020 y
#   una regla aritmetica solo se puede discriminar bien si se puede probar
#   aislada, con vectores exactos y sin fixtures.
#
#   F04-D020 · La ocurrencia k SIEMPRE se calcula como
#
#       origen_del_segmento + k x intervalo
#
#   y NUNCA como `fecha_anterior + intervalo`. La diferencia no es de estilo:
#   sumar sucesivamente arrastra los recortes. Con origen 31/01 y cadencia
#   mensual, el acumulativo da 28/02 y luego 28/03; el correcto da 31/03,
#   porque el recorte afecta SOLO a la ocurrencia que no cabe en su mes y el
#   origen no se mueve. Por eso `ocurrencia()` recibe `k` y no la fecha previa:
#   con esta firma, el error acumulativo no es solo incorrecto, es
#   inexpresable.
#
#   Y el recorte no es "fin de mes". Con origen 30/04 la siguiente mensual es
#   30/05, no 31/05: 30 existe en mayo, de modo que no hay nada que recortar.
#   Inferir fin de mes desde un 30 de abril seria inventar la intencion.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import calendar
import datetime as dt
import decimal
from typing import Iterable, Sequence

from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_prevision import (
    ANUAL,
    CALENDARIO,
    Cadencia,
    DIARIA,
    FECHA_ANCLA,
    FECHA_VENTANA,
    MENSUAL,
    Ocurrencia,
    OcurrenciaHistorica,
    RODANTE,
    SEMANAL,
    Ventana,
)

CERO = decimal.Decimal("0")


# ==================================================================
# F04-D020 — aritmetica de ocurrencias
# ==================================================================

def _ultimo_dia(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def _con_dia_recortado(anio: int, mes: int, dia_ordinal: int) -> dt.date:
    """Fecha en (anio, mes) con el dia ordinal, recortado si no existe.

    El recorte afecta SOLO a esta fecha. El origen del segmento no cambia
    nunca, de modo que la ocurrencia siguiente vuelve a intentar el dia
    original.
    """
    return dt.date(anio, mes, min(dia_ordinal, _ultimo_dia(anio, mes)))


def ocurrencia(origen: dt.date, cadencia: Cadencia, k: int) -> dt.date:
    """Ocurrencia k-esima del segmento. k=0 es el propio origen.

    Se calcula siempre desde el origen. No existe variante acumulativa.
    """
    if k < 0:
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA, "El indice de ocurrencia no puede ser negativo."
        )
    if not cadencia.recurrente:
        raise ErrorMotor(
            CodigoError.CADENCIA_INVALIDA,
            "La version no define cadencia: no genera ocurrencias.",
        )
    paso = int(cadencia.intervalo) * k

    if cadencia.periodicidad == DIARIA:
        return origen + dt.timedelta(days=paso)
    if cadencia.periodicidad == SEMANAL:
        return origen + dt.timedelta(weeks=paso)
    if cadencia.periodicidad == MENSUAL:
        total = (origen.year * 12 + origen.month - 1) + paso
        return _con_dia_recortado(total // 12, total % 12 + 1, origen.day)
    if cadencia.periodicidad == ANUAL:
        # 29/02 vuelve a 29/02 en cuanto el ano destino es bisiesto: el dia
        # ordinal del origen se conserva y solo se recorta donde no cabe.
        return _con_dia_recortado(origen.year + paso, origen.month, origen.day)
    raise ErrorMotor(
        CodigoError.CADENCIA_INVALIDA,
        "Periodicidad no soportada.",
    )


def ocurrencias_hasta(
    origen: dt.date,
    cadencia: Cadencia,
    *,
    hasta_fecha: dt.date | None = None,
    max_ocurrencias: int | None = None,
    desde_fecha: dt.date | None = None,
) -> list[dt.date]:
    """Ocurrencias del segmento dentro de un horizonte FINITO.

    Exige al menos uno de los dos limites. No existe generacion infinita: un
    bucle sin tope materializaria futuro indefinido, y una previsión
    materializada es una fila real con auditoria, no una vista.
    """
    if hasta_fecha is None and max_ocurrencias is None:
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA,
            "La generacion exige un limite explicito: hasta_fecha o "
            "max_ocurrencias.",
        )
    if max_ocurrencias is not None and max_ocurrencias < 1:
        raise ErrorMotor(
            CodigoError.ENTRADA_INVALIDA, "max_ocurrencias debe ser al menos 1."
        )

    salida: list[dt.date] = []
    k = 0
    # Tope duro de seguridad: con hasta_fecha puede no haber max_ocurrencias, y
    # una cadencia mal formada no debe poder colgar el proceso.
    tope = max_ocurrencias if max_ocurrencias is not None else 10_000
    while len(salida) < tope:
        fecha = ocurrencia(origen, cadencia, k)
        k += 1
        if hasta_fecha is not None and fecha > hasta_fecha:
            break
        if desde_fecha is not None and fecha < desde_fecha:
            continue
        salida.append(fecha)
        if max_ocurrencias is not None and len(salida) >= max_ocurrencias:
            break
    return salida


def es_ocurrencia(
    origen: dt.date, cadencia: Cadencia, objetivo: dt.date
) -> bool:
    """True si `objetivo` es una ocurrencia exacta del segmento.

    Se usa para decidir si una identidad ya materializada SIGUE perteneciendo
    al calendario vigente tras un cambio de cadencia. Se compara contra la
    serie generada desde el origen, nunca por aritmetica inversa: una division
    daria falsos positivos en cuanto hay recortes de mes, porque el paso entre
    ocurrencias no es constante en dias.
    """
    if objetivo < origen or not cadencia.recurrente:
        return False
    for k in range(0, 10_000):
        fecha = ocurrencia(origen, cadencia, k)
        if fecha == objetivo:
            return True
        if fecha > objetivo:
            return False
    return False  # pragma: no cover - horizonte agotado


# ==================================================================
# Ventanas
# ==================================================================

def ventana_de(
    fecha_objetivo: dt.date,
    *,
    fecha_modo: str,
    dia_desde: int | None = None,
    dia_hasta: int | None = None,
    fecha_override: dt.date | None = None,
) -> Ventana:
    """Ventana esperada de una ocurrencia.

    En modo ANCLA la ventana es un punto. En modo VENTANA se usan los dias del
    MES DE LA OCURRENCIA, recortando cada limite al ultimo dia valido de ese
    mes. Un `fecha_override` convierte la ocurrencia en fecha puntual y no
    altera el objetivo canonico.
    """
    if fecha_override is not None:
        return Ventana(fecha_override, fecha_override)

    if fecha_modo == FECHA_ANCLA:
        return Ventana(fecha_objetivo, fecha_objetivo)

    if fecha_modo == FECHA_VENTANA:
        if dia_desde is None or dia_hasta is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "fecha_modo=VENTANA exige dia_desde y dia_hasta.",
            )
        desde = _con_dia_recortado(fecha_objetivo.year, fecha_objetivo.month, dia_desde)
        hasta = _con_dia_recortado(fecha_objetivo.year, fecha_objetivo.month, dia_hasta)
        if desde > hasta:  # pragma: no cover - el CHECK fisico exige desde<=hasta
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Tras el recorte, la ventana quedaria invertida.",
            )
        return Ventana(desde, hasta)

    raise ErrorMotor(
        CodigoError.CALENDARIO_ENTIDAD_NO_SOPORTADO,
        "fecha_modo=CALENDARIO_ENTIDAD exige un adaptador de dominio "
        "autoritativo; no se deducen fechas de nombres, categorias, notas ni "
        "importes.",
    )


def exigir_anclaje_compatible(cadencia: Cadencia, fecha_modo: str) -> None:
    """RODANTE solo admite fecha_modo=ANCLA.

    Tambien lo impone un CHECK de 0310. Se duplica aqui para dar un error de
    dominio legible antes de tocar la base.
    """
    if cadencia.anclaje == RODANTE and fecha_modo != FECHA_ANCLA:
        raise ErrorMotor(
            CodigoError.ANCLAJE_INVALIDO,
            "RODANTE solo admite fecha_modo=ANCLA: una cadena de cabeza unica "
            "no tiene ventana.",
        )


# ==================================================================
# Segmentos y transiciones
# ==================================================================

def rompe_segmento(
    anterior: Cadencia | None,
    nueva: Cadencia,
    *,
    hay_pausa: bool,
) -> bool:
    """True si la nueva version inicia un segmento nuevo.

    Rompen: pausa, cambio de periodicidad, cambio de intervalo y cualquier
    cambio de anclaje. NO rompen: importe, categoria, tercero, cuentas ni
    ningun otro parametro que no sea de cadencia. Y no existe reanclaje
    voluntario manteniendo exactamente la misma cadencia: si alguien lo
    necesitase, seria una decision nueva, no una inferencia.
    """
    if anterior is None or hay_pausa:
        return True
    return not anterior.misma_cadencia(nueva)


def origen_de_segmento_nuevo(
    *,
    vigente_desde: dt.date,
    anterior: Cadencia | None,
    nueva: Cadencia,
    ancla_terminal_previa: dt.date | None = None,
) -> dt.date:
    """Origen del segmento que comienza en `vigente_desde`.

    CALENDARIO reinicia SIEMPRE desde `vigente_desde`, incluso viniendo de
    RODANTE: no hereda la ultima fecha real ni crea atrasos previos.

    CALENDARIO -> RODANTE usa como ancla la ultima ocurrencia terminal valida
    del segmento anterior, y el primer candidato es
    `max(ancla + intervalo_nuevo, vigente_desde)`. Sin terminal previa
    defendible, `vigente_desde`.
    """
    if nueva.anclaje == CALENDARIO:
        return vigente_desde

    if (
        anterior is not None
        and anterior.anclaje == CALENDARIO
        and ancla_terminal_previa is not None
    ):
        candidato = ocurrencia(ancla_terminal_previa, nueva, 1)
        return max(candidato, vigente_desde)

    return vigente_desde


def primer_candidato_libre(
    origen: dt.date,
    cadencia: Cadencia,
    identidades_consumidas: Iterable[dt.date],
) -> dt.date:
    """Avanza por cadencia hasta la primera identidad no consumida.

    Una identidad CANCELADA es un tombstone permanente: no se reutiliza ni en
    un retry ni al cambiar de segmento. Reutilizarla resucitaria una ocurrencia
    que alguien decidio cancelar.
    """
    consumidas = set(identidades_consumidas)
    for k in range(0, 10_000):
        candidato = ocurrencia(origen, cadencia, k)
        if candidato not in consumidas:
            return candidato
    raise ErrorMotor(  # pragma: no cover - inalcanzable en la practica
        CodigoError.CADENCIA_INVALIDA,
        "No se encontro ninguna identidad libre en el horizonte explorado.",
    )


def ancla_rodante(
    *,
    estado: str,
    fecha_real_maxima: dt.date | None,
    fecha_objetivo: dt.date,
    hechos_activos: int,
) -> dt.date | None:
    """Ancla para calcular el sucesor de una cabeza RODANTE terminada.

    REALIZADA con realidad ACTIVA: la fecha real mayor de sus hechos activos.
    OMITIDA: el objetivo canonico, NUNCA un fecha_override.
    CANCELADA: no hay sucesor.
    REALIZADA sin realidad activa (AMB-009): la cadena queda bloqueada y NO se
    usa el objetivo como respaldo de una realidad que ya no existe.
    Devuelve None cuando no corresponde generar sucesor.
    """
    from app.core.modelos_prevision import CANCELADA, OMITIDA, REALIZADA

    if estado == REALIZADA:
        if hechos_activos == 0 or fecha_real_maxima is None:
            return None
        return fecha_real_maxima
    if estado == OMITIDA:
        return fecha_objetivo
    if estado == CANCELADA:
        return None
    return None


# ==================================================================
# Estimacion de importe
# ==================================================================

def historicos_elegibles(
    historicos: Sequence[OcurrenciaHistorica],
    *,
    objetivo: dt.date,
    moneda: str,
    meses_historico: int | None = None,
) -> list[OcurrenciaHistorica]:
    """Filtra la muestra historica.

    El corte se hace por IDENTIDAD de ocurrencia (`fecha_objetivo`), no por
    fecha bancaria: una factura pagada tarde no debe desplazar la muestra.

    La moneda distinta EXCLUYE la ocurrencia. No se convierte, no se consulta
    FX y no se inventa tipo de cambio.
    """
    limite: dt.date | None = None
    if meses_historico is not None:
        total = (objetivo.year * 12 + objetivo.month - 1) - meses_historico
        limite = _con_dia_recortado(total // 12, total % 12 + 1, objetivo.day)

    return [
        h
        for h in historicos
        if h.fecha_objetivo < objetivo
        and h.moneda == moneda
        and (limite is None or h.fecha_objetivo >= limite)
    ]


def media_historica(muestra: Sequence[OcurrenciaHistorica]) -> decimal.Decimal | None:
    """Media aritmetica exacta. Sin muestra devuelve None, nunca 0.

    No se redondea aqui: el redondeo monetario pertenece a la materializacion
    o a la presentacion, y redondear intermedios desplaza el resultado.
    """
    if not muestra:
        return None
    total = sum((h.importe_real for h in muestra), start=CERO)
    return total / decimal.Decimal(len(muestra))


def mediana_historica(muestra: Sequence[OcurrenciaHistorica]) -> decimal.Decimal | None:
    """Mediana exacta. Con numero par, media de los dos centrales."""
    if not muestra:
        return None
    valores = sorted(h.importe_real for h in muestra)
    mitad = len(valores) // 2
    if len(valores) % 2 == 1:
        return valores[mitad]
    return (valores[mitad - 1] + valores[mitad]) / decimal.Decimal(2)


def ultimo_real(muestra: Sequence[OcurrenciaHistorica]) -> decimal.Decimal | None:
    """Importe de la ocurrencia elegible con mayor `fecha_objetivo`.

    Por objetivo, NO por `created_at` ni por la fecha del movimiento bancario:
    lo que ordena la serie es la identidad de la ocurrencia, no cuando se
    capturo el dato.
    """
    if not muestra:
        return None
    return max(muestra, key=lambda h: h.fecha_objetivo).importe_real


def importe_por_saldo_objetivo(
    *,
    saldo_real: decimal.Decimal | None,
    saldo_objetivo: decimal.Decimal,
    flujo: str,
) -> decimal.Decimal | None:
    """Magnitud necesaria para alcanzar el objetivo de saldo.

    Devuelve None cuando el saldo real es INDETERMINADO: no se asume cero.
    Devuelve CERO cuando el objetivo ya se cumple, y es el llamante quien debe
    tratar ese caso como omision determinista en vez de crear una previsión
    monetaria de importe 0.
    Si la necesidad va en sentido contrario al flujo configurado, es error de
    configuracion: no se cambia automaticamente SALIDA por ENTRADA.
    """
    from app.core.modelos_prevision import FLUJO_ENTRADA, FLUJO_SALIDA

    if saldo_real is None:
        return None
    necesidad = decimal.Decimal(saldo_objetivo) - decimal.Decimal(saldo_real)
    if necesidad == CERO:
        return CERO
    if necesidad > CERO and flujo == FLUJO_ENTRADA:
        return necesidad
    if necesidad < CERO and flujo == FLUJO_SALIDA:
        return -necesidad
    raise ErrorMotor(
        CodigoError.RESULTADO_SALDO_OBJETIVO_INCOMPATIBLE,
        "El ajuste necesario va en sentido contrario al flujo configurado.",
    )
