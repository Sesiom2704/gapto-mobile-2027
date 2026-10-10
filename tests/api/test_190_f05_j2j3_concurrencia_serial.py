# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_190_f05_j2j3_concurrencia_serial.py
# Ruta: tests/api/test_190_f05_j2j3_concurrencia_serial.py
# Descripcion: Bateria SERIAL y determinista de concurrencia de F05-03 /
#   F05-04 (J2 §3; F05 §45.4 R4, §46.4 R4; F05-D032 C2/C3; WM 12C.1). FUERA
#   de la suite general: solo se ejecuta con GAPTO_J2J3_CONCURRENCIA=1 (si
#   no, se omite). Si GAPTO_J2J3_EVIDENCIA apunta a una carpeta, cada
#   escenario deja alli su JSON con pg_locks y sondas NOWAIT.
#   Tecnica: una sesion BARRERA retiene un lock (fila o advisory); los
#   comandos se lanzan uno a uno y cada uno debe quedar ESPERANDO a la
#   barrera (pg_blocking_pids) antes de lanzar el siguiente; al liberar,
#   PostgreSQL concede en orden de llegada. Asi el orden es determinista.
#   Escenarios:
#     L1 orden de locks del registro con contexto: INVERSIONES (advisory)
#        ya concedido cuando espera la cuenta (RG01);
#     L2 transferencia: las dos cuentas en ORDER BY id (sonda NOWAIT sobre
#        la de menor id mientras espera la de mayor);
#     L3 registro frente a desactivacion de la categoria (dos ordenes);
#     L4 registro frente a desactivacion del tercero y del contexto;
#     L5 transferencia frente a retirada de capacidad y frente a
#        desactivacion de la cuenta;
#     L6 dos altas de tercero con el mismo nombre (dos ordenes): ambas;
#     L7 dos altas de plantilla con el mismo nombre (dos ordenes): gana la
#        primera; alta de acceso frente a desactivacion de la plantilla
#        (dos ordenes); dos reordenaciones (PL01);
#     L8 onboarding frente a alta manual de categoria (dos ordenes);
#     L9 ordenes opuestos con 40P01: la UdT reintenta la transaccion
#        COMPLETA y no queda nada parcial.
#   Espera de los pasos tras liberar la barrera (_serie): la fija
#   GAPTO_J2J3_JOIN_TIMEOUT_S (segundos); sin ella, 30 s si la base es
#   local (socket o localhost/127.0.0.1/::1, la misma regla de host local
#   que bootstrap_dev_db.py y comun_envdev.py) y 300 s si es un proveedor
#   remoto (Neon: el onboarding de 93 nodos tarda ~30-85 s por latencia).
#   Solo cambia cuanto se espera; las aserciones de orden y de resultado
#   son las mismas. Cada JSON de evidencia anota la espera aplicada y la
#   duracion de cada paso.
# Version: 0.2.0 (MANT-190-L8, AJ-J4-01)
# Historial:
#   0.1.0 F05-03/F05-04 J2 §3: bateria inicial.
#   0.2.0 MANT-190-L8 (AJ-J4-01): espera configurable en _serie
#         (GAPTO_J2J3_JOIN_TIMEOUT_S; 30 s local, 300 s proveedor remoto).
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import uuid

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_J2J3_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_J2J3_CONCURRENCIA=1)")
GASTO = "/v1/intenciones/gasto-pagado"
TRANSF = "/v1/intenciones/transferencia"
HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}
ESPERA_LOCAL_S = 30.0
ESPERA_PROVEEDOR_S = 300.0


# ------------------------------------------------------------------ utilidades
def _espera_join_s() -> float:
    """Segundos que _serie espera a cada paso tras liberar la barrera."""
    valor = os.getenv("GAPTO_J2J3_JOIN_TIMEOUT_S")
    if valor:
        return float(valor)
    host = conninfo_to_dict(h.dsn()).get("host", "")
    local = host == "" or host.startswith("/") or host in HOSTS_LOCALES
    return ESPERA_LOCAL_S if local else ESPERA_PROVEEDOR_S


def _evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_J2J3_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=2, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def _barrera_fila(owner, sql: str, params: tuple):
    c = fh.sesion_owner(owner)
    c.execute(sql, params)
    return c


def _barrera_advisory(owner, clave: str):
    c = fh.sesion_owner(owner)
    c.execute(f"SELECT pg_advisory_xact_lock(hashtext('gapto:{clave}'), hashtext(%s::uuid::text))", (str(owner),))
    return c


def _bloqueados(pid_x: int, minimo: int, limite: float = 10.0) -> list[int]:
    fin = time.monotonic() + limite
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        while time.monotonic() < fin:
            # Bloqueados directa o TRANSITIVAMENTE por la barrera (el segundo
            # en llegar espera el lock de tupla del primero, no a la barrera).
            filas = mon.execute("SELECT pid, pg_blocking_pids(pid), backend_start FROM pg_stat_activity "
                                "WHERE cardinality(pg_blocking_pids(pid)) > 0").fetchall()
            bloqueados, cambio = set(), True
            while cambio:
                cambio = False
                for pid, por, _ in filas:
                    if pid not in bloqueados and (pid_x in por or bloqueados & set(por)):
                        bloqueados.add(pid)
                        cambio = True
            pids = [f[0] for f in sorted(filas, key=lambda f: f[2]) if f[0] in bloqueados]
            if len(pids) >= minimo:
                return pids
            time.sleep(0.05)
    return []


def _locks(pid: int) -> list[dict]:
    with psycopg.connect(h.dsn(), autocommit=True) as mon:
        filas = mon.execute(
            "SELECT locktype, mode, granted, classid, objid, objsubid, relation::regclass::text "
            "FROM pg_locks WHERE pid = %s ORDER BY granted DESC, locktype", (pid,)).fetchall()
    claves = ("locktype", "mode", "granted", "classid", "objid", "objsubid", "relacion")
    return [dict(zip(claves, f)) for f in filas]


def _clave_advisory(owner, clave: str) -> tuple[int, int]:
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        a, b = c.execute("SELECT hashtext(%s), hashtext(%s::uuid::text)", (f"gapto:{clave}", str(owner))).fetchone()
    return a & 0xFFFFFFFF, b & 0xFFFFFFFF


def _tiene_advisory(locks: list[dict], clave: tuple[int, int]) -> bool:
    return any(l["locktype"] == "advisory" and l["granted"] and (l["classid"], l["objid"]) == clave for l in locks)


def _nowait(owner, sql: str, params: tuple) -> bool:
    """True si la fila esta bloqueada por otra transaccion (55P03)."""
    c = fh.sesion_owner(owner)
    try:
        c.execute(sql + " NOWAIT", params)
        return False
    except psycopg.errors.LockNotAvailable:
        return True
    finally:
        c.rollback()
        c.close()


def _serie(barrera, pasos: list, nombre: str, inspeccion=None) -> dict:
    """Lanza los pasos EN ORDEN (cada uno debe quedar esperando a la barrera
    antes del siguiente), inspecciona y libera. Devuelve {clave: resultado}."""
    salida: dict = {}
    duraciones: dict = {}
    hilos = []
    evid: dict = {"escenario": nombre, "pasos": [p[0] for p in pasos]}

    def _ejecutar(clave, fn):
        inicio = time.monotonic()
        resultado = fn()
        duraciones[clave] = round(time.monotonic() - inicio, 3)
        salida[clave] = resultado

    try:
        pid_x = fh.pid_servidor(barrera)
        for n, (clave, fn) in enumerate(pasos, start=1):
            hilo = threading.Thread(target=_ejecutar, args=(clave, fn))
            hilo.start()
            hilos.append(hilo)
            pids = _bloqueados(pid_x, n)
            assert len(pids) >= n, f"{clave} no espero a la barrera"
            evid[f"locks_{clave}"] = _locks(pids[n - 1])
        assert not salida, "algun paso termino sin esperar a la barrera"
        if inspeccion:
            evid["inspeccion"] = inspeccion(evid)
        barrera.execute("COMMIT")
    finally:
        barrera.close()
    espera = _espera_join_s()
    evid["espera_join_s"] = espera
    for hilo in hilos:
        hilo.join(timeout=espera)
        assert not hilo.is_alive()
    evid["duracion_s"] = duraciones
    evid["resultado"] = {k: (v.status_code, v.json()) if hasattr(v, "status_code") else repr(v)
                         for k, v in salida.items()}
    _evidencia(nombre, evid)
    return salida


def _cod(r):
    return r.json().get("codigo")


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    corriente = h.crear_cuenta(owner, [(actor, 100)], tipo="CORRIENTE")
    ahorro = h.crear_cuenta(owner, [(actor, 100)], tipo="AHORRO")
    return owner, actor, cli, corriente, ahorro


def _tercero(cli, nombre="ALDI"):
    tid = uuid.uuid4()
    r = cli.post("/v1/terceros", json={"id": str(tid), "nombre": nombre}, headers=h.AUTH)
    return tid, r


def _contexto(cli):
    cid = uuid.uuid4()
    assert cli.post("/v1/contextos", json={"id": str(cid), "nombre": "Viaje", "tipo_contexto": "VIAJE"},
                    headers=h.AUTH).status_code == 200
    return cid


# ------------------------------------------------------------------ L1 / L2 orden de locks
def test_l1_registro_con_contexto_toma_inversiones_antes_que_la_cuenta(t):
    owner, _, cli, corriente, _ = t
    ctx = _contexto(cli)
    clave = _clave_advisory(owner, "INVERSIONES")
    barrera = _barrera_fila(owner, "SELECT id FROM gapto.cuentas WHERE id=%s FOR UPDATE", (corriente,))
    cuerpo = h.intencion(corriente, contexto_id=str(ctx))

    def inspeccion(evid):
        tiene = _tiene_advisory(evid["locks_registro"], clave)
        assert tiene, "el registro espera la cuenta SIN haber tomado INVERSIONES"
        return {"inversiones_concedido_mientras_espera_la_cuenta": tiene}

    salida = _serie(barrera, [("registro", lambda: cli.post(GASTO, json=cuerpo, headers=h.AUTH))],
                    "L1_inversiones_antes_que_cuenta", inspeccion)
    assert salida["registro"].status_code == 200


def test_l1_registro_sin_contexto_no_toma_inversiones(t):
    owner, _, cli, corriente, _ = t
    clave = _clave_advisory(owner, "INVERSIONES")
    barrera = _barrera_fila(owner, "SELECT id FROM gapto.cuentas WHERE id=%s FOR UPDATE", (corriente,))

    def inspeccion(evid):
        assert not _tiene_advisory(evid["locks_registro"], clave)
        return {"inversiones": False}

    salida = _serie(barrera, [("registro", lambda: cli.post(GASTO, json=h.intencion(corriente), headers=h.AUTH))],
                    "L1_sin_contexto_sin_inversiones", inspeccion)
    assert salida["registro"].status_code == 200


def test_l2_transferencia_bloquea_las_cuentas_en_orden_de_id(t):
    owner, _, cli, corriente, ahorro = t
    menor, mayor = sorted([corriente, ahorro])
    barrera = _barrera_fila(owner, "SELECT id FROM gapto.cuentas WHERE id=%s FOR UPDATE", (mayor,))
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": "10.00", "moneda": "EUR", "fecha_hecho": "2026-09-24",
              "cuenta_origen_id": str(mayor), "cuenta_destino_id": str(menor)}

    def inspeccion(evid):
        menor_tomada = _nowait(owner, "SELECT id FROM gapto.cuentas WHERE id=%s FOR UPDATE", (menor,))
        assert menor_tomada, "la cuenta de menor id no estaba bloqueada mientras espera la de mayor id"
        return {"menor_bloqueada_mientras_espera_la_mayor": menor_tomada}

    salida = _serie(barrera, [("transferencia", lambda: cli.post(TRANSF, json=cuerpo, headers=h.AUTH))],
                    "L2_transferencia_orden_de_cuentas", inspeccion)
    assert salida["transferencia"].status_code == 200


# ------------------------------------------------------------------ L3 / L4 registro frente a desactivaciones
@pytest.mark.parametrize("primero", ["registro", "desactivar"])
def test_l3_registro_frente_a_desactivar_categoria(t, primero):
    owner, _, cli, corriente, _ = t
    cat = ph.categoria(owner, "Super")
    barrera = _barrera_fila(owner, "SELECT id FROM gapto.categorias_financieras WHERE id=%s FOR UPDATE", (cat,))
    cuerpo = h.intencion(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(cat)})
    pasos = {"registro": lambda: cli.post(GASTO, json=cuerpo, headers=h.AUTH),
             "desactivar": lambda: cli.post(f"/v1/categorias/{cat}/desactivar",
                                            json={"modo": "SOLO_SI_SIN_HIJOS_ACTIVOS", "row_version": 1},
                                            headers=h.AUTH)}
    segundo = "desactivar" if primero == "registro" else "registro"
    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"L3_categoria_{primero}")
    assert salida["desactivar"].status_code == 200
    if primero == "registro":
        assert salida["registro"].status_code == 200
    else:
        assert _cod(salida["registro"]) == "CATEGORIA_NO_ELEGIBLE"


@pytest.mark.parametrize("maestro", ["tercero", "contexto"])
@pytest.mark.parametrize("primero", ["registro", "desactivar"])
def test_l4_registro_frente_a_desactivar_tercero_o_contexto(t, maestro, primero):
    owner, _, cli, corriente, _ = t
    if maestro == "tercero":
        mid = _tercero(cli)[0]
        barrera = _barrera_fila(owner, "SELECT id FROM gapto.terceros WHERE id=%s FOR UPDATE", (mid,))
        cuerpo = h.intencion(corriente, tercero_id=str(mid))
        ruta, codigo = f"/v1/terceros/{mid}/desactivar", "TERCERO_NO_DISPONIBLE"
    else:
        mid = _contexto(cli)
        barrera = _barrera_fila(owner, "SELECT id FROM gapto.entidades WHERE id=%s FOR UPDATE", (mid,))
        cuerpo = h.intencion(corriente, contexto_id=str(mid))
        ruta, codigo = f"/v1/contextos/{mid}/desactivar", "CONTEXTO_NO_DISPONIBLE"
    pasos = {"registro": lambda: cli.post(GASTO, json=cuerpo, headers=h.AUTH),
             "desactivar": lambda: cli.post(ruta, json={"row_version": 1}, headers=h.AUTH)}
    segundo = "desactivar" if primero == "registro" else "registro"
    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"L4_{maestro}_{primero}")
    assert salida["desactivar"].status_code == 200
    if primero == "registro":
        assert salida["registro"].status_code == 200
    else:
        assert _cod(salida["registro"]) == codigo


# ------------------------------------------------------------------ L5 transferencia frente a capacidad / cuenta
@pytest.mark.parametrize("cambio", ["capacidad", "desactivar_cuenta"])
@pytest.mark.parametrize("primero", ["transferencia", "cambio"])
def test_l5_transferencia_frente_a_cambio_de_cuenta(t, cambio, primero):
    owner, _, cli, corriente, ahorro = t
    if cambio == "capacidad":
        # La barrera retiene la fila de capacidad: el registro la pide FOR SHARE
        # (bajo el lock de la cuenta) y la retirada la borra.
        barrera = _barrera_fila(owner, "SELECT id FROM gapto.cuenta_capacidades WHERE cuenta_id=%s "
                                       "AND capacidad_codigo='TRANSFERIR_ENTRADA' FOR UPDATE", (ahorro,))
        sql = "DELETE FROM gapto.cuenta_capacidades WHERE cuenta_id=%s AND capacidad_codigo='TRANSFERIR_ENTRADA'"
    else:
        barrera = _barrera_fila(owner, "SELECT id FROM gapto.cuentas WHERE id=%s FOR UPDATE", (ahorro,))
        sql = "UPDATE gapto.cuentas SET enabled=false WHERE id=%s"
    cuerpo = {"intencion_id": str(uuid.uuid4()), "importe": "10.00", "moneda": "EUR", "fecha_hecho": "2026-09-24",
              "cuenta_origen_id": str(corriente), "cuenta_destino_id": str(ahorro)}

    def aplicar_cambio():
        c = fh.sesion_owner(owner)
        try:
            c.execute(sql, (ahorro,))
            c.execute("COMMIT")
            return "OK"
        finally:
            c.close()

    pasos = {"transferencia": lambda: cli.post(TRANSF, json=cuerpo, headers=h.AUTH), "cambio": aplicar_cambio}
    segundo = "cambio" if primero == "transferencia" else "transferencia"
    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"L5_{cambio}_{primero}")
    assert salida["cambio"] == "OK"
    if primero == "transferencia":
        assert salida["transferencia"].status_code == 200
    else:
        assert _cod(salida["transferencia"]) == "CUENTA_DESCONOCIDA"


# ------------------------------------------------------------------ L6 terceros homonimos
@pytest.mark.parametrize("primero", ["A", "B"])
def test_l6_dos_altas_de_tercero_mismo_nombre(t, primero):
    owner, _, cli, _, _ = t
    barrera = _barrera_advisory(owner, "TERCEROS")
    pasos = {"A": lambda: _tercero(cli, "Mercadona")[1], "B": lambda: _tercero(cli, " MERCADONA ")[1]}
    segundo = "B" if primero == "A" else "A"
    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"L6_terceros_{primero}")
    assert salida["A"].status_code == salida["B"].status_code == 200
    assert len(cli.get("/v1/terceros/candidatos", params={"nombre": "mercadona"},
                       headers=h.AUTH).json()["terceros"]) == 2


# ------------------------------------------------------------------ L7 plantillas y accesos
def _plantilla(cli, owner, nombre, pid=None):
    pid = pid or uuid.uuid4()
    r = cli.post("/v1/plantillas", json={"id": str(pid), "nombre": nombre, "tipo_hecho_id": str(ph.tipo_gasto(owner)),
                                         "presupuestable_default": True}, headers=h.AUTH)
    return pid, r


@pytest.mark.parametrize("primero", ["A", "B"])
def test_l7_dos_altas_de_plantilla_mismo_nombre(t, primero):
    owner, _, cli, _, _ = t
    ids = {"A": uuid.uuid4(), "B": uuid.uuid4()}
    barrera = _barrera_advisory(owner, "PLANTILLAS")
    pasos = {"A": lambda: _plantilla(cli, owner, "Súper semanal", ids["A"])[1],
             "B": lambda: _plantilla(cli, owner, "SUPER  semanal", ids["B"])[1]}
    segundo = "B" if primero == "A" else "A"
    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"L7_nombre_{primero}")
    assert salida[primero].status_code == 200
    assert _cod(salida[segundo]) == "PLANTILLA_NOMBRE_REPETIDO"
    assert salida[segundo].json()["detalle"] == {"plantilla_id": str(ids[primero])}


@pytest.mark.parametrize("primero", ["acceso", "desactivar"])
def test_l7_alta_de_acceso_frente_a_desactivar_plantilla(t, primero):
    owner, _, cli, _, _ = t
    pid, _ = _plantilla(cli, owner, "P")
    aid = uuid.uuid4()
    barrera = _barrera_advisory(owner, "PLANTILLAS")
    pasos = {"acceso": lambda: cli.post("/v1/acciones-rapidas", json={"id": str(aid), "plantilla_registro_id": str(pid),
                                                                      "nombre": "P"}, headers=h.AUTH),
             "desactivar": lambda: cli.post(f"/v1/plantillas/{pid}/desactivar", json={"row_version": 1},
                                            headers=h.AUTH)}
    segundo = "desactivar" if primero == "acceso" else "acceso"
    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"L7_acceso_{primero}")
    assert salida["desactivar"].status_code == 200
    if primero == "acceso":
        assert salida["acceso"].status_code == 200
        assert h.leer(owner, "SELECT enabled FROM gapto.acciones_rapidas WHERE id=%s", (aid,)) == [(False,)]
    else:
        assert _cod(salida["acceso"]) == "ACCION_PLANTILLA_NO_DISPONIBLE"


def test_l7_dos_reordenaciones(t):
    owner, _, cli, _, _ = t
    acciones = []
    for i in range(3):
        pid, _ = _plantilla(cli, owner, f"P{i}")
        aid = uuid.uuid4()
        assert cli.post("/v1/acciones-rapidas", json={"id": str(aid), "plantilla_registro_id": str(pid),
                                                      "nombre": f"A{i}"}, headers=h.AUTH).status_code == 200
        acciones.append(aid)
    barrera = _barrera_advisory(owner, "PLANTILLAS")
    uno = {"acciones": [{"id": str(a), "row_version": 1} for a in reversed(acciones)]}
    dos = {"acciones": [{"id": str(a), "row_version": 1} for a in acciones[1:] + acciones[:1]]}
    pasos = [("primera", lambda: cli.post("/v1/acciones-rapidas/reordenar", json=uno, headers=h.AUTH)),
             ("segunda", lambda: cli.post("/v1/acciones-rapidas/reordenar", json=dos, headers=h.AUTH))]
    salida = _serie(barrera, pasos, "L7_dos_reordenaciones")
    assert salida["primera"].status_code == 200
    assert _cod(salida["segunda"]) == "VERSION_DESFASADA"


# ------------------------------------------------------------------ L8 onboarding frente a alta manual
@pytest.mark.parametrize("primero", ["onboarding", "manual"])
def test_l8_onboarding_frente_a_alta_manual(t, primero):
    owner, _, cli, _, _ = t
    barrera = _barrera_advisory(owner, "CATEGORIAS")
    manual = {"id": str(uuid.uuid4()), "nombre": "Mía", "parent_id": None, "ambito": "GASTO",
              "presupuestable_default": True}
    pasos = {"onboarding": lambda: cli.post("/v1/categorias/onboarding", headers=h.AUTH),
             "manual": lambda: cli.post("/v1/categorias", json=manual, headers=h.AUTH)}
    segundo = "manual" if primero == "onboarding" else "onboarding"
    salida = _serie(barrera, [(primero, pasos[primero]), (segundo, pasos[segundo])], f"L8_onboarding_{primero}")
    assert salida["manual"].status_code == 200
    n = h.leer(owner, "SELECT count(*) FROM gapto.categorias_financieras")[0][0]
    if primero == "onboarding":
        assert salida["onboarding"].json()["creadas"] == 93 and n == 94
    else:
        assert _cod(salida["onboarding"]) == "ONBOARDING_NO_APLICABLE" and n == 1


# ------------------------------------------------------------------ L9 ordenes opuestos y 40P01
def test_l9_ordenes_opuestos_y_reintento_completo_ante_40p01(t):
    """El registro toma cuenta -> tercero (FOR SHARE); otra sesion toma
    tercero -> cuenta. El interbloqueo se resuelve con 40P01 para una de las
    dos; si la victima es el registro, la UdT reintenta la transaccion
    COMPLETA y no deja nada parcial."""
    from app.api.dto_vs01 import IntencionGastoPagado
    from app.api.ejecucion_gasto_pagado import registrar_gasto_pagado
    from app.core.contexto import ContextoOperacion

    owner, _, cli, corriente, _ = t
    ter = _tercero(cli)[0]
    x = _barrera_fila(owner, "SELECT id FROM gapto.terceros WHERE id=%s FOR UPDATE", (ter,))
    intencion = IntencionGastoPagado.model_validate(h.intencion(corriente, tercero_id=str(ter)))
    unidad = fh.unidad()
    salida: dict = {}

    class ConTraza:
        """Envoltorio de la UdT que anota los intentos (retry completo)."""

        def ejecutar(self, c, op, nombre="x"):
            r = unidad.ejecutar_con_traza(c, op, nombre=nombre)
            salida["intentos"] = r.traza.intentos_realizados
            return r.valor

    def registrar():
        ctx = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
        try:
            salida["registro"] = registrar_gasto_pagado(ConTraza(), ctx, intencion)
        except Exception as exc:  # se afirma despues
            salida["error"] = repr(exc)

    hilo = threading.Thread(target=registrar)
    hilo.start()
    assert _bloqueados(fh.pid_servidor(x), 1), "el registro no llego a esperar el tercero"
    victima_externa = False
    try:
        x.execute("SELECT id FROM gapto.cuentas WHERE id=%s FOR UPDATE", (corriente,))
        x.execute("COMMIT")
    except psycopg.errors.DeadlockDetected:
        victima_externa = True
        x.rollback()
    finally:
        x.close()
    hilo.join(timeout=30)
    assert not hilo.is_alive()
    hid = intencion.intencion_id
    assert h.leer(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id=%s", (hid,))[0][0] == 1
    assert h.leer(owner, "SELECT count(*) FROM gapto.hecho_terceros WHERE hecho_id=%s", (hid,))[0][0] == 1
    assert victima_externa or salida.get("intentos", 1) >= 2
    _evidencia("L9_40P01", {"victima_externa": victima_externa, "intentos_registro": salida.get("intentos")})
