# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_285_f04_r_hip_frontera_f05.py
# Ruta: tests/api/test_285_f04_r_hip_frontera_f05.py
# Descripcion: T3-F06 · F04-R-HIP, subhito F05 (literal F05 v1.2, S1-S10;
#   mandato v1.2 §9 y adenda v1.3 con D-08). Por HTTP, como gapto_runtime con
#   RLS; fixtures sinteticos con la forma del contrato v0.4
#   (tests/backend/f04_r_hip_formas.py), creados bajo gapto_owner donde el
#   motor no escribe. Un negativo discriminante por superficie, en cuota y en
#   Hd, con estado identico, y el oraculo de lectura de cada superficie:
#     O-H22-S1 reparto (REPARTO_NO_CORREGIBLE, motivo HECHO_DE_FINANCIACION);
#     O-H22-S2 devoluciones y abono; O-H22-S3 anular por duplicado (frontera:
#       HECHO_DE_FINANCIACION, no el codigo de motor A9: O-A9-S3);
#     O-H22-S4 corregir pago y transferencia; O-H22-S5 corregir categoria V3;
#     O-H22-S7 vincular, omitir, dar por cubierta y, O-H35, reabrir;
#     O-H22-S8 posiciones (no regresion: POSICION_NO_ENCONTRADA);
#     O-H22-S10-{GP,GC,IC,TR}-{T,F} (PREVISION_DE_CUOTA) y O-H22-S10-L.
#   S6 (suplementos) y la frontera B3 se prueban por no alcanzabilidad en
#   test_286. Reloj fijo 2026-10-10; fechas fijas; ORDER BY en los oraculos.
# Version: 0.1.0 (F06 T3-F06 · F04-R-HIP, paso 4)
# Version: 0.1.1 (F06 T3-F06 · F04-R-HIP, STOP n.º 2): el oraculo de candidatos de la prevision de
#   una cuota exige el mensaje de la cuota (MF05-L-candidatos-cuota sobrevivia por «sin criterio»).
# ============================================================

from __future__ import annotations

import decimal
import pathlib
import sys
import uuid

import pytest

import f05_01_helpers as fh
import f05_05_helpers as x
import f05_06_m2_helpers as m2
import f05_06_m3_helpers as m3
import f05_06_m5_helpers as m
import vs01_api_helpers as h

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
import f04_r_hip_formas as fz  # noqa: E402

D = decimal.Decimal
HF = "HECHO_DE_FINANCIACION"
PC = "PREVISION_DE_CUOTA"


class Esc:
    def __init__(self):
        self.owner, self.actor, self.cli, self.cta, self.ahorro = m.entorno()
        self.dsn = h.dsn()

    def u(self):
        return fh.unidad()

    def ctx(self):
        return m.ctx(self.owner)

    def financiacion(self, prevision_id=None, v3=False):
        return fz.financiacion(self.dsn, self.owner, prevision_id=prevision_id, v3=v3)

    def cuota(self, *, conciliada=True, prevision=True, realizada=False, vincular=True, categoria=None):
        pid = m.prevision(self.owner, "Cuota 1 hipoteca", importe="500.00", cuenta_salida=self.cta,
                          desde="2026-10-01") if prevision else None
        entidad, cuota = self.financiacion(pid)
        f = fz.cuota_pagada(self.dsn, self.u(), self.ctx(), self.owner, entidad,
                            cuenta_id=self.cta if conciliada else None, actor_id=self.actor, vincular=vincular,
                            categoria_id=categoria)
        if realizada:
            from app.core.modelos_prevision import DatosVinculo
            from app.services.previsiones_service import PrevisionesService
            PrevisionesService(self.u()).vincular_realidad(
                self.ctx(), prevision_id=pid, row_version_esperada=m.version(self.owner, pid),
                datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=f.hecho_id, importe_asignado=fz.CUOTA,
                                   marcar_realizada=True))
        return pid, cuota, f

    def hd(self, *, conciliada=True):
        entidad, _ = self.financiacion()
        return fz.desembolso_hd(self.dsn, self.u(), self.ctx(), self.owner, entidad,
                                cuenta_id=self.cta if conciliada else None)

    def forma(self, tipo):
        if tipo == "cuota":
            pid, cuota, f = self.cuota()
            return f, pid, cuota
        return self.hd(), None, None

    def foto(self, f, pid=None, cuota=None):
        return fz.foto(self.dsn, self.owner, f.hecho_id, pid, cuota)

    def movimientos_rv(self, f):
        return {str(mv[0]): mv[2] for mv in self.foto(f)["movimientos"]}


@pytest.fixture()
def esc():
    return Esc()


def _rechazo(r, status, codigo):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text
    return r.json()


TIPOS = ["cuota", "hd"]


# ------------------------------------------------------------------ S1 reparto

@pytest.mark.parametrize("tipo", TIPOS)
def test_o_h22_s1_reparto_rechaza_y_la_lectura_es_veraz(esc, tipo) -> None:
    f, pid, cuota = esc.forma(tipo)
    lectura = esc.cli.get(f"/v1/hechos/{f.hecho_id}/reparto", headers=h.AUTH).json()
    assert (lectura["corregible"], lectura["motivo"]) == (False, HF)
    partes = {uuid.uuid4(): "1.00"}  # Hd: sin reparto (en el HEAD de inicio, TIPO_NO_ADMITIDO)
    if tipo == "cuota":
        partes = {m3.atribucion_de(esc.owner, f.hecho_id, esc.actor): "100.00"}
    antes = esc.foto(f, pid, cuota)
    j = _rechazo(m3.corregir(esc.cli, f.hecho_id, f.version, partes), 409, "REPARTO_NO_CORREGIBLE")
    assert j["detalle"] == {"motivo": HF}
    assert esc.foto(f, pid, cuota) == antes


# ------------------------------------------------------------------ S2 devoluciones y abono

@pytest.mark.parametrize("tipo", TIPOS)
def test_o_h22_s2_devolucion_rechaza_y_la_lectura_es_veraz(esc, tipo) -> None:
    f, pid, cuota = esc.forma(tipo)
    lectura = esc.cli.get(m2.url_devoluciones(f.hecho_id), headers=h.AUTH).json()
    assert (lectura["disponible"], lectura["tuya_disponible"], lectura["motivo"]) == (False, False, HF)
    antes = esc.foto(f, pid, cuota)
    huella = m3.huella(esc.owner)
    _, r = m2.devolver(esc.cli, f.hecho_id, importe="40.00", atribucion="SIN_INDICAR")
    _rechazo(r, 409, HF)
    assert esc.foto(f, pid, cuota) == antes
    assert m3.huella(esc.owner) == huella


def test_o_h22_s2_abono_de_una_devolucion_de_cuota(esc) -> None:
    _pid, _cuota, f = esc.cuota(vincular=False)
    _, r = m2.devolver(esc.cli, f.hecho_id, importe="40.00", atribucion="SIN_INDICAR")
    assert r.status_code == 200, r.text  # aun sin vinculo: una devolucion previa (p. ej. V3)
    devolucion = uuid.UUID(r.json()["hecho_id"])
    fz.vincular_nivel_efecto(esc.dsn, esc.owner, f.hecho_id, f.efecto_deuda, f.entidad_id)
    antes = fz.foto(esc.dsn, esc.owner, devolucion)
    huella = m3.huella(esc.owner)
    _, r = m2.abonar(esc.cli, devolucion, esc.cta, fecha="2026-09-12")
    _rechazo(r, 409, HF)
    assert fz.foto(esc.dsn, esc.owner, devolucion) == antes
    assert m3.huella(esc.owner) == huella


# ------------------------------------------------------------------ S3 anular por duplicado (frontera)

@pytest.mark.parametrize("tipo", TIPOS)
def test_o_h22_s3_anular_duplicado_rechaza_en_la_frontera(esc, tipo) -> None:
    """O-A9-S3: responde la guarda de frontera (HECHO_DE_FINANCIACION), no la de
    motor (ANULACION_FINANCIACION_SIN_REVERSION), que se prueba por servicio."""
    f, pid, cuota = esc.forma(tipo)
    anul = esc.cli.get(f"/v1/hechos/{f.hecho_id}/anulacion", headers=h.AUTH).json()
    assert anul["elegible"] is False and HF in anul["motivos"]
    edi = esc.cli.get(f"/v1/hechos/{f.hecho_id}/edicion", headers=h.AUTH).json()
    assert (edi["acciones"]["anular_duplicado"]["disponible"], edi["acciones"]["anular_duplicado"]["codigo"]) == (
        False, HF)
    assert edi["acciones"]["anular_duplicado"]["motivo"]
    antes = esc.foto(f, pid, cuota)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": f.version, "movimientos_row_version": esc.movimientos_rv(f),
         "motivo": "Duplicado", "duplicado_declarado": True}
    _rechazo(esc.cli.post(f"/v1/hechos/{f.hecho_id}/anular-duplicado", json=c, headers=h.AUTH), 409, HF)
    assert esc.foto(f, pid, cuota) == antes


# ------------------------------------------------------------------ S4 edicion

@pytest.mark.parametrize("tipo", TIPOS)
def test_o_h22_s4_corregir_pago_y_transferencia_rechazan(esc, tipo) -> None:
    f, pid, cuota = esc.forma(tipo)
    edi = esc.cli.get(f"/v1/hechos/{f.hecho_id}/edicion", headers=h.AUTH).json()
    assert (edi["acciones"]["corregir"]["disponible"], edi["acciones"]["corregir"]["codigo"]) == (False, HF)
    antes = esc.foto(f, pid, cuota)
    mov = esc.movimientos_rv(f)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": f.version, "movimiento_row_version": next(iter(mov.values())),
         "motivo": "Importe mal", "error_de_registro": True, "importe": "450.00"}
    _rechazo(esc.cli.post(f"/v1/hechos/{f.hecho_id}/corregir-pago", json=c, headers=h.AUTH), 409, HF)
    t = {"intencion_id": str(uuid.uuid4()), "row_version": f.version, "movimientos_row_version": mov,
         "motivo": "No alcanzable", "error_de_registro": True, "importe": "450.00"}
    _rechazo(esc.cli.post(f"/v1/transferencias/{f.hecho_id}/corregir", json=t, headers=h.AUTH), 409, HF)
    assert esc.foto(f, pid, cuota) == antes


# ------------------------------------------------------------------ S5 corregir categoria (V3)

def _hecho_v3(esc):
    from app.core.modelos import DatosCreacionHecho
    from app.core.modelos_efectos import DatosEfecto
    from app.services.efectos_service import EfectosService
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla

    entidad, _ = esc.financiacion(v3=True)
    hecho_id, deuda = uuid.uuid4(), uuid.uuid4()
    r = HechosService(esc.u(), impacto_ancla=impacto_correccion_ancla).crear_hecho(esc.ctx(), DatosCreacionHecho(
        hecho_id=hecho_id, fecha_hecho=fz.FECHA, moneda="EUR", presupuestable=False,
        estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GASTO", concepto="V3 cuota", importe_total=fz.CUOTA))
    EfectosService(esc.u()).registrar_efectos(esc.ctx(), hecho_id=hecho_id, row_version_esperada=r.row_version,
                                              efectos=[DatosEfecto(efecto_id=deuda, tipo_efecto="GASTO",
                                                                   importe_delta=fz.CUOTA,
                                                                   estado_atribucion="NO_DISPONIBLE")],
                                              presupuestable=False)
    vinculo = fz.vincular_nivel_efecto(esc.dsn, esc.owner, hecho_id, deuda, entidad)
    fz.marcar_v3(esc.dsn, esc.owner, hecho_id)
    return fz.Forma(hecho_id, deuda, None, vinculo, entidad, None, fz.version(esc.dsn, esc.owner, hecho_id))


@pytest.mark.parametrize("tipo", TIPOS + ["v3"])
def test_o_h22_s5_corregir_categoria_rechaza(esc, tipo) -> None:
    """V3-FIX: el hecho importado de una HIPOTECA sin cuadro tambien es de
    financiacion; su lectura no ofrece «Corregir categoria»."""
    if tipo == "v3":
        f, pid, cuota = _hecho_v3(esc), None, None
        edi = esc.cli.get(f"/v1/hechos/{f.hecho_id}/edicion", headers=h.AUTH).json()
        cat = edi["acciones"]["corregir_categoria"]
        assert (cat["disponible"], cat["codigo"]) == (False, HF)
        rep = esc.cli.get(f"/v1/hechos/{f.hecho_id}/reparto", headers=h.AUTH).json()
        assert (rep["corregible"], rep["motivo"]) == (False, HF)
    else:
        f, pid, cuota = esc.forma(tipo)
    categoria = x.categoria(esc.owner, f"Cat {uuid.uuid4().hex[:6]}")
    antes = esc.foto(f, pid, cuota)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": f.version, "motivo": "Categoria", "categoria_id": str(categoria)}
    _rechazo(esc.cli.post(f"/v1/hechos/{f.hecho_id}/corregir-categoria", json=c, headers=h.AUTH), 409, HF)
    assert esc.foto(f, pid, cuota) == antes


# ------------------------------------------------------------------ S7 previsiones y O-H35

ACCIONES = ("registrar", "ya_lo_registre", "omitir", "swipe", "dar_por_cubierta", "reabrir")


@pytest.mark.parametrize("realizada", [False, True], ids=["ABIERTA", "REALIZADA"])
def test_o_h22_s7_s10_l_lectura_de_la_prevision_de_una_cuota(esc, realizada) -> None:
    """O-H22-S10-L y lectura de S7: ninguna accion disponible, en cualquier estado."""
    pid, _cuota, _f = esc.cuota(realizada=realizada)
    d = m.detalle(esc.cli, pid)
    assert d["estado"] == ("REALIZADA" if realizada else "ABIERTA")
    for k in ACCIONES:
        assert d["acciones"][k]["disponible"] is False, k
        assert d["acciones"][k]["codigo"] == PC, k
        assert d["acciones"][k]["motivo"], k
    from app.previsiones.lecturas import MOTIVO_PREVISION_DE_CUOTA
    cand = m.candidatos(esc.cli, pid)
    # 0.1.1 (STOP n.º 2, MF05-L-candidatos-cuota VIVO en la repeticion 1): el mensaje es el de la cuota,
    # no el de «sin criterio» (que tambien deja la lista vacia y enmascaraba el mutante).
    assert cand["candidatos"] == [] and cand["mensaje"] == MOTIVO_PREVISION_DE_CUOTA


def test_o_h22_s7_un_hecho_de_financiacion_no_es_candidato(esc) -> None:
    categoria = x.categoria(esc.owner, f"Banco {uuid.uuid4().hex[:6]}")
    _pid, _cuota, f = esc.cuota(prevision=False, categoria=categoria)
    ordinaria = m.prevision(esc.owner, "Recibo banco", importe="100.00", categoria=categoria, desde="2026-06-01")
    ids = [c["hecho_id"] for c in m.candidatos(esc.cli, ordinaria, ampliado=True)["candidatos"]]
    assert str(f.hecho_id) not in ids


@pytest.mark.parametrize("accion", ["vincular", "omitir", "dar_por_cubierta", "reabrir"])
def test_o_h22_s7_acciones_sobre_la_prevision_de_una_cuota(esc, accion) -> None:
    """«Reabrir» sobre la REALIZADA es O-H35; «Dar por cubierta» sobre la ABIERTA
    con realidad parcial (la marcaria REALIZADA sin pago)."""
    realizada = accion == "reabrir"
    pid, cuota, f = esc.cuota(realizada=realizada)
    if accion == "dar_por_cubierta":
        g = x.gasto(esc.cli, esc.cta, fecha="2026-10-05", importe="10.00")
        from app.core.modelos_prevision import DatosVinculo
        from app.services.previsiones_service import PrevisionesService
        PrevisionesService(esc.u()).vincular_realidad(
            esc.ctx(), prevision_id=pid, row_version_esperada=m.version(esc.owner, pid),
            datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=g, importe_asignado=D("10.0000"),
                               marcar_realizada=False))
    otro = x.gasto(esc.cli, esc.cta, fecha="2026-10-05", importe="500.00") if accion == "vincular" else None
    antes = esc.foto(f, pid, cuota)
    huella = m.huella(esc.owner)
    rv = m.version(esc.owner, pid)
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version": rv, "motivo": "Prueba F04-R-HIP"}
    if accion == "vincular":
        _, r = m.vincular(esc.cli, esc.owner, pid, otro, "500.00", True)
    elif accion == "omitir":
        _, r = m.omitir(esc.cli, esc.owner, pid, motivo="No hubo")
    elif accion == "dar_por_cubierta":
        r = esc.cli.post(f"/v1/previsiones/{pid}/dar-por-realizada", json=cuerpo, headers=h.AUTH)
    else:
        r = esc.cli.post(f"/v1/previsiones/{pid}/reabrir", json=cuerpo, headers=h.AUTH)
    _rechazo(r, 409, PC)
    assert esc.foto(f, pid, cuota) == antes
    assert m.huella(esc.owner) == huella


def test_o_h22_s7_vincular_un_hecho_de_financiacion_a_otra_prevision(esc) -> None:
    f = esc.hd()
    ordinaria = m.prevision(esc.owner, "Recibo", importe="100.00", desde="2026-06-01")
    antes = esc.foto(f)
    huella = m.huella(esc.owner)
    _, r = m.vincular(esc.cli, esc.owner, ordinaria, f.hecho_id, "100.00", True)
    _rechazo(r, 409, HF)
    assert esc.foto(f) == antes and m.huella(esc.owner) == huella


# ------------------------------------------------------------------ S8 posiciones (no regresion)

@pytest.mark.parametrize("accion", ["cobro", "pago", "perdon"])
def test_o_h22_s8_posiciones_sobre_una_financiacion(esc, accion) -> None:
    entidad, _ = esc.financiacion()
    huella = m3.huella(esc.owner)
    if accion == "perdon":
        _, r = m3.perdon(esc.cli, entidad, "10.00")
    else:
        _, r = m3.cobro(esc.cli, entidad, esc.cta, "10.00", accion=accion)
    _rechazo(r, 404, "POSICION_NO_ENCONTRADA")
    assert m3.huella(esc.owner) == huella


# ------------------------------------------------------------------ S10 registrar desde la prevision

def _s10(esc, ruta, pid, marcar):
    if ruta == "GP":
        return m.gasto_desde(esc.cli, esc.owner, esc.cta, pid, "500.00", marcar)
    if ruta == "GC":
        c = m3.cuerpo("500.00", pagado_por=m3.con_cuenta(esc.cta), reparto=m3.SOLO_MIO)
        c["prevision"] = m.bloque(esc.owner, pid, marcar)
        return c, esc.cli.post(m.COMPARTIDO, json=c, headers=h.AUTH)
    if ruta == "IC":
        return m.ingreso_desde(esc.cli, esc.owner, esc.cta, pid, "500.00", marcar)
    return m.transferencia_desde(esc.cli, esc.owner, esc.cta, esc.ahorro, pid, "500.00", marcar)


@pytest.mark.parametrize("marcar", [True, False], ids=["T", "F"])
@pytest.mark.parametrize("ruta", ["GP", "GC", "IC", "TR"])
def test_o_h22_s10_registrar_desde_la_prevision_de_una_cuota(esc, ruta, marcar) -> None:
    """GP y GC prosperarian en el HEAD de inicio; IC y TR discriminan por codigo
    (hoy PREVISION_TIPO_DISTINTO)."""
    pid, cuota, f = esc.cuota()
    antes = esc.foto(f, pid, cuota)
    huella = m.huella(esc.owner)
    c, r = _s10(esc, ruta, pid, marcar)
    _rechazo(r, 409, PC)
    assert esc.foto(f, pid, cuota) == antes
    assert m.huella(esc.owner) == huella
    assert m.uno(esc.owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (c["intencion_id"],))[0] == 0
