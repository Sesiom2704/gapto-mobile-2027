# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_128_f04_r1_oraculos_propagacion.py
# Ruta: tests/backend/test_128_f04_r1_oraculos_propagacion.py
# Descripcion: F04-R1 (F04-D058 G-R1-D punto 4; AJ-F04R1-V11-04/05; mandato
#   F04-R1 IMPL v1.0 §F1.4 y §F4). ORACULOS de la propagacion de OP-02 y OP-03
#   a las previsiones sucesoras (`impacto_correccion_ancla`): seleccion de
#   sucesores, orden cronologico, campos y estados resultantes y revision
#   derivada, en escenarios SIN conflicto.
#   El oraculo se capturo sobre la base 5536bb3 (antes de G-R1-D) y se
#   versiona en tests/backend/fixtures/f04r1_oraculos_propagacion.json. Tras
#   reordenar la adquisicion de locks, el resultado debe coincidir
#   EXACTAMENTE; si difiere: STOP (mandato §F4).
#   Normalizacion: los UUID se sustituyen por etiquetas estables; se comparan
#   el resultado de la operacion (requiere_revision, motivo, afectadas,
#   propagadas, en orden) y, por previsión de las reglas implicadas: estado,
#   recalculo_automatico, fecha_objetivo_regla, ventana, importe_esperado,
#   row_version y numero de vinculos.
#   Regenerar (solo sobre la base, con decision): GAPTO_F04R1_GENERAR_ORACULOS=1.
# Version: 0.1.0 (F04-R1 IMPL F1)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import pathlib
import uuid

import pytest

from app.core.modelos import CamposCorreccion
from app.core.modelos_prevision import DatosRegla, DatosVinculo
from test_113_rodante_y_materializacion import crear_hecho, version_rodante

D = decimal.Decimal
F = dt.date.fromisoformat
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "f04r1_oraculos_propagacion.json"


def _regla(servicio_reglas, servicio_previsiones, contexto, nombre: str, desde: str) -> tuple[uuid.UUID, uuid.UUID]:
    regla_id, cabeza = uuid.uuid4(), uuid.uuid4()
    servicio_reglas.crear_regla(contexto, DatosRegla(regla_id=regla_id, nombre=nombre),
                                version_rodante(vigente_desde=F(desde)))
    servicio_previsiones.generar_rodante(contexto, regla_id=regla_id, uuid_nuevo=cabeza)
    return regla_id, cabeza


def _vincular(servicio_previsiones, contexto, prevision_id, hecho_id, importe="45.0000", *, sucesor=None):
    estado = servicio_previsiones.estado_de(contexto, prevision_id)
    servicio_previsiones.vincular_realidad(
        contexto, prevision_id=prevision_id, row_version_esperada=estado.row_version,
        datos=DatosVinculo(vinculo_id=uuid.uuid4(), hecho_id=hecho_id, importe_asignado=D(importe),
                           marcar_realizada=sucesor is not None),
        uuid_sucesor=sucesor)


def _foto(admin, owner, reglas: list[uuid.UUID], etiquetas: dict) -> list[dict]:
    with admin.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute(
            "SELECT p.id, p.estado, p.recalculo_automatico, p.fecha_objetivo_regla, p.fecha_esperada_desde, "
            "p.fecha_esperada_hasta, p.importe_esperado, p.row_version, "
            "(SELECT count(*) FROM gapto.prevision_hechos pv WHERE pv.prevision_id = p.id) "
            "FROM gapto.previsiones p JOIN gapto.regla_versiones v ON v.id = p.regla_version_id "
            "WHERE v.regla_id = ANY(%s) ORDER BY p.fecha_objetivo_regla, p.id", (reglas,))
        filas = cur.fetchall()
    salida = [{"prevision": etiquetas.get(f[0], "?"), "estado": f[1], "recalculo": f[2], "objetivo": str(f[3]),
               "desde": str(f[4]), "hasta": str(f[5]), "importe": str(f[6]), "row_version": f[7], "vinculos": f[8]}
              for f in filas]
    # Orden estable: dos previsiones con el mismo objetivo se ordenarian por su UUID (aleatorio).
    return sorted(salida, key=lambda x: (x["objetivo"], x["prevision"]))


def _resultado(r, etiquetas: dict) -> dict:
    return {"requiere_revision": r.requiere_revision, "motivo": r.motivo_revision,
            "afectadas": [etiquetas.get(x, "?") for x in r.previsiones_afectadas],
            "propagadas": [etiquetas.get(x, "?") for x in r.previsiones_propagadas]}


def _corregir_fecha(servicio, contexto, admin, hecho_id, fecha: str):
    from test_138_f04_r1_discriminantes import version_hecho
    return servicio.corregir_hecho(contexto, hecho_id=hecho_id,
                                   row_version_esperada=version_hecho(admin, contexto.owner_user_id, hecho_id),
                                   campos=CamposCorreccion(fecha_hecho=F(fecha)), motivo="fecha mal capturada")


def _escenario(nombre, servicio, servicio_reglas, servicio_previsiones, contexto, admin) -> dict:
    """Construye el escenario `nombre`, ejecuta OP-02/OP-03 y devuelve el oraculo normalizado."""
    from test_138_f04_r1_discriminantes import anular

    et: dict = {}
    if nombre == "rodante_una_realizada":
        regla, cabeza = _regla(servicio_reglas, servicio_previsiones, contexto, "Gimnasio", "2027-01-10")
        s1 = uuid.uuid4()
        h = crear_hecho(servicio, contexto, F("2027-02-02"))
        _vincular(servicio_previsiones, contexto, cabeza, h, sucesor=s1)
        et.update({cabeza: "cabeza", s1: "s1"})
        r = _corregir_fecha(servicio, contexto, admin, h, "2027-02-09")
        reglas = [regla]
    elif nombre == "rodante_varias_realizadas_mismo_ancla":
        regla, cabeza = _regla(servicio_reglas, servicio_previsiones, contexto, "Gimnasio", "2027-01-10")
        s1, s2 = uuid.uuid4(), uuid.uuid4()
        h = crear_hecho(servicio, contexto, F("2027-02-02"), importe=D("100.0000"))
        _vincular(servicio_previsiones, contexto, cabeza, h, sucesor=s1)
        # El ancla H realiza tambien s1; un segundo hecho mas tardio hace avanzar la cadena (s2 nace).
        _vincular(servicio_previsiones, contexto, s1, h)
        _vincular(servicio_previsiones, contexto, s1, crear_hecho(servicio, contexto, F("2027-03-10")), sucesor=s2)
        et.update({cabeza: "cabeza", s1: "s1", s2: "s2"})
        r = _corregir_fecha(servicio, contexto, admin, h, "2027-02-09")
        reglas = [regla]
    elif nombre == "sucesores_de_reglas_distintas":
        ra, ca = _regla(servicio_reglas, servicio_previsiones, contexto, "Gimnasio A", "2027-01-10")
        rb, cb = _regla(servicio_reglas, servicio_previsiones, contexto, "Gimnasio B", "2027-01-17")
        sa, sb = uuid.uuid4(), uuid.uuid4()
        h = crear_hecho(servicio, contexto, F("2027-02-02"), importe=D("100.0000"))
        _vincular(servicio_previsiones, contexto, ca, h, sucesor=sa)
        _vincular(servicio_previsiones, contexto, cb, h, sucesor=sb)
        et.update({ca: "cabeza_a", cb: "cabeza_b", sa: "s_a", sb: "s_b"})
        r = _corregir_fecha(servicio, contexto, admin, h, "2027-02-09")
        reglas = [ra, rb]
    elif nombre == "sucesor_con_realidad":
        regla, cabeza = _regla(servicio_reglas, servicio_previsiones, contexto, "Gimnasio", "2027-01-10")
        s1 = uuid.uuid4()
        h = crear_hecho(servicio, contexto, F("2027-02-02"))
        _vincular(servicio_previsiones, contexto, cabeza, h, sucesor=s1)
        _vincular(servicio_previsiones, contexto, s1, crear_hecho(servicio, contexto, F("2027-03-10")))
        et.update({cabeza: "cabeza", s1: "s1"})
        r = _corregir_fecha(servicio, contexto, admin, h, "2027-02-20")
        reglas = [regla]
    elif nombre == "sin_cambio_de_ventana":
        regla, cabeza = _regla(servicio_reglas, servicio_previsiones, contexto, "Gimnasio", "2027-01-10")
        s1 = uuid.uuid4()
        h = crear_hecho(servicio, contexto, F("2027-02-02"))
        _vincular(servicio_previsiones, contexto, cabeza, h, sucesor=s1)
        et.update({cabeza: "cabeza", s1: "s1"})
        from test_138_f04_r1_discriminantes import version_hecho
        r = servicio.corregir_hecho(contexto, hecho_id=h,
                                    row_version_esperada=version_hecho(admin, contexto.owner_user_id, h),
                                    campos=CamposCorreccion(concepto="Cuota"), motivo="concepto")
        reglas = [regla]
    elif nombre == "anulacion":
        ra, ca = _regla(servicio_reglas, servicio_previsiones, contexto, "Gimnasio A", "2027-01-10")
        rb, cb = _regla(servicio_reglas, servicio_previsiones, contexto, "Gimnasio B", "2027-01-17")
        sa, sb = uuid.uuid4(), uuid.uuid4()
        h = crear_hecho(servicio, contexto, F("2027-02-02"), importe=D("100.0000"))
        _vincular(servicio_previsiones, contexto, ca, h, sucesor=sa)
        _vincular(servicio_previsiones, contexto, cb, h, sucesor=sb)
        et.update({ca: "cabeza_a", cb: "cabeza_b", sa: "s_a", sb: "s_b"})
        r = anular(servicio, contexto, admin, h)
        reglas = [ra, rb]
    else:  # pragma: no cover
        raise AssertionError(nombre)
    return {"resultado": _resultado(r, et), "previsiones": _foto(admin, contexto.owner_user_id, reglas, et)}


ESCENARIOS = ["rodante_una_realizada", "rodante_varias_realizadas_mismo_ancla", "sucesores_de_reglas_distintas",
              "sucesor_con_realidad", "sin_cambio_de_ventana", "anulacion"]


@pytest.mark.parametrize("nombre", ESCENARIOS)
def test_oraculo_de_propagacion(nombre, servicio, servicio_reglas, servicio_previsiones, contexto, admin):
    obtenido = _escenario(nombre, servicio, servicio_reglas, servicio_previsiones, contexto, admin)
    if os.getenv("GAPTO_F04R1_GENERAR_ORACULOS") == "1":
        datos = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}
        datos[nombre] = obtenido
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(datos, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        pytest.skip("oraculo generado")
    esperado = json.loads(FIXTURE.read_text(encoding="utf-8"))[nombre]
    assert obtenido == esperado
