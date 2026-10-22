# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_categoria_v3.py
# Ruta: backend/app/api/ejecucion_categoria_v3.py
# Descripcion: Adaptador de F05-06 M1 v1.1 · «Corregir categoria» de un
#   registro migrado de V3 (Q9 opcion (a); STOP_M5BM1_Q9; F05-D047 §61.3
#   limitado a la categoria). API DE INTEGRACION F05, PENDIENTE DE
#   CONSOLIDACION F10.
#
#   OP-21 (CorreccionesService.corregir) con LISTA BLANCA {categoria_id}
#   (CAMPOS_V3_CORREGIBLES): el unico cambio que llega al motor es la
#   categoria del UNICO efecto del hecho. Importe, fecha, cuenta, pagador,
#   descripcion, concepto, notas, tipo, atribucion o efectos: el DTO los
#   rechaza (extra="forbid", 422) y aqui no hay forma de pasarlos. Sin cambios
#   en el motor. La descripcion o nota de V3 NO se corrige: deuda
#   DEU-M1-V3-NOTA (F06, OP-02 sobre `notas`).
#
#   UNA transaccion (UnidadDeTrabajo, retry completo ante 40P01/40001):
#     1. forma, sin lock: actividad/edicion.motivo_categoria_v3 (la misma
#        regla que la lectura): importado, ACTIVO, GASTO/INGRESO, un efecto;
#     2. identidad: la auditoria de este request_id (= intencion_id). La misma
#        intencion ya aplicada -> idempotente sin escribir; otra ->
#        IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION. Solo una intencion nueva
#        pasa a 3;
#     3. categoria validada en el servidor: guarda C-a (FOR SHARE de la
#        categoria; naturaleza del efecto) y C07 con las magnitudes YA
#        registradas en el hecho (FOR SHARE de las asociaciones; la
#        correccion no captura magnitudes: una categoria con una obligatoria
#        que el hecho no tiene, o que no admite las que tiene, se rechaza);
#     4. OP-21: root lock del hecho, version esperada (VERSION_DESFASADA),
#        estado final, motivo obligatorio (MOTIVO_AUSENTE) y auditoria con el
#        motivo. Un UPDATE de categoria_id no toca movimientos, importes ni
#        fechas.
#   Orden de locks: categoria FS -> C07 FS -> hecho -> posiciones (el mismo
#   del registro y de M3: categoria antes que hecho). Sin advisory: no toca
#   importe ni tipo ni hecho_entidades.
#   Frontera I3 (test_154): excepcion NOMINAL y acotada a este fichero; solo
#   CorreccionesService.corregir, con DatosCorreccion de hecho_id,
#   row_version_esperada, motivo y efectos_a_actualizar de {categoria_id}.
# Version: 0.1.0 (F05-06 M1 v1.1)
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.actividad import edicion as lect_edi
from app.api.dto_edicion import IntencionCorregirCategoriaV3
from app.api.ejecucion_registro import RechazoRegistro, validar_categoria_y_magnitudes
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import correccion_tesoreria_repository as repo
from app.services.correcciones_service import CorreccionesService, DatosCorreccion

#: Lista blanca de lo que esta via puede cambiar en el efecto (Q9 opcion (a)).
CAMPOS_V3_CORREGIBLES = frozenset({"categoria_id"})

CATEGORIA_V3_NO_CORREGIBLE = "CATEGORIA_V3_NO_CORREGIBLE"
HECHO_NO_ENCONTRADO = "HECHO_NO_ENCONTRADO"
TABLA_EFECTOS = "hecho_efectos"


@dataclass(frozen=True, slots=True)
class CategoriaCorregida:
    hecho_id: uuid.UUID
    hecho_row_version: int
    idempotente: bool


@dataclass(frozen=True, slots=True)
class _Magnitud:
    magnitud_id: uuid.UUID
    valor: str


def _magnitudes(sesion: SesionMotor, hecho_id: uuid.UUID) -> list[_Magnitud]:
    """Magnitudes ya registradas en el hecho (C07 las juzga contra la categoria nueva)."""
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT magnitud_id, valor FROM gapto.hecho_magnitudes WHERE hecho_id = %s ORDER BY magnitud_id",
                    (hecho_id,))
        return [_Magnitud(f[0], str(f[1])) for f in cur.fetchall()]


def _version(sesion: SesionMotor, hecho_id: uuid.UUID) -> int:
    return sesion.uno("SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))[0]


def _identidad(sesion: SesionMotor, contexto: ContextoOperacion, hecho_id: uuid.UUID, efecto_id: uuid.UUID,
               intencion: IntencionCorregirCategoriaV3) -> CategoriaCorregida | None:
    """None si el request_id es nuevo; la misma intencion ya aplicada -> idempotente."""
    auditadas = repo.auditorias_de_peticion(sesion, contexto.request_id)
    if not auditadas:
        return None
    propias = all(a["registro_id"] in (hecho_id, efecto_id) and a["accion"] == auditoria.ACCION_ACTUALIZAR
                  and a["motivo"] == intencion.motivo for a in auditadas)
    efecto = [a for a in auditadas if a["tabla"] == TABLA_EFECTOS]
    if propias and len(efecto) == 1 and efecto[0]["despues"].get("categoria_id") == str(intencion.categoria_id):
        return CategoriaCorregida(hecho_id=hecho_id, hecho_row_version=_version(sesion, hecho_id), idempotente=True)
    raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                     "Ese request_id ya se uso con otra intencion: no se repite ni se completa.")


def _cambios(intencion: IntencionCorregirCategoriaV3) -> dict[str, Any]:
    cambios = {"categoria_id": intencion.categoria_id}
    if not set(cambios) <= CAMPOS_V3_CORREGIBLES:
        raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "Fuera de la lista blanca de V3.")
    return cambios


def corregir_categoria_v3(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, hecho_id: uuid.UUID,
                          intencion: IntencionCorregirCategoriaV3) -> CategoriaCorregida | RechazoRegistro:
    def operacion(sesion: SesionMotor) -> CategoriaCorregida | RechazoRegistro:
        motivo, efecto = lect_edi.motivo_categoria_v3(sesion, hecho_id)
        if motivo == "NO_ENCONTRADO":
            return RechazoRegistro(HECHO_NO_ENCONTRADO)
        if motivo is not None:
            return RechazoRegistro(CATEGORIA_V3_NO_CORREGIBLE, {"motivo": motivo})
        ya = _identidad(sesion, contexto, hecho_id, efecto["id"], intencion)
        if ya is not None:
            return ya
        rechazo = validar_categoria_y_magnitudes(sesion, intencion.categoria_id, efecto["naturaleza"],
                                                 _magnitudes(sesion, hecho_id), ())
        if rechazo is not None:
            return RechazoRegistro(rechazo)
        datos = DatosCorreccion(hecho_id=hecho_id, row_version_esperada=intencion.row_version,
                                motivo=intencion.motivo, efectos_a_actualizar={efecto["id"]: _cambios(intencion)})
        resultado = CorreccionesService(UnidadDeTrabajoAdscrita(sesion)).corregir(contexto, datos)
        return CategoriaCorregida(hecho_id=hecho_id, hecho_row_version=resultado.hecho_row_version, idempotente=False)

    return unidad.ejecutar(contexto, operacion, nombre="F05-06 M1 corregir_categoria_v3 (OP-21 lista blanca)")
