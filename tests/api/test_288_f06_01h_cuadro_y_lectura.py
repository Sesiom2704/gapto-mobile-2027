# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_288_f06_01h_cuadro_y_lectura.py
# Ruta: tests/api/test_288_f06_01h_cuadro_y_lectura.py
# Descripcion: T3-F06 bloque 2 F06-01H · W-HIP-00 y L-HIP por HTTP (contrato v0.4 §1.3, §1.4, §3.1, §3.3 y §7;
#   mandato v1.1 §2.2, §11.1 y §13.3). Como gapto_runtime con RLS (create_app + UnidadDeTrabajo).
#   W-HIP-00 (POST /v1/hipotecas/cuadro, sin escritura):
#     - O-H1 por HTTP cuota a cuota contra el CSV del paso 12 (fuente independiente, SHA verificado), con
#       vencimientos acotados al ultimo dia del mes y sumas; O-H3c sin primera cuota (vencimiento null);
#     - O-H11 en la vista previa: SEMANAL/ANUAL -> 422 CONDICIONES_INCOMPLETAS motivo PERIODICIDAD_NO_SOPORTADA;
#       LINEAL -> SISTEMA_NO_SOPORTADO; fuera de rango -> VALORES_FUERA_DE_RANGO;
#     - huella de TODA la base (todas las tablas de gapto, leida sin RLS) identica antes y despues de cada
#       peticion, aceptada o rechazada.
#   L-HIP (GET /v1/propiedades/{propiedad_id}/hipoteca), con fixtures SINTETICOS bajo gapto_owner con la GUC
#   de tenant (hechos, efectos, movimientos, previsiones y vinculo de prevision por los SERVICIOS como
#   gapto_runtime):
#     - hipoteca coherente con G2 (Σ capital previsto = capital contratado, cuotas 1..N, version ALTA con Hd):
#       estado derivado PAGADA / VENCIDA / PENDIENTE (hoy 2026-10-10), pendiente por fila, deuda pendiente =
#       Σ DEUDA de nivel efecto (Hd +300,00 y pago -100,00 = 200,00; un DEUDA de nivel HECHO no cuenta),
#       desembolso, version vigente, proxima cuota y cuenta de cargo;
#     - O-H10 (lectura): legacy V3 con apertura indeterminada -> deuda_pendiente null y deuda_indeterminada
#       true, NUNCA 0, aunque tenga un DEUDA vinculado; cuotas SIN_PREVISION;
#     - propiedad sin hipoteca -> 200 {"hipoteca": null}; propiedad de otro owner -> 404 indistinguible de una
#       inexistente, sin fuga de IDs; la lectura no escribe.
#   Fechas fijas; ORDER BY en los fixtures y en la lectura.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 4)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H; N-30, firma 0f3e5633…, enmienda 52ef5511…): oraculo de servidor de
#   `titularidad_prestamo` (aditivo en L-HIP): participaciones del prestamo con su vigencia, distintas de las de la
#   propiedad, y proyeccion en cada vencimiento == pago.propuesta (lo que relee W-HIP-02).
# Version: 0.3.0 (F06 T3-F06 bloque 2 F06-01H; H3, N-10 rama A, firma b7dbf079…): oraculo de la deuda con apertura
#   conocida (forma RV3 P5/P6 D8-E) y frontera F04-D053 A1: apertura 150,00 + DEUDA -50,00 posterior al seguimiento
#   = 100,00; el DEUDA +200,00 anterior no cuenta (test_l_hip_n10_apertura_conocida_y_frontera).
# ============================================================

from __future__ import annotations

import csv
import datetime as dt
import decimal
import hashlib
import json
import pathlib
import sys
import uuid

import pytest

import f05_06_m5_helpers as m
import f06_01_b1_helpers as b
import vs01_api_helpers as h

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
import f04_r_hip_formas as fz  # noqa: E402

D = decimal.Decimal
ORACULOS = pathlib.Path(__file__).resolve().parent / "oraculos_f06h"
URL_CUADRO = "/v1/hipotecas/cuadro"
F_ALTA = dt.date(2026, 8, 20)
F_CAMBIO = dt.date(2026, 10, 1)
#: Cuadro sintetico coherente con G2: Σ capital = 300,00 = capital contratado.
CUADRO = [(1, dt.date(2026, 9, 5), D("101.75"), D("1.75"), D("100.00")),
          (2, dt.date(2026, 10, 5), D("101.17"), D("1.17"), D("100.00")),
          (3, dt.date(2026, 11, 5), D("100.58"), D("0.58"), D("100.00"))]
P = D("300.00")


def _url(propiedad_id) -> str:
    return f"/v1/propiedades/{propiedad_id}/hipoteca"


def _csv(nombre: str) -> list[dict[str, str]]:
    sumas = dict(reversed(l.split(" ", 1)) for l in (ORACULOS / "SHA256SUMS.txt").read_text("ascii").splitlines())
    sumas = {k.lstrip("*").removeprefix("./"): v for k, v in sumas.items()}
    assert hashlib.sha256((ORACULOS / nombre).read_bytes()).hexdigest() == sumas[nombre]
    with (ORACULOS / nombre).open(encoding="ascii", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ escenario
class Esc:
    def __init__(self):
        self.owner, self.actor, self.cli, self.cta, self.ahorro = m.entorno()
        self.dsn = h.dsn()

    def u(self):
        import f05_01_helpers as fh
        return fh.unidad()

    def ctx(self):
        return m.ctx(self.owner)

    def propiedad(self, nombre="Piso Gran Vía") -> uuid.UUID:
        return uuid.UUID(b.crear(self.cli, b.alta(nombre=nombre))["id"])

    def hecho_deuda(self, tipo: str, total: D, efectos: list[tuple[str, D]], cuenta_importe: D | None,
                    fecha: dt.date) -> tuple[uuid.UUID, dict[str, uuid.UUID], int]:
        from app.core.modelos_efectos import DatosEfecto
        from app.services.efectos_service import EfectosService

        hecho_id, v = fz._hecho(self.u(), self.ctx(), tipo, total, tipo == "GASTO", fecha)
        ids = {t: uuid.uuid4() for t, _ in efectos}
        r = EfectosService(self.u()).registrar_efectos(self.ctx(), hecho_id=hecho_id, row_version_esperada=v, efectos=[
            DatosEfecto(efecto_id=ids[t], tipo_efecto=t, importe_delta=imp, estado_atribucion="NO_DISPONIBLE")
            for t, imp in efectos], **({"presupuestable": True} if tipo == "GASTO" else {}))
        v = r.row_version
        if cuenta_importe is not None:
            _, v = fz._tesoreria(self.u(), self.ctx(), hecho_id, self.cta, cuenta_importe, v, fecha)
        return hecho_id, ids, v

    def hipoteca(self, propiedad_id) -> dict:
        """Hipoteca coherente con G2 y M (version ALTA con Hd), cuota 1 pagada (prevision REALIZADA)."""
        previsiones = [m.prevision(self.owner, f"Cuota {n} hipoteca", importe=str(total), cuenta_salida=self.cta,
                                   desde=venc.isoformat()) for n, venc, total, _, _ in CUADRO]
        hd, ef_hd, _ = self.hecho_deuda("GENERACION_DERECHO_OBLIGACION", P, [("DEUDA", P)], P, F_ALTA)
        fid, alta, cambio = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        sentencias = [
            ("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
             "VALUES (%s, %s, 'FINANCIACION', 'Hipoteca Gran Vía')", (fid, self.owner)),
            ("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda, capital_original_contratado, "
             "saldo_principal_apertura, fecha_inicio_seguimiento, fecha_inicio, fecha_vencimiento_final_prevista) "
             "VALUES (%s, 'HIPOTECA', 'EUR', %s, 0, %s, %s, %s)", (fid, P, F_ALTA, F_ALTA, CUADRO[-1][1])),
            ("INSERT INTO gapto.entidad_relaciones (entidad_origen_id, entidad_destino_id, tipo_relacion, "
             "vigente_desde) VALUES (%s, %s, 'GARANTIZADA_POR', %s)", (fid, propiedad_id, F_ALTA)),
            ("INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
             "vigente_hasta, motivo_version, hecho_causa_id, tipo_interes, tasa_anual_pct, sistema_amortizacion, "
             "periodicidad, intervalo, importe_cuota_referencia, numero_cuotas_referencia) VALUES "
             "(%s, %s, %s, %s, 'ALTA', %s, 'FIJO', 7, 'FRANCES', 'MENSUAL', 1, 101.75, 3)",
             (alta, fid, F_ALTA, F_CAMBIO - dt.timedelta(days=1), hd)),
            ("INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
             "motivo_version, tipo_interes, tasa_anual_pct, sistema_amortizacion, periodicidad, intervalo, "
             "importe_cuota_referencia, numero_cuotas_referencia) VALUES "
             "(%s, %s, %s, 'CAMBIO_CONDICIONES', 'VARIABLE', 6.5, 'FRANCES', 'MENSUAL', 1, 101.17, 2)",
             (cambio, fid, F_CAMBIO)),
        ]
        for (n, venc, total, interes, capital), pid in zip(CUADRO, previsiones):
            sentencias.append((
                "INSERT INTO gapto.financiacion_cuotas (financiacion_entidad_id, condicion_version_id, numero_cuota, "
                "fecha_vencimiento, capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto, "
                "prevision_id) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s)",
                (fid, alta if n == 1 else cambio, n, venc, capital, interes, total, pid)))
        sentencias.append((
            "INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal, "
            "owner_user_id) VALUES (%s, %s, %s, %s, 'AFECTA_A', false, %s)",
            (uuid.uuid4(), hd, ef_hd["DEUDA"], fid, self.owner)))
        fz.como_owner(self.dsn, self.owner, sentencias)
        # pago de la cuota 1: GASTO +intereses y DEUDA -capital (nivel efecto), movimiento -cuota conciliado
        n1, venc1, total1, interes1, capital1 = CUADRO[0]
        pago, ef_pago, _ = self.hecho_deuda("GASTO", total1, [("GASTO", interes1), ("DEUDA", -capital1)], -total1,
                                            venc1)
        fz.vincular_nivel_efecto(self.dsn, self.owner, pago, ef_pago["DEUDA"], fid)
        from app.core.modelos_prevision import DatosVinculo
        from app.services.previsiones_service import PrevisionesService
        PrevisionesService(self.u()).vincular_realidad(
            self.ctx(), prevision_id=previsiones[0], row_version_esperada=m.version(self.owner, previsiones[0]),
            datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=pago, importe_asignado=total1, marcar_realizada=True))
        # un DEUDA vinculado a NIVEL HECHO no es deuda de la hipoteca (§1.4: solo nivel efecto)
        ajeno, _, _ = self.hecho_deuda("GENERACION_DERECHO_OBLIGACION", D("50.00"), [("DEUDA", D("50.00"))], None,
                                       F_ALTA)
        fz.vincular_nivel_efecto(self.dsn, self.owner, ajeno, None, fid)
        return {"fid": fid, "hd": hd, "pago": pago, "alta": alta, "cambio": cambio, "previsiones": previsiones}

    def legacy(self, propiedad_id) -> uuid.UUID:
        """Forma legacy V3 (contrato §1.4, Q-T3D-13): apertura indeterminada, ALTA sin hecho causa, cuotas sin
        prevision con Σ capital = principal (coherente con G2) y un DEUDA importado vinculado a nivel efecto."""
        fid = uuid.uuid4()
        deuda, ef, _ = self.hecho_deuda("GENERACION_DERECHO_OBLIGACION", D("200.00"), [("DEUDA", D("200.00"))], None,
                                        dt.date(2026, 1, 15))
        fz.marcar_v3(self.dsn, self.owner, deuda)
        fz.como_owner(self.dsn, self.owner, [
            ("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
             "VALUES (%s, %s, 'FINANCIACION', 'Hipoteca V3')", (fid, self.owner)),
            ("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda, capital_original_contratado, "
             "fecha_inicio) VALUES (%s, 'HIPOTECA', 'EUR', 200, %s)", (fid, dt.date(2026, 1, 15))),
            ("INSERT INTO gapto.entidad_relaciones (entidad_origen_id, entidad_destino_id, tipo_relacion) "
             "VALUES (%s, %s, 'GARANTIZADA_POR')", (fid, propiedad_id)),
            ("INSERT INTO gapto.financiacion_condiciones_versiones (financiacion_entidad_id, vigente_desde, "
             "motivo_version, tipo_interes, tasa_anual_pct, sistema_amortizacion, periodicidad) VALUES "
             "(%s, %s, 'ALTA', 'FIJO', 0, 'SIN_INTERES', 'MENSUAL')", (fid, dt.date(2026, 1, 15))),
            ("INSERT INTO gapto.financiacion_cuotas (financiacion_entidad_id, numero_cuota, fecha_vencimiento, "
             "capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto) "
             "VALUES (%s, 1, %s, 100, 0, 0, 100)", (fid, dt.date(2026, 2, 15))),
            ("INSERT INTO gapto.financiacion_cuotas (financiacion_entidad_id, numero_cuota, fecha_vencimiento, "
             "capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto) "
             "VALUES (%s, 2, %s, 100, 0, 0, 100)", (fid, dt.date(2026, 3, 15))),
            ("INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal, "
             "owner_user_id) VALUES (%s, %s, %s, %s, 'AFECTA_A', false, %s)",
             (uuid.uuid4(), deuda, ef["DEUDA"], fid, self.owner)),
        ])
        return fid

    def legacy_conocida(self, propiedad_id) -> uuid.UUID:
        """N-10 (firma b7dbf079…): forma que escribe RV3 P5/P6 (D8-E): HIPOTECA con apertura CONOCIDA = 150,00 y
        seguimiento desde 2026-02-01; un DEUDA +200,00 del 2026-01-15 (ANTERIOR a la frontera: no cuenta) y un
        DEUDA -50,00 del 2026-02-15 (posterior: cuenta), ambos a nivel efecto. Cuotas sin prevision (Σ = 200)."""
        fid = uuid.uuid4()
        previo, ef_previo, _ = self.hecho_deuda("GENERACION_DERECHO_OBLIGACION", D("200.00"),
                                                [("DEUDA", D("200.00"))], None, dt.date(2026, 1, 15))
        fz.marcar_v3(self.dsn, self.owner, previo)
        pago, ef_pago, _ = self.hecho_deuda("GASTO", D("60.00"), [("GASTO", D("10.00")), ("DEUDA", D("-50.00"))],
                                            None, dt.date(2026, 2, 15))
        fz.como_owner(self.dsn, self.owner, [
            ("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
             "VALUES (%s, %s, 'FINANCIACION', 'Hipoteca V3 con apertura')", (fid, self.owner)),
            ("INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, moneda, capital_original_contratado, "
             "saldo_principal_apertura, fecha_inicio_seguimiento, fecha_inicio) "
             "VALUES (%s, 'HIPOTECA', 'EUR', 200, 150, %s, %s)", (fid, dt.date(2026, 2, 1), dt.date(2026, 1, 15))),
            ("INSERT INTO gapto.entidad_relaciones (entidad_origen_id, entidad_destino_id, tipo_relacion) "
             "VALUES (%s, %s, 'GARANTIZADA_POR')", (fid, propiedad_id)),
            ("INSERT INTO gapto.financiacion_condiciones_versiones (financiacion_entidad_id, vigente_desde, "
             "motivo_version, tipo_interes, tasa_anual_pct, sistema_amortizacion, periodicidad) VALUES "
             "(%s, %s, 'ALTA', 'FIJO', 0, 'SIN_INTERES', 'MENSUAL')", (fid, dt.date(2026, 1, 15))),
            ("INSERT INTO gapto.financiacion_cuotas (financiacion_entidad_id, numero_cuota, fecha_vencimiento, "
             "capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto) "
             "VALUES (%s, 1, %s, 100, 0, 0, 100)", (fid, dt.date(2026, 2, 15))),
            ("INSERT INTO gapto.financiacion_cuotas (financiacion_entidad_id, numero_cuota, fecha_vencimiento, "
             "capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto) "
             "VALUES (%s, 2, %s, 100, 0, 0, 100)", (fid, dt.date(2026, 3, 15))),
            ("INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal, "
             "owner_user_id) VALUES (%s, %s, %s, %s, 'AFECTA_A', false, %s)",
             (uuid.uuid4(), previo, ef_previo["DEUDA"], fid, self.owner)),
            ("INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal, "
             "owner_user_id) VALUES (%s, %s, %s, %s, 'AFECTA_A', false, %s)",
             (uuid.uuid4(), pago, ef_pago["DEUDA"], fid, self.owner)),
        ])
        return fid


@pytest.fixture()
def esc():
    return Esc()


def _rechazo(r, status: int, codigo: str, motivo: str | None = None) -> dict:
    assert r.status_code == status, r.text
    j = r.json()
    assert j["codigo"] == codigo, r.text
    if motivo is not None:
        assert (j["motivo"], j["detalle"]) == (motivo, {"motivo": motivo}), r.text
    return j


# ------------------------------------------------------------------ W-HIP-00
def test_w_hip_00_o_h1_cuota_a_cuota_sin_escritura(esc) -> None:
    antes = b.huella()
    r = esc.cli.post(URL_CUADRO, json={"capital": "160000.00", "tasa_anual": "2.5", "numero_cuotas": 360,
                                       "primera_cuota": "2027-01-31"}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert b.huella() == antes
    j = r.json()
    assert {k: j[k] for k in ("sistema", "periodicidad", "convencion", "capital", "tasa_anual", "numero_cuotas",
                              "cuota_referencia", "suma_capital", "suma_intereses", "total_a_pagar")} == {
        "sistema": "FRANCES", "periodicidad": "MENSUAL", "convencion": "MENSUAL_ANUAL_12", "capital": "160000.00",
        "tasa_anual": "2.5", "numero_cuotas": 360, "cuota_referencia": "632.19", "suma_capital": "160000.00",
        "suma_intereses": "67590.10", "total_a_pagar": "227590.10"}
    esperadas = _csv("caso1_frances_160000_2.5_360.csv")
    assert len(j["cuotas"]) == len(esperadas) == 360
    for c, e in zip(j["cuotas"], esperadas):
        assert set(c) == {"n", "vencimiento", "cuota", "interes", "capital", "comision", "pendiente"}
        assert (c["n"], D(c["cuota"]), D(c["interes"]), D(c["capital"]), D(c["pendiente"]), c["comision"]) == (
            int(e["n"]), D(e["cuota"]), D(e["interes"]), D(e["capital"]), D(e["pendiente"]), "0.00"), (c, e)
    assert (j["cuotas"][0]["capital"], j["cuotas"][0]["interes"]) == ("298.86", "333.33")
    assert [c["vencimiento"] for c in j["cuotas"][:4]] == ["2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30"]
    assert j["cuotas"][13]["vencimiento"] == "2028-02-29"
    assert j["cuotas"][-1]["pendiente"] == "0.00"


def test_w_hip_00_o_h3c_sin_primera_cuota(esc) -> None:
    antes = b.huella()
    r = esc.cli.post(URL_CUADRO, json={"capital": "100.00", "tasa_anual": 7, "numero_cuotas": 2}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert b.huella() == antes
    j = r.json()
    assert [(c["n"], c["vencimiento"], c["cuota"], c["capital"]) for c in j["cuotas"]] == [
        (1, None, "50.44", "49.86"), (2, None, "50.43", "50.14")]
    assert (j["suma_capital"], j["suma_intereses"]) == ("100.00", "0.87")


@pytest.mark.parametrize("cambios, motivo", [
    ({"periodicidad": "SEMANAL"}, "PERIODICIDAD_NO_SOPORTADA"),
    ({"periodicidad": "ANUAL"}, "PERIODICIDAD_NO_SOPORTADA"),
    ({"sistema": "LINEAL"}, "SISTEMA_NO_SOPORTADO"),
    ({"numero_cuotas": 0}, "VALORES_FUERA_DE_RANGO"),
    ({"numero_cuotas": 601}, "VALORES_FUERA_DE_RANGO"),
    ({"capital": "0.00"}, "VALORES_FUERA_DE_RANGO"),
    ({"capital": "100.001"}, "VALORES_FUERA_DE_RANGO"),
    ({"tasa_anual": "30.5"}, "VALORES_FUERA_DE_RANGO"),
])
def test_w_hip_00_condiciones_incompletas_sin_escritura(esc, cambios, motivo) -> None:
    cuerpo = {"capital": "160000.00", "tasa_anual": "2.5", "numero_cuotas": 360, "primera_cuota": "2027-01-31"}
    antes = b.huella()
    _rechazo(esc.cli.post(URL_CUADRO, json={**cuerpo, **cambios}, headers=h.AUTH), 422, "CONDICIONES_INCOMPLETAS",
             motivo)
    assert b.huella() == antes


def test_w_hip_00_entrada_invalida_y_sin_autorizacion(esc) -> None:
    cuerpo = {"capital": "1000.00", "tasa_anual": "3", "numero_cuotas": 12}
    antes = b.huella()
    _rechazo(esc.cli.post(URL_CUADRO, json={**cuerpo, "comisiones": "1.00"}, headers=h.AUTH), 422, "ENTRADA_INVALIDA")
    _rechazo(esc.cli.post(URL_CUADRO, json={"capital": "1000.00", "tasa_anual": "3"}, headers=h.AUTH), 422,
             "ENTRADA_INVALIDA")
    assert esc.cli.post(URL_CUADRO, json=cuerpo).status_code == 401
    assert b.huella() == antes


# ------------------------------------------------------------------ L-HIP
def test_l_hip_hipoteca_coherente(esc) -> None:
    pid = esc.propiedad()
    x = esc.hipoteca(pid)
    antes = b.huella()
    r = esc.cli.get(_url(pid), headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert b.huella() == antes                                    # la lectura no escribe
    hip = r.json()["hipoteca"]
    assert {k: hip[k] for k in ("financiacion_id", "nombre", "estado", "propiedad_id", "compra_hecho_id", "capital",
                                "fecha_inicio", "fecha_fin_prevista", "convencion", "cuenta_cargo_id",
                                "tipo_vigente", "vigente_desde", "cuota_vigente", "deuda_pendiente",
                                "deuda_indeterminada", "capital_amortizado", "intereses_pagados", "cuotas_pagadas",
                                "numero_cuotas", "financiador")} == {
        "financiacion_id": str(x["fid"]), "nombre": "Hipoteca Gran Vía", "estado": "ACTIVA",
        "propiedad_id": str(pid), "compra_hecho_id": None, "capital": "300.00", "fecha_inicio": "2026-08-20",
        "fecha_fin_prevista": "2026-11-05", "convencion": "MENSUAL_ANUAL_12", "cuenta_cargo_id": str(esc.cta),
        "tipo_vigente": "6.5", "vigente_desde": "2026-10-01", "cuota_vigente": "101.17",
        "deuda_pendiente": "200.00", "deuda_indeterminada": False, "capital_amortizado": "100.00",
        "intereses_pagados": "1.75", "cuotas_pagadas": 1, "numero_cuotas": 3, "financiador": None}
    assert isinstance(hip["row_version"], int)
    assert hip["desembolso"] == {"hecho_id": str(x["hd"]), "cuenta_id": str(esc.cta), "fecha": "2026-08-20",
                                 "importe": "300.00"}
    assert [(c["numero"], c["vencimiento"], c["cuota"], c["interes"], c["capital"], c["pendiente"], c["estado"],
             c["version_id"], c["hecho_pago_id"]) for c in hip["cuotas"]] == [
        (1, "2026-09-05", "101.75", "1.75", "100.00", "200.00", "PAGADA", str(x["alta"]), str(x["pago"])),
        (2, "2026-10-05", "101.17", "1.17", "100.00", "100.00", "VENCIDA", str(x["cambio"]), None),
        (3, "2026-11-05", "100.58", "0.58", "100.00", "0.00", "PENDIENTE", str(x["cambio"]), None)]
    assert hip["proxima_cuota"]["numero"] == 2 and hip["proxima_cuota"]["estado"] == "VENCIDA"
    assert [(v["id"], v["vigente_desde"], v["vigente_hasta"], v["motivo"], v["tipo_interes"], v["tasa_anual"],
             v["cuota_referencia"], v["numero_cuotas"], v["hecho_causa_id"]) for v in hip["condiciones"]] == [
        (str(x["alta"]), "2026-08-20", "2026-09-30", "ALTA", "FIJO", "7", "101.75", 3, str(x["hd"])),
        (str(x["cambio"]), "2026-10-01", None, "CAMBIO_CONDICIONES", "VARIABLE", "6.5", "101.17", 2, None)]
    assert all(c["capital"] is not None for c in hip["cuotas"])
    assert "bonificacion" not in json.dumps(hip).lower()


def test_l_hip_n30_titularidad_vigente_del_prestamo(esc) -> None:
    """N-30 (firma 0f3e5633…; enmienda 52ef5511… del contrato v0.4 en L-HIP): L-HIP devuelve, como campo aditivo,
    la titularidad DEL PRESTAMO con su vigencia, distinta de la de la propiedad; la proyeccion en el vencimiento de
    cada cuota coincide con la propuesta que W-HIP-02 relee (pago.propuesta, Q-T3D-08)."""
    from app.hipotecas import pago as serv_pago

    pid = esc.propiedad()                                   # propiedad: 100 % mia
    x = esc.hipoteca(pid)
    sin = esc.cli.get(_url(pid), headers=h.AUTH).json()["hipoteca"]
    assert sin["titularidad_prestamo"] == []                # sin participaciones del prestamo: lista vacia
    ana = b.tercero(esc.cli, "Ana Préstamo")
    otra = uuid.UUID(b.crear(esc.cli, b.alta(b.compartida([b.yo("60"), b.de(ana, "40")]), nombre="Garaje"))["id"])
    actores = {str(t): a for a, t in fz_actores(esc, otra)}
    yo, a_ana = actores["None"], actores[str(ana)]
    corte = dt.date(2026, 9, 30)
    fz.como_owner(esc.dsn, esc.owner, [
        ("INSERT INTO gapto.entidad_participaciones (id, entidad_id, actor_id, porcentaje, vigente_desde, "
         "vigente_hasta) VALUES (%s, %s, %s, 100, %s, %s)", (uuid.uuid4(), x["fid"], yo, F_ALTA, corte)),
        ("INSERT INTO gapto.entidad_participaciones (id, entidad_id, actor_id, porcentaje, vigente_desde) "
         "VALUES (%s, %s, %s, 70, %s)", (uuid.uuid4(), x["fid"], yo, corte + dt.timedelta(days=1))),
        ("INSERT INTO gapto.entidad_participaciones (id, entidad_id, actor_id, porcentaje, vigente_desde) "
         "VALUES (%s, %s, %s, 30, %s)", (uuid.uuid4(), x["fid"], a_ana, corte + dt.timedelta(days=1))),
    ])
    antes = b.huella()
    r = esc.cli.get(_url(pid), headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert b.huella() == antes
    hip = r.json()["hipoteca"]
    tramo2 = sorted([(str(yo), "70.0000", True, None, None), (str(a_ana), "30.0000", False, str(ana), "Ana Préstamo")])
    assert [(t["actor_id"], t["porcentaje"], t["yo"], t["tercero_id"], t["nombre"], t["vigente_desde"],
             t["vigente_hasta"]) for t in hip["titularidad_prestamo"]] == [
        (str(yo), "100.0000", True, None, None, "2026-08-20", "2026-09-30"),
        *[(*t, "2026-10-01", None) for t in tramo2]]
    # la de la propiedad (100 % mia) no es la del prestamo: el campo no la copia
    assert {t["porcentaje"] for t in hip["titularidad_prestamo"]} != {"100.0000"}
    # proyeccion en el vencimiento de cada cuota == propuesta que relee W-HIP-02
    for c in hip["cuotas"]:
        venc = c["vencimiento"]
        vista = sorted((t["actor_id"], decimal.Decimal(t["porcentaje"])) for t in hip["titularidad_prestamo"]
                       if t["vigente_desde"] <= venc and (t["vigente_hasta"] is None or venc <= t["vigente_hasta"]))
        fecha = dt.date.fromisoformat(venc)
        servidor = sorted((str(a), p) for a, p in esc.u().ejecutar(
            esc.ctx(), lambda s, f=fecha: serv_pago.propuesta(s, x["fid"], f), nombre="N-30 propuesta W-HIP-02"))
        assert vista == servidor, (venc, vista, servidor)


def fz_actores(esc, entidad) -> list[tuple]:
    """(actor_id, tercero_id) de las participaciones de `entidad` (lectura sin RLS de la base desechable)."""
    import psycopg
    with psycopg.connect(esc.dsn, autocommit=True) as c:
        return c.execute("SELECT x.actor_id, a.tercero_id FROM gapto.entidad_participaciones x JOIN "
                         "gapto.actores_financieros a ON a.id = x.actor_id WHERE x.entidad_id = %s", (entidad,)).fetchall()


def test_l_hip_o_h10_legacy_indeterminada_nunca_cero(esc) -> None:
    pid = esc.propiedad("Piso heredado")
    fid = esc.legacy(pid)
    antes = b.huella()
    r = esc.cli.get(_url(pid), headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert b.huella() == antes
    hip = r.json()["hipoteca"]
    assert hip["financiacion_id"] == str(fid)
    assert hip["deuda_pendiente"] is None and hip["deuda_indeterminada"] is True
    assert hip["desembolso"] is None and hip["cuenta_cargo_id"] is None and hip["proxima_cuota"] is None
    assert [(c["numero"], c["pendiente"], c["estado"], c["hecho_pago_id"]) for c in hip["cuotas"]] == [
        (1, "100.00", "SIN_PREVISION", None), (2, "0.00", "SIN_PREVISION", None)]


def test_l_hip_n10_apertura_conocida_y_frontera(esc) -> None:
    """N-10 rama A (firma b7dbf079…; F04-D053 A1): deuda = apertura 150,00 + Σ DEUDA desde el seguimiento (-50,00)
    = 100,00. Sin apertura daria -50,00; sin frontera, 300,00 (discrimina M-H-45 y M-H-46)."""
    pid = esc.propiedad("Piso V3 con apertura")
    fid = esc.legacy_conocida(pid)
    antes = b.huella()
    r = esc.cli.get(_url(pid), headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert b.huella() == antes
    hip = r.json()["hipoteca"]
    assert hip["financiacion_id"] == str(fid)
    assert hip["deuda_pendiente"] == "100.00" and hip["deuda_indeterminada"] is False


def test_l_hip_propiedad_sin_hipoteca_y_aislamiento(esc) -> None:
    pid = esc.propiedad()
    x = esc.hipoteca(pid)
    sin = esc.propiedad("Trastero")
    r = esc.cli.get(_url(sin), headers=h.AUTH)
    assert (r.status_code, r.json()) == (200, {"hipoteca": None})
    # otro owner: 404 indistinguible de una propiedad inexistente, sin IDs de A en la respuesta, sin escribir
    owner_b, _actor_b = h.crear_tenant()
    cli_b = h.cliente(owner_b)
    antes = b.huella()
    ajena = cli_b.get(_url(pid), headers=h.AUTH)
    inexistente = cli_b.get(_url(uuid.uuid4()), headers=h.AUTH)
    assert b.huella() == antes
    _rechazo(ajena, 404, "AGREGADO_NO_ENCONTRADO")
    assert (ajena.status_code, ajena.json()) == (inexistente.status_code, inexistente.json())
    assert not any(str(v) in ajena.text for v in (x["fid"], x["hd"], x["pago"], pid))
    # y el dueno sigue leyendo la suya
    assert esc.cli.get(_url(pid), headers=h.AUTH).json()["hipoteca"]["financiacion_id"] == str(x["fid"])
