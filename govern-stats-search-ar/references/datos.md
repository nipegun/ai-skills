# Extraer cifras de los archivos del INDEC

## IPC por región, división y mes

Ejecuta `python3 scripts/cuadros.py ipc --region Nacional --codigo 0 --desde AAAA-MM --hasta AAAA-MM` desde la carpeta de la skill. Con los dos meses iguales, la consulta abarca un mes. Al omitir ambos límites, toma el último mes disponible de la serie solicitada. `--descripcion` admite la etiqueta completa de una división. Para el detalle adicional, usa `--archivo aperturas` y comprueba las regiones disponibles.

Los CSV del IPC usan punto y coma, coma decimal y en los archivos comprobados una codificación de la familia Windows-1252. `Codigo` conserva los ceros iniciales. `Indice_IPC` es el índice con base diciembre de 2016, `v_m_IPC` es la variación mensual y `v_i_a_IPC` es la interanual. `NA` indica que el cálculo correspondiente no aplica. El comando devuelve el archivo oficial, su cobertura, la región, el período y las tres medidas. [Divisiones](https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv) · [Aperturas](https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_aperturas.csv) · [Metadatos](https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_metadatos.txt)

Si te piden una variación acumulada, busca el informe o calcula el cambio a partir de los niveles del mismo índice en los extremos apropiados. Etiqueta el cálculo y cita ambas observaciones.

## Cuadros Excel, informes y microdatos

- Ejecuta `python3 scripts/cuadros.py xlsx URL --hoja 1 --filtrar "TÉRMINOS"` para recuperar celdas del XLSX. `--hoja` admite nombre o posición. El comando devuelve las primeras filas como contexto y las filas filtradas con referencias de celda. Comprueba los encabezados de varios niveles, el universo y las notas. Conserva cada símbolo de la fuente. Las fechas almacenadas como números de Excel conservan ese valor interno.
- Para XLS binario, abre el cuadro con un lector de ese formato o haz una copia XLSX en el directorio temporal. Si el mismo indicador está en CSV, usa el CSV. En los PDF, lee la página y el cuadro en que coincidan el período, la geografía y la unidad.
- Para un indicador EPH, empieza por el informe y el cuadro de tasas. Usa las bases de microdatos y su diseño de registro cuando el usuario necesite un cruce específico y se pueda calcular con el ponderador correcto. Documenta el universo, el trimestre y los filtros. [Mercado de trabajo](https://www.indec.gob.ar/Nivel4/Tema/4/31/58) · [Bases de microdatos](https://www.indec.gob.ar/Institucional/Indec/BasesDeDatos)
