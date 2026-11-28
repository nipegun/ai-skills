# youtube-video-downloader-loop — Code reference

This CODE is also available in:\
en-GB, [en-US](CODE.md), [es-AR](CODE.es-AR.md), [es-ES](CODE.es-ES.md)

- [Architecture](#architecture)
- [Module map](#module-map)
- [Key symbols](#key-symbols)
- [Main flows](#main-flows)
- [CLI entry point](#cli-entry-point)
- [Change impact](#change-impact)
- [Extension points](#extension-points)

## Architecture

Individual links and channel listings share the same per-video workflow. Processing one video at a time lets the CLI release its temporary files before starting the next one.

yt-dlp selects streams by resolution and packages them as Matroska. FFmpeg decodes RGB thumbnails in presentation order. The search uses fingerprints of consecutive frames to propose periods and verify that a full sequence repeats. It can also index tile means and compare the motion near candidate boundaries. The export uses source timestamps to keep the duration of the last displayed frame. It copies the video packets when it can extract the exact range between keyframes. Otherwise it uses a lossless encoder with the source pixel format. The full audio track is encoded separately as a constant 192 kb/s MP3.

## Module map

| Module | Path | Responsibility | Depends on | Used by |
| --- | --- | --- | --- | --- |
| Python CLI | [scripts/youtube-video-downloader-loop.py](../scripts/youtube-video-downloader-loop.py) | Download the original, export its audio, and generate the loop | yt-dlp, FFmpeg, FFprobe, NumPy, SciPy | Skill and CLI users |

## Key symbols

| Symbol | File | Purpose |
| --- | --- | --- |
| `fChannelUrl` | [script:82](../scripts/youtube-video-downloader-loop.py#L82) | Recognise a channel, tab, or uploads playlist URL. |
| `fChannelVideos` | [script:117](../scripts/youtube-video-downloader-loop.py#L117) | Enumerate the unique video IDs in the listing. |
| `fDownload` | [script:158](../scripts/youtube-video-downloader-loop.py#L158) | Download at the highest available resolution and read YouTube metadata. |
| `fMediaStem` | [script:147](../scripts/youtube-video-downloader-loop.py#L147) | Combine the channel, YouTube date, and title. |
| `fMediaPath` | [script:190](../scripts/youtube-video-downloader-loop.py#L190) | Fit the media filename and its suffix to the destination filesystem. |
| `fSavedOriginal` | [script:201](../scripts/youtube-video-downloader-loop.py#L201) | Find the saved download in the video's folder. |
| `fExportAudio` | [script:279](../scripts/youtube-video-downloader-loop.py#L279) | Export and verify the full MP3 at a constant 192 kb/s. |
| `fReadFrames` | [script:327](../scripts/youtube-video-downloader-loop.py#L327) | Decode a thumbnail and exact timestamp for each frame. |
| `fPublishMedia` | [script:232](../scripts/youtube-video-downloader-loop.py#L232) | Save the file and replace colons if the destination rejects them. |
| `fFindExactRepeat` | [script:450](../scripts/youtube-video-downloader-loop.py#L450) | Verify a period using a repeating thumbnail sequence. |
| `fFindLoop` | [script:486](../scripts/youtube-video-downloader-loop.py#L486) | Find matching frames and check the surrounding motion. |
| `fCopyLoop` | [script:599](../scripts/youtube-video-downloader-loop.py#L599) | Check the cut boundaries and verify the copied packet data and timestamps. |
| `fRenderLoop` | [script:636](../scripts/youtube-video-downloader-loop.py#L636) | Export a video-only loop by stream copy or lossless encoding. |
| `fProcessVideo` | [script:671](../scripts/youtube-video-downloader-loop.py#L671) | Run the full workflow and return one video's result. |
| `fProcessChannel` | [script:723](../scripts/youtube-video-downloader-loop.py#L723) | Process the listing one video at a time and collect the results. |
| `fMain` | [script:747](../scripts/youtube-video-downloader-loop.py#L747) | Run the workflow and return the result as JSON. |

## Main flows

1. The command validates the URL. For a channel listing, yt-dlp enumerates the videos and the CLI processes the unique IDs in sequence. The name base combines the channel, `upload_date` (or `release_date` when absent), and title. Each video's temporary media goes under `--work-dir`.
2. FFmpeg exports the full audio track with libmp3lame. FFprobe checks the bitrate and frame sizes before the MP3 is published.
3. The analysis checks for a complete repeat and passes an inclusive start and exclusive end to the renderer.
4. The renderer checks that the MP4 has one video stream and the expected frame count, dimensions, pixel format, and duration. It saves the verified clip next to the original.

## CLI entry point

| Command | Handler | File |
| --- | --- | --- |
| `python3 scripts/youtube-video-downloader-loop.py URL` | `fMain` | [scripts/youtube-video-downloader-loop.py](../scripts/youtube-video-downloader-loop.py) |

## Change impact

Frame numbering affects the analysis result and the FFmpeg trim. Preserve `last_frame = matched_frame - 1` and derive the clip duration from its boundary timestamps. Format selection affects the downloaded and exported resolution.

## Extension points

Adjust visual detection in `fFindLoop` and `fAssessPair`. Apply output codec changes in `fRenderLoop` and keep the video-only, frame, pixel format, and timing checks.
