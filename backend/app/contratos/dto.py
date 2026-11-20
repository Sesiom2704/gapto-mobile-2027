# ============================================================
# GAPTO MOBILE 2027
# Fichero: dto.py
# Ruta: backend/app/contratos/dto.py
# Descripcion: DTO HTTP de F06-02/03 (contrato v1.1 Partes I-III y V; PA-20: escrituras con POST). Todos
#   estrictos (`extra="forbid"`). Los campos `renta` y `fianza` SE DECLARAN a proposito (como `dict | None`) para
#   que su presencia llegue al servicio y se rechace con RENTA_NO_DISPONIBLE (R-E-01) en su lugar del orden de
#   validaciones, en vez del 422 generico de `extra="forbid"`. Los terceros nuevos llevan `id` de cliente (como
#   AltaTercero de F05): el replay es determinista.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, pasos 3 y 4)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.contratos import modelos as m

TipoContrato = Literal["VIVIENDA_COMPLETA", "HABITACION", "OTRO"]
EstadoAlta = Literal["FORMALIZADO", "BORRADOR"]
RolParticipante = Literal["PROPIETARIO", "INQUILINO", "AVALISTA", "GESTOR", "AGENCIA", "ADMINISTRADOR"]
TipoRevision = Literal["NINGUNA", "IPC", "INDICE", "PORCENTAJE_FIJO", "MANUAL", "OTRO"]
ModoTratamiento = Literal["INCLUIDO", "REPERCUTIDO_FIJO", "POR_FACTURA", "NO_REPERCUTIDO", "SIN_INDICAR"]
TipoServicio = Literal["LUZ", "AGUA", "GAS", "INTERNET", "LIMPIEZA", "COMUNIDAD", "SEGURO", "OTRO"]
LONGITUD_NOMBRE = 160
LONGITUD_MOTIVO = 200


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NuevoTerceroDto(_Estricto):
    id: uuid.UUID
    nombre: str = Field(max_length=LONGITUD_NOMBRE * 2)
    naturaleza: Literal["PERSONA", "EMPRESA", "ORGANISMO", "OTRO"] | None = None


class ActorTerceroDto(_Estricto):
    tercero_id: uuid.UUID


class ActorNuevoDto(_Estricto):
    nuevo_tercero: NuevoTerceroDto


class PersonaDto(_Estricto):
    """actor: «YO», {tercero_id} o {nuevo_tercero}."""
    actor: Literal["YO"] | ActorTerceroDto | ActorNuevoDto
    rol: RolParticipante
    principal: StrictBool = False

    def a_modelo(self, desde: dt.date | None = None) -> m.Persona:
        if self.actor == "YO":
            return m.Persona(rol=self.rol, principal=self.principal, yo=True, desde=desde)
        if isinstance(self.actor, ActorTerceroDto):
            return m.Persona(rol=self.rol, principal=self.principal, tercero_id=self.actor.tercero_id, desde=desde)
        nt = self.actor.nuevo_tercero
        return m.Persona(rol=self.rol, principal=self.principal, desde=desde,
                         nuevo=m.NuevoTercero(id=nt.id, nombre=nt.nombre, naturaleza=nt.naturaleza))


class ClausulaDto(_Estricto):
    tipo: TipoRevision
    indice_referencia: str | None = Field(default=None, max_length=80)
    periodicidad_meses: int | None = None
    fecha_primera_revision: dt.date | None = None
    porcentaje_fijo: decimal.Decimal | None = None
    notas: str | None = Field(default=None, max_length=4000)

    def a_modelo(self) -> m.Clausula:
        return m.Clausula(tipo=self.tipo, indice_referencia=self.indice_referencia,
                          periodicidad_meses=self.periodicidad_meses,
                          fecha_primera_revision=self.fecha_primera_revision, porcentaje_fijo=self.porcentaje_fijo,
                          notas=self.notas)


class TratamientoDto(_Estricto):
    """Forma del cliente: `actor` = {tercero_id} (INQUILINO vigente); `inquilino_tercero_id` tambien se admite."""
    servicio_id: uuid.UUID
    modo: ModoTratamiento
    actor: ActorTerceroDto | None = None
    inquilino_tercero_id: uuid.UUID | None = None
    porcentaje: decimal.Decimal | None = None
    desde: dt.date | None = None

    def inquilino(self) -> uuid.UUID | None:
        return self.actor.tercero_id if self.actor is not None else self.inquilino_tercero_id

    def a_modelo(self) -> m.Tratamiento:
        return m.Tratamiento(servicio_id=self.servicio_id, modo=self.modo,
                             inquilino_tercero_id=self.inquilino(), porcentaje=self.porcentaje)


# ------------------------------------------------------------------ contratos
class AltaContrato(_Estricto):
    """C-CON-01. `renta` y `fianza` se declaran solo para rechazarlos con RENTA_NO_DISPONIBLE."""
    intencion_id: uuid.UUID
    propiedad_id: uuid.UUID
    tipo: TipoContrato
    habitacion: int | None = None
    nombre: str = Field(max_length=LONGITUD_NOMBRE * 2)
    fecha_inicio: dt.date | None = None
    fecha_fin_prevista: dt.date | None = None
    estado: EstadoAlta
    personas: list[PersonaDto] | None = Field(default=None, max_length=50)
    clausula_revision: ClausulaDto | None = None
    servicios: list[TratamientoDto] | None = Field(default=None, max_length=50)
    notas: str | None = Field(default=None, max_length=4000)
    renta: dict | None = None
    fianza: dict | None = None

    def renta_presente(self) -> bool:
        return "renta" in self.model_fields_set or "fianza" in self.model_fields_set


class NuevoContratoSucesor(_Estricto):
    """`nuevo` de C-CON-05: AltaContrato sin `propiedad_id`, `tipo` ni `habitacion` (se heredan)."""
    nombre: str = Field(max_length=LONGITUD_NOMBRE * 2)
    fecha_inicio: dt.date | None = None
    fecha_fin_prevista: dt.date | None = None
    estado: EstadoAlta
    personas: list[PersonaDto] | None = Field(default=None, max_length=50)
    clausula_revision: ClausulaDto | None = None
    servicios: list[TratamientoDto] | None = Field(default=None, max_length=50)
    notas: str | None = Field(default=None, max_length=4000)
    renta: dict | None = None
    fianza: dict | None = None

    def renta_presente(self) -> bool:
        return "renta" in self.model_fields_set or "fianza" in self.model_fields_set


class EditarContrato(_Estricto):
    """C-CON-02: solo los campos presentes cambian. `propiedad_id` y `tipo` se declaran para devolver
    CAMPO_INMUTABLE (y no el 422 generico)."""
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)
    nombre: str | None = Field(default=None, max_length=LONGITUD_NOMBRE * 2)
    notas: str | None = Field(default=None, max_length=4000)
    fecha_inicio: dt.date | None = None
    fecha_fin_prevista: dt.date | None = None
    habitacion: int | None = None
    propiedad_id: uuid.UUID | None = None
    tipo: TipoContrato | None = None


CAMPOS_EDITAR_CONTRATO = ("nombre", "notas", "fecha_inicio", "fecha_fin_prevista", "habitacion")
CAMPOS_INMUTABLES = ("propiedad_id", "tipo")


class TerminarContrato(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    fecha_fin_real: dt.date


class CorregirTerminacion(TerminarContrato):
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)


class VersionContrato(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)


class CancelarContrato(VersionContrato):
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)


class SucesorContrato(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    fecha_fin_real: dt.date
    nuevo: NuevoContratoSucesor


class AnadirPersona(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    actor: Literal["YO"] | ActorTerceroDto | ActorNuevoDto
    rol: RolParticipante
    principal: StrictBool = False
    desde: dt.date


class CerrarPersona(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    hasta: dt.date
    nuevo_principal: uuid.UUID | None = None      # id de la fila de participante que pasa a ser principal


class CorregirPersona(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)
    desde: dt.date | None = None
    hasta: dt.date | None = None
    principal: StrictBool | None = None


class NuevaClausula(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    desde: dt.date
    clausula: ClausulaDto


class CorregirClausula(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)
    clausula: ClausulaDto


# ------------------------------------------------------------------ servicios
class AltaServicio(_Estricto):
    intencion_id: uuid.UUID
    tipo_servicio: TipoServicio
    nombre: str = Field(max_length=LONGITUD_NOMBRE * 2)
    categoria_default_id: uuid.UUID | None = None
    propiedad_id: uuid.UUID | None = None
    desde: dt.date | None = None
    notas: str | None = Field(default=None, max_length=4000)


class EditarServicio(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    nombre: str | None = Field(default=None, max_length=LONGITUD_NOMBRE * 2)
    categoria_default_id: uuid.UUID | None = None
    notas: str | None = Field(default=None, max_length=4000)


class BajaServicio(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    fecha_fin_real: dt.date


class TratamientoContrato(_Estricto):
    """C-SRV-04. Forma del cliente: `tratamiento` anidado {servicio_id, modo, actor, porcentaje, desde}; tambien se
    admite la forma plana (modo, inquilino_tercero_id, porcentaje, desde)."""
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    tratamiento: TratamientoDto | None = None
    modo: ModoTratamiento | None = None
    inquilino_tercero_id: uuid.UUID | None = None
    porcentaje: decimal.Decimal | None = None
    desde: dt.date | None = None
    corregir: StrictBool = False
    motivo: str | None = Field(default=None, max_length=LONGITUD_MOTIVO)

    def plano(self):
        if self.tratamiento is not None:
            tr = self.tratamiento
            return tr.modo, tr.inquilino(), tr.porcentaje, tr.desde
        return self.modo, self.inquilino_tercero_id, self.porcentaje, self.desde


# ------------------------------------------------------------------ terceros
class AnadirRoles(_Estricto):
    """C-TER-01: `anadir` (no el conjunto completo). `quitar` se declara para devolver RETIRADA_NO_ADMITIDA."""
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    anadir: list[str] = Field(default_factory=list, max_length=20)
    quitar: list[str] | None = None


class AsignarClasificaciones(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    anadir: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    principal: uuid.UUID | None = None
    quitar: list[uuid.UUID] | None = None


class AltaClasificacion(_Estricto):
    intencion_id: uuid.UUID                      # = clasificaciones_tercero.id
    nombre: str = Field(max_length=200)
    parent_id: uuid.UUID | None = None


class RenombrarClasificacion(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    nombre: str = Field(max_length=200)


class MoverClasificacion(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)
    parent_id: uuid.UUID | None = None


class EstadoClasificacion(_Estricto):
    intencion_id: uuid.UUID
    row_version_esperada: int = Field(ge=1)


def presentes(c: BaseModel, campos: tuple[str, ...]) -> dict:
    """Solo los campos que la peticion trae (omitido = no cambia)."""
    return {n: v for n, v in c.model_dump().items() if n in campos and n in c.model_fields_set}
