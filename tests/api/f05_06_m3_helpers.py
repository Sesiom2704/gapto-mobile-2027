# ============================================================
# GAPTO MOBILE 2027
# Fichero: f05_06_m3_helpers.py
# Ruta: tests/api/f05_06_m3_helpers.py
# Descripcion: Helpers de los tests de F05-06 M3 (reparto, pagador real y
#   posiciones): personas y empresas por la API de terceros, cuerpos del
#   gasto compartido (peluqueria y cena de GD-3), cobro/pago/perdon, «Pendiente
#   con» y «Corregir reparto», y lecturas fisicas como gapto_runtime.
#   Datos sinteticos; base desechable.
# Version: 0.1.0 (F05-06 M3 §A6)
# ============================================================

from __future__ import annotations

import decimal
import uuid

import f05_05_helpers as x
import vs01_api_helpers as h

D = decimal.Decimal
GASTO_COMPARTIDO = "/v1/intenciones/gasto-compartido"
FECHA = "2026-10-03"
FECHA_CENA = "2026-10-09"


def entorno():
    """(owner, actor_self, cliente, cuenta corriente, cuenta ahorro)."""
    return x.entorno()


def persona(cli, nombre: str = "Tania") -> uuid.UUID:
    return x.tercero(cli, nombre, naturaleza="PERSONA")


def empresa(cli, nombre: str = "Peluquería Lola") -> uuid.UUID:
    return x.tercero(cli, nombre, naturaleza="EMPRESA")


def cuerpo(importe: str, *, pagado_por: dict, reparto: dict, fecha: str = FECHA, tercero_id=None,
           nota: str | None = None, categoria=None, intencion_id=None, presupuestable: bool = True) -> dict:
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "importe": importe, "moneda": "EUR",
         "fecha_hecho": fecha, "presupuestable": presupuestable,
         "categoria": categoria or {"estado": "SIN_CATEGORIA"}, "pagado_por": pagado_por, "reparto": reparto,
         "nota": nota}
    if tercero_id is not None:
        c["tercero_id"] = str(tercero_id)
    return c


def con_cuenta(cuenta) -> dict:
    return {"tipo": "CUENTA", "cuenta_id": str(cuenta)}


def por_persona(tercero, le_debo: str = "SI") -> dict:
    return {"tipo": "PERSONA", "tercero_id": str(tercero), "le_debo": le_debo}


SOLO_MIO = {"modo": "SOLO_MIO"}


def repartir(mi_parte: str | None, *partes: tuple) -> dict:
    """partes: (tercero, importe|None, me_debe|None)."""
    return {"modo": "REPARTIR", "mi_parte": mi_parte,
            "partes": [{"tercero_id": str(t), "importe": imp, "me_debe": md} for t, imp, md in partes]}


def registrar(cli, c: dict):
    return cli.post(GASTO_COMPARTIDO, json=c, headers=h.AUTH)


def peluqueria(cli, tania, *, le_debo: str = "SI", importe: str = "15.00", tercero_id=None):
    """A1/A2: gasto mio que pago Tania; deuda solo con «SI»."""
    c = cuerpo(importe, pagado_por=por_persona(tania, le_debo), reparto=SOLO_MIO, tercero_id=tercero_id,
               nota="Peluquería")
    return c, registrar(cli, c)


def cena(cli, cuenta, tania, carlos, *, mi_parte: str | None = "14.50", tania_debe: str = "SI"):
    """B1-B4: la pago yo y se reparte entre tres; Carlos invitado."""
    c = cuerpo("44.50", pagado_por=con_cuenta(cuenta), fecha=FECHA_CENA, nota="Cena con amigos",
               reparto=repartir(mi_parte, (tania, "15.00", tania_debe), (carlos, "15.00", "NO")))
    return c, registrar(cli, c)


def leer(owner, sql: str, params: tuple = ()) -> list[tuple]:
    return h.leer(owner, sql, params)


def uno(owner, sql: str, params: tuple = ()):
    filas = h.leer(owner, sql, params)
    return filas[0] if filas else None


def actor_de(owner, tercero) -> uuid.UUID | None:
    fila = uno(owner, "SELECT id FROM gapto.actores_financieros WHERE tercero_id = %s", (tercero,))
    return None if fila is None else fila[0]


def efectos(owner, hecho) -> dict[str, D]:
    return {t: imp for t, imp in leer(owner, "SELECT tipo_efecto, importe_delta FROM gapto.hecho_efectos "
                                             "WHERE hecho_id = %s", (hecho,))}


def atribuciones(owner, hecho) -> dict:
    return {actor: imp for actor, imp in leer(
        owner, "SELECT a.actor_id, a.importe_atribuido FROM gapto.efecto_atribuciones a "
               "JOIN gapto.hecho_efectos e ON e.id = a.efecto_id WHERE e.hecho_id = %s AND e.tipo_efecto = 'GASTO'",
        (hecho,))}


def posiciones(owner, hecho) -> list[tuple]:
    """(tipo, contraparte, importe del efecto vinculado) de las posiciones del hecho."""
    return sorted(leer(
        owner, "SELECT p.tipo, p.contraparte_actor_id, e.importe_delta FROM gapto.hecho_entidades v "
               "JOIN gapto.derechos_obligaciones_financieras p ON p.entidad_id = v.entidad_id "
               "JOIN gapto.hecho_efectos e ON e.id = v.efecto_id WHERE v.hecho_id = %s", (hecho,)), key=str)


def entidad_de_posicion(owner, hecho) -> uuid.UUID:
    return uno(owner, "SELECT v.entidad_id FROM gapto.hecho_entidades v JOIN gapto.derechos_obligaciones_financieras p "
                      "ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s", (hecho,))[0]


def huella(owner) -> tuple:
    """Recuentos de todo lo que M3 podria escribir (oraculo «sin efectos»)."""
    return tuple(uno(owner, f"SELECT count(*) FROM gapto.{t}")[0] for t in (
        "hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_participantes", "hecho_aportaciones_pago",
        "movimientos_tesoreria", "hecho_movimientos_tesoreria", "derechos_obligaciones_financieras",
        "hecho_entidades", "actores_financieros", "hecho_relaciones", "auditoria"))


def cobro(cli, entidad, cuenta, importe: str, fecha: str = "2026-10-10", accion: str = "cobro", intencion_id=None):
    c = {"intencion_id": str(intencion_id or uuid.uuid4()), "importe": importe, "cuenta_id": str(cuenta), "fecha": fecha}
    return c, cli.post(f"/v1/posiciones/{entidad}/{accion}", json=c, headers=h.AUTH)


def perdon(cli, entidad, importe: str, fecha: str = "2026-10-10"):
    c = {"intencion_id": str(uuid.uuid4()), "importe": importe, "fecha": fecha}
    return c, cli.post(f"/v1/posiciones/{entidad}/perdon", json=c, headers=h.AUTH)


def pendiente(cli, tercero):
    return cli.get(f"/v1/terceros/{tercero}/pendiente", headers=h.AUTH)


def corregir(cli, hecho, row_version: int, partes: dict, motivo: str = "Otro dato mal elegido"):
    c = {"row_version": row_version, "motivo": motivo,
         "partes": [{"atribucion_id": str(a), "importe": imp} for a, imp in partes.items()]}
    return cli.post(f"/v1/hechos/{hecho}/reparto", json=c, headers=h.AUTH)


def version(owner, hecho) -> int:
    return uno(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho,))[0]


def atribucion_de(owner, hecho, actor) -> uuid.UUID:
    return uno(owner, "SELECT a.id FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id = a.efecto_id "
                      "WHERE e.hecho_id = %s AND e.tipo_efecto = 'GASTO' AND a.actor_id = %s", (hecho, actor))[0]
