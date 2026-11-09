# Guía del código

Este CODE también está disponible en:\
[en-GB](CODE.en-GB.md), [en-US](CODE.md), [es-AR](CODE.es-AR.md), es-ES.

## Índice

1. [Arquitectura y decisiones de diseño](#arquitectura-y-decisiones-de-diseño)
2. [Mapa de módulos](#mapa-de-módulos)
3. [Índice de símbolos clave](#índice-de-símbolos-clave)
4. [Flujos principales](#flujos-principales)
5. [Mapa de comandos](#mapa-de-comandos)
6. [Análisis de impacto](#análisis-de-impacto)
7. [Puntos de extensión](#puntos-de-extensión)

## Arquitectura y decisiones de diseño

El punto de entrada de la skill controla una elección de catálogo independiente de la plataforma. La ruta predeterminada lee las cachés incluidas, busca candidatos y realiza la revisión semántica; después comprueba únicamente los enlaces canónicos que han sobrevivido hasta la recomendación revisada. La ruta opcional de actualización en vivo enruta a la implementación del sistema operativo, obtiene una sesión autorizada y reconstruye ambos catálogos antes de las mismas etapas de búsqueda y revisión. Así, la ruta rápida común no depende del almacenamiento del navegador y las credenciales específicas de cada plataforma quedan limitadas a una actualización explícita.

La skill separa tres responsabilidades: obtener cookies de sesión autorizadas, usar esas cookies mediante el transporte de la plataforma seleccionada y ordenar metadatos públicos guardados en caché. Esta frontera mantiene los detalles del almacenamiento del navegador fuera del cliente de TryHackMe y las credenciales de la cuenta fuera de la lógica de recomendación.

Las llamadas HTTP directas a la aplicación actual de TryHackMe topan con su control de seguridad en JavaScript. Por eso `TryHackMeBrowserClient` lanza un Chromium del sistema aislado mediante Playwright, importa únicamente las cookies de TryHackMe y hace llamadas `fetch` del mismo origen desde el navegador. Las cookies de Firefox, LibreWolf y Epiphany son valores SQLite en texto plano; los valores `v10` y `v11` de Chromium se descifran localmente con el algoritmo de Chromium para Linux y Secret Service. El socket de instancia única de Chromium no puede superar los 104 caracteres, y la carpeta temporal del espacio de trabajo contribuye a esa longitud, así que `fRequireUsableSocketPath` se niega a arrancar con un mensaje diagnosticable en lugar del fallo opaco del navegador que provocaría una ruta de proyecto profunda.

Windows mantiene su lógica de credenciales en `os-windows/`. Firefox se lee mediante la API de copia de seguridad de SQLite y admite la caducidad expresada en segundos o milisegundos. Los perfiles compatibles de Chrome, Edge y Chromium usan DPAPI del usuario actual más AES-GCM para valores heredados `v10`/`v11`. Los valores `v20` app-bound se rechazan explícitamente porque Windows vincula su descifrado a la aplicación del navegador; la implementación no inyecta código ni eleva privilegios para eludir ese límite. El cliente aislado localiza Chrome, Edge o Chromium instalado y reutiliza los mismos contratos públicos de catálogo, caché e informe que Debian.

`os-mac/MACOS.md` dirige macOS 14 o posterior a `os-mac/modern/` y macOS 10.14 a 13.x a `os-mac/legacy-http/`. Ambas rutas leen Firefox desde copias SQLite privadas y descifran los valores `v10` de Chrome o Chromium con Safe Storage, PBKDF2-HMAC-SHA1, 1.003 iteraciones y AES-128-CBC. La ruta moderna también analiza registros acotados de `Cookies.binarycookies` de Safari. Su cliente prefiere un contexto Playwright aislado, pero detecta el sandbox Seatbelt de macOS —que deniega el servicio de encuentro Mach de Chromium— y entonces usa un `CookieJar` en memoria cuyas peticiones y redirecciones se limitan a dominios HTTPS de TryHackMe. La ruta HTTP heredada siempre usa ese transporte restringido. Todas las rutas verifican la sesión mediante `/api/v2/users/self`; Safe Storage y las cookies en claro nunca se registran ni persisten.

Los dos tipos de contenido son deliberadamente dos comandos con dos cachés. Una sala es un laboratorio individual; un módulo es una secuencia comisariada de salas. Se verifican con mecanismos distintos y sus costes de preparación difieren en un orden de magnitud, así que acoplarlos obligaría a quien quiere uno a pagar por el otro. Cada comando abre su propia sesión autenticada y es dueño de su propio archivo de caché.

Las cachés son una frontera operativa. El esquema 2 de salas y el esquema 1 de módulos guardan metadatos públicos normalizados, el estado de verificación y el historial de descubrimiento, nunca datos de sesión ni de cuenta. El detalle de módulo descarta a propósito los campos `progress` y `toPay` de la plataforma, porque describen al usuario que ha iniciado sesión y no al contenido. Ambas fusiones son uniones: las entradas nuevas se añaden, las que reaparecen se vuelven a listar y las que faltan se conservan con `listed: false`. Las escrituras se preparan bajo la carpeta temporal del proyecto, se vuelcan, se sincronizan y se reemplazan de forma atómica.

Salas y módulos se verifican de forma distinta porque la plataforma responde de forma distinta. Una sala se valida con un GET ligero de su URL canónica. Un módulo no puede validarse así, porque `https://tryhackme.com/module/<código>` es una ruta de aplicación de página única que devuelve HTTP 200 para cualquier camino; `/api/v2/modules/data?moduleURL=<código>` devuelve HTTP 404 cuando el módulo ya no existe, así que la lectura del detalle es a la vez el enriquecimiento y la prueba de existencia.

El endpoint de búsqueda de módulos pagina sobre un índice no determinista: las páginas consecutivas se solapan y una sola pasada puede devolver únicamente parte del catálogo, con un déficit que varía entre ejecuciones por lo demás idénticas. Por eso `mFetchModuleCatalogue` repite la pasada y une los resultados hasta alcanzar el total que declara el propio endpoint, y devuelve ese total para que `fDiscoverModules` pueda decidir si la pasada fue completa. Una pasada incompleta nunca marca como retirado un módulo guardado, y un fallo transitorio de detalle nunca degrada un módulo que una pasada anterior verificó, porque la búsqueda sólo acepta módulos verificados y cualquiera de esos sucesos borraría en silencio contenido real del consejo.

Ninguno de los dos catálogos es lo bastante pequeño para inyectarlo en el contexto del modelo. `search_rooms.py` normaliza las variantes técnicas habituales, aplica una ordenación estilo BM25 con refuerzo por frase exacta y descarta las coincidencias parciales sin cobertura significativa de tokens. `search_modules.py` reutiliza esa puntuación, pero construye sus documentos con el título, el resumen, la descripción, los aprendizajes clave, las etiquetas del módulo y los títulos de las salas que contiene, que es lo que permite que un módulo coincida con el vocabulario de la oferta a través de sus laboratorios. Cada consulta aceptada emite sus tokens coincidentes, su cobertura y la evidencia de frase exacta. Después la skill toma la decisión semántica contra la oferta original, porque una ordenación determinista de texto no puede decidir por sí sola si un contenido enseña realmente un requisito.

El resultado revisado cruza una segunda frontera explícita antes de persistirse. En el modo incluido, el script independiente de plataforma `scripts/verify_recommendations.py` extrae únicamente las URL canónicas de salas y módulos del JSON revisado, las comprueba de forma secuencial sin cookies de navegador y repite exactamente una vez cada resultado distinto de 200. La skill elimina antes de renderizar el contenido cuya indisponibilidad queda confirmada con HTTP 404 o 410. Las limitaciones de velocidad, los controles de seguridad, los errores del servidor y los fallos de transporte no son concluyentes y sólo permiten conservar una entrada de caché con una validación anterior correcta, indicándolo expresamente. Después, `render_report.py` valida el contrato JSON reducido, escapa cada valor y genera un `rooms-to-satisfy-offer.html` autocontenido en la carpeta de invocación. Las tablas de módulos se renderizan después de todas las tablas de salas, porque el consejo trata del orden de aprendizaje sobre contenido que el lector ya ha visto. El JSON intermedio es temporal; sólo el HTML solicitado por el usuario conserva la oferta traducida.

Todos los bucles de red son secuenciales. La espera adaptable, la variación aleatoria, los reintentos acotados, el respeto de `Retry-After`, los guardados incrementales y una condición de parada por bloqueo persistente limitan la carga sobre la plataforma y permiten reanudar las ejecuciones largas.

## Mapa de módulos

| Módulo | Ruta | Responsabilidad | Depende de | Usado por |
|---|---|---|---|---|
| Punto de entrada | `SKILL.md` | Enruta por sistema operativo y define el flujo de recomendación | `os-debian/DEBIAN.md`, `os-windows/WINDOWS.md`, `os-mac/MACOS.md` | Cargador de skills |
| Operaciones de salas | `os-debian/manage_rooms.py` | CLI de salas, migración, descubrimiento con validación previa, unión de caché y orquestación de sesión | `browser_sessions.py`, `tryhackme_client.py`, `i18n/*.json` | `SKILL.md`, `manage_modules.py`, operador |
| Operaciones de módulos | `os-debian/manage_modules.py` | CLI de módulos, refresco de detalles previo, descubrimiento, unión de caché y estado de detalle | `manage_rooms.py`, `tryhackme_client.py` | `SKILL.md`, `search_modules.py`, operador |
| Sesiones de navegador | `os-debian/browser_sessions.py` | Descubre perfiles, copia almacenes SQLite y descifra valores de Chromium | SQLite, SecretStorage, cryptography | `manage_rooms.py` |
| Cliente de TryHackMe | `os-debian/tryhackme_client.py` | Control de seguridad, autenticación, paginación de salas y módulos, normalización y GET ligeros | Playwright, Chromium del sistema | `manage_rooms.py`, `manage_modules.py` |
| Búsqueda de salas | `os-debian/search_rooms.py` | Ordena las salas válidas guardadas según los requisitos extraídos | `manage_rooms.py`, `all-rooms.json` | `SKILL.md`, `search_modules.py` |
| Búsqueda de módulos | `os-debian/search_modules.py` | Ordena los módulos verificados usando su propio texto y los títulos de sus salas | `manage_modules.py`, `search_rooms.py`, `all-modules.json` | `SKILL.md` |
| Verificador selectivo de recomendaciones | `scripts/verify_recommendations.py` | Comprueba únicamente los enlaces canónicos revisados de salas y módulos y repite una vez un resultado distinto de 200 | JSON del informe, enlaces públicos de TryHackMe | `SKILL.md` |
| Renderizador HTML | `os-debian/render_report.py` | Valida los datos revisados del informe y genera el informe adaptable persistente | `manage_rooms.py`, `i18n/*.json` | `SKILL.md` |
| Implementación de Windows | `os-windows/*.py` | Replica los flujos de catálogo, búsqueda e informe con descubrimiento de navegadores de Windows, DPAPI/AES-GCM y selección de ejecutable | Perfiles de navegador de Windows, SQLite, DPAPI, Playwright | `SKILL.md`, operador |
| Enrutamiento de macOS | `os-mac/MACOS.md` | Selecciona la implementación documentada por familia de versiones y capacidad de transporte | Versión de macOS | `SKILL.md`, operador |
| Implementación moderna de macOS | `os-mac/modern/*.py` | Añade el descubrimiento binario de Safari y un cliente que prioriza Playwright con fallback limitado a TryHackMe bajo Seatbelt | Perfiles de navegador de macOS, SQLite, cookies binarias de Safari, llavero, cryptography, Playwright | `os-mac/MACOS.md`, operador |
| Implementación HTTP heredada de macOS | `os-mac/legacy-http/*.py` | Replica los flujos con descubrimiento de perfiles Firefox/Chromium, Keychain/AES-CBC y un transporte HTTP restringido por dominio | Perfiles de navegador de macOS, SQLite, llavero, cryptography | `os-mac/MACOS.md`, operador |
| Localización | `i18n/*.json` | Contiene las cadenas de comandos y de informe para cuatro idiomas | JSON | `Localiser` |
| Caché de salas | `thm-rooms/all-rooms.json` | Guarda el catálogo de salas versionado y sus datos de validación | Catálogo de TryHackMe | Gestor y buscador de salas |
| Caché de módulos | `thm-modules/all-modules.json` | Guarda el catálogo de módulos, sus listas de salas, duraciones y verificación de detalle | Endpoints de búsqueda y detalle de módulos | Gestor y buscador de módulos |

## Índice de símbolos clave

| Símbolo | Archivo:línea | Qué hace |
|---|---|---|
| `fDiscoverCookieStores` | `os-debian/browser_sessions.py:65` | Encuentra los almacenes nativos y en sandbox compatibles |
| `fGetChromiumSafeStoragePassword` | `os-debian/browser_sessions.py:171` | Obtiene el secreto de cifrado de Chromium sin registrarlo |
| `fDecryptChromiumCookie` | `os-debian/browser_sessions.py:215` | Descifra los valores `v10`/`v11` de Chromium en Linux |
| `fFindSessionCandidates` | `os-debian/browser_sessions.py:341` | Construye perfiles candidatos con cookies de TryHackMe sin caducar |
| `fDiscoverCookieStores` | `os-windows/browser_sessions.py` | Encuentra almacenes de Firefox, Chrome, Edge y Chromium en Windows |
| `fWindowsDpapiUnprotect` | `os-windows/browser_sessions.py` | Descifra blobs DPAPI del usuario actual sin registrar su contenido |
| `fReadChromiumMasterKey` | `os-windows/browser_sessions.py` | Lee una clave AES compatible de Chromium desde `Local State` |
| `fDecryptChromiumCookie` | `os-windows/browser_sessions.py` | Descifra valores DPAPI o AES-GCM `v10`/`v11` y rechaza `v20` |
| `fGeckoExpiryToUnix` | `os-windows/browser_sessions.py` | Normaliza segundos y milisegundos de Firefox antes de importar en Playwright |
| `fReadMacKeychainPassword` | `os-mac/legacy-http/browser_sessions.py` | Lee Safe Storage de Chrome o Chromium sin registrarlo |
| `fDecryptChromiumCookie` | `os-mac/legacy-http/browser_sessions.py` | Descifra valores `v10` AES-CBC de Chromium en macOS y retira el hash del host |
| `fRequireTryHackMeUrl` | `os-mac/legacy-http/tryhackme_client.py` | Impide que peticiones o redirecciones autenticadas de macOS salgan de TryHackMe |
| `fReadSafariCookies` | `os-mac/modern/browser_sessions.py` | Analiza registros acotados de Safari y conserva únicamente cookies vigentes de TryHackMe |
| `fCanLaunchMacBrowser` | `os-mac/modern/tryhackme_client.py` | Selecciona el fallback HTTPS restringido cuando la variable de entorno `CODEX_SANDBOX` indica Seatbelt |
| `fRequireTryHackMeUrl` | `os-mac/modern/tryhackme_client.py` | Mantiene las peticiones y redirecciones del fallback en hosts HTTPS de TryHackMe |
| `AdaptiveRateLimiter` | `os-debian/tryhackme_client.py:112` | Controla el ritmo secuencial de las peticiones y su espera |
| `fRequireUsableSocketPath` | `os-debian/tryhackme_client.py:154` | Rechaza una ruta demasiado profunda para el socket de Chromium |
| `fNormaliseRoom` | `os-debian/tryhackme_client.py:269` | Traduce las claves cambiantes de la API a metadatos estables de sala |
| `fExtractModuleCode` | `os-debian/tryhackme_client.py:398` | Lee un código de módulo de `moduleURL`, una ruta `/module/` o un slug |
| `fNormaliseModule` | `os-debian/tryhackme_client.py:442` | Traduce un registro de búsqueda de módulo a metadatos estables |
| `fFindModuleRecordList` | `os-debian/tryhackme_client.py:499` | Encuentra la lista con aspecto de módulos en un payload tolerante |
| `fNormaliseModuleRoom` | `os-debian/tryhackme_client.py:528` | Conserva los campos de sala de un módulo y descarta el progreso de la cuenta |
| `fNormaliseModuleDetail` | `os-debian/tryhackme_client.py:551` | Deriva salas, nivel, duración, prerequisitos y aprendizajes clave |
| `TryHackMeBrowserClient.mVerifySession` | `os-debian/tryhackme_client.py:763` | Confirma las cookies importadas con el endpoint de usuario autenticado |
| `TryHackMeBrowserClient.mFetchCatalogue` | `os-debian/tryhackme_client.py:783` | Pagina y deduplica todas las salas del catálogo |
| `TryHackMeBrowserClient.mFetchModuleCatalogue` | `os-debian/tryhackme_client.py:868` | Repite pasadas sobre el índice inestable hasta alcanzar su total |
| `TryHackMeBrowserClient.mFetchModuleData` | `os-debian/tryhackme_client.py:960` | Lee el detalle oficial de un módulo y prueba si aún existe |
| `fMigrateCache` | `os-debian/manage_rooms.py:122` | Migra las salas del esquema 1 al esquema 2 con historial |
| `fMergeCatalogue` | `os-debian/manage_rooms.py:234` | Une el descubrimiento vigente con el historial e informa de los cambios |
| `fDiscoverCatalogue` | `os-debian/manage_rooms.py:408` | Obtiene todas las páginas del catálogo vigente en cada ejecución |
| `fValidateCatalogueUrls` | `os-debian/manage_rooms.py:472` | Valida todas las salas o sólo los códigos recién descubiertos |
| `fMergeModuleCatalogue` | `os-debian/manage_modules.py:161` | Une el descubrimiento de módulos y respeta el listado si la pasada es parcial |
| `fDiscoverModules` | `os-debian/manage_modules.py:248` | Ejecuta el descubrimiento y decide si la pasada fue completa |
| `fApplyModuleDetail` | `os-debian/manage_modules.py:314` | Guarda los metadatos de detalle y protege a los módulos verificados de fallos transitorios |
| `fFetchModuleDetails` | `os-debian/manage_modules.py:370` | Lee todos los detalles o una selección con limitación adaptable |
| `fRankRooms` | `os-debian/search_rooms.py:229` | Produce un conjunto compacto de salas candidatas con evidencia |
| `fPrepareModuleDocuments` | `os-debian/search_modules.py:44` | Crea los documentos de módulo con su texto y los títulos de sus salas |
| `fRankModules` | `os-debian/search_modules.py:92` | Produce candidatos de módulo con salas, duración y datos de orden |
| `fExtractRecommendationUrls` | `scripts/verify_recommendations.py:94` | Extrae y deduplica únicamente los enlaces canónicos revisados de salas y módulos |
| `fCheckUrl` | `scripts/verify_recommendations.py:204` | Comprueba un enlace y hace exactamente una segunda comprobación tras un resultado distinto de 200 |
| `fValidateCanonicalUrl` | `os-debian/render_report.py:377` | Restringe los enlaces del informe a URL canónicas de sala o módulo |
| `fFormatDuration` | `os-debian/render_report.py:588` | Escribe horas enteras por encima de una hora y minutos por debajo |
| `fRenderModuleTable` | `os-debian/render_report.py:656` | Renderiza la tabla de módulos aconsejados con su columna de salas |
| `fBuildHtml` | `os-debian/render_report.py:739` | Escapa los datos revisados y construye el documento HTML autocontenido |

## Flujos principales

### Elección del modo de catálogo

El modelo pregunta por el modo incluido o de actualización en vivo → el modo incluido se presenta primero y es el predeterminado → el modo incluido confirma que ambas cachés son legibles y omite la obtención de sesión → la actualización en vivo enruta por sistema operativo y ejecuta ambos comandos de preparación.

### Preparación en vivo del catálogo de salas

`manage_rooms.fMain` → `fOpenAuthenticatedClient` → `fLoadCache`/`fMigrateCache` → `fValidateCatalogueUrls` completo → `fDiscoverCatalogue` → `mFetchCatalogue` → `fMergeCatalogue` → `fSaveCache` → validación selectiva de los códigos nuevos o recuperados.

### Preparación en vivo del catálogo de módulos

`manage_modules.fMain` → `fOpenAuthenticatedClient` → `fLoadModuleCache` → `fFetchModuleDetails` completo → `fDiscoverModules` → `mFetchModuleCatalogue` (pasadas repetidas) → `fMergeModuleCatalogue` con el indicador de completitud → `fSaveModuleCache` → `fFetchModuleDetails` selectivo para los códigos nuevos o recuperados.

### Obtención de la sesión en vivo

`fFindSessionCandidates` → `fDiscoverCookieStores` de la plataforma → copia privada → `fReadGeckoCookies`, `fReadSafariCookies` o `fReadChromiumCookies` → descifrado de la plataforma cuando haga falta (Secret Service en Debian, DPAPI/AES-GCM en Windows, llavero/AES-CBC en macOS) → contexto Playwright aislado, o jarra HTTP limitada a TryHackMe en la ruta moderna bajo Seatbelt y siempre en la ruta HTTP heredada → `/api/v2/users/self`.

### Validación en vivo de URL de salas

`fValidateCatalogueUrls` → `AdaptiveRateLimiter.mWait` → `TryHackMeBrowserClient.mQuickGet` → recuento de éxitos y esperas → adjuntar `validation` → `fSaveCache` cada diez salas → guardado atómico final.

### Verificación de detalle de módulos

`fFetchModuleDetails` → `AdaptiveRateLimiter.mWait` → `mFetchModuleData` → `fNormaliseModuleDetail` → `fApplyModuleDetail` (los fallos transitorios conservan el estado verificado anterior) → `fSaveModuleCache` cada diez módulos → guardado atómico final.

### Recomendación para una oferta

El modelo extrae requisitos atómicos → llama a `search_rooms.fMain` con consultas repetidas → `fLoadCache` → `fPrepareDocuments` → `fDocumentFrequencies` → `fRankRooms` → las mismas consultas llegan a `search_modules.fMain` → `fPrepareModuleDocuments` → `fRankModules` → revisión semántica del modelo → recomendación de salas agrupada seguida del consejo de módulos con enlaces oficiales, niveles y duraciones.

### Informe persistente

El modelo traduce la oferta completa → crea el JSON temporal revisado del informe → en modo incluido, `verify_recommendations.fMain` → `fExtractRecommendationUrls` → `fCheckUrl` secuencial con una segunda comprobación cuando haga falta → el modelo elimina el contenido cuya indisponibilidad queda confirmada, aplica la regla de validación guardada a los fallos no concluyentes y actualiza solapamientos y carencias → `render_report.fMain` → `fLoadReport` → validación de esquema y de URL canónicas de salas y módulos → `fBuildHtml` → tablas de salas, después `fRenderModuleTable` por cada sección de módulos, después las carencias → escribe `rooms-to-satisfy-offer.html` en la carpeta de invocación original → elimina el JSON temporal → enlaza el informe e indica el modo de catálogo en la respuesta de consola.

## Mapa de comandos

| Comando | Manejador | Archivo |
|---|---|---|
| `./os-debian/manage_rooms.py` | `fMain` | `os-debian/manage_rooms.py:654` |
| `./os-debian/manage_rooms.py --headed` | `fMain` con Playwright visible | `os-debian/manage_rooms.py:654` |
| `./os-debian/manage_modules.py` | `fMain` | `os-debian/manage_modules.py:545` |
| `./os-debian/manage_modules.py --skip-module-details` | `fMain` sin `fFetchModuleDetails` | `os-debian/manage_modules.py:545` |
| `./os-debian/search_rooms.py --query …` | `fMain` → `fRankRooms` | `os-debian/search_rooms.py:295` |
| `./os-debian/search_modules.py --query …` | `fMain` → `fRankModules` | `os-debian/search_modules.py:171` |
| `python3 scripts/verify_recommendations.py --input …` | `fMain` → `fCheckUrl` | `scripts/verify_recommendations.py:273` |
| `./os-debian/render_report.py --input … --output-directory …` | `fMain` → `fBuildHtml` | `os-debian/render_report.py:815` |
| `python .\os-windows\manage_rooms.py` | `fMain` | `os-windows/manage_rooms.py` |
| `python .\os-windows\manage_modules.py` | `fMain` | `os-windows/manage_modules.py` |
| `python .\os-windows\search_rooms.py --query …` | `fMain` → `fRankRooms` | `os-windows/search_rooms.py` |
| `python .\os-windows\search_modules.py --query …` | `fMain` → `fRankModules` | `os-windows/search_modules.py` |
| `python .\os-windows\render_report.py --input … --output-directory …` | `fMain` → `fBuildHtml` | `os-windows/render_report.py` |
| `./os-mac/modern/manage_rooms.py` | `fMain` | `os-mac/modern/manage_rooms.py` |
| `./os-mac/modern/manage_modules.py` | `fMain` | `os-mac/modern/manage_modules.py` |
| `./os-mac/modern/search_rooms.py --query …` | `fMain` → `fRankRooms` | `os-mac/modern/search_rooms.py` |
| `./os-mac/modern/search_modules.py --query …` | `fMain` → `fRankModules` | `os-mac/modern/search_modules.py` |
| `./os-mac/modern/render_report.py --input … --output-directory …` | `fMain` → `fBuildHtml` | `os-mac/modern/render_report.py` |
| `./os-mac/legacy-http/manage_rooms.py` | `fMain` | `os-mac/legacy-http/manage_rooms.py` |
| `./os-mac/legacy-http/manage_modules.py` | `fMain` | `os-mac/legacy-http/manage_modules.py` |
| `./os-mac/legacy-http/search_rooms.py --query …` | `fMain` → `fRankRooms` | `os-mac/legacy-http/search_rooms.py` |
| `./os-mac/legacy-http/search_modules.py --query …` | `fMain` → `fRankModules` | `os-mac/legacy-http/search_modules.py` |
| `./os-mac/legacy-http/render_report.py --input … --output-directory …` | `fMain` → `fBuildHtml` | `os-mac/legacy-http/render_report.py` |

Las rutas GET externas son `/api/v2/users/self`, `/api/v2/hacktivities/extended-search` tanto para `kind=rooms` como para `kind=modules`, `/api/v2/rooms/tasks` para las descripciones oficiales que faltan, `/api/v2/modules/data` para el detalle de módulos y las páginas canónicas `/room/<código>` y `/module/<código>`. No se modifica ningún endpoint.

## Análisis de impacto

| Componente modificado | Efectos directos | Documentación que hay que actualizar |
|---|---|---|
| Rutas de navegador o esquema de base de datos | Descubrimiento de sesión en uno o más navegadores | Secciones de almacenes en `DEBIAN.md` o `WINDOWS.md`, README y MANUAL |
| Descifrado de cookies | Autenticación de Chromium y riesgo con credenciales | Arquitectura, privacidad y dependencias |
| Ruta de la carpeta temporal | Arranque de Chromium con rutas de proyecto profundas | Notas del límite de socket en `DEBIAN.md` y MANUAL |
| Normalización de la API de salas o esquema de caché | Historial de descubrimiento, cada sala guardada y su elegibilidad | Contrato de caché de salas, índice de símbolos y migración |
| Normalización de módulos o análisis del detalle | Nivel, duración, lista de salas y elegibilidad del consejo | Contrato de caché de módulos y reglas de consejo |
| Paginación de módulos o regla de completitud | Cobertura del catálogo y marcado de módulos como no listados | Notas de paginación en `DEBIAN.md`, README y MANUAL |
| Ritmo de peticiones | Duración del catálogo, tiempo de verificación y riesgo de bloqueo | Guía de tiempos y resolución de problemas |
| Algoritmo de ordenación | Recuperación de candidatos, tanto de salas como de módulos | Flujo de recomendación y comportamiento del manual |
| Elección del modo de catálogo o verificador selectivo | Latencia predeterminada, acceso al navegador y tratamiento de enlaces finales | `SKILL.md`, todas las guías de plataforma y variantes de README, MANUAL y CODE |
| JSON del informe o maquetación HTML | Salida persistente, accesibilidad y almacenamiento de la oferta | Contrato del informe y todas las variantes de documentación |
| Claves de i18n | Todos los mensajes visibles de comandos e informe | Los cuatro archivos de idioma a la vez |

## Puntos de extensión

### Añadir un sistema operativo

Crea una implementación `os-<plataforma>/` dedicada, añade su guía operativa y actualiza la sección de enrutado de `SKILL.md`. Reutiliza los esquemas públicos de caché y el contrato de recomendación; no pongas lógica de credenciales específica de plataforma en archivos compartidos.

### Añadir un navegador de Windows

Añade sus rutas de perfil a `os-windows/browser_sessions.py`, reutiliza un lector existente sólo cuando coincidan los contratos SQLite y de cifrado, y asígnale una prioridad determinista. Los formatos app-bound deben seguir siendo una condición de parada documentada salvo que el proveedor publique una interfaz de exportación compatible; no añadas inyección, elevación ni extracción de memoria de procesos.

### Añadir un navegador de Debian

Añade sus patrones de perfil a `fDiscoverCookieStores`, implementa un lector sólo si su formato SQLite o de cifrado difiere y asígnale una prioridad determinista. Mantén los errores saneados y nunca incluyas nombres ni valores de cookies en la salida.

### Adaptar un cambio de payload de TryHackMe

Amplía las claves toleradas en `fExtractRoomCode`, `fExtractPremium`, `fNormaliseRoom`, `fExtractModuleCode` o `fNormaliseModuleDetail`. Incrementa `cSchemaVersion` o `cModuleSchemaVersion` sólo cuando cambie el contrato JSON persistido, y añade entonces una migración explícita o fuerza un reemplazo limpio del catálogo.

### Añadir un idioma

Crea un archivo JSON completo bajo `i18n/`, añade el idioma a `cLocales` en `manage_rooms.py` y conserva el orden alfabético de presentación. `en-GB.json` sigue siendo la fuente de verdad de reserva. Las cadenas con recuento vienen en pares de singular y plural; añade los dos.

### Ajustar la recuperación de recomendaciones

Modifica `fTokenise` o `fScoreDocument` manteniendo ambas salidas de búsqueda como candidatos y no como conclusiones. Para los módulos, `fPrepareModuleDocuments` decide qué texto representa a un módulo; cambiar su ponderación cambia la recuperación sin tocar el puntuador compartido. La relevancia semántica, el orden de aprendizaje y las carencias del catálogo siguen siendo decisiones que toma la skill contra el texto completo de la oferta.

### Ampliar el informe HTML

Añade campos revisados opcionales a `fLoadReport`, escápalos en `fBuildHtml` o `fRenderModuleTable` y documenta el cambio de esquema en `DEBIAN.md`. Mantén la oferta al principio, mantén las tablas de módulos después de las de salas, conserva la paridad con la consola, evita recursos externos y preserva los contenedores adaptables de las tablas. Verifica el desbordamiento horizontal a 320, 360, 390, 412 y 430 píxeles en ambos temas después de cualquier cambio de maquetación.
