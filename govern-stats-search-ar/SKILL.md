---
name: govern-stats-search-ar
description: >
  Busca, consulta y verifica estadísticas, series, cuadros, informes,
  metodologías y fechas de publicación del INDEC de Argentina. Úsala para
  responder preguntas con datos del INDEC y citar el período, la cobertura y
  la fuente oficial.
---

# Consultar el INDEC de Argentina

1. Identifica el indicador, el período de referencia, el ámbito geográfico y la población o categoría pedida. Usa la serie y la unidad que correspondan a la pregunta. Si el contexto permite interpretar un término ambiguo, indica el criterio. Pide una aclaración concreta si las interpretaciones plausibles cambian la respuesta y conviene elegir una.
2. Empieza por la ficha temática, el informe o el cuadro oficial. Usa la [guía del portal](references/portal.md) para descubrir fuentes y resolver las fichas que cargan contenido aparte. Una búsqueda con `site:indec.gob.ar` sirve para encontrar enlaces oficiales.
3. Para IPC, series y cuadros descargables, usa la [guía de extracción](references/datos.md). Para consultas al Catálogo API-INDEC o a la API nacional de Series de Tiempo, usa la [guía de las API](references/api.md). Si la consulta requiere un servicio autenticado y falta el token, pide al usuario que lo ingrese mediante el aviso de entrada oculta del comando `api` en su terminal.
4. Para población, país de nacimiento y año de llegada, usa la [guía de población y migraciones](references/poblacion.md). Verifica el universo censal, el año de la última llegada y el alcance de los grupos de años. Para desocupación, empleo, pobreza y canastas, comprueba la cobertura de la encuesta o valorización en su informe.
5. Verifica el valor, la unidad, la base, la geografía, el período y el estado de publicación en la fuente. Distingue proyecciones, datos observados, series desestacionalizadas, estimaciones y revisiones. Representa un valor faltante como tal y conserva la nota o símbolo del cuadro.
6. Responde en el idioma del usuario. Da la cifra y su contexto y enlaza el cuadro, el archivo o el informe primario. Cita «Fuente: INDEC» para cifras producidas por el INDEC. Si otro organismo elaboró un dato publicado en un anuario o catálogo, indica ese organismo. Identifica los cálculos propios y el insumo utilizado.

Si una ruta devuelve un resultado vacío o queda fuera de cobertura, prueba el cuadro o informe de la misma operación. Si sigue faltando información, explica el período y el desglose que pudiste verificar.
