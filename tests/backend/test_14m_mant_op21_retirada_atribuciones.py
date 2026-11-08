# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_14m_mant_op21_retirada_atribuciones.py
# Ruta: tests/backend/test_14m_mant_op21_retirada_atribuciones.py
# Descripcion: F04 MANT OP-21 (F04-D071; R-L12-01 y R-L17-01). Retirar en una
#   misma correccion un efecto y su reparto o sus vinculos de nivel efecto.
#   fk_efecto_atribuciones__efecto es RESTRICT y no diferible: las
#   atribuciones que la correccion retira tienen que salir ANTES que su
#   efecto. Casos T1..T7 del dictamen de diseno del MANT (AJ-MOP21-03); T6 es
#   el mutante de orden, que ejecuta el arnes y no este fichero.
#
#   R-L17-01 (fk_hecho_entidades__hecho_efecto, vinculos de contexto de nivel
#   efecto): misma familia, corregido en el mismo MANT por decision de Moises
#   (opcion A, 2026-11-08; F04-D071). Casos E1/E1b (positivos), E2 (control)
#   y E3 (negativo de integridad); su mutante de orden lo ejecuta el arnes.
#
#   Todos los casos corren como gapto_runtime con RLS (conftest de backend).
# Version: 0.2.0
#   0.2.0 (F04-D071, MANT N1 de OP-21): R-L17-01 opcion A. El xfail estricto
#   del prototipo pasa a casos permanentes E1/E1b/E2/E3.
# Version: 0.1.0
#   0.1.0 (F04 MANT OP-21, prototipo del lote 18): T1..T5, T7 y R-L17-01.
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosContextoHecho, DatosEntidadHecho
from app.core.modelos_efectos import DatosAtribucion, DatosEfecto
from app.services.contexto_service import ContextoService
from app.services.correcciones_service import DatosAtribucionNueva, DatosCorreccion
from conftest import leer_fila
from test_140_f04_r3_op22 import nueva_entidad

D = decimal.Decimal
FECHA = dt.date(2026, 6, 1)
TOTAL = D("44.5000")
MITAD = D("22.2500")


@pytest.fixture()
def servicio_contexto(unidad):
    return ContextoService(unidad)


def _atribucion(actor_id, importe):
    return DatosAtribucion(atribucion_id=uuid.uuid4(), actor_id=actor_id,
                           importe_atribuido=importe, criterio_atribucion="MANUAL")


def _cena(servicio, servicio_efectos, contexto, atribuciones, estado):
    hecho_id, efecto_id = uuid.uuid4(), uuid.uuid4()
    creado = servicio.crear_hecho(contexto, DatosCreacionHecho(
        hecho_id=hecho_id, fecha_hecho=FECHA, moneda="EUR", presupuestable=True,
        estado_localizacion="DESCONOCIDA", tipo_hecho_codigo="GASTO",
        concepto="cena compartida", importe_total=TOTAL))
    r = servicio_efectos.registrar_efectos(
        contexto, hecho_id=hecho_id, row_version_esperada=creado.row_version,
        efectos=[DatosEfecto(efecto_id=efecto_id, tipo_efecto="GASTO", importe_delta=TOTAL,
                             estado_atribucion=estado, atribuciones=tuple(atribuciones))],
        presupuestable=True)
    return hecho_id, efecto_id, r.row_version


def _reemplazo(estado):
    return DatosEfecto(efecto_id=uuid.uuid4(), tipo_efecto="GASTO", importe_delta=TOTAL,
                       estado_atribucion=estado)


def _foto(admin, contexto, hecho_id, ids):
    owner = contexto.owner_user_id
    return {
        "hecho": leer_fila(admin, owner, "SELECT count(*), max(row_version) FROM gapto.hechos_financieros "
                           "WHERE id = %s", (hecho_id,)),
        "efectos": leer_fila(admin, owner, "SELECT count(*), COALESCE(sum(importe_delta), 0) "
                             "FROM gapto.hecho_efectos WHERE hecho_id = %s", (hecho_id,)),
        "atribuciones": leer_fila(admin, owner, "SELECT count(*), COALESCE(sum(a.importe_atribuido), 0) "
                                  "FROM gapto.efecto_atribuciones a JOIN gapto.hecho_efectos e "
                                  "ON e.id = a.efecto_id WHERE e.hecho_id = %s", (hecho_id,)),
        "auditoria_mutaciones": leer_fila(admin, owner, "SELECT count(*) FROM gapto.auditoria "
                                          "WHERE registro_id = ANY(%s) AND accion IN ('ANULAR', 'ACTUALIZAR')",
                                          (list(ids),)),
    }


def _huerfanas(admin, contexto, efecto_id):
    return leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.efecto_atribuciones WHERE efecto_id = %s", (efecto_id,))[0]


# ------------------------------------------------------------------ T1

def test_t1_positivo_completo_efecto_y_reparto_reemplazados(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    a, b = _atribucion(actor_a, MITAD), _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [a, b], "COMPLETA")
    nuevo = _reemplazo("COMPLETA")
    nuevas = tuple(DatosAtribucionNueva(atribucion_id=uuid.uuid4(), efecto_id=nuevo.efecto_id,
                                        actor_id=x, importe_atribuido=MITAD, criterio_atribucion="MANUAL")
                   for x in (actor_a, actor_b))
    r = servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=version, motivo="el efecto y su reparto eran otros",
        atribuciones_a_eliminar=(a.atribucion_id, b.atribucion_id), efectos_a_eliminar=(efecto_id,),
        efectos_a_crear=(nuevo,), atribuciones_a_crear=nuevas))
    assert (r.efectos_eliminados, r.efectos_creados, r.efectos_finales) == (1, 1, 1)
    assert (r.atribuciones_eliminadas, r.atribuciones_creadas) == (2, 2)
    f = _foto(admin, contexto, hecho_id, [a.atribucion_id, b.atribucion_id, efecto_id])
    assert f["hecho"] == (1, version + 1)
    assert f["efectos"] == (1, TOTAL)
    assert f["atribuciones"] == (2, TOTAL)
    assert f["auditoria_mutaciones"] == (3,)
    assert _huerfanas(admin, contexto, efecto_id) == 0


# ------------------------------------------------------------------ T2

def test_t2_positivo_minimo_reemplazo_no_disponible(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    a, b = _atribucion(actor_a, MITAD), _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [a, b], "COMPLETA")
    r = servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=version, motivo="el reparto no se conoce",
        atribuciones_a_eliminar=(a.atribucion_id, b.atribucion_id), efectos_a_eliminar=(efecto_id,),
        efectos_a_crear=(_reemplazo("NO_DISPONIBLE"),)))
    assert (r.efectos_eliminados, r.efectos_creados, r.atribuciones_eliminadas) == (1, 1, 2)
    f = _foto(admin, contexto, hecho_id, [a.atribucion_id, b.atribucion_id, efecto_id])
    assert f["hecho"] == (1, version + 1)
    assert f["atribuciones"] == (0, 0)
    assert _huerfanas(admin, contexto, efecto_id) == 0


# ------------------------------------------------------------------ T3

def test_t3_control_efecto_sin_atribuciones(
    servicio, servicio_efectos, servicio_correcciones, contexto, admin
) -> None:
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [], "NO_DISPONIBLE")
    r = servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=version, motivo="el efecto correcto era otro",
        efectos_a_eliminar=(efecto_id,), efectos_a_crear=(_reemplazo("NO_DISPONIBLE"),)))
    assert (r.efectos_eliminados, r.efectos_creados, r.efectos_finales) == (1, 1, 1)
    assert r.atribuciones_eliminadas == 0
    assert _foto(admin, contexto, hecho_id, [efecto_id])["hecho"] == (1, version + 1)


# ------------------------------------------------------------------ T4

def test_t4_negativo_efecto_sin_retirar_su_reparto_cae_en_la_fk(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """Sin cascada implicita: si el llamante no lista las atribuciones, la FK
    sigue impidiendo dejarlas huerfanas."""
    a, b = _atribucion(actor_a, MITAD), _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [a, b], "COMPLETA")
    ids = [a.atribucion_id, b.atribucion_id, efecto_id]
    antes = _foto(admin, contexto, hecho_id, ids)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(contexto, DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=version, motivo="olvido el reparto",
            efectos_a_eliminar=(efecto_id,), efectos_a_crear=(_reemplazo("NO_DISPONIBLE"),)))
    assert excepcion.value.codigo is CodigoError.VIOLACION_INVARIANTE_FISICA
    assert excepcion.value.sqlstate == "23503"
    assert _foto(admin, contexto, hecho_id, ids) == antes


# ------------------------------------------------------------------ T5

def test_t5_negativo_atribucion_de_otro_hecho_junto_a_la_retirada(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """La comprobacion de pertenencia se conserva aunque las bajas de
    atribuciones vayan antes. El codigo es el contractual de test_126
    (AGREGADO_NO_ENCONTRADO), no ENTRADA_INVALIDA."""
    ajena = _atribucion(actor_a, TOTAL)
    _cena(servicio, servicio_efectos, contexto, [ajena], "COMPLETA")
    b = _atribucion(actor_b, TOTAL)
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [b], "COMPLETA")
    ids = [b.atribucion_id, ajena.atribucion_id, efecto_id]
    antes = _foto(admin, contexto, hecho_id, ids)
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(contexto, DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=version, motivo="cruce de agregados",
            atribuciones_a_eliminar=(ajena.atribucion_id, b.atribucion_id), efectos_a_eliminar=(efecto_id,),
            efectos_a_crear=(_reemplazo("NO_DISPONIBLE"),)))
    assert excepcion.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
    assert _foto(admin, contexto, hecho_id, ids) == antes


# ------------------------------------------------------------------ T7

def test_t7_fallo_tardio_tras_retirar_el_reparto_deshace_todo(
    servicio, servicio_efectos, servicio_correcciones, contexto, actor_a, actor_b, admin
) -> None:
    """Las bajas de atribuciones (3a) y del efecto ya se han ejecutado cuando
    la guarda de estado final rechaza el reparto nuevo descuadrado: no queda
    nada (efectos, atribuciones, row_version ni auditoria)."""
    a, b = _atribucion(actor_a, MITAD), _atribucion(actor_b, MITAD)
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [a, b], "COMPLETA")
    ids = [a.atribucion_id, b.atribucion_id, efecto_id]
    antes = _foto(admin, contexto, hecho_id, ids)
    nuevo = _reemplazo("COMPLETA")
    descuadradas = tuple(DatosAtribucionNueva(atribucion_id=uuid.uuid4(), efecto_id=nuevo.efecto_id,
                                              actor_id=x, importe_atribuido=D("10.0000"),
                                              criterio_atribucion="MANUAL")
                         for x in (actor_a, actor_b))
    with pytest.raises(ErrorMotor):
        servicio_correcciones.corregir(contexto, DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=version, motivo="reparto nuevo que no cuadra",
            atribuciones_a_eliminar=(a.atribucion_id, b.atribucion_id), efectos_a_eliminar=(efecto_id,),
            efectos_a_crear=(nuevo,), atribuciones_a_crear=descuadradas))
    assert _foto(admin, contexto, hecho_id, ids) == antes
    assert leer_fila(admin, contexto.owner_user_id,
                     "SELECT count(*) FROM gapto.hecho_efectos WHERE id = %s", (nuevo.efecto_id,)) == (0,)


# ------------------------------------------------------------------ R-L17-01 (opcion A, F04-D071)
#   Vinculos contextuales de hecho_entidades de NIVEL EFECTO.
#   fk_hecho_entidades__hecho_efecto es RESTRICT y no diferible: el vinculo
#   que la correccion retira tiene que salir antes que su efecto (paso 3b).


def _vincular(servicio_contexto, contexto, admin, hecho_id, version, efecto_id,
              tipo="PROPIEDAD", relacion="RELACIONADO_CON", principal=False):
    vinculo = uuid.uuid4()
    datos = DatosContextoHecho(entidades=[DatosEntidadHecho(
        vinculo, nueva_entidad(admin, contexto.owner_user_id, tipo), relacion,
        principal=principal, efecto_id=efecto_id)])
    r = servicio_contexto.enriquecer(contexto, hecho_id=hecho_id, row_version_esperada=version, datos=datos)
    return vinculo, r.hecho_row_version


def _foto_vinculos(admin, contexto, hecho_id, ids):
    owner = contexto.owner_user_id
    return {
        "hecho": leer_fila(admin, owner, "SELECT count(*), max(row_version) FROM gapto.hechos_financieros "
                           "WHERE id = %s", (hecho_id,)),
        "efectos": leer_fila(admin, owner, "SELECT count(*) FROM gapto.hecho_efectos WHERE hecho_id = %s",
                             (hecho_id,)),
        "vinculos": leer_fila(admin, owner, "SELECT count(*), count(efecto_id) FROM gapto.hecho_entidades "
                              "WHERE hecho_id = %s", (hecho_id,)),
        "auditoria_mutaciones": leer_fila(admin, owner, "SELECT count(*) FROM gapto.auditoria "
                                          "WHERE registro_id = ANY(%s) AND accion IN ('ANULAR', 'ACTUALIZAR')",
                                          (list(ids),)),
    }


@pytest.mark.parametrize(
    ("tipo", "relacion", "principal"),
    [("PROPIEDAD", "RELACIONADO_CON", False), ("CONTEXTO", "AFECTA_A", True)],
    ids=["e1_propiedad_relacionado_con", "e1b_contexto_afecta_a_principal"],
)
def test_e1_vinculo_de_efecto_retirado_con_su_efecto(
    servicio, servicio_efectos, servicio_correcciones, servicio_contexto, contexto, admin,
    tipo, relacion, principal,
) -> None:
    """E1/E1b. Retirar el efecto y su vinculo de nivel efecto e instalar un
    reemplazo: estado final valido, sin vinculo huerfano."""
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [], "NO_DISPONIBLE")
    vinculo, version = _vincular(servicio_contexto, contexto, admin, hecho_id, version, efecto_id,
                                 tipo, relacion, principal)
    r = servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=version, motivo="el vinculo era del efecto falso",
        efectos_a_eliminar=(efecto_id,), efectos_a_crear=(_reemplazo("NO_DISPONIBLE"),),
        entidades_a_eliminar=(vinculo,)))
    assert (r.efectos_eliminados, r.efectos_creados, r.efectos_finales) == (1, 1, 1)
    f = _foto_vinculos(admin, contexto, hecho_id, [vinculo, efecto_id])
    assert f["hecho"] == (1, version + 1)
    assert f["efectos"] == (1,)
    assert f["vinculos"] == (0, 0)
    assert f["auditoria_mutaciones"] == (2,)


def test_e2_control_vinculo_de_hecho_no_se_toca(
    servicio, servicio_efectos, servicio_correcciones, servicio_contexto, contexto, admin
) -> None:
    """E2. Control: un vinculo de nivel HECHO no depende del efecto; retirar el
    efecto no lo toca."""
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [], "NO_DISPONIBLE")
    vinculo, version = _vincular(servicio_contexto, contexto, admin, hecho_id, version, None)
    servicio_correcciones.corregir(contexto, DatosCorreccion(
        hecho_id=hecho_id, row_version_esperada=version, motivo="solo el efecto era falso",
        efectos_a_eliminar=(efecto_id,), efectos_a_crear=(_reemplazo("NO_DISPONIBLE"),)))
    f = _foto_vinculos(admin, contexto, hecho_id, [vinculo])
    assert f["vinculos"] == (1, 0)
    assert f["auditoria_mutaciones"] == (0,)


def test_e3_negativo_efecto_retirado_sin_su_vinculo(
    servicio, servicio_efectos, servicio_correcciones, servicio_contexto, contexto, admin
) -> None:
    """E3. Negativo de integridad: retirar el efecto SIN listar su vinculo de
    nivel efecto sigue rechazandose (sin borrado implicito) y no deja rastro."""
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [], "NO_DISPONIBLE")
    vinculo, version = _vincular(servicio_contexto, contexto, admin, hecho_id, version, efecto_id)
    antes = _foto_vinculos(admin, contexto, hecho_id, [vinculo, efecto_id])
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(contexto, DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=version, motivo="intento con vinculo olvidado",
            efectos_a_eliminar=(efecto_id,), efectos_a_crear=(_reemplazo("NO_DISPONIBLE"),)))
    assert excepcion.value.codigo is CodigoError.VIOLACION_INVARIANTE_FISICA
    assert excepcion.value.sqlstate == "23503"
    assert _foto_vinculos(admin, contexto, hecho_id, [vinculo, efecto_id]) == antes


def test_e4_vinculo_de_efecto_repetido_sigue_siendo_no_encontrado(
    servicio, servicio_efectos, servicio_correcciones, servicio_contexto, contexto, admin
) -> None:
    """E4. Listar dos veces el mismo vinculo de nivel efecto conserva el
    contrato anterior: la segunda baja no encuentra la fila
    (AGREGADO_NO_ENCONTRADO) y no queda rastro."""
    hecho_id, efecto_id, version = _cena(servicio, servicio_efectos, contexto, [], "NO_DISPONIBLE")
    vinculo, version = _vincular(servicio_contexto, contexto, admin, hecho_id, version, efecto_id)
    antes = _foto_vinculos(admin, contexto, hecho_id, [vinculo, efecto_id])
    with pytest.raises(ErrorMotor) as excepcion:
        servicio_correcciones.corregir(contexto, DatosCorreccion(
            hecho_id=hecho_id, row_version_esperada=version, motivo="vinculo repetido",
            efectos_a_eliminar=(efecto_id,), efectos_a_crear=(_reemplazo("NO_DISPONIBLE"),),
            entidades_a_eliminar=(vinculo, vinculo)))
    assert excepcion.value.codigo is CodigoError.AGREGADO_NO_ENCONTRADO
    assert _foto_vinculos(admin, contexto, hecho_id, [vinculo, efecto_id]) == antes
