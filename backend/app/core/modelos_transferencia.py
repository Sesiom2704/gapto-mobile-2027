# ============================================================
# GAPTO MOBILE 2027
# Fichero: modelos_transferencia.py
# Ruta: backend/app/core/modelos_transferencia.py
# Descripcion: F04-06 / B1. DTO de entrada y salida de OP-10.
#
#   SEIS IDENTIDADES RESERVADAS. Una transferencia crea seis filas en tres
#   tablas raiz y dos tablas hijas. Las seis identidades se reservan ANTES del
#   primer intento y se reutilizan en cualquier retry: es lo que hace seguro
#   repetir la operacion despues de un 40P01 con resultado desconocido.
#
#   LOS IMPORTES SE DECLARAN COMO MAGNITUDES POSITIVAS. El signo lo pone el
#   motor: salida negativa, entrada positiva. Pedir al llamante que envie el
#   signo correcto seria delegar en el una invariante fisica, y un signo
#   invertido produciria una transferencia que PostgreSQL rechaza al COMMIT con
#   un mensaje que no es contrato.
#
#   NO EXISTE `comision`. El campo se acepta solo para RECHAZARLO: una comision
#   real es su propia realidad economica, con su hecho y su efecto. Admitirla
#   aqui la escondaria dentro de una operacion que es economicamente neutra.
#
#   NO EXISTE `owner_user_id`: el tenant llega por ContextoOperacion y lo impone
#   RLS. Aceptarlo seria un parametro falsificable.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Final

CERO: Final = decimal.Decimal("0")

# Tipo de hecho canonico de una transferencia. No se reclasifica nunca de forma
# automatica: F04-D031 lo prohibe expresamente para salvar una invariante.
TIPO_HECHO_TRANSFERENCIA: Final = "TRANSFERENCIA"

# Clase de movimiento de una transferencia ordinaria. AJUSTE_SALDO describe una
# correccion de saldo, no dinero que se mueve entre cuentas propias.
CLASE_OPERACION: Final = "OPERACION"


@dataclass(frozen=True, slots=True)
class DatosTransferencia:
    """Entrada de OP-10.

    `importe_salida` e `importe_entrada` son MAGNITUDES POSITIVAS. En la misma
    moneda deben coincidir —lo exige `trg_transferencias__estructura`— y en
    monedas distintas pueden diferir sin que el motor infiera ningun tipo de
    cambio: no hay FX y no se fabrica.
    """

    transferencia_id: uuid.UUID
    hecho_id: uuid.UUID
    movimiento_salida_id: uuid.UUID
    movimiento_entrada_id: uuid.UUID
    conciliacion_salida_id: uuid.UUID
    conciliacion_entrada_id: uuid.UUID

    cuenta_origen_id: uuid.UUID
    cuenta_destino_id: uuid.UUID

    fecha_hecho: dt.date | None
    fecha_movimiento: dt.date | None
    moneda: str | None

    importe_salida: decimal.Decimal | None
    importe_entrada: decimal.Decimal | None

    concepto: str | None = None
    notas: str | None = None
    descripcion_salida: str | None = None
    descripcion_entrada: str | None = None

    # Se acepta para RECHAZAR con COMISION_EMBEBIDA. Nunca se persiste.
    comision: decimal.Decimal | None = None

    @property
    def identidades(self) -> tuple[uuid.UUID, ...]:
        """Las seis identidades reservadas, en orden estable.

        El lote es todo-o-nada: o no existe ninguna, o existen las seis con la
        misma intencion. Un subconjunto es siempre conflicto.
        """
        return (
            self.hecho_id,
            self.movimiento_salida_id,
            self.movimiento_entrada_id,
            self.transferencia_id,
            self.conciliacion_salida_id,
            self.conciliacion_entrada_id,
        )


@dataclass(frozen=True, slots=True)
class ResultadoTransferencia:
    """Salida de OP-10.

    Devuelve las `row_version` de las tres raices para que el llamante pueda
    encadenar correcciones sin releer.
    """

    transferencia_id: uuid.UUID
    hecho_id: uuid.UUID
    hecho_row_version: int
    movimiento_salida_id: uuid.UUID
    movimiento_salida_row_version: int
    movimiento_entrada_id: uuid.UUID
    movimiento_entrada_row_version: int
    idempotente: bool = False
