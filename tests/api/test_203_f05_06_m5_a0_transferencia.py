# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_203_f05_06_m5_a0_transferencia.py
# Ruta: tests/api/test_203_f05_06_m5_a0_transferencia.py
# Descripcion: Gate de viabilidad A0 de F05-06 M5 (AJ-M5-DEC-01; F05 §59
#   F05-D044 decision 2, opcion A): «Registrar transferencia desde la
#   prevision» = OP-10 + OP-17 en UNA UnidadDeTrabajo del adaptador, con
#   servicios publicos adscritos. Discriminantes, con gapto_runtime y RLS:
#     - exito: una transferencia (dos patas, sin efectos), un vinculo por el
#       importe y la prevision REALIZADA; un solo intento y un solo COMMIT;
#       efecto economico nulo (resultado_mes identico);
#     - OP-17 rechazado (estado, version, moneda, prevision ajena) -> 0 hechos,
#       0 movimientos, 0 transferencias, 0 vinculos y 0 auditoria con el
#       request_id de la operacion (huella identica). La porcion no es
#       rechazable aqui: el hecho es nuevo y el vinculo es su importe total;
#     - fallo de OP-10 (natural y forzado tras escribir) -> 0 vinculos;
#     - sin commit intermedio: un observador en otra conexion, entre OP-10 y
#       OP-17, no ve la transferencia.
#   Reloj fijo 2026-10-10 (Madrid).
# Version: 0.1.0 (F05-06 M5 §A0)
# ============================================================

from __future__ import annotations

import uuid
from contextlib import contextmanager

import psycopg
import pytest

import f05_06_m5_helpers as m
import vs01_api_helpers as h
from app.api import ejecucion_prevision as ejp
from app.api.dto_registro import IntencionTransferencia
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import UnidadDeTrabajo


class _Contada:
    """Conexion que cuenta las transacciones confirmadas (COMMIT)."""

    def __init__(self, conexion, contador):
        self._c, self._n = conexion, contador

    def __getattr__(self, nombre):
        return getattr(self._c, nombre)

    @contextmanager
    def transaction(self, *a, **kw):
        with self._c.transaction(*a, **kw) as t:
            yield t
        self._n["commits"] += 1


def _unidad(contador):
    @contextmanager
    def _abrir():
        contador["conexiones"] += 1
        with psycopg.connect(h.dsn()) as conexion:
            yield _Contada(conexion, contador)

    return UnidadDeTrabajo(_abrir, rol_runtime="gapto_runtime")


@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m.entorno()
    nomina = m.prevision(owner, "Nómina → Ahorro", tipo="TRANSFERENCIA", desde="2026-10-01", importe="500.00",
                         cuenta_salida=cta, cuenta_entrada=ahorro)
    return owner, cli, cta, ahorro, nomina


def _intencion(owner, cta, ahorro, pid, *, marcar=True, row_version=None, fecha="2026-10-07", importe="500.00"):
    return IntencionTransferencia(
        intencion_id=uuid.uuid4(), importe=importe, moneda="EUR", fecha_hecho=fecha, cuenta_origen_id=cta,
        cuenta_destino_id=ahorro,
        prevision={"prevision_id": pid, "row_version": row_version or m.version(owner, pid),
                   "marcar_realizada": marcar})


def _ejecutar(owner, intencion, contador=None):
    contador = contador if contador is not None else {"commits": 0, "conexiones": 0}
    ctx = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
    r = ejp.registrar_transferencia_prevista(_unidad(contador), ctx, intencion, m.x.reloj())
    return r, ctx.request_id, contador


def test_a0_exito_una_pieza_un_commit_sin_efecto_economico(t):
    owner, cli, cta, ahorro, nomina = t
    antes = m.resultado(cli)
    i = _intencion(owner, cta, ahorro, nomina)
    r, rid, contador = _ejecutar(owner, i)
    assert r.hecho_id == i.intencion_id and not r.idempotente
    assert contador == {"commits": 1, "conexiones": 1}  # un intento, un COMMIT
    assert m.movimientos(owner, i.intencion_id) == sorted([(cta, m.D("-500.0000")), (ahorro, m.D("500.0000"))],
                                                          key=str)
    assert m.efectos(owner, i.intencion_id) == []  # la transferencia no crea efectos
    assert m.uno(owner, "SELECT count(*) FROM gapto.transferencias WHERE movimiento_salida_id IN (SELECT "
                        "hm.movimiento_tesoreria_id FROM gapto.hecho_movimientos_tesoreria hm WHERE hm.hecho_id = %s)",
                 (i.intencion_id,))[0] == 1
    assert m.vinculos(owner, nomina) == [(i.intencion_id, m.D("500.0000"))]
    assert m.estado(owner, nomina) == "REALIZADA"
    assert m.auditoria_de(owner, rid) > 0
    assert m.resultado(cli) == antes  # efecto economico nulo


@pytest.mark.parametrize("caso", ["estado", "version", "moneda", "ajena"])
def test_a0_op17_rechazado_revierte_op10(t, caso):
    owner, cli, cta, ahorro, nomina = t
    pid, row_version = nomina, None
    if caso == "estado":
        m.omitir(cli, owner, nomina)
        assert m.estado(owner, nomina) == "OMITIDA"
    elif caso == "version":
        row_version = m.version(owner, nomina) + 7
    elif caso == "moneda":
        pid = m.prevision(owner, "Envío USD", tipo="TRANSFERENCIA", importe="500.00", moneda="USD")
    else:
        otro, *_ = m.entorno()
        pid = m.prevision(otro, "Ajena", tipo="TRANSFERENCIA", importe="500.00")
        row_version = 1
    base = m.huella(owner)
    i = _intencion(owner, cta, ahorro, pid, row_version=row_version)
    with pytest.raises(ErrorMotor) as e:
        _ejecutar(owner, i)
    esperado = {"estado": CodigoError.ESTADO_PREVISION_INCOMPATIBLE, "version": CodigoError.VERSION_DESFASADA,
                "moneda": CodigoError.ASIGNACION_MULTIDIVISA_NO_DEMOSTRADA,
                "ajena": CodigoError.AGREGADO_NO_ENCONTRADO}[caso]
    assert e.value.codigo is esperado
    assert m.huella(owner) == base  # 0 hechos, movimientos, transferencias, vinculos y auditoria
    assert m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (i.intencion_id,))[0] == 0


def test_a0_op17_rechazado_sin_auditoria_del_request(t):
    owner, cli, cta, ahorro, nomina = t
    i = _intencion(owner, cta, ahorro, nomina, row_version=99)
    ctx = ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())
    with pytest.raises(ErrorMotor):
        ejp.registrar_transferencia_prevista(_unidad({"commits": 0, "conexiones": 0}), ctx, i, m.x.reloj())
    assert m.auditoria_de(owner, ctx.request_id) == 0


def test_a0_fallo_natural_de_op10_sin_vinculo(t):
    owner, cli, cta, ahorro, nomina = t
    base = m.huella(owner)
    r, _, _ = _ejecutar(owner, _intencion(owner, cta, ahorro, nomina, fecha="2026-10-11"))  # FECHA_FUTURA
    assert r.codigo == "FECHA_FUTURA"
    assert m.huella(owner) == base and m.vinculos(owner, nomina) == []


def test_a0_fallo_forzado_tras_op10_sin_vinculo(t, monkeypatch):
    owner, cli, cta, ahorro, nomina = t
    from app.api import ejecucion_registro as er

    original = er.TransferenciasService.transferir

    def transferir_y_fallar(self, contexto, datos):
        original(self, contexto, datos)
        raise RuntimeError("fallo inyectado tras escribir OP-10")

    monkeypatch.setattr(er.TransferenciasService, "transferir", transferir_y_fallar)
    base = m.huella(owner)
    with pytest.raises(ErrorMotor) as e:
        _ejecutar(owner, _intencion(owner, cta, ahorro, nomina))
    assert e.value.codigo is CodigoError.INTERNO
    assert m.huella(owner) == base and m.vinculos(owner, nomina) == []


def test_a0_sin_commit_intermedio(t, monkeypatch):
    """Entre OP-10 y OP-17, otra conexion no ve la transferencia."""
    owner, cli, cta, ahorro, nomina = t
    i = _intencion(owner, cta, ahorro, nomina)
    visto: list[int] = []
    Original = ejp.PrevisionesService

    class Observada(Original):
        def vincular_realidad(self, contexto, **kw):
            visto.append(m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s",
                               (i.intencion_id,))[0])
            return super().vincular_realidad(contexto, **kw)

    monkeypatch.setattr(ejp, "PrevisionesService", Observada)
    _ejecutar(owner, i)
    assert visto == [0]
    assert m.uno(owner, "SELECT count(*) FROM gapto.hechos_financieros WHERE id = %s", (i.intencion_id,))[0] == 1
