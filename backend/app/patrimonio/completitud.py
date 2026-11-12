# ============================================================
# GAPTO MOBILE 2027
# Fichero: completitud.py
# Ruta: backend/app/patrimonio/completitud.py
# Descripcion: C-PROP-05 · declarar (o retirar) la completitud del coste de un ambito (R1 v0.9.5 C-PROP-05,
#   §I.5.1, §I.5.2 y §I.5.4; politica I-B del §II.6). CONSUMIDOR PROVISIONAL DE 0352: no se habilita antes de
#   la certificacion de 0352 (habilitacion.py); con los consumidores no habilitados responde
#   FUNCION_NO_HABILITADA sin tocar la base.
#   Precedencia (§I.5.1, respuesta 7): DTO -> corte no futuro (capa, sin lock; O8.6) -> 0P (funcion UNICA de
#   B1, `bloquear_intencion_propiedad`, importada, nunca copiada; §I.5.4) -> NK de la propiedad (404) ->
#   IDENTIDAD (auditoria append-only de la raiz con request_id = intencion_id y `intencion = {operacion:
#   "COMPLETITUD", contenido}` por igualdad exacta; E-6) -> version -> corte frente a fecha_adquisicion ->
#   componentes (ADQUISICION) -> relectura del conjunto y huella (COMPLETITUD_VISTA_DESFASADA) -> sin cambios
#   (200 sin escribir ni auditar) -> escritura de la terna, row_version + 1 y auditoria.
#   Contenido sellado: {propiedad_id, ambito, completo, fecha_corte, huella_conjunto_vista, row_version_esperada}
#   (operacion aparte, en la clave `intencion`). El conjunto releido no entra en el contenido.
#   Las columnas de 0352 solo se tocan a traves de propiedades/repositorio.py (FA-01).
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.core.unidad_trabajo import SesionMotor
from app.patrimonio import habilitacion
from app.propiedades import lecturas
from app.propiedades import repositorio as repo
from app.propiedades.servicio import bloquear_intencion_propiedad
from app.repositories import auditoria_repository as auditoria

OPERACION = "COMPLETITUD"
MOTIVO = "F06-01 B2 PROPIEDAD COMPLETITUD"
AMBITOS = ("ADQUISICION", "MEJORAS")

NO_ENCONTRADA = "AGREGADO_NO_ENCONTRADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
SIN_FECHA_DE_CORTE = "COMPLETITUD_SIN_FECHA_DE_CORTE"
SIN_COMPONENTES = "COMPLETITUD_SIN_COMPONENTES"
VISTA_DESFASADA = "COMPLETITUD_VISTA_DESFASADA"


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    propiedad: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


def contenido(propiedad_id: uuid.UUID, ambito: str, completo: bool, fecha_corte: dt.date | None,
              huella_vista: str | None, row_version: int) -> dict[str, Any]:
    return {"propiedad_id": str(propiedad_id), "ambito": ambito, "completo": completo,
            "fecha_corte": fecha_corte.isoformat() if fecha_corte else None,
            "huella_conjunto_vista": huella_vista, "row_version_esperada": row_version}


def identidad(sesion: SesionMotor, intencion_id: uuid.UUID, propiedad_id: uuid.UUID,
              contenido_: dict[str, Any]) -> bool | Rechazo:
    """True = replay exacto; False = intencion nueva; Rechazo = la intencion ya esta en la auditoria con otra cosa.
    Replay exacto = UNA auditoria, de la raiz, del mismo registro y con `intencion` igual (nunca inclusion)."""
    auditadas = repo.auditorias_de_intencion(sesion, intencion_id)
    if not auditadas:
        return False
    if len(auditadas) == 1 and auditadas[0]["tabla"] == "entidades" and auditadas[0]["registro_id"] == propiedad_id:
        sellada = (json.loads(auditadas[0]["despues"]) or {}).get("intencion")
        if sellada == {"operacion": OPERACION, "contenido": contenido_}:
            return True
    return Rechazo(IDENTIDAD_REUTILIZADA)


def _vista(sesion: SesionMotor, propiedad_id: uuid.UUID, hoy: dt.date) -> dict[str, Any]:
    vista = lecturas.detalle(sesion, propiedad_id, hoy)
    assert vista is not None
    return vista


def auditar(sesion: SesionMotor, propiedad_id: uuid.UUID, antes: str, intencion: dict[str, Any], motivo: str) -> None:
    despues = json.loads(repo.snapshot(sesion, propiedad_id))
    despues["intencion"] = intencion
    auditoria.registrar(sesion, tabla="entidades", registro_id=propiedad_id, accion=auditoria.ACCION_ACTUALIZAR,
                        datos_antes_json=antes, datos_despues_json=json.dumps(despues, ensure_ascii=False),
                        motivo=motivo)


def declarar(sesion: SesionMotor, *, propiedad_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
             ambito: str, completo: bool, fecha_corte: dt.date | None, huella_vista: str | None,
             reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    if not habilitacion.consumidores_0352_habilitados():
        return Rechazo(habilitacion.FUNCION_NO_HABILITADA)
    if ambito not in AMBITOS or not isinstance(completo, bool):
        return Rechazo(ENTRADA_INVALIDA)
    if completo and (fecha_corte is None or not huella_vista):
        return Rechazo(ENTRADA_INVALIDA)
    if not completo and (fecha_corte is not None or huella_vista is not None):
        return Rechazo(ENTRADA_INVALIDA)
    sellado = contenido(propiedad_id, ambito, completo, fecha_corte, huella_vista, row_version)
    # 0P: primer recurso de la transaccion (§I.5.4). Antes de cualquier lectura de estado o lock.
    bloquear_intencion_propiedad(sesion, intencion_id)
    hoy = hoy_owner(sesion, reloj)
    if completo and fecha_corte > hoy:          # capa (O8.6): antes que el lock y que la version
        return Rechazo(SIN_FECHA_DE_CORTE)
    raiz = repo.bloquear(sesion, propiedad_id)
    if raiz is None:
        return Rechazo(NO_ENCONTRADA)
    replay = identidad(sesion, intencion_id, propiedad_id, sellado)
    if replay is True:
        return Resultado(propiedad=_vista(sesion, propiedad_id, hoy), idempotente=True)
    if isinstance(replay, Rechazo):
        return replay
    if raiz["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    actual = repo.declaracion_completitud(sesion, propiedad_id, ambito)
    if not completo:
        if actual == (None, None, None):
            return Resultado(propiedad=_vista(sesion, propiedad_id, hoy))       # sin cambios: no escribe
        nueva: tuple[Any, Any, Any] = (None, None, None)
    else:
        if ambito == "ADQUISICION" and raiz["fecha_adquisicion"] is not None and fecha_corte < raiz["fecha_adquisicion"]:
            return Rechazo(SIN_FECHA_DE_CORTE)
        vigente, huella = repo.conjunto_completitud(sesion, propiedad_id, ambito, fecha_corte)
        if ambito == "ADQUISICION" and not vigente:
            return Rechazo(SIN_COMPONENTES)
        if huella != huella_vista:
            return Rechazo(VISTA_DESFASADA)
        nueva = (True, fecha_corte, vigente)
        if actual == nueva:
            return Resultado(propiedad=_vista(sesion, propiedad_id, hoy))       # sin cambios: no escribe
    antes = repo.snapshot(sesion, propiedad_id)
    repo.escribir_declaracion_completitud(sesion, propiedad_id, ambito, nueva)
    repo.subir_version(sesion, propiedad_id)
    auditar(sesion, propiedad_id, antes, {"operacion": OPERACION, "contenido": sellado}, MOTIVO)
    return Resultado(propiedad=_vista(sesion, propiedad_id, hoy), modificadas=(propiedad_id,))
