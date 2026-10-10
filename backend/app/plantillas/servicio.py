# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/plantillas/servicio.py
# Descripcion: Writers de plantillas de registro y acciones rapidas (F05-03
#   J2 §1.6; F05 §45.3 A1/A2/A6, §45.4 R1/R3/R4, §46.3 A11; enmienda de
#   CC-03-8 del acta F05-D032 §6; D-032.2). API DE INTEGRACION F05, PENDIENTE
#   DE CONSOLIDACION F10.
#
#   Cada comando, en UNA transaccion de UnidadDeTrabajo (retry completo ante
#   40P01/40001), con este orden fijo (R3):
#     advisory (PLANTILLAS, owner)          <- SIEMPRE lo primero
#     -> plantilla(s) FOR NO KEY UPDATE -> accion(es) FOR NO KEY UPDATE, y
#        varias filas en orden UUID ascendente
#     -> validaciones (lecturas SIN lock de categoria, tercero, contexto y
#        cuenta: la FK solo toma KEY SHARE, compatible con el registro)
#     -> escritura -> auditoria.
#   El registro NO toma este advisory ni relee la plantilla (R2).
#
#   Plantillas (A1, A11, CC-03-8 enmendado):
#     - tipo GASTO o INGRESO; otro -> PLANTILLA_TIPO_NO_ADMITIDO (sin
#       plantillas de transferencia: una sola columna de cuenta);
#     - al menos uno de categoria, cuenta, presupuestable, tercero o contexto
#       -> PLANTILLA_SIN_VALOR;
#     - categoria del owner, habilitada y de ambito compatible con el tipo
#       (C-a por ambito, sin lock) -> PLANTILLA_CATEGORIA_NO_ELEGIBLE;
#     - tercero del owner y habilitado -> PLANTILLA_TERCERO_NO_ELEGIBLE;
#     - entidad SOLO si es un CONTEXTO habilitado del owner ->
#       PLANTILLA_ENTIDAD_NO_CONTEXTO (nunca vinculos arbitrarios);
#     - cuenta elegible para la operacion del tipo (regla unica R1, en la
#       fecha funcional del owner) -> PLANTILLA_CUENTA_NO_ELEGIBLE;
#     - nombre 1..100, unico entre las plantillas HABILITADAS del owner con la
#       normalizacion de C06, comprobado bajo el advisory ->
#       PLANTILLA_NOMBRE_REPETIDO (detalle plantilla_id); la reactivacion lo
#       vuelve a comprobar;
#     - nunca concepto, nota, importe, atribucion ni magnitudes (sin columnas).
#   Acciones rapidas (A2):
#     - la plantilla debe existir, ser del owner y estar habilitada ->
#       ACCION_PLANTILLA_NO_DISPONIBLE; una plantilla tiene a lo sumo un
#       acceso habilitado en Inicio -> ACCION_PLANTILLA_YA_EN_INICIO;
#     - limite de 3 habilitadas por owner -> ACCION_LIMITE_ALCANZADO;
#     - nombre corto 1..80; icono_key NULL (el de la categoria, solo
#       presentacion) o una clave PUBLICADA v1 -> ICONO_ACCION_NO_VALIDO;
#     - reordenacion atomica del conjunto COMPLETO de habilitadas
#       (CONJUNTO_ACCIONES_DESFASADO), desactivacion.
#   Desactivar una plantilla desactiva sus acciones en la MISMA transaccion
#   (savepoint de comando); reactivarla no las reactiva.
#   Identidad (E09): un UUID de otro owner (PK fisica) ->
#   IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin efectos. Una referencia ajena
#   que llegara al INSERT/UPDATE la rechaza la RLS (42501) y se traduce a
#   REFERENCIA_NO_DISPONIBLE (defensa; las validaciones la cortan antes).
#   Auditoria: CREAR en altas; ACTUALIZAR (motivo por operacion) en el resto.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.6)
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from app.api.elegibilidad_categoria import ambito_compatible
from app.categorias.iconos import icono_valido
from app.categorias.normalizacion import nombre_visible, normalizar
from app.comun.elegibilidad_cuentas import motivo_cuenta
from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.core.unidad_trabajo import SesionMotor
from app.plantillas import repositorio as repo
from app.repositories import auditoria_repository as auditoria

LONGITUD_NOMBRE = 100
LONGITUD_NOMBRE_ACCION = 80
LIMITE_ACCIONES = 3
TIPOS_ADMITIDOS = ("GASTO", "INGRESO")

MOTIVOS = {
    "ALTA": "F05-03 PLANTILLA ALTA",
    "EDITAR": "F05-03 PLANTILLA EDITAR",
    "DESACTIVAR": "F05-03 PLANTILLA DESACTIVAR",
    "REACTIVAR": "F05-03 PLANTILLA REACTIVAR",
    "ACCION_ALTA": "F05-03 ACCION ALTA",
    "ACCION_EDITAR": "F05-03 ACCION EDITAR",
    "ACCION_REORDENAR": "F05-03 ACCION REORDENAR",
    "ACCION_DESACTIVAR": "F05-03 ACCION DESACTIVAR",
    "ACCION_CASCADA": "F05-03 ACCION DESACTIVAR_POR_PLANTILLA",
}

TIPO_NO_ADMITIDO = "PLANTILLA_TIPO_NO_ADMITIDO"
SIN_VALOR = "PLANTILLA_SIN_VALOR"
CATEGORIA_NO_ELEGIBLE = "PLANTILLA_CATEGORIA_NO_ELEGIBLE"
TERCERO_NO_ELEGIBLE = "PLANTILLA_TERCERO_NO_ELEGIBLE"
ENTIDAD_NO_CONTEXTO = "PLANTILLA_ENTIDAD_NO_CONTEXTO"
CUENTA_NO_ELEGIBLE = "PLANTILLA_CUENTA_NO_ELEGIBLE"
NOMBRE_REPETIDO = "PLANTILLA_NOMBRE_REPETIDO"
PLANTILLA_NO_ENCONTRADA = "PLANTILLA_NO_ENCONTRADA"
ACCION_NO_ENCONTRADA = "ACCION_NO_ENCONTRADA"
ACCION_PLANTILLA_NO_DISPONIBLE = "ACCION_PLANTILLA_NO_DISPONIBLE"
ACCION_PLANTILLA_YA_EN_INICIO = "ACCION_PLANTILLA_YA_EN_INICIO"
ACCION_LIMITE_ALCANZADO = "ACCION_LIMITE_ALCANZADO"
ICONO_ACCION_NO_VALIDO = "ICONO_ACCION_NO_VALIDO"
CONJUNTO_DESFASADO = "CONJUNTO_ACCIONES_DESFASADO"
REFERENCIA_NO_DISPONIBLE = "REFERENCIA_NO_DISPONIBLE"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"

_CONSTRAINTS = {"pk_plantillas_registro": IDENTIDAD_REUTILIZADA, "pk_acciones_rapidas": IDENTIDAD_REUTILIZADA}
_CAMPOS = ("nombre", "tipo_hecho_id", "categoria_id", "tercero_id", "entidad_id", "cuenta_default_id",
           "presupuestable_default")


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    plantilla: dict[str, Any] | None = None
    accion: dict[str, Any] | None = None
    acciones: tuple[dict[str, Any], ...] = ()
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)


class _Abortar(Exception):
    def __init__(self, rechazo: Rechazo) -> None:
        super().__init__(rechazo.codigo)
        self.rechazo = rechazo


# ------------------------------------------------------------------ utilidades
def _escribir(sesion: SesionMotor, accion) -> Rechazo | None:
    """Escritura en un savepoint; traduce PK por identidad y la RLS (42501)
    a un codigo estable. Un fallo no reconocido se propaga."""
    try:
        with sesion.conexion.transaction():
            accion()
    except psycopg.Error as exc:
        if exc.sqlstate == "42501":
            return Rechazo(REFERENCIA_NO_DISPONIBLE)
        codigo = _CONSTRAINTS.get(exc.diag.constraint_name)
        if codigo is None:
            raise
        return Rechazo(codigo)
    return None


def _auditar(sesion: SesionMotor, tabla: str, registro_id, operacion: str, antes: str | None) -> None:
    despues = (repo.snapshot_plantilla if tabla == "plantillas_registro" else repo.snapshot_accion)(sesion, registro_id)
    auditoria.registrar(
        sesion, tabla=tabla, registro_id=registro_id,
        accion=auditoria.ACCION_CREAR if operacion in ("ALTA", "ACCION_ALTA") else auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=antes, datos_despues_json=despues, motivo=MOTIVOS[operacion],
    )


def _codigo_tipo(sesion: SesionMotor, tipo_hecho_id) -> str | None:
    fila = sesion.uno("SELECT codigo FROM gapto.tipos_hecho WHERE id = %s", (tipo_hecho_id,))
    return None if fila is None else fila[0]


def _uno(sesion: SesionMotor, sql: str, ident) -> tuple | None:
    return sesion.uno(sql + " AND owner_user_id = current_setting('gapto.owner_user_id')::uuid", (ident,))


def _validar(sesion: SesionMotor, v: dict[str, Any], reloj: Reloj) -> Rechazo | None:
    """Validaciones del contenido completo, en orden fijo. Sin locks."""
    visible = nombre_visible(v["nombre"]) if isinstance(v["nombre"], str) else ""
    if not 0 < len(visible) <= LONGITUD_NOMBRE:
        return Rechazo(ENTRADA_INVALIDA)
    codigo = _codigo_tipo(sesion, v["tipo_hecho_id"])
    if codigo not in TIPOS_ADMITIDOS:
        return Rechazo(TIPO_NO_ADMITIDO)
    if all(v[c] is None for c in ("categoria_id", "cuenta_default_id", "presupuestable_default", "tercero_id",
                                  "entidad_id")):
        return Rechazo(SIN_VALOR)
    if v["categoria_id"] is not None:
        fila = _uno(sesion, "SELECT enabled, ambito FROM gapto.categorias_financieras WHERE id = %s", v["categoria_id"])
        if fila is None or not fila[0] or not ambito_compatible(codigo, fila[1]):
            return Rechazo(CATEGORIA_NO_ELEGIBLE)
    if v["tercero_id"] is not None:
        fila = _uno(sesion, "SELECT enabled FROM gapto.terceros WHERE id = %s", v["tercero_id"])
        if fila is None or not fila[0]:
            return Rechazo(TERCERO_NO_ELEGIBLE)
    if v["entidad_id"] is not None:
        fila = _uno(sesion, "SELECT enabled, tipo_entidad FROM gapto.entidades WHERE id = %s", v["entidad_id"])
        if fila is None or not fila[0] or fila[1] != "CONTEXTO":
            return Rechazo(ENTIDAD_NO_CONTEXTO)
    if v["cuenta_default_id"] is not None and motivo_cuenta(
        sesion, v["cuenta_default_id"], codigo, hoy_owner(sesion, reloj)
    ) is not None:
        return Rechazo(CUENTA_NO_ELEGIBLE)
    return None


def _repetida(sesion: SesionMotor, nombre: str, propia) -> dict | None:
    """Plantilla HABILITADA del owner con el mismo nombre normalizado (C06)."""
    clave = normalizar(nombre)
    for p in repo.plantillas(sesion):
        if p["id"] != propia and p["enabled"] and normalizar(p["nombre"]) == clave:
            return p
    return None


def _valores(**kw) -> dict[str, Any]:
    v = {c: kw[c] for c in _CAMPOS}
    v["nombre"] = nombre_visible(v["nombre"]) if isinstance(v["nombre"], str) else v["nombre"]
    return v


def _plantilla(sesion: SesionMotor, plantilla_id, row_version: int) -> dict | Rechazo:
    fila = repo.leer_plantilla(sesion, plantilla_id, bloquear=True)
    if fila is None:
        return Rechazo(PLANTILLA_NO_ENCONTRADA)
    if fila["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    return fila


# ------------------------------------------------------------------ plantillas
def alta(sesion: SesionMotor, *, plantilla_id, nombre, tipo_hecho_id, categoria_id=None, tercero_id=None,
         entidad_id=None, cuenta_default_id=None, presupuestable_default=None,
         reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """Alta (tambien «Guardar como plantilla»: escritura independiente con su UUID)."""
    repo.tomar_advisory(sesion)
    v = _valores(nombre=nombre, tipo_hecho_id=tipo_hecho_id, categoria_id=categoria_id, tercero_id=tercero_id,
                 entidad_id=entidad_id, cuenta_default_id=cuenta_default_id,
                 presupuestable_default=presupuestable_default)
    existente = repo.leer_plantilla(sesion, plantilla_id)
    if existente is not None:
        igual = existente["row_version"] == 1 and existente["enabled"] and all(existente[c] == v[c] for c in _CAMPOS)
        return Resultado(plantilla=existente, idempotente=True) if igual else Rechazo(IDENTIDAD_REUTILIZADA)
    rechazo = _validar(sesion, v, reloj)
    if rechazo is not None:
        return rechazo
    otra = _repetida(sesion, v["nombre"], plantilla_id)
    if otra is not None:
        return Rechazo(NOMBRE_REPETIDO, {"plantilla_id": otra["id"]})
    rechazo = _escribir(sesion, lambda: repo.insertar_plantilla(sesion, plantilla_id=plantilla_id, v=v))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, "plantillas_registro", plantilla_id, "ALTA", None)
    return Resultado(plantilla=repo.leer_plantilla(sesion, plantilla_id), modificadas=(plantilla_id,))


def editar(sesion: SesionMotor, *, plantilla_id, row_version: int, nombre, tipo_hecho_id, categoria_id=None,
           tercero_id=None, entidad_id=None, cuenta_default_id=None, presupuestable_default=None,
           reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """Reemplazo COMPLETO (incluye el renombrado)."""
    repo.tomar_advisory(sesion)
    fila = _plantilla(sesion, plantilla_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    v = _valores(nombre=nombre, tipo_hecho_id=tipo_hecho_id, categoria_id=categoria_id, tercero_id=tercero_id,
                 entidad_id=entidad_id, cuenta_default_id=cuenta_default_id,
                 presupuestable_default=presupuestable_default)
    rechazo = _validar(sesion, v, reloj)
    if rechazo is not None:
        return rechazo
    cambios = {c: v[c] for c in _CAMPOS if fila[c] != v[c]}
    if not cambios:
        return Resultado(plantilla=fila, idempotente=True)
    if fila["enabled"]:
        otra = _repetida(sesion, v["nombre"], plantilla_id)
        if otra is not None:
            return Rechazo(NOMBRE_REPETIDO, {"plantilla_id": otra["id"]})
    antes = repo.snapshot_plantilla(sesion, plantilla_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_plantilla(sesion, plantilla_id, cambios))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, "plantillas_registro", plantilla_id, "EDITAR", antes)
    return Resultado(plantilla=repo.leer_plantilla(sesion, plantilla_id), modificadas=(plantilla_id,))


def desactivar(sesion: SesionMotor, *, plantilla_id, row_version: int) -> Resultado | Rechazo:
    """Desactiva la plantilla y, en la MISMA transaccion, sus acciones
    habilitadas (plantilla -> acciones en orden de id)."""
    repo.tomar_advisory(sesion)
    fila = _plantilla(sesion, plantilla_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    accs = repo.acciones_de_plantilla_bloqueadas(sesion, plantilla_id)
    if not fila["enabled"] and not accs:
        return Resultado(plantilla=fila, idempotente=True)
    modificadas: list[uuid.UUID] = []
    try:
        with sesion.conexion.transaction():  # savepoint de alcance de comando
            if fila["enabled"]:
                antes = repo.snapshot_plantilla(sesion, plantilla_id)
                r = _escribir(sesion, lambda: repo.actualizar_plantilla(sesion, plantilla_id, {"enabled": False}))
                if r is not None:
                    raise _Abortar(r)
                _auditar(sesion, "plantillas_registro", plantilla_id, "DESACTIVAR", antes)
                modificadas.append(plantilla_id)
            for a in accs:
                antes = repo.snapshot_accion(sesion, a["id"])
                r = _escribir(sesion, lambda a=a: repo.actualizar_accion(sesion, a["id"], {"enabled": False}))
                if r is not None:
                    raise _Abortar(r)
                _auditar(sesion, "acciones_rapidas", a["id"], "ACCION_CASCADA", antes)
                modificadas.append(a["id"])
    except _Abortar as abortado:
        return abortado.rechazo
    return Resultado(plantilla=repo.leer_plantilla(sesion, plantilla_id), modificadas=tuple(modificadas))


def reactivar(sesion: SesionMotor, *, plantilla_id, row_version: int) -> Resultado | Rechazo:
    """Reactiva SOLO la plantilla (sus acciones no vuelven a Inicio solas) y
    vuelve a comprobar la unicidad del nombre."""
    repo.tomar_advisory(sesion)
    fila = _plantilla(sesion, plantilla_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    if fila["enabled"]:
        return Resultado(plantilla=fila, idempotente=True)
    otra = _repetida(sesion, fila["nombre"], plantilla_id)
    if otra is not None:
        return Rechazo(NOMBRE_REPETIDO, {"plantilla_id": otra["id"]})
    antes = repo.snapshot_plantilla(sesion, plantilla_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_plantilla(sesion, plantilla_id, {"enabled": True}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, "plantillas_registro", plantilla_id, "REACTIVAR", antes)
    return Resultado(plantilla=repo.leer_plantilla(sesion, plantilla_id), modificadas=(plantilla_id,))


# ------------------------------------------------------------------ acciones rapidas
def _nombre_accion(nombre) -> str | None:
    visible = nombre_visible(nombre) if isinstance(nombre, str) else ""
    return visible if 0 < len(visible) <= LONGITUD_NOMBRE_ACCION else None


def alta_accion(sesion: SesionMotor, *, accion_id, plantilla_id, nombre, icono_key=None) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    plantilla = repo.leer_plantilla(sesion, plantilla_id, bloquear=True)
    visible = _nombre_accion(nombre)
    if visible is None:
        return Rechazo(ENTRADA_INVALIDA)
    if not icono_valido(icono_key):
        return Rechazo(ICONO_ACCION_NO_VALIDO)
    habilitadas = repo.acciones_habilitadas_bloqueadas(sesion)
    existente = repo.leer_accion(sesion, accion_id)
    if existente is not None:
        igual = (existente["row_version"] == 1 and existente["enabled"] and existente["nombre"] == visible
                 and existente["plantilla_registro_id"] == plantilla_id and existente["icono_key"] == icono_key)
        return Resultado(accion=existente, idempotente=True) if igual else Rechazo(IDENTIDAD_REUTILIZADA)
    if plantilla is None or not plantilla["enabled"]:
        return Rechazo(ACCION_PLANTILLA_NO_DISPONIBLE)
    if any(a["plantilla_registro_id"] == plantilla_id for a in habilitadas):
        return Rechazo(ACCION_PLANTILLA_YA_EN_INICIO)
    if len(habilitadas) >= LIMITE_ACCIONES:
        return Rechazo(ACCION_LIMITE_ALCANZADO)
    orden = max((a["orden"] for a in habilitadas), default=-1) + 1
    rechazo = _escribir(sesion, lambda: repo.insertar_accion(
        sesion, accion_id=accion_id, nombre=visible, plantilla_id=plantilla_id, orden=orden, icono_key=icono_key))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, "acciones_rapidas", accion_id, "ACCION_ALTA", None)
    return Resultado(accion=repo.leer_accion(sesion, accion_id), modificadas=(accion_id,))


def _accion(sesion: SesionMotor, accion_id, row_version: int) -> dict | Rechazo:
    fila = repo.leer_accion(sesion, accion_id, bloquear=True)
    if fila is None:
        return Rechazo(ACCION_NO_ENCONTRADA)
    if fila["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    return fila


def editar_accion(sesion: SesionMotor, *, accion_id, row_version: int, nombre, icono_key=None) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    fila = _accion(sesion, accion_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    visible = _nombre_accion(nombre)
    if visible is None:
        return Rechazo(ENTRADA_INVALIDA)
    if not icono_valido(icono_key):
        return Rechazo(ICONO_ACCION_NO_VALIDO)
    cambios = {k: x for k, x in (("nombre", visible), ("icono_key", icono_key)) if fila[k] != x}
    if not cambios:
        return Resultado(accion=fila, idempotente=True)
    antes = repo.snapshot_accion(sesion, accion_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_accion(sesion, accion_id, cambios))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, "acciones_rapidas", accion_id, "ACCION_EDITAR", antes)
    return Resultado(accion=repo.leer_accion(sesion, accion_id), modificadas=(accion_id,))


def desactivar_accion(sesion: SesionMotor, *, accion_id, row_version: int) -> Resultado | Rechazo:
    repo.tomar_advisory(sesion)
    fila = _accion(sesion, accion_id, row_version)
    if isinstance(fila, Rechazo):
        return fila
    if not fila["enabled"]:
        return Resultado(accion=fila, idempotente=True)
    antes = repo.snapshot_accion(sesion, accion_id)
    rechazo = _escribir(sesion, lambda: repo.actualizar_accion(sesion, accion_id, {"enabled": False}))
    if rechazo is not None:
        return rechazo
    _auditar(sesion, "acciones_rapidas", accion_id, "ACCION_DESACTIVAR", antes)
    return Resultado(accion=repo.leer_accion(sesion, accion_id), modificadas=(accion_id,))


def reordenar_acciones(sesion: SesionMotor, *, acciones: list[tuple[uuid.UUID, int]]) -> Resultado | Rechazo:
    """`acciones`: [(id, row_version)] en el orden deseado; debe ser el conjunto
    COMPLETO de acciones habilitadas del owner. Atomico."""
    repo.tomar_advisory(sesion)
    persistidas = {a["id"]: a for a in repo.acciones_habilitadas_bloqueadas(sesion)}
    pedidas = [i for i, _ in acciones]
    if not pedidas or len(set(pedidas)) != len(pedidas) or set(pedidas) != set(persistidas):
        return Rechazo(CONJUNTO_DESFASADO)
    if any(persistidas[i]["row_version"] != rv for i, rv in acciones):
        return Rechazo(VERSION_DESFASADA)
    cambian = [(i, pos) for pos, i in enumerate(pedidas) if persistidas[i]["orden"] != pos]
    for i, pos in cambian:
        antes = repo.snapshot_accion(sesion, i)
        rechazo = _escribir(sesion, lambda i=i, pos=pos: repo.actualizar_accion(sesion, i, {"orden": pos}))
        if rechazo is not None:
            return rechazo
        _auditar(sesion, "acciones_rapidas", i, "ACCION_REORDENAR", antes)
    return Resultado(acciones=tuple(repo.leer_accion(sesion, i) for i in pedidas), idempotente=not cambian,
                     modificadas=tuple(i for i, _ in cambian))
