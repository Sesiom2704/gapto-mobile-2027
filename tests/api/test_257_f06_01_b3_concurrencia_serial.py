# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_257_f06_01_b3_concurrencia_serial.py
# Ruta: tests/api/test_257_f06_01_b3_concurrencia_serial.py
# Descripcion: F06 T1-F06 · B3 N1 · bateria SERIAL y determinista con COMMIT real (WM §13.3.7; R1 v0.9.5 §III.3.6
#   y Parte IV-bis §4; oraculos v0.7 O7 y B.1/B.2), FUERA de la suite general: solo con GAPTO_B3_CONCURRENCIA=1
#   (base desechable). Barreras externas que retienen el recurso que el escenario necesita (HF-18): la fila de la
#   propiedad en NK, la fila del hecho o el advisory de la raiz de OP-22. pg_locks y pg_stat_database.deadlocks;
#   JSON por caso si GAPTO_B3_EVIDENCIA apunta a una carpeta. Sin 40P01 en ningun caso.
#     O7.2-A (S6′-A) C-MEJ-03 || OP-21 generico que CONSERVA efecto_id (importe), en los dos ordenes: el primero OK,
#            el segundo VERSION_DESFASADA. S6′-B (O7.2-B-S/B-R con OP-21 real) NO se ejecuta: dependencia
#            identificada (decision de Moises S6B nº 1; Parte IV-bis §4).
#     O7.3 (S9)  C-MEJ-03 || reintento de la alta C-MEJ-01: alta primero -> idempotente; C-MEJ-03 primero ->
#            IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
#     O7.4 (S10) C-MEJ-03 || OP-21P (correccion del pago del mismo hecho): sin 40P01.
#     O7.5 (S11) C-MEJ-03 || deshabilitar la propiedad: o entra antes, o PROPIEDAD_NO_DISPONIBLE.
#     O7.6 (S12) C-MEJ-03 || C-PROP-03 (cambio de titularidad): los dos OK; atribuciones copiadas = las de antes.
#     O7.7-A/B (S13-A/B) dos C-MEJ-03 identicas (una idempotente) o con la misma intencion y otro contenido
#            (INTENCION_CORRECCION_NO_VIGENTE); un solo e1 y una sola tanda de auditoria.
#     O7.8 literal (S14) C-MEJ-03 (reparacion -> MEJORA) || C-PROP-05 (MEJORAS con la huella previa), C-PROP-05
#            ejercitado con los consumidores activados SOLO en el test: C-MEJ-03 primero -> COMPLETITUD_VISTA_
#            DESFASADA; C-PROP-05 primero -> 200 y lectura PARCIAL DECLARACION_DESACTUALIZADA.
#     O7.9 (S15) OP-03 anula un componente de C-MEJ-02 || C-PROP-05 que lo incluye: PARCIAL tras la relectura.
#     S16/S17 (O11.9/O11.10) dos C-PROP-05 de MEJORAS con componentes de B3: identica -> idempotente; otro corte ->
#            IDENTIDAD_REUTILIZADA.
#     C-MEJ-01 || C-PROP-03 (titularidad en la fecha del hecho): C-PROP-03 primero -> ATRIBUCION_PROPUESTA_
#            DESFASADA; C-MEJ-01 primero -> los dos 200.
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import pathlib
import uuid

import psycopg
import pytest

import f06_01_b1_helpers as b
import f06_01_b2_helpers as c2
import f06_01_b3_helpers as b3
import vs01_api_helpers as h
from app.core.contexto import ContextoOperacion
from test_237_f06_01_b1r_intencion_concurrente_serial import (BarreraNK, cliente, deadlocks, en_hilo,
                                                              esperar_bloqueado, foto_locks, unidad)

ORDENES = ["A-primero", "B-primero"]
NO_VIGENTE = "INTENCION_CORRECCION_NO_VIGENTE"
REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_B3_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_B3_CONCURRENCIA=1)")


def evidencia(nombre: str, datos) -> None:
    carpeta = os.getenv("GAPTO_B3_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False), encoding="utf-8")


class BarreraHecho:
    """Conexion de control que retiene la fila del hecho (FOR UPDATE) hasta `soltar`."""

    def __init__(self, hecho_id):
        self.c = psycopg.connect(h.dsn(), autocommit=False)
        self.c.execute("SELECT 1 FROM gapto.hechos_financieros WHERE id = %s FOR UPDATE", (hecho_id,))

    def soltar(self):
        self.c.commit()
        self.c.close()


class BarreraRaiz:
    """Conexion de control que retiene el advisory de la raiz de OP-22 del hecho hasta `soltar`."""

    def __init__(self, hecho_id):
        self.c = psycopg.connect(h.dsn(), autocommit=False)
        self.c.execute("SELECT pg_advisory_xact_lock(hashtext('gapto:OP22'), hashtext(%s::uuid::text))", (hecho_id,))

    def soltar(self):
        self.c.commit()
        self.c.close()


def _correr(fa, fb, barrera, nombre_a="b1r_A", nombre_b="b1r_B"):
    d0 = deadlocks()
    try:
        ta, ra = en_hilo(fa)
        esperar_bloqueado(nombre_a)
        tb, rb = en_hilo(fb)
        esperar_bloqueado(nombre_b)
        locks = foto_locks()
    finally:
        barrera.soltar()
    ta.join(90)
    tb.join(90)
    vivos = [n for n, t in (("A", ta), ("B", tb)) if t.is_alive()]
    return ra, rb, {"deadlocks_nuevos": deadlocks() - d0, "vivos": vivos, "pg_locks": locks,
                    "esperas": [f for f in locks if not f[3]]}


def _http(salida: dict):
    assert "e" not in salida, salida
    r = salida["r"]
    j = r.json()
    return r.status_code, j.get("codigo"), j.get("idempotente")


def _servicio(salida: dict):
    if "e" in salida:
        texto = salida["e"]
        for codigo in ("VERSION_DESFASADA", "CONFLICTO_CONCURRENCIA", "AGREGADO_NO_ENCONTRADO",
                       "CORRECCION_AGREGADA_REQUERIDA"):
            if codigo in texto:
                return ("ERROR", codigo)
        return ("ERROR", texto)
    return ("OK", None)


def _ctx(owner):
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


def _op21_importe(lab, hid, nombre: str, importe: str):
    """OP-21 generico por servicio (no hay ruta: PROPIEDAD reservada) que conserva efecto_id."""
    from app.patrimonio.atribucion import repartir
    from app.services.correcciones_service import CorreccionesService, DatosCorreccion
    e0 = lab.efectos(hid)[0][0]
    atrs = lab.sql("SELECT id, porcentaje_aplicado FROM gapto.efecto_atribuciones WHERE efecto_id = %s", (e0,))
    nuevo = decimal.Decimal(importe)
    reparto = repartir(nuevo, [(a, p) for a, p in atrs]) if atrs else {}
    datos = DatosCorreccion(hecho_id=uuid.UUID(hid), row_version_esperada=lab.hecho(hid)[1], motivo="S6′-A",
                            efectos_a_actualizar={e0: {"importe_delta": nuevo}},
                            atribuciones_a_actualizar={a: {"importe_atribuido": reparto[a]} for a, _ in atrs})
    servicio = CorreccionesService(unidad(nombre))
    return lambda: servicio.corregir(_ctx(lab.owner), datos)


def _mejora(lab, fecha="2026-02-10", importe="8500.00") -> str:
    c = lab.cuerpo(clase="MEJORA", importe=importe, fecha=fecha)
    lab.ok(c)
    return c["intencion_id"]


def _reparacion(lab, fecha="2026-01-15", importe="300.00") -> str:
    c = lab.cuerpo(clase="REPARACION", importe=importe, fecha=fecha)
    lab.ok(c)
    return c["intencion_id"]


# ================================================================== O7.2-A (S6′-A)
@pytest.mark.parametrize("orden", ORDENES)
def test_o7_2_a_cmej03_frente_a_op21_que_conserva_el_efecto(orden):
    lab = b3.Lab()
    hid = _reparacion(lab)
    cuerpo = lab.correccion(hid, "MEJORA")
    ca = cliente(lab.owner, "b1r_A")
    cb = cliente(lab.owner, "b1r_B")
    barrera = BarreraHecho(hid)
    if orden == "A-primero":   # C-MEJ-03 primero
        ra, rb, traza = _correr(lambda: lab.corregir(hid, cuerpo, cli=ca), _op21_importe(lab, hid, "b1r_B", "320.00"),
                                barrera)
        cm, op = _http(ra), _servicio(rb)
        esperado = ((200, None, False), ("ERROR", "VERSION_DESFASADA"))
    else:
        ra, rb, traza = _correr(_op21_importe(lab, hid, "b1r_A", "320.00"), lambda: lab.corregir(hid, cuerpo, cli=cb),
                                barrera)
        op, cm = _servicio(ra), _http(rb)
        esperado = ((409, "VERSION_DESFASADA", None), ("OK", None))
    datos = {"orden": orden, "cmej03": cm, "op21": op, **traza}
    evidencia(f"O7_2_A_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert (cm, op) == esperado, datos


# ================================================================== O7.3 (S9)
@pytest.mark.parametrize("orden", ORDENES)
def test_o7_3_cmej03_frente_al_reintento_de_la_alta(orden):
    lab = b3.Lab()
    alta = lab.cuerpo(clase="MEJORA", importe="8500.00", fecha="2026-02-10")
    lab.ok(alta)
    hid = alta["intencion_id"]
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraRaiz(hid)
    if orden == "A-primero":   # reintento de la alta primero
        ra, rb, traza = _correr(lambda: lab.registrar(alta, ca), lambda: lab.corregir(hid, cuerpo, cli=cb), barrera)
        reintento, cm = _http(ra), _http(rb)
        esperado = ((200, None, True), (200, None, False))
    else:
        ra, rb, traza = _correr(lambda: lab.corregir(hid, cuerpo, cli=ca), lambda: lab.registrar(alta, cb), barrera)
        cm, reintento = _http(ra), _http(rb)
        esperado = ((409, REUTILIZADA, None), (200, None, False))
    datos = {"orden": orden, "reintento": reintento, "cmej03": cm, **traza}
    evidencia(f"O7_3_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert (reintento, cm) == esperado, datos


# ================================================================== O7.4 (S10)
@pytest.mark.parametrize("orden", ORDENES)
def test_o7_4_cmej03_frente_a_op21p_del_mismo_hecho(orden):
    from app.services.correccion_tesoreria_service import CorreccionTesoreriaService, DatosCorreccionPago
    lab = b3.Lab()
    hid = _reparacion(lab)
    cuerpo = lab.correccion(hid, "MEJORA")
    c3 = h.crear_cuenta(lab.owner, [(lab.actor, 100)])
    mov_v = lab.sql("SELECT m.row_version FROM gapto.hecho_movimientos_tesoreria x JOIN gapto.movimientos_tesoreria m "
                    "ON m.id = x.movimiento_tesoreria_id WHERE x.hecho_id = %s", (hid,))[0][0]
    datos_pago = DatosCorreccionPago(hecho_id=uuid.UUID(hid), row_version_esperada=lab.hecho(hid)[1],
                                     movimiento_row_version_esperada=mov_v, motivo="S10", error_de_registro=True,
                                     cuenta_id=c3)

    def op21p(nombre):
        from app.services.previsiones_service import conjunto_impacto_correccion_ancla, impacto_correccion_ancla
        servicio = CorreccionTesoreriaService(unidad(nombre), impacto_ancla=impacto_correccion_ancla,
                                              conjunto_impacto=conjunto_impacto_correccion_ancla)
        return lambda: servicio.corregir_pago(_ctx(lab.owner), datos_pago)
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraHecho(hid)
    if orden == "A-primero":
        ra, rb, traza = _correr(lambda: lab.corregir(hid, cuerpo, cli=ca), op21p("b1r_B"), barrera)
        cm, op = _http(ra), _servicio(rb)
    else:
        ra, rb, traza = _correr(op21p("b1r_A"), lambda: lab.corregir(hid, cuerpo, cli=cb), barrera)
        op, cm = _servicio(ra), _http(rb)
    datos = {"orden": orden, "cmej03": cm, "op21p": op, **traza}
    evidencia(f"O7_4_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert "40P01" not in repr((cm, op)) and "deadlock detected" not in repr((cm, op)), datos
    if orden == "A-primero":   # tras C-MEJ-03 el hecho es MEJORA: OP-21P rechaza sin escribir
        assert cm == (200, None, False) and op in (("ERROR", "VERSION_DESFASADA"),
                                                   ("ERROR", "CORRECCION_AGREGADA_REQUERIDA")), datos
    else:
        assert op[0] == "OK" and cm == (409, "VERSION_DESFASADA", None), datos


# ================================================================== O7.5 (S11)
def test_o7_5_cmej03_frente_a_deshabilitar_la_propiedad():
    lab = b3.Lab()
    hid = _reparacion(lab)
    cuerpo = lab.correccion(hid, "MEJORA")
    ca = cliente(lab.owner, "b1r_A")
    # la deshabilitacion (fixture declarado como gapto_owner) retiene la entidad hasta confirmar
    c = psycopg.connect(h.dsn(), autocommit=False)
    c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(lab.owner),))
    c.execute("SET LOCAL ROLE gapto_owner")
    c.execute("UPDATE gapto.entidades SET enabled = false WHERE id = %s", (lab.pid,))
    d0 = deadlocks()
    t, r = en_hilo(lambda: lab.corregir(hid, cuerpo, cli=ca))
    esperar_bloqueado("b1r_A")
    c.commit()
    c.close()
    t.join(60)
    salida = _http(r)
    datos = {"cmej03": salida, "deadlocks_nuevos": deadlocks() - d0}
    evidencia("O7_5", datos)
    assert datos["deadlocks_nuevos"] == 0 and salida == (409, "PROPIEDAD_NO_DISPONIBLE", None), datos


# ================================================================== O7.6 (S12) y C-MEJ-03 || C-PROP-03
@pytest.mark.parametrize("orden", ORDENES)
def test_o7_6_cmej03_frente_a_cambio_de_titularidad(orden):
    lab = b3.Lab(cambio=False)
    hid = _mejora(lab)
    e0 = lab.efectos(hid)[0][0]
    antes = lab.sql("SELECT actor_id, importe_atribuido::text FROM gapto.efecto_atribuciones WHERE efecto_id = %s "
                    "ORDER BY actor_id", (e0,))
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    cambio = b.cambio(b.leer(lab.cli, lab.pid), b.solo_mia(desde=b.HOY))
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraNK(lab.pid)
    f_cm = lambda cli: lambda: lab.corregir(hid, cuerpo, cli=cli)                                   # noqa: E731
    f_tit = lambda cli: lambda: b.post(cli, f"/v1/propiedades/{lab.pid}/titularidad", cambio)       # noqa: E731
    if orden == "A-primero":
        ra, rb, traza = _correr(f_cm(ca), f_tit(cb), barrera)
        cm, tit = _http(ra), _http(rb)
    else:
        ra, rb, traza = _correr(f_tit(ca), f_cm(cb), barrera)
        tit, cm = _http(ra), _http(rb)
    e1 = lab.efectos(hid)[0][0]
    despues = lab.sql("SELECT actor_id, importe_atribuido::text FROM gapto.efecto_atribuciones WHERE efecto_id = %s "
                      "ORDER BY actor_id", (e1,))
    datos = {"orden": orden, "cmej03": cm, "titularidad": tit, "antes": antes, "despues": despues, **traza}
    evidencia(f"O7_6_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert cm == (200, None, False) and tit[0] == 200, datos
    assert despues == antes and e1 != e0, datos                                  # no se reatribuye (M-2)


# ================================================================== O7.7-A/B (S13-A/B)
@pytest.mark.parametrize("variante", ["identica", "otro_contenido"])
def test_o7_7_dos_cmej03_con_la_misma_intencion(variante):
    lab = b3.Lab()
    hid = _mejora(lab)
    cuerpo = lab.correccion(hid, "REPARACION", presupuestable=True)
    otro = cuerpo if variante == "identica" else {**cuerpo, "motivo": "otro motivo"}
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraRaiz(hid)
    ra, rb, traza = _correr(lambda: lab.corregir(hid, cuerpo, cli=ca), lambda: lab.corregir(hid, otro, cli=cb),
                            barrera)
    a, bb = _http(ra), _http(rb)
    auds = len(b3.auditorias(lab.owner, cuerpo["intencion_id"]))
    datos = {"variante": variante, "A": a, "B": bb, "auditorias": auds, "efectos": lab.efectos(hid), **traza}
    evidencia(f"O7_7_{variante}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert a == (200, None, False), datos
    assert bb == ((200, None, True) if variante == "identica" else (409, NO_VIGENTE, None)), datos
    assert len(lab.efectos(hid)) == 1 and auds == 9, datos                         # una sola tanda (O5.1: 9 filas)


# ================================================================== O7.8 literal (S14)
def _declarar_mejoras(lab, cli, huella, corte="2026-06-30", intencion=None, version=None):
    return cli.post(f"/v1/propiedades/{lab.pid}/completitud", json={
        "intencion_id": str(intencion or uuid.uuid4()),
        "row_version_esperada": lab.version_propiedad() if version is None else version, "ambito": "MEJORAS",
        "completo": True, "fecha_corte": corte, "huella_conjunto_vista": huella}, headers=h.AUTH)


def _huella_mejoras(lab, corte="2026-06-30") -> str:
    return b2_coste(lab, corte)["MEJORAS"]["huella_conjunto"]


def b2_coste(lab, a_fecha):
    return c2.leer_coste(lab.cli, lab.pid, a_fecha)


@pytest.mark.parametrize("orden", ORDENES)
def test_o7_8_literal_cmej03_frente_a_c_prop_05(monkeypatch, orden):
    c2.habilitar_0352(monkeypatch)
    lab = b3.Lab()
    _mejora(lab)
    rep = _reparacion(lab)
    cuerpo = lab.correccion(rep, "MEJORA")
    huella = _huella_mejoras(lab)
    version = lab.version_propiedad()
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraNK(lab.pid)
    f_cm = lambda cli: lambda: lab.corregir(rep, cuerpo, cli=cli)                                    # noqa: E731
    f_decl = lambda cli: lambda: _declarar_mejoras(lab, cli, huella, version=version)               # noqa: E731
    if orden == "A-primero":   # C-MEJ-03 primero
        ra, rb, traza = _correr(f_cm(ca), f_decl(cb), barrera)
        cm, decl = _http(ra), _http(rb)
    else:
        ra, rb, traza = _correr(f_decl(ca), f_cm(cb), barrera)
        decl, cm = _http(ra), _http(rb)
    coste = c2.leer_coste(lab.cli, lab.pid)["MEJORAS"]
    datos = {"orden": orden, "cmej03": cm, "declaracion": decl, "coste": coste, **traza}
    evidencia(f"O7_8_literal_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert cm == (200, None, False), datos
    if orden == "A-primero":
        assert decl == (409, "COMPLETITUD_VISTA_DESFASADA", None), datos
        assert coste["motivo_estado"] == "SIN_DECLARACION", datos
    else:
        assert decl[0] == 200, datos
        assert (coste["estado"], coste["motivo_estado"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA"), datos


# ================================================================== O7.9 (S15)
def test_o7_9_op03_anula_componente_de_c_mej_02_frente_a_c_prop_05(monkeypatch):
    c2.habilitar_0352(monkeypatch)
    lab = b3.Lab()
    mh = lab.cuerpo_mh(fecha="2026-02-10")
    assert lab.mejora_historica(mh).status_code == 200
    huella = _huella_mejoras(lab)
    version = lab.version_propiedad()
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla
    hid = uuid.UUID(mh["intencion_id"])
    v = lab.hecho(hid)[1]
    servicio = HechosService(unidad("b1r_A"), impacto_ancla=impacto_correccion_ancla)
    cb = cliente(lab.owner, "b1r_B")
    barrera = BarreraHecho(hid)
    d0 = deadlocks()
    try:
        ta, ra = en_hilo(lambda: servicio.anular_hecho(_ctx(lab.owner), hecho_id=hid, row_version_esperada=v,
                                                       motivo_anulacion="S15"))
        esperar_bloqueado("b1r_A")
        tb, rb = en_hilo(lambda: _declarar_mejoras(lab, cb, huella, version=version))
        tb.join(60)
    finally:
        barrera.soltar()
    ta.join(60)
    decl = _http(rb)
    op03 = _servicio(ra)
    coste = c2.leer_coste(lab.cli, lab.pid)["MEJORAS"]
    datos = {"declaracion": decl, "op03": op03, "coste": coste, "deadlocks_nuevos": deadlocks() - d0}
    evidencia("O7_9", datos)
    assert datos["deadlocks_nuevos"] == 0 and decl[0] == 200 and op03 == ("OK", None), datos
    assert (coste["estado"], coste["motivo_estado"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA"), datos


# ================================================================== S16/S17 (O11.9/O11.10) con componentes de B3
@pytest.mark.parametrize("variante", ["identica", "otro_corte"])
def test_s16_s17_dos_c_prop_05_de_mejoras_con_componentes_de_b3(monkeypatch, variante):
    c2.habilitar_0352(monkeypatch)
    lab = b3.Lab()
    _mejora(lab)
    huella = _huella_mejoras(lab)
    huella_b = huella if variante == "identica" else _huella_mejoras(lab, "2026-07-31")
    version = lab.version_propiedad()
    intencion = uuid.uuid4()
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraNK(lab.pid)
    corte_b = "2026-06-30" if variante == "identica" else "2026-07-31"
    ra, rb, traza = _correr(lambda: _declarar_mejoras(lab, ca, huella, intencion=intencion, version=version),
                            lambda: _declarar_mejoras(lab, cb, huella_b, corte=corte_b, intencion=intencion,
                                                      version=version), barrera)
    a, bb = _http(ra), _http(rb)
    datos = {"variante": variante, "A": a, "B": bb, **traza}
    evidencia(f"S16_S17_{variante}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert a == (200, None, False), datos
    assert bb == ((200, None, True) if variante == "identica" else (409, REUTILIZADA, None)), datos


# ================================================================== C-MEJ-01 || C-PROP-03
@pytest.mark.parametrize("orden", ORDENES)
def test_cmej01_frente_a_cambio_de_titularidad_en_la_fecha_del_hecho(orden):
    lab = b3.Lab(cambio=False)
    cuerpo = lab.cuerpo(fecha=b.HOY)                       # propuesta YO 50 / T 50 en HOY
    cambio = b.cambio(b.leer(lab.cli, lab.pid), b.solo_mia(desde=b.HOY))
    ca, cb = cliente(lab.owner, "b1r_A"), cliente(lab.owner, "b1r_B")
    barrera = BarreraNK(lab.pid)
    f_g = lambda cli: lambda: lab.registrar(cuerpo, cli)                                           # noqa: E731
    f_t = lambda cli: lambda: b.post(cli, f"/v1/propiedades/{lab.pid}/titularidad", cambio)        # noqa: E731
    if orden == "A-primero":   # C-PROP-03 primero
        ra, rb, traza = _correr(f_t(ca), f_g(cb), barrera)
        tit, gasto = _http(ra), _http(rb)
        esperado = (200, (409, "ATRIBUCION_PROPUESTA_DESFASADA", None))
    else:
        ra, rb, traza = _correr(f_g(ca), f_t(cb), barrera)
        gasto, tit = _http(ra), _http(rb)
        esperado = (200, (200, None, False))
    datos = {"orden": orden, "gasto": gasto, "titularidad": tit, **traza}
    evidencia(f"CMEJ01_CPROP03_{orden}", datos)
    assert traza["deadlocks_nuevos"] == 0 and traza["vivos"] == [], datos
    assert (tit[0], gasto) == esperado, datos
