# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_rv3_003_fuente_normalizacion.py
# Ruta: tests/migration/test_rv3_003_fuente_normalizacion.py
# Descripcion: RV3 / P2-P4. Tests con corpus SINTETICO de la libreria de fuente:
#              RV3_SOURCE_JSONCELL_V1 byte-exacto, identidad UUIDv5 canonica,
#              regla contextual del 141 (RV3-D002-C), marcadores None/NONE,
#              conservacion del literal y mutante TODO_141_A_NULL.
#
# Versión: 0.1.0
# ============================================================
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / "scripts" / "migration_v3" / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


F = _cargar("rv3_fuente")
P23 = _cargar("rv3_p2_p3_inventario")


# ---------------------------------------------------------------- hash de registro
def test_jsoncell_v1_es_sha256_de_los_bytes_utf8_exactos():
    texto = '{"id": 1, "nombre": "Ñandú"}'
    assert F.hash_registro(texto) == hashlib.sha256(texto.encode("utf-8")).hexdigest()


def test_jsoncell_v1_distingue_serializaciones_equivalentes():
    # Mismo JSON parseado, distinta cadena -> distinto hash: preserva el artefacto byte a byte.
    assert F.hash_registro('{"a": 1, "b": 2}') != F.hash_registro('{"b": 2, "a": 1}')
    assert F.hash_registro('{"a": 1}') != F.hash_registro('{"a":1}')


# ---------------------------------------------------------------- identidad
def test_uuid_canonico_reproduce_vector_documentado():
    # Migration V3 §35.3: valoracion terminal documentada.
    assert F.uuid_v3("public.inversion", "INV-2F7A749023", "inversion_valoraciones",
                     "valoracion:cierre") == "cf2a8dce-8a08-52c5-8664-9844effa1824"


def test_uuid_determinista_y_sensible_a_cada_parte():
    base = F.uuid_v3("public.x", "K1", "tabla", "rol")
    assert base == F.uuid_v3("public.x", "K1", "tabla", "rol")
    assert len({base, F.uuid_v3("public.y", "K1", "tabla", "rol"), F.uuid_v3("public.x", "K2", "tabla", "rol"),
                F.uuid_v3("public.x", "K1", "otra", "rol"), F.uuid_v3("public.x", "K1", "tabla", "otro")}) == 5


@pytest.mark.parametrize("args", [("", "K", "t", "r"), ("c", None, "t", "r"), ("c", "K", "t|x", "r"),
                                  ("c", "K", "t", "")])
def test_uuid_rechaza_identidad_invalida(args):
    with pytest.raises(ValueError):
        F.uuid_v3(*args)


# ---------------------------------------------------------------- normalizacion
def _cuotas(n, prestamo="P1", hueco=None):
    return {f"{prestamo}-{i}": {"id": f"{prestamo}-{i}", "prestamo_id": prestamo, "num_cuota": i,
                                "importe": 10, "fecha_pago": 141}
            for i in range(1, n + 1) if i != hueco}


def test_141_real_en_num_cuota_dentro_de_secuencia_completa():
    fuente = {"public.prestamo_cuota": _cuotas(150)}
    n = F.normalizar_fuente(fuente)
    c = n["public.prestamo_cuota"]["P1-141"]["num_cuota"]
    assert (c.estado, c.valor, c.literal) == (F.REAL_141, 141, 141)


def test_141_en_otra_columna_de_la_misma_fila_es_sentinel():
    n = F.normalizar_fuente({"public.prestamo_cuota": _cuotas(150)})
    c = n["public.prestamo_cuota"]["P1-141"]["fecha_pago"]
    assert (c.estado, c.valor, c.literal) == (F.AUSENCIA_141, None, 141)


def test_141_en_num_cuota_con_secuencia_incompleta_no_se_acepta_como_real():
    n = F.normalizar_fuente({"public.prestamo_cuota": _cuotas(150, hueco=7)})
    assert n["public.prestamo_cuota"]["P1-141"]["num_cuota"].estado == F.AUSENCIA_141


def test_141_en_num_cuota_con_menos_de_141_cuotas_es_sentinel():
    fuente = {"public.prestamo_cuota": {**_cuotas(100), "X": {"id": "X", "prestamo_id": "P1", "num_cuota": 141}}}
    assert F.normalizar_fuente(fuente)["public.prestamo_cuota"]["X"]["num_cuota"].estado == F.AUSENCIA_141


def test_141_en_otra_tabla_es_sentinel_aunque_la_columna_se_llame_igual():
    n = F.normalizar_fuente({"public.gastos": {"G": {"id": "G", "num_cuota": 141, "prestamo_id": "P1"}},
                             "public.prestamo_cuota": _cuotas(150)})
    assert n["public.gastos"]["G"]["num_cuota"].estado == F.AUSENCIA_141


@pytest.mark.parametrize("v,estado,valor", [
    ("None", F.AUSENCIA_NONE, None), ("NONE", F.AUSENCIA_NONE, None), ("none", F.CONOCIDO, "none"),
    (None, F.NULO, None), ("", F.NULO, None), (0, F.CONOCIDO, 0), ("141", F.AUSENCIA_141, None),
    (141.0, F.AUSENCIA_141, None), (142, F.CONOCIDO, 142), (False, F.CONOCIDO, False),
])
def test_estados_de_celda(v, estado, valor):
    c = F.normalizar("public.t", "col", v, {}, {"cuotas": {}})
    assert (c.estado, c.valor) == (estado, valor)
    assert c.literal is v or c.literal == v


# ---------------------------------------------------------------- mutante contractual
def test_mutante_todo_141_a_null_muere_en_la_reconciliacion_de_cuotas(monkeypatch):
    fuente = {"public.prestamo_cuota": _cuotas(150)}
    monkeypatch.setitem(P23.CANON, "cuotas", 150)
    assert P23.reconciliar_cuotas(F.normalizar_fuente(fuente))["ok"] is True
    assert P23.mutante_todo_141_a_null(fuente)["ok"] is False
    # el mutante no deja residuo: la regla real sigue activa despues
    assert P23.reconciliar_cuotas(F.normalizar_fuente(fuente))["ok"] is True
