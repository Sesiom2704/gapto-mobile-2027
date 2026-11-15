# ============================================================
# GAPTO MOBILE 2027
# Fichero: propiedad_registro.py
# Ruta: backend/app/api/propiedad_registro.py
# Descripcion: F06 T2-F06 CAT-VIV · bloque `propiedad` de los registros de gasto de F05 (L-04; Q-CV-02 variante (a);
#   OBL-VIV-01; mandato CAT-VIV v1.1 §2.4). API DE INTEGRACION F05, PENDIENTE DE CONSOLIDACION F10.
#
#   Con el bloque, el writer de F05 conserva su composicion (C07 y magnitudes, comercio, contexto, etiquetas,
#   prevision) y este modulo le anade:
#     - AFECTA_A PRINCIPAL DE NIVEL EFECTO a la propiedad, con id uuid5(intencion, PREFIJO_RG + "afecta_a"): marca
#       de procedencia propia del registro de gasto (no exige tocar B3; L-GASTO-PROPIEDAD no la lista: D-CV-04);
#     - VS-01: atribucion M-2 por la titularidad de la PROPIEDAD en la fecha del hecho (propuesta_vista releida
#       bajo el lock: ATRIBUCION_PROPUESTA_DESFASADA / TITULARIDAD_NO_DISPONIBLE_EN_FECHA; MANUAL o NO_LO_SE;
#       nunca 100 % mio por defecto) y quien pago y quien debe con el componedor de PAG (patrimonio/pagos.py,
#       sin modificarlo), con confirmacion verificable (posiciones_confirmadas);
#     - M3 (L-04b no firmada): solo el vinculo y la vigencia de la propuesta vista; M3 compone con sus reglas.
#   Clase: GASTO_CORRIENTE o REPARACION, no se persiste; nunca MEJORA: el gasto no entra en L-COSTE.
#
#   Orden de locks con propiedad (§2.4.5): advisory raiz -> INVERSIONES -> propiedad FOR SHARE -> cuenta ->
#   identidad -> categoria (C-a + exigir_propiedad, FOR SHARE) -> C07 -> tercero y contexto -> terceros de pagos y
#   saldos -> relectura de la titularidad -> OP-22. Sin el bloque, el writer no llama a nada de este modulo.
# Version: 0.1.0 (F06 T2-F06 CAT-VIV N1)
# ============================================================

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from decimal import Decimal

from app.core.modelos_compuesto import DatosContextoHecho, DatosEntidadHecho, DatosHechoCompuesto
from app.core.unidad_trabajo import SesionMotor
from app.patrimonio import atribucion as m2
from app.patrimonio import gasto_propiedad as gp
from app.patrimonio import pagos as pag

PREFIJO_RG = "gapto.f06.registro_gasto."
CENT = Decimal("0.01")


def ident(iid: uuid.UUID, rol: str) -> uuid.UUID:
    return uuid.uuid5(iid, PREFIJO_RG + rol)


def _dump(lista) -> list[dict]:
    return [x.model_dump() for x in lista]


def afecta_a(datos: DatosHechoCompuesto, iid: uuid.UUID, propiedad_id: uuid.UUID) -> DatosHechoCompuesto:
    """Anade el AFECTA_A principal de nivel efecto (efecto unico del gasto) sin tocar el resto del contexto."""
    efecto = datos.efectos[0]
    vinculo = DatosEntidadHecho(registro_id=ident(iid, "afecta_a"), entidad_id=propiedad_id, tipo_relacion="AFECTA_A",
                                principal=True, efecto_id=efecto.efecto_id)
    contexto = datos.contexto or DatosContextoHecho()
    return dataclasses.replace(datos, contexto=dataclasses.replace(
        contexto, entidades=[*contexto.entidades, vinculo]))


def bloquear(sesion: SesionMotor, propiedad_id: uuid.UUID) -> dict | None:
    """Propiedad FOR SHARE (nivel de B3), antes de la cuenta."""
    return gp.bloquear_propiedad_compartida(sesion, propiedad_id)


def revalidar_propiedad(sesion: SesionMotor, raiz: dict, propiedad_id: uuid.UUID, hoy: dt.date) -> str | None:
    """Intencion nueva, bajo el lock: disponible y no DE_OTROS (M-8 de B3: OPERACION_NO_PERMITIDA_EN_ESTADO)."""
    if not gp.disponible(raiz):
        return gp.PROPIEDAD_NO_DISPONIBLE
    if gp.de_otros(sesion, propiedad_id, hoy):
        return gp.NO_PERMITIDA_EN_ESTADO
    return None


# ------------------------------------------------------------------ VS-01
def _atr(intencion) -> dict:
    return intencion.propiedad.atribucion.model_dump()


def pagos_vs01(intencion) -> list[dict]:
    return _dump(intencion.propiedad.pagos)


def partes_peticion(intencion) -> list[tuple[uuid.UUID, Decimal]] | None:
    atr = _atr(intencion)
    return None if atr["modo"] == m2.NO_LO_SE else gp._partes_peticion(atr)


def yo_pago(intencion) -> bool:
    return pag.mi_pago(pagos_vs01(intencion)) is not None


def validar_pura_vs01(intencion, yo: uuid.UUID) -> str | None:
    """Antes de los locks: forma de la atribucion y del bloque de PAG; mi pago sale de la cuenta de VS-01."""
    atr = _atr(intencion)
    forma = m2.validar_forma(atr, criterio=gp.CRITERIO_HECHO, fecha_referencia=intencion.fecha_hecho)
    if forma:
        return forma
    b = intencion.propiedad
    mio = pag.mi_pago(pagos_vs01(intencion))
    if mio is not None and uuid.UUID(str(mio["cuenta_id"])) != intencion.cuenta_id:
        return pag.ENTRADA_INVALIDA
    return pag.validar(importe=Decimal(str(intencion.importe)).quantize(CENT), partes=partes_peticion(intencion),
                       yo=yo, pagos=pagos_vs01(intencion), saldos=_dump(b.saldos),
                       confirmadas=_dump(b.posiciones_confirmadas))


def revalidar_vs01(sesion: SesionMotor, intencion, yo: uuid.UUID) -> str | tuple:
    """Bajo los locks, tras C-a/C07/tercero/contexto: terceros de pagos y saldos y relectura M-2.
    Devuelve el codigo de rechazo o ("PARTES", partes) con partes None = NO_LO_SE."""
    b = intencion.propiedad
    ps, ss = pagos_vs01(intencion), _dump(b.saldos)
    rechazo = gp._guardas_v2_terceros(sesion, {"pagos": ps, "saldos": ss})
    if rechazo:
        return rechazo
    partes = m2.resolver(sesion, b.propiedad_id, _atr(intencion))
    if isinstance(partes, str):
        return partes
    if partes is None:                       # NO_LO_SE: pagadores contra la titularidad en la fecha (Q-PAG-09)
        titulares = {x["actor_id"] for x in m2.titularidad_en_fecha(sesion, b.propiedad_id, intencion.fecha_hecho)}
        if not set(pag.pagadores_otros(ps)) <= titulares:
            return pag.ENTRADA_INVALIDA
    return ("PARTES", partes)


def componer_vs01(datos: DatosHechoCompuesto, intencion, yo: uuid.UUID, partes) -> DatosHechoCompuesto:
    """Solo desde la peticion sellada (un replay compone lo mismo): VS-01 + M-2 + pagos/aportaciones/posiciones +
    AFECTA_A. Los pagos y aportaciones de VS-01 se sustituyen por los del bloque (no hay dos fuentes)."""
    iid = intencion.intencion_id
    b = intencion.propiedad
    efecto = datos.efectos[0]
    estado, filas = m2.filas(efecto.efecto_id, Decimal(str(efecto.importe_delta)).quantize(CENT), partes,
                             _atr(intencion)["modo"], PREFIJO_RG + "atribucion:")
    efecto = dataclasses.replace(efecto, estado_atribucion=estado, atribuciones=filas)
    pg, ap, po = pag.componer(iid=iid, ident=lambda rol: ident(iid, rol), fecha=intencion.fecha_hecho,
                              nota=intencion.concepto, pagos=pagos_vs01(intencion), saldos=_dump(b.saldos), yo=yo)
    datos = dataclasses.replace(datos, efectos=[efecto, *datos.efectos[1:]], pagos=pg, aportaciones=ap,
                                posiciones=[*datos.posiciones, *po])
    return afecta_a(datos, iid, b.propiedad_id)


# ------------------------------------------------------------------ M3 (sin componedor; L-04b no firmada)
def validar_pura_m3(bloque, fecha_hecho: dt.date) -> str | None:
    vista = bloque.propuesta_vista
    if vista is None:
        return None
    if vista.criterio != gp.CRITERIO_HECHO or vista.fecha_referencia != fecha_hecho:
        return m2.ENTRADA_INVALIDA
    return None


def revalidar_m3(sesion: SesionMotor, bloque, fecha_hecho: dt.date) -> str | None:
    """La titularidad en la fecha PROPONE las partes de M3 (en el cliente); bajo el lock solo se exige que la
    propuesta vista siga siendo la vigente: con titularidad y sin propuesta, o distinta -> DESFASADA; con
    propuesta y sin titularidad -> TITULARIDAD_NO_DISPONIBLE_EN_FECHA. Las partes y posiciones son las de M3."""
    vigente = sorted(((x["actor_id"], x["porcentaje"]) for x in
                      m2.titularidad_en_fecha(sesion, bloque.propiedad_id, fecha_hecho)), key=lambda x: str(x[0]))
    vista = bloque.propuesta_vista
    if vista is None:
        return m2.PROPUESTA_DESFASADA if vigente else None
    if not vigente:
        return m2.TITULARIDAD_NO_DISPONIBLE
    if vigente != m2._partes([p.model_dump() for p in vista.partes]):
        return m2.PROPUESTA_DESFASADA
    return None
