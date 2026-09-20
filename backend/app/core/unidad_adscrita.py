# ============================================================
# GAPTO MOBILE 2027
# Fichero: unidad_adscrita.py
# Ruta: backend/app/core/unidad_adscrita.py
# Descripcion: Unidad de trabajo ADSCRITA a una transaccion ya abierta.
#
#   PARA QUE EXISTE. F04-D038 §3 exige que una llamada OP-19 sea UNA sola
#   transaccion reutilizando las capacidades certificadas de OP-01, OP-04,
#   OP-05, OP-06, OP-08 y OP-09, sin duplicar sus validadores ni crear una
#   segunda arquitectura. Hoy cada servicio abre su propia transaccion:
#   encadenar sus metodos publicos daria cuatro COMMIT independientes, que es
#   justo lo que §4 prohibe.
#
#   COMO LO RESUELVE. La frontera transaccional no vive en los servicios: vive
#   en `UnidadDeTrabajo`, que los servicios reciben por constructor. Esta clase
#   presenta la MISMA interfaz (`ejecutar_con_traza`) pero, en lugar de abrir
#   conexion y transaccion, ejecuta la operacion sobre la sesion que ya esta
#   abierta. El orquestador de OP-19 construye los servicios existentes
#   adscritos a su propia transaccion y llama a sus metodos publicos tal cual.
#
#   Consecuencia deliberada: CERO cambios en los servicios certificados de
#   F04-01..F04-03. Se reutiliza su codigo entero —validaciones, prevalidacion
#   D-169, auditoria, guardas— sin copiar una sola linea y sin tocar ficheros
#   ya cerrados. La alternativa, extraer los closures internos de siete metodos
#   repartidos en tres ficheros certificados, era refactor mecanico sobre
#   superficie cerrada a cambio de ninguna ganancia funcional.
#
#   LO QUE ESTA CLASE NO HACE, Y POR QUE:
#
#   - NO reintenta. El retry de D-171 envuelve la TRANSACCION COMPLETA, y aqui
#     la transaccion es la del orquestador. Reintentar un paso interno sobre
#     una transaccion ya abortada es imposible, y reintentarlo sobre una sana
#     dejaria efectos a medias. Un `40P01` sube intacto para que lo reintegre
#     quien abrio la transaccion.
#
#   - NO abre savepoints. Un savepoint permitiria que un paso fallase y los
#     anteriores sobreviviesen: exactamente el commit parcial que §4 prohibe.
#     Si falla cualquier componente solicitado, cae la invocacion entera.
#
#   - NO fija el contexto tenant/actor. Las GUC ya fueron fijadas con
#     `SET LOCAL` por la transaccion anfitriona y duran hasta su final.
#     Reescribirlas a mitad seria ruido, y hacerlo con otro contexto seria un
#     cruce de tenant dentro de una misma transaccion.
#
#   - NO confirma ni deshace nada. El COMMIT, con la validacion de las
#     constraints diferidas de 0310, sigue ocurriendo una sola vez y en un
#     unico sitio: al salir del bloque de la transaccion anfitriona.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

from typing import Callable, TypeVar

from app.core.contexto import ContextoOperacion
from app.core.unidad_trabajo import Resultado, SesionMotor, Traza

T = TypeVar("T")


class UnidadDeTrabajoAdscrita:
    """Sustituto de `UnidadDeTrabajo` para operaciones internas compuestas.

    Se construye con la sesion viva del orquestador y se inyecta en los
    servicios existentes exactamente igual que la unidad real. Para el
    servicio la diferencia es invisible: recibe una `SesionMotor` y devuelve
    su resultado.
    """

    __slots__ = ("_sesion",)

    def __init__(self, sesion: SesionMotor) -> None:
        self._sesion = sesion

    @property
    def sesion(self) -> SesionMotor:
        return self._sesion

    def ejecutar_con_traza(
        self,
        contexto: ContextoOperacion,
        operacion: Callable[[SesionMotor], T],
        *,
        nombre: str = "operacion",
    ) -> Resultado[T]:
        """Ejecuta el paso sobre la transaccion anfitriona.

        La traza se emite con un unico intento porque, por construccion, aqui
        no hay reintento posible: el intento real lo cuenta la unidad que
        abrio la transaccion.
        """
        traza = Traza(operacion=nombre, request_id=contexto.request_id)
        traza.intentos_realizados = 1
        valor = operacion(self._sesion)
        return Resultado(valor=valor, traza=traza)
