---
name: govern-stats-search-es
description: >
  Busca, consulta y verifica estadísticas oficiales del Instituto Nacional de
  Estadística de España en ine.es e INEbase. Úsala para responder preguntas
  sobre cifras, series, tablas, notas de prensa, metodología o fechas de
  publicación del INE, con el período y el enlace oficial correspondientes.
---

# Consultar el INE de España

Para el total de residentes en España a 1 de enero por país de nacimiento o de nacionalidad, empieza por la [consulta directa de población por país](references/poblacion.md). El comando resuelve el país a partir de los datos del INE. Para varios años, consulta el intervalo completo y usa las variaciones anuales que devuelve. Usa el flujo general si la petición tiene otra fecha de referencia o la ruta directa carece de cobertura.

Para llegadas desde el extranjero que establecieron residencia en España o para residentes según el año de su última llegada, usa la [consulta de inmigración y año de llegada](references/inmigracion.md). Elige país de nacimiento o nacionalidad según la pregunta y comprueba el período disponible de cada cifra.

## Flujo general

1. Identifica el indicador exacto, el territorio y su nivel, el período de referencia, la población estudiada y los demás filtros que importan. Usa los nombres de operaciones y variables del INE para buscar. Si el contexto permite elegir una interpretación, indica cuál has usado. Si quedan varias interpretaciones que cambian la respuesta, pide una aclaración concreta.
2. Abre el enlace oficial que proporcione el usuario. Si partes de una pregunta, busca la operación en INEbase o en el catálogo de la API. Revisa período, frecuencia, territorio, unidad, base y clasificaciones al elegir entre tablas de título parecido. La ficha de la operación y el aviso de tabla histórica ayudan a encontrar la edición pertinente. [Catálogo de INEbase](https://www.ine.es/dyngs/INEbase/listaoperaciones.htm)
3. Para cifras y series, sigue [la guía de la API](references/api.md). Usa el MCP oficial si sus herramientas están disponibles y ofrecen los datos de la tabla. La API pública es accesible directamente desde el comando incluido. Para notas de prensa, metodología, calendario, descargas y productos con consulta propia, sigue [la guía del portal](references/portal.md).
4. Comprueba las observaciones de la serie seleccionada. Verifica los filtros devueltos, el período, la unidad, la escala y el estado de publicación. El último período puede ser un avance. Si el usuario pide el último dato definitivo, busca la observación definitiva más reciente. Conserva los ceros y las celdas sin dato según su representación original. Un contador de series puede ser positivo con una lista de observaciones vacía.
5. Responde en el idioma del usuario. Da el dato y la unidad, el territorio, el período exacto y los filtros que cambian el significado. Indica el estado y la fecha de publicación o actualización cuando consten y aporten contexto. Cita la tabla, nota o informe oficial, con el ID de la tabla o el código de serie cuando faciliten la reproducción. Identifica los cálculos propios basados en datos del INE.

Si el primer resultado queda vacío, comprueba la tabla, la versión, los filtros y la cobertura. Usa la descarga oficial o la publicación correspondiente cuando aporten el dato. Si sigues sin poder confirmarlo, indica qué cruce buscaste y si la fuente carece de esa cobertura o hubo un fallo de acceso.

Para una búsqueda externa de enlaces, usa `site:ine.es` y abre la fuente oficial para comprobar cada cifra o afirmación. Usa los catálogos, las fichas y las interfaces públicas de datos para las consultas automatizadas. El archivo de rastreo excluye `/buscar/`. [robots.txt del INE](https://www.ine.es/robots.txt)
