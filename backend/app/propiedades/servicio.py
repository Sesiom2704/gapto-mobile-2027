# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/propiedades/servicio.py
# Descripcion: Writers de B1 (F06-01; contratos R1 v0.8 §1 y Parte I, v0.7
#   Parte I donde la v0.8 remite a ella, ajustes PR1-01 y PR1-04 del
#   dictamen de R1): C-PROP-01 alta con titularidad, C-PROP-02 editar datos,
#   C-PROP-03 cambio de titularidad desde una fecha y C-PROP-04 valoraciones
#   (alta). API DE INTEGRACION, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   Una transaccion de UnidadDeTrabajo por comando (retry completo ante
#   40P01/40001). Orden de locks (v0.8 §1.4; B1 empieza en el nivel 2, NUNCA
#   toma INVERSIONES ni advisory de raiz: no escribe hechos, efectos,
#   hecho_entidades, posiciones ni atribuciones):
#     alta:          terceros FOR SHARE por UUID (nivel 5) -> writer de actor
#                    (nivel 6) -> entidad nueva -> propiedades -> participaciones
#     resto:         entidad PROPIEDAD FOR NO KEY UPDATE (nivel 2) -> filas de
#                    titularidad FOR UPDATE -> terceros FOR SHARE
#                    -> writer de actor -> escritura -> row_version + 1
#   Actores y agregado en UN savepoint: un rechazo posterior a la creacion de
#   actores no deja actores huerfanos (v0.8 §1.5).
#
#   Identidad (v0.8 §1.3; F04-D050): `intencion_id` es el request_id de la
#   operacion (la ruta lo fija en el contexto). La auditoria de la raiz
#   (`entidades`) guarda, junto al snapshot del agregado, la clave
#   `intencion` = {operacion, contenido} con el contenido sellado CANONICO
#   (importes a 2 decimales, porcentajes a 4, fechas ISO, partes ordenadas
#   por actor). Reintento: misma operacion, mismo registro y contenido
#   IGUAL (igualdad exacta, nunca inclusion) -> respuesta con
#   idempotente=true; cualquier otra auditoria con ese request_id ->
#   IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION. El replay se reconoce ANTES de
#   la version (un reintento con la version ya superada es replay).
#   En el alta, un UUID que ya es otra entidad del owner, o de otro owner
#   (PK fisica), es IDENTIDAD_REUTILIZADA sin revelar nada.
#
#   PR1-04 en B1: C-PROP-03 compara bajo el lock de la entidad el conjunto
#   COMPLETO de partes vigentes hoy (actor y porcentaje exactos) con el que
#   vio el cliente (`titularidad_vista`); si difiere, VERSION_DESFASADA con
#   detalle TITULARIDAD_CAMBIADA y sin escribir. B1 no escribe atribuciones
#   ni infiere pagador. Porcentajes sin redondeo (mas de 4 decimales ->
#   ENTRADA_INVALIDA); el unico redondeo de B1 es el de la vista estructural
#   de lecturas.py (ROUND_HALF_UP a centimos).
# Version: 0.1.0 (F06-01 B1, lote 12)
# Version: 0.2.0 (F03 · N1 de 0352, mandato v1.4; AJ-0352-05; extension de C-PROP-02 autorizada
#   prospectivamente por F06-D006, expediente F06 0.5 §1.5): `editar` rechaza con
#   ADQUISICION_POSTERIOR_AL_CORTE_DECLARADO (422) una nueva fecha_adquisicion POSTERIOR al corte de una
#   declaracion de adquisicion (coste_adquisicion_declarado_completo = true), despues del replay y de
#   VERSION_DESFASADA y junto a ADQUISICION_POSTERIOR_A_TITULARIDAD, bajo el lock de la entidad y sin
#   escribir nada (row_version y auditoria intactas). Nada mas cambia en B1: ni otros contratos, ni el
#   orden de locks, ni la identidad de las intenciones, ni EDITABLES/COLUMNAS_PROPIEDAD (AJ-0352-08).
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import psycopg

from app.actores import repositorio as repo_act
from app.actores import servicio as serv_act
from app.categorias.normalizacion import nombre_visible
from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.core.unidad_trabajo import SesionMotor
from app.propiedades import lecturas
from app.propiedades import repositorio as repo
from app.repositories import auditoria_repository as auditoria

TABLA = "entidades"
LONGITUD_MAXIMA = 160
LONGITUD_CATASTRAL = 50
TIPOS = frozenset({"VIVIENDA", "LOCAL", "GARAJE", "TERRENO", "OTRO"})
MODOS = frozenset({"SOLO_MIA", "COMPARTIDA", "DE_OTROS", "DESCONOCIDA"})
METODOS_ALTA = frozenset({"MERCADO", "TASACION", "MANUAL", "FISCAL_REFERENCIA"})
METODO_COMPRA = "COMPRA"
NATURALEZAS_TITULARIDAD = frozenset({repo_act.NATURALEZA_PERSONA, repo_act.NATURALEZA_EMPRESA})
CIEN = Decimal("100")
CENTIMO = Decimal("0.01")
DIEZMILESIMA = Decimal("0.0001")

#: Campos editables de C-PROP-02 y los que admiten null explicito (borrar el dato).
EDITABLES = ("nombre",) + repo.COLUMNAS_PROPIEDAD
ANULABLES = frozenset(EDITABLES) - {"nombre", "tipo_propiedad", "incluir_en_rentabilidad"}

NO_ENCONTRADA = "AGREGADO_NO_ENCONTRADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
SUMA_NO_CUADRA = "SUMA_NO_CUADRA"
PARTICIPACION_NO_POSITIVA = "PARTICIPACION_NO_POSITIVA"
PARTICIPANTE_DUPLICADO = "PARTICIPANTE_DUPLICADO"
TERCERO_NO_DISPONIBLE = "TERCERO_NO_DISPONIBLE"
NATURALEZA_NO_ADMITIDA = "NATURALEZA_NO_ADMITIDA_EN_TITULARIDAD"
FECHA_ANTERIOR_INICIO = "FECHA_ANTERIOR_INICIO"
ADQUISICION_POSTERIOR = "ADQUISICION_POSTERIOR_A_TITULARIDAD"
ADQUISICION_POSTERIOR_AL_CORTE = "ADQUISICION_POSTERIOR_AL_CORTE_DECLARADO"   # 0352, AJ-0352-05
HABITACIONES_EN_USO = "HABITACIONES_EN_USO"
CAMBIO_RETROACTIVO = "CAMBIO_RETROACTIVO_SIN_POLITICA"
CAMBIO_PROGRAMADO = "CAMBIO_PROGRAMADO_EXISTENTE"
REPARTO_ANTERIOR = "REPARTO_ANTERIOR_AL_VIGENTE"
NO_PERMITIDA_EN_ESTADO = "OPERACION_NO_PERMITIDA_EN_ESTADO"
METODO_RESERVADO = "METODO_RESERVADO_A_LA_COMPRA"
ACTOR_SELF_AUSENTE = "ACTOR_DESCONOCIDO"
TITULARIDAD_CAMBIADA = "TITULARIDAD_CAMBIADA"

OP_ALTA = "PROPIEDAD_ALTA"
OP_EDITAR = "PROPIEDAD_EDITAR"
OP_TITULARIDAD = "PROPIEDAD_TITULARIDAD"
OP_VALORACION = "PROPIEDAD_VALORACION_ALTA"
MOTIVOS = {
    OP_ALTA: "F06-01 B1 PROPIEDAD ALTA",
    OP_EDITAR: "F06-01 B1 PROPIEDAD EDITAR",
    OP_TITULARIDAD: "F06-01 B1 PROPIEDAD CAMBIO DE TITULARIDAD",
    OP_VALORACION: "F06-01 B1 VALORACION ALTA",
}
MOTIVO_ACTOR = "F06-01 B1: alta del actor financiero de un cotitular"


@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    propiedad: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)
    avisos: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Parte:
    yo: bool
    tercero_id: uuid.UUID | None
    porcentaje: Decimal


# ------------------------------------------------------------------ canonicalizacion
def _texto(valor: Any, paso: Decimal | None = None) -> Any:
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return str(valor.quantize(paso or CENTIMO))
    if isinstance(valor, (dt.date, uuid.UUID)):
        return str(valor) if isinstance(valor, uuid.UUID) else valor.isoformat()
    return valor


def _partes_canonicas(partes: list[Parte] | None) -> list[dict[str, Any]] | None:
    if partes is None:
        return None
    return sorted(({"yo": p.yo, "tercero_id": _texto(p.tercero_id), "porcentaje": _texto(p.porcentaje, DIEZMILESIMA)}
                   for p in partes), key=lambda d: (not d["yo"], d["tercero_id"] or ""))


def _decimales(valor: Decimal) -> int:
    exponente = valor.as_tuple().exponent
    return -exponente if isinstance(exponente, int) and exponente < 0 else 0


# ------------------------------------------------------------------ validaciones puras
def validar_titularidad(modo: str, desde: dt.date | None, partes: list[Parte] | None, *,
                        alta: bool) -> Rechazo | None:
    """Forma -> porcentaje > 0 -> maximo 100 y 4 decimales -> duplicados -> suma (v0.8 Parte I)."""
    if modo not in MODOS:
        return Rechazo(ENTRADA_INVALIDA)
    if modo == "DESCONOCIDA":
        if not alta:
            return Rechazo(NO_PERMITIDA_EN_ESTADO)  # no se vuelve a DESCONOCIDA (v0.7 C-PROP-03)
        return None if desde is None and partes is None else Rechazo(ENTRADA_INVALIDA)
    if desde is None:
        return Rechazo(ENTRADA_INVALIDA)
    if modo == "SOLO_MIA":
        return None if partes is None else Rechazo(ENTRADA_INVALIDA)
    partes = partes or []
    if any(p.yo == (p.tercero_id is not None) for p in partes):
        return Rechazo(ENTRADA_INVALIDA)
    hay_yo = any(p.yo for p in partes)
    if modo == "COMPARTIDA" and (len(partes) < 2 or not hay_yo):
        return Rechazo(ENTRADA_INVALIDA)
    if modo == "DE_OTROS" and (len(partes) < 1 or hay_yo):
        return Rechazo(ENTRADA_INVALIDA)
    if any(p.porcentaje <= 0 for p in partes):
        return Rechazo(PARTICIPACION_NO_POSITIVA)
    if any(p.porcentaje > CIEN or _decimales(p.porcentaje) > 4 for p in partes):
        return Rechazo(ENTRADA_INVALIDA)
    claves = ["YO" if p.yo else str(p.tercero_id) for p in partes]
    if len(set(claves)) != len(claves):
        return Rechazo(PARTICIPANTE_DUPLICADO)
    if sum((p.porcentaje for p in partes), Decimal(0)) != CIEN:
        return Rechazo(SUMA_NO_CUADRA)
    return None


def _validar_datos(datos: dict[str, Any]) -> Rechazo | None:
    """Datos de `propiedades` (solo las claves presentes)."""
    if "tipo_propiedad" in datos and datos["tipo_propiedad"] not in TIPOS:
        return Rechazo(ENTRADA_INVALIDA)
    for c in ("superficie_m2", "superficie_construida_m2"):
        v = datos.get(c)
        if v is not None and (v <= 0 or _decimales(v) > 2 or v >= Decimal("100000000")):
            return Rechazo(ENTRADA_INVALIDA)
    for c in ("habitaciones", "banos"):
        v = datos.get(c)
        if v is not None and not 0 <= v <= 32767:
            return Rechazo(ENTRADA_INVALIDA)
    for c in ("referencia_catastral", "notas"):
        v = datos.get(c)
        if v is not None and not v.strip():
            return Rechazo(ENTRADA_INVALIDA)
    if datos.get("referencia_catastral") is not None and len(datos["referencia_catastral"]) > LONGITUD_CATASTRAL:
        return Rechazo(ENTRADA_INVALIDA)
    return None


def _nombre(nombre: Any) -> str | Rechazo:
    visible = nombre_visible(nombre) if isinstance(nombre, str) else ""
    return visible if 0 < len(visible) <= LONGITUD_MAXIMA else Rechazo(ENTRADA_INVALIDA)


# ------------------------------------------------------------------ piezas comunes
def _replay(sesion: SesionMotor, intencion_id: uuid.UUID, operacion: str, registro_id: uuid.UUID,
            contenido: dict[str, Any]) -> bool | Rechazo:
    """True = reintento identico; False = intencion nueva; Rechazo = reutilizada con otra intencion."""
    auditadas = repo.auditorias_de_intencion(sesion, intencion_id)
    if not auditadas:
        return False
    raiz = [a for a in auditadas if a["tabla"] == TABLA]
    resto_valido = all(a["tabla"] == repo_act.TABLA and a["motivo"] == MOTIVO_ACTOR
                       for a in auditadas if a["tabla"] != TABLA)
    if len(raiz) == 1 and resto_valido and raiz[0]["registro_id"] == registro_id:
        sellada = (json.loads(raiz[0]["despues"]) or {}).get("intencion")
        if sellada == {"operacion": operacion, "contenido": contenido}:
            return True
    return Rechazo(IDENTIDAD_REUTILIZADA)


def _auditar(sesion: SesionMotor, entidad_id: uuid.UUID, operacion: str, antes: str | None,
             contenido: dict[str, Any], motivo_usuario: str | None = None) -> None:
    despues = json.loads(repo.snapshot(sesion, entidad_id))
    despues["intencion"] = {"operacion": operacion, "contenido": contenido}
    motivo = MOTIVOS[operacion] + (f": {motivo_usuario}" if motivo_usuario else "")
    auditoria.registrar(
        sesion, tabla=TABLA, registro_id=entidad_id,
        accion=auditoria.ACCION_CREAR if operacion == OP_ALTA else auditoria.ACCION_ACTUALIZAR,
        datos_antes_json=antes, datos_despues_json=json.dumps(despues, ensure_ascii=False), motivo=motivo,
    )


def _validar_terceros(sesion: SesionMotor, partes: list[Parte] | None) -> Rechazo | None:
    """Nivel 5: TODOS los terceros FOR SHARE por UUID; primero disponibilidad, despues naturaleza."""
    terceros = sorted({p.tercero_id for p in (partes or []) if p.tercero_id is not None}, key=str)
    leidos = [(tid, repo_act.leer_tercero_compartido(sesion, tid)) for tid in terceros]
    for tid, t in leidos:
        if t is None or not t["enabled"]:
            return Rechazo(TERCERO_NO_DISPONIBLE, {"tercero_id": str(tid)})
    for tid, t in leidos:
        if t["naturaleza"] not in NATURALEZAS_TITULARIDAD:
            return Rechazo(NATURALEZA_NO_ADMITIDA, {"tercero_id": str(tid)})
    return None


def _filas(modo: str, desde: dt.date, partes: list[Parte] | None, self_id: uuid.UUID,
           actores: dict[uuid.UUID, uuid.UUID]) -> list[tuple[uuid.UUID, Decimal]]:
    if modo == "DESCONOCIDA":
        return []
    if modo == "SOLO_MIA":
        return [(self_id, CIEN)]
    return sorted(((self_id if p.yo else actores[p.tercero_id]), p.porcentaje) for p in partes or [])


def _escribir_titularidad(sesion: SesionMotor, *, intencion_id: uuid.UUID, entidad_id: uuid.UUID, modo: str,
                          desde: dt.date | None, partes: list[Parte] | None, self_id: uuid.UUID) -> None:
    """Actores (writer vigente con la politica de la titularidad, ya validada) y filas nuevas."""
    terceros = sorted({p.tercero_id for p in (partes or []) if p.tercero_id is not None}, key=str)
    actores = {tid: serv_act.actor_de_tercero(sesion, tid, MOTIVO_ACTOR) for tid in terceros}
    for actor_id, porcentaje in _filas(modo, desde, partes, self_id, actores):
        repo.insertar_participacion(sesion, fila_id=uuid.uuid5(intencion_id, f"titularidad:{actor_id}"),
                                    entidad_id=entidad_id, actor_id=actor_id, porcentaje=porcentaje, desde=desde)


def _vista(sesion: SesionMotor, entidad_id: uuid.UUID, hoy: dt.date) -> dict[str, Any]:
    vista = lecturas.detalle(sesion, entidad_id, hoy)
    assert vista is not None
    return vista


# ------------------------------------------------------------------ C-PROP-01 alta
def alta(sesion: SesionMotor, *, entidad_id: uuid.UUID, nombre: str, datos: dict[str, Any], modo: str,
         desde: dt.date | None, partes: list[Parte] | None, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    visible = _nombre(nombre)
    if isinstance(visible, Rechazo):
        return visible
    datos = {c: datos.get(c) for c in repo.COLUMNAS_PROPIEDAD if c != "incluir_en_rentabilidad"}
    rechazo = _validar_datos(datos) or validar_titularidad(modo, desde, partes, alta=True)
    if rechazo is not None:
        return rechazo
    contenido = {"nombre": visible, **{c: _texto(v) for c, v in datos.items()},
                 "titularidad": {"modo": modo, "desde": _texto(desde), "partes": _partes_canonicas(partes)}}
    hoy = hoy_owner(sesion, reloj)
    replay = _replay(sesion, entidad_id, OP_ALTA, entidad_id, contenido)
    if replay is True:
        return Resultado(propiedad=_vista(sesion, entidad_id, hoy), idempotente=True)
    if isinstance(replay, Rechazo):
        return replay
    if repo.existe_entidad(sesion, entidad_id):
        return Rechazo(IDENTIDAD_REUTILIZADA)
    self_id = repo.actor_self(sesion)
    if self_id is None:
        return Rechazo(ACTOR_SELF_AUSENTE)
    rechazo = _validar_terceros(sesion, partes)
    if rechazo is not None:
        return rechazo
    if desde is not None and datos["fecha_adquisicion"] is not None and desde < datos["fecha_adquisicion"]:
        return Rechazo(FECHA_ANTERIOR_INICIO)
    conexion = sesion.conexion
    try:
        # UN savepoint para actores y agregado: ningun rechazo posterior deja actores huerfanos.
        with conexion.transaction():
            repo.insertar_propiedad(sesion, entidad_id=entidad_id, nombre=visible,
                                    datos={**datos, "incluir_en_rentabilidad": True})
            _escribir_titularidad(sesion, intencion_id=entidad_id, entidad_id=entidad_id, modo=modo, desde=desde,
                                  partes=partes, self_id=self_id)
            conexion.execute(f"SET CONSTRAINTS {repo.TRIGGERS_SUBTIPO} IMMEDIATE")
    except serv_act.RechazoActor as exc:
        return Rechazo(exc.codigo, {"tercero_id": str(exc.tercero_id)})
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name not in ("pk_entidades", "pk_propiedades", "pk_entidad_participaciones"):
            raise
        # Otra transaccion con la misma intencion confirmo antes (o el UUID es de otro owner).
        replay = _replay(sesion, entidad_id, OP_ALTA, entidad_id, contenido)
        if replay is True:
            return Resultado(propiedad=_vista(sesion, entidad_id, hoy), idempotente=True)
        return Rechazo(IDENTIDAD_REUTILIZADA)
    finally:
        conexion.execute(f"SET CONSTRAINTS {repo.TRIGGERS_SUBTIPO} DEFERRED")
    _auditar(sesion, entidad_id, OP_ALTA, None, contenido)
    return Resultado(propiedad=_vista(sesion, entidad_id, hoy), modificadas=(entidad_id,))


# ------------------------------------------------------------------ C-PROP-02 editar
def editar(sesion: SesionMotor, *, entidad_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
           campos: dict[str, Any], motivo: str | None = None, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """`campos` solo trae los campos PRESENTES en la peticion (omitido = no cambia; None = borrar)."""
    if not campos or set(campos) - set(EDITABLES):
        return Rechazo(ENTRADA_INVALIDA)
    if any(campos[c] is None for c in campos if c not in ANULABLES):
        return Rechazo(ENTRADA_INVALIDA)
    nuevos = dict(campos)
    if "nombre" in nuevos:
        visible = _nombre(nuevos["nombre"])
        if isinstance(visible, Rechazo):
            return visible
        nuevos["nombre"] = visible
    rechazo = _validar_datos(nuevos)
    if rechazo is not None:
        return rechazo
    contenido = {"row_version_esperada": row_version, "motivo": motivo,
                 "campos": {c: _texto(v) for c, v in sorted(nuevos.items())}}
    hoy = hoy_owner(sesion, reloj)
    raiz = repo.bloquear(sesion, entidad_id)
    if raiz is None:
        return Rechazo(NO_ENCONTRADA)
    replay = _replay(sesion, intencion_id, OP_EDITAR, entidad_id, contenido)
    if replay is True:
        return Resultado(propiedad=_vista(sesion, entidad_id, hoy), idempotente=True)
    if isinstance(replay, Rechazo):
        return replay
    if raiz["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    actual = repo.leer(sesion, entidad_id)
    cambios = {c: v for c, v in nuevos.items() if actual[c] != v}
    if "fecha_adquisicion" in cambios and cambios["fecha_adquisicion"] is not None:
        inicio = min((f["vigente_desde"] for f in repo.participaciones(sesion, entidad_id)), default=None)
        if inicio is not None and cambios["fecha_adquisicion"] > inicio:
            return Rechazo(ADQUISICION_POSTERIOR)
        # 0352 (AJ-0352-05): con la adquisicion declarada completa, la fecha no puede pasar del corte declarado.
        corte = repo.corte_adquisicion_declarado(sesion, entidad_id)
        if corte is not None and cambios["fecha_adquisicion"] > corte:
            return Rechazo(ADQUISICION_POSTERIOR_AL_CORTE)
    if "habitaciones" in cambios:
        maxima, contratos = repo.max_habitacion_en_uso(sesion, entidad_id)
        if maxima is not None and (cambios["habitaciones"] is None or cambios["habitaciones"] < maxima):
            return Rechazo(HABITACIONES_EN_USO, {"contratos": [str(c) for c in contratos]})
    if not cambios:
        return Resultado(propiedad=_vista(sesion, entidad_id, hoy))
    antes = repo.snapshot(sesion, entidad_id)
    repo.actualizar_propiedad(sesion, entidad_id, cambios)
    repo.subir_version(sesion, entidad_id)
    _auditar(sesion, entidad_id, OP_EDITAR, antes, contenido, motivo)
    return Resultado(propiedad=_vista(sesion, entidad_id, hoy), modificadas=(entidad_id,))


# ------------------------------------------------------------------ C-PROP-03 cambio de titularidad
def cambiar_titularidad(sesion: SesionMotor, *, entidad_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                        modo: str, desde: dt.date, partes: list[Parte] | None,
                        vista_cliente: list[tuple[uuid.UUID, Decimal]], motivo: str | None = None,
                        reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    rechazo = validar_titularidad(modo, desde, partes, alta=False)
    if rechazo is not None:
        return rechazo
    contenido = {"row_version_esperada": row_version, "motivo": motivo, "modo": modo, "desde": _texto(desde),
                 "partes": _partes_canonicas(partes),
                 "titularidad_vista": sorted([str(a), _texto(p, DIEZMILESIMA)] for a, p in vista_cliente)}
    hoy = hoy_owner(sesion, reloj)
    raiz = repo.bloquear(sesion, entidad_id)
    if raiz is None:
        return Rechazo(NO_ENCONTRADA)
    filas = repo.participaciones(sesion, entidad_id, bloquear_filas=True)
    replay = _replay(sesion, intencion_id, OP_TITULARIDAD, entidad_id, contenido)
    if replay is True:
        return Resultado(propiedad=_vista(sesion, entidad_id, hoy), idempotente=True)
    if isinstance(replay, Rechazo):
        return replay
    if raiz["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    vigentes_hoy = sorted((f["actor_id"], f["porcentaje"]) for f in filas if f["vigente_desde"] <= hoy
                          and (f["vigente_hasta"] is None or f["vigente_hasta"] >= hoy))
    if vigentes_hoy != sorted(vista_cliente):
        return Rechazo(VERSION_DESFASADA, {"motivo": TITULARIDAD_CAMBIADA})
    if desde < hoy:
        return Rechazo(CAMBIO_RETROACTIVO)
    if raiz["fecha_adquisicion"] is not None and desde < raiz["fecha_adquisicion"]:
        return Rechazo(FECHA_ANTERIOR_INICIO)
    if any(f["vigente_desde"] > hoy for f in filas):
        return Rechazo(CAMBIO_PROGRAMADO)
    abiertas = [f for f in filas if f["vigente_hasta"] is None]
    if any(f["vigente_desde"] >= desde for f in abiertas):
        return Rechazo(REPARTO_ANTERIOR)
    self_id = repo.actor_self(sesion)
    if self_id is None:
        return Rechazo(ACTOR_SELF_AUSENTE)
    rechazo = _validar_terceros(sesion, partes)
    if rechazo is not None:
        return rechazo
    antes = repo.snapshot(sesion, entidad_id)
    try:
        with sesion.conexion.transaction():
            for f in abiertas:
                repo.cerrar_participacion(sesion, f["id"], desde - dt.timedelta(days=1))
            _escribir_titularidad(sesion, intencion_id=intencion_id, entidad_id=entidad_id, modo=modo, desde=desde,
                                  partes=partes, self_id=self_id)
    except serv_act.RechazoActor as exc:
        return Rechazo(exc.codigo, {"tercero_id": str(exc.tercero_id)})
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name != "pk_entidad_participaciones":
            raise
        return Rechazo(IDENTIDAD_REUTILIZADA)  # filas derivadas de una intencion de otro owner
    repo.subir_version(sesion, entidad_id)
    _auditar(sesion, entidad_id, OP_TITULARIDAD, antes, contenido, motivo)
    return Resultado(propiedad=_vista(sesion, entidad_id, hoy), modificadas=(entidad_id,))


# ------------------------------------------------------------------ C-PROP-04 valoraciones
def _validar_valoracion(valores: dict[str, Any]) -> Rechazo | None:
    if valores.get("metodo") == METODO_COMPRA:
        return Rechazo(METODO_RESERVADO)
    if "metodo" in valores and valores["metodo"] not in METODOS_ALTA:
        return Rechazo(ENTRADA_INVALIDA)
    v = valores.get("valor_total")
    if "valor_total" in valores and (v is None or v <= 0 or _decimales(v) > 2 or v >= Decimal("100000000000000")):
        return Rechazo(ENTRADA_INVALIDA)
    if "fecha_valoracion" in valores and valores["fecha_valoracion"] is None:
        return Rechazo(ENTRADA_INVALIDA)
    for c in ("fuente", "notas"):
        if valores.get(c) is not None and not valores[c].strip():
            return Rechazo(ENTRADA_INVALIDA)
    if valores.get("fuente") is not None and len(valores["fuente"]) > LONGITUD_MAXIMA:
        return Rechazo(ENTRADA_INVALIDA)
    return None


def alta_valoracion(sesion: SesionMotor, *, propiedad_id: uuid.UUID, valoracion_id: uuid.UUID, row_version: int,
                    valor_total: Decimal, fecha: dt.date, metodo: str, fuente: str | None, notas: str | None,
                    reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    valores = {"valor_total": valor_total, "fecha_valoracion": fecha, "metodo": metodo, "fuente": fuente,
               "notas": notas}
    rechazo = _validar_valoracion(valores)
    if rechazo is not None:
        return rechazo
    contenido = {"row_version_esperada": row_version, "valoracion_id": str(valoracion_id),
                 **{c: _texto(v) for c, v in valores.items()}}
    hoy = hoy_owner(sesion, reloj)
    raiz = repo.bloquear(sesion, propiedad_id)
    if raiz is None:
        return Rechazo(NO_ENCONTRADA)
    replay = _replay(sesion, valoracion_id, OP_VALORACION, propiedad_id, contenido)
    if replay is True:
        return Resultado(propiedad=_vista(sesion, propiedad_id, hoy), idempotente=True)
    if isinstance(replay, Rechazo) or repo.leer_valoracion(sesion, valoracion_id) is not None:
        return Rechazo(IDENTIDAD_REUTILIZADA)
    if raiz["row_version"] != row_version:
        return Rechazo(VERSION_DESFASADA)
    antes = repo.snapshot(sesion, propiedad_id)
    try:
        with sesion.conexion.transaction():
            repo.insertar_valoracion(sesion, valoracion_id=valoracion_id, propiedad_id=propiedad_id,
                                     valor_total=valor_total, fecha=fecha, metodo=metodo, fuente=fuente, notas=notas)
    except psycopg.errors.UniqueViolation as exc:
        if exc.diag.constraint_name != "pk_propiedad_valoraciones":
            raise
        return Rechazo(IDENTIDAD_REUTILIZADA)  # id de otro owner: invisible por RLS, sin revelarlo
    repo.subir_version(sesion, propiedad_id)
    _auditar(sesion, propiedad_id, OP_VALORACION, antes, contenido)
    return Resultado(propiedad=_vista(sesion, propiedad_id, hoy), modificadas=(propiedad_id,))

