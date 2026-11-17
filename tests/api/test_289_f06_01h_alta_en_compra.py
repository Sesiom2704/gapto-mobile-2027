# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_289_f06_01h_alta_en_compra.py
# Ruta: tests/api/test_289_f06_01h_alta_en_compra.py
# Descripcion: W-HIP-01 · alta de la hipoteca dentro de C-COMPRA-01 por HTTP, como gapto_runtime con RLS
#   (F06-01H; contrato v0.4 §3.2, §3.2.7; mandato T3-F06 bloque 2 v1.1 §2.1, §11.1 y §11.2). Oraculos:
#   O-H26/O-H29 + O-1/O-2 (composicion de Hd y H0), O-H14 (replay exacto), O-H15/OG-1 (replay divergente
#   parametrizado), O-H27 (Σ pagos propios = precio intacta), O-H34 (P > precio valido), O-H32/O-H33
#   (desembolso distinto de P y modalidad no representable), O-H11 (periodicidad), O-4/O-H31 (capacidad y
#   estado de la cuenta de desembolso), O-5 (la capacidad no clasifica), O-H30 (aviso_reparto_distinto),
#   O-H16 (L-COSTE sin el desembolso), O-7 (integridad de posiciones no ve la financiacion; hueco B), R-1
#   (textos de error sin «ingreso» ni «cobro»). Datos sinteticos; fechas fijas (escritura 2026-03-20, hoy
#   2026-10-10); orden explicito en todas las lecturas.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 5)
# Version: 0.1.1 (F06 T3-F06 bloque 2 F06-01H, paso 6): O-H30 por cuenta_participaciones + aviso (enmienda del STOP n.º 2).
# ============================================================
from __future__ import annotations

import datetime as dt
import re
import uuid
from decimal import Decimal

import pytest

import f06_01_b1_helpers as b
import f06_01_b2_helpers as c2
import vs01_api_helpers as h

REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
GDO_UUID = "26ee751e-aa9c-5c3b-a81c-7a28e5a5be34"
P = "160000.00"
TABLAS = c2.TABLAS_COMPRA + ("financiaciones", "financiacion_condiciones_versiones", "financiacion_cuotas",
                             "previsiones", "entidad_relaciones", "hecho_aportaciones_pago", "actores_financieros")


def huella() -> str:
    return b.huella(TABLAS)


class LabHip(c2.Lab):
    """Lab de B2 + banco (tercero EMPRESA) y cuenta C de desembolso 100 % mia con RECIBIR_INGRESO y PAGAR_GASTO."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.banco = b.tercero(self.cli, "Banco sintetico", naturaleza="EMPRESA")
        self.cd = h.crear_cuenta(self.owner, [(self.actor, 100)], capacidades=("RECIBIR_INGRESO", "PAGAR_GASTO"))

    def bloque(self, **cambios) -> dict:
        hip = {"financiador": {"tercero_id": str(self.banco)}, "importe_prestamo": P,
               "cuenta_desembolso_id": str(self.cd),
               "titularidad": {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": self.propuesta()},
               "tipo_interes": "FIJO", "tasa_anual_pct": "2.5", "numero_cuotas": 360,
               "fecha_primera_cuota": "2026-04-20", "cuenta_cargo_id": str(self.cd)}
        hip.update(cambios)
        return hip

    def peticion_hip(self, *, hip: dict | None = None, **kw) -> dict:
        cuerpo = self.peticion(gastos=[], **kw)
        cuerpo["pagos_propios"] = [{"linea_id": str(uuid.uuid4()), "rol": "FIRMA", "cuenta_id": str(self.cd),
                                    "fecha_pago": c2.ESCRITURA, "importe": "200000.00"}]
        cuerpo["hipoteca"] = self.bloque() if hip is None else hip
        return cuerpo


@pytest.fixture()
def lab():
    return LabHip()


def _ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def _rechazo(r, status: int, codigo: str, motivo: str | None = None):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text
    if motivo is not None:
        assert r.json()["motivo"] == motivo and r.json()["detalle"]["motivo"] == motivo, r.text
    return r.json()


def _ids(cuerpo) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    h0 = uuid.UUID(cuerpo["intencion_id"])
    return h0, uuid.uuid5(h0, "gapto.f06.compra.desembolso"), uuid.uuid5(h0, "gapto.f06.hipoteca.financiacion")


def _saldo(lab, cuenta) -> Decimal:
    return Decimal(lab.sql("SELECT coalesce(sum(importe), 0) FROM gapto.movimientos_tesoreria WHERE cuenta_id = %s "
                           "AND estado = 'ACTIVO'", (cuenta,))[0][0])


# ================================================================== O-H26, O-H29, O-1, O-2
def test_o_h26_o1_o2_composicion_de_hd_y_h0(lab):
    cuerpo = lab.peticion_hip()
    previo = _saldo(lab, lab.cd)
    j = _ok(lab.compra(cuerpo))
    h0, hd, f = _ids(cuerpo)
    assert j["idempotente"] is False and hd != h0
    # O-1: tipo exacto de Hd por codigo y por UUID; H0 ADQUISICION_PATRIMONIAL
    tipos = lab.sql("SELECT h.id, th.codigo, th.id::text, h.presupuestable, h.importe_total::text, h.fecha_hecho::text "
                    "FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "
                    "WHERE h.id IN (%s, %s) ORDER BY h.id = %s DESC", (h0, hd, hd))
    assert tipos[0][1:] == ("GENERACION_DERECHO_OBLIGACION", GDO_UUID, False, "160000.0000", c2.ESCRITURA)
    assert tipos[1][1] == "ADQUISICION_PATRIMONIAL"
    # O-2: exactamente un efecto DEUDA +P en Hd, de nivel efecto a la financiacion; H0 sin DEUDA
    efectos = lab.sql("SELECT e.hecho_id = %s, e.tipo_efecto, e.importe_delta::text FROM gapto.hecho_efectos e "
                      "WHERE e.hecho_id IN (%s, %s) ORDER BY e.hecho_id = %s DESC, e.tipo_efecto", (hd, h0, hd, hd))
    assert efectos == [(True, "DEUDA", "160000.0000"), (False, "VALOR_ACTIVO", "200000.0000")]
    vinculo = lab.sql("SELECT entidad_id, efecto_id IS NOT NULL, tipo_relacion, principal FROM gapto.hecho_entidades "
                      "WHERE hecho_id = %s ORDER BY id", (hd,))
    assert vinculo == [(f, True, "AFECTA_A", False)]
    # +P en C conciliado ENTERO; ningun otro movimiento en Hd
    conc = lab.sql("SELECT m.cuenta_id, m.importe::text, c.importe_asignado::text, m.fecha_movimiento::text "
                   "FROM gapto.hecho_movimientos_tesoreria c JOIN gapto.movimientos_tesoreria m "
                   "ON m.id = c.movimiento_tesoreria_id WHERE c.hecho_id = %s ORDER BY c.id", (hd,))
    assert conc == [(lab.cd, "160000.0000", "160000.0000", c2.ESCRITURA)]
    # 0 efectos INGRESO o GASTO en toda la compra; saldo de C = previo + P - pagos desde C
    assert lab.sql("SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id IN (%s, %s) "
                   "AND tipo_efecto IN ('INGRESO', 'GASTO')", (h0, hd)) == [(0,)]
    assert _saldo(lab, lab.cd) - previo == Decimal("-40000")
    # Hd pertenece a la compra (PARTE_DE propia) y la version ALTA lo apunta
    assert lab.sql("SELECT hecho_destino_id FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s", (hd,)) == [(h0,)]
    hip = j["hipoteca"]
    assert hip["financiacion_id"] == str(f) and hip["desembolso"]["hecho_id"] == str(hd)
    assert hip["desembolso"]["importe"] == P and hip["desembolso"]["cuenta_id"] == str(lab.cd)
    assert hip["deuda_pendiente"] == P and hip["deuda_indeterminada"] is False and hip["capital"] == P
    assert hip["numero_cuotas"] == 360 and hip["cuotas"][0]["cuota"] == "632.19"
    assert hip["cuotas"][0]["capital"] == "298.86" and hip["cuotas"][0]["interes"] == "333.33"
    assert hip["cuotas"][-1]["pendiente"] == "0.00" and hip["condiciones"][0]["motivo"] == "ALTA"
    assert hip["condiciones"][0]["hecho_causa_id"] == str(hd) and hip["compra_hecho_id"] == str(h0)
    # cuotas con su prevision MANUAL ABIERTA (I3: crear_manual)
    assert lab.sql("SELECT count(*), count(DISTINCT q.prevision_id), bool_and(p.estado = 'ABIERTA' "
                   "AND p.regla_version_id IS NULL AND NOT p.recalculo_automatico AND p.entidad_id = %s) "
                   "FROM gapto.financiacion_cuotas q JOIN gapto.previsiones p ON p.id = q.prevision_id "
                   "WHERE q.financiacion_entidad_id = %s", (f, f)) == [(360, 360, True)]
    assert lab.sql("SELECT count(*) FROM gapto.auditoria WHERE tabla = 'financiaciones' AND registro_id = %s "
                   "AND accion = 'CREAR'", (f,)) == [(1,)]
    assert j["aviso_reparto_distinto"] is True          # cuenta 100 % mia, prestamo 60/40 (titularidad del inmueble)


# ================================================================== O-H14, O-H15 / OG-1
def test_o_h14_replay_exacto_idempotente(lab):
    cuerpo = lab.peticion_hip()
    _ok(lab.compra(cuerpo))
    antes = huella()
    j = _ok(lab.compra(cuerpo))
    assert j["idempotente"] is True and j["hipoteca"]["numero_cuotas"] == 360
    assert huella() == antes


DIVERGENCIAS = {
    "cuota_de_mas": {"numero_cuotas": 361},
    "cuota_de_menos": {"numero_cuotas": 359},
    "otro_importe": {"importe_prestamo": "160000.01"},
    "otra_cuenta_de_desembolso": "OTRA_CUENTA",
    "otra_tasa": {"tasa_anual_pct": "2.6"},
    "otro_plazo": {"fecha_primera_cuota": "2026-05-20"},
    "otra_titularidad": "OTRA_TITULARIDAD",
}


@pytest.mark.parametrize("caso", sorted(DIVERGENCIAS))
def test_og1_o_h15_replay_divergente_rechazado_sin_escrituras(lab, caso):
    cuerpo = lab.peticion_hip()
    _ok(lab.compra(cuerpo))
    cambio = DIVERGENCIAS[caso]
    if cambio == "OTRA_CUENTA":
        cambio = {"cuenta_desembolso_id": str(h.crear_cuenta(lab.owner, [(lab.actor, 100)],
                                                             capacidades=("RECIBIR_INGRESO",)))}
    elif cambio == "OTRA_TITULARIDAD":
        cambio = {"titularidad": {"modo": "MANUAL", "partes": [{"actor_id": lab.yo, "porcentaje": "100"}]}}
    otro = {**cuerpo, "hipoteca": {**cuerpo["hipoteca"], **cambio}}
    antes = huella()
    _rechazo(lab.compra(otro), 409, REUTILIZADA)
    assert huella() == antes
    assert _ok(lab.compra(cuerpo))["idempotente"] is True


# ================================================================== O-H27, O-H34
def test_o_h27_pagos_propios_que_no_suman_el_precio(lab):
    cuerpo = lab.peticion_hip()
    cuerpo["pagos_propios"][0]["importe"] = "40000.00"
    antes = huella()
    _rechazo(lab.compra(cuerpo), 422, "SUMA_NO_CUADRA")
    assert huella() == antes


def test_o_h34_prestamo_mayor_que_el_precio_es_valido(lab):
    cuerpo = lab.peticion_hip(hip=lab.bloque(importe_prestamo="210000.00"))
    previo = _saldo(lab, lab.cd)
    j = _ok(lab.compra(cuerpo))
    assert j["hipoteca"]["capital"] == "210000.00" and j["hipoteca"]["deuda_pendiente"] == "210000.00"
    assert _saldo(lab, lab.cd) - previo == Decimal("10000")


# ================================================================== O-H32, O-H33, O-H11 y forma
@pytest.mark.parametrize("cambio, motivo", [
    ({"importe_ingresado": "159000.00"}, "DESEMBOLSO_DISTINTO_DE_CAPITAL"),
    ({"comision_retenida": "1000.00"}, "DESEMBOLSO_DISTINTO_DE_CAPITAL"),
    ({"importe_ingresado": P}, "MODALIDAD_DESEMBOLSO_NO_SOPORTADA"),
    ({"fecha_desembolso": "2026-03-25"}, "MODALIDAD_DESEMBOLSO_NO_SOPORTADA"),
    ({"pago_directo_vendedor": True}, "MODALIDAD_DESEMBOLSO_NO_SOPORTADA"),
    ({"tramos": [{"importe": "80000.00"}]}, "MODALIDAD_DESEMBOLSO_NO_SOPORTADA"),
    ({"periodicidad": "SEMANAL"}, "PERIODICIDAD_NO_SOPORTADA"),
    ({"periodicidad": "ANUAL"}, "PERIODICIDAD_NO_SOPORTADA"),
    ({"sistema": "LINEAL"}, "SISTEMA_NO_SOPORTADO"),
    ({"fecha_primera_cuota": c2.ESCRITURA}, "PRIMERA_CUOTA_NO_POSTERIOR_A_LA_ESCRITURA"),
    ({"tasa_anual_pct": "30.01"}, "VALORES_FUERA_DE_RANGO"),
    ({"tasa_anual_pct": "2.12345"}, "VALORES_FUERA_DE_RANGO"),
    ({"numero_cuotas": 601}, "VALORES_FUERA_DE_RANGO"),
    ({"importe_prestamo": "0.00"}, "VALORES_FUERA_DE_RANGO"),
    ({"tipo_interes": "MIXTO"}, "VALORES_FUERA_DE_RANGO"),
    ({"cuenta_cargo_id": None}, "DATO_OBLIGATORIO_AUSENTE"),
])
def test_o_h32_o_h33_o_h11_condiciones_incompletas_sin_escrituras(lab, cambio, motivo):
    antes = huella()
    _rechazo(lab.compra(lab.peticion_hip(hip=lab.bloque(**cambio))), 422, "CONDICIONES_INCOMPLETAS", motivo)
    assert huella() == antes


def test_campo_no_previsto_en_el_bloque_es_entrada_invalida(lab):
    _rechazo(lab.compra(lab.peticion_hip(hip=lab.bloque(comisiones_periodicas="10.00"))), 422, "ENTRADA_INVALIDA")


# ================================================================== O-4, O-5, O-H31 (capacidad y estado de la cuenta)
@pytest.mark.parametrize("capacidades", [(), ("TRANSFERIR_ENTRADA",), ("PAGAR_GASTO",)])
def test_o4_cuenta_de_desembolso_sin_recibir_ingreso(lab, capacidades):
    otra = h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=capacidades)
    antes = huella()
    j = _rechazo(lab.compra(lab.peticion_hip(hip=lab.bloque(cuenta_desembolso_id=str(otra)))), 409,
                 "CUENTA_SIN_CAPACIDAD")
    assert j["detalle"]["operacion"] == "DESEMBOLSO_FINANCIACION" and j["detalle"]["capacidad"] == "RECIBIR_INGRESO"
    assert not re.search(r"ingres|cobr", j["mensaje"], re.IGNORECASE)
    assert huella() == antes


def test_o4_o5_positivo_con_solo_recibir_ingreso_y_sin_efecto_ingreso(lab):
    solo = h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=("RECIBIR_INGRESO",))
    cuerpo = lab.peticion_hip(hip=lab.bloque(cuenta_desembolso_id=str(solo)))
    _ok(lab.compra(cuerpo))
    _, hd, _ = _ids(cuerpo)
    assert lab.sql("SELECT th.codigo, array_agg(e.tipo_efecto ORDER BY e.id) FROM gapto.hechos_financieros x "
                   "JOIN gapto.tipos_hecho th ON th.id = x.tipo_hecho_id JOIN gapto.hecho_efectos e ON e.hecho_id = x.id "
                   "WHERE x.id = %s GROUP BY th.codigo", (hd,)) == [("GENERACION_DERECHO_OBLIGACION", ["DEUDA"])]


@pytest.mark.parametrize("sql", [
    "UPDATE gapto.cuentas SET fecha_cierre = DATE '2026-03-01', enabled = false WHERE id = %s",
    "UPDATE gapto.cuentas SET fecha_inicio_ledger = DATE '2026-03-21', saldo_apertura = 0 WHERE id = %s",
    "UPDATE gapto.cuentas SET enabled = false WHERE id = %s",
])
def test_o_h31_cuenta_de_desembolso_cerrada_ledger_posterior_o_deshabilitada(lab, sql):
    otra = h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=("RECIBIR_INGRESO",))
    c2.como_owner(lab.owner, sql, (otra,))
    antes = huella()
    j = _rechazo(lab.compra(lab.peticion_hip(hip=lab.bloque(cuenta_desembolso_id=str(otra)))), 409,
                 "CUENTA_SIN_CAPACIDAD")
    assert not re.search(r"ingres|cobr", j["mensaje"], re.IGNORECASE)
    assert huella() == antes


def test_cuenta_de_cargo_sin_pagar_gasto(lab):
    otra = h.crear_cuenta(lab.owner, [(lab.actor, 100)], capacidades=("RECIBIR_INGRESO",))
    antes = huella()
    _rechazo(lab.compra(lab.peticion_hip(hip=lab.bloque(cuenta_cargo_id=str(otra)))), 422, "CUENTA_DESCONOCIDA")
    assert huella() == antes


# ================================================================== O-H30 (aviso_reparto_distinto)
def test_o_h30_distribuciones_distintas_aviso_y_atribuciones_conservadas(lab):
    cuerpo = lab.peticion_hip()                     # cuenta 100 % mia; prestamo = titularidad del inmueble 60/40
    j = _ok(lab.compra(cuerpo))
    _, hd, _ = _ids(cuerpo)
    assert j["aviso_reparto_distinto"] is True and j["hipoteca"]["aviso_reparto_distinto"] is True
    atrib = lab.sql("SELECT a.actor_id::text, a.importe_atribuido::text FROM gapto.efecto_atribuciones a "
                    "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s ORDER BY 1", (hd,))
    assert sorted(atrib) == sorted([(lab.yo, "96000.0000"), (lab.a, "64000.0000")])
    # O-H30 enmendado (firma STOP n.º 2, 5f3f5f8e…): la entrada sigue la titularidad de la cuenta
    # (cuenta_participaciones 100 % mia) sin aportaciones; la deuda, la del prestamo (60/40)
    assert lab.sql("SELECT actor_id, porcentaje::text FROM gapto.cuenta_participaciones WHERE cuenta_id = %s",
                   (lab.cd,)) == [(lab.actor, "100.0000")]
    assert lab.sql("SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s", (hd,)) == [(0,)]


def test_o_h30_distribuciones_iguales_sin_aviso(lab):
    partes = [{"actor_id": str(lab.actor), "porcentaje": "50"}, {"actor_id": lab.a, "porcentaje": "50"}]
    cuerpo = lab.peticion_hip(hip=lab.bloque(cuenta_desembolso_id=str(lab.c2), cuenta_cargo_id=str(lab.c2),
                                             titularidad={"modo": "MANUAL", "partes": partes}))
    j = _ok(lab.compra(cuerpo))
    assert j["aviso_reparto_distinto"] is False and j["hipoteca"]["aviso_reparto_distinto"] is False


# ================================================================== O-H16 (L-COSTE) y O-7 (hueco B)
def test_o_h16_coste_de_adquisicion_sin_desembolso_ni_deuda(lab):
    cuerpo = lab.peticion_hip()
    j = _ok(lab.compra(cuerpo))
    assert j["compra"]["coste_adquisicion"]["total"] == "200000.00"
    assert c2.leer_coste(lab.cli, lab.pid)["ADQUISICION"]["total"] == "200000.00"


def test_o7_integridad_de_posiciones_no_ve_la_financiacion(lab):
    from app.services import integridad_posicion
    cuerpo = lab.peticion_hip()
    _ok(lab.compra(cuerpo))
    _, hd, _ = _ids(cuerpo)

    def operacion(sesion):
        posiciones = integridad_posicion.adquirir_raiz(sesion, lab.owner, hechos=[hd])
        integridad_posicion.validar(sesion, integridad_posicion.fotografiar(sesion, posiciones, hechos=[hd]))
        return posiciones
    assert c2.unidad().ejecutar(c2.ctx(lab.owner), operacion, nombre="O-7") == []
