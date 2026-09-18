# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_111_recurrencia_pura.py
# Ruta: tests/backend/test_111_recurrencia_pura.py
# Descripcion: F04-05. Aritmetica pura de recurrencia, ventanas, segmentos,
#   transiciones de anclaje y estimacion de importe.
#
#   Sin base de datos y sin fixtures: estos helpers son puros a proposito,
#   porque es donde vive F04-D020 y una regla aritmetica solo se discrimina
#   bien si se prueba aislada con vectores exactos.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal

import pytest

from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_prevision import (
    ANUAL,
    CALENDARIO,
    Cadencia,
    DIARIA,
    FECHA_ANCLA,
    FECHA_CALENDARIO_ENTIDAD,
    FECHA_VENTANA,
    FLUJO_ENTRADA,
    FLUJO_SALIDA,
    MENSUAL,
    OcurrenciaHistorica,
    RODANTE,
    SEMANAL,
)
from app.core import recurrencia as r

D = decimal.Decimal
F = dt.date.fromisoformat

MENSUAL_1 = Cadencia(MENSUAL, 1, CALENDARIO)
ANUAL_1 = Cadencia(ANUAL, 1, CALENDARIO)


def serie(origen: str, n: int, cadencia: Cadencia = MENSUAL_1) -> list[str]:
    return [r.ocurrencia(F(origen), cadencia, k).isoformat() for k in range(1, n + 1)]


# ==================================================================
# F04-D020
# ==================================================================

def test_d020_origen_31_de_enero() -> None:
    """El recorte afecta SOLO a la ocurrencia que no cabe; el origen no cambia."""
    assert serie("2027-01-31", 4) == [
        "2027-02-28",
        "2027-03-31",
        "2027-04-30",
        "2027-05-31",
    ]


def test_d020_origen_30_de_enero() -> None:
    assert serie("2027-01-30", 4) == [
        "2027-02-28",
        "2027-03-30",
        "2027-04-30",
        "2027-05-30",
    ]


def test_d020_origen_30_de_abril_no_es_fin_de_mes() -> None:
    """30/04 -> 30/05, NUNCA 31/05. No se infiere "fin de mes" desde un 30."""
    assert serie("2027-04-30", 1) == ["2027-05-30"]


def test_d020_29_de_febrero_anual_vuelve_en_bisiesto() -> None:
    assert serie("2028-02-29", 4, ANUAL_1) == [
        "2029-02-28",
        "2030-02-28",
        "2031-02-28",
        "2032-02-29",
    ]


def test_d020_k_directo_coincide_con_la_serie_completa() -> None:
    """Generar k=12 directamente debe dar lo mismo que generar todas y coger
    la doceava. Un calculo acumulativo falla aqui: arrastraria el recorte de
    febrero y daria 28/01/2028 en vez de 31/01/2028."""
    origen = F("2027-01-31")
    directo = r.ocurrencia(origen, MENSUAL_1, 12)
    completa = r.ocurrencias_hasta(origen, MENSUAL_1, max_ocurrencias=13)[12]
    assert directo == completa == F("2028-01-31")


def test_d020_todas_las_k_coinciden_con_la_serie() -> None:
    """Version reforzada: la equivalencia se comprueba en TODO el horizonte,
    no solo en k=12. Es el test que mata un mutante acumulativo en la primera
    ocurrencia recortada."""
    origen = F("2027-01-31")
    completa = r.ocurrencias_hasta(origen, MENSUAL_1, max_ocurrencias=25)
    for k, esperada in enumerate(completa):
        assert r.ocurrencia(origen, MENSUAL_1, k) == esperada, k


@pytest.mark.parametrize(
    "periodicidad, intervalo, origen, esperada",
    [
        (DIARIA, 1, "2027-01-31", "2027-02-01"),
        (DIARIA, 10, "2027-01-25", "2027-02-04"),
        (SEMANAL, 5, "2027-01-10", "2027-02-14"),
        (MENSUAL, 2, "2027-01-31", "2027-03-31"),
        (ANUAL, 1, "2027-03-15", "2028-03-15"),
    ],
)
def test_d020_otras_periodicidades(periodicidad, intervalo, origen, esperada) -> None:
    cadencia = Cadencia(periodicidad, intervalo, CALENDARIO)
    assert r.ocurrencia(F(origen), cadencia, 1) == F(esperada)


def test_k_cero_es_el_origen() -> None:
    assert r.ocurrencia(F("2027-01-31"), MENSUAL_1, 0) == F("2027-01-31")


def test_indice_negativo_rechazado() -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        r.ocurrencia(F("2027-01-31"), MENSUAL_1, -1)
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_version_sin_cadencia_no_genera() -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        r.ocurrencia(F("2027-01-31"), Cadencia(None, None, None), 1)
    assert excinfo.value.codigo is CodigoError.CADENCIA_INVALIDA


# ==================================================================
# Generacion finita
# ==================================================================

def test_la_generacion_exige_un_limite_explicito() -> None:
    """No existe generacion infinita: una previsión materializada es una fila
    real con auditoria, no una vista."""
    with pytest.raises(ErrorMotor) as excinfo:
        r.ocurrencias_hasta(F("2027-01-31"), MENSUAL_1)
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_limite_por_fecha() -> None:
    fechas = r.ocurrencias_hasta(
        F("2027-01-31"), MENSUAL_1, hasta_fecha=F("2027-05-31")
    )
    assert [f.isoformat() for f in fechas] == [
        "2027-01-31",
        "2027-02-28",
        "2027-03-31",
        "2027-04-30",
        "2027-05-31",
    ]


def test_limite_por_numero() -> None:
    assert len(r.ocurrencias_hasta(F("2027-01-31"), MENSUAL_1, max_ocurrencias=3)) == 3


def test_max_ocurrencias_cero_rechazado() -> None:
    with pytest.raises(ErrorMotor):
        r.ocurrencias_hasta(F("2027-01-31"), MENSUAL_1, max_ocurrencias=0)


def test_ventana_inferior_filtra_sin_mover_el_origen() -> None:
    fechas = r.ocurrencias_hasta(
        F("2027-01-31"),
        MENSUAL_1,
        desde_fecha=F("2027-04-01"),
        hasta_fecha=F("2027-05-31"),
    )
    assert [f.isoformat() for f in fechas] == ["2027-04-30", "2027-05-31"]


# ==================================================================
# Ventanas
# ==================================================================

def test_modo_ancla_es_un_punto() -> None:
    v = r.ventana_de(F("2027-03-10"), fecha_modo=FECHA_ANCLA)
    assert v.desde == v.hasta == F("2027-03-10")


def test_modo_ventana_recorta_cada_limite_al_mes() -> None:
    v = r.ventana_de(
        F("2027-02-28"), fecha_modo=FECHA_VENTANA, dia_desde=25, dia_hasta=31
    )
    assert (v.desde.isoformat(), v.hasta.isoformat()) == ("2027-02-25", "2027-02-28")


def test_modo_ventana_exige_los_dos_dias() -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        r.ventana_de(F("2027-03-10"), fecha_modo=FECHA_VENTANA, dia_desde=5)
    assert excinfo.value.codigo is CodigoError.ENTRADA_INVALIDA


def test_override_convierte_la_ocurrencia_en_punto() -> None:
    """Y no altera el objetivo canonico: eso lo garantiza el write-path."""
    v = r.ventana_de(
        F("2027-03-10"),
        fecha_modo=FECHA_VENTANA,
        dia_desde=5,
        dia_hasta=15,
        fecha_override=F("2027-03-22"),
    )
    assert v.desde == v.hasta == F("2027-03-22")


def test_calendario_entidad_sin_adaptador_no_se_inventa() -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        r.ventana_de(F("2027-03-10"), fecha_modo=FECHA_CALENDARIO_ENTIDAD)
    assert excinfo.value.codigo is CodigoError.CALENDARIO_ENTIDAD_NO_SOPORTADO


def test_rodante_con_ventana_rechazado() -> None:
    with pytest.raises(ErrorMotor) as excinfo:
        r.exigir_anclaje_compatible(Cadencia(MENSUAL, 1, RODANTE), FECHA_VENTANA)
    assert excinfo.value.codigo is CodigoError.ANCLAJE_INVALIDO


def test_rodante_con_ancla_permitido() -> None:
    r.exigir_anclaje_compatible(Cadencia(MENSUAL, 1, RODANTE), FECHA_ANCLA)


# ==================================================================
# Segmentos
# ==================================================================

def test_cambio_de_importe_no_rompe_segmento() -> None:
    """Importe, categoria o tercero no son cadencia: el calendario continua."""
    assert (
        r.rompe_segmento(MENSUAL_1, Cadencia(MENSUAL, 1, CALENDARIO), hay_pausa=False)
        is False
    )


@pytest.mark.parametrize(
    "nueva",
    [
        Cadencia(SEMANAL, 1, CALENDARIO),
        Cadencia(MENSUAL, 2, CALENDARIO),
        Cadencia(MENSUAL, 1, RODANTE),
    ],
)
def test_cambio_de_cadencia_rompe_segmento(nueva) -> None:
    assert r.rompe_segmento(MENSUAL_1, nueva, hay_pausa=False) is True


def test_la_pausa_rompe_segmento() -> None:
    assert (
        r.rompe_segmento(MENSUAL_1, Cadencia(MENSUAL, 1, CALENDARIO), hay_pausa=True)
        is True
    )


def test_sin_version_anterior_hay_segmento_nuevo() -> None:
    assert r.rompe_segmento(None, MENSUAL_1, hay_pausa=False) is True


# ==================================================================
# Transiciones de anclaje
# ==================================================================

def test_rodante_a_calendario_reinicia_en_vigente_desde() -> None:
    """No hereda la ultima fecha real RODANTE ni crea atrasos previos."""
    origen = r.origen_de_segmento_nuevo(
        vigente_desde=F("2027-07-01"),
        anterior=Cadencia(MENSUAL, 1, RODANTE),
        nueva=MENSUAL_1,
        ancla_terminal_previa=F("2027-06-18"),
    )
    assert origen == F("2027-07-01")


def test_calendario_a_rodante_ancla_en_la_terminal_previa() -> None:
    origen = r.origen_de_segmento_nuevo(
        vigente_desde=F("2027-07-01"),
        anterior=MENSUAL_1,
        nueva=Cadencia(MENSUAL, 1, RODANTE),
        ancla_terminal_previa=F("2027-06-30"),
    )
    assert origen == F("2027-07-30")


def test_calendario_a_rodante_nunca_antes_de_vigente_desde() -> None:
    origen = r.origen_de_segmento_nuevo(
        vigente_desde=F("2027-09-01"),
        anterior=MENSUAL_1,
        nueva=Cadencia(MENSUAL, 1, RODANTE),
        ancla_terminal_previa=F("2027-01-31"),
    )
    assert origen == F("2027-09-01")


def test_sin_terminal_previa_defendible_usa_vigente_desde() -> None:
    origen = r.origen_de_segmento_nuevo(
        vigente_desde=F("2027-07-01"),
        anterior=MENSUAL_1,
        nueva=Cadencia(MENSUAL, 1, RODANTE),
        ancla_terminal_previa=None,
    )
    assert origen == F("2027-07-01")


def test_una_identidad_cancelada_no_se_reutiliza() -> None:
    """Tombstone permanente: se avanza por cadencia hasta la primera libre."""
    libre = r.primer_candidato_libre(
        F("2027-07-30"),
        Cadencia(MENSUAL, 1, RODANTE),
        [F("2027-07-30"), F("2027-08-30")],
    )
    assert libre == F("2027-09-30")


# ==================================================================
# Ancla RODANTE
# ==================================================================

def test_realizada_ancla_en_la_fecha_real_maxima() -> None:
    assert r.ancla_rodante(
        estado="REALIZADA",
        fecha_real_maxima=F("2027-02-02"),
        fecha_objetivo=F("2027-01-10"),
        hechos_activos=2,
    ) == F("2027-02-02")


def test_omitida_ancla_en_el_objetivo_canonico() -> None:
    """Nunca en un fecha_override: la omision avanza desde la identidad."""
    assert r.ancla_rodante(
        estado="OMITIDA",
        fecha_real_maxima=None,
        fecha_objetivo=F("2027-01-10"),
        hechos_activos=0,
    ) == F("2027-01-10")


def test_cancelada_no_genera_sucesor() -> None:
    assert (
        r.ancla_rodante(
            estado="CANCELADA",
            fecha_real_maxima=None,
            fecha_objetivo=F("2027-01-10"),
            hechos_activos=0,
        )
        is None
    )


def test_abierta_no_genera_sucesor() -> None:
    assert (
        r.ancla_rodante(
            estado="ABIERTA",
            fecha_real_maxima=F("2027-01-20"),
            fecha_objetivo=F("2027-01-10"),
            hechos_activos=1,
        )
        is None
    )


def test_realizada_sin_realidad_activa_bloquea_la_cadena() -> None:
    """AMB-009: no se usa el objetivo como respaldo de una realidad que ya no
    existe."""
    assert (
        r.ancla_rodante(
            estado="REALIZADA",
            fecha_real_maxima=None,
            fecha_objetivo=F("2027-01-10"),
            hechos_activos=0,
        )
        is None
    )


def test_vector_gimnasio_d126() -> None:
    """Cadencia 5 semanas. Objetivo 10/01, realidad 02/02, REALIZADA.
    Siguiente objetivo RODANTE: 09/03."""
    cadencia = Cadencia(SEMANAL, 5, RODANTE)
    ancla = r.ancla_rodante(
        estado="REALIZADA",
        fecha_real_maxima=F("2027-02-02"),
        fecha_objetivo=F("2027-01-10"),
        hechos_activos=1,
    )
    assert ancla == F("2027-02-02")
    assert r.ocurrencia(ancla, cadencia, 1) == F("2027-03-09")


# ==================================================================
# Estimacion de importe
# ==================================================================

def historico(fecha: str, importe: str, moneda: str = "EUR") -> OcurrenciaHistorica:
    return OcurrenciaHistorica(F(fecha), D(importe), moneda)


def test_solo_participan_ocurrencias_anteriores() -> None:
    muestra = r.historicos_elegibles(
        [historico("2027-01-10", "100"), historico("2027-05-10", "900")],
        objetivo=F("2027-03-10"),
        moneda="EUR",
    )
    assert [h.importe_real for h in muestra] == [D("100")]


def test_moneda_incompatible_excluida_sin_convertir() -> None:
    """Sin FX inventado: el historico en otra divisa simplemente no participa."""
    muestra = r.historicos_elegibles(
        [historico("2027-01-10", "100", "USD"), historico("2027-02-10", "80")],
        objetivo=F("2027-03-10"),
        moneda="EUR",
    )
    assert [h.importe_real for h in muestra] == [D("80")]


def test_ventana_meses_corta_por_identidad_de_ocurrencia() -> None:
    """Una factura pagada tarde no desplaza la muestra: el corte es por
    fecha_objetivo, no por fecha bancaria."""
    muestra = r.historicos_elegibles(
        [
            historico("2026-09-10", "10"),
            historico("2027-01-10", "20"),
            historico("2027-02-10", "30"),
        ],
        objetivo=F("2027-03-10"),
        moneda="EUR",
        meses_historico=3,
    )
    assert [h.importe_real for h in muestra] == [D("20"), D("30")]


def test_media_exacta_sin_redondeo_intermedio() -> None:
    muestra = [historico("2027-01-10", "10"), historico("2027-02-10", "11")]
    assert r.media_historica(muestra) == D("10.5")


def test_media_sin_historicos_es_none_no_cero() -> None:
    assert r.media_historica([]) is None


def test_mediana_impar() -> None:
    muestra = [
        historico("2027-01-10", "10"),
        historico("2027-02-10", "100"),
        historico("2027-03-10", "20"),
    ]
    assert r.mediana_historica(muestra) == D("20")


def test_mediana_par_es_media_de_los_dos_centrales() -> None:
    muestra = [
        historico("2027-01-10", "10"),
        historico("2027-02-10", "20"),
        historico("2027-03-10", "30"),
        historico("2027-04-10", "50"),
    ]
    assert r.mediana_historica(muestra) == D("25")


def test_mediana_sin_historicos_es_none() -> None:
    assert r.mediana_historica([]) is None


def test_ultimo_real_ordena_por_objetivo_no_por_captura() -> None:
    """La serie la ordena la identidad de la ocurrencia, no cuando se capturo
    el dato ni la fecha del movimiento.

    El ORDEN DE LA LISTA contradice a proposito el orden por objetivo: el
    mayor objetivo va en ultima posicion y el menor en primera. Con la muestra
    ya ordenada, una implementacion que devolviese `muestra[0]` coincidiria por
    casualidad y el test pasaria por el motivo equivocado.
    """
    muestra = [
        historico("2027-01-10", "100"),
        historico("2027-03-10", "300"),
        historico("2027-02-10", "200"),
    ]
    assert r.ultimo_real(muestra) == D("300")


def test_ultimo_real_indiferente_al_orden_de_la_muestra() -> None:
    """Mismo conjunto, tres ordenaciones distintas, mismo resultado."""
    base = [
        historico("2027-01-10", "100"),
        historico("2027-03-10", "300"),
        historico("2027-02-10", "200"),
    ]
    for muestra in (base, list(reversed(base)), sorted(base, key=lambda h: h.importe_real)):
        assert r.ultimo_real(muestra) == D("300")


def test_ultimo_real_sin_historicos_es_none() -> None:
    assert r.ultimo_real([]) is None


# ==================================================================
# SALDO_OBJETIVO
# ==================================================================

def test_saldo_objetivo_con_saldo_conocido() -> None:
    assert (
        r.importe_por_saldo_objetivo(
            saldo_real=D("300"), saldo_objetivo=D("1000"), flujo=FLUJO_ENTRADA
        )
        == D("700")
    )


def test_saldo_objetivo_con_saldo_indeterminado_es_none() -> None:
    """No se asume cero: un saldo desconocido no produce una necesidad de 1000."""
    assert (
        r.importe_por_saldo_objetivo(
            saldo_real=None, saldo_objetivo=D("1000"), flujo=FLUJO_ENTRADA
        )
        is None
    )


def test_saldo_objetivo_ya_cumplido_devuelve_cero() -> None:
    """Y el llamante debe tratarlo como omision determinista, no crear una
    previsión monetaria de importe 0."""
    assert (
        r.importe_por_saldo_objetivo(
            saldo_real=D("1000"), saldo_objetivo=D("1000"), flujo=FLUJO_ENTRADA
        )
        == D("0")
    )


def test_saldo_objetivo_en_sentido_contrario_es_error_de_configuracion() -> None:
    """No se cambia automaticamente SALIDA por ENTRADA."""
    with pytest.raises(ErrorMotor) as excinfo:
        r.importe_por_saldo_objetivo(
            saldo_real=D("300"), saldo_objetivo=D("1000"), flujo=FLUJO_SALIDA
        )
    assert excinfo.value.codigo is CodigoError.RESULTADO_SALDO_OBJETIVO_INCOMPATIBLE


def test_saldo_objetivo_exceso_con_flujo_salida() -> None:
    assert (
        r.importe_por_saldo_objetivo(
            saldo_real=D("1500"), saldo_objetivo=D("1000"), flujo=FLUJO_SALIDA
        )
        == D("500")
    )
