# Inmigración exterior a España y residentes por año de llegada

Usa esta ruta cuando la pregunta relacione un país y un intervalo de años con llegadas a España o con personas que aún residen aquí. La inmigración exterior mide el establecimiento de residencia habitual desde el extranjero. El Censo mide personas que residen en España a la fecha de referencia y registra el año en que comenzó su última estancia en el país. [Metodología de migraciones](https://www.ine.es/metodologia/meto_emcr_2023.pdf#page=6) · [Metodología del Censo](https://www.ine.es/metodologia/t20/meto_censo_poblacion_anual.pdf#page=22)

## Consulta directa

Desde la carpeta de la skill, ejecuta `python3 scripts/inmigracion.py "NOMBRE DEL PAÍS" --years INICIO:FIN --by birth --measure both`. El intervalo incluye ambos extremos y el comando busca el nombre del país en los metadatos. Para gentilicios o abreviaturas, pasa la etiqueta oficial del INE.

- Usa `--by birth` para el país de nacimiento y `--by nationality` para la nacionalidad. Si el usuario pregunta por el país desde el que se trasladaron, busca la dimensión de procedencia con el flujo general.
- Usa `--measure flows` para las llegadas desde el extranjero y `--measure residents` para quienes residían en España a la fecha del Censo según su última llegada. Usa `--measure both` si la pregunta combina estas dos ideas.
- Para un ámbito subnacional, filtros demográficos adicionales o una fecha censal concreta, localiza la tabla apropiada con el flujo general.

## Fechas y cobertura

| Recuento | País de nacimiento | Nacionalidad |
| --- | --- | --- |
| Llegadas anuales hasta 2020 | [Tabla 24289](https://www.ine.es/jaxiT3/Tabla.htm?t=24289) | [Tabla 24287](https://www.ine.es/jaxiT3/Tabla.htm?t=24287) |
| Llegadas anuales desde 2021 | [Tabla 69694](https://www.ine.es/jaxiT3/Tabla.htm?t=69694) | [Tabla 69693](https://www.ine.es/jaxiT3/Tabla.htm?t=69693) |
| Primeros recuentos trimestrales desde 2023 | [Tabla 59012](https://www.ine.es/jaxiT3/Tabla.htm?t=59012) | [Tabla 59011](https://www.ine.es/jaxiT3/Tabla.htm?t=59011) |
| Residentes por año de última llegada | [Tabla 70341](https://www.ine.es/jaxiT3/Tabla.htm?t=70341) | [Tabla 70340](https://www.ine.es/jaxiT3/Tabla.htm?t=70340) |

El comando consulta las tablas anuales pertinentes en paralelo. Para los años que carecen de un dato definitivo, busca las primeras estimaciones trimestrales de la ECP cuando hay cobertura. Cada observación corresponde al trimestre previo a su fecha de referencia. Por ejemplo, el dato fechado el 1 de enero corresponde al cuarto trimestre del año anterior. Verifica los trimestres efectivamente disponibles. [Resultados de la ECP](https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177095&idp=1254735572981&menu=resultados)

En `flows`, `definitive_total` suma los años con cifras definitivas. Describe ese intervalo y revisa `missing_definitive_years`. En `first_estimates`, `partial_sum` suma únicamente los trimestres disponibles de cada año. Presenta estos resultados como recuentos parciales y redondeados de la ECP. Un mismo migrante puede figurar en más de una llegada a lo largo del intervalo. [Metodología de la ECP, pág. 5](https://www.ine.es/inebaseDYN/ecp30282/docs/meto_ECP.pdf#page=5)

En `residents`, `reference_date` es la fecha del Censo y `cohorts` contiene los años o grupos de años de última llegada. El total usa las categorías completas contenidas en el intervalo. Revisa `uncovered_arrival_years` y expresa el alcance real. Un año sin desglose o posterior al corte del Censo queda sin cifra.

Cita `source` para cada dato. Si falta cobertura, confirma la etiqueta del país y busca en el resto de INEbase el mismo criterio y período. Las tablas detallan algunos países por separado y agrupan otros. [Guía del portal](portal.md) · [Calendario del INE](https://www.ine.es/dynt3/Calendario/calenHTML.htm)
