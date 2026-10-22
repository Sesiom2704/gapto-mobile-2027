# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_209_f05_06_m1_corregir_anular.py
# Ruta: tests/api/test_209_f05_06_m1_corregir_anular.py
# Descripcion: F05-06 M1 por HTTP (CONTRATO_M1 v0.1; F05 §61.2 F05-D047;
#   lamina EDIT-HECHO v0.1; AJ-M5BM1-06). Con el rol real gapto_runtime y RLS:
#     - GET /v1/hechos/{id}/edicion: elegibilidad visible con su codigo y su
#       texto (pago simple, transferencia, ingreso, compra con devolucion,
#       reparto, V3, anulado), versiones del hecho y de cada movimiento, y
#       ANULADO con su motivo; otro owner 404;
#     - POST /v1/hechos/{id}/corregir-pago (OP-21P): OK con su oraculo
#       (hecho, efecto, movimiento, saldo y auditoria con el motivo); sin
#       declaracion de error 422 y con false ACONTECIMIENTO_POSTERIOR (422,
#       mapeo existente de OPERACION_NO_PERMITIDA_EN_ESTADO);
#       motivo ausente 422; VERSION_DESFASADA 409 con la edicion releida y sin
#       escritura; campos ajenos 422; reintento de la misma intencion
#       idempotente; V3, devolucion y reparto rechazados en el servidor aunque
#       el cliente los envie (revalidacion, AJ-06);
#     - POST /v1/transferencias/{id}/corregir (OP-21T): importe y cuentas;
#     - POST /v1/hechos/{id}/anular-duplicado (OP-03P): con la declaracion,
#       ANULADO y saldo restituido; false MOVIMIENTO_REAL_NO_ANULABLE (422);
#       ausente 422; compra con devolucion 409;
#     - orden de bloqueos del adaptador por ruta: cuentas nuevas -> raiz del
#       hecho en OP-21P/OP-21T; raiz sin cuentas en OP-03P.
#   Reloj fijo 2026-10-10 12:00Z (Madrid).
# Version: 0.1.0 (F05-06 M1)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import pytest

import f05_05_helpers as x
import f05_06_m2_helpers as m2
import f05_06_m3_helpers as r3
import vs01_api_helpers as h

D = decimal.Decimal


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = x.entorno()
    return owner, cli, cta, ahorro


def _uno(owner, sql, params=()):
    return h.leer(owner, sql, params)[0]


def _ed(cli, hid):
    r = cli.get(f"/v1/hechos/{hid}/edicion", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _huella(owner):
    """Recuentos y versiones de lo que M1 podria escribir (oraculo «sin escritura»)."""
    return (_uno(owner, "SELECT count(*), COALESCE(sum(row_version), 0), count(*) FILTER (WHERE estado = 'ANULADO') "
                        "FROM gapto.hechos_financieros"),
            _uno(owner, "SELECT count(*), COALESCE(sum(row_version), 0), COALESCE(sum(importe), 0) "
                        "FROM gapto.movimientos_tesoreria"),
            _uno(owner, "SELECT count(*), COALESCE(sum(importe_delta), 0) FROM gapto.hecho_efectos"),
            _uno(owner, "SELECT count(*), COALESCE(sum(importe_asignado), 0) FROM gapto.hecho_movimientos_tesoreria"),
            _uno(owner, "SELECT count(*) FROM gapto.auditoria"))


def _saldo(owner, cuenta):
    return _uno(owner, "SELECT COALESCE(sum(importe), 0) FROM gapto.movimientos_tesoreria "
                       "WHERE cuenta_id = %s AND estado = 'ACTIVO'", (cuenta,))[0]


def _pago(cli, hid, e, **kw):
    c = {"intencion_id": str(uuid.uuid4()), "row_version": e["row_version"],
         "movimiento_row_version": e["movimientos"][0]["row_version"], "motivo": "Importe mal tecleado",
         "error_de_registro": True}
    c.update(kw)
    c = {k: v for k, v in c.items() if v is not ...}
    return c, cli.post(f"/v1/hechos/{hid}/corregir-pago", json=c, headers=h.AUTH)


def _anular(cli, hid, e, **kw):
    c = {"intencion_id": str(uuid.uuid4()), "row_version": e["row_version"],
         "movimientos_row_version": {m["movimiento_id"]: m["row_version"] for m in e["movimientos"]},
         "motivo": "Lo registré dos veces", "duplicado_declarado": True}
    c.update(kw)
    c = {k: v for k, v in c.items() if v is not ...}
    return c, cli.post(f"/v1/hechos/{hid}/anular-duplicado", json=c, headers=h.AUTH)


# ==================================================================
# Lectura de elegibilidad
# ==================================================================
def test_edicion_pago_simple_elegible_con_versiones(t):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="48.72")
    e = _ed(cli, hid)
    assert (e["estado"], e["tipo"], e["importe"], e["origen_v3"], e["anulado"]) == ("ACTIVO", "GASTO", "48.72", False, None)
    assert e["acciones"] == {"corregir": {"disponible": True, "codigo": None, "motivo": None},
                             "anular_duplicado": {"disponible": True, "codigo": None, "motivo": None}}
    [m] = e["movimientos"]
    assert (m["pata"], m["cuenta"]["id"], m["importe"]) == ("SALIDA", str(cta), "48.72")
    assert m["row_version"] == _uno(owner, "SELECT row_version FROM gapto.movimientos_tesoreria WHERE id = %s",
                                    (m["movimiento_id"],))[0]


def test_edicion_transferencia_dos_patas(t):
    owner, cli, cta, ahorro = t
    hid = x.transferencia(cli, cta, ahorro, importe="500.00")
    e = _ed(cli, hid)
    assert e["acciones"]["corregir"]["disponible"] and e["acciones"]["anular_duplicado"]["disponible"]
    assert [(m["pata"], m["cuenta"]["id"]) for m in e["movimientos"]] == [("SALIDA", str(cta)), ("ENTRADA", str(ahorro))]


def test_edicion_ingreso_no_se_corrige_pero_se_anula(t):
    owner, cli, cta, _ = t
    hid = x.ingreso(cli, cta, importe="100.00")
    a = _ed(cli, hid)["acciones"]
    assert a["corregir"]["codigo"] == "TIPO_NO_SOPORTADO" and a["corregir"]["motivo"]
    assert a["anular_duplicado"]["disponible"] is True


def test_edicion_v3_limitado_y_rechazo_en_servidor(t):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="65.00")
    m2.marcar_v3(owner, hid)
    e = _ed(cli, hid)
    assert e["origen_v3"] is True
    for k in ("corregir", "anular_duplicado"):
        assert e["acciones"][k]["codigo"] == "ORIGEN_IMPORTADO" and "V3" in e["acciones"][k]["motivo"]
    base = _huella(owner)
    # El cliente no deberia enviarlo: el servidor lo rechaza (OPERACION_NO_PERMITIDA_EN_ESTADO, mapeo existente).
    _, r = _pago(cli, hid, e, importe="60.00")
    assert r.status_code == 422 and r.json()["detalle"]["motivo"] == "ORIGEN_IMPORTADO", r.text
    assert "V3" in r.json()["mensaje"]
    _, r = _anular(cli, hid, e)
    assert r.status_code == 422 and r.json()["detalle"]["motivo"] == "ORIGEN_IMPORTADO", r.text
    assert _huella(owner) == base


def test_edicion_compra_con_devolucion(t):
    owner, cli, cta, _ = t
    compra = m2.compra(cli, cta)
    c, r = m2.devolver(cli, compra)
    assert r.status_code == 200, r.text
    # La compra se corrige (el motor revalida lo ya devuelto, §3.2) pero no se anula mientras tenga devolucion.
    a = _ed(cli, compra)["acciones"]
    assert a["corregir"]["disponible"] is True and a["anular_duplicado"]["codigo"] == "DEPENDENCIAS_ACTIVAS"
    # La devolucion misma (aqui con el abono pendiente: sin movimiento) no se ofrece, con su motivo.
    devolucion = _ed(cli, uuid.UUID(c["intencion_id"]))["acciones"]["corregir"]
    assert devolucion["disponible"] is False and devolucion["codigo"] == "SIN_TESORERIA" and devolucion["motivo"]
    base = _huella(owner)
    _, r = _anular(cli, compra, _ed(cli, compra))
    assert r.status_code == 409 and r.json()["codigo"] == "HECHO_CON_REALIDAD_ASOCIADA"
    assert _huella(owner) == base


def test_edicion_gasto_con_reparto_no_se_corrige_aqui(t):
    owner, cli, cta, _ = t
    tania, carlos = r3.persona(cli, "Tania"), r3.persona(cli, "Carlos")
    c, r = r3.cena(cli, cta, tania, carlos)
    assert r.status_code == 200, r.text
    assert _ed(cli, uuid.UUID(c["intencion_id"]))["acciones"]["corregir"]["codigo"] == "REPARTO"


def test_edicion_otro_owner_404(t):
    owner, cli, cta, _ = t
    otro = x.entorno()
    ajeno = x.gasto(otro[2], otro[3], importe="5.00")
    assert cli.get(f"/v1/hechos/{ajeno}/edicion", headers=h.AUTH).status_code == 404


# ==================================================================
# OP-21P
# ==================================================================
def test_corregir_pago_importe_con_su_movimiento(t):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="48.72")
    e = _ed(cli, hid)
    saldo = _saldo(owner, cta)
    c, r = _pago(cli, hid, e, importe="47.82", motivo="  Importe mal tecleado ")
    assert r.status_code == 200, r.text
    assert r.json() == {"intencion_id": c["intencion_id"], "hecho_id": str(hid), "row_version": e["row_version"] + 1,
                        "estado": "ACTIVO", "idempotente": False}
    assert _uno(owner, "SELECT importe_total FROM gapto.hechos_financieros WHERE id = %s", (hid,))[0] == D("47.8200")
    assert _uno(owner, "SELECT importe_delta FROM gapto.hecho_efectos WHERE hecho_id = %s", (hid,))[0] == D("47.8200")
    assert _saldo(owner, cta) - saldo == D("0.90")
    motivos = h.leer(owner, "SELECT DISTINCT motivo FROM gapto.auditoria WHERE request_id = %s", (c["intencion_id"],))
    assert motivos == [("Importe mal tecleado",)]
    # Reintento de la misma intencion: idempotente, sin segunda escritura.
    base = _huella(owner)
    r2 = cli.post(f"/v1/hechos/{hid}/corregir-pago", json=c, headers=h.AUTH)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True and _huella(owner) == base


def test_corregir_pago_fecha(t):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="10.00", fecha="2026-10-05")
    _, r = _pago(cli, hid, _ed(cli, hid), fecha="2026-10-04", motivo="Fecha equivocada")
    assert r.status_code == 200, r.text
    assert _uno(owner, "SELECT fecha_hecho FROM gapto.hechos_financieros WHERE id = %s", (hid,))[0].isoformat() == "2026-10-04"


def test_corregir_pago_sin_declaracion_de_error(t):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="10.00")
    e = _ed(cli, hid)
    base = _huella(owner)
    _, r = _pago(cli, hid, e, importe="9.00", error_de_registro=...)
    assert r.status_code == 422 and "error_de_registro" in r.json()["mensaje"]
    _, r = _pago(cli, hid, e, importe="9.00", error_de_registro=False)
    assert r.status_code == 422 and r.json()["codigo"] == "OPERACION_NO_PERMITIDA_EN_ESTADO"
    assert r.json()["detalle"]["motivo"] == "ACONTECIMIENTO_POSTERIOR"
    assert "nunca fueron ciertos" in r.json()["mensaje"]
    _, r = _pago(cli, hid, e, importe="9.00", error_de_registro="true")  # StrictBool
    assert r.status_code == 422
    assert _huella(owner) == base


@pytest.mark.parametrize("motivo", [None, "   "])
def test_corregir_pago_sin_motivo(t, motivo):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="10.00")
    base = _huella(owner)
    _, r = _pago(cli, hid, _ed(cli, hid), importe="9.00", motivo=motivo)
    assert r.status_code == 422 and r.json()["codigo"] == "MOTIVO_AUSENTE" and _huella(owner) == base


def test_corregir_pago_version_desfasada_sin_pisar(t):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="48.72")
    vieja = _ed(cli, hid)
    _, r = _pago(cli, hid, vieja, importe="47.82")
    assert r.status_code == 200
    base = _huella(owner)
    _, r = _pago(cli, hid, vieja, fecha="2026-10-04")  # otro dispositivo, con la version anterior
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA"
    assert r.json()["mensaje"] == "Este registro ha cambiado mientras lo corregías. Tus cambios no se han aplicado."
    assert r.json()["detalle"]["edicion"]["importe"] == "47.82"
    assert r.json()["detalle"]["edicion"]["row_version"] == vieja["row_version"] + 1
    assert _huella(owner) == base


@pytest.mark.parametrize("campo", [{"categoria_id": str(uuid.uuid4())}, {"atribuciones_nuevas": {}},
                                   {"tercero_id": str(uuid.uuid4())}])
def test_corregir_pago_campos_ajenos_rechazados(t, campo):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="10.00")
    base = _huella(owner)
    _, r = _pago(cli, hid, _ed(cli, hid), importe="9.00", **campo)
    assert r.status_code == 422 and _huella(owner) == base


def test_corregir_pago_reparto_rechazado_en_servidor(t):
    owner, cli, cta, _ = t
    tania, carlos = r3.persona(cli, "Tania"), r3.persona(cli, "Carlos")
    c, _ = r3.cena(cli, cta, tania, carlos)
    hid = uuid.UUID(c["intencion_id"])
    e = _ed(cli, hid)
    base = _huella(owner)
    _, r = _pago(cli, hid, e, importe="40.00")
    assert r.status_code in (409, 422) and _huella(owner) == base


# ==================================================================
# OP-21T
# ==================================================================
def test_corregir_transferencia_importe_y_cuentas(t):
    owner, cli, cta, ahorro = t
    hid = x.transferencia(cli, cta, ahorro, importe="500.00")
    e = _ed(cli, hid)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": e["row_version"],
         "movimientos_row_version": {m["movimiento_id"]: m["row_version"] for m in e["movimientos"]},
         "motivo": "Importe mal tecleado", "error_de_registro": True, "importe": "450.00"}
    r = cli.post(f"/v1/transferencias/{hid}/corregir", json=c, headers=h.AUTH)
    assert r.status_code == 200, r.text
    importes = sorted(v for (v,) in h.leer(owner, "SELECT m.importe FROM gapto.hecho_movimientos_tesoreria c JOIN "
                                                  "gapto.movimientos_tesoreria m ON m.id = c.movimiento_tesoreria_id "
                                                  "WHERE c.hecho_id = %s", (hid,)))
    assert importes == [D("-450.0000"), D("450.0000")]
    # Origen y destino iguales: rechazo de campo, sin escritura.
    e = _ed(cli, hid)
    base = _huella(owner)
    c = {**c, "intencion_id": str(uuid.uuid4()), "row_version": e["row_version"], "importe": None,
         "movimientos_row_version": {m["movimiento_id"]: m["row_version"] for m in e["movimientos"]},
         "cuenta_destino_id": str(cta)}
    r = cli.post(f"/v1/transferencias/{hid}/corregir", json=c, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "MISMA_CUENTA" and _huella(owner) == base


# ==================================================================
# OP-03P
# ==================================================================
def test_anular_duplicado_con_declaracion(t):
    owner, cli, cta, _ = t
    saldo = _saldo(owner, cta)
    hid = x.gasto(cli, cta, importe="4.00")
    c, r = _anular(cli, hid, _ed(cli, hid))
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ANULADO"
    assert _saldo(owner, cta) == saldo
    e = _ed(cli, hid)  # el hecho no desaparece
    assert e["estado"] == "ANULADO" and e["anulado"]["motivo"] == "Lo registré dos veces"
    assert all(a["codigo"] == "HECHO_ANULADO" and not a["disponible"] for a in e["acciones"].values())


def test_anular_duplicado_sin_declaracion(t):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="4.00")
    e = _ed(cli, hid)
    base = _huella(owner)
    _, r = _anular(cli, hid, e, duplicado_declarado=False)
    assert r.status_code == 422 and r.json()["detalle"]["motivo"] == "MOVIMIENTO_REAL_NO_ANULABLE"
    assert "el cargo no ocurrió dos veces" in r.json()["mensaje"]
    _, r = _anular(cli, hid, e, duplicado_declarado=...)
    assert r.status_code == 422 and "duplicado_declarado" in r.json()["mensaje"]
    _, r = _anular(cli, hid, e, motivo=None)
    assert r.status_code == 422 and r.json()["codigo"] == "MOTIVO_AUSENTE"
    assert _huella(owner) == base


def test_anular_transferencia_duplicada(t):
    owner, cli, cta, ahorro = t
    s1, s2 = _saldo(owner, cta), _saldo(owner, ahorro)
    hid = x.transferencia(cli, cta, ahorro, importe="500.00")
    _, r = _anular(cli, hid, _ed(cli, hid))
    assert r.status_code == 200, r.text
    assert (_saldo(owner, cta), _saldo(owner, ahorro)) == (s1, s2)


def test_anular_version_desfasada(t):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="4.00")
    e = _ed(cli, hid)
    base = _huella(owner)
    _, r = _anular(cli, hid, {**e, "row_version": e["row_version"] + 1})
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA" and _huella(owner) == base


# ==================================================================
# Orden de bloqueos del adaptador (una prueba por ruta)
# ==================================================================
def _registrar_orden(monkeypatch):
    from app.api import ejecucion_correccion
    from app.services import integridad_posicion

    orden: list[str] = []
    original_cuentas, original_raiz = ejecucion_correccion.bloquear_cuentas, integridad_posicion.adquirir_raiz

    def cuentas(*a, **k):
        orden.append("cuentas")
        return original_cuentas(*a, **k)

    def raiz(*a, **k):
        orden.append("raiz")
        return original_raiz(*a, **k)

    monkeypatch.setattr(ejecucion_correccion, "bloquear_cuentas", cuentas)
    monkeypatch.setattr(integridad_posicion, "adquirir_raiz", raiz)
    return orden


def test_orden_locks_corregir_pago_cuenta_nueva(t, monkeypatch):
    owner, cli, cta, ahorro = t
    hid = x.gasto(cli, cta, importe="10.00")
    e = _ed(cli, hid)
    orden = _registrar_orden(monkeypatch)
    _, r = _pago(cli, hid, e, cuenta_id=str(ahorro), motivo="Otro dato mal elegido")
    assert r.status_code in (200, 409), r.text  # 409 si «Ahorro» no puede pagar gastos (capacidad)
    assert orden[:2] == ["cuentas", "raiz"] or (r.status_code == 409 and orden == ["cuentas"]), orden


def test_orden_locks_corregir_transferencia(monkeypatch):
    owner, actor, cli, cta, ahorro = x.entorno()
    otra = h.crear_cuenta(owner, [(actor, 100)], tipo="AHORRO")
    hid = x.transferencia(cli, cta, ahorro, importe="50.00")
    e = _ed(cli, hid)
    orden = _registrar_orden(monkeypatch)
    c = {"intencion_id": str(uuid.uuid4()), "row_version": e["row_version"],
         "movimientos_row_version": {m["movimiento_id"]: m["row_version"] for m in e["movimientos"]},
         "motivo": "Otro dato mal elegido", "error_de_registro": True, "cuenta_destino_id": str(otra)}
    r = cli.post(f"/v1/transferencias/{hid}/corregir", json=c, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert orden[:2] == ["cuentas", "raiz"], orden


def test_orden_locks_anular_sin_cuentas(t, monkeypatch):
    owner, cli, cta, _ = t
    hid = x.gasto(cli, cta, importe="4.00")
    e = _ed(cli, hid)
    orden = _registrar_orden(monkeypatch)
    _, r = _anular(cli, hid, e)
    assert r.status_code == 200, r.text
    assert orden and orden[0] == "raiz" and "cuentas" not in orden, orden
