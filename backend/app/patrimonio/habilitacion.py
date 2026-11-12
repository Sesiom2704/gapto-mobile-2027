# ============================================================
# GAPTO MOBILE 2027
# Fichero: habilitacion.py
# Ruta: backend/app/patrimonio/habilitacion.py
# Descripcion: Bloqueo de habilitacion de los consumidores PROVISIONALES de 0352 (WM 0.32 §13.6.2.5 y
#   §13.6.14.7; N1-RF2-16..20; dictamen del tren 1 §13; mandato B2 §1.2.10; oraculo O10.29).
#   Consumidores: C-PROP-05 (POST /v1/propiedades/{id}/completitud), la declaracion de completitud en
#   C-COMPRA-01/03 (`completitud_adquisicion`, `huella_conjunto_vista`) y la parte de L-COSTE que depende de la
#   declaracion (estado COMPLETO, fecha de corte y huella del conjunto).
#   Mecanismo: una CONSTANTE DE CODIGO, no una variable de entorno ni de configuracion. Solo puede cambiar con
#   un commit revisado despues de la certificacion de 0352 (recierre de F03 en el cierre del tren). Mientras
#   valga False:
#     - la ruta de C-PROP-05 responde 404 FUNCION_NO_HABILITADA y el servicio rechaza igual (defensa);
#     - C-COMPRA-01/03 con declaracion responden 422 ENTRADA_INVALIDA (como el plan B: «sin 0352 el campo no
#       existe») sin escribir;
#     - L-COSTE no lee la declaracion: nunca COMPLETO (O10.10), sin fecha de corte ni huella.
#   Los tests de los consumidores la activan solo dentro del propio test (monkeypatch), nunca por entorno.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

#: False hasta que 0352 este certificada (decision de Moisés tras el recierre de F03). NO leer del entorno.
CONSUMIDORES_0352_HABILITADOS = False

FUNCION_NO_HABILITADA = "FUNCION_NO_HABILITADA"


def consumidores_0352_habilitados() -> bool:
    return CONSUMIDORES_0352_HABILITADOS is True
