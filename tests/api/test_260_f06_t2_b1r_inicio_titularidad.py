# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_260_f06_t2_b1r_inicio_titularidad.py
# Ruta: tests/api/test_260_f06_t2_b1r_inicio_titularidad.py
# Descripcion: F06 T2-F06 · B1-R (reapertura de B1 por L-01 y L-01b; mandato B1-R §4 y §8.1). Oraculos de
#   C-PROP-03bis «Corregir el inicio de la titularidad» por HTTP (POST /v1/propiedades/{id}/titularidad/inicio),
#   de la cota del alta (L-01b), de la lectura de gastos afectados (GET .../titularidad/inicio/afectados) y de
#   `inicio_titularidad` en el detalle, como gapto_runtime con RLS (cliente de la app con reloj fijo).
#   Hoy del owner: 2026-11-14 (las fechas de los oraculos del mandato se usan tal cual).
#   Casos TI-0..TI-6 del laboratorio (lote 30) dentro de los oraculos, con su nombre en el docstring.
#   Exige GAPTO_TEST_DATABASE_URL (base desechable; estos tests confirman filas).
# Version: 0.1.0 (F06 T2-F06 · B1-R N1)
# Version: 0.1.1 (F06 T2-F06 A3-0352 · L-06 ampliada): O-B1R-24 comprobaba como linea base que los consumidores de 0352
#   seguian sin habilitar; A3-0352 los habilita (L-05): la asercion pasa de False a True. Nada mas cambia.
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest

import f05_05_helpers as x5
import f06_01_b1_helpers as b
import f06_01_b2_helpers as b2
import f06_01_b3_helpers as b3
import vs01_api_helpers as h
from app.patrimonio import habilitacion
from app.propiedades import repositorio as repo

HOY = "2026-11-14"
RELOJ = "2026-11-14T12:00:00"
RUTA = "/v1/propiedades/{}/titularidad/inicio"
AFECTADOS = "/v1/propiedades/{}/titularidad/inicio/afectados"
TABLAS = b3.TABLAS_B3 + ("actores_financieros", "propiedad_valoraciones", "terceros")


class Lab(b3.Lab):
    """Owner con cliente en HOY, una propiedad P y los utiles de B3 (C-MEJ-01) para registrar gastos."""

    def __init__(self, *, modo: str = "COMPARTIDA", desde: str = "2026-11-01", adquisicion: str | None = "2015-03-10"):
        self.owner, self.actor, self.cli, self.c1, _ = x5.entorno(RELOJ)
        self.t = b.tercero(self.cli, "Tomás")
        if modo == "COMPARTIDA":
            tit = b.compartida([b.yo("50"), b.de(self.t, "50")], desde=desde)
        elif modo == "SOLO_MIA":
            tit = b.solo_mia(desde)
        else:
            tit = {"modo": "DESCONOCIDA"}
        extra = {"fecha_adquisicion": adquisicion} if adquisicion else {}
        prop = b.crear(self.cli, b.alta(tit, **extra))
        self.pid = prop["id"]
        partes = prop["titularidad"]["partes"]
        self.yo = next((x["actor_id"] for x in partes if x["yo"]), str(self.actor))
        self.ta = next((x["actor_id"] for x in partes if not x["yo"]), None)
        self.c2 = self.c1
        self.cat = x5.categoria(self.owner, "Hogar · Reparaciones")

    def detalle(self) -> dict:
        return b.leer(self.cli, self.pid)

    def filas(self) -> list[tuple]:
        return self.sql("SELECT actor_id::text, porcentaje::text, vigente_desde::text, vigente_hasta::text "
                        "FROM gapto.entidad_participaciones WHERE entidad_id = %s ORDER BY vigente_desde, actor_id",
                        (self.pid,))

    def auditorias(self) -> int:
        return self.sql("SELECT count(*) FROM gapto.auditoria WHERE tabla = 'entidades' AND registro_id = %s",
                        (self.pid,))[0][0]

    def peticion(self, nuevo: str, *, iid=None, version: int | None = None, inicio: str | None = None,
                 vista: list | None = None, motivo: str | None = "Puse mal la fecha") -> dict:
        d = self.detalle()
        it = d["inicio_titularidad"]
        return {"intencion_id": str(iid or uuid.uuid4()),
                "row_version_esperada": d["row_version"] if version is None else version,
                "nuevo_desde": nuevo, "inicio_visto": (it["inicio"] or HOY) if inicio is None else inicio,
                "primera_version_vista": it["primera_version"] if vista is None else vista, "motivo": motivo}

    def corregir(self, nuevo: str, cli=None, **kw):
        return b.post(cli or self.cli, RUTA.format(self.pid), self.peticion(nuevo, **kw))

    def afectados(self, nuevo: str | None = None, cli=None, pid=None):
        return (cli or self.cli).get(AFECTADOS.format(pid or self.pid),
                                     params={"nuevo_desde": nuevo} if nuevo else None, headers=h.AUTH)

    def gasto_no_lo_se(self, fecha: str, importe: str = "300.00", pid=None) -> str:
        cuerpo = self.cuerpo(fecha=fecha, importe=importe, atribucion={"modo": "NO_LO_SE"}, deuda=[], pid=pid)
        self.ok(cuerpo)
        return cuerpo["intencion_id"]

    def huella_hecho(self, hecho_id) -> list:
        return [self.sql("SELECT h.row_version, h.fecha_hecho::text, h.importe_total::text, h.estado "
                         "FROM gapto.hechos_financieros h WHERE h.id = %s", (hecho_id,)),
                self.efectos(hecho_id),
                self.sql("SELECT t.actor_id::text, t.importe_atribuido::text, t.criterio_atribucion "
                         "FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e ON e.id = t.efecto_id "
                         "WHERE e.hecho_id = %s ORDER BY 1", (hecho_id,))]


def _ok(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()


def _rechazo(lab: Lab, codigo: str, nuevo: str, *, status: int = 422, motivo: str | None = None, **kw):
    antes, auds = b.huella(TABLAS), lab.auditorias()
    r = lab.corregir(nuevo, **kw)
    assert r.status_code == status and r.json()["codigo"] == codigo, r.text
    if motivo is not None:
        assert r.json()["detalle"]["motivo"] == motivo, r.text
    assert b.huella(TABLAS) == antes, "un rechazo no deja escrituras"
    assert lab.auditorias() == auds, "un rechazo no audita"
    return r


def _primera_futura(lab: Lab, desde: str, segunda: str | None = None) -> None:
    """Fixture SQL bajo gapto_owner (HT2-17): la primera version empieza en el futuro y, si se pide, hay una
    segunda version aun mas tarde. Solo para estados que el alta ya no admite (L-01b)."""
    b3.como_owner(lab.owner, "UPDATE gapto.entidad_participaciones SET vigente_desde = %s WHERE entidad_id = %s",
                  (desde, lab.pid))
    if segunda:
        hasta = (dt.date.fromisoformat(segunda) - dt.timedelta(days=1)).isoformat()
        b3.como_owner(lab.owner, "UPDATE gapto.entidad_participaciones SET vigente_hasta = %s WHERE entidad_id = %s",
                      (hasta, lab.pid))
        b3.como_owner(lab.owner, "INSERT INTO gapto.entidad_participaciones (entidad_id, actor_id, porcentaje, "
                                 "vigente_desde) VALUES (%s, %s, 100, %s)", (lab.pid, lab.yo, segunda))


# ================================================================== O-B1R-01..04: la correccion valida
def test_o_b1r_01_solo_mia_a_la_fecha_de_adquisicion():
    """O-B1R-01 (TI-1): 200, filas en la adquisicion, row_version + 1 y una auditoria con el contenido sellado."""
    lab = Lab(modo="SOLO_MIA")
    v0, auds = lab.detalle()["row_version"], lab.auditorias()
    iid = uuid.uuid4()
    j = _ok(lab.corregir("2015-03-10", iid=iid))
    assert j["idempotente"] is False and j["modificadas"] == [lab.pid]
    assert [(f[2], f[3]) for f in lab.filas()] == [("2015-03-10", None)]
    assert j["propiedad"]["row_version"] == v0 + 1 and lab.detalle()["row_version"] == v0 + 1
    assert lab.auditorias() == auds + 1
    (motivo, despues), = lab.sql("SELECT motivo, datos_despues::text FROM gapto.auditoria WHERE request_id = %s "
                                 "AND tabla = 'entidades'", (iid,))
    assert motivo == "F06 T2 B1-R CORREGIR INICIO DE TITULARIDAD: Puse mal la fecha"
    assert json.loads(despues)["intencion"] == {"operacion": "PROPIEDAD_INICIO_TITULARIDAD", "contenido": {
        "row_version_esperada": v0, "motivo": "Puse mal la fecha", "nuevo_desde": "2015-03-10",
        "inicio_visto": "2026-11-01", "primera_version_vista": [[lab.yo, "100.0000"]]}}
    assert j["propiedad"]["inicio_titularidad"]["inicio"] == "2015-03-10"


def test_o_b1r_02_compartida_todas_las_filas_en_un_unico_update(monkeypatch):
    """O-B1R-02: las DOS filas de la primera version se mueven en UNA llamada (un UPDATE por id) y la suma 100,
    el EXCLUDE y el CHECK pasan en el COMMIT."""
    lab = Lab(adquisicion=None)
    llamadas = []
    original = repo.adelantar_inicio_participaciones

    def espia(sesion, ids, nuevo):
        n = original(sesion, ids, nuevo)
        llamadas.append((sorted(map(str, ids)), nuevo, n))
        return n
    monkeypatch.setattr(repo, "adelantar_inicio_participaciones", espia)
    _ok(lab.corregir("2020-01-01"))
    assert len(llamadas) == 1 and len(llamadas[0][0]) == 2 and llamadas[0][2] == 2, llamadas
    assert [(f[1], f[2], f[3]) for f in lab.filas()] == [("50.0000", "2020-01-01", None)] * 2
    assert sorted(p["porcentaje"] for p in b2.titularidad_en(lab.cli, lab.pid, "2020-01-01")) == ["50.0000"] * 2


def test_o_b1r_03_titularidad_en_fecha_gana_el_periodo_sin_cambiar_lo_demas():
    """O-B1R-03 (TI-1): titularidad_en_fecha(2021-06-01) pasa de [] a 50/50; en fechas >= el inicio original no
    cambia."""
    lab = Lab(adquisicion=None)
    fechas = ("2026-11-01", "2026-11-14")
    antes = {f: b2.titularidad_en(lab.cli, lab.pid, f) for f in fechas}
    assert b2.titularidad_en(lab.cli, lab.pid, "2021-06-01") == []
    assert lab.propuesta("2021-06-01").json()["titularidad_disponible"] is False
    _ok(lab.corregir("2020-01-01"))
    assert sorted(p["porcentaje"] for p in b2.titularidad_en(lab.cli, lab.pid, "2021-06-01")) == ["50.0000"] * 2
    assert {f: b2.titularidad_en(lab.cli, lab.pid, f) for f in fechas} == antes
    assert lab.propuesta("2021-06-01").json()["titularidad_disponible"] is True
    assert b2.titularidad_en(lab.cli, lab.pid, "2019-12-31") == []


def test_o_b1r_04_no_reatribuye_hechos_registrados():
    """O-B1R-04 (TI-1): un gasto de 2021 registrado antes con «No lo sé» queda igual (hecho, efectos y
    atribuciones); uno nuevo de esa fecha si recibe la propuesta por titularidad."""
    lab = Lab(adquisicion=None)
    previo = lab.gasto_no_lo_se("2021-05-15")
    huella = lab.huella_hecho(previo)
    assert huella[1][0][5] == "NO_DISPONIBLE" and huella[2] == []
    _ok(lab.corregir("2020-01-01"))
    assert lab.huella_hecho(previo) == huella
    nuevo = lab.cuerpo(fecha="2021-05-15", importe="300.00")
    lab.ok(nuevo)
    assert sorted(a[1] for a in lab.huella_hecho(nuevo["intencion_id"])[2]) == ["150.0000", "150.0000"]


# ================================================================== O-B1R-05..12: guardas
def test_o_b1r_05_no_anterior_igual_y_posterior():
    """O-B1R-05 (TI-3; Q-B1R-03): igual al inicio vigente y posterior -> INICIO_NO_ANTERIOR, sin escribir."""
    lab = Lab()
    _rechazo(lab, "INICIO_NO_ANTERIOR", "2026-11-01")
    _rechazo(lab, "INICIO_NO_ANTERIOR", "2026-11-10")


def test_o_b1r_06_anterior_a_la_adquisicion():
    """O-B1R-06 (TI-3): anterior a la adquisicion -> FECHA_ANTERIOR_INICIO; igual a la adquisicion se admite."""
    lab = Lab()
    _rechazo(lab, "FECHA_ANTERIOR_INICIO", "2015-03-09")
    _ok(lab.corregir("2015-03-10"))


def test_o_b1r_07_cambio_programado():
    """O-B1R-07 (TI-3b): con una segunda version futura (C-PROP-03 programado) -> CAMBIO_PROGRAMADO_EXISTENTE."""
    lab = Lab()
    _ok(b.post(lab.cli, f"/v1/propiedades/{lab.pid}/titularidad",
               b.cambio(lab.detalle(), b.solo_mia(desde="2026-12-01"))))
    assert lab.detalle()["inicio_titularidad"]["inicio_corregible"] is False
    _rechazo(lab, "CAMBIO_PROGRAMADO_EXISTENTE", "2020-01-01", status=409)


def test_o_b1r_08_desconocida():
    """O-B1R-08 (TI-3b): DESCONOCIDA -> SIN_TITULARIDAD, sin escribir."""
    lab = Lab(modo="DESCONOCIDA")
    assert lab.detalle()["inicio_titularidad"] == {"inicio": None, "inicio_corregible": False, "primera_version": []}
    _rechazo(lab, "SIN_TITULARIDAD", "2020-01-01", inicio="2026-01-01", vista=[])


def test_o_b1r_09_dos_versiones_solo_se_mueve_la_primera():
    """O-B1R-09 (TI-4): con un cambio de titularidad ya aplicado, solo se mueve la primera version; la segunda y el
    cierre de la primera quedan intactos."""
    lab = Lab(desde="2026-05-01", adquisicion=None)
    antes = h.cliente(lab.owner, reloj=x5.reloj("2026-05-20T12:00:00"))
    _ok(b.post(antes, f"/v1/propiedades/{lab.pid}/titularidad",
               b.cambio(b.leer(antes, lab.pid), b.solo_mia(desde="2026-06-01"))))
    segunda = [f for f in lab.filas() if f[2] == "2026-06-01"]
    _ok(lab.corregir("2026-01-01"))
    filas = lab.filas()
    assert [(f[2], f[3]) for f in filas if f[3] is not None] == [("2026-01-01", "2026-05-31")] * 2
    assert [f for f in filas if f[2] == "2026-06-01"] == segunda == [(lab.yo, "100.0000", "2026-06-01", None)]
    assert sorted(p["porcentaje"] for p in b2.titularidad_en(lab.cli, lab.pid, "2026-03-01")) == ["50.0000"] * 2
    assert [p["porcentaje"] for p in b2.titularidad_en(lab.cli, lab.pid, "2026-07-01")] == ["100.0000"]


def test_o_b1r_10a_inicio_visto_desfasado():
    """O-B1R-10 (TI-3): el inicio que vio el cliente no es el vigente -> VERSION_DESFASADA (TITULARIDAD_CAMBIADA)."""
    lab = Lab()
    _rechazo(lab, "VERSION_DESFASADA", "2020-01-01", status=409, motivo="TITULARIDAD_CAMBIADA", inicio="2026-10-01")


def test_o_b1r_10b_primera_version_vista_con_otras_partes():
    """O-B1R-10 (TI-3): la primera version vista con otras partes -> VERSION_DESFASADA (TITULARIDAD_CAMBIADA)."""
    lab = Lab()
    _rechazo(lab, "VERSION_DESFASADA", "2020-01-01", status=409, motivo="TITULARIDAD_CAMBIADA",
             vista=[{"actor_id": lab.yo, "porcentaje": "100.0000"}])
    _rechazo(lab, "VERSION_DESFASADA", "2020-01-01", status=409, version=lab.detalle()["row_version"] + 3)


def test_o_b1r_11_replay_identico():
    """O-B1R-11 (TI-2): replay identico tras el COMMIT -> idempotente y sin segunda auditoria."""
    lab = Lab()
    cuerpo = lab.peticion("2020-01-01")
    assert _ok(b.post(lab.cli, RUTA.format(lab.pid), cuerpo))["idempotente"] is False
    antes, auds = b.huella(TABLAS), lab.auditorias()
    assert _ok(b.post(lab.cli, RUTA.format(lab.pid), cuerpo))["idempotente"] is True
    assert b.huella(TABLAS) == antes and lab.auditorias() == auds


def test_o_b1r_12_misma_intencion_con_otro_contenido():
    """O-B1R-12 (TI-2): la misma intencion con otro nuevo_desde -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION."""
    lab = Lab()
    cuerpo = lab.peticion("2020-01-01")
    _ok(b.post(lab.cli, RUTA.format(lab.pid), cuerpo))
    antes, auds = b.huella(TABLAS), lab.auditorias()
    r = b.post(lab.cli, RUTA.format(lab.pid), {**cuerpo, "nuevo_desde": "2019-01-01"})
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", r.text
    assert b.huella(TABLAS) == antes and lab.auditorias() == auds


# ================================================================== O-B1R-15, 16: B3 e aislamiento
def test_o_b1r_15_propuesta_de_b3_leida_antes_y_enviada_despues():
    """O-B1R-15 (R1 §III.1bis 3): C-MEJ-01 relee la titularidad en la fecha del hecho BAJO LOCK despues de la
    correccion. Una propuesta leida antes (sin titularidad: partes vacias) no puede enviarse como «segun
    titularidad» (rechazo sin escribir) y una propuesta con partes que no son las releidas responde
    ATRIBUCION_PROPUESTA_DESFASADA sin escribir; la propuesta releida despues se acepta."""
    lab = Lab(adquisicion=None)
    leida = lab.vista("2026-05-15")
    assert leida["partes"] == []
    _ok(lab.corregir("2026-01-01"))
    antes = b.huella(TABLAS)
    vacia = lab.cuerpo(fecha="2026-05-15", atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": leida})
    r = lab.registrar(vacia)
    assert r.status_code == 422 and r.json()["codigo"] == "ENTRADA_INVALIDA", r.text
    ajena = {**leida, "partes": [{"actor_id": lab.yo, "porcentaje": "100.0000"}]}
    r = lab.registrar(lab.cuerpo(fecha="2026-05-15",
                                 atribucion={"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": ajena}))
    assert r.status_code == 409 and r.json()["codigo"] == "ATRIBUCION_PROPUESTA_DESFASADA", r.text
    assert b.huella(TABLAS) == antes
    lab.ok(lab.cuerpo(fecha="2026-05-15"))


def test_o_b1r_16_aislamiento_por_owner():
    """O-B1R-16: otro owner no corrige ni lee los afectados de P (AGREGADO_NO_ENCONTRADO, 0 filas de P)."""
    lab = Lab(adquisicion=None)
    lab.gasto_no_lo_se("2026-05-15")
    otro, _ = h.crear_tenant()
    cli_otro = h.cliente(otro, reloj=x5.reloj(RELOJ))
    cuerpo = lab.peticion("2020-01-01")
    antes = b.huella(TABLAS)
    r = b.post(cli_otro, RUTA.format(lab.pid), cuerpo)
    assert r.status_code == 404 and r.json()["codigo"] == "AGREGADO_NO_ENCONTRADO", r.text
    r = lab.afectados(cli=cli_otro)
    assert r.status_code == 404 and r.json()["codigo"] == "AGREGADO_NO_ENCONTRADO", r.text
    assert lab.pid not in r.text
    assert b.huella(TABLAS) == antes
    assert _ok(lab.afectados())["afectados"]["recuento"] == 1


# ================================================================== O-B1R-19: P0001 traducido
def _doble_una_fila(sesion, ids, nuevo):
    """Doble defectuoso: mueve SOLO la primera fila de la primera version y declara que movio todas."""
    sesion.ejecutar("UPDATE gapto.entidad_participaciones SET vigente_desde = %s WHERE id = %s", (nuevo, ids[0]))
    return len(ids)


def _doble_honesto(sesion, ids, nuevo):
    """Doble que mueve una fila y lo dice (el servicio exige len(ids))."""
    return sesion.ejecutar("UPDATE gapto.entidad_participaciones SET vigente_desde = %s WHERE id = %s",
                           (nuevo, ids[0]))


@pytest.mark.parametrize("doble", [_doble_una_fila, _doble_honesto], ids=["p0001_de_la_base", "filas_afectadas"])
def test_o_b1r_19_p0001_traducido_sin_cambios_ni_auditoria(monkeypatch, doble):
    """O-B1R-19 (Q-B1R-07; R-B1R-04): si solo se mueve una fila de la primera version, la suma 100 (P0001 de
    gapto.fn_check_participacion_suma(), en IMMEDIATE dentro del savepoint) o el recuento de filas se devuelven
    como 422 SUMA_NO_CUADRA (PRIMERA_VERSION_INCOMPLETA), nunca 500; estado y row_version identicos; 0 auditorias."""
    lab = Lab(adquisicion=None)
    v0 = lab.detalle()["row_version"]
    monkeypatch.setattr(repo, "adelantar_inicio_participaciones", doble)
    _rechazo(lab, "SUMA_NO_CUADRA", "2020-01-01", motivo="PRIMERA_VERSION_INCOMPLETA")
    assert lab.detalle()["row_version"] == v0
    assert [f[2] for f in lab.filas()] == ["2026-11-01", "2026-11-01"]


def test_o_b1r_19b_exclude_y_check_traducidos(monkeypatch):
    """O-B1R-19 (defensivo, §4.3.3): el EXCLUDE de solape y el CHECK de vigencia de entidad_participaciones (TI-5) se
    devuelven como SUMA_NO_CUADRA con motivo SOLAPE / INTERVALO, sin cambios."""
    lab = Lab(desde="2026-05-01", adquisicion=None)
    antes = h.cliente(lab.owner, reloj=x5.reloj("2026-05-20T12:00:00"))
    _ok(b.post(antes, f"/v1/propiedades/{lab.pid}/titularidad",
               b.cambio(b.leer(antes, lab.pid), b.solo_mia(desde="2026-06-01"))))

    def intervalo(sesion, ids, nuevo):   # la primera version mas alla de su cierre
        return sesion.ejecutar("UPDATE gapto.entidad_participaciones SET vigente_desde = '2026-06-15' "
                               "WHERE id = ANY(%s)", (list(ids),))
    monkeypatch.setattr(repo, "adelantar_inicio_participaciones", intervalo)
    _rechazo(lab, "SUMA_NO_CUADRA", "2026-01-01", motivo="INTERVALO")

    def solape(sesion, ids, nuevo):      # la segunda version dentro de la primera
        sesion.ejecutar("UPDATE gapto.entidad_participaciones SET vigente_desde = '2026-05-15' "
                        "WHERE entidad_id = (SELECT entidad_id FROM gapto.entidad_participaciones WHERE id = %s) "
                        "AND vigente_hasta IS NULL", (ids[0],))
        return len(ids)
    monkeypatch.setattr(repo, "adelantar_inicio_participaciones", solape)
    _rechazo(lab, "SUMA_NO_CUADRA", "2026-01-01", motivo="SOLAPE")


# ================================================================== O-B1R-20..22: cotas
def test_o_b1r_20_fecha_futura():
    """O-B1R-20 (TI-3b): nuevo_desde posterior a hoy (con la primera version aun mas tarde, fixture) -> FECHA_FUTURA."""
    lab = Lab(modo="SOLO_MIA", desde=HOY, adquisicion=None)
    _primera_futura(lab, "2026-12-01")
    _rechazo(lab, "FECHA_FUTURA", "2026-11-20")


def test_o_b1r_21_primera_version_futura_no_es_cambio_programado():
    """O-B1R-21 (HT2-17; TI-3b): con la primera version en el futuro, corregir a hoy se admite; con ademas una
    segunda version futura -> CAMBIO_PROGRAMADO_EXISTENTE."""
    lab = Lab(modo="SOLO_MIA", desde=HOY, adquisicion=None)
    _primera_futura(lab, "2026-12-01")
    assert lab.detalle()["inicio_titularidad"]["inicio_corregible"] is True
    _ok(lab.corregir(HOY))
    assert [(f[2], f[3]) for f in lab.filas()] == [(HOY, None)]
    otro = Lab(modo="SOLO_MIA", desde=HOY, adquisicion=None)
    _primera_futura(otro, "2026-12-01", segunda="2027-01-01")
    assert otro.detalle()["inicio_titularidad"]["inicio_corregible"] is False
    _rechazo(otro, "CAMBIO_PROGRAMADO_EXISTENTE", HOY, status=409)


def test_o_b1r_22_alta_con_desde_futuro_rechazada():
    """O-B1R-22 (L-01b): el alta con «Desde» = manana -> FECHA_FUTURA sin escribir nada (0 entidades, 0 actores,
    0 auditorias); con «Desde» = hoy -> 200."""
    owner, _, cli, _, _ = x5.entorno(RELOJ)
    ana = b.tercero(cli, "Ana")

    def recuento():
        return h.leer(owner, "SELECT (SELECT count(*) FROM gapto.entidades), (SELECT count(*) FROM "
                             "gapto.actores_financieros), (SELECT count(*) FROM gapto.auditoria WHERE tabla IN "
                             "('entidades', 'actores_financieros'))")[0]
    antes, huella = recuento(), b.huella(TABLAS)
    cuerpo = b.alta(b.compartida([b.yo("50"), b.de(ana, "50")], desde="2026-11-15"), fecha_adquisicion="2015-03-10")
    r = b.post(cli, "/v1/propiedades", cuerpo)
    assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA", r.text
    assert r.json()["mensaje"] == "La fecha «Desde» no puede ser posterior a hoy."
    assert recuento() == antes and b.huella(TABLAS) == huella
    p = b.crear(cli, b.alta(b.compartida([b.yo("50"), b.de(ana, "50")], desde=HOY)))
    assert p["titularidad"]["desde"] == HOY


# ================================================================== O-B1R-23: gastos afectados
def test_o_b1r_23_lectura_de_gastos_afectados_sin_escrituras():
    """O-B1R-23 (Q-B1R-09; HT2-18): solo los hechos de P con fecha en [nuevo_desde, inicio); sin nuevo_desde, todos
    los anteriores al inicio; nunca los de otra propiedad ni los >= inicio; 0 escrituras."""
    lab = Lab(adquisicion=None)
    otra = b.crear(lab.cli, b.alta(b.solo_mia("2020-01-01"), nombre="Garaje"))["id"]
    dentro = lab.gasto_no_lo_se("2026-05-15", "300.00")
    antiguo = lab.gasto_no_lo_se("2025-06-01", "120.00")
    lab.gasto_no_lo_se("2026-11-05", "50.00")                       # >= inicio: no entra
    lab.gasto_no_lo_se("2026-06-01", "80.00", pid=otra)              # otra propiedad: no entra
    antes, auds = b.huella(TABLAS), lab.auditorias()
    j = _ok(lab.afectados("2026-01-01"))["afectados"]
    assert j["inicio_vigente"] == "2026-11-01" and j["nuevo_desde"] == "2026-01-01" and j["recuento"] == 1
    assert [(x["hecho_id"], x["fecha"], x["importe"], x["clase"], x["atribucion"]) for x in j["hechos"]] == [
        (dentro, "2026-05-15", "300.00", "GASTO", "NO_LO_SE")]
    todos = _ok(lab.afectados())["afectados"]
    assert [x["hecho_id"] for x in todos["hechos"]] == [antiguo, dentro] and todos["recuento"] == 2
    assert b.huella(TABLAS) == antes and lab.auditorias() == auds
    assert _ok(lab.afectados(cli=None, pid=otra))["afectados"]["hechos"] == []


# ================================================================== O-B1R-24..26: lecturas que releen el inicio
def test_o_b1r_24_c_compra_01_tras_corregir():
    """O-B1R-24 (Q-B1R-10): la compra con escritura en la adquisicion no encuentra titularidad antes de corregir
    (TITULARIDAD_NO_DISPONIBLE_EN_FECHA, sin escribir) y, tras corregir el inicio a la adquisicion, se atribuye por la
    titularidad corregida. A3-0352: los consumidores de 0352 estan habilitados por el repositorio (L-06)."""
    assert habilitacion.CONSUMIDORES_0352_HABILITADOS is True
    lab = Lab(adquisicion="2015-03-10")
    escritura = "2015-03-10"
    partes = [{"actor_id": lab.yo, "porcentaje": "50.0000"}, {"actor_id": lab.ta, "porcentaje": "50.0000"}]

    def compra():
        return {"intencion_id": str(uuid.uuid4()), "row_version_esperada": lab.detalle()["row_version"],
                "fecha_escritura": escritura, "precio": "100000.00",
                "pagos_propios": [{"linea_id": str(uuid.uuid4()), "rol": "FIRMA", "cuenta_id": str(lab.c1),
                                   "fecha_pago": escritura, "importe": "100000.00"}],
                "gastos": [],
                "atribucion": {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
                    "criterio": "TITULARIDAD_EN_FECHA_ESCRITURA", "fecha_referencia": escritura,
                    "partes": sorted(partes, key=lambda p: p["actor_id"])}}}
    assert b2.titularidad_en(lab.cli, lab.pid, escritura) == []
    antes = b.huella(TABLAS)
    r = b.post(lab.cli, f"/v1/propiedades/{lab.pid}/compra", compra())
    assert r.status_code == 422 and r.json()["codigo"] == "TITULARIDAD_NO_DISPONIBLE_EN_FECHA", r.text
    assert b.huella(TABLAS) == antes
    _ok(lab.corregir(escritura))
    assert sorted(p["porcentaje"] for p in b2.titularidad_en(lab.cli, lab.pid, escritura)) == ["50.0000"] * 2
    _ok(b.post(lab.cli, f"/v1/propiedades/{lab.pid}/compra", compra()))
    atr = lab.sql("SELECT t.actor_id::text, t.criterio_atribucion, t.porcentaje_aplicado::text "
                  "FROM gapto.efecto_atribuciones t JOIN gapto.hecho_efectos e ON e.id = t.efecto_id "
                  "JOIN gapto.hecho_entidades x ON x.hecho_id = e.hecho_id AND x.entidad_id = %s "
                  "WHERE e.tipo_efecto = 'VALOR_ACTIVO' ORDER BY 1", (lab.pid,))
    assert atr and {a[1] for a in atr} == {"PARTICIPACION_ENTIDAD"} and {a[2] for a in atr} == {"50.0000"}
    assert habilitacion.CONSUMIDORES_0352_HABILITADOS is True


def test_o_b1r_25_adquisicion_desconocida_e_inicio_corregible():
    """O-B1R-25 (Q-B1R-04): con la adquisicion «No la se», corregir a 1990-01-01 se admite sin presentar la fecha como
    verificada ni crear o cambiar atribuciones; inicio_corregible verdadero con titularidad y falso con DESCONOCIDA o
    cambio programado."""
    lab = Lab(adquisicion=None)
    assert lab.detalle()["inicio_titularidad"]["inicio_corregible"] is True
    atribuciones = lab.sql("SELECT count(*) FROM gapto.efecto_atribuciones")[0][0]
    j = _ok(lab.corregir("1990-01-01"))["propiedad"]
    assert j["fecha_adquisicion"] is None
    assert not [k for k in json.dumps(j) .split('"') if "verific" in k.lower()]
    assert lab.sql("SELECT count(*) FROM gapto.efecto_atribuciones")[0][0] == atribuciones
    assert j["inicio_titularidad"] == {"inicio": "1990-01-01", "inicio_corregible": True, "primera_version": sorted(
        [{"actor_id": lab.yo, "porcentaje": "50.0000"}, {"actor_id": lab.ta, "porcentaje": "50.0000"}],
        key=lambda p: p["actor_id"])}
    assert Lab(modo="DESCONOCIDA").detalle()["inicio_titularidad"]["inicio_corregible"] is False


def test_o_b1r_26_c_prop_02_relee_el_nuevo_inicio():
    """O-B1R-26 (TI-6): tras corregir, adelantar la adquisicion queda acotado por el inicio nuevo."""
    lab = Lab(adquisicion=None)
    _ok(lab.corregir("2020-01-01"))
    prop = lab.detalle()
    r = b.post(lab.cli, f"/v1/propiedades/{lab.pid}/editar",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": prop["row_version"],
                "fecha_adquisicion": "2021-01-01"})
    assert r.status_code == 422 and r.json()["codigo"] == "ADQUISICION_POSTERIOR_A_TITULARIDAD", r.text
    r = b.post(lab.cli, f"/v1/propiedades/{lab.pid}/editar",
               {"intencion_id": str(uuid.uuid4()), "row_version_esperada": prop["row_version"],
                "fecha_adquisicion": "2020-01-01"})
    assert r.status_code == 200, r.text


def test_ti_0_linea_base_c_prop_03_no_adelanta():
    """TI-0: antes de B1-R, un gasto anterior al inicio no encuentra titularidad y C-PROP-03 no puede adelantarla
    (sigue siendo asi: P13 no cambia para C-PROP-03)."""
    lab = Lab(adquisicion=None)
    assert lab.propuesta("2026-05-15").json()["titularidad_disponible"] is False
    r = b.post(lab.cli, f"/v1/propiedades/{lab.pid}/titularidad",
               b.cambio(lab.detalle(), b.compartida([b.yo("50"), b.de(lab.t, "50")], desde="2026-01-01")))
    assert r.status_code == 422 and r.json()["codigo"] == "CAMBIO_RETROACTIVO_SIN_POLITICA", r.text


def test_dto_estricto_y_fechas():
    """Guarda 0: DTO estricto (campos de mas, fechas invalidas, version < 1) -> 422 ENTRADA_INVALIDA sin escribir."""
    lab = Lab()
    base = lab.peticion("2020-01-01")
    antes = b.huella(TABLAS)
    for malo in ({**base, "partes": []}, {**base, "nuevo_desde": "2020-02-30"}, {**base, "row_version_esperada": 0},
                 {k: v for k, v in base.items() if k != "inicio_visto"}):
        r = b.post(lab.cli, RUTA.format(lab.pid), malo)
        assert r.status_code == 422, r.text
    assert b.huella(TABLAS) == antes
