# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_231_f06_01_b1_propiedades.py
# Ruta: tests/api/test_231_f06_01_b1_propiedades.py
# Descripcion: F06-01 B1 · Propiedad (N1; contratos R1 v0.8 Parte I y §1,
#   ajustes PR1-01/PR1-04 del dictamen de R1; contrato HTTP de B1 del
#   lote 12). Por HTTP, como gapto_runtime con RLS (adaptador real):
#     - C-PROP-01 alta: los cuatro modos, 33,3333 + 33,3333 + 33,3334,
#       DE_OTROS al 100 %, cotitular EMPRESA; negativos POR CAPA (DTO ->
#       forma -> porcentaje > 0 -> maximo/decimales -> duplicado -> suma ->
#       tercero -> naturaleza -> fecha) con huella SHA-256 identica y casos
#       de doble error con su ganador contractual; idempotencia por igualdad
#       EXACTA (nunca inclusion), replay con la version ya superada,
#       reordenacion de partes = mismo contenido canonico, UUID de otra
#       entidad, de otro owner y desde otra ruta; sin actores huerfanos.
#     - C-PROP-02 editar: omitido = no cambia, null = borrar, campos no
#       editables -> 422, version, replay, ADQUISICION_POSTERIOR_A_TITULARIDAD,
#       HABITACIONES_EN_USO (contrato no CANCELADO), sin cambios = sin
#       escritura.
#     - C-PROP-03 titularidad: frontera inclusiva (desde = hoy), cierre en
#       desde - 1, cambio programado y segundo programado, retroactivo, vuelta
#       a DESCONOCIDA, REPARTO_ANTERIOR_AL_VIGENTE, fecha de adquisicion,
#       titularidad vista desfasada (PR1-04), hueco rechazado por el trigger.
#     - C-PROP-04 valoraciones: alta, COMPRA reservada, version, replay, UUID
#       de otro owner.
#     - L-PROP: estimado (futura no cuenta, fiscal no desplaza, empate), sin
#       fecha como evidencia, cuota ROUND_HALF_UP etiquetada, importes como
#       texto, lista.
#     - B1 no escribe hechos, efectos, movimientos ni atribuciones.
# Version: 0.1.0 (F06-01 B1, lote 12)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid

import psycopg
import pytest

import f06_01_b1_helpers as b
import vs01_api_helpers as h

ALTA = "/v1/propiedades"


def ruta(pid, sufijo: str = "") -> str:
    return f"/v1/propiedades/{pid}{sufijo}"


@pytest.fixture()
def t():
    return b.entorno()


def _rechazo(r, status: int, codigo: str):
    assert r.status_code == status, r.text
    assert r.json()["codigo"] == codigo, r.text


def _filas(owner, pid):
    return h.leer(owner, "SELECT a.tercero_id, x.porcentaje, x.vigente_desde, x.vigente_hasta "
                         "FROM gapto.entidad_participaciones x JOIN gapto.actores_financieros a ON a.id = x.actor_id "
                         "WHERE x.entidad_id = %s ORDER BY x.vigente_desde, a.tercero_id NULLS FIRST", (pid,))


# ================================================================== C-PROP-01 alta
def test_alta_cuatro_modos(t):
    owner, actor, cli = t
    ana, lola = b.tercero(cli, "Ana"), b.tercero(cli, "Lola SL", "EMPRESA")
    p1 = b.crear(cli, b.alta(b.solo_mia(), fecha_adquisicion="2025-12-15", superficie_m2="80.5", habitaciones=3,
                             tiene_garaje=None, referencia_catastral="1234567AB1234N0001XY"))
    assert p1["titularidad"] == {"modo": "SOLO_MIA", "desde": "2026-01-01", "partes": [
        {"actor_id": str(actor), "yo": True, "tercero_id": None, "nombre": None, "porcentaje": "100.0000"}]}
    assert p1["row_version"] == 1 and p1["superficie_m2"] == "80.50" and p1["incluir_en_rentabilidad"] is True
    assert p1["tiene_garaje"] is None and p1["cambio_programado"] is None and p1["valor_estimado"] is None
    p2 = b.crear(cli, b.alta(b.compartida([b.yo("33.3333"), b.de(ana, "33.3333"), b.de(lola, "33.3334")])))
    assert p2["titularidad"]["modo"] == "COMPARTIDA"
    assert [p["porcentaje"] for p in p2["titularidad"]["partes"]] == ["33.3333", "33.3333", "33.3334"]
    assert [p["nombre"] for p in p2["titularidad"]["partes"]] == [None, "Ana", "Lola SL"]
    p3 = b.crear(cli, b.alta({"modo": "DE_OTROS", "desde": "2026-02-01", "partes": [b.de(ana, "100")]}))
    assert p3["titularidad"]["modo"] == "DE_OTROS" and len(p3["titularidad"]["partes"]) == 1
    p4 = b.crear(cli, b.alta({"modo": "DESCONOCIDA"}))
    assert p4["titularidad"] == {"modo": "DESCONOCIDA", "desde": None, "partes": []}
    assert _filas(owner, p4["id"]) == []
    # un actor por cotitular, auditoria CREAR de la raiz con la intencion sellada
    assert h.leer(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id IN (%s, %s)",
                  (ana, lola))[0][0] == 2
    assert h.leer(owner, "SELECT accion FROM gapto.auditoria WHERE tabla = 'entidades' AND registro_id = %s",
                  (p2["id"],)) == [("CREAR",)]


def test_alta_lista_y_detalle_ajeno(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(nombre="Zeta"))
    b.crear(cli, b.alta(nombre="Alfa", titularidad={"modo": "DESCONOCIDA"}))
    lista = cli.get(ALTA, headers=h.AUTH).json()["propiedades"]
    assert [x["nombre"] for x in lista] == ["Alfa", "Zeta"]
    assert [x["modo_titularidad"] for x in lista] == ["DESCONOCIDA", "SOLO_MIA"]
    otro, _, cli_otro = b.entorno()
    assert cli_otro.get(ALTA, headers=h.AUTH).json()["propiedades"] == []
    r1, r2 = cli_otro.get(ruta(p["id"]), headers=h.AUTH), cli_otro.get(ruta(uuid.uuid4()), headers=h.AUTH)
    _rechazo(r1, 404, "AGREGADO_NO_ENCONTRADO")
    assert r1.json() == r2.json()


NEGATIVOS_ALTA = [
    # (descripcion, titularidad o None, extra, status, codigo)
    ("campo no listado (direccion)", None, {"direccion": {"direccion_id": str(uuid.uuid4())}}, 422, "ENTRADA_INVALIDA"),
    ("incluir_en_rentabilidad en el alta", None, {"incluir_en_rentabilidad": False}, 422, "ENTRADA_INVALIDA"),
    ("nombre en blanco", None, {"nombre": "   "}, 422, "ENTRADA_INVALIDA"),
    ("superficie 0", None, {"superficie_m2": "0"}, 422, "ENTRADA_INVALIDA"),
    ("solo mia con partes", {"modo": "SOLO_MIA", "desde": "2026-01-01", "partes": [b.yo("100")]}, {}, 422,
     "ENTRADA_INVALIDA"),
    ("solo mia sin desde", {"modo": "SOLO_MIA"}, {}, 422, "ENTRADA_INVALIDA"),
    ("desconocida con desde", {"modo": "DESCONOCIDA", "desde": "2026-01-01"}, {}, 422, "ENTRADA_INVALIDA"),
    ("compartida sin yo", "SIN_YO", {}, 422, "ENTRADA_INVALIDA"),
    ("de otros con yo", "DE_OTROS_YO", {}, 422, "ENTRADA_INVALIDA"),
    ("parte con yo y tercero", "YO_Y_TERCERO", {}, 422, "ENTRADA_INVALIDA"),
    ("porcentaje 0", "CERO", {}, 422, "PARTICIPACION_NO_POSITIVA"),
    ("porcentaje negativo", "NEGATIVO", {}, 422, "PARTICIPACION_NO_POSITIVA"),
    ("porcentaje > 100", "MAS_DE_CIEN", {}, 422, "ENTRADA_INVALIDA"),
    ("porcentaje con 5 decimales", "CINCO_DECIMALES", {}, 422, "ENTRADA_INVALIDA"),
    ("tercero duplicado", "DUPLICADO", {}, 422, "PARTICIPANTE_DUPLICADO"),
    ("suma 99,9999", "SUMA", {}, 422, "SUMA_NO_CUADRA"),
    ("tercero de otro owner", "AJENO", {}, 409, "TERCERO_NO_DISPONIBLE"),
    ("tercero inexistente", "INEXISTENTE", {}, 409, "TERCERO_NO_DISPONIBLE"),
    ("tercero deshabilitado", "DESHABILITADO", {}, 409, "TERCERO_NO_DISPONIBLE"),
    ("tercero ORGANISMO", "ORGANISMO", {}, 422, "NATURALEZA_NO_ADMITIDA_EN_TITULARIDAD"),
    ("tercero sin naturaleza", "SIN_NATURALEZA", {}, 422, "NATURALEZA_NO_ADMITIDA_EN_TITULARIDAD"),
    ("desde anterior a la adquisicion", "FECHA", {"fecha_adquisicion": "2026-03-01"}, 422, "FECHA_ANTERIOR_INICIO"),
    # dobles errores: gana la capa anterior (precedencia contractual)
    ("doble: porcentaje 0 y suma", "CERO_Y_SUMA", {}, 422, "PARTICIPACION_NO_POSITIVA"),
    ("doble: duplicado y suma", "DUPLICADO_Y_SUMA", {}, 422, "PARTICIPANTE_DUPLICADO"),
    ("doble: suma y tercero ajeno", "SUMA_Y_AJENO", {}, 422, "SUMA_NO_CUADRA"),
    ("doble: tercero ajeno y ORGANISMO", "AJENO_Y_ORGANISMO", {}, 409, "TERCERO_NO_DISPONIBLE"),
    ("doble: ORGANISMO y fecha", "ORGANISMO", {"fecha_adquisicion": "2026-03-01"}, 422,
     "NATURALEZA_NO_ADMITIDA_EN_TITULARIDAD"),
]


def _titularidad_negativa(clave, cli, ana, ajeno, organismo, deshabilitado):
    c = lambda partes: b.compartida(partes)  # noqa: E731
    return {
        "SIN_YO": c([b.de(ana, "50"), b.de(ajeno, "50")]),
        "DE_OTROS_YO": {"modo": "DE_OTROS", "desde": "2026-01-01", "partes": [b.yo("100")]},
        "YO_Y_TERCERO": c([{"yo": True, "tercero_id": str(ana), "porcentaje": "50"}, b.yo("50")]),
        "CERO": c([b.yo("100"), b.de(ana, "0")]),
        "NEGATIVO": c([b.yo("110"), b.de(ana, "-10")]),
        "MAS_DE_CIEN": c([b.yo("100.5"), b.de(ana, "0.5")]),
        "CINCO_DECIMALES": c([b.yo("50.00001"), b.de(ana, "49.99999")]),
        "DUPLICADO": c([b.yo("50"), b.de(ana, "25"), b.de(ana, "25")]),
        "SUMA": c([b.yo("50"), b.de(ana, "49.9999")]),
        "AJENO": c([b.yo("50"), b.de(ajeno, "50")]),
        "INEXISTENTE": c([b.yo("50"), b.de(uuid.uuid4(), "50")]),
        "DESHABILITADO": c([b.yo("50"), b.de(deshabilitado, "50")]),
        "ORGANISMO": c([b.yo("50"), b.de(organismo, "50")]),
        "SIN_NATURALEZA": c([b.yo("50"), b.de(b.tercero(cli, "Sin naturaleza", None), "50")]),
        "FECHA": c([b.yo("50"), b.de(ana, "50")]),
        "CERO_Y_SUMA": c([b.yo("90"), b.de(ana, "0")]),
        "DUPLICADO_Y_SUMA": c([b.yo("50"), b.de(ana, "20"), b.de(ana, "20")]),
        "SUMA_Y_AJENO": c([b.yo("50"), b.de(ajeno, "40")]),
        "AJENO_Y_ORGANISMO": c([b.yo("40"), b.de(ajeno, "30"), b.de(organismo, "30")]),
    }[clave]


@pytest.fixture()
def negativos(t):
    owner, actor, cli = t
    ana = b.tercero(cli, "Ana")
    organismo = b.tercero(cli, "Ayuntamiento", "ORGANISMO")
    deshabilitado = b.tercero(cli, "Baja")
    r = cli.post(f"/v1/terceros/{deshabilitado}/desactivar", json={"row_version": 1}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    _, _, cli_otro = b.entorno()
    ajeno = b.tercero(cli_otro, "Ana de otro")
    return owner, cli, ana, ajeno, organismo, deshabilitado


@pytest.mark.parametrize("desc,clave,extra,status,codigo", NEGATIVOS_ALTA, ids=[n[0] for n in NEGATIVOS_ALTA])
def test_alta_negativos_por_capa_con_estado_identico(negativos, desc, clave, extra, status, codigo):
    owner, cli, ana, ajeno, organismo, deshabilitado = negativos
    if clave is None or isinstance(clave, dict):
        titularidad = clave
    else:
        titularidad = _titularidad_negativa(clave, cli, ana, ajeno, organismo, deshabilitado)
    cuerpo = b.alta(titularidad, **extra)
    antes = b.huella()
    r = b.post(cli, ALTA, cuerpo)
    _rechazo(r, status, codigo)
    assert b.huella() == antes, desc


def test_alta_idempotencia_por_igualdad_exacta(t):
    owner, _, cli = t
    ana, luis = b.tercero(cli, "Ana"), b.tercero(cli, "Luis")
    cuerpo = b.alta(b.compartida([b.yo("50"), b.de(ana, "25"), b.de(luis, "25")]), fecha_adquisicion="2025-06-01")
    p = b.crear(cli, cuerpo)
    r = b.post(cli, ALTA, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["modificadas"] == []
    # reordenar las partes no cambia el contenido canonico
    reordenado = {**cuerpo, "titularidad": b.compartida([b.de(luis, "25.0000"), b.yo("50.00"), b.de(ana, "25")])}
    assert b.post(cli, ALTA, reordenado).json()["idempotente"] is True
    # el replay se reconoce aunque la version ya haya avanzado
    r = b.post(cli, ruta(p["id"], "/valoraciones"), b.valoracion(p))
    assert r.status_code == 200 and r.json()["propiedad"]["row_version"] == 2
    r = b.post(cli, ALTA, cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["propiedad"]["row_version"] == 2
    antes = b.huella()
    for distinto in (
        {**cuerpo, "nombre": "Otro nombre"},
        {**cuerpo, "fecha_adquisicion": None},
        {**cuerpo, "habitaciones": 2},
        {**cuerpo, "titularidad": b.compartida([b.yo("50"), b.de(ana, "50")])},          # subconjunto
        {**cuerpo, "titularidad": b.compartida([b.yo("50"), b.de(ana, "30"), b.de(luis, "20")])},
        {**cuerpo, "titularidad": {"modo": "DESCONOCIDA"}},
    ):
        _rechazo(b.post(cli, ALTA, distinto), 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    assert b.huella() == antes


def test_alta_inclusion_no_es_replay(t):
    """Mutante M9 de D5: una alta DESCONOCIDA sobre una propiedad ya creada SOLO_MIA no es replay."""
    _, _, cli = t
    cuerpo = b.alta(b.solo_mia())
    b.crear(cli, cuerpo)
    _rechazo(b.post(cli, ALTA, {**cuerpo, "titularidad": {"modo": "DESCONOCIDA"}}), 409,
             "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")


def test_alta_uuid_de_otra_entidad_otro_owner_y_otra_ruta(t):
    owner, _, cli = t
    contexto = uuid.uuid4()
    r = cli.post("/v1/contextos", json={"id": str(contexto), "nombre": "Viaje", "tipo_contexto": "VIAJE"},
                 headers=h.AUTH)
    assert r.status_code == 200, r.text
    antes = b.huella()
    _rechazo(b.post(cli, ALTA, b.alta(intencion_id=contexto)), 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    # UUID de una propiedad de otro owner (PK fisica), con un cotitular NUEVO: sin actor huerfano
    _, _, cli_otro = b.entorno()
    ajena = b.crear(cli_otro, b.alta())
    ana = b.tercero(cli, "Ana nueva")
    antes = b.huella()
    r = b.post(cli, ALTA, b.alta(b.compartida([b.yo("50"), b.de(ana, "50")]), intencion_id=ajena["id"]))
    _rechazo(r, 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    assert b.huella() == antes
    assert h.leer(owner, "SELECT count(*) FROM gapto.actores_financieros WHERE tercero_id = %s", (ana,))[0][0] == 0
    # la intencion de un alta reutilizada en otra ruta de B1
    p = b.crear(cli, b.alta())
    r = b.post(cli, ruta(p["id"], "/editar"), {"intencion_id": p["id"], "row_version_esperada": 1, "nombre": "X"})
    _rechazo(r, 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")


def test_alta_sin_actor_self_y_sin_efectos_financieros(t):
    owner, _, cli = t
    antes = b.huella(b.TABLAS_FINANCIERAS)
    p = b.crear(cli, b.alta())
    b.post(cli, ruta(p["id"], "/valoraciones"), b.valoracion(p))
    b.post(cli, ruta(p["id"], "/editar"), {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 2,
                                           "notas": "Reformada"})
    assert b.huella(b.TABLAS_FINANCIERAS) == antes


# ================================================================== C-PROP-02 editar
def test_editar_omitido_null_y_version(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(fecha_adquisicion="2025-12-01", habitaciones=3, banos=1, notas="Exterior",
                            superficie_m2="80"))
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 1, "nombre": "  Piso   Centro ",
              "notas": None, "superficie_m2": "81.25", "incluir_en_rentabilidad": False, "motivo": "Datos reales"}
    r = b.post(cli, ruta(p["id"], "/editar"), cuerpo)
    assert r.status_code == 200, r.text
    e = r.json()["propiedad"]
    assert (e["nombre"], e["notas"], e["superficie_m2"], e["incluir_en_rentabilidad"], e["row_version"]) == \
        ("Piso Centro", None, "81.25", False, 2)
    assert (e["habitaciones"], e["banos"], e["fecha_adquisicion"]) == (3, 1, "2025-12-01")
    assert r.json()["modificadas"] == [p["id"]]
    aud = h.leer(owner, "SELECT accion, motivo FROM gapto.auditoria WHERE tabla = 'entidades' AND registro_id = %s "
                        "AND request_id = %s", (p["id"], cuerpo["intencion_id"]))
    assert aud == [("ACTUALIZAR", "F06-01 B1 PROPIEDAD EDITAR: Datos reales")]
    # replay con la version ya superada
    r = b.post(cli, ruta(p["id"], "/editar"), cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["propiedad"]["row_version"] == 2
    antes = b.huella()
    _rechazo(b.post(cli, ruta(p["id"], "/editar"), {**cuerpo, "notas": "otra"}), 409,
             "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    # omitido frente a explicito: no es la misma intencion
    sin_notas = {k: v for k, v in cuerpo.items() if k != "notas"}
    _rechazo(b.post(cli, ruta(p["id"], "/editar"), sin_notas), 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    _rechazo(b.post(cli, ruta(p["id"], "/editar"), {**cuerpo, "intencion_id": str(uuid.uuid4())}), 409,
             "VERSION_DESFASADA")
    assert b.huella() == antes
    # sin cambios reales: nada se escribe
    r = b.post(cli, ruta(p["id"], "/editar"), {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 2,
                                               "nombre": "Piso Centro"})
    assert r.status_code == 200 and r.json()["modificadas"] == [] and r.json()["propiedad"]["row_version"] == 2
    assert b.huella() == antes


@pytest.mark.parametrize("extra,codigo", [
    ({"titularidad": b.solo_mia()}, "ENTRADA_INVALIDA"),
    ({"direccion": None}, "ENTRADA_INVALIDA"),
    ({"enabled": False}, "ENTRADA_INVALIDA"),
    ({"tipo_entidad": "CONTEXTO"}, "ENTRADA_INVALIDA"),
    ({"nombre": None}, "ENTRADA_INVALIDA"),
    ({"tipo_propiedad": None}, "ENTRADA_INVALIDA"),
    ({"incluir_en_rentabilidad": None}, "ENTRADA_INVALIDA"),
    ({}, "ENTRADA_INVALIDA"),
    ({"habitaciones": -1}, "ENTRADA_INVALIDA"),
    ({"referencia_catastral": "  "}, "ENTRADA_INVALIDA"),
])
def test_editar_negativos(t, extra, codigo):
    _, _, cli = t
    p = b.crear(cli, b.alta())
    antes = b.huella()
    r = b.post(cli, ruta(p["id"], "/editar"), {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 1, **extra})
    _rechazo(r, 422, codigo)
    assert b.huella() == antes


def test_editar_fecha_adquisicion_y_habitaciones(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta(b.solo_mia("2026-01-01"), fecha_adquisicion="2025-12-01", habitaciones=4))
    antes = b.huella()
    r = b.post(cli, ruta(p["id"], "/editar"), {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 1,
                                               "fecha_adquisicion": "2026-01-02"})
    _rechazo(r, 422, "ADQUISICION_POSTERIOR_A_TITULARIDAD")
    assert b.huella() == antes
    r = b.post(cli, ruta(p["id"], "/editar"), {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 1,
                                               "fecha_adquisicion": "2026-01-01"})
    assert r.status_code == 200, r.text  # frontera inclusiva
    # contrato de habitacion 3 (no cancelado) y otro CANCELADO con la 4
    vivo, cancelado = uuid.uuid4(), uuid.uuid4()
    for cid, hab, estado in ((vivo, 3, "BORRADOR"), (cancelado, 4, "CANCELADO")):
        with psycopg.connect(h.dsn()) as c, c.transaction():
            c.execute("SET LOCAL ROLE gapto_owner")
            c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
            c.execute("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
                      "VALUES (%s, %s, 'CONTRATO', 'Habitacion')", (cid, owner))
            c.execute("INSERT INTO gapto.contratos (entidad_id, propiedad_entidad_id, tipo_contrato, "
                      "estado_documental, habitacion) VALUES (%s, %s, 'HABITACION', %s, %s)",
                      (cid, p["id"], estado, hab))
    antes = b.huella()
    for valor in (2, None):
        r = b.post(cli, ruta(p["id"], "/editar"), {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 2,
                                                   "habitaciones": valor})
        _rechazo(r, 409, "HABITACIONES_EN_USO")
        assert r.json()["detalle"] == {"contratos": [str(vivo)]}
    assert b.huella() == antes
    r = b.post(cli, ruta(p["id"], "/editar"), {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 2,
                                               "habitaciones": 3})
    assert r.status_code == 200 and r.json()["propiedad"]["habitaciones"] == 3


def test_editar_ajena_igual_que_inexistente(t):
    _, _, cli = t
    _, _, cli_otro = b.entorno()
    ajena = b.crear(cli_otro, b.alta())
    cuerpo = {"intencion_id": str(uuid.uuid4()), "row_version_esperada": 1, "nombre": "Mía"}
    antes = b.huella()
    r1 = b.post(cli, ruta(ajena["id"], "/editar"), cuerpo)
    r2 = b.post(cli, ruta(uuid.uuid4(), "/editar"), {**cuerpo, "intencion_id": str(uuid.uuid4())})
    _rechazo(r1, 404, "AGREGADO_NO_ENCONTRADO")
    assert r1.json() == r2.json() and b.huella() == antes


# ================================================================== C-PROP-03 titularidad
def test_titularidad_frontera_cierre_y_programado(t):
    owner, actor, cli = t
    ana = b.tercero(cli, "Ana")
    p = b.crear(cli, b.alta(b.solo_mia("2026-01-01")))
    r = b.post(cli, ruta(p["id"], "/titularidad"),
               b.cambio(p, b.compartida([b.yo("60"), b.de(ana, "40")], desde=b.HOY), motivo="Boda"))
    assert r.status_code == 200, r.text
    v = r.json()["propiedad"]
    assert v["titularidad"]["modo"] == "COMPARTIDA" and v["titularidad"]["desde"] == b.HOY and v["row_version"] == 2
    assert _filas(owner, p["id"]) == [
        (None, 100, dt.date(2026, 1, 1), dt.date(2026, 10, 9)),
        (None, 60, dt.date(2026, 10, 10), None),
        (ana, 40, dt.date(2026, 10, 10), None)]
    # REPARTO_ANTERIOR_AL_VIGENTE: el vigente empieza hoy
    antes = b.huella()
    _rechazo(b.post(cli, ruta(p["id"], "/titularidad"), b.cambio(v, b.solo_mia(b.HOY))), 422,
             "REPARTO_ANTERIOR_AL_VIGENTE")
    assert b.huella() == antes
    # cambio programado y segundo programado
    r = b.post(cli, ruta(p["id"], "/titularidad"), b.cambio(v, b.solo_mia("2026-12-01")))
    assert r.status_code == 200, r.text
    v = r.json()["propiedad"]
    assert v["titularidad"]["modo"] == "COMPARTIDA"
    assert v["cambio_programado"]["modo"] == "SOLO_MIA" and v["cambio_programado"]["desde"] == "2026-12-01"
    antes = b.huella()
    _rechazo(b.post(cli, ruta(p["id"], "/titularidad"), b.cambio(v, b.solo_mia("2027-01-01"))), 409,
             "CAMBIO_PROGRAMADO_EXISTENTE")
    assert b.huella() == antes
    # no reatribuye ni escribe atribuciones
    assert h.leer(owner, "SELECT count(*) FROM gapto.efecto_atribuciones")[0][0] == 0


def test_titularidad_negativos(t):
    owner, _, cli = t
    ana = b.tercero(cli, "Ana")
    p = b.crear(cli, b.alta(b.solo_mia("2026-01-01")))
    futura = b.crear(cli, b.alta(b.solo_mia("2026-11-01"), fecha_adquisicion="2026-11-01"))
    desconocida = b.crear(cli, b.alta({"modo": "DESCONOCIDA"}))
    casos = [
        (p, b.cambio(p, b.solo_mia("2026-10-09")), 422, "CAMBIO_RETROACTIVO_SIN_POLITICA"),
        (p, b.cambio(p, {"modo": "DESCONOCIDA", "desde": b.HOY}), 422, "OPERACION_NO_PERMITIDA_EN_ESTADO"),
        (p, b.cambio(p, b.compartida([b.yo("60"), b.de(ana, "41")], desde=b.HOY)), 422, "SUMA_NO_CUADRA"),
        (p, b.cambio(p, b.compartida([b.yo("100"), b.de(ana, "0")], desde=b.HOY)), 422, "PARTICIPACION_NO_POSITIVA"),
        (p, b.cambio(p, b.solo_mia(b.HOY), version=7), 409, "VERSION_DESFASADA"),
        (p, b.cambio(p, b.solo_mia(b.HOY), titularidad_vista=[]), 409, "VERSION_DESFASADA"),
        (p, b.cambio(p, b.compartida([b.yo("50"), b.de(uuid.uuid4(), "50")], desde=b.HOY)), 409,
         "TERCERO_NO_DISPONIBLE"),
        (futura, b.cambio(futura, b.solo_mia("2026-10-20")), 422, "FECHA_ANTERIOR_INICIO"),
        (futura, b.cambio(futura, b.solo_mia("2026-11-15")), 409, "CAMBIO_PROGRAMADO_EXISTENTE"),
        (p, {**b.cambio(p, b.solo_mia(b.HOY)), "titularidad": None}, 422, "ENTRADA_INVALIDA"),
    ]
    for prop, cuerpo, status, codigo in casos:
        antes = b.huella()
        _rechazo(b.post(cli, ruta(prop["id"], "/titularidad"), cuerpo), status, codigo)
        assert b.huella() == antes, codigo
    r = b.post(cli, ruta(p["id"], "/titularidad"), b.cambio(p, b.solo_mia(b.HOY), titularidad_vista=[]))
    assert r.json().get("detalle") == {"motivo": "TITULARIDAD_CAMBIADA"}
    # desde DESCONOCIDA: solo se inserta
    r = b.post(cli, ruta(desconocida["id"], "/titularidad"), b.cambio(desconocida, b.solo_mia(b.HOY)))
    assert r.status_code == 200 and r.json()["propiedad"]["titularidad"]["modo"] == "SOLO_MIA"


def test_titularidad_vista_desfasada_por_porcentaje(t):
    """PR1-04: el conjunto visto se compara completo (actor Y porcentaje exactos)."""
    _, _, cli = t
    ana = b.tercero(cli, "Ana")
    p = b.crear(cli, b.alta(b.compartida([b.yo("50"), b.de(ana, "50")])))
    vista = b.vista_de(p)
    vista[0] = {**vista[0], "porcentaje": "50.0001"}
    antes = b.huella()
    r = b.post(cli, ruta(p["id"], "/titularidad"), b.cambio(p, b.solo_mia(b.HOY), titularidad_vista=vista))
    _rechazo(r, 409, "VERSION_DESFASADA")
    assert b.huella() == antes
    r = b.post(cli, ruta(p["id"], "/titularidad"), b.cambio(p, b.solo_mia(b.HOY), titularidad_vista=vista[:1]))
    _rechazo(r, 409, "VERSION_DESFASADA")


def test_titularidad_replay_con_version_superada(t):
    _, _, cli = t
    p = b.crear(cli, b.alta(b.solo_mia("2026-01-01")))
    ana = b.tercero(cli, "Ana")
    cuerpo = b.cambio(p, b.compartida([b.yo("50"), b.de(ana, "50")], desde=b.HOY))
    assert b.post(cli, ruta(p["id"], "/titularidad"), cuerpo).status_code == 200
    v = b.leer(cli, p["id"])
    assert b.post(cli, ruta(p["id"], "/valoraciones"), b.valoracion(v)).status_code == 200
    r = b.post(cli, ruta(p["id"], "/titularidad"), cuerpo)
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["propiedad"]["row_version"] == 3
    antes = b.huella()
    _rechazo(b.post(cli, ruta(p["id"], "/titularidad"), {**cuerpo, "desde": "2026-10-11"}), 409,
             "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION")
    assert b.huella() == antes


def test_titularidad_hueco_rechazado_por_el_trigger(t):
    """Respaldo fisico: un hueco en la titularidad no sobrevive al COMMIT (trg_entidad_participaciones__suma_100)."""
    owner, actor, cli = t
    p = b.crear(cli, b.alta(b.solo_mia("2026-01-01")))
    h.como_owner(owner, "UPDATE gapto.entidad_participaciones SET vigente_hasta = DATE '2026-05-31' "
                        "WHERE entidad_id = %s", (p["id"],))
    with pytest.raises(Exception, match="sumar exactamente 100"):
        h.como_owner(owner, "INSERT INTO gapto.entidad_participaciones (entidad_id, actor_id, porcentaje, "
                            "vigente_desde) VALUES (%s, %s, 100, DATE '2026-07-01')", (p["id"], actor))


# ================================================================== C-PROP-04 valoraciones
def test_valoraciones_alta_replay_y_negativos(t):
    owner, _, cli = t
    p = b.crear(cli, b.alta())
    cuerpo = b.valoracion(p, "250000", fuente="Idealista")
    r = b.post(cli, ruta(p["id"], "/valoraciones"), cuerpo)
    assert r.status_code == 200, r.text
    v = r.json()["propiedad"]
    assert v["row_version"] == 2 and v["valor_estimado"]["valor_total"] == "250000.00"
    assert v["valor_estimado"]["id"] == cuerpo["intencion_id"]
    assert h.leer(owner, "SELECT moneda FROM gapto.propiedad_valoraciones WHERE id = %s",
                  (cuerpo["intencion_id"],)) == [("EUR",)]
    r = b.post(cli, ruta(p["id"], "/valoraciones"), cuerpo)  # version 1 ya superada: replay
    assert r.status_code == 200 and r.json()["idempotente"] is True
    _, _, cli_otro = b.entorno()
    ajena = b.crear(cli_otro, b.alta())
    ajena_val = b.valoracion(ajena)
    assert b.post(cli_otro, ruta(ajena["id"], "/valoraciones"), ajena_val).status_code == 200
    casos = [
        ({**cuerpo, "valor_total": "260000"}, 409, "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"),
        (b.valoracion(v, metodo="COMPRA"), 422, "METODO_RESERVADO_A_LA_COMPRA"),
        (b.valoracion(v, version=1), 409, "VERSION_DESFASADA"),
        (b.valoracion(v, "0"), 422, "ENTRADA_INVALIDA"),
        (b.valoracion(v, "10.001"), 422, "ENTRADA_INVALIDA"),
        (b.valoracion(v, fecha=None), 422, "ENTRADA_INVALIDA"),
        (b.valoracion(v, moneda="USD"), 422, "ENTRADA_INVALIDA"),
        ({**b.valoracion(v), "intencion_id": ajena_val["intencion_id"]}, 409,
         "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"),
        # doble error: COMPRA con version desfasada -> gana el DTO/capa (metodo)
        (b.valoracion(v, metodo="COMPRA", version=1), 422, "METODO_RESERVADO_A_LA_COMPRA"),
    ]
    for c, status, codigo in casos:
        antes = b.huella()
        _rechazo(b.post(cli, ruta(p["id"], "/valoraciones"), c), status, codigo)
        assert b.huella() == antes, codigo
    antes = b.huella()
    r1 = b.post(cli, ruta(ajena["id"], "/valoraciones"), b.valoracion(ajena))
    r2 = b.post(cli, ruta(uuid.uuid4(), "/valoraciones"), b.valoracion(ajena))
    _rechazo(r1, 404, "AGREGADO_NO_ENCONTRADO")
    assert r1.json() == r2.json() and b.huella() == antes


# ================================================================== L-PROP
def test_lecturas_precedencia_y_cuota(t):
    owner, _, cli = t
    ana = b.tercero(cli, "Ana")
    p = b.crear(cli, b.alta(b.compartida([b.yo("50"), b.de(ana, "50")])))
    pid = p["id"]
    sin_fecha = uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.propiedad_valoraciones (id, propiedad_entidad_id, valor_total, moneda, "
                        "metodo) VALUES (%s, %s, 999999, 'EUR', 'MANUAL')", (sin_fecha, pid))
    v = b.leer(cli, pid)
    assert v["valor_estimado"] is None and v["cuota_segun_titularidad"] is None
    assert v["valoraciones"][0]["sin_fecha"] is True
    for valor, fecha, metodo in (("200000", "2026-05-01", "TASACION"), ("0.05", "2026-09-01", "MANUAL"),
                                 ("300000", "2026-12-01", "MERCADO"), ("150000", "2026-10-01", "FISCAL_REFERENCIA")):
        v = b.leer(cli, pid)
        r = b.post(cli, ruta(pid, "/valoraciones"), b.valoracion(v, valor, fecha, metodo))
        assert r.status_code == 200, r.text
    v = r.json()["propiedad"]
    # futura no cuenta; la fiscal (posterior) no desplaza; el estimado es la ultima con fecha <= hoy
    assert (v["valor_estimado"]["valor_total"], v["valor_estimado"]["metodo"]) == ("0.05", "MANUAL")
    assert v["referencia_fiscal"]["valor_total"] == "150000.00" and v["valor_compra"] is None
    # 0,05 x 50 % = 0,025 -> ROUND_HALF_UP = 0,03 (HALF_EVEN daria 0,02)
    assert v["cuota_segun_titularidad"] == {"importe": "0.03", "porcentaje": "50.0000", "etiqueta": "VISTA_ESTRUCTURAL"}
    assert len(v["valoraciones"]) == 5 and v["fecha_consulta"] == b.HOY
    de_otros = b.crear(cli, b.alta({"modo": "DE_OTROS", "desde": "2026-01-01", "partes": [b.de(ana, "100")]}))
    b.post(cli, ruta(de_otros["id"], "/valoraciones"), b.valoracion(de_otros))
    assert b.leer(cli, de_otros["id"])["cuota_segun_titularidad"] is None


def test_lecturas_empate_de_fecha_por_id(t):
    _, _, cli = t
    p = b.crear(cli, b.alta())
    ids = sorted([uuid.uuid4(), uuid.uuid4()], key=str)
    v = p
    for i, valor in zip(reversed(ids), ("111", "222")):
        r = b.post(cli, ruta(p["id"], "/valoraciones"), b.valoracion(v, valor, "2026-09-01", intencion_id=i))
        v = r.json()["propiedad"]
    assert v["valor_estimado"]["id"] == str(ids[1])


def test_alta_sin_actor_propio(t):
    """ACTOR_DESCONOCIDO (409): un owner sin actor financiero propio no puede ser titular; nada se escribe."""
    import f05_05_helpers as x5
    owner = uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, 'Sin actor')",
                 (owner, f"{owner}@example.invalid"))
    cli = h.cliente(owner, reloj=x5.reloj(b.RELOJ))
    antes = b.huella()
    _rechazo(b.post(cli, ALTA, b.alta()), 409, "ACTOR_DESCONOCIDO")
    assert b.huella() == antes
