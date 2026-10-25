# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_213_f04_r3_il1b_adaptadores_serial.py
# Ruta: tests/api/test_213_f04_r3_il1b_adaptadores_serial.py
# Descripcion: F04-R3 (F05-D050 §64.4; adenda 2 §D). Bateria SERIAL y
#   determinista, FUERA de la suite general: solo con
#   GAPTO_F04R3_CONCURRENCIA=1 (evidencia JSON si GAPTO_F04R3_EVIDENCIA apunta
#   a una carpeta). COMMIT real sobre base desechable. Nunca en paralelo.
#   Solo rutas EXPUESTAS, por las funciones del adaptador HTTP.
#
#   `il1b`: el advisory POR RAIZ es el PRIMER recurso de cada adaptador que
#      compone OP-22 (gasto pagado, ingreso cobrado y gasto compartido): una
#      sesion retiene el advisory (hashtext('gapto:OP22'), hashtext(<raiz>)),
#      se lanza el adaptador y, VISTO su backend esperando ese advisory en
#      pg_locks, otra sesion sondea sin esperar que NO retiene nada: el advisory
#      INVERSIONES del owner esta libre (pg_try_advisory_xact_lock) y la cuenta
#      admite FOR NO KEY UPDATE NOWAIT. Quien espera este advisory no retiene
#      ningun otro lock, luego no puede cerrar un ciclo (NOTA_ORDEN_LOCKS_IL1B).
#      Al liberar, el registro se crea (idempotente=False).
#   Mutantes M3-M5 de scripts/dev/mutantes_f04_r3.py (quitar el advisory del
#   adaptador y dejar solo el de OP-22): el adaptador queda esperando con la
#   cuenta y el advisory INVERSIONES tomados y el sondeo lo detecta.
# Version: 0.1.0 (F04-R3 il1b)
# ============================================================

from __future__ import annotations

import json
import os
import pathlib
import time
import uuid

import psycopg
import pytest

import f05_01_helpers as fh
import f05_06_m3_helpers as m3
import f05_06_m5_helpers as m
import vs01_api_helpers as h
from app.api.dto_registro import IntencionIngresoCobrado
from app.api.dto_reparto import IntencionGastoCompartido
from app.api.dto_vs01 import IntencionGastoPagado
from app.api.ejecucion_gasto_pagado import registrar_gasto_pagado
from app.api.ejecucion_registro import registrar_ingreso_cobrado
from app.api.ejecucion_reparto import registrar_gasto_compartido
from test_205_f05_06_m5_concurrencia_serial import OK, Paso, ctx  # arnes comun

pytestmark = pytest.mark.skipif(os.getenv("GAPTO_F04R3_CONCURRENCIA") != "1",
                                reason="bateria serial fuera de la suite general (GAPTO_F04R3_CONCURRENCIA=1)")

ESPERANDO_ADVISORY = (
    "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND NOT granted AND objsubid = 2 "
    "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
    "AND classid::bigint = (hashtext('gapto:OP22')::bigint & 4294967295) "
    "AND objid::bigint = (hashtext(%s::text)::bigint & 4294967295)"
)


def evidencia(nombre: str, datos: dict) -> None:
    carpeta = os.getenv("GAPTO_F04R3_EVIDENCIA")
    if carpeta:
        p = pathlib.Path(carpeta)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{nombre}.json").write_text(json.dumps(datos, indent=1, default=str, ensure_ascii=False),
                                          encoding="utf-8")


def _gasto_pagado(owner, cli, cta, raiz):
    cuerpo = h.intencion(cta, intencion_id=str(raiz), fecha_hecho="2026-10-07", importe="12.00",
                         contexto_id=str(m.x.contexto(cli)))
    i = IntencionGastoPagado(**cuerpo)
    return lambda: registrar_gasto_pagado(fh.unidad(), ctx(owner), i, m.x.reloj())


def _ingreso_cobrado(owner, cli, cta, raiz):
    i = IntencionIngresoCobrado(
        intencion_id=raiz, importe="12.00", moneda="EUR", fecha_hecho="2026-10-07", cuenta_id=cta,
        presupuestable=True, atribucion="SOLO_MIO", categoria={"estado": "SIN_CATEGORIA"}, nota=None,
        contexto_id=m.x.contexto(cli))
    return lambda: registrar_ingreso_cobrado(fh.unidad(), ctx(owner), i, m.x.reloj())


def _gasto_compartido(owner, cli, cta, raiz):
    tania, carlos = m3.persona(cli, "Tania"), m3.persona(cli, "Carlos")
    c = m3.cuerpo("44.50", pagado_por=m3.con_cuenta(cta), fecha=m3.FECHA_CENA, nota="Cena con amigos",
                  reparto=m3.repartir("14.50", (tania, "15.00", "SI"), (carlos, "15.00", "NO")), intencion_id=raiz)
    i = IntencionGastoCompartido(**c)
    return lambda: registrar_gasto_compartido(fh.unidad(), ctx(owner), i, m.x.reloj())


ADAPTADORES = {"gasto_pagado": _gasto_pagado, "ingreso_cobrado": _ingreso_cobrado,
               "gasto_compartido": _gasto_compartido}


def _sondeo_sin_esperar(dsn, owner, cta) -> dict:
    """Otra sesion: INVERSIONES libre y cuenta sin lock (NOWAIT)."""
    with psycopg.connect(dsn) as c:
        inversiones = c.execute("SELECT pg_try_advisory_xact_lock(hashtext('gapto:INVERSIONES'), "
                                "hashtext(%s::uuid::text))", (str(owner),)).fetchone()[0]
        c.rollback()
        try:
            c.execute("SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE NOWAIT", (cta,))
            cuenta = "LIBRE"
        except psycopg.errors.LockNotAvailable:
            cuenta = "RETENIDA"
        c.rollback()
    return {"inversiones": "LIBRE" if inversiones else "RETENIDO", "cuenta": cuenta}


@pytest.mark.parametrize("adaptador", list(ADAPTADORES))
def test_il1b_advisory_por_raiz_es_el_primer_recurso_del_adaptador(adaptador):
    owner, _actor, cli, cta, _ahorro = m.entorno()
    raiz = uuid.uuid4()
    fn = ADAPTADORES[adaptador](owner, cli, cta, raiz)
    dsn = h.dsn()
    traza: dict = {"adaptador": adaptador}
    retenedor = psycopg.connect(dsn)
    paso = Paso("ADAPTADOR", fn)
    try:
        retenedor.execute("SELECT pg_advisory_xact_lock(hashtext('gapto:OP22'), hashtext(%s::uuid::text))",
                          (str(raiz),))
        paso.start()
        fin = time.monotonic() + 15
        visto = []
        with psycopg.connect(dsn, autocommit=True) as monitor:
            while time.monotonic() < fin and paso.is_alive() and not visto:
                visto = monitor.execute(ESPERANDO_ADVISORY, (str(raiz),)).fetchall()
                time.sleep(0.01)
        traza["esperando_advisory"] = bool(visto)
        traza["sondeo"] = _sondeo_sin_esperar(dsn, owner, cta) if visto else None
    finally:
        retenedor.rollback()
        retenedor.close()
        paso.join(60)
    traza["vivo"] = paso.is_alive()
    traza["codigo"] = paso.codigo
    idempotente = getattr(paso.resultado, "idempotente", None)
    if idempotente is None and getattr(paso.resultado, "resultado", None) is not None:
        idempotente = paso.resultado.resultado.idempotente  # VS-01 envuelve el resultado de OP-22
    traza["idempotente"] = idempotente
    evidencia(f"il1b_primer_recurso_{adaptador}", traza)
    assert traza["esperando_advisory"] and not traza["vivo"], traza
    assert traza["sondeo"] == {"inversiones": "LIBRE", "cuenta": "LIBRE"}, traza
    assert traza["codigo"] == OK and traza["idempotente"] is False, traza
    assert m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (raiz,))[0] == 1
