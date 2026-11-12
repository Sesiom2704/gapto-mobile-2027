# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_252_f06_01_b2_coste_completitud.py
# Ruta: tests/api/test_252_f06_01_b2_coste_completitud.py
# Descripcion: F06 T1-F06 · B2 N1 · consumidores PROVISIONALES de 0352 y L-COSTE, por HTTP como gapto_runtime:
#   - O10.29 (nuevo, mandato B2 §7.1): con habilitacion.CONSUMIDORES_0352_HABILITADOS = False (estado del
#     repositorio) la ruta de C-PROP-05 es inaccesible (404 FUNCION_NO_HABILITADA), la declaracion en
#     C-COMPRA-01/03 es 422 sin escribir y L-COSTE no lee la declaracion (nunca COMPLETO, sin corte ni huella);
#     por llamada directa al servicio, igual. La constante es de codigo, no de entorno.
#   - Con los consumidores activados SOLO dentro de cada test (monkeypatch): O2′ completo/no completo, O10.1-O10.6,
#     O10.7′, O10.9, O10.12, O10.13-OP-02, O10.13-OP-03′, O10.15-O10.17, O10.20 (ABA en MEJORAS y adquisicion),
#     O10.21, O10.22 (HF-07), O10.24 (HF-08), O10.25 (HF-11), O10.26 (HF-13), O11.1-O11.8, O11.11-O11.13, O11.16,
#     O8.6 y AJ-0352-04 (ABA). Los componentes de MEJORAS se siembran por fixture (C-MEJ-02 es de B3).
#   - O10.28: inventario cerrado de los writers de las columnas de 0352 (solo C-PROP-05 y C-COMPRA-01/03, en el
#     modulo propio de B2) y O11.22 de B2 (la funcion unica del 0P, importada; cinco llamadas en backend/app).
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import pathlib
import re
import uuid

import pytest

import f06_01_b1_helpers as b
import f06_01_b2_helpers as c2
import vs01_api_helpers as h
from app.patrimonio import completitud as compl
from app.patrimonio import habilitacion

RAIZ = pathlib.Path(__file__).resolve().parents[2]
REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


def _ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def _rechazo(r, status: int, codigo: str):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text


def _terna(lab) -> tuple:
    return lab.sql("SELECT coste_adquisicion_declarado_completo, coste_adquisicion_declarado_en::text, "
                   "coste_adquisicion_conjunto_declarado::text, mejoras_declaradas_completas, mejoras_declaradas_en::text, "
                   "mejoras_conjunto_declarado::text FROM gapto.propiedades WHERE entidad_id = %s", (lab.pid,))[0]


@pytest.fixture()
def lab():
    return c2.Lab()


@pytest.fixture()
def on(monkeypatch):
    c2.habilitar_0352(monkeypatch)


@pytest.fixture()
def comprado(lab, on):
    """O2′ con la adquisicion declarada completa (corte 2026-03-20) por la propia compra."""
    cuerpo = lab.peticion(completitud={"completo": True, "fecha_corte": c2.CORTE})
    _ok(lab.compra(cuerpo))
    return lab, cuerpo


# ================================================================== O10.29 · habilitacion bloqueada
def test_o10_29_constante_de_codigo_desactivada():
    assert habilitacion.CONSUMIDORES_0352_HABILITADOS is False
    texto = (RAIZ / "backend" / "app" / "patrimonio" / "habilitacion.py").read_text(encoding="utf-8")
    codigo = "\n".join(linea.split("#", 1)[0] for linea in texto.splitlines())
    assert not re.search(r"environ|getenv|configuracion", codigo)          # no se activa por entorno


def test_o10_29_ruta_c_prop_05_inaccesible_y_servicio_rechaza(lab):
    antes = c2.huella()
    _rechazo(lab.declarar("MEJORAS", True, b.HOY, "0" * 64), 404, habilitacion.FUNCION_NO_HABILITADA)
    _rechazo(lab.declarar("ADQUISICION", False), 404, habilitacion.FUNCION_NO_HABILITADA)
    r = c2.unidad().ejecutar(c2.ctx(lab.owner), lambda s: compl.declarar(
        s, propiedad_id=uuid.UUID(lab.pid), intencion_id=uuid.uuid4(), row_version=1, ambito="MEJORAS", completo=False,
        fecha_corte=None, huella_vista=None))
    assert isinstance(r, compl.Rechazo) and r.codigo == habilitacion.FUNCION_NO_HABILITADA
    assert c2.huella() == antes


def test_o10_29_declaracion_en_la_compra_y_en_el_gasto_posterior_es_422(lab):
    antes = c2.huella()
    _rechazo(lab.compra(lab.peticion(completitud={"completo": True, "fecha_corte": c2.CORTE})), 422, "ENTRADA_INVALIDA")
    _rechazo(lab.compra(lab.peticion(completitud={"completo": False})), 422, "ENTRADA_INVALIDA")
    assert c2.huella() == antes
    _ok(lab.compra(lab.peticion()))
    antes = c2.huella()
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    _rechazo(lab.gasto_posterior(lab.peticion03(linea, completitud={"completo": False})), 422, "ENTRADA_INVALIDA")
    _rechazo(lab.gasto_posterior(lab.peticion03(linea, completitud={"completo": True, "fecha_corte": "2026-04-02"},
                                                huella_vista="0" * 64)), 422, "ENTRADA_INVALIDA")
    assert c2.huella() == antes


def test_o10_29_o10_10_l_coste_sin_declaracion_nunca_completo(lab):
    _ok(lab.compra(lab.peticion()))
    # aunque las columnas tuvieran una declaracion (fixture), la lectura no la ve sin habilitacion
    c2.como_owner(lab.owner, "UPDATE gapto.propiedades SET coste_adquisicion_declarado_completo = true, "
                             "coste_adquisicion_declarado_en = %s, coste_adquisicion_conjunto_declarado = '[]'::jsonb "
                             "WHERE entidad_id = %s", (c2.CORTE, lab.pid))
    coste = lab.coste()
    assert coste["declaracion_habilitada"] is False
    adq = coste["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"], adq["fecha_corte"], adq["huella_conjunto"]) == (
        "PARCIAL", "SIN_DECLARACION", None, None)
    assert adq["total"] == "216830.00" and coste["MEJORAS"]["estado"] == "NO_DISPONIBLE"


# ================================================================== O2′ con declaracion (consumidores activados)
def test_o2_completo_y_no_completo(lab, on):
    j = _ok(lab.compra(lab.peticion(completitud={"completo": True, "fecha_corte": c2.CORTE})))
    adq = j["compra"]["coste_adquisicion"]
    assert (adq["total"], adq["estado"], adq["tu_parte"]) == ("216830.00", "COMPLETO",
                                                             {"importe": "130098.00", "estado": "COMPLETO"})
    t = _terna(lab)
    assert t[0] is True and t[1] == c2.CORTE and len(json.loads(t[2])) == 4
    otro = c2.Lab()
    _ok(otro.compra(otro.peticion(completitud={"completo": False})))
    assert _terna(otro)[:3] == (None, None, None)
    assert otro.coste()["ADQUISICION"]["estado"] == "PARCIAL"


def test_o10_1_y_o10_2_gasto_posterior_conserva_o_redeclara(comprado):
    lab, _ = comprado
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    _ok(lab.gasto_posterior(lab.peticion03(linea)))
    assert _terna(lab)[1] == c2.CORTE                                                   # se conserva
    adq = lab.coste()["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "COMPONENTE_POSTERIOR_AL_CORTE")
    huella = lab.coste("2026-04-02")["ADQUISICION"]["huella_conjunto"]
    _ok(lab.declarar("ADQUISICION", True, "2026-04-02", huella))
    assert lab.coste()["ADQUISICION"]["estado"] == "COMPLETO"                           # O10.2


def test_o10_2_c_compra_03_con_declaracion_nueva(comprado):
    lab, _ = comprado
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    huella_previa = lab.coste("2026-04-02")["ADQUISICION"]["huella_conjunto"]          # conjunto ANTERIOR al alta
    _ok(lab.gasto_posterior(lab.peticion03(linea, completitud={"completo": True, "fecha_corte": "2026-04-02"},
                                           huella_vista=huella_previa)))
    adq = lab.coste()["ADQUISICION"]
    assert (adq["estado"], adq["fecha_corte"], adq["total"]) == ("COMPLETO", "2026-04-02", "217230.00")


def test_o10_4_lectura_anterior_al_corte(comprado):
    lab, _ = comprado
    adq = lab.coste("2026-02-28")["ADQUISICION"]
    assert (adq["total"], adq["estado"], adq["motivo_estado"]) == ("3630.00", "PARCIAL", "LECTURA_ANTERIOR_AL_CORTE")


def test_o10_5_o10_16_mejoras_sin_hechos(comprado):
    lab, _ = comprado
    mej = lab.coste()["MEJORAS"]
    assert (mej["estado"], mej["total"]) == ("NO_DISPONIBLE", "0.00")
    _ok(lab.declarar("MEJORAS", True, b.HOY, lab.coste(b.HOY)["MEJORAS"]["huella_conjunto"]))
    coste = lab.coste()
    assert (coste["MEJORAS"]["estado"], coste["MEJORAS"]["total"]) == ("COMPLETO", "0.00")
    assert coste["ADQUISICION"]["estado"] == "COMPLETO"                                  # independiente (RR1-03)
    otro = c2.Lab()
    _ok(otro.compra(otro.peticion()))                                                    # adquisicion PARCIAL
    _ok(otro.declarar("MEJORAS", True, b.HOY, otro.coste(b.HOY)["MEJORAS"]["huella_conjunto"]))
    coste = otro.coste()
    assert coste["MEJORAS"]["estado"] == "COMPLETO" and coste["ADQUISICION"]["estado"] == "PARCIAL"   # O10.16


def test_o10_6_permanece_nunca_completo(comprado):
    lab, _ = comprado
    _ok(lab.declarar("MEJORAS", True, b.HOY, lab.coste(b.HOY)["MEJORAS"]["huella_conjunto"]))
    coste = lab.coste()
    assert coste["ADQUISICION"]["estado"] == coste["MEJORAS"]["estado"] == "COMPLETO"
    assert coste["PERMANECE"] == {"total": "216830.00", "estado": "PARCIAL", "bajas": "NO_REPRESENTADAS"}


def test_o10_9_no_lo_se(lab, on):
    _ok(lab.compra(lab.peticion(atribucion={"modo": "NO_LO_SE"})))
    adq = lab.coste()["ADQUISICION"]
    assert adq["total"] == "216830.00" and adq["tu_parte"] == {"importe": None, "estado": "NO_DISPONIBLE"}


def test_o10_12_gasto_omitido_anterior_al_corte(comprado):
    lab, _ = comprado
    antes = _terna(lab)
    _ok(lab.gasto_posterior(lab.peticion03(lab.gasto("OTRO", "250.00", "2026-03-15", "2026-03-15"),
                                           atribucion={"modo": "NO_LO_SE"})))         # sin titularidad el 15-03
    assert _terna(lab) == antes
    adq = lab.coste()["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"], adq["total"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA", "217080.00")


def test_o10_13_op02_fecha_que_cruza_el_corte_y_aba(comprado):
    lab, _ = comprado
    itp = next(x for x in c2.hechos_de_la_compra(lab.owner, lab.pid) if str(x[3]).startswith("12000"))
    c2.op02_fecha(lab.owner, itp[0], "2026-03-25")
    adq = lab.coste()["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA")
    c2.op02_fecha(lab.owner, itp[0], c2.ESCRITURA)                                       # O10.20 adquisicion: ABA
    assert lab.coste()["ADQUISICION"]["estado"] == "COMPLETO"


def _mejoras_declaradas(lab, importe="3000.00"):
    hecho, ef = c2.componente_fixture(lab.owner, lab.pid, "2026-05-01", importe, "TRANSFORMACION_CAPITALIZABLE")
    _ok(lab.declarar("MEJORAS", True, b.HOY, lab.coste(b.HOY)["MEJORAS"]["huella_conjunto"]))
    assert lab.coste()["MEJORAS"]["estado"] == "COMPLETO"
    return hecho, ef


def test_o10_7p_o10_13_op03p_anulacion_de_un_componente_de_mejoras(comprado):
    lab, _ = comprado
    hecho, _ = _mejoras_declaradas(lab)
    c2.op03_anular(lab.owner, hecho)
    for a_fecha in (None, b.HOY):
        mej = lab.coste(a_fecha)["MEJORAS"]
        assert (mej["total"], mej["estado"], mej["motivo_estado"]) == ("0.00", "PARCIAL", "DECLARACION_DESACTUALIZADA")


def test_o10_20_aba_en_mejoras_con_op21(comprado):
    lab, _ = comprado
    hecho, ef = _mejoras_declaradas(lab)
    c2.op21_importe(lab.owner, hecho, ef, "3100.00")
    assert lab.coste()["MEJORAS"]["motivo_estado"] == "DECLARACION_DESACTUALIZADA"
    c2.op21_importe(lab.owner, hecho, ef, "3000.00")
    assert lab.coste()["MEJORAS"]["estado"] == "COMPLETO"                                # AJ-0352-04 (ABA aceptado)


def test_o10_20_bis_b2_sustitucion_con_efecto_nuevo_no_recupera(comprado):
    """Variante B2 de O10.20 bis (C-MEJ-03 es de B3): el componente se sustituye por otro efecto del MISMO hecho, con
    el mismo importe, fecha y causa (fixture). El conjunto incluye efecto_id: PARCIAL (M-CO-09 daria COMPLETO)."""
    lab, _ = comprado
    hecho, _ = _mejoras_declaradas(lab)
    e2 = uuid.uuid4()
    c2.como_owner(lab.owner, "INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, estado_atribucion, "
                             "causa_valor_activo) VALUES (%s, %s, 'VALOR_ACTIVO', 3000, 'NO_DISPONIBLE', "
                             "'TRANSFORMACION_CAPITALIZABLE')", (e2, hecho))
    c2.como_owner(lab.owner, "UPDATE gapto.hecho_entidades SET efecto_id = %s WHERE hecho_id = %s", (e2, hecho))
    mej = lab.coste()["MEJORAS"]
    assert (mej["total"], mej["estado"], mej["motivo_estado"]) == ("3000.00", "PARCIAL", "DECLARACION_DESACTUALIZADA")


def test_componente_de_mejora_en_un_hecho_de_otro_tipo_cuenta(comprado):
    """Discriminante de M-CO-04 en B2: el ambito se define por la CAUSA del efecto, no por el tipo del hecho (un
    GASTO reclasificado por C-MEJ-03 conserva su tipo y lleva TRANSFORMACION_CAPITALIZABLE)."""
    lab, _ = comprado
    c2.componente_fixture(lab.owner, lab.pid, "2026-05-01", "700.00", "TRANSFORMACION_CAPITALIZABLE", tipo="GASTO")
    assert lab.coste()["MEJORAS"]["total"] == "700.00"


def test_o10_21_escala_de_4_decimales(comprado):
    lab, _ = comprado
    hecho, ef = _mejoras_declaradas(lab)
    c2.op21_importe(lab.owner, hecho, ef, "3000.004")
    mej = lab.coste()["MEJORAS"]
    assert (mej["estado"], mej["motivo_estado"]) == ("PARCIAL", "DECLARACION_DESACTUALIZADA")


def test_o10_15_componente_posterior_segun_a_fecha(comprado):
    lab, _ = comprado
    _ok(lab.gasto_posterior(lab.peticion03(lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02"))))
    assert lab.coste("2026-03-31")["ADQUISICION"]["estado"] == "COMPLETO"
    adq = lab.coste("2026-04-02")["ADQUISICION"]
    assert (adq["estado"], adq["motivo_estado"]) == ("PARCIAL", "COMPONENTE_POSTERIOR_AL_CORTE")


def test_o10_17_c_prop_05_con_huella_antigua(comprado):
    lab, _ = comprado
    vieja = lab.coste(b.HOY)["ADQUISICION"]["huella_conjunto"]
    _ok(lab.gasto_posterior(lab.peticion03(lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02"))))
    antes = c2.huella()
    _rechazo(lab.declarar("ADQUISICION", True, b.HOY, vieja), 409, "COMPLETITUD_VISTA_DESFASADA")
    assert c2.huella() == antes


def test_o10_22_hf07_componente_ajeno_a_las_raices(lab, on):
    c2.componente_fixture(lab.owner, lab.pid, "2026-03-01", "500.00", "ADQUISICION", tipo="GASTO")
    antes = c2.huella()
    _rechazo(lab.compra(lab.peticion(completitud={"completo": True, "fecha_corte": c2.CORTE})), 409,
             "COMPLETITUD_VISTA_DESFASADA")
    assert c2.huella() == antes


def test_o10_24_hf08_vinculo_de_nivel_hecho_no_es_componente(lab, on):
    c2.componente_fixture(lab.owner, lab.pid, "2026-03-01", "500.00", "ADQUISICION", nivel_efecto=False)
    adq = lab.coste()["ADQUISICION"]
    assert (adq["estado"], adq["total"], adq["componentes"]) == ("NO_DISPONIBLE", "0.00", 0)


def test_o10_24_inventario_un_solo_principal_por_efecto(comprado):
    lab, _ = comprado
    filas = lab.sql("SELECT efecto_id, count(*) FROM gapto.hecho_entidades WHERE tipo_relacion = 'AFECTA_A' AND principal "
                    "AND efecto_id IS NOT NULL GROUP BY efecto_id HAVING count(*) > 1")
    assert filas == []


def test_o10_25_huella_es_sha256_del_texto_jsonb(comprado):
    lab, _ = comprado
    huella = lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]
    texto = lab.sql("SELECT coste_adquisicion_conjunto_declarado::text FROM gapto.propiedades WHERE entidad_id = %s",
                    (lab.pid,))[0][0]
    assert huella == hashlib.sha256(texto.encode("utf-8")).hexdigest()
    conjunto = json.loads(texto)
    assert all(re.fullmatch(r"\d+\.\d{4}", c["importe"]) for c in conjunto)               # escala 4 (HF-04)


def test_o10_26_tu_parte_y_permanece(lab, on):
    coste = lab.coste()
    assert coste["ADQUISICION"]["estado"] == "NO_DISPONIBLE" and coste["PERMANECE"]["estado"] == "NO_DISPONIBLE"
    _ok(lab.compra(lab.peticion()))
    adq = lab.coste()["ADQUISICION"]
    assert adq["estado"] == "PARCIAL" and adq["tu_parte"]["estado"] == "COMPLETO"


# ================================================================== O11 · C-PROP-05
def test_o11_1_a_o11_5_replay_reutilizacion_y_estado_vigente(comprado):
    lab, _ = comprado
    i0 = uuid.uuid4()
    linea = lab.gasto("OTRO", "400.00", "2026-04-02", "2026-04-02")
    _ok(lab.gasto_posterior(lab.peticion03(linea)))
    huella = lab.coste("2026-04-02")["ADQUISICION"]["huella_conjunto"]
    v = lab.version()
    _ok(lab.declarar("ADQUISICION", True, "2026-04-02", huella, intencion_id=i0, version=v))
    original = dict(ambito="ADQUISICION", completo=True, fecha_corte="2026-04-02", huella=huella, intencion_id=i0,
                    version=v)
    antes = c2.huella()
    assert _ok(lab.declarar(**original))["idempotente"] is True                           # O11.1
    assert c2.huella() == antes
    for cambio in ({"fecha_corte": c2.CORTE, "huella": lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]},
                   {"huella": "a" * 64}, {"completo": False, "fecha_corte": None, "huella": None},
                   {"version": v + 1}):
        _rechazo(lab.declarar(**{**original, **cambio}), 409, REUTILIZADA)               # O11.2 a/b/c y M-IP-04
    assert c2.huella() == antes
    # O11.3: otra intencion sustituye; el replay de i0 es idempotente con el estado vigente
    huella_corte = lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]
    _ok(lab.declarar("ADQUISICION", True, c2.CORTE, huella_corte))
    j = _ok(lab.declarar(**original))
    assert j["idempotente"] is True and _terna(lab)[1] == c2.CORTE
    # O11.4: retirada y replay de i0
    _ok(lab.declarar("ADQUISICION", False))
    assert _ok(lab.declarar(**original))["idempotente"] is True and _terna(lab)[:3] == (None, None, None)
    # O11.5: replay tras una edicion de B1
    assert b.post(lab.cli, f"/v1/propiedades/{lab.pid}/editar", {"intencion_id": str(uuid.uuid4()),
                                                                  "row_version_esperada": lab.version(),
                                                                  "notas": "x"}).status_code == 200
    assert _ok(lab.declarar(**original))["idempotente"] is True


def test_o11_6_o11_7_o8_6_version_y_corte_futuro(comprado):
    lab, _ = comprado
    vieja = lab.version() - 1
    huella = lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]
    antes = c2.huella()
    _rechazo(lab.declarar("ADQUISICION", True, c2.CORTE, huella, version=vieja), 409, "VERSION_DESFASADA")
    _rechazo(lab.declarar("ADQUISICION", True, "2026-10-11", huella, version=vieja), 422, "COMPLETITUD_SIN_FECHA_DE_CORTE")
    assert c2.huella() == antes


def test_o11_8_o11_16_intencion_de_b1_en_la_misma_y_en_otra_propiedad(comprado):
    lab, _ = comprado
    i = uuid.uuid4()
    assert b.post(lab.cli, f"/v1/propiedades/{lab.pid}/editar", {"intencion_id": str(i), "row_version_esperada":
                                                                  lab.version(), "notas": "y"}).status_code == 200
    huella = lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]
    _rechazo(lab.declarar("ADQUISICION", True, c2.CORTE, huella, intencion_id=i), 409, REUTILIZADA)    # O11.8
    otra = b.crear(lab.cli, b.alta(b.solo_mia(), nombre="Garaje", fecha_adquisicion="2026-01-01"))["id"]
    r = b.post(lab.cli, f"/v1/propiedades/{otra}/completitud",
               {"intencion_id": str(i), "row_version_esperada": 1, "ambito": "MEJORAS", "completo": True,
                "fecha_corte": b.HOY, "huella_conjunto_vista": c2.leer_coste(lab.cli, otra, b.HOY)["MEJORAS"]["huella_conjunto"]})
    _rechazo(r, 409, REUTILIZADA)                                                                        # O11.16


def test_o11_11_rechazo_por_huella_no_consume_la_intencion(comprado):
    lab, _ = comprado
    i = uuid.uuid4()
    _rechazo(lab.declarar("MEJORAS", True, b.HOY, "b" * 64, intencion_id=i), 409, "COMPLETITUD_VISTA_DESFASADA")
    assert c2.auditorias(lab.owner, i) == []
    _ok(lab.declarar("MEJORAS", True, b.HOY, lab.coste(b.HOY)["MEJORAS"]["huella_conjunto"], intencion_id=i))


def test_o11_12_sin_cambios_no_escribe(comprado):
    lab, _ = comprado
    huella = lab.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]
    antes = c2.huella()
    i = uuid.uuid4()
    j = _ok(lab.declarar("ADQUISICION", True, c2.CORTE, huella, intencion_id=i))
    assert j["idempotente"] is False and j["modificadas"] == [] and c2.huella() == antes
    assert _ok(lab.declarar("MEJORAS", False))["modificadas"] == [] and c2.huella() == antes
    assert _ok(lab.declarar("ADQUISICION", True, c2.CORTE, huella, intencion_id=i))["idempotente"] is False


def test_o11_13_auditoria_con_las_siete_claves(comprado):
    lab, _ = comprado
    i = uuid.uuid4()
    huella = lab.coste(b.HOY)["MEJORAS"]["huella_conjunto"]
    v = lab.version()
    _ok(lab.declarar("MEJORAS", True, b.HOY, huella, intencion_id=i, version=v))
    sellada = lab.sql("SELECT datos_despues -> 'intencion' FROM gapto.auditoria WHERE request_id = %s", (str(i),))[0][0]
    assert sellada == {"operacion": "COMPLETITUD", "contenido": {
        "propiedad_id": lab.pid, "ambito": "MEJORAS", "completo": True, "fecha_corte": b.HOY,
        "huella_conjunto_vista": huella, "row_version_esperada": v}}


def test_c_prop_05_reglas_del_corte_y_componentes(comprado):
    lab, _ = comprado
    vacia = c2.Lab()
    _rechazo(vacia.declarar("ADQUISICION", True, c2.CORTE, vacia.coste(c2.CORTE)["ADQUISICION"]["huella_conjunto"]),
             422, "COMPLETITUD_SIN_COMPONENTES")
    _rechazo(lab.declarar("ADQUISICION", True, "2026-03-19", lab.coste("2026-03-19")["ADQUISICION"]["huella_conjunto"]),
             422, "COMPLETITUD_SIN_FECHA_DE_CORTE")                                       # anterior a la adquisicion
    _rechazo(lab.declarar("ADQUISICION", True, c2.CORTE), 422, "ENTRADA_INVALIDA")        # sin huella
    r = b.post(lab.cli, f"/v1/propiedades/{uuid.uuid4()}/completitud",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 1, "ambito": "MEJORAS", "completo": False})
    _rechazo(r, 404, "AGREGADO_NO_ENCONTRADO")


# ================================================================== O10.28 y O11.22 (B2)
def _llamadas(nombre: str) -> dict[str, int]:
    cuenta = {}
    for f in (RAIZ / "backend" / "app").rglob("*.py"):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        n = sum(1 for x in ast.walk(arbol) if isinstance(x, ast.Call) and (
            (isinstance(x.func, ast.Attribute) and x.func.attr == nombre) or (isinstance(x.func, ast.Name) and x.func.id == nombre)))
        if n:
            cuenta[f.relative_to(RAIZ).as_posix()] = n
    return cuenta


def test_o10_28_writers_de_las_columnas_de_0352():
    assert _llamadas("escribir_declaracion_completitud") == {"backend/app/patrimonio/completitud.py": 1,
                                                            "backend/app/patrimonio/compra.py": 2}
    compra_txt = (RAIZ / "backend" / "app" / "patrimonio" / "compra.py").read_text(encoding="utf-8")
    fn = ast.get_source_segment(compra_txt, next(n for n in ast.parse(compra_txt).body
                                                 if isinstance(n, ast.FunctionDef) and n.name == "_declarar"))
    assert "escribir_declaracion_completitud" in fn
    assert _llamadas("_declarar") == {"backend/app/patrimonio/compra.py": 2}            # C-COMPRA-01 y C-COMPRA-03


def test_o11_22_cinco_llamadas_a_la_funcion_unica_del_0p():
    assert _llamadas("bloquear_intencion_propiedad") == {"backend/app/propiedades/servicio.py": 4,
                                                         "backend/app/patrimonio/completitud.py": 1}
    texto = (RAIZ / "backend" / "app" / "patrimonio" / "completitud.py").read_text(encoding="utf-8")
    assert "from app.propiedades.servicio import bloquear_intencion_propiedad" in texto
    assert "pg_advisory" not in texto and "gapto:INTENCION" not in texto
    declarar = next(n for n in ast.parse(texto).body if isinstance(n, ast.FunctionDef) and n.name == "declarar")
    con_sesion = [x for x in ast.walk(declarar) if isinstance(x, ast.Call)
                  and any(isinstance(a, ast.Name) and a.id == "sesion" for a in x.args)]
    primera = min(con_sesion, key=lambda x: (x.lineno, x.col_offset))
    assert ast.unparse(primera) == "bloquear_intencion_propiedad(sesion, intencion_id)"
