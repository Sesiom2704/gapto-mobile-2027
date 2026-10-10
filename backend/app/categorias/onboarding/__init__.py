# ============================================================
# GAPTO MOBILE 2027
# Fichero: __init__.py
# Ruta: backend/app/categorias/onboarding/__init__.py
# Descripcion: Onboarding de categorias sugeridas (F05-03 J2 §1.8; F05 §45.3
#   A8, §45.4 R5; F05-D032 C5). API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   FICHERO: F05-03_categorias_sugeridas_v1.md de este paquete, copia byte a
#   byte del fichero aprobado por Moises (2026-10-09). Antes de parsear se
#   coteja su SHA-256 COMPLETO (SHA256_V1); cualquier diferencia aborta.
#
#   CONTRATO DEL PARSER (`parsear`):
#     - version: la del titulo («— versión N»); debe ser VERSION (1);
#     - filas de la tabla `| # | Categoría | Ámbito | Presupuesto por defecto |
#       Icono (clave v1) | Nota |`, con # consecutivo 1..n (= orden del fichero);
#     - nivel por el nombre: «**Nombre**» = grupo (nivel 0); «— Nombre» =
#       nivel 1; «— — Nombre» = nivel 2. El padre es el ultimo nodo del nivel
#       anterior: los padres van SIEMPRE antes que los hijos;
#     - id estable del nodo = ruta normalizada (normalizacion C06 de cada
#       segmento, unidos por «/»); el UUID de la categoria es
#       uuid5(owner, «gapto.f05.onboarding.v1:» + ruta), determinista;
#     - orden = posicion entre sus hermanos en el orden del fichero;
#     - ambito (GASTO | INGRESO | AMBOS), presupuestable_default (Sí | No) e
#       icon_key (clave PUBLICADA de la biblioteca v1) OBLIGATORIOS;
#     - rechazo (ErrorFichero) de: version distinta, fila mal formada, campo
#       ausente o desconocido, nivel sin padre (salto de nivel), # no
#       consecutivo, ruta duplicada o hermanos con el mismo nombre normalizado
#       (ambiguedad). Cero defaults inventados: ningun dato se deduce.
#   La «clave estable» del fichero (codigo = «sug.» + nombre normalizado) NO
#   se persiste: el CHECK fisico ck_categorias_financieras__codigo_formato
#   solo admite ^[A-Z0-9]+(_[A-Z0-9]+)*$ (sin DDL). La identidad estable es
#   el UUID determinista por ruta (desviacion declarada en el handoff J2J3).
#
#   COMANDO `onboarding_categorias` (R5), en la transaccion de la UdT:
#     advisory (CATEGORIAS, owner)  (el mismo de C06; reentrante)
#     -> recuento de categorias del owner (habilitadas o no) bajo el advisory:
#        0 -> crea el arbol COMPLETO con los writers de C06 (alta y
#        reordenar por padre), en un savepoint de comando: cualquier rechazo
#        o fallo deja CERO categorias (rollback del savepoint o de la UdT);
#        el arbol EXACTO de esta version -> idempotente, sin escribir;
#        cualquier otro estado -> ONBOARDING_NO_APLICABLE (tambien un tenant
#        migrado de V3, que nunca tiene cero categorias).
#   Auditoria: la de los writers de C06 (CREAR por nodo, ACTUALIZAR por
#   reorden). Sin camino de escritura propio.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.8)
# ============================================================

from __future__ import annotations

import hashlib
import pathlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

from app.categorias import servicio as serv_cat
from app.categorias.iconos import CLAVES_PUBLICADAS
from app.categorias.normalizacion import normalizar
from app.core.unidad_trabajo import SesionMotor

FICHERO = pathlib.Path(__file__).resolve().parent / "F05-03_categorias_sugeridas_v1.md"
SHA256_V1 = "929b308e38f18da44d047e17dc7e5f2f0bf8be7446da9f7c725e93b915cc3fcc"
VERSION = 1
NODOS_V1 = 93
GRUPOS_V1 = 23
NO_APLICABLE = "ONBOARDING_NO_APLICABLE"
AMBITOS = frozenset({"GASTO", "INGRESO", "AMBOS"})
PRESUPUESTO = {"Sí": True, "No": False}

_TITULO = re.compile(r"^# .*— versión (\d+)\b")
_FILA = re.compile(r"^\|\s*(\d+)\s*\|(.*)\|\s*$")
_GRUPO = re.compile(r"^\*\*(.+)\*\*$")
_HIJO = re.compile(r"^((?:— )+)(.+)$")
_ICONO = re.compile(r"^`([^`]+)`$")


class ErrorFichero(Exception):
    """El fichero no cumple el contrato del parser (nunca se corrige)."""


@dataclass(frozen=True)
class Nodo:
    ruta: str
    nombre: str
    nivel: int
    padre: str | None
    orden: int
    ambito: str
    presupuestable_default: bool
    icon_key: str


def leer_fichero() -> bytes:
    contenido = FICHERO.read_bytes()
    if hashlib.sha256(contenido).hexdigest() != SHA256_V1:
        raise ErrorFichero("SHA-256 del fichero de categorias sugeridas distinto del aprobado")
    return contenido


def parsear(contenido: bytes) -> list[Nodo]:
    texto = contenido.decode("utf-8")
    lineas = texto.splitlines()
    m = _TITULO.match(lineas[0]) if lineas else None
    if m is None or int(m.group(1)) != VERSION:
        raise ErrorFichero("version del fichero ausente o distinta de la soportada")
    nodos: list[Nodo] = []
    ultimo_por_nivel: dict[int, Nodo] = {}
    hermanos: dict[str | None, list[str]] = {}
    esperado = 1
    for linea in lineas:
        f = _FILA.match(linea)
        if f is None:
            continue
        numero = int(f.group(1))
        celdas = [c.strip() for c in f.group(2).split("|")]
        if len(celdas) != 5:
            raise ErrorFichero(f"fila {numero}: numero de columnas distinto de 6")
        if numero != esperado:
            raise ErrorFichero(f"fila {numero}: numeracion no consecutiva (se esperaba {esperado})")
        esperado += 1
        nombre_celda, ambito, presupuesto, icono, _nota = celdas
        g = _GRUPO.match(nombre_celda)
        if g is not None:
            nivel, nombre = 0, g.group(1).strip()
        else:
            h = _HIJO.match(nombre_celda)
            if h is None:
                raise ErrorFichero(f"fila {numero}: nombre sin nivel reconocible")
            nivel, nombre = h.group(1).count("—"), h.group(2).strip()
        if not nombre:
            raise ErrorFichero(f"fila {numero}: nombre ausente")
        if ambito not in AMBITOS:
            raise ErrorFichero(f"fila {numero}: ambito ausente o desconocido")
        if presupuesto not in PRESUPUESTO:
            raise ErrorFichero(f"fila {numero}: presupuesto por defecto ausente o desconocido")
        ic = _ICONO.match(icono)
        if ic is None or ic.group(1) not in CLAVES_PUBLICADAS:
            raise ErrorFichero(f"fila {numero}: icono ausente o no publicado en la biblioteca v1")
        padre = None
        if nivel > 0:
            if (nivel - 1) not in ultimo_por_nivel:
                raise ErrorFichero(f"fila {numero}: nivel {nivel} sin padre")
            padre = ultimo_por_nivel[nivel - 1].ruta
        clave = normalizar(nombre)
        ruta = clave if padre is None else f"{padre}/{clave}"
        if clave in hermanos.setdefault(padre, []):
            raise ErrorFichero(f"fila {numero}: ruta duplicada o ambigua ({ruta})")
        hermanos[padre].append(clave)
        nodo = Nodo(ruta=ruta, nombre=nombre, nivel=nivel, padre=padre, orden=len(hermanos[padre]) - 1,
                    ambito=ambito, presupuestable_default=PRESUPUESTO[presupuesto], icon_key=ic.group(1))
        nodos.append(nodo)
        ultimo_por_nivel[nivel] = nodo
        for mas_profundo in [n for n in ultimo_por_nivel if n > nivel]:
            del ultimo_por_nivel[mas_profundo]
    return nodos


def arbol_v1() -> list[Nodo]:
    nodos = parsear(leer_fichero())
    grupos = sum(1 for n in nodos if n.nivel == 0)
    if len(nodos) != NODOS_V1 or grupos != GRUPOS_V1:
        raise ErrorFichero(f"el fichero describe {len(nodos)} nodos y {grupos} grupos (esperado 93 / 23)")
    return nodos


def id_categoria(owner: uuid.UUID, ruta: str) -> uuid.UUID:
    return uuid.uuid5(owner, f"gapto.f05.onboarding.v{VERSION}:{ruta}")


# ------------------------------------------------------------------ comando
@dataclass(frozen=True)
class Resultado:
    creadas: tuple[uuid.UUID, ...]
    idempotente: bool


class _Abortar(Exception):
    def __init__(self, rechazo: serv_cat.Rechazo) -> None:
        super().__init__(rechazo.codigo)
        self.rechazo = rechazo


def _todas(sesion: SesionMotor) -> list[dict[str, Any]]:
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT id, parent_id, nombre, ambito, presupuestable_default, icon_key, orden, enabled "
            "FROM gapto.categorias_financieras "
            "WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid"
        )
        claves = ("id", "parent_id", "nombre", "ambito", "presupuestable_default", "icon_key", "orden", "enabled")
        return [dict(zip(claves, f)) for f in cur.fetchall()]


def _es_el_arbol(existentes: list[dict[str, Any]], esperado: dict[uuid.UUID, dict[str, Any]]) -> bool:
    if len(existentes) != len(esperado):
        return False
    for e in existentes:
        x = esperado.get(e["id"])
        if x is None or any(e[k] != x[k] for k in x):
            return False
    return True


def onboarding_categorias(sesion: SesionMotor) -> Resultado | serv_cat.Rechazo:
    serv_cat.tomar_advisory_del_catalogo(sesion)
    owner = sesion.uno("SELECT current_setting('gapto.owner_user_id')::uuid")[0]
    nodos = arbol_v1()
    ids = {n.ruta: id_categoria(owner, n.ruta) for n in nodos}
    esperado = {
        ids[n.ruta]: {"parent_id": None if n.padre is None else ids[n.padre], "nombre": n.nombre,
                      "ambito": n.ambito, "presupuestable_default": n.presupuestable_default,
                      "icon_key": n.icon_key, "orden": n.orden, "enabled": True}
        for n in nodos
    }
    existentes = _todas(sesion)
    if existentes:
        if _es_el_arbol(existentes, esperado):
            return Resultado(creadas=(), idempotente=True)
        return serv_cat.Rechazo(NO_APLICABLE)
    try:
        with sesion.conexion.transaction():  # savepoint de alcance de comando
            for n in nodos:
                r = serv_cat.alta(sesion, categoria_id=ids[n.ruta], nombre=n.nombre,
                                  parent_id=None if n.padre is None else ids[n.padre], ambito=n.ambito,
                                  presupuestable_default=n.presupuestable_default, icon_key=n.icon_key)
                if isinstance(r, serv_cat.Rechazo):
                    raise _Abortar(r)
            padres: dict[str | None, list[Nodo]] = {}
            for n in nodos:
                padres.setdefault(n.padre, []).append(n)
            for padre, hijos in padres.items():
                if len(hijos) < 2:
                    continue
                r = serv_cat.reordenar(sesion, parent_id=None if padre is None else ids[padre],
                                       hermanos=[(ids[h.ruta], 1) for h in hijos])
                if isinstance(r, serv_cat.Rechazo):
                    raise _Abortar(r)
    except _Abortar as abortado:
        return abortado.rechazo
    return Resultado(creadas=tuple(ids[n.ruta] for n in nodos), idempotente=False)
