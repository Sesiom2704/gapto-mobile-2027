# ============================================================
# GAPTO MOBILE 2027
# Fichero: peticion.py
# Ruta: backend/app/core/peticion.py
# Descripcion: Estado de una peticion HTTP para AJ-05 (F06 T4; diseno v0.2 §3, §5.2-§5.4; dictamen R2
#   AJ-R2-01/02/05/06). Lo crea el middleware ASGI al entrar (`iniciar`) y lo consulta la unidad de trabajo
#   (`actual`). Fuera de una peticion HTTP (tests de servicio, scripts) no hay estado y la unidad de trabajo se
#   comporta exactamente como antes de AJ-05.
#
#   - Deadline monotonico UNICO por peticion: se calcula al entrar y nunca se reinicia (ni entre unidades, ni entre
#     reintentos, ni en el backoff). Plazos candidatos: A = 8 s, B = 40 s (mandato §3.1; se fijan con mediciones).
#   - Seguimiento transaccional EXPLICITO y ACUMULADO por peticion (AJ-R2-01/02): cada intento de cada unidad deja su
#     estado; ninguna unidad nueva borra el de otra. `pg_current_xact_id_if_assigned()` es solo evidencia auxiliar.
#   - `PlazoAgotado` es una excepcion propia, FUERA de `ErrorMotor`: ninguna envoltura de ruta que capture
#     `ErrorMotor` la puede convertir en un rechazo 4xx. La traduce un unico manejador global.
# Version: 0.1.0 (F06 T4 · AJ-05 ampliado + R-C7-07, mandato b4ff6b70…, adenda 01 24113472… y adenda 02 9744307e…)
# ============================================================

from __future__ import annotations

import contextvars
import enum
import math
import re
import time
import uuid
from dataclasses import dataclass, field

# Plazos del perfil BETA_LOCAL (adenda 01 al mandato, 24113472…; dictamen R3 AJ-R3-01/02): backend y PostgreSQL en el
# mismo PC. NO certifican el perfil BACKEND_REMOTO_NEON (pendiente, deuda D-AJ05-HOST). Cliente: A 10 s, B 45 s.
PLAZO_CLASE_S: dict[str, float] = {"A": 8.0, "B": 40.0}
# lock_timeout por clase (mandato §3.3): 3 s en A; 0 EXPLICITO en B (no hereda nada de sesion ni de rol).
LOCK_TIMEOUT_CLASE_MS: dict[str, int] = {"A": 3000, "B": 0}
# Ningun intento empieza con menos de esto (diseno §3; dictamen R2, objecion 3).
MINIMO_PARA_INTENTO_S = 0.5
# Margen de transaction_timeout sobre el restante (adenda 02 §1.3 y §3, AJ-R4-03: >= 3 x COMMIT maximo medido en
# BETA_LOCAL = 3 x 0,301 s (compra de 360 cuotas) = 0,90 s). Compatible con los plazos: A 8 + 1 = 9 s < cliente 10 s;
# B 40 + 1 = 41 s < cliente 45 s. El COMMIT con triggers diferidos SOLO lo acota este limite (el statement_timeout no lo
# corta): un corte de sesion (25P04) durante el COMMIT es COMMIT_INDETERMINADO -> RESULTADO_NO_CONFIRMADO.
MARGEN_TRANSACTION_TIMEOUT_S = 1.0
CONNECT_TIMEOUT_MAX_S = 5
# Un 57014 solo es del propio statement_timeout si llega cuando el deadline ya esta (casi) cumplido: la unidad fija
# statement_timeout = restante al empezar, asi que una sentencia no puede agotarlo antes. Margen de reloj.
TOLERANCIA_DEADLINE_S = 0.05

# Clase B (mandato §3.1): el POST de la compra y el de la revision del tipo. Todo lo demas es A.
_CLASE_B = (
    ("POST", re.compile(r"^/v1/propiedades/[^/]+/compra$")),
    ("POST", re.compile(r"^/v1/hipotecas/[^/]+/revision$")),
)
PLANTILLAS_CLASE_B = ("POST /v1/propiedades/{propiedad_id}/compra", "POST /v1/hipotecas/{financiacion_id}/revision")


def clase_de(metodo: str, ruta: str) -> str:
    """Clase provisional por metodo y ruta (antes del enrutado)."""
    for m, patron in _CLASE_B:
        if metodo == m and patron.match(ruta):
            return "B"
    return "A"


class EstadoUnidad(str, enum.Enum):
    """Estados de un intento de unidad de trabajo (AJ-R2-02; mandato §3.4)."""

    SIN_ESCRITURA_POSIBLE = "SIN_ESCRITURA_POSIBLE"   # declarada solo_lectura: READ ONLY antes de cualquier consulta
    ESCRITURA_POSIBLE = "ESCRITURA_POSIBLE"           # potencialmente persistente, en curso
    COMMIT_INICIADO = "COMMIT_INICIADO"               # la operacion termino; el COMMIT esta en vuelo
    COMMIT_CONFIRMADO = "COMMIT_CONFIRMADO"           # el servidor confirmo el COMMIT
    COMMIT_INDETERMINADO = "COMMIT_INDETERMINADO"     # se perdio la conexion o se corto la sesion durante el COMMIT
    ROLLBACK_CONFIRMADO = "ROLLBACK_CONFIRMADO"       # error SQL del servidor antes o durante el COMMIT: abortada
    ABORTADA_SIN_COMMIT = "ABORTADA_SIN_COMMIT"       # no llego a conectar: ni la operacion empezo (no confirma)
    CORTE_ANTES_DEL_COMMIT = "CORTE_ANTES_DEL_COMMIT" # conectada, se perdio la conexion o se corto la sesion (25P04)
                                                      # antes de pedir el COMMIT: diseno §5.2, indeterminado


@dataclass(slots=True)
class RegistroIntento:
    numero: int
    estado: EstadoUnidad
    solo_lectura: bool
    sqlstate: str | None = None
    conexion_ms: float | None = None
    transaccion_ms: float | None = None
    commit_ms: float | None = None
    xid_auxiliar: bool | None = None   # evidencia auxiliar (nunca criterio): XID asignado antes del COMMIT


@dataclass(slots=True)
class RegistroUnidad:
    nombre: str
    audit_request_id: str
    solo_lectura: bool
    intentos: list[RegistroIntento] = field(default_factory=list)


class Persistencia(str, enum.Enum):
    """Resumen ACUMULADO de la peticion (diseno §5.3 con AJ-R2-01/02)."""

    NINGUNA = "NINGUNA"
    COMMIT_INDETERMINADO = "COMMIT_INDETERMINADO"
    ESCRITURA_INTERRUMPIDA = "ESCRITURA_INTERRUMPIDA"   # corte antes del COMMIT en una unidad potencialmente
                                                        # persistente: conservador, nunca «no guardado»
    ESCRITURA_CONFIRMADA = "ESCRITURA_CONFIRMADA"


@dataclass(slots=True)
class EstadoPeticion:
    http_request_id: uuid.UUID
    clase: str
    t0: float
    deadline: float
    unidades: list[RegistroUnidad] = field(default_factory=list)
    anomalias: list[str] = field(default_factory=list)

    def restante(self) -> float:
        return self.deadline - time.monotonic()

    def fuera_de_plazo(self) -> bool:
        return time.monotonic() > self.deadline

    def lock_timeout_ms(self) -> int:
        return LOCK_TIMEOUT_CLASE_MS[self.clase]

    def persistencia(self) -> Persistencia:
        """Confirmada si ALGUN intento de alguna unidad potencialmente persistente confirmo; si no, indeterminada si
        alguno quedo indeterminado. Acumulado: nada posterior lo rebaja."""
        estados = [i.estado for u in self.unidades if not u.solo_lectura for i in u.intentos]
        if EstadoUnidad.COMMIT_CONFIRMADO in estados:
            return Persistencia.ESCRITURA_CONFIRMADA
        if EstadoUnidad.COMMIT_INDETERMINADO in estados:
            return Persistencia.COMMIT_INDETERMINADO
        if EstadoUnidad.CORTE_ANTES_DEL_COMMIT in estados:
            return Persistencia.ESCRITURA_INTERRUMPIDA
        return Persistencia.NINGUNA

    def connect_timeout_s(self) -> int:
        """`connect_timeout = min(5, restante)` en segundos enteros de libpq (al menos 1)."""
        return max(1, min(CONNECT_TIMEOUT_MAX_S, math.ceil(self.restante())))


_ACTUAL: contextvars.ContextVar[EstadoPeticion | None] = contextvars.ContextVar("gapto_peticion", default=None)


def actual() -> EstadoPeticion | None:
    return _ACTUAL.get()


def iniciar(metodo: str, ruta: str, *, ahora: float | None = None) -> tuple[EstadoPeticion, contextvars.Token]:
    t0 = time.monotonic() if ahora is None else ahora
    clase = clase_de(metodo, ruta)
    estado = EstadoPeticion(http_request_id=uuid.uuid4(), clase=clase, t0=t0, deadline=t0 + PLAZO_CLASE_S[clase])
    return estado, _ACTUAL.set(estado)


def terminar(token: contextvars.Token) -> None:
    _ACTUAL.reset(token)


class PlazoAgotado(Exception):
    """Plazo de la peticion agotado (diseno §5.2 y §5.4). NO es un `ErrorMotor`.

    `motivo`: SIN_PLAZO_PARA_INTENTO (ningun intento empieza con menos de 0,5 s), STATEMENT_TIMEOUT (57014 del
    statement_timeout que fijo la propia unidad) o LOCK_TIMEOUT (55P03 del lock_timeout que fijo la propia unidad).
    El desenlace HTTP lo decide el manejador global con la persistencia ACUMULADA de la peticion.
    """

    def __init__(self, motivo: str, *, sqlstate: str | None = None, unidad: str | None = None) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.sqlstate = sqlstate
        self.unidad = unidad
