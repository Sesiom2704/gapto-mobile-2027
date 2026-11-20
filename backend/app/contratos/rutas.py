# ============================================================
# GAPTO MOBILE 2027
# Fichero: rutas.py
# Ruta: backend/app/contratos/rutas.py
# Descripcion: Rutas HTTP de F06-02/03 (API DE INTEGRACION, PENDIENTE DE CONSOLIDACION F10), registradas por
#   `create_app` con UNA llamada (patron de patrimonio/rutas.py). Escrituras con POST (PA-20); una transaccion de
#   UnidadDeTrabajo por comando con request_id = intencion_id; rechazos con el mapa propio de contratos/errores.py.
#   ESCRITURAS
#     POST /v1/intenciones/contrato-alquiler                    C-CON-01
#     POST /v1/contratos/{id}/editar | terminar | corregir-terminacion | formalizar | cancelar | sucesor
#     POST /v1/contratos/{id}/personas                          C-CON-06 (anadir)
#     POST /v1/contratos/{id}/personas/{p}/cerrar | corregir    C-CON-06
#     POST /v1/contratos/{id}/clausula                          C-REV-01 (version nueva)
#     POST /v1/contratos/{id}/clausula/{v}/corregir             C-REV-01 (errata)
#     POST /v1/contratos/{id}/servicios/{servicio_id}           C-SRV-04
#     POST /v1/intenciones/servicio                             C-SRV-01
#     POST /v1/servicios/{id}/editar | baja                     C-SRV-02, C-SRV-03
#     POST /v1/terceros/{id}/roles | clasificaciones            C-TER-01, C-TER-03
#     POST /v1/clasificaciones-tercero [ /{id}/renombrar | mover | desactivar | reactivar ]   C-TER-03 (arbol)
#   LECTURAS
#     GET  /v1/terceros/asistente-contratos?q=                  V-bis (selector del asistente; ruta del cliente;
#                                                               va ANTES de GET /v1/terceros/{id})
#     GET  /v1/contratos/{id}                                   L-CON-02
#     GET  /v1/propiedades/{id}/contratos [ /propuesta ]        L-CON-01, L-CON-03
#     GET  /v1/propiedades/{id}/servicios                       L-SRV-01
#     GET  /v1/terceros/{id}                                    L-TER-01 (RUTA NUEVA: debe registrarse DESPUES de
#                                                               GET /v1/terceros/candidatos, que declara create_app)
#     GET  /v1/clasificaciones-tercero                          arbol (C-TER-03)
#   V-ter reutiliza GET /v1/terceros/candidatos y POST /v1/terceros/{id}/reactivar de F05, sin cambios.
#   Las rutas de DIRECCIONES de terceros (C-TER-02) NO existen en este bloque.
#   (Rutas del arbol de clasificaciones: el contrato v1.1 no fija su ruta; esta es una propuesta a confirmar.)
# Version: 0.1.1 (F06 T3-F06 Bloque 3, pasos 3-4 con base): L-TER-01 devuelve la ficha sin doble envoltorio
#   («tercero» dentro de «tercero»), con la forma FichaTercero del cliente.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, pasos 3 y 4)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Callable

from fastapi import Depends, FastAPI, Query
from fastapi.responses import JSONResponse

from app.comun.fecha_funcional import hoy_owner
from app.contratos import dto
from app.contratos import errores as e
from app.contratos import lecturas, servicio, servicios
from app.contratos import terceros as ter
from app.contratos.modelos import Rechazo, Resultado
from app.core.contexto import ContextoOperacion


def _texto(valor: Any) -> Any:
    """JSON exacto: fechas ISO, UUID y Decimal como texto (sin pasar por float)."""
    if isinstance(valor, dict):
        return {k: _texto(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_texto(v) for v in valor]
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, dt.date):
        return valor.isoformat()
    if hasattr(valor, "as_tuple"):
        return str(valor)
    return valor


def _rechazo(r: Rechazo) -> JSONResponse:
    status, cuerpo = e.rechazo_http(r.codigo, r.detalle)
    return JSONResponse(_texto(cuerpo), status_code=status)


def _no_encontrado() -> JSONResponse:
    return _rechazo(Rechazo(e.AGREGADO_NO_ENCONTRADO))


def _datos_contrato(c: dto.AltaContrato, personas=None) -> servicio.DatosContrato:
    return servicio.DatosContrato(
        nombre=c.nombre, tipo=c.tipo, habitacion=c.habitacion, fecha_inicio=c.fecha_inicio,
        fecha_fin_prevista=c.fecha_fin_prevista, estado=c.estado,
        personas=None if c.personas is None else [p.a_modelo() for p in c.personas],
        clausula=None if c.clausula_revision is None else c.clausula_revision.a_modelo(),
        servicios=None if c.servicios is None else [t.a_modelo() for t in c.servicios], notas=c.notas,
        renta_presente=c.renta_presente())


def _datos_sucesor(n: dto.NuevoContratoSucesor) -> servicio.DatosContrato:
    """tipo y habitacion se HEREDAN del contrato actual: el servicio los sustituye por los del actual."""
    return servicio.DatosContrato(
        nombre=n.nombre, tipo="HABITACION", habitacion=None, fecha_inicio=n.fecha_inicio,
        fecha_fin_prevista=n.fecha_fin_prevista, estado=n.estado,
        personas=None if n.personas is None else [p.a_modelo() for p in n.personas],
        clausula=None if n.clausula_revision is None else n.clausula_revision.a_modelo(),
        servicios=None if n.servicios is None else [t.a_modelo() for t in n.servicios], notas=n.notas,
        renta_presente=n.renta_presente())


def registrar(app: FastAPI, *, unidad, owner: Callable[[], uuid.UUID], contexto: Callable[[], ContextoOperacion],
              autorizar, reloj) -> None:
    dep = [Depends(autorizar)]

    def _comando(nombre: str, intencion_id: uuid.UUID, clave: str, operacion) -> Any:
        ctx = ContextoOperacion.de_usuario(owner(), request_id=intencion_id)
        salida = unidad.ejecutar(ctx, operacion, nombre=f"F06-02/03 {nombre}")
        if isinstance(salida, Rechazo):
            return _rechazo(salida)
        assert isinstance(salida, Resultado)
        cuerpo = {clave: salida.dato, f"{clave}_id": salida.dato.get("id"), "row_version": salida.dato.get("row_version"),
                  "idempotente": salida.idempotente, "modificadas": list(salida.modificadas), **salida.extra}
        return _texto(cuerpo)

    def _lectura(nombre: str, operacion) -> Any:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F06-02/03 {nombre}")
        return _no_encontrado() if salida is None else _texto(salida)

    # ============================================================ C-CON-01 alta
    @app.post("/v1/intenciones/contrato-alquiler", dependencies=dep)
    def alta_contrato(c: dto.AltaContrato):
        return _comando("contrato_alta", c.intencion_id, "contrato", lambda s: servicio.alta(
            s, contrato_id=c.intencion_id, propiedad_id=c.propiedad_id, datos=_datos_contrato(c), reloj=reloj))

    # ============================================================ C-CON-02..05
    @app.post("/v1/contratos/{contrato_id}/editar", dependencies=dep)
    def editar_contrato(contrato_id: uuid.UUID, c: dto.EditarContrato):
        return _comando("contrato_editar", c.intencion_id, "contrato", lambda s: servicio.editar(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            campos=dto.presentes(c, dto.CAMPOS_EDITAR_CONTRATO), motivo=c.motivo,
            inmutables_presentes=any(n in c.model_fields_set for n in dto.CAMPOS_INMUTABLES), reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/terminar", dependencies=dep)
    def terminar_contrato(contrato_id: uuid.UUID, c: dto.TerminarContrato):
        return _comando("contrato_terminar", c.intencion_id, "contrato", lambda s: servicio.terminar(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            fecha_fin_real=c.fecha_fin_real, reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/corregir-terminacion", dependencies=dep)
    def corregir_terminacion(contrato_id: uuid.UUID, c: dto.CorregirTerminacion):
        return _comando("contrato_corregir_terminacion", c.intencion_id, "contrato",
                        lambda s: servicio.corregir_terminacion(
                            s, contrato_id=contrato_id, intencion_id=c.intencion_id,
                            row_version=c.row_version_esperada, fecha_fin_real=c.fecha_fin_real, motivo=c.motivo,
                            reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/formalizar", dependencies=dep)
    def formalizar_contrato(contrato_id: uuid.UUID, c: dto.VersionContrato):
        return _comando("contrato_formalizar", c.intencion_id, "contrato", lambda s: servicio.formalizar(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/cancelar", dependencies=dep)
    def cancelar_contrato(contrato_id: uuid.UUID, c: dto.CancelarContrato):
        return _comando("contrato_cancelar", c.intencion_id, "contrato", lambda s: servicio.cancelar(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            motivo=c.motivo, reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/sucesor", dependencies=dep)
    def sucesor_contrato(contrato_id: uuid.UUID, c: dto.SucesorContrato):
        return _comando("contrato_sucesor", c.intencion_id, "contrato", lambda s: servicio.sucesor(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            fecha_fin_real=c.fecha_fin_real, nuevo=_datos_sucesor(c.nuevo), reloj=reloj))

    # ============================================================ C-CON-06 personas
    @app.post("/v1/contratos/{contrato_id}/personas", dependencies=dep)
    def anadir_persona(contrato_id: uuid.UUID, c: dto.AnadirPersona):
        persona = dto.PersonaDto(actor=c.actor, rol=c.rol, principal=c.principal).a_modelo(c.desde)
        return _comando("persona_anadir", c.intencion_id, "contrato", lambda s: servicio.anadir_persona(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            persona=persona, desde=c.desde, reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/personas/{persona_id}/cerrar", dependencies=dep)
    def cerrar_persona(contrato_id: uuid.UUID, persona_id: uuid.UUID, c: dto.CerrarPersona):
        return _comando("persona_cerrar", c.intencion_id, "contrato", lambda s: servicio.cerrar_persona(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            persona_id=persona_id, hasta=c.hasta, nuevo_principal_id=c.nuevo_principal, reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/personas/{persona_id}/corregir", dependencies=dep)
    def corregir_persona(contrato_id: uuid.UUID, persona_id: uuid.UUID, c: dto.CorregirPersona):
        datos = c.model_dump()
        campos = {fisico: datos[n] for n, fisico in (("desde", "vigente_desde"), ("hasta", "vigente_hasta"),
                                                    ("principal", "principal")) if n in c.model_fields_set}
        return _comando("persona_corregir", c.intencion_id, "contrato", lambda s: servicio.corregir_persona(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            persona_id=persona_id, campos=campos, motivo=c.motivo, reloj=reloj))

    # ============================================================ C-REV-01 clausula
    @app.post("/v1/contratos/{contrato_id}/clausula", dependencies=dep)
    def nueva_clausula(contrato_id: uuid.UUID, c: dto.NuevaClausula):
        return _comando("clausula_nueva", c.intencion_id, "contrato", lambda s: servicio.nueva_clausula(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            clausula=c.clausula.a_modelo(), desde=c.desde, reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/clausula/{version_id}/corregir", dependencies=dep)
    def corregir_clausula(contrato_id: uuid.UUID, version_id: uuid.UUID, c: dto.CorregirClausula):
        return _comando("clausula_corregir", c.intencion_id, "contrato", lambda s: servicio.corregir_clausula(
            s, contrato_id=contrato_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            version_id=version_id, clausula=c.clausula.a_modelo(), motivo=c.motivo, reloj=reloj))

    # ============================================================ C-SRV-01..04
    @app.post("/v1/intenciones/servicio", dependencies=dep)
    def alta_servicio(c: dto.AltaServicio):
        return _comando("servicio_alta", c.intencion_id, "servicio", lambda s: servicios.alta(
            s, servicio_id=c.intencion_id, tipo_servicio=c.tipo_servicio, nombre=c.nombre,
            categoria_default_id=c.categoria_default_id, propiedad_id=c.propiedad_id, desde=c.desde, notas=c.notas,
            reloj=reloj))

    @app.post("/v1/servicios/{servicio_id}/editar", dependencies=dep)
    def editar_servicio(servicio_id: uuid.UUID, c: dto.EditarServicio):
        return _comando("servicio_editar", c.intencion_id, "servicio", lambda s: servicios.editar(
            s, servicio_id=servicio_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            campos=dto.presentes(c, ("nombre", "categoria_default_id", "notas")), reloj=reloj))

    @app.post("/v1/servicios/{servicio_id}/baja", dependencies=dep)
    def baja_servicio(servicio_id: uuid.UUID, c: dto.BajaServicio):
        return _comando("servicio_baja", c.intencion_id, "servicio", lambda s: servicios.baja(
            s, servicio_id=servicio_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            fecha_fin_real=c.fecha_fin_real, reloj=reloj))

    @app.post("/v1/contratos/{contrato_id}/servicios/{servicio_id}", dependencies=dep)
    def tratamiento_servicio(contrato_id: uuid.UUID, servicio_id: uuid.UUID, c: dto.TratamientoContrato):
        modo, inquilino, porcentaje, desde = c.plano()
        if modo is None:
            return _rechazo(Rechazo(e.ENTRADA_INVALIDA))
        return _comando("servicio_tratamiento", c.intencion_id, "contrato", lambda s: servicios.tratamiento(
            s, contrato_id=contrato_id, servicio_id=servicio_id, intencion_id=c.intencion_id,
            row_version=c.row_version_esperada, modo=modo, inquilino_tercero_id=inquilino,
            porcentaje=porcentaje, desde=desde, corregir=c.corregir, motivo=c.motivo, reloj=reloj))

    # ============================================================ C-TER-01 y C-TER-03
    @app.post("/v1/terceros/{tercero_id}/roles", dependencies=dep)
    def roles_tercero(tercero_id: uuid.UUID, c: dto.AnadirRoles):
        return _comando("tercero_roles", c.intencion_id, "tercero", lambda s: ter.anadir_roles(
            s, tercero_id=tercero_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            anadir=c.anadir, quitar=c.quitar))

    @app.post("/v1/terceros/{tercero_id}/clasificaciones", dependencies=dep)
    def clasificaciones_tercero(tercero_id: uuid.UUID, c: dto.AsignarClasificaciones):
        return _comando("tercero_clasificaciones", c.intencion_id, "tercero", lambda s: ter.asignar_clasificaciones(
            s, tercero_id=tercero_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            anadir=c.anadir, principal=c.principal, principal_presente="principal" in c.model_fields_set,
            quitar=c.quitar))

    @app.post("/v1/clasificaciones-tercero", dependencies=dep)
    def alta_clasificacion(c: dto.AltaClasificacion):
        return _comando("clasificacion_alta", c.intencion_id, "clasificacion", lambda s: ter.crear_clasificacion(
            s, clasificacion_id=c.intencion_id, nombre=c.nombre, parent_id=c.parent_id))

    @app.post("/v1/clasificaciones-tercero/{clasificacion_id}/renombrar", dependencies=dep)
    def renombrar_clasificacion(clasificacion_id: uuid.UUID, c: dto.RenombrarClasificacion):
        return _comando("clasificacion_renombrar", c.intencion_id, "clasificacion",
                        lambda s: ter.renombrar_clasificacion(
                            s, clasificacion_id=clasificacion_id, intencion_id=c.intencion_id,
                            row_version=c.row_version_esperada, nombre=c.nombre))

    @app.post("/v1/clasificaciones-tercero/{clasificacion_id}/mover", dependencies=dep)
    def mover_clasificacion(clasificacion_id: uuid.UUID, c: dto.MoverClasificacion):
        return _comando("clasificacion_mover", c.intencion_id, "clasificacion", lambda s: ter.mover_clasificacion(
            s, clasificacion_id=clasificacion_id, intencion_id=c.intencion_id, row_version=c.row_version_esperada,
            parent_id=c.parent_id))

    @app.post("/v1/clasificaciones-tercero/{clasificacion_id}/desactivar", dependencies=dep)
    def desactivar_clasificacion(clasificacion_id: uuid.UUID, c: dto.EstadoClasificacion):
        return _comando("clasificacion_desactivar", c.intencion_id, "clasificacion",
                        lambda s: ter.desactivar_clasificacion(
                            s, clasificacion_id=clasificacion_id, intencion_id=c.intencion_id,
                            row_version=c.row_version_esperada))

    @app.post("/v1/clasificaciones-tercero/{clasificacion_id}/reactivar", dependencies=dep)
    def reactivar_clasificacion(clasificacion_id: uuid.UUID, c: dto.EstadoClasificacion):
        return _comando("clasificacion_reactivar", c.intencion_id, "clasificacion",
                        lambda s: ter.reactivar_clasificacion(
                            s, clasificacion_id=clasificacion_id, intencion_id=c.intencion_id,
                            row_version=c.row_version_esperada))

    # ============================================================ lecturas (las rutas ESTATICAS van antes que {id})
    @app.get("/v1/terceros/asistente-contratos", dependencies=dep)
    def selector_terceros(q: str | None = Query(None, max_length=160)):
        return _texto({"terceros": unidad.ejecutar(
            contexto(), lambda s: lecturas.selector_asistente(s, q), nombre="F06-02/03 V-bis selector_terceros")})

    @app.get("/v1/contratos/{contrato_id}", dependencies=dep)
    def detalle_contrato(contrato_id: uuid.UUID):
        vista = unidad.ejecutar(contexto(), lambda s: lecturas.detalle_contrato(s, contrato_id, hoy_owner(s, reloj)),
                                nombre="F06-02/03 L-CON-02")
        return _no_encontrado() if vista is None else _texto({"contrato": vista})

    @app.get("/v1/propiedades/{propiedad_id}/contratos", dependencies=dep)
    def contratos_de_propiedad(propiedad_id: uuid.UUID):
        return _lectura("L-CON-01", lambda s: lecturas.contratos_de_propiedad(s, propiedad_id, hoy_owner(s, reloj)))

    @app.get("/v1/propiedades/{propiedad_id}/contratos/propuesta", dependencies=dep)
    def propuesta_contrato(propiedad_id: uuid.UUID, tipo: dto.TipoContrato = Query(...),
                           habitacion: int | None = Query(None, ge=1), inicio: dt.date | None = Query(None),
                           inquilino_id: uuid.UUID | None = Query(None)):
        return _lectura("L-CON-03", lambda s: lecturas.propuesta(
            s, propiedad_id, tipo=tipo, habitacion=habitacion, inicio=inicio, inquilino_id=inquilino_id,
            hoy=hoy_owner(s, reloj)))

    @app.get("/v1/propiedades/{propiedad_id}/servicios", dependencies=dep)
    def servicios_de_propiedad(propiedad_id: uuid.UUID):
        return _lectura("L-SRV-01", lambda s: lecturas.servicios_de_propiedad(s, propiedad_id, hoy_owner(s, reloj)))

    @app.get("/v1/terceros/{tercero_id}", dependencies=dep)
    def detalle_tercero(tercero_id: uuid.UUID):
        vista = unidad.ejecutar(contexto(), lambda s: lecturas.tercero_detalle(s, tercero_id),
                                nombre="F06-02/03 L-TER-01")
        if vista is None:
            return _rechazo(Rechazo(e.TERCERO_NO_ENCONTRADO))
        return _texto(vista)   # FichaTercero {tercero, roles, clasificaciones, uso, uso_en_gapto}: sin doble envoltorio

    @app.get("/v1/clasificaciones-tercero", dependencies=dep)
    def arbol_clasificaciones():
        from app.contratos import repositorio as repo
        filas = unidad.ejecutar(contexto(), repo.clasificaciones, nombre="F06-02/03 clasificaciones_tercero")
        return _texto({"clasificaciones": [{**f, "clasificacion_id": f["id"], "padre_id": f["parent_id"]}
                                           for f in filas]})
