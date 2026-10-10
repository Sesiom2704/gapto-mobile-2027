# ============================================================
# GAPTO MOBILE 2027
# Fichero: capacidades_sinteticas.py
# Ruta: scripts/dev/capacidades_sinteticas.py
# Descripcion: Capacidades EXPLICITAS de las cuentas SINTETICAS (F05-03/F05-04
#   J2 §1.0; F05-D032 C1). Matriz de DATOS, no una regla de servicio: la
#   elegibilidad runtime solo lee filas de gapto.cuenta_capacidades y ningun
#   servicio infiere capacidades por tipo ni por naturaleza (C1). Este modulo
#   lo usan exclusivamente la semilla de ENV-DEV (bootstrap_dev_db.py), los
#   fixtures de los tests y los scripts versionados de scripts/envdev/.
#     CORRIENTE y EFECTIVO -> PAGAR_GASTO, RECIBIR_INGRESO, TRANSFERIR_SALIDA,
#                             TRANSFERIR_ENTRADA
#     AHORRO               -> TRANSFERIR_SALIDA, TRANSFERIR_ENTRADA
#     CREDITO              -> PAGAR_GASTO, TRANSFERIR_ENTRADA
#   Un tipo fuera de la matriz no recibe capacidades (no elegible).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.0)
# ============================================================

from __future__ import annotations

_CUATRO = ("PAGAR_GASTO", "RECIBIR_INGRESO", "TRANSFERIR_SALIDA", "TRANSFERIR_ENTRADA")

CAPACIDADES_POR_TIPO: dict[str, tuple[str, ...]] = {
    "CORRIENTE": _CUATRO,
    "EFECTIVO": _CUATRO,
    "AHORRO": ("TRANSFERIR_SALIDA", "TRANSFERIR_ENTRADA"),
    "CREDITO": ("PAGAR_GASTO", "TRANSFERIR_ENTRADA"),
}


def capacidades_de(tipo: str) -> tuple[str, ...]:
    return CAPACIDADES_POR_TIPO.get(tipo, ())
