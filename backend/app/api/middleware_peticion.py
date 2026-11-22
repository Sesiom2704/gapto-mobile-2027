# ============================================================
# GAPTO MOBILE 2027
# Fichero: middleware_peticion.py
# Ruta: backend/app/api/middleware_peticion.py
# Descripcion: Middleware ASGI de AJ-05 (F06 T4; diseno v0.2 §3, §5.4, §6; dictamen R2 AJ-R2-03/05/06/07).
#
#   Al entrar, ANTES del enrutado:
#   - crea el estado de la peticion (`app.core.peticion`): `http_request_id`, clase A/B provisional por metodo y ruta,
#     deadline monotonico unico y el seguimiento acumulado de unidades; lo deja tambien en `scope["gapto_peticion"]`
#     para los manejadores globales (el de `Exception` corre fuera de este middleware);
#   - registra RECIBIDA (sin ruta: aun no esta resuelta y la URL no se registra).
#   Al salir, tambien por excepcion: registra TERMINADA con la plantilla resuelta (o NO_RESUELTA), el estado HTTP, el
#   codigo, el desenlace, la persistencia acumulada, las unidades con sus intentos, duraciones y `fuera_de_plazo`.
#
#   Red de seguridad (AJ-R2-03), ACOTADA: SOLO sustituye por RESULTADO_NO_CONFIRMADO una respuesta 5xx que afirme que
#   NO se ha guardado (`NO_GUARDADO_5XX`) cuando la peticion tiene una escritura con COMMIT_CONFIRMADO; deja una
#   anomalia en la traza. NUNCA toca un rechazo funcional 4xx: si llega uno tras un COMMIT y no esta en la lista
#   cerrada del inventario (`RECHAZOS_TRAS_COMMIT_PREVISTOS`), se registra como anomalia y se devuelve tal cual.
#
#   El registro es fail-open: nada de lo que haga (ni un fallo suyo) cambia el codigo, el cuerpo, las cabeceras ni el
#   resultado transaccional, tampoco durante una excepcion del backend.
# Version: 0.1.0 (F06 T4 · AJ-05 ampliado + R-C7-07, mandato b4ff6b70… y adenda 01 24113472…)
# ============================================================

from __future__ import annotations

import json
import time
from typing import Any

from app.api import errores_http as eh
from app.api.registro_peticiones import RegistroPeticiones, uuid_de_cabecera
from app.core import peticion as pet

# Respuestas 5xx cuyo texto afirma que NO se ha guardado nada (errores_http): con un COMMIT confirmado serian falsas.
NO_GUARDADO_5XX = frozenset({"TIEMPO_AGOTADO", "CONFLICTO_CONCURRENCIA"})

# Lista CERRADA de rechazos funcionales que el codigo preve DESPUES de un COMMIT confirmado en la misma peticion
# (inventario de la Fase 1, INVENTARIO_FRONTERAS.md §3 y AJ-D-05; sin cambios por D-C7-10): (metodo, plantilla, HTTP).
# Todos son rechazos de dominio dentro de un SAVEPOINT revertido: la unidad confirma una transaccion SIN escritura
# neta. Fuera de esta lista: anomalia en la traza (y STOP del bloque si aparece en pruebas).
RECHAZOS_TRAS_COMMIT_PREVISTOS: frozenset[tuple[str, str, int]] = frozenset({
    ("POST", "/v1/acciones-rapidas", 409),
    ("POST", "/v1/afinidades", 409),
    ("POST", "/v1/categorias", 409),
    ("POST", "/v1/categorias/{categoria_id}/desactivar", 409),
    ("POST", "/v1/categorias/{categoria_id}/magnitudes", 409),
    ("POST", "/v1/categorias/{categoria_id}/magnitudes/reordenar", 409),
    ("POST", "/v1/categorias/{categoria_id}/magnitudes/{asociacion_id}/retirar", 409),
    ("POST", "/v1/categorias/{categoria_id}/mover", 409),
    ("POST", "/v1/clasificaciones-tercero", 409),
    ("POST", "/v1/clasificaciones-tercero/{clasificacion_id}/mover", 422),
    ("POST", "/v1/contextos", 409),
    ("POST", "/v1/contratos/{contrato_id}/clausula", 409),
    ("POST", "/v1/contratos/{contrato_id}/personas", 422),
    ("POST", "/v1/contratos/{contrato_id}/servicios/{servicio_id}", 409),
    ("POST", "/v1/intenciones/contrato-alquiler", 422),
    ("POST", "/v1/plantillas", 409),
    ("POST", "/v1/preferencias", 409),
    ("POST", "/v1/propiedades", 409),
    ("POST", "/v1/propiedades/{propiedad_id}/compra", 409),
    ("POST", "/v1/propiedades/{propiedad_id}/titularidad/inicio", 422),
    ("POST", "/v1/propiedades/{propiedad_id}/valoraciones", 409),
    ("POST", "/v1/terceros", 409),
    ("POST", "/v1/terceros/{tercero_id}/editar", 409),
})


def _intentos(u: pet.RegistroUnidad) -> list[dict[str, Any]]:
    return [{"n": i.numero, "estado": i.estado.value, "sqlstate": i.sqlstate, "conexion_ms": i.conexion_ms,
             "transaccion_ms": i.transaccion_ms, "commit_ms": i.commit_ms, "xid_auxiliar": i.xid_auxiliar}
            for i in u.intentos]


def desenlace(estado_http: int | None, codigo: str | None, persistencia: pet.Persistencia) -> str:
    if estado_http is None:
        return "EXCEPCION"
    if estado_http < 400:
        return "CONFIRMADO"
    if estado_http < 500:
        return "RECHAZO"
    if codigo == "TIEMPO_AGOTADO":
        return "NO_GUARDADO"
    return "INDETERMINADO"


def traza_persistencia(persistencia: pet.Persistencia, estado_http: int | None) -> str:
    """AJ-R2-06: con COMMIT conocido y sin respuesta funcional completa, la traza lo dice asi; nunca lo rebaja a
    «posible». Con COMMIT indeterminado, lo dice como tal."""
    completa = estado_http is not None and estado_http < 400
    if persistencia is pet.Persistencia.ESCRITURA_CONFIRMADA:
        return "ESCRITURA_CONFIRMADA" if completa else "ESCRITURA_CONFIRMADA / RESPUESTA_NO_COMPLETADA"
    if persistencia is pet.Persistencia.COMMIT_INDETERMINADO:
        return "COMMIT_INDETERMINADO"
    return "NINGUNA"


class MiddlewarePeticion:
    def __init__(self, app: Any, registro: RegistroPeticiones | None = None) -> None:
        self.app = app
        self.registro = registro

    def _escribir(self, evento: dict[str, Any]) -> None:
        if self.registro is None:
            return
        try:
            self.registro.escribir(evento)
        except BaseException:  # noqa: BLE001 - fail-open: el registro nunca altera la respuesta
            pass

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        estado, token = pet.iniciar(scope.get("method", ""), scope.get("path", ""))
        scope["gapto_peticion"] = estado
        cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        identidades = {"http_request_id": str(estado.http_request_id),
                       "client_attempt_id": uuid_de_cabecera(cabeceras.get("x-gapto-intento-id")),
                       "intencion_id": uuid_de_cabecera(cabeceras.get("x-gapto-intencion-id"))}
        self._escribir({"evento": "RECIBIDA", **identidades, "metodo": scope.get("method"),
                        "clase_provisional": estado.clase})

        salida: dict[str, Any] = {"estado": None, "codigo": None}
        retenido: dict[str, Any] = {"inicio": None, "cuerpo": b""}

        async def enviar(msg: dict) -> None:
            if msg["type"] == "http.response.start":
                salida["estado"] = msg["status"]
                if msg["status"] >= 400:
                    retenido["inicio"] = msg   # se retiene para leer el codigo (y, en 5xx, quiza sustituir)
                    return
                await send(msg)
                return
            if msg["type"] == "http.response.body" and retenido["inicio"] is not None:
                retenido["cuerpo"] += msg.get("body", b"")
                if msg.get("more_body", False):
                    return
                inicio, cuerpo = retenido["inicio"], retenido["cuerpo"]
                retenido["inicio"] = None
                try:
                    salida["codigo"] = json.loads(cuerpo or b"{}").get("codigo")
                except Exception:  # noqa: BLE001
                    salida["codigo"] = None
                if (inicio["status"] >= 500 and salida["codigo"] in NO_GUARDADO_5XX
                        and estado.persistencia() is pet.Persistencia.ESCRITURA_CONFIRMADA):
                    estado.anomalias.append(f"RED_DE_SEGURIDAD:{salida['codigo']}")
                    status, nuevo = eh.resultado_no_confirmado()
                    cuerpo = json.dumps(nuevo, ensure_ascii=False).encode("utf-8")
                    otras = [(k, v) for k, v in inicio.get("headers", []) if k.lower() != b"content-length"]
                    inicio = {**inicio, "status": status,
                              "headers": [*otras, (b"content-length", str(len(cuerpo)).encode())]}
                    salida["estado"], salida["codigo"] = status, nuevo["codigo"]
                await send(inicio)
                await send({"type": "http.response.body", "body": cuerpo, "more_body": False})
                return
            await send(msg)

        excepcion = None
        try:
            await self.app(scope, receive, enviar)
        except BaseException as exc:  # noqa: BLE001
            excepcion = type(exc).__name__   # solo el NOMBRE del tipo: nunca su mensaje
            raise
        finally:
            pet.terminar(token)
            try:
                self._terminada(scope, estado, identidades, salida, excepcion)
            except BaseException:  # noqa: BLE001 - fail-open, tambien durante una excepcion del backend
                pass

    def _terminada(self, scope: dict, estado: pet.EstadoPeticion, identidades: dict, salida: dict,
                   excepcion: str | None) -> None:
        ruta = scope.get("route")
        plantilla = getattr(ruta, "path", None) or "NO_RESUELTA"
        persistencia = estado.persistencia()
        if (salida["estado"] is not None and 400 <= salida["estado"] < 500
                and persistencia is pet.Persistencia.ESCRITURA_CONFIRMADA
                and (scope.get("method"), plantilla, salida["estado"]) not in RECHAZOS_TRAS_COMMIT_PREVISTOS):
            estado.anomalias.append(f"RECHAZO_TRAS_COMMIT_NO_PREVISTO:{salida['codigo']}")
        self._escribir({
            "evento": "TERMINADA", **identidades, "metodo": scope.get("method"), "ruta": plantilla,
            "clase": estado.clase, "estado_http": salida["estado"], "codigo": salida["codigo"],
            "desenlace": desenlace(salida["estado"], salida["codigo"], persistencia),
            "persistencia": traza_persistencia(persistencia, salida["estado"]),
            "excepcion": excepcion, "duracion_ms": round((time.monotonic() - estado.t0) * 1000, 2),
            "fuera_de_plazo": estado.fuera_de_plazo(), "anomalias": list(estado.anomalias),
            "unidades": [{"nombre": u.nombre, "audit_request_id": u.audit_request_id, "solo_lectura": u.solo_lectura,
                          "intentos": _intentos(u)} for u in estado.unidades],
        })
