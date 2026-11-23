# ============================================================
# GAPTO MOBILE 2027
# Fichero: ambos.py
# Ruta: backend/app/preferencias/ambos.py
# Descripcion: «Ambos» al recordar (F06 T6 S5, N1; dictamen 1 Q2/A3; DF-10, DF-13; F09 0.55
#   §12.107.3). Dos preferencias INDEPENDIENTES (una del tercero y otra de la categoria) en UNA
#   transaccion de la UdT, con los writers de siempre (`servicio.alta` / `servicio.editar`, con su
#   auditoria). Sin ambito combinado y sin precedencia implicita nueva: el resolver de siempre.
#
#   Secuencia: advisory (PREFERENCIAS, owner) -> PREFLIGHT de las dos operaciones antes de escribir
#   (validaciones del writer unico, identidad del alta o version de la edicion, empate de §41.4
#   contra las habilitadas y entre las dos operaciones; se recogen TODOS los conflictos) ->
#   escrituras. Si una escritura falla tras el preflight, `FalloAmbos` revierte la transaccion
#   entera: o las dos o ninguna, nunca un resultado parcial.
#   Contrato completo: evidencia T6 Q2_s5/S5_CONTRATO.md.
# Version: 0.1.0 (F06 T6 · S5)
# ============================================================

from __future__ import annotations

from typing import Any

from app.comun.fecha_funcional import Reloj, reloj_sistema
from app.core.unidad_trabajo import SesionMotor
from app.preferencias import repositorio as repo
from app.preferencias import servicio as srv
from app.preferencias.resolver import especificidad, pueden_coincidir

AMBITOS = ("TERCERO", "CATEGORIA")
CAMPOS_VALOR = ("cuenta_default_id", "presupuestable_default")
#: Campo afectado por cada codigo de rechazo del writer (para decir al usuario que choca).
_CAMPOS_DE_CODIGO = {
    srv.CUENTA_NO_ELEGIBLE: ["cuenta_default_id"],
    srv.CATEGORIA_NO_ELEGIBLE: ["categoria_id"],
    srv.TERCERO_NO_ELEGIBLE: ["tercero_id"],
    srv.SIN_VALOR: list(CAMPOS_VALOR),
}


class FalloAmbos(Exception):
    """Una escritura fallo tras el preflight: la UdT revierte la transaccion entera."""

    def __init__(self, ambito: str, rechazo: srv.Rechazo) -> None:
        super().__init__(f"{ambito}: {rechazo.codigo}")
        self.ambito = ambito
        self.rechazo = rechazo


def _valores(op: dict[str, Any]) -> dict[str, Any]:
    c = op["contenido"]
    return srv._valores(tipo_hecho_id=c.get("tipo_hecho_id"), categoria_id=c.get("categoria_id"),
                        tercero_id=c.get("tercero_id"), entidad_id=c.get("entidad_id"),
                        cuenta_default_id=c.get("cuenta_default_id"),
                        presupuestable_default=c.get("presupuestable_default"),
                        prioridad=c.get("prioridad", srv.PRIORIDAD_V1))


def _campos_distintos(v: dict[str, Any], q: dict[str, Any]) -> list[str]:
    return [k for k in CAMPOS_VALOR if v[k] is not None and q[k] is not None and v[k] != q[k]]


def _ambito_coherente(op: dict[str, Any], v: dict[str, Any]) -> bool:
    if op["ambito"] == "TERCERO":
        return v["tercero_id"] is not None and v["categoria_id"] is None
    return v["categoria_id"] is not None and v["tercero_id"] is None


def preflight(sesion: SesionMotor, operaciones: list[dict[str, Any]], reloj: Reloj = reloj_sistema) -> list[dict[str, Any]]:
    """Conflictos de TODAS las operaciones (vacio = se puede escribir). No escribe."""
    conflictos: list[dict[str, Any]] = []
    valores: list[dict[str, Any]] = []
    for op in operaciones:
        v = _valores(op)
        valores.append(v)
        if not _ambito_coherente(op, v):
            conflictos.append({"ambito": op["ambito"], "codigo": srv.ENTRADA_INVALIDA, "campos": ["tercero_id", "categoria_id"]})
            continue
        if op["accion"] == "ALTA":
            existente = repo.leer(sesion, op["id"])
            if existente is not None:
                igual = existente["row_version"] == 1 and existente["enabled"] and all(existente[k] == v[k] for k in v)
                if not igual:
                    conflictos.append({"ambito": op["ambito"], "codigo": srv.IDENTIDAD_REUTILIZADA, "campos": []})
                continue  # identica: el alta sera idempotente
        else:
            fila = repo.leer(sesion, op["id"])
            if fila is None:
                conflictos.append({"ambito": op["ambito"], "codigo": srv.NO_ENCONTRADO, "campos": []})
                continue
            if fila["row_version"] != op.get("row_version"):
                conflictos.append({"ambito": op["ambito"], "codigo": srv.VERSION_DESFASADA, "campos": []})
                continue
        r = srv._validar_valores(sesion, v, reloj)
        if r is not None:
            conflictos.append({"ambito": op["ambito"], "codigo": r.codigo, "campos": _CAMPOS_DE_CODIGO.get(r.codigo, [])})
            continue
        if op["accion"] == "EDITAR":
            if not fila["enabled"]:
                continue  # como `editar`: una desactivada no participa; el empate se evalua al reactivarla
            v = {**v, "prioridad": fila["prioridad"]}  # prioridad no editable: el empate usa la persistida
        r = srv._empate(sesion, v, op["id"])
        if r is not None:
            cid = (r.detalle or {}).get("preferencia_conflicto_id")
            q = repo.leer(sesion, cid) if cid is not None else None
            conflictos.append({"ambito": op["ambito"], "codigo": r.codigo, "campos": _campos_distintos(v, q) if q else [],
                               "preferencia_conflicto_id": str((r.detalle or {}).get("preferencia_conflicto_id"))})
    # Entre las dos operaciones: la misma regla de empate de §41.4.
    if len(valores) == 2 and all(_ambito_coherente(o, v) for o, v in zip(operaciones, valores)):
        a, b = valores
        if especificidad(a) == especificidad(b) and a["prioridad"] == b["prioridad"] and pueden_coincidir(a, b):
            campos = _campos_distintos(a, b)
            if campos:
                for op in operaciones:
                    conflictos.append({"ambito": op["ambito"], "codigo": srv.EMPATE_CONTRADICTORIO, "campos": campos})
    return conflictos


def ambos(sesion: SesionMotor, *, operaciones: list[dict[str, Any]], reloj: Reloj = reloj_sistema) -> dict[str, Any] | srv.Rechazo:
    """Escribe una o dos preferencias de ambitos distintos de forma atomica, o devuelve el rechazo con todos los conflictos."""
    if not 1 <= len(operaciones) <= 2 or len({op["ambito"] for op in operaciones}) != len(operaciones):
        return srv.Rechazo(srv.ENTRADA_INVALIDA, {"conflictos": []})
    repo.tomar_advisory(sesion)
    conflictos = preflight(sesion, operaciones, reloj)
    if conflictos:
        return srv.Rechazo(conflictos[0]["codigo"], {"conflictos": conflictos})
    resultados = []
    for op in operaciones:
        c = _valores(op)
        datos = {k: c[k] for k in ("tipo_hecho_id", "categoria_id", "tercero_id", "entidad_id",
                                   "cuenta_default_id", "presupuestable_default", "prioridad")}
        if op["accion"] == "ALTA":
            r = srv.alta(sesion, preferencia_id=op["id"], reloj=reloj, **datos)
        else:
            r = srv.editar(sesion, preferencia_id=op["id"], row_version=op["row_version"], reloj=reloj, **datos)
        if isinstance(r, srv.Rechazo):
            raise FalloAmbos(op["ambito"], r)
        resultados.append({"ambito": op["ambito"], "preferencia": r.preferencia, "idempotente": r.idempotente})
    return {"resultados": resultados}
