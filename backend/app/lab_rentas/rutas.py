# ============================================================
# GAPTO MOBILE 2027 · LABORATORIO (rama lab-t5; no es implementacion de T5)
# Fichero: rutas.py
# Ruta: backend/app/lab_rentas/rutas.py
# Descripcion: L1 · rutas de LABORATORIO de F06-04 (prefijo /v1/lab, marca «LAB»), sobre LAB_0357:
#   - GET  /v1/lab/contratos/{id}/renta/calendario   cobros previstos (R8, R14), puro;
#   - GET  /v1/lab/renta/propuesta-revision          renta exacta y propuesta a la baja (R5) con tope y receptor (R6), aviso
#                                                    y fecha de efecto (R10, R11), puro;
#   - POST /v1/lab/contratos/{id}/revisiones         registra «Aplicar» o «No aplicar este año» (R4-A, R9) en
#                                                    gapto.lab_renta_revisiones (historico, una por aniversario);
#   - POST /v1/lab/contratos/{id}/tope               nueva version del tope con receptor (R6, R9), cerrando la vigente.
#   SUPUESTO del laboratorio: «Aplicar» SOLO registra la revision; crear la version de la regla de renta y recalcular los
#   previstos abiertos exige los writers de reglas afectados por RVRX-REGLA (L2) y NO se hace aqui.
# Version: 0.1.0 (LAB T5 · L1)
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any, Literal

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.lab_rentas import dominio as d

MARCA = "LAB"


class RegistrarRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aniversario: dt.date
    renta_anterior: Decimal = Field(gt=0)
    indice_texto: str | None = Field(None, max_length=80)
    indice_porcentaje: Decimal | None = None
    decision: Literal["APLICADA", "NO_APLICADA"]
    renta_aplicada: Decimal | None = Field(None, gt=0)
    fecha_aviso: dt.date | None = None
    motivo: str | None = Field(None, max_length=500)


class FijarTope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receptor_contrato_id: uuid.UUID
    porcentaje_tope: Decimal = Field(gt=0, le=100)
    vigente_desde: dt.date


def _json(x: Any) -> JSONResponse:
    return JSONResponse(json.loads(json.dumps(x, default=str)))


def registrar(app: FastAPI, *, unidad, contexto, autorizar) -> None:
    dep = [Depends(autorizar)]

    @app.get("/v1/lab/contratos/{contrato_id}/renta/calendario", dependencies=dep)
    def lab_calendario(contrato_id: uuid.UUID, inicio: dt.date = Query(...), renta: Decimal = Query(..., gt=0),
                       hasta: dt.date = Query(...), fin: dt.date | None = Query(None)):
        try:
            cobros = d.calendario_cobros(inicio, renta, hasta, fin)
        except d.ReglaRenta as e:
            return JSONResponse({"codigo": "REGLA_RENTA", "mensaje": str(e), "marca": MARCA}, status_code=422)
        return _json({"marca": MARCA, "contrato_id": contrato_id,
                      "cobros": [{"fecha": x.fecha, "importe": x.importe, "medio_mes": x.medio_mes} for x in cobros]})

    @app.get("/v1/lab/renta/propuesta-revision", dependencies=dep)
    def lab_propuesta(renta_anterior: Decimal = Query(..., gt=0), porcentaje: Decimal = Query(...), aniversario: dt.date = Query(...),
                      fecha_aviso: dt.date | None = Query(None)):
        p = d.proponer_revision(renta_anterior, porcentaje)
        primero, segundo = d.avisos(aniversario)
        return _json({"marca": MARCA, "exacta": p.exacta, "propuesta": p.propuesta, "aviso_primero": primero,
                      "aviso_segundo": segundo, "efecto": d.fecha_efecto(aniversario, fecha_aviso or segundo)})

    def _registrar_revision(s, contrato_id: uuid.UUID, c: RegistrarRevision) -> dict:
        exacta = propuesta = None
        if c.indice_porcentaje is not None:
            p = d.proponer_revision(c.renta_anterior, c.indice_porcentaje)
            exacta, propuesta = p.exacta, p.propuesta
        primero, segundo = d.avisos(c.aniversario)
        fila = s.uno(
            "INSERT INTO gapto.lab_renta_revisiones (contrato_entidad_id, aniversario, renta_anterior, indice_texto, "
            "indice_porcentaje, renta_exacta, renta_propuesta, decision, renta_aplicada, aviso_primero, aviso_segundo, motivo) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT ON CONSTRAINT uq_lab_renta_revisiones__contrato_aniversario DO NOTHING RETURNING id",
            (contrato_id, c.aniversario, c.renta_anterior, c.indice_texto, c.indice_porcentaje, exacta, propuesta, c.decision,
             c.renta_aplicada if c.decision == "APLICADA" else None, primero, segundo, c.motivo))
        if fila is None:
            return {"codigo": "REVISION_YA_REGISTRADA"}
        return {"id": fila[0], "renta_exacta": exacta, "renta_propuesta": propuesta, "aviso_primero": primero, "aviso_segundo": segundo,
                "efecto": d.fecha_efecto(c.aniversario, c.fecha_aviso or segundo)}

    @app.post("/v1/lab/contratos/{contrato_id}/revisiones", dependencies=dep)
    def lab_revision(contrato_id: uuid.UUID, c: RegistrarRevision):
        if c.decision == "APLICADA" and c.renta_aplicada is None:
            return JSONResponse({"codigo": "ENTRADA_INVALIDA", "mensaje": "Indica la renta que se aplica.", "marca": MARCA}, status_code=422)
        salida = unidad.ejecutar(contexto(), lambda s: _registrar_revision(s, contrato_id, c), nombre="LAB T5 L1 revision")
        if salida.get("codigo") == "REVISION_YA_REGISTRADA":
            return JSONResponse({**salida, "mensaje": "Ese aniversario ya está registrado.", "marca": MARCA}, status_code=409)
        return _json({"marca": MARCA, "revision": salida})

    def _fijar_tope(s, contrato_id: uuid.UUID, c: FijarTope) -> dict:
        # Nueva version: cierra la vigente el dia anterior y abre la nueva (sin solapes, EXCLUDE).
        s.uno("UPDATE gapto.lab_contrato_topes SET vigente_hasta = %s WHERE contrato_entidad_id = %s AND vigente_hasta IS NULL "
              "AND vigente_desde < %s RETURNING id", (c.vigente_desde - dt.timedelta(days=1), contrato_id, c.vigente_desde))
        fila = s.uno("INSERT INTO gapto.lab_contrato_topes (contrato_entidad_id, receptor_contrato_entidad_id, porcentaje_tope, "
                     "vigente_desde) VALUES (%s,%s,%s,%s) RETURNING id", (contrato_id, c.receptor_contrato_id, c.porcentaje_tope, c.vigente_desde))
        return {"id": fila[0]}

    @app.post("/v1/lab/contratos/{contrato_id}/tope", dependencies=dep)
    def lab_tope(contrato_id: uuid.UUID, c: FijarTope):
        return _json({"marca": MARCA, "tope": unidad.ejecutar(contexto(), lambda s: _fijar_tope(s, contrato_id, c), nombre="LAB T5 L1 tope")})
