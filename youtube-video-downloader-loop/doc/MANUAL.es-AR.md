# youtube-video-downloader-loop — Manual de uso

This MANUAL is also available in:\
[en-GB](MANUAL.en-GB.md), [en-US](MANUAL.md), es-AR, [es-ES](MANUAL.es-ES.md)

## Requisitos

Usá Python 3.13 o posterior, NumPy, SciPy, FFmpeg 7.1 o posterior con libmp3lame, FFprobe, yt-dlp con sus dependencias por defecto y Deno. El proyecto busca estos ejecutables en `_/temp/bin/` y después en `PATH`. La codificación sin pérdida usa libx264 o libaom según el formato de píxel.

Instalá Deno 2.3 o posterior con el paquete para tu sistema operativo. El ejecutable oficial de yt-dlp incluye los componentes JavaScript que necesita para YouTube. [Deno](https://docs.deno.com/runtime/getting_started/installation/) · [yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/EJS)

Desde la carpeta del proyecto, colocá el ejecutable oficial para Unix con estos comandos. Repetilos cuando necesites una versión más reciente de yt-dlp.

```bash
mkdir -p _/temp/bin
curl -fL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o _/temp/bin/yt-dlp
chmod 755 _/temp/bin/yt-dlp
```

## Ejecutar la skill

Pasale a Codex la ruta de la skill y el enlace de YouTube, o ejecutá el script desde la carpeta del proyecto.

```bash
python3 scripts/youtube-video-downloader-loop.py 'URL_DE_YOUTUBE'
python3 scripts/youtube-video-downloader-loop.py 'https://www.youtube.com/@CANAL/videos'
```

El enlace de un canal incluye las subidas que YouTube enumera, incluidos Shorts y directos archivados. Una URL con `/videos`, `/shorts` o `/streams` selecciona esa pestaña. También se puede usar una lista de subidas `playlist?list=UU…`. La skill procesa cada video una vez, omite los directos activos o pendientes y continúa si falla algún video.

Cada descarga crea una carpeta nueva en `downloads/` con el identificador del video. El nombre base es `Canal - yAAAAmMMdDD - Título`, con la fecha de YouTube. La descarga termina en ` (original).mkv`, el audio en ` (audio).mp3` y el bucle en ` (loop).mp4`. Si el destino rechaza los dos puntos, la skill los sustituye por comas. Usá `--output-dir` para fijar el destino y `--work-dir` para elegir la unidad para los archivos temporales.

La skill exporta la pista de audio completa en MP3 a 192 kb/s constantes, antes de buscar el bucle. El archivo MP3 se genera cuando el video tiene una pista de audio.

Usá `--reuse-original` con la misma URL y el mismo `--output-dir` para analizar de nuevo la descarga guardada. El bucle toma el nombre base de la descarga. Si ya existe un bucle, el siguiente termina en ` (loop 2).mp4`. Las descargas antiguas llamadas `original.mkv` usan el identificador del video como nombre base. La skill aprovecha el MP3 existente cuando verifica que está a 192 kb/s constantes. Con un enlace de canal, esta opción busca una descarga guardada para cada video y registra un fallo por cada copia que falta.

El bucle se exporta siempre sin pista de audio y conserva la resolución y el formato de píxel del original. Siempre que el corte exacto lo permita, se copia el flujo de vídeo. Si hace falta recodificar, se usa codificación sin pérdida.

Con `--min-seconds` podés cambiar la duración mínima de 0,25 segundos y con `--tolerance` podés ajustar la similitud exigida. La tolerancia inicial es de 2,5 en una escala de diferencia RGB de 0 a 255.

## Leer el resultado

El resultado JSON numera los fotogramas desde cero. El clip incluye `start_frame` y acaba en `last_frame`, el fotograma anterior a `matched_frame`. Los tiempos se miden desde el primer fotograma del video. `repeated_sequence_frames` indica cuántas miniaturas consecutivas coincidieron cuando se detectó una secuencia completa.

`render_mode` indica si el clip se generó por copia directa (`stream_copy`) o por codificación sin pérdida (`lossless_encode`).

El campo `audio` indica la ruta del MP3. Su valor es `null` si el video carece de pista de audio.

Con un video individual, el código 3 indica `no_match` y el código 1 indica un fallo de procesamiento. Activá la repetición en el reproductor para comprobar la transición visual.

Un lote de canal devuelve `results` con el estado y las rutas de cada video. Devuelve el código 0 si se completa y el código 1 si algún video falla. Los videos con estado `no_match` conservan sus archivos descargados y exportados.
