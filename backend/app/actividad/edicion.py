# ============================================================
# GAPTO MOBILE 2027
# Fichero: edicion.py
# Ruta: backend/app/actividad/edicion.py
# Descripcion: F05-06 M1 (CONTRATO_M1 v0.1 §1; F05 §61.2 F05-D047; lamina
#   EDIT-HECHO v0.1; AJ-M5BM1-06). Lectura de la ELEGIBILIDAD VISIBLE de un
#   hecho para «Corregir» (OP-21P pago simple, OP-21T transferencia propia) y
#   «Anular por duplicado» (OP-03P), SIN locks ni escritura (precedente:
#   elegibilidad_anulacion de M3, AJ-M3-DEC-04). Es informativa: cada POST
#   revalida en el motor bajo sus locks y con sus codigos; esta lectura solo
#   evita ofrecer lo que el motor rechazaria por la FORMA del hecho.
#   Devuelve tambien lo que el cliente necesita para enviar la intencion: la
#   row_version del hecho y la de cada movimiento conciliado (con su pata y su
#   cuenta), y el estado ANULADO con su motivo (el hecho no desaparece).
#   Motivos (codigos del motor, contexto_extra.motivo, o propios de la
#   lectura cuando el motor no llega a decidir por falta de forma):
#     HECHO_ANULADO, ORIGEN_IMPORTADO (registros de V3: la app no los corrige
#     ni los anula; desde 0.2.0 solo «Corregir categoria»), TIPO_NO_SOPORTADO, DEVOLUCION (origen de una
#     devolucion: no se corrige), DEPENDENCIAS_ACTIVAS (no se anula), INVERSION,
#     SIN_TESORERIA, VARIOS_MOVIMIENTOS, REPARTO (reparto con otras personas o
#     posiciones: fuera de M1, «Corregir reparto»), MOVIMIENTO_COMPARTIDO,
#     REVERSION_EXISTENTE, MOVIMIENTO_ANULADO, CONCILIACION_PARCIAL, MULTIDIVISA.
#   Los textos de usuario viven en errores_http.MOTIVOS_EDICION.
# Version: 0.1.0 (F05-06 M1)
# Version: 0.2.0 (F05-06 M1 v1.1; Q9 opcion (a); F05-D047 §61.3 limitado a la
#   categoria): «Corregir categoria» de un registro de V3. motivo_categoria_v3
#   es la UNICA regla de forma (la usan esta lectura y el adaptador
#   ejecucion_categoria_v3, que la reevalua dentro de su transaccion): solo un
#   hecho importado, ACTIVO, GASTO o INGRESO, con un unico efecto de su misma
#   naturaleza. Motivos: NO_IMPORTADO (fuera de esta via), HECHO_ANULADO,
#   TIPO_NO_SOPORTADO, VARIOS_EFECTOS. La lectura devuelve
#   `acciones.corregir_categoria` y `categoria` (efecto, naturaleza y
#   categoria actual) SOLO para registros de V3 (None en el resto). Sin locks.
# ============================================================

from __future__ import annotations

import decimal
import uuid
from typing import Any

from app.core.unidad_trabajo import SesionMotor
from app.repositories import correccion_tesoreria_repository as repo
from app.repositories import hechos_repository as repo_hechos

D = decimal.Decimal
_CENT = D("0.01")


def _texto(v: Any) -> str | None:
    return None if v is None else str(D(v).quantize(_CENT))


def _accion(motivo: str | None) -> dict[str, Any]:
    return {"disponible": motivo is None, "codigo": motivo}


def _movimientos(sesion: SesionMotor, hecho_id: uuid.UUID) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(conciliaciones, movimientos leidos) del hecho, sin lock."""
    conciliaciones = repo.conciliaciones(sesion, hecho_id)
    movimientos = []
    for c in conciliaciones:
        m = repo.leer_movimiento(sesion, c["movimiento_id"])
        if m is not None:
            cuenta = sesion.uno("SELECT nombre FROM gapto.cuentas WHERE id = %s", (m["cuenta_id"],))
            movimientos.append({**m, "id": c["movimiento_id"], "conciliado": c["importe"],
                                "cuenta_nombre": None if cuenta is None else cuenta[0]})
    return conciliaciones, movimientos


def _comun(sesion: SesionMotor, hecho_id: uuid.UUID, hecho: dict[str, Any],
           movimientos: list[dict[str, Any]]) -> str | None:
    """Motivos que impiden tanto corregir como anular por esta via."""
    if hecho["estado"] != "ACTIVO":
        return "HECHO_ANULADO"
    destinos = [("hechos_financieros", hecho_id)] + [("movimientos_tesoreria", m["id"]) for m in movimientos]
    if repo.importado(sesion, destinos):
        return "ORIGEN_IMPORTADO"
    if hecho["tipo"] not in ("GASTO", "INGRESO", "TRANSFERENCIA"):
        return "TIPO_NO_SOPORTADO"
    if repo.tiene_entidad_de_inversion(sesion, hecho_id):
        return "INVERSION"
    if not movimientos:
        return "SIN_TESORERIA"
    for m in movimientos:
        if m["estado"] != "ACTIVO":
            return "MOVIMIENTO_ANULADO"
        if m["clase"] == "AJUSTE_SALDO":
            return "TIPO_NO_SOPORTADO"
        if repo.hechos_conciliados(sesion, m["id"]) != [hecho_id]:
            return "MOVIMIENTO_COMPARTIDO"
        if m["reversiones"] > 0 or m["reversion_de"] is not None:
            return "REVERSION_EXISTENTE"
    return None


def _con_reparto(sesion: SesionMotor, hecho_id: uuid.UUID) -> bool:
    """Reparto con otras personas o posiciones: fuera de M1 (P-EDIT-04)."""
    fila = sesion.uno(
        "SELECT (SELECT count(*) FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e ON e.id = a.efecto_id "
        "WHERE e.hecho_id = %s) > 1 OR EXISTS (SELECT 1 FROM gapto.hecho_entidades v JOIN "
        "gapto.derechos_obligaciones_financieras p ON p.entidad_id = v.entidad_id WHERE v.hecho_id = %s)",
        (hecho_id, hecho_id))
    return bool(fila and fila[0])


def _motivo_corregir(sesion: SesionMotor, hecho_id: uuid.UUID, hecho: dict[str, Any],
                     movimientos: list[dict[str, Any]], comun: str | None) -> str | None:
    if comun is not None:
        return comun
    total = hecho["importe_total"]
    if hecho["tipo"] == "GASTO":
        if repo.es_origen_de_devolucion(sesion, hecho_id):
            return "DEVOLUCION"
        if _con_reparto(sesion, hecho_id):
            return "REPARTO"
        efectos = repo.efectos(sesion, hecho_id)
        if len(efectos) != 1 or efectos[0]["tipo_efecto"] != "GASTO" or D(efectos[0]["importe_delta"]) <= 0:
            return "TIPO_NO_SOPORTADO"
        if len(movimientos) > 1:
            return "VARIOS_MOVIMIENTOS"
        m = movimientos[0]
        if D(m["importe"]) >= 0 or m["transferencia_id"] is not None:
            return "TIPO_NO_SOPORTADO"
    elif hecho["tipo"] == "TRANSFERENCIA":
        if repo.efectos(sesion, hecho_id) or len(movimientos) != 2:
            return "VARIOS_MOVIMIENTOS" if len(movimientos) != 2 else "TIPO_NO_SOPORTADO"
    else:
        return "TIPO_NO_SOPORTADO"  # ingresos: fuera de OP-21P en v1
    for m in movimientos:
        if total is None or abs(D(m["conciliado"])) != abs(D(m["importe"])) or abs(D(m["importe"])) != abs(D(total)):
            return "CONCILIACION_PARCIAL"
        cuenta = repo.leer_cuenta(sesion, m["cuenta_id"])
        if cuenta is None or cuenta["moneda"] != hecho["moneda"]:
            return "MULTIDIVISA"
    return None


def _motivo_anular(sesion: SesionMotor, hecho_id: uuid.UUID, hecho: dict[str, Any],
                   movimientos: list[dict[str, Any]], comun: str | None) -> str | None:
    if comun is not None:
        return comun
    if repo_hechos.dependencias_activas(sesion, hecho_id):
        return "DEPENDENCIAS_ACTIVAS"
    if hecho["tipo"] == "TRANSFERENCIA" and len(movimientos) != 2:
        return "TIPO_NO_SOPORTADO"
    return None


def motivo_categoria_v3(sesion: SesionMotor, hecho_id: uuid.UUID,
                        hecho: dict[str, Any] | None = None) -> tuple[str | None, dict[str, Any] | None]:
    """(motivo, efecto {id, naturaleza}) de «Corregir categoria» de V3, sin locks. motivo None ->
    el efecto unico que se corrige; NO_ENCONTRADO si el hecho no es visible."""
    hecho = hecho or repo.leer_hecho(sesion, hecho_id)
    if hecho is None:
        return "NO_ENCONTRADO", None
    if not repo.importado(sesion, [("hechos_financieros", hecho_id)]):
        return "NO_IMPORTADO", None
    if hecho["estado"] != "ACTIVO":
        return "HECHO_ANULADO", None
    if hecho["tipo"] not in ("GASTO", "INGRESO"):
        return "TIPO_NO_SOPORTADO", None
    efectos = repo.efectos(sesion, hecho_id)
    if len(efectos) != 1:
        return "VARIOS_EFECTOS", None
    if efectos[0]["tipo_efecto"] != hecho["tipo"]:
        return "TIPO_NO_SOPORTADO", None
    return None, {"id": efectos[0]["id"], "naturaleza": efectos[0]["tipo_efecto"]}


def _categoria_v3(sesion: SesionMotor, hecho_id: uuid.UUID, hecho: dict[str, Any]
                  ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(accion, categoria actual) de V3; (None, None) si el hecho no es de V3."""
    motivo, efecto = motivo_categoria_v3(sesion, hecho_id, hecho)
    if motivo == "NO_IMPORTADO":
        return None, None
    if efecto is None:
        return _accion(motivo), None
    fila = sesion.uno("SELECT e.categoria_id, c.nombre FROM gapto.hecho_efectos e LEFT JOIN "
                      "gapto.categorias_financieras c ON c.id = e.categoria_id WHERE e.id = %s", (efecto["id"],))
    return _accion(None), {"efecto_id": efecto["id"], "naturaleza": efecto["naturaleza"],
                           "categoria_id": fila[0] if fila else None, "nombre": fila[1] if fila else None}


def edicion(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[str, Any] | None:
    """Elegibilidad visible de «Corregir», «Anular por duplicado» y, en V3, «Corregir categoria» (o None)."""
    hecho = repo.leer_hecho(sesion, hecho_id)
    if hecho is None:
        return None
    anulado = sesion.uno("SELECT anulado_at, motivo_anulacion FROM gapto.hechos_financieros WHERE id = %s",
                         (hecho_id,))
    _, movimientos = _movimientos(sesion, hecho_id)
    comun = _comun(sesion, hecho_id, hecho, movimientos)
    accion_categoria, categoria = _categoria_v3(sesion, hecho_id, hecho)
    patas = []
    for m in sorted(movimientos, key=lambda x: (D(x["importe"]) > 0, str(x["id"]))):
        patas.append({"movimiento_id": m["id"], "row_version": m["row_version"],
                      "pata": "ENTRADA" if D(m["importe"]) > 0 else "SALIDA",
                      "cuenta": {"id": m["cuenta_id"], "nombre": m["cuenta_nombre"]},
                      "importe": _texto(abs(D(m["importe"]))), "fecha": m["fecha"]})
    return {
        "hecho_id": hecho_id, "row_version": hecho["row_version"], "estado": hecho["estado"], "tipo": hecho["tipo"],
        "importe": _texto(hecho["importe_total"]), "fecha": hecho["fecha"], "moneda": hecho["moneda"],
        "origen_v3": comun == "ORIGEN_IMPORTADO",
        "anulado": None if hecho["estado"] == "ACTIVO" else {
            "fecha": anulado[0].date() if anulado and anulado[0] else None, "motivo": anulado[1] if anulado else None},
        "movimientos": patas,
        "categoria": categoria,
        "acciones": {
            "corregir": _accion(_motivo_corregir(sesion, hecho_id, hecho, movimientos, comun)),
            "anular_duplicado": _accion(_motivo_anular(sesion, hecho_id, hecho, movimientos, comun)),
            "corregir_categoria": accion_categoria,
        },
    }
