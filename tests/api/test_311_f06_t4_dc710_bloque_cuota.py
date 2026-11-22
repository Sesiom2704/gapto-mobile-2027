# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_311_f06_t4_dc710_bloque_cuota.py
# Ruta: tests/api/test_311_f06_t4_dc710_bloque_cuota.py
# Descripcion: D-C7-10 · bloque `cuota` de las filas de cuota de Inicio y Pendientes (mandato F06 T4 DC710 v1.0
#   §2.2-§2.3 y §4 «Servidor»; AJ-DC710-01/02). Como gapto_runtime con RLS por HTTP. Oraculos:
#   - bloque correcto (financiacion, numero, version, vencimiento, cuenta de cargo) y propuesta = la del escritor
#     (W-HIP-02 acepta el payload compuesto con el bloque);
#   - calendario guardado: ordinal 31 y dia 1;
#   - `swipe_disponible = false` en cada condicion por separado (futura, anterior ABIERTA, anterior OMITIDA,
#     financiacion CERRADA, apertura desconocida, sin cuenta de cargo, importe distinto, realidad previa);
#   - `sin_dudas = false` en cada condicion por separado (cuenta deshabilitada, cerrada antes del vencimiento, sin
#     PAGAR_GASTO, propuesta vacia, participacion de la cuenta desconocida, reparto distinto) y AJ-DC710-02 en los
#     dos sentidos (el aviso del desembolso no decide);
#   - filas ordinarias sin ninguna clave nueva; las resueltas no llevan el bloque.
#   Los estados no alcanzables por la API se fijan con SQL bajo gapto_owner (fixture declarado, como O-H10).
# Version: 0.1.0 (F06 T4 · D-C7-10, mandato 7041970a…)
# ============================================================
from __future__ import annotations

import uuid

import pytest

import f05_06_m5_helpers as m
import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from test_293_f06_01h_pago_cuota import LabPago
from test_297_f06_01h_f05_q3_listas import CLAVES_C5E4FF8

INICIO, PENDIENTES = "/v1/inicio/previsiones", "/v1/previsiones/pendientes"


class LabSwipe(LabPago):
    """Hipoteca de 12 cuotas (primera 2026-04-20 salvo cambio; reloj 2026-10-10: 6 vencidas). Prestamo YO 60 / A 40
    (titularidad aceptada de la propiedad). Cuenta de cargo `cargo`: por defecto `cc`, 60/40 con PAGAR_GASTO (sin
    dudas); `cd` (100 % mia) da reparto distinto. El desembolso va a `desembolso` (por defecto `cd`)."""

    def __init__(self, *, cargo: str = "cc", desembolso: str = "cd", primera: str = "2026-04-20", cuotas: int = 12):
        self._cargo, self._desembolso, self._primera, self._n = cargo, desembolso, primera, cuotas
        super().__init__()

    def bloque(self, **cambios) -> dict:
        if not hasattr(self, "cc"):
            self.cc = h.crear_cuenta(self.owner, [(self.actor, 60), (uuid.UUID(self.a), 40)],
                                     capacidades=("RECIBIR_INGRESO", "PAGAR_GASTO"))
        cambios.setdefault("numero_cuotas", self._n)
        cambios["fecha_primera_cuota"] = self._primera
        cambios.setdefault("cuenta_cargo_id", str(getattr(self, self._cargo)))
        cambios.setdefault("cuenta_desembolso_id", str(getattr(self, self._desembolso)))
        return super().bloque(**cambios)

    def peticion_hip(self, *, hip=None, **kw):
        cuerpo = super().peticion_hip(hip=hip, **kw)
        cuerpo["pagos_propios"][0]["cuenta_id"] = str(getattr(self, self._desembolso))
        return cuerpo

    def cuotas(self) -> dict[int, uuid.UUID]:
        return {n: p for n, p in self.sql("SELECT numero_cuota, prevision_id FROM gapto.financiacion_cuotas "
                                          "WHERE financiacion_entidad_id = %s ORDER BY numero_cuota", (self.f,))}

    def fila(self, numero: int, ruta: str = PENDIENTES, cli=None) -> dict | None:
        cuerpo = _get(cli or self.cli, ruta)
        pid = str(self.cuotas()[numero])
        return next((f for f in _filas(cuerpo) if f["id"] == pid), None)

    def owner_sql(self, sql: str, params: tuple = ()) -> None:
        c2.como_owner(self.owner, sql, params)


def _get(cli, ruta: str) -> dict:
    r = cli.get(ruta, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _filas(cuerpo: dict) -> list[dict]:
    if "requiere_atencion" in cuerpo:
        return cuerpo["requiere_atencion"]["primeras"] + cuerpo["proximos"]
    s = cuerpo["secciones"]
    return s["vencidas"] + s["con_pago_parcial"] + s["sin_fecha"]


def _cliente(lab, dia: str):
    return h.cliente(lab.owner, reloj=m.x.reloj(f"{dia}T12:00:00"))


@pytest.fixture()
def lab():
    return LabSwipe()


def _payload(fila: dict) -> dict:
    """Payload de W-HIP-02 compuesto SOLO con el bloque (mandato §2.4)."""
    q = fila["cuota"]
    return {"intencion_id": str(uuid.uuid4()), "row_version_esperada": q["financiacion_row_version"],
            "cuenta_id": q["cuenta_cargo"]["id"], "fecha_pago": q["fecha_vencimiento"],
            "atribucion": {"propuesta_vista": {"partes": q["propuesta_atribucion"]},
                           "partes": q["propuesta_atribucion"]}}


# ================================================================== bloque correcto
def test_bloque_de_la_primera_cuota_sin_dudas_y_propuesta_del_escritor(lab):
    f = lab.fila(1)
    q = f["cuota"]
    assert list(f) == CLAVES_C5E4FF8 + ["codigo", "cuota"]
    assert q["financiacion_id"] == str(lab.f) and q["numero"] == 1 and q["fecha_vencimiento"] == "2026-04-20"
    assert q["financiacion_row_version"] == lab.hipoteca()["row_version"]
    assert q["cuenta_cargo"]["id"] == str(lab.cc) and q["cuenta_cargo"] == f["cuenta_salida"]
    assert q["propuesta_atribucion"] == sorted([{"actor_id": lab.yo, "porcentaje": "60.0000"},
                                                {"actor_id": lab.a, "porcentaje": "40.0000"}],
                                               key=lambda p: p["actor_id"])
    assert q["swipe_disponible"] is True and q["sin_dudas"] is True
    # la propuesta es la del escritor: W-HIP-02 acepta el payload compuesto solo con el bloque
    r = lab.pagar(1, _payload(f))
    assert r.status_code == 200 and r.json()["idempotente"] is False, r.text


def test_inicio_lleva_el_mismo_bloque_y_las_posteriores_no_ofrecen_gesto(lab):
    ini = lab.fila(1, INICIO)
    assert ini["cuota"] == lab.fila(1)["cuota"]
    for n in range(2, 7):
        q = lab.fila(n)["cuota"]
        assert q["numero"] == n and q["swipe_disponible"] is False and q["sin_dudas"] is False
        assert q["propuesta_atribucion"] is None
    # la 7.ª (2026-10-20) es la proxima de Inicio: futura y con anteriores sin pagar
    assert lab.fila(7, INICIO)["cuota"]["swipe_disponible"] is False


def test_tras_pagar_la_primera_la_segunda_ofrece_el_gesto(lab):
    assert lab.pagar(1, _payload(lab.fila(1))).status_code == 200
    q = lab.fila(2)["cuota"]
    assert q["swipe_disponible"] is True and q["sin_dudas"] is True and q["fecha_vencimiento"] == "2026-05-20"
    assert q["financiacion_row_version"] == lab.hipoteca()["row_version"]


@pytest.mark.parametrize("primera, numero, vencimiento", [
    ("2026-03-31", 3, "2026-05-31"), ("2026-03-31", 2, "2026-04-30"), ("2026-03-31", 7, "2026-09-30"),
    ("2026-04-01", 1, "2026-04-01"), ("2026-04-01", 7, "2026-10-01"),
])
def test_calendario_guardado_ordinal_31_y_dia_1(primera, numero, vencimiento):
    lab = LabSwipe(primera=primera)
    assert lab.fila(numero)["cuota"]["fecha_vencimiento"] == vencimiento
    assert lab.fila(1)["cuota"]["swipe_disponible"] is True


# ================================================================== swipe_disponible = false, una a una
def test_no_disponible_cuota_futura(lab):
    cli = _cliente(lab, "2026-04-19")
    q = lab.fila(1, INICIO, cli)["cuota"]
    assert q["fecha_vencimiento"] == "2026-04-20" and q["swipe_disponible"] is False and q["sin_dudas"] is False
    # control: el mismo dia del vencimiento si
    assert lab.fila(1, INICIO, _cliente(lab, "2026-04-20"))["cuota"]["swipe_disponible"] is True


def test_no_disponible_anterior_omitida(lab):
    cuotas = lab.cuotas()
    lab.owner_sql("UPDATE gapto.previsiones SET estado = 'OMITIDA' WHERE id = %s", (cuotas[1],))
    q = lab.fila(2)["cuota"]
    assert q["swipe_disponible"] is False and q["sin_dudas"] is False


def test_no_disponible_anterior_cancelada(lab):
    cuotas = lab.cuotas()
    lab.owner_sql("UPDATE gapto.previsiones SET estado = 'CANCELADA' WHERE id = %s", (cuotas[1],))
    assert lab.fila(2)["cuota"]["swipe_disponible"] is False


def test_no_disponible_financiacion_cerrada(lab):
    lab.owner_sql("UPDATE gapto.financiaciones SET estado = 'CERRADA', fecha_cierre_real = DATE '2026-10-01' "
                  "WHERE entidad_id = %s", (lab.f,))
    assert lab.fila(1)["cuota"]["swipe_disponible"] is False


def test_no_disponible_apertura_desconocida(lab):
    lab.owner_sql("UPDATE gapto.financiaciones SET saldo_principal_apertura = NULL, fecha_inicio_seguimiento = NULL "
                  "WHERE entidad_id = %s", (lab.f,))
    assert lab.fila(1)["cuota"]["swipe_disponible"] is False


def test_no_disponible_sin_cuenta_de_cargo(lab):
    lab.owner_sql("UPDATE gapto.previsiones SET cuenta_salida_esperada_id = NULL WHERE id = %s", (lab.cuotas()[1],))
    q = lab.fila(1)["cuota"]
    assert q["cuenta_cargo"] is None and q["swipe_disponible"] is False and q["sin_dudas"] is False


def test_no_disponible_importe_distinto_de_la_cuota(lab):
    lab.owner_sql("UPDATE gapto.previsiones SET importe_esperado = importe_esperado + 1 WHERE id = %s",
                  (lab.cuotas()[1],))
    assert lab.fila(1)["cuota"]["swipe_disponible"] is False


def test_no_disponible_con_realidad_previa(lab):
    hd = lab.sql("SELECT hecho_id FROM gapto.hecho_entidades WHERE entidad_id = %s LIMIT 1", (lab.f,))[0][0]
    lab.owner_sql("INSERT INTO gapto.prevision_hechos (id, prevision_id, hecho_id, importe_asignado) "
                  "VALUES (%s, %s, %s, 1)", (uuid.uuid4(), lab.cuotas()[1], hd))
    f = lab.fila(1)
    assert f["con_realidad"] is True and f["cuota"]["swipe_disponible"] is False


# ================================================================== sin_dudas = false, una a una
def test_dudas_cuenta_deshabilitada(lab):
    lab.owner_sql("UPDATE gapto.cuentas SET enabled = false WHERE id = %s", (lab.cc,))
    q = lab.fila(1)["cuota"]
    assert q["swipe_disponible"] is True and q["sin_dudas"] is False


def test_dudas_cuenta_cerrada_antes_del_vencimiento(lab):
    # el cierre exige deshabilitar (ck_cuentas__cierre_deshabilita)
    lab.owner_sql("UPDATE gapto.cuentas SET enabled = false, fecha_cierre = DATE '2026-04-10' WHERE id = %s", (lab.cc,))
    q = lab.fila(1)["cuota"]
    assert q["swipe_disponible"] is True and q["sin_dudas"] is False


def test_dudas_ledger_de_la_cuenta_posterior_al_vencimiento(lab):
    """Cuenta habilitada, con PAGAR_GASTO y abierta, pero su ledger empieza despues del vencimiento: el contrato
    comun de elegibilidad (no solo la capacidad) la descarta (AJ-DC710-01, M4)."""
    # saldo y fecha de apertura van en pareja (ck_cuentas__apertura_pareja)
    lab.owner_sql("UPDATE gapto.cuentas SET saldo_apertura = 0, fecha_inicio_ledger = DATE '2026-05-01' WHERE id = %s",
                  (lab.cc,))
    q = lab.fila(1)["cuota"]
    assert q["swipe_disponible"] is True and q["sin_dudas"] is False


def test_dudas_cuenta_sin_pagar_gasto(lab):
    lab.owner_sql("DELETE FROM gapto.cuenta_capacidades WHERE cuenta_id = %s AND capacidad_codigo = 'PAGAR_GASTO'",
                  (lab.cc,))
    q = lab.fila(1)["cuota"]
    assert q["swipe_disponible"] is True and q["sin_dudas"] is False


def test_dudas_propuesta_vacia_en_el_vencimiento(lab):
    lab.owner_sql("UPDATE gapto.entidad_participaciones SET vigente_desde = DATE '2026-05-01' WHERE entidad_id = %s",
                  (lab.f,))
    q = lab.fila(1)["cuota"]
    assert q["swipe_disponible"] is True and q["propuesta_atribucion"] == [] and q["sin_dudas"] is False


def test_dudas_participacion_de_la_cuenta_desconocida_en_el_vencimiento(lab):
    lab.owner_sql("UPDATE gapto.cuenta_participaciones SET vigente_desde = DATE '2026-05-01' WHERE cuenta_id = %s",
                  (lab.cc,))
    q = lab.fila(1)["cuota"]
    assert q["swipe_disponible"] is True and q["sin_dudas"] is False


def test_dudas_reparto_de_la_cuenta_de_cargo_distinto_aunque_el_desembolso_coincida():
    """AJ-DC710-02: cargo `cd` 100 % mia frente al prestamo 60/40, con el desembolso en `cc` (60/40, el aviso de
    L-HIP, que compara el desembolso, dice que NO hay reparto distinto)."""
    lab = LabSwipe(cargo="cd", desembolso="cc")
    assert lab.hipoteca()["aviso_reparto_distinto"] is False
    q = lab.fila(1)["cuota"]
    assert q["swipe_disponible"] is True and q["sin_dudas"] is False


def test_sin_dudas_aunque_el_desembolso_difiera():
    """AJ-DC710-02 en el otro sentido: desembolso `cd` (100 % mia, aviso de L-HIP verdadero) y cargo `cc` 60/40."""
    lab = LabSwipe(cargo="cc", desembolso="cd")
    assert lab.hipoteca()["aviso_reparto_distinto"] is True
    assert lab.fila(1)["cuota"]["sin_dudas"] is True


# ================================================================== filas ordinarias y resueltas
def test_filas_ordinarias_sin_claves_nuevas_y_resueltas_sin_bloque(lab):
    m.prevision(lab.owner, "Seguro hogar", desde="2026-05-05", importe="10.00")
    for ruta in (INICIO, PENDIENTES):
        for f in _filas(_get(lab.cli, ruta)):
            if f.get("codigo") is None:
                assert list(f) == CLAVES_C5E4FF8, f
    assert lab.pagar(1, _payload(lab.fila(1))).status_code == 200
    hoy = m.uno(lab.owner, "SELECT (now() AT TIME ZONE 'Europe/Madrid')::date")[0]
    resueltas = _get(_cliente(lab, hoy.isoformat()), PENDIENTES)["resueltas_mes"]["filas"]
    assert resueltas and all("cuota" not in f for f in resueltas)
