# Navegación y fuentes del INDEC

## Encontrar la ficha de una operación

- La portada muestra indicadores recientes, noticias y el calendario. En caso de que la URL principal devuelva solo el menú, abre el contenido de portada directamente. El dato destacado suele enlazar al informe o a la ficha con el período de referencia y su unidad. [Portada](https://www.indec.gob.ar/indec/Portada) · [Mapa de rutas](https://www.indec.gob.ar/sitemap.xml)
- El menú organiza las estadísticas por Población, Sociedad, Economía y Geoestadística. En el HTML, los enlaces de navegación pueden usar `data-view`. Abre la ruta a la que apunta ese atributo. La ficha reúne informes técnicos, cuadros y metadatos, según el indicador.
- El buscador interno admite términos, categorías, temas y ordenación por relevancia o fecha. Carga los resultados en un segundo paso. En esta revisión hubo solicitudes que devolvieron solo la navegación con HTTP 200, esperas agotadas y una página de bloqueo en Chromium. Usa búsqueda por dominio y confirma el resultado en la ficha, informe o descarga oficial. [Buscador del INDEC](https://www.indec.gob.ar/indec/web/Buscador-Buscador-1-2024-Todo-Todo-Relevantes)

## Cargar fichas y seguir sus archivos

La ruta visible `/indec/web/Nivel4-Tema-3-5-31` corresponde al contenido en `/Nivel4/Tema/3/5/31`. El comando `python3 scripts/indec.py tema 3/5/31` acepta el identificador o la URL. Para secciones institucionales se aplica el mismo esquema, por ejemplo `/indec/web/Institucional-Indec-BasesDeDatos` y `/Institucional/Indec/BasesDeDatos`. En los fragmentos, las rutas relativas que comienzan en `ftp/` o `uploads/` resuelven normalmente desde la raíz del sitio. [Ficha del IPC](https://www.indec.gob.ar/Nivel4/Tema/3/5/31) · [Bases de datos](https://www.indec.gob.ar/Institucional/Indec/BasesDeDatos)

Usa `--filtrar` por texto o extensión para localizar cuadros, informes y metadatos. El texto inicial y los enlaces son ayuda de navegación. Abre el recurso seleccionado para comprobar títulos, unidades y notas. Los informes tienen URL propia bajo `/uploads/informesdeprensa/` y sus nombres suelen incluir la edición y un sufijo. Obtén el enlace de la ficha vigente o de la lista de informes anteriores.

| Tema | Ficha y comprobaciones |
| --- | --- |
| IPC | Distingue índice base diciembre de 2016, variación mensual, interanual y acumulada. Comprueba nivel general, región y división. La serie nacional difiere de series históricas del IPC-GBA. [IPC](https://www.indec.gob.ar/Nivel4/Tema/3/5/31) |
| Mercado de trabajo | La EPH continua difunde tasas de los 31 aglomerados urbanos. La EPH total urbano tiene una cobertura más amplia y su propio período. Lee la tasa de desocupación como porcentaje de la población económicamente activa. [Mercado de trabajo](https://www.indec.gob.ar/Nivel4/Tema/4/31/58) |
| Actividad y cuentas nacionales | Verifica si piden EMAE mensual o PIB trimestral, precios corrientes o constantes, serie original, desestacionalizada o tendencia-ciclo. [Cuentas nacionales](https://www.indec.gob.ar/Nivel3/Tema/3/9) |
| Comercio exterior | Usa los informes y sus cuadros para exportaciones, importaciones y saldo. Revisa fecha, unidades, revisión y nivel de apertura. El ICA digital también ofrece bases mensuales. [ICA](https://www.indec.gob.ar/Nivel4/Tema/3/2/40) |
| Población y censos | Para proyecciones identifica su base y el 1 de julio del año. Para datos censales sigue la [guía de población](poblacion.md). [Proyecciones](https://www.indec.gob.ar/Nivel3/Tema/2/24) · [Censo 2022](https://www.indec.gob.ar/Nivel4/Tema/2/41/165) |

## Publicaciones relacionadas

- El calendario contiene la fecha de difusión y enlaza los calendarios semestrales en PDF. Comprueba por separado el período de referencia del próximo informe. [Calendario](https://www.indec.gob.ar/Calendario/Fecha/0)
- Las fichas de operaciones estadísticas y las metodologías describen cobertura, periodicidad y población analizada. En el archivo histórico revisa la advertencia del organismo sobre las series difundidas en 2007–2015 y las revisiones identificadas. [Operaciones estadísticas](https://www.indec.gob.ar/Institucional/Indec/OperacionesEstadisticas/1) · [Información de archivo](https://www.indec.gob.ar/Institucional/Indec/InformacionDeArchivo/2)
- Las bases de microdatos EPH ofrecen archivos ZIP y diseños de registro. Para cálculos a medida, verifica la base de personas u hogares, el trimestre, el ponderador y el dominio de estimación. Para una tasa ya publicada, usa el cuadro oficial. [Bases](https://www.indec.gob.ar/Institucional/Indec/BasesDeDatos)
- El [Anuario](https://anuario.indec.gob.ar/) reúne cuadros de distintos organismos. Lee la fuente al pie de cada cuadro. Para mapas y datos espaciales, consulta el [Geoportal temático](https://www.indec.gob.ar/Nivel3/Tema/1/16) y verifica la unidad geográfica. La [cartelera SDDS](https://sdds.indec.gob.ar/nsdp.htm) enlaza series y metodologías de distintos productores.
