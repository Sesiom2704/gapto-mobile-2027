# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_293_f06_01h_pago_cuota.py
# Ruta: tests/api/test_293_f06_01h_pago_cuota.py
# Descripcion: W-HIP-02 · pago de una cuota por HTTP como gapto_runtime con RLS (F06-01H; contrato v0.4 §3.4;
#   #96; mandato T3-F06 bloque 2 v1.1 §2.3 y §11.1). Oraculos: O-H6 (pago de c1 de O-H1: -632,19 = DEUDA -298,86
#   + GASTO 333,33; resto 0; prevision REALIZADA; 1 hecho; deuda pendiente 160.000 - 298,86), O-H7 (pago doble:
#   CUOTA_NO_PENDIENTE, estado identico), O-H21 (c3 con c2 sin pagar: CUOTA_ANTERIOR_PENDIENTE), replay exacto
#   idempotente y misma intencion en otra cuota (IDENTIDAD_REUTILIZADA), VERSION_DESFASADA, FECHA_PAGO_INCOHERENTE,
#   CUENTA_DESCONOCIDA, ATRIBUCION_PROPUESTA_DESFASADA, AGREGADO_NO_ENCONTRADO, O-H10 (legacy indeterminado ->
#   SALDO_PRINCIPAL_INDETERMINADO), O-H8 (OP-22 generico con vinculo de financiacion de nivel efecto ->
#   OWNERSHIP_F07). Fechas fijas; orden explicito.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 6)
# Version: 0.1.1 (F06 T3-F06 bloque 2 F06-01H, paso 12, relevo 6): orden de locks del pago por espia (discrimina M-H-42).
# ============================================================
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from test_289_f06_01h_alta_en_compra import LabHip, huella


class LabPago(LabHip):
    def __init__(self, **kw):
        super().__init__(**kw)
        cuerpo = self.peticion_hip(hip=self.bloque(fecha_primera_cuota="2026-04-20"))
        r = self.compra(cuerpo)
        assert r.status_code == 200, r.text
        self.h0 = uuid.UUID(cuerpo["intencion_id"])
        self.f = uuid.uuid5(self.h0, "gapto.f06.hipoteca.financiacion")

    def hipoteca(self) -> dict:
        r = self.cli.get(f"/v1/propiedades/{self.pid}/hipoteca", headers=h.AUTH)
        assert r.status_code == 200, r.text
        return r.json()["hipoteca"]

    def cuerpo(self, *, intencion=None, fecha="2026-04-20", cuenta=None, version=None, partes=None, vista=None):
        hip = self.hipoteca()
        prop = [{"actor_id": self.yo, "porcentaje": "60.0000"}, {"actor_id": self.a, "porcentaje": "40.0000"}]
        return {"intencion_id": str(intencion or uuid.uuid4()),
                "row_version_esperada": hip["row_version"] if version is None else version,
                "cuenta_id": str(cuenta or self.cd), "fecha_pago": fecha,
                "atribucion": {"propuesta_vista": {"partes": prop if vista is None else vista},
                               "partes": prop if partes is None else partes}}

    def pagar(self, numero: int, cuerpo: dict):
        return self.cli.post(f"/v1/hipotecas/{self.f}/cuotas/{numero}/pago", json=cuerpo, headers=h.AUTH)


@pytest.fixture()
def lab():
    return LabPago()


def _rechazo(r, status, codigo):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text


def test_o_h6_pago_de_la_primera_cuota(lab):
    cuerpo = lab.cuerpo()
    r = lab.pagar(1, cuerpo)
    assert r.status_code == 200, r.text
    j = r.json()
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert j["idempotente"] is False and j["hecho_id"] == str(hid)
    efectos = lab.sql("SELECT tipo_efecto, importe_delta::text FROM gapto.hecho_efectos WHERE hecho_id = %s "
                      "ORDER BY tipo_efecto", (hid,))
    assert efectos == [("DEUDA", "-298.8600"), ("GASTO", "333.3300")]
    conc = lab.sql("SELECT m.importe::text, c.importe_asignado::text FROM gapto.hecho_movimientos_tesoreria c "
                   "JOIN gapto.movimientos_tesoreria m ON m.id = c.movimiento_tesoreria_id WHERE c.hecho_id = %s", (hid,))
    assert conc == [("-632.1900", "-632.1900")]
    vinc = lab.sql("SELECT x.entidad_id, e.tipo_efecto FROM gapto.hecho_entidades x JOIN gapto.hecho_efectos e "
                   "ON e.id = x.efecto_id WHERE x.hecho_id = %s", (hid,))
    assert vinc == [(lab.f, "DEUDA")]
    hip = j["hipoteca"]
    assert hip["cuotas"][0]["estado"] == "PAGADA" and hip["cuotas"][0]["hecho_pago_id"] == str(hid)
    assert hip["deuda_pendiente"] == "159701.14" and hip["cuotas_pagadas"] == 1
    assert hip["intereses_pagados"] == "333.33" and hip["capital_amortizado"] == "298.86"
    assert lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (hid,)) == [(1,)]


def test_replay_exacto_y_misma_intencion_en_otra_cuota(lab):
    cuerpo = lab.cuerpo()
    assert lab.pagar(1, cuerpo).status_code == 200
    antes = huella()
    r = lab.pagar(1, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
    assert huella() == antes
    _rechazo(lab.pagar(2, {**cuerpo, "row_version_esperada": lab.hipoteca()["row_version"]}), 409,
             "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    assert huella() == antes


def test_o_h7_pago_doble_cuota_no_pendiente(lab):
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    antes = huella()
    _rechazo(lab.pagar(1, lab.cuerpo()), 409, "CUOTA_NO_PENDIENTE")
    assert huella() == antes


def test_o_h21_cuota_anterior_pendiente(lab):
    antes = huella()
    _rechazo(lab.pagar(3, lab.cuerpo(fecha="2026-06-20")), 409, "CUOTA_ANTERIOR_PENDIENTE")
    assert huella() == antes


@pytest.mark.parametrize("caso, status, codigo", [
    ("version", 409, "VERSION_DESFASADA"),
    ("fecha_futura", 422, "FECHA_PAGO_INCOHERENTE"),
    ("cuenta_sin_pagar", 422, "CUENTA_DESCONOCIDA"),
    ("propuesta", 409, "ATRIBUCION_PROPUESTA_DESFASADA"),
    ("cuota_inexistente", 404, "AGREGADO_NO_ENCONTRADO"),
])
def test_guardas_sin_escrituras(lab, caso, status, codigo):
    numero = 1
    if caso == "version":
        cuerpo = lab.cuerpo(version=99)
    elif caso == "fecha_futura":
        cuerpo = lab.cuerpo(fecha="2026-10-11")
    elif caso == "cuenta_sin_pagar":
        cuerpo = lab.cuerpo(cuenta=h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=("RECIBIR_INGRESO",)))
    elif caso == "propuesta":
        cuerpo = lab.cuerpo(vista=[{"actor_id": lab.yo, "porcentaje": "100"}])
    else:
        cuerpo, numero = lab.cuerpo(), 361
    antes = huella()
    _rechazo(lab.pagar(numero, cuerpo), status, codigo)
    assert huella() == antes


def test_financiacion_de_otro_owner_o_inexistente(lab):
    otro = LabHip()
    r = otro.cli.post(f"/v1/hipotecas/{lab.f}/cuotas/1/pago", json=lab.cuerpo(), headers=h.AUTH)
    _rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")


def test_o_h10_legacy_indeterminado(lab):
    c2.como_owner(lab.owner, "UPDATE gapto.financiaciones SET saldo_principal_apertura = NULL, "
                             "fecha_inicio_seguimiento = NULL WHERE entidad_id = %s", (lab.f,))
    antes = huella()
    _rechazo(lab.pagar(1, lab.cuerpo()), 409, "SALDO_PRINCIPAL_INDETERMINADO")
    assert huella() == antes
    assert lab.hipoteca()["deuda_pendiente"] is None and lab.hipoteca()["deuda_indeterminada"] is True


def test_o_h8_op22_generico_con_vinculo_de_financiacion_rechazado(lab):
    """La ruta generica de contexto sigue rechazando el vinculo FINANCIACION de nivel efecto (OWNERSHIP_F07)."""
    from app.core.errores import CodigoError, ErrorMotor
    from app.core.modelos_compuesto import DatosEntidadHecho
    from app.services.contexto_service import validar_entidad_contextual
    with pytest.raises(ErrorMotor) as exc:
        def op(sesion):
            validar_entidad_contextual(sesion, uuid.uuid4(), DatosEntidadHecho(
                registro_id=uuid.uuid4(), entidad_id=lab.f, tipo_relacion="AFECTA_A", principal=False,
                efecto_id=uuid.uuid4()))
        c2.unidad().ejecutar(c2.ctx(lab.owner), op, nombre="O-H8")
    assert exc.value.codigo == CodigoError.OWNERSHIP_F07


def test_capacidad_privada_no_se_construye_desde_fuera():
    from app.core.errores import ErrorMotor
    from app.hipotecas import vinculo
    with pytest.raises(ErrorMotor):
        vinculo.Capacidad(object(), "DTO", uuid.uuid4())


# ================================================================== O-H35 (servicio y HTTP; M-H-36, G1-R)
def _prevision_c1(lab) -> tuple[uuid.UUID, int]:
    pid = uuid.uuid5(lab.f, "gapto.f06.hipoteca.prevision:1")
    return pid, lab.sql("SELECT row_version FROM gapto.previsiones WHERE id = %s", (pid,))[0][0]


def test_o_h35_servicio_corregir_estado_terminal_rechaza_la_prevision_de_una_cuota(lab):
    from app.core.errores import CodigoError, ErrorMotor
    from app.services.previsiones_service import PrevisionesService
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    pid, rv = _prevision_c1(lab)
    antes = huella()
    with pytest.raises(ErrorMotor) as exc:
        PrevisionesService(c2.unidad()).corregir_estado_terminal(c2.ctx(lab.owner), prevision_id=pid,
                                                                 row_version_esperada=rv, motivo="error de captura")
    assert exc.value.codigo == CodigoError.ESTADO_PREVISION_INCOMPATIBLE
    assert exc.value.contexto_extra == {"motivo": "PREVISION_DE_CUOTA_HIPOTECA"}
    assert huella() == antes


def test_o_h35_http_reabrir_la_prevision_de_una_cuota_pagada(lab):
    assert lab.pagar(1, lab.cuerpo()).status_code == 200
    pid, rv = _prevision_c1(lab)
    antes = huella()
    r = lab.cli.post(f"/v1/previsiones/{pid}/reabrir", json={"row_version_esperada": rv, "motivo": "error"},
                     headers=h.AUTH)
    assert r.status_code in (409, 422), r.text
    assert huella() == antes
    assert lab.sql("SELECT estado FROM gapto.previsiones WHERE id = %s", (pid,)) == [("REALIZADA",)]

# ================================================================== orden de locks del pago (R1; discrimina M-H-42)
def test_o_h_orden_locks_pago_cuenta_antes_que_financiacion(lab, monkeypatch):
    """R1 (contrato §6; AJ-T3D-08): el pago toma la cuenta (FOR NO KEY UPDATE) ANTES que la financiacion
    (FOR NO KEY UPDATE OF e, f) y esta antes que la cuota. Espia de las sentencias de la sesion del motor; mata M-H-42
    (orden invertido), que en concurrencia no es observable porque INVERSIONES serializa antes que ambas."""
    from app.core import unidad_trabajo as ut_mod

    orden: list[str] = []
    real_uno = ut_mod.SesionMotor.uno

    def espia(self, sql, params=()):
        if "FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE" in sql:
            orden.append("CUENTA")
        elif "FOR NO KEY UPDATE OF e, f" in sql:
            orden.append("FINANCIACION")
        elif "q.numero_cuota = %s FOR UPDATE" in sql:
            orden.append("CUOTA")
        return real_uno(self, sql, params)
    monkeypatch.setattr(ut_mod.SesionMotor, "uno", espia)
    r = lab.pagar(1, lab.cuerpo())
    assert r.status_code == 200, r.text
    assert orden[:3] == ["CUENTA", "FINANCIACION", "CUOTA"], orden
