# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_158_f05_01_c07_magnitudes.py
# Ruta: tests/api/test_158_f05_01_c07_magnitudes.py
# Descripcion: Bateria de aceptacion de S6-C07 (F05-D014 §28.4): C07 con el
#   servidor como autoridad, wire estructural (AJ-C07-02), identidad derivada
#   (AJ-C07-03), identidad antes de C07 (AJ-C07-04), unidad snapshot
#   (AJ-C07-05), valor sin redondeo (AJ-C07-06), orden de locks con
#   interleaving controlado (AJ-C07-07, WM 12C.1) y lectura de capturabilidad
#   (AJ-C07-08).
#   Todo rechazo C07 se comprueba SIN mutaciones (huella del agregado a cero,
#   incluidas hecho_magnitudes y auditoria).
#   Base local desechable 0001..0340 (estos tests confirman filas). Datos
#   sinteticos, creados como gapto_owner con la GUC del tenant (WM 12C.7).
#
#   v0.2.0 (auditoria S6-C07, AJ-S6C07-01): `test_valor_demasiado_largo_422`
#   fijaba la decision D2 (rechazada). Se sustituye por dos discriminantes
#   del contrato §28.2: un decimal canonico largo fuera de capacidad llega a
#   C07 -> 409 MAGNITUD_VALOR_NO_VALIDO sin mutaciones; y un valor canonico
#   largo pero numericamente valido (ceros de cola) se admite sin redondeo.
#   Ambos fallan contra 203891b0 (WM 12C.2).
#
#   v0.3.0 (F05-01 S6-WIRE+UI (este mandato); F05 §28.3): fin de la transicion.
#   Un payload VS-01 sin `categoria` ya no es de compatibilidad: 422 sin hecho
#   ni filas de hecho_magnitudes.
#
#   v0.4.0 (F05-01 S7-MAG (F05-D020 D-MAG-04), commit 1): la lectura del arbol
#   incluye `asociacion_id` en cada magnitud; el test de campos lo exige igual
#   a la PK de la asociacion persistida (se extiende, no se relaja) y uno
#   nuevo comprueba que cada asociacion visible tiene identidad propia.
# Version: 0.4.0
# ============================================================

from __future__ import annotations

import threading
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

URL = "/v1/intenciones/gasto-pagado"


@pytest.fixture()
def tenant():
    owner, actor = h.crear_tenant()
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    return owner, actor, cuenta


# ------------------------------------------------------------------ fixtures
def _magnitud(owner, nombre=None, *, unidad="l", precision=2, enabled=True) -> uuid.UUID:
    mid = uuid.uuid4()
    h.como_owner(
        owner,
        "INSERT INTO gapto.magnitudes (id, owner_user_id, nombre, unidad_default, precision_decimales, enabled) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (mid, owner, nombre or f"Mag {mid.hex[:8]}", unidad, precision, enabled),
    )
    return mid


def _asociar(owner, categoria, magnitud, *, obligatoria, orden=0) -> uuid.UUID:
    cm = uuid.uuid4()
    h.como_owner(
        owner,
        "INSERT INTO gapto.categoria_magnitudes (id, categoria_id, magnitud_id, obligatoria, orden) "
        "VALUES (%s,%s,%s,%s,%s)",
        (cm, categoria, magnitud, obligatoria, orden),
    )
    return cm


def _cuerpo(cuenta, categoria, magnitudes=None, **extra) -> dict:
    cat = {"estado": "CATEGORIA", "categoria_id": str(categoria)}
    if magnitudes is not None:
        cat["magnitudes"] = [{"magnitud_id": str(m), "valor": v} for m, v in magnitudes]
    return h.intencion(cuenta, categoria=cat, **extra)


def _hid(cuerpo) -> uuid.UUID:
    return uuid.UUID(cuerpo["intencion_id"])


def _filas_magnitud(owner, hid) -> list[tuple]:
    return h.leer(
        owner,
        "SELECT id, magnitud_id, valor, unidad FROM gapto.hecho_magnitudes WHERE hecho_id=%s ORDER BY magnitud_id",
        (hid,),
    )


def _cero(owner, hid) -> None:
    huella = fh.huella_agregado(owner, hid)
    huella["magnitudes"] = len(_filas_magnitud(owner, hid))
    assert huella == {
        "hechos": 0, "efectos": 0, "conciliaciones": 0, "aportaciones": 0, "auditoria": 0, "magnitudes": 0,
    }


def _post(owner, cuerpo):
    return h.cliente(owner).post(URL, json=cuerpo, headers=h.AUTH)


def _rechazo(r, codigo) -> None:
    assert r.status_code == 409, r.text
    assert r.json()["codigo"] == codigo and r.json()["reintentable"] is False


# ------------------------------------------------------------------ transicion
def test_payload_vs01_sin_categoria_es_422_sin_escritura(tenant):
    owner, _, cuenta = tenant
    cuerpo = h.intencion(cuenta)
    del cuerpo["categoria"]
    r = _post(owner, cuerpo)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text
    assert _filas_magnitud(owner, _hid(cuerpo)) == []


def test_codigo_transitorio_retirado(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Combustible", "GASTO")
    _asociar(owner, cat, _magnitud(owner), obligatoria=True)
    r = _post(owner, _cuerpo(cuenta, cat))
    assert r.json()["codigo"] != "CATEGORIA_REQUIERE_MAGNITUDES"


# ------------------------------------------------------------------ captura valida
def test_categoria_sin_magnitudes(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Ropa", "GASTO")
    cuerpo = _cuerpo(cuenta, cat)
    assert _post(owner, cuerpo).status_code == 200
    assert _filas_magnitud(owner, _hid(cuerpo)) == []


def test_opcional_omitida(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Limpieza", "GASTO")
    _asociar(owner, cat, _magnitud(owner), obligatoria=False)
    cuerpo = _cuerpo(cuenta, cat, [])
    assert _post(owner, cuerpo).status_code == 200
    assert _filas_magnitud(owner, _hid(cuerpo)) == []


def test_obligatoria_informada_con_unidad_snapshot_e_identidad_derivada(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Combustible", "GASTO")
    m = _magnitud(owner, "Litros", unidad="l", precision=2)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "42.37")])
    r = _post(owner, cuerpo)
    assert r.status_code == 200, r.text
    hid = _hid(cuerpo)
    [(fila_id, mid, valor, unidad)] = _filas_magnitud(owner, hid)
    assert mid == m and str(valor) == "42.370000" and unidad == "l"
    assert fila_id == uuid.uuid5(hid, f"magnitud:{m}")


def test_varias_magnitudes_y_orden_del_array_no_es_identidad(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Electricidad", "GASTO")
    a = _magnitud(owner, "kWh", unidad="kWh", precision=3)
    b = _magnitud(owner, "Dias", unidad="d", precision=0)
    _asociar(owner, cat, a, obligatoria=True)
    _asociar(owner, cat, b, obligatoria=False)
    cuerpo = _cuerpo(cuenta, cat, [(a, "123.456"), (b, "30")])
    assert _post(owner, cuerpo).status_code == 200
    invertido = dict(cuerpo)
    invertido["categoria"] = dict(cuerpo["categoria"], magnitudes=list(reversed(cuerpo["categoria"]["magnitudes"])))
    r = _post(owner, invertido)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
    assert len(_filas_magnitud(owner, _hid(cuerpo))) == 2


@pytest.mark.parametrize(
    "valor,precision,guardado",
    [("0", 2, "0.000000"), ("-2.5", 2, "-2.500000"), ("1.230", 2, "1.230000"), ("3.0", 0, "3.000000"),
     ("999999999999.999999", 6, "999999999999.999999"), ("-999999999999", 0, "-999999999999.000000")],
)
def test_valores_admitidos_sin_redondeo(tenant, valor, precision, guardado):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Cat {valor}", "GASTO")
    m = _magnitud(owner, precision=precision)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, valor)])
    assert _post(owner, cuerpo).status_code == 200
    [(_, _, v, _)] = _filas_magnitud(owner, _hid(cuerpo))
    assert str(v) == guardado


# ------------------------------------------------------------------ rechazos C07 (409)
def test_obligatoria_ausente(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Combustible", "GASTO")
    _asociar(owner, cat, _magnitud(owner), obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [])
    _rechazo(_post(owner, cuerpo), "MAGNITUD_OBLIGATORIA_AUSENTE")
    _cero(owner, _hid(cuerpo))


def test_obligatoria_deshabilitada_hace_la_categoria_no_capturable(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Combustible", "GASTO")
    m = _magnitud(owner, enabled=False)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "10")])
    _rechazo(_post(owner, cuerpo), "CATEGORIA_MAGNITUD_NO_DISPONIBLE")
    _cero(owner, _hid(cuerpo))


@pytest.mark.parametrize("origen", ["NO_ASOCIADA", "INEXISTENTE", "AJENA", "OPCIONAL_DESHABILITADA"])
def test_magnitud_no_admitida(tenant, origen):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Hogar", "GASTO")
    if origen == "NO_ASOCIADA":
        m = _magnitud(owner)
    elif origen == "INEXISTENTE":
        m = uuid.uuid4()
    elif origen == "AJENA":
        otro, _ = h.crear_tenant()
        m = _magnitud(otro)
    else:
        m = _magnitud(owner, enabled=False)
        _asociar(owner, cat, m, obligatoria=False)
    cuerpo = _cuerpo(cuenta, cat, [(m, "1")])
    r = _post(owner, cuerpo)
    _rechazo(r, "MAGNITUD_NO_ADMITIDA")
    _cero(owner, _hid(cuerpo))


@pytest.mark.parametrize(
    "valor,precision", [("1.234", 2), ("3.5", 0), ("0.0000001", 6), ("1000000000000", 6), ("-1000000000000", 0)]
)
def test_valor_fuera_de_precision_o_capacidad_sin_redondeo_ni_escritura(tenant, valor, precision):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Cat {valor}", "GASTO")
    m = _magnitud(owner, precision=precision)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, valor)])
    _rechazo(_post(owner, cuerpo), "MAGNITUD_VALOR_NO_VALIDO")
    _cero(owner, _hid(cuerpo))


def test_orden_de_evaluacion_de_los_codigos(tenant):
    """§28.2: NO_DISPONIBLE -> NO_ADMITIDA -> OBLIGATORIA_AUSENTE -> VALOR."""
    owner, _, cuenta = tenant
    ajena = _magnitud(owner)  # existe pero no esta asociada
    # 1 gana a 2: obligatoria deshabilitada + magnitud no asociada.
    c1 = fh.crear_categoria(owner, "Orden 1", "GASTO")
    _asociar(owner, c1, _magnitud(owner, enabled=False), obligatoria=True)
    _rechazo(_post(owner, _cuerpo(cuenta, c1, [(ajena, "1")])), "CATEGORIA_MAGNITUD_NO_DISPONIBLE")
    # 2 gana a 3: magnitud no asociada + obligatoria ausente.
    c2 = fh.crear_categoria(owner, "Orden 2", "GASTO")
    _asociar(owner, c2, _magnitud(owner), obligatoria=True)
    _rechazo(_post(owner, _cuerpo(cuenta, c2, [(ajena, "1")])), "MAGNITUD_NO_ADMITIDA")
    # 3 gana a 4: obligatoria ausente + opcional con exceso de precision.
    c3 = fh.crear_categoria(owner, "Orden 3", "GASTO")
    _asociar(owner, c3, _magnitud(owner), obligatoria=True)
    opc = _magnitud(owner, precision=0)
    _asociar(owner, c3, opc, obligatoria=False)
    _rechazo(_post(owner, _cuerpo(cuenta, c3, [(opc, "1.5")])), "MAGNITUD_OBLIGATORIA_AUSENTE")


# ------------------------------------------------------------------ wire estructural (422)
def _con_categoria_cruda(cuenta, categoria: dict) -> dict:
    return h.intencion(cuenta, categoria=categoria)


@pytest.mark.parametrize(
    "fabricar",
    [
        pytest.param(lambda c, m: {"estado": "CATEGORIA", "categoria_id": str(c), "magnitudes": None}, id="null"),
        pytest.param(lambda c, m: {"estado": "CATEGORIA", "categoria_id": str(c), "magnitudes": [
            {"magnitud_id": str(m), "valor": "1"}, {"magnitud_id": str(m), "valor": "2"}]}, id="duplicada"),
        pytest.param(lambda c, m: {"estado": "CATEGORIA", "categoria_id": str(c), "magnitudes": [
            {"magnitud_id": str(m), "valor": "1", "unidad": "l"}]}, id="unidad"),
        pytest.param(lambda c, m: {"estado": "SIN_CATEGORIA", "magnitudes": [
            {"magnitud_id": str(m), "valor": "1"}]}, id="sin_categoria_con_magnitud"),
        pytest.param(lambda c, m: {"estado": "SIN_CATEGORIA", "magnitudes": []}, id="sin_categoria_lista_vacia"),
        pytest.param(lambda c, m: {"estado": "CATEGORIA", "categoria_id": str(c), "magnitudes": [
            {"magnitud_id": str(m), "valor": 1.5}]}, id="numero_json"),
        pytest.param(lambda c, m: {"estado": "CATEGORIA", "categoria_id": str(c), "magnitudes": [
            {"magnitud_id": str(m)}]}, id="sin_valor"),
        pytest.param(lambda c, m: {"estado": "CATEGORIA", "categoria_id": str(c), "magnitudes": [
            {"magnitud_id": str(m), "valor": None}]}, id="valor_null"),
    ],
)
def test_wire_estructural_422(tenant, fabricar):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Wire", "GASTO")
    m = _magnitud(owner)
    _asociar(owner, cat, m, obligatoria=False)
    cuerpo = _con_categoria_cruda(cuenta, fabricar(cat, m))
    r = _post(owner, cuerpo)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text
    _cero(owner, _hid(cuerpo))


@pytest.mark.parametrize(
    "valor", ["1,5", "1e3", "1E3", "+1", "NaN", "Infinity", "-Infinity", "01", "1.", ".5", " 1", "1 ", "",
              "-0", "-0.00", "0x10", "1_000", "٣"],
)
def test_valor_no_canonico_422(tenant, valor):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Sintaxis", "GASTO")
    m = _magnitud(owner)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, valor)])
    r = _post(owner, cuerpo)
    assert r.status_code == 422, (valor, r.text)
    _cero(owner, _hid(cuerpo))


def test_dto_rechaza_estructura_antes_de_llegar_a_la_base():
    """El 422 estructural lo decide el DTO, no una defensa posterior de OP-22
    (que tambien rechazaria identidades repetidas)."""
    from pydantic import ValidationError

    from app.api.dto_vs01 import CategoriaSeleccionada

    m = str(uuid.uuid4())
    base = {"estado": "CATEGORIA", "categoria_id": str(uuid.uuid4())}
    for magnitudes in (
        [{"magnitud_id": m, "valor": "1"}, {"magnitud_id": m, "valor": "1"}],
        None,
        [{"magnitud_id": m, "valor": "1", "unidad": "l"}],
        [{"magnitud_id": m, "valor": 1}],
    ):
        with pytest.raises(ValidationError):
            CategoriaSeleccionada.model_validate(dict(base, magnitudes=magnitudes))
    assert CategoriaSeleccionada.model_validate(base).magnitudes == ()


@pytest.mark.parametrize("valor", ["1" * 41, "-" + "9" * 60, "123456789012" + "3" * 30 + ".5"])
def test_valor_canonico_largo_fuera_de_capacidad_es_409(tenant, valor):
    """§28.2: forma valida pero fuera de rango -> C07, nunca 422 del DTO."""
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Largo", "GASTO")
    m = _magnitud(owner, precision=6)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, valor)])
    _rechazo(_post(owner, cuerpo), "MAGNITUD_VALOR_NO_VALIDO")
    _cero(owner, _hid(cuerpo))


def test_valor_canonico_largo_numericamente_valido_se_admite(tenant):
    """AJ-C07-06: los ceros decimales de cola no consumen precision."""
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Colas", "GASTO")
    m = _magnitud(owner, precision=2)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "1.25" + "0" * 60)])
    assert _post(owner, cuerpo).status_code == 200
    [(_, _, v, _)] = _filas_magnitud(owner, _hid(cuerpo))
    assert str(v) == "1.250000"


# ------------------------------------------------------------------ identidad antes de C07
def test_reintento_identico_tras_commit_es_idempotente(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Agua", "GASTO")
    m = _magnitud(owner, unidad="m3", precision=3)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "12.5")])
    assert _post(owner, cuerpo).status_code == 200
    r = _post(owner, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
    assert len(_filas_magnitud(owner, _hid(cuerpo))) == 1


@pytest.mark.parametrize(
    "cambio",
    [
        "UPDATE gapto.magnitudes SET enabled=false WHERE id=%s",
        "UPDATE gapto.magnitudes SET unidad_default='galon' WHERE id=%s",
        "UPDATE gapto.magnitudes SET precision_decimales=0 WHERE id=%s",
    ],
    ids=["desactivada", "unidad_cambiada", "precision_reducida"],
)
def test_reintento_tras_cambio_de_configuracion_sigue_idempotente(tenant, cambio):
    """AJ-C07-04/05: una intencion materializada no se revalida y el snapshot
    de unidad no se reinterpreta."""
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Gasoil", "GASTO")
    m = _magnitud(owner, unidad="l", precision=2)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "40.25")])
    assert _post(owner, cuerpo).status_code == 200
    h.como_owner(owner, cambio, (m,))
    r = _post(owner, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
    [(_, _, valor, unidad)] = _filas_magnitud(owner, _hid(cuerpo))
    assert str(valor) == "40.250000" and unidad == "l"


def test_reintento_tras_quitar_la_asociacion_sigue_idempotente(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Taxi", "GASTO")
    m = _magnitud(owner, unidad="km")
    cm = _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "8.4")])
    assert _post(owner, cuerpo).status_code == 200
    h.como_owner(owner, "DELETE FROM gapto.categoria_magnitudes WHERE id=%s", (cm,))
    r = _post(owner, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text


@pytest.mark.parametrize("variante", ["OTRO_VALOR", "SIN_LA_OPCIONAL", "CON_OTRA_OPCIONAL"])
def test_misma_intencion_con_otras_magnitudes_no_es_idempotente(tenant, variante):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Gas", "GASTO")
    obl = _magnitud(owner)
    opc = _magnitud(owner)
    otra = _magnitud(owner)
    _asociar(owner, cat, obl, obligatoria=True)
    _asociar(owner, cat, opc, obligatoria=False)
    _asociar(owner, cat, otra, obligatoria=False)
    cuerpo = _cuerpo(cuenta, cat, [(obl, "5"), (opc, "1")])
    assert _post(owner, cuerpo).status_code == 200
    mags = {
        "OTRO_VALOR": [(obl, "6"), (opc, "1")],
        "SIN_LA_OPCIONAL": [(obl, "5")],
        "CON_OTRA_OPCIONAL": [(obl, "5"), (opc, "1"), (otra, "2")],
    }[variante]
    distinto = dict(cuerpo, categoria=_cuerpo(cuenta, cat, mags)["categoria"])
    r = _post(owner, distinto)
    _rechazo(r, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    filas = _filas_magnitud(owner, _hid(cuerpo))
    assert sorted((f[1], str(f[2])) for f in filas) == sorted([(obl, "5.000000"), (opc, "1.000000")])


def test_mismo_valor_con_otra_representacion_es_la_misma_intencion(tenant):
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Pan", "GASTO")
    m = _magnitud(owner, precision=2)
    _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "1.23")])
    assert _post(owner, cuerpo).status_code == 200
    otra = dict(cuerpo, categoria=_cuerpo(cuenta, cat, [(m, "1.230")])["categoria"])
    r = _post(owner, otra)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text


# ------------------------------------------------------------------ concurrencia (WM 12C.1)
def _lanzar(owner, cuerpo, salida):
    hilo = threading.Thread(target=lambda: salida.update(r=_post(owner, cuerpo)))
    hilo.start()
    return hilo


_BLOQUEOS_A = {
    "MAGNITUD": ("UPDATE gapto.magnitudes SET enabled=false WHERE id=%s", "CATEGORIA_MAGNITUD_NO_DISPONIBLE"),
    "ASOCIACION": ("UPDATE gapto.categoria_magnitudes SET obligatoria=true WHERE id=%s", "MAGNITUD_OBLIGATORIA_AUSENTE"),
}


@pytest.mark.parametrize("objetivo", sorted(_BLOQUEOS_A))
@pytest.mark.parametrize("desenlace_b", ["COMMIT", "ROLLBACK"])
def test_orden_1_configuracion_primero_registro_espera_y_relee(tenant, objetivo, desenlace_b):
    """B modifica la magnitud (la desactiva) o la asociacion (la vuelve
    obligatoria) y retiene el lock. El registro A debe ESPERAR en su FOR SHARE
    y, al terminar B, decidir sobre el estado confirmado:
      COMMIT   -> rechazo C07 sin escritura;
      ROLLBACK -> se registra.
    Sin FOR SHARE, A no espera y decide sobre la fila anterior."""
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Conc {objetivo} {desenlace_b}", "GASTO")
    if objetivo == "MAGNITUD":
        m = _magnitud(owner)
        _asociar(owner, cat, m, obligatoria=True)
        cuerpo = _cuerpo(cuenta, cat, [(m, "3")])
        fila = m
    else:
        m = _magnitud(owner)
        fila = _asociar(owner, cat, m, obligatoria=False)
        cuerpo = _cuerpo(cuenta, cat, [])
    sql, codigo = _BLOQUEOS_A[objetivo]
    salida: dict = {}
    b = fh.sesion_owner(owner)
    try:
        b.execute(sql, (fila,))
        pid_b = fh.pid_servidor(b)
        hilo = _lanzar(owner, cuerpo, salida)
        assert fh.esperar_bloqueo((pid_b,)), "el registro no espero el lock"
        assert hilo.is_alive() and "r" not in salida
        b.execute(desenlace_b)
    finally:
        b.close()
    hilo.join(timeout=15)
    assert not hilo.is_alive()
    r = salida["r"]
    if desenlace_b == "COMMIT":
        _rechazo(r, codigo)
        _cero(owner, _hid(cuerpo))
    else:
        assert r.status_code == 200, r.text


_MUTACIONES_B = {
    "MAGNITUD": "UPDATE gapto.magnitudes SET enabled=false WHERE id=%s",
    "ASOCIACION": "UPDATE gapto.categoria_magnitudes SET obligatoria=false WHERE id=%s",
}


@pytest.mark.parametrize("objetivo", sorted(_MUTACIONES_B))
def test_orden_2_registro_primero_configuracion_espera(tenant, objetivo):
    """A queda retenido DESPUES de C07 (C bloquea la fila del usuario que el
    INSERT del hecho necesita en FOR KEY SHARE). B intenta modificar la
    magnitud o la asociacion y debe ESPERAR el FOR SHARE de A. Al liberar C,
    A confirma con la magnitud y solo despues B aplica su cambio."""
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, f"Retenida {objetivo}", "GASTO")
    m = _magnitud(owner)
    cm = _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "7.5")])
    fila = m if objetivo == "MAGNITUD" else cm
    salida: dict = {}
    c = fh.sesion_owner(owner)
    b = None
    hilo_b = None
    try:
        c.execute("SELECT id FROM gapto.usuarios WHERE id=%s FOR UPDATE", (owner,))
        pid_c = fh.pid_servidor(c)
        hilo_a = _lanzar(owner, cuerpo, salida)
        assert fh.esperar_bloqueo((pid_c,)), "el registro no llego a retenerse tras C07"
        b = fh.sesion_owner(owner)
        pid_b = fh.pid_servidor(b)

        def _mutar():
            try:
                b.execute(_MUTACIONES_B[objetivo], (fila,))
                salida["b"] = "aplicada"
            except psycopg.Error as exc:  # pragma: no cover - diagnostico
                salida["b"] = type(exc).__name__

        hilo_b = threading.Thread(target=_mutar)
        hilo_b.start()
        assert fh.esperar_bloqueo((pid_c,), minimo=2), "B no espero el FOR SHARE de C07"
        assert pid_b in fh.pids_esperando((pid_b,))
        assert "b" not in salida
        c.execute("COMMIT")
        hilo_a.join(timeout=15)
        assert not hilo_a.is_alive()
        hilo_b.join(timeout=15)
        assert salida.get("b") == "aplicada"
        b.execute("COMMIT")
    finally:
        c.close()
        if b is not None:
            b.close()
    assert salida["r"].status_code == 200, salida["r"].text
    assert [f[1] for f in _filas_magnitud(owner, _hid(cuerpo))] == [m]


def _bloqueadores(pid: int) -> list[int]:
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        return mon.execute("SELECT pg_blocking_pids(%s)", (pid,)).fetchone()[0]


def _pid_en_espera(excluidos: tuple[int, ...], limite_s: float = 8.0) -> int:
    fin = time.monotonic() + limite_s
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            fila = mon.execute(
                "SELECT pid FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> ALL(%s) AND pid <> pg_backend_pid() AND wait_event_type = 'Lock'",
                (list(excluidos),),
            ).fetchone()
            if fila:
                return fila[0]
            time.sleep(0.05)
    raise AssertionError("el registro no quedo en espera")


def _esperar_bloqueador(pid: int, esperado: int, limite_s: float = 8.0) -> None:
    fin = time.monotonic() + limite_s
    visto = None
    while time.monotonic() < fin:
        visto = _bloqueadores(pid)
        if visto == [esperado]:
            return
        time.sleep(0.05)
    raise AssertionError(f"bloqueador esperado {esperado}, visto {visto}")


def test_orden_de_locks_cuenta_categoria_asociacion_magnitud(tenant):
    """AJ-C07-07: cuatro sesiones retienen, cada una, UNA de las filas que el
    registro necesita. El registro debe quedar bloqueado sucesivamente por la
    cuenta, la categoria, la asociacion y la magnitud, en ese orden: se
    observa con pg_blocking_pids y se libera cada retenedor por turno."""
    owner, _, cuenta = tenant
    cat = fh.crear_categoria(owner, "Orden locks", "GASTO")
    m = _magnitud(owner)
    cm = _asociar(owner, cat, m, obligatoria=True)
    cuerpo = _cuerpo(cuenta, cat, [(m, "1")])
    orden = [
        ("SELECT id FROM gapto.cuentas WHERE id=%s FOR NO KEY UPDATE", cuenta),
        ("SELECT id FROM gapto.categorias_financieras WHERE id=%s FOR NO KEY UPDATE", cat),
        ("SELECT id FROM gapto.categoria_magnitudes WHERE id=%s FOR NO KEY UPDATE", cm),
        ("SELECT id FROM gapto.magnitudes WHERE id=%s FOR NO KEY UPDATE", m),
    ]
    retenedores = []
    salida: dict = {}
    try:
        for sql, fila in orden:
            s = fh.sesion_owner(owner)
            s.execute(sql, (fila,))
            retenedores.append(s)
        pids = tuple(fh.pid_servidor(s) for s in retenedores)
        hilo = _lanzar(owner, cuerpo, salida)
        pid_a = _pid_en_espera(pids)
        for s, pid in zip(retenedores, pids):
            _esperar_bloqueador(pid_a, pid)
            s.execute("ROLLBACK")
        hilo.join(timeout=15)
        assert not hilo.is_alive()
    finally:
        for s in retenedores:
            s.close()
    assert salida["r"].status_code == 200, salida["r"].text


# ------------------------------------------------------------------ lectura AJ-C07-08
def _nodo(owner, cat) -> dict:
    r = h.cliente(owner).get("/v1/categorias", headers=h.AUTH)
    assert r.status_code == 200, r.text
    [nodo] = [n for n in r.json()["categorias"] if n["id"] == str(cat)]
    return nodo


def test_lectura_sin_magnitudes(tenant):
    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, "Vacia", "GASTO")
    nodo = _nodo(owner, cat)
    assert nodo["magnitudes"] == [] and nodo["capturable"] is True and nodo["motivo_no_capturable"] is None


def test_lectura_campos_y_orden_de_magnitudes(tenant):
    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, "Coche", "GASTO")
    z = _magnitud(owner, "Zeta", unidad="u", precision=0)
    a = _magnitud(owner, "Alfa", unidad="km", precision=1)
    b = _magnitud(owner, "Beta", unidad="l", precision=2)
    _asociar(owner, cat, b, obligatoria=False, orden=1)
    cm_a = _asociar(owner, cat, a, obligatoria=True, orden=1)
    _asociar(owner, cat, z, obligatoria=False, orden=0)
    nodo = _nodo(owner, cat)
    assert [x["nombre"] for x in nodo["magnitudes"]] == ["Zeta", "Alfa", "Beta"]
    alfa = nodo["magnitudes"][1]
    assert alfa == {
        "asociacion_id": str(cm_a), "magnitud_id": str(a), "nombre": "Alfa", "obligatoria": True, "orden": 1,
        "enabled": True, "unidad_default": "km", "precision_decimales": 1, "row_version": 1,
    }
    assert nodo["capturable"] is True


def test_lectura_asociacion_id_es_la_identidad_de_cada_asociacion(tenant):
    """S7-MAG D-MAG-04: la misma magnitud en dos categorias tiene dos asociaciones distintas."""
    owner, _, _ = tenant
    c1 = fh.crear_categoria(owner, "Uno", "GASTO")
    c2 = fh.crear_categoria(owner, "Dos", "GASTO")
    m = _magnitud(owner, "Compartida")
    cm1 = _asociar(owner, c1, m, obligatoria=True)
    cm2 = _asociar(owner, c2, m, obligatoria=False)
    assert [x["asociacion_id"] for x in _nodo(owner, c1)["magnitudes"]] == [str(cm1)]
    assert [x["asociacion_id"] for x in _nodo(owner, c2)["magnitudes"]] == [str(cm2)]
    assert cm1 != cm2


def test_lectura_obligatoria_deshabilitada_no_capturable(tenant):
    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, "Bloqueada", "GASTO")
    _asociar(owner, cat, _magnitud(owner, enabled=False), obligatoria=True)
    nodo = _nodo(owner, cat)
    assert nodo["capturable"] is False
    assert nodo["motivo_no_capturable"] == "MAGNITUD_OBLIGATORIA_NO_DISPONIBLE"
    assert nodo["enabled"] is True  # capturable no sustituye a enabled


def test_lectura_opcional_deshabilitada_no_afecta(tenant):
    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, "Opcional off", "GASTO")
    _asociar(owner, cat, _magnitud(owner, enabled=False), obligatoria=False)
    nodo = _nodo(owner, cat)
    assert nodo["capturable"] is True and nodo["magnitudes"][0]["enabled"] is False


def test_lectura_categoria_deshabilitada_calcula_capturable_por_separado(tenant):
    owner, _, _ = tenant
    cat = fh.crear_categoria(owner, "Apagada", "GASTO", enabled=False)
    _asociar(owner, cat, _magnitud(owner), obligatoria=True)
    nodo = _nodo(owner, cat)
    assert nodo["enabled"] is False and nodo["capturable"] is True


def test_comandos_c06_no_cambian_su_respuesta(tenant):
    owner, _, _ = tenant
    r = h.cliente(owner).post(
        "/v1/categorias",
        json={"id": str(uuid.uuid4()), "nombre": "Nueva", "parent_id": None, "ambito": "GASTO",
              "presupuestable_default": True},
        headers=h.AUTH,
    )
    assert r.status_code == 200, r.text
    assert not {"magnitudes", "capturable", "motivo_no_capturable"} & set(r.json()["categoria"])
