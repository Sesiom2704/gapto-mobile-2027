# ============================================================
# GAPTO MOBILE 2027
# Fichero: propuesta.py
# Ruta: backend/app/plantillas/propuesta.py
# Descripcion: Propuesta por campo del registro con la capa PLANTILLA (F05-03
#   J2 §1.6/§1.9; F05 §45.3 A3/E1/E2, §45.4 R1/R2, §46.3 A11; D-042). Servicio
#   de LECTURA: no escribe, no toma advisories (ni PLANTILLAS ni PREFERENCIAS)
#   y solo bloquea, como la propuesta de F05-02, la categoria EXPLICITA con la
#   guarda C-a (FOR SHARE, §43.4). Es una instantanea para MOSTRAR: el
#   registro sella los valores finales y nunca relee la plantilla (R2).
#
#   Precedencia por campo: explicito (lo aplica el cliente: nunca pisa un
#   campo tocado) > PLANTILLA > PREFERENCIA > DEFAULT_GENERAL.
#   - categoria: SOLO la propone una plantilla (E2 a C01). Si la de la
#     plantilla no es elegible para el tipo (deshabilitada, ajena o de ambito
#     incompatible): no se aplica, aviso, y el estado queda PENDIENTE; ninguna
#     otra capa la propone.
#   - cuenta: la de la plantilla si es elegible (regla unica R1 para la
#     operacion del tipo, en `fecha`); si no, aviso y la capa siguiente
#     (resolver de preferencias: preferencia elegible o cuenta unica).
#   - presupuestable: el de la plantilla si no es NULL; si no, preferencias.
#   - tercero y contexto: los de la plantilla si siguen del owner y
#     habilitados (contexto: entidad CONTEXTO); si no, aviso (A11).
#   - NULL en la plantilla = no propone. La plantilla debe ser del owner,
#     estar habilitada y ser del mismo tipo; si no, aviso y sin capa plantilla.
#   El contexto de las preferencias (categoria y tercero) es el explicito del
#   cliente o, si no lo hay, el que aplica la plantilla.
#   Avisos: [{campo, motivo}] con motivo NO_ELEGIBLE | NO_DISPONIBLE.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.6)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.api.elegibilidad_categoria import ambito_compatible, validar_seleccion_categoria
from app.comun.elegibilidad_cuentas import motivo_cuenta
from app.core.unidad_trabajo import SesionMotor
from app.plantillas import repositorio as repo
from app.preferencias.resolver import resolver, tipo_hecho_registro

CAPA_PLANTILLA = "PLANTILLA"


def _de_plantilla(valor: Any, plantilla_id: uuid.UUID) -> dict[str, Any]:
    return {"valor": valor, "origen": {"capa": CAPA_PLANTILLA, "plantilla_id": plantilla_id, "preferencia_id": None}}


def _de_preferencia(p: dict[str, Any] | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {"valor": p["valor"], "origen": {"capa": p["origen"]["capa"], "plantilla_id": None,
                                            "preferencia_id": p["origen"]["preferencia_id"]}}


def _owner_uno(sesion: SesionMotor, sql: str, ident) -> tuple | None:
    return sesion.uno(sql + " AND owner_user_id = current_setting('gapto.owner_user_id')::uuid", (ident,))


def propuesta_registro(
    sesion: SesionMotor,
    *,
    tipo: str,
    fecha: dt.date,
    plantilla_id: uuid.UUID | None = None,
    categoria_id: uuid.UUID | None = None,
    sin_categoria: bool = False,
    tercero_id: uuid.UUID | None = None,
    sin_tercero: bool = False,
) -> dict[str, Any] | str:
    """Propuesta por campo; o CATEGORIA_NO_ELEGIBLE si la categoria EXPLICITA
    no es elegible para `tipo` (guarda C-a, como la propuesta de F05-02)."""
    if categoria_id is not None:
        rechazo = validar_seleccion_categoria(sesion, categoria_id, tipo)
        if rechazo is not None:
            return rechazo
    avisos: list[dict[str, str]] = []
    campos: dict[str, Any] = {"categoria": None, "tercero": None, "contexto": None, "cuenta": None,
                              "presupuestable": None}
    tipo_id = tipo_hecho_registro(sesion, tipo)

    p = repo.leer_plantilla(sesion, plantilla_id) if plantilla_id is not None else None
    if plantilla_id is not None and (p is None or not p["enabled"] or p["tipo_hecho_id"] != tipo_id):
        avisos.append({"campo": "plantilla", "motivo": "NO_DISPONIBLE"})
        p = None

    if p is not None:
        pid = p["id"]
        if p["categoria_id"] is not None:
            fila = _owner_uno(sesion, "SELECT enabled, ambito FROM gapto.categorias_financieras WHERE id = %s",
                              p["categoria_id"])
            if fila is not None and fila[0] and ambito_compatible(tipo, fila[1]):
                campos["categoria"] = _de_plantilla(p["categoria_id"], pid)
            else:
                avisos.append({"campo": "categoria", "motivo": "NO_ELEGIBLE"})
        if p["tercero_id"] is not None:
            fila = _owner_uno(sesion, "SELECT enabled FROM gapto.terceros WHERE id = %s", p["tercero_id"])
            if fila is not None and fila[0]:
                campos["tercero"] = _de_plantilla(p["tercero_id"], pid)
            else:
                avisos.append({"campo": "tercero", "motivo": "NO_ELEGIBLE"})
        if p["entidad_id"] is not None:
            fila = _owner_uno(sesion, "SELECT enabled, tipo_entidad FROM gapto.entidades WHERE id = %s",
                              p["entidad_id"])
            if fila is not None and fila[0] and fila[1] == "CONTEXTO":
                campos["contexto"] = _de_plantilla(p["entidad_id"], pid)
            else:
                avisos.append({"campo": "contexto", "motivo": "NO_ELEGIBLE"})
        if p["presupuestable_default"] is not None:
            campos["presupuestable"] = _de_plantilla(p["presupuestable_default"], pid)
        if p["cuenta_default_id"] is not None:
            if motivo_cuenta(sesion, p["cuenta_default_id"], tipo, fecha) is None:
                campos["cuenta"] = _de_plantilla(p["cuenta_default_id"], pid)
            else:
                avisos.append({"campo": "cuenta", "motivo": "NO_ELEGIBLE"})

    # Contexto de las preferencias: lo explicito o lo que aplica la plantilla.
    ctx_categoria = None if sin_categoria else (
        categoria_id if categoria_id is not None else (campos["categoria"] or {}).get("valor"))
    ctx_tercero = None if sin_tercero else (
        tercero_id if tercero_id is not None else (campos["tercero"] or {}).get("valor"))
    prefs = resolver(sesion, tipo_hecho_id=tipo_id, categoria_id=ctx_categoria, fecha=fecha, tercero_id=ctx_tercero)
    if campos["cuenta"] is None:
        campos["cuenta"] = _de_preferencia(prefs["cuenta"])
    if campos["presupuestable"] is None:
        campos["presupuestable"] = _de_preferencia(prefs["presupuestable"])
    return {"tipo": tipo, "campos": campos, "avisos": avisos}
