# Salas de TryHackMe para satisfacer una oferta laboral

Este README también está disponible en:\
[en-GB](README.en-GB.md), [en-US](../README.md), es-AR, [es-ES](README.es-ES.md) 

Esta skill convierte los requisitos de una oferta laboral de ciberseguridad en una lista personalizada de capacitación de TryHackMe. Por defecto busca en los catálogos incluidos de salas y módulos; si el usuario lo pide, puede reconstruir ambos mediante la búsqueda autenticada de TryHackMe antes de encontrar coincidencias directas y complementarias para el puesto.

Una sala es un laboratorio práctico individual. Un módulo es una secuencia curada de salas, publicada en `https://tryhackme.com/module/<código>`. El informe recomienda primero las salas y después aconseja los módulos que las agrupan, de modo que el lector vea tanto los laboratorios sueltos como la ruta de aprendizaje que los recorre.

## Compatibilidad actual

La implementación funcional es compatible con Debian, Windows y macOS 10.14 o posterior. Debian lee Firefox, Chromium, LibreWolf y Epiphany. Windows lee Firefox y perfiles heredados compatibles de Chrome, Edge y Chromium; las cookies `v20` app-bound actuales siguen sin ser exportables por diseño. macOS 14 o posterior usa `os-mac/modern/`, que lee perfiles de Firefox, Safari, Chrome y Chromium y está validada en Sequoia 15.x. macOS 10.14 a 13.x usa `os-mac/legacy-http/`, que lee Firefox, Chrome y Chromium y está validada en Mojave 10.14.

El [catálogo de salas](thm-rooms/all-rooms.json) y el [catálogo de módulos](thm-modules/all-modules.json) generados contienen solamente datos públicos. Las cookies del navegador, los datos de la cuenta, el progreso personal y el texto de la oferta nunca se escriben en ellos.

## Requisitos

- Python 3.13 o posterior en Debian, Windows y la ruta moderna de macOS; Python 3.10 o posterior en la ruta HTTP heredada de macOS.
- Solamente para actualizar el catálogo en vivo: una sesión iniciada en TryHackMe, los paquetes Python de la plataforma seleccionada y sus requisitos documentados de navegador de automatización.
- Solamente para actualizar en vivo desde Debian, una ruta de proyecto lo bastante corta para el límite de sockets de Chromium; el comando lo indica con claridad si no lo es.

## Elección del catálogo

Cada ejecución de recomendaciones pregunta qué fuente debe usar, salvo que el pedido ya lo indique expresamente:

1. **Usar los catálogos incluidos — opción predeterminada y recomendada.** Omite el acceso al navegador y los dos gestores largos de catálogo.
2. **Actualizar y ampliar ambos catálogos.** Usa la sesión autorizada del navegador para volver a comprobar todas las salas y módulos contra TryHackMe antes de emparejar la oferta.

En el modo rápido predeterminado, antes de crear el informe solamente se comprueban los enlaces de salas y módulos que sobreviven a la revisión semántica. Toda respuesta distinta de HTTP 200 se reintenta una vez.

## Instalación en Debian

Esta instalación solamente es necesaria para una actualización en vivo. Ejecutala como el usuario de escritorio cuyo navegador contiene la sesión de TryHackMe:

```bash
python3 -m pip install -r os-debian/requirements.txt --break-system-packages
```

Si Chromium no está instalado, instalalo como `root`:

```bash
apt-get update
apt-get install chromium
```

## Instalación en Windows

Esta instalación solamente es necesaria para una actualización en vivo. Ejecutala desde PowerShell como el usuario de escritorio cuyo navegador contiene la sesión de TryHackMe:

```powershell
python -m pip install -r .\os-windows\requirements.txt
```

Firefox puede permanecer abierto mientras se lee su sesión. Chrome, Edge y Chromium pueden bloquear la base de datos de cookies mientras se ejecutan y las versiones actuales suelen usar cifrado `v20` app-bound no exportable. El helper de Windows informa ambas situaciones sin exponer cookies; cuando ocurra, usá un perfil autenticado de Firefox.

## Instalación en macOS

Esta instalación solamente es necesaria para una actualización en vivo. En macOS 14 o posterior, ejecutala como el usuario de escritorio cuyo perfil de Firefox, Safari, Chrome o Chromium contiene la sesión de TryHackMe:

```bash
python3 -m pip install -r os-mac/modern/requirements.txt
```

En macOS 10.14 a 13.x, instalá en su lugar `os-mac/legacy-http/requirements.txt`; esa ruta admite Firefox, Chrome y Chromium, pero no Safari. El navegador puede permanecer abierto. Para Chrome o Chromium, mantené desbloqueado el llavero de inicio de sesión y autorizá el acceso a Safe Storage si macOS lo solicita. Las contraseñas y cookies solamente permanecen en la memoria del proceso.

## Ejecutar una actualización del catálogo en vivo

Estos comandos se usan únicamente en el modo opcional de actualización en vivo. Desde esta carpeta, ejecutá ambos; cada uno abre su propia sesión de navegador:

```bash
./os-debian/manage_rooms.py --locale es-AR
./os-debian/manage_modules.py --locale es-AR
```

En Windows, usá:

```powershell
python .\os-windows\manage_rooms.py --locale es-AR
python .\os-windows\manage_modules.py --locale es-AR
```

En macOS, usá:

```bash
./os-mac/modern/manage_rooms.py --locale es-AR
./os-mac/modern/manage_modules.py --locale es-AR
```

En macOS 10.14 a 13.x, reemplazá `modern` por `legacy-http` en ambos comandos.

La primera ejecución de cada uno obtiene y verifica su catálogo completo. Cada ejecución posterior verifica primero las entradas guardadas, obtiene el listado vigente completo, agrega las salas o los módulos recién publicados y verifica esas incorporaciones. Las entradas que desaparecen del listado vigente se conservan como historial, pero quedan excluidas de las recomendaciones.

Si el control de seguridad de TryHackMe no puede completarse en un contexto Playwright, reintentá con `--headed`. En la ruta moderna bajo el sandbox Seatbelt de macOS, o en la ruta HTTP heredada, actualizá la página autenticada en el navegador de origen y repetí una vez.

## Emparejar una vacante

Invocá la skill y pegá el texto completo de la oferta. El modelo extrae habilidades concretas y busca en ambos catálogos con una consulta atómica por cada habilidad, herramienta o responsabilidad. Los scripts `search_rooms.py` y `search_modules.py` de la plataforma seleccionada informan los tokens coincidentes y la cobertura de cada candidato; después el modelo revisa semánticamente esa evidencia, elimina las coincidencias parciales, ordena las salas desde los fundamentos hasta el material especializado y las etiqueta como Gratis, Premium o MAX.

Los módulos candidatos incluyen además las salas que contienen, su duración estimada, sus prerequisitos y sus siguientes pasos, que es lo que permite que el consejo nombre el solapamiento con las salas ya recomendadas.

## Informe HTML persistente

Cada recomendación terminada crea también `rooms-to-satisfy-offer.html` en la carpeta desde la que se invocó la skill. El informe contiene primero una traducción completa de la oferta al idioma del usuario, seguida de las mismas tablas de recomendación revisadas que se muestran en la consola, después los módulos aconsejados y, por último, las carencias del catálogo.

El informe es autocontenido, adaptable, accesible, imprimible y compatible con los temas claro y oscuro del sistema. No contiene cookies ni datos de la cuenta. Volver a ejecutar la skill desde la misma carpeta reemplaza el informe anterior por la nueva oferta y sus recomendaciones.

## Ritmo de las solicitudes

Durante una actualización en vivo, las solicitudes de catálogo, de URL y de detalle de módulo son secuenciales. La espera empieza en 1,25 segundos, incluye variación aleatoria, disminuye lentamente tras rachas de éxito y aumenta cuando hay limitación de velocidad. Se respeta `Retry-After`, el progreso se guarda cada diez entradas y un bloqueo persistente detiene la ejecución sin descartar el trabajo ya terminado. En el modo incluido, la revisión selectiva final también es secuencial, espera brevemente entre enlaces y permite exactamente una segunda revisión por cada resultado distinto de 200.

El endpoint de búsqueda de módulos pagina sobre un índice no determinista, así que una sola pasada puede devolver solamente parte del catálogo. El comando repite la pasada hasta alcanzar el total que declara la propia plataforma y, mientras una pasada siga incompleta, ningún módulo guardado se marca como retirado.

## Límites de seguridad

Solamente durante una actualización en vivo se abren los almacenes de cookies mediante copias privadas dentro de la carpeta `../_/temp/thm/` del espacio de trabajo. Esas copias se eliminan después de usarse. En la ruta moderna de macOS, el almacén binario de Safari se analiza localmente; ambas rutas de macOS leen Safe Storage de Chromium mediante el llavero del sistema sin registrarlo. Las cookies se restringen a los dominios de TryHackMe, nunca se imprimen y se usan solamente para confirmar la sesión, leer los catálogos y verificar las URL canónicas de salas y módulos. El modo incluido nunca lee datos del navegador. La skill no arranca máquinas, no resuelve salas ni evade el acceso pago.
