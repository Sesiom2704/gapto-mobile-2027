# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos.py
# Ruta: backend/app/contratos/modelos.py
# Descripcion: Modelos puros (sin base de datos) de contratos, servicios y terceros (F06-02/03):
#   catalogos cerrados, dataclasses de entrada de los servicios, Rechazo/Resultado y las validaciones PURAS
#   de personas, cláusula y tratamiento de servicios (contrato v1.1 §I y Partes II-III). Nada aqui lee ni
#   escribe la base: los servicios las invocan bajo los locks.
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 3)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.contratos import errores as e

# ---------------------------------------------------------------- catalogos
#: DTO (nombre de producto) -> tipo fisico.
TIPOS_CONTRATO = {"VIVIENDA_COMPLETA": "ALQUILER_VIVIENDA", "HABITACION": "HABITACION", "OTRO": "OTRO"}
TIPO_VIVIENDA, TIPO_HABITACION, TIPO_OTRO = "ALQUILER_VIVIENDA", "HABITACION", "OTRO"
ESTADOS_ALTA = frozenset({"FORMALIZADO", "BORRADOR"})
ROLES = ("PROPIETARIO", "INQUILINO", "AVALISTA", "GESTOR", "AGENCIA", "ADMINISTRADOR")
ROLES_ARRENDADOR = frozenset({"PROPIETARIO", "GESTOR"})
#: D25: principal obligatorio SOLO en estos roles.
ROLES_PRINCIPAL_OBLIGATORIO = frozenset({"PROPIETARIO", "GESTOR", "INQUILINO"})
#: Decision 2 = A: el usuario nunca es agencia ni administrador (D25: tampoco inquilino).
ROLES_PROHIBIDOS_PARA_YO = {"INQUILINO": e.INQUILINO_NO_PUEDE_SER_YO,
                            "AGENCIA": e.ROL_NO_ADMITIDO_PARA_YO, "ADMINISTRADOR": e.ROL_NO_ADMITIDO_PARA_YO}
TIPOS_REVISION = frozenset({"NINGUNA", "IPC", "INDICE", "PORCENTAJE_FIJO", "MANUAL", "OTRO"})
INDICE_IPC = "IPC INE"
TIPOS_SERVICIO = frozenset({"LUZ", "AGUA", "GAS", "INTERNET", "LIMPIEZA", "COMUNIDAD", "SEGURO", "OTRO"})
MODOS_TRATAMIENTO = frozenset({"INCLUIDO", "REPERCUTIDO_FIJO", "POR_FACTURA", "NO_REPERCUTIDO", "SIN_INDICAR"})
ROLES_TERCERO = ("COMERCIO", "ENTIDAD_FINANCIERA", "FINANCIADOR", "INQUILINO", "AVALISTA", "EMPLEADOR",
                 "SUMINISTRADOR", "OBLIGADO_REEMBOLSO", "GESTOR", "ASEGURADORA")
LONGITUD_NOMBRE = 160
LONGITUD_MOTIVO = 200
CIEN = Decimal("100")
DIEZMILESIMA = Decimal("0.0001")
FIN_INFINITO = dt.date.max


# ---------------------------------------------------------------- resultado
@dataclass(frozen=True)
class Rechazo:
    codigo: str
    detalle: dict[str, Any] | None = None


@dataclass(frozen=True)
class Resultado:
    """`dato` es la vista completa del agregado (contrato, servicio o tercero) tras la operacion."""
    dato: dict[str, Any]
    idempotente: bool = False
    modificadas: tuple[uuid.UUID, ...] = field(default_factory=tuple)
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- entrada
@dataclass(frozen=True)
class NuevoTercero:
    id: uuid.UUID
    nombre: str
    naturaleza: str | None = None


@dataclass(frozen=True)
class Persona:
    """actor = YO (yo=True), un tercero existente (tercero_id) o un tercero nuevo (nuevo)."""
    rol: str
    principal: bool = False
    yo: bool = False
    tercero_id: uuid.UUID | None = None
    nuevo: NuevoTercero | None = None
    desde: dt.date | None = None

    @property
    def clave_actor(self) -> str:
        if self.yo:
            return "YO"
        return str(self.nuevo.id if self.nuevo is not None else self.tercero_id)


@dataclass(frozen=True)
class Clausula:
    tipo: str
    indice_referencia: str | None = None
    periodicidad_meses: int | None = None
    fecha_primera_revision: dt.date | None = None
    porcentaje_fijo: Decimal | None = None
    notas: str | None = None


@dataclass(frozen=True)
class Tratamiento:
    servicio_id: uuid.UUID
    modo: str
    inquilino_tercero_id: uuid.UUID | None = None
    porcentaje: Decimal | None = None


# ---------------------------------------------------------------- canonicalizacion (sellado de la intencion)
def texto(valor: Any) -> Any:
    if valor is None or isinstance(valor, (str, int, bool)):
        return valor
    if isinstance(valor, Decimal):
        return str(valor.quantize(DIEZMILESIMA))
    if isinstance(valor, dt.date):
        return valor.isoformat()
    if isinstance(valor, uuid.UUID):
        return str(valor)
    raise TypeError(type(valor))


def persona_canonica(p: Persona) -> dict[str, Any]:
    return {"rol": p.rol, "principal": p.principal, "actor": p.clave_actor, "desde": texto(p.desde),
            "nuevo": None if p.nuevo is None else {"id": str(p.nuevo.id), "nombre": p.nuevo.nombre,
                                                   "naturaleza": p.nuevo.naturaleza}}


def personas_canonicas(personas: list[Persona] | None) -> list[dict[str, Any]] | None:
    if personas is None:
        return None
    return sorted((persona_canonica(p) for p in personas), key=lambda d: (d["rol"], d["actor"]))


def clausula_canonica(c: Clausula | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {"fecha_primera_revision": texto(c.fecha_primera_revision), "indice_referencia": c.indice_referencia,
            "notas": c.notas, "periodicidad_meses": c.periodicidad_meses,
            "porcentaje_fijo": texto(c.porcentaje_fijo), "tipo": c.tipo}


def tratamientos_canonicos(ts: list[Tratamiento] | None) -> list[dict[str, Any]] | None:
    if ts is None:
        return None
    return sorted(({"servicio_id": str(t.servicio_id), "modo": t.modo,
                    "inquilino_tercero_id": texto(t.inquilino_tercero_id), "porcentaje": texto(t.porcentaje)}
                   for t in ts), key=lambda d: d["servicio_id"])


def decimales(valor: Decimal) -> int:
    exponente = valor.as_tuple().exponent
    return -exponente if isinstance(exponente, int) and exponente < 0 else 0


# ---------------------------------------------------------------- validaciones puras de personas (alta, paso 5)
def validar_personas_alta(personas: list[Persona], *, formalizado: bool) -> Rechazo | None:
    """Orden de §I paso 5, solo lo que no necesita base: duplicados, YO prohibido, principales, partes."""
    if any(p.rol not in ROLES for p in personas):
        return Rechazo(e.ROL_DESCONOCIDO)
    if any(int(p.yo) + int(p.tercero_id is not None) + int(p.nuevo is not None) != 1 for p in personas):
        return Rechazo(e.ENTRADA_INVALIDA)
    pares = [(p.clave_actor, p.rol) for p in personas]
    if len(set(pares)) != len(pares):
        return Rechazo(e.PARTICIPANTE_DUPLICADO)
    return None


def validar_yo(personas: list[Persona]) -> Rechazo | None:
    for p in personas:
        if p.yo and p.rol in ROLES_PROHIBIDOS_PARA_YO:
            return Rechazo(ROLES_PROHIBIDOS_PARA_YO[p.rol])
    return None


def validar_principales(personas: list[Persona], *, formalizado: bool) -> Rechazo | None:
    """Mas de un principal por rol -> PRINCIPAL_DUPLICADO; PROPIETARIO/GESTOR/INQUILINO con personas y sin
    principal -> PRINCIPAL_REQUERIDO (D25); partes para formalizar (AGENCIA y ADMINISTRADOR nunca cuentan)."""
    por_rol: dict[str, list[Persona]] = {}
    for p in personas:
        por_rol.setdefault(p.rol, []).append(p)
    if any(sum(1 for p in ps if p.principal) > 1 for ps in por_rol.values()):
        return Rechazo(e.PRINCIPAL_DUPLICADO)
    if any(rol in ROLES_PRINCIPAL_OBLIGATORIO and not any(p.principal for p in ps) for rol, ps in por_rol.items()):
        return Rechazo(e.PRINCIPAL_REQUERIDO)
    if formalizado:
        return partes_para_formalizar(set(por_rol), {r for r, ps in por_rol.items() if any(p.principal for p in ps)})
    return None


def partes_para_formalizar(roles: set[str], roles_con_principal: set[str]) -> Rechazo | None:
    """(PROPIETARIO o GESTOR) e INQUILINO principal; AGENCIA/ADMINISTRADOR no cuentan (Q-T3D-21)."""
    if not (roles & ROLES_ARRENDADOR) or "INQUILINO" not in roles_con_principal:
        return Rechazo(e.FALTAN_PARTES_PARA_FORMALIZAR)
    return None


# ---------------------------------------------------------------- clausula (C-REV-01)
def validar_clausula(c: Clausula) -> Rechazo | dict[str, Any]:
    """Devuelve las columnas de la fila o el rechazo. IPC fija el indice «IPC INE» si no viene."""
    if c.tipo not in TIPOS_REVISION:
        return Rechazo(e.ENTRADA_INVALIDA)
    if c.periodicidad_meses is not None and c.periodicidad_meses <= 0:
        return Rechazo(e.ENTRADA_INVALIDA)
    if c.porcentaje_fijo is not None and (c.porcentaje_fijo < 0 or c.porcentaje_fijo > Decimal("99999.9999")
                                          or decimales(c.porcentaje_fijo) > 4):
        return Rechazo(e.ENTRADA_INVALIDA)
    if c.tipo == "PORCENTAJE_FIJO" and c.porcentaje_fijo is None:
        return Rechazo(e.CLAUSULA_INCOMPLETA)
    if c.tipo == "NINGUNA" and (c.indice_referencia or c.periodicidad_meses is not None
                                or c.porcentaje_fijo is not None or c.fecha_primera_revision is not None):
        return Rechazo(e.CLAUSULA_INCOMPLETA)
    indice = c.indice_referencia
    if c.tipo == "IPC" and not indice:
        indice = INDICE_IPC
    return {"tipo_revision": c.tipo, "indice_referencia": indice, "periodicidad_meses": c.periodicidad_meses,
            "porcentaje_fijo": c.porcentaje_fijo, "notas": c.notas, "fecha_primera_revision": c.fecha_primera_revision}


# ---------------------------------------------------------------- tratamiento de servicios (C-SRV-04)
def columnas_tratamiento(modo: str, actor_id: uuid.UUID | None, porcentaje: Decimal | None) -> dict[str, Any] | Rechazo:
    """Fila de `contrato_servicios` para el modo (M-9). El writer exige % > 0 en FIJO aunque el CHECK admita 0."""
    if modo == "INCLUIDO":
        if actor_id is not None or porcentaje is not None:
            return Rechazo(e.TRATAMIENTO_INCOMPATIBLE)
        return {"incluido_en_renta": True, "repercutible": False, "modo_reparto": None,
                "actor_repercusion_id": None, "porcentaje_repercutible": None}
    if modo == "NO_REPERCUTIDO":
        if actor_id is not None or porcentaje is not None:
            return Rechazo(e.TRATAMIENTO_INCOMPATIBLE)
        return {"incluido_en_renta": False, "repercutible": False, "modo_reparto": None,
                "actor_repercusion_id": None, "porcentaje_repercutible": None}
    if modo == "REPERCUTIDO_FIJO":
        if porcentaje is None or porcentaje <= 0 or porcentaje > CIEN or decimales(porcentaje) > 4:
            return Rechazo(e.TRATAMIENTO_INCOMPATIBLE)
        return {"incluido_en_renta": False, "repercutible": True, "modo_reparto": "FIJO",
                "actor_repercusion_id": actor_id, "porcentaje_repercutible": porcentaje}
    if modo == "POR_FACTURA":
        if porcentaje is not None:
            return Rechazo(e.TRATAMIENTO_INCOMPATIBLE)
        return {"incluido_en_renta": False, "repercutible": True, "modo_reparto": "POR_FACTURA",
                "actor_repercusion_id": actor_id, "porcentaje_repercutible": None}
    return Rechazo(e.ENTRADA_INVALIDA)


# ---------------------------------------------------------------- intervalos
def intervalo_solapa(a_desde: dt.date, a_hasta: dt.date | None, b_desde: dt.date, b_hasta: dt.date | None) -> bool:
    """Intervalos inclusivos con fin abierto (None = sin fin)."""
    return a_desde <= (b_hasta or FIN_INFINITO) and b_desde <= (a_hasta or FIN_INFINITO)


def cubre(intervalos: list[tuple[dt.date, dt.date | None]], desde: dt.date, hasta: dt.date | None) -> bool:
    """True si la union de los intervalos inclusivos cubre [desde, hasta] sin huecos (hasta None = sin fin)."""
    limite = hasta or FIN_INFINITO
    cursor = desde
    for d, h in sorted(intervalos, key=lambda x: x[0]):
        if d > cursor:
            return False
        fin = h or FIN_INFINITO
        if fin >= cursor:
            if fin >= limite:
                return True
            cursor = fin + dt.timedelta(days=1)
    return cursor > limite
