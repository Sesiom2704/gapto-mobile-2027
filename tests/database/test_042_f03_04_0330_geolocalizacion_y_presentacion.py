# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_042_f03_04_0330_geolocalizacion_y_presentacion.py
# Ruta: tests/database/test_042_f03_04_0330_geolocalizacion_y_presentacion.py
# Descripción: Verifica F03-04 / migration 0330 (D-182 + D-184 + D-185 +
#              D-186 §2/§3): geolocalización persistente de propiedad y
#              metadatos de presentación sobre `documento_vinculos`.
#
#              DISCRIMINACIÓN. Contra 0320 fallan todos los bloques: las cinco
#              columnas no existen. Contra un mutante que elimine el predicado
#              parcial del índice de portada falla
#              test_0330_misma_foto_reutilizable_en_otra_entidad. Contra un
#              mutante que sustituya la garantía B por un UNIQUE global
#              (entidad_id, documento_id) falla
#              test_0330_roles_documentales_no_visuales_intactos. Contra un
#              mutante que retire ck_..._presentacion_solo_entidad falla
#              test_0330_presentacion_solo_con_entidad.
#
#              LAS DOS GARANTÍAS SON DISTINTAS (D-186 §2):
#                A. una sola PORTADA por entidad;
#                B. una sola aparición visual de un documento por entidad.
#              B no es redundante con el UNIQUE histórico
#              uq_documento_vinculos__entidad, que incluye rol_vinculo en la
#              clave y por tanto permitiría la misma foto dos veces en la
#              misma galería bajo roles documentales distintos.
#
#              LO QUE NO SE PRUEBA AQUÍ Y NO ES UN OLVIDO. Que el documento
#              sea FOTO y esté DISPONIBLE, y que una geocodificación
#              automática no reescriba una coordenada ya persistida, son
#              garantías SRV/API (D-186 §3). No hay trigger y no debe haberlo:
#              probarlas contra el catálogo daría una falsa sensación de
#              garantía física. Se prueban en el servicio.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

OWNER = "0330a000-0000-4000-8000-000000000001"
OTRO_OWNER = "0330a000-0000-4000-8000-0000000000ff"

CK_PROPIEDADES = (
    "ck_propiedades__coordenadas_pareja",
    "ck_propiedades__latitud_rango",
    "ck_propiedades__longitud_rango",
    "ck_propiedades__geolocalizacion_origen",
    "ck_propiedades__geolocalizacion_origen_coherente",
)

CK_VINCULOS = (
    "ck_documento_vinculos__uso_presentacion",
    "ck_documento_vinculos__presentacion_solo_entidad",
    "ck_documento_vinculos__orden_presentacion",
    "ck_documento_vinculos__orden_exige_presentacion",
)

INDICES_0330 = (
    "uq_documento_vinculos__portada_entidad",
    "uq_documento_vinculos__presentacion_entidad_documento",
)


@pytest.fixture()
def db():
    url = os.environ.get("GAPTO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GAPTO_TEST_DATABASE_URL no definida")
    con = psycopg.connect(url)
    con.execute("SET ROLE gapto_owner")
    yield con
    con.rollback()
    con.close()


def _uno(db: psycopg.Connection, sql: str, params: tuple | None = None):
    with db.cursor() as cur:
        cur.execute(sql, params)
        fila = cur.fetchone()
    return fila[0] if fila else None


class Escenario:
    """Dos propiedades del mismo owner y una fotografía DISPONIBLE."""

    def __init__(self, db: psycopg.Connection) -> None:
        self.db = db
        db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER,))
        for owner in (OWNER, OTRO_OWNER):
            db.execute(
                "INSERT INTO gapto.usuarios (id, email, nombre) VALUES (%s, %s, '0330') "
                "ON CONFLICT DO NOTHING", (owner, f"{uuid.uuid4()}@example.invalid"))
        self.propiedad_a = self.propiedad()
        self.propiedad_b = self.propiedad()
        self.foto = self.documento("FOTO")
        self.foto_2 = self.documento("FOTO")

    def propiedad(self) -> str:
        eid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) "
            "VALUES (%s, %s, 'PROPIEDAD', %s)", (eid, OWNER, f"Piso {eid[:8]}"))
        self.db.execute(
            "INSERT INTO gapto.propiedades (entidad_id, tipo_propiedad) VALUES (%s, 'VIVIENDA')",
            (eid,))
        return eid

    def documento(self, tipo: str) -> str:
        did = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.documentos (id, owner_user_id, tipo, nombre_archivo_original, "
            "mime_type, size_bytes, storage_key) "
            "VALUES (%s, %s, %s, %s, 'image/jpeg', 1024, %s)",
            (did, OWNER, tipo, f"{did[:8]}.jpg", f"privado/{did}"))
        return did

    def vinculo(self, documento: str, entidad: str, rol: str = "PRINCIPAL",
                uso: str | None = None, orden: int | None = None) -> str:
        vid = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO gapto.documento_vinculos (id, documento_id, entidad_id, rol_vinculo, "
            "uso_presentacion, orden_presentacion) VALUES (%s, %s, %s, %s, %s, %s)",
            (vid, documento, entidad, rol, uso, orden))
        return vid

    def geolocalizar(self, entidad: str, lat, lon, origen) -> None:
        self.db.execute(
            "UPDATE gapto.propiedades SET latitud = %s, longitud = %s, "
            "geolocalizacion_origen = %s WHERE entidad_id = %s",
            (lat, lon, origen, entidad))


@pytest.fixture()
def esc(db: psycopg.Connection) -> Escenario:
    return Escenario(db)


def _rechaza(esc: Escenario, excepcion, accion) -> None:
    esc.db.execute("SAVEPOINT s")
    with pytest.raises(excepcion):
        accion()
    esc.db.execute("ROLLBACK TO SAVEPOINT s")


# ------------------------------------------------------------
# Estructura
# ------------------------------------------------------------

def test_0330_columnas_con_tipo_exacto(db: psycopg.Connection) -> None:
    esperado = {
        ("propiedades", "latitud"): "numeric(9,6)",
        ("propiedades", "longitud"): "numeric(9,6)",
        ("propiedades", "geolocalizacion_origen"): "character varying(20)",
        ("documento_vinculos", "uso_presentacion"): "character varying(20)",
        ("documento_vinculos", "orden_presentacion"): "smallint",
    }
    with db.cursor() as cur:
        cur.execute("""
            SELECT c.relname, a.attname,
                   pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull
              FROM pg_catalog.pg_attribute a
              JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
             WHERE c.relnamespace = 'gapto'::regnamespace
               AND (c.relname, a.attname) IN (
                   ('propiedades','latitud'), ('propiedades','longitud'),
                   ('propiedades','geolocalizacion_origen'),
                   ('documento_vinculos','uso_presentacion'),
                   ('documento_vinculos','orden_presentacion'))
        """)
        filas = cur.fetchall()
    assert len(filas) == 5, "faltan columnas de 0330"
    for tabla, columna, tipo, notnull in filas:
        assert tipo == esperado[(tabla, columna)], f"{tabla}.{columna}: {tipo}"
        assert notnull is False, f"{tabla}.{columna} debe ser nullable: V3 no aporta el dato"


@pytest.mark.parametrize("nombre", CK_PROPIEDADES + CK_VINCULOS)
def test_0330_checks_existen_y_estan_validados(db: psycopg.Connection, nombre: str) -> None:
    """Un CHECK NOT VALID sería una invariante decorativa."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_constraint k
         WHERE k.conname = %s AND k.contype = 'c' AND k.convalidated
    """, (nombre,)) == 1


@pytest.mark.parametrize("nombre", INDICES_0330)
def test_0330_indices_son_unicos_y_parciales(db: psycopg.Connection, nombre: str) -> None:
    """El predicado parcial es esencial: sin él, la garantía se convertiría en
    una prohibición que rompe casos legítimos."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_index i
          JOIN pg_catalog.pg_class ci ON ci.oid = i.indexrelid
         WHERE ci.relname = %s AND i.indisunique AND i.indpred IS NOT NULL
    """, (nombre,)) == 1


def test_0330_no_crea_postgis_ni_triggers_ni_tablas(db: psycopg.Connection) -> None:
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_extension WHERE extname LIKE 'postgis%'
    """) == 0
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class
         WHERE relnamespace='gapto'::regnamespace AND relkind='r'
           AND relname IN ('propiedad_fotos','propiedad_documentos')
    """) == 0
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class
         WHERE relnamespace='gapto'::regnamespace AND relkind='r'
    """) == 80
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
         WHERE c.relnamespace='gapto'::regnamespace AND NOT t.tgisinternal
    """) == 58


def test_0330_force_rls_restaurado(db: psycopg.Connection) -> None:
    """D-104: el patrón levantar/validar/restaurar no puede dejar una tabla
    sin FORCE."""
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class
         WHERE relnamespace='gapto'::regnamespace AND relkind='r'
           AND relrowsecurity AND relforcerowsecurity
    """) == 75
    assert _uno(db, """
        SELECT count(*) FROM pg_catalog.pg_class
         WHERE relnamespace='gapto'::regnamespace
           AND relname IN ('propiedades','documento_vinculos')
           AND relrowsecurity AND relforcerowsecurity
    """) == 2


def test_0330_uq_historico_de_vinculos_intacto(db: psycopg.Connection) -> None:
    """La garantía B existe precisamente porque este UNIQUE incluye
    rol_vinculo. Si desapareciera, el razonamiento de D-186 §2 cambiaría."""
    definicion = _uno(db, """
        SELECT indexdef FROM pg_catalog.pg_indexes
         WHERE schemaname='gapto' AND indexname='uq_documento_vinculos__entidad'
    """)
    assert definicion is not None
    assert "rol_vinculo" in definicion


# ------------------------------------------------------------
# D-184 — geolocalización
# ------------------------------------------------------------

def test_0330_legacy_sin_coordenadas_es_valido(esc: Escenario) -> None:
    """V3 y todo lo preexistente quedan a NULL y siguen siendo válidos."""
    assert _uno(esc.db, """
        SELECT count(*) FROM gapto.propiedades
         WHERE entidad_id = %s AND latitud IS NULL AND longitud IS NULL
           AND geolocalizacion_origen IS NULL
    """, (esc.propiedad_a,)) == 1


def test_0330_coordenada_completa_se_persiste(esc: Escenario) -> None:
    esc.geolocalizar(esc.propiedad_a, "37.771000", "-1.502000", "MANUAL")
    assert _uno(esc.db, "SELECT latitud FROM gapto.propiedades WHERE entidad_id = %s",
                (esc.propiedad_a,)) is not None


@pytest.mark.parametrize("lat,lon", [("37.771000", None), (None, "-1.502000")])
def test_0330_media_coordenada_rechazada(esc: Escenario, lat, lon) -> None:
    """Media coordenada no es un dato parcial útil: es un dato falso (D-052)."""
    _rechaza(esc, psycopg.errors.CheckViolation,
             lambda: esc.geolocalizar(esc.propiedad_a, lat, lon, "MANUAL"))


@pytest.mark.parametrize("lat,lon", [
    ("90.000001", "0.000000"), ("-90.000001", "0.000000"),
    ("0.000000", "180.000001"), ("0.000000", "-180.000001"),
])
def test_0330_rangos_fuera_de_limite_rechazados(esc: Escenario, lat, lon) -> None:
    _rechaza(esc, psycopg.errors.CheckViolation,
             lambda: esc.geolocalizar(esc.propiedad_a, lat, lon, "GPS"))


@pytest.mark.parametrize("lat,lon", [
    ("90.000000", "180.000000"), ("-90.000000", "-180.000000"), ("0.000000", "0.000000"),
])
def test_0330_limites_exactos_admitidos(esc: Escenario, lat, lon) -> None:
    """Los extremos son válidos: el CHECK es inclusivo."""
    esc.geolocalizar(esc.propiedad_a, lat, lon, "IMPORTADA")


def test_0330_coordenada_sin_origen_rechazada(esc: Escenario) -> None:
    _rechaza(esc, psycopg.errors.CheckViolation,
             lambda: esc.geolocalizar(esc.propiedad_a, "37.771000", "-1.502000", None))


def test_0330_origen_sin_coordenada_rechazado(esc: Escenario) -> None:
    """Una procedencia sin punto no describe nada."""
    _rechaza(esc, psycopg.errors.CheckViolation,
             lambda: esc.geolocalizar(esc.propiedad_a, None, None, "GEOCODIFICADA"))


def test_0330_origen_fuera_del_catalogo_rechazado(esc: Escenario) -> None:
    _rechaza(esc, psycopg.errors.CheckViolation,
             lambda: esc.geolocalizar(esc.propiedad_a, "37.771000", "-1.502000", "CATASTRO"))


@pytest.mark.parametrize("origen", ["MANUAL", "GEOCODIFICADA", "GPS", "IMPORTADA"])
def test_0330_los_cuatro_origenes_aprobados(esc: Escenario, origen: str) -> None:
    esc.geolocalizar(esc.propiedad_a, "37.771000", "-1.502000", origen)


# ------------------------------------------------------------
# D-185 — presentación documental
# ------------------------------------------------------------

def test_0330_portada_y_galeria_se_persisten(esc: Escenario) -> None:
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "PORTADA", 1)
    esc.vinculo(esc.foto_2, esc.propiedad_a, "ANEXO", "GALERIA", 2)
    assert _uno(esc.db, """
        SELECT count(*) FROM gapto.documento_vinculos
         WHERE entidad_id = %s AND uso_presentacion IS NOT NULL
    """, (esc.propiedad_a,)) == 2


def test_0330_una_sola_portada_por_entidad(esc: Escenario) -> None:
    """GARANTÍA A."""
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "PORTADA", 1)
    _rechaza(esc, psycopg.errors.UniqueViolation,
             lambda: esc.vinculo(esc.foto_2, esc.propiedad_a, "ANEXO", "PORTADA", 2))


def test_0330_misma_foto_no_duplicable_en_la_misma_galeria(esc: Escenario) -> None:
    """GARANTÍA B. Sin ella el UNIQUE histórico permitiría la misma foto dos
    veces en la misma entidad bajo roles documentales distintos."""
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "GALERIA", 1)
    _rechaza(esc, psycopg.errors.UniqueViolation,
             lambda: esc.vinculo(esc.foto, esc.propiedad_a, "EVIDENCIA", "GALERIA", 2))


def test_0330_portada_y_galeria_del_mismo_documento_excluidas(esc: Escenario) -> None:
    """PORTADA ya participa en la galería: no hace falta una segunda fila y la
    garantía B la impide."""
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "PORTADA", 1)
    _rechaza(esc, psycopg.errors.UniqueViolation,
             lambda: esc.vinculo(esc.foto, esc.propiedad_a, "ANEXO", "GALERIA", 2))


def test_0330_misma_foto_reutilizable_en_otra_entidad(esc: Escenario) -> None:
    """La garantía B es por entidad, no global: una misma fotografía puede ser
    portada de dos propiedades distintas."""
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "PORTADA", 1)
    esc.vinculo(esc.foto, esc.propiedad_b, "PRINCIPAL", "PORTADA", 1)
    assert _uno(esc.db, """
        SELECT count(*) FROM gapto.documento_vinculos
         WHERE documento_id = %s AND uso_presentacion = 'PORTADA'
    """, (esc.foto,)) == 2


def test_0330_roles_documentales_no_visuales_intactos(esc: Escenario) -> None:
    """D-186 §2 rechazó el UNIQUE global: fuera de la presentación, el mismo
    documento conserva varios roles frente a la misma entidad."""
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", None, None)
    esc.vinculo(esc.foto, esc.propiedad_a, "EVIDENCIA", None, None)
    assert _uno(esc.db, """
        SELECT count(*) FROM gapto.documento_vinculos
         WHERE documento_id = %s AND entidad_id = %s
    """, (esc.foto, esc.propiedad_a)) == 2


def test_0330_rol_vinculo_no_cambia_de_significado(esc: Escenario) -> None:
    """uso_presentacion es ortogonal: una PORTADA puede tener cualquier rol
    documental, y el catálogo de roles no se ha ampliado."""
    definicion = _uno(esc.db, """
        SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint
         WHERE conname = 'ck_documento_vinculos__rol'
    """)
    for rol in ("PRINCIPAL", "ANEXO", "EVIDENCIA", "OTRO"):
        assert rol in definicion
    assert "PORTADA" not in definicion and "GALERIA" not in definicion


def test_0330_presentacion_solo_con_entidad(esc: Escenario) -> None:
    """D-185: la presentación visual solo tiene sentido contra una entidad."""
    tipo = _uno(esc.db, "SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")
    hecho = str(uuid.uuid4())
    esc.db.execute(
        "INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, "
        "concepto, importe_total, moneda, estado_localizacion, presupuestable) "
        "VALUES (%s, %s, %s, CURRENT_DATE, '0330', '10.0000', 'EUR', 'NO_APLICA', true)",
        (hecho, OWNER, tipo))

    def _vincular_a_hecho():
        esc.db.execute(
            "INSERT INTO gapto.documento_vinculos (id, documento_id, hecho_id, rol_vinculo, "
            "uso_presentacion) VALUES (%s, %s, %s, 'EVIDENCIA', 'GALERIA')",
            (str(uuid.uuid4()), esc.foto, hecho))

    _rechaza(esc, psycopg.errors.CheckViolation, _vincular_a_hecho)

    # El mismo vínculo SIN presentación sigue siendo legítimo.
    esc.db.execute(
        "INSERT INTO gapto.documento_vinculos (id, documento_id, hecho_id, rol_vinculo) "
        "VALUES (%s, %s, %s, 'EVIDENCIA')", (str(uuid.uuid4()), esc.foto, hecho))


def test_0330_uso_presentacion_fuera_del_catalogo_rechazado(esc: Escenario) -> None:
    _rechaza(esc, psycopg.errors.CheckViolation,
             lambda: esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "MINIATURA", 1))


@pytest.mark.parametrize("orden", [0, -1])
def test_0330_orden_no_positivo_rechazado(esc: Escenario, orden: int) -> None:
    _rechaza(esc, psycopg.errors.CheckViolation,
             lambda: esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "GALERIA", orden))


def test_0330_orden_sin_uso_rechazado(esc: Escenario) -> None:
    """Un orden sin uso visual sería un dato huérfano."""
    _rechaza(esc, psycopg.errors.CheckViolation,
             lambda: esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", None, 1))


def test_0330_uso_sin_orden_admitido(esc: Escenario) -> None:
    """El orden no es obligatorio: el read-model desempata por created_at e id."""
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "GALERIA", None)


def test_0330_orden_repetido_admitido(esc: Escenario) -> None:
    """El orden NO es identidad: no lleva UNIQUE a propósito."""
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "GALERIA", 1)
    esc.vinculo(esc.foto_2, esc.propiedad_a, "ANEXO", "GALERIA", 1)


def test_0330_legacy_sin_presentacion_es_valido(esc: Escenario) -> None:
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", None, None)
    assert _uno(esc.db, """
        SELECT count(*) FROM gapto.documento_vinculos
         WHERE documento_id = %s AND uso_presentacion IS NULL
           AND orden_presentacion IS NULL
    """, (esc.foto,)) == 1


# ------------------------------------------------------------
# Aislamiento tenant
# ------------------------------------------------------------

def test_0330_galeria_aislada_por_tenant(esc: Escenario) -> None:
    """La policy de documento_vinculos deriva de documentos.owner_user_id y es
    FOR ALL, así que el USING gobierna también la lectura de la galería."""
    esc.vinculo(esc.foto, esc.propiedad_a, "PRINCIPAL", "PORTADA", 1)
    esc.db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
    esc.db.execute("SAVEPOINT s")
    try:
        esc.db.execute("RESET ROLE")
        esc.db.execute("SET ROLE gapto_runtime")
    except psycopg.errors.InsufficientPrivilege:
        esc.db.execute("ROLLBACK TO SAVEPOINT s")
        pytest.skip("El rol del arnés no puede asumir gapto_runtime: cobertura no ejercitada.")
    assert _uno(esc.db, """
        SELECT count(*) FROM gapto.documento_vinculos WHERE entidad_id = %s
    """, (esc.propiedad_a,)) == 0


def test_0330_propiedades_aisladas_por_tenant(esc: Escenario) -> None:
    esc.geolocalizar(esc.propiedad_a, "37.771000", "-1.502000", "MANUAL")
    esc.db.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (OTRO_OWNER,))
    esc.db.execute("SAVEPOINT s")
    try:
        esc.db.execute("RESET ROLE")
        esc.db.execute("SET ROLE gapto_runtime")
    except psycopg.errors.InsufficientPrivilege:
        esc.db.execute("ROLLBACK TO SAVEPOINT s")
        pytest.skip("El rol del arnés no puede asumir gapto_runtime: cobertura no ejercitada.")
    assert _uno(esc.db, """
        SELECT count(*) FROM gapto.propiedades WHERE entidad_id = %s
    """, (esc.propiedad_a,)) == 0
