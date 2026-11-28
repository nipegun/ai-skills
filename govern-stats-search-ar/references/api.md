# APIs para estadísticas de Argentina

## Catálogo API-INDEC

La ficha de cada servicio ofrece su descripción y sus columnas. El catálogo público devuelve JSON en `/api/datasets?page=1`. Usa `python3 scripts/indec.py catalogo --pagina 1 --filtrar "población"` y consulta `total_pages` si necesitas buscar en más páginas. El filtrado del comando se aplica a la página recibida. Usa `esquema SERVICIO` con el `slug` del catálogo para obtener el contrato OpenAPI, los parámetros y la clave de ordenación. [Catálogo API-INDEC](https://api.indec.gob.ar/datasets) · [Documentación](https://api.indec.gob.ar/docs)

Los datos de `https://api.indec.gob.ar/v1/` requieren el token que el titular obtiene en el portal del INDEC. Ejecuta `python3 scripts/indec.py api SERVICIO --param periodo=eq.AAAAMM --param limit=20` desde la carpeta de la skill. El comando lee `INDEC_API_TOKEN` si está disponible. Si falta y la entrada es una terminal interactiva, solicita el token con entrada oculta. El valor se usa en la cabecera Bearer de la petición al INDEC. Comprueba en `esquema` el nombre y la capitalización de las columnas y el formato del período. [Preguntas frecuentes](https://api.indec.gob.ar/ayuda/faq)

Cuando una consulta requiera este servicio y falte la credencial, pide al usuario que ejecute el comando e ingrese su token en el aviso oculto de su terminal. En un entorno automatizado, usa la variable de entorno configurada por el usuario.

La API documenta filtros como `eq.`, `gte.`, `lte.` e `ilike.`, y parámetros `select`, `order`, `limit` y `offset`. Repite `--param` para filtros distintos sobre una columna. Para paginar, aplica el orden de la clave completa que documenta el servicio. El límite por consulta es 1.000 filas. Usa `--contar` para solicitar `Content-Range` con el total.

Durante la revisión fueron accesibles los metadatos y el esquema. Una consulta de datos del IPC sin credencial devolvió HTTP 401. Si el usuario omite la entrada del token o prefiere la vía pública, usa los informes y las descargas de la misma operación. [OpenAPI](https://api.indec.gob.ar/api/openapi?v=2) · [Guía de extracción](datos.md)

## API nacional de Series de Tiempo

`series-buscar` y `series` usan `requests` cuando está disponible y la biblioteca estándar como alternativa. En la revisión, el servidor de Series de Tiempo aceptó las peticiones hechas con `requests` y devolvió HTTP 403 con el cliente estándar. El portal, el Catálogo API-INDEC y los archivos públicos se consultan con la biblioteca estándar.

`python3 scripts/indec.py series-buscar "TÉRMINOS"` usa `/series/api/search/`. Cada hallazgo ofrece `field.id`, descripción, unidades, fechas de cobertura y un `dataset` con título y fuente. `--desplazamiento` y `--limite` controlan la página. La búsqueda puede mostrar primero series discontinuadas y datos elaborados por organismos distintos del INDEC.

Consulta los IDs escogidos con `python3 scripts/indec.py series ID --desde AAAA-MM-DD --hasta AAAA-MM-DD`. El comando pide `metadata=full`. Comprueba `meta[].dataset.source`, `meta[].field.time_index_end`, la frecuencia y los valores en `data`. Una respuesta HTTP 200 con `data: []` puede indicar que el intervalo solicitado queda fuera de la cobertura. [Documentación oficial](https://datosgobar.github.io/series-tiempo-ar-api/reference/api-reference/)

Verifica los datos recientes contra la publicación original del INDEC. Si el nombre de la serie parece adecuado pero la cobertura está atrasada o describe otra región o base, usa el archivo publicado en la ficha temática. [API Series de Tiempo](https://www.argentina.gob.ar/datos-abiertos/api-series-de-tiempo)
