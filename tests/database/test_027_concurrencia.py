# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_027_concurrencia.py
# Ruta: tests/database/test_027_concurrencia.py
# Descripción: FASE 03, frente de concurrencia READ COMMITTED. Batería de
#              concurrencia REAL sobre los constraint triggers diferidos que
#              bloquean al padre y sobre los EXCLUDE temporales. Usa varias
#              conexiones simultáneas, hace COMMIT de verdad y comprueba que
#              los bloqueos ocurren, no solo el estado final.
#
#              SOLO se ejecuta contra el laboratorio: exige la variable
#              GAPTO_CONCURRENCY_URL y que current_database() sea
#              gapto2027_cleanroom. Sin la variable, el módulo entero se
#              salta y la suite normal no cambia. Con la variable apuntando a
#              cualquier otra base, falla de forma explícita.
#
#              Rol: las operaciones bajo prueba se ejecutan como
#              gapto_runtime con contexto de tenant (camino real de
#              producción). Montaje, lectura del estado final y limpieza van
#              por una conexión administrativa separada como gapto_owner.
#
#              Cada caso emite una etiqueta:
#                PASS                        -> propiedad cumplida y bloqueo observado
#                PASS_WITH_EXPECTED_DEADLOCK -> 40P01 en una transacción, estado
#                                               final correcto y reintento completo
#                                               de la transacción con el resultado
#                                               correcto
#                FAIL_INTEGRITY              -> estado final que viola la invariante;
#                                               DETIENE el resto de la batería
#                FAIL_LIVENESS               -> operación legítima abortada, bloqueo
#                                               sin resolver o espera no justificada
#              Un resultado fuera de estas cuatro (p. ej. no se observa el
#              bloqueo que el caso exige) se marca NO_CLASIFICABLE y falla:
#              pasar sin bloquear es pasar por el motivo equivocado.
#
#              Casos:
#                C1  write-skew de suma desde vacío (participaciones), con barrera
#                C2  delta cero compensado por cierre de vigencia (vivacidad)
#                C3  write-skew temporal con conflicto directo de fila
#                C4  write-skew de atribuciones, camino INSERT (hija), con barrera
#                C4b atribuciones: INSERT en hija frente a UPDATE del padre
#                C5  EXCLUDE temporal con periodos incompatibles (regla_versiones)
#                C6  EXCLUDE temporal con periodos compatibles (vivacidad)
#                C7  deadlock multi-padre deliberado y reintento en orden fijo
#                C8  reversión autorreferente: dos reversiones que juntas superan
#                    el original (misma tabla, FK autorreferente), con barrera
#                C8b reversión autorreferente, control de vivacidad: dos
#                    reversiones que juntas caben; orden natural, sin espera
#                C9  transferencia: orden determinista de los DOS locks. Una
#                    tercera sesión (H) retiene el movimiento de salida para
#                    forzar la contención; el par invertido provocaría deadlock
#                    si los locks se tomaran por columna y no por LEAST/GREATEST
#                C10 BOLSA desde presupuesto_lineas: empate de prioridad, con barrera
#                C11 BOLSA desde presupuesto_linea_alcances: aparición del cruce
#                    de alcances, con barrera
#
#              Matriz de cobertura por TOPOLOGÍA de lock (no por tabla):
#                un padre + suma de hijas ........................ C1-C4b
#                padre e hijas en la misma tabla (autorreferencia) C8, C8b
#                dos padres bloqueados en orden determinista ..... C9
#                conflicto por JOIN provocado desde la línea ..... C10
#                conflicto por JOIN provocado desde el alcance ... C11
#                deadlock multi-padre inevitable ................. C7
#              entidad_participaciones, inversion_asignaciones_efecto y
#              hecho_movimientos_tesoreria se aceptan por EQUIVALENCIA
#              ESTRUCTURAL verificada estáticamente en test_028, no por prueba
#              empírica concurrente.
#
#              BARRERA. En C1/C4/C4b, A ejecuta SET CONSTRAINTS ALL IMMEDIATE:
#              su validación se ejecuta en ese instante y toma el lock del
#              padre, que retiene hasta terminar, igual que ocurre dentro de
#              su COMMIT. Así el solape entre validaciones es determinista y
#              no depende del azar de dos COMMIT casi simultáneos.
#
#              El modo de lock del padre que usan las funciones de invariante
#              se registra como propiedad (no se afirma), para poder leer los
#              resultados con el código realmente instalado.
#
#              Residuo aceptado: el tenant de laboratorio (usuario + actor
#              self) persiste entre ejecuciones porque
#              fn_check_actor_self_unico impide borrar el actor self. Todo lo
#              demás que crea cada caso se borra en su finally; el último
#              test verifica que no queda residuo.
#
# PRECONDICIÓN: cadena 0001..0240 aplicada en gapto2027_cleanroom.
# Versión: 0.2.0  -- añade C8, C8b, C9, C10 y C11 (topologías de lock no
#                   cubiertas por C1-C7) y la sesión H para C9.
#                   v0.1.0: C1-C7.
# ============================================================

from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import psycopg
import pytest
from psycopg import pq

URL = os.getenv("GAPTO_CONCURRENCY_URL")

pytestmark = pytest.mark.skipif(
    not URL,
    reason="GAPTO_CONCURRENCY_URL no definida: la batería de concurrencia solo se "
    "ejecuta contra el laboratorio gapto2027_cleanroom",
)

BASE_LABORATORIO = "gapto2027_cleanroom"
OWNER_LAB = "c0270000-0000-4000-8000-000000000001"
SELF_LAB = "c0270000-0000-4000-8000-000000000002"

ETIQUETAS = ("PASS", "PASS_WITH_EXPECTED_DEADLOCK", "FAIL_INTEGRITY", "FAIL_LIVENESS")
SQLSTATE_INVARIANTE = "P0001"
SQLSTATE_DEADLOCK = "40P01"
SQLSTATE_EXCLUSION = "23P01"
SQLSTATES_VIVACIDAD = {"55P03", "57014", "TIMEOUT_ORQUESTADOR"}

D_ENE = date(2026, 1, 1)
D_MAR = date(2026, 3, 1)
D_JUN_FIN = date(2026, 6, 30)
D_JUL = date(2026, 7, 1)
D_AGO_FIN = date(2026, 8, 31)
D_SEP = date(2026, 9, 1)
D_SEP_FIN = date(2026, 9, 30)
D_DIC_FIN = date(2026, 12, 31)

INS_CP = (
    "INSERT INTO gapto.cuenta_participaciones "
    "(cuenta_id, actor_id, porcentaje, vigente_desde, vigente_hasta) "
    "VALUES (%s, %s, %s, %s, %s)"
)
UPD_CP_HASTA = "UPDATE gapto.cuenta_participaciones SET vigente_hasta = %s WHERE id = %s"
INS_ATR = (
    "INSERT INTO gapto.efecto_atribuciones "
    "(efecto_id, actor_id, importe_atribuido, criterio_atribucion) "
    "VALUES (%s, %s, %s, 'MANUAL')"
)
UPD_EFECTO_IMPORTE = "UPDATE gapto.hecho_efectos SET importe_delta = %s WHERE id = %s"
INS_RV = (
    "INSERT INTO gapto.regla_versiones "
    "(regla_id, vigente_desde, vigente_hasta, tipo_hecho_id, flujo_tesoreria_esperado, "
    " moneda, fecha_modo, importe_modo, presupuestable) "
    "VALUES (%s, %s, %s, %s, 'SIN_MOVIMIENTO', 'EUR', 'ANCLA', 'MANUAL', true)"
)
INS_REVERSION = (
    "INSERT INTO gapto.movimientos_tesoreria "
    "(cuenta_id, fecha_movimiento, importe, confirmado_at, clase_movimiento, "
    " reversion_de_movimiento_id) "
    "VALUES (%s, CURRENT_DATE, %s, now(), 'OPERACION', %s)"
)
INS_TRANSFERENCIA = (
    "INSERT INTO gapto.transferencias (movimiento_salida_id, movimiento_entrada_id) "
    "VALUES (%s, %s)"
)
UPD_LINEA_PRIORIDAD = "UPDATE gapto.presupuesto_lineas SET prioridad_consumo = %s WHERE id = %s"
INS_ALCANCE = (
    "INSERT INTO gapto.presupuesto_linea_alcances (presupuesto_linea_id, categoria_id) "
    "VALUES (%s, %s)"
)
SET_IMMEDIATE = ("SET CONSTRAINTS ALL IMMEDIATE", None)
SET_DEFERRED = ("SET CONSTRAINTS ALL DEFERRED", None)
COMMIT = ("COMMIT", None)

_ESTADO = {"detenida_por": None}


# ------------------------------------------------------------
# Oráculos independientes de los triggers
# ------------------------------------------------------------

def suma_participacion_valida(filas: list[tuple]) -> bool:
    """Misma semántica que D-107, calculada fuera de la base.

    Cero filas = propiedad no modelada = válido. Con filas, la suma debe ser
    exactamente 100 en cada instante muestreado dentro del intervalo cubierto,
    muestreando vigente_desde y vigente_hasta + 1 día.
    """
    if not filas:
        return True
    inicio = min(desde for desde, _, _ in filas)
    abierto = any(hasta is None for _, hasta, _ in filas)
    fin = None if abierto else max(hasta for _, hasta, _ in filas)
    puntos = {desde for desde, _, _ in filas}
    puntos |= {hasta + timedelta(days=1) for _, hasta, _ in filas if hasta is not None}
    for punto in puntos:
        if punto < inicio or (fin is not None and punto > fin):
            continue
        suma = sum(
            (pct for desde, hasta, pct in filas
             if desde <= punto and (hasta is None or hasta >= punto)),
            Decimal(0),
        )
        if suma != 100:
            return False
    return True


def atribucion_parcial_valida(importe_delta: Decimal, suma: Decimal) -> bool:
    if abs(suma) > abs(importe_delta):
        return False
    if suma != 0 and (suma > 0) != (importe_delta > 0):
        return False
    return True


def versiones_sin_solape(filas: list[tuple]) -> bool:
    """Rangos cerrados [desde, hasta]; hasta NULL = abierto."""
    rangos = sorted(filas, key=lambda fila: fila[0])
    for (d1, h1), (d2, _h2) in zip(rangos, rangos[1:]):
        if h1 is None or d2 <= h1:
            return False
    return True


# ------------------------------------------------------------
# Orquestación
# ------------------------------------------------------------

@dataclass
class Operacion:
    sesion: "Sesion"
    pasos: list
    t0: float = 0.0
    t1: float | None = None
    sqlstate: str | None = None
    error: str | None = None
    paso_fallido: int | None = None
    hecho: threading.Event = field(default_factory=threading.Event)

    @property
    def ok(self) -> bool:
        return self.hecho.is_set() and self.sqlstate is None

    @property
    def duracion(self) -> float | None:
        return None if self.t1 is None else round(self.t1 - self.t0, 3)


class Sesion:
    def __init__(self, nombre: str, lock_timeout_ms: int, statement_timeout_ms: int) -> None:
        self.nombre = nombre
        self._lock_timeout_ms = lock_timeout_ms
        self._statement_timeout_ms = statement_timeout_ms
        self.conn: psycopg.Connection | None = None
        self.pid: int | None = None
        self.conectar()

    def conectar(self) -> None:
        if self.conn is not None and not self.conn.closed:
            self.conn.close()
        self.conn = psycopg.connect(URL, autocommit=True)
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT set_config('lock_timeout', %s, false)",
                           (f"{self._lock_timeout_ms}ms",))
            cursor.execute("SELECT set_config('statement_timeout', %s, false)",
                           (f"{self._statement_timeout_ms}ms",))
            cursor.execute("SELECT set_config('idle_in_transaction_session_timeout', '300s', false)")
            cursor.execute("SELECT pg_backend_pid()")
            (self.pid,) = cursor.fetchone()

    def sql(self, consulta: str, parametros: tuple | list | None = None) -> list[tuple]:
        with self.conn.cursor() as cursor:
            cursor.execute(consulta, parametros)
            return cursor.fetchall() if cursor.description else []

    def abrir_runtime(self) -> None:
        self.sql("BEGIN")
        self.sql("SET LOCAL ROLE gapto_runtime")
        self.sql("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_LAB,))

    def abortar(self) -> None:
        if self.conn is None or self.conn.closed or self.conn.broken:
            self.conectar()
            return
        if self.conn.info.transaction_status != pq.TransactionStatus.IDLE:
            try:
                self.sql("ROLLBACK")
            except psycopg.Error:
                self.conectar()

    def cancelar(self) -> None:
        cancelar = getattr(self.conn, "cancel_safe", None) or self.conn.cancel
        try:
            cancelar()
        except Exception:
            pass


class Monitor:
    """Muestrea pg_stat_activity en su propia conexión y registra esperas de lock."""

    PERIODO = 0.02

    def __init__(self, sesion: Sesion) -> None:
        self.sesion = sesion
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._mutex = threading.Lock()
        self.pids: list[int] = []
        self.registro: dict[int, dict] = {}
        self.ultimo: dict[int, bool] = {}

    def iniciar(self, pids: list[int]) -> None:
        self.detener()
        self.pids = list(pids)
        self.registro = {pid: {"segundos": 0.0, "eventos": set(), "bloqueadores": set()}
                         for pid in self.pids}
        self.ultimo = {pid: False for pid in self.pids}
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        if self._hilo is not None:
            self._parar.set()
            self._hilo.join(timeout=5)
            self._hilo = None

    def _bucle(self) -> None:
        anterior = time.monotonic()
        while not self._parar.is_set():
            ahora = time.monotonic()
            try:
                filas = self.sesion.sql(
                    "SELECT pid, wait_event_type, wait_event, pg_blocking_pids(pid) "
                    "FROM pg_catalog.pg_stat_activity WHERE pid = ANY(%s)",
                    (self.pids,),
                )
            except psycopg.Error:
                filas = []
            with self._mutex:
                vistos = set()
                for pid, tipo, evento, bloqueadores in filas:
                    vistos.add(pid)
                    en_lock = tipo == "Lock"
                    if en_lock:
                        registro = self.registro[pid]
                        registro["segundos"] += ahora - anterior
                        registro["eventos"].add(evento)
                        registro["bloqueadores"].update(bloqueadores or [])
                    self.ultimo[pid] = en_lock
                for pid in self.pids:
                    if pid not in vistos:
                        self.ultimo[pid] = False
            anterior = ahora
            time.sleep(self.PERIODO)

    def en_espera(self, pid: int) -> bool:
        with self._mutex:
            return self.ultimo.get(pid, False)

    def resumen(self, pid: int) -> str:
        with self._mutex:
            registro = self.registro.get(pid)
            if not registro or registro["segundos"] == 0:
                return "sin_espera"
            return (f"{registro['segundos']:.2f}s"
                    f"[{','.join(sorted(registro['eventos']))}]")

    def segundos(self, pid: int) -> float:
        with self._mutex:
            registro = self.registro.get(pid)
            return registro["segundos"] if registro else 0.0


class Laboratorio:
    def __init__(self) -> None:
        self.admin = Sesion("ADMIN", 60000, 120000)
        self._preflight()
        lock_timeout_ms = int(max(20.0, 5 * self.deadlock_s) * 1000)
        self.espera_maxima = max(40.0, 10 * self.deadlock_s)
        self.ventana = self.deadlock_s + 1.5
        statement_ms = int((self.espera_maxima + 15) * 1000)
        self.a = Sesion("A", lock_timeout_ms, statement_ms)
        self.b = Sesion("B", lock_timeout_ms, statement_ms)
        self.h = Sesion("H", lock_timeout_ms, statement_ms)
        self.monitor = Monitor(Sesion("MON", 10000, 10000))
        self.creados: dict[str, list[str]] = {}
        self._asegurar_tenant()

    # ---------- preflight ----------

    def _preflight(self) -> None:
        (base,) = self.admin.sql("SELECT current_database()")[0]
        if base != BASE_LABORATORIO:
            pytest.fail(
                f"GAPTO_CONCURRENCY_URL apunta a '{base}'. Esta batería hace COMMIT "
                f"real y solo puede ejecutarse contra '{BASE_LABORATORIO}'."
            )
        pid_1 = self.admin.sql("SELECT pg_backend_pid()")[0][0]
        pid_2 = self.admin.sql("SELECT pg_backend_pid()")[0][0]
        if pid_1 != pid_2:
            pytest.fail(
                "El backend cambia entre sentencias: la conexión pasa por un pooler en "
                "modo transacción. Usa conexión directa o pooler en modo sesión."
            )
        (self.version,) = self.admin.sql("SHOW server_version")[0]
        (ms,) = self.admin.sql(
            "SELECT setting::numeric FROM pg_catalog.pg_settings WHERE name = 'deadlock_timeout'"
        )[0]
        self.deadlock_s = float(ms) / 1000.0
        (aislamiento,) = self.admin.sql("SHOW default_transaction_isolation")[0]
        if aislamiento != "read committed":
            pytest.fail(f"default_transaction_isolation={aislamiento}; el baseline exige READ COMMITTED")
        faltan = self.admin.sql("""
            SELECT r FROM unnest(ARRAY['gapto_owner','gapto_runtime']) AS r
             WHERE NOT pg_catalog.pg_has_role(current_user, r, 'SET')
        """)
        if faltan:
            pytest.fail(f"el rol de conexión no puede asumir {[f[0] for f in faltan]}")
        requeridos = [
            ("gapto.cuenta_participaciones", "INSERT"), ("gapto.cuenta_participaciones", "UPDATE"),
            ("gapto.efecto_atribuciones", "INSERT"), ("gapto.hecho_efectos", "UPDATE"),
            ("gapto.cuentas", "UPDATE"), ("gapto.regla_versiones", "INSERT"),
        ]
        sin_privilegio = [
            f"{tabla}:{priv}" for tabla, priv in requeridos
            if not self.admin.sql("SELECT has_table_privilege('gapto_runtime', %s, %s)",
                                  (tabla, priv))[0][0]
        ]
        if sin_privilegio:
            pytest.fail(f"gapto_runtime carece de {sin_privilegio}")
        (fuente,) = self.admin.sql("""
            SELECT p.prosrc FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'gapto' AND p.proname = 'fn_check_participacion_suma'
        """)[0]
        fuente_min = " ".join(fuente.upper().split())
        if "FOR NO KEY UPDATE" in fuente_min:
            self.modo_lock = "FOR NO KEY UPDATE"
        elif "FOR UPDATE" in fuente_min:
            self.modo_lock = "FOR UPDATE"
        else:
            self.modo_lock = "desconocido"

    def _asegurar_tenant(self) -> None:
        self.tx_owner([
            ("INSERT INTO gapto.usuarios (id, email, nombre) "
             "VALUES (%s, 'c027-lab@example.invalid', 'Laboratorio concurrencia') "
             "ON CONFLICT (id) DO NOTHING", (OWNER_LAB,)),
            ("INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) "
             "VALUES (%s, %s, NULL) ON CONFLICT (id) DO NOTHING", (SELF_LAB, OWNER_LAB)),
        ])
        filas = self.leer("SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")
        assert filas, "falta el tipo de hecho GASTO (seed 0150)"
        self.tipo_gasto = str(filas[0][0])

    # ---------- administración como gapto_owner ----------

    def tx_owner(self, sentencias: list[tuple]) -> list[list[tuple]]:
        resultados = []
        self.admin.abortar()
        self.admin.sql("BEGIN")
        try:
            self.admin.sql("SET LOCAL ROLE gapto_owner")
            self.admin.sql("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_LAB,))
            for consulta, parametros in sentencias:
                resultados.append(self.admin.sql(consulta, parametros))
            self.admin.sql("COMMIT")
        except BaseException:
            self.admin.abortar()
            raise
        return resultados

    def leer(self, consulta: str, parametros: tuple | None = None) -> list[tuple]:
        return self.tx_owner([(consulta, parametros)])[0]

    def _anotar(self, clase: str, identificador: str) -> str:
        self.creados.setdefault(clase, []).append(identificador)
        return identificador

    def nueva_cuenta(self) -> str:
        cuenta = self._anotar("cuentas", str(uuid.uuid4()))
        self.tx_owner([(
            "INSERT INTO gapto.cuentas (id, owner_user_id, nombre, tipo, naturaleza, moneda, "
            "computa_liquidez, computa_patrimonio, permite_negativo) "
            "VALUES (%s, %s, 'Cuenta C027', 'CORRIENTE', 'ACTIVO', 'EUR', true, true, false)",
            (cuenta, OWNER_LAB),
        )])
        return cuenta

    def nuevo_actor(self) -> str:
        tercero = self._anotar("terceros", str(uuid.uuid4()))
        actor = self._anotar("actores", str(uuid.uuid4()))
        self.tx_owner([
            ("INSERT INTO gapto.terceros (id, owner_user_id, nombre, naturaleza) "
             "VALUES (%s, %s, 'Tercero C027', 'PERSONA')", (tercero, OWNER_LAB)),
            ("INSERT INTO gapto.actores_financieros (id, owner_user_id, tercero_id) "
             "VALUES (%s, %s, %s)", (actor, OWNER_LAB, tercero)),
        ])
        return actor

    def participacion_inicial(self, filas: list[tuple]) -> list[str]:
        """Inserta y confirma participaciones de partida; devuelve sus ids."""
        resultados = self.tx_owner([(INS_CP + " RETURNING id", fila) for fila in filas])
        return [str(r[0][0]) for r in resultados]

    def nuevo_efecto_parcial(self, importe: Decimal) -> str:
        hecho = self._anotar("hechos", str(uuid.uuid4()))
        efecto = str(uuid.uuid4())
        self.tx_owner([
            ("INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, "
             "fecha_hecho, concepto, moneda, estado_localizacion, presupuestable) "
             "VALUES (%s, %s, %s, CURRENT_DATE, 'Hecho C027', 'EUR', 'NO_APLICA', true)",
             (hecho, OWNER_LAB, self.tipo_gasto)),
            ("INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, "
             "estado_atribucion) VALUES (%s, %s, 'GASTO', %s, 'PARCIAL')",
             (efecto, hecho, importe)),
        ])
        return efecto

    def nueva_regla(self) -> str:
        regla = self._anotar("reglas", str(uuid.uuid4()))
        self.tx_owner([(
            "INSERT INTO gapto.reglas_financieras (id, owner_user_id, nombre) "
            "VALUES (%s, %s, 'Regla C027')", (regla, OWNER_LAB),
        )])
        return regla

    def nuevo_movimiento(self, cuenta: str, importe: Decimal,
                         reversion_de: str | None = None) -> str:
        movimiento = str(uuid.uuid4())
        self.tx_owner([(
            "INSERT INTO gapto.movimientos_tesoreria (id, cuenta_id, fecha_movimiento, "
            "importe, confirmado_at, clase_movimiento, reversion_de_movimiento_id) "
            "VALUES (%s, %s, CURRENT_DATE, %s, now(), 'OPERACION', %s)",
            (movimiento, cuenta, importe, reversion_de),
        )])
        return movimiento

    def nuevo_presupuesto(self) -> str:
        presupuesto = self._anotar("presupuestos", str(uuid.uuid4()))
        self.tx_owner([(
            "INSERT INTO gapto.presupuestos (id, owner_user_id, periodo_desde, periodo_hasta, "
            "moneda, perspectiva, version_presupuesto) "
            "VALUES (%s, %s, DATE '2026-01-01', DATE '2026-12-31', 'EUR', 'TOTAL', 1)",
            (presupuesto, OWNER_LAB),
        )])
        return presupuesto

    def nueva_categoria(self) -> str:
        categoria = self._anotar("categorias", str(uuid.uuid4()))
        self.tx_owner([(
            "INSERT INTO gapto.categorias_financieras (id, owner_user_id, nombre, ambito, "
            "presupuestable_default) VALUES (%s, %s, %s, 'GASTO', true)",
            (categoria, OWNER_LAB, f"Categoria C027 {categoria}"),
        )])
        return categoria

    def nueva_bolsa(self, presupuesto: str, prioridad: int, categorias: list[str]) -> str:
        linea = str(uuid.uuid4())
        sentencias = [(
            "INSERT INTO gapto.presupuesto_lineas (id, presupuesto_id, tipo_linea, "
            "naturaleza_economica, prioridad_consumo, importe_objetivo, metodo_estimacion) "
            "VALUES (%s, %s, 'BOLSA', 'GASTO', %s, 100, 'MANUAL')",
            (linea, presupuesto, prioridad),
        )]
        sentencias += [(INS_ALCANCE, (linea, categoria)) for categoria in categorias]
        self.tx_owner(sentencias)
        return linea

    def reversiones(self, original: str) -> tuple:
        return self.leer(
            "SELECT abs(o.importe), COALESCE(sum(abs(r.importe)) "
            "       FILTER (WHERE r.estado = 'ACTIVO'), 0) "
            "FROM gapto.movimientos_tesoreria o "
            "LEFT JOIN gapto.movimientos_tesoreria r ON r.reversion_de_movimiento_id = o.id "
            "WHERE o.id = %s GROUP BY o.importe", (original,))[0]

    def transferencias(self, movimientos: list[str]) -> list[tuple]:
        return self.leer(
            "SELECT movimiento_salida_id::text, movimiento_entrada_id::text "
            "FROM gapto.transferencias "
            "WHERE movimiento_salida_id = ANY(%s::uuid[]) "
            "   OR movimiento_entrada_id = ANY(%s::uuid[])", (movimientos, movimientos))

    def empates_bolsa(self, presupuesto: str) -> int:
        return self.leer("""
            SELECT count(*)
              FROM gapto.presupuesto_lineas l1
              JOIN gapto.presupuesto_lineas l2
                ON l2.presupuesto_id = l1.presupuesto_id AND l2.id > l1.id
               AND l2.tipo_linea = 'BOLSA' AND l1.tipo_linea = 'BOLSA'
               AND l2.prioridad_consumo = l1.prioridad_consumo
              JOIN gapto.presupuesto_linea_alcances a1 ON a1.presupuesto_linea_id = l1.id
              JOIN gapto.presupuesto_linea_alcances a2 ON a2.presupuesto_linea_id = l2.id
               AND (a1.categoria_id = a2.categoria_id OR a1.entidad_id = a2.entidad_id)
             WHERE l1.presupuesto_id = %s
        """, (presupuesto,))[0][0]

    def participaciones(self, cuenta: str) -> list[tuple]:
        return self.leer(
            "SELECT vigente_desde, vigente_hasta, porcentaje "
            "FROM gapto.cuenta_participaciones WHERE cuenta_id = %s", (cuenta,))

    def atribucion(self, efecto: str) -> tuple:
        return self.leer(
            "SELECT e.importe_delta, COALESCE(sum(a.importe_atribuido), 0) "
            "FROM gapto.hecho_efectos e "
            "LEFT JOIN gapto.efecto_atribuciones a ON a.efecto_id = e.id "
            "WHERE e.id = %s GROUP BY e.importe_delta", (efecto,))[0]

    def versiones(self, regla: str) -> list[tuple]:
        return self.leer(
            "SELECT vigente_desde, vigente_hasta FROM gapto.regla_versiones "
            "WHERE regla_id = %s", (regla,))

    def limpiar(self) -> None:
        c = self.creados
        self.tx_owner([
            ("DELETE FROM gapto.efecto_atribuciones WHERE efecto_id IN "
             "(SELECT id FROM gapto.hecho_efectos WHERE hecho_id = ANY(%s::uuid[]))",
             (c.get("hechos", []),)),
            ("DELETE FROM gapto.hecho_efectos WHERE hecho_id = ANY(%s::uuid[])",
             (c.get("hechos", []),)),
            ("DELETE FROM gapto.hechos_financieros WHERE id = ANY(%s::uuid[])",
             (c.get("hechos", []),)),
            ("DELETE FROM gapto.cuenta_participaciones WHERE cuenta_id = ANY(%s::uuid[])",
             (c.get("cuentas", []),)),
            ("DELETE FROM gapto.transferencias WHERE movimiento_salida_id IN "
             "(SELECT id FROM gapto.movimientos_tesoreria WHERE cuenta_id = ANY(%s::uuid[])) "
             "OR movimiento_entrada_id IN "
             "(SELECT id FROM gapto.movimientos_tesoreria WHERE cuenta_id = ANY(%s::uuid[]))",
             (c.get("cuentas", []), c.get("cuentas", []))),
            ("DELETE FROM gapto.movimientos_tesoreria WHERE cuenta_id = ANY(%s::uuid[]) "
             "AND reversion_de_movimiento_id IS NOT NULL", (c.get("cuentas", []),)),
            ("DELETE FROM gapto.movimientos_tesoreria WHERE cuenta_id = ANY(%s::uuid[])",
             (c.get("cuentas", []),)),
            ("DELETE FROM gapto.cuentas WHERE id = ANY(%s::uuid[])", (c.get("cuentas", []),)),
            ("DELETE FROM gapto.presupuesto_linea_alcances WHERE presupuesto_linea_id IN "
             "(SELECT id FROM gapto.presupuesto_lineas WHERE presupuesto_id = ANY(%s::uuid[]))",
             (c.get("presupuestos", []),)),
            ("DELETE FROM gapto.presupuesto_lineas WHERE presupuesto_id = ANY(%s::uuid[])",
             (c.get("presupuestos", []),)),
            ("DELETE FROM gapto.presupuestos WHERE id = ANY(%s::uuid[])",
             (c.get("presupuestos", []),)),
            ("DELETE FROM gapto.categorias_financieras WHERE id = ANY(%s::uuid[])",
             (c.get("categorias", []),)),
            ("DELETE FROM gapto.regla_versiones WHERE regla_id = ANY(%s::uuid[])",
             (c.get("reglas", []),)),
            ("DELETE FROM gapto.reglas_financieras WHERE id = ANY(%s::uuid[])",
             (c.get("reglas", []),)),
            ("DELETE FROM gapto.actores_financieros WHERE id = ANY(%s::uuid[])",
             (c.get("actores", []),)),
            ("DELETE FROM gapto.terceros WHERE id = ANY(%s::uuid[])", (c.get("terceros", []),)),
        ])
        self.creados = {}

    # ---------- ejecución concurrente ----------

    def lote(self, sesion: Sesion, pasos: list[tuple]) -> Operacion:
        """Ejecuta los pasos en orden, en un hilo, sobre la conexión de la sesión."""
        operacion = Operacion(sesion=sesion, pasos=pasos)

        def ejecutar() -> None:
            operacion.t0 = time.monotonic()
            try:
                for indice, (consulta, parametros) in enumerate(pasos):
                    operacion.paso_fallido = indice
                    sesion.sql(consulta, parametros)
                operacion.paso_fallido = None
            except psycopg.Error as error:
                operacion.sqlstate = error.sqlstate or "SIN_SQLSTATE"
                operacion.error = str(error).splitlines()[0][:200]
            except Exception as error:  # noqa: BLE001
                operacion.sqlstate = "PYTHON"
                operacion.error = repr(error)[:200]
            finally:
                operacion.t1 = time.monotonic()
                operacion.hecho.set()

        threading.Thread(target=ejecutar, daemon=True).start()
        return operacion

    def observar(self, operacion: Operacion) -> str:
        """TERMINADA, BLOQUEADA (esperando un lock) o EN_CURSO tras la ventana."""
        limite = time.monotonic() + self.ventana
        while time.monotonic() < limite:
            if operacion.hecho.is_set():
                return "TERMINADA"
            if self.monitor.en_espera(operacion.sesion.pid):
                return "BLOQUEADA"
            time.sleep(0.02)
        return "TERMINADA" if operacion.hecho.is_set() else "EN_CURSO"

    def esperar(self, *operaciones: Operacion) -> None:
        for operacion in operaciones:
            if not operacion.hecho.wait(self.espera_maxima):
                operacion.sesion.cancelar()
                operacion.hecho.wait(10)
                if not operacion.hecho.is_set():
                    operacion.sesion.conn.close()
                    operacion.hecho.wait(5)
                operacion.sqlstate = "TIMEOUT_ORQUESTADOR"

    def ejecutar(self, sesion: Sesion, pasos: list[tuple]) -> Operacion:
        operacion = self.lote(sesion, pasos)
        self.esperar(operacion)
        return operacion

    def reintentar(self, sesion: Sesion, pasos: list[tuple]) -> Operacion:
        """Reintenta la TRANSACCIÓN COMPLETA, no solo el COMMIT."""
        sesion.abortar()
        sesion.abrir_runtime()
        operacion = self.ejecutar(sesion, pasos + [COMMIT])
        sesion.abortar()
        return operacion

    def cerrar(self) -> None:
        self.monitor.detener()
        for sesion in (self.a, self.b, self.h, self.monitor.sesion, self.admin):
            try:
                sesion.conn.close()
            except Exception:
                pass


# ------------------------------------------------------------
# Fixtures y emisión de resultados
# ------------------------------------------------------------

@pytest.fixture(scope="module")
def lab():
    laboratorio = Laboratorio()
    yield laboratorio
    laboratorio.cerrar()


@pytest.fixture(autouse=True)
def _bateria_detenida():
    if _ESTADO["detenida_por"]:
        pytest.skip(f"batería detenida por FAIL_INTEGRITY en {_ESTADO['detenida_por']}")


@pytest.fixture
def caso(lab):
    """Garantiza sesiones limpias antes y limpieza completa después de cada caso."""
    lab.a.abortar()
    lab.b.abortar()
    lab.h.abortar()
    yield lab
    lab.monitor.detener()
    lab.a.abortar()
    lab.b.abortar()
    lab.h.abortar()
    lab.limpiar()


def emitir(prop, nombre: str, etiqueta: str, detalle: dict) -> None:
    prop(f"{nombre}.etiqueta", etiqueta)
    for clave, valor in detalle.items():
        prop(f"{nombre}.{clave}", str(valor))
    linea = "; ".join(f"{k}={v}" for k, v in detalle.items())
    print(f"\n[{nombre}] {etiqueta} :: {linea}")
    if etiqueta == "FAIL_INTEGRITY":
        _ESTADO["detenida_por"] = nombre
        pytest.fail(f"{nombre}: FAIL_INTEGRITY. Batería detenida. {linea}")
    if etiqueta == "FAIL_LIVENESS":
        pytest.fail(f"{nombre}: FAIL_LIVENESS. {linea}")
    if etiqueta not in ETIQUETAS:
        pytest.fail(f"{nombre}: {etiqueta}. {linea}")


def _op(operacion: Operacion) -> str:
    if operacion.sqlstate is None:
        return f"OK({operacion.duracion}s)"
    return f"{operacion.sqlstate}({operacion.duracion}s)"


# ------------------------------------------------------------
# Plantilla con barrera: C1, C4, C4b
# ------------------------------------------------------------

def _caso_con_barrera(lab: Laboratorio, prop, nombre: str, pasos_a: list, pasos_b: list,
                      estado_valido) -> None:
    """A y B preparan; A valida ya (barrera) reteniendo el lock del padre; B
    confirma; A confirma. Como mucho una puede confirmar si ambas juntas
    violan la invariante; ninguna puede quedar abortada sin motivo."""
    lab.monitor.iniciar([lab.a.pid, lab.b.pid])
    lab.a.abrir_runtime()
    preparar_a = lab.ejecutar(lab.a, pasos_a)
    lab.b.abrir_runtime()
    preparar_b = lab.ejecutar(lab.b, pasos_b)
    if not (preparar_a.ok and preparar_b.ok):
        lab.monitor.detener()
        emitir(prop, nombre, "NO_CLASIFICABLE",
               {"preparar_a": _op(preparar_a), "preparar_b": _op(preparar_b),
                "error": preparar_a.error or preparar_b.error})

    validar_a = lab.lote(lab.a, [SET_IMMEDIATE])
    estado_validar_a = lab.observar(validar_a)
    fin_b = lab.lote(lab.b, [COMMIT])
    estado_fin_b = lab.observar(fin_b)
    lab.esperar(validar_a)
    fin_a = lab.ejecutar(lab.a, [COMMIT]) if validar_a.ok else validar_a
    lab.esperar(fin_b)
    lab.monitor.detener()

    detalle = {
        "modo_lock": lab.modo_lock,
        "barrera_A": estado_validar_a,
        "commit_B": estado_fin_b,
        "A": _op(fin_a),
        "B": _op(fin_b),
        "espera_A": lab.monitor.resumen(lab.a.pid),
        "espera_B": lab.monitor.resumen(lab.b.pid),
    }
    confirmadas = [x for x in (fin_a, fin_b) if x.ok]
    fallidas = [(pasos, x) for pasos, x in ((pasos_a, fin_a), (pasos_b, fin_b)) if not x.ok]

    valido = estado_valido()
    detalle["estado_final_valido"] = valido
    if not valido or len(confirmadas) == 2:
        emitir(prop, nombre, "FAIL_INTEGRITY", detalle)
    if not confirmadas:
        emitir(prop, nombre, "FAIL_LIVENESS", detalle)

    pasos_perdedora, perdedora = fallidas[0]
    if perdedora.sqlstate == SQLSTATE_INVARIANTE:
        hubo_bloqueo = "BLOQUEADA" in (estado_validar_a, estado_fin_b)
        emitir(prop, nombre, "PASS" if hubo_bloqueo else "NO_CLASIFICABLE", detalle)
        return
    if perdedora.sqlstate == SQLSTATE_DEADLOCK:
        sesion = perdedora.sesion
        reintento = lab.reintentar(sesion, pasos_perdedora)
        detalle["reintento"] = _op(reintento)
        valido = estado_valido()
        detalle["estado_tras_reintento_valido"] = valido
        if not valido or reintento.ok:
            emitir(prop, nombre, "FAIL_INTEGRITY", detalle)
        if reintento.sqlstate == SQLSTATE_INVARIANTE:
            emitir(prop, nombre, "PASS_WITH_EXPECTED_DEADLOCK", detalle)
            return
        emitir(prop, nombre, "FAIL_LIVENESS", detalle)
    if perdedora.sqlstate in SQLSTATES_VIVACIDAD:
        emitir(prop, nombre, "FAIL_LIVENESS", detalle)
    emitir(prop, nombre, "NO_CLASIFICABLE", detalle)


# ------------------------------------------------------------
# Tests
# ------------------------------------------------------------

def test_c27_00_preflight(lab, record_testsuite_property) -> None:
    """Deja constancia del entorno en el que se han obtenido los resultados."""
    record_testsuite_property("c27.base", BASE_LABORATORIO)
    record_testsuite_property("c27.server_version", lab.version)
    record_testsuite_property("c27.deadlock_timeout_s", str(lab.deadlock_s))
    record_testsuite_property("c27.modo_lock_padre", lab.modo_lock)
    print(f"\n[PREFLIGHT] base={BASE_LABORATORIO} version={lab.version} "
          f"deadlock_timeout={lab.deadlock_s}s modo_lock_padre={lab.modo_lock}")
    assert lab.deadlock_s > 0


def test_c27_c1_write_skew_suma_desde_vacio(caso, record_testsuite_property) -> None:
    """Cuenta sin participaciones. A y B insertan cada una un 100% para
    actores distintos. Cada una por separado es válida; juntas suman 200."""
    lab = caso
    cuenta = lab.nueva_cuenta()
    actor_2 = lab.nuevo_actor()
    _caso_con_barrera(
        lab, record_testsuite_property, "C1",
        [(INS_CP, (cuenta, SELF_LAB, 100, D_ENE, None))],
        [(INS_CP, (cuenta, actor_2, 100, D_ENE, None))],
        lambda: suma_participacion_valida(lab.participaciones(cuenta)),
    )


def test_c27_c2_delta_cero_compensado(caso, record_testsuite_property) -> None:
    """Partida 50/50. A cierra el actor 1 y abre el 3; B cierra el 2 y abre el
    4; ambas con delta cero. Las dos son legítimas y juntas también: deben
    confirmar las dos sin espera apreciable. Sin barrera: orden natural."""
    lab = caso
    cuenta = lab.nueva_cuenta()
    actor_2, actor_3, actor_4 = lab.nuevo_actor(), lab.nuevo_actor(), lab.nuevo_actor()
    fila_1, fila_2 = lab.participacion_inicial([
        (cuenta, SELF_LAB, 50, D_ENE, None),
        (cuenta, actor_2, 50, D_ENE, None),
    ])
    pasos_a = [(UPD_CP_HASTA, (D_JUN_FIN, fila_1)), (INS_CP, (cuenta, actor_3, 50, D_JUL, None))]
    pasos_b = [(UPD_CP_HASTA, (D_JUN_FIN, fila_2)), (INS_CP, (cuenta, actor_4, 50, D_JUL, None))]

    lab.monitor.iniciar([lab.a.pid, lab.b.pid])
    lab.a.abrir_runtime()
    preparar_a = lab.ejecutar(lab.a, pasos_a)
    lab.b.abrir_runtime()
    preparar_b = lab.ejecutar(lab.b, pasos_b)
    fin_a = lab.lote(lab.a, [COMMIT])
    estado_fin_a = lab.observar(fin_a)
    fin_b = lab.lote(lab.b, [COMMIT])
    lab.esperar(fin_a, fin_b)
    lab.monitor.detener()

    umbral = 0.25 * lab.deadlock_s
    espera_total = lab.monitor.segundos(lab.a.pid) + lab.monitor.segundos(lab.b.pid)
    detalle = {
        "modo_lock": lab.modo_lock,
        "preparar": f"{_op(preparar_a)}/{_op(preparar_b)}",
        "commit_A": estado_fin_a,
        "A": _op(fin_a),
        "B": _op(fin_b),
        "espera_A": lab.monitor.resumen(lab.a.pid),
        "espera_B": lab.monitor.resumen(lab.b.pid),
        "umbral_vivacidad_s": umbral,
    }
    valido = suma_participacion_valida(lab.participaciones(cuenta))
    detalle["estado_final_valido"] = valido
    if not (preparar_a.ok and preparar_b.ok):
        emitir(record_testsuite_property, "C2", "NO_CLASIFICABLE", detalle)
    if not valido:
        emitir(record_testsuite_property, "C2", "FAIL_INTEGRITY", detalle)
    if fin_a.ok and fin_b.ok and espera_total < umbral:
        emitir(record_testsuite_property, "C2", "PASS", detalle)
        return
    for pasos, fin in ((pasos_a, fin_a), (pasos_b, fin_b)):
        if fin.sqlstate == SQLSTATE_DEADLOCK:
            reintento = lab.reintentar(fin.sesion, pasos)
            detalle["reintento"] = _op(reintento)
            valido = suma_participacion_valida(lab.participaciones(cuenta))
            detalle["estado_tras_reintento_valido"] = valido
            if not valido:
                emitir(record_testsuite_property, "C2", "FAIL_INTEGRITY", detalle)
    emitir(record_testsuite_property, "C2", "FAIL_LIVENESS", detalle)


def test_c27_c3_write_skew_temporal(caso, record_testsuite_property) -> None:
    """Partida: actor 1 al 100% abierto. A lo cierra a 30-06 y abre el actor 2
    desde 01-07. B lo cierra a 31-08 y abre el actor 3 desde 01-09. B debe
    bloquear en su UPDATE (lock de tupla) y terminar rechazada."""
    lab = caso
    cuenta = lab.nueva_cuenta()
    actor_2, actor_3 = lab.nuevo_actor(), lab.nuevo_actor()
    (fila_1,) = lab.participacion_inicial([(cuenta, SELF_LAB, 100, D_ENE, None)])

    lab.monitor.iniciar([lab.a.pid, lab.b.pid])
    lab.a.abrir_runtime()
    preparar_a = lab.ejecutar(lab.a, [
        (UPD_CP_HASTA, (D_JUN_FIN, fila_1)),
        (INS_CP, (cuenta, actor_2, 100, D_JUL, None)),
    ])
    lab.b.abrir_runtime()
    update_b = lab.lote(lab.b, [(UPD_CP_HASTA, (D_AGO_FIN, fila_1))])
    estado_update_b = lab.observar(update_b)
    fin_a = lab.ejecutar(lab.a, [COMMIT])
    lab.esperar(update_b)
    if update_b.ok:
        fin_b = lab.ejecutar(lab.b, [(INS_CP, (cuenta, actor_3, 100, D_SEP, None)), COMMIT])
    else:
        fin_b = update_b
    lab.monitor.detener()

    valido = suma_participacion_valida(lab.participaciones(cuenta))
    detalle = {
        "modo_lock": lab.modo_lock,
        "preparar_A": _op(preparar_a),
        "update_B": estado_update_b,
        "A": _op(fin_a),
        "B": _op(fin_b),
        "espera_B": lab.monitor.resumen(lab.b.pid),
        "estado_final_valido": valido,
    }
    if not valido or (fin_a.ok and fin_b.ok):
        emitir(record_testsuite_property, "C3", "FAIL_INTEGRITY", detalle)
    if not preparar_a.ok or not fin_a.ok:
        emitir(record_testsuite_property, "C3", "FAIL_LIVENESS", detalle)
    if estado_update_b != "BLOQUEADA":
        emitir(record_testsuite_property, "C3", "NO_CLASIFICABLE", detalle)
    if fin_b.sqlstate == SQLSTATE_INVARIANTE:
        emitir(record_testsuite_property, "C3", "PASS", detalle)
        return
    if fin_b.sqlstate in SQLSTATES_VIVACIDAD or fin_b.sqlstate == SQLSTATE_DEADLOCK:
        emitir(record_testsuite_property, "C3", "FAIL_LIVENESS", detalle)
    emitir(record_testsuite_property, "C3", "NO_CLASIFICABLE", detalle)


def test_c27_c4_write_skew_atribuciones(caso, record_testsuite_property) -> None:
    """Efecto PARCIAL de -100 sin atribuciones. A y B atribuyen -100 cada una
    a actores distintos. Juntas suman -200 frente a -100."""
    lab = caso
    efecto = lab.nuevo_efecto_parcial(Decimal("-100.00"))
    actor_2 = lab.nuevo_actor()

    def valido() -> bool:
        importe, suma = lab.atribucion(efecto)
        return atribucion_parcial_valida(importe, suma)

    _caso_con_barrera(
        lab, record_testsuite_property, "C4",
        [(INS_ATR, (efecto, SELF_LAB, Decimal("-100.00")))],
        [(INS_ATR, (efecto, actor_2, Decimal("-100.00")))],
        valido,
    )


def test_c27_c4b_atribucion_frente_a_update_del_padre(caso, record_testsuite_property) -> None:
    """A atribuye -100 (válido con importe -100). B reduce el importe del
    efecto a -50 (válido sin atribuciones). Juntas: -100 atribuido sobre -50.
    Recorre los dos caminos del trigger: hija (INSERT) y padre (UPDATE)."""
    lab = caso
    efecto = lab.nuevo_efecto_parcial(Decimal("-100.00"))

    def valido() -> bool:
        importe, suma = lab.atribucion(efecto)
        return atribucion_parcial_valida(importe, suma)

    _caso_con_barrera(
        lab, record_testsuite_property, "C4b",
        [(INS_ATR, (efecto, SELF_LAB, Decimal("-100.00")))],
        [(UPD_EFECTO_IMPORTE, (Decimal("-50.00"), efecto))],
        valido,
    )


def test_c27_c5_exclude_periodos_incompatibles(caso, record_testsuite_property) -> None:
    """Dos versiones solapadas de la misma regla. B debe bloquear dentro de su
    INSERT (recheck del EXCLUDE DEFERRABLE INITIALLY IMMEDIATE) y fallar con
    23P01 cuando A confirme."""
    lab = caso
    regla = lab.nueva_regla()

    lab.monitor.iniciar([lab.a.pid, lab.b.pid])
    lab.a.abrir_runtime()
    preparar_a = lab.ejecutar(lab.a, [(INS_RV, (regla, D_ENE, D_JUN_FIN, lab.tipo_gasto))])
    lab.b.abrir_runtime()
    insert_b = lab.lote(lab.b, [(INS_RV, (regla, D_MAR, D_SEP_FIN, lab.tipo_gasto))])
    estado_insert_b = lab.observar(insert_b)
    fin_a = lab.ejecutar(lab.a, [COMMIT])
    lab.esperar(insert_b)
    fin_b = lab.ejecutar(lab.b, [COMMIT]) if insert_b.ok else insert_b
    lab.monitor.detener()

    valido = versiones_sin_solape(lab.versiones(regla))
    detalle = {
        "preparar_A": _op(preparar_a),
        "insert_B": estado_insert_b,
        "A": _op(fin_a),
        "B": _op(fin_b),
        "espera_B": lab.monitor.resumen(lab.b.pid),
        "estado_final_valido": valido,
    }
    if not valido or (fin_a.ok and fin_b.ok):
        emitir(record_testsuite_property, "C5", "FAIL_INTEGRITY", detalle)
    if not fin_a.ok:
        emitir(record_testsuite_property, "C5", "FAIL_LIVENESS", detalle)
    if fin_b.sqlstate == SQLSTATE_EXCLUSION and estado_insert_b == "BLOQUEADA":
        emitir(record_testsuite_property, "C5", "PASS", detalle)
        return
    if fin_b.sqlstate in SQLSTATES_VIVACIDAD:
        emitir(record_testsuite_property, "C5", "FAIL_LIVENESS", detalle)
    emitir(record_testsuite_property, "C5", "NO_CLASIFICABLE", detalle)


def test_c27_c6_exclude_periodos_compatibles(caso, record_testsuite_property) -> None:
    """Dos versiones contiguas sin solape: ambas deben confirmar y ninguna
    debe esperar un lock."""
    lab = caso
    regla = lab.nueva_regla()

    lab.monitor.iniciar([lab.a.pid, lab.b.pid])
    lab.a.abrir_runtime()
    insert_a = lab.ejecutar(lab.a, [(INS_RV, (regla, D_ENE, D_JUN_FIN, lab.tipo_gasto))])
    lab.b.abrir_runtime()
    insert_b = lab.lote(lab.b, [(INS_RV, (regla, D_JUL, D_DIC_FIN, lab.tipo_gasto))])
    estado_insert_b = lab.observar(insert_b)
    lab.esperar(insert_b)
    fin_a = lab.ejecutar(lab.a, [COMMIT])
    fin_b = lab.ejecutar(lab.b, [COMMIT])
    lab.monitor.detener()

    valido = versiones_sin_solape(lab.versiones(regla))
    espera = lab.monitor.segundos(lab.a.pid) + lab.monitor.segundos(lab.b.pid)
    detalle = {
        "insert_A": _op(insert_a),
        "insert_B": estado_insert_b,
        "A": _op(fin_a),
        "B": _op(fin_b),
        "espera_A": lab.monitor.resumen(lab.a.pid),
        "espera_B": lab.monitor.resumen(lab.b.pid),
        "estado_final_valido": valido,
    }
    if not valido:
        emitir(record_testsuite_property, "C6", "FAIL_INTEGRITY", detalle)
    if insert_a.ok and insert_b.ok and fin_a.ok and fin_b.ok and espera == 0:
        emitir(record_testsuite_property, "C6", "PASS", detalle)
        return
    emitir(record_testsuite_property, "C6", "FAIL_LIVENESS", detalle)


def test_c27_c7_deadlock_multi_padre(caso, record_testsuite_property) -> None:
    """Dos cuentas P1 y P2, cada una 50/50. A reparte en P1 y luego en P2; B en
    P2 y luego en P1, validando cada padre al terminar con él. Las filas
    tocadas son disjuntas: el conflicto está solo en los padres. Si aparece
    40P01, la víctima se reintenta COMPLETA en orden fijo P1 -> P2."""
    lab = caso
    p1, p2 = lab.nueva_cuenta(), lab.nueva_cuenta()
    actor_2, actor_3, actor_4 = lab.nuevo_actor(), lab.nuevo_actor(), lab.nuevo_actor()
    p1_f1, p1_f2 = lab.participacion_inicial([(p1, SELF_LAB, 50, D_ENE, None),
                                              (p1, actor_2, 50, D_ENE, None)])
    p2_f1, p2_f2 = lab.participacion_inicial([(p2, SELF_LAB, 50, D_ENE, None),
                                              (p2, actor_2, 50, D_ENE, None)])

    def reparto(fila: str, cuenta: str, actor: str) -> list[tuple]:
        return [(UPD_CP_HASTA, (D_JUN_FIN, fila)),
                (INS_CP, (cuenta, actor, 50, D_JUL, None)),
                SET_IMMEDIATE, SET_DEFERRED]

    a_p1, a_p2 = reparto(p1_f1, p1, actor_3), reparto(p2_f1, p2, actor_3)
    b_p1, b_p2 = reparto(p1_f2, p1, actor_4), reparto(p2_f2, p2, actor_4)

    lab.monitor.iniciar([lab.a.pid, lab.b.pid])
    lab.a.abrir_runtime()
    paso_a1 = lab.ejecutar(lab.a, a_p1)
    lab.b.abrir_runtime()
    paso_b1 = lab.ejecutar(lab.b, b_p2)
    paso_a2 = lab.lote(lab.a, a_p2)
    estado_a2 = lab.observar(paso_a2)
    paso_b2 = lab.lote(lab.b, b_p1)
    lab.esperar(paso_a2, paso_b2)
    fin_a = lab.ejecutar(lab.a, [COMMIT]) if paso_a2.ok else paso_a2
    fin_b = lab.ejecutar(lab.b, [COMMIT]) if paso_b2.ok else paso_b2
    lab.monitor.detener()

    detalle = {
        "modo_lock": lab.modo_lock,
        "preparar": f"{_op(paso_a1)}/{_op(paso_b1)}",
        "segundo_padre_A": estado_a2,
        "A": _op(fin_a),
        "B": _op(fin_b),
        "espera_A": lab.monitor.resumen(lab.a.pid),
        "espera_B": lab.monitor.resumen(lab.b.pid),
    }

    def valido() -> bool:
        return (suma_participacion_valida(lab.participaciones(p1))
                and suma_participacion_valida(lab.participaciones(p2)))

    if not (paso_a1.ok and paso_b1.ok):
        emitir(record_testsuite_property, "C7", "NO_CLASIFICABLE", detalle)
    detalle["estado_final_valido"] = valido()
    if not detalle["estado_final_valido"]:
        emitir(record_testsuite_property, "C7", "FAIL_INTEGRITY", detalle)
    if fin_a.ok and fin_b.ok:
        emitir(record_testsuite_property, "C7", "PASS", detalle)
        return
    victimas = [(fin, pasos) for fin, pasos in ((fin_a, a_p1 + a_p2), (fin_b, b_p1 + b_p2))
                if fin.sqlstate == SQLSTATE_DEADLOCK]
    supervivientes = [fin for fin in (fin_a, fin_b) if fin.ok]
    if len(victimas) == 1 and len(supervivientes) == 1:
        victima, pasos_orden_fijo = victimas[0]
        reintento = lab.reintentar(victima.sesion, pasos_orden_fijo)
        detalle["reintento_orden_fijo"] = _op(reintento)
        detalle["estado_tras_reintento_valido"] = valido()
        if not detalle["estado_tras_reintento_valido"]:
            emitir(record_testsuite_property, "C7", "FAIL_INTEGRITY", detalle)
        if reintento.ok:
            emitir(record_testsuite_property, "C7", "PASS_WITH_EXPECTED_DEADLOCK", detalle)
            return
    emitir(record_testsuite_property, "C7", "FAIL_LIVENESS", detalle)


def test_c27_c8_reversion_autorreferente(caso, record_testsuite_property) -> None:
    """Original de -100. A y B revierten +60 cada una: cada reversión cabe
    sola, juntas suman 120 frente a 100. Padre e hijas viven en la misma
    tabla (FK autorreferente reversion_de_movimiento_id)."""
    lab = caso
    cuenta = lab.nueva_cuenta()
    original = lab.nuevo_movimiento(cuenta, Decimal("-100.0000"))

    def valido() -> bool:
        importe, revertido = lab.reversiones(original)
        return revertido <= importe

    _caso_con_barrera(
        lab, record_testsuite_property, "C8",
        [(INS_REVERSION, (cuenta, Decimal("60.0000"), original))],
        [(INS_REVERSION, (cuenta, Decimal("60.0000"), original))],
        valido,
    )


def test_c27_c8b_reversion_control_vivacidad(caso, record_testsuite_property) -> None:
    """Original de -100. A revierte +60 y B +40: juntas caben exactamente.
    Orden natural, sin barrera: ambas deben confirmar sin espera apreciable."""
    lab = caso
    cuenta = lab.nueva_cuenta()
    original = lab.nuevo_movimiento(cuenta, Decimal("-100.0000"))

    lab.monitor.iniciar([lab.a.pid, lab.b.pid])
    lab.a.abrir_runtime()
    preparar_a = lab.ejecutar(lab.a, [(INS_REVERSION, (cuenta, Decimal("60.0000"), original))])
    lab.b.abrir_runtime()
    preparar_b = lab.ejecutar(lab.b, [(INS_REVERSION, (cuenta, Decimal("40.0000"), original))])
    fin_a = lab.lote(lab.a, [COMMIT])
    estado_fin_a = lab.observar(fin_a)
    fin_b = lab.lote(lab.b, [COMMIT])
    lab.esperar(fin_a, fin_b)
    lab.monitor.detener()

    importe, revertido = lab.reversiones(original)
    umbral = 0.25 * lab.deadlock_s
    espera = lab.monitor.segundos(lab.a.pid) + lab.monitor.segundos(lab.b.pid)
    detalle = {
        "modo_lock": lab.modo_lock,
        "preparar": f"{_op(preparar_a)}/{_op(preparar_b)}",
        "commit_A": estado_fin_a,
        "A": _op(fin_a),
        "B": _op(fin_b),
        "espera_A": lab.monitor.resumen(lab.a.pid),
        "espera_B": lab.monitor.resumen(lab.b.pid),
        "revertido": f"{revertido}/{importe}",
        "estado_final_valido": revertido <= importe,
    }
    if not (preparar_a.ok and preparar_b.ok):
        emitir(record_testsuite_property, "C8b", "NO_CLASIFICABLE", detalle)
    if revertido > importe:
        emitir(record_testsuite_property, "C8b", "FAIL_INTEGRITY", detalle)
    if fin_a.ok and fin_b.ok and espera < umbral and revertido == importe:
        emitir(record_testsuite_property, "C8b", "PASS", detalle)
        return
    emitir(record_testsuite_property, "C8b", "FAIL_LIVENESS", detalle)


def test_c27_c9_transferencia_orden_de_locks(caso, record_testsuite_property) -> None:
    """Dos locks sobre movimientos_tesoreria en orden LEAST/GREATEST.

    H retiene con FOR NO KEY UPDATE el movimiento de SALIDA de A. A inserta
    la transferencia válida (salida=Mout, entrada=Min) y valida; B inserta el
    par invertido (salida=Min, entrada=Mout) y valida. Ambas quedan en
    contención y H libera.

    Con locks ordenados por identificador, ninguna retiene un movimiento
    mientras espera el otro en orden opuesto: cero deadlock, A confirma y B
    se rechaza por la invariante (su salida es positiva). Si los locks se
    tomaran por columna (salida y luego entrada), B retendría Min esperando
    Mout, A obtendría Mout esperando Min, y habría 40P01. Por eso este caso
    discrimina el orden, cosa que dos COMMIT sucesivos no harían."""
    lab = caso
    cuenta_x, cuenta_y = lab.nueva_cuenta(), lab.nueva_cuenta()
    m_out = lab.nuevo_movimiento(cuenta_x, Decimal("-100.0000"))
    m_in = lab.nuevo_movimiento(cuenta_y, Decimal("100.0000"))

    lab.monitor.iniciar([lab.a.pid, lab.b.pid])
    lab.h.sql("BEGIN")
    lab.h.sql("SET LOCAL ROLE gapto_owner")
    lab.h.sql("SELECT set_config('gapto.owner_user_id', %s, true)", (OWNER_LAB,))
    lab.h.sql("SELECT 1 FROM gapto.movimientos_tesoreria WHERE id = %s FOR NO KEY UPDATE",
              (m_out,))

    lab.a.abrir_runtime()
    preparar_a = lab.ejecutar(lab.a, [(INS_TRANSFERENCIA, (m_out, m_in))])
    validar_a = lab.lote(lab.a, [SET_IMMEDIATE])
    estado_a = lab.observar(validar_a)
    lab.b.abrir_runtime()
    preparar_b = lab.ejecutar(lab.b, [(INS_TRANSFERENCIA, (m_in, m_out))])
    validar_b = lab.lote(lab.b, [SET_IMMEDIATE])
    estado_b = lab.observar(validar_b)

    lab.h.sql("ROLLBACK")
    lab.esperar(validar_a)
    fin_a = lab.ejecutar(lab.a, [COMMIT]) if validar_a.ok else validar_a
    lab.esperar(validar_b)
    fin_b = lab.ejecutar(lab.b, [COMMIT]) if validar_b.ok else validar_b
    lab.monitor.detener()

    filas = lab.transferencias([m_out, m_in])
    detalle = {
        "modo_lock": lab.modo_lock,
        "preparar": f"{_op(preparar_a)}/{_op(preparar_b)}",
        "validar_A": estado_a,
        "validar_B": estado_b,
        "A": _op(fin_a),
        "B": _op(fin_b),
        "espera_A": lab.monitor.resumen(lab.a.pid),
        "espera_B": lab.monitor.resumen(lab.b.pid),
        "transferencias_finales": len(filas),
    }
    if not (preparar_a.ok and preparar_b.ok):
        emitir(record_testsuite_property, "C9", "NO_CLASIFICABLE", detalle)
    if len(filas) > 1 or (filas and filas[0] != (m_out, m_in)):
        emitir(record_testsuite_property, "C9", "FAIL_INTEGRITY", detalle)
    if SQLSTATE_DEADLOCK in (fin_a.sqlstate, fin_b.sqlstate) or not fin_a.ok:
        emitir(record_testsuite_property, "C9", "FAIL_LIVENESS", detalle)
    if estado_a != "BLOQUEADA" or estado_b != "BLOQUEADA":
        emitir(record_testsuite_property, "C9", "NO_CLASIFICABLE", detalle)
    if fin_b.sqlstate == SQLSTATE_INVARIANTE:
        emitir(record_testsuite_property, "C9", "PASS", detalle)
        return
    if fin_b.sqlstate in SQLSTATES_VIVACIDAD:
        emitir(record_testsuite_property, "C9", "FAIL_LIVENESS", detalle)
    emitir(record_testsuite_property, "C9", "NO_CLASIFICABLE", detalle)


def test_c27_c10_bolsa_empate_desde_linea(caso, record_testsuite_property) -> None:
    """Dos BOLSA con alcance cruzado y prioridades 10 y 20 (válido). A sube
    la primera a 30; B sube la segunda a 30. Cada cambio es válido frente al
    estado inicial; juntos empatan. Ejercita fn_check_bolsa_prioridad."""
    lab = caso
    presupuesto = lab.nuevo_presupuesto()
    categoria = lab.nueva_categoria()
    linea_1 = lab.nueva_bolsa(presupuesto, 10, [categoria])
    linea_2 = lab.nueva_bolsa(presupuesto, 20, [categoria])
    _caso_con_barrera(
        lab, record_testsuite_property, "C10",
        [(UPD_LINEA_PRIORIDAD, (30, linea_1))],
        [(UPD_LINEA_PRIORIDAD, (30, linea_2))],
        lambda: lab.empates_bolsa(presupuesto) == 0,
    )


def test_c27_c11_bolsa_cruce_desde_alcance(caso, record_testsuite_property) -> None:
    """Dos BOLSA con la misma prioridad y alcances disjuntos (A y B, válido).
    A añade la categoría C a la primera; B añade C a la segunda. Cada alta es
    válida frente al estado inicial; juntas crean el cruce con empate.
    Ejercita fn_check_bolsa_prioridad_alcance (la segunda vía de D-108)."""
    lab = caso
    presupuesto = lab.nuevo_presupuesto()
    cat_a, cat_b, cat_c = lab.nueva_categoria(), lab.nueva_categoria(), lab.nueva_categoria()
    linea_1 = lab.nueva_bolsa(presupuesto, 10, [cat_a])
    linea_2 = lab.nueva_bolsa(presupuesto, 10, [cat_b])
    _caso_con_barrera(
        lab, record_testsuite_property, "C11",
        [(INS_ALCANCE, (linea_1, cat_c))],
        [(INS_ALCANCE, (linea_2, cat_c))],
        lambda: lab.empates_bolsa(presupuesto) == 0,
    )


def test_c27_99_sin_residuos(lab) -> None:
    """Tras la batería solo puede quedar el tenant de laboratorio (usuario +
    actor self). Cualquier otra fila indica una limpieza incompleta."""
    fila = lab.leer("""
        SELECT (SELECT count(*) FROM gapto.cuentas WHERE owner_user_id = %(o)s),
               (SELECT count(*) FROM gapto.cuenta_participaciones cp
                  JOIN gapto.cuentas c ON c.id = cp.cuenta_id WHERE c.owner_user_id = %(o)s),
               (SELECT count(*) FROM gapto.terceros WHERE owner_user_id = %(o)s),
               (SELECT count(*) FROM gapto.actores_financieros
                 WHERE owner_user_id = %(o)s AND tercero_id IS NOT NULL),
               (SELECT count(*) FROM gapto.hechos_financieros WHERE owner_user_id = %(o)s),
               (SELECT count(*) FROM gapto.reglas_financieras WHERE owner_user_id = %(o)s),
               (SELECT count(*) FROM gapto.presupuestos WHERE owner_user_id = %(o)s),
               (SELECT count(*) FROM gapto.categorias_financieras WHERE owner_user_id = %(o)s)
    """, {"o": OWNER_LAB})[0]
    assert tuple(fila) == (0, 0, 0, 0, 0, 0, 0, 0), (
        "residuo en el laboratorio (cuentas, participaciones, terceros, actores no self, "
        f"hechos, reglas, presupuestos, categorias) = {tuple(fila)}"
    )
