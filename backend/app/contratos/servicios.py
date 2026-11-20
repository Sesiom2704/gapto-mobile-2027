# ============================================================
# GAPTO MOBILE 2027
# Fichero: servicios.py
# Ruta: backend/app/contratos/servicios.py
# Descripcion: Writers de SERVICIOS de F06-02/03 (contrato v1.1 Parte III; M-9; Q-CON-04; PA-18):
#     C-SRV-01 alta   C-SRV-02 editar   C-SRV-03 baja   C-SRV-04 tratamiento en el contrato
#   Sin DELETE: toda retirada es cerrar una vigencia con UPDATE; toda errata, un UPDATE auditado.
#   NO crea reglas (importe y compania esperados: F06-04) ni derecho de cobro alguno: el tratamiento solo propone
#   en el gasto (F06-05). La baja de un servicio con regla financiera se rechaza con el motivo
#   REGLA_SERVICIO_PENDIENTE_DE_F06_04 (AJ-DELTA-05), nunca con el de renta.
#   Orden de recursos (§1.3): 0P -> propiedad(es) NK -> contratos NK por UUID -> servicio (FOR NO KEY UPDATE en
#   C-SRV-01..03; FOR SHARE en C-SRV-04) -> hijas. Agregado servicio = `entidades.row_version` del servicio;
#   agregado contrato = el del contrato (se sube cuando se toca una fila de contrato_servicios).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 3)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from app.categorias.normalizacion import nombre_visible
from app.comun.fecha_funcional import Reloj, reloj_sistema
from app.contratos import errores as e
from app.contratos import lecturas
from app.contratos import modelos as m
from app.contratos import repositorio as repo
from app.contratos.base import (TRIGGERS_SUBTIPO_SERVICIO, auditar, bloquear_intencion_propiedad,
                                ejecutar_escritura, replay)
from app.contratos.modelos import Rechazo, Resultado
from app.contratos.servicio import Abierto, abrir, exigir_motivo, resultado as resultado_contrato
from app.core.unidad_trabajo import SesionMotor
from app.propiedades import repositorio as repo_prop

OP_ALTA, OP_EDITAR, OP_BAJA, OP_TRATAMIENTO = ("SERVICIO_ALTA", "SERVICIO_EDITAR", "SERVICIO_BAJA",
                                               "CONTRATO_SERVICIO_TRATAMIENTO")
MOTIVOS = {OP_ALTA: "F06-02/03 SERVICIO ALTA", OP_EDITAR: "F06-02/03 SERVICIO EDITAR", OP_BAJA: "F06-02/03 SERVICIO BAJA",
           OP_TRATAMIENTO: "F06-02/03 CONTRATO SERVICIO TRATAMIENTO"}


def _nombre(nombre: Any) -> str | Rechazo:
    visible = nombre_visible(nombre) if isinstance(nombre, str) else ""
    return visible if 0 < len(visible) <= m.LONGITUD_NOMBRE else Rechazo(e.ENTRADA_INVALIDA)


def vista_servicio(sesion: SesionMotor, servicio_id: uuid.UUID) -> dict[str, Any]:
    s = repo.servicio(sesion, servicio_id)
    assert s is not None
    return {**s, "vinculos": repo.vinculos_servicio(sesion, servicio_id)}


def _resultado(sesion: SesionMotor, servicio_id: uuid.UUID, *, idempotente: bool = False,
               modificadas: tuple[uuid.UUID, ...] = ()) -> Resultado:
    return Resultado(dato=vista_servicio(sesion, servicio_id), idempotente=idempotente, modificadas=modificadas)


# ------------------------------------------------------------------ C-SRV-01 alta
def alta(sesion: SesionMotor, *, servicio_id: uuid.UUID, tipo_servicio: str, nombre: str,
         categoria_default_id: uuid.UUID | None, propiedad_id: uuid.UUID | None, desde: dt.date | None,
         notas: str | None, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """Composicion: entidades (SERVICIO) -> servicios -> propiedad_servicios -> auditoria. No crea reglas."""
    visible = _nombre(nombre)
    if isinstance(visible, Rechazo):
        return visible
    if tipo_servicio not in m.TIPOS_SERVICIO or (notas is not None and not notas.strip()):
        return Rechazo(e.ENTRADA_INVALIDA)
    contenido = {"tipo_servicio": tipo_servicio, "nombre": visible, "categoria_default_id": m.texto(categoria_default_id),
                 "propiedad_id": m.texto(propiedad_id), "desde": m.texto(desde), "notas": notas}
    bloquear_intencion_propiedad(sesion, servicio_id)                                       # 0P
    if propiedad_id is not None and repo_prop.bloquear(sesion, propiedad_id) is None:       # nivel 3
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    previo = replay(sesion, servicio_id, OP_ALTA, servicio_id, contenido)
    if previo is True:
        return _resultado(sesion, servicio_id, idempotente=True)
    if isinstance(previo, Rechazo):
        return previo
    if repo_prop.existe_entidad(sesion, servicio_id):
        return Rechazo(e.IDENTIDAD_REUTILIZADA)
    if propiedad_id is not None:
        if desde is None:
            return Rechazo(e.FECHA_INICIO_REQUERIDA)                                        # `desde` obligatoria con propiedad
        ficha = repo_prop.leer(sesion, propiedad_id)
        assert ficha is not None
        if ficha["fecha_salida_patrimonio"] is not None and ficha["fecha_salida_patrimonio"] < desde:
            return Rechazo(e.PROPIEDAD_FUERA_DE_PATRIMONIO)
    if categoria_default_id is not None and not repo.categoria_admitida_para_gasto(sesion, categoria_default_id):
        return Rechazo(e.ENTRADA_INVALIDA)

    def escribir() -> None:
        repo.insertar_servicio(sesion, servicio_id=servicio_id, nombre=visible, tipo_servicio=tipo_servicio,
                               categoria_default_id=categoria_default_id, fecha_inicio=desde, notas=notas)
        if propiedad_id is not None:
            repo.insertar_vinculo_propiedad(sesion, fila_id=uuid.uuid5(servicio_id, "vinculo"), servicio_id=servicio_id,
                                  propiedad_id=propiedad_id, desde=desde, hasta=None)

    rechazo = ejecutar_escritura(sesion, escribir, triggers=TRIGGERS_SUBTIPO_SERVICIO)
    if rechazo is not None:
        return rechazo
    auditar(sesion, servicio_id, operacion=OP_ALTA, motivo=MOTIVOS[OP_ALTA], antes=None,
            despues=repo.snapshot_servicio(sesion, servicio_id), contenido=contenido, crear=True)
    return _resultado(sesion, servicio_id, modificadas=(servicio_id,))


# ------------------------------------------------------------------ C-SRV-02 editar
def editar(sesion: SesionMotor, *, servicio_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
           campos: dict[str, Any], reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """`campos` solo trae los presentes: nombre, categoria_default_id, notas. «Cambiar de compania» no es una
    escritura (la compania real vive en cada gasto)."""
    nuevos = dict(campos)
    if not nuevos or set(nuevos) - {"nombre", "categoria_default_id", "notas"}:
        return Rechazo(e.ENTRADA_INVALIDA)
    if "nombre" in nuevos:
        visible = _nombre(nuevos["nombre"])
        if isinstance(visible, Rechazo):
            return visible
        nuevos["nombre"] = visible
    if nuevos.get("notas") is not None and not nuevos["notas"].strip():
        return Rechazo(e.ENTRADA_INVALIDA)
    contenido = {"row_version_esperada": row_version, "campos": {k: m.texto(v) for k, v in sorted(nuevos.items())}}
    bloquear_intencion_propiedad(sesion, intencion_id)                                      # 0P
    s = repo.servicio(sesion, servicio_id, bloqueo="NK")                                    # nivel 7
    if s is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    previo = replay(sesion, intencion_id, OP_EDITAR, servicio_id, contenido)
    if previo is True:
        return _resultado(sesion, servicio_id, idempotente=True)
    if isinstance(previo, Rechazo):
        return previo
    if s["row_version"] != row_version:
        return Rechazo(e.VERSION_DESFASADA)
    if nuevos.get("categoria_default_id") is not None and not repo.categoria_admitida_para_gasto(
            sesion, nuevos["categoria_default_id"]):
        return Rechazo(e.ENTRADA_INVALIDA)
    cambios = {k: v for k, v in nuevos.items() if s[k] != v}
    if not cambios:
        return _resultado(sesion, servicio_id)
    antes = repo.snapshot_servicio(sesion, servicio_id)

    def escribir() -> None:
        repo.actualizar_servicio(sesion, servicio_id, cambios)
        repo.subir_version(sesion, servicio_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, servicio_id, operacion=OP_EDITAR, motivo=MOTIVOS[OP_EDITAR], antes=antes,
            despues=repo.snapshot_servicio(sesion, servicio_id), contenido=contenido)
    return _resultado(sesion, servicio_id, modificadas=(servicio_id,))


# ------------------------------------------------------------------ C-SRV-03 baja
def baja(sesion: SesionMotor, *, servicio_id: uuid.UUID, intencion_id: uuid.UUID, row_version: int,
         fecha_fin_real: dt.date, reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """Cierra con UPDATE las vigencias abiertas de `propiedad_servicios` y `contrato_servicios`; no borra pagos.
    Los contratos afectados suben su row_version (escritura en `contrato_servicios`). Su auditoria queda sellada en la
    del servicio (`contratos`)."""
    contenido = {"row_version_esperada": row_version, "fecha_fin_real": m.texto(fecha_fin_real)}
    bloquear_intencion_propiedad(sesion, intencion_id)                                      # 0P
    previo_s = repo.servicio(sesion, servicio_id)
    if previo_s is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    # propiedades vinculadas (lectura sin lock) -> NK por UUID ascendente; despues contratos NK; despues el servicio
    propiedades = sorted({v["propiedad_id"] for v in repo.vinculos_servicio(sesion, servicio_id)}, key=str)
    for pid in propiedades:
        repo_prop.bloquear(sesion, pid)                                                     # nivel 3
    abiertos = repo.tratamientos_abiertos_de_servicio(sesion, servicio_id)
    contratos = repo.bloquear_contratos(sesion, [t["contrato_id"] for t in abiertos])       # nivel 6
    s = repo.servicio(sesion, servicio_id, bloqueo="NK")                                    # nivel 7
    if s is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    previo = replay(sesion, intencion_id, OP_BAJA, servicio_id, contenido)
    if previo is True:
        return _resultado(sesion, servicio_id, idempotente=True)
    if isinstance(previo, Rechazo):
        return previo
    if s["row_version"] != row_version:
        return Rechazo(e.VERSION_DESFASADA)
    if s["fecha_fin_real"] is not None:
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    if repo.tiene_regla_financiera(sesion, servicio_id):                                    # AJ-DELTA-05
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": e.REGLA_SERVICIO_PENDIENTE})
    vinculos = [v for v in repo.vinculos_servicio(sesion, servicio_id) if v["vigente_hasta"] is None]
    abiertos = repo.tratamientos_abiertos_de_servicio(sesion, servicio_id)                 # relectura bajo los locks
    if (s["fecha_inicio"] is not None and fecha_fin_real < s["fecha_inicio"]) or any(
            x["vigente_desde"] > fecha_fin_real for x in vinculos + abiertos):
        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
    antes = repo.snapshot_servicio(sesion, servicio_id)
    afectados = sorted({t["contrato_id"] for t in abiertos}, key=str)

    def escribir() -> None:
        repo.cerrar_vigencia(sesion, "propiedad_servicios", [v["id"] for v in vinculos], fecha_fin_real)
        repo.cerrar_vigencia(sesion, "contrato_servicios", [t["id"] for t in abiertos], fecha_fin_real)
        repo.actualizar_servicio(sesion, servicio_id, {"fecha_fin_real": fecha_fin_real})
        repo.subir_version(sesion, servicio_id)
        for cid in afectados:
            repo.subir_version(sesion, cid)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, servicio_id, operacion=OP_BAJA, motivo=MOTIVOS[OP_BAJA], antes=antes,
            despues=repo.snapshot_servicio(sesion, servicio_id), contenido=contenido,
            extra={"contratos": [str(c) for c in afectados]})
    return _resultado(sesion, servicio_id, modificadas=(servicio_id, *afectados))


# ------------------------------------------------------------------ C-SRV-04 tratamiento en el contrato
def tratamiento(sesion: SesionMotor, *, contrato_id: uuid.UUID, servicio_id: uuid.UUID, intencion_id: uuid.UUID,
                row_version: int, modo: str, inquilino_tercero_id: uuid.UUID | None, porcentaje: Decimal | None,
                desde: dt.date | None, corregir: bool = False, motivo: str | None = None,
                reloj: Reloj = reloj_sistema) -> Resultado | Rechazo:
    """Cambio de tratamiento (cierra la fila abierta en `desde - 1` y crea otra desde `desde`) o, con `corregir`,
    errata sin cambio de vigencia (UPDATE auditado con motivo). SIN_INDICAR cierra la abierta y nunca borra."""
    contenido = {"row_version_esperada": row_version, "servicio_id": str(servicio_id), "modo": modo,
                 "inquilino_tercero_id": m.texto(inquilino_tercero_id), "porcentaje": m.texto(porcentaje),
                 "desde": m.texto(desde), "corregir": corregir, "motivo": motivo}
    if modo not in m.MODOS_TRATAMIENTO or (desde is None and not corregir):
        return Rechazo(e.ENTRADA_INVALIDA)
    abierto = abrir(sesion, contrato_id=contrato_id, intencion_id=intencion_id, operacion=OP_TRATAMIENTO,
                    contenido=contenido, row_version=row_version, reloj=reloj)
    if not isinstance(abierto, Abierto):
        return abierto
    c, hoy = abierto.c, abierto.hoy
    if c["estado_documental"] == "CANCELADO":
        return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
    if c["fecha_inicio"] is None:
        return Rechazo(e.FECHA_INICIO_REQUERIDA)
    s = repo.servicio(sesion, servicio_id, bloqueo="SHARE")                                 # nivel 7
    if s is None:
        return Rechazo(e.AGREGADO_NO_ENCONTRADO)
    filas = [t for t in repo.tratamientos(sesion, contrato_id) if t["servicio_id"] == servicio_id]
    actual = next((t for t in filas if t["vigente_hasta"] is None), None)
    if corregir:
        motivo_ok = exigir_motivo(motivo)
        if isinstance(motivo_ok, Rechazo):
            return motivo_ok
        if actual is None or modo == "SIN_INDICAR":
            return Rechazo(e.NO_PERMITIDA_EN_ESTADO)
        fecha = actual["vigente_desde"]
    else:
        motivo_ok = None
        fecha = desde
        if fecha < c["fecha_inicio"]:
            return Rechazo(e.FECHA_ANTERIOR_INICIO)
        if c["fecha_fin_real"] is not None and fecha > c["fecha_fin_real"]:
            return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)
        if actual is not None:
            if fecha == actual["vigente_desde"]:
                return Rechazo(e.DESDE_IGUAL_A_VERSION_ABIERTA)
            if fecha < actual["vigente_desde"]:
                return Rechazo(e.FECHA_ANTERIOR_INICIO)
    if modo != "SIN_INDICAR":
        if s["fecha_fin_real"] is not None and s["fecha_fin_real"] < fecha:
            return Rechazo(e.SERVICIO_DADO_DE_BAJA)
        if not repo.servicio_vinculado_en(sesion, servicio_id, c["propiedad_id"], fecha):
            return Rechazo(e.SERVICIO_NO_VINCULADO_A_PROPIEDAD)
    actor = None
    if modo in ("REPERCUTIDO_FIJO", "POR_FACTURA"):
        inquilino = next((p for p in repo.participantes(sesion, contrato_id)
                          if p["rol"] == "INQUILINO" and p["tercero_id"] is not None
                          and p["tercero_id"] == inquilino_tercero_id and p["vigente_desde"] <= fecha
                          and (p["vigente_hasta"] is None or p["vigente_hasta"] >= fecha)), None)
        if inquilino is None:
            return Rechazo(e.ACTOR_NO_ES_INQUILINO)
        actor = inquilino["actor_id"]
    columnas = None if modo == "SIN_INDICAR" else m.columnas_tratamiento(modo, actor, porcentaje)
    if isinstance(columnas, Rechazo):
        return columnas
    if modo == "SIN_INDICAR" and (actor is not None or porcentaje is not None or actual is None):
        return resultado_contrato(sesion, contrato_id, hoy) if actual is None else Rechazo(e.TRATAMIENTO_INCOMPATIBLE)
    antes = repo.snapshot_contrato(sesion, contrato_id)
    fila_id = uuid.uuid5(intencion_id, "tratamiento")

    def escribir() -> None:
        if corregir:
            repo.actualizar_tratamiento(sesion, actual["id"], columnas)
        else:
            if actual is not None:
                repo.cerrar_vigencia(sesion, "contrato_servicios", [actual["id"]], fecha - dt.timedelta(days=1))
            if columnas is not None:
                repo.insertar_tratamiento(sesion, fila_id=fila_id, contrato_id=contrato_id, servicio_id=servicio_id,
                                          columnas=columnas, desde=fecha, hasta=c["fecha_fin_real"])
        repo.subir_version(sesion, contrato_id)

    rechazo = ejecutar_escritura(sesion, escribir)
    if rechazo is not None:
        return rechazo
    auditar(sesion, contrato_id, operacion=OP_TRATAMIENTO, motivo=MOTIVOS[OP_TRATAMIENTO], antes=antes,
            despues=repo.snapshot_contrato(sesion, contrato_id), contenido=contenido, motivo_usuario=motivo_ok)
    return resultado_contrato(sesion, contrato_id, hoy, modificadas=(contrato_id,))
