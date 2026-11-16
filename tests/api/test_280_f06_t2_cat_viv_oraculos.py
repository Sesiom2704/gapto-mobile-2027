# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_280_f06_t2_cat_viv_oraculos.py
# Ruta: tests/api/test_280_f06_t2_cat_viv_oraculos.py
# Descripcion: T2-F06 CAT-VIV N1 · oraculos del mandato v1.1 §9.2 (anexo A v0.1 §5 y §8; AJ-T2 §2.2 y §3):
#   C-CAT-VIV-01 (O-CV-02..04), OBL-VIV-01 en VS-01, M3 y M5 (O-CV-05, 05b, 09, 10, 10b, 10c, 10d, 11, 19, 21),
#   bloque `propiedad` de VS-01 (O-CV-06, 07, 15, 18) y de M3 (O-CV-06b), ingresos fuera (O-CV-08), correcciones
#   con aviso de lectura (O-CV-13) y regresion sin bloque (O-CV-20). Datos sinteticos; cada rechazo exige estado
#   identico y ninguna auditoria. Propiedad del Lab de B3: YO 50 / T 50 desde 2026-01-01 y YO 100 desde
#   2026-06-01; FECHA 2026-05-15 (50/50).
# Version: 0.1.0 (F06 T2-F06 CAT-VIV N1)
# Version: 0.1.1 (gate local, plan B): O-CV-06 leia el primer efecto del hecho sin orden (la posicion añade efectos);
#   ahora exige un unico efecto GASTO con su categoria. Correccion del propio test, sin cambio de contrato.
# Version: 0.1.2 (lote 38, STOP C04; decision de Moises 2026-11-16, F06-00_Decisiones_Moises_2026-11-16_M-CV-04_
#   oraculo_v1.0): O-CV-06 y O-CV-18 exigen ademas, de forma determinista, que el hecho de VS-01 con propiedad
#   conserve el tipo GASTO (nunca MEJORA_PATRIMONIAL) y no tenga efecto VALOR_ACTIVO (no entra en L-COSTE);
#   mata M-CV-04. Solo test, sin cambio de contrato.
# ============================================================
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

import f05_01_helpers as fh
import f05_05_helpers as x5
import f05_06_m2_helpers as m2h
import f05_06_m3_helpers as m3
import f05_06_m5_helpers as m5
import f06_01_b1_helpers as b
import f06_01_b2_helpers as b2
import f06_01_b3_helpers as b3
import vs01_api_helpers as h

D = Decimal
FECHA = "2026-05-15"
GASTO = "/v1/intenciones/gasto-pagado"
PREFIJO_RG = "gapto.f06.registro_gasto."


@pytest.fixture
def lab() -> b3.Lab:
    return b3.Lab()


# ------------------------------------------------------------------ utilidades
def _version_cat(lab, cat) -> int:
    return lab.sql("SELECT row_version FROM gapto.categorias_financieras WHERE id = %s", (cat,))[0][0]


def _marcar(lab, cat=None, valor: bool = True, row_version=None):
    cat = cat or lab.cat
    return lab.cli.post(f"/v1/categorias/{cat}/vivienda",
                        json={"asociada_vivienda": valor, "row_version": row_version or _version_cat(lab, cat)},
                        headers=h.AUTH)


def _marcada(lab, cat=None):
    r = _marcar(lab, cat)
    assert r.status_code == 200, r.text
    return r.json()


def _huella(lab) -> tuple:
    return (b3.huella(), m3.huella(lab.owner), m5.huella(lab.owner))


def _vs01(lab, *, propiedad=None, cat="LAB", importe="120.00", fecha=FECHA, cuenta=None, **extra) -> dict:
    cat = lab.cat if cat == "LAB" else cat
    c = h.intencion(cuenta or lab.c1, importe=importe, fecha_hecho=fecha, concepto="Comunidad",
                    atribucion="SIN_INDICAR", financiacion=h.NO_DETERMINADA, categoria=x5._cat(cat))
    if propiedad is not None:
        c["propiedad"] = propiedad
    c.update(extra)
    return c


def _bloque(lab, *, importe="120.00", fecha=FECHA, pagos=None, saldos=None, atribucion=None, pid=None,
            clase="GASTO_CORRIENTE", cuenta=None) -> dict:
    mitad = str((D(importe) / 2).quantize(D("0.01")))
    saldos = saldos if saldos is not None else [{"actor_id": lab.ta, "sentido": "ME_DEBE", "importe": mitad}]
    return {"propiedad_id": str(pid or lab.pid), "clase": clase,
            "atribucion": atribucion or {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": lab.vista(fecha)},
            "pagos": pagos or [{"pagador": "YO", "cuenta_id": str(cuenta or lab.c1), "importe": importe}],
            "saldos": saldos,
            "posiciones_confirmadas": [{"actor_id": s["actor_id"], "tipo": {"ME_DEBE": "DERECHO_COBRO",
                                                                            "LE_DEBO": "OBLIGACION_PAGO"}[s["sentido"]],
                                        "importe": s["importe"]} for s in saldos if s["sentido"] != "NADA"]}


def _post(lab, ruta, cuerpo):
    return lab.cli.post(ruta, json=cuerpo, headers=h.AUTH)


def _ok(lab, cuerpo, ruta=GASTO) -> dict:
    r = _post(lab, ruta, cuerpo)
    assert r.status_code == 200, r.text
    return r.json()


def _rechazo(lab, cuerpo, codigo, status=422, ruta=GASTO):
    antes = _huella(lab)
    r = _post(lab, ruta, cuerpo)
    assert r.status_code == status, r.text
    assert r.json().get("codigo") == codigo, r.text
    assert _huella(lab) == antes
    return r


def _afecta_a(lab, hid) -> list[tuple]:
    return lab.sql("SELECT id, entidad_id, principal, efecto_id IS NOT NULL FROM gapto.hecho_entidades "
                   "WHERE hecho_id = %s AND tipo_relacion = 'AFECTA_A'", (hid,))


def _atribuciones(lab, hid):
    return sorted((str(a), str(D(i).quantize(D("0.01"))), c) for a, i, c in lab.sql(
        "SELECT t.actor_id, t.importe_atribuido, t.criterio_atribucion FROM gapto.efecto_atribuciones t "
        "JOIN gapto.hecho_efectos e ON e.id = t.efecto_id WHERE e.hecho_id = %s", (hid,)))


def _posiciones(lab, hid):
    return sorted((t, str(a), str(D(i).quantize(D("0.01")))) for t, a, i in m3.posiciones(lab.owner, hid))


def _no_es_mejora(lab, hid) -> None:
    """M-CV-04: el gasto de vivienda conserva el tipo GASTO (nunca MEJORA_PATRIMONIAL) y no tiene VALOR_ACTIVO."""
    assert lab.sql("SELECT th.codigo FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th "
                   "ON th.id = h.tipo_hecho_id WHERE h.id = %s", (hid,)) == [("GASTO",)]
    assert lab.sql("SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s AND tipo_efecto = 'VALOR_ACTIVO'",
                   (hid,)) == [(0,)]


def _detalle_actividad(lab, hid) -> dict:
    r = lab.cli.get(f"/v1/actividad/{hid}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


# ================================================================== C-CAT-VIV-01
def test_o_cv_02_marcar_y_desmarcar_row_version_auditoria_e_idempotencia(lab):
    v0 = _version_cat(lab, lab.cat)
    aud0 = m3.uno(lab.owner, "SELECT count(*) FROM gapto.auditoria")[0]
    j = _marcada(lab)
    assert j["categoria"]["asociada_vivienda"] is True and j["idempotente"] is False
    assert j["categoria"]["row_version"] == v0 + 1
    assert m3.uno(lab.owner, "SELECT count(*) FROM gapto.auditoria")[0] == aud0 + 1
    # idempotente: misma marca -> sin escritura ni auditoria
    r = _marcar(lab)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    assert _version_cat(lab, lab.cat) == v0 + 1
    assert m3.uno(lab.owner, "SELECT count(*) FROM gapto.auditoria")[0] == aud0 + 1
    # version vieja -> VERSION_DESFASADA, sin escritura
    r = _marcar(lab, valor=False, row_version=v0)
    assert r.status_code == 409 and r.json()["codigo"] == "VERSION_DESFASADA"
    # desmarcar
    r = _marcar(lab, valor=False)
    assert r.status_code == 200 and r.json()["categoria"]["asociada_vivienda"] is False
    assert _version_cat(lab, lab.cat) == v0 + 2
    assert m3.uno(lab.owner, "SELECT count(*) FROM gapto.auditoria")[0] == aud0 + 2


def test_o_cv_02_ambito_ingreso_rechazado_y_ambos_admitido(lab):
    ingreso = x5.categoria(lab.owner, "Nómina", "INGRESO")
    antes = _version_cat(lab, ingreso)
    r = _marcar(lab, ingreso)
    assert r.status_code == 422 and r.json()["codigo"] == "CATEGORIA_AMBITO_NO_ADMITE_VIVIENDA"
    assert _version_cat(lab, ingreso) == antes
    ambos = x5.categoria(lab.owner, "Seguros", "AMBOS")
    assert _marcada(lab, ambos)["categoria"]["asociada_vivienda"] is True


def test_o_cv_02_arbol_devuelve_la_marca_sin_herencia(lab):
    hijo = fh.crear_categoria(lab.owner, "Hijo", "GASTO", parent_id=lab.cat)
    _marcada(lab)
    r = lab.cli.get("/v1/categorias", headers=h.AUTH)
    assert r.status_code == 200, r.text
    nodos = {n["id"]: n for n in r.json()["categorias"]}
    assert nodos[str(lab.cat)]["asociada_vivienda"] is True
    assert nodos[str(hijo)]["asociada_vivienda"] is False


def _huella_hechos(lab) -> tuple:
    return tuple(lab.sql(f"SELECT count(*), md5(coalesce(string_agg(to_jsonb(x)::text, ',' ORDER BY to_jsonb(x)::text), '')) "
                         f"FROM gapto.{t} x")[0] for t in (
        "hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_entidades", "hecho_aportaciones_pago",
        "derechos_obligaciones_financieras", "previsiones", "prevision_hechos"))


def test_o_cv_03_y_04_marcar_y_desmarcar_no_reinterpretan_nada(lab):
    x5.gasto(lab.cli, lab.c1, fecha=FECHA, importe="80.00", categoria_id=lab.cat)
    m5.prevision(lab.owner, "Comunidad", desde="2026-11-01", categoria=lab.cat, cuenta_salida=lab.c1)
    antes = _huella_hechos(lab)
    _marcada(lab)
    assert _huella_hechos(lab) == antes                       # O-CV-03
    _ok(lab, _vs01(lab, propiedad=_bloque(lab)))
    medio = _huella_hechos(lab)
    r = _marcar(lab, valor=False)
    assert r.status_code == 200
    assert _huella_hechos(lab) == medio                       # O-CV-04


# ================================================================== OBL-VIV-01
def test_o_cv_05_gasto_pagado_marcado_sin_propiedad_422_sin_escritura(lab):
    _marcada(lab)
    _rechazo(lab, _vs01(lab), "CATEGORIA_EXIGE_PROPIEDAD")


def test_o_cv_05b_m3_compartido_y_reembolsable_sin_propiedad_422(lab):
    _marcada(lab)
    tania = m3.persona(lab.cli, "Tania")
    c = m3.cuerpo("40.00", pagado_por=m3.con_cuenta(lab.c1), reparto=m3.repartir("20.00", (tania, "20.00", "SI")),
                  fecha=FECHA, categoria=x5._cat(lab.cat))
    _rechazo(lab, c, "CATEGORIA_EXIGE_PROPIEDAD", ruta="/v1/intenciones/gasto-compartido")
    c = _reembolsable(lab, tania)
    _rechazo(lab, c, "CATEGORIA_EXIGE_PROPIEDAD", ruta="/v1/intenciones/gasto-reembolsable")


def _reembolsable(lab, quien, propiedad=None) -> dict:
    c = {"intencion_id": str(uuid.uuid4()), "concepto": "Caldera", "importe": "100.00", "moneda": "EUR",
         "fecha_hecho": FECHA, "cuenta_id": str(lab.c1), "presupuestable": True, "financiacion": h.NO_DETERMINADA,
         "categoria": x5._cat(lab.cat), "reembolso": {"tercero_id": str(quien), "importe": "40.00"}}
    if propiedad is not None:
        c["propiedad"] = propiedad
    return c


def test_o_cv_06_vs01_con_propiedad_50_50_cuenta_mia_deuda_confirmada(lab):
    _marcada(lab)
    coste = b2.leer_coste(lab.cli, lab.pid)
    c = _vs01(lab, propiedad=_bloque(lab))
    j = _ok(lab, c)
    hid = uuid.UUID(j["hecho_id"])
    # GASTO con su categoria y presupuesto; clase no persistida (tipo GASTO, sin VALOR_ACTIVO).
    gastos = lab.sql("SELECT e.categoria_id FROM gapto.hecho_efectos e WHERE e.hecho_id = %s AND e.tipo_efecto = 'GASTO'",
                     (hid,))
    assert gastos == [(lab.cat,)]                                 # un unico efecto GASTO, con su categoria
    # AFECTA_A principal de nivel efecto con la marca de procedencia del registro de gasto.
    vinculos = _afecta_a(lab, hid)
    assert vinculos == [(uuid.uuid5(hid, PREFIJO_RG + "afecta_a"), uuid.UUID(str(lab.pid)), True, True)]
    # Atribuciones por titularidad (PARTICIPACION_ENTIDAD), 60/60.
    assert _atribuciones(lab, hid) == sorted([(str(lab.yo), "60.00", "PARTICIPACION_ENTIDAD"),
                                              (str(lab.ta), "60.00", "PARTICIPACION_ENTIDAD")])
    # Posicion confirmada por el componedor de PAG: T me debe 60.
    assert _posiciones(lab, hid) == [("DERECHO_COBRO", str(lab.ta), "60.00")]
    # Sale de mi cuenta 120; L-COSTE sin cambios (M-CV-04).
    assert m5.movimientos(lab.owner, hid) == [(lab.c1, D("-120.0000"))]
    assert b2.leer_coste(lab.cli, lab.pid) == coste
    _no_es_mejora(lab, hid)                                       # tipo GASTO, sin VALOR_ACTIVO (M-CV-04)


def test_o_cv_06b_m3_compartido_y_reembolsable_con_propiedad(lab):
    _marcada(lab)
    tania = m3.persona(lab.cli, "Tania")
    vista = lab.vista(FECHA)
    c = m3.cuerpo("40.00", pagado_por=m3.con_cuenta(lab.c1), reparto=m3.repartir("20.00", (tania, "20.00", "SI")),
                  fecha=FECHA, categoria=x5._cat(lab.cat))
    c["propiedad"] = {"propiedad_id": str(lab.pid), "propuesta_vista": vista}
    j = _ok(lab, c, "/v1/intenciones/gasto-compartido")
    hid = uuid.UUID(j["hecho_id"])
    assert len(_afecta_a(lab, hid)) == 1 and _afecta_a(lab, hid)[0][2:] == (True, True)
    # Reglas de M3 intactas: mi parte 20, Tania me debe 20 (M3, no el componedor de PAG).
    assert j["tu_parte"] == "20.00" and [p["tipo"] for p in j["posiciones"]] == ["DERECHO_COBRO"]
    # Reembolsable con propiedad: 100 % mio con su derecho de cobro y el vinculo.
    r = _ok(lab, _reembolsable(lab, tania, {"propiedad_id": str(lab.pid), "propuesta_vista": vista}),
            "/v1/intenciones/gasto-reembolsable")
    assert len(_afecta_a(lab, uuid.UUID(r["hecho_id"]))) == 1


def test_o_cv_06b_m3_propuesta_vista_desfasada_o_ausente(lab):
    _marcada(lab)
    tania = m3.persona(lab.cli, "Tania")
    c = m3.cuerpo("40.00", pagado_por=m3.con_cuenta(lab.c1), reparto=m3.repartir("20.00", (tania, "20.00", "SI")),
                  fecha=FECHA, categoria=x5._cat(lab.cat))
    c["propiedad"] = {"propiedad_id": str(lab.pid), "propuesta_vista": None}
    _rechazo(lab, c, "ATRIBUCION_PROPUESTA_DESFASADA", 409, "/v1/intenciones/gasto-compartido")
    vieja = lab.vista("2026-07-01")                              # YO 100: no es la de la fecha
    c["propiedad"] = {"propiedad_id": str(lab.pid), "propuesta_vista": {**vieja, "fecha_referencia": FECHA}}
    _rechazo(lab, c, "ATRIBUCION_PROPUESTA_DESFASADA", 409, "/v1/intenciones/gasto-compartido")


def test_o_cv_07_gasto_anterior_a_la_titularidad_sin_propuesta():
    lab = _lab_titularidad_tardia()
    _marcada(lab)
    fecha = "2026-02-15"                                          # cuentas desde 2026-01-01; titularidad desde 03-01
    vista = {"criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": fecha,
             "partes": [{"actor_id": lab.yo, "porcentaje": "100"}]}
    c = _vs01(lab, fecha=fecha, propiedad=_bloque(lab, fecha=fecha, saldos=[], atribucion={
        "modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": vista}))
    _rechazo(lab, c, "TITULARIDAD_NO_DISPONIBLE_EN_FECHA")
    j = _ok(lab, _vs01(lab, fecha=fecha, propiedad=_bloque(lab, fecha=fecha, saldos=[],
                                                           atribucion={"modo": "NO_LO_SE"})))
    assert j["estado_atribucion"] == "NO_DISPONIBLE"
    j = _ok(lab, _vs01(lab, fecha=fecha, propiedad=_bloque(lab, fecha=fecha, saldos=[], atribucion={
        "modo": "MANUAL", "partes": [{"actor_id": lab.yo, "porcentaje": "100"}]})))
    assert j["estado_atribucion"] == "COMPLETA"


def _lab_titularidad_tardia() -> b3.Lab:
    lab = b3.Lab.__new__(b3.Lab)
    lab.owner, lab.actor, lab.cli, lab.c1, _ = x5.entorno(b.RELOJ)
    lab.t = b.tercero(lab.cli, "Tomás")
    prop = b.crear(lab.cli, b.alta(b.compartida([b.yo("50"), b.de(lab.t, "50")], desde="2026-03-01"),
                                   fecha_adquisicion="2025-12-01"))
    lab.pid = prop["id"]
    partes = prop["titularidad"]["partes"]
    lab.yo = next(x["actor_id"] for x in partes if x["yo"])
    lab.ta = next(x["actor_id"] for x in partes if not x["yo"])
    lab.cat = x5.categoria(lab.owner, "Hogar · Comunidad")
    return lab


def test_o_cv_08_ingreso_con_categoria_ambos_marcada_sin_propiedad(lab):
    ambos = x5.categoria(lab.owner, "Seguros", "AMBOS")
    _marcada(lab, ambos)
    x5.ingreso(lab.cli, lab.c1, fecha=FECHA, importe="50.00", categoria_id=ambos)


def test_o_cv_09_marca_cambiada_entre_abrir_y_enviar(lab):
    c = _vs01(lab)                                               # abierto sin marca
    _marcada(lab)
    _rechazo(lab, c, "CATEGORIA_EXIGE_PROPIEDAD")
    c = _vs01(lab, propiedad=_bloque(lab))                       # abierto con marca
    assert _marcar(lab, valor=False).status_code == 200
    j = _ok(lab, c)                                               # asociar a una propiedad no exige la marca
    assert len(_afecta_a(lab, uuid.UUID(j["hecho_id"]))) == 1


def test_o_cv_11_propiedad_de_otros_m8(lab):
    _marcada(lab)
    otra = b.crear(lab.cli, b.alta({"modo": "DE_OTROS", "desde": "2026-01-01", "partes": [b.de(lab.t, "100")]},
                                   nombre="Casa de Tomás"))
    c = _vs01(lab, propiedad=_bloque(lab, pid=otra["id"], saldos=[], atribucion={"modo": "NO_LO_SE"}))
    _rechazo(lab, c, "OPERACION_NO_PERMITIDA_EN_ESTADO", 422)


def test_o_cv_21_cuenta_compartida_con_propiedad(lab):
    _marcada(lab)
    c = _vs01(lab, cuenta=lab.c2, propiedad=_bloque(lab, cuenta=lab.c2))
    _rechazo(lab, c, "PAGO_DESDE_CUENTA_COMPARTIDA")


def test_o_cv_vs01_mi_pago_desde_otra_cuenta_y_sin_bloque_coherente(lab):
    c = _vs01(lab, propiedad=_bloque(lab, cuenta=uuid.uuid4()))
    _rechazo(lab, c, "ENTRADA_INVALIDA")
    c = _vs01(lab, propiedad=_bloque(lab))
    c["atribucion"] = "SOLO_MIO"
    r = _post(lab, GASTO, c)
    assert r.status_code == 422                                   # DTO: con propiedad, SIN_INDICAR y NO_DETERMINADA


def test_o_cv_04_clase_mejora_no_admitida_desde_el_registro(lab):
    c = _vs01(lab, propiedad=_bloque(lab, clase="MEJORA"))
    assert _post(lab, GASTO, c).status_code == 422


# ================================================================== M5 · previsiones (OBL-VIV-01.3-4)
def _prevision(lab):
    return m5.prevision(lab.owner, "Comunidad", desde=FECHA, importe="120.00", categoria=lab.cat,
                        cuenta_salida=lab.c1)


def test_o_cv_10_confirmar_prevision_que_crea_el_hecho_sin_propiedad(lab):
    prev = _prevision(lab)                                        # O-CV-10c: creada ANTES de marcar
    antes = m5.estado(lab.owner, prev), m5.version(lab.owner, prev)
    _marcada(lab)
    assert (m5.estado(lab.owner, prev), m5.version(lab.owner, prev)) == antes   # marcar no la cambia
    c = _vs01(lab, prevision=m5.bloque(lab.owner, prev, True))
    _rechazo(lab, c, "CATEGORIA_EXIGE_PROPIEDAD")
    assert m5.estado(lab.owner, prev) == "ABIERTA" and m5.vinculos(lab.owner, prev) == []
    # Por M3 (gasto compartido desde la prevision) tambien.
    tania = m3.persona(lab.cli, "Tania")
    c = m3.cuerpo("120.00", pagado_por=m3.con_cuenta(lab.c1), reparto=m3.repartir("60.00", (tania, "60.00", "SI")),
                  fecha=FECHA, categoria=x5._cat(lab.cat))
    c["prevision"] = m5.bloque(lab.owner, prev, True)
    _rechazo(lab, c, "CATEGORIA_EXIGE_PROPIEDAD", ruta="/v1/intenciones/gasto-compartido")
    assert m5.estado(lab.owner, prev) == "ABIERTA"


def test_o_cv_10b_confirmar_prevision_con_propiedad_50_50(lab):
    prev = _prevision(lab)
    _marcada(lab)
    coste = b2.leer_coste(lab.cli, lab.pid)
    j = _ok(lab, _vs01(lab, propiedad=_bloque(lab), prevision=m5.bloque(lab.owner, prev, True)))
    hid = uuid.UUID(j["hecho_id"])
    assert len(_afecta_a(lab, hid)) == 1
    assert _atribuciones(lab, hid) == sorted([(str(lab.yo), "60.00", "PARTICIPACION_ENTIDAD"),
                                              (str(lab.ta), "60.00", "PARTICIPACION_ENTIDAD")])
    assert m5.estado(lab.owner, prev) == "REALIZADA"
    assert b2.leer_coste(lab.cli, lab.pid) == coste


def test_o_cv_10d_vincular_prevision_a_un_hecho_existente_no_exige_propiedad(lab):
    hid = x5.gasto(lab.cli, lab.c1, fecha=FECHA, importe="120.00", categoria_id=lab.cat)
    prev = _prevision(lab)
    _marcada(lab)
    entidades = m3.uno(lab.owner, "SELECT count(*) FROM gapto.hecho_entidades")[0]
    _, r = m5.vincular(lab.cli, lab.owner, prev, hid, "120.00", True)
    assert r.status_code == 200, r.text
    assert m3.uno(lab.owner, "SELECT count(*) FROM gapto.hecho_entidades")[0] == entidades


# ================================================================== O-CV-13 · correcciones con aviso
def test_o_cv_13_corregir_categoria_v3_hacia_una_marcada_con_aviso(lab):
    otra = x5.categoria(lab.owner, "Varios")
    hid = x5.gasto(lab.cli, lab.c1, fecha=FECHA, importe="300.00", categoria_id=otra, concepto="Derrama ascensor")
    m2h.marcar_v3(lab.owner, hid)
    _marcada(lab)
    assert _detalle_actividad(lab, hid)["aviso_vivienda_sin_propiedad"] is False
    antes = tuple(m3.uno(lab.owner, f"SELECT count(*) FROM gapto.{t}")[0]
                  for t in ("hecho_entidades", "efecto_atribuciones", "derechos_obligaciones_financieras"))
    e = lab.cli.get(f"/v1/hechos/{hid}/edicion", headers=h.AUTH).json()
    r = lab.cli.post(f"/v1/hechos/{hid}/corregir-categoria", headers=h.AUTH, json={
        "intencion_id": str(uuid.uuid4()), "row_version": e["row_version"], "motivo": "Categoría mal asignada en V3",
        "categoria_id": str(lab.cat)})
    assert r.status_code == 200, r.text
    assert tuple(m3.uno(lab.owner, f"SELECT count(*) FROM gapto.{t}")[0]
                 for t in ("hecho_entidades", "efecto_atribuciones", "derechos_obligaciones_financieras")) == antes
    assert _detalle_actividad(lab, hid)["aviso_vivienda_sin_propiedad"] is True


def test_o_cv_13_c_mej_03_hacia_una_categoria_marcada_sin_vinculos_nuevos(lab):
    marcada = x5.categoria(lab.owner, "Hogar · Comunidad")
    _marcada(lab, marcada)
    hid = lab.ok(lab.cuerpo(clase="MEJORA"))["hecho_id"]          # C-MEJ-03 cambia de clase de efecto
    entidades = m3.uno(lab.owner, "SELECT count(*) FROM gapto.hecho_entidades")[0]
    r = lab.corregir(hid, lab.correccion(hid, "REPARACION", presupuestable=True, categoria=marcada))
    assert r.status_code == 200, r.text
    assert m3.uno(lab.owner, "SELECT count(*) FROM gapto.hecho_entidades")[0] == entidades
    assert _detalle_actividad(lab, hid)["aviso_vivienda_sin_propiedad"] is False   # ya tiene su propiedad


# ================================================================== O-CV-15 · conservacion
def test_o_cv_15_conservacion_c07_tercero_contexto_magnitudes_con_propiedad(lab):
    _marcada(lab)
    mag = h.crear_magnitud(lab.owner, "m3 agua")
    h.crear_asociacion(lab.owner, lab.cat, mag, obligatoria=True)
    # C07 obligatoria tambien con el bloque (CV-8 del prototipo en positivo), sin escritura.
    antes = _huella(lab)
    r = _post(lab, GASTO, _vs01(lab, propiedad=_bloque(lab)))
    assert r.status_code in (409, 422) and r.json()["codigo"] == "MAGNITUD_OBLIGATORIA_AUSENTE", r.text
    assert _huella(lab) == antes
    comercio = x5.tercero(lab.cli, "Aguas SA")
    ctx = x5.contexto(lab.cli, "Obra baño")
    cat = {"estado": "CATEGORIA", "categoria_id": str(lab.cat), "magnitudes": [{"magnitud_id": str(mag), "valor": "12"}]}
    j = _ok(lab, _vs01(lab, propiedad=_bloque(lab), categoria=cat, tercero_id=str(comercio), contexto_id=str(ctx)))
    hid = uuid.UUID(j["hecho_id"])
    tipos = sorted(t for (t,) in lab.sql("SELECT tipo_relacion FROM gapto.hecho_entidades WHERE hecho_id = %s", (hid,)))
    assert "AFECTA_A" in tipos and len(tipos) >= 2                # contexto conservado junto al vinculo
    assert lab.sql("SELECT count(*) FROM gapto.hecho_terceros WHERE hecho_id = %s", (hid,))[0][0] == 1
    assert lab.sql("SELECT count(*) FROM gapto.hecho_magnitudes WHERE hecho_id = %s", (hid,))[0][0] == 1


# ================================================================== O-CV-18 · VP-2b
def test_o_cv_18_mueble_de_250_cuenta_en_el_mes_y_no_en_el_coste(lab):
    muebles = x5.categoria(lab.owner, "Hogar · Muebles")
    _marcada(lab, muebles)
    fecha = "2026-07-10"                                          # YO 100 %
    coste = b2.leer_coste(lab.cli, lab.pid)
    invertido = lab.cli.get("/v1/patrimonio/invertido-mes", params={"fecha": fecha}, headers=h.AUTH).json()
    antes = lab.cli.get("/v1/inicio/resultado-mes", params={"fecha": fecha}, headers=h.AUTH).json()
    c = _vs01(lab, cat=muebles, importe="250.00", fecha=fecha,
              propiedad=_bloque(lab, importe="250.00", fecha=fecha, saldos=[]))
    j = _ok(lab, c)
    despues = lab.cli.get("/v1/inicio/resultado-mes", params={"fecha": fecha}, headers=h.AUTH).json()
    assert D(despues["gastos_propios"]) - D(antes["gastos_propios"]) == D("250.00")
    assert b2.leer_coste(lab.cli, lab.pid) == coste
    assert lab.cli.get("/v1/patrimonio/invertido-mes", params={"fecha": fecha}, headers=h.AUTH).json() == invertido
    assert len(_afecta_a(lab, uuid.UUID(j["hecho_id"]))) == 1
    _no_es_mejora(lab, uuid.UUID(j["hecho_id"]))                  # tipo GASTO, sin VALOR_ACTIVO (M-CV-04)


# ================================================================== O-CV-19 · replay
def test_o_cv_19_replay_idempotente_tras_marcar(lab):
    c = _vs01(lab)
    _ok(lab, c)
    _marcada(lab)
    antes = _huella(lab)
    j = _ok(lab, c)                                               # identidad antes que la guarda
    assert j["idempotente"] is True and _huella(lab) == antes
    cp = _vs01(lab, propiedad=_bloque(lab))
    _ok(lab, cp)
    antes = _huella(lab)
    assert _ok(lab, cp)["idempotente"] is True and _huella(lab) == antes


# ================================================================== O-CV-20 · regresion sin bloque
def test_o_cv_20_sin_bloque_ni_marca_vs01_no_toma_inversiones_ni_propiedad(lab, monkeypatch):
    import app.api.ejecucion_gasto_pagado as ejg
    import app.api.ejecucion_reparto as ejrep
    import app.api.ejecucion_reembolsable as ejree

    llamadas: list[str] = []
    real_inv = ejg.tomar_inversiones
    monkeypatch.setattr(ejg, "tomar_inversiones", lambda s: (llamadas.append("INVERSIONES"), real_inv(s))[1])
    assert ejg.pr is ejrep.pr is ejree.pr
    real = ejg.pr.bloquear
    monkeypatch.setattr(ejg.pr, "bloquear", lambda s, pid: (llamadas.append("PROPIEDAD"), real(s, pid))[1])
    j = _ok(lab, _vs01(lab))
    assert llamadas == []
    assert set(j) == {"intencion_id", "hecho_id", "idempotente", "importe", "moneda", "estado_atribucion",
                      "aportacion_criterio", "financiacion", "estado_categorial", "aviso"}
    assert j["estado_atribucion"] == "NO_DISPONIBLE" and j["aportacion_criterio"] is None
    assert _afecta_a(lab, uuid.UUID(j["hecho_id"])) == []
    tania = m3.persona(lab.cli, "Tania")
    c = m3.cuerpo("40.00", pagado_por=m3.con_cuenta(lab.c1), reparto=m3.SOLO_MIO, fecha=FECHA,
                  categoria=x5._cat(lab.cat))
    _ok(lab, c, "/v1/intenciones/gasto-compartido")
    _ok(lab, _reembolsable(lab, tania), "/v1/intenciones/gasto-reembolsable")
    assert "PROPIEDAD" not in llamadas
    # con bloque, el orden: INVERSIONES y despues la propiedad
    _ok(lab, _vs01(lab, propiedad=_bloque(lab)))
    assert llamadas[-2:] == ["INVERSIONES", "PROPIEDAD"]
