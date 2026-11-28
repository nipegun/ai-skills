# Población residente en España por país

Para el total nacional por país de nacimiento o nacionalidad, usa las cifras de residentes a 1 de enero de cada año e indica esa fecha en la respuesta. Si el usuario da una fuente concreta o pide otra fecha, un territorio subnacional o un grupo de edad, sigue el flujo general.

- Para «personas de [país]», usa `--by both`. Presenta primero el dato de quienes nacieron allí y añade el de quienes tienen esa nacionalidad. El recuento por nacimiento incluye a residentes de todas las nacionalidades.
- Para «nacidas en», usa `--by birth`. Para «con nacionalidad», o cuando el gentilicio se refiera a la nacionalidad, usa `--by nationality` e indica ese criterio.

## Ejecutar la consulta

Ejecuta `python3 scripts/poblacion.py "NOMBRE DEL PAÍS" --year AAAA --by both` desde la carpeta de la skill. Para varios años, usa `--years INICIO:FIN`, con ambos extremos incluidos. Por ejemplo, `python3 scripts/poblacion.py Argentina --years 2020:2026 --by nationality` recupera todo el intervalo en una petición. Cuando se piden ambos recuentos, se realizan en paralelo. Omite las opciones de año para obtener el último dato anual disponible.

Pasa el nombre del país en español. Para gentilicios, abreviaturas o nombres alternativos, usa la etiqueta oficial del INE, por ejemplo «Estados Unidos de América» para «EE. UU.». El comando compara los nombres completos ignorando tildes y mayúsculas y devuelve las etiquetas disponibles cuando no encuentra el país. Usa esa lista para reconocer variantes del mismo país. Si la expresión se refiere a más de un país, confirma cuál necesita el usuario.

El comando usa el Censo Anual de Población para años desde 2021. Si el intervalo empieza antes de 2021, consulta la serie definitiva de la Estadística Continua de Población para todo el período y toma solo las observaciones de 1 de enero. Ambas consultas seleccionan el total nacional de residentes de ambos sexos y todas las edades. [Censo por nacimiento](https://www.ine.es/jaxiT3/Tabla.htm?t=68528) · [Censo por nacionalidad](https://www.ine.es/jaxiT3/Tabla.htm?t=68527) · [ECP por nacimiento](https://www.ine.es/jaxiT3/Tabla.htm?t=56937) · [ECP por nacionalidad](https://www.ine.es/jaxiT3/Tabla.htm?t=56936)

Lee `observations` en orden cronológico. En un intervalo, usa `annual_changes` para mostrar la diferencia en personas y el porcentaje respecto al año anterior. El cálculo requiere dos años consecutivos con cifras disponibles. Comprueba `missing_years`, los valores vacíos, la fecha y el estado de publicación. Cita el enlace `source` de cada serie.

Si falta un dato, conserva las cifras disponibles y busca las restantes en el flujo general para el mismo país, período y criterio. Si un país falta en la tabla histórica, consulta el tramo desde 2021 con el Censo Anual. El INE publica algunos países dentro de agrupaciones geográficas. Da una cifra individual solo cuando aparezca el país desglosado. [Guía de la API](api.md) · [Guía del portal](portal.md)
