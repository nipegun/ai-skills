# Manual de uso

Este MANUAL también está disponible en:\
[en-GB](MANUAL.en-GB.md), [en-US](MANUAL.md), es-AR, [es-ES](MANUAL.es-ES.md) 

## Propósito

Usá esta skill cuando tengas una oferta laboral de ciberseguridad y quieras una lista completa y razonada de salas de TryHackMe que enseñen las habilidades exigidas, junto con los módulos que agrupan esas salas en una ruta de aprendizaje. Por defecto, la skill usa sus catálogos incluidos; un modo opcional de actualización en vivo los reconstruye desde TryHackMe antes de analizar la oferta.

## Elegir el modo de catálogo

Salvo que el pedido ya indique una opción, la skill pregunta primero si querés usar los catálogos incluidos o actualizar y ampliar ambos catálogos desde TryHackMe. Usar los datos incluidos es la opción recomendada y predeterminada, no necesita una sesión de navegador y genera el resultado mucho más rápido. Una actualización en vivo puede tardar decenas de minutos.

En el modo incluido, antes del informe final solamente se revisan los enlaces que aparecen en la recomendación revisada. Todo enlace que no devuelva HTTP 200 se revisa una vez más. Una recomendación cuya indisponibilidad quede confirmada, por ejemplo mediante HTTP 404 o 410, se elimina y se declara como carencia del catálogo. Una limitación de velocidad, un control de seguridad, un error del servidor o una falla de transporte repetidos solamente permiten conservar una entrada de caché validada con anterioridad, y la respuesta final indica que la comprobación actual no fue concluyente.

## Preparación de actualización en vivo en Debian

1. Iniciá sesión en `https://tryhackme.com` con Firefox, Chromium, LibreWolf o Epiphany.
2. Mantené desbloqueado el llavero del escritorio si la sesión activa está en Chromium.
3. Instalá las dependencias de `os-debian/requirements.txt`.
4. Invocá `$tryhackme-rooms-to-satisfy-job-offer` y pegá la oferta cuando se te solicite.

Cuando se selecciona la actualización en vivo, la skill ejecuta automáticamente ambos comandos de catálogo. Para ejecutarlos vos mismo, usá:

```bash
./os-debian/manage_rooms.py --locale es-AR
./os-debian/manage_modules.py --locale es-AR
```

Son comandos independientes y cada uno abre su propia sesión de navegador, así que podés ejecutar solamente uno de ellos cuando quieras actualizar un único catálogo.

## Preparación de actualización en vivo en Windows

1. Iniciá sesión en `https://tryhackme.com` con Firefox. También se detectan perfiles de Chrome, Edge y Chromium, pero otra aplicación no puede exportar las cookies `v20` app-bound actuales.
2. Instalá las dependencias de `os-windows/requirements.txt` con el mismo usuario de escritorio propietario del perfil del navegador.
3. Comprobá que Chrome, Edge o Chromium esté instalado como navegador aislado de automatización.
4. Invocá `$tryhackme-rooms-to-satisfy-job-offer` y pegá la oferta cuando se te solicite.

Los comandos manuales equivalentes son:

```powershell
python .\os-windows\manage_rooms.py --locale es-AR
python .\os-windows\manage_modules.py --locale es-AR
```

Firefox puede permanecer abierto. Para diagnosticar Chrome, Edge o Chromium con `--browser`, cerrá primero ese navegador por completo para que Windows pueda crear una copia de su base de datos. Si después informa cifrado `v20` app-bound, usá Firefox: esa protección impide deliberadamente exportar las cookies.

## Preparación de actualización en vivo en macOS

1. En macOS 14 o posterior, iniciá sesión en `https://tryhackme.com` con Firefox, Safari, Google Chrome o Chromium. En macOS 10.14 a 13.x, usá Firefox, Chrome o Chromium.
2. Instalá las dependencias de `os-mac/modern/requirements.txt` con el usuario de escritorio propietario del perfil. En macOS 10.14 a 13.x, usá `os-mac/legacy-http/requirements.txt`.
3. Para Chrome o Chromium, mantené desbloqueado el llavero de inicio de sesión y autorizá el acceso a Safe Storage si macOS lo solicita.
4. Invocá `$tryhackme-rooms-to-satisfy-job-offer` y pegá la oferta cuando se solicite.

Los comandos manuales equivalentes son:

```bash
./os-mac/modern/manage_rooms.py --locale es-AR
./os-mac/modern/manage_modules.py --locale es-AR
```

En macOS 10.14 a 13.x, reemplazá `modern` por `legacy-http` en ambos comandos. Todos los navegadores de origen pueden permanecer abiertos. Los valores de Firefox se leen desde una copia SQLite privada, los de Safari en la ruta moderna desde una copia binaria privada y los de Chrome o Chromium se descifran en memoria con su elemento Safe Storage del llavero.

## Qué ocurre durante la preparación de salas

Esta sección solamente se aplica al modo opcional de actualización en vivo.

El comando revisa cada perfil de navegador compatible hasta que TryHackMe confirma una sesión autenticada. No considera suficiente la mera presencia de una cookie.

Si falta `thm-rooms/all-rooms.json`, se recopila y valida el catálogo completo de salas. Si la caché existe, primero se validan todas las URL guardadas. Después se obtiene el catálogo vigente completo en cada ejecución, para poder agregar y validar de inmediato las salas recién publicadas.

Las salas ausentes del último listado vigente se conservan con `listed: false` para el historial y la auditoría. La búsqueda de recomendaciones no las usa. Una sala que vuelve a aparecer se marca de nuevo como listada y su URL se revalida.

A continuación se revisa cada URL canónica de sala con una solicitud GET liviana. Para un catálogo de aproximadamente 1.300 salas, una pasada completa normal tarda entre 17 y 30 minutos antes de las esperas de red. El progreso se guarda cada diez salas, así que una ejecución interrumpida conserva las comprobaciones terminadas.

## Qué ocurre durante la preparación de módulos

`./os-debian/manage_modules.py` prepara `thm-modules/all-modules.json` de la misma forma, pero un módulo se verifica leyendo su detalle oficial en lugar de descargando su página: `https://tryhackme.com/module/<código>` es una ruta de aplicación de página única que responde HTTP 200 para cualquier camino, así que no demuestra nada. El endpoint de detalle responde HTTP 404 cuando el módulo ya no existe.

En Windows, `python .\os-windows\manage_modules.py` realiza el mismo flujo y usa el mismo contrato de caché. En macOS, usá el `manage_modules.py` específico de la versión que seleccione `os-mac/MACOS.md`.

Cada lectura de detalle actualiza además las salas que contiene el módulo, su duración estimada, sus prerequisitos, sus siguientes pasos y sus aprendizajes clave. El nivel de acceso se deriva de las salas: si todas son gratuitas el módulo es Gratis, y si al menos una es paga el módulo es Premium.

Para unos 170 módulos, una pasada completa tarda alrededor de cuatro minutos. El progreso se guarda cada diez módulos. Un módulo que falla por un error de red transitorio conserva su estado verificado anterior en lugar de desaparecer del consejo.

El endpoint de búsqueda de módulos pagina sobre un índice no determinista: las páginas consecutivas se solapan y una sola pasada puede devolver solamente parte del catálogo. El comando repite la pasada hasta alcanzar el total que declara la plataforma y, mientras una pasada siga incompleta, no marca como retirado ningún módulo que falte.

## Alternativa con navegador visible

Si un comando informa que el control de seguridad no pudo completarse, cerrá el proceso fallido y ejecutá ese mismo comando con `--headed`:

```bash
./os-debian/manage_modules.py --locale es-AR --headed
```

En una ruta que usa Playwright se abre una ventana de Chromium. Completá ahí cualquier aviso de TryHackMe o de Vercel. Las cookies importadas quedan en el contexto aislado temporal y se descartan cuando el comando termina. La ruta HTTP heredada de macOS no inicia un navegador de automatización.

En Windows, la alternativa equivalente es:

```powershell
python .\os-windows\manage_modules.py --locale es-AR --headed
```

La ruta moderna de macOS prefiere Playwright y admite el mismo recurso `--headed` fuera de entornos restringidos. Bajo el sandbox Seatbelt de macOS usa automáticamente una jarra HTTPS limitada a TryHackMe porque Chromium no puede registrar su servicio Mach; si ese transporte informa el control de seguridad, actualizá una página autenticada en el navegador de origen y repetí una vez. La ruta HTTP heredada usa ese mismo comportamiento de actualización y repetición.

## Aportar la oferta laboral

Pegá el texto completo, incluidas responsabilidades, habilidades obligatorias, habilidades deseables, plataformas, herramientas y nivel de seniority. Sacar secciones puede ocultar capacitación útil. La skill convierte la oferta en búsquedas atómicas y solamente acepta un candidato cuando tiene una cobertura de tokens significativa o evidencia exacta; la decisión semántica final la sigue tomando el modelo.

La respuesta final separa:

- Salas nucleares que cubren directamente los requisitos obligatorios.
- Salas específicas del puesto para herramientas, plataformas y responsabilidades concretas.
- Salas complementarias que cubren prerequisitos o habilidades deseables.
- Módulos aconsejados que agrupan las salas recomendadas en una ruta de aprendizaje.
- Carencias del catálogo para los requisitos sin una coincidencia defendible.

Cada recomendación de sala incluye el título oficial, la relevancia, el nivel de suscripción y la URL canónica. Cada módulo aconsejado agrega su tiempo estimado, cuántas salas contiene y cuáles de esas salas ya se recomendaron más arriba. El contenido Premium y MAX es solamente una recomendación; la skill no evade sus controles de acceso.

## Informe HTML

Después de imprimir las tablas completas, la skill crea `rooms-to-satisfy-offer.html` en la carpeta desde la que se invocó. Abrí ese archivo en cualquier navegador moderno para conservar la oferta traducida, la evaluación del puesto, el estado del catálogo, las tablas de recomendación, los módulos aconsejados y los requisitos no cubiertos. Las tablas de módulos van siempre después de las tablas de salas.

En el modo incluido, `scripts/verify_recommendations.py` lee los datos revisados del informe, revisa únicamente sus enlaces canónicos de salas y módulos de TryHackMe y repite una vez cada respuesta distinta de 200 antes de ejecutar el renderizador.

La oferta se traduce por completo en lugar de resumirse. Se conservan los nombres, los productos, las URL, las monedas, las cifras salariales y la estructura de las listas. El informe sigue el tema claro u oscuro del sistema e incluye formato específico para impresión. Una ejecución posterior en la misma carpeta reemplaza el archivo.

## Opciones manuales de catálogo

Cuando se selecciona el modo de actualización en vivo, el descubrimiento es automático en cada ejecución de ambos comandos y no tiene opción para desactivarlo. En Debian usá `--browser firefox`, `chromium`, `librewolf` o `epiphany`; en Windows usá `--browser firefox`, `chrome`, `edge` o `chromium`; en la ruta moderna de macOS usá `--browser firefox`, `safari`, `chrome` o `chromium`. La ruta HTTP heredada de macOS omite `safari`. Usá `--locale en-GB`, `en-US`, `es-AR` o `es-ES` para los mensajes de los comandos.

`--skip-url-validation` en el comando de salas y `--skip-module-details` en el de módulos existen para una actualización rápida pedida explícitamente. Ninguno se usa en el flujo normal de actualización en vivo: la verificación completa forma parte de ese modo y, sin sus detalles, un módulo no tiene nivel de acceso, ni duración, ni lista de salas, así que no puede aconsejarse.

## Fallas habituales

### No hay sesión utilizable

Abrí TryHackMe en un navegador compatible, iniciá sesión, confirmá que funciona una página autenticada y volvé a ejecutar la skill. Una base de datos de cookies vencida se ignora.

### Llavero de Chromium bloqueado

Desbloqueá el llavero de GNOME del usuario de escritorio actual, o usá en su lugar un perfil autenticado de Firefox, LibreWolf o Epiphany.

### Base de datos de Chromium bloqueada o app-bound en Windows

Cerrá Chrome, Edge o Chromium por completo antes de seleccionar ese navegador explícitamente. Si la ejecución siguiente informa cifrado `v20` app-bound, el navegador funciona como está diseñado y otro proceso no puede exportar esas cookies. Usá un perfil autenticado de Firefox. La skill no evade este límite de seguridad de Windows.

### Safe Storage no disponible en macOS

Ejecutá el comando como el mismo usuario de escritorio propietario del perfil de Chrome o Chromium, desbloqueá el llavero de inicio de sesión y autorizá el acceso si macOS lo solicita. Si el entorno de ejecución no puede acceder al llavero del escritorio interactivo, usá un perfil autenticado de Firefox o Safari; la skill no extrae memoria de procesos del navegador ni cambia la seguridad del llavero.

### La ruta del espacio de trabajo es demasiado profunda

El socket de instancia única de Chromium no puede superar los 104 caracteres y la carpeta temporal del proyecto contribuye a esa longitud. El comando se niega a arrancar con un mensaje que nombra la ruta problemática; mové el proyecto a una ruta absoluta más corta.

### Respuestas HTTP 429 persistentes

El comando aumenta su espera y respeta `Retry-After`. Si tres entradas consecutivas siguen bloqueadas tras tres reintentos cada una, se detiene y conserva el progreso guardado. Esperá antes de reanudar; no reduzcas la espera para saltear el límite.

### Falta un paquete de Python

Ejecutá:

```bash
python3 -m pip install -r os-debian/requirements.txt --break-system-packages
```

En Windows, ejecutá:

```powershell
python -m pip install -r .\os-windows\requirements.txt
```

En macOS, ejecutá:

```bash
python3 -m pip install -r os-mac/modern/requirements.txt
```

En macOS 10.14 a 13.x, instalá en su lugar `os-mac/legacy-http/requirements.txt`.

## Privacidad

Ambas cachés contienen metadatos públicos y el estado de verificación HTTP. No contienen valores de cookies, historial del navegador, datos de la cuenta, tu propio progreso por las salas de un módulo ni la oferta laboral pegada. Las copias temporales de los almacenes de cookies se crean solamente dentro de la carpeta temporal del proyecto y se eliminan cuando termina la lectura. En la ruta moderna de macOS, los valores de Safari solamente permanecen en memoria; en ambas rutas de macOS ocurre lo mismo con Safe Storage y las cookies de Chromium descifradas.
