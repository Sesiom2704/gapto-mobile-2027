# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_01_b3_helpers.py
# Ruta: tests/api/f06_01_b3_helpers.py
# Descripcion: Utilidades de los tests de F06-01 B3 (obras y gastos de una propiedad): laboratorio con propiedad
#   P compartida YO 50 / T 50 desde 2026-01-01 y YO 100 desde 2026-06-01 (cambio de C-PROP-03 hecho con un reloj
#   anterior, siembra del §A.8 de los oraculos v0.7), cuenta C1 solo del usuario, C2 compartida YO 50 / T 50,
#   categoria de gasto; peticiones de C-MEJ-01/02/03 y lecturas por HTTP como gapto_runtime con RLS.
#   Los fixtures declarados (SQL como gapto_owner con la GUC del tenant) solo construyen estados que las rutas
#   no producen (O5.10, O5.11, O5.14b, O5.38, O9.11).
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# ============================================================

from __future__ import annotations

import uuid

import f05_05_helpers as x5
import f06_01_b1_helpers as b
import f06_01_b2_helpers as b2
import vs01_api_helpers as h

HOY = b.HOY
RELOJ_ANTES = "2026-05-20T12:00:00"
TABLAS_B3 = ("hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_entidades", "hecho_relaciones",
             "movimientos_tesoreria", "hecho_movimientos_tesoreria", "propiedades", "entidades", "auditoria",
             "entidad_participaciones", "derechos_obligaciones_financieras", "hecho_aportaciones_pago",
             "hecho_magnitudes")
LIMITACION = ("Los hechos de gasto de propiedad con una posición de deuda asociada no admiten actualmente la "
              "operación Corregir clase. No existe en este alcance una vía soportada para corregir su clase "
              "conservando la posición. Esta capacidad queda pendiente de una corrección de clase para hechos con "
              "varios efectos.")


def huella() -> str:
    return b.huella(TABLAS_B3)


def intencion_vigente(efecto_id) -> str:
    return str(uuid.uuid5(uuid.UUID(str(efecto_id)), "gapto.f06.cmej03.intencion"))


def marca(hecho_id, prefijo: str = "gapto.f06.gasto_propiedad.") -> uuid.UUID:
    return uuid.uuid5(uuid.UUID(str(hecho_id)), prefijo + "afecta_a")


class Lab:
    """Owner con P (YO 50 / T 50 desde 01-01; YO 100 desde 06-01), C1 propia, C2 compartida con T y categoria."""

    def __init__(self, *, naturaleza_t: str = "PERSONA", cambio: bool = True, titularidad: dict | None = None):
        self.owner, self.actor, self.cli, self.c1, _ = x5.entorno(b.RELOJ)
        self.t = b.tercero(self.cli, "Tomás", naturaleza=naturaleza_t)
        tit = titularidad or b.compartida([b.yo("50"), b.de(self.t, "50")], desde="2026-01-01")
        prop = b.crear(self.cli, b.alta(tit, fecha_adquisicion="2025-12-01"))
        self.pid = prop["id"]
        partes = prop["titularidad"]["partes"]
        self.yo = next((x["actor_id"] for x in partes if x["yo"]), str(self.actor))
        self.ta = next((x["actor_id"] for x in partes if not x["yo"]), None)
        if cambio and self.ta:
            antes = h.cliente(self.owner, reloj=x5.reloj(RELOJ_ANTES))
            r = b.post(antes, f"/v1/propiedades/{self.pid}/titularidad",
                       b.cambio(b.leer(antes, self.pid), b.solo_mia(desde="2026-06-01")))
            assert r.status_code == 200, r.text
        self.c2 = h.crear_cuenta(self.owner, [(self.actor, 50), (uuid.UUID(self.ta), 50)]) if self.ta else self.c1
        self.cat = x5.categoria(self.owner, "Hogar · Reparaciones")

    def sql(self, sql: str, params: tuple = ()) -> list[tuple]:
        return h.leer(self.owner, sql, params)

    def version_propiedad(self) -> int:
        return b.leer(self.cli, self.pid)["row_version"]

    # ---------------------------------------------------------------- lecturas
    def propuesta(self, fecha: str, cuenta=None):
        params = {"fecha": fecha}
        if cuenta is not None:
            params["cuenta_id"] = str(cuenta)
        return self.cli.get(f"/v1/propiedades/{self.pid}/propuesta-gasto", params=params, headers=h.AUTH)

    def vista(self, fecha: str) -> dict:
        r = self.propuesta(fecha)
        assert r.status_code == 200, r.text
        partes = [{"actor_id": p["actor_id"], "porcentaje": p["porcentaje"]} for p in r.json()["partes"]]
        return {"criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": fecha, "partes": partes}

    def gasto(self, hecho_id, pid=None):
        return self.cli.get(f"/v1/propiedades/{pid or self.pid}/gastos/{hecho_id}", headers=h.AUTH)

    def leer_gasto(self, hecho_id) -> dict:
        r = self.gasto(hecho_id)
        assert r.status_code == 200, r.text
        return r.json()

    def impacto(self, hecho_id, clase: str, presupuestable: bool | None = None) -> dict:
        params = {"clase_nueva": clase}
        if presupuestable is not None:
            params["presupuestable"] = "true" if presupuestable else "false"
        r = self.cli.get(f"/v1/propiedades/{self.pid}/gastos/{hecho_id}/impacto-correccion", params=params,
                         headers=h.AUTH)
        assert r.status_code == 200, r.text
        return r.json()["comparacion"]

    # ---------------------------------------------------------------- C-MEJ-01
    def cuerpo(self, *, clase: str = "REPARACION", importe: str = "300.00", fecha: str = "2026-05-15", cuenta=None,
               atribucion: dict | None = None, deuda: list | None = None, derechos: list | None = None,
               aportacion: str | None = None, intencion_id=None, pid=None, **extra) -> dict:
        cuerpo = {"intencion_id": str(intencion_id or uuid.uuid4()), "propiedad_id": str(pid or self.pid),
                  "clase": clase, "importe": importe, "fecha_hecho": fecha, "cuenta_id": str(cuenta or self.c1),
                  "atribucion": atribucion or {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": self.vista(fecha)}}
        if clase != "MEJORA":
            cuerpo["categoria_id"] = str(self.cat)
            cuerpo["presupuestable"] = True
        partes = cuerpo["atribucion"].get("partes") or (cuerpo["atribucion"].get("propuesta_vista") or {}).get("partes") or []
        otros = [p["actor_id"] for p in partes if p["actor_id"] != self.yo]
        cuerpo["deuda"] = deuda if deuda is not None else [{"actor_id": a, "me_debe": "NO"} for a in otros]
        cuerpo["derechos_confirmados"] = derechos or []
        if aportacion is not None:
            cuerpo["aportacion_indicada"] = aportacion
        cuerpo.update(extra)
        return cuerpo

    def registrar(self, cuerpo: dict, cli=None):
        return (cli or self.cli).post("/v1/intenciones/gasto-propiedad", json=cuerpo, headers=h.AUTH)

    def ok(self, cuerpo: dict) -> dict:
        r = self.registrar(cuerpo)
        assert r.status_code == 200, r.text
        return r.json()

    # ---------------------------------------------------------------- C-MEJ-02
    def cuerpo_mh(self, *, importe: str = "3000.00", fecha: str = "2026-02-10", atribucion: dict | None = None,
                  deuda: list | None = None, intencion_id=None, version: int | None = None) -> dict:
        return {"intencion_id": str(intencion_id or uuid.uuid4()),
                "row_version_esperada": self.version_propiedad() if version is None else version,
                "descripcion": "Cocina", "importe": importe, "fecha": fecha,
                "atribucion": atribucion or {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": self.vista(fecha)},
                "deuda": deuda or []}

    def mejora_historica(self, cuerpo: dict):
        return self.cli.post(f"/v1/propiedades/{self.pid}/mejoras-historicas", json=cuerpo, headers=h.AUTH)

    # ---------------------------------------------------------------- C-MEJ-03
    def correccion(self, hecho_id, clase: str, *, presupuestable: bool | None = None, categoria=None, motivo="Error",
                   intencion_id=None, version: int | None = None, comparacion: dict | None = None) -> dict:
        g = self.leer_gasto(hecho_id)
        cuerpo = {"intencion_id": str(intencion_id or g["intencion_correccion_id"]),
                  "row_version_esperada": g["row_version"] if version is None else version, "clase_nueva": clase,
                  "motivo": motivo,
                  "comparacion_vista": comparacion or self.impacto(hecho_id, clase, presupuestable)}
        if clase != "MEJORA":
            cuerpo["categoria_id"] = str(categoria or self.cat)
            cuerpo["presupuestable"] = presupuestable
        elif presupuestable is not None:
            cuerpo["presupuestable"] = presupuestable
        return cuerpo

    def corregir(self, hecho_id, cuerpo: dict, pid=None, cli=None):
        return (cli or self.cli).post(f"/v1/propiedades/{pid or self.pid}/gastos/{hecho_id}/corregir-clase",
                                      json=cuerpo, headers=h.AUTH)

    def efectos(self, hecho_id) -> list[tuple]:
        return self.sql("SELECT id, tipo_efecto, importe_delta::text, categoria_id, causa_valor_activo, "
                        "estado_atribucion FROM gapto.hecho_efectos WHERE hecho_id = %s ORDER BY id", (hecho_id,))

    def hecho(self, hecho_id) -> tuple:
        return self.sql("SELECT th.codigo, h.row_version, h.presupuestable, h.estado_localizacion, h.estado "
                        "FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "
                        "WHERE h.id = %s", (hecho_id,))[0]

    def posiciones(self, hecho_id) -> list[tuple]:
        return self.sql("SELECT d.entidad_id, d.tipo, d.contraparte_actor_id FROM gapto.hecho_entidades v "
                        "JOIN gapto.derechos_obligaciones_financieras d ON d.entidad_id = v.entidad_id "
                        "WHERE v.hecho_id = %s AND v.efecto_id IS NOT NULL", (hecho_id,))


def como_owner(owner, sql: str, params: tuple = ()) -> None:
    b2.como_owner(owner, sql, params)


def auditorias(owner, request_id) -> list[tuple]:
    return b2.auditorias(owner, request_id)
