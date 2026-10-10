# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_179_f05_03_plantillas.py
# Ruta: tests/api/test_179_f05_03_plantillas.py
# Descripcion: Plantillas de registro y acciones rapidas (F05-03 J2 §1.6;
#   F05 §45.3 A1/A2/A3/A6, §45.4 R1/R3, §46.3 A11; CC-03-8 enmendado; D-032.2).
#   Writers por HTTP, propuesta con la capa plantilla y RLS cruzada en INSERT
#   y UPDATE sobre las primitivas del repositorio (gapto_runtime, FORCE RLS).
#   Casos §45.7: 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 15 (12 y la concurrencia en
#   el lote serial de concurrencia; 6 y 14 en el registro; 13 en onboarding).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.6)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

BASE = "/v1/plantillas"
ACC = "/v1/acciones-rapidas"
PROP = "/v1/registro/propuesta"
FECHA = ph.FECHA


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    a = ph.cuenta(owner, actor, nombre="Tarjeta")
    b = ph.cuenta(owner, actor, nombre="Efectivo")
    return owner, actor, cli, a, b


def tipo(owner, codigo="GASTO"):
    return h.leer(owner, "SELECT id FROM gapto.tipos_hecho WHERE codigo=%s", (codigo,))[0][0]


def _s(v):
    return str(v) if isinstance(v, uuid.UUID) else v


def alta(cli, owner, pid=None, *, nombre="Súper semanal", codigo="GASTO", **campos):
    pid = pid or uuid.uuid4()
    cuerpo = {"id": str(pid), "nombre": nombre, "tipo_hecho_id": str(tipo(owner, codigo)),
              **{k: _s(v) for k, v in campos.items()}}
    return pid, cli.post(BASE, json=cuerpo, headers=h.AUTH)


def editar(cli, owner, pid, rv, *, nombre="Súper semanal", codigo="GASTO", **campos):
    cuerpo = {"row_version": rv, "nombre": nombre, "tipo_hecho_id": str(tipo(owner, codigo)),
              **{k: _s(v) for k, v in campos.items()}}
    return cli.post(f"{BASE}/{pid}/editar", json=cuerpo, headers=h.AUTH)


def accion(cli, plantilla, aid=None, nombre="Súper", icono_key=None):
    aid = aid or uuid.uuid4()
    return aid, cli.post(ACC, json={"id": str(aid), "plantilla_registro_id": str(plantilla), "nombre": nombre,
                                    "icono_key": icono_key}, headers=h.AUTH)


def propuesta(cli, **params):
    q = {"tipo": "GASTO", "fecha": FECHA.isoformat(), **{k: _s(v) for k, v in params.items()}}
    return cli.get(PROP, params=q, headers=h.AUTH)


def fila(owner, pid):
    f = h.leer(owner, "SELECT nombre, categoria_id, cuenta_default_id, presupuestable_default, enabled, row_version "
                      "FROM gapto.plantillas_registro WHERE id=%s", (pid,))
    return f[0] if f else None


def _codigo(r):
    return r.json().get("codigo")


# ------------------------------------------------------------------ writers de plantilla
def test_caso1_super_semanal_y_propuesta_por_campo(t):
    owner, _, cli, a, _ = t
    cat = ph.categoria(owner, "Supermercado")
    pid, r = alta(cli, owner, categoria_id=cat, cuenta_default_id=a, presupuestable_default=True)
    assert r.status_code == 200, r.text
    assert fila(owner, pid) == ("Súper semanal", cat, a, True, True, 1)
    _, r2 = alta(cli, owner, pid, categoria_id=cat, cuenta_default_id=a, presupuestable_default=True)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True
    p = propuesta(cli, plantilla_id=pid).json()
    origen = {"capa": "PLANTILLA", "plantilla_id": str(pid), "preferencia_id": None}
    assert p["campos"]["categoria"] == {"valor": str(cat), "origen": origen}
    assert p["campos"]["cuenta"] == {"valor": str(a), "origen": origen}
    assert p["campos"]["presupuestable"] == {"valor": True, "origen": origen}
    assert p["avisos"] == []
    aud = h.leer(owner, "SELECT accion, motivo FROM gapto.auditoria WHERE registro_id=%s", (pid,))
    assert aud == [("CREAR", "F05-03 PLANTILLA ALTA")]


def test_caso2_solo_categoria_con_cuenta_de_una_preferencia(t):
    owner, _, cli, a, b = t
    cat = ph.categoria(owner, "Supermercado")
    pref = ph.insertar_sql(owner, categoria_id=cat, cuenta=b)
    pid, _ = alta(cli, owner, categoria_id=cat)
    c = propuesta(cli, plantilla_id=pid).json()["campos"]
    assert c["categoria"]["origen"]["capa"] == "PLANTILLA"
    assert c["cuenta"] == {"valor": str(b), "origen": {"capa": "PREFERENCIA", "plantilla_id": None,
                                                         "preferencia_id": str(pref)}}
    assert c["presupuestable"] is None  # sin propuesta: nunca se inventa


def test_caso3_categoria_explicita_reorienta_las_preferencias(t):
    owner, _, cli, a, b = t
    super_, farmacia = ph.categoria(owner, "Supermercado"), ph.categoria(owner, "Farmacia")
    ph.insertar_sql(owner, categoria_id=farmacia, cuenta=b)
    pid, _ = alta(cli, owner, categoria_id=super_, presupuestable_default=True)
    c = propuesta(cli, plantilla_id=pid, categoria_id=farmacia).json()["campos"]
    assert c["cuenta"]["valor"] == str(b) and c["cuenta"]["origen"]["capa"] == "PREFERENCIA"
    assert c["presupuestable"]["origen"]["capa"] == "PLANTILLA"  # el resto de la plantilla se mantiene


@pytest.mark.parametrize("caso", ["preferencia", "unica", "ninguna"])
def test_caso4_cuenta_no_disponible_cae_a_la_capa_siguiente(t, caso):
    owner, actor, cli, a, b = t
    pid, _ = alta(cli, owner, cuenta_default_id=a, presupuestable_default=False)
    ph.deshabilitar_cuenta(owner, a)
    if caso == "preferencia":
        pref = ph.insertar_sql(owner, cuenta=b)
    elif caso == "ninguna":
        ph.cuenta(owner, actor, nombre="Otra")  # dos elegibles: sin cuenta unica
    p = propuesta(cli, plantilla_id=pid).json()
    assert {"campo": "cuenta", "motivo": "NO_ELEGIBLE"} in p["avisos"]
    c = p["campos"]["cuenta"]
    if caso == "preferencia":
        assert c["origen"] == {"capa": "PREFERENCIA", "plantilla_id": None, "preferencia_id": str(pref)}
    elif caso == "unica":
        assert c == {"valor": str(b), "origen": {"capa": "DEFAULT_GENERAL", "plantilla_id": None,
                                                 "preferencia_id": None}}
    else:
        assert c is None
    assert p["campos"]["presupuestable"]["valor"] is False


def test_caso5_categoria_deshabilitada_queda_pendiente_sin_fallback(t):
    owner, _, cli, a, _ = t
    cat = ph.categoria(owner, "Supermercado")
    pid, _ = alta(cli, owner, categoria_id=cat, cuenta_default_id=a)
    h.como_owner(owner, "UPDATE gapto.categorias_financieras SET enabled=false WHERE id=%s", (cat,))
    p = propuesta(cli, plantilla_id=pid).json()
    assert p["campos"]["categoria"] is None and {"campo": "categoria", "motivo": "NO_ELEGIBLE"} in p["avisos"]
    lista = cli.get(BASE, headers=h.AUTH).json()["plantillas"]
    assert {"campo": "categoria", "motivo": "NO_ELEGIBLE"} in lista[0]["avisos"]


def test_plantilla_de_otro_tipo_o_desactivada_no_aplica(t):
    owner, _, cli, a, _ = t
    pid, _ = alta(cli, owner, cuenta_default_id=a)
    p = propuesta(cli, plantilla_id=pid, tipo="INGRESO").json()
    assert p["avisos"] == [{"campo": "plantilla", "motivo": "NO_DISPONIBLE"}]
    assert cli.post(f"{BASE}/{pid}/desactivar", json={"row_version": 1}, headers=h.AUTH).status_code == 200
    assert propuesta(cli, plantilla_id=pid).json()["avisos"] == [{"campo": "plantilla", "motivo": "NO_DISPONIBLE"}]


# ------------------------------------------------------------------ validaciones del writer
def test_tipos_admitidos_y_rechazados(t):
    owner, _, cli, a, _ = t
    _, r = alta(cli, owner, nombre="Nómina", codigo="INGRESO", cuenta_default_id=a)
    assert r.status_code == 200, r.text
    for codigo in ("TRANSFERENCIA", "CONDONACION"):
        pid, r = alta(cli, owner, nombre=f"P {codigo}", codigo=codigo, presupuestable_default=True)
        assert r.status_code == 422 and _codigo(r) == "PLANTILLA_TIPO_NO_ADMITIDO"
        assert fila(owner, pid) is None


def test_sin_valor_y_campos_no_admitidos(t):
    owner, _, cli, _, _ = t
    pid, r = alta(cli, owner)
    assert r.status_code == 422 and _codigo(r) == "PLANTILLA_SIN_VALOR" and fila(owner, pid) is None
    for extra in ({"concepto": "x"}, {"nota": "x"}, {"importe": "3.00"}, {"atribucion": "SOLO_MIO"},
                  {"magnitudes": []}):
        _, r = alta(cli, owner, presupuestable_default=True, **extra)
        assert r.status_code == 422 and _codigo(r) == "ENTRADA_INVALIDA", extra


def test_tercero_y_contexto_admitidos_y_entidad_solo_contexto(t):
    owner, _, cli, _, _ = t
    ter = ph.tercero(owner)
    ctx = uuid.uuid4()
    assert cli.post("/v1/contextos", json={"id": str(ctx), "nombre": "Viaje", "tipo_contexto": "VIAJE"},
                    headers=h.AUTH).status_code == 200
    _, r = alta(cli, owner, nombre="Con tercero", tercero_id=ter)
    assert r.status_code == 200, r.text
    _, r = alta(cli, owner, nombre="Con contexto", entidad_id=ctx)
    assert r.status_code == 200, r.text
    pid, r = alta(cli, owner, nombre="Con propiedad", entidad_id=ph.entidad(owner))
    assert r.status_code == 409 and _codigo(r) == "PLANTILLA_ENTIDAD_NO_CONTEXTO" and fila(owner, pid) is None
    h.como_owner(owner, "UPDATE gapto.terceros SET enabled=false WHERE id=%s", (ter,))
    _, r = alta(cli, owner, nombre="Tercero off", tercero_id=ter)
    assert r.status_code == 409 and _codigo(r) == "PLANTILLA_TERCERO_NO_ELEGIBLE"


def test_categoria_por_ambito_del_tipo_y_cuenta_por_capacidad(t):
    owner, actor, cli, a, _ = t
    gasto, ingreso = ph.categoria(owner, "Súper"), ph.categoria(owner, "Nómina", ambito="INGRESO")
    _, r = alta(cli, owner, nombre="Mal tipo", categoria_id=ingreso)
    assert r.status_code == 409 and _codigo(r) == "PLANTILLA_CATEGORIA_NO_ELEGIBLE"
    _, r = alta(cli, owner, nombre="Ingreso ok", codigo="INGRESO", categoria_id=ingreso)
    assert r.status_code == 200
    credito = ph.cuenta(owner, actor, naturaleza="PASIVO")  # PAGAR_GASTO, sin RECIBIR_INGRESO
    _, r = alta(cli, owner, nombre="Cobro en credito", codigo="INGRESO", cuenta_default_id=credito)
    assert r.status_code == 409 and _codigo(r) == "PLANTILLA_CUENTA_NO_ELEGIBLE"
    _, r = alta(cli, owner, nombre="Pago con credito", cuenta_default_id=credito, categoria_id=gasto)
    assert r.status_code == 200


def test_caso9_nombre_repetido_normalizado_y_reactivacion(t):
    owner, _, cli, a, _ = t
    p1, _ = alta(cli, owner, nombre="Súper semanal", presupuestable_default=True)
    pid, r = alta(cli, owner, nombre="  SUPER   semanal ", presupuestable_default=False)
    assert r.status_code == 409 and _codigo(r) == "PLANTILLA_NOMBRE_REPETIDO"
    assert r.json()["detalle"] == {"plantilla_id": str(p1)} and fila(owner, pid) is None
    assert cli.post(f"{BASE}/{p1}/desactivar", json={"row_version": 1}, headers=h.AUTH).status_code == 200
    p2, r = alta(cli, owner, nombre="Super Semanal", presupuestable_default=False)
    assert r.status_code == 200  # la desactivada no cuenta
    r = cli.post(f"{BASE}/{p1}/reactivar", json={"row_version": 2}, headers=h.AUTH)
    assert r.status_code == 409 and _codigo(r) == "PLANTILLA_NOMBRE_REPETIDO" and fila(owner, p1)[4] is False
    r = editar(cli, owner, p2, 1, nombre="Súper semanal ", presupuestable_default=False)
    assert r.status_code == 200 and r.json()["idempotente"] is False  # renombrar a si misma: sin choque


def test_caso11_edicion_con_row_version(t):
    owner, _, cli, a, b = t
    pid, _ = alta(cli, owner, cuenta_default_id=a)
    assert editar(cli, owner, pid, 1, cuenta_default_id=b).status_code == 200
    r = editar(cli, owner, pid, 1, cuenta_default_id=a)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA" and fila(owner, pid)[2] == b
    r = editar(cli, owner, uuid.uuid4(), 1, cuenta_default_id=a)
    assert r.status_code == 404 and _codigo(r) == "PLANTILLA_NO_ENCONTRADA"


# ------------------------------------------------------------------ acciones rapidas
def _plantillas(cli, owner, n):
    return [alta(cli, owner, nombre=f"P{i}", presupuestable_default=True)[0] for i in range(n)]


def test_caso8_limite_de_tres_y_una_por_plantilla(t):
    owner, _, cli, _, _ = t
    ps = _plantillas(cli, owner, 4)
    for p in ps[:3]:
        assert accion(cli, p)[1].status_code == 200
    aid, r = accion(cli, ps[3])
    assert r.status_code == 409 and _codigo(r) == "ACCION_LIMITE_ALCANZADO"
    _, r = accion(cli, ps[0], nombre="Otra vez")
    assert r.status_code == 409 and _codigo(r) == "ACCION_PLANTILLA_YA_EN_INICIO"
    acciones = cli.get(BASE, headers=h.AUTH).json()["acciones"]
    assert [x["orden"] for x in acciones] == [0, 1, 2]


def test_accion_icono_nombre_idempotencia(t):
    owner, _, cli, _, _ = t
    p = _plantillas(cli, owner, 1)[0]
    aid, r = accion(cli, p, icono_key="compras.carrito")
    assert r.status_code == 200
    assert accion(cli, p, aid, icono_key="compras.carrito")[1].json()["idempotente"] is True
    _, r = accion(cli, p, aid, icono_key="ocio.cine")
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    q = _plantillas(cli, owner, 2)[1]
    _, r = accion(cli, q, icono_key="pricetag-outline")  # la reserva de la app no es clave publicada
    assert r.status_code == 422 and _codigo(r) == "ICONO_ACCION_NO_VALIDO"
    r = cli.post(f"{ACC}/{aid}/editar", json={"row_version": 1, "nombre": "Súper", "icono_key": None},
                 headers=h.AUTH)
    assert r.status_code == 200 and r.json()["accion"]["icono_key"] is None


def test_accion_sobre_plantilla_desactivada_o_ajena(t):
    owner, _, cli, _, _ = t
    p = _plantillas(cli, owner, 1)[0]
    assert cli.post(f"{BASE}/{p}/desactivar", json={"row_version": 1}, headers=h.AUTH).status_code == 200
    _, r = accion(cli, p)
    assert r.status_code == 409 and _codigo(r) == "ACCION_PLANTILLA_NO_DISPONIBLE"
    otro, _, cli_otro = ph.tenant()
    ajena, _ = alta(cli_otro, otro, presupuestable_default=True)
    _, r = accion(cli, ajena)
    assert r.status_code == 409 and _codigo(r) == "ACCION_PLANTILLA_NO_DISPONIBLE"


def test_caso10_desactivar_en_cascada_y_reactivar_sin_volver_a_inicio(t):
    owner, _, cli, _, _ = t
    p = _plantillas(cli, owner, 1)[0]
    aid, _ = accion(cli, p)
    r = cli.post(f"{BASE}/{p}/desactivar", json={"row_version": 1}, headers=h.AUTH)
    assert r.status_code == 200 and set(r.json()["modificadas"]) == {str(p), str(aid)}
    assert h.leer(owner, "SELECT enabled FROM gapto.acciones_rapidas WHERE id=%s", (aid,)) == [(False,)]
    assert cli.post(f"{BASE}/{p}/reactivar", json={"row_version": 2}, headers=h.AUTH).status_code == 200
    assert h.leer(owner, "SELECT enabled FROM gapto.acciones_rapidas WHERE id=%s", (aid,)) == [(False,)]
    assert cli.get(BASE, headers=h.AUTH).json()["acciones"] == []


def test_reordenar_atomico_y_conjunto_completo(t):
    owner, _, cli, _, _ = t
    ps = _plantillas(cli, owner, 3)
    ids = [accion(cli, p, nombre=f"A{i}")[0] for i, p in enumerate(ps)]
    cuerpo = {"acciones": [{"id": str(i), "row_version": 1} for i in reversed(ids)]}
    r = cli.post(f"{ACC}/reordenar", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert [x["id"] for x in cli.get(BASE, headers=h.AUTH).json()["acciones"]] == [str(i) for i in reversed(ids)]
    r = cli.post(f"{ACC}/reordenar", json={"acciones": cuerpo["acciones"][:2]}, headers=h.AUTH)
    assert r.status_code == 409 and _codigo(r) == "CONJUNTO_ACCIONES_DESFASADO"
    r = cli.post(f"{ACC}/reordenar", json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA"  # las movidas subieron de version


# ------------------------------------------------------------------ «Guardar como plantilla» (A6) y caso 7
def test_caso7_guardar_como_plantilla_doble_envio_y_fallo_inyectado(t, monkeypatch):
    from app.core.errores import ErrorMotor
    from app.plantillas import servicio

    owner, _, cli, a, _ = t
    gasto = h.intencion(a)
    assert cli.post("/v1/intenciones/gasto-pagado", json=gasto, headers=h.AUTH).status_code == 200
    pid = uuid.uuid4()
    assert alta(cli, owner, pid, nombre="Desde el éxito", cuenta_default_id=a)[1].status_code == 200
    assert alta(cli, owner, pid, nombre="Desde el éxito", cuenta_default_id=a)[1].json()["idempotente"] is True
    monkeypatch.setattr(servicio, "_auditar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("inyectado")))
    otra, r = alta(cli, owner, nombre="Fallida", cuenta_default_id=a)
    assert r.status_code == 500 and fila(owner, otra) is None
    hid = uuid.UUID(gasto["intencion_id"])
    assert h.leer(owner, "SELECT estado FROM gapto.hechos_financieros WHERE id=%s", (hid,)) == [("ACTIVO",)]


# ------------------------------------------------------------------ caso 15 e identidad de otro owner
def test_caso15_ids_de_otro_owner(t):
    owner, actor, cli, a, _ = t
    otro, otro_actor, cli_otro = ph.tenant()
    ajena, _ = alta(cli_otro, otro, presupuestable_default=True)
    _, r = alta(cli, owner, ajena, presupuestable_default=True)
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert fila(otro, ajena)[5] == 1
    cat_ajena = ph.categoria(otro, "Ajena")
    cuenta_ajena = ph.cuenta(otro, otro_actor)
    _, r = alta(cli, owner, nombre="X", categoria_id=cat_ajena)
    assert _codigo(r) == "PLANTILLA_CATEGORIA_NO_ELEGIBLE"
    _, r = alta(cli, owner, nombre="Y", cuenta_default_id=cuenta_ajena)
    assert _codigo(r) == "PLANTILLA_CUENTA_NO_ELEGIBLE"
    _, r = alta(cli, owner, nombre="Z", tercero_id=ph.tercero(otro))
    assert _codigo(r) == "PLANTILLA_TERCERO_NO_ELEGIBLE"
    aid, r = accion(cli_otro, ajena)
    _, r = accion(cli, alta(cli, owner, presupuestable_default=True)[0], aid)
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


# ------------------------------------------------------------------ RLS cruzada (D-032.2): INSERT y UPDATE -> 42501
def _como_runtime(owner, op):
    with psycopg.connect(h.dsn()) as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET LOCAL ROLE gapto_runtime")
            cur.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            op(cur)


@pytest.mark.parametrize("columna", ["categoria_id", "tercero_id", "entidad_id", "cuenta_default_id"])
def test_rls_cruzada_en_insert_y_update_de_plantillas(t, columna):
    owner, actor, cli, a, _ = t
    otro, otro_actor = h.crear_tenant()
    ajena = {"categoria_id": lambda: ph.categoria(otro, "Ajena"), "tercero_id": lambda: ph.tercero(otro),
             "entidad_id": lambda: ph.entidad(otro), "cuenta_default_id": lambda: ph.cuenta(otro, otro_actor)}[columna]()
    g = tipo(owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como_runtime(owner, lambda cur: cur.execute(
            f"INSERT INTO gapto.plantillas_registro (id, owner_user_id, nombre, tipo_hecho_id, {columna}) "
            "VALUES (%s, %s, 'X', %s, %s)", (uuid.uuid4(), owner, g, ajena)))
    pid, _ = alta(cli, owner, presupuestable_default=True)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como_runtime(owner, lambda cur: cur.execute(
            f"UPDATE gapto.plantillas_registro SET {columna} = %s WHERE id = %s", (ajena, pid)))
    assert fila(owner, pid)[5] == 1


def test_rls_cruzada_en_insert_y_update_de_acciones_y_preferencias(t):
    owner, actor, cli, a, _ = t
    otro, _, cli_otro = ph.tenant()
    ajena, _ = alta(cli_otro, otro, presupuestable_default=True)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como_runtime(owner, lambda cur: cur.execute(
            "INSERT INTO gapto.acciones_rapidas (id, owner_user_id, nombre, plantilla_registro_id) "
            "VALUES (%s, %s, 'X', %s)", (uuid.uuid4(), owner, ajena)))
    p = alta(cli, owner, presupuestable_default=True)[0]
    aid, _ = accion(cli, p)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como_runtime(owner, lambda cur: cur.execute(
            "UPDATE gapto.acciones_rapidas SET plantilla_registro_id = %s WHERE id = %s", (ajena, aid)))
    pref, _ = ph.alta(cli, cuenta_default_id=a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como_runtime(owner, lambda cur: cur.execute(
            "UPDATE gapto.preferencias_registro SET categoria_id = %s WHERE id = %s", (ph.categoria(otro, "Aj"), pref)))


def test_rls_traducida_a_codigo_estable_si_falta_la_validacion(t, monkeypatch):
    """Defensa: si una referencia ajena llegara al INSERT (validacion
    anulada), la RLS la rechaza y el writer responde REFERENCIA_NO_DISPONIBLE
    sin escribir."""
    from app.plantillas import servicio

    owner, _, cli, _, _ = t
    otro, otro_actor = h.crear_tenant()
    monkeypatch.setattr(servicio, "_validar", lambda *a, **k: None)
    pid, r = alta(cli, owner, nombre="X", cuenta_default_id=ph.cuenta(otro, otro_actor))
    assert r.status_code == 409 and _codigo(r) == "REFERENCIA_NO_DISPONIBLE" and fila(owner, pid) is None


def test_el_registro_no_toma_el_advisory_plantillas(t):
    """R2: con (PLANTILLAS, owner) retenido por otra sesion, el registro y la
    propuesta terminan sin esperar."""
    import threading

    owner, _, cli, a, _ = t
    x = fh.sesion_owner(owner)
    x.execute("SELECT pg_advisory_xact_lock(hashtext('gapto:PLANTILLAS'), hashtext(%s::uuid::text))", (str(owner),))
    salida = {}

    def trabajo():
        salida["registro"] = cli.post("/v1/intenciones/gasto-pagado", json=h.intencion(a), headers=h.AUTH)
        salida["propuesta"] = propuesta(cli)

    hilo = threading.Thread(target=trabajo)
    hilo.start()
    hilo.join(timeout=15)
    terminado = not hilo.is_alive()
    x.execute("ROLLBACK")
    x.close()
    hilo.join(timeout=15)
    assert terminado, "el registro o la propuesta esperaron el advisory PLANTILLAS"
    assert salida["registro"].status_code == 200 and salida["propuesta"].status_code == 200


def test_mismo_uuid_con_otro_contenido(t):
    owner, _, cli, a, b = t
    pid, _ = alta(cli, owner, cuenta_default_id=a)
    _, r = alta(cli, owner, pid, cuenta_default_id=b)
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert fila(owner, pid)[2] == a and fila(owner, pid)[5] == 1
