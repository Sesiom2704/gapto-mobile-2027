# ============================================================
# GAPTO MOBILE 2027
# Fichero: f05_d052_c03_helpers.py
# Ruta: tests/api/f05_d052_c03_helpers.py
# Descripcion: Helpers de las pruebas del gasto propio reembolsable C-03
#   (F05 §66.A; F05-D052): entorno con cuenta y categoria, terceros por la API,
#   cuerpo de la intencion, cobro, lecturas fisicas como gapto_runtime y huella
#   de todo lo que la ruta podria escribir (oraculo «0 filas»). Datos
#   sinteticos; base desechable.
# Version: 0.1.0 (F05-D052 paso 2; F05 §66.A.11)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import f05_05_helpers as x
import f05_06_m3_helpers as m
import vs01_api_helpers as h

D = decimal.Decimal
RUTA = "/v1/intenciones/gasto-reembolsable"
FECHA = "2026-10-03"
FECHA_COBRO = "2026-10-08"


def entorno():
    """(owner, actor_self, cliente, cuenta corriente, cuenta ahorro, categoria «Combustible»)."""
    owner, actor, cli, cta, ahorro = x.entorno()
    return owner, actor, cli, cta, ahorro, x.categoria(owner, "Combustible")


def tercero(cli, nombre: str, naturaleza: str | None = "EMPRESA") -> uuid.UUID:
    return x.tercero(cli, nombre, naturaleza=naturaleza)


def cuerpo(cuenta, deudor, recuperable: str, *, importe: str = "60.00", fecha: str = FECHA, categoria=None,
           comercio=None, contexto_id=None, concepto: str | None = "Gasolina", financiacion=None,
           intencion_id=None, presupuestable: bool = True, magnitudes=None) -> dict:
    cat = {"estado": "SIN_CATEGORIA"} if categoria is None else {"estado": "CATEGORIA", "categoria_id": str(categoria)}
    if magnitudes:
        cat["magnitudes"] = [{"magnitud_id": str(mid), "valor": v} for mid, v in magnitudes]
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "concepto": concepto, "importe": importe,
         "moneda": "EUR", "fecha_hecho": fecha, "cuenta_id": str(cuenta), "presupuestable": presupuestable,
         "financiacion": financiacion or h.propuesta_self_100(importe), "categoria": cat,
         "reembolso": {"tercero_id": str(deudor), "importe": recuperable}}
    if comercio is not None:
        c["tercero_id"] = str(comercio)
    if contexto_id is not None:
        c["contexto_id"] = str(contexto_id)
    return c


def registrar(cli, c: dict):
    return cli.post(RUTA, json=c, headers=h.AUTH)


def cobro(cli, entidad, cuenta, importe: str, fecha: str = FECHA_COBRO):
    return m.cobro(cli, entidad, cuenta, importe, fecha=fecha)[1]


def leer(owner, sql: str, params: tuple = ()) -> list[tuple]:
    return h.leer(owner, sql, params)


def uno(owner, sql: str, params: tuple = ()):
    return m.uno(owner, sql, params)


def huella(owner) -> tuple:
    """Recuentos de TODO lo que C-03 podria escribir (incluidos actores, vinculos
    de contexto, terceros del hecho, magnitudes y auditoria)."""
    return m.huella(owner) + tuple(uno(owner, f"SELECT count(*) FROM gapto.{t}")[0] for t in (
        "hecho_terceros", "hecho_magnitudes", "entidades"))


def efectos(owner, hecho) -> list[tuple]:
    return sorted(leer(owner, "SELECT tipo_efecto, importe_delta, estado_atribucion, categoria_id "
                              "FROM gapto.hecho_efectos WHERE hecho_id = %s", (hecho,)), key=str)


def resultado_mes(cli, fecha: str = FECHA) -> dict:
    r = cli.get(f"/v1/inicio/resultado-mes?fecha={fecha}", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def reparto(cli, hecho):
    return cli.get(f"/v1/hechos/{hecho}/reparto", headers=h.AUTH)


def edicion(cli, hecho) -> dict:
    r = cli.get(f"/v1/hechos/{hecho}/edicion", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def editar_naturaleza(cli, tid, naturaleza: str | None):
    t = next(z for z in cli.get("/v1/terceros", headers=h.AUTH).json()["terceros"] if z["id"] == str(tid))
    r = cli.post(f"/v1/terceros/{tid}/editar", json={"row_version": t["row_version"], "nombre": t["nombre"],
                                                     "naturaleza": naturaleza}, headers=h.AUTH)
    assert r.status_code == 200, r.text
