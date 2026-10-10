# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_154_f05_01_inventario_categorias.py
# Ruta: tests/api/test_154_f05_01_inventario_categorias.py
# Descripcion: Inventario FAIL-CLOSED de escritores y consumidores de
#   categoria (F05-D009 §23.3 C-b; mandato F05-01 backend v0.2, AJ-03).
#   Test estatico: no necesita base de datos.
#
#   Se congela la PROPIEDAD, no la cardinalidad (el baseline de H2 era 16
#   ficheros / 28 lineas en backend/app). Reglas:
#
#   I1  Toda funcion (o nivel de modulo) del codigo productivo que mencione
#       `categoria_id` esta REGISTRADA con write-path + operacion + semantica.
#       Una aparicion nueva sin registrar, o un registro que ya no existe,
#       hace fallar el test. Si un componente tuviera caminos A y B, se
#       registran como entradas separadas (una por funcion).
#   I2  Clases:
#         A_FRONTERA  composicion de una seleccion NUEVA en la frontera F05;
#                     solo es valida tras la guarda C-a (se verifica en I4).
#         GUARDA      la guarda C-a y su punto de invocacion.
#         A_MOTOR     write-path del motor F04 que persiste una seleccion
#                     nueva sin guarda propia (la guarda es de la frontera).
#         B           referencia historica o correccion: no revalida
#                     selectabilidad actual (D-194, C04, D-198).
#         P           semantica A/B dependiente de una superficie F05 aun no
#                     contratada: la frontera NO puede alcanzarla (I3).
#         R           lectura, declaracion de tipo/columna o valor NULL fijo.
#   I3  La frontera F05 (backend/app/api, backend/app/categorias) solo contiene
#       apariciones R, GUARDA o A_FRONTERA y solo alcanza el motor a traves de
#       OP-22 (HechosCompuestosService): no referencia directamente servicios
#       con caminos A_MOTOR, B o P.
#   I4  La guarda se invoca DESPUES del reconocimiento de identidad (dentro de
#       la rama `not ya_materializada`) y ANTES de `componer`; `componer`
#       tiene un unico llamador productivo.
#   I5  Escritores de `categorias_financieras`: ninguno en runtime hasta S4, y
#       DELETE/TRUNCATE prohibidos siempre (`DELETE writers = 0`, F05-01-R12).
#   I6  SQL con nombre de tabla dinamico: solo las construcciones de la lista
#       blanca, cada una SELECT sobre un conjunto cerrado que no contiene
#       `categorias_financieras`; y ninguna construccion troceada de los
#       literales `categoria_id` / `categorias_financieras`.
#   I7  Cliente movil y scripts/dev: ninguna mencion sin registrar. Unica
#       exclusion cerrada: el arnes de mutacion (texto de mutantes).
#
#   v0.2.0 (F05-01, S4; AJ-S4-01): clase CATALOGO para el paquete de gestion
#   del arbol (escribe/lee categorias_financieras; NO consume
#   hecho_efectos.categoria_id). I5 autoriza exactamente
#   backend/app/categorias/repositorio.py como escritor del catalogo (INSERT y
#   UPDATE; DELETE = 0). I8: toda funcion publica de servicio.py toma el
#   advisory como PRIMERA llamada, y las primitivas de escritura del
#   repositorio solo se invocan desde servicio.py.
#
#   v0.3.0 (F05-01, S6-C07; F05-D014 §28.2 "Inventario C-b"): se amplia a
#   las magnitudes.
#   I4  ademas: C07 (`validar_magnitudes`) se invoca UNA vez, dentro de
#       `not ya_materializada`, DESPUES de la guarda C-a y ANTES de `componer`.
#   I9  Escritores de `magnitudes` y `categoria_magnitudes`: CERO en runtime
#       (gate F05-01-R16: todo writer futuro de asociaciones exige decision y
#       lock de la categoria padre). Escritores de `hecho_magnitudes`:
#       exactamente las primitivas certificadas de F04 en
#       contexto_repository.py (alta OP-22, correccion OP-21); la frontera F05
#       no escribe `hecho_magnitudes` directamente (solo via OP-22). Se
#       congela la propiedad (conjunto de escritores), no una cardinalidad.
#
#   v0.4.0 (F05-01 S6-ICONO (F05-D013), AJ-ICON-06): se registran la ruta
#   POST /v1/categorias/{id}/icono y el comando `cambiar_icono` (I1, I8: toma
#   el advisory como PRIMERA llamada). COLUMNAS_EDITABLES incluye `icon_key`
#   y sigue excluyendo presupuestable_default e identidad. I10: la biblioteca
#   (backend/app/categorias/iconos.py) es un modulo puro, sin SQL, sin
#   escritores y sin dependencias de acceso a datos; alta y cambiar_icono la
#   invocan antes de escribir.
#
#   v0.5.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): el comando `reordenar` entra
#   en COMANDOS (I8: advisory como PRIMERA llamada; escribe solo via
#   `_escribir` + `repo.actualizar`). Ninguna primitiva de escritura nueva:
#   `hijos_bloqueados` es lectura. I11: prohibicion de §26.3 como propiedad
#   estatica: la ruta por nodo /{id}/orden solo aparece en su declaracion de
#   app.py; ningun otro codigo productivo ni el cliente movil la invoca, y la
#   reordenacion tiene una unica ruta atomica /v1/categorias/reordenar.
#
#   v0.6.0 (F05-01 S6-WIRE+UI (este mandato); F05 §26.2 AJ-03, §28.3): I12, el
#   estado de compatibilidad retirado por S6-WIRE no aparece en el codigo
#   productivo (backend/app) ni en el cliente (mobile/src, mobile/App.tsx),
#   ni siquiera en comentarios.
#   Ademas (mismo corte): clase SEED_DEV (F05 §26.4 Q8) para los dos writers
#   SQL del seed de ENV-DEV (bootstrap_dev_db.py: `magnitudes` y
#   `categoria_magnitudes`), sin valor certificador: I9 sigue exigiendo CERO
#   escritores RUNTIME y autoriza exactamente esas dos funciones del script de
#   desarrollo. I7 pasa de «cero menciones» a REGISTRO CERRADO de menciones del
#   cliente movil (fail-closed en ambos sentidos): S6-WIRE obliga al cliente a
#   sellar `categoria_id` en el wire de §28.2 y a leer el uso de una categoria.
#
#   v0.7.0 (F05-01 S7-MAG (F05-D020 D-MAG-08)): el paquete backend/app/magnitudes
#   entra en la frontera F05 (clase CATALOGO).
#   I1  registra las rutas, DTO, lecturas, repositorio y comandos nuevos que
#       mencionan `categoria_id`.
#   I9  pasa de CERO escritores runtime a un REGISTRO CERRADO por tabla y
#       operacion: `magnitudes` INSERT/UPDATE solo en
#       backend/app/magnitudes/repositorio.py (insertar_magnitud,
#       actualizar_magnitud), DELETE runtime = 0; `categoria_magnitudes`
#       INSERT/UPDATE/DELETE solo en ese mismo fichero (insertar_asociacion,
#       actualizar_asociacion, eliminar_asociacion); mas los SEED_DEV ya
#       registrados. Un DELETE de asociaciones no autoriza borrar magnitudes.
#       Propiedades estaticas: R17 (ningun UPDATE de magnitudes con
#       unidad_default ni precision_decimales; COLUMNAS_EDITABLES_MAGNITUD =
#       {nombre, enabled}) y el modulo de magnitudes no escribe
#       categorias_financieras.
#   I8  se extiende al servicio de magnitudes: toda funcion publica mutadora
#       toma el advisory como PRIMERA llamada (tras la docstring); solo los
#       comandos (con sus funciones anidadas) y los helpers internos de
#       escritura, a su vez llamados solo desde comandos, invocan primitivas;
#       las primitivas de magnitudes solo se invocan desde
#       magnitudes/servicio.py; de categorias/repositorio.py el servicio de
#       magnitudes solo usa `tomar_advisory` y `leer` con bloquear=True.
#   Ninguna prohibicion estatica se presenta como revocacion de permisos
#   PostgreSQL (D-MAG-08).
#
#   v0.7.1 (F05-01 S7-MAG correctivo AJ-S7MAGIMPL-02): I1 registra
#   `_asociacion_id_del_alta` (deriva el asociacion_id del alta rapida de
#   magnitud_id y categoria_id; sin SQL ni escritura). Ninguna regla cambia.
#
#   v0.7.2 (F05-01 S7-MAG UI, hito 1): I7 registra la mencion del cliente movil
#   en mobile/src/domain/magnitud.ts (tipo del catalogo GET /v1/magnitudes y su
#   conversion a una vista neutra; lectura, nunca escritura) y amplia la
#   justificacion de mobile/src/api/cliente.ts (detalle de impacto de
#   deshabilitar). La reordenacion de magnitudes usa su propia ruta atomica
#   /v1/categorias/{id}/magnitudes/reordenar, que no es la ruta por nodo de I11.
#
#   v0.8.0 (F05-01 P7 · N4, AJ-P7BAT-05): I13, frontera C03 ESTRUCTURAL del
#   cliente (sin preseleccion ni propuesta de categoria), fail-closed como
#   I1..I12 y no por vocabulario:
#   I13a Camino productivo de resolucion categorial: RegistroGastoScreen.tsx
#        -> SelectorCategorias.tsx -> domain/categoria.ts (+ la lectura de
#        api/cliente.ts). Registro CERRADO de imports (modulo, nombre) de
#        esos cuatro ficheros, sin import() dinamico ni require: cualquier
#        import nuevo, o uno registrado que desaparece, falla.
#   I13b Estado categorial: el borrador nace con categoria
#        { estado: 'PENDIENTE' } (borradorInicial, unica inicializacion de
#        `b`); registro CERRADO de los sitios que escriben `categoria` y de
#        los que construyen CATEGORIA / SIN_CATEGORIA / PENDIENTE: el reinicio
#        a PENDIENTE tras un rechazo categorial, la eleccion explicita de un
#        nodo (elegirNodo, solo como onElegir del selector), «Sin categoría»
#        de la raiz y «Continuar sin categoría».
#   I13c Orden: el arbol se presenta en el orden autoritativo de la API
#        (ORDER BY orden, nombre, id); registro CERRADO (vacio) de llamadas
#        de ordenacion en el camino de I13a; construirArbol conserva el orden
#        de la lista.
#   I13d Ningun resolver de propuesta/ranking: en el camino VS-01 del
#        backend el categoria_id solo procede de la intencion
#        (`intencion.categoria_id`, propiedad que devuelve el campo sellado o
#        None); corroboracion: test_152 (ausencia -> 422, el servidor no
#        deduce categoria).
#   I13e Barrido textual corroborante acotado a los ficheros de I13a (nunca
#        oraculo unico).
#   Discriminante del mutante P03 (mutantes_f05_01.py): I13b.
#   I1 registra ademas `preparar_p7` de scripts/dev/e2e_regcat.py 0.2.0 (R:
#   lee categoria_id del detalle de impacto para confirmar por la API).
#
#   v0.8.1 (F04-D052 B2, D2 condicionado y autorizado): I1 registra UNA
#   entrada R, `PosicionesService.condonar_obligacion.extra`: el INGRESO
#   declarado de la condonacion de obligacion, con categoria_id=None fijo.
#   Sigue el contrato del GASTO declarado de `condonar_derecho` (F04-D015 §7
#   + E01: presupuestable explicito, localizacion aplicable) reutilizando
#   `_decision_hecho_condonacion`; la funcion es nueva porque cambian la
#   naturaleza, el importe (declarado <= condonado) y el ambito del duplicado
#   (por hecho). Ninguna regla cambia.
#
#   v0.9.0 (F05-02 B1, mandato v0.2 §2, opcion A del STOP): alta SOLO
#   aditiva del paquete de preferencias (F05-D026). Clase nueva PREFERENCIA:
#   usa `categoria_id` como clave de contexto de `preferencias_registro`
#   (writer y resolver de F05-02) y lee `categorias_financieras` para la
#   elegibilidad al escribir; no consume `hecho_efectos.categoria_id` ni
#   escribe el catalogo. backend/app/preferencias/ entra en FRONTERA (I3
#   admite PREFERENCIA). REGISTRO: entradas del paquete, del DTO y de las
#   rutas nuevas. EXCLUIDOS: el arnes mutantes_f05_02.py. Ninguna regla
#   (I1..I13) ni entrada previa cambia; test_170 verifica este diff.
#
#   v0.10.0 (F05-02 B2, F05-D027 §42.7; mandato B2 §1, «altas aditivas en
#   inventarios»): SOLO altas, ninguna regla ni entrada previa cambia.
#   I7  registra mobile/src/domain/preferencias.ts (lee categoria_id de la
#       intencion sellada y de las preferencias para la tarjeta «Guardar como
#       preferencia» y el ambito «Una categoria»; nunca escribe el catalogo).
#   I13a registra los imports nuevos de RegistroGastoScreen.tsx: el componente
#       GuardarPreferencia y la logica pura de domain/preferencias.ts. Ninguno
#       resuelve ni propone CATEGORIA (la propuesta es de cuenta y
#       presupuestable; C01 sigue siendo eleccion del usuario: I13b intacta).
#   La propuesta con categoria no elegible usa la guarda C-a ya registrada
#   (preferencias/lecturas.py::propuesta, clase PREFERENCIA, sin entrada nueva).
#
#   v0.11.0 (F05-02 B3, mandato B3+B4 B2, «altas aditivas en inventarios»):
#   SOLO altas, ninguna regla ni entrada previa cambia.
#   I7  registra mobile/src/screens/PreferenciasAjustesScreen.tsx (Ajustes >
#       Preferencias lee la clave `categoria_id` de cada preferencia para
#       mostrarla y la envia, completa, en el alta y la edicion por
#       /v1/preferencias; nunca escribe el catalogo).
#   I13 sin altas: la pantalla nueva no forma parte del camino de resolucion
#       categorial del registro (RegistroGastoScreen, SelectorCategorias,
#       domain/categoria, api/cliente); reutiliza SelectorCategorias sin
#       modificarlo y sus imports de cliente.ts no cambian.
#
#   v0.12.0 (F05-03/F05-04 J2 §1.6/§1.10; F05 §45.4 R3 «test_154 se amplia
#   de forma aditiva con la clase PLANTILLA y el uso de C-a»): SOLO altas,
#   ninguna regla ni entrada previa cambia.
#   - Clase nueva PLANTILLA: el paquete backend/app/plantillas/ usa
#     `categoria_id` como valor PROPUESTO por una plantilla (writer bajo el
#     advisory PLANTILLAS; elegibilidad por ambito del tipo sin lock, C-a por
#     ambito) y como capa de la propuesta del registro (lectura; la categoria
#     EXPLICITA pasa por la guarda C-a con FOR SHARE, como §43.4). No consume
#     hecho_efectos.categoria_id ni escribe el catalogo.
#   - backend/app/plantillas/ tiene su comprobacion I3 propia (aditiva):
#     solo clases R, GUARDA, A_FRONTERA o PLANTILLA y sin servicios del motor
#     con caminos A/B/P (test_i3_plantillas_frontera).
#   - EXCLUIDOS: el arnes mutantes_f05_j2j3.py (los mutantes son texto).
#
#   v0.13.0 (F05-03/F05-04 J2 §1.7; F05 §46.3 A3, A12): SOLO altas. El
#   registro de INGRESO (ejecucion_registro.py) es el SEGUNDO llamante
#   productivo de la guarda C-a (por tipo) y de C07, con el mismo contrato
#   I4: dentro de `not ya_materializada` (identidad antes) y ANTES de
#   componer (componer_ingreso, A_FRONTERA con un unico llamador). Se anaden
#   sus entradas al REGISTRO, el llamante a la lista cerrada de C07 y una
#   comprobacion I4 propia del ingreso. Las reglas I1..I13 no cambian.
#
#   v0.14.0 (F05-03 J2 §1.8/§1.10; F05 §45.4 R5): SOLO altas. El comando de
#   onboarding (backend/app/categorias/onboarding) crea el arbol con los
#   writers de C06 (servicio.alta y servicio.reordenar; clase CATALOGO) y
#   toma el advisory con servicio.tomar_advisory_del_catalogo (el recuento
#   de cero categorias se hace bajo el advisory): no importa el repositorio
#   (I8 intacta); comprobacion propia test_i8_onboarding_solo_comandos_de_c06.
# Version: 0.14.0
# ============================================================

from __future__ import annotations

import ast
import importlib
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

APP = BACKEND / "app"
FRONTERA = ("backend/app/api/", "backend/app/categorias/", "backend/app/magnitudes/", "backend/app/preferencias/")
TOKEN = "categoria_id"

# ------------------------------------------------------------------ registro
# (ruta, funcion) -> (clase, operacion, justificacion)
REGISTRO: dict[tuple[str, str], tuple[str, str, str]] = {
    # --- seed de ENV-DEV (F05 §26.4 Q8): solo desarrollo, sin valor certificador
    ("scripts/dev/bootstrap_dev_db.py", "_seed_asociaciones"): (
        "SEED_DEV", "seed ENV-DEV categoria_magnitudes", "SQL de desarrollo idempotente; nunca runtime"),
    # --- E2E web de desarrollo (corroboracion, no runtime): solo lectura de verificacion
    ("scripts/dev/e2e_vs01.py", "leer_bd"): ("R", "E2E VS-01 verificacion", "lee hecho_efectos.categoria_id del hecho registrado"),
    ("scripts/dev/e2e_regcat.py", "hechos_de"): ("R", "E2E REG-CAT verificacion", "lee categoria_id y hecho_magnitudes del hecho"),
    ("scripts/dev/e2e_regcat.py", "main"): ("R", "E2E REG-CAT", "compara el categoria_id leido con el esperado"),
    ("scripts/dev/e2e_regcat.py", "preparar_p7"): (
        "R", "E2E REG-CAT P7 fixture", "lee categoria_id del detalle de impacto para confirmar el deshabilitado por la API"),
    # --- frontera F05
    ("backend/app/api/elegibilidad_categoria.py", "validar_seleccion_categoria"): (
        "GUARDA", "F05-01 C-a", "guarda unica de elegibilidad (F05-D009 §23.3)"),
    ("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion"): (
        "GUARDA", "VS-01 intencion", "invoca la guarda tras la identidad y antes de componer (I4)"),
    ("backend/app/api/traductor_gasto_pagado.py", "componer"): (
        "A_FRONTERA", "VS-01 -> OP-22", "sella categoria_id en el efecto GASTO; guardado por I4"),
    ("backend/app/api/dto_vs01.py", "CategoriaSeleccionada"): (
        "R", "DTO", "declaracion del estado CATEGORIA del wire"),
    ("backend/app/api/dto_vs01.py", "IntencionGastoPagado.categoria_id"): (
        "R", "DTO", "lectura derivada del estado categorial sellado"),
    ("backend/app/api/dto_categorias.py", "UsoCategoria"): (
        "R", "DTO", "respuesta de lectura"),
    ("backend/app/api/app.py", "create_app.uso_categoria"): (
        "R", "GET /v1/categorias/{id}/uso", "parametro de ruta de una lectura"),
    ("backend/app/categorias/lecturas.py", "uso_por_naturaleza"): (
        "R", "lectura S3", "recuento de uso historico (C06)"),
    ("backend/app/categorias/lecturas.py", "_magnitudes_por_categoria"): (
        "R", "lectura S6-C07", "magnitudes y capturabilidad por categoria (AJ-C07-08); no es autoridad"),
    ("backend/app/api/captura_magnitudes.py", "validar_magnitudes"): (
        "GUARDA", "F05-01 C07", "C07 servidor autoridad; invocada tras C-a y antes de componer (I4)"),
    ("backend/app/api/captura_magnitudes.py", "_asociaciones"): (
        "GUARDA", "F05-01 C07", "lectura FOR SHARE de las asociaciones de la categoria (AJ-C07-07)"),
    # --- catalogo S4 (escritor/lector de categorias_financieras)
    **{("backend/app/api/app.py", f"create_app.{n}"): ("CATALOGO", "ruta S4", "parametro de ruta del comando")
       for n in ("alta_categoria", "renombrar_categoria", "mover_categoria", "desactivar_categoria",
                 "reactivar_categoria", "ordenar_categoria", "ambito_categoria", "icono_categoria")},
    **{("backend/app/categorias/servicio.py", n): ("CATALOGO", f"C06 {n}", "comando del arbol bajo advisory (I8)")
       for n in ("alta", "renombrar", "mover", "ordenar", "cambiar_ambito", "desactivar", "reactivar",
                 "cambiar_icono", "_auditar", "_nodo", "_resultado")},
    **{("backend/app/categorias/repositorio.py", n): ("CATALOGO", f"repositorio {n}", "unico escritor del catalogo (I5)")
       for n in ("leer", "snapshot", "insertar", "actualizar")},
    # --- S7-MAG (F05-D020): catalogo de magnitudes y asociaciones
    **{("backend/app/api/app.py", f"create_app.{n}"): ("CATALOGO", "ruta S7-MAG", "parametro de ruta del comando")
       for n in ("asociar_magnitud", "obligatoria_magnitud", "retirar_magnitud", "reordenar_magnitudes")},
    **{("backend/app/api/app.py", f"create_app.{n}"): ("R", "respuesta S7-MAG", "copia categoria_id a la respuesta")
       for n in ("_asociacion", "_asociaciones")},
    **{("backend/app/api/dto_magnitudes.py", n): ("R", "DTO S7-MAG", "declaracion de campo de respuesta")
       for n in ("CategoriaDeMagnitud", "ResultadoAsociacionMagnitud", "ResultadoAsociacionesMagnitud")},
    ("backend/app/magnitudes/lecturas.py", "catalogo"): (
        "R", "GET /v1/magnitudes", "categorias asociadas a cada magnitud (AJ-S7MAG-08); no es autoridad"),
    **{("backend/app/magnitudes/repositorio.py", n): ("CATALOGO", f"repositorio S7-MAG {n}",
                                                      "unico escritor runtime de categoria_magnitudes (I9)")
       for n in ("asociaciones", "categorias_obligatorias_habilitadas", "insertar_asociacion")},
    **{("backend/app/magnitudes/servicio.py", n): ("CATALOGO", f"S7-MAG {n}", "comando de magnitudes bajo advisory (I8)")
       for n in ("asociar", "asociar.escrituras", "cambiar_obligatoria", "retirar", "reordenar", "deshabilitar",
                 "_categoria_bloqueada", "_asociacion_id_del_alta", "ResultadoAsociacion", "ResultadoAsociaciones")},
    # --- F05-02 B1 (F05-D026): preferencias de registro, clave de contexto categoria_id
    **{("backend/app/api/app.py", f"create_app.{n}"): ("PREFERENCIA", "ruta F05-02", "parametro de la ruta de preferencias")
       for n in ("alta_preferencia", "editar_preferencia", "propuesta_preferencias")},
    **{("backend/app/api/dto_preferencias.py", n): ("R", "DTO F05-02", "declaracion de campo de preferencia")
       for n in ("_Contenido", "PreferenciaNodo")},
    ("backend/app/preferencias/lecturas.py", "propuesta"): (
        "PREFERENCIA", "GET /v1/preferencias/propuesta", "contexto del resolver; solo lectura"),
    ("backend/app/preferencias/repositorio.py", "<modulo>"): (
        "PREFERENCIA", "columnas de preferencias_registro", "SELECT y lista de columnas"),
    ("backend/app/preferencias/repositorio.py", "insertar_preferencia"): (
        "PREFERENCIA", "INSERT preferencias_registro", "unico escritor runtime; tras el advisory PREFERENCIAS"),
    ("backend/app/preferencias/resolver.py", "<modulo>"): (
        "PREFERENCIA", "dimensiones operativas del resolver", "coincidencia exacta, sin herencia (AJ-D026-05)"),
    ("backend/app/preferencias/resolver.py", "resolver"): (
        "PREFERENCIA", "resolver por campo", "lectura de preferencias; no consume hecho_efectos"),
    **{("backend/app/preferencias/servicio.py", n): ("PREFERENCIA", f"F05-02 {n}", "writer de preferencias bajo advisory")
       for n in ("<modulo>", "_categoria_elegible", "_validar_valores", "_valores", "alta", "editar")},
    # --- F05-03 J2 §1.6 (PLANTILLA): plantillas de registro y capa plantilla de la propuesta
    **{("backend/app/api/app.py", f"create_app.{n}"): ("R", "ruta F05-03", "parametro de la ruta de plantillas")
       for n in ("alta_plantilla", "editar_plantilla", "propuesta_registro")},
    **{("backend/app/api/dto_plantillas.py", n): ("R", "DTO F05-03", "declaracion de campo de plantilla")
       for n in ("_ContenidoPlantilla", "PlantillaNodo")},
    ("backend/app/plantillas/repositorio.py", "<modulo>"): (
        "PLANTILLA", "columnas de plantillas_registro", "SELECT y lista de columnas"),
    ("backend/app/plantillas/repositorio.py", "insertar_plantilla"): (
        "PLANTILLA", "INSERT plantillas_registro", "unico escritor runtime; tras el advisory PLANTILLAS"),
    **{("backend/app/plantillas/servicio.py", n): ("PLANTILLA", f"F05-03 {n}", "writer de plantillas bajo advisory")
       for n in ("<modulo>", "_validar", "alta", "editar")},
    ("backend/app/plantillas/lecturas.py", "_avisos"): (
        "PLANTILLA", "lista de plantillas", "aviso de categoria no elegible hoy; solo lectura"),
    ("backend/app/plantillas/propuesta.py", "propuesta_registro"): (
        "PLANTILLA", "GET /v1/registro/propuesta", "capa plantilla; categoria explicita por la guarda C-a (lectura)"),
    # --- F05-03 J2 §1.8: onboarding de categorias sugeridas (writers de C06)
    ("backend/app/categorias/onboarding/__init__.py", "onboarding_categorias"): (
        "CATALOGO", "F05-03 onboarding", "alta y reordenar de C06 bajo el advisory CATEGORIAS; sin escritor propio"),
    # --- F05-04 J2 §1.7: registro de INGRESO (C-14 via OP-22)
    ("backend/app/api/dto_registro.py", "IntencionIngresoCobrado.categoria_id"): (
        "R", "DTO F05-04", "lectura derivada del estado categorial sellado"),
    ("backend/app/api/ejecucion_registro.py", "registrar_ingreso_cobrado.operacion"): (
        "GUARDA", "F05-04 intencion INGRESO", "C-a + C07 tras la identidad y antes de componer (I4)"),
    ("backend/app/api/ejecucion_registro.py", "validar_categoria_y_magnitudes"): (
        "GUARDA", "F05-04 C-a por tipo + C07", "invoca la guarda unica C-a y C07 en ese orden"),
    ("backend/app/api/traductor_registro.py", "componer_ingreso"): (
        "A_FRONTERA", "INGRESO -> OP-22", "sella categoria_id en el efecto INGRESO; guardado por I4"),
    # --- motor F04 (certificado, no se modifica)
    ("backend/app/core/modelos_efectos.py", "DatosEfecto"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/core/modelos_devolucion.py", "DatosDevolucion"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/core/modelos_suplemento.py", "DatosSuplemento"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/core/modelos_prevision.py", "DatosVersionRegla"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/core/modelos_prevision.py", "DatosPrevisionManual"): ("R", "modelo", "campo del DTO interno"),
    ("backend/app/repositories/efectos_repository.py", "<modulo>"): (
        "R", "tipos SQL", "mapa de columnas; la escritura se registra en la funcion"),
    ("backend/app/repositories/efectos_repository.py", "insertar_efecto_si_no_existe"): (
        "A_MOTOR", "primitiva INSERT hecho_efectos",
        "persiste lo que decide el llamador: OP-04/OP-18 (A_MOTOR), OP-13/OP-21 (B/P)"),
    ("backend/app/services/efectos_service.py", "EfectosService.registrar_efectos.operacion"): (
        "A_MOTOR", "OP-04", "efecto nuevo con la categoria declarada; guarda en frontera"),
    ("backend/app/services/efectos_service.py", "EfectosService._valores_efecto"): (
        "R", "OP-04 idempotencia", "comparacion de intencion en reintento"),
    ("backend/app/services/compuesto_service.py", "HechosCompuestosService._agregado_coincide"): (
        "R", "OP-22 identidad", "comparacion exacta del agregado (F04-D051)"),
    ("backend/app/services/suplementos_service.py", "SuplementosService.registrar.operacion"): (
        "A_MOTOR", "OP-18", "realidad suplementaria nueva con categoria declarada (no se presupone B)"),
    ("backend/app/services/devoluciones_service.py", "DevolucionesService.devolver.operacion"): (
        "B", "OP-13", "categoria heredada del efecto origen (D-194); superficie F05-06"),
    ("backend/app/services/correcciones_service.py", "<modulo>"): (
        "R", "OP-21", "lista cerrada de campos corregibles"),
    ("backend/app/services/correcciones_service.py", "CorreccionesService._crear_efectos"): (
        "P", "OP-21 reemplazo", "correccion de error de captura; A/B segun superficie F05-06"),
    ("backend/app/repositories/correcciones_repository.py", "<modulo>"): (
        "R", "OP-21", "tipos SQL de la correccion"),
    ("backend/app/repositories/correcciones_repository.py", "actualizar_efecto"): (
        "P", "OP-21 UPDATE", "puede conservar referencia historica (C04) o elegir otra; superficie F05-06"),
    ("backend/app/services/posiciones_service.py", "PosicionesService.condonar_derecho.extra"): (
        "R", "OP-12/condonacion", "categoria_id=None fijo"),
    ("backend/app/services/posiciones_service.py", "PosicionesService.condonar_obligacion.extra"): (
        "R", "condonacion de obligacion (F04-D052)", "INGRESO declarado, categoria_id=None fijo"),
    ("backend/app/services/posiciones_service.py", "PosicionesService._crear_delta"): (
        "R", "OP-12 delta", "categoria_id=None fijo"),
    ("backend/app/services/reglas_service.py", "ReglasService._insertar_version"): (
        "P", "regla_versiones", "expectativa configurada; superficie de reglas no contratada en F05-01"),
    ("backend/app/repositories/reglas_repository.py", "<modulo>"): ("R", "tipos SQL", "mapa de columnas"),
    ("backend/app/services/previsiones_service.py", "PrevisionesService.crear_manual.operacion"): (
        "P", "prevision manual", "expectativa; superficie no contratada en F05-01"),
    ("backend/app/services/previsiones_service.py", "PrevisionesService._materializar_ocurrencia"): (
        "B", "generacion", "snapshot de la version de regla ya configurada"),
    ("backend/app/services/previsiones_service.py", "PrevisionesService._regobernar"): (
        "B", "regobernanza", "snapshot de la version de regla ya configurada"),
    ("backend/app/services/previsiones_service.py", "PrevisionesService._snapshot_de_version"): (
        "R", "snapshot", "lectura de la version"),
    ("backend/app/repositories/previsiones_repository.py", "<modulo>"): ("R", "tipos SQL", "mapa de columnas"),
}

CLASES = {"A_FRONTERA", "GUARDA", "A_MOTOR", "B", "P", "R", "CATALOGO", "SEED_DEV", "PREFERENCIA"}
#: v0.12.0 (J2 §1.6): alta aditiva de la clase PLANTILLA.
CLASES = CLASES | {"PLANTILLA"}

#: Servicios del motor que la frontera NO puede referenciar (I3): tienen
#: caminos A_MOTOR, B o P con categoria. OP-22 es la unica puerta.
SERVICIOS_VEDADOS_EN_FRONTERA = (
    "EfectosService", "SuplementosService", "DevolucionesService", "CorreccionesService",
    "ReglasService", "PrevisionesService", "insertar_efecto_si_no_existe", "actualizar_efecto",
)

#: Construcciones con nombre de tabla dinamico (I6): (ruta, funcion) ->
#: (modulo, atributo del conjunto cerrado, justificacion).
DINAMICAS_AUTORIZADAS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("backend/app/repositories/posiciones_repository.py", "existe_registro"): (
        "app.repositories.posiciones_repository", "TABLAS_CON_ID", "SELECT 1 por identidad; lista blanca"),
    ("backend/app/repositories/contexto_repository.py", "leer_registro"): (
        "app.repositories.contexto_repository", "TABLAS_CONTEXTO", "SELECT por id; conjunto cerrado"),
    ("backend/app/repositories/compuesto_repository.py", "leer"): (
        "app.repositories.compuesto_repository", "TABLAS_IDENTIDAD", "SELECT por identidad OP-22"),
    ("backend/app/repositories/compuesto_repository.py", "identidades_del_agregado"): (
        "app.repositories.compuesto_repository", "FILTROS_AGREGADO", "SELECT de ids del agregado OP-22"),
}

#: Escritores autorizados de categorias_financieras (I5): exactamente el
#: repositorio del paquete S4.
ESCRITORES_CATALOGO: dict[tuple[str, str], str] = {
    ("backend/app/categorias/repositorio.py", "insertar"): "INSERT del alta",
    ("backend/app/categorias/repositorio.py", "actualizar"): "UPDATE de columnas editables",
}
SERVICIO = "backend/app/categorias/servicio.py"
PRIMITIVAS_ESCRITURA = {"insertar", "actualizar"}
COMANDOS = ("alta", "renombrar", "mover", "ordenar", "cambiar_ambito", "desactivar", "reactivar", "cambiar_icono",
            "reordenar")
ICONOS = "backend/app/categorias/iconos.py"


# ------------------------------------------------------------------ utilidades
def _rel(p: pathlib.Path) -> str:
    return p.relative_to(RAIZ).as_posix()


#: Herramientas de test dentro de scripts/dev que NO se ejecutan en runtime y
#: contienen, como texto, los mutantes que este inventario debe detectar.
EXCLUIDOS: dict[str, str] = {
    "scripts/dev/mutantes_f05_01.py": "arnes de mutacion F05-01 (D-181): los mutantes son texto",
    "scripts/dev/mutantes_f05_02.py": "arnes de mutacion F05-02 (D-181): los mutantes son texto",
    "scripts/dev/mutantes_f05_j2j3.py": "arnes de mutacion F05-03/F05-04 J2J3 (D-181): los mutantes son texto",
}


def _productivos_py() -> list[pathlib.Path]:
    candidatos = sorted(p for p in APP.rglob("*.py")) + sorted((RAIZ / "scripts" / "dev").rglob("*.py"))
    return [p for p in candidatos if _rel(p) not in EXCLUIDOS]


def _menciona(nodo: ast.AST) -> bool:
    for n in ast.walk(nodo):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and TOKEN in n.value:
            return True
        if isinstance(n, ast.Name) and n.id == TOKEN:
            return True
        if isinstance(n, ast.Attribute) and n.attr == TOKEN:
            return True
        if isinstance(n, ast.arg) and n.arg == TOKEN:
            return True
        if isinstance(n, ast.keyword) and n.arg == TOKEN:
            return True
    return False


def _apariciones(ruta: pathlib.Path) -> set[str]:
    """Nombres cualificados de funcion/clase (o '<modulo>') cuyo cuerpo
    PROPIO menciona `categoria_id` (sin contar funciones anidadas)."""
    arbol = ast.parse(ruta.read_bytes().decode("utf-8"))
    hallados: set[str] = set()

    def visitar(nodo: ast.AST, pila: list[str]) -> None:
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nueva = pila + [hijo.name]
                if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = hijo.args.args + hijo.args.kwonlyargs + hijo.args.posonlyargs
                    if any(a.arg == TOKEN for a in args):
                        hallados.add(".".join(nueva))
                visitar(hijo, nueva)
            elif _menciona(hijo):
                hallados.add(".".join(pila) or "<modulo>")

    visitar(arbol, [])
    return hallados


def _funciones(arbol: ast.AST):
    def rec(nodo, pila):
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = pila + [hijo.name]
                yield ".".join(q), hijo
                yield from rec(hijo, q)

    yield from rec(arbol, [])


def _nodo(ruta: str, qual: str) -> ast.AST:
    arbol = ast.parse((RAIZ / ruta).read_bytes().decode("utf-8"))
    for q, n in _funciones(arbol):
        if q == qual:
            return n
    raise AssertionError(f"{ruta}:{qual} no existe")


# ------------------------------------------------------------------ I1 / I2
def test_i1_toda_aparicion_de_categoria_id_esta_registrada():
    encontradas = {(_rel(p), q) for p in _productivos_py() for q in _apariciones(p)}
    sin_registrar = sorted(encontradas - set(REGISTRO))
    obsoletas = sorted(set(REGISTRO) - encontradas)
    assert not sin_registrar, f"consumidores/escritores de categoria_id sin clasificar: {sin_registrar}"
    assert not obsoletas, f"entradas del registro que ya no existen: {obsoletas}"


def test_i2_clases_validas_y_justificadas():
    for clave, (clase, operacion, justificacion) in REGISTRO.items():
        assert clase in CLASES, clave
        assert operacion.strip() and justificacion.strip(), clave


# ------------------------------------------------------------------ I3
def test_i3_frontera_solo_r_guarda_o_a_frontera():
    for (ruta, qual), (clase, _, _) in REGISTRO.items():
        if ruta.startswith(FRONTERA):
            assert clase in {"R", "GUARDA", "A_FRONTERA", "CATALOGO", "PREFERENCIA"}, (ruta, qual, clase)


def test_i3_frontera_no_referencia_servicios_con_caminos_a_b_o_p():
    for p in _productivos_py():
        ruta = _rel(p)
        if not ruta.startswith(FRONTERA):
            continue
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
        nombres |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
        for imp in (n for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)):
            nombres |= {a.name for a in imp.names}
        vedados = sorted(nombres & set(SERVICIOS_VEDADOS_EN_FRONTERA))
        assert not vedados, f"{ruta} alcanza el motor sin pasar por OP-22: {vedados}"


# ------------------------------------------------------------------ I4
def _llamadas(nodo: ast.AST, nombre: str) -> list[ast.Call]:
    return [
        n for n in ast.walk(nodo)
        if isinstance(n, ast.Call)
        and ((isinstance(n.func, ast.Name) and n.func.id == nombre)
             or (isinstance(n.func, ast.Attribute) and n.func.attr == nombre))
    ]


def test_i4_guarda_tras_identidad_y_antes_de_componer():
    fn = _nodo("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion")
    guardas = _llamadas(fn, "validar_seleccion_categoria")
    composiciones = _llamadas(fn, "componer")
    assert len(guardas) == 1 and len(composiciones) == 1
    assert guardas[0].lineno < composiciones[0].lineno, "la guarda debe preceder a componer"
    # La guarda vive dentro de `if not ya_materializada:` (identidad antes).
    padres = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and any(g is c for g in ast.walk(n) for c in guardas)
    ]
    assert any(
        isinstance(i.test, ast.UnaryOp) and isinstance(i.test.op, ast.Not)
        and isinstance(i.test.operand, ast.Name) and i.test.operand.id == "ya_materializada"
        for i in padres
    ), "la guarda no esta subordinada al reconocimiento de identidad"


def test_i4_componer_tiene_un_unico_llamador_productivo():
    llamadores = []
    for p in _productivos_py():
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        for q, n in _funciones(arbol):
            if any(True for _ in _llamadas_directas(n, "componer")):
                llamadores.append((_rel(p), q))
    assert llamadores == [("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion")]


def _llamadas_directas(fn: ast.AST, nombre: str):
    """Llamadas en el cuerpo propio (sin funciones anidadas)."""
    pila = list(ast.iter_child_nodes(fn))
    while pila:
        n = pila.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == nombre:
            yield n
        pila.extend(ast.iter_child_nodes(n))


def test_i4_c07_tras_la_guarda_y_antes_de_componer():
    fn = _nodo("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion")
    guardas = _llamadas(fn, "validar_seleccion_categoria")
    c07 = _llamadas(fn, "validar_magnitudes")
    composiciones = _llamadas(fn, "componer")
    assert len(c07) == 1, "C07 debe invocarse exactamente una vez"
    assert guardas[0].lineno < c07[0].lineno < composiciones[0].lineno, "orden guarda -> C07 -> componer"
    padres = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.If) and any(g is c07[0] for g in ast.walk(n))
    ]
    assert any(
        isinstance(i.test, ast.UnaryOp) and isinstance(i.test.op, ast.Not)
        and isinstance(i.test.operand, ast.Name) and i.test.operand.id == "ya_materializada"
        for i in padres
    ), "C07 no esta subordinada al reconocimiento de identidad (AJ-C07-04)"


def test_i4_c07_solo_se_invoca_desde_la_ejecucion():
    llamadores = []
    for p in _productivos_py():
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        for q, n in _funciones(arbol):
            if any(True for _ in _llamadas_directas(n, "validar_magnitudes")):
                llamadores.append((_rel(p), q))
    # v0.13.0 (J2 §1.7): alta del segundo llamante productivo (registro de INGRESO).
    assert sorted(llamadores) == sorted([("backend/app/api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado.operacion"),
                                         ("backend/app/api/ejecucion_registro.py", "validar_categoria_y_magnitudes")])


def test_i4_ingreso_guarda_tras_identidad_y_antes_de_componer():
    """J2 §1.7: mismo contrato I4 en el registro de INGRESO."""
    fn = _nodo("backend/app/api/ejecucion_registro.py", "registrar_ingreso_cobrado.operacion")
    guardas = _llamadas(fn, "validar_categoria_y_magnitudes")
    composiciones = _llamadas(fn, "componer_ingreso")
    assert len(guardas) == 1 and len(composiciones) == 1
    assert guardas[0].lineno < composiciones[0].lineno
    padres = [n for n in ast.walk(fn) if isinstance(n, ast.If) and any(g is guardas[0] for g in ast.walk(n))]
    assert any(isinstance(i.test, ast.UnaryOp) and isinstance(i.test.op, ast.Not)
               and isinstance(i.test.operand, ast.Name) and i.test.operand.id == "ya_materializada" for i in padres)
    aux = _nodo("backend/app/api/ejecucion_registro.py", "validar_categoria_y_magnitudes")
    c_a, c07 = _llamadas(aux, "validar_seleccion_categoria"), _llamadas(aux, "validar_magnitudes")
    assert len(c_a) == 1 and len(c07) == 1 and c_a[0].lineno < c07[0].lineno
    llamadores = []
    for p in _productivos_py():
        for q, n in _funciones(ast.parse(p.read_bytes().decode("utf-8"))):
            if any(True for _ in _llamadas_directas(n, "componer_ingreso")):
                llamadores.append((_rel(p), q))
    assert llamadores == [("backend/app/api/ejecucion_registro.py", "registrar_ingreso_cobrado.operacion")]


# ------------------------------------------------------------------ I5
_ESCRITURA = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?(gapto\s*\.\s*)?\"?categorias_financieras\b",
    re.IGNORECASE,
)
_BORRADO = re.compile(r"\b(DELETE\s+FROM|TRUNCATE)\b[^;]*categorias_financieras", re.IGNORECASE | re.DOTALL)


def _textos_productivos():
    for p in _productivos_py():
        yield p, p.read_bytes().decode("utf-8")
    for p in sorted((RAIZ / "mobile" / "src").rglob("*")):
        if p.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            yield p, p.read_bytes().decode("utf-8")


def test_i5_escritores_de_categorias_financieras():
    encontrados = set()
    for p, texto in _textos_productivos():
        if _ESCRITURA.search(texto):
            encontrados.add(_rel(p))
    autorizados = {ruta for ruta, _ in ESCRITORES_CATALOGO}
    assert encontrados <= autorizados, f"escritor de categorias_financieras no autorizado: {sorted(encontrados - autorizados)}"


def test_i5_delete_writers_cero():
    for p, texto in _textos_productivos():
        assert not _BORRADO.search(texto), f"DELETE/TRUNCATE de categorias_financieras en {_rel(p)}"


def test_i5_escrituras_solo_en_las_funciones_autorizadas():
    ruta = "backend/app/categorias/repositorio.py"
    texto = (RAIZ / ruta).read_bytes().decode("utf-8")
    arbol = ast.parse(texto)
    lineas = texto.splitlines()
    con_escritura = set()
    for q, n in _funciones(arbol):
        cuerpo = "\n".join(lineas[n.lineno - 1:n.end_lineno])
        if re.search(r"\b(INSERT\s+INTO|UPDATE)\s+gapto\.categorias_financieras", cuerpo):
            con_escritura.add((ruta, q))
    assert con_escritura == set(ESCRITORES_CATALOGO)


# ------------------------------------------------------------------ I9
def _escritura_de(tabla: str) -> re.Pattern:
    return re.compile(
        r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(\s+TABLE)?)\s+(ONLY\s+)?(gapto\s*\.\s*)?\"?"
        + tabla + r"\b",
        re.IGNORECASE,
    )


#: Escritores autorizados de hecho_magnitudes: primitivas certificadas F04.
ESCRITORES_HECHO_MAGNITUDES = {
    ("backend/app/repositories/contexto_repository.py", "insertar_magnitud"),
    ("backend/app/repositories/contexto_repository.py", "eliminar_magnitud"),
    ("backend/app/repositories/contexto_repository.py", "actualizar_magnitud"),
}


#: Writers SQL de desarrollo (SEED_DEV, F05 §26.4): escritores de desarrollo
#: de magnitudes / categoria_magnitudes, sin valor certificador.
ESCRITORES_SEED_DEV = {
    "magnitudes": {("scripts/dev/bootstrap_dev_db.py", "_seed_magnitudes")},
    "categoria_magnitudes": {("scripts/dev/bootstrap_dev_db.py", "_seed_asociaciones")},
}
#: Escritores RUNTIME (S7-MAG, D-MAG-08): exactamente el repositorio de magnitudes.
REPO_MAGNITUDES = "backend/app/magnitudes/repositorio.py"
ESCRITORES_RUNTIME = {
    "magnitudes": {(REPO_MAGNITUDES, "insertar_magnitud"), (REPO_MAGNITUDES, "actualizar_magnitud")},
    "categoria_magnitudes": {(REPO_MAGNITUDES, "insertar_asociacion"), (REPO_MAGNITUDES, "actualizar_asociacion"),
                             (REPO_MAGNITUDES, "eliminar_asociacion")},
}
#: Operaciones autorizadas por (tabla, funcion): DELETE runtime de magnitudes = 0.
OPERACIONES_RUNTIME = {
    ("magnitudes", "insertar_magnitud"): {"INSERT"},
    ("magnitudes", "actualizar_magnitud"): {"UPDATE"},
    ("categoria_magnitudes", "insertar_asociacion"): {"INSERT"},
    ("categoria_magnitudes", "actualizar_asociacion"): {"UPDATE"},
    ("categoria_magnitudes", "eliminar_asociacion"): {"DELETE"},
}


def _con_escritura(ruta: str, patron: re.Pattern) -> set[tuple[str, str]]:
    """Funciones HOJA (sin funciones anidadas) de `ruta` cuyo cuerpo escribe la tabla."""
    texto = (RAIZ / ruta).read_bytes().decode("utf-8")
    lineas = texto.splitlines()
    return {(ruta, q) for q, n in _funciones(ast.parse(texto))
            if not isinstance(n, ast.ClassDef) and patron.search("\n".join(lineas[n.lineno - 1:n.end_lineno]))
            and not any(isinstance(h, (ast.FunctionDef, ast.AsyncFunctionDef)) for h in ast.iter_child_nodes(n))}


def test_i9_escritores_de_magnitudes_y_asociaciones_registro_cerrado():
    for tabla in ("magnitudes", "categoria_magnitudes"):
        patron = _escritura_de(tabla)
        encontrados = sorted(_rel(p) for p, texto in _textos_productivos() if patron.search(texto))
        autorizados = sorted({ruta for ruta, _ in ESCRITORES_SEED_DEV[tabla] | ESCRITORES_RUNTIME[tabla]})
        assert encontrados == autorizados, f"escritor de {tabla} no autorizado (D-MAG-08): {encontrados}"
        assert not any(r.startswith("mobile/") for r in encontrados)
        assert {r for r in encontrados if r.startswith("backend/")} == {REPO_MAGNITUDES}, tabla
        for ruta in autorizados:
            esperado = {x for x in ESCRITORES_SEED_DEV[tabla] | ESCRITORES_RUNTIME[tabla] if x[0] == ruta}
            assert _con_escritura(ruta, patron) == esperado, (tabla, ruta)


def test_i9_operaciones_por_tabla_y_sin_delete_runtime_de_magnitudes():
    texto = (RAIZ / REPO_MAGNITUDES).read_bytes().decode("utf-8")
    lineas = texto.splitlines()
    for q, n in _funciones(ast.parse(texto)):
        cuerpo = "\n".join(lineas[n.lineno - 1:n.end_lineno])
        for tabla in ("magnitudes", "categoria_magnitudes"):
            ops = {m.group(1).split()[0].upper() for m in _escritura_de(tabla).finditer(cuerpo)}
            if ops:
                assert ops == OPERACIONES_RUNTIME[(tabla, q)], (tabla, q, ops)
    borrado = re.compile(r"\b(DELETE\s+FROM|TRUNCATE)\s+(TABLE\s+)?(ONLY\s+)?(gapto\s*\.\s*)?\"?magnitudes\b",
                         re.IGNORECASE)
    for p, contenido in _textos_productivos():
        if _rel(p).startswith("backend/"):
            assert not borrado.search(contenido), f"DELETE runtime de magnitudes en {_rel(p)}"


def test_i9_r17_unidad_y_precision_no_editables():
    texto = (RAIZ / REPO_MAGNITUDES).read_bytes().decode("utf-8")
    assert not re.search(r"UPDATE\s+gapto\.magnitudes\s+SET[^\"]*(unidad_default|precision_decimales)", texto)
    repo = importlib.import_module("app.magnitudes.repositorio")
    assert repo.COLUMNAS_EDITABLES_MAGNITUD == frozenset({"nombre", "enabled"})
    assert repo.COLUMNAS_EDITABLES_ASOCIACION == frozenset({"obligatoria", "orden"})


def test_i9_el_modulo_de_magnitudes_no_escribe_categorias_financieras():
    for p in sorted((APP / "magnitudes").rglob("*.py")):
        assert not _ESCRITURA.search(p.read_bytes().decode("utf-8")), _rel(p)


def test_i9_escritores_de_hecho_magnitudes_solo_f04():
    patron = _escritura_de("hecho_magnitudes")
    hallados = set()
    for p in _productivos_py():
        texto = p.read_bytes().decode("utf-8")
        if not patron.search(texto):
            continue
        lineas = texto.splitlines()
        for q, n in _funciones(ast.parse(texto)):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if patron.search("\n".join(lineas[n.lineno - 1:n.end_lineno])):
                hallados.add((_rel(p), q))
    assert hallados == ESCRITORES_HECHO_MAGNITUDES, sorted(hallados ^ ESCRITORES_HECHO_MAGNITUDES)
    for ruta, _ in hallados:
        assert not ruta.startswith(FRONTERA), ruta


# ------------------------------------------------------------------ I8
def _nombre_llamada(c: ast.Call) -> str | None:
    if isinstance(c.func, ast.Attribute):
        return c.func.attr
    if isinstance(c.func, ast.Name):
        return c.func.id
    return None


def test_i8_todo_comando_toma_el_advisory_primero():
    for qual in COMANDOS:
        fn = _nodo(SERVICIO, qual)
        primera = fn.body[0]
        assert (isinstance(primera, ast.Expr) and isinstance(primera.value, ast.Call)
                and _nombre_llamada(primera.value) == "tomar_advisory"), f"{qual} no toma el advisory primero"


def test_i8_toda_funcion_que_escribe_es_un_comando_con_advisory():
    arbol = ast.parse((RAIZ / SERVICIO).read_bytes().decode("utf-8"))
    for q, n in _funciones(arbol):
        if not isinstance(n, ast.FunctionDef):
            continue
        llamadas = {_nombre_llamada(c) for c in ast.walk(n) if isinstance(c, ast.Call)}
        if llamadas & (PRIMITIVAS_ESCRITURA | {"_escribir"}) and q not in ("_escribir",):
            assert q in COMANDOS, f"{q} escribe el catalogo sin ser un comando con advisory"


def test_i8_primitivas_de_escritura_solo_desde_el_servicio():
    for p in _productivos_py():
        ruta = _rel(p)
        if ruta in (SERVICIO, "backend/app/categorias/repositorio.py"):
            continue
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        for c in ast.walk(arbol):
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in PRIMITIVAS_ESCRITURA:
                if isinstance(c.func.value, ast.Name) and c.func.value.id in ("repo", "repositorio"):
                    raise AssertionError(f"{ruta} invoca una primitiva de escritura del catalogo")
        texto = p.read_bytes().decode("utf-8")
        if ruta == SERVICIO_MAG:
            continue  # uso acotado de categorias/repositorio.py: test_i8_magnitudes_solo_advisory_y_lectura_de_categorias
        assert "categorias.repositorio" not in texto and "categorias import repositorio" not in texto, ruta


SERVICIO_MAG = "backend/app/magnitudes/servicio.py"
ONBOARDING = "backend/app/categorias/onboarding/__init__.py"


def test_i8_onboarding_solo_comandos_de_c06():
    """J2 §1.8: el onboarding no importa categorias/repositorio.py; toma el
    advisory con el helper de servicio.py y escribe solo con alta y
    reordenar (sin camino de escritura propio)."""
    arbol = ast.parse((RAIZ / ONBOARDING).read_bytes().decode("utf-8"))
    comandos = {c.attr for c in ast.walk(arbol) if isinstance(c, ast.Attribute)
                and isinstance(c.value, ast.Name) and c.value.id == "serv_cat"}
    assert comandos <= {"alta", "reordenar", "tomar_advisory_del_catalogo", "Rechazo"}, comandos
    texto = (RAIZ / ONBOARDING).read_bytes().decode("utf-8")
    assert not re.search(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", texto)
PRIMITIVAS_ESCRITURA_MAG = {"insertar_magnitud", "actualizar_magnitud", "insertar_asociacion",
                            "actualizar_asociacion", "eliminar_asociacion"}
COMANDOS_MAG = ("asociar", "cambiar_obligatoria", "retirar", "reordenar", "renombrar", "deshabilitar", "rehabilitar")
#: Helpers internos de escritura: solo se invocan desde comandos (o entre si).
HELPERS_ESCRITURA_MAG = {"_escribir", "_escribir_orden", "_actualizar", "_comando"}


def _sin_docstring(fn: ast.FunctionDef) -> list[ast.stmt]:
    cuerpo = list(fn.body)
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant) \
            and isinstance(cuerpo[0].value.value, str):
        cuerpo = cuerpo[1:]
    return cuerpo


def test_i8_magnitudes_todo_comando_toma_el_advisory_primero():
    for qual in COMANDOS_MAG:
        primera = _sin_docstring(_nodo(SERVICIO_MAG, qual))[0]
        assert (isinstance(primera, ast.Expr) and isinstance(primera.value, ast.Call)
                and _nombre_llamada(primera.value) == "tomar_advisory"), f"{qual} no toma el advisory primero"


def test_i8_magnitudes_solo_los_comandos_escriben():
    arbol = ast.parse((RAIZ / SERVICIO_MAG).read_bytes().decode("utf-8"))
    publicas = {n.name for n in arbol.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}
    assert publicas == set(COMANDOS_MAG), sorted(publicas ^ set(COMANDOS_MAG))
    for q, n in _funciones(arbol):
        if not isinstance(n, ast.FunctionDef):
            continue
        llamadas = {_nombre_llamada(c) for c in ast.walk(n) if isinstance(c, ast.Call)}
        if llamadas & (PRIMITIVAS_ESCRITURA_MAG | HELPERS_ESCRITURA_MAG):
            raiz = q.split(".")[0]
            assert raiz in COMANDOS_MAG or raiz in HELPERS_ESCRITURA_MAG, f"{q} escribe sin ser un comando con advisory"
    # Los helpers de escritura solo los invocan comandos (o sus anidadas) u otros helpers.
    for q, n in _funciones(arbol):
        if isinstance(n, ast.FunctionDef) and q.split(".")[0] not in set(COMANDOS_MAG) | HELPERS_ESCRITURA_MAG:
            llamadas = {_nombre_llamada(c) for c in ast.walk(n) if isinstance(c, ast.Call)}
            assert not llamadas & HELPERS_ESCRITURA_MAG, q


def test_i8_primitivas_de_magnitudes_solo_desde_su_servicio():
    # F04 tiene primitivas homonimas de hecho_magnitudes (contexto_repository): el control es
    # que ningun otro modulo importe el repositorio de magnitudes y que, dentro del paquete, solo
    # el servicio invoque sus primitivas.
    for p in sorted((APP / "magnitudes").rglob("*.py")):
        ruta = _rel(p)
        if ruta in (SERVICIO_MAG, REPO_MAGNITUDES):
            continue
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        assert not any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                       and c.func.attr in PRIMITIVAS_ESCRITURA_MAG for c in ast.walk(arbol)), ruta
    for p in _productivos_py():
        ruta = _rel(p)
        if ruta in (SERVICIO_MAG, REPO_MAGNITUDES):
            continue
        texto = p.read_bytes().decode("utf-8")
        assert "magnitudes.repositorio" not in texto and "magnitudes import repositorio" not in texto, ruta


def test_i8_magnitudes_solo_advisory_y_lectura_bloqueante_de_categorias():
    arbol = ast.parse((RAIZ / SERVICIO_MAG).read_bytes().decode("utf-8"))
    usados = {n.attr for n in ast.walk(arbol)
              if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "repo_cat"}
    assert usados == {"tomar_advisory", "leer"}, usados
    lecturas = [c for c in ast.walk(arbol) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                and isinstance(c.func.value, ast.Name) and c.func.value.id == "repo_cat" and c.func.attr == "leer"]
    assert lecturas and all(any(k.arg == "bloquear" and getattr(k.value, "value", None) is True for k in c.keywords)
                            for c in lecturas), "la categoria se lee sin FOR NO KEY UPDATE (R16)"


def test_i8_columnas_editables_incluyen_icon_key():
    repo = importlib.import_module("app.categorias.repositorio")
    assert repo.COLUMNAS_EDITABLES == frozenset({"nombre", "parent_id", "orden", "enabled", "ambito", "icon_key"})


# ------------------------------------------------------------------ I10
_SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b|\bgapto\s*\.", re.IGNORECASE)


def test_i10_biblioteca_de_iconos_sin_sql_ni_escritores():
    texto = (RAIZ / ICONOS).read_bytes().decode("utf-8")
    arbol = ast.parse(texto)
    for n in ast.walk(arbol):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            assert not _SQL.search(n.value), f"SQL en la biblioteca de iconos: {n.value!r}"
    importados = {a.name for i in ast.walk(arbol) if isinstance(i, (ast.Import, ast.ImportFrom)) for a in i.names}
    modulos = {i.module for i in ast.walk(arbol) if isinstance(i, ast.ImportFrom)}
    assert importados <= {"annotations"} and modulos <= {"__future__"}, (importados, modulos)
    llamadas = {_nombre_llamada(c) for c in ast.walk(arbol) if isinstance(c, ast.Call)}
    assert not llamadas & (PRIMITIVAS_ESCRITURA | {"uno", "execute", "_escribir"}), llamadas


def test_i10_alta_y_cambiar_icono_validan_con_la_biblioteca_antes_de_escribir():
    for qual in ("alta", "cambiar_icono"):
        fn = _nodo(SERVICIO, qual)
        validaciones = _llamadas(fn, "icono_valido")
        escrituras = _llamadas(fn, "_escribir")
        assert len(validaciones) == 1 and len(escrituras) == 1, qual
        assert validaciones[0].lineno < escrituras[0].lineno, f"{qual} escribe antes de validar el icono"


# ------------------------------------------------------------------ I6
_DINAMICA = re.compile(r"gapto\s*\.\s*\{|Identifier\(\s*[\"']gapto[\"']|[\"']gapto\.[\"']\s*\+")
_TROCEO = re.compile(
    r"[\"']categoria[s]?_?[\"']\s*\+|\+\s*[\"']_?id[\"']|categorias?_\{|[\"']categorias_[\"']\s*\+|[\"']financieras[\"']"
)


def test_i6_sql_de_tabla_dinamica_solo_en_lista_blanca():
    halladas = set()
    for p in _productivos_py():
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        lineas = p.read_bytes().decode("utf-8").splitlines()
        for q, n in _funciones(arbol):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            cuerpo = "\n".join(lineas[n.lineno - 1:n.end_lineno])
            propias = [f for f in ast.walk(n) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f is not n]
            if propias:
                continue
            if _DINAMICA.search(cuerpo):
                halladas.add((_rel(p), q))
    assert halladas == set(DINAMICAS_AUTORIZADAS), f"SQL de tabla dinamica no autorizado: {sorted(halladas ^ set(DINAMICAS_AUTORIZADAS))}"
    for (ruta, qual), (modulo, atributo, _) in DINAMICAS_AUTORIZADAS.items():
        conjunto = getattr(importlib.import_module(modulo), atributo)
        assert "categorias_financieras" not in conjunto, (ruta, qual)
        cuerpo = "\n".join(
            (RAIZ / ruta).read_bytes().decode("utf-8").splitlines()[_nodo(ruta, qual).lineno - 1:_nodo(ruta, qual).end_lineno]
        )
        for linea in cuerpo.splitlines():
            if _DINAMICA.search(linea):
                assert re.search(r"SELECT", linea, re.IGNORECASE), (ruta, qual, linea)


def test_i6_sin_literales_troceados():
    for p, texto in _textos_productivos():
        assert not _TROCEO.search(texto), f"literal de categoria construido por piezas en {_rel(p)}"


def test_exclusiones_cerradas_y_existentes():
    """La lista de exclusiones es cerrada: cada entrada existe y es un arnes
    de mutacion, nunca codigo que el backend importe."""
    for ruta, motivo in EXCLUIDOS.items():
        assert (RAIZ / ruta).is_file() and motivo.strip(), ruta
        assert ruta.startswith("scripts/dev/mutantes_"), ruta
    for p in APP.rglob("*.py"):
        texto = p.read_bytes().decode("utf-8")
        assert "mutantes_f05_01" not in texto, _rel(p)


# ------------------------------------------------------------------ I7
#: Menciones de `categoria_id` en el cliente movil (registro cerrado, S6-WIRE): la
#: app SELLA la categoria en el wire de §28.2 y LEE el uso de una categoria.
#: Nunca escribe categorias_financieras (eso es I5, que sigue sin el cliente).
MENCIONES_CLIENTE: dict[str, str] = {
    "mobile/src/domain/intencion.ts": "sella {estado:'CATEGORIA', categoria_id, magnitudes} (A_FRONTERA via VS-01; C-a en servidor)",
    "mobile/src/api/cliente.ts": "tipo de lectura de GET /v1/categorias/{id}/uso y detalle de impacto de deshabilitar magnitud (R)",
    "mobile/src/domain/magnitud.ts": "tipo del catalogo GET /v1/magnitudes (categorias de cada magnitud) y su vista neutra (R)",
    "mobile/src/domain/preferencias.ts": "lee la categoria sellada y la clave de contexto de las preferencias (F05-02 B2, R)",
    "mobile/src/screens/PreferenciasAjustesScreen.tsx": "Ajustes > Preferencias: muestra y envia la clave de categoria de la preferencia por /v1/preferencias (F05-02 B3, R)",
}


def test_i7_cliente_movil_sin_menciones_sin_registrar():
    menciones = sorted(
        _rel(p) for p, t in _textos_productivos()
        if p.suffix in {".ts", ".tsx", ".js", ".jsx"} and (TOKEN in t or "categorias_financieras" in t)
    )
    assert menciones == sorted(MENCIONES_CLIENTE), menciones
    for ruta, texto in ((r, (RAIZ / r).read_bytes().decode("utf-8")) for r in MENCIONES_CLIENTE):
        assert "categorias_financieras" not in texto, ruta


# ------------------------------------------------------------------ I11
_RUTA_POR_NODO = re.compile(r"/orden\b")


def test_i11_reordenar_solo_por_la_ruta_atomica():
    """F05-D012 §26.3: prohibido reordenar con N llamadas al comando por nodo.
    La ruta /{id}/orden (S4) solo aparece en su declaracion de app.py; ningun
    otro codigo productivo ni el cliente movil la invoca."""
    usos = []
    for p, texto in _textos_productivos():
        for linea in texto.splitlines():
            if linea.lstrip().startswith(("#", "//", "*", "/*")):
                continue
            if _RUTA_POR_NODO.search(linea):
                usos.append((_rel(p), linea.strip()))
    assert usos == [("backend/app/api/app.py", '@app.post("/v1/categorias/{categoria_id}/orden", **_R)')], usos
    app_py = (RAIZ / "backend" / "app" / "api" / "app.py").read_bytes().decode("utf-8")
    assert app_py.count('"/v1/categorias/reordenar"') == 1
    comandos = [n for n in ast.walk(_nodo(SERVICIO, "reordenar")) if isinstance(n, ast.For)]
    assert len(comandos) == 1, "reordenar: un unico bucle de escritura sobre las filas que cambian"


# ------------------------------------------------------------------ I12
ESTADO_RETIRADO = "NO_CAPTURADA" + "_LEGACY"


def test_i12_estado_de_compatibilidad_retirado_del_codigo_y_del_cliente():
    """S6-WIRE (F05 §26.2 AJ-03): ninguna peticion ordinaria genera el estado de
    compatibilidad; su literal no sobrevive en el codigo ni en comentarios."""
    candidatos = sorted(APP.rglob("*.py")) + sorted((RAIZ / "mobile" / "src").rglob("*")) + [RAIZ / "mobile" / "App.tsx"]
    apariciones = [_rel(p) for p in candidatos
                   if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}
                   and ESTADO_RETIRADO in p.read_bytes().decode("utf-8")]
    assert apariciones == [], apariciones


# ------------------------------------------------------------------ I13 (P7 · N4, AJ-P7BAT-05)
REG = "mobile/src/screens/RegistroGastoScreen.tsx"
SEL = "mobile/src/components/SelectorCategorias.tsx"
DOM = "mobile/src/domain/categoria.ts"
CLI = "mobile/src/api/cliente.ts"
INT = "mobile/src/domain/intencion.ts"
CAMINO_CATEGORIAL = (REG, SEL, DOM, CLI)

_IMPORT = re.compile(r"^import\s+(?P<tipo>type\s+)?(?P<cl>[\s\S]*?)\s+from\s+'(?P<mod>[^']+)';", re.MULTILINE)
_IMPORT_LINEA = re.compile(r"^import\b", re.MULTILINE)
_IMPORT_DINAMICO = re.compile(r"\bimport\s*\(|\brequire\s*\(")


def _texto(ruta: str) -> str:
    return (RAIZ / ruta).read_bytes().decode("utf-8")


def _imports_ts(texto: str) -> set[tuple[str, str]]:
    """(modulo, nombre importado) de cada sentencia `import ... from '...'`."""
    out: set[tuple[str, str]] = set()
    for m in _IMPORT.finditer(texto):
        clausula, nombres = m["cl"].strip(), []
        llaves = re.search(r"\{([\s\S]*)\}", clausula)
        if llaves:
            nombres += [n.strip() for n in llaves[1].split(",") if n.strip()]
            clausula = clausula[: llaves.start()] + clausula[llaves.end():]
        nombres += [n.strip() for n in clausula.split(",") if n.strip()]
        for n in nombres:
            out.add((m["mod"], ("type " if m["tipo"] else "") + re.sub(r"\s+", " ", n)))
    return out


#: Registro CERRADO de imports del camino de resolucion categorial (fijado tras
#: inspeccion de c06d219). Ninguno es un resolver de propuesta ni de ranking.
IMPORTS_CAMINO: dict[str, set[tuple[str, str]]] = {
    REG: {
        ("../api/cliente", "type ClienteApi"), ("../api/cliente", "type CuentaPago"),
        ("../components/Basicos", "BotonPrimario"), ("../components/Basicos", "BotonTexto"),
        ("../components/Basicos", "Chip"), ("../components/Basicos", "EstadoDato"),
        ("../components/Basicos", "Segmentado"), ("../components/Basicos", "Velo"),
        ("../components/SelectorCategorias", "BotonSecundario"), ("../components/SelectorCategorias", "CargaArbol"),
        ("../components/SelectorCategorias", "IconoCategoriaVista"), ("../components/SelectorCategorias", "SelectorCategorias"),
        ("../domain/categoria", "CategoriaNodo"), ("../domain/categoria", "MagnitudCategoria"),
        ("../domain/categoria", "construirArbol"), ("../domain/categoria", "elegibleParaGasto"),
        ("../domain/categoria", "magnitudesPedibles"), ("../domain/categoria", "motivoNoSeleccionable"),
        ("../domain/categoria", "rutaTexto"), ("../domain/categoria", "visibleEnRegistro"),
        ("../domain/fechas", "ayer"), ("../domain/fechas", "ddmmaaaaAIso"), ("../domain/fechas", "fechaCortaIso"),
        ("../domain/fechas", "isoADdmmaaaa"), ("../domain/fechas", "isoLocal"),
        ("../domain/importe", "formatearEur"), ("../domain/importe", "parsearImporte"),
        ("../domain/intencion", "Borrador"), ("../domain/intencion", "Errores"),
        ("../domain/intencion", "SeleccionCategoria"), ("../domain/intencion", "borradorInicial"),
        ("../domain/intencion", "esFechaIso"), ("../domain/intencion", "validar"),
        ("../domain/magnitud", "conservarMagnitudes"), ("../domain/magnitud", "descartadas"),
        # F05-02 B2 (alta aditiva): preferencias de registro (cuenta y presupuestable; nunca categoria).
        ("../components/GuardarPreferencia", "GuardarPreferencia"),
        ("../domain/preferencias", "type IndicePreferencias"), ("../domain/preferencias", "type PropuestaVista"),
        ("../domain/preferencias", "aplicarPropuesta"), ("../domain/preferencias", "datosRecordables"),
        ("../domain/preferencias", "faltanPreferencias"), ("../domain/preferencias", "indexar"),
        ("../domain/preferencias", "propuestaAplicable"), ("../domain/preferencias", "SIN_PROPUESTA"),
        ("../domain/preferencias", "TEXTO_ELEGIDA"), ("../domain/preferencias", "textoOrigen"),
        ("../domain/preferencias", "valoresPropuestos"),
        ("../state/useEnvioGasto", "useEnvioGasto"), ("../theme/tema", "useTema"),
        ("../theme/tokens", "TACTIL_MIN"), ("../theme/tokens", "espacio"), ("../theme/tokens", "importe"),
        ("../theme/tokens", "radio"), ("../theme/tokens", "tipo"),
        ("@expo/vector-icons", "Ionicons"),
        ("react", "React"), ("react", "useCallback"), ("react", "useEffect"), ("react", "useMemo"),
        ("react", "useRef"), ("react", "useState"),
        ("react-native", "KeyboardAvoidingView"), ("react-native", "Platform"), ("react-native", "Pressable"),
        ("react-native", "ScrollView"), ("react-native", "StyleSheet"), ("react-native", "Text"),
        ("react-native", "TextInput"), ("react-native", "View"),
        ("react-native-safe-area-context", "useSafeAreaInsets"),
    },
    SEL: {
        ("../domain/categoria", "Arbol"), ("../domain/categoria", "CategoriaNodo"), ("../domain/categoria", "ancestros"),
        ("../domain/categoria", "hijosDe"), ("../domain/categoria", "tieneDescendienteElegible"),
        ("../theme/iconosCategoria", "glifoDe"), ("../theme/tema", "useTema"),
        ("../theme/tokens", "TACTIL_MIN"), ("../theme/tokens", "espacio"), ("../theme/tokens", "radio"), ("../theme/tokens", "tipo"),
        ("./Basicos", "BotonPrimario"), ("./Basicos", "BotonTexto"),
        ("@expo/vector-icons", "Ionicons"),
        ("react", "React"), ("react", "useMemo"), ("react", "useState"),
        ("react-native", "Pressable"), ("react-native", "ScrollView"), ("react-native", "StyleSheet"),
        ("react-native", "Text"), ("react-native", "View"),
        ("react-native-safe-area-context", "useSafeAreaInsets"),
    },
    DOM: set(),  # modulo puro: sin imports
    CLI: {
        ("../domain/categoria", "type Ambito"), ("../domain/categoria", "type CategoriaNodo"),
        ("../domain/intencion", "type PayloadGastoPagado"), ("../domain/magnitud", "type MagnitudCatalogo"),
    },
}


def test_i13_a_imports_del_camino_categorial_registro_cerrado():
    """I13a: cualquier import nuevo (o uno registrado que desaparece) en el
    camino de resolucion categorial del cliente hace fallar el test."""
    assert sorted(IMPORTS_CAMINO) == sorted(CAMINO_CATEGORIAL)
    for ruta in CAMINO_CATEGORIAL:
        texto = _texto(ruta)
        assert not _IMPORT_DINAMICO.search(texto), f"import dinamico o require en {ruta}"
        assert len(_IMPORT_LINEA.findall(texto)) == len(_IMPORT.findall(texto)), f"sentencia import no reconocida en {ruta}"
        assert _imports_ts(texto) == IMPORTS_CAMINO[ruta], (ruta, sorted(_imports_ts(texto) ^ IMPORTS_CAMINO[ruta]))


_ESTADO_LITERAL = re.compile(r"estado:\s*'(CATEGORIA|SIN_CATEGORIA|PENDIENTE)'")
_CAMPO_CATEGORIA = re.compile(r"\bcategoria:\s")

#: Registro CERRADO de las lineas de RegistroGastoScreen que construyen un estado
#: categorial o escriben el campo `categoria` del borrador (fijado tras inspeccion).
SITIOS_ESTADO_CATEGORIAL: dict[str, str] = {
    "setB((x) => ({ ...x, categoria: { estado: 'PENDIENTE' } }));":
        "reinicio a PENDIENTE tras rechazo categorial definitivo (se pide otra categoria)",
    "cambiar({ categoria: destino, magnitudesTexto: conservarMagnitudes(b.magnitudesTexto, nuevas) });":
        "aplicarCategoria: aplica el destino que eligio el usuario (directo o tras confirmar el descarte)",
    "estado: 'CATEGORIA',":
        "elegirNodo: el usuario toca un nodo elegible del selector (onElegir)",
    "onPress: () => proponerCategoria({ estado: 'SIN_CATEGORIA' }),":
        "opcion fija de la raiz «Sin categoría» del selector (decision explicita)",
    "onContinuarSinCategoria={() => proponerCategoria({ estado: 'SIN_CATEGORIA' })}":
        "«Continuar sin categoría» ante error de carga (decision explicita, nunca automatica)",
    "categoria: 'categoría',":
        "etiqueta de la lista «faltan» (R: texto, no estado)",
}


def _cuerpo_ts(texto: str, cabecera: str) -> str:
    """Cuerpo (llaves equilibradas) de la funcion cuyo texto empieza por `cabecera`."""
    k = texto.index(cabecera) + len(cabecera) - 1  # parentesis que abre los parametros
    nivel = 0
    for k in range(k, len(texto)):
        nivel += {"(": 1, ")": -1}.get(texto[k], 0)
        if nivel == 0:
            break
    j = texto.index("{", k)
    nivel = 0
    for k in range(j, len(texto)):
        nivel += {"{": 1, "}": -1}.get(texto[k], 0)
        if nivel == 0:
            return texto[j: k + 1]
    raise AssertionError(f"cuerpo sin cerrar: {cabecera}")


def test_i13_b_estado_categorial_solo_por_eleccion_explicita():
    """I13b: el borrador nace PENDIENTE y solo una eleccion explicita del usuario
    (nodo, «Sin categoría», «Continuar sin categoría») lo resuelve; el unico
    reinicio vuelve a PENDIENTE. Discriminante del mutante P03 (preseleccion)."""
    inicial = _cuerpo_ts(_texto(INT), "export function borradorInicial(")
    assert re.findall(r"\bcategoria:\s*(.*?),?\n", inicial) == ["{ estado: 'PENDIENTE' }"]
    reg = _texto(REG)
    assert reg.count("useState<Borrador>(") == 1
    assert "const [b, setB] = useState<Borrador>(() => borradorInicial(hoyIso));" in reg
    sitios = [linea.strip() for linea in reg.splitlines()
              if _ESTADO_LITERAL.search(linea) or _CAMPO_CATEGORIA.search(linea)]
    assert sorted(sitios) == sorted(SITIOS_ESTADO_CATEGORIAL), sorted(set(sitios) ^ set(SITIOS_ESTADO_CATEGORIAL))
    # Las fuentes de CATEGORIA / SIN_CATEGORIA solo se alcanzan desde el selector.
    assert reg.count("elegirNodo") == 2 and "onElegir={elegirNodo}" in reg
    assert len(re.findall(r"\bproponerCategoria\(", reg)) == 3  # elegirNodo, raiz, continuar sin categoria
    assert len(re.findall(r"\baplicarCategoria\(", reg)) == 2  # sin perdidas, y confirmar el descarte
    assert "onPress={() => aplicarCategoria(cambioPendiente.destino)}" in reg


_ORDENACION = re.compile(r"\.(sort|toSorted|reverse|toReversed)\s*\(|localeCompare|Intl\s*\.\s*Collator")

#: Registro CERRADO de llamadas de ordenacion en el camino de I13a: ninguna.
ORDENACIONES_CAMINO: list[tuple[str, str]] = []


def test_i13_c_orden_autoritativo_de_la_api_sin_reordenacion_en_el_cliente():
    """I13c: el arbol se presenta en el orden de la API (orden -> nombre -> id);
    el cliente no reordena en el camino de resolucion categorial."""
    halladas = [(ruta, linea.strip()) for ruta in CAMINO_CATEGORIAL
                for linea in _texto(ruta).splitlines() if _ORDENACION.search(linea)]
    assert halladas == ORDENACIONES_CAMINO, halladas
    construir = _cuerpo_ts(_texto(DOM), "export function construirArbol(")
    assert len(re.findall(r"\bfor\s*\(", construir)) == 1 and "for (const n of lista)" in construir
    assert re.findall(r"\.(push|unshift|splice)\(", construir) == ["push"]
    lecturas = (APP / "categorias" / "lecturas.py").read_bytes().decode("utf-8")
    assert '"ORDER BY orden, nombre, id"' in lecturas


def _es_intencion_categoria_id(n: ast.AST) -> bool:
    return isinstance(n, ast.Attribute) and n.attr == TOKEN and isinstance(n.value, ast.Name) and n.value.id == "intencion"


def test_i13_d_el_camino_vs01_del_backend_no_resuelve_categoria():
    """I13d: en el camino VS-01 del backend el categoria_id solo procede de la
    intencion sellada; la propiedad devuelve el campo o None. Corrobora
    test_152 (ausencia -> 422 y nunca SIN_CATEGORIA deducido)."""
    usos = 0
    for ruta in ("backend/app/api/ejecucion_gasto_pagado.py", "backend/app/api/traductor_gasto_pagado.py"):
        for nodo in ast.walk(ast.parse(_texto(ruta))):
            if isinstance(nodo, ast.keyword) and nodo.arg == TOKEN:
                assert _es_intencion_categoria_id(nodo.value), (ruta, ast.unparse(nodo))
            if isinstance(nodo, ast.Attribute) and nodo.attr == TOKEN:
                assert _es_intencion_categoria_id(nodo), (ruta, ast.unparse(nodo))
                usos += 1
            if isinstance(nodo, ast.Name) and nodo.id == TOKEN:
                raise AssertionError(f"variable categoria_id local en {ruta}: origen no sellado")
    assert usos > 0
    prop = _nodo("backend/app/api/dto_vs01.py", "IntencionGastoPagado.categoria_id")
    devueltos = [ast.unparse(r.value) for r in ast.walk(prop) if isinstance(r, ast.Return)]
    assert sorted(devueltos) == ["None", "self.categoria.categoria_id"], devueltos
    t152 = _texto("tests/api/test_152_f05_01_elegibilidad_categoria.py")
    assert "def test_ausencia_de_categoria_es_422_y_no_sin_categoria(" in t152


_PROPUESTA_TEXTUAL = re.compile(r"ranking|sugerenc|recomend|frecuen|m[aá]s usad", re.IGNORECASE)


def test_i13_e_barrido_textual_corroborante():
    """I13e: corroboracion textual acotada al codigo (no comentarios) de I13a.
    Nunca es el oraculo: la propiedad la fijan I13a..I13d."""
    for ruta in CAMINO_CATEGORIAL:
        codigo = [linea for linea in _texto(ruta).splitlines() if not linea.lstrip().startswith(("//", "*", "/*"))]
        assert not [linea for linea in codigo if _PROPUESTA_TEXTUAL.search(linea)], ruta


# ------------------------------------------------------------------ I3 de plantillas (J2 §1.6, aditivo)
def test_i3_plantillas_frontera():
    """backend/app/plantillas/: solo clases R, GUARDA, A_FRONTERA o PLANTILLA
    y sin referencias a servicios del motor con caminos A/B/P."""
    for (ruta, qual), (clase, _, _) in REGISTRO.items():
        if ruta.startswith("backend/app/plantillas/"):
            assert clase in {"R", "GUARDA", "A_FRONTERA", "PLANTILLA"}, (ruta, qual, clase)
    for p in sorted((APP / "plantillas").rglob("*.py")):
        arbol = ast.parse(p.read_bytes().decode("utf-8"))
        nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
        nombres |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
        for imp in (n for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)):
            nombres |= {a.name for a in imp.names}
        assert not nombres & set(SERVICIOS_VEDADOS_EN_FRONTERA), _rel(p)
