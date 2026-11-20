# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_283_f06_t2_a3_0352_oraculos.py
# Ruta: tests/api/test_283_f06_t2_a3_0352_oraculos.py
# Descripcion: F06 T2-F06 · A3-0352 N1 (habilitacion de los consumidores de 0352; L-05; contrato A3-0352 v1.1). Oraculos
#   por HTTP y por llamada directa, como gapto_runtime con RLS, SIN forzar el interruptor (estado del repositorio):
#   - O-A3-R15-01..11 (incluidos 02c y 10a-d; R15-a, fila 2 bis de L-COSTE y lectura L2 con su reintento y
#     agotamiento). O-A3-R15-11 (interruptor apagado) vive en test_252 (O10.29-H (c)), unico sitio con
#     deshabilitar_0352.
#   - O-A3-R15-INV (P-L2-1..5): inventario estatico cerrado de los escritores de gapto.propiedades (fecha y terna) y de
#     gapto.entidades.row_version en backend/app y en el catalogo de la base, y prueba dinamica de row_version + 1 en
#     el MISMO COMMIT de cada escritor sin estado intermedio visible.
#   - O-A3-INV (ningun test fuerza True; deshabilitar_0352 solo en la variante «apagado»), O-A3-B1 (propiedades/ con
#     el SHA del HEAD de inicio), O-A3-TXT (texto del rechazo y motivos de L-COSTE iguales en servidor y cliente) y
#     O-A3-T2 (consumidores tras B1-R, PAG y CAT-VIV).
#   Exige GAPTO_TEST_DATABASE_URL (base desechable; estos tests confirman filas).
# Version: 0.1.0 (F06 T2-F06 A3-0352 N1)
# Version: 0.1.1 (F06 T3-F06 bloque 3 F06-02/03, paso 8; L-06-T3 del mandato v1.2 §5, añadido en el handoff, solo
#   test_o_a3_r15_inv_estatico_escritores_cerrados): P-L2-5 admite los UPDATE del nombre de contrato y de servicio
#   (contratos/repositorio.py, C-CON-02 y C-SRV-02), cerrados por funcion; el nombre solo llega por `editar`, que sube
#   la version despues de escribir, y el resto de llamadas pasan un dict literal sin «nombre». Lo de propiedades no cambia.
# ============================================================

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import pathlib
import re
import uuid

import psycopg
import pytest

import f06_01_b1_helpers as b
import f06_01_b2_helpers as c2
import f06_01_b3_helpers as b3
import vs01_api_helpers as h
from app.patrimonio import completitud as compl
from app.patrimonio import coste as coste_mod
from app.patrimonio import habilitacion
from app.patrimonio import rutas
from app.propiedades import repositorio as repo

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SIN_FECHA = "COMPLETITUD_SIN_FECHA_DE_ADQUISICION"
MENSAJE = "Para marcar el coste como completo, indica antes la fecha de adquisición de la propiedad."
REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
HOY = dt.date.fromisoformat(b.HOY)


def _ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def _rechazo(r, status: int, codigo: str):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text


def _terna(lab) -> tuple:
    return lab.sql("SELECT coste_adquisicion_declarado_completo, coste_adquisicion_declarado_en::text, "
                   "coste_adquisicion_conjunto_declarado::text FROM gapto.propiedades WHERE entidad_id = %s",
                   (lab.pid,))[0]


def _editar(lab, **campos):
    return b.post(lab.cli, f"/v1/propiedades/{lab.pid}/editar",
                  {"intencion_id": str(uuid.uuid4()), "row_version_esperada": lab.version(), **campos})


def _borrar_fecha(lab):
    j = _ok(_editar(lab, fecha_adquisicion=None))
    assert j["propiedad"]["fecha_adquisicion"] is None
    return j


def _huella(lab, a_fecha: str | None = None) -> str:
    return lab.coste(a_fecha)["ADQUISICION"]["huella_conjunto"]


def _declarada(fecha: str | None = c2.ESCRITURA):
    """O2′ comprado SIN declaracion y despues declarado completo por C-PROP-05 (corte 2026-03-20)."""
    lab = c2.Lab(fecha_adquisicion=fecha)
    _ok(lab.compra(lab.peticion()))
    _ok(lab.declarar("ADQUISICION", True, c2.CORTE, _huella(lab, c2.CORTE)))
    return lab


def _sin_fecha_comprada():
    lab = c2.Lab(fecha_adquisicion=None)
    _ok(lab.compra(lab.peticion()))
    return lab


# ================================================================== O-A3-R15-01
def test_o_a3_r15_01_c_prop_05_sin_fecha_422_sin_escribir():
    lab = _sin_fecha_comprada()
    huella = _huella(lab, c2.CORTE)
    antes, rv = c2.huella(), lab.version()
    _rechazo(lab.declarar("ADQUISICION", True, c2.CORTE, huella), 422, SIN_FECHA)
    assert r_mensaje(lab.declarar("ADQUISICION", True, c2.CORTE, huella)) == MENSAJE
    r = c2.unidad().ejecutar(c2.ctx(lab.owner), lambda s: compl.declarar(
        s, propiedad_id=uuid.UUID(lab.pid), intencion_id=uuid.uuid4(), row_version=rv, ambito="ADQUISICION",
        completo=True, fecha_corte=dt.date.fromisoformat(c2.CORTE), huella_vista=huella))
    assert isinstance(r, compl.Rechazo) and r.codigo == SIN_FECHA
    assert c2.huella() == antes and lab.version() == rv and _terna(lab) == (None, None, None)


def r_mensaje(r) -> str:
    assert r.status_code == 422, r.text
    return r.json()["mensaje"]


# ================================================================== O-A3-R15-02 (precedencia en C-PROP-05)
def test_o_a3_r15_02_precedencia_en_c_prop_05():
    lab = _sin_fecha_comprada()
    huella, rv = _huella(lab, c2.CORTE), lab.version()
    antes = c2.huella()
    # gana el corte futuro (capa, antes del lock)
    _rechazo(lab.declarar("ADQUISICION", True, "2026-12-01", huella), 422, "COMPLETITUD_SIN_FECHA_DE_CORTE")
    # gana el NK
    r = lab.cli.post(f"/v1/propiedades/{uuid.uuid4()}/completitud", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version_esperada": rv, "ambito": "ADQUISICION", "completo": True,
        "fecha_corte": c2.CORTE, "huella_conjunto_vista": huella})
    _rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")
    # gana la version (R15-a va DESPUES; M-A3-R15-03)
    _rechazo(lab.declarar("ADQUISICION", True, c2.CORTE, huella, version=rv - 1), 409, "VERSION_DESFASADA")
    # R15-a gana a la huella (vista desfasada) ...
    _rechazo(lab.declarar("ADQUISICION", True, c2.CORTE, "0" * 64), 422, SIN_FECHA)
    assert c2.huella() == antes
    # ... y a los componentes (propiedad sin compra y sin fecha)
    vacia = c2.Lab(fecha_adquisicion=None)
    _rechazo(vacia.declarar("ADQUISICION", True, c2.CORTE, "0" * 64), 422, SIN_FECHA)


def test_o_a3_r15_02_replay_exacto_tras_borrar_la_fecha_e_intencion_reutilizada():
    lab = c2.Lab()
    _ok(lab.compra(lab.peticion()))
    huella, rv, i = _huella(lab, c2.CORTE), lab.version(), uuid.uuid4()
    _ok(lab.declarar("ADQUISICION", True, c2.CORTE, huella, intencion_id=i, version=rv))
    _borrar_fecha(lab)
    antes = c2.huella()
    j = _ok(lab.declarar("ADQUISICION", True, c2.CORTE, huella, intencion_id=i, version=rv))
    assert j["idempotente"] is True and c2.huella() == antes                       # replay exacto: 200 sin escribir
    _rechazo(lab.declarar("ADQUISICION", True, "2026-03-21", huella, intencion_id=i, version=rv), 409, REUTILIZADA)
    # nueva declaracion con la fecha NULL: R15-a
    _rechazo(lab.declarar("ADQUISICION", True, c2.CORTE, huella), 422, SIN_FECHA)
    assert c2.huella() == antes


# ================================================================== O-A3-R15-02c (precedencia en C-COMPRA-01 y -03)
def test_o_a3_r15_02c_precedencia_en_c_compra_01():
    lab = c2.Lab(fecha_adquisicion=None)
    decl = {"completo": True, "fecha_corte": c2.CORTE}
    rv = lab.version()
    antes = c2.huella()
    # version obsoleta Y fecha NULL -> 409 (la version gana a R15-a; discriminante A, M-A3-R15-10 C-COMPRA-01)
    _rechazo(lab.compra(lab.peticion(completitud=decl, version=rv + 7)), 409, "VERSION_DESFASADA")
    # las reglas propias de la operacion ganan a R15-a
    malo = lab.peticion(completitud=decl)
    malo["pagos_propios"][1]["importe"] = "1.00"
    _rechazo(lab.compra(malo), 422, "SUMA_NO_CUADRA")
    # version al dia y fecha NULL -> 422 R15-a, nada escrito
    _rechazo(lab.compra(lab.peticion(completitud=decl)), 422, SIN_FECHA)
    assert c2.huella() == antes
    # replay exacto de una compra declarada ANTES de borrar la fecha -> 200 idempotente
    otra = c2.Lab()
    cuerpo = otra.peticion(completitud=decl)
    _ok(otra.compra(cuerpo))
    _borrar_fecha(otra)
    antes = c2.huella()
    assert _ok(otra.compra(cuerpo))["idempotente"] is True and c2.huella() == antes


def test_o_a3_r15_02c_precedencia_en_c_compra_03():
    lab = _sin_fecha_comprada()
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    decl = {"completo": True, "fecha_corte": "2026-04-02"}
    huella, rv = _huella(lab, "2026-04-02"), lab.version()
    antes = c2.huella()
    _rechazo(lab.gasto_posterior(lab.peticion03(linea, completitud=decl, huella_vista=huella, version=rv - 1)), 409,
             "VERSION_DESFASADA")                                                  # M-A3-R15-10 (C-COMPRA-03)
    _rechazo(lab.gasto_posterior(lab.peticion03(linea, completitud=decl, huella_vista="0" * 64)), 422, SIN_FECHA)
    _rechazo(lab.gasto_posterior(lab.peticion03(linea, completitud=decl, huella_vista=huella)), 422, SIN_FECHA)
    assert c2.huella() == antes
    # regla propia de la operacion (sin compra registrada) gana a R15-a
    vacia = c2.Lab(fecha_adquisicion=None)
    _rechazo(vacia.gasto_posterior(vacia.peticion03(vacia.gasto("OTRO", "1.00", "2026-04-02", "2026-04-02"),
                                                    completitud=decl, huella_vista="0" * 64)), 409, "COMPRA_NO_REGISTRADA")
    # replay exacto de un gasto posterior declarado antes de borrar la fecha -> 200
    con = c2.Lab()
    _ok(con.compra(con.peticion()))
    cuerpo = con.peticion03(con.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02"), completitud=decl,
                            huella_vista=_huella(con, "2026-04-02"))
    _ok(con.gasto_posterior(cuerpo))
    _borrar_fecha(con)
    antes = c2.huella()
    assert _ok(con.gasto_posterior(cuerpo))["idempotente"] is True and c2.huella() == antes


# ================================================================== O-A3-R15-03 / -04
def test_o_a3_r15_03_retirar_no_exige_fecha():
    lab = _declarada()
    _borrar_fecha(lab)
    rv = lab.version()
    j = _ok(lab.declarar("ADQUISICION", False))
    assert j["modificadas"] == [lab.pid] and lab.version() == rv + 1 and _terna(lab) == (None, None, None)
    assert _ok(lab.declarar("ADQUISICION", False))["modificadas"] == []           # sin cambios: no escribe
    adq = lab.coste()["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "SIN_DECLARACION")
    # en la compra, retirar (completo = false) con la fecha NULL tambien se admite
    otra = c2.Lab(fecha_adquisicion=None)
    _ok(otra.compra(otra.peticion(completitud={"completo": False})))


def test_o_a3_r15_04_mejoras_con_fecha_null_como_hoy():
    lab = _sin_fecha_comprada()
    mej = lab.coste()["MEJORAS"]
    j = _ok(lab.declarar("MEJORAS", True, b.HOY, mej["huella_conjunto"]))
    assert j["modificadas"] == [lab.pid]
    coste = lab.coste()
    assert (coste["MEJORAS"]["estado"], coste["MEJORAS"]["motivo_estado"]) == ("COMPLETO", None)   # M-A3-R15-05
    assert coste["ADQUISICION"]["motivo_estado"] == "SIN_DECLARACION"


# ================================================================== O-A3-R15-05 / -06 (atomicidad)
def test_o_a3_r15_05_c_compra_01_sin_fecha_nada_escrito():
    lab = c2.Lab(fecha_adquisicion=None)
    antes, rv = c2.huella(), lab.version()
    _rechazo(lab.compra(lab.peticion(completitud={"completo": True, "fecha_corte": c2.CORTE})), 422, SIN_FECHA)
    assert c2.huella() == antes and lab.version() == rv                        # incluye valoraciones y auditoria
    _ok(lab.compra(lab.peticion()))                                          # sin declaracion: como hoy
    assert lab.coste()["ADQUISICION"]["motivo_estado"] == "SIN_DECLARACION"


def test_o_a3_r15_06_c_compra_03_sin_fecha_nada_escrito():
    lab = _sin_fecha_comprada()
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    huella = _huella(lab, "2026-04-02")
    antes, rv = c2.huella(), lab.version()
    cuerpo = lab.peticion03(linea, completitud={"completo": True, "fecha_corte": "2026-04-02"}, huella_vista=huella)
    _rechazo(lab.gasto_posterior(cuerpo), 422, SIN_FECHA)
    assert c2.huella() == antes and lab.version() == rv                        # sin Hk, PARTE_DE, movimiento ni terna
    assert lab.sql("SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (cuerpo["intencion_id"],))[0][0] == 0
    _ok(lab.gasto_posterior(lab.peticion03(linea)))                            # sin declaracion: 200


# ================================================================== O-A3-R15-07 / -08 / -09 (fila 2 bis)
def test_o_a3_r15_07_borrar_la_fecha_da_parcial_sin_fecha_y_conserva_corte_y_huella():
    lab = _declarada()
    antes = lab.coste()
    assert antes["ADQUISICION"]["estado"] == "COMPLETO"
    terna = _terna(lab)
    _borrar_fecha(lab)
    despues = lab.coste()
    adq, prev = despues["ADQUISICION"], antes["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "SIN_FECHA_DE_ADQUISICION")
    assert (adq["fecha_corte"], adq["huella_conjunto"], adq["total"]) == (prev["fecha_corte"], prev["huella_conjunto"],
                                                                         prev["total"])          # M-A3-R15-14
    assert adq["tu_parte"] == prev["tu_parte"] and _terna(lab) == terna
    assert despues["MEJORAS"] == antes["MEJORAS"] and despues["PERMANECE"] == antes["PERMANECE"]


def test_o_a3_r15_08_reponer_la_fecha_reevalua_las_filas_3_a_6():
    lab = _declarada()
    _borrar_fecha(lab)
    _ok(_editar(lab, fecha_adquisicion=c2.ESCRITURA))
    assert lab.coste()["ADQUISICION"]["estado"] == "COMPLETO"
    # con un gasto <= corte anadido mientras faltaba la fecha, reponerla NO da COMPLETO (discriminante D)
    otra = _declarada()
    _borrar_fecha(otra)
    _ok(otra.gasto_posterior(otra.peticion03(otra.gasto("OTRO", "250.00", "2026-03-19", "2026-03-19"),
                                             atribucion={"modo": "NO_LO_SE"})))
    assert otra.coste()["ADQUISICION"]["motivo_estado"] == "SIN_FECHA_DE_ADQUISICION"   # la fila 2 bis gana a la 4
    _ok(_editar(otra, fecha_adquisicion=c2.ESCRITURA))
    adq = otra.coste()["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA")   # M-A3-R15-12
    # fecha > corte: la guarda de B1 (AJ-0352-05), sin cambios (titularidad desde junio para no chocar con su cota)
    tarde = c2.Lab(titularidad_desde="2026-06-01", fecha_adquisicion="2026-02-01")
    _ok(tarde.compra(tarde.peticion(atribucion={"modo": "NO_LO_SE"})))
    _ok(tarde.declarar("ADQUISICION", True, c2.CORTE, _huella(tarde, c2.CORTE)))
    _borrar_fecha(tarde)
    _rechazo(_editar(tarde, fecha_adquisicion="2026-03-21"), 422, "ADQUISICION_POSTERIOR_AL_CORTE_DECLARADO")
    assert tarde.coste()["ADQUISICION"]["motivo_estado"] == "SIN_FECHA_DE_ADQUISICION"


def test_o_a3_r15_09_precedencia_de_l_coste():
    # fecha NULL sin declaracion -> SIN_DECLARACION (M-A3-R15-07); sin componentes -> NO_DISPONIBLE
    lab = _sin_fecha_comprada()
    assert lab.coste()["ADQUISICION"]["motivo_estado"] == "SIN_DECLARACION"
    vacia = c2.Lab(fecha_adquisicion=None)
    assert (vacia.coste()["ADQUISICION"]["estado"], vacia.coste()["ADQUISICION"]["motivo_estado"]) == (
        "NO_DISPONIBLE", "SIN_COMPONENTES")
    # la fila 2 bis gana a la 3 (lectura anterior al corte) y a la 5 (componente posterior)
    dec = _declarada()
    assert dec.coste("2026-03-01")["ADQUISICION"]["motivo_estado"] == "LECTURA_ANTERIOR_AL_CORTE"
    _ok(dec.gasto_posterior(dec.peticion03(dec.gasto("OTRO", "90.00", "2026-04-02", "2026-04-02"))))
    assert dec.coste()["ADQUISICION"]["motivo_estado"] == "COMPONENTE_POSTERIOR_AL_CORTE"
    _borrar_fecha(dec)
    assert dec.coste("2026-03-01")["ADQUISICION"]["motivo_estado"] == "SIN_FECHA_DE_ADQUISICION"
    assert dec.coste()["ADQUISICION"]["motivo_estado"] == "SIN_FECHA_DE_ADQUISICION"


# ================================================================== O-A3-R15-10 (L2)
class _Contador:
    def __init__(self, monkeypatch, *, s0=None, s2=None, tras_s1=None):
        self.leer = self.leer_coste = 0
        self._leer, self._leer_coste = repo.leer, repo.leer_coste
        self.s0, self.s2, self.tras_s1 = s0, s2, tras_s1
        monkeypatch.setattr(repo, "leer", self.f_leer)
        monkeypatch.setattr(repo, "leer_coste", self.f_leer_coste)

    def f_leer(self, *a, **k):
        self.leer += 1
        fila = self._leer(*a, **k)
        muestra = (self.leer + 1) // 2                         # 1, 1, 2, 2, 3, 3
        es_s0 = self.leer % 2 == 1
        ajuste = (self.s0 if es_s0 else self.s2)
        return ajuste(muestra, dict(fila)) if (ajuste and fila) else fila

    def f_leer_coste(self, *a, **k):
        self.leer_coste += 1
        filas = self._leer_coste(*a, **k)
        if self.tras_s1:
            self.tras_s1(self.leer_coste)
        return filas


def _leer_directo(lab, a_fecha: dt.date = HOY):
    return c2.unidad().ejecutar(c2.ctx(lab.owner), lambda s: coste_mod.leer(s, uuid.UUID(lab.pid), a_fecha))


def test_o_a3_r15_10a_l2_estable_una_sola_vuelta(monkeypatch):
    lab = _declarada()
    n = _Contador(monkeypatch)
    adq = _leer_directo(lab)["ADQUISICION"]
    assert adq["estado"] == "COMPLETO" and (n.leer, n.leer_coste) == (2, 1)      # S0, S1, S2


def test_o_a3_r15_10b_recuperacion_calcula_con_la_segunda_muestra(monkeypatch):
    """La primera muestra (descartada) lleva la fecha NULL y es inestable; la segunda es estable y con fecha conocida:
    el resultado es el de la SEGUNDA (COMPLETO), nunca SIN_FECHA_DE_ADQUISICION (discriminante B, M-A3-R15-09)."""
    lab = _declarada()

    def s0(muestra, fila):
        return {**fila, "fecha_adquisicion": None} if muestra == 1 else fila

    def s2(muestra, fila):
        return {**fila, "row_version": fila["row_version"] + 1} if muestra == 1 else fila
    n = _Contador(monkeypatch, s0=s0, s2=s2)
    adq = _leer_directo(lab)["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"]) == ("COMPLETO", None)
    assert (n.leer, n.leer_coste) == (4, 2)
    monkeypatch.undo()
    # y al reves: la descartada con fecha y la estable sin ella -> SIN_FECHA_DE_ADQUISICION
    sin = _declarada()
    _borrar_fecha(sin)

    def s0b(muestra, fila):
        return {**fila, "fecha_adquisicion": dt.date(2026, 3, 20)} if muestra == 1 else fila
    _Contador(monkeypatch, s0=s0b, s2=s2)
    assert _leer_directo(sin)["ADQUISICION"]["motivo_estado"] == "SIN_FECHA_DE_ADQUISICION"


def test_o_a3_r15_10c_agotamiento_nunca_completo(monkeypatch, caplog):
    lab, sin = _declarada(), _sin_fecha_comprada()

    def s2(muestra, fila):
        return {**fila, "row_version": fila["row_version"] + 1}
    n = _Contador(monkeypatch, s2=s2)
    with caplog.at_level("WARNING", logger="gapto.patrimonio.coste"):
        adq = _leer_directo(lab)["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "LECTURA_NO_ESTABLE")     # M-A3-R15-08 y -11
    assert (n.leer, n.leer_coste) == (6, 3)                                                # acotado: 3 muestras
    assert any("agotada" in r.getMessage() for r in caplog.records)
    # un resultado que no es COMPLETO se devuelve tal cual tras el agotamiento
    assert _leer_directo(sin)["ADQUISICION"]["motivo_estado"] == "SIN_DECLARACION"


def test_o_a3_r15_10d_l2_con_commit_real_entre_s0_y_s2(monkeypatch):
    """C-PROP-02 borra la fecha y CONFIRMA entre S1 y S2 de la primera muestra: v0 != v2, se repite y el resultado final
    es PARCIAL SIN_FECHA_DE_ADQUISICION (nunca COMPLETO con la fecha NULL ya confirmada)."""
    lab = _declarada()
    hecho = []

    def tras_s1(i):
        if i == 1:
            hecho.append(_borrar_fecha(lab))
    n = _Contador(monkeypatch, tras_s1=tras_s1)
    adq = _leer_directo(lab)["ADQUISICION"]
    assert hecho and (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "SIN_FECHA_DE_ADQUISICION")
    assert n.leer_coste == 2


# ================================================================== O-A3-R15-INV (P-L2-1..5)
def _py(ruta: pathlib.Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _funciones_con(patron: str) -> set[tuple[str, str]]:
    """(fichero relativo, funcion) de backend/app cuyo cuerpo contiene el patron (en codigo o en literales)."""
    salida = set()
    for f in sorted((RAIZ / "backend" / "app").rglob("*.py")):
        texto = _py(f)
        if not re.search(patron, texto):
            continue
        for nodo in ast.walk(ast.parse(texto)):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cuerpo = ast.get_source_segment(texto, nodo) or ""
                internas = [x for x in ast.walk(nodo) if x is not nodo and isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if re.search(patron, cuerpo) and not any(re.search(patron, ast.get_source_segment(texto, x) or "") for x in internas):
                    salida.add((f.relative_to(RAIZ).as_posix(), nodo.name))
    return salida


REPO = "backend/app/propiedades/repositorio.py"
REPO_CONTRATOS = "backend/app/contratos/repositorio.py"  # bloque 3 F06-02/03 (L-06-T3)


def test_o_a3_r15_inv_estatico_escritores_cerrados():
    # P-L2-1 / P-L2-3: los UNICOS UPDATE de gapto.propiedades
    assert _funciones_con(r"(?i)UPDATE gapto\.propiedades") == {(REPO, "actualizar_propiedad"),
                                                                (REPO, "escribir_declaracion_completitud")}
    assert not _funciones_con(r"(?i)INSERT INTO gapto\.propiedades[^;]*ON CONFLICT")
    # sus llamadores, cerrados, y cada operacion sube la version DESPUES de escribir
    assert _funciones_con(r"\.actualizar_propiedad\(") == {("backend/app/propiedades/servicio.py", "editar")}
    assert _funciones_con(r"\.escribir_declaracion_completitud\(") == {("backend/app/patrimonio/completitud.py", "declarar"),
                                                                       ("backend/app/patrimonio/compra.py", "_declarar")}
    assert _funciones_con(r"(?<!def )\b_declarar\(sesion") == {("backend/app/patrimonio/compra.py", "registrar_compra"),
                                                      ("backend/app/patrimonio/compra.py", "gasto_posterior")}
    for fichero, funcion, escritor in (("backend/app/propiedades/servicio.py", "editar", "repo.actualizar_propiedad("),
                                       ("backend/app/patrimonio/completitud.py", "declarar", "repo.escribir_declaracion_completitud("),
                                       ("backend/app/patrimonio/compra.py", "registrar_compra", "_declarar(sesion"),
                                       ("backend/app/patrimonio/compra.py", "gasto_posterior", "_declarar(sesion")):
        texto = _py(RAIZ / fichero)
        nodo = next(n for n in ast.walk(ast.parse(texto)) if isinstance(n, ast.FunctionDef) and n.name == funcion)
        cuerpo = ast.get_source_segment(texto, nodo)
        assert cuerpo.index(escritor) < cuerpo.index("repo.subir_version(sesion"), (fichero, funcion)
    # P-L2-5: toda escritura de gapto.entidades.row_version es «row_version + 1»; el unico UPDATE de entidades sin version
    # es el del nombre en actualizar_propiedad (C-PROP-02 sube la version a continuacion)
    for f in sorted((RAIZ / "backend" / "app").rglob("*.py")):
        for m in re.finditer(r"(?is)UPDATE gapto\.entidades(?: AS e)?\s+SET\s+(.{0,400}?)(?:WHERE|RETURNING)", _py(f)):
            clausula = m.group(1)
            if "row_version" in clausula:
                assert re.search(r"row_version\s*=\s*(?:e\.)?row_version\s*\+\s*1", clausula), (f, clausula)
                assert len(re.findall(r"row_version\s*=", clausula)) == 1, (f, clausula)
            else:
                assert f.relative_to(RAIZ).as_posix() in (REPO, REPO_CONTRATOS) and "nombre = %s" in clausula, (f, clausula)
    # Bloque 3 F06-02/03 (L-06-T3): los UPDATE de nombre sin version estan cerrados (propiedad, contrato y servicio)
    assert _funciones_con(r"(?i)UPDATE gapto\.entidades SET nombre") == {(REPO, "actualizar_propiedad"),
                                                                         (REPO_CONTRATOS, "actualizar_contrato"),
                                                                         (REPO_CONTRATOS, "actualizar_servicio")}
    # ...el nombre solo llega por `editar` (C-CON-02 y C-SRV-02), que sube la version DESPUES de escribir...
    for fichero, escritor in (("backend/app/contratos/servicio.py", "repo.actualizar_contrato("),
                              ("backend/app/contratos/servicios.py", "repo.actualizar_servicio(")):
        texto = _py(RAIZ / fichero)
        editar = next(n for n in ast.parse(texto).body if isinstance(n, ast.FunctionDef) and n.name == "editar")
        cuerpo = ast.get_source_segment(texto, editar)
        assert cuerpo.index(escritor) < cuerpo.index("repo.subir_version(sesion"), (fichero, "editar")
        # ...y el resto de llamadas pasan un dict literal sin «nombre»
        for funcion in (n for n in ast.parse(texto).body if isinstance(n, ast.FunctionDef) and n.name != "editar"):
            for x in ast.walk(funcion):
                if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == escritor[5:-1]:
                    cambios = x.args[2]
                    assert isinstance(cambios, ast.Dict), (fichero, funcion.name)
                    assert "nombre" not in {k.value for k in cambios.keys if isinstance(k, ast.Constant)}, (fichero, funcion.name)


def test_o_a3_r15_inv_catalogo_de_la_base():
    """P-L2-3: ninguna funcion ni trigger de la base escribe gapto.propiedades ni gapto.entidades ni asigna NEW de la
    fecha, la terna o row_version (lista cerrada de triggers de esas tablas)."""
    with psycopg.connect(h.dsn(), autocommit=True) as c:
        escritoras = c.execute(
            "SELECT p.proname FROM pg_proc p WHERE p.pronamespace = 'gapto'::regnamespace AND (p.prosrc ~* "
            "'update\\s+(gapto\\.)?(propiedades|entidades)\\M' OR p.prosrc ~* 'NEW\\.(row_version|fecha_adquisicion|"
            "coste_adquisicion\\w*)\\s*:=')").fetchall()
        triggers = c.execute(
            "SELECT c.relname, t.tgname, p.proname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_proc p ON p.oid = t.tgfoid WHERE NOT t.tgisinternal AND c.relnamespace = 'gapto'::regnamespace "
            "AND c.relname IN ('propiedades', 'entidades') ORDER BY 1, 2").fetchall()
    assert escritoras == []
    assert triggers == [("entidades", "trg_entidades__d080_subtipo", "fn_check_inversion_principal"),
                        ("entidades", "trg_entidades__garantizada_por", "fn_check_entidad_garantizada_por"),
                        ("entidades", "trg_entidades__owner_inmutable", "fn_guard_owner_inmutable"),
                        ("entidades", "trg_entidades__subtipo_unico", "fn_check_entidad_subtipo_unico"),
                        ("propiedades", "trg_propiedades__subtipo_unico", "fn_check_entidad_subtipo_unico")]


def test_o_a3_r15_inv_dinamico_version_en_el_mismo_commit(monkeypatch):
    """P-L2-2: tras cada escritor de la fecha o de la terna, row_version + 1 en el mismo COMMIT; justo antes de subir la
    version, otra conexion no ve ni la escritura ni la version nueva (ningun estado intermedio visible)."""
    vistos = []
    real = repo.subir_version

    def espia(sesion, entidad_id):
        with psycopg.connect(h.dsn(), autocommit=True) as otra:
            vistos.append(otra.execute(
                "SELECT e.row_version, p.fecha_adquisicion, p.coste_adquisicion_declarado_completo FROM gapto.entidades e "
                "JOIN gapto.propiedades p ON p.entidad_id = e.id WHERE e.id = %s", (entidad_id,)).fetchone())
        return real(sesion, entidad_id)
    lab = c2.Lab()
    _ok(lab.compra(lab.peticion()))
    monkeypatch.setattr(repo, "subir_version", espia)

    def paso(nombre, accion):
        antes = lab.sql("SELECT e.row_version, p.fecha_adquisicion, p.coste_adquisicion_declarado_completo "
                        "FROM gapto.entidades e JOIN gapto.propiedades p ON p.entidad_id = e.id WHERE e.id = %s",
                        (lab.pid,))[0]
        _ok(accion())
        despues = lab.sql("SELECT e.row_version, p.fecha_adquisicion, p.coste_adquisicion_declarado_completo "
                          "FROM gapto.entidades e JOIN gapto.propiedades p ON p.entidad_id = e.id WHERE e.id = %s",
                          (lab.pid,))[0]
        assert vistos[-1] == antes, (nombre, vistos[-1], antes)                # sin estado intermedio visible
        assert despues[0] == antes[0] + 1 and despues != antes, (nombre, antes, despues)
    paso("C-PROP-05", lambda: lab.declarar("ADQUISICION", True, c2.CORTE, _huella(lab, c2.CORTE)))
    paso("C-PROP-02", lambda: _editar(lab, fecha_adquisicion=None))
    paso("C-PROP-02 reponer", lambda: _editar(lab, fecha_adquisicion=c2.ESCRITURA))
    paso("C-COMPRA-03", lambda: lab.gasto_posterior(lab.peticion03(
        lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02"), completitud={"completo": True, "fecha_corte": "2026-04-02"},
        huella_vista=_huella(lab, "2026-04-02"))))
    paso("C-PROP-05 retirar", lambda: lab.declarar("ADQUISICION", False))
    otra = c2.Lab()
    lab.pid = otra.pid
    lab.owner, lab.cli = otra.owner, otra.cli
    paso("C-COMPRA-01", lambda: otra.compra(otra.peticion(completitud={"completo": True, "fecha_corte": c2.CORTE})))


# ================================================================== O-A3-INV / O-A3-B1 / O-A3-TXT
def _lineas_de_codigo(f: pathlib.Path) -> list[str]:
    return [linea for linea in f.read_text(encoding="utf-8").splitlines() if not linea.lstrip().startswith(("#", "//", "*"))]


def test_o_a3_inv_ningun_test_fuerza_el_interruptor():
    fuerza = re.compile(r"(?<!des)habilitar_0352\(|CONSUMIDORES_0352_HABILITADOS[\"']?\s*,\s*True|"
                        r"CONSUMIDORES_0352_HABILITADOS\s*=\s*True|CONSUMIDORES_0352_HABILITADOS\s*=\s*true")
    culpables, apagan = [], set()
    for f in sorted((RAIZ / "tests").rglob("*.py")) + sorted((RAIZ / "mobile" / "__tests__").rglob("*.ts*")):
        for linea in _lineas_de_codigo(f):
            if fuerza.search(linea):
                culpables.append((f.name, linea.strip()))
            if re.search(r"\.deshabilitar_0352\(monkeypatch\)", linea):
                apagan.add(f.name)
    assert culpables == []
    assert apagan == {"test_252_f06_01_b2_coste_completitud.py"}
    ayuda = (RAIZ / "tests" / "api" / "f06_01_b2_helpers.py").read_text(encoding="utf-8")
    assert "def habilitar_0352" not in ayuda and '"CONSUMIDORES_0352_HABILITADOS", False)' in ayuda


SHA_PROPIEDADES = {   # HEAD de inicio de A3-0352 (eb1e719): propiedades/ no se toca (O-A3-B1, CS-04)
    "__init__.py": "bf1934d8b2a75fd37542f8f25838e29bcac085f9ed2b26ee1b36db4fb758e8c4",
    "lecturas.py": "fc8b68cfe8c51da5f00bece858c1e2be330fb04036b7048cdfed3c2d5f7cea17",
    "repositorio.py": "01fd95e6bd2c3ba7e884cdd9161ec738710cac632a9cefa11ee132ed8bae9fd9",
    "servicio.py": "14ed8a1fecf24834eb2bbf16b3ce6fb80003ab9dd3be17715acb9cb4ddbe1eb0",
}


def test_o_a3_b1_propiedades_sin_cambios():
    carpeta = RAIZ / "backend" / "app" / "propiedades"
    actuales = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in carpeta.glob("*.py")}
    assert actuales == SHA_PROPIEDADES


def test_o_a3_txt_servidor_y_cliente_coherentes():
    assert rutas.RECHAZOS[SIN_FECHA] == (422, MENSAJE)
    ts = (RAIZ / "mobile" / "src" / "domain" / "compra.ts").read_text(encoding="utf-8")
    assert f"export const TEXTO_SIN_FECHA_ADQUISICION = '{MENSAJE}';" in ts
    assert re.search(r"COMPLETITUD_SIN_FECHA_DE_ADQUISICION: TEXTO_SIN_FECHA_ADQUISICION,", ts)
    motivos_servidor = set(re.findall(r'"((?:SIN|LECTURA|DECLARACION|COMPONENTE)_[A-Z_]+)"',
                                      _py(RAIZ / "backend" / "app" / "patrimonio" / "coste.py")))
    bloque = ts[ts.index("export const MOTIVOS_COSTE_ADQUISICION"):]
    bloque = bloque[:bloque.index("};")]
    motivos_cliente = set(re.findall(r"^\s+([A-Z_]+):", bloque, re.M))
    assert motivos_servidor == motivos_cliente and {"SIN_FECHA_DE_ADQUISICION", "LECTURA_NO_ESTABLE"} <= motivos_servidor


# ================================================================== O-A3-T2 (consumidores tras el tren)
def test_o_a3_t2_b1r_compra_con_inicio_adelantado_declara_y_completo():
    """Tras B1-R (Q-B1R-10): corregido el inicio de la titularidad a la adquisicion, la compra con la declaracion se
    admite sin forzar y L-COSTE da COMPLETO."""
    from test_260_f06_t2_b1r_inicio_titularidad import Lab as LabB1R
    lab = LabB1R(adquisicion="2015-03-10")
    escritura = "2015-03-10"
    _ok(lab.corregir(escritura))
    partes = [{"actor_id": lab.yo, "porcentaje": "50.0000"}, {"actor_id": lab.ta, "porcentaje": "50.0000"}]
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": lab.detalle()["row_version"],
              "fecha_escritura": escritura, "precio": "100000.00",
              "pagos_propios": [{"linea_id": str(uuid.uuid4()), "rol": "FIRMA", "cuenta_id": str(lab.c1),
                                 "fecha_pago": escritura, "importe": "100000.00"}],
              "gastos": [], "completitud_adquisicion": {"completo": True, "fecha_corte": escritura},
              "atribucion": {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
                  "criterio": "TITULARIDAD_EN_FECHA_ESCRITURA", "fecha_referencia": escritura,
                  "partes": sorted(partes, key=lambda p: p["actor_id"])}}}
    j = _ok(b.post(lab.cli, f"/v1/propiedades/{lab.pid}/compra", cuerpo))
    assert j["compra"]["coste_adquisicion"]["estado"] == "COMPLETO"
    assert c2.leer_coste(lab.cli, lab.pid)["ADQUISICION"]["estado"] == "COMPLETO"


def _declarar_mejoras(lab, a_fecha: str | None = None):
    coste = c2.leer_coste(lab.cli, lab.pid, a_fecha)
    corte = a_fecha or b3.HOY
    return lab.cli.post(f"/v1/propiedades/{lab.pid}/completitud", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version_esperada": lab.version_propiedad(), "ambito": "MEJORAS",
        "completo": True, "fecha_corte": corte, "huella_conjunto_vista": coste["MEJORAS"]["huella_conjunto"]})


def test_o_a3_t2_pag_el_coste_no_depende_de_quien_pago():
    """Tras PAG (QP-P5): una mejora pagada por el cotitular cuenta en el coste y se declara completa sin forzar."""
    import test_262_f06_t2_pag_quien_pago as pag
    lab = b3.Lab()
    p = pag._peticion(lab, clase="MEJORA", pagos=[pag._t(lab, "8000.00")], saldos=[pag._saldo(lab, "LE_DEBO", "4000.00")])
    pag._registrar(lab, p)
    _ok(_declarar_mejoras(lab))
    mej = c2.leer_coste(lab.cli, lab.pid)["MEJORAS"]
    assert (mej["total"], mej["estado"]) == ("8000.00", "COMPLETO")


def test_o_a3_t2_cat_viv_gasto_corriente_no_entra_en_l_coste():
    """Tras CAT-VIV (Q-CV-04): un GASTO_CORRIENTE de vivienda no cambia L-COSTE ni la declaracion completa."""
    import test_280_f06_t2_cat_viv_oraculos as cv
    lab = b3.Lab()
    cv._marcada(lab)
    _ok(_declarar_mejoras(lab))
    antes = c2.leer_coste(lab.cli, lab.pid)
    assert antes["MEJORAS"]["estado"] == "COMPLETO"
    cv._ok(lab, cv._vs01(lab, propiedad=cv._bloque(lab)))
    assert c2.leer_coste(lab.cli, lab.pid) == antes
