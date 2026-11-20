# ============================================================
# GAPTO MOBILE 2027
# Fichero: terceros.py
# Ruta: backend/app/contratos/terceros.py
# Descripcion: Escrituras de terceros de F06-02/03 (contrato v1.1 Parte V; Q-CON-13: AÑADIR Y EDITAR, NUNCA
#   RETIRAR):
#     C-TER-01 roles de un tercero (`anadir`; quitar -> RETIRADA_NO_ADMITIDA; AGENCIA y ADMINISTRADOR no son roles
#              de tercero: decision 2 = A)
#     C-TER-03 clasificacion: asignar (y editar `principal`), y el arbol (crear, renombrar, mover,
#              desactivar/reactivar con `enabled`; sin DELETE; sin ciclos; nombre unico entre hermanos activos)
#   C-TER-02 (direcciones) QUEDA FUERA del bloque (D-A-04): ninguna operacion de direcciones aqui.
#   Orden de recursos de las escrituras de terceros (§1.3): 0P -> advisory de terceros de F05 -> tercero
#   (FOR NO KEY UPDATE; sube `terceros.row_version` con terceros.repositorio.incrementar_version) -> hijas.
#   NUNCA toman una propiedad ni un contrato, asi que no forman ciclo con el orden de contratos.
#   El SQL de las hijas vive en contratos/repositorio.py (fuera de CAPA_F05, test_182).
#   C-31 CERRADO (decision de Moises del 19-11; contrato v1.2 §1.5, bbceffda…): CLASIFICACION_CICLO se traduce por la firma de gapto.fn_check_jerarquia_aciclica()
#   (trigger diferido forzado a IMMEDIATE dentro del savepoint), como en categorias/servicio.py.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import uuid
from typing import Any, Callable

from app.categorias.normalizacion import nombre_visible
from app.contratos import errores as e
from app.contratos import modelos as m
from app.contratos import repositorio as repo
from app.contratos.base import auditar, bloquear_intencion_propiedad, ejecutar_escritura, replay
from app.contratos.modelos import Rechazo, Resultado
from app.core.unidad_trabajo import SesionMotor
from app.terceros import repositorio as repo_ter

OP_ROLES, OP_ASIGNAR = "TERCERO_ROLES", "TERCERO_CLASIFICACIONES"
OP_CLAS_ALTA, OP_CLAS_RENOMBRAR, OP_CLAS_MOVER = "CLASIFICACION_ALTA", "CLASIFICACION_RENOMBRAR", "CLASIFICACION_MOVER"
OP_CLAS_DESACTIVAR, OP_CLAS_REACTIVAR = "CLASIFICACION_DESACTIVAR", "CLASIFICACION_REACTIVAR"
MOTIVOS = {
    OP_ROLES: "F06-02/03 TERCERO ROLES", OP_ASIGNAR: "F06-02/03 TERCERO CLASIFICACIONES",
    OP_CLAS_ALTA: "F06-02/03 CLASIFICACION ALTA", OP_CLAS_RENOMBRAR: "F06-02/03 CLASIFICACION RENOMBRAR",
    OP_CLAS_MOVER: "F06-02/03 CLASIFICACION MOVER", OP_CLAS_DESACTIVAR: "F06-02/03 CLASIFICACION DESACTIVAR",
    OP_CLAS_REACTIVAR: "F06-02/03 CLASIFICACION REACTIVAR",
}
TABLA_TERCEROS, TABLA_CLASIFICACIONES = "terceros", "clasificaciones_tercero"
TRIGGER_ACICLICA = "gapto.trg_clasificaciones_tercero__aciclica"
LONGITUD_CLASIFICACION = 100


def _vista_tercero(sesion: SesionMotor, tercero_id: uuid.UUID) -> dict[str, Any]:
    t = repo.tercero_con_hijas(sesion, tercero_id)
    assert t is not None
    return {**t, "roles": repo.roles_de_tercero(sesion, tercero_id),
            "clasificaciones": repo.clasificaciones_de_tercero(sesion, tercero_id)}


def _abrir_tercero(sesion: SesionMotor, *, tercero_id: uuid.UUID, intencion_id: uuid.UUID, operacion: str,
                   contenido: dict[str, Any], row_version: int) -> dict[str, Any] | Resultado | Rechazo:
    """0P -> advisory de terceros -> tercero FOR NO KEY UPDATE -> replay -> VERSION_DESFASADA."""
    bloquear_intencion_propiedad(sesion, intencion_id)
    repo_ter.tomar_advisory(sesion)
    t = repo_ter.leer(sesion, tercero_id, bloquear=True)
    if t is None:
        return Rechazo(e.TERCERO_NO_ENCONTRADO)
    previo = replay(sesion, intencion_id, operacion, tercero_id, contenido, tabla=TABLA_TERCEROS)
    if previo is True:
        return Resultado(dato=_vista_tercero(sesion, tercero_id), idempotente=True)
    if isinstance(previo, Rechazo):
        return previo
    if t["row_version"] != row_version:
        return Rechazo(e.VERSION_DESFASADA)
    return t


# ------------------------------------------------------------------ C-TER-01 roles
def anadir_roles(sesion: SesionMotor, *, tercero_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                 anadir: list[str], quitar: list[str] | None = None) -> Resultado | Rechazo:
    """Añade roles (no manda el conjunto completo). Un rol ya presente cuenta como «ya está» (no escribe). Quitar
    -> RETIRADA_NO_ADMITIDA. «Editar» un rol no existe: corregir es añadir el correcto; el erroneo se queda."""
    if any(r not in m.ROLES_TERCERO for r in anadir):
        return Rechazo(e.ROL_DESCONOCIDO)                    # AGENCIA/ADMINISTRADOR no son roles de tercero
    if not anadir and not quitar:
        return Rechazo(e.ENTRADA_INVALIDA)
    contenido = {"row_version_esperada": row_version, "anadir": sorted(set(anadir)), "quitar": sorted(quitar or [])}
    t = _abrir_tercero(sesion, tercero_id=tercero_id, intencion_id=intencion_id, operacion=OP_ROLES,
                       contenido=contenido, row_version=row_version)
    if not isinstance(t, dict):
        return t
    if quitar:
        return Rechazo(e.RETIRADA_NO_ADMITIDA)
    antes = repo.snapshot_tercero_con_hijas(sesion, tercero_id)
    nuevos: list[str] = []

    def escribir() -> None:
        for rol in sorted(set(anadir)):
            if repo.insertar_rol_si_no_existe(sesion, tercero_id, rol):
                nuevos.append(rol)
        if nuevos:
            repo_ter.incrementar_version(sesion, tercero_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    if not nuevos:
        return Resultado(dato=_vista_tercero(sesion, tercero_id), idempotente=True,
                         extra={"ya_estaban": sorted(set(anadir))})
    auditar(sesion, tercero_id, operacion=OP_ROLES, motivo=MOTIVOS[OP_ROLES], antes=antes,
            despues=repo.snapshot_tercero_con_hijas(sesion, tercero_id), contenido=contenido, tabla=TABLA_TERCEROS)
    return Resultado(dato=_vista_tercero(sesion, tercero_id), modificadas=(tercero_id,),
                     extra={"anadidos": nuevos, "ya_estaban": sorted(set(anadir) - set(nuevos))})


# ------------------------------------------------------------------ C-TER-03 clasificacion de un tercero
def asignar_clasificaciones(sesion: SesionMotor, *, tercero_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                            anadir: list[uuid.UUID], principal: uuid.UUID | None, principal_presente: bool,
                            quitar: list[uuid.UUID] | None = None) -> Resultado | Rechazo:
    """Asigna clasificaciones y/o fija la `principal` (como mucho una por tercero: regla de servicio, no hay
    restriccion fisica). Editar la asignacion = UPDATE auditado de `principal`. Desasignar -> RETIRADA_NO_ADMITIDA."""
    if not anadir and not principal_presente and not quitar:
        return Rechazo(e.ENTRADA_INVALIDA)
    contenido = {"row_version_esperada": row_version, "anadir": sorted(str(a) for a in set(anadir)),
                 "principal": m.texto(principal), "principal_presente": principal_presente,
                 "quitar": sorted(str(q) for q in (quitar or []))}
    t = _abrir_tercero(sesion, tercero_id=tercero_id, intencion_id=intencion_id, operacion=OP_ASIGNAR,
                       contenido=contenido, row_version=row_version)
    if not isinstance(t, dict):
        return t
    if quitar:
        return Rechazo(e.RETIRADA_NO_ADMITIDA)
    for cid in sorted(set(anadir), key=str):
        c = repo.clasificacion(sesion, cid)
        if c is None:
            return Rechazo(e.AGREGADO_NO_ENCONTRADO)
        if not c["enabled"]:
            return Rechazo(e.ENTRADA_INVALIDA)
    asignadas = {f["clasificacion_id"] for f in repo.clasificaciones_de_tercero(sesion, tercero_id)}
    if principal_presente and principal is not None and principal not in asignadas | set(anadir):
        return Rechazo(e.ENTRADA_INVALIDA)
    antes = repo.snapshot_tercero_con_hijas(sesion, tercero_id)
    cambios = {"n": 0}

    def escribir() -> None:
        for cid in sorted(set(anadir), key=str):
            if repo.insertar_asignacion_si_no_existe(sesion, tercero_id, cid, False):
                cambios["n"] += 1
        if principal_presente:
            cambios["n"] += repo.fijar_principal_asignacion(sesion, tercero_id, principal)
        if cambios["n"]:
            repo_ter.incrementar_version(sesion, tercero_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    if not cambios["n"]:
        return Resultado(dato=_vista_tercero(sesion, tercero_id), idempotente=True)
    auditar(sesion, tercero_id, operacion=OP_ASIGNAR, motivo=MOTIVOS[OP_ASIGNAR], antes=antes,
            despues=repo.snapshot_tercero_con_hijas(sesion, tercero_id), contenido=contenido, tabla=TABLA_TERCEROS)
    return Resultado(dato=_vista_tercero(sesion, tercero_id), modificadas=(tercero_id,))


# ------------------------------------------------------------------ C-TER-03 arbol de clasificaciones
def _nombre(nombre: Any) -> str | Rechazo:
    visible = nombre_visible(nombre) if isinstance(nombre, str) else ""
    return visible if 0 < len(visible) <= LONGITUD_CLASIFICACION else Rechazo(e.ENTRADA_INVALIDA)


def _hermano_repetido(sesion: SesionMotor, parent_id: uuid.UUID | None, nombre: str,
                      excluir: uuid.UUID | None = None) -> bool:
    return any(c["enabled"] and c["parent_id"] == parent_id and c["nombre"] == nombre and c["id"] != excluir
               for c in repo.clasificaciones(sesion))


def _es_descendiente(sesion: SesionMotor, candidato: uuid.UUID | None, de: uuid.UUID) -> bool:
    """True si `candidato` es `de` o cuelga de `de` (mover bajo un descendiente crearia un ciclo)."""
    padres = {c["id"]: c["parent_id"] for c in repo.clasificaciones(sesion)}
    visto: set[uuid.UUID] = set()
    while candidato is not None and candidato not in visto:
        if candidato == de:
            return True
        visto.add(candidato)
        candidato = padres.get(candidato)
    return False


def _vista_clasificacion(sesion: SesionMotor, clasificacion_id: uuid.UUID) -> dict[str, Any]:
    c = repo.clasificacion(sesion, clasificacion_id)
    assert c is not None
    return c


def crear_clasificacion(sesion: SesionMotor, *, clasificacion_id: uuid.UUID, nombre: str,
                        parent_id: uuid.UUID | None) -> Resultado | Rechazo:
    visible = _nombre(nombre)
    if isinstance(visible, Rechazo):
        return visible
    contenido = {"nombre": visible, "parent_id": m.texto(parent_id)}
    bloquear_intencion_propiedad(sesion, clasificacion_id)
    repo_ter.tomar_advisory(sesion)
    previo = replay(sesion, clasificacion_id, OP_CLAS_ALTA, clasificacion_id, contenido, tabla=TABLA_CLASIFICACIONES)
    if previo is True:
        return Resultado(dato=_vista_clasificacion(sesion, clasificacion_id), idempotente=True)
    if isinstance(previo, Rechazo):
        return previo
    if repo.clasificacion(sesion, clasificacion_id) is not None:
        return Rechazo(e.IDENTIDAD_REUTILIZADA)
    if parent_id is not None:
        padre = repo.clasificacion(sesion, parent_id, bloquear=True)
        if padre is None:
            return Rechazo(e.AGREGADO_NO_ENCONTRADO)
        if not padre["enabled"]:
            return Rechazo(e.ENTRADA_INVALIDA)
    if _hermano_repetido(sesion, parent_id, visible):
        return Rechazo(e.CLASIFICACION_NOMBRE_REPETIDO)
    rechazo = ejecutar_escritura(sesion, lambda: repo.insertar_clasificacion(
        sesion, clasificacion_id=clasificacion_id, parent_id=parent_id, nombre=visible), triggers=TRIGGER_ACICLICA)
    if rechazo is not None:
        return rechazo
    auditar(sesion, clasificacion_id, operacion=OP_CLAS_ALTA, motivo=MOTIVOS[OP_CLAS_ALTA], antes=None,
            despues=repo.snapshot_clasificacion(sesion, clasificacion_id), contenido=contenido, crear=True,
            tabla=TABLA_CLASIFICACIONES)
    return Resultado(dato=_vista_clasificacion(sesion, clasificacion_id), modificadas=(clasificacion_id,))


def _comando_arbol(sesion: SesionMotor, *, clasificacion_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                   operacion: str, contenido: dict[str, Any],
                   preparar: Callable[[dict[str, Any]], Rechazo | dict[str, Any]]) -> Resultado | Rechazo:
    """0P -> advisory -> clasificacion NK -> replay -> version -> `preparar` (validaciones y cambios) -> escritura."""
    bloquear_intencion_propiedad(sesion, intencion_id)
    repo_ter.tomar_advisory(sesion)
    actual = repo.clasificacion(sesion, clasificacion_id, bloquear=True)
    if actual is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    previo = replay(sesion, intencion_id, operacion, clasificacion_id, contenido, tabla=TABLA_CLASIFICACIONES)
    if previo is True:
        return Resultado(dato=_vista_clasificacion(sesion, clasificacion_id), idempotente=True)
    if isinstance(previo, Rechazo):
        return previo
    if actual["row_version"] != row_version:
        return Rechazo(e.VERSION_DESFASADA)
    cambios = preparar(actual)
    if isinstance(cambios, Rechazo):
        return cambios
    cambios = {k: v for k, v in cambios.items() if actual[k] != v}
    if not cambios:
        return Resultado(dato=actual)
    antes = repo.snapshot_clasificacion(sesion, clasificacion_id)
    rechazo = ejecutar_escritura(sesion, lambda: repo.actualizar_clasificacion(sesion, clasificacion_id, cambios),
                                 triggers=TRIGGER_ACICLICA)
    if rechazo is not None:
        return rechazo
    auditar(sesion, clasificacion_id, operacion=operacion, motivo=MOTIVOS[operacion], antes=antes,
            despues=repo.snapshot_clasificacion(sesion, clasificacion_id), contenido=contenido,
            tabla=TABLA_CLASIFICACIONES)
    return Resultado(dato=_vista_clasificacion(sesion, clasificacion_id), modificadas=(clasificacion_id,))


def renombrar_clasificacion(sesion: SesionMotor, *, clasificacion_id: uuid.UUID, intencion_id: uuid.UUID,
                            row_version: int, nombre: str) -> Resultado | Rechazo:
    visible = _nombre(nombre)
    if isinstance(visible, Rechazo):
        return visible

    def preparar(actual: dict[str, Any]) -> Rechazo | dict[str, Any]:
        if actual["enabled"] and _hermano_repetido(sesion, actual["parent_id"], visible, clasificacion_id):
            return Rechazo(e.CLASIFICACION_NOMBRE_REPETIDO)
        return {"nombre": visible}

    return _comando_arbol(sesion, clasificacion_id=clasificacion_id, intencion_id=intencion_id,
                          row_version=row_version, operacion=OP_CLAS_RENOMBRAR,
                          contenido={"row_version_esperada": row_version, "nombre": visible}, preparar=preparar)


def mover_clasificacion(sesion: SesionMotor, *, clasificacion_id: uuid.UUID, intencion_id: uuid.UUID,
                        row_version: int, parent_id: uuid.UUID | None) -> Resultado | Rechazo:
    def preparar(actual: dict[str, Any]) -> Rechazo | dict[str, Any]:
        if parent_id is not None:
            padre = repo.clasificacion(sesion, parent_id)
            if padre is None:
                return Rechazo(e.AGREGADO_NO_ENCONTRADO)
            if _es_descendiente(sesion, parent_id, clasificacion_id):
                return Rechazo(e.CLASIFICACION_CICLO)             # validacion previa con el mismo predicado del trigger
            if not padre["enabled"]:
                return Rechazo(e.ENTRADA_INVALIDA)
        if actual["enabled"] and _hermano_repetido(sesion, parent_id, actual["nombre"], clasificacion_id):
            return Rechazo(e.CLASIFICACION_NOMBRE_REPETIDO)
        return {"parent_id": parent_id}

    return _comando_arbol(sesion, clasificacion_id=clasificacion_id, intencion_id=intencion_id,
                          row_version=row_version, operacion=OP_CLAS_MOVER,
                          contenido={"row_version_esperada": row_version, "parent_id": m.texto(parent_id)},
                          preparar=preparar)


def desactivar_clasificacion(sesion: SesionMotor, *, clasificacion_id: uuid.UUID, intencion_id: uuid.UUID,
                             row_version: int) -> Resultado | Rechazo:
    """Afecta a TODOS los terceros que la tengan (no es una desasignacion individual): las asignaciones se conservan."""
    return _comando_arbol(sesion, clasificacion_id=clasificacion_id, intencion_id=intencion_id,
                          row_version=row_version, operacion=OP_CLAS_DESACTIVAR,
                          contenido={"row_version_esperada": row_version},
                          preparar=lambda actual: {"enabled": False})


def reactivar_clasificacion(sesion: SesionMotor, *, clasificacion_id: uuid.UUID, intencion_id: uuid.UUID,
                            row_version: int) -> Resultado | Rechazo:
    def preparar(actual: dict[str, Any]) -> Rechazo | dict[str, Any]:
        if _hermano_repetido(sesion, actual["parent_id"], actual["nombre"], clasificacion_id):
            return Rechazo(e.CLASIFICACION_NOMBRE_REPETIDO)
        return {"enabled": True}

    return _comando_arbol(sesion, clasificacion_id=clasificacion_id, intencion_id=intencion_id,
                          row_version=row_version, operacion=OP_CLAS_REACTIVAR,
                          contenido={"row_version_esperada": row_version}, preparar=preparar)
