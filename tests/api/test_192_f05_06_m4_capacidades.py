# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_192_f05_06_m4_capacidades.py
# Ruta: tests/api/test_192_f05_06_m4_capacidades.py
# Descripcion: Writer unico y lecturas de capacidades de cuenta (F05-06 M4
#   §2.1-§2.4 y §4.1; F05 §51.2/§51.4; PD-1..PD-4; F09 §12.105 CAP).
#   - Activar y desactivar: fila de cuenta_capacidades, row_version + 1 y UNA
#     auditoria (tabla cuentas, ACTUALIZAR, antes/despues) en la misma
#     transaccion; la elegibilidad del registro cambia solo para lo nuevo.
#   - Idempotencia (sin escritura ni auditoria), VERSION_DESFASADA sin pisar,
#     CAPACIDAD_NO_EDITABLE (DOMICILIAR, COMPRA_TARJETA), ENTRADA_INVALIDA,
#     OPERACION_NO_PERMITIDA_EN_ESTADO (deshabilitada o cerrada, PD-2).
#   - Fallo forzado tras la auditoria: nada persiste (ni fila, ni version,
#     ni auditoria).
#   - IDs de otro owner o inexistentes: misma respuesta 404, sin efectos,
#     con el rol real gapto_runtime.
#   - Lecturas: lista y conteo «sin configurar», detalle con efecto y
#     «Otras», origen V3 desde mapeos_importacion (PD-4), historial desde
#     auditoria (sin entradas inventadas), impacto en plantillas y
#     preferencias.
#   - CUENTA_SIN_CAPACIDAD (D-CAP-08): texto de B3 y detalle en gasto,
#     ingreso y transferencia (origen y destino).
# Version: 0.1.0 (F05-06 M4 F1)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

FECHA = ph.FECHA
BASE = "/v1/cuentas"


@pytest.fixture()
def t():
    return ph.tenant()


def _cuenta(owner, actor, capacidades=(), nombre="Cuenta nómina"):
    return ph.cuenta(owner, actor, nombre=nombre, capacidades=capacidades)


def _cambiar(cli, cuenta, capacidad, accion, row_version):
    return cli.post(f"{BASE}/{cuenta}/capacidades/{capacidad}/{accion}", json={"row_version": row_version},
                    headers=h.AUTH)


def _estado(owner, cuenta):
    caps = [f[0] for f in h.leer(owner, "SELECT capacidad_codigo FROM gapto.cuenta_capacidades WHERE cuenta_id=%s "
                                        "ORDER BY capacidad_codigo", (cuenta,))]
    rv = h.leer(owner, "SELECT row_version FROM gapto.cuentas WHERE id=%s", (cuenta,))
    return caps, (rv[0][0] if rv else None)


def _auditorias(owner, cuenta):
    return h.leer(owner, "SELECT accion, datos_antes::text, datos_despues::text, motivo, actor_tipo "
                         "FROM gapto.auditoria WHERE tabla='cuentas' AND registro_id=%s ORDER BY created_at, id",
                  (cuenta,))


# ------------------------------------------------------------------ activar / desactivar
def test_activar_y_desactivar_con_version_y_auditoria(t):
    owner, actor, cli = t
    cid = _cuenta(owner, actor, capacidades=("PAGAR_GASTO",))
    r = _cambiar(cli, cid, "RECIBIR_INGRESO", "activar", 1)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["idempotente"] is False and cuerpo["cuenta"]["row_version"] == 2
    assert {c["codigo"]: c["permitida"] for c in cuerpo["cuenta"]["capacidades"]} == {
        "PAGAR_GASTO": True, "RECIBIR_INGRESO": True, "TRANSFERIR_SALIDA": False, "TRANSFERIR_ENTRADA": False}
    assert _estado(owner, cid) == (["PAGAR_GASTO", "RECIBIR_INGRESO"], 2)
    elegibles = cli.get(f"{BASE}/elegibles", params={"operacion": "INGRESO", "fecha": FECHA.isoformat()},
                        headers=h.AUTH).json()["cuentas"]
    assert [c["cuenta_id"] for c in elegibles] == [str(cid)]

    r = _cambiar(cli, cid, "PAGAR_GASTO", "desactivar", 2)
    assert r.status_code == 200, r.text
    assert _estado(owner, cid) == (["RECIBIR_INGRESO"], 3)
    aud = _auditorias(owner, cid)
    assert [(a[0], a[3], a[4]) for a in aud] == [
        ("ACTUALIZAR", "F05-06 CAPACIDAD ACTIVAR", "USUARIO"), ("ACTUALIZAR", "F05-06 CAPACIDAD DESACTIVAR", "USUARIO")]
    import json
    assert json.loads(aud[0][1]) == {"capacidad_codigo": "RECIBIR_INGRESO", "permitida": False, "row_version": 1}
    assert json.loads(aud[0][2]) == {"capacidad_codigo": "RECIBIR_INGRESO", "permitida": True, "row_version": 2}
    assert json.loads(aud[1][1]) == {"capacidad_codigo": "PAGAR_GASTO", "permitida": True, "row_version": 2}
    assert json.loads(aud[1][2]) == {"capacidad_codigo": "PAGAR_GASTO", "permitida": False, "row_version": 3}


def test_idempotente_sin_escritura_ni_auditoria(t):
    owner, actor, cli = t
    cid = _cuenta(owner, actor, capacidades=("PAGAR_GASTO",))
    for capacidad, accion in (("PAGAR_GASTO", "activar"), ("RECIBIR_INGRESO", "desactivar")):
        r = _cambiar(cli, cid, capacidad, accion, 1)
        assert r.status_code == 200 and r.json()["idempotente"] is True, r.text
        assert r.json()["cuenta"]["row_version"] == 1
    assert _estado(owner, cid) == (["PAGAR_GASTO"], 1)
    assert _auditorias(owner, cid) == []


def test_version_desfasada_no_pisa(t):
    owner, actor, cli = t
    cid = _cuenta(owner, actor)
    assert _cambiar(cli, cid, "PAGAR_GASTO", "activar", 1).status_code == 200
    for capacidad, accion in (("PAGAR_GASTO", "desactivar"), ("RECIBIR_INGRESO", "activar"),
                              ("RECIBIR_INGRESO", "desactivar")):
        r = _cambiar(cli, cid, capacidad, accion, 1)  # version vieja
        assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA", r.text
    assert _estado(owner, cid) == (["PAGAR_GASTO"], 2)
    assert len(_auditorias(owner, cid)) == 1


@pytest.mark.parametrize("capacidad", ["DOMICILIAR", "COMPRA_TARJETA"])
@pytest.mark.parametrize("accion", ["activar", "desactivar"])
def test_capacidades_no_editables(t, capacidad, accion):
    owner, actor, cli = t
    cid = _cuenta(owner, actor, capacidades=("COMPRA_TARJETA",))
    r = _cambiar(cli, cid, capacidad, accion, 1)
    assert r.status_code == 409 and r.json()["codigo"] == "CAPACIDAD_NO_EDITABLE", r.text
    assert _estado(owner, cid) == (["COMPRA_TARJETA"], 1) and _auditorias(owner, cid) == []
    r = cli.get(f"{BASE}/{cid}/capacidades/{capacidad}/impacto", headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "CAPACIDAD_NO_EDITABLE"


def test_capacidad_fuera_del_catalogo(t):
    owner, actor, cli = t
    cid = _cuenta(owner, actor)
    for capacidad in ("PAGAR", "pagar_gasto", "OTRA"):
        r = _cambiar(cli, cid, capacidad, "activar", 1)
        assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text
    assert _cambiar(cli, cid, "PAGAR_GASTO", "activar", 0).status_code == 422
    assert _estado(owner, cid) == ([], 1)


@pytest.mark.parametrize("estado", ["deshabilitada", "cerrada"])
@pytest.mark.parametrize("accion,capacidad", [("activar", "RECIBIR_INGRESO"), ("desactivar", "PAGAR_GASTO")])
def test_cuenta_cerrada_o_deshabilitada(t, estado, accion, capacidad):
    owner, actor, cli = t
    cid = _cuenta(owner, actor, capacidades=("PAGAR_GASTO",))
    if estado == "deshabilitada":
        ph.deshabilitar_cuenta(owner, cid)
    else:
        h.como_owner(owner, "UPDATE gapto.cuentas SET enabled=false, fecha_cierre=%s WHERE id=%s", (FECHA, cid))
    r = _cambiar(cli, cid, capacidad, accion, 1)
    assert r.status_code == 409 and r.json()["codigo"] == "OPERACION_NO_PERMITIDA_EN_ESTADO", r.text
    assert _estado(owner, cid) == (["PAGAR_GASTO"], 1) and _auditorias(owner, cid) == []
    detalle = cli.get(f"{BASE}/{cid}/capacidades", headers=h.AUTH).json()
    assert detalle["estado"] == ("DESHABILITADA" if estado == "deshabilitada" else "CERRADA")


def test_fallo_forzado_tras_la_auditoria_no_deja_nada(t):
    owner, actor, _ = t
    cid = _cuenta(owner, actor)
    from app.capacidades import servicio
    from app.core.errores import ErrorMotor

    class _Forzado(Exception):
        pass

    def operacion(s):
        r = servicio.activar(s, cuenta_id=cid, capacidad="PAGAR_GASTO", row_version=1)
        assert isinstance(r, servicio.Resultado) and not r.idempotente
        n = s.uno("SELECT count(*) FROM gapto.auditoria WHERE tabla='cuentas' AND registro_id=%s", (cid,))[0]
        assert n == 1  # la auditoria ya esta escrita en ESTA transaccion
        raise _Forzado()

    with pytest.raises((_Forzado, ErrorMotor)):
        fh.en_transaccion(owner, operacion)
    assert _estado(owner, cid) == ([], 1) and _auditorias(owner, cid) == []


def test_ids_de_otro_owner_o_inexistentes_sin_efectos(t):
    owner, _, cli = t
    otro, otro_actor = h.crear_tenant()
    ajena = h.crear_cuenta(otro, [(otro_actor, 100)], capacidades=("PAGAR_GASTO",))
    respuestas = []
    for cid in (ajena, uuid.uuid4()):
        for capacidad, accion in (("RECIBIR_INGRESO", "activar"), ("PAGAR_GASTO", "desactivar")):
            r = _cambiar(cli, cid, capacidad, accion, 1)
            assert r.status_code == 404, r.text
            respuestas.append(r.json())
        for ruta in ("capacidades", "capacidades/historial", "capacidades/PAGAR_GASTO/impacto"):
            r = cli.get(f"{BASE}/{cid}/{ruta}", headers=h.AUTH)
            assert r.status_code == 404, (ruta, r.text)
            respuestas.append(r.json())
    assert all(x == {"codigo": "CUENTA_NO_ENCONTRADA", "mensaje": "No encontrado.", "reintentable": False}
               for x in respuestas)
    assert _estado(otro, ajena) == (["PAGAR_GASTO"], 1) and _auditorias(otro, ajena) == []
    assert ajena not in {c["cuenta_id"] for c in cli.get(f"{BASE}/capacidades", headers=h.AUTH).json()["cuentas"]}

    # Mismo resultado por el servicio con el rol real gapto_runtime (UnidadDeTrabajo de tests).
    from app.capacidades import servicio
    rol = fh.en_transaccion(owner, lambda s: s.uno("SELECT current_user")[0])
    assert rol == "gapto_runtime"
    r = fh.en_transaccion(owner, lambda s: servicio.desactivar(s, cuenta_id=ajena, capacidad="PAGAR_GASTO",
                                                              row_version=1))
    assert r == servicio.Rechazo("CUENTA_NO_ENCONTRADA")
    assert _estado(otro, ajena) == (["PAGAR_GASTO"], 1)


# ------------------------------------------------------------------ lecturas
def test_lista_detalle_y_conteo_sin_configurar(t):
    owner, actor, cli = t
    a = _cuenta(owner, actor, capacidades=("PAGAR_GASTO", "TRANSFERIR_ENTRADA"), nombre="A tarjeta")
    b = _cuenta(owner, actor, capacidades=(), nombre="B sin configurar")
    c = _cuenta(owner, actor, capacidades=("COMPRA_TARJETA", "DOMICILIAR"), nombre="C solo otras")
    d = _cuenta(owner, actor, capacidades=(), nombre="D cerrada")
    h.como_owner(owner, "UPDATE gapto.cuentas SET enabled=false, fecha_cierre=%s WHERE id=%s", (FECHA, d))
    r = cli.get(f"{BASE}/capacidades", headers=h.AUTH)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert [x["cuenta_id"] for x in cuerpo["cuentas"]] == [str(a), str(b), str(c), str(d)]
    assert [x["sin_configurar"] for x in cuerpo["cuentas"]] == [False, True, True, True]
    assert cuerpo["sin_configurar"] == 2  # la cerrada no cuenta para el aviso
    assert cli.get(f"{BASE}/sin-configurar", headers=h.AUTH).json() == {"sin_configurar": 2}

    detalle = cli.get(f"{BASE}/{c}/capacidades", headers=h.AUTH).json()
    assert detalle["row_version"] == 1 and detalle["origen_v3"] is False and detalle["estado"] == "ACTIVA"
    assert detalle["capacidades"] == [
        {"codigo": "PAGAR_GASTO", "etiqueta": "Pagar gastos", "efecto": "Aparece en «Pagado con»",
         "permitida": False, "editable": True},
        {"codigo": "RECIBIR_INGRESO", "etiqueta": "Recibir ingresos", "efecto": "Aparece en «Cobrado en»",
         "permitida": False, "editable": True},
        {"codigo": "TRANSFERIR_SALIDA", "etiqueta": "Enviar a otras cuentas tuyas", "efecto": "Aparece en «Desde»",
         "permitida": False, "editable": True},
        {"codigo": "TRANSFERIR_ENTRADA", "etiqueta": "Recibir de otras cuentas tuyas", "efecto": "Aparece en «A»",
         "permitida": False, "editable": True}]
    assert detalle["otras"] == [
        {"codigo": "COMPRA_TARJETA", "etiqueta": "Compras con tarjeta", "efecto": "Aún no se usa en el registro",
         "permitida": True, "editable": False},
        {"codigo": "DOMICILIAR", "etiqueta": "Domiciliar recibos", "efecto": "Aún no se usa en el registro",
         "permitida": True, "editable": False}]


def test_origen_v3_desde_mapeos_importacion(t):
    """PD-4: «De V3» solo si la cuenta tiene un mapeo RV3 (tabla_destino 'cuentas')."""
    owner, actor, cli = t
    v3 = _cuenta(owner, actor, nombre="Cuenta ING")
    propia = _cuenta(owner, actor, nombre="Otra")
    fuente, origen = uuid.uuid4(), uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.fuentes_importacion (id, owner_user_id, tipo_fuente, nombre_fuente) "
                        "VALUES (%s, %s, 'DB', 'V3 sintetica')", (fuente, owner))
    h.como_owner(owner, "INSERT INTO gapto.registros_origen_importacion (id, fuente_importacion_id, contenedor_origen, "
                        "clave_origen, datos_origen) VALUES (%s, %s, 'public.cuentas_bancarias', '1', '{}'::jsonb)",
                 (origen, fuente))
    h.como_owner(owner, "INSERT INTO gapto.mapeos_importacion (registro_origen_id, tabla_destino, registro_destino_id, "
                        "tipo_mapping, confianza) VALUES (%s, 'cuentas', %s, 'CREADO', 'ALTA')", (origen, v3))
    filas = {x["cuenta_id"]: x["origen_v3"] for x in cli.get(f"{BASE}/capacidades", headers=h.AUTH).json()["cuentas"]}
    assert filas == {str(v3): True, str(propia): False}
    # El origen V3 no aporta capacidades ni entradas de historial (nada inventado).
    assert cli.get(f"{BASE}/{v3}/capacidades/historial", headers=h.AUTH).json() == {"entradas": []}


def test_historial_desde_auditoria(t):
    owner, actor, cli = t
    cid = _cuenta(owner, actor)
    assert cli.get(f"{BASE}/{cid}/capacidades/historial", headers=h.AUTH).json() == {"entradas": []}
    assert _cambiar(cli, cid, "PAGAR_GASTO", "activar", 1).status_code == 200
    assert _cambiar(cli, cid, "TRANSFERIR_ENTRADA", "activar", 2).status_code == 200
    assert _cambiar(cli, cid, "PAGAR_GASTO", "desactivar", 3).status_code == 200
    assert _cambiar(cli, cid, "PAGAR_GASTO", "desactivar", 4).json()["idempotente"] is True  # no deja entrada
    entradas = cli.get(f"{BASE}/{cid}/capacidades/historial", headers=h.AUTH).json()["entradas"]
    assert [(e["accion"], e["capacidad"], e["etiqueta"], e["actor_tipo"], e["actor_es_owner"]) for e in entradas] == [
        ("DESACTIVAR", "PAGAR_GASTO", "Pagar gastos", "USUARIO", True),
        ("ACTIVAR", "TRANSFERIR_ENTRADA", "Recibir de otras cuentas tuyas", "USUARIO", True),
        ("ACTIVAR", "PAGAR_GASTO", "Pagar gastos", "USUARIO", True)]
    # Una auditoria ajena al writer de capacidades sobre la misma cuenta no entra en el historial.
    fh.en_transaccion(owner, lambda s: s.uno(
        "SELECT gapto.fn_registrar_auditoria('cuentas'::varchar, %s::uuid, 'ACTUALIZAR'::varchar, NULL, NULL, "
        "'otro writer'::text)", (cid,)))
    assert len(cli.get(f"{BASE}/{cid}/capacidades/historial", headers=h.AUTH).json()["entradas"]) == 3


def test_impacto_en_plantillas_y_preferencias(t):
    owner, actor, cli = t
    nomina = _cuenta(owner, actor, capacidades=("PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA"))
    otra = _cuenta(owner, actor, capacidades=("PAGAR_GASTO",), nombre="Otra")
    tipos = cli.get("/v1/preferencias", headers=h.AUTH).json()["tipos"]
    alquiler = uuid.uuid4()
    r = cli.post("/v1/plantillas", json={"id": str(alquiler), "nombre": "Alquiler", "tipo_hecho_id": tipos["GASTO"],
                                         "cuenta_default_id": str(nomina)}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    r = cli.post("/v1/plantillas", json={"id": str(uuid.uuid4()), "nombre": "Nomina", "tipo_hecho_id": tipos["INGRESO"],
                                         "cuenta_default_id": str(nomina)}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    r = cli.post("/v1/plantillas", json={"id": str(uuid.uuid4()), "nombre": "Con otra", "tipo_hecho_id": tipos["GASTO"],
                                         "cuenta_default_id": str(otra)}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    hogar = ph.categoria(owner, "Hogar")
    pid, r = ph.alta(cli, categoria_id=hogar, cuenta_default_id=nomina)
    assert r.status_code == 200, r.text

    r = cli.get(f"{BASE}/{nomina}/capacidades/PAGAR_GASTO/impacto", headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "plantillas": [{"plantilla_id": str(alquiler), "nombre": "Alquiler", "enabled": True}],
        "preferencias": [{"preferencia_id": str(pid), "enabled": True, "categoria_id": str(hogar),
                          "categoria_nombre": "Hogar", "tercero_id": None, "tercero_nombre": None}]}
    r = cli.get(f"{BASE}/{nomina}/capacidades/TRANSFERIR_SALIDA/impacto", headers=h.AUTH)
    assert r.json() == {"plantillas": [], "preferencias": []}
    ingreso = cli.get(f"{BASE}/{nomina}/capacidades/RECIBIR_INGRESO/impacto", headers=h.AUTH).json()
    assert [p["nombre"] for p in ingreso["plantillas"]] == ["Nomina"] and ingreso["preferencias"] == []
    # La lectura del impacto no escribe ni bloquea nada.
    assert _estado(owner, nomina) == (["PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA"], 1)


# ------------------------------------------------------------------ CUENTA_SIN_CAPACIDAD (D-CAP-08)
def _nada(owner, intencion_id):
    return h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s",
                  (uuid.UUID(intencion_id),))[0][0] == 0


def test_rechazo_especifico_en_gasto_con_texto_b3(t):
    owner, actor, cli = t
    nomina = _cuenta(owner, actor, capacidades=("PAGAR_GASTO",))
    cuerpo = h.intencion(nomina)
    assert _cambiar(cli, nomina, "PAGAR_GASTO", "desactivar", 1).status_code == 200
    r = cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409, r.text
    assert r.json() == {
        "codigo": "CUENTA_SIN_CAPACIDAD",
        "mensaje": "Cuenta nómina ya no puede pagar gastos. Se cambió mientras registrabas. "
                   "El gasto no se ha guardado: elige otra cuenta.",
        "reintentable": False,
        "detalle": {"cuenta_id": str(nomina), "cuenta": "Cuenta nómina", "operacion": "GASTO",
                    "capacidad": "PAGAR_GASTO"}}
    assert _nada(owner, cuerpo["intencion_id"])
    # Reactivar: la MISMA intencion se registra (el cambio afecta a operaciones nuevas).
    assert _cambiar(cli, nomina, "PAGAR_GASTO", "activar", 2).status_code == 200
    assert cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH).status_code == 200


def test_rechazo_especifico_en_ingreso_y_transferencia(t):
    owner, actor, cli = t
    a = _cuenta(owner, actor, capacidades=("TRANSFERIR_ENTRADA",), nombre="Ahorro")
    b = _cuenta(owner, actor, capacidades=("TRANSFERIR_SALIDA",), nombre="Nómina")
    casos = [
        ("/v1/intenciones/ingreso-cobrado", {"intencion_id": str(uuid.uuid4()), "importe": "10.00", "moneda": "EUR",
                                             "fecha_hecho": FECHA.isoformat(), "cuenta_id": str(a),
                                             "presupuestable": True, "atribucion": "SOLO_MIO",
                                             "categoria": {"estado": "SIN_CATEGORIA"}},
         "Ahorro ya no puede recibir ingresos. Se cambió mientras registrabas. "
         "El ingreso no se ha guardado: elige otra cuenta.", "INGRESO"),
        ("/v1/intenciones/transferencia", {"intencion_id": str(uuid.uuid4()), "importe": "10.00", "moneda": "EUR",
                                           "fecha_hecho": FECHA.isoformat(), "cuenta_origen_id": str(a),
                                           "cuenta_destino_id": str(b)},
         "Ahorro ya no puede enviar a otras cuentas tuyas. Se cambió mientras registrabas. "
         "La transferencia no se ha guardado: elige otra cuenta.", "TRANSFERENCIA_ORIGEN"),
    ]
    for url, cuerpo, mensaje, operacion in casos:
        r = cli.post(url, json=cuerpo, headers=h.AUTH)
        assert r.status_code == 409 and r.json()["codigo"] == "CUENTA_SIN_CAPACIDAD", r.text
        assert r.json()["mensaje"] == mensaje and r.json()["detalle"]["operacion"] == operacion
        assert _nada(owner, cuerpo["intencion_id"])
    # Destino sin TRANSFERIR_ENTRADA.
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": "10.00", "moneda": "EUR", "fecha_hecho": FECHA.isoformat(),
              "cuenta_origen_id": str(b), "cuenta_destino_id": str(_cuenta(owner, actor, nombre="Hucha"))}
    r = cli.post("/v1/intenciones/transferencia", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["mensaje"] == (
        "Hucha ya no puede recibir de otras cuentas tuyas. Se cambió mientras registrabas. "
        "La transferencia no se ha guardado: elige otra cuenta."), r.text
    assert r.json()["detalle"]["operacion"] == "TRANSFERENCIA_DESTINO" and _nada(owner, cuerpo["intencion_id"])


def test_otros_motivos_conservan_su_codigo(t):
    """Solo SIN_CAPACIDAD cambia: deshabilitada, cerrada y ajena -> CUENTA_DESCONOCIDA; USD -> MONEDA_INVALIDA."""
    owner, actor, cli = t
    desh = _cuenta(owner, actor, capacidades=("PAGAR_GASTO",))
    ph.deshabilitar_cuenta(owner, desh)
    cerrada = _cuenta(owner, actor, capacidades=("PAGAR_GASTO",))
    h.como_owner(owner, "UPDATE gapto.cuentas SET enabled=false, fecha_cierre=%s WHERE id=%s", (FECHA, cerrada))
    otro, otro_actor = h.crear_tenant()
    ajena = h.crear_cuenta(otro, [(otro_actor, 100)], capacidades=())
    usd = ph.cuenta(owner, actor, moneda="USD", capacidades=())
    for cid, esperado in ((desh, "CUENTA_DESCONOCIDA"), (cerrada, "CUENTA_DESCONOCIDA"),
                          (ajena, "CUENTA_DESCONOCIDA"), (usd, "MONEDA_INVALIDA")):
        r = cli.post("/v1/intenciones/gasto-pagado", json=h.intencion(cid), headers=h.AUTH)
        assert (r.status_code, r.json()["codigo"]) == (422, esperado), r.text
