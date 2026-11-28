# youtube-video-downloader-loop — Referencia de código

This CODE is also available in:\
[en-GB](CODE.en-GB.md), [en-US](CODE.md), [es-AR](CODE.es-AR.md), es-ES

- [Arquitectura](#arquitectura)
- [Mapa de módulos](#mapa-de-módulos)
- [Símbolos clave](#símbolos-clave)
- [Flujos principales](#flujos-principales)
- [Entrada de la CLI](#entrada-de-la-cli)
- [Análisis de impacto](#análisis-de-impacto)
- [Puntos de extensión](#puntos-de-extensión)

## Arquitectura

Los enlaces individuales y los listados de un canal comparten el mismo procesamiento por vídeo. Al tratar cada vídeo por separado, la CLI libera sus archivos temporales antes de empezar el siguiente.

yt-dlp elige flujos por resolución y los empaqueta como Matroska. FFmpeg lee miniaturas RGB en orden de presentación. La búsqueda usa las huellas de fotogramas contiguos para proponer periodos y confirmar que una secuencia completa se repite. Si hace falta, compara candidatos por similitud de imagen y por el movimiento cerca de la unión. La exportación usa las marcas de tiempo de origen para conservar la duración del último fotograma visible. Copia los paquetes de vídeo cuando el intervalo exacto se puede extraer entre fotogramas clave. Si hace falta recodificar, usa un codificador sin pérdida con el formato de píxel de origen. La pista de audio completa se codifica por separado en MP3 a 192 kb/s constantes.

## Mapa de módulos

| Módulo | Ruta | Responsabilidad | Depende de | Usado por |
| --- | --- | --- | --- | --- |
| Python CLI | [scripts/youtube-video-downloader-loop.py](../scripts/youtube-video-downloader-loop.py) | Descargar el original, exportar el audio y generar el bucle | yt-dlp, FFmpeg, FFprobe, NumPy, SciPy | La skill y usuarios de la CLI |

## Símbolos clave

| Símbolo | Archivo | Propósito |
| --- | --- | --- |
| `fChannelUrl` | [script:82](../scripts/youtube-video-downloader-loop.py#L82) | Identifica una URL de canal, pestaña o lista de subidas. |
| `fChannelVideos` | [script:117](../scripts/youtube-video-downloader-loop.py#L117) | Enumera los identificadores únicos de los vídeos listados. |
| `fDownload` | [script:158](../scripts/youtube-video-downloader-loop.py#L158) | Descarga la mayor resolución disponible y lee los metadatos de YouTube. |
| `fMediaStem` | [script:147](../scripts/youtube-video-downloader-loop.py#L147) | Combina el canal, la fecha de YouTube y el título. |
| `fMediaPath` | [script:190](../scripts/youtube-video-downloader-loop.py#L190) | Ajusta el nombre y el sufijo al sistema de archivos de destino. |
| `fSavedOriginal` | [script:201](../scripts/youtube-video-downloader-loop.py#L201) | Encuentra la descarga guardada en la carpeta del vídeo. |
| `fExportAudio` | [script:279](../scripts/youtube-video-downloader-loop.py#L279) | Exporta y verifica el MP3 completo a 192 kb/s constantes. |
| `fReadFrames` | [script:327](../scripts/youtube-video-downloader-loop.py#L327) | Lee una miniatura y la marca de tiempo exacta de cada fotograma. |
| `fPublishMedia` | [script:232](../scripts/youtube-video-downloader-loop.py#L232) | Publica el archivo y sustituye los dos puntos si el destino los rechaza. |
| `fFindExactRepeat` | [script:450](../scripts/youtube-video-downloader-loop.py#L450) | Confirma un periodo a partir de una secuencia de miniaturas repetida. |
| `fFindLoop` | [script:486](../scripts/youtube-video-downloader-loop.py#L486) | Busca fotogramas coincidentes y compara el movimiento cercano. |
| `fCopyLoop` | [script:599](../scripts/youtube-video-downloader-loop.py#L599) | Comprueba los límites y verifica los paquetes y las marcas de tiempo de la copia. |
| `fRenderLoop` | [script:636](../scripts/youtube-video-downloader-loop.py#L636) | Exporta vídeo sin audio mediante copia directa o codificación sin pérdida. |
| `fProcessVideo` | [script:671](../scripts/youtube-video-downloader-loop.py#L671) | Ejecuta el flujo completo y devuelve el resultado de un vídeo. |
| `fProcessChannel` | [script:723](../scripts/youtube-video-downloader-loop.py#L723) | Procesa la lista por vídeo y recoge los resultados. |
| `fMain` | [script:747](../scripts/youtube-video-downloader-loop.py#L747) | Ejecuta el flujo y devuelve el resultado como JSON. |

## Flujos principales

1. El comando valida la URL. Para un listado de canal, yt-dlp enumera los vídeos y la CLI procesa los identificadores únicos uno a uno. El nombre base combina el canal, `upload_date` (o `release_date` cuando falta) y el título. Los temporales de cada vídeo se crean bajo `--work-dir`.
2. FFmpeg exporta la pista de audio completa con libmp3lame. FFprobe comprueba el bitrate y el tamaño de las tramas antes de publicar el MP3.
3. El análisis confirma una repetición completa cuando está disponible y pasa un inicio incluido y un final excluido al exportador.
4. El exportador confirma que el MP4 tiene una sola pista de vídeo y conserva el número de fotogramas, las dimensiones, el formato de píxel y la duración esperados. Después lo guarda junto al original.

## Entrada de la CLI

| Comando | Función | Archivo |
| --- | --- | --- |
| `python3 scripts/youtube-video-downloader-loop.py URL` | `fMain` | [scripts/youtube-video-downloader-loop.py](../scripts/youtube-video-downloader-loop.py) |

## Análisis de impacto

La numeración de fotogramas afecta al resultado del análisis y al recorte de FFmpeg. Mantén `last_frame = matched_frame - 1` y calcula la duración con las marcas de tiempo de ambos límites. La selección del formato afecta a la resolución descargada y exportada.

## Puntos de extensión

Ajusta la detección visual en `fFindLoop` y `fAssessPair`. Aplica cambios de códec en `fRenderLoop` y conserva la comprobación de pista única, fotogramas, formato de píxel y duración.
