---
name: youtube-video-downloader-loop
description: Download a YouTube video or the uploads listed by a YouTube channel at the highest available resolution. Export full 192 kb/s CBR MP3 audio and create a silent MP4 loop when a visual repeat exists. Use for individual video, channel, Videos tab, or channel uploads URLs.
---

# YouTube video downloader loop

Run [the loop script](scripts/youtube-video-downloader-loop.py) with the supplied video, channel, or channel uploads URL. Resolve the script path relative to this file. The default destination is the project's `downloads/` directory. Pass `--output-dir` to choose where to save the results and `--work-dir` to put temporary media on a specified drive.

```bash
python3 scripts/youtube-video-downloader-loop.py 'YOUTUBE_URL'
```

The script needs Python 3.13+, NumPy, SciPy, FFmpeg 7.1+ with libmp3lame, FFprobe, yt-dlp with its default dependencies, and Deno. FFmpeg uses libx264 or libaom if lossless video encoding is needed. It finds yt-dlp and Deno in `_/temp/bin/` or on `PATH`. See [installation and usage](doc/MANUAL.md) if a dependency is missing.

- A channel URL processes all listed uploads, including Shorts and archived streams. A tab URL such as `https://www.youtube.com/@HANDLE/videos` processes that tab. Channel uploads playlist URLs with a `UU…` ID also work. Each listed video ID is processed once. Active and scheduled streams and streams still being processed are skipped.
- Let yt-dlp choose the highest downloadable resolution for each video, including separate video and audio streams. Save it as `Channel - yYYYYmMMdDD - Title (original).mkv` using YouTube metadata. Replace colons with commas if the destination rejects them.
- Export the full audio track as `Channel - yYYYYmMMdDD - Title (audio).mp3` at a constant 192 kb/s before looking for a visual loop. If the source has no audio track, the `audio` field is `null`.
- The search first looks for a full sequence that repeats. This helps distinguish a recurring scene from matching title cards. When needed, it compares individual frames and nearby motion. Report frame numbers as zero-based and give their times from the first source frame.
- Export `Channel - yYYYYmMMdDD - Title (loop).mp4` using the source file's name base. The matching end frame is the exclusive boundary. The last displayed frame is one frame earlier, so the image at the boundary plays once when the loop restarts.
- Compare the two source frames at full resolution before reporting that they match pixel for pixel.
- Export every loop without an audio track. The script verifies a direct packet copy when the exact boundaries allow it. Otherwise it encodes the selected frames losslessly at the source pixel format. Report the export method from `render_mode`.
- Read the JSON result on stdout for the final paths. A channel run continues after individual failures and returns a `results` list with each video's status. With `status: no_match`, give the user the paths to the original and any exported MP3. Use `--reuse-original` with the same URL and `--output-dir` to process saved originals.
