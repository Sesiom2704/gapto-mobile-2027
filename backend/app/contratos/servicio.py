# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicio.py
# Ruta: backend/app/contratos/servicio.py
# Descripcion: Writers de contratos de alquiler y de la clausula de revision SIN RENTA (F06-02/03; contrato
#   operativo v1.1 Parte I y II, D25, decisiones 1-7 de Moises del 2026-11-18). API DE INTEGRACION, PENDIENTE
#   DE CONSOLIDACION F10.
#     C-CON-01 alta (contrato, personas, clausula y servicios en UNA operacion)
#     C-CON-02 editar y prorrogar        C-CON-03 terminar y corregir la terminacion
#     C-CON-04 formalizar o cancelar     C-CON-05 sucesor en una habitacion
#     C-CON-06 personas por vigencias    C-REV-01 clausula (nueva version y errata)
#   Orden de recursos (§1.3, alineado con el orden CERTIFICADO; prohibido invertirlo):
#     0P de intencion -> propiedad FOR NO KEY UPDATE (sin subir su row_version) -> advisory de terceros de F05
#     (solo si se CREA un tercero) -> terceros FOR SHARE por UUID -> contratos FOR NO KEY UPDATE por UUID ->
#     servicios FOR SHARE por UUID -> filas hijas.
#   Todo el estado se relee BAJO el lock de la propiedad. Garantias NUEVAS de concurrencia en servicio (STOP D
#   autorizado por el mandato): solape entre FORMALIZADOS de una propiedad (INV-ALQ-08), arrendador/inquilino
#   siempre presentes (INV-ALQ-07) y D25. Un borrador no ocupa ni cuenta para el solape.
#   NO ESCRIBE renta, `regla_renta_id`, reglas, previsiones ni OP-21; un contrato con `regla_renta_id` (dato V3)
#   no se termina ni cambia de inicio (409, motivo RENTA_PENDIENTE_DE_F06_04).
#   Identidad: `intencion_id` = request_id (auditoria de la raiz con la intencion sellada); en el alta
#   `intencion_id` = entidades.id del contrato.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 3)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.categorias.normalizacion import nombre_visible
from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.contratos import errores as e
from app.contratos import lecturas
from app.contratos import modelos as m
from app.contratos import repositorio as repo
from app.contratos.base import (Abortar, actor_de, auditar, bloquear_intencion_propiedad, bloquear_terceros,
                                crear_tercero, ejecutar_escritura, replay, TRIGGERS_SUBTIPO_CONTRATO)
from app.contratos.modelos import Clausula, NuevoTercero, Persona, Rechazo, Resultado, Tratamiento
from app.core.unidad_trabajo import SesionMotor
from app.propiedades import repositorio as repo_prop

OP_ALTA, OP_EDITAR, OP_TERMINAR, OP_CORREGIR_TERMINACION = "CONTRATO_ALTA", "CONTRATO_EDITAR", "CONTRATO_TERMINAR", \
    "CONTRATO_CORREGIR_TERMINACION"
OP_FORMALIZAR, OP_CANCELAR, OP_SUCESOR, OP_SUCESOR_NUEVO = "CONTRATO_FORMALIZAR", "CONTRATO_CANCELAR", \
    "CONTRATO_SUCESOR", "CONTRATO_SUCESOR_NUEVO"
OP_PERSONA_ANADIR, OP_PERSONA_CERRAR, OP_PERSONA_CORREGIR = "CONTRATO_PERSONA_ANADIR", "CONTRATO_PERSONA_CERRAR", \
    "CONTRATO_PERSONA_CORREGIR"
OP_CLAUSULA, OP_CLAUSULA_CORREGIR = "CONTRATO_CLAUSULA", "CONTRATO_CLAUSULA_CORREGIR"
MOTIVOS = {
    OP_ALTA: "F06-02/03 CONTRATO ALTA", OP_EDITAR: "F06-02/03 CONTRATO EDITAR",
    OP_TERMINAR: "F06-02/03 CONTRATO TERMINAR", OP_CORREGIR_TERMINACION: "F06-02/03 CONTRATO CORREGIR TERMINACION",
    OP_FORMALIZAR: "F06-02/03 CONTRATO FORMALIZAR", OP_CANCELAR: "F06-02/03 CONTRATO CANCELAR",
    OP_SUCESOR: "F06-02/03 CONTRATO SUCESOR (TERMINA EL ANTERIOR)", OP_SUCESOR_NUEVO: "F06-02/03 CONTRATO SUCESOR (NUEVO)",
    OP_PERSONA_ANADIR: "F06-02/03 CONTRATO PERSONA ANADIR", OP_PERSONA_CERRAR: "F06-02/03 CONTRATO PERSONA CERRAR",
    OP_PERSONA_CORREGIR: "F06-02/03 CONTRATO PERSONA CORREGIR", OP_CLAUSULA: "F06-02/03 CONTRATO CLAUSULA",
    OP_CLAUSULA_CORREGIR: "F06-02/03 CONTRATO CLAUSULA CORREGIR",
}
TABLAS_VIGENCIA = ("contrato_participantes", "contrato_servicios", "contrato_revision_renta_versiones")


# ------------------------------------------------------------------ datos de entrada
@dataclass(frozen=True)
class DatosContrato:
    """Lo que describe un contrato nuevo (alta y `nuevo` del sucesor)."""
    nombre: str
    tipo: str                      # nombre de producto: VIVIENDA_COMPLETA, HABITACION u OTRO
    habitacion: int | None
    fecha_inicio: dt.date | None
    fecha_fin_prevista: dt.date | None
    estado: str
    personas: list[Persona] | None = None
    clausula: Clausula | None = None
    servicios: list[Tratamiento] | None = None
    notas: str | None = None
    renta_presente: bool = False    # el bloque `renta` o `fianza` venia en la peticion (R-E-01)


@dataclass
class Abierto:
    c: dict[str, Any]
    hoy: dt.date
    terceros: dict[uuid.UUID, dict[str, Any] | None] = field(default_factory=dict)


# ------------------------------------------------------------------ canonicalizacion
def _contenido_nuevo(d: DatosContrato) -> dict[str, Any]:
    return {"nombre": d.nombre, "tipo": d.tipo, "habitacion": d.habitacion, "fecha_inicio": m.texto(d.fecha_inicio),
            "fecha_fin_prevista": m.texto(d.fecha_fin_prevista), "estado": d.estado,
            "personas": m.personas_canonicas(d.personas), "clausula": m.clausula_canonica(d.clausula),
            "servicios": m.tratamientos_canonicos(d.servicios), "notas": d.notas, "renta": d.renta_presente}


def _nombre(nombre: Any) -> str | Rechazo:
    visible = nombre_visible(nombre) if isinstance(nombre, str) else ""
    return visible if 0 < len(visible) <= m.LONGITUD_NOMBRE else Rechazo(e.ENTRADA_INVALIDA)


def exigir_motivo(motivo: str | None) -> str | Rechazo:
    limpio = (motivo or "").strip()
    return limpio if limpio else Rechazo(e.MOTIVO_AUSENTE)


def vista(sesion: SesionMotor, contrato_id: uuid.UUID, hoy: dt.date) -> dict[str, Any]:
    vista = lecturas.detalle_contrato(sesion, contrato_id, hoy)
    assert vista is not None
    return vista


def resultado(sesion: SesionMotor, contrato_id: uuid.UUID, hoy: dt.date, *, idempotente: bool = False,
               modificadas: tuple[uuid.UUID, ...] = (), extra: dict[str, Any] | None = None) -> Resultado:
    return Resultado(dato=vista(sesion, contrato_id, hoy), idempotente=idempotente, modificadas=modificadas,
                     extra=extra or {})


def _detalle_solape(c: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(c["id"]), "nombre": c["nombre"], "tipo": lecturas.TIPO_PRODUCTO.get(c["tipo_contrato"]),
            "habitacion": c["habitacion"], "desde": c["fecha_inicio"].isoformat(),
            "hasta": None if c["fecha_fin_real"] is None else c["fecha_fin_real"].isoformat()}


def _fin_previsto_anterior_al_inicio(inicio: dt.date | None, fin_prevista: dt.date | None) -> bool:
    """Coherencia de fechas (paso 4 de §I); ultima barrera: ck_contratos__fin_prevista_no_anterior."""
    return inicio is not None and fin_prevista is not None and fin_prevista < inicio


# ------------------------------------------------------------------ validaciones con base (bajo los locks)
def _validar_habitacion(ficha: dict[str, Any], tipo_fisico: str, habitacion: int | None) -> Rechazo | None:
    """Paso 3 de §I: la etiqueta se valida contra la ficha EN EL MOMENTO de la escritura, bajo el lock."""
    if tipo_fisico == m.TIPO_HABITACION and habitacion is None:
        return Rechazo(e.HABITACION_REQUERIDA)
    if tipo_fisico != m.TIPO_HABITACION and habitacion is not None:
        return Rechazo(e.HABITACION_NO_ADMITIDA)
    if tipo_fisico == m.TIPO_HABITACION:
        if habitacion < 1:
            return Rechazo(e.HABITACION_NO_ADMITIDA)
        if not ficha["habitaciones"]:               # NULL o 0: la columna admite 0 y no se inventan (D-A-11)
            return Rechazo(e.HABITACIONES_NO_INDICADAS)
        if habitacion > ficha["habitaciones"]:
            return Rechazo(e.HABITACION_FUERA_DE_FICHA)
    return None


def solapes(sesion: SesionMotor, propiedad_id: uuid.UUID, *, tipo_fisico: str, habitacion: int | None,
            inicio: dt.date, fin_real: dt.date | None, excluir: frozenset[uuid.UUID] = frozenset(),
            fin_de: dict[uuid.UUID, dt.date | None] | None = None) -> list[dict[str, Any]]:
    """Contratos FORMALIZADOS de la propiedad que coinciden con la ocupacion `[inicio, fin_real ?? inf]` (inclusiva;
    el fin PREVISTO no libera: decision 6). HABITACION n: misma habitacion Y vivienda completa; VIVIENDA_COMPLETA:
    todos (habitaciones y viviendas); OTRO: nada. Los borradores y cancelados no cuentan. Se llama bajo el lock de
    la propiedad."""
    if tipo_fisico == m.TIPO_OTRO:
        return []
    salida = []
    for c in repo.contratos_de_propiedad(sesion, propiedad_id):
        if c["id"] in excluir or c["estado_documental"] != "FORMALIZADO" or c["tipo_contrato"] == m.TIPO_OTRO:
            continue
        if tipo_fisico == m.TIPO_HABITACION and not (
                c["tipo_contrato"] == m.TIPO_VIVIENDA
                or (c["tipo_contrato"] == m.TIPO_HABITACION and c["habitacion"] == habitacion)):
            continue
        fin_c = (fin_de or {}).get(c["id"], c["fecha_fin_real"])
        if m.intervalo_solapa(inicio, fin_real, c["fecha_inicio"], fin_c):
            salida.append(c)
    return salida


def _rechazo_solape(contratos: list[dict[str, Any]]) -> Rechazo:
    return Rechazo(e.SOLAPE_CON_CONTRATO_FIRMADO, {"solapados": [_detalle_solape(c) for c in contratos]})


def _validar_servicios_nuevos(sesion: SesionMotor, propiedad_id: uuid.UUID, servicios: list[Tratamiento],
                              inquilinos: set[uuid.UUID], desde: dt.date) -> Rechazo | None:
    """C-SRV-04 en el alta: servicios FOR SHARE por UUID (nivel 7); baja -> vinculo -> actor INQUILINO ->
    coherencia del modo."""
    ids = [t.servicio_id for t in servicios]
    if len(set(ids)) != len(ids):
        return Rechazo(e.ENTRADA_INVALIDA)                     # una entrada por servicio
    por_id = {t.servicio_id: t for t in servicios}
    for sid in sorted(por_id, key=str):
        s = repo.servicio(sesion, sid, bloqueo="SHARE")
        if s is None:
            return Rechazo(e.AGREGADO_NO_ENCONTRADO)
        if s["fecha_fin_real"] is not None and s["fecha_fin_real"] < desde:
            return Rechazo(e.SERVICIO_DADO_DE_BAJA)
        if not repo.servicio_vinculado_en(sesion, sid, propiedad_id, desde):
            return Rechazo(e.SERVICIO_NO_VINCULADO_A_PROPIEDAD)
        t = por_id[sid]
        if t.modo in ("REPERCUTIDO_FIJO", "POR_FACTURA") and t.inquilino_tercero_id not in inquilinos:
            return Rechazo(e.ACTOR_NO_ES_INQUILINO)
        invalido = m.columnas_tratamiento(t.modo, uuid.uuid4() if t.inquilino_tercero_id else None, t.porcentaje)
        if isinstance(invalido, Rechazo):
            return invalido
    return None


# ------------------------------------------------------------------ nuevo contrato (alta y sucesor)
def _ids_terceros(personas: list[Persona] | None) -> tuple[list[uuid.UUID], list[NuevoTercero]]:
    existentes = [p.tercero_id for p in personas or [] if p.tercero_id is not None]
    nuevos = [p.nuevo for p in personas or [] if p.nuevo is not None]
    return existentes, nuevos


def _validar_nuevo(sesion: SesionMotor, ficha: dict[str, Any], propiedad_id: uuid.UUID, tipo_fisico: str,
                   habitacion: int | None, d: DatosContrato, terceros: dict[uuid.UUID, dict[str, Any] | None],
                   *, excluir: frozenset[uuid.UUID] = frozenset(),
                   fin_de: dict[uuid.UUID, dt.date | None] | None = None) -> Rechazo | None:
    """Pasos 1 a 7 de C-CON-01, en su orden. Todo bajo el lock de la propiedad; nada se escribe aqui."""
    salida = ficha["fecha_salida_patrimonio"]
    if salida is not None and d.fecha_inicio is not None and salida < d.fecha_inicio:      # 1
        return Rechazo(e.PROPIEDAD_FUERA_DE_PATRIMONIO)
    if d.renta_presente:                                                                    # 2 (R-E-01)
        return Rechazo(e.RENTA_NO_DISPONIBLE)
    if d.fecha_inicio is None:                                                              # Q-CON-09
        return Rechazo(e.FECHA_INICIO_REQUERIDA)
    rechazo = _validar_habitacion(ficha, tipo_fisico, habitacion)                           # 3
    if rechazo is not None:
        return rechazo
    if _fin_previsto_anterior_al_inicio(d.fecha_inicio, d.fecha_fin_prevista):               # 4
        return Rechazo(e.FECHA_ANTERIOR_INICIO)
    formalizado = d.estado == "FORMALIZADO"
    personas = d.personas or []
    rechazo = m.validar_personas_alta(personas, formalizado=formalizado)                    # 5
    if rechazo is not None:
        return rechazo
    for p in personas:
        tid = p.tercero_id
        if tid is not None and (terceros.get(tid) is None or not terceros[tid]["enabled"]):
            return Rechazo(e.TERCERO_NO_DISPONIBLE, {"tercero_id": str(tid)})
        if p.nuevo is not None and terceros.get(p.nuevo.id) is not None:
            return Rechazo(e.IDENTIDAD_REUTILIZADA)
    if any(p.nuevo is not None and not isinstance(_nombre(p.nuevo.nombre), str) for p in personas):
        return Rechazo(e.ENTRADA_INVALIDA)
    rechazo = m.validar_yo(personas)
    if rechazo is not None:
        return rechazo
    if any(p.yo for p in personas) and repo_prop.actor_self(sesion) is None:
        return Rechazo(e.ACTOR_DESCONOCIDO)
    rechazo = m.validar_principales(personas, formalizado=formalizado)
    if rechazo is not None:
        return rechazo
    if formalizado:                                                                         # 6
        coinciden = solapes(sesion, propiedad_id, tipo_fisico=tipo_fisico, habitacion=habitacion,
                            inicio=d.fecha_inicio, fin_real=None, excluir=excluir, fin_de=fin_de)
        if coinciden:
            return _rechazo_solape(coinciden)
    if d.clausula is not None:                                                              # 7
        columnas = m.validar_clausula(d.clausula)
        if isinstance(columnas, Rechazo):
            return columnas
    if d.servicios:
        inquilinos = {p.nuevo.id if p.nuevo is not None else p.tercero_id for p in personas if p.rol == "INQUILINO"}
        return _validar_servicios_nuevos(sesion, propiedad_id, d.servicios, inquilinos, d.fecha_inicio)
    return None


def _escribir_nuevo(sesion: SesionMotor, contrato_id: uuid.UUID, propiedad_id: uuid.UUID, tipo_fisico: str,
                    habitacion: int | None, d: DatosContrato, nombre: str) -> None:
    """Escrituras del nuevo contrato (dentro del savepoint de la operacion): terceros nuevos con el writer de F05,
    actores, entidad+contrato, personas, clausula y tratamientos. `regla_renta_id` queda NULL."""
    _, nuevos = _ids_terceros(d.personas)
    for nt in sorted(nuevos, key=lambda n: str(n.id)):
        crear_tercero(sesion, nt)
    actores: dict[str, uuid.UUID] = {}
    for p in sorted(d.personas or [], key=lambda x: (x.rol, x.clave_actor)):
        if p.clave_actor not in actores:
            if p.yo:
                actor = repo_prop.actor_self(sesion)
                if actor is None:
                    raise Abortar(Rechazo(e.ACTOR_DESCONOCIDO))
                actores[p.clave_actor] = actor
            else:
                actores[p.clave_actor] = actor_de(sesion, p.nuevo.id if p.nuevo is not None else p.tercero_id)
    repo.insertar_contrato(sesion, contrato_id=contrato_id, nombre=nombre, propiedad_id=propiedad_id, tipo=tipo_fisico,
                           estado=d.estado, fecha_inicio=d.fecha_inicio, fecha_fin_prevista=d.fecha_fin_prevista,
                           habitacion=habitacion, notas=d.notas)
    for p in sorted(d.personas or [], key=lambda x: (x.rol, x.clave_actor)):
        repo.insertar_participante(sesion, fila_id=uuid.uuid5(contrato_id, f"participante:{p.clave_actor}:{p.rol}"),
                                   contrato_id=contrato_id, actor_id=actores[p.clave_actor], rol=p.rol,
                                   principal=p.principal, desde=d.fecha_inicio, hasta=None)
    if d.clausula is not None:
        columnas = m.validar_clausula(d.clausula)
        assert isinstance(columnas, dict)
        repo.insertar_clausula(sesion, fila_id=uuid.uuid5(contrato_id, "clausula:1"), contrato_id=contrato_id,
                               desde=d.fecha_inicio, hasta=None, columnas=columnas)
    for t in sorted(d.servicios or [], key=lambda x: str(x.servicio_id)):
        actor = None if t.inquilino_tercero_id is None else actores[str(t.inquilino_tercero_id)]
        columnas = m.columnas_tratamiento(t.modo, actor, t.porcentaje)
        assert isinstance(columnas, dict)
        repo.insertar_tratamiento(sesion, fila_id=uuid.uuid5(contrato_id, f"servicio:{t.servicio_id}:{d.fecha_inicio}"),
                                  contrato_id=contrato_id, servicio_id=t.servicio_id, columnas=columnas,
                                  desde=d.fecha_inicio, hasta=None)


# ------------------------------------------------------------------ C-CON-01 alta
def alta(sesion: SesionMotor, *, contrato_id: uuid.UUID, propiedad_id: uuid.UUID, datos: DatosContrato,
         reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    nombre = _nombre(datos.nombre)
    if isinstance(nombre, Rechazo):
        return nombre
    if datos.tipo not in m.TIPOS_CONTRATO or datos.estado not in m.ESTADOS_ALTA:
        return Rechazo(e.ENTRADA_INVALIDA)
    tipo_fisico = m.TIPOS_CONTRATO[datos.tipo]
    contenido = {"propiedad_id": str(propiedad_id), **_contenido_nuevo(datos), "nombre": nombre}
    bloquear_intencion_propiedad(sesion, contrato_id)                                        # 0P, primer recurso
    hoy = hoy_owner(sesion, reloj)
    if repo_prop.bloquear(sesion, propiedad_id) is None:                                     # nivel 3
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    existentes, nuevos = _ids_terceros(datos.personas)
    terceros = bloquear_terceros(sesion, existentes=existentes, nuevos=nuevos)               # niveles 4 y 5
    previo = replay(sesion, contrato_id, OP_ALTA, contrato_id, contenido,
                    registros_extra=())
    if previo is True:
        return resultado(sesion, contrato_id, hoy, idempotente=True)
    if isinstance(previo, Rechazo):
        return previo
    if repo_prop.existe_entidad(sesion, contrato_id):
        return Rechazo(e.IDENTIDAD_REUTILIZADA)
    ficha = repo_prop.leer(sesion, propiedad_id)
    assert ficha is not None
    rechazo = _validar_nuevo(sesion, ficha, propiedad_id, tipo_fisico, datos.habitacion, datos, terceros)
    if rechazo is not None:
        return rechazo
    rechazo = ejecutar_escritura(sesion, lambda: _escribir_nuevo(sesion, contrato_id, propiedad_id, tipo_fisico,
                                                                 datos.habitacion, datos, nombre),
                                 triggers=TRIGGERS_SUBTIPO_CONTRATO)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_ALTA, motivo=MOTIVOS[OP_ALTA], antes=None,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido, crear=True)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


# ------------------------------------------------------------------ preludio comun de las escrituras sobre un contrato
def abrir(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, operacion: str,
           contenido: dict[str, Any], row_version: int, reloj: Reloj, existentes: list[uuid.UUID] | None = None,
           nuevos: list[NuevoTercero] | None = None, registros_extra: tuple[uuid.UUID, ...] = ()) -> Abierto | Resultado | Rechazo:
    """0P -> propiedad NK -> advisory/terceros FS -> contrato NK (relectura) -> replay -> VERSION_DESFASADA.
    La propiedad se identifica con una lectura SIN lock (es inmutable: CAMPO_INMUTABLE)."""
    bloquear_intencion_propiedad(sesion, intencion_id)                                       # 0P
    hoy = hoy_owner(sesion, reloj)
    previo = repo.contrato(sesion, contrato_id)
    if previo is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    if repo_prop.bloquear(sesion, previo["propiedad_id"]) is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    terceros = bloquear_terceros(sesion, existentes=existentes or [], nuevos=nuevos or [])
    c = repo.contrato(sesion, contrato_id, bloquear=True)                                    # nivel 6
    if c is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    previo_r = replay(sesion, intencion_id, operacion, contrato_id, contenido, registros_extra)
    if previo_r is True:
        return resultado(sesion, contrato_id, hoy, idempotente=True)
    if isinstance(previo_r, Rechazo):
        return previo_r
    if c["row_version"] != row_version:
        return Rechazo(e.VERSION_DESFASADA)
    return Abierto(c={"id": contrato_id, **c}, hoy=hoy, terceros=terceros)


def _renta_pendiente(c: dict[str, Any]) -> Rechazo | None:
    """PC-CON-04: con `regla_renta_id` (dato V3) no se termina ni se cambia el inicio. Estado identico."""
    if c["regla_renta_id"] is not None:
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": e.RENTA_PENDIENTE})
    return None


def _filas_vigencia(sesion: SesionMotor, contrato_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    return {"contrato_participantes": repo.participantes(sesion, contrato_id),
            "contrato_servicios": repo.tratamientos(sesion, contrato_id),
            "contrato_revision_renta_versiones": repo.clausulas(sesion, contrato_id)}


def _ids_cierre(filas: dict[str, list[dict[str, Any]]]) -> dict[str, list[uuid.UUID]]:
    return {t: [f["id"] for f in fs if f["vigente_hasta"] is None] for t, fs in filas.items()}


def _terminar_en(sesion: SesionMotor, contrato_id: uuid.UUID, fecha: dt.date,
                 filas: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    """Cierra en `fecha` las vigencias ABIERTAS de personas, servicios y clausula; las ya cerradas no se tocan."""
    cerradas = _ids_cierre(filas)
    for tabla, ids in cerradas.items():
        repo.cerrar_vigencia(sesion, tabla, ids, fecha)
    repo.actualizar_contrato(sesion, contrato_id, {"fecha_fin_real": fecha})
    return {t: [str(i) for i in ids] for t, ids in cerradas.items()}


def _fin_anterior_a_vigencia(c: dict[str, Any], fecha: dt.date, filas: dict[str, list[dict[str, Any]]]) -> bool:
    """AJ-DELTA-06: ningun cierre produce `vigente_hasta < vigente_desde` (se miran las vigencias ABIERTAS)."""
    if c["fecha_inicio"] is not None and fecha < c["fecha_inicio"]:
        return True
    return any(f["vigente_hasta"] is None and f["vigente_desde"] is not None and f["vigente_desde"] > fecha
               for fs in filas.values() for f in fs)


# ------------------------------------------------------------------ C-CON-02 editar
def editar(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
           campos: dict[str, Any], motivo: str | None = None, inmutables_presentes: bool = False,
           reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """`campos` trae SOLO los campos presentes: nombre, notas, fecha_fin_prevista, fecha_inicio, habitacion."""
    if not campos and not inmutables_presentes:
        return Rechazo(e.ENTRADA_INVALIDA)
    nuevos = dict(campos)
    if "nombre" in nuevos:
        visible = _nombre(nuevos["nombre"])
        if isinstance(visible, Rechazo):
            return visible
        nuevos["nombre"] = visible
    if "fecha_inicio" in nuevos and nuevos["fecha_inicio"] is None:
        return Rechazo(e.FECHA_INICIO_REQUERIDA)                    # Q-CON-09: tambien en borrador
    if nuevos.get("notas") is not None and not nuevos["notas"].strip():
        return Rechazo(e.ENTRADA_INVALIDA)
    contenido = {"row_version_esperada": row_version, "motivo": motivo, "inmutables": inmutables_presentes,
                 "campos": {k: m.texto(v) for k, v in sorted(nuevos.items())}}
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_EDITAR,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    if inmutables_presentes:
        return Rechazo(e.CAMPO_INMUTABLE)
    if c["estado_documental"] == "CANCELADO":
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    cambios = {k: v for k, v in nuevos.items() if k in c and c[k] != v}
    if "fecha_fin_prevista" in cambios:
        motivo_ok = exigir_motivo(motivo)
        if isinstance(motivo_ok, Rechazo):
            return motivo_ok
    mueve_inicio = "fecha_inicio" in cambios
    if mueve_inicio:
        rechazo = _renta_pendiente(c)
        if rechazo is not None:
            return rechazo
    inicio = cambios.get("fecha_inicio", c["fecha_inicio"])
    fin_prevista = cambios.get("fecha_fin_prevista", c["fecha_fin_prevista"])
    habitacion = cambios.get("habitacion", c["habitacion"])
    ficha = repo_prop.leer(sesion, c["propiedad_id"])
    assert ficha is not None
    if "habitacion" in cambios:
        rechazo = _validar_habitacion(ficha, c["tipo_contrato"], habitacion)
        if rechazo is not None:
            return rechazo
    if mueve_inicio and ficha["fecha_salida_patrimonio"] is not None and ficha["fecha_salida_patrimonio"] < inicio:
        return Rechazo(e.PROPIEDAD_FUERA_DE_PATRIMONIO)
    if _fin_previsto_anterior_al_inicio(inicio, fin_prevista):
        return Rechazo(e.FECHA_ANTERIOR_INICIO)
    filas = _filas_vigencia(sesion, contrato_id)
    mover: dict[str, list[uuid.UUID]] = {}
    if mueve_inicio:
        if c["fecha_fin_real"] is not None and inicio > c["fecha_fin_real"]:
            return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": "INICIO_POSTERIOR_AL_FIN"})
        for tabla, fs in filas.items():
            for f in fs:
                if f["vigente_desde"] == c["fecha_inicio"]:
                    if f["vigente_hasta"] is not None and f["vigente_hasta"] < inicio:
                        return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": "VIGENCIA_INVERTIDA"})
                    mover.setdefault(tabla, []).append(f["id"])
                elif f["vigente_desde"] is not None and f["vigente_desde"] < inicio:
                    return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": "VIGENCIA_ANTERIOR_AL_INICIO"})
    if c["estado_documental"] == "FORMALIZADO" and (mueve_inicio or "habitacion" in cambios):
        coinciden = solapes(sesion, c["propiedad_id"], tipo_fisico=c["tipo_contrato"], habitacion=habitacion,
                            inicio=inicio, fin_real=c["fecha_fin_real"], excluir=frozenset({contrato_id}))
        if coinciden:
            return _rechazo_solape(coinciden)
    if not cambios:
        return resultado(sesion, contrato_id, hoy)
    antes = repo.snapshot_contrato(sesion, contrato_id)

    def escribir() -> None:
        repo.actualizar_contrato(sesion, contrato_id, cambios)
        for tabla, ids in mover.items():
            repo.mover_vigencia(sesion, tabla, ids, "vigente_desde", inicio)
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_EDITAR, motivo=MOTIVOS[OP_EDITAR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido, motivo_usuario=motivo)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


# ------------------------------------------------------------------ C-CON-03 terminar y corregir la terminacion
def terminar(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
             fecha_fin_real: dt.date, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    contenido = {"row_version_esperada": row_version, "fecha_fin_real": m.texto(fecha_fin_real)}
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_TERMINAR,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    rechazo = _renta_pendiente(c)                       # lo primero tras el replay y VERSION_DESFASADA (PC-CON-04)
    if rechazo is not None:
        return rechazo
    if c["estado_documental"] != "FORMALIZADO" or c["fecha_fin_real"] is not None:
        return Rechazo(e.CONTRATO_NO_VIGENTE)
    filas = _filas_vigencia(sesion, contrato_id)
    if _fin_anterior_a_vigencia(c, fecha_fin_real, filas):
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    antes = repo.snapshot_contrato(sesion, contrato_id)
    cerradas: dict[str, list[str]] = {}

    def escribir() -> None:
        cerradas.update(_terminar_en(sesion, contrato_id, fecha_fin_real, filas))
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_TERMINAR, motivo=MOTIVOS[OP_TERMINAR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido, extra={"cerradas": cerradas})
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


def _cerradas_por_terminacion(sesion: SesionMotor, contrato_id: uuid.UUID) -> dict[str, set[uuid.UUID]] | None:
    """Vigencias que cerro la ultima terminacion (o correccion), segun su auditoria; None si no consta."""
    import json
    for a in repo.auditorias_de_registro(sesion, contrato_id):
        intencion = (json.loads(a["despues"]) or {}).get("intencion") or {}
        if intencion.get("operacion") in (OP_TERMINAR, OP_CORREGIR_TERMINACION, OP_SUCESOR):
            return {t: {uuid.UUID(i) for i in ids} for t, ids in (intencion.get("cerradas") or {}).items()}
    return None


def corregir_terminacion(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                         fecha_fin_real: dt.date, motivo: str | None, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    contenido = {"row_version_esperada": row_version, "fecha_fin_real": m.texto(fecha_fin_real), "motivo": motivo}
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_CORREGIR_TERMINACION,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    rechazo = _renta_pendiente(c)
    if rechazo is not None:
        return rechazo
    if c["estado_documental"] != "FORMALIZADO" or c["fecha_fin_real"] is None:
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    motivo_ok = exigir_motivo(motivo)
    if isinstance(motivo_ok, Rechazo):
        return motivo_ok
    anterior = c["fecha_fin_real"]
    filas = _filas_vigencia(sesion, contrato_id)
    por_auditoria = _cerradas_por_terminacion(sesion, contrato_id)
    mover: dict[str, list[uuid.UUID]] = {}
    for tabla, fs in filas.items():
        for f in fs:
            if f["vigente_hasta"] == anterior and (por_auditoria is None or f["id"] in por_auditoria.get(tabla, set())):
                mover.setdefault(tabla, []).append(f["id"])
    ids_mover = {i for ids in mover.values() for i in ids}
    # la nueva fecha cumple la misma regla (>= inicio y >= desde de lo que se mueve) y nunca reabre nada
    if fecha_fin_real < c["fecha_inicio"] or any(
            f["id"] in ids_mover and f["vigente_desde"] > fecha_fin_real for fs in filas.values() for f in fs):
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    if fecha_fin_real == anterior:
        return resultado(sesion, contrato_id, hoy)
    if fecha_fin_real > anterior:                                         # retrasar: puede coincidir con otro firmado
        coinciden = solapes(sesion, c["propiedad_id"], tipo_fisico=c["tipo_contrato"], habitacion=c["habitacion"],
                            inicio=c["fecha_inicio"], fin_real=fecha_fin_real, excluir=frozenset({contrato_id}))
        if coinciden:
            return _rechazo_solape(coinciden)
    antes = repo.snapshot_contrato(sesion, contrato_id)

    def escribir() -> None:
        for tabla, ids in mover.items():
            repo.mover_vigencia(sesion, tabla, ids, "vigente_hasta", fecha_fin_real)
        repo.actualizar_contrato(sesion, contrato_id, {"fecha_fin_real": fecha_fin_real})
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    cerradas = {t: [str(i) for i in ids] for t, ids in mover.items()}
    auditar(sesion, contrato_id, operacion=OP_CORREGIR_TERMINACION, motivo=MOTIVOS[OP_CORREGIR_TERMINACION],
            antes=antes, despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido,
            motivo_usuario=motivo_ok, extra={"cerradas": cerradas})
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


# ------------------------------------------------------------------ C-CON-04 formalizar o cancelar
def _personas_de_filas(filas: list[dict[str, Any]]) -> list[Persona]:
    return [Persona(rol=f["rol"], principal=f["principal"], yo=f["tercero_id"] is None, tercero_id=f["tercero_id"])
            for f in filas if f["vigente_hasta"] is None]


def formalizar(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
               reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    contenido = {"row_version_esperada": row_version}
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_FORMALIZAR,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    if c["estado_documental"] != "BORRADOR":
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    if c["fecha_inicio"] is None:
        return Rechazo(e.FECHA_INICIO_REQUERIDA)
    personas = _personas_de_filas(repo.participantes(sesion, contrato_id))
    rechazo = m.validar_principales(personas, formalizado=True)             # D25 + (PROPIETARIO o GESTOR) e INQUILINO
    if rechazo is not None:
        return rechazo
    coinciden = solapes(sesion, c["propiedad_id"], tipo_fisico=c["tipo_contrato"], habitacion=c["habitacion"],
                        inicio=c["fecha_inicio"], fin_real=c["fecha_fin_real"], excluir=frozenset({contrato_id}))
    if coinciden:
        return _rechazo_solape(coinciden)                                   # sigue siendo borrador
    antes = repo.snapshot_contrato(sesion, contrato_id)

    def escribir() -> None:
        repo.actualizar_contrato(sesion, contrato_id, {"estado_documental": "FORMALIZADO"})
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_FORMALIZAR, motivo=MOTIVOS[OP_FORMALIZAR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


def cancelar(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
             motivo: str | None, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    contenido = {"row_version_esperada": row_version, "motivo": motivo}
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_CANCELAR,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    motivo_ok = exigir_motivo(motivo)
    if isinstance(motivo_ok, Rechazo):
        return motivo_ok
    if c["estado_documental"] != "BORRADOR":                                # un FORMALIZADO se termina
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    antes = repo.snapshot_contrato(sesion, contrato_id)

    def escribir() -> None:
        repo.actualizar_contrato(sesion, contrato_id, {"estado_documental": "CANCELADO"})
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_CANCELAR, motivo=MOTIVOS[OP_CANCELAR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido, motivo_usuario=motivo_ok)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


# ------------------------------------------------------------------ C-CON-05 sucesor en una habitacion
def sucesor(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
            fecha_fin_real: dt.date, nuevo: DatosContrato, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """C-CON-03 sobre el actual y C-CON-01 sobre el nuevo en UNA operacion. `nuevo.tipo` y `nuevo.habitacion` se
    HEREDAN del actual. Recursos: los de §1.3 LITERALES (0P -> propiedad -> advisory de terceros y writer de F05 si
    `nuevo` trae terceros nuevos -> terceros FS por UUID -> contrato actual NK -> servicios FS -> hijas)."""
    nombre = _nombre(nuevo.nombre)
    if isinstance(nombre, Rechazo):
        return nombre
    if nuevo.estado not in m.ESTADOS_ALTA:
        return Rechazo(e.ENTRADA_INVALIDA)
    nuevo_id = uuid.uuid5(intencion_id, "contrato")
    heredado = {k: v for k, v in _contenido_nuevo(nuevo).items() if k not in ("tipo", "habitacion")}
    contenido = {"row_version_esperada": row_version, "fecha_fin_real": m.texto(fecha_fin_real),
                 "nuevo": {**heredado, "nombre": nombre}}
    existentes, nuevos = _ids_terceros(nuevo.personas)
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_SUCESOR,
                     contenido=contenido, row_version=row_version, reloj=reloj, existentes=existentes, nuevos=nuevos,
                     registros_extra=(nuevo_id,))
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    rechazo = _renta_pendiente(c)
    if rechazo is not None:
        return rechazo
    if c["estado_documental"] != "FORMALIZADO" or c["fecha_fin_real"] is not None or c["tipo_contrato"] != m.TIPO_HABITACION:
        return Rechazo(e.CONTRATO_NO_VIGENTE)
    filas = _filas_vigencia(sesion, contrato_id)
    if _fin_anterior_a_vigencia(c, fecha_fin_real, filas):
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    if nuevo.fecha_inicio is not None and nuevo.fecha_inicio <= fecha_fin_real:
        return Rechazo(e.SUCESOR_SOLAPADO)
    if repo_prop.existe_entidad(sesion, nuevo_id):
        return Rechazo(e.IDENTIDAD_REUTILIZADA)
    ficha = repo_prop.leer(sesion, c["propiedad_id"])
    assert ficha is not None
    rechazo = _validar_nuevo(sesion, ficha, c["propiedad_id"], c["tipo_contrato"], c["habitacion"], nuevo,
                             abierto.terceros, excluir=frozenset({contrato_id}))
    if rechazo is not None:
        return rechazo
    antes = repo.snapshot_contrato(sesion, contrato_id)
    cerradas: dict[str, list[str]] = {}

    def escribir() -> None:
        cerradas.update(_terminar_en(sesion, contrato_id, fecha_fin_real, filas))
        repo.subir_version(sesion, contrato_id)
        _escribir_nuevo(sesion, nuevo_id, c["propiedad_id"], c["tipo_contrato"], c["habitacion"], nuevo, nombre)

    rechazo = ejecutar_escritura(sesion, escribir, triggers=TRIGGERS_SUBTIPO_CONTRATO)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_SUCESOR, motivo=MOTIVOS[OP_SUCESOR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido, extra={"cerradas": cerradas})
    auditar(sesion, nuevo_id, operacion=OP_SUCESOR_NUEVO, motivo=MOTIVOS[OP_SUCESOR_NUEVO], antes=None,
            despues=repo.snapshot_contrato(sesion, nuevo_id), contenido={"origen": str(contrato_id)}, crear=True)
    return resultado(sesion, nuevo_id, hoy, modificadas=(contrato_id, nuevo_id),
                      extra={"terminado": vista(sesion, contrato_id, hoy)})


# ------------------------------------------------------------------ C-CON-06 personas por vigencias
def _roles_a_cubrir(rol: str) -> str | None:
    """Que garantia de INV-ALQ-07 protege un rol: INQUILINO o arrendador (PROPIETARIO y GESTOR se suman)."""
    return "INQUILINO" if rol == "INQUILINO" else ("ARRENDADOR" if rol in m.ROLES_ARRENDADOR else None)


def _cobertura_ok(c: dict[str, Any], filas: list[dict[str, Any]]) -> Rechazo | None:
    """INV-ALQ-07: un FORMALIZADO siempre tiene (PROPIETARIO o GESTOR) e INQUILINO a lo largo de toda su vida
    (de `fecha_inicio` a `fecha_fin_real`, o sin fin). Comprobado sobre el estado FINAL simulado."""
    if c["estado_documental"] != "FORMALIZADO":
        return None
    inquilinos = [(f["vigente_desde"], f["vigente_hasta"]) for f in filas if f["rol"] == "INQUILINO"]
    arrendadores = [(f["vigente_desde"], f["vigente_hasta"]) for f in filas if f["rol"] in m.ROLES_ARRENDADOR]
    if not m.cubre(inquilinos, c["fecha_inicio"], c["fecha_fin_real"]):
        return Rechazo(e.CONTRATO_SIN_INQUILINO)
    if not m.cubre(arrendadores, c["fecha_inicio"], c["fecha_fin_real"]):
        return Rechazo(e.CONTRATO_SIN_ARRENDADOR)
    return None


def _principales_ok(filas: list[dict[str, Any]], solo_rol: str | None = None) -> Rechazo | None:
    """Como mucho un principal ABIERTO por rol (validacion previa de la EXCLUDE) y principal obligatorio solo en
    PROPIETARIO, GESTOR e INQUILINO con personas abiertas (D25). `solo_rol`: no se juzga un rol ajeno a la
    operacion (un dato heredado de V3 no bloquea cambios no relacionados)."""
    por_rol: dict[str, list[dict[str, Any]]] = {}
    for f in filas:
        if f["vigente_hasta"] is None and (solo_rol is None or f["rol"] == solo_rol):
            por_rol.setdefault(f["rol"], []).append(f)
    for rol, fs in por_rol.items():
        principales = sum(1 for f in fs if f["principal"])
        if principales > 1:
            return Rechazo(e.PRINCIPAL_DUPLICADO)
        if principales == 0 and rol in m.ROLES_PRINCIPAL_OBLIGATORIO:
            return Rechazo(e.PRINCIPAL_REQUERIDO)
    return None


def _duplicada(filas: list[dict[str, Any]], excluir: uuid.UUID | None = None) -> bool:
    """La misma persona (actor) en el mismo rol con vigencias que se solapan (reverso de la EXCLUDE)."""
    vistas = [f for f in filas if f["id"] != excluir]
    for i, a in enumerate(vistas):
        for b in vistas[i + 1:]:
            if (a["actor_id"], a["rol"]) == (b["actor_id"], b["rol"]) and m.intervalo_solapa(
                    a["vigente_desde"], a["vigente_hasta"], b["vigente_desde"], b["vigente_hasta"]):
                return True
    return False


def _principal_solapado(filas: list[dict[str, Any]]) -> bool:
    """Dos principales del mismo rol con vigencias que se solapan (reverso de la EXCLUDE de principal)."""
    ps = [f for f in filas if f["principal"]]
    return any(a["rol"] == b["rol"] and m.intervalo_solapa(a["vigente_desde"], a["vigente_hasta"],
                                                           b["vigente_desde"], b["vigente_hasta"])
               for i, a in enumerate(ps) for b in ps[i + 1:])


def anadir_persona(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                   persona: Persona, desde: dt.date, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    contenido = {"row_version_esperada": row_version, "persona": m.persona_canonica(persona), "desde": m.texto(desde)}
    existentes, nuevos = _ids_terceros([persona])
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_PERSONA_ANADIR,
                     contenido=contenido, row_version=row_version, reloj=reloj, existentes=existentes, nuevos=nuevos)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    if c["estado_documental"] == "CANCELADO":
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    if persona.rol not in m.ROLES:
        return Rechazo(e.ROL_DESCONOCIDO)
    rechazo = m.validar_personas_alta([persona], formalizado=False)
    if rechazo is not None:
        return rechazo
    tid = persona.tercero_id
    if tid is not None and (abierto.terceros.get(tid) is None or not abierto.terceros[tid]["enabled"]):
        return Rechazo(e.TERCERO_NO_DISPONIBLE, {"tercero_id": str(tid)})
    if persona.nuevo is not None and (abierto.terceros.get(persona.nuevo.id) is not None):
        return Rechazo(e.IDENTIDAD_REUTILIZADA)
    rechazo = m.validar_yo([persona])
    if rechazo is not None:
        return rechazo
    if persona.yo and repo_prop.actor_self(sesion) is None:
        return Rechazo(e.ACTOR_DESCONOCIDO)
    if c["fecha_inicio"] is None:
        return Rechazo(e.FECHA_INICIO_REQUERIDA)
    if desde < c["fecha_inicio"]:
        return Rechazo(e.FECHA_ANTERIOR_INICIO)
    if c["fecha_fin_real"] is not None and desde > c["fecha_fin_real"]:
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    filas = repo.participantes(sesion, contrato_id)
    fila_id = uuid.uuid5(intencion_id, "persona")
    # actor de la persona nueva: si ya existe (tercero existente o YO) para la comprobacion de duplicados
    actor_previo = repo_prop.actor_self(sesion) if persona.yo else (None if tid is None else _actor_existente(sesion, tid))
    hasta = c["fecha_fin_real"]
    simuladas = filas + [{"id": fila_id, "actor_id": actor_previo or uuid.uuid4(), "tercero_id": tid, "nombre": None,
                          "rol": persona.rol, "principal": persona.principal, "vigente_desde": desde,
                          "vigente_hasta": hasta}]
    if _duplicada(simuladas):
        return Rechazo(e.PARTICIPANTE_DUPLICADO)
    if _principal_solapado(simuladas):
        return Rechazo(e.PRINCIPAL_DUPLICADO)
    rechazo = _principales_ok(simuladas, persona.rol)
    if rechazo is not None:
        return rechazo
    antes = repo.snapshot_contrato(sesion, contrato_id)

    def escribir() -> None:
        if persona.nuevo is not None:
            crear_tercero(sesion, persona.nuevo)
        if persona.yo:
            actor = repo_prop.actor_self(sesion)
            if actor is None:
                raise Abortar(Rechazo(e.ACTOR_DESCONOCIDO))
        else:
            actor = actor_de(sesion, persona.nuevo.id if persona.nuevo is not None else tid)
        repo.insertar_participante(sesion, fila_id=fila_id, contrato_id=contrato_id, actor_id=actor, rol=persona.rol,
                                   principal=persona.principal, desde=desde, hasta=hasta)
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_PERSONA_ANADIR, motivo=MOTIVOS[OP_PERSONA_ANADIR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


def _actor_existente(sesion: SesionMotor, tercero_id: uuid.UUID) -> uuid.UUID | None:
    from app.actores import repositorio as repo_act
    return repo_act.leer_actor_de_tercero(sesion, tercero_id)


def cerrar_persona(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                   persona_id: uuid.UUID, hasta: dt.date, nuevo_principal_id: uuid.UUID | None = None,
                   reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    contenido = {"row_version_esperada": row_version, "persona_id": str(persona_id), "hasta": m.texto(hasta),
                 "nuevo_principal_id": m.texto(nuevo_principal_id)}
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_PERSONA_CERRAR,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    if c["estado_documental"] == "CANCELADO":
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    filas = repo.participantes(sesion, contrato_id)
    p = next((f for f in filas if f["id"] == persona_id), None)
    if p is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    if p["vigente_hasta"] is not None:                        # nunca se cierra una vigencia ya cerrada
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    if hasta < p["vigente_desde"]:
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    if c["fecha_fin_real"] is not None and hasta > c["fecha_fin_real"]:
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": "FUERA_DE_LA_VIGENCIA_DEL_CONTRATO"})
    quedan = [f for f in filas if f["rol"] == p["rol"] and f["id"] != persona_id and f["vigente_hasta"] is None]
    cambios_filas: dict[uuid.UUID, dict[str, Any]] = {persona_id: {"vigente_hasta": hasta}}
    if p["principal"] and p["rol"] in m.ROLES_PRINCIPAL_OBLIGATORIO and quedan:
        sucesor_p = next((f for f in quedan if f["id"] == nuevo_principal_id), None)
        if sucesor_p is None:
            return Rechazo(e.PRINCIPAL_REQUERIDO)
        # la EXCLUDE de principal impide dos principales a la vez: el cerrado deja de serlo (modelo fisico)
        cambios_filas[persona_id]["principal"] = False
        cambios_filas[nuevo_principal_id] = {"principal": True}
    simuladas = [{**f, **cambios_filas.get(f["id"], {})} for f in filas]
    rechazo = _cobertura_ok(c, simuladas)
    if rechazo is not None:
        return rechazo
    antes = repo.snapshot_contrato(sesion, contrato_id)

    def escribir() -> None:
        # primero el cierre (libera el principal), despues el nuevo principal
        for fid in (persona_id, nuevo_principal_id):
            if fid is not None and fid in cambios_filas:
                repo.actualizar_participante(sesion, fid, cambios_filas[fid])
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_PERSONA_CERRAR, motivo=MOTIVOS[OP_PERSONA_CERRAR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


def corregir_persona(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                     persona_id: uuid.UUID, campos: dict[str, Any], motivo: str | None,
                     reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """Errata de fechas (`vigente_desde`, `vigente_hasta`) o de `principal`, con motivo. Nunca reabre (hasta None)."""
    contenido = {"row_version_esperada": row_version, "persona_id": str(persona_id), "motivo": motivo,
                 "campos": {k: m.texto(v) for k, v in sorted(campos.items())}}
    if not campos or set(campos) - {"vigente_desde", "vigente_hasta", "principal"} or campos.get("vigente_hasta", 0) is None:
        return Rechazo(e.ENTRADA_INVALIDA)
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_PERSONA_CORREGIR,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    if c["estado_documental"] == "CANCELADO":
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    motivo_ok = exigir_motivo(motivo)
    if isinstance(motivo_ok, Rechazo):
        return motivo_ok
    filas = repo.participantes(sesion, contrato_id)
    p = next((f for f in filas if f["id"] == persona_id), None)
    if p is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    nuevo = {**p, **campos}
    if c["fecha_inicio"] is None or nuevo["vigente_desde"] < c["fecha_inicio"]:
        return Rechazo(e.FECHA_ANTERIOR_INICIO)
    if nuevo["vigente_hasta"] is not None and nuevo["vigente_hasta"] < nuevo["vigente_desde"]:
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    if c["fecha_fin_real"] is not None and nuevo["vigente_desde"] > c["fecha_fin_real"]:
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    simuladas = [nuevo if f["id"] == persona_id else f for f in filas]
    if _duplicada(simuladas):
        return Rechazo(e.PARTICIPANTE_DUPLICADO)
    if _principal_solapado(simuladas):
        return Rechazo(e.PRINCIPAL_DUPLICADO)
    rechazo = _principales_ok(simuladas, p["rol"])
    if rechazo is not None:
        return rechazo
    rechazo = _cobertura_ok(c, simuladas)
    if rechazo is not None:
        return rechazo
    cambios = {k: v for k, v in campos.items() if p[k] != v}
    if not cambios:
        return resultado(sesion, contrato_id, hoy)
    antes = repo.snapshot_contrato(sesion, contrato_id)

    def escribir() -> None:
        repo.actualizar_participante(sesion, persona_id, cambios)
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_PERSONA_CORREGIR, motivo=MOTIVOS[OP_PERSONA_CORREGIR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido, motivo_usuario=motivo_ok)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


# ------------------------------------------------------------------ C-REV-01 clausula de revision
def nueva_clausula(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                   clausula: Clausula, desde: dt.date, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """Version nueva: cierra la abierta en `desde - 1`. `desde` posterior al `vigente_desde` de la abierta (igual ->
    DESDE_IGUAL_A_VERSION_ABIERTA; anterior -> FECHA_ANTERIOR_INICIO). La clausula NUNCA toca la renta."""
    contenido = {"row_version_esperada": row_version, "desde": m.texto(desde), "clausula": m.clausula_canonica(clausula)}
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_CLAUSULA,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    if c["estado_documental"] == "CANCELADO":
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    columnas = m.validar_clausula(clausula)
    if isinstance(columnas, Rechazo):
        return columnas
    if c["fecha_inicio"] is None:
        return Rechazo(e.FECHA_INICIO_REQUERIDA)
    if desde < c["fecha_inicio"]:
        return Rechazo(e.FECHA_ANTERIOR_INICIO)
    if c["fecha_fin_real"] is not None and desde > c["fecha_fin_real"]:
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    versiones = repo.clausulas(sesion, contrato_id)
    abierta = next((v for v in versiones if v["vigente_hasta"] is None and v["vigente_desde"] is not None), None)
    if abierta is not None:
        if desde == abierta["vigente_desde"]:
            return Rechazo(e.DESDE_IGUAL_A_VERSION_ABIERTA)
        if desde < abierta["vigente_desde"]:
            return Rechazo(e.FECHA_ANTERIOR_INICIO)
    antes = repo.snapshot_contrato(sesion, contrato_id)
    fila_id = uuid.uuid5(intencion_id, "clausula")

    def escribir() -> None:
        if abierta is not None:
            repo.cerrar_vigencia(sesion, "contrato_revision_renta_versiones", [abierta["id"]],
                                 desde - dt.timedelta(days=1))
        repo.insertar_clausula(sesion, fila_id=fila_id, contrato_id=contrato_id, desde=desde,
                               hasta=c["fecha_fin_real"], columnas=columnas)
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_CLAUSULA, motivo=MOTIVOS[OP_CLAUSULA], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))


def corregir_clausula(sesion: SesionMotor, *, contrato_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
                      version_id: uuid.UUID, clausula: Clausula, motivo: str | None,
                      reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """Errata auditada de una version (parametros del tipo). Las filas V3 sin `vigente_desde` son solo lectura."""
    contenido = {"row_version_esperada": row_version, "version_id": str(version_id), "motivo": motivo,
                 "clausula": m.clausula_canonica(clausula)}
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_CLAUSULA_CORREGIR,
                     contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    if c["estado_documental"] == "CANCELADO":
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    motivo_ok = exigir_motivo(motivo)
    if isinstance(motivo_ok, Rechazo):
        return motivo_ok
    v = next((x for x in repo.clausulas(sesion, contrato_id) if x["id"] == version_id), None)
    if v is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    if v["vigente_desde"] is None:                       # fila V3: solo lectura
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": "CLAUSULA_V3_SOLO_LECTURA"})
    columnas = m.validar_clausula(clausula)
    if isinstance(columnas, Rechazo):
        return columnas
    cambios = {k: val for k, val in columnas.items() if v[k] != val}
    if not cambios:
        return resultado(sesion, contrato_id, hoy)
    antes = repo.snapshot_contrato(sesion, contrato_id)

    def escribir() -> None:
        repo.actualizar_clausula(sesion, version_id, cambios)
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_CLAUSULA_CORREGIR, motivo=MOTIVOS[OP_CLAUSULA_CORREGIR], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido, motivo_usuario=motivo_ok)
    return resultado(sesion, contrato_id, hoy, modificadas=(contrato_id,))
