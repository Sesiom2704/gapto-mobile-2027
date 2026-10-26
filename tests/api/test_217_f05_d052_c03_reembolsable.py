# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_217_f05_d052_c03_reembolsable.py
# Ruta: tests/api/test_217_f05_d052_c03_reembolsable.py
# Descripcion: F05-D052 (F05 §66.A, contrato C-03 v1.0). Gasto propio
#   reembolsable por la API con el rol real gapto_runtime y oraculo fisico:
#     1. oraculo fisico y economico de G2-A6 tras el registro y tras cada cobro
#        (hechos, efectos, atribucion, actores, posiciones, tesoreria y
#        Resultado; el cobro no es ingreso);
#     2. positivos: PERSONA y EMPRESA, recuperacion total y parcial, cobro
#        parcial y total, dos derechos con la misma empresa (navegacion por
#        entidad);
#     3. negativos de §66.A.3 y §66.A.9 con 0 filas escritas y sin actor
#        huerfano (recuento);
#     4. idempotencia, reintento con otro contenido y reutilizacion entre rutas;
#     5. aislamiento por owner;
#     7. regresion: el reparto sigue rechazando EMPRESA (politica por llamante);
#   mas R6 del gasto compartido (§66.A.10, tres casos) y la lectura del detalle
#   con `posiciones_vinculadas` leida UNA vez por entidad (§66.A.8, §66.5).
#   La concurrencia (6) esta en test_218 (serie).
# Version: 0.1.0 (F05-D052 paso 2; F05 §66.A.11)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import pytest

import f05_05_helpers as x
import f05_06_m2_helpers as dv
import f05_06_m3_helpers as m
import f05_d052_c03_helpers as c
import vs01_api_helpers as h

D = decimal.Decimal


@pytest.fixture()
def t():
    owner, yo, cli, cta, ahorro, comb = c.entorno()
    return owner, yo, cli, cta, ahorro, comb, c.tercero(cli, "Empresa SL"), c.tercero(cli, "Repsol")


def _cod(r):
    return r.json().get("codigo")


def _registrado(cli, cuerpo) -> uuid.UUID:
    r = c.registrar(cli, cuerpo)
    assert r.status_code == 200, r.text
    return uuid.UUID(cuerpo["intencion_id"])


def _posicion(owner, hecho):
    return c.uno(owner, "SELECT p.entidad_id, p.tipo, p.contraparte_actor_id, p.saldo_apertura, "
                        "p.fecha_inicio_seguimiento, p.estado, p.motivo_cierre, v.tipo_relacion "
                        "FROM gapto.hecho_entidades v JOIN gapto.derechos_obligaciones_financieras p "
                        "ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s AND v.efecto_id IS NOT NULL", (hecho,))


def _sin_ingresos(owner):
    assert c.uno(owner, "SELECT count(*) FROM gapto.hecho_efectos WHERE tipo_efecto = 'INGRESO'")[0] == 0
    assert c.uno(owner, "SELECT count(*) FROM gapto.hecho_efectos WHERE tipo_efecto = 'GASTO' "
                        "AND importe_delta < 0")[0] == 0


# ------------------------------------------------------------------ 1. oraculo G2-A6
def test_oraculo_fisico_y_economico_empresa_parcial_y_dos_cobros(t):
    owner, yo, cli, cta, ahorro, comb, emp, repsol = t
    base = c.resultado_mes(cli)
    actores_antes = c.uno(owner, "SELECT count(*) FROM gapto.actores_financieros")[0]
    cuerpo = c.cuerpo(cta, emp, "40.00", categoria=comb, comercio=repsol)
    r = c.registrar(cli, cuerpo)
    assert r.status_code == 200, r.text
    hecho = uuid.UUID(cuerpo["intencion_id"])
    j = r.json()
    assert (j["hecho_id"], j["idempotente"], j["tu_parte"], j["estado_atribucion"]) == (
        str(hecho), False, "60.00", "COMPLETA")
    assert j["movimiento"]["importe"] == "-60.00" and j["movimiento"]["cuenta_id"] == str(cta)
    [p] = j["posiciones"]
    assert (p["tipo"], p["contraparte_tercero_id"], p["nombre"], p["importe"], p["saldo"], p["estado"],
            p["apertura_indeterminada"]) == ("DERECHO_COBRO", str(emp), "Pendiente de cobro · Combustible",
                                             "40.00", "40.00", "ACTIVA", False)
    # Hechos: un GASTO ACTIVO por el total.
    assert c.leer(owner, "SELECT t.codigo, h.estado, h.importe_total, h.concepto FROM gapto.hechos_financieros h "
                         "JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id") == [("GASTO", "ACTIVO", D("60.0000"),
                                                                                   "Gasolina")]
    # Efectos: GASTO +60 COMPLETA con categoria; DERECHO_COBRO +40 sin categoria.
    assert c.efectos(owner, hecho) == sorted([("DERECHO_COBRO", D("40.0000"), "NO_DISPONIBLE", None),
                                              ("GASTO", D("60.0000"), "COMPLETA", comb)], key=str)
    # Atribucion: UNA fila propia por el TOTAL; ninguna de la empresa (§66.1).
    actor_emp = m.actor_de(owner, emp)
    assert c.leer(owner, "SELECT a.actor_id, a.importe_atribuido FROM gapto.efecto_atribuciones a "
                         "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
                  (hecho,)) == [(yo, D("60.0000"))]
    # Actores: uno nuevo para la empresa, con su auditoria en la misma transaccion.
    assert c.uno(owner, "SELECT count(*) FROM gapto.actores_financieros")[0] == actores_antes + 1
    assert c.uno(owner, "SELECT motivo FROM gapto.auditoria WHERE tabla = 'actores_financieros' "
                        "AND registro_id = %s", (actor_emp,))[0].startswith("F05-D052 C-03")
    # Posicion: DERECHO_COBRO frente al actor de la empresa, apertura 0, inicio = fecha, GENERADO_POR.
    entidad, tipo, contraparte, apertura, inicio, estado, motivo, relacion = _posicion(owner, hecho)
    assert (str(entidad), tipo, contraparte, apertura, str(inicio), estado, motivo, relacion) == (
        p["entidad_id"], "DERECHO_COBRO", actor_emp, D("0.0000"), c.FECHA, "ACTIVA", None, "GENERADO_POR")
    # Tesoreria: -60 en la cuenta pagadora, conciliado; aportacion propia 60.
    assert c.leer(owner, "SELECT m.cuenta_id, m.importe, hm.importe_asignado FROM gapto.movimientos_tesoreria m "
                         "JOIN gapto.hecho_movimientos_tesoreria hm ON hm.movimiento_tesoreria_id = m.id "
                         "WHERE hm.hecho_id = %s", (hecho,)) == [(cta, D("-60.0000"), D("-60.0000"))]
    assert c.leer(owner, "SELECT actor_id, importe, criterio_aportacion FROM gapto.hecho_aportaciones_pago "
                         "WHERE hecho_id = %s", (hecho,)) == [(yo, D("60.0000"), "PARTICIPACION_CUENTA")]
    # Comercio VENDEDOR.
    assert c.leer(owner, "SELECT tercero_id, rol_en_hecho FROM gapto.hecho_terceros WHERE hecho_id = %s",
                  (hecho,)) == [(repsol, "VENDEDOR")]
    # Resultado: el gasto cuenta entero.
    tras_registro = c.resultado_mes(cli)
    assert D(tras_registro["gastos_propios"]) - D(base["gastos_propios"]) == D("60.00")
    assert tras_registro["ingresos_propios"] == base["ingresos_propios"]
    _sin_ingresos(owner)

    # Cobro parcial 25 en la cuenta (con capacidad de recibir): ACTIVA, saldo 15; tesoreria +25; Resultado igual.
    r = c.cobro(cli, p["entidad_id"], cta, "25.00")
    assert r.status_code == 200, r.text
    assert (r.json()["saldo"], r.json()["estado"], r.json()["apertura_indeterminada"]) == ("15.00", "ACTIVA", False)
    assert c.uno(owner, "SELECT count(*) FROM gapto.hecho_relaciones WHERE tipo_relacion = 'REEMBOLSO_DE' "
                        "AND hecho_destino_id = %s", (hecho,))[0] == 1
    assert c.uno(owner, "SELECT sum(importe) FROM gapto.movimientos_tesoreria WHERE cuenta_id = %s", (cta,))[0] \
        == D("-35.0000")
    assert c.resultado_mes(cli) == tras_registro
    _sin_ingresos(owner)
    assert c.efectos(owner, hecho) == sorted([("DERECHO_COBRO", D("40.0000"), "NO_DISPONIBLE", None),
                                              ("GASTO", D("60.0000"), "COMPLETA", comb)], key=str)

    # Cobro total del resto (15): CERRADA LIQUIDADA, saldo 0; Resultado igual.
    r = c.cobro(cli, p["entidad_id"], cta, "15.00")
    assert r.status_code == 200, r.text
    assert (r.json()["saldo"], r.json()["estado"]) == ("0.00", "CERRADA")
    assert _posicion(owner, hecho)[5:7] == ("CERRADA", "LIQUIDADA")
    assert c.resultado_mes(cli) == tras_registro
    _sin_ingresos(owner)
    assert c.leer(owner, "SELECT a.actor_id, a.importe_atribuido FROM gapto.efecto_atribuciones a "
                         "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s",
                  (hecho,)) == [(yo, D("60.0000"))]


# ------------------------------------------------------------------ 2. positivos
@pytest.mark.parametrize("naturaleza", ["PERSONA", "EMPRESA"])
def test_persona_y_empresa_recuperacion_total(t, naturaleza):
    owner, yo, cli, cta, _, comb, _, _ = t
    deudor = c.tercero(cli, f"Deudor {naturaleza}", naturaleza)
    hecho = _registrado(cli, c.cuerpo(cta, deudor, "60.00"))
    assert c.efectos(owner, hecho) == sorted([("DERECHO_COBRO", D("60.0000"), "NO_DISPONIBLE", None),
                                              ("GASTO", D("60.0000"), "COMPLETA", None)], key=str)
    assert _posicion(owner, hecho)[2] == m.actor_de(owner, deudor)
    rep = c.reparto(cli, hecho).json()
    assert rep["posiciones_vinculadas"][0]["contraparte_tercero_id"] == str(deudor)
    assert rep["posiciones_vinculadas"][0]["saldo"] == "60.00"


def test_sin_categoria_nombre_y_financiacion_no_determinada_sin_aportacion(t):
    owner, _, cli, cta, _, _, emp, _ = t
    hecho = _registrado(cli, c.cuerpo(cta, emp, "10.00", categoria=None, financiacion=h.NO_DETERMINADA))
    assert c.uno(owner, "SELECT nombre FROM gapto.entidades WHERE id = %s", (_posicion(owner, hecho)[0],))[0] \
        == "Pendiente de cobro"
    assert c.uno(owner, "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s", (hecho,))[0] == 0


def test_contexto_y_magnitudes_viajan_en_la_misma_op22(t):
    owner, _, cli, cta, _, comb, emp, repsol = t
    litros = h.crear_magnitud(owner, "Litros C03")
    h.crear_asociacion(owner, comb, litros, obligatoria=True)
    ctx = x.contexto(cli, "Viaje de trabajo")
    sin_mag = c.registrar(cli, c.cuerpo(cta, emp, "60.00", categoria=comb))
    assert (sin_mag.status_code, _cod(sin_mag)) == (409, "MAGNITUD_OBLIGATORIA_AUSENTE")
    hecho = _registrado(cli, c.cuerpo(cta, emp, "60.00", categoria=comb, comercio=repsol, contexto_id=ctx,
                                      magnitudes=[(litros, "40.5")]))
    assert c.leer(owner, "SELECT magnitud_id, valor FROM gapto.hecho_magnitudes WHERE hecho_id = %s",
                  (hecho,)) == [(litros, D("40.500000"))]
    assert c.leer(owner, "SELECT entidad_id, tipo_relacion, efecto_id FROM gapto.hecho_entidades WHERE hecho_id = %s "
                         "AND efecto_id IS NULL", (hecho,)) == [(ctx, "RELACIONADO_CON", None)]


def test_dos_derechos_con_la_misma_empresa_cobro_solo_al_elegido(t):
    owner, _, cli, cta, ahorro, _, emp, _ = t
    a = c.registrar(cli, c.cuerpo(cta, emp, "40.00", importe="40.00")).json()["posiciones"][0]["entidad_id"]
    b = c.registrar(cli, c.cuerpo(cta, emp, "20.00", importe="20.00", concepto="Peaje")).json()["posiciones"][0][
        "entidad_id"]
    assert a != b
    p = m.pendiente(cli, emp).json()
    assert sorted(x_["entidad_id"] for x_ in p["posiciones"]) == sorted([a, b]) and p["te_debe"] == "60.00"
    r = c.cobro(cli, b, cta, "20.00")
    assert r.status_code == 200 and r.json()["entidad_id"] == b and r.json()["estado"] == "CERRADA", r.text
    p = m.pendiente(cli, emp).json()
    assert [(x_["entidad_id"], x_["saldo"]) for x_ in p["posiciones"]] == [(a, "40.00")]


# ------------------------------------------------------------------ 3. negativos (0 filas, sin actor huerfano)
def _rechazo_sin_efectos(owner, cli, cuerpo, status, codigo):
    antes = c.huella(owner)
    r = c.registrar(cli, cuerpo)
    assert (r.status_code, _cod(r)) == (status, codigo), r.text
    assert c.huella(owner) == antes  # incluye actores_financieros y auditoria


def test_negativo_importe_recuperable_excede_el_total(t):
    owner, _, cli, cta, _, _, emp, _ = t
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, emp, "60.01"), 422, "REEMBOLSO_EXCEDE_TOTAL")


@pytest.mark.parametrize("reembolso", [None, {}, {"tercero_id": None, "importe": "10.00"}, "AUSENTE",
                                       "CERO", "NEGATIVO", "TRES_DECIMALES", "NULO", "EXTRA"])
def test_negativo_reembolso_mal_formado_422(t, reembolso):
    owner, _, cli, cta, _, _, emp, _ = t
    cuerpo = c.cuerpo(cta, emp, "10.00")
    especiales = {"AUSENTE": None, "CERO": "0.00", "NEGATIVO": "-1.00", "TRES_DECIMALES": "1.005", "NULO": None}
    if reembolso == "AUSENTE":
        del cuerpo["reembolso"]
    elif isinstance(reembolso, str) and reembolso in especiales:
        cuerpo["reembolso"]["importe"] = especiales[reembolso]
    elif isinstance(reembolso, str) and reembolso == "EXTRA":
        cuerpo["reembolso"]["porcentaje"] = "50"
    else:
        cuerpo["reembolso"] = reembolso
    _rechazo_sin_efectos(owner, cli, cuerpo, 422, "ENTRADA_INVALIDA")


@pytest.mark.parametrize("campo", ["atribucion", "prevision", "owner_user_id"])
def test_negativo_campos_no_admitidos_422(t, campo):
    owner, _, cli, cta, _, _, emp, _ = t
    cuerpo = c.cuerpo(cta, emp, "10.00")
    cuerpo[campo] = {"atribucion": "SOLO_MIO", "prevision": {"prevision_id": str(uuid.uuid4())},
                     "owner_user_id": str(uuid.uuid4())}[campo]
    _rechazo_sin_efectos(owner, cli, cuerpo, 422, "ENTRADA_INVALIDA")


def test_negativo_contraparte_es_el_comercio(t):
    owner, _, cli, cta, _, _, emp, _ = t
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, emp, "10.00", comercio=emp), 422, "CONTRAPARTE_ES_COMERCIO")


def test_negativo_tercero_inexistente_ajeno_y_deshabilitado_sin_revelar(t):
    owner, _, cli, cta, _, _, _, _ = t
    otro = x.entorno()
    ajeno = c.tercero(otro[2], "Empresa ajena")
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, uuid.uuid4(), "10.00"), 409, "TERCERO_NO_DISPONIBLE")
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, ajeno, "10.00"), 409, "TERCERO_NO_DISPONIBLE")
    apagada = c.tercero(cli, "Empresa apagada")
    x.desactivar_tercero(cli, apagada)
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, apagada, "10.00"), 409, "TERCERO_NO_DISPONIBLE")
    # Sin revelar: el ajeno y el inexistente responden igual (mismo cuerpo).
    r1 = c.registrar(cli, c.cuerpo(cta, ajeno, "10.00"))
    r2 = c.registrar(cli, c.cuerpo(cta, uuid.uuid4(), "10.00"))
    assert r1.json() == r2.json()


@pytest.mark.parametrize("naturaleza", ["ORGANISMO", "OTRO", None])
def test_negativo_naturaleza_no_admitida(t, naturaleza):
    owner, _, cli, cta, _, _, _, _ = t
    deudor = c.tercero(cli, f"Deudor {naturaleza}", naturaleza)
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, deudor, "10.00"), 409, "NATURALEZA_NO_ADMITIDA_EN_REEMBOLSO")


def test_negativo_validaciones_antes_del_writer_sin_actor_huerfano(t):
    """Contraparte NUEVA y valida (sin actor aun) con un rechazo posterior en
    cada validacion: ningun actor nace (C03-M10)."""
    owner, _, cli, cta, _, comb, _, _ = t
    nueva = c.tercero(cli, "Empresa nueva")
    comercio = c.tercero(cli, "Comercio apagado")
    x.desactivar_tercero(cli, comercio)
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, nueva, "10.00", comercio=comercio), 409, "TERCERO_NO_DISPONIBLE")
    apagada = x.categoria(owner, "Categoria apagada")
    x.desactivar_categoria(owner, apagada)
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, nueva, "10.00", categoria=apagada), 409, "CATEGORIA_NO_ELEGIBLE")
    ctx = x.contexto(cli, "Contexto apagado")
    h.como_owner(owner, "UPDATE gapto.entidades SET enabled = false WHERE id = %s", (ctx,))
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, nueva, "10.00", contexto_id=ctx), 409, "CONTEXTO_NO_DISPONIBLE")
    _rechazo_sin_efectos(owner, cli, c.cuerpo(cta, nueva, "10.00", fecha="2026-12-01"), 422, "FECHA_FUTURA")
    assert m.actor_de(owner, nueva) is None


# ------------------------------------------------------------------ 3. negativos §66.A.9 (tres momentos)
def _momento(cli, entidad, cuenta, momento):
    if momento in ("parcial", "total"):
        assert c.cobro(cli, entidad, cuenta, "10.00").status_code == 200
    if momento == "total":
        assert c.cobro(cli, entidad, cuenta, "30.00").status_code == 200


@pytest.mark.parametrize("momento", ["antes", "parcial", "total"])
def test_posteriores_correccion_anulacion_y_devolucion_bloqueadas(t, momento):
    owner, _, cli, cta, ahorro, comb, emp, _ = t
    cuerpo = c.cuerpo(cta, emp, "40.00", categoria=comb)
    r = c.registrar(cli, cuerpo)
    hecho = uuid.UUID(cuerpo["intencion_id"])
    _momento(cli, r.json()["posiciones"][0]["entidad_id"], cta, momento)
    ed = c.edicion(cli, hecho)
    assert ed["acciones"]["corregir"]["codigo"] == "POSICIONES" and ed["acciones"]["corregir"]["motivo"]
    assert ed["acciones"]["anular_duplicado"]["codigo"] == "POSICIONES"
    ctx_dev = cli.get(dv.url_devoluciones(hecho), headers=h.AUTH).json()
    assert (ctx_dev["disponible"], ctx_dev["motivo"]) == (False, "GASTO_CON_DERECHO_DE_COBRO")
    mov = ed["movimientos"][0]
    antes = c.huella(owner)
    # Correccion M1 (OP-21P), llamada directa: el motor la rechaza (un unico efecto exigido).
    r = cli.post(f"/v1/hechos/{hecho}/corregir-pago", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": ed["row_version"], "motivo": "Prueba",
        "movimiento_row_version": mov["row_version"], "error_de_registro": True, "importe": "20.00"})
    assert (r.status_code, _cod(r), r.json()["detalle"]["motivo"]) == (
        409, "CORRECCION_AGREGADA_REQUERIDA", "TIPO_NO_SOPORTADO"), r.text
    # Anulacion: guarda vigente POSICIONES.
    r = cli.post(f"/v1/hechos/{hecho}/anular-duplicado", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": ed["row_version"], "motivo": "Prueba",
        "movimientos_row_version": {mov["movimiento_id"]: mov["row_version"]}, "duplicado_declarado": True})
    assert (r.status_code, _cod(r), r.json()["detalle"]["motivo"]) == (
        409, "HECHO_CON_REALIDAD_ASOCIADA", "POSICIONES"), r.text
    # Devolucion contextual D-194: bloqueada en cualquier estado del derecho.
    _, r = dv.devolver(cli, hecho, importe="10.00", atribucion="SIN_INDICAR", fecha="2026-10-05")
    assert (r.status_code, _cod(r)) == (409, "GASTO_CON_DERECHO_DE_COBRO"), r.text
    assert c.huella(owner) == antes
    assert c.uno(owner, "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0] == "ACTIVO"


def test_exclusion_m1_en_servidor_aunque_el_efecto_gasto_ordene_primero(t):
    """Discriminante de la exclusion M1 en el servidor: con el efecto GASTO
    primero por id, una lectura que tomara el primer efecto corregiria el gasto."""
    owner, _, cli, cta, _, _, emp, _ = t
    import app.api.ejecucion_reembolsable as ejr
    while True:
        iid = uuid.uuid4()
        if str(ejr._id(iid, "efecto")) < str(ejr._id(iid, "posicion.efecto")):
            break
    hecho = _registrado(cli, c.cuerpo(cta, emp, "40.00", intencion_id=iid))
    ed = c.edicion(cli, hecho)
    mov = ed["movimientos"][0]
    antes = c.huella(owner)
    r = cli.post(f"/v1/hechos/{hecho}/corregir-pago", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": ed["row_version"], "motivo": "Prueba",
        "movimiento_row_version": mov["row_version"], "error_de_registro": True, "importe": "20.00"})
    assert (r.status_code, _cod(r), r.json()["detalle"]["motivo"]) == (
        409, "CORRECCION_AGREGADA_REQUERIDA", "TIPO_NO_SOPORTADO"), r.text
    assert c.huella(owner) == antes


@pytest.mark.parametrize("campo", ["cuenta_id", "financiacion", "presupuestable", "categoria"])
def test_negativo_comunes_obligatorios_sin_default(t, campo):
    """§66.A.2: cuenta pagadora obligatoria y sin defaults financieros nuevos (C03-M07)."""
    owner, _, cli, cta, _, _, emp, _ = t
    cuerpo = c.cuerpo(cta, emp, "10.00")
    del cuerpo[campo]
    _rechazo_sin_efectos(owner, cli, cuerpo, 422, "ENTRADA_INVALIDA")


# ------------------------------------------------------------------ 4. idempotencia y reutilizacion entre rutas
def test_reintento_identico_idempotente_y_con_otro_contenido_rechazado(t):
    owner, _, cli, cta, _, comb, emp, repsol = t
    otra = c.tercero(cli, "Otra Empresa")
    ctx = x.contexto(cli, "Viaje")
    cuerpo = c.cuerpo(cta, emp, "40.00", categoria=comb, comercio=repsol, contexto_id=ctx)
    primera = c.registrar(cli, cuerpo).json()
    antes = c.huella(owner)
    r = c.registrar(cli, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert {k: v for k, v in r.json().items() if k != "idempotente"} == {
        k: v for k, v in primera.items() if k != "idempotente"}
    assert c.huella(owner) == antes
    variantes = [
        {"reembolso": {"tercero_id": str(emp), "importe": "39.99"}},
        {"reembolso": {"tercero_id": str(otra), "importe": "40.00"}},
        {"importe": "61.00", "financiacion": h.propuesta_self_100("61.00")},
        {"fecha_hecho": "2026-10-04"}, {"cuenta_id": str(x.entorno()[3])}, {"categoria": {"estado": "SIN_CATEGORIA"}},
        {"concepto": "Otra nota"}, {"presupuestable": False}, {"contexto_id": None}, {"tercero_id": None},
        {"financiacion": h.NO_DETERMINADA},
    ]
    for cambio in variantes:
        r = c.registrar(cli, {**cuerpo, **cambio})
        assert (r.status_code, _cod(r)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"), (cambio, r.text)
        assert c.huella(owner) == antes, cambio


def test_reutilizacion_entre_rutas_en_ambos_sentidos(t):
    owner, _, cli, cta, _, _, emp, _ = t
    tania = m.persona(cli, "Tania")
    # C-03 -> gasto pagado y gasto compartido.
    cuerpo = c.cuerpo(cta, emp, "60.00")
    _registrado(cli, cuerpo)
    antes = c.huella(owner)
    pagado = h.intencion(cta, intencion_id=cuerpo["intencion_id"], importe="60.00", fecha_hecho=c.FECHA,
                         concepto="Gasolina")
    r = cli.post("/v1/intenciones/gasto-pagado", json=pagado, headers=h.AUTH)
    assert (r.status_code, _cod(r)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"), r.text
    compartido = m.cuerpo("60.00", pagado_por=m.con_cuenta(cta), reparto=m.SOLO_MIO, fecha=c.FECHA,
                          nota="Gasolina", intencion_id=cuerpo["intencion_id"])
    r = m.registrar(cli, compartido)
    assert (r.status_code, _cod(r)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"), r.text
    assert c.huella(owner) == antes
    # gasto pagado y gasto compartido -> C-03.
    pagado = h.intencion(cta, importe="60.00", fecha_hecho=c.FECHA, concepto="Gasolina")
    assert cli.post("/v1/intenciones/gasto-pagado", json=pagado, headers=h.AUTH).status_code == 200
    compartido = m.cuerpo("60.00", pagado_por=m.con_cuenta(cta), fecha=c.FECHA, nota="Gasolina",
                          reparto=m.repartir("30.00", (tania, "30.00", "SI")))
    assert m.registrar(cli, compartido).status_code == 200
    antes = c.huella(owner)
    for iid in (pagado["intencion_id"], compartido["intencion_id"]):
        r = c.registrar(cli, c.cuerpo(cta, emp, "60.00", intencion_id=uuid.UUID(iid)))
        assert (r.status_code, _cod(r)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"), r.text
        r = c.registrar(cli, c.cuerpo(cta, tania, "30.00", intencion_id=uuid.UUID(iid)))
        assert (r.status_code, _cod(r)) == (409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"), r.text
    assert c.huella(owner) == antes


@pytest.mark.parametrize("cambio", ["DESHABILITAR", "ORGANISMO"])
def test_replay_tras_deshabilitar_o_cambiar_naturaleza_devuelve_el_agregado(t, cambio):
    owner, _, cli, cta, _, _, emp, _ = t
    cuerpo = c.cuerpo(cta, emp, "60.00")
    primera = c.registrar(cli, cuerpo).json()
    if cambio == "DESHABILITAR":
        x.desactivar_tercero(cli, emp)
    else:
        c.editar_naturaleza(cli, emp, "ORGANISMO")
    antes = c.huella(owner)
    r = c.registrar(cli, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
    assert r.json()["posiciones"] == primera["posiciones"]
    assert c.huella(owner) == antes  # ni actor nuevo ni posicion duplicada
    # Una intencion NUEVA con ese tercero si se rechaza.
    r = c.registrar(cli, c.cuerpo(cta, emp, "60.00"))
    assert _cod(r) == ("TERCERO_NO_DISPONIBLE" if cambio == "DESHABILITAR" else "NATURALEZA_NO_ADMITIDA_EN_REEMBOLSO")


def test_replay_tras_cobro_total_refleja_el_estado_actual(t):
    owner, _, cli, cta, ahorro, _, emp, _ = t
    cuerpo = c.cuerpo(cta, emp, "60.00")
    entidad = c.registrar(cli, cuerpo).json()["posiciones"][0]["entidad_id"]
    assert c.cobro(cli, entidad, cta, "60.00").status_code == 200
    r = c.registrar(cli, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert (r.json()["posiciones"][0]["saldo"], r.json()["posiciones"][0]["estado"]) == ("0.00", "CERRADA")


# ------------------------------------------------------------------ 5. aislamiento por owner
def test_aislamiento_por_owner(t):
    owner, _, cli, cta, ahorro, _, emp, _ = t
    cuerpo = c.cuerpo(cta, emp, "60.00")
    entidad = c.registrar(cli, cuerpo).json()["posiciones"][0]["entidad_id"]
    otro_owner, _, otro_cli, otra_cta, _, _ = c.entorno()
    antes, antes_otro = c.huella(owner), c.huella(otro_owner)
    assert otro_cli.get(f"/v1/hechos/{cuerpo['intencion_id']}/reparto", headers=h.AUTH).status_code == 404
    r = c.cobro(otro_cli, entidad, otra_cta, "10.00")
    assert (r.status_code, _cod(r)) == (404, "POSICION_NO_ENCONTRADA"), r.text
    # Su propia cuenta con mi tercero: no disponible, sin revelar.
    r = c.registrar(otro_cli, c.cuerpo(otra_cta, emp, "10.00"))
    assert (r.status_code, _cod(r)) == (409, "TERCERO_NO_DISPONIBLE")
    # Mi tercero con la cuenta de otro owner: cuenta no disponible, sin escribir.
    r = c.registrar(cli, c.cuerpo(otra_cta, emp, "10.00"))
    assert r.status_code in (409, 422) and _cod(r) in ("CUENTA_DESCONOCIDA",), r.text
    assert (c.huella(owner), c.huella(otro_owner)) == (antes, antes_otro)


# ------------------------------------------------------------------ 7. regresion: politica por llamante
def test_el_reparto_sigue_rechazando_empresa(t):
    owner, _, cli, cta, _, _, emp, _ = t
    antes = c.huella(owner)
    r = m.registrar(cli, m.cuerpo("60.00", pagado_por=m.con_cuenta(cta),
                                  reparto=m.repartir("30.00", (emp, "30.00", "SI"))))
    assert (r.status_code, _cod(r)) == (409, "TERCERO_NO_PERSONA"), r.text
    assert c.huella(owner) == antes


# ------------------------------------------------------------------ R6 (§66.A.10)
def test_r6_tres_casos(t):
    owner, _, cli, cta, _, _, _, _ = t
    tania, carlos = m.persona(cli, "Tania"), m.persona(cli, "Carlos")
    antes = c.huella(owner)
    # Igualdad con mi parte desconocida -> codigo estable con texto propio (sin «pon 0»).
    r = m.registrar(cli, m.cuerpo("60.00", pagado_por=m.con_cuenta(cta),
                                  reparto=m.repartir(None, (tania, "30.00", None), (carlos, "30.00", None))))
    assert (r.status_code, _cod(r)) == (422, "REPARTO_SIN_MARGEN_PARA_DESCONOCIDO"), r.text
    assert "0" not in r.json()["mensaje"].replace("No se ha", "") and "Corregir" not in r.json()["mensaje"]
    # Alcance general: parte ajena desconocida y lo conocido (mi parte + la otra) = total.
    r = m.registrar(cli, m.cuerpo("60.00", pagado_por=m.con_cuenta(cta),
                                  reparto=m.repartir("30.00", (tania, "30.00", None), (carlos, None, None))))
    assert (r.status_code, _cod(r)) == (422, "REPARTO_SIN_MARGEN_PARA_DESCONOCIDO"), r.text
    # Exceso: conserva su error actual.
    r = m.registrar(cli, m.cuerpo("60.00", pagado_por=m.con_cuenta(cta),
                                  reparto=m.repartir(None, (tania, "40.00", None), (carlos, "30.00", None))))
    assert (r.status_code, _cod(r)) == (422, "ENTRADA_INVALIDA"), r.text
    assert c.huella(owner) == antes
    # Suma incompleta con alguna desconocida: sigue admitida (PARCIAL).
    r = m.registrar(cli, m.cuerpo("60.00", pagado_por=m.con_cuenta(cta),
                                  reparto=m.repartir(None, (tania, "20.00", None), (carlos, "30.00", None))))
    assert r.status_code == 200 and r.json()["estado_atribucion"] == "PARCIAL", r.text
    # Todo conocido y = total: sin cambios (COMPLETA).
    r = m.registrar(cli, m.cuerpo("60.00", pagado_por=m.con_cuenta(cta),
                                  reparto=m.repartir("10.00", (tania, "20.00", None), (carlos, "30.00", None))))
    assert r.status_code == 200 and r.json()["estado_atribucion"] == "COMPLETA", r.text


# ------------------------------------------------------------------ lectura del detalle (§66.A.8, §66.5)
def test_detalle_posiciones_vinculadas_separadas_sin_duplicar(t):
    owner, _, cli, cta, ahorro, _, emp, _ = t
    tania = m.persona(cli, "Tania")
    # C-03: el derecho NO es una parte; la unica parte es la mia.
    cuerpo = c.cuerpo(cta, emp, "40.00")
    hecho = _registrado(cli, cuerpo)
    rep = c.reparto(cli, hecho).json()
    assert [(p["es_yo"], p["importe"], p["posicion"]) for p in rep["partes"]] == [(True, "60.00", None)]
    [v] = rep["posiciones_vinculadas"]
    assert (v["tipo"], v["contraparte_tercero_id"], v["contraparte_nombre"], v["saldo"], v["estado"],
            v["apertura_indeterminada"]) == ("DERECHO_COBRO", str(emp), "Empresa SL", "40.00", "ACTIVA", False)
    assert c.cobro(cli, v["entidad_id"], cta, "40.00").status_code == 200
    v = c.reparto(cli, hecho).json()["posiciones_vinculadas"][0]
    assert (v["saldo"], v["estado"]) == ("0.00", "CERRADA")
    # M3 con «me debe»: la posicion ya cuelga de la parte de Tania y no se repite.
    c3, r = m.cena(cli, cta, tania, m.persona(cli, "Carlos"))
    rep = c.reparto(cli, c3["intencion_id"]).json()
    assert [p["posicion"]["tipo"] for p in rep["partes"] if p["posicion"]] == ["DERECHO_COBRO"]
    assert rep["posiciones_vinculadas"] == []


def test_lectura_una_vez_por_entidad_con_vinculos_repetidos(t, monkeypatch):
    """§66.5 (AJ-F0507G3-13): con vinculos repetidos de la misma entidad, el
    motor se lee UNA vez por entidad. Los vinculos repetidos se simulan en la
    frontera de lectura (`_estado_reparto`): ningun flujo actual de escritura
    los produce; la regla de la lectura no depende de como se formen."""
    owner, _, cli, cta, _, _, emp, _ = t
    from app.api import ejecucion_reparto as rep
    from app.services.posiciones_service import PosicionesService

    hecho = _registrado(cli, c.cuerpo(cta, emp, "40.00"))
    original_estado, original_saldo = rep._estado_reparto, PosicionesService.saldo
    lecturas: list = []

    def estado_con_repetidos(sesion, hecho_id):
        e = original_estado(sesion, hecho_id)
        return None if e is None else {**e, "vinculos": list(e["vinculos"]) * 3}

    def saldo_contado(self, contexto, entidad_id):
        lecturas.append(entidad_id)
        return original_saldo(self, contexto, entidad_id)

    monkeypatch.setattr(rep, "_estado_reparto", estado_con_repetidos)
    monkeypatch.setattr(PosicionesService, "saldo", saldo_contado)
    j = c.reparto(cli, hecho).json()
    assert len(lecturas) == 1 and len(set(lecturas)) == 1, lecturas
    assert len(j["posiciones_vinculadas"]) == 1


# ------------------------------------------------------------------ §66.A.9 con la forma RV3 (AFECTA_A)
@pytest.mark.parametrize("momento", ["antes", "parcial"])
def test_posteriores_bloqueadas_con_vinculo_rv3_afecta_a(t, momento):
    """Forma de la carga RV3 (P5 D6, H9; G6 del paso 6): GASTO V3 con un
    DERECHO_COBRO vinculado AFECTA_A (efecto propio), no GENERADO_POR. La
    escritura runtime no puede producir esa forma (la matriz R3-01 prohibe
    vinculos contextuales con posiciones): se prepara con el motor y se
    reescribe la relacion como la deja la carga, igual que marcar_v3 simula el
    origen V3. «Vinculado» se aplica literal: cualquier vinculo bloquea."""
    owner, _, cli, cta, _, _, emp, _ = t
    cuerpo = c.cuerpo(cta, emp, "40.00")
    entidad = c.registrar(cli, cuerpo).json()["posiciones"][0]["entidad_id"]
    hecho = uuid.UUID(cuerpo["intencion_id"])
    h.como_owner(owner, "UPDATE gapto.hecho_entidades SET tipo_relacion = 'AFECTA_A' WHERE hecho_id = %s "
                        "AND entidad_id = %s", (hecho, uuid.UUID(entidad)))
    assert c.leer(owner, "SELECT tipo_relacion FROM gapto.hecho_entidades WHERE hecho_id = %s", (hecho,)) == [
        ("AFECTA_A",)]
    _momento(cli, entidad, cta, momento)
    dv.marcar_v3(owner, hecho)
    ed = c.edicion(cli, hecho)
    assert ed["acciones"]["anular_duplicado"]["codigo"] in ("POSICIONES", "ORIGEN_IMPORTADO")
    ctx_dev = cli.get(dv.url_devoluciones(hecho), headers=h.AUTH).json()
    assert (ctx_dev["disponible"], ctx_dev["motivo"]) == (False, "GASTO_CON_DERECHO_DE_COBRO")
    mov = ed["movimientos"][0]
    antes = c.huella(owner)
    _, r = dv.devolver(cli, hecho, importe="5.00", atribucion="SIN_INDICAR", fecha="2026-10-05")
    assert (r.status_code, _cod(r)) == (409, "GASTO_CON_DERECHO_DE_COBRO"), r.text
    r = cli.post(f"/v1/hechos/{hecho}/anular-duplicado", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": ed["row_version"], "motivo": "Prueba",
        "movimientos_row_version": {mov["movimiento_id"]: mov["row_version"]}, "duplicado_declarado": True})
    assert (r.status_code, _cod(r), r.json()["detalle"]["motivo"]) == (
        409, "HECHO_CON_REALIDAD_ASOCIADA", "POSICIONES"), r.text
    r = cli.post(f"/v1/hechos/{hecho}/corregir-pago", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": ed["row_version"], "motivo": "Prueba",
        "movimiento_row_version": mov["row_version"], "error_de_registro": True, "importe": "20.00"})
    assert (r.status_code, _cod(r)) == (409, "CORRECCION_AGREGADA_REQUERIDA"), r.text
    assert c.huella(owner) == antes
