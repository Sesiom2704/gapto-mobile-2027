# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14r_f06_t5_e1_c2_dos_reglas.py
# Ruta: tests/backend/test_14r_f06_t5_e1_c2_dos_reglas.py
# Descripcion: F06 T5 E1 · C2 como precondicion real (A §3.1-2, AJ-T5A-04), parte NO concurrente (O-A2):
#   dos reglas CALENDARIO del MISMO owner con previsiones intercaladas en las mismas fechas y en todos los
#   estados (ABIERTA recalculable, REALIZADA, OMITIDA, ABIERTA con pago parcial = congelada F04-D019).
#   `recalcular_futuras` de A, tras una version nueva de A, regobierna SOLO las ABIERTAS recalculables
#   futuras de A; respeta su congelada y sus terminales; y no cambia NINGUNA fila de B (previsiones,
#   vinculos, regla, versiones, excepciones). Y simetrico con B. La intercalacion concurrente esta en
#   test_14s (bateria serial, fuera de la suite general).
# Version: 0.1.0 (F06 T5 E1, mandato T5E1_HITO v1.0 P1.3)
# ============================================================
from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import uuid

import pytest

from app.core.modelos_prevision import DatosRegla, DatosVinculo
from conftest import leer_fila
from test_112_reglas_y_calendario import mapa_mensual, version
from test_113_rodante_y_materializacion import crear_hecho

D = decimal.Decimal
F = dt.date.fromisoformat


@dataclasses.dataclass
class Regla:
    regla_id: uuid.UUID
    version_id: uuid.UUID
    row_version: int
    mapa: dict


def crear_regla_calendario(reg, prev, ctx, nombre: str, importe: str) -> Regla:
    regla_id = uuid.uuid4()
    v = version(importe_fijo=D(importe))
    r = reg.crear_regla(ctx, DatosRegla(regla_id=regla_id, nombre=nombre), v)
    mapa = mapa_mensual(2027, range(1, 13))
    prev.generar_calendario(ctx, regla_id=regla_id, uuids_por_objetivo=mapa, hasta_fecha=F("2027-12-31"))
    return Regla(regla_id, v.version_id, r.regla_row_version, mapa)


def vincular(prev, ctx, prevision_id, hecho_id, importe: str, *, realizar: bool = False):
    e = prev.estado_de(ctx, prevision_id)
    return prev.vincular_realidad(ctx, prevision_id=prevision_id, row_version_esperada=e.row_version,
                                  datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=hecho_id,
                                                     importe_asignado=D(importe), marcar_realizada=realizar))


def estados(hec, prev, ctx, r: Regla, importe: str, *, realizada: int, omitida: int, parcial: int) -> None:
    """Mes `realizada` REALIZADA (realidad completa), `omitida` OMITIDA y `parcial` ABIERTA congelada."""
    hecho = crear_hecho(hec, ctx, F(f"2027-{realizada:02d}-10"), importe=D(importe))
    vincular(prev, ctx, r.mapa[F(f"2027-{realizada:02d}-10")], hecho, importe, realizar=True)
    p = r.mapa[F(f"2027-{omitida:02d}-10")]
    prev.omitir(ctx, prevision_id=p, row_version_esperada=prev.estado_de(ctx, p).row_version, motivo="C2")
    hecho = crear_hecho(hec, ctx, F(f"2027-{parcial:02d}-10"), importe=D("50.0000"))
    vincular(prev, ctx, r.mapa[F(f"2027-{parcial:02d}-10")], hecho, "50.0000")


def foto_regla(admin, owner, regla_id) -> tuple:
    """Huella de TODO el agregado de la regla: regla, versiones, excepciones, previsiones y sus vinculos."""
    sql = """
    SELECT
     (SELECT md5(r::text) FROM gapto.reglas_financieras r WHERE r.id = %(r)s),
     (SELECT md5(coalesce(string_agg(v::text, '|' ORDER BY v.id), '')) FROM gapto.regla_versiones v
       WHERE v.regla_id = %(r)s),
     (SELECT md5(coalesce(string_agg(e::text, '|' ORDER BY e.id), '')) FROM gapto.regla_excepciones e
       WHERE e.regla_id = %(r)s),
     (SELECT md5(coalesce(string_agg(p::text, '|' ORDER BY p.id), '')) FROM gapto.previsiones p
       JOIN gapto.regla_versiones v ON v.id = p.regla_version_id WHERE v.regla_id = %(r)s),
     (SELECT md5(coalesce(string_agg(ph::text, '|' ORDER BY ph.id), '')) FROM gapto.prevision_hechos ph
       JOIN gapto.previsiones p ON p.id = ph.prevision_id
       JOIN gapto.regla_versiones v ON v.id = p.regla_version_id WHERE v.regla_id = %(r)s)
    """
    with admin.cursor() as c:
        c.execute("RESET ROLE")
        c.execute("SELECT set_config('gapto.owner_user_id', %s, false)", (str(owner),))
        try:
            c.execute(sql, {"r": regla_id})
            return c.fetchone()
        finally:
            c.execute("RESET ALL")


def nueva_version(reg, ctx, r: Regla, importe: str, desde: str = "2027-05-01", hasta: str = "2027-04-30"):
    return reg.crear_version(ctx, regla_id=r.regla_id, regla_row_version_esperada=r.row_version,
                             version=version(vigente_desde=F(desde), importe_fijo=D(importe)),
                             cerrar_version_id=r.version_id, cerrar_vigente_hasta=F(hasta))


@pytest.fixture()
def dos(servicio, servicio_reglas, servicio_previsiones, contexto):
    a = crear_regla_calendario(servicio_reglas, servicio_previsiones, contexto, "C2 A", "800.0000")
    b = crear_regla_calendario(servicio_reglas, servicio_previsiones, contexto, "C2 B", "300.0000")
    estados(servicio, servicio_previsiones, contexto, a, "800.0000", realizada=3, omitida=4, parcial=6)
    estados(servicio, servicio_previsiones, contexto, b, "300.0000", realizada=2, omitida=6, parcial=7)
    return a, b


@pytest.mark.parametrize("cual", ["A", "B"])
def test_c2_recalcular_una_regla_no_toca_la_otra(dos, servicio_reglas, servicio_previsiones, contexto, admin, cual):
    a, b = dos
    obj, otra = (a, b) if cual == "A" else (b, a)
    owner = contexto.owner_user_id
    antes_otra = foto_regla(admin, owner, otra.regla_id)
    ver = lambda mes: servicio_previsiones.estado_de(contexto, obj.mapa[F(f"2027-{mes:02d}-10")])  # noqa: E731
    antes = {m: (ver(m).estado, ver(m).importe_esperado) for m in range(1, 13)}
    nueva_version(servicio_reglas, contexto, obj, "999.0000")
    res = servicio_previsiones.recalcular_futuras(contexto, regla_id=obj.regla_id, desde_fecha=F("2027-05-01"),
                                                  motivo="C2")
    despues = {m: (ver(m).estado, ver(m).importe_esperado) for m in range(1, 13)}
    assert foto_regla(admin, owner, otra.regla_id) == antes_otra                       # O-A2: B intacta
    for m in range(1, 5):
        assert despues[m] == antes[m]                                                  # el pasado no cambia
    terminales_o_congeladas = {m for m in range(5, 13) if antes[m][0] != "ABIERTA"} | (
        {6} if cual == "A" else {7})
    for m in range(5, 13):
        if m in terminales_o_congeladas:
            assert despues[m] == antes[m], m                                           # terminal / congelada
        else:
            assert despues[m] == ("ABIERTA", D("999.0000")), m                         # regobernada
    regobernadas = {servicio_previsiones.estado_de(contexto, p).fecha_objetivo_regla for p in res.regobernadas}
    assert regobernadas == {F(f"2027-{m:02d}-10") for m in range(5, 13) if m not in terminales_o_congeladas}
