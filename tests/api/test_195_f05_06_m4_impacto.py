# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_195_f05_06_m4_impacto.py
# Ruta: tests/api/test_195_f05_06_m4_impacto.py
# Descripcion: Impacto de desactivar una capacidad (F05-06 M4 §4.4; D-CAP-03;
#   F05 §51.4 AJ-F0506P-09). La lista que ve A4 ANTES de confirmar coincide
#   exactamente con lo que pasa a «No disponible» en las lecturas de
#   plantillas (aviso de cuenta) y de preferencias (cuenta_disponible_hoy)
#   DESPUES de confirmar; reactivar lo restaura. Ni desactivar ni reactivar
#   reasignan nada: cuenta_default_id y row_version de plantillas y
#   preferencias no cambian y no se escribe auditoria sobre ellas. Las
#   capacidades de transferencia no afectan a plantillas ni preferencias.
# Version: 0.1.0 (F05-06 M4 F3)
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_02_helpers as ph
import vs01_api_helpers as h

CAPS = ("PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA", "TRANSFERIR_ENTRADA")


@pytest.fixture()
def escenario():
    owner, actor, cli = ph.tenant()
    nomina = ph.cuenta(owner, actor, nombre="Cuenta nómina", capacidades=CAPS)
    otra = ph.cuenta(owner, actor, nombre="Otra", capacidades=CAPS)
    tipos = cli.get("/v1/preferencias", headers=h.AUTH).json()["tipos"]
    hogar, ocio = ph.categoria(owner, "Hogar"), ph.categoria(owner, "Ocio")
    sueldo = ph.categoria(owner, "Sueldo", ambito="INGRESO")

    def plantilla(nombre, tipo, cuenta, activa=True):
        pid = uuid.uuid4()
        r = cli.post("/v1/plantillas", json={"id": str(pid), "nombre": nombre, "tipo_hecho_id": tipos[tipo],
                                             "cuenta_default_id": str(cuenta)}, headers=h.AUTH)
        assert r.status_code == 200, r.text
        if not activa:
            assert cli.post(f"/v1/plantillas/{pid}/desactivar", json={"row_version": 1}, headers=h.AUTH).status_code == 200
        return pid

    def preferencia(tipo, categoria, cuenta, activa=True):
        pid, r = ph.alta(cli, tipo_hecho_id=tipos[tipo], categoria_id=categoria, cuenta_default_id=cuenta)
        assert r.status_code == 200, r.text
        if not activa:
            assert ph.desactivar(cli, pid, 1).status_code == 200
        return pid

    plantilla("Alquiler", "GASTO", nomina)
    plantilla("Antigua", "GASTO", nomina, activa=False)
    plantilla("Nómina", "INGRESO", nomina)
    plantilla("Con otra", "GASTO", otra)
    preferencia("GASTO", hogar, nomina)
    preferencia("GASTO", ocio, nomina, activa=False)
    preferencia("INGRESO", sueldo, nomina)
    preferencia("GASTO", None, otra)
    return owner, cli, nomina


def _estado(cli):
    """(no disponibles, foto de lo persistido) segun las lecturas de Ajustes."""
    plantillas = cli.get("/v1/plantillas", headers=h.AUTH).json()["plantillas"]
    preferencias = cli.get("/v1/preferencias", headers=h.AUTH).json()["preferencias"]
    no_disp = ({("plantillas", p["id"]) for p in plantillas if any(a["campo"] == "cuenta" for a in p["avisos"])}
               | {("preferencias", p["id"]) for p in preferencias if p["cuenta_disponible_hoy"] is False})
    foto = ({p["id"]: (p["cuenta_default_id"], p["row_version"], p["enabled"]) for p in plantillas},
            {p["id"]: (p["cuenta_default_id"], p["row_version"], p["enabled"]) for p in preferencias})
    return no_disp, foto


def _auditoria_maestros(owner):
    return h.leer(owner, "SELECT count(*) FROM gapto.auditoria WHERE tabla IN ('plantillas_registro', "
                         "'preferencias_registro')")[0][0]


@pytest.mark.parametrize("capacidad", CAPS)
def test_lista_de_a4_igual_a_lo_que_pasa_a_no_disponible_y_reactivar_restaura(escenario, capacidad):
    owner, cli, nomina = escenario
    antes, foto = _estado(cli)
    assert antes == set()
    aud = _auditoria_maestros(owner)
    impacto = cli.get(f"/v1/cuentas/{nomina}/capacidades/{capacidad}/impacto", headers=h.AUTH).json()
    lista_a4 = ({("plantillas", x["plantilla_id"]) for x in impacto["plantillas"]}
                | {("preferencias", x["preferencia_id"]) for x in impacto["preferencias"]})

    assert cli.post(f"/v1/cuentas/{nomina}/capacidades/{capacidad}/desactivar", json={"row_version": 1},
                    headers=h.AUTH).status_code == 200
    despues, foto_despues = _estado(cli)
    assert despues - antes == lista_a4
    assert foto_despues == foto  # nada reasignado ni reescrito
    if capacidad == "PAGAR_GASTO":
        assert len(impacto["plantillas"]) == 2 and len(impacto["preferencias"]) == 2  # incluye las desactivadas
    elif capacidad == "RECIBIR_INGRESO":
        assert len(impacto["plantillas"]) == 1 and len(impacto["preferencias"]) == 1
    else:
        assert lista_a4 == set()

    assert cli.post(f"/v1/cuentas/{nomina}/capacidades/{capacidad}/activar", json={"row_version": 2},
                    headers=h.AUTH).status_code == 200
    restaurado, foto_final = _estado(cli)
    assert restaurado == antes and foto_final == foto
    assert _auditoria_maestros(owner) == aud
