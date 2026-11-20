# ============================================================
# GAPTO MOBILE 2027
# Fichero: base.py
# Ruta: backend/app/contratos/base.py
# Descripcion: Piezas comunes de los writers de F06-02/03 (contrato v1.1 §1.2, §1.3 y §1.5):
#   - `ejecutar_escritura`: TODAS las escrituras de una operacion en UN savepoint; un rechazo de dominio
#     (`Abortar`) o una violacion fisica del mapa de errores.py deshacen el savepoint completo (estado byte a
#     byte igual) y se devuelven como Rechazo; una violacion FUERA del mapa se propaga (500 generico, sin
#     disfraz: politica de exclusion).
#   - `replay`: idempotencia por auditoria con request_id = intencion_id (patron B1): misma operacion y mismo
#     contenido sellado -> True; cualquier otra auditoria con esa intencion -> IDENTIDAD_REUTILIZADA.
#   - `auditar`: auditoria de la raiz (`entidades`) con la intencion sellada.
#   - `bloquear_terceros`: nivel 4 y 5 de §1.3 (advisory de terceros solo si se CREA uno; terceros FOR SHARE por
#     UUID ascendente).
#   El primer recurso de cada writer es el 0P (`bloquear_intencion_propiedad`, importada, nunca copiada: test_233).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 3)
# ============================================================

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

import psycopg

from app.actores import repositorio as repo_act
from app.actores import servicio as serv_act
from app.contratos import errores as e
from app.contratos.modelos import NuevoTercero, Rechazo
from app.core.unidad_trabajo import SesionMotor
from app.propiedades import repositorio as repo_prop
from app.propiedades.servicio import bloquear_intencion_propiedad  # noqa: F401  (0P: se importa, nunca se copia)
from app.repositories import auditoria_repository as auditoria
from app.terceros import repositorio as repo_ter
from app.terceros import servicio as serv_ter

TABLA = "entidades"
MOTIVO_ACTOR = "F06-02/03: alta del actor financiero de una parte del contrato"
#: Tablas cuyas auditorias acompanan legitimamente a la raiz en una misma intencion.
TABLAS_ACCESORIAS = frozenset({"actores_financieros", "terceros"})
TRIGGERS_SUBTIPO_CONTRATO = "gapto.trg_entidades__subtipo_unico, gapto.trg_contratos__subtipo_unico"
TRIGGERS_SUBTIPO_SERVICIO = "gapto.trg_entidades__subtipo_unico, gapto.trg_servicios__subtipo_unico"
_TRADUCCION_TERCERO = {"TERCERO_NATURALEZA_NO_ADMITIDA": e.ENTRADA_INVALIDA}


class Abortar(Exception):
    """Sale del savepoint de la operacion con un rechazo de dominio (deshace TODAS sus escrituras)."""

    def __init__(self, rechazo: Rechazo) -> None:
        super().__init__(rechazo.codigo)
        self.rechazo = rechazo


def ejecutar_escritura(sesion: SesionMotor, accion: Callable[[], None], *, triggers: str | None = None) -> Rechazo | None:
    """Ejecuta `accion` en un savepoint. Devuelve None si todo fue bien o el Rechazo traducido."""
    conexion = sesion.conexion
    try:
        with conexion.transaction():
            accion()
            if triggers:
                conexion.execute(f"SET CONSTRAINTS {triggers} IMMEDIATE")
    except Abortar as exc:
        return exc.rechazo
    except serv_act.RechazoActor as exc:
        return Rechazo(exc.codigo, {"tercero_id": str(exc.tercero_id)})
    except psycopg.Error as exc:
        codigo = e.traducir_fisico(exc)
        if codigo is None:
            raise  # politica de exclusion: constraint fuera del mapa -> error generico registrado
        return Rechazo(codigo)
    finally:
        if triggers:
            conexion.execute(f"SET CONSTRAINTS {triggers} DEFERRED")
    return None


def replay(sesion: SesionMotor, intencion_id: uuid.UUID, operacion: str, registro_id: uuid.UUID,
           contenido: dict[str, Any], registros_extra: tuple[uuid.UUID, ...] = (),
           tabla: str = TABLA) -> bool | Rechazo:
    """True = reintento identico; False = intencion nueva; Rechazo = reutilizada con otra intencion. `tabla` es la de
    la raiz auditada (`entidades` para contratos y servicios; `terceros` o `clasificaciones_tercero` en C-TER)."""
    auditadas = repo_prop.auditorias_de_intencion(sesion, intencion_id)
    if not auditadas:
        return False
    raiz = [a for a in auditadas if a["tabla"] == tabla and a["registro_id"] == registro_id]
    resto_valido = all(a["tabla"] in TABLAS_ACCESORIAS or (a["tabla"] == tabla and a["registro_id"] in registros_extra)
                       for a in auditadas if not (a["tabla"] == tabla and a["registro_id"] == registro_id))
    if len(raiz) == 1 and resto_valido:
        sellada = (json.loads(raiz[0]["despues"]) or {}).get("intencion") or {}
        if sellada.get("operacion") == operacion and sellada.get("contenido") == contenido:
            return True
    return Rechazo(e.IDENTIDAD_REUTILIZADA)


def auditar(sesion: SesionMotor, entidad_id: uuid.UUID, *, operacion: str, motivo: str, antes: str | None,
            despues: str, contenido: dict[str, Any], crear: bool = False, motivo_usuario: str | None = None,
            extra: dict[str, Any] | None = None, tabla: str = TABLA) -> None:
    """Auditoria de la raiz con la intencion sellada (operacion + contenido + datos auxiliares del writer)."""
    foto = json.loads(despues)
    foto["intencion"] = {"operacion": operacion, "contenido": contenido, **(extra or {})}
    auditoria.registrar(
        sesion, tabla=tabla, registro_id=entidad_id,
        accion=auditoria.ACCION_CREAR if crear else auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=antes, datos_despues_json=json.dumps(foto, ensure_ascii=False),
        motivo=motivo + (f": {motivo_usuario}" if motivo_usuario else ""))


def bloquear_terceros(sesion: SesionMotor, *, existentes: list[uuid.UUID],
                      nuevos: list[NuevoTercero]) -> dict[uuid.UUID, dict[str, Any] | None]:
    """Nivel 4 (advisory de terceros de F05, SOLO si la operacion crea terceros) y nivel 5 (terceros FOR SHARE por
    UUID ascendente). Devuelve {tercero_id: fila|None}; los `nuevos` figuran como None si no existen todavia."""
    if nuevos:
        repo_ter.tomar_advisory(sesion)
    leidos: dict[uuid.UUID, dict[str, Any] | None] = {}
    for tid in sorted(set(existentes), key=str):
        leidos[tid] = repo_act.leer_tercero_compartido(sesion, tid)
    for nt in sorted(nuevos, key=lambda n: str(n.id)):
        leidos[nt.id] = repo_ter.leer(sesion, nt.id)
    return leidos


def crear_tercero(sesion: SesionMotor, nt: NuevoTercero) -> None:
    """Writer de F05 (`terceros.servicio.alta`) tal cual; un rechazo aborta la operacion entera."""
    salida = serv_ter.alta(sesion, tercero_id=nt.id, nombre=nt.nombre, naturaleza=nt.naturaleza)
    if isinstance(salida, serv_ter.Rechazo):
        raise Abortar(Rechazo(_TRADUCCION_TERCERO.get(salida.codigo, salida.codigo), salida.detalle))


def actor_de(sesion: SesionMotor, tercero_id: uuid.UUID) -> uuid.UUID:
    """Actor del tercero (lo crea si no existe) con el precedente certificado de hipotecas/alta.py: el tercero ya
    esta FOR SHARE y habilitado; no se exige PERSONA (agencias y administradores son empresas)."""
    return serv_act.actor_de_tercero(sesion, tercero_id, MOTIVO_ACTOR)
