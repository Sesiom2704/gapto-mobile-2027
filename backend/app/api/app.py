# ============================================================
# GAPTO MOBILE 2027
# Fichero: app.py
# Ruta: backend/app/api/app.py
# Descripcion: Adaptador HTTP FastAPI del vertical slice VS-01.
#   API DE INTEGRACION F05-00-B, PENDIENTE DE CONSOLIDACION F10.
#   *** IDENTIDAD DE DESARROLLO: NO ES AUTENTICACION DE PRODUCCION (F10-01) ***
#
#   Rutas:
#     POST /v1/intenciones/gasto-pagado  -> OP-22 (unica escritura)
#     GET  /v1/vs01/cuentas-pago?fecha=   -> cuentas elegibles + propuesta de financiacion
#     GET  /v1/vs01/gasto-mes?mes=        -> lectura estrecha VS-01 (candidata F08)
#     GET  /v1/categorias                 -> arbol del owner (F05-01, S3)
#     GET  /v1/categorias/{id}/uso        -> uso historico por naturaleza (C06)
#     GET  /v1/salud                      -> diagnostico de desarrollo
#   Todas exigen `Authorization: Bearer <GAPTO_DEV_TOKEN>`.
#
#   Arranque: `create_app()` falla (fail-closed) si la configuracion no es de
#   desarrollo o si la base conectada no esta en la lista blanca.
#   Ejecucion: uvicorn "app.api.app:create_app_desde_entorno" --factory --host 127.0.0.1
#
#   v0.2.0 (F05-D003): la escritura se ejecuta en UNA transaccion del
#   adaptador (lock de cuenta -> identidad -> revalidacion -> OP-22 adscrito,
#   ejecucion_gasto_pagado.py); cuentas-pago recibe la fecha del pago.
#
#   v0.3.0 (F05-01, F05-D009): la intencion admite la dimension categorial
#   (CATEGORIA / SIN_CATEGORIA; la ausencia derivaba entonces un estado de
#   compatibilidad, retirado en v0.7.0) y la respuesta informa
#   `estado_categorial`. Lecturas del arbol de categorias.
#
#   v0.4.0 (F05-01, S4): comandos de gestion del arbol (C06), uno por ruta,
#   cada uno en una transaccion de la unidad de trabajo. Sin DELETE ni
#   escritura de icon_key.
#
#   v0.5.0 (F05-01 S6-ICONO (F05-D013)): POST /v1/categorias/{id}/icono
#   (cambiar_icono) y `icon_key` opcional en el alta. Sin DELETE; sin
#   lectura de la biblioteca de iconos (queda para el mandato de UI).
#
#   v0.6.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): POST /v1/categorias/reordenar
#   (reordenar hermanos, atomico, una transaccion de la UdT). El comando por
#   nodo POST /v1/categorias/{id}/orden (S4) se CONSERVA sin cambios; la
#   prohibicion de §26.3 (reordenar con N llamadas por nodo) rige para la UI,
#   que solo usara /reordenar (D-ORD-08).
#
#   v0.7.0 (F05-01 S6-WIRE+UI (este mandato); F05 §26.2 AJ-03): la intencion
#   exige `categoria` (ausente o null -> 422); `estado_categorial` es siempre
#   CATEGORIA o SIN_CATEGORIA. Sin rutas nuevas.
#
#   v0.8.0 (F05-01 S7-MAG (F05-D020 D-MAG-04), commit 1): GET /v1/categorias
#   responde con ArbolCategoriasMagnitudes (dto_magnitudes.py): cada magnitud
#   asociada anade `asociacion_id`. Campo aditivo; sin rutas nuevas.
#
#   v0.9.0 (F05-01 S7-MAG (F05-D020), commit 2): rutas de magnitudes, cada
#   comando en UNA transaccion de la unidad de trabajo (magnitudes/servicio.py):
#     POST /v1/categorias/{id}/magnitudes                       asociar (EXISTENTE | NUEVA)
#     POST /v1/categorias/{id}/magnitudes/{asociacion}/obligatoria
#     POST /v1/categorias/{id}/magnitudes/{asociacion}/retirar
#     POST /v1/categorias/{id}/magnitudes/reordenar
#     POST /v1/magnitudes/{id}/renombrar | deshabilitar | rehabilitar
#     GET  /v1/magnitudes                                       catalogo del owner
#   Sin DELETE HTTP: retirar una asociacion es un POST por accion. Sin cambio
#   de unidad ni precision (R17).
#
#   v0.10.0 (F05-02 B1, F05-D026 §41.3): rutas /v1 internas y provisionales
#   de preferencias de registro, cada comando en UNA transaccion de la unidad
#   de trabajo (preferencias/servicio.py):
#     GET  /v1/preferencias                       lista + cuenta_disponible_hoy
#     POST /v1/preferencias                       alta
#     POST /v1/preferencias/{id}/editar | desactivar | reactivar
#     GET  /v1/preferencias/propuesta?categoria_id=&fecha=   resolver (lectura)
#   No se conectan a REG-01, a la ejecucion del gasto ni al cliente (B2).
#
#   v0.11.0 (F05-02 B2; F05 §42.7): GET /v1/preferencias/propuesta con una
#   categoria_id no elegible para GASTO responde 409 CATEGORIA_NO_ELEGIBLE
#   (mismo codigo y cuerpo que el rechazo de la intencion) y nunca una
#   propuesta. La ejecucion del gasto y su traductor no cambian.
#
#   v0.11.1 (F05-02 B3, AJ-B2-05): ese 409 de la propuesta (una LECTURA)
#   conserva codigo y status, pero lleva un mensaje propio de lectura
#   (MENSAJE_PROPUESTA_NO_ELEGIBLE), sin «no se ha guardado nada». El mensaje
#   del rechazo de la intencion no cambia.
#
#   v0.12.0 (F05-03/F05-04 J2 §1.5; F05 §46.4 R6, §46.5 E2/E3):
#     GET /v1/preferencias/propuesta admite `tipo` (GASTO por defecto |
#       INGRESO) y `tercero_id` (dimension operativa, E2); la guarda C-a se
#       evalua con ese tipo;
#     GET /v1/preferencias anade `tipos` (ids de GASTO e INGRESO, campo
#       aditivo) para que el cliente envie siempre el tipo (E3: no hay
#       preferencia sin tipo).
#
#   v0.13.0 (F05-03/F05-04 J2 §1.1/§1.9; F05 §46.4 R1; F05-D032 C1):
#     GET /v1/cuentas/elegibles?operacion=&fecha= -> cuentas elegibles por
#       operacion (GASTO | INGRESO | TRANSFERENCIA_ORIGEN |
#       TRANSFERENCIA_DESTINO) y fecha, con la regla unica de
#       comun/elegibilidad_cuentas.py. /v1/vs01/cuentas-pago usa la misma
#       regla (GASTO).
#
#   v0.14.0 (F05-03/F05-04 J2 §1.2; F05-D032 C6): `create_app(reloj=...)`
#   inyecta el reloj de la fecha funcional del owner (por defecto, el del
#   sistema en UTC) en el registro (FECHA_FUTURA) y en los writers y la lista
#   de preferencias (elegibilidad de cuenta «hoy»).
#
#   v0.15.0 (F05-03/F05-04 J2 §1.3/§1.4/§1.9): rutas /v1 internas de los
#   maestros del registro, cada comando en UNA transaccion de la UdT:
#     GET  /v1/terceros                 lista (activos e inactivos, `usos`)
#     GET  /v1/terceros/candidatos?nombre=   posibles duplicados (C06)
#     POST /v1/terceros                 alta (UUID de cliente)
#     POST /v1/terceros/{id}/editar | desactivar | reactivar
#     GET  /v1/contextos                lista
#     POST /v1/contextos                alta (UUID de cliente)
#     POST /v1/contextos/{id}/editar | desactivar | reactivar
#
#   v0.16.0 (F05-03/F05-04 J2 §1.6/§1.9): plantillas, acciones rapidas y
#   propuesta del registro con la capa plantilla:
#     GET  /v1/plantillas                       plantillas (con avisos) + acciones
#     POST /v1/plantillas                       alta (tambien «Guardar como plantilla»)
#     POST /v1/plantillas/{id}/editar | desactivar | reactivar
#     POST /v1/acciones-rapidas                 alta
#     POST /v1/acciones-rapidas/reordenar       conjunto completo, atomico
#     POST /v1/acciones-rapidas/{id}/editar | desactivar
#     GET  /v1/registro/propuesta?tipo=&fecha=&plantilla_id=&categoria_id=
#          &sin_categoria=&tercero_id=&sin_tercero=   (lectura, sin advisory)
#
#   v0.17.0 (F05-03/F05-04 J2 §1.7): escrituras del registro por tipo, cada
#   una en UNA transaccion del adaptador (ejecucion_registro.py):
#     POST /v1/intenciones/ingreso-cobrado  -> C-14 via OP-22
#     POST /v1/intenciones/transferencia    -> OP-10 (guarda de replay propia)
#   El gasto sigue en /v1/intenciones/gasto-pagado (tercero, contexto y «No
#   lo sé» aditivos).
#
#   v0.18.0 (F05-03 J2 §1.8; F05 §45.4 R5): onboarding de categorias:
#     GET  /v1/categorias/sugeridas   arbol del fichero versionado (O02)
#     POST /v1/categorias/onboarding  crea el arbol si el owner tiene cero
#                                     categorias (ONBOARDING_NO_APLICABLE si no;
#                                     idempotente con el arbol exacto)
#
#   v0.19.0 (F05-05 K2 §1.2-§1.4; F05 §49.4 A1-A5, §49.5 R1-R10):
#     GET  /v1/senales/categorias?tipo=&tercero_id=&fecha=   senales (lectura)
#     GET  /v1/senales/terceros?tipo=&fecha=                 «Recientes» (lectura)
#          (nunca «sugeridas»: ya existe para el onboarding)
#     POST /v1/afinidades                      alta (UUID del cliente idempotente)
#     POST /v1/afinidades/{id}/retirar         baja (idempotente)
#     GET  /v1/terceros/{id}/afinidades?tipo=&fecha=  guardadas + segun historial
#     GET  /v1/terceros?q=&incluir_inactivos=  busqueda ILIKE en servidor; sin `q`,
#          la lista completa de siempre (activos e inactivos)
#   Fecha funcional obligatoria en las senales (C6); FECHA_FUTURA si procede.
#   v0.20.0 (F05-05 K2 §1.5; F05 §49.4 A7): Actividad v0, solo lectura:
#     GET  /v1/actividad?desde=&hasta=&tipo=&categoria_id=&incluir_subcategorias=
#          &cuenta_id=&tercero_id=&contexto_id=&q=&importe=&cursor=&limite=
#          (periodo [desde, hasta); sin periodo, todo el historial; keyset
#          (fecha_hecho DESC, id ASC) con cursor opaco; `total` con los filtros)
#     GET  /v1/actividad/{id}   detalle rapido (sin posiciones ni acciones)
#   v0.21.0 (F05-05 K2 §1.6; F05 §49.4 A9, D13): read models de Inicio:
#     GET  /v1/yo                         nombre del owner (identidad de desarrollo)
#     GET  /v1/inicio/resultado-mes?fecha= Resultado del mes (contrato de A9)
#   v0.22.0 (F05-06 M4 §2.2-§2.4; F09 §12.105 CAP): capacidades de cuenta
#   (Ajustes › Preferencias financieras › Cuentas, entrada provisional):
#     GET  /v1/cuentas/capacidades                 lista (A1) + numero sin configurar
#     GET  /v1/cuentas/sin-configurar              numero sin configurar (aviso B2)
#     GET  /v1/cuentas/{id}/capacidades            detalle (A2/B1)
#     GET  /v1/cuentas/{id}/capacidades/historial  historial de auditoria (B4)
#     GET  /v1/cuentas/{id}/capacidades/{capacidad}/impacto  plantillas y
#          preferencias que pasarian a «No disponible» (A4)
#     POST /v1/cuentas/{id}/capacidades/{capacidad}/activar | desactivar
#          {row_version} (writer unico, capacidades/servicio.py)
#   El registro responde CUENTA_SIN_CAPACIDAD (409, con detalle) cuando la
#   cuenta perdio la capacidad (D-CAP-08); los rechazos de capa F05 llevan
#   su detalle si lo tienen.
#   v0.23.0 (F05-06 M2 §A2-§A4; F05 §14, §51.2; lamina DEV v0.1):
#   devolucion contextual D-194 (ejecucion_devolucion.py):
#     GET  /v1/hechos/{origen_id}/devoluciones   contexto del formulario
#          (origen, lo devuelto, lo que queda, propuestas P-DEV-01/02)
#     POST /v1/hechos/{origen_id}/devoluciones   OP-13 + OP-05 [+ OP-08 +
#          OP-09 con «Ya cobrado»] en una transaccion
#     POST /v1/hechos/{devolucion_id}/abono      «Registrar abono»: OP-08 +
#          OP-09 sobre una devolucion pendiente
#   La Actividad y su detalle ganan campos aditivos (devolucion_de, abono,
#   devoluciones).
#   v0.24.0 (F05-06 M3 §A2-§A5; F05 §51.2, §57 F05-D043; lamina REP v0.2):
#   reparto, pagador real y posiciones (ejecucion_reparto.py):
#     POST /v1/intenciones/gasto-compartido      OP-22 de una sola llamada
#          (reparto, pagador real, aportaciones y posiciones explicitas)
#     POST /v1/posiciones/{entidad_id}/cobro      OP-14 con cuenta Gapto
#     POST /v1/posiciones/{entidad_id}/pago       OP-12B con cuenta Gapto
#     POST /v1/posiciones/{entidad_id}/perdon     condonacion (sin dinero)
#     GET  /v1/terceros/{tercero_id}/pendiente    «Pendiente con» (OP-20)
#     GET  /v1/hechos/{hecho_id}/reparto          lectura sin locks del reparto
#     POST /v1/hechos/{hecho_id}/reparto          «Corregir reparto» (OP-21
#          con whitelist; REPARTO_CAMBIA_POSICIONES con su motivo)
#     GET  /v1/hechos/{hecho_id}/anulacion        elegibilidad de OP-03 (iii)
# Version: 0.24.0
#   v0.25.0 (F05-06 M5 §A5; F05 §59 F05-D044 decision 14; D-M5-15; laminas
#   PREV v0.2 y HOME-01 v0.4): confirmacion de previsiones
#   (previsiones/lecturas.py y ejecucion_prevision.py):
#     GET  /v1/inicio/previsiones                 recuento comun, dos primeras
#          de «Requiere atencion» y tres proximos (sin importes sumados)
#     GET  /v1/previsiones/pendientes             lista «Pendientes» con «Por
#          pagar» y «Por cobrar» separados
#     GET  /v1/previsiones/{id}                   detalle en cualquier estado
#     GET  /v1/previsiones/{id}/candidatos        «Ya lo registre» (?ampliado)
#     POST /v1/previsiones/{id}/vincular          OP-17 suelto
#     POST /v1/previsiones/{id}/omitir            «No hubo este mes»
#   y el bloque opcional `prevision` en gasto-pagado, ingreso-cobrado,
#   transferencia (OP-10 + OP-17, opcion A) y gasto-compartido. Ninguna ruta
#   crea, cancela, corrige, retira ni recalcula previsiones. Los errores de
#   prevision de esas rutas usan errores_http.rechazo_prevision.
# Version: 0.25.0
#   v0.26.0 (F05-06 M5-B; F05-D047 §61.1; F04-D065): dos rutas nuevas en
#   ejecucion_prevision.py, sin swipe:
#     POST /v1/previsiones/{id}/dar-por-realizada «Dar por cubierta»
#          (dar_por_realizada; PREVISION_SIN_REALIDAD_ACTIVA 409)
#     POST /v1/previsiones/{id}/reabrir           «Reabrir» REALIZADA u OMITIDA
#          (corregir_estado_terminal; CANCELADA rechazada en el adaptador;
#          TRAMO_RODANTE_REQUIERE_REVISION 409 sin reintento automatico)
#   Los 409 de estado o version devuelven el estado releido (como omitir).
# Version: 0.26.0
#   v0.27.0 (F05-06 M1; F05 §61.2 F05-D047; CONTRATO_M1 v0.1 §1; lamina
#   EDIT-HECHO v0.1): corregir y anular desde la app, sin cambiar el motor:
#     GET  /v1/hechos/{id}/edicion           elegibilidad visible (sin locks;
#          informativa), versiones del hecho y de cada movimiento y ANULADO
#          con su motivo (el hecho no desaparece)
#     POST /v1/hechos/{id}/corregir-pago     OP-21P (ejecucion_correccion)
#     POST /v1/transferencias/{id}/corregir  OP-21T (ejecucion_correccion)
#     POST /v1/hechos/{id}/anular-duplicado  OP-03P con declaracion explicita
#          (ejecucion_anulacion)
#   Cada POST revalida en el motor bajo sus locks (AJ-M5BM1-06). La
#   intencion_id es el request_id (reintento idempotente). Rechazos con
#   errores_http.rechazo_edicion; VERSION_DESFASADA 409 con la edicion releida.
# Version: 0.27.0
#   v0.28.0 (F05-06 M1 v1.1; Q9 opcion (a); F05-D047 §61.3 limitado a la
#   categoria): POST /v1/hechos/{id}/corregir-categoria «Corregir categoria»
#   de un registro de V3 (ejecucion_categoria_v3: OP-21 con lista blanca
#   {categoria_id}, C-a y C07 en el servidor). Misma envoltura que M1
#   (_escritura_edicion): request_id = intencion_id, rechazos del motor con
#   rechazo_edicion y VERSION_DESFASADA 409 con la edicion releida. La
#   lectura /edicion trae `acciones.corregir_categoria` solo en V3.
# Version: 0.28.0
# ============================================================

from __future__ import annotations

import datetime as dt
import hmac
import logging
import re
import uuid
from contextlib import contextmanager
from typing import Callable, Iterator, Literal

import psycopg
from fastapi import Body, Depends, FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import errores_http as eh
from app.api import lecturas_vs01 as lect
from app.api.configuracion import (
    AVISO_IDENTIDAD,
    ConfiguracionApi,
    cargar_desde_entorno,
    verificar_base_permitida,
)
from app.api.dto_capacidades import (
    CambioCapacidad,
    CuentaCapacidades,
    HistorialCapacidades,
    ImpactoDesactivar,
    ListaCuentasCapacidades,
    ResultadoComandoCapacidad,
    SinConfigurar,
)
from app.api.dto_categorias import (
    AltaCategoria,
    AmbitoCambio,
    CategoriaNodo,
    CategoriasSugeridas,
    DesactivarCategoria,
    IconoCategoria,
    MoverCategoria,
    OrdenCategoria,
    ReactivarCategoria,
    RenombrarCategoria,
    ReordenarHermanos,
    ResultadoComandoCategoria,
    ResultadoOnboarding,
    ResultadoReordenar,
    UsoCategoria,
)
from app.api.dto_magnitudes import (
    ArbolCategoriasMagnitudes,
    AsociarMagnitud,
    AsociarNueva,
    CatalogoMagnitudes,
    DeshabilitarMagnitud,
    ObligatoriaAsociacion,
    RehabilitarMagnitud,
    RenombrarMagnitud,
    ReordenarMagnitudes,
    ResultadoAsociacionesMagnitud,
    ResultadoAsociacionMagnitud,
    ResultadoComandoMagnitud,
    RetirarAsociacion,
)
from app.api.dto_maestros import (
    AltaContexto,
    AltaTercero,
    EditarContexto,
    EditarTercero,
    EstadoContexto,
    EstadoTercero,
    ListaContextos,
    ListaTerceros,
    ResultadoComandoContexto,
    ResultadoComandoTercero,
)
from app.api.dto_plantillas import (
    AltaAccion,
    AltaPlantilla,
    EditarAccion,
    EditarPlantilla,
    EstadoAccion,
    EstadoPlantilla,
    ListaPlantillas,
    PropuestaRegistroTipo,
    ReordenarAcciones,
    ResultadoComandoAccion,
    ResultadoComandoPlantilla,
    ResultadoReordenarAcciones,
)
from app.api.dto_preferencias import (
    AltaPreferencia,
    DesactivarPreferencia,
    EditarPreferencia,
    ListaPreferencias,
    PreferenciaNodo,
    PropuestaRegistro,
    ReactivarPreferencia,
    ResultadoComandoPreferencia,
)
from app.api.dto_f05_05 import (
    AltaAfinidad,
    DetalleActividad,
    DetalleAfinidades,
    PaginaActividad,
    ResultadoMes,
    ResultadoComandoAfinidad,
    SenalesCategorias,
    SenalesTerceros,
    Yo,
)
from app.api.dto_vs01 import (
    GastoMesVs01,
    IntencionGastoPagado,
    ListaCuentasElegibles,
    ListaCuentasPago,
    ResultadoGastoPagado,
)
from app.api.dto_registro import IntencionIngresoCobrado, IntencionTransferencia, ResultadoRegistro
from app.api.ejecucion_gasto_pagado import RechazoIntegracion, registrar_gasto_pagado
from app.api.ejecucion_registro import RechazoRegistro, registrar_ingreso_cobrado, registrar_transferencia
from app.api.dto_devolucion import (
    ContextoDevolucion,
    IntencionAbono,
    IntencionDevolucion,
    ResultadoAbonoHttp,
    ResultadoDevolucionHttp,
)
from app.api.ejecucion_devolucion import contexto_devolucion, registrar_abono, registrar_devolucion
from app.api.dto_reparto import (
    ElegibilidadAnulacion,
    IntencionCobroPago,
    IntencionCorregirReparto,
    IntencionGastoCompartido,
    IntencionPerdon,
    PendienteConPersona,
    RepartoDeHecho,
    ResultadoCorreccionRepartoHttp,
    ResultadoGastoCompartidoHttp,
    ResultadoPosicionHttp,
)
from app.api import ejecucion_reparto as rep
from app.api import ejecucion_prevision as ejp
from app.api import ejecucion_anulacion as eja
from app.api import ejecucion_correccion as ejc
from app.api import ejecucion_categoria_v3 as ejv3
from app.api.dto_edicion import (
    EdicionHecho,
    IntencionAnularDuplicado,
    IntencionCorregirCategoriaV3,
    IntencionCorregirPago,
    IntencionCorregirTransferencia,
    ResultadoEdicion,
)
from app.actividad import edicion as lect_edi
from app.api.dto_prevision import (
    CandidatosPrevision,
    DetallePrevision,
    InicioPrevisiones,
    IntencionDarPorCubierta,
    IntencionOmitir,
    IntencionReabrir,
    IntencionVincular,
    PendientesPrevisiones,
    ResultadoOmitir,
    ResultadoTransicion,
    ResultadoVinculo,
)
from app.previsiones import lecturas as lect_prev
from app.actividad import lecturas as lect_act
from app.afinidades import lecturas as lect_afi
from app.afinidades import servicio as serv_afi
from app.capacidades import lecturas as lect_cap
from app.capacidades import servicio as serv_cap
from app.categorias import lecturas as lect_cat
from app.categorias import onboarding as onb
from app.inicio import lecturas as lect_ini
from app.contextos import lecturas as lect_ctx
from app.plantillas import lecturas as lect_plt
from app.plantillas import propuesta as prop_plt
from app.plantillas import servicio as serv_plt
from app.contextos import servicio as serv_ctx
from app.terceros import lecturas as lect_ter
from app.terceros import servicio as serv_ter
from app.comun import elegibilidad_cuentas as eleg
from app.comun.fecha_funcional import Reloj, es_futura, hoy_owner, reloj_sistema
from app.categorias import servicio as serv_cat
from app.magnitudes import lecturas as lect_mag
from app.magnitudes import servicio as serv_mag
from app.preferencias import lecturas as lect_pref
from app.preferencias import servicio as serv_pref
from app.senales import lecturas as senales
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import UnidadDeTrabajo

_LOG = logging.getLogger("gapto.api.f05_00_b")
import decimal
_CENT = decimal.Decimal("0.01")
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

#: AJ-B2-05: mensaje de CATEGORIA_NO_ELEGIBLE en la propuesta (lectura: no hay nada que guardar).
MENSAJE_PROPUESTA_NO_ELEGIBLE = "Esa categoría no se puede elegir para registrar un gasto. Elige otra o «Sin categoría»."
MENSAJE_PROPUESTA_NO_ELEGIBLE_INGRESO = (
    "Esa categoría no se puede elegir para registrar un ingreso. Elige otra o «Sin categoría».")


class _NoAutorizado(Exception):
    pass


def _proveedor_por_defecto(dsn: str) -> Callable[[], object]:
    @contextmanager
    def _abrir() -> Iterator[psycopg.Connection]:
        with psycopg.connect(dsn, connect_timeout=5) as conexion:
            yield conexion

    return _abrir


def create_app(
    cfg: ConfiguracionApi | None = None,
    *,
    proveedor_conexion: Callable[[], object] | None = None,
    origenes_cors: tuple[str, ...] = (),
    reloj: Reloj = reloj_sistema,
) -> FastAPI:
    cfg = cfg or cargar_desde_entorno()
    proveedor = proveedor_conexion or _proveedor_por_defecto(cfg.dsn)

    # Fail-closed: la base real conectada debe ser de desarrollo.
    with proveedor() as conexion:
        nombre = conexion.execute("SELECT current_database()").fetchone()[0]
    verificar_base_permitida(nombre, cfg)

    unidad = UnidadDeTrabajo(proveedor, rol_runtime=cfg.rol_runtime)
    app = FastAPI(
        title="GaptoMobile 2027 — API de integracion F05-00-B",
        description=f"Pendiente de consolidacion F10. {AVISO_IDENTIDAD}.",
        version="0.1.0",
    )
    if origenes_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origenes_cors),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    def contexto() -> ContextoOperacion:
        # El owner NO procede de la peticion: es configuracion del servidor.
        return ContextoOperacion.de_usuario(cfg.owner_user_id, request_id=uuid.uuid4())

    def autorizar(request: Request) -> None:
        cabecera = request.headers.get("authorization", "")
        esperado = f"Bearer {cfg.token_desarrollo}"
        if not hmac.compare_digest(cabecera.encode(), esperado.encode()):
            raise _NoAutorizado()

    @app.exception_handler(_NoAutorizado)
    def _h_auth(_: Request, __: _NoAutorizado) -> JSONResponse:
        status, cuerpo = eh.no_autorizado()
        return JSONResponse(cuerpo, status_code=status)

    @app.exception_handler(ErrorMotor)
    def _h_motor(_: Request, exc: ErrorMotor) -> JSONResponse:
        _LOG.warning("error de motor", extra=exc.diagnostico_interno())
        status, cuerpo = eh.traducir_error_motor(exc.codigo)
        return JSONResponse(cuerpo, status_code=status)

    @app.exception_handler(psycopg.OperationalError)
    def _h_bd(_: Request, exc: psycopg.OperationalError) -> JSONResponse:
        _LOG.warning("BD no disponible: %s", type(exc).__name__)
        status, cuerpo = eh.backend_no_disponible()
        return JSONResponse(cuerpo, status_code=status)

    @app.exception_handler(RequestValidationError)
    def _h_validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        campos = sorted({".".join(str(p) for p in e.get("loc", ())[1:]) for e in exc.errors()})
        return JSONResponse(
            {
                "codigo": "ENTRADA_INVALIDA",
                "mensaje": "Revisa los datos: " + ", ".join(c for c in campos if c),
                "reintentable": False,
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    def _h_interno(_: Request, exc: Exception) -> JSONResponse:
        _LOG.error("error no clasificado: %s", type(exc).__name__)
        status, cuerpo = eh.interno()
        return JSONResponse(cuerpo, status_code=status)

    @app.get("/v1/salud", dependencies=[Depends(autorizar)])
    def salud() -> dict:
        return {"estado": "OK", "entorno": cfg.entorno, "aviso": AVISO_IDENTIDAD, "base": nombre}

    @app.get("/v1/vs01/cuentas-pago", response_model=ListaCuentasPago, dependencies=[Depends(autorizar)])
    def cuentas_pago(fecha: dt.date = Query(...)) -> dict:
        # `fecha` es la fecha comun de gasto y pago elegida en el formulario:
        # la propuesta de financiacion se evalua en esa fecha (§16.4).
        filas = unidad.ejecutar(contexto(), lambda s: lect.cuentas_pago(s, fecha), nombre="VS01 cuentas_pago")
        return {"cuentas": filas}

    @app.get("/v1/cuentas/elegibles", response_model=ListaCuentasElegibles, dependencies=[Depends(autorizar)])
    def cuentas_elegibles_operacion(
        operacion: Literal["GASTO", "INGRESO", "TRANSFERENCIA_ORIGEN", "TRANSFERENCIA_DESTINO"] = Query(...),
        fecha: dt.date = Query(...),
    ) -> dict:
        filas = unidad.ejecutar(contexto(), lambda s: eleg.cuentas_elegibles(s, operacion, fecha),
                                nombre="F05-03 cuentas_elegibles")
        return {"operacion": operacion, "cuentas": [{"cuenta_id": f[0], "nombre": f[1], "moneda": f[2]} for f in filas]}

    @app.get("/v1/vs01/gasto-mes", response_model=GastoMesVs01, dependencies=[Depends(autorizar)])
    def gasto_mes(mes: str = Query(...)) -> dict:
        if not _MES.match(mes):
            return JSONResponse(
                {"codigo": "ENTRADA_INVALIDA", "mensaje": "Revisa los datos: mes", "reintentable": False},
                status_code=422,
            )
        return unidad.ejecutar(contexto(), lambda s: lect.gasto_mes(s, mes), nombre="VS01 gasto_mes")

    @app.get("/v1/categorias", response_model=ArbolCategoriasMagnitudes, dependencies=[Depends(autorizar)])
    def categorias() -> dict:
        filas = unidad.ejecutar(contexto(), lect_cat.arbol, nombre="F05-01 arbol_categorias")
        return {"categorias": filas}

    @app.get(
        "/v1/categorias/{categoria_id}/uso",
        response_model=UsoCategoria,
        dependencies=[Depends(autorizar)],
    )
    def uso_categoria(categoria_id: uuid.UUID) -> dict:
        return unidad.ejecutar(
            contexto(), lambda s: lect_cat.uso_por_naturaleza(s, categoria_id), nombre="F05-01 uso_categoria"
        )

    def _comando(nombre_op: str, operacion) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-01 {nombre_op}")
        if isinstance(salida, serv_cat.Rechazo):
            status, cuerpo = eh.rechazo_categoria(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        campos = CategoriaNodo.model_fields
        return {
            "categoria": {k: v for k, v in salida.categoria.items() if k in campos},
            "idempotente": salida.idempotente,
            "modificadas": list(salida.modificadas),
        }

    _R = {"response_model": ResultadoComandoCategoria, "dependencies": [Depends(autorizar)]}

    @app.post("/v1/categorias", **_R)
    def alta_categoria(c: AltaCategoria):
        return _comando("alta", lambda s: serv_cat.alta(
            s, categoria_id=c.id, nombre=c.nombre, parent_id=c.parent_id, ambito=c.ambito,
            presupuestable_default=c.presupuestable_default, icon_key=c.icon_key))

    @app.post("/v1/categorias/{categoria_id}/renombrar", **_R)
    def renombrar_categoria(categoria_id: uuid.UUID, c: RenombrarCategoria):
        return _comando("renombrar", lambda s: serv_cat.renombrar(
            s, categoria_id=categoria_id, nombre=c.nombre, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/mover", **_R)
    def mover_categoria(categoria_id: uuid.UUID, c: MoverCategoria):
        return _comando("mover", lambda s: serv_cat.mover(
            s, categoria_id=categoria_id, parent_id=c.parent_id, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/desactivar", **_R)
    def desactivar_categoria(categoria_id: uuid.UUID, c: DesactivarCategoria):
        return _comando("desactivar", lambda s: serv_cat.desactivar(
            s, categoria_id=categoria_id, modo=c.modo, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/reactivar", **_R)
    def reactivar_categoria(categoria_id: uuid.UUID, c: ReactivarCategoria):
        return _comando("reactivar", lambda s: serv_cat.reactivar(
            s, categoria_id=categoria_id, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/orden", **_R)
    def ordenar_categoria(categoria_id: uuid.UUID, c: OrdenCategoria):
        return _comando("orden", lambda s: serv_cat.ordenar(
            s, categoria_id=categoria_id, orden=c.orden, row_version=c.row_version))

    @app.post("/v1/categorias/{categoria_id}/ambito", **_R)
    def ambito_categoria(categoria_id: uuid.UUID, c: AmbitoCambio):
        return _comando("ambito", lambda s: serv_cat.cambiar_ambito(
            s, categoria_id=categoria_id, ambito=c.ambito, confirmacion_uso=c.confirmacion_uso,
            row_version=c.row_version))

    @app.post("/v1/categorias/reordenar", response_model=ResultadoReordenar, dependencies=[Depends(autorizar)])
    def reordenar_categorias(c: ReordenarHermanos):
        salida = unidad.ejecutar(contexto(), lambda s: serv_cat.reordenar(
            s, parent_id=c.parent_id, hermanos=[(h.id, h.row_version) for h in c.hermanos]),
            nombre="F05-01 reordenar")
        if isinstance(salida, serv_cat.Rechazo):
            status, cuerpo = eh.rechazo_categoria(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        campos = CategoriaNodo.model_fields
        return {
            "hermanos": [{k: v for k, v in n.items() if k in campos} for n in salida.hermanos],
            "idempotente": salida.idempotente,
            "modificadas": list(salida.modificadas),
        }

    @app.get("/v1/categorias/sugeridas", response_model=CategoriasSugeridas, dependencies=[Depends(autorizar)])
    def categorias_sugeridas() -> dict:
        return {"version": onb.VERSION, "nodos": [n.__dict__ for n in onb.arbol_v1()]}

    @app.post("/v1/categorias/onboarding", response_model=ResultadoOnboarding, dependencies=[Depends(autorizar)])
    def onboarding_categorias():
        salida = unidad.ejecutar(contexto(), onb.onboarding_categorias, nombre="F05-03 onboarding_categorias")
        if isinstance(salida, serv_cat.Rechazo):
            status, cuerpo = eh.rechazo_categoria(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {"creadas": len(salida.creadas), "idempotente": salida.idempotente}

    @app.post("/v1/categorias/{categoria_id}/icono", **_R)
    def icono_categoria(categoria_id: uuid.UUID, c: IconoCategoria):
        return _comando("icono", lambda s: serv_cat.cambiar_icono(
            s, categoria_id=categoria_id, icon_key=c.icon_key, row_version=c.row_version))

    # ------------------------------------------------------------ S7-MAG
    def _comando_magnitudes(nombre_op: str, operacion, convertir) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-01 {nombre_op}")
        if isinstance(salida, serv_cat.Rechazo):
            status, cuerpo = eh.rechazo_magnitud(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {**convertir(salida), "idempotente": salida.idempotente, "modificadas": list(salida.modificadas)}

    def _asociacion(r: serv_mag.ResultadoAsociacion) -> dict:
        return {"categoria_id": r.categoria_id, "asociacion": r.asociacion, "magnitud": r.magnitud}

    def _asociaciones(r: serv_mag.ResultadoAsociaciones) -> dict:
        return {"categoria_id": r.categoria_id, "asociaciones": list(r.asociaciones)}

    def _ficha(r: serv_mag.ResultadoMagnitud) -> dict:
        return {"magnitud": r.magnitud}

    _RA = {"response_model": ResultadoAsociacionMagnitud, "dependencies": [Depends(autorizar)]}
    _RL = {"response_model": ResultadoAsociacionesMagnitud, "dependencies": [Depends(autorizar)]}
    _RM = {"response_model": ResultadoComandoMagnitud, "dependencies": [Depends(autorizar)]}

    @app.get("/v1/magnitudes", response_model=CatalogoMagnitudes, dependencies=[Depends(autorizar)])
    def magnitudes() -> dict:
        return {"magnitudes": unidad.ejecutar(contexto(), lect_mag.catalogo, nombre="F05-01 catalogo_magnitudes")}

    @app.post("/v1/categorias/{categoria_id}/magnitudes", **_RA)
    def asociar_magnitud(categoria_id: uuid.UUID, c: AsociarMagnitud = Body(...)):
        if isinstance(c, AsociarNueva):
            nueva = {"magnitud_id": c.magnitud.magnitud_id, "nombre": c.magnitud.nombre,
                     "unidad_default": c.magnitud.unidad_default,
                     "precision_decimales": c.magnitud.precision_decimales}
            op = lambda s: serv_mag.asociar(s, categoria_id=categoria_id, obligatoria=c.obligatoria,  # noqa: E731
                                            nueva=nueva)
        else:
            op = lambda s: serv_mag.asociar(s, categoria_id=categoria_id, obligatoria=c.obligatoria,  # noqa: E731
                                            magnitud_id=c.magnitud_id)
        return _comando_magnitudes("mag_asociar", op, _asociacion)

    # Ruta literal antes de la parametrizada: /reordenar no es un asociacion_id.
    @app.post("/v1/categorias/{categoria_id}/magnitudes/reordenar", **_RL)
    def reordenar_magnitudes(categoria_id: uuid.UUID, c: ReordenarMagnitudes):
        return _comando_magnitudes("mag_reordenar", lambda s: serv_mag.reordenar(
            s, categoria_id=categoria_id,
            asociaciones=[(a.asociacion_id, a.magnitud_id, a.orden, a.obligatoria) for a in c.asociaciones]),
            _asociaciones)

    @app.post("/v1/categorias/{categoria_id}/magnitudes/{asociacion_id}/obligatoria", **_RA)
    def obligatoria_magnitud(categoria_id: uuid.UUID, asociacion_id: uuid.UUID, c: ObligatoriaAsociacion):
        return _comando_magnitudes("mag_obligatoria", lambda s: serv_mag.cambiar_obligatoria(
            s, categoria_id=categoria_id, asociacion_id=asociacion_id, magnitud_id=c.magnitud_id,
            obligatoria_actual=c.obligatoria_actual, obligatoria=c.obligatoria), _asociacion)

    @app.post("/v1/categorias/{categoria_id}/magnitudes/{asociacion_id}/retirar", **_RL)
    def retirar_magnitud(categoria_id: uuid.UUID, asociacion_id: uuid.UUID, c: RetirarAsociacion):
        return _comando_magnitudes("mag_retirar", lambda s: serv_mag.retirar(
            s, categoria_id=categoria_id, asociacion_id=asociacion_id, magnitud_id=c.magnitud_id,
            obligatoria_actual=c.obligatoria_actual), _asociaciones)

    @app.post("/v1/magnitudes/{magnitud_id}/renombrar", **_RM)
    def renombrar_magnitud(magnitud_id: uuid.UUID, c: RenombrarMagnitud):
        return _comando_magnitudes("mag_renombrar", lambda s: serv_mag.renombrar(
            s, magnitud_id=magnitud_id, nombre=c.nombre, row_version=c.row_version), _ficha)

    @app.post("/v1/magnitudes/{magnitud_id}/deshabilitar", **_RM)
    def deshabilitar_magnitud(magnitud_id: uuid.UUID, c: DeshabilitarMagnitud):
        return _comando_magnitudes("mag_deshabilitar", lambda s: serv_mag.deshabilitar(
            s, magnitud_id=magnitud_id, row_version=c.row_version,
            confirmacion_impacto=c.confirmacion_impacto), _ficha)

    @app.post("/v1/magnitudes/{magnitud_id}/rehabilitar", **_RM)
    def rehabilitar_magnitud(magnitud_id: uuid.UUID, c: RehabilitarMagnitud):
        return _comando_magnitudes("mag_rehabilitar", lambda s: serv_mag.rehabilitar(
            s, magnitud_id=magnitud_id, row_version=c.row_version), _ficha)

    # ------------------------------------------------------------ F05-02 B1
    def _comando_preferencia(nombre_op: str, operacion) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-02 {nombre_op}")
        if isinstance(salida, serv_pref.Rechazo):
            status, cuerpo = eh.rechazo_preferencia(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        campos = PreferenciaNodo.model_fields
        return {
            "preferencia": {k: v for k, v in salida.preferencia.items() if k in campos},
            "idempotente": salida.idempotente,
            "modificadas": list(salida.modificadas),
        }

    _RP = {"response_model": ResultadoComandoPreferencia, "dependencies": [Depends(autorizar)]}

    @app.get("/v1/preferencias", response_model=ListaPreferencias, dependencies=[Depends(autorizar)])
    def preferencias() -> dict:
        return unidad.ejecutar(
            contexto(), lambda s: {"preferencias": lect_pref.listar(s, reloj), "tipos": lect_pref.tipos_registro(s)},
            nombre="F05-02 listar")

    @app.get("/v1/preferencias/propuesta", response_model=PropuestaRegistro, dependencies=[Depends(autorizar)])
    def propuesta_preferencias(fecha: dt.date = Query(...), categoria_id: uuid.UUID | None = Query(None),
                               tipo: Literal["GASTO", "INGRESO"] = Query("GASTO"),
                               tercero_id: uuid.UUID | None = Query(None)):
        # Sin categoria_id = «Sin categoria»: solo casan preferencias de categoria NULL.
        # Sin tercero_id = sin tercero: solo casan preferencias de tercero NULL (E2).
        salida = unidad.ejecutar(
            contexto(), lambda s: lect_pref.propuesta(s, categoria_id, fecha, tipo, tercero_id),
            nombre="F05-02 propuesta",
        )
        if isinstance(salida, str):
            # Categoria no elegible para el tipo (guarda C-a): codigo y status de la capa F05,
            # con mensaje de lectura (AJ-B2-05).
            status, cuerpo = eh.rechazo_integracion(salida)
            mensaje = MENSAJE_PROPUESTA_NO_ELEGIBLE if tipo == "GASTO" else MENSAJE_PROPUESTA_NO_ELEGIBLE_INGRESO
            return JSONResponse({**cuerpo, "mensaje": mensaje}, status_code=status)
        return salida

    @app.post("/v1/preferencias", **_RP)
    def alta_preferencia(c: AltaPreferencia):
        return _comando_preferencia("alta", lambda s: serv_pref.alta(
            s, preferencia_id=c.id, tipo_hecho_id=c.tipo_hecho_id, categoria_id=c.categoria_id,
            tercero_id=c.tercero_id, entidad_id=c.entidad_id, cuenta_default_id=c.cuenta_default_id,
            presupuestable_default=c.presupuestable_default, prioridad=c.prioridad, reloj=reloj))

    @app.post("/v1/preferencias/{preferencia_id}/editar", **_RP)
    def editar_preferencia(preferencia_id: uuid.UUID, c: EditarPreferencia):
        return _comando_preferencia("editar", lambda s: serv_pref.editar(
            s, preferencia_id=preferencia_id, row_version=c.row_version, tipo_hecho_id=c.tipo_hecho_id,
            categoria_id=c.categoria_id, tercero_id=c.tercero_id, entidad_id=c.entidad_id,
            cuenta_default_id=c.cuenta_default_id, presupuestable_default=c.presupuestable_default,
            prioridad=c.prioridad, reloj=reloj))

    @app.post("/v1/preferencias/{preferencia_id}/desactivar", **_RP)
    def desactivar_preferencia(preferencia_id: uuid.UUID, c: DesactivarPreferencia):
        return _comando_preferencia("desactivar", lambda s: serv_pref.desactivar(
            s, preferencia_id=preferencia_id, row_version=c.row_version))

    @app.post("/v1/preferencias/{preferencia_id}/reactivar", **_RP)
    def reactivar_preferencia(preferencia_id: uuid.UUID, c: ReactivarPreferencia):
        return _comando_preferencia("reactivar", lambda s: serv_pref.reactivar(
            s, preferencia_id=preferencia_id, row_version=c.row_version))

    # ------------------------------------------------------------ F05-06 M4 capacidades de cuenta
    def _rechazo_capacidad(salida) -> JSONResponse:
        status, cuerpo = eh.rechazo_capacidad(salida.codigo, salida.detalle)
        return JSONResponse(cuerpo, status_code=status)

    @app.get("/v1/cuentas/capacidades", response_model=ListaCuentasCapacidades, dependencies=[Depends(autorizar)])
    def capacidades_lista() -> dict:
        def _op(s):
            cuentas = lect_cap.lista(s)
            return {"cuentas": cuentas, "sin_configurar": lect_cap.contar_sin_configurar(cuentas)}
        return unidad.ejecutar(contexto(), _op, nombre="F05-06 capacidades lista")

    @app.get("/v1/cuentas/sin-configurar", response_model=SinConfigurar, dependencies=[Depends(autorizar)])
    def capacidades_sin_configurar() -> dict:
        return {"sin_configurar": unidad.ejecutar(contexto(), lect_cap.sin_configurar,
                                                  nombre="F05-06 capacidades sin configurar")}

    @app.get("/v1/cuentas/{cuenta_id}/capacidades", response_model=CuentaCapacidades,
             dependencies=[Depends(autorizar)])
    def capacidades_detalle(cuenta_id: uuid.UUID):
        salida = unidad.ejecutar(contexto(), lambda s: lect_cap.detalle(s, cuenta_id),
                                 nombre="F05-06 capacidades detalle")
        return _rechazo_capacidad(serv_cap.Rechazo(serv_cap.CUENTA_NO_ENCONTRADA)) if salida is None else salida

    @app.get("/v1/cuentas/{cuenta_id}/capacidades/historial", response_model=HistorialCapacidades,
             dependencies=[Depends(autorizar)])
    def capacidades_historial(cuenta_id: uuid.UUID):
        def _op(s):
            if lect_cap.detalle(s, cuenta_id) is None:
                return serv_cap.Rechazo(serv_cap.CUENTA_NO_ENCONTRADA)
            return {"entradas": lect_cap.historial(s, cuenta_id)}
        salida = unidad.ejecutar(contexto(), _op, nombre="F05-06 capacidades historial")
        return _rechazo_capacidad(salida) if isinstance(salida, serv_cap.Rechazo) else salida

    @app.get("/v1/cuentas/{cuenta_id}/capacidades/{capacidad}/impacto", response_model=ImpactoDesactivar,
             dependencies=[Depends(autorizar)])
    def capacidades_impacto(cuenta_id: uuid.UUID, capacidad: str):
        def _op(s):
            rechazo = serv_cap.validar_capacidad(capacidad)
            if rechazo is not None:
                return rechazo
            if lect_cap.detalle(s, cuenta_id) is None:
                return serv_cap.Rechazo(serv_cap.CUENTA_NO_ENCONTRADA)
            return lect_cap.impacto(s, cuenta_id, capacidad, reloj)
        salida = unidad.ejecutar(contexto(), _op, nombre="F05-06 capacidades impacto")
        return _rechazo_capacidad(salida) if isinstance(salida, serv_cap.Rechazo) else salida

    def _comando_capacidad(nombre_op: str, operacion) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-06 capacidad {nombre_op}")
        if isinstance(salida, serv_cap.Rechazo):
            return _rechazo_capacidad(salida)
        return {"cuenta": salida.cuenta, "idempotente": salida.idempotente}

    _RCAP = {"response_model": ResultadoComandoCapacidad, "dependencies": [Depends(autorizar)]}

    @app.post("/v1/cuentas/{cuenta_id}/capacidades/{capacidad}/activar", **_RCAP)
    def activar_capacidad(cuenta_id: uuid.UUID, capacidad: str, c: CambioCapacidad):
        return _comando_capacidad("activar", lambda s: serv_cap.activar(
            s, cuenta_id=cuenta_id, capacidad=capacidad, row_version=c.row_version))

    @app.post("/v1/cuentas/{cuenta_id}/capacidades/{capacidad}/desactivar", **_RCAP)
    def desactivar_capacidad(cuenta_id: uuid.UUID, capacidad: str, c: CambioCapacidad):
        return _comando_capacidad("desactivar", lambda s: serv_cap.desactivar(
            s, cuenta_id=cuenta_id, capacidad=capacidad, row_version=c.row_version))

    # ------------------------------------------------------------ F05-04 J2 §1.3/§1.4 maestros
    def _comando_maestro(nombre_op: str, operacion, modulo, traducir, clave: str) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-04 {nombre_op}")
        if isinstance(salida, modulo.Rechazo):
            status, cuerpo = traducir(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {clave: getattr(salida, clave), "idempotente": salida.idempotente,
                "modificadas": list(salida.modificadas)}

    _RT = {"response_model": ResultadoComandoTercero, "dependencies": [Depends(autorizar)]}
    _RC = {"response_model": ResultadoComandoContexto, "dependencies": [Depends(autorizar)]}

    @app.get("/v1/terceros", response_model=ListaTerceros, dependencies=[Depends(autorizar)])
    def terceros(q: str | None = Query(None, max_length=160), incluir_inactivos: bool = Query(False)) -> dict:
        if q is None:
            return {"terceros": unidad.ejecutar(contexto(), lect_ter.listar, nombre="F05-04 terceros")}
        return {"terceros": unidad.ejecutar(contexto(), lambda s: lect_ter.buscar(s, q, incluir_inactivos),
                                            nombre="F05-05 buscar_terceros")}

    @app.get("/v1/terceros/candidatos", response_model=ListaTerceros, dependencies=[Depends(autorizar)])
    def candidatos_tercero(nombre: str = Query(..., max_length=160)) -> dict:
        return {"terceros": unidad.ejecutar(contexto(), lambda s: lect_ter.candidatos(s, nombre),
                                            nombre="F05-04 candidatos_tercero")}

    @app.post("/v1/terceros", **_RT)
    def alta_tercero(c: AltaTercero):
        return _comando_maestro("tercero_alta", lambda s: serv_ter.alta(
            s, tercero_id=c.id, nombre=c.nombre, naturaleza=c.naturaleza), serv_ter, eh.rechazo_tercero, "tercero")

    @app.post("/v1/terceros/{tercero_id}/editar", **_RT)
    def editar_tercero(tercero_id: uuid.UUID, c: EditarTercero):
        return _comando_maestro("tercero_editar", lambda s: serv_ter.editar(
            s, tercero_id=tercero_id, row_version=c.row_version, nombre=c.nombre, naturaleza=c.naturaleza),
            serv_ter, eh.rechazo_tercero, "tercero")

    @app.post("/v1/terceros/{tercero_id}/desactivar", **_RT)
    def desactivar_tercero(tercero_id: uuid.UUID, c: EstadoTercero):
        return _comando_maestro("tercero_desactivar", lambda s: serv_ter.desactivar(
            s, tercero_id=tercero_id, row_version=c.row_version), serv_ter, eh.rechazo_tercero, "tercero")

    @app.post("/v1/terceros/{tercero_id}/reactivar", **_RT)
    def reactivar_tercero(tercero_id: uuid.UUID, c: EstadoTercero):
        return _comando_maestro("tercero_reactivar", lambda s: serv_ter.reactivar(
            s, tercero_id=tercero_id, row_version=c.row_version), serv_ter, eh.rechazo_tercero, "tercero")

    @app.get("/v1/contextos", response_model=ListaContextos, dependencies=[Depends(autorizar)])
    def contextos() -> dict:
        return {"contextos": unidad.ejecutar(contexto(), lect_ctx.listar, nombre="F05-04 contextos")}

    @app.post("/v1/contextos", **_RC)
    def alta_contexto(c: AltaContexto):
        return _comando_maestro("contexto_alta", lambda s: serv_ctx.alta(
            s, contexto_id=c.id, nombre=c.nombre, tipo_contexto=c.tipo_contexto, fecha_inicio=c.fecha_inicio,
            fecha_fin=c.fecha_fin), serv_ctx, eh.rechazo_contexto, "contexto")

    @app.post("/v1/contextos/{contexto_id}/editar", **_RC)
    def editar_contexto(contexto_id: uuid.UUID, c: EditarContexto):
        return _comando_maestro("contexto_editar", lambda s: serv_ctx.editar(
            s, contexto_id=contexto_id, row_version=c.row_version, nombre=c.nombre, tipo_contexto=c.tipo_contexto,
            fecha_inicio=c.fecha_inicio, fecha_fin=c.fecha_fin), serv_ctx, eh.rechazo_contexto, "contexto")

    @app.post("/v1/contextos/{contexto_id}/desactivar", **_RC)
    def desactivar_contexto(contexto_id: uuid.UUID, c: EstadoContexto):
        return _comando_maestro("contexto_desactivar", lambda s: serv_ctx.desactivar(
            s, contexto_id=contexto_id, row_version=c.row_version), serv_ctx, eh.rechazo_contexto, "contexto")

    @app.post("/v1/contextos/{contexto_id}/reactivar", **_RC)
    def reactivar_contexto(contexto_id: uuid.UUID, c: EstadoContexto):
        return _comando_maestro("contexto_reactivar", lambda s: serv_ctx.reactivar(
            s, contexto_id=contexto_id, row_version=c.row_version), serv_ctx, eh.rechazo_contexto, "contexto")

    # ------------------------------------------------------------ F05-03 J2 §1.6 plantillas y acciones
    def _comando_plantilla(nombre_op: str, operacion, clave: str) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-03 {nombre_op}")
        if isinstance(salida, serv_plt.Rechazo):
            status, cuerpo = eh.rechazo_plantilla(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        valor = list(salida.acciones) if clave == "acciones" else getattr(salida, clave)
        return {clave: valor, "idempotente": salida.idempotente, "modificadas": list(salida.modificadas)}

    _RPL = {"response_model": ResultadoComandoPlantilla, "dependencies": [Depends(autorizar)]}
    _RAC = {"response_model": ResultadoComandoAccion, "dependencies": [Depends(autorizar)]}

    @app.get("/v1/plantillas", response_model=ListaPlantillas, dependencies=[Depends(autorizar)])
    def plantillas() -> dict:
        return unidad.ejecutar(contexto(), lambda s: {"plantillas": lect_plt.listar(s, reloj),
                                                      "acciones": lect_plt.acciones(s)}, nombre="F05-03 plantillas")

    @app.post("/v1/plantillas", **_RPL)
    def alta_plantilla(c: AltaPlantilla):
        return _comando_plantilla("plantilla_alta", lambda s: serv_plt.alta(
            s, plantilla_id=c.id, nombre=c.nombre, tipo_hecho_id=c.tipo_hecho_id, categoria_id=c.categoria_id,
            tercero_id=c.tercero_id, entidad_id=c.entidad_id, cuenta_default_id=c.cuenta_default_id,
            presupuestable_default=c.presupuestable_default, reloj=reloj), "plantilla")

    @app.post("/v1/plantillas/{plantilla_id}/editar", **_RPL)
    def editar_plantilla(plantilla_id: uuid.UUID, c: EditarPlantilla):
        return _comando_plantilla("plantilla_editar", lambda s: serv_plt.editar(
            s, plantilla_id=plantilla_id, row_version=c.row_version, nombre=c.nombre, tipo_hecho_id=c.tipo_hecho_id,
            categoria_id=c.categoria_id, tercero_id=c.tercero_id, entidad_id=c.entidad_id,
            cuenta_default_id=c.cuenta_default_id, presupuestable_default=c.presupuestable_default,
            reloj=reloj), "plantilla")

    @app.post("/v1/plantillas/{plantilla_id}/desactivar", **_RPL)
    def desactivar_plantilla(plantilla_id: uuid.UUID, c: EstadoPlantilla):
        return _comando_plantilla("plantilla_desactivar", lambda s: serv_plt.desactivar(
            s, plantilla_id=plantilla_id, row_version=c.row_version), "plantilla")

    @app.post("/v1/plantillas/{plantilla_id}/reactivar", **_RPL)
    def reactivar_plantilla(plantilla_id: uuid.UUID, c: EstadoPlantilla):
        return _comando_plantilla("plantilla_reactivar", lambda s: serv_plt.reactivar(
            s, plantilla_id=plantilla_id, row_version=c.row_version), "plantilla")

    @app.post("/v1/acciones-rapidas", **_RAC)
    def alta_accion(c: AltaAccion):
        return _comando_plantilla("accion_alta", lambda s: serv_plt.alta_accion(
            s, accion_id=c.id, plantilla_id=c.plantilla_registro_id, nombre=c.nombre, icono_key=c.icono_key),
            "accion")

    # Ruta literal antes de la parametrizada: /reordenar no es un accion_id.
    @app.post("/v1/acciones-rapidas/reordenar", response_model=ResultadoReordenarAcciones,
              dependencies=[Depends(autorizar)])
    def reordenar_acciones(c: ReordenarAcciones):
        return _comando_plantilla("accion_reordenar", lambda s: serv_plt.reordenar_acciones(
            s, acciones=[(a.id, a.row_version) for a in c.acciones]), "acciones")

    @app.post("/v1/acciones-rapidas/{accion_id}/editar", **_RAC)
    def editar_accion(accion_id: uuid.UUID, c: EditarAccion):
        return _comando_plantilla("accion_editar", lambda s: serv_plt.editar_accion(
            s, accion_id=accion_id, row_version=c.row_version, nombre=c.nombre, icono_key=c.icono_key), "accion")

    @app.post("/v1/acciones-rapidas/{accion_id}/desactivar", **_RAC)
    def desactivar_accion(accion_id: uuid.UUID, c: EstadoAccion):
        return _comando_plantilla("accion_desactivar", lambda s: serv_plt.desactivar_accion(
            s, accion_id=accion_id, row_version=c.row_version), "accion")

    @app.get("/v1/registro/propuesta", response_model=PropuestaRegistroTipo, dependencies=[Depends(autorizar)])
    def propuesta_registro(
        tipo: Literal["GASTO", "INGRESO"] = Query(...), fecha: dt.date = Query(...),
        plantilla_id: uuid.UUID | None = Query(None), categoria_id: uuid.UUID | None = Query(None),
        sin_categoria: bool = Query(False), tercero_id: uuid.UUID | None = Query(None),
        sin_tercero: bool = Query(False),
    ):
        salida = unidad.ejecutar(contexto(), lambda s: prop_plt.propuesta_registro(
            s, tipo=tipo, fecha=fecha, plantilla_id=plantilla_id, categoria_id=categoria_id,
            sin_categoria=sin_categoria, tercero_id=tercero_id, sin_tercero=sin_tercero),
            nombre="F05-03 propuesta_registro")
        if isinstance(salida, str):
            status, cuerpo = eh.rechazo_integracion(salida)
            mensaje = MENSAJE_PROPUESTA_NO_ELEGIBLE if tipo == "GASTO" else MENSAJE_PROPUESTA_NO_ELEGIBLE_INGRESO
            return JSONResponse({**cuerpo, "mensaje": mensaje}, status_code=status)
        return salida

    # ------------------------------------------------------------ F05-06 M5 errores de prevision
    def _rechazo_motor_prevision(exc: ErrorMotor, detalle: dict | None = None) -> JSONResponse | None:
        """Error del motor en una ruta de prevision -> texto propio (o None si no es de prevision)."""
        if exc.codigo.value not in eh.CODIGOS_PREVISION:
            return None
        if exc.codigo is CodigoError.PORCION_DE_REALIDAD_EXCEDIDA:
            detalle = {**(detalle or {}), "motivo": (exc.contexto_extra or {}).get("motivo")}
        status, cuerpo = eh.rechazo_prevision(exc.codigo.value, detalle)
        return JSONResponse(cuerpo, status_code=status)

    def _con_prevision(intencion, ejecutar):
        """Registro con bloque `prevision`: los errores de OP-17 llevan los textos de M5."""
        if getattr(intencion, "prevision", None) is None:
            return ejecutar()
        try:
            return ejecutar()
        except ErrorMotor as exc:
            respuesta = _rechazo_motor_prevision(exc)
            if respuesta is None:
                raise
            return respuesta

    @app.post(
        "/v1/intenciones/gasto-pagado",
        response_model=ResultadoGastoPagado,
        dependencies=[Depends(autorizar)],
    )
    def gasto_pagado(intencion: IntencionGastoPagado) -> dict:
        salida = _con_prevision(intencion, lambda: registrar_gasto_pagado(unidad, contexto(), intencion, reloj))
        if isinstance(salida, JSONResponse):
            return salida
        if isinstance(salida, RechazoIntegracion):
            status, cuerpo = eh.rechazo_integracion(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        r, datos = salida.resultado, salida.datos
        return {
            "intencion_id": intencion.intencion_id,
            "hecho_id": r.hecho_id,
            "idempotente": r.idempotente,
            "importe": str(intencion.importe.quantize(_CENT)),
            "moneda": intencion.moneda,
            "estado_atribucion": datos.efectos[0].estado_atribucion,
            "aportacion_criterio": datos.aportaciones[0].criterio_aportacion if datos.aportaciones else None,
            "financiacion": intencion.financiacion.estado,
            "estado_categorial": intencion.estado_categorial,
            "aviso": "API de integracion F05-00-B, pendiente de consolidacion F10",
        }

    def _respuesta_registro(salida, intencion, tipo: str, estado_categorial) -> dict | JSONResponse:
        if isinstance(salida, JSONResponse):
            return salida
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_integracion(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {
            "intencion_id": intencion.intencion_id, "hecho_id": salida.hecho_id, "idempotente": salida.idempotente,
            "tipo": tipo, "importe": str(intencion.importe.quantize(_CENT)), "moneda": intencion.moneda,
            "estado_atribucion": salida.estado_atribucion, "estado_categorial": estado_categorial,
            "aviso": "API de integracion F05, pendiente de consolidacion F10",
        }

    @app.post("/v1/intenciones/ingreso-cobrado", response_model=ResultadoRegistro, dependencies=[Depends(autorizar)])
    def ingreso_cobrado(intencion: IntencionIngresoCobrado):
        salida = _con_prevision(intencion, lambda: registrar_ingreso_cobrado(unidad, contexto(), intencion, reloj))
        return _respuesta_registro(salida, intencion, "INGRESO", intencion.categoria.estado)

    @app.post("/v1/intenciones/transferencia", response_model=ResultadoRegistro, dependencies=[Depends(autorizar)])
    def transferencia(intencion: IntencionTransferencia):
        if intencion.prevision is not None:  # F05-06 M5 opcion A: OP-10 + OP-17 en una transaccion
            salida = _con_prevision(intencion, lambda: ejp.registrar_transferencia_prevista(
                unidad, contexto(), intencion, reloj))
        else:
            salida = registrar_transferencia(unidad, contexto(), intencion, reloj)
        return _respuesta_registro(salida, intencion, "TRANSFERENCIA", None)

    # ------------------------------------------------------------ F05-06 M2 devolucion contextual
    _AVISO_F05 = "API de integracion F05, pendiente de consolidacion F10"

    @app.get("/v1/hechos/{origen_id}/devoluciones", response_model=ContextoDevolucion,
             dependencies=[Depends(autorizar)])
    def contexto_de_devolucion(origen_id: uuid.UUID):
        salida = unidad.ejecutar(contexto(), lambda s: contexto_devolucion(s, origen_id),
                                 nombre="F05-06 M2 contexto_devolucion")
        if salida is None:
            status, cuerpo = eh.rechazo_lectura("HECHO_NO_ENCONTRADO")
            return JSONResponse(cuerpo, status_code=status)
        return salida

    @app.post("/v1/hechos/{origen_id}/devoluciones", response_model=ResultadoDevolucionHttp,
              dependencies=[Depends(autorizar)])
    def devolucion(origen_id: uuid.UUID, intencion: IntencionDevolucion):
        salida = registrar_devolucion(unidad, contexto(), origen_id, intencion, reloj)
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_integracion(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {
            "intencion_id": intencion.intencion_id, "hecho_id": salida.hecho_id, "origen_id": origen_id,
            "idempotente": salida.idempotente, "importe": str(intencion.importe.quantize(_CENT)),
            "moneda": intencion.moneda, "estado_atribucion": salida.estado_atribucion, "abono": salida.abono,
            "devuelto": str(salida.devuelto.quantize(_CENT)), "queda": str(salida.queda.quantize(_CENT)),
            "aviso": _AVISO_F05,
        }

    @app.post("/v1/hechos/{devolucion_id}/abono", response_model=ResultadoAbonoHttp,
              dependencies=[Depends(autorizar)])
    def abono(devolucion_id: uuid.UUID, intencion: IntencionAbono):
        salida = registrar_abono(unidad, contexto(), devolucion_id, intencion, reloj)
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_integracion(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {
            "intencion_id": intencion.intencion_id, "hecho_id": salida.hecho_id,
            "movimiento_id": salida.movimiento_id, "idempotente": salida.idempotente,
            "importe": str(salida.importe.quantize(_CENT)), "abono": "COBRADO", "aviso": _AVISO_F05,
        }

    # ------------------------------------------------------------ F05-06 M3 reparto y posiciones
    def _posicion_http(intencion, salida):
        return {"intencion_id": intencion.intencion_id, "hecho_id": salida.hecho_id,
                "entidad_id": salida.entidad_id, "idempotente": salida.idempotente,
                "importe": str(intencion.importe.quantize(_CENT)),
                "saldo": None if salida.saldo is None else str(salida.saldo.quantize(_CENT)),
                "estado": salida.estado, "aviso": _AVISO_F05}

    def _posiciones_http(posiciones):
        return [{"entidad_id": p.entidad_id, "tipo": p.tipo, "tercero_id": p.tercero_id,
                 "importe": str(p.importe.quantize(_CENT))} for p in posiciones]

    @app.post("/v1/intenciones/gasto-compartido", response_model=ResultadoGastoCompartidoHttp,
              dependencies=[Depends(autorizar)])
    def gasto_compartido(intencion: IntencionGastoCompartido):
        salida = _con_prevision(intencion, lambda: rep.registrar_gasto_compartido(unidad, contexto(), intencion, reloj))
        if isinstance(salida, JSONResponse):
            return salida
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_integracion(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {
            "intencion_id": intencion.intencion_id, "hecho_id": salida.hecho_id,
            "idempotente": salida.idempotente, "importe": str(intencion.importe.quantize(_CENT)),
            "moneda": intencion.moneda, "estado_atribucion": salida.estado_atribucion,
            "tu_parte": None if salida.tu_parte is None else str(salida.tu_parte.quantize(_CENT)),
            "movimiento": None if salida.movimiento is None else str(salida.movimiento.quantize(_CENT)),
            "posiciones": _posiciones_http(salida.posiciones), "aviso": _AVISO_F05,
        }

    def _reduccion(fn, entidad_id, intencion):
        salida = fn(unidad, contexto(), entidad_id, intencion, reloj)
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_integracion(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return _posicion_http(intencion, salida)

    @app.post("/v1/posiciones/{entidad_id}/cobro", response_model=ResultadoPosicionHttp,
              dependencies=[Depends(autorizar)])
    def cobro_posicion(entidad_id: uuid.UUID, intencion: IntencionCobroPago):
        return _reduccion(rep.cobrar, entidad_id, intencion)

    @app.post("/v1/posiciones/{entidad_id}/pago", response_model=ResultadoPosicionHttp,
              dependencies=[Depends(autorizar)])
    def pago_posicion(entidad_id: uuid.UUID, intencion: IntencionCobroPago):
        return _reduccion(rep.pagar, entidad_id, intencion)

    @app.post("/v1/posiciones/{entidad_id}/perdon", response_model=ResultadoPosicionHttp,
              dependencies=[Depends(autorizar)])
    def perdon_posicion(entidad_id: uuid.UUID, intencion: IntencionPerdon):
        return _reduccion(rep.perdonar, entidad_id, intencion)

    @app.get("/v1/terceros/{tercero_id}/pendiente", response_model=PendienteConPersona,
             dependencies=[Depends(autorizar)])
    def pendiente_con(tercero_id: uuid.UUID):
        ctx = contexto()
        salida = unidad.ejecutar(ctx, lambda s: rep.pendiente_con(s, ctx, tercero_id),
                                 nombre="F05-06 M3 pendiente_con (OP-20)")
        if salida is None:
            status, cuerpo = eh.rechazo_lectura("TERCERO_NO_ENCONTRADO")
            return JSONResponse(cuerpo, status_code=status)
        return {**salida, "aviso": _AVISO_F05}

    @app.post("/v1/hechos/{hecho_id}/reparto", response_model=ResultadoCorreccionRepartoHttp,
              dependencies=[Depends(autorizar)])
    def corregir_reparto(hecho_id: uuid.UUID, intencion: IntencionCorregirReparto):
        try:
            salida = rep.corregir_reparto(unidad, contexto(), hecho_id, intencion)
        except ErrorMotor as exc:
            if exc.codigo is not CodigoError.CORRECCION_AGREGADA_REQUERIDA:
                raise
            motivo = (exc.contexto_extra or {}).get("motivo")
            status, cuerpo = eh.traducir_error_motor(exc.codigo)
            return JSONResponse({**cuerpo, "detalle": {"motivo": motivo}}, status_code=status)
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_integracion(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {"hecho_id": salida.hecho_id, "row_version": salida.row_version,
                "tu_parte": None if salida.tu_parte is None else str(salida.tu_parte.quantize(_CENT)),
                "posiciones": _posiciones_http(salida.posiciones), "aviso": _AVISO_F05}

    @app.get("/v1/hechos/{hecho_id}/reparto", response_model=RepartoDeHecho, dependencies=[Depends(autorizar)])
    def reparto_de_hecho(hecho_id: uuid.UUID):
        ctx = contexto()
        salida = unidad.ejecutar(ctx, lambda s: rep.reparto_de_hecho(s, ctx, hecho_id),
                                 nombre="F05-06 M3 reparto_de_hecho")
        if salida is None:
            status, cuerpo = eh.rechazo_lectura("HECHO_NO_ENCONTRADO")
            return JSONResponse(cuerpo, status_code=status)
        return salida

    @app.get("/v1/hechos/{hecho_id}/anulacion", response_model=ElegibilidadAnulacion,
             dependencies=[Depends(autorizar)])
    def elegibilidad_anulacion(hecho_id: uuid.UUID):
        salida = unidad.ejecutar(contexto(), lambda s: rep.elegibilidad_anulacion(s, hecho_id),
                                 nombre="F05-06 M3 elegibilidad_anulacion")
        if salida is None:
            status, cuerpo = eh.rechazo_lectura("HECHO_NO_ENCONTRADO")
            return JSONResponse(cuerpo, status_code=status)
        return salida

    # ------------------------------------------------------------ F05-06 M1 corregir y anular (EDIT-HECHO v0.1)
    def _leer_edicion(hecho_id: uuid.UUID) -> dict | None:
        d = unidad.ejecutar(contexto(), lambda s: lect_edi.edicion(s, hecho_id), nombre="F05-06 M1 edicion")
        if d is not None:
            for accion in d["acciones"].values():
                if accion is not None:
                    accion["motivo"] = eh.MOTIVOS_EDICION.get(accion["codigo"]) if accion["codigo"] else None
        return d

    def _escritura_edicion(hecho_id: uuid.UUID, intencion, ejecutar):
        try:
            salida = ejecutar(ContextoOperacion.de_usuario(cfg.owner_user_id, request_id=intencion.intencion_id))
        except ErrorMotor as exc:
            if exc.codigo in (CodigoError.INTERNO, CodigoError.VIOLACION_INVARIANTE_FISICA):
                raise
            status, cuerpo = eh.rechazo_edicion(exc.codigo, exc.contexto_extra)
            if exc.codigo is CodigoError.VERSION_DESFASADA:
                cuerpo = {**cuerpo, "detalle": {**cuerpo.get("detalle", {}), "edicion": jsonable_encoder(
                    _leer_edicion(hecho_id))}}
            return JSONResponse(cuerpo, status_code=status)
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_integracion(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        estado = unidad.ejecutar(contexto(), lambda s: s.uno(
            "SELECT estado FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,)), nombre="F05-06 M1 estado")
        return {"intencion_id": intencion.intencion_id, "hecho_id": hecho_id, "row_version": salida.hecho_row_version,
                "estado": estado[0] if estado else "ACTIVO", "idempotente": salida.idempotente}

    @app.get("/v1/hechos/{hecho_id}/edicion", response_model=EdicionHecho, dependencies=[Depends(autorizar)])
    def edicion_hecho(hecho_id: uuid.UUID):
        salida = _leer_edicion(hecho_id)
        if salida is None:
            status, cuerpo = eh.rechazo_lectura("HECHO_NO_ENCONTRADO")
            return JSONResponse(cuerpo, status_code=status)
        return salida

    @app.post("/v1/hechos/{hecho_id}/corregir-pago", response_model=ResultadoEdicion, dependencies=[Depends(autorizar)])
    def corregir_pago_hecho(hecho_id: uuid.UUID, intencion: IntencionCorregirPago):
        return _escritura_edicion(hecho_id, intencion, lambda ctx: ejc.corregir_pago_http(unidad, ctx, hecho_id, intencion))

    @app.post("/v1/transferencias/{hecho_id}/corregir", response_model=ResultadoEdicion,
              dependencies=[Depends(autorizar)])
    def corregir_transferencia_hecho(hecho_id: uuid.UUID, intencion: IntencionCorregirTransferencia):
        return _escritura_edicion(hecho_id, intencion,
                                  lambda ctx: ejc.corregir_transferencia_http(unidad, ctx, hecho_id, intencion))

    @app.post("/v1/hechos/{hecho_id}/anular-duplicado", response_model=ResultadoEdicion,
              dependencies=[Depends(autorizar)])
    def anular_duplicado_hecho(hecho_id: uuid.UUID, intencion: IntencionAnularDuplicado):
        return _escritura_edicion(hecho_id, intencion,
                                  lambda ctx: eja.anular_duplicado_http(unidad, ctx, hecho_id, intencion))

    @app.post("/v1/hechos/{hecho_id}/corregir-categoria", response_model=ResultadoEdicion,
              dependencies=[Depends(autorizar)])
    def corregir_categoria_hecho(hecho_id: uuid.UUID, intencion: IntencionCorregirCategoriaV3):
        return _escritura_edicion(hecho_id, intencion,
                                  lambda ctx: ejv3.corregir_categoria_v3(unidad, ctx, hecho_id, intencion))

    # ------------------------------------------------------------ F05-06 M5 confirmacion de previsiones
    def _no_encontrada() -> JSONResponse:
        status, cuerpo = eh.rechazo_prevision("AGREGADO_NO_ENCONTRADO")
        return JSONResponse(cuerpo, status_code=status)

    def _estado_actual(prevision_id: uuid.UUID) -> dict | None:
        """Estado releido tras un 409 (D-PREV-14), en una lectura aparte."""
        d = unidad.ejecutar(contexto(), lambda s: lect_prev.detalle(s, prevision_id, hoy_owner(s, reloj)),
                            nombre="F05-06 M5 estado tras rechazo")
        if d is None:
            return None
        return {"estado": d["estado"], "estado_derivado": d["estado_derivado"], "row_version": d["row_version"],
                "con_realidad": d["con_realidad"], "cubierto": d["cubierto"]}

    @app.get("/v1/inicio/previsiones", response_model=InicioPrevisiones, dependencies=[Depends(autorizar)])
    def inicio_previsiones():
        salida = unidad.ejecutar(contexto(), lambda s: lect_prev.inicio(s, hoy_owner(s, reloj)),
                                 nombre="F05-06 M5 inicio_previsiones")
        return {**salida, "aviso": _AVISO_F05}

    @app.get("/v1/previsiones/pendientes", response_model=PendientesPrevisiones, dependencies=[Depends(autorizar)])
    def pendientes_previsiones():
        salida = unidad.ejecutar(contexto(), lambda s: lect_prev.pendientes(s, hoy_owner(s, reloj)),
                                 nombre="F05-06 M5 pendientes")
        return {**salida, "aviso": _AVISO_F05}

    @app.get("/v1/previsiones/{prevision_id}", response_model=DetallePrevision, dependencies=[Depends(autorizar)])
    def detalle_prevision(prevision_id: uuid.UUID):
        salida = unidad.ejecutar(contexto(), lambda s: lect_prev.detalle(s, prevision_id, hoy_owner(s, reloj)),
                                 nombre="F05-06 M5 detalle_prevision")
        return _no_encontrada() if salida is None else {**salida, "aviso": _AVISO_F05}

    @app.get("/v1/previsiones/{prevision_id}/candidatos", response_model=CandidatosPrevision,
             dependencies=[Depends(autorizar)])
    def candidatos_prevision(prevision_id: uuid.UUID, ampliado: bool = Query(False)):
        salida = unidad.ejecutar(contexto(), lambda s: lect_prev.candidatos(s, prevision_id, ampliado=ampliado),
                                 nombre="F05-06 M5 candidatos")
        return _no_encontrada() if salida is None else {**salida, "aviso": _AVISO_F05}

    @app.post("/v1/previsiones/{prevision_id}/vincular", response_model=ResultadoVinculo,
              dependencies=[Depends(autorizar)])
    def vincular_prevision(prevision_id: uuid.UUID, intencion: IntencionVincular):
        try:
            salida = ejp.vincular(unidad, contexto(), prevision_id, intencion)
        except ErrorMotor as exc:
            respuesta = _rechazo_motor_prevision(exc)
            if respuesta is None:
                raise
            return respuesta
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_prevision(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {"intencion_id": intencion.intencion_id, "prevision_id": prevision_id, "hecho_id": salida.hecho_id,
                "importe_vinculado": str(salida.importe.quantize(_CENT)), "estado": salida.estado,
                "row_version": salida.row_version, "idempotente": salida.idempotente, "aviso": _AVISO_F05}

    @app.post("/v1/previsiones/{prevision_id}/omitir", response_model=ResultadoOmitir,
              dependencies=[Depends(autorizar)])
    def omitir_prevision(prevision_id: uuid.UUID, intencion: IntencionOmitir):
        try:
            salida = ejp.omitir(unidad, contexto(), prevision_id, intencion)
        except ErrorMotor as exc:
            detalle = None
            if exc.codigo in (CodigoError.ESTADO_PREVISION_INCOMPATIBLE, CodigoError.VERSION_DESFASADA):
                detalle = {"estado_actual": _estado_actual(prevision_id)}
            respuesta = _rechazo_motor_prevision(exc, detalle)
            if respuesta is None:
                raise
            return respuesta
        return {"intencion_id": intencion.intencion_id, "prevision_id": prevision_id, "estado": salida.estado,
                "row_version": salida.row_version, "aviso": _AVISO_F05}

    # ------------------------------------------------------------ F05-06 M5-B dar por cubierta y reabrir
    def _transicion(prevision_id: uuid.UUID, intencion, ejecutar):
        try:
            salida = ejecutar()
        except ErrorMotor as exc:
            releer = exc.codigo in (CodigoError.ESTADO_PREVISION_INCOMPATIBLE, CodigoError.VERSION_DESFASADA)
            respuesta = _rechazo_motor_prevision(exc, {"estado_actual": _estado_actual(prevision_id)} if releer else None)
            if respuesta is None:
                raise
            return respuesta
        if isinstance(salida, RechazoRegistro):
            status, cuerpo = eh.rechazo_prevision(salida.codigo, {"estado_actual": _estado_actual(prevision_id)})
            return JSONResponse(cuerpo, status_code=status)
        return {"intencion_id": intencion.intencion_id, "prevision_id": prevision_id, "estado": salida.estado,
                "row_version": salida.row_version, "aviso": _AVISO_F05}

    @app.post("/v1/previsiones/{prevision_id}/dar-por-realizada", response_model=ResultadoTransicion,
              dependencies=[Depends(autorizar)])
    def dar_por_realizada_prevision(prevision_id: uuid.UUID, intencion: IntencionDarPorCubierta):
        return _transicion(prevision_id, intencion,
                           lambda: ejp.dar_por_cubierta(unidad, contexto(), prevision_id, intencion))

    @app.post("/v1/previsiones/{prevision_id}/reabrir", response_model=ResultadoTransicion,
              dependencies=[Depends(autorizar)])
    def reabrir_prevision(prevision_id: uuid.UUID, intencion: IntencionReabrir):
        return _transicion(prevision_id, intencion, lambda: ejp.reabrir(unidad, contexto(), prevision_id, intencion))

    # ------------------------------------------------------------ F05-05 K2 §1.2-§1.4
    def _lectura_con_fecha(nombre_op: str, fecha: dt.date, operacion) -> dict | JSONResponse:
        """Lectura con fecha funcional (C6): FECHA_FUTURA y TERCERO_NO_ENCONTRADO
        se devuelven con su codigo; si no, el resultado de la operacion."""
        def _op(s):
            if es_futura(s, fecha, reloj):
                return "FECHA_FUTURA"
            return operacion(s)
        salida = unidad.ejecutar(contexto(), _op, nombre=f"F05-05 {nombre_op}")
        if isinstance(salida, str):
            status, cuerpo = eh.rechazo_lectura(salida)
            return JSONResponse(cuerpo, status_code=status)
        return salida

    @app.get("/v1/senales/categorias", response_model=SenalesCategorias, dependencies=[Depends(autorizar)])
    def senales_categorias(tipo: Literal["GASTO", "INGRESO"] = Query(...), fecha: dt.date = Query(...),
                           tercero_id: uuid.UUID | None = Query(None)):
        def _op(s):
            if tercero_id is not None and not senales.tercero_visible(s, tercero_id):
                return "TERCERO_NO_ENCONTRADO"
            return {"tipo": tipo, "fecha": fecha, "tercero_id": tercero_id,
                    "candidatas": senales.categorias_candidatas(s, tipo, tercero_id, fecha)}
        return _lectura_con_fecha("senales_categorias", fecha, _op)

    @app.get("/v1/senales/terceros", response_model=SenalesTerceros, dependencies=[Depends(autorizar)])
    def senales_terceros(tipo: Literal["GASTO", "INGRESO"] = Query(...), fecha: dt.date = Query(...)):
        return _lectura_con_fecha("senales_terceros", fecha, lambda s: {
            "tipo": tipo, "fecha": fecha, "terceros": senales.terceros_recientes(s, tipo, fecha)})

    @app.get("/v1/terceros/{tercero_id}/afinidades", response_model=DetalleAfinidades,
             dependencies=[Depends(autorizar)])
    def afinidades_tercero(tercero_id: uuid.UUID, fecha: dt.date = Query(...),
                           tipo: Literal["GASTO", "INGRESO"] = Query("GASTO")):
        def _op(s):
            salida = lect_afi.detalle(s, tercero_id, tipo, fecha)
            return "TERCERO_NO_ENCONTRADO" if salida is None else salida
        return _lectura_con_fecha("afinidades_tercero", fecha, _op)

    def _comando_afinidad(nombre_op: str, operacion) -> dict | JSONResponse:
        salida = unidad.ejecutar(contexto(), operacion, nombre=f"F05-05 {nombre_op}")
        if isinstance(salida, serv_afi.Rechazo):
            status, cuerpo = eh.rechazo_afinidad(salida.codigo, salida.detalle)
            return JSONResponse(cuerpo, status_code=status)
        return {"afinidad": salida.afinidad, "idempotente": salida.idempotente, "aviso": salida.aviso}

    _RAF = {"response_model": ResultadoComandoAfinidad, "dependencies": [Depends(autorizar)]}

    @app.post("/v1/afinidades", **_RAF)
    def alta_afinidad(c: AltaAfinidad):
        return _comando_afinidad("afinidad_alta", lambda s: serv_afi.alta(
            s, afinidad_id=c.id, tercero_id=c.tercero_id, categoria_id=c.categoria_id))

    @app.post("/v1/afinidades/{afinidad_id}/retirar", **_RAF)
    def retirar_afinidad(afinidad_id: uuid.UUID):
        return _comando_afinidad("afinidad_baja", lambda s: serv_afi.baja(s, afinidad_id=afinidad_id))

    # ------------------------------------------------------------ F05-05 K2 §1.5 Actividad v0
    @app.get("/v1/actividad", response_model=PaginaActividad, dependencies=[Depends(autorizar)])
    def actividad(
        desde: dt.date | None = Query(None), hasta: dt.date | None = Query(None),
        tipo: list[Literal["GASTO", "INGRESO", "TRANSFERENCIA"]] | None = Query(None),
        categoria_id: uuid.UUID | None = Query(None), incluir_subcategorias: bool = Query(True),
        cuenta_id: uuid.UUID | None = Query(None), tercero_id: uuid.UUID | None = Query(None),
        contexto_id: uuid.UUID | None = Query(None), q: str | None = Query(None, max_length=200),
        importe: decimal.Decimal | None = Query(None, max_digits=18, decimal_places=4),
        cursor: str | None = Query(None, max_length=200),
        limite: int = Query(lect_act.LIMITE_POR_DEFECTO, ge=1, le=lect_act.LIMITE_MAXIMO),
    ):
        if desde is not None and hasta is not None and desde > hasta:
            status, cuerpo = eh.rechazo_lectura("ENTRADA_INVALIDA")
            return JSONResponse(cuerpo, status_code=status)
        texto = q.strip() if q else None
        filtros = lect_act.Filtros(desde=desde, hasta=hasta, tipos=tuple(tipo or ()), categoria=categoria_id,
                                   incluir_subcategorias=incluir_subcategorias, cuenta=cuenta_id, tercero=tercero_id,
                                   contexto=contexto_id, q=texto or None, importe=importe)
        if cursor is not None:
            try:
                lect_act.decodificar_cursor(cursor)
            except lect_act.CursorInvalido:
                status, cuerpo = eh.rechazo_lectura("ENTRADA_INVALIDA")
                return JSONResponse(cuerpo, status_code=status)
        return unidad.ejecutar(contexto(), lambda s: lect_act.listar(s, filtros, cursor, limite),
                               nombre="F05-05 actividad")

    @app.get("/v1/actividad/{hecho_id}", response_model=DetalleActividad, dependencies=[Depends(autorizar)])
    def detalle_actividad(hecho_id: uuid.UUID):
        salida = unidad.ejecutar(contexto(), lambda s: lect_act.detalle(s, hecho_id), nombre="F05-05 actividad_detalle")
        if salida is None:
            status, cuerpo = eh.rechazo_lectura("HECHO_NO_ENCONTRADO")
            return JSONResponse(cuerpo, status_code=status)
        return salida

    # ------------------------------------------------------------ F05-05 K2 §1.6 Inicio (D13)
    @app.get("/v1/yo", response_model=Yo, dependencies=[Depends(autorizar)])
    def yo() -> dict:
        return unidad.ejecutar(contexto(), lect_ini.yo, nombre="F05-05 yo")

    @app.get("/v1/inicio/resultado-mes", response_model=ResultadoMes, dependencies=[Depends(autorizar)])
    def resultado_mes(fecha: dt.date = Query(...)):
        return _lectura_con_fecha("resultado_mes", fecha, lambda s: lect_ini.resultado_mes(s, fecha))

    return app


def create_app_desde_entorno() -> FastAPI:
    """Punto de entrada uvicorn --factory. CORS solo por variable explicita."""
    import os

    origenes = tuple(o for o in os.environ.get("GAPTO_DEV_CORS_ORIGINS", "").split(",") if o)
    return create_app(origenes_cors=origenes)
