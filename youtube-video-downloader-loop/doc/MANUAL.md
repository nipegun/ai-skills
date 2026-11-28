# youtube-video-downloader-loop — User manual

This MANUAL is also available in:\
[en-GB](MANUAL.en-GB.md), en-US, [es-AR](MANUAL.es-AR.md), [es-ES](MANUAL.es-ES.md)

## Requirements

Use Python 3.13 or newer, NumPy, SciPy, FFmpeg 7.1 or newer with libmp3lame, FFprobe, yt-dlp with its default dependencies, and Deno. The project looks for these executables in `_/temp/bin/` and then on `PATH`. Lossless encoding uses libx264 or libaom depending on the pixel format.

Install Deno 2.3 or newer with the package for your operating system. The official yt-dlp executable includes the JavaScript components it needs for YouTube. [Deno](https://docs.deno.com/runtime/getting_started/installation/) · [yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/EJS)

From the project directory, place the official Unix executable in the project with these commands. Repeat them when you need a newer yt-dlp release.

```bash
mkdir -p _/temp/bin
curl -fL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o _/temp/bin/yt-dlp
chmod 755 _/temp/bin/yt-dlp
```

## Run the skill

Give Codex the path to the skill and the YouTube URL, or run the script from the project directory.

```bash
python3 scripts/youtube-video-downloader-loop.py 'YOUTUBE_URL'
python3 scripts/youtube-video-downloader-loop.py 'https://www.youtube.com/@HANDLE/videos'
```

A channel URL includes the uploads YouTube lists, including Shorts and archived streams. A URL with `/videos`, `/shorts`, or `/streams` selects that tab. An uploads playlist `playlist?list=UU…` also works. The skill processes each video ID once, skips active or pending streams, and continues when an individual video fails.

Each download creates a new folder under `downloads/` named after the video ID. The name base is `Channel - yYYYYmMMdDD - Title`, using YouTube's date. The download ends in ` (original).mkv`, the audio in ` (audio).mp3`, and the loop in ` (loop).mp4`. If the destination rejects colons, the skill replaces them with commas. Use `--output-dir` for the destination and `--work-dir` for temporary media on a different drive.

The skill exports the full audio track as a constant 192 kb/s MP3 before looking for a loop. It creates an MP3 when the video has an audio track.

Use `--reuse-original` with the same URL and `--output-dir` to process the saved download again. The loop inherits the name base of the download. If a loop already exists, the next one ends in ` (loop 2).mp4`. A legacy download named `original.mkv` uses the video ID as its name base. The skill keeps an existing MP3 when it verifies a constant 192 kb/s bitrate. With a channel URL, this option looks up the saved original for each video and reports any missing copies.

Every loop has a single video stream and keeps the source resolution and pixel format. The script copies the source stream when the exact cut allows it and uses lossless encoding when required.

Use `--min-seconds` to change the minimum duration from 0.25 seconds or `--tolerance` to adjust how closely the frames must match. The default tolerance is 2.5 on a 0–255 RGB difference scale.

## Read the result

The JSON result reports zero-based frame numbers. `start_frame` is included and `last_frame` is the frame immediately before `matched_frame`. The times are measured from the first video frame. `repeated_sequence_frames` gives the number of consecutive matching thumbnails when a full sequence was detected.

`render_mode` reports direct stream copy (`stream_copy`) or lossless encoding (`lossless_encode`).

The `audio` field gives the MP3 path. Its value is `null` if the video has no audio track.

For a single video, code 3 indicates `no_match` and code 1 indicates a processing error. Enable repeat in your player to check the transition.

A channel run returns a `results` list with the status and paths for each video. It returns code 0 when it completes and code 1 if an individual video fails. Videos with `no_match` keep their downloaded and exported files.
