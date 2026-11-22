# Registro de peticiones (AJ-05 · R-C7-07)

Módulo: `registro_peticiones.py`. Lo usa el middleware `middleware_peticion.py`.
Origen: mandato F06 T4 AJ-05 (`b4ff6b70…`), §3.7; dictamen R2, AJ-R2-07; adendas 01 y 02.

## Qué registra
- **Formato:** JSONL, una línea por evento, en el directorio `GAPTO_LOG_DIR`. El fichero es `peticiones-AAAAMMDD.jsonl`, con fecha UTC.
- **RECIBIDA:** se escribe antes del enrutado y no lleva ruta.
- **TERMINADA:** se escribe al salir, también si hay una excepción. Lleva:
  - la plantilla de la ruta o `NO_RESUELTA`;
  - el estado HTTP, el código, el desenlace y la persistencia acumulada;
  - las unidades, con sus intentos y duraciones (conexión, transacción y COMMIT);
  - `fuera_de_plazo` y las anomalías.
- **Identidades:** cuatro, separadas: `http_request_id`, `client_attempt_id` (cabecera `X-Gapto-Intento-Id`), `intencion_id` (cabecera `X-Gapto-Intencion-Id`) y `audit_request_id`, este último uno por unidad. Las cabeceras solo se aceptan como UUID canónico; si no lo son, se registra `INVALIDO`.
- **Lo que nunca se registra:** cuerpos, importes, conceptos, `Authorization`, token, DSN ni mensajes de excepción. De una excepción solo se registra el nombre del tipo.

## Garantías y límites
- **Fail-closed al arrancar:** `create_app_desde_entorno` exige `GAPTO_LOG_DIR` fuera del repositorio. Escribe una línea real de comprobación, la relee y verifica su contenido; si algo falla, el backend no arranca (`RegistroNoDisponible`).
- **Fail-open en marcha:** un fallo de escritura (disco lleno, permisos o fichero bloqueado) nunca cambia el código HTTP, el cuerpo, las cabeceras funcionales ni el resultado transaccional, ni siquiera durante una excepción del backend. El fallo se cuenta en `fallos` y se avisa por consola con un texto fijo, sin datos de la petición.
- **Sin fsync por evento:** cada línea se vacía al buffer del sistema operativo, pero no se sincroniza en el disco físico. Es **trazabilidad operativa de mejor esfuerzo, no auditoría durable**. Un corte de energía o una caída del sistema pueden perder las últimas líneas, y el lector tolera una última línea truncada. La confirmación de las escrituras la dan `gapto.auditoria` y la reconciliación con la misma intención.
- **RECIBIDA sin TERMINADA** no prueba por sí sola una caída, porque también puede ser un fallo del registro. Que falte TERMINADA tampoco prueba que no se persistiera nada (adenda 02 §5).
- **Un solo proceso uvicorn:** un cerrojo serializa la escritura entre hilos. Con varios procesos sobre el mismo fichero, el registro **no es válido**; es un riesgo declarado.
- **Rotación y retención:** rotación diaria. Al cambiar de día se borran los `peticiones-*.jsonl` de más de 30 días y nada más.

## Configuración
- En ENV-DEV, `scripts/dev/envdev_arranque.ps1` fija `GAPTO_LOG_DIR=<Base>\logs`, fuera del repositorio.
- En los tests, el registro se inyecta con `create_app(registro=...)`. Sin registro, el middleware no escribe nada.
