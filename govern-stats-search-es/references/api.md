# API pública de INEbase

## Acceso y descubrimiento

La base JSON en español es `https://servicios.ine.es/wstempus/js/ES/`. Desde la carpeta de la skill, `python3 scripts/ine_api.py RECURSO [identificadores] --param nombre=valor` hace una consulta GET. Usa Python 3.13 o posterior y su biblioteca estándar. Puedes repetir `--param` para conservar varios `tv`. La salida contiene `url` y `response`, y para listas añade los recuentos `received`, `matched` y el indicador `truncated`. `--find` busca todos los términos de una frase en el nombre o los códigos de cada elemento, con comparación sin distinción de tildes ni mayúsculas. `--limit` recorta la salida local después de filtrar. También puedes invocar las rutas con una herramienta HTTP que conserve los parámetros repetidos.

```bash
python3 scripts/ine_api.py OPERACIONES_DISPONIBLES --find "precios consumo"
python3 scripts/ine_api.py TABLAS_OPERACION IPC --find "índices nacionales ecoicop"
```

Una operación puede tener código interno numérico, abreviatura y código de inventario. El IPC admite `25`, `IPC` e `IOE30138`. Estos códigos identifican la operación. El ID de tabla y el código de serie se obtienen de la tabla elegida. `TABLAS_OPERACION` ofrece fechas y periodicidad cuando están disponibles. Para resolver una periodicidad dudosa, consulta `PERIODICIDADES` y comprueba los períodos reales de la tabla. Las fichas de INEbase aportan tablas y documentos que pueden quedar fuera del catálogo operativo de la API. [Referencia de la API](https://www.ine.es/dyngs/DAB/index.htm?cid=1100) · [INEbase](https://www.ine.es/dyngs/INEbase/listaoperaciones.htm)

Cuando consultes un recurso paginado, comprueba si cada página aporta identificadores nuevos y si tienes cobertura suficiente. La longitud de página observada en `SERIES_OPERACION` puede diferir de la documentada. En el IPC, `SERIES_TABLA` devolvió la misma lista al variar `page`.

## Obtener la tabla y sus dimensiones

| Enlace de origen | Identificador para `DATOS_TABLA` | Metadatos para filtrar |
| --- | --- | --- |
| `/jaxiT3/Tabla.htm?t=76125` | `76125` | En Tempus3, usa `GRUPOS_TABLA/{tabla}` y después `VALORES_GRUPOSTABLA/{tabla}/{grupo}`. |
| `/jaxi/Tabla.htm?tpx=33387` | `33387` | En TPX, usa `SERIES_TABLA/{tabla}?tip=M` para obtener los códigos. |
| `/jaxi/Tabla.htm?path=/t20/e245/p08/l0/&file=01001.px` | `t20/e245/p08/l0/01001.px` | En PC-Axis, usa `SERIES_TABLA/{ruta}?tip=M`. |

En **Tempus3**, toma ambos números de la misma fila devuelta por `VALORES_GRUPOSTABLA`. Construye `tv=FK_Variable:Id` con `det=0` o `tv=Variable.Id:Id` con `det=1`. Usa el ID de grupo para pedir esa lista de valores. El valor seleccionado puede tener además un `Codigo` oficial, como `15030` para el municipio de A Coruña. Ese código ayuda a identificar el territorio y el filtro numérico usa el `Id` de la fila.

```bash
python3 scripts/ine_api.py GRUPOS_TABLA 76125
python3 scripts/ine_api.py VALORES_GRUPOSTABLA 76125 155578 --param det=1 --find "variación anual"
python3 scripts/ine_api.py DATOS_TABLA 76125 \
  --param tv=762:304092 --param tv=3:74 \
  --param date=20261001:20261031 --param tip=AM
```

El ejemplo consulta la variación interanual del IPC general nacional en octubre de 2026. Los identificadores de otra tabla se obtienen de sus metadatos. Si ya tienes un código de serie Tempus3, puedes consultar `DATOS_SERIE` con el período y el tipo de salida adecuados. [Tabla del ejemplo](https://www.ine.es/jaxiT3/Tabla.htm?t=76125) · [Códigos de tablas y series](https://www.ine.es/dyngs/DAB/index.htm?cid=1104)

En **TPX y PC-Axis**, construye `tv=codigo_variable:codigo_valor`. Hay TPX híbridos que también admiten `tv=variable~id:valor~id` con los identificadores numéricos documentados. Obtén la unidad y las notas de la página de la tabla si faltan en el JSON.

```bash
python3 scripts/ine_api.py SERIES_TABLA 33387 --param tip=M --find "extraccion nacional"
python3 scripts/ine_api.py DATOS_TABLA 33387 \
  --param tv=tipodematerial:extraccionnacional --param nult=2 --param tip=AM
python3 scripts/ine_api.py DATOS_TABLA t20/e245/p08/l0/01001.px \
  --param tv=sexo:mujeres --param tv=espanolesextranjeros:espanoles \
  --param tv=edad3gruposdeedad:totaledades --param nult=2
```

En el caso de extracción, la respuesta incluye etiquetas como `2025 (avance)` y `2024`. El ejemplo PC-Axis permite seleccionar 2022 a partir de `NombrePeriodo`. Para otra fecha, comprueba la cobertura y usa un intervalo de datos que la incluya o la descarga completa. [Guía oficial de filtros](https://www.ine.es/dyngs/DAB/es/index.htm?cid=1102)

## Períodos, resultados y errores

- En Tempus3, usa `date=AAAAMMDD:AAAAMMDD` para un rango o `nult=N` para los últimos períodos. Usa un solo parámetro temporal. Para el cuarto trimestre de 2025, el rango es `20251001:20251231`. Comprueba el año y el código del período además de la fecha. El formato básico puede devolver milisegundos y la salida amigable incluye fechas con zona horaria.
- `tip=AM` facilita la comprobación de nombres y metadatos. Según `tip` y `det`, el período, la unidad, la escala y el estado pueden aparecer como IDs, etiquetas u objetos. Ordena por el período comprobado cuando calcules cambios o selecciones el último dato disponible.
- Revisa `Data` de cada serie. `[]`, una serie con `Data: []` y una observación con `Valor: null` aportan información distinta. Conserva las marcas de secreto y supresión de la fuente. Un cuerpo vacío, HTML, una respuesta demasiado grande o un error HTTP requieren revisar la consulta o usar otra vía de acceso oficial.
- Para descargar muchos datos, usa los filtros de la API o el archivo de la tabla. El límite de tamaño del comando se aplica a la respuesta completa. `--limit` recorta la lista tras la descarga.

## Usar el MCP oficial cuando esté disponible

Consulta los esquemas de las herramientas conectadas. En la versión revisada, el servidor exige seguir `ine_select_operation` → `ine_select_multiple_tables` → `ine_select_multiple_table_groups` → `ine_select_multiple_values` → `ine_select_multiple_table_data`. Pide los valores con `det=0` para obtener `FK_Variable` e `Id`, y usa el objeto `source` para citar la operación, la tabla y los filtros. Comprueba las listas `Data` aunque `total_observations` sea positivo. Para fuentes sin cobertura en el MCP, consulta la API o el producto oficial del portal. [Servidor MCP oficial del INE](https://github.com/es-ine/mcp)
