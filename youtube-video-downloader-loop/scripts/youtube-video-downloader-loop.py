#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""Download YouTube videos and export their audio and frame-accurate visual loops."""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from errno import EACCES, EILSEQ, EINVAL, ENOENT, EOPNOTSUPP, EPERM, EXDEV
from fractions import Fraction
from itertools import count
from pathlib import Path
from typing import NamedTuple
from urllib.parse import parse_qs, urlsplit

import numpy as np
from scipy.spatial import cKDTree


cProject = Path(__file__).resolve().parents[1]
cTemp = cProject / "_" / "temp"
cWidth = 96
cHeight = 54
cRows = 6
cColumns = 8
cFrameSize = cWidth * cHeight * 3
cTileShape = (cRows, cHeight // cRows, cColumns, cWidth // cColumns, 3)
cIndexBlockSize = 128
cMaxCandidates = 32
cTimeBasePattern = re.compile(r"config in time_base:\s*(\d+/\d+)")
cFramePattern = re.compile(r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)")
cVideoIdPattern = re.compile(r"[A-Za-z0-9_-]{11}")
cChannelIdPattern = re.compile(r"UC[A-Za-z0-9_-]{22}")
cUploadsIdPattern = re.compile(r"UU[A-Za-z0-9_-]{22}")
cYoutubeHosts = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com")
cPendingLiveStatuses = ("is_live", "is_upcoming", "post_live")
cUnsafeFilename = re.compile(r"[/\\\x00-\x1f\x7f]")
cOriginalSuffix = " (original).mkv"
cAudioBitrate = 192_000
cMp3SampleRates = ("32000", "44100", "48000")


class LoopMatch(NamedTuple):
  vStart: int
  vEnd: int
  vMeanError: float
  vTileError: float
  vRepeatedMotion: bool
  vSequenceFrames: int = 0


def fVideoId(pUrl: str) -> str:
  vUrl = urlsplit(pUrl)
  vHost = vUrl.hostname
  if vUrl.scheme not in ("http", "https") or vUrl.username or vUrl.password:
    raise ValueError("Enter an HTTP or HTTPS YouTube URL.")

  aParts = vUrl.path.strip("/").split("/")
  if vHost in ("youtu.be", "www.youtu.be") and len(aParts) == 1:
    vId = aParts[0]
  elif vHost in (*cYoutubeHosts, "youtube-nocookie.com", "www.youtube-nocookie.com"):
    if aParts == ["watch"]:
      vId = parse_qs(vUrl.query).get("v", [""])[0]
    elif len(aParts) == 2 and aParts[0] in ("shorts", "embed", "live", "v"):
      vId = aParts[1]
    else:
      vId = ""
  else:
    vId = ""

  if not cVideoIdPattern.fullmatch(vId):
    raise ValueError("Enter a YouTube video, channel, or channel uploads URL.")
  return vId


def fChannelUrl(pUrl: str) -> str | None:
  vUrl = urlsplit(pUrl)
  if (vUrl.scheme not in ("http", "https") or vUrl.username or vUrl.password
      or vUrl.hostname not in cYoutubeHosts):
    return None
  aParts = vUrl.path.strip("/").split("/")
  if aParts == ["playlist"]:
    vUploads = parse_qs(vUrl.query).get("list", [""])[0]
    return f"https://www.youtube.com/playlist?list={vUploads}" if cUploadsIdPattern.fullmatch(vUploads) else None

  vKind = aParts[0]
  if vKind in ("channel", "c", "user"):
    if len(aParts) < 2 or not aParts[1]:
      return None
    if vKind == "channel" and not cChannelIdPattern.fullmatch(aParts[1]):
      return None
    vRootLength = 2
  else:
    if vKind.startswith("@"):
      if len(vKind) == 1:
        return None
    elif (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", vKind)
          or vKind.lower() in ("watch", "shorts", "live", "embed", "v", "feed", "results",
                               "redirect", "account", "browse")):
      return None
    vRootLength = 1

  aTabs = aParts[vRootLength:]
  if aTabs == ["featured"]:
    aParts.pop()
  elif aTabs and (len(aTabs) != 1 or aTabs[0] not in ("videos", "shorts", "streams")):
    return None
  return f"https://www.youtube.com/{'/'.join(aParts)}"


def fChannelVideos(pUrl: str, pdEnvironment: dict) -> dict[str, bool]:
  aCommand = [
    "yt-dlp", "--ignore-config", "--no-cache-dir", "--flat-playlist",
    "--skip-download", "--dump-single-json", "--", pUrl,
  ]
  dListing = json.loads(subprocess.check_output(aCommand, env=pdEnvironment))
  if not isinstance(dListing, dict) or not isinstance(dListing.get("entries"), list):
    raise RuntimeError("yt-dlp did not return a channel video listing.")

  # A channel URL can return separate nested listings for Videos, Shorts and Live.
  lPending = list(reversed(dListing["entries"]))
  dVideos = {}
  while lPending:
    vEntry = lPending.pop()
    if not isinstance(vEntry, dict):
      continue
    lEntries = vEntry.get("entries")
    if isinstance(lEntries, list):
      lPending.extend(reversed(lEntries))
      continue
    vId = vEntry.get("id")
    if (not isinstance(vId, str) or not cVideoIdPattern.fullmatch(vId)
        or vEntry.get("ie_key") not in (None, "Youtube")):
      continue
    vPending = (vEntry.get("live_status") in cPendingLiveStatuses
                or vEntry.get("is_live") is True or vEntry.get("is_upcoming") is True)
    dVideos[vId] = dVideos.get(vId, False) or vPending
  return dVideos


def fMediaStem(pdMetadata: dict, pVideoId: str) -> str:
  vChannel = (pdMetadata.get("channel") or pdMetadata.get("uploader") or "").strip()
  vTitle = (pdMetadata.get("title") or pVideoId).strip() or pVideoId
  vUploadDate = pdMetadata.get("upload_date") or pdMetadata.get("release_date") or ""
  vDate = ""
  if vMatch := re.fullmatch(r"([0-9]{4})([0-9]{2})([0-9]{2})", vUploadDate):
    vYear, vMonth, vDay = vMatch.groups()
    vDate = f"y{vYear}m{vMonth}d{vDay}"
  return " - ".join(vPart for vPart in (vChannel, vDate, vTitle) if vPart)


def fDownload(pVideoId: str, pWork: Path, pdEnvironment: dict) -> tuple[Path, str]:
  vUrl = f"https://www.youtube.com/watch?v={pVideoId}"
  vMetadataFile = pWork / "metadata.json"
  aCommand = [
    "yt-dlp", "--ignore-config", "--no-cache-dir", "--no-playlist", "--no-mtime", "--newline",
    "--match-filters", "!is_live & !is_upcoming",
    "--format", "bv*+ba/bv*", "--format-sort", "res", "--format-sort-force", "--check-formats",
    "--merge-output-format", "mkv", "--remux-video", "mkv",
    "--no-simulate", "--print-to-file", "after_move:%(.{channel,uploader,upload_date,release_date,title})j",
    str(vMetadataFile).replace("%", "%%"),
    "--paths", str(pWork), "--output", "original.%(ext)s", "--", vUrl,
  ]
  subprocess.run(aCommand, env=pdEnvironment, stdout=sys.stderr, check=True)
  vSource = pWork / "original.mkv"
  if not vSource.is_file():
    raise RuntimeError("yt-dlp did not produce the expected original.mkv file.")
  dMetadata = json.loads(vMetadataFile.read_text(encoding="utf-8")) if vMetadataFile.is_file() else {}
  return vSource, fMediaStem(dMetadata, pVideoId)


def fResultFolder(pDestination: Path, pVideoId: str) -> Path:
  pDestination.mkdir(parents=True, exist_ok=True)
  for vAttempt in count(1):
    vName = pVideoId if vAttempt == 1 else f"{pVideoId}-{vAttempt}"
    vFolder = pDestination / vName
    try:
      vFolder.mkdir()
      return vFolder
    except FileExistsError:
      continue


def fMediaPath(pFolder: Path, pStem: str, pSuffix: str) -> Path:
  vName = cUnsafeFilename.sub("_", pStem).strip()
  vLimit = os.pathconf(pFolder, "PC_NAME_MAX")
  if vLimit > 0:
    vAvailable = max(0, vLimit - len(os.fsencode(pSuffix)))
    vName = os.fsencode(vName)[:vAvailable].decode(sys.getfilesystemencoding(), errors="ignore").rstrip()
  if not vName:
    raise ValueError("The media name and suffix cannot fit on the destination filesystem.")
  return pFolder / (vName + pSuffix)


def fSavedOriginal(pFolder: Path, pVideoId: str) -> tuple[Path, str]:
  lOriginals = [vPath for vPath in pFolder.glob(f"*{cOriginalSuffix}") if vPath.is_file()]
  if len(lOriginals) > 1:
    raise RuntimeError(f"More than one saved original was found in {pFolder}.")
  if lOriginals:
    vSource = lOriginals[0]
    return vSource, vSource.name.removesuffix(cOriginalSuffix)
  vLegacy = pFolder / "original.mkv"
  if vLegacy.is_file():
    return vLegacy, pVideoId
  raise RuntimeError(f"No saved original was found in {pFolder}.")


def fPublishFile(pSource: Path, pTarget: Path) -> None:
  try:
    pTarget.hardlink_to(pSource)
    return
  except OSError as vError:
    if vError.errno not in (EXDEV, EOPNOTSUPP, EPERM):
      raise
  vCreated = False
  try:
    with pSource.open("rb") as vInput, pTarget.open("xb") as vOutput:
      vCreated = True
      shutil.copyfileobj(vInput, vOutput, length=1024 * 1024)
  except BaseException:
    if vCreated:
      pTarget.unlink(missing_ok=True)
    raise


def fPublishMedia(pSource: Path, pFolder: Path, pStem: str, pSuffix: str) -> Path:
  vTarget = fMediaPath(pFolder, pStem, pSuffix)
  try:
    fPublishFile(pSource, vTarget)
  except OSError as vError:
    if ":" not in vTarget.name or vError.errno not in (EACCES, EILSEQ, EINVAL, ENOENT, EOPNOTSUPP, EPERM):
      raise
    vTarget = vTarget.with_name(vTarget.name.replace(":", ","))
    fPublishFile(pSource, vTarget)
  return vTarget


def fPublishNumbered(pSource: Path, pFolder: Path, pStem: str, pKind: str) -> Path:
  for vAttempt in count(1):
    vNumber = "" if vAttempt == 1 else f" {vAttempt}"
    vSuffix = f" ({pKind}{vNumber}){pSource.suffix}"
    try:
      return fPublishMedia(pSource, pFolder, pStem, vSuffix)
    except FileExistsError:
      continue


def fProbeAudio(pFile: Path, pdEnvironment: dict) -> dict | None:
  aCommand = [
    "ffprobe", "-v", "error", "-select_streams", "a:0",
    "-show_entries", "stream=codec_name,sample_rate,channels,bit_rate", "-of", "json", str(pFile),
  ]
  lStreams = json.loads(subprocess.check_output(aCommand, env=pdEnvironment)).get("streams", [])
  return lStreams[0] if lStreams else None


def fIsExportedAudio(pFile: Path, pdEnvironment: dict) -> bool:
  dStream = fProbeAudio(pFile, pdEnvironment)
  if (dStream is None or dStream.get("codec_name") != "mp3"
      or dStream.get("bit_rate") != str(cAudioBitrate) or dStream.get("sample_rate") not in cMp3SampleRates):
    return False
  # MPEG-1 Layer III carries 1152 samples per frame, with byte padding when needed.
  vFrameSize = Fraction(144 * cAudioBitrate, int(dStream["sample_rate"]))
  sExpectedSizes = {str(math.floor(vFrameSize)), str(math.ceil(vFrameSize))}
  aCommand = [
    "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_packets",
    "-show_entries", "packet=size:packet_side_data=", "-of", "default=nw=1:nk=1", str(pFile),
  ]
  sPacketSizes = set(subprocess.check_output(aCommand, env=pdEnvironment, text=True).split())
  return bool(sPacketSizes) and sPacketSizes <= sExpectedSizes


def fExportAudio(pSource: Path, pFolder: Path, pStem: str, pWork: Path,
                 pdEnvironment: dict) -> Path | None:
  dSource = fProbeAudio(pSource, pdEnvironment)
  if dSource is None:
    return None

  vExisting = fMediaPath(pFolder, pStem, " (audio).mp3")
  if vExisting.is_file():
    try:
      if fIsExportedAudio(vExisting, pdEnvironment):
        return vExisting
    except subprocess.CalledProcessError:
      pass

  print("Exporting the full audio track as a 192 kb/s MP3…", file=sys.stderr, flush=True)
  vRendered = pWork / "audio.mp3"
  aCommand = [
    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning", "-xerror", "-i", str(pSource),
    "-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-b:a", str(cAudioBitrate), "-abr", "0",
  ]
  # MPEG-1 Layer III supports 192 kb/s at these sample rates.
  if dSource.get("sample_rate") not in cMp3SampleRates:
    aCommand += ["-ar", "48000"]
  if dSource.get("channels", 0) > 2:
    aCommand += ["-ac", "2"]
  aCommand += ["-map_chapters", "-1", "-f", "mp3", "-n", str(vRendered)]
  subprocess.run(aCommand, env=pdEnvironment, stdout=sys.stderr, check=True)
  if not fIsExportedAudio(vRendered, pdEnvironment):
    raise RuntimeError("FFmpeg did not produce an MP3 audio stream at a constant 192 kb/s.")
  return fPublishNumbered(vRendered, pFolder, pStem, "audio")


def fProbeVideo(pFile: Path, pdEnvironment: dict, pLoop: bool = False) -> dict:
  aCommand = ["ffprobe", "-v", "error"]
  if not pLoop:
    aCommand += ["-select_streams", "V:0"]
  aCommand += [
    "-show_entries", "stream=codec_type,codec_name,width,height,pix_fmt,nb_frames,time_base,start_pts,duration_ts",
    "-of", "json", str(pFile),
  ]
  lStreams = json.loads(subprocess.check_output(aCommand, env=pdEnvironment)).get("streams", [])
  if not lStreams:
    raise RuntimeError(f"No video stream was found in {pFile}.")
  if pLoop and (len(lStreams) != 1 or lStreams[0]["codec_type"] != "video"):
    raise RuntimeError("The loop must contain exactly one video stream.")
  return lStreams[0]


def fReadFrames(pSource: Path, pWork: Path,
                pdEnvironment: dict) -> tuple[np.memmap, np.ndarray, Fraction]:
  vThumbnails = pWork / "frames.rgb"
  vLog = pWork / "ffmpeg-frames.log"
  aCommand = [
    "ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info", "-xerror", "-copyts",
    "-i", str(pSource), "-map", "0:V:0", "-an",
    "-vf", f"scale={cWidth}:{cHeight}:flags=area,format=rgb24,showinfo=checksum=0",
    "-c:v", "rawvideo", "-threads:v", "1", "-fps_mode:v", "passthrough",
    "-f", "rawvideo", str(vThumbnails),
  ]
  with vLog.open("wb") as vLogFile:
    vProcess = subprocess.run(aCommand, stderr=vLogFile, env=pdEnvironment)
  if vProcess.returncode:
    with vLog.open("rb") as vLogFile:
      vLogFile.seek(max(0, vLog.stat().st_size - 2048))
      vDetails = vLogFile.read().decode(errors="replace").strip()
    raise RuntimeError(f"FFmpeg could not read the video frames.\n{vDetails}")

  lPts = []
  vTimeBase = None
  with vLog.open(encoding="utf-8", errors="replace") as vLogFile:
    for vLine in vLogFile:
      if "Parsed_showinfo" not in vLine:
        continue
      if vBaseMatch := cTimeBasePattern.search(vLine):
        vNewBase = Fraction(vBaseMatch[1])
        if vTimeBase is not None and vNewBase != vTimeBase:
          raise RuntimeError("The source video changed its frame time base during decoding.")
        vTimeBase = vNewBase
      if vFrameMatch := cFramePattern.search(vLine):
        if int(vFrameMatch[1]) != len(lPts):
          raise RuntimeError("FFmpeg did not report a continuous sequence of frame numbers.")
        lPts.append(int(vFrameMatch[2]))

  aPts = np.asarray(lPts, dtype=np.int64)
  if not len(aPts) or not vTimeBase or vThumbnails.stat().st_size != len(aPts) * cFrameSize:
    raise RuntimeError("FFmpeg did not produce a timestamp for each decoded frame.")
  if np.any(np.diff(aPts) <= 0):
    raise RuntimeError("The source video has non-increasing frame timestamps.")
  aFrames = np.memmap(vThumbnails, dtype=np.uint8, mode="r", shape=(len(aPts), *cTileShape))
  return aFrames, aPts, vTimeBase


def fFrameFeatures(paFrames: np.memmap) -> tuple[np.ndarray, np.ndarray]:
  aDescriptors = np.empty((len(paFrames), cRows * cColumns * 3), dtype=np.float32)
  aMotion = np.zeros(len(paFrames), dtype=np.float32)
  for vStart in range(0, len(paFrames), 128):
    vEnd = min(len(paFrames), vStart + 128)
    aFrames = paFrames[vStart:vEnd]
    aTileMeans = aFrames.mean(axis=(2, 4), dtype=np.float32)
    aDescriptors[vStart:vEnd] = aTileMeans.reshape(vEnd - vStart, -1)
    vPrevious = max(0, vStart - 1)
    aPixels = paFrames[vPrevious:vEnd].astype(np.int16)
    aChanges = np.abs(np.diff(aPixels, axis=0))
    aTiles = aChanges.mean(axis=(2, 4, 5), dtype=np.float32)
    aMotion[vPrevious + 1:vEnd] = aTiles.mean(axis=(1, 2)) + aTiles.max(axis=(1, 2)) / 4
  return aDescriptors, aMotion


def fFrameDifference(paFrames: np.ndarray, pFirst: int, pSecond: int) -> tuple[float, float]:
  aChanges = np.abs(np.subtract(paFrames[pFirst], paFrames[pSecond], dtype=np.int16))
  aTiles = aChanges.mean(axis=(1, 3, 4), dtype=np.float32)
  return float(aTiles.mean()), float(aTiles.max())


def fRepeatContext(paFrames: np.ndarray, pStart: int, pEnd: int, pTolerance: float) -> bool:
  for vDirection in (1, -1):
    vCount = 0
    for vStep in (1, 2, 3):
      vOffset = vDirection * vStep
      if not (0 <= pStart + vOffset < pEnd + vOffset < len(paFrames)):
        break
      vMean, vTile = fFrameDifference(paFrames, pStart + vOffset, pEnd + vOffset)
      if vMean > 1.5 * pTolerance or vTile > 4.5 * pTolerance:
        break
      vCount += 1
    if vCount >= 2:
      return True
  return False


def fAssessPair(paFrames: np.ndarray, paMotion: np.ndarray, paSeconds: np.ndarray,
                pStart: int, pEnd: int, pTolerance: float, pMinSeconds: float) -> LoopMatch | None:
  vMean, vTile = fFrameDifference(paFrames, pStart, pEnd)
  if vMean > pTolerance or vTile > 3 * pTolerance:
    return None
  vError = vMean + vTile / 4

  # Use the closest frame in the immediate neighborhood of the return.
  for vNeighbor in (pEnd - 1, pEnd + 1):
    if vNeighbor >= len(paFrames) or vNeighbor < pStart + 2:
      continue
    if paSeconds[vNeighbor] - paSeconds[pStart] < pMinSeconds:
      continue
    vNearMean, vNearTile = fFrameDifference(paFrames, pStart, vNeighbor)
    if vNearMean + vNearTile / 4 < vError:
      return None

  # Require some movement away from the starting image within the proposed loop.
  aInterior = np.linspace(pStart + 1, pEnd - 1, min(12, pEnd - pStart - 1), dtype=int)
  vPeak = pStart + 1 + int(np.argmax(paMotion[pStart + 1:pEnd]))
  aInterior = np.append(aInterior, (vPeak, max(pStart + 1, vPeak - 1)))
  vExcursion = max(vMeanSample + vTileSample / 4 for vMeanSample, vTileSample in
                   (fFrameDifference(paFrames, pStart, int(vFrame)) for vFrame in aInterior))
  if vExcursion <= max(0.8, 1.75 * vError, pTolerance / 2):
    return None

  # Compare both transitions at the seam to the motion just inside the clip.
  vIncomingMean, vIncomingTile = fFrameDifference(paFrames, pEnd - 1, pStart)
  vIncoming = vIncomingMean + vIncomingTile / 4
  aNearby = np.concatenate((paMotion[pStart + 2:min(pStart + 7, pEnd)],
                            paMotion[max(pEnd - 5, pStart + 2):pEnd]))
  vMotionLimit = max(5.0, 3 * pTolerance, 3 * float(np.median(aNearby))) if aNearby.size else math.inf
  if max(vIncoming, float(paMotion[pStart + 1])) > vMotionLimit:
    return None

  vRepeated = fRepeatContext(paFrames, pStart, pEnd, pTolerance)
  if not vRepeated and (vMean > 0.65 * pTolerance or vTile > 2 * pTolerance):
    return None
  return LoopMatch(pStart, pEnd, vMean, vTile, vRepeated)


def fFindExactRepeat(paFrames: np.memmap, paSeconds: np.ndarray,
                     pMinSeconds: float) -> LoopMatch | None:
  aHashes = np.fromiter((hash(vFrame.tobytes()) for vFrame in paFrames),
                        dtype=np.int64, count=len(paFrames))
  dPositions = defaultdict(list)
  for vFrame, aContext in enumerate(zip(aHashes, aHashes[1:], aHashes[2:]), start=1):
    vPrevious, vCurrent, vNext = aContext
    if vPrevious == vCurrent == vNext:
      continue
    dPositions[aContext].append(vFrame)

  dVotes = Counter()
  for lPositions in dPositions.values():
    # Count each changing neighborhood once per gap, regardless of how often it occurs.
    sGaps = {vSecond - vFirst for vFirst, vSecond in zip(lPositions, lPositions[1:])
             if vSecond - vFirst >= 2 and paSeconds[vSecond] - paSeconds[vFirst] >= pMinSeconds}
    dVotes.update(sGaps)

  lRanked = sorted(dVotes.items(), key=lambda pVote: (-pVote[1], pVote[0]))
  for vGap, vVotes in lRanked:
    if vVotes < min(3, vGap) or 2 * vGap > len(aHashes):
      continue
    aEqual = aHashes[:-vGap] == aHashes[vGap:]
    aRuns = np.flatnonzero(np.diff(np.r_[False, aEqual, False])).reshape(-1, 2)
    for vFirst, vStop in aRuns:
      vStart = int(vFirst)
      vEnd = vStart + vGap
      if vEnd > vStop or paSeconds[vEnd] - paSeconds[vStart] < pMinSeconds:
        continue
      if np.all(aHashes[vStart:vEnd] == aHashes[vStart]):
        continue
      if np.array_equal(paFrames[vStart], paFrames[vEnd]):
        return LoopMatch(vStart, vEnd, 0.0, 0.0, True, int(vStop - vStart))
  return None


def fFindLoop(paFrames: np.memmap, paSeconds: np.ndarray, pTolerance: float,
              pMinSeconds: float) -> LoopMatch | None:
  if len(paFrames) < 3 or paSeconds[-1] - paSeconds[0] < pMinSeconds:
    return None
  vExact = fFindExactRepeat(paFrames, paSeconds, pMinSeconds)
  if vExact is not None:
    return vExact
  aDescriptors, aMotion = fFrameFeatures(paFrames)
  aAnchors = np.flatnonzero(aMotion > 0)
  if not aAnchors.size:
    return None
  aAnchors = np.insert(aAnchors, 0, 0)
  aFeatures = aDescriptors[aAnchors]
  vRadius = pTolerance * aFeatures.shape[1] + 1e-5
  lTrees = []
  vIndexed = 0
  vBest = None
  for vEnd in aAnchors[1:]:
    vEnd = int(vEnd)
    vLimit = min(vEnd - 1, int(np.searchsorted(paSeconds, paSeconds[vEnd] - pMinSeconds,
                                               side="right")))
    if vLimit < 1:
      continue
    vEligible = int(np.searchsorted(aAnchors, vLimit))
    if not vEligible:
      continue

    # Index only elapsed footage. Merge adjacent blocks of equal size as they become eligible.
    while vIndexed + cIndexBlockSize <= vEligible:
      vBlockStart = vIndexed
      vIndexed += cIndexBlockSize
      while lTrees and lTrees[-1][1] - lTrees[-1][0] == vIndexed - vBlockStart:
        vBlockStart = lTrees.pop()[0]
      lTrees.append((vBlockStart, vIndexed, cKDTree(aFeatures[vBlockStart:vIndexed])))

    aFeature = aDescriptors[vEnd]
    lCandidates = [np.arange(vIndexed, vEligible, dtype=np.intp)]
    for vBlockStart, vBlockEnd, vTree in lTrees:
      aDistances, aMatches = vTree.query(aFeature, k=min(cMaxCandidates, vBlockEnd - vBlockStart),
                                         p=1, distance_upper_bound=vRadius)
      lCandidates.append(vBlockStart + aMatches[np.isfinite(aDistances)])
    aHits = np.concatenate(lCandidates)
    aTileErrors = np.abs(aFeatures[aHits] - aDescriptors[vEnd]).reshape(-1, cRows * cColumns, 3)
    aTileErrors = aTileErrors.mean(axis=2)
    aMeanErrors = aTileErrors.mean(axis=1)
    aMaxErrors = aTileErrors.max(axis=1)
    aValid = (aMeanErrors <= pTolerance + 1e-5) & (aMaxErrors <= 3 * pTolerance + 1e-5)
    aHits = aHits[aValid]
    aCosts = aMeanErrors[aValid] + aMaxErrors[aValid] / 4
    if len(aHits) > cMaxCandidates:
      aKeep = np.argpartition(aCosts, cMaxCandidates - 1)[:cMaxCandidates]
      aHits, aCosts = aHits[aKeep], aCosts[aKeep]
    aOrder = np.lexsort((aAnchors[aHits], aCosts))

    vConfirmed = None
    for vHit in aHits[aOrder]:
      vStart = int(aAnchors[vHit])
      vMatch = fAssessPair(paFrames, aMotion, paSeconds, vStart, vEnd, pTolerance, pMinSeconds)
      if vMatch is None:
        continue
      vRank = (vMatch.vMeanError + vMatch.vTileError / 4, vStart)
      if vMatch.vRepeatedMotion and (vConfirmed is None or vRank < vConfirmed[0]):
        vConfirmed = (vRank, vMatch)
      if vBest is None or vRank < vBest[0]:
        vBest = (vRank, vMatch)
    if vConfirmed is not None:
      return vConfirmed[1]
  return vBest[1] if vBest is not None else None


def fMp4Options(pTarget: Path, pTimeBase: Fraction, pLast: Fraction, pEnd: Fraction,
                pOffset: Fraction = Fraction(0)) -> list[str]:
  # The excluded frame's timestamp determines the last displayed packet's duration.
  vLastDuration = pEnd - pLast
  vDurationExpression = (
    f"if(eq(PTS,round({pLast.numerator}/{pLast.denominator}/TB)),"
    f"round({vLastDuration.numerator}/{vLastDuration.denominator}/TB),DURATION)"
  )
  vShift = f"round({pOffset.numerator}/{pOffset.denominator}/TB)"
  vFilter = f"setts=pts=PTS-{vShift}:dts=DTS-{vShift}:duration='{vDurationExpression}'"
  return [
    "-map", "0:V:0", "-an", "-bsf:v", vFilter,
    "-video_track_timescale", str(pTimeBase.denominator),
    "-movie_timescale", str(pTimeBase.denominator),
    "-map_chapters", "-1", "-movflags", "+faststart", "-f", "mp4", "-n", str(pTarget),
  ]


def fVerifyLoop(pTarget: Path, pdSource: dict, pFrames: int, pDuration: Fraction, pdEnvironment: dict) -> dict:
  dOutput = fProbeVideo(pTarget, pdEnvironment, pLoop=True)
  if int(dOutput.get("nb_frames", 0)) != pFrames:
    raise RuntimeError(f"The rendered clip does not contain the expected {pFrames} frames.")
  if sorted((dOutput["width"], dOutput["height"])) != sorted((pdSource["width"], pdSource["height"])):
    raise RuntimeError("The rendered clip does not preserve the resolution of the download.")
  if dOutput.get("pix_fmt") != pdSource.get("pix_fmt"):
    raise RuntimeError("The rendered clip does not preserve the source pixel format.")
  vOutputDuration = int(dOutput.get("duration_ts", 0)) * Fraction(dOutput["time_base"])
  if dOutput.get("start_pts") != 0 or vOutputDuration != pDuration:
    raise RuntimeError("The rendered clip does not preserve the timing of the selected frames.")
  return dOutput


def fProbePackets(pFile: Path, pdEnvironment: dict, pInterval: str | None = None) -> list[dict]:
  aCommand = ["ffprobe", "-v", "error", "-select_streams", "V:0"]
  if pInterval is not None:
    aCommand += ["-read_intervals", pInterval]
  aCommand += [
    "-show_packets", "-show_entries", "packet=pts,dts,flags,data_hash",
    "-show_data_hash", "sha256", "-of", "json", str(pFile),
  ]
  return json.loads(subprocess.check_output(aCommand, env=pdEnvironment)).get("packets", [])


def fCopyLoop(pSource: Path, pTarget: Path, pdSource: dict, paPts: np.ndarray,
              pTimeBase: Fraction, pdEnvironment: dict) -> dict | None:
  if Fraction(pdSource["time_base"]) != pTimeBase:
    return None
  vFirst = int(paPts[0])
  vStart, vLast, vEnd = (int(paPts[vIndex]) * pTimeBase for vIndex in (0, -2, -1))
  vInterval = f"{float(vStart):.6f}%+#{len(paPts)}"
  lSource = fProbePackets(pSource, pdEnvironment, vInterval)
  if len(lSource) != len(paPts):
    return None
  if any("K" not in dPacket.get("flags", "") for dPacket in (lSource[0], lSource[-1])):
    return None
  # A whole group with packets in display order can be copied at these boundaries.
  if any(dPacket.get("pts") != vPts or dPacket.get("dts") != vPts or not dPacket.get("data_hash")
         for dPacket, vPts in zip(lSource, paPts)):
    return None

  vCount = len(paPts) - 1
  aCommand = [
    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning", "-xerror", "-copyts",
    "-seek_timestamp", "1", "-ss", f"{float(vStart):.6f}", "-i", str(pSource),
    "-c:v", "copy", "-copytb", "1", "-frames:v", str(vCount),
    *fMp4Options(pTarget, pTimeBase, vLast, vEnd, vStart),
  ]
  subprocess.run(aCommand, env=pdEnvironment, capture_output=True, check=True)
  dOutput = fVerifyLoop(pTarget, pdSource, vCount, vEnd - vStart, pdEnvironment)
  lOutput = fProbePackets(pTarget, pdEnvironment)
  if len(lOutput) != vCount or dOutput["codec_name"] != pdSource["codec_name"]:
    return None
  vOutputBase = Fraction(dOutput["time_base"])
  if any(dTarget.get("data_hash") != dSource["data_hash"]
         or dTarget.get("pts", -1) * vOutputBase != (dSource["pts"] - vFirst) * pTimeBase
         for dSource, dTarget in zip(lSource[:-1], lOutput)):
    return None
  return dOutput


def fRenderLoop(pSource: Path, pTarget: Path, pdSource: dict, pMatch: LoopMatch,
                paPts: np.ndarray, pTimeBase: Fraction, pdEnvironment: dict) -> dict:
  aClipPts = paPts[pMatch.vStart:pMatch.vEnd + 1]
  try:
    dCopy = fCopyLoop(pSource, pTarget, pdSource, aClipPts, pTimeBase, pdEnvironment)
  except (RuntimeError, ValueError, subprocess.CalledProcessError):
    dCopy = None
  if dCopy is not None:
    return dCopy | {"render_mode": "stream_copy"}
  pTarget.unlink(missing_ok=True)

  print("Encoding the exact frame range losslessly…", file=sys.stderr, flush=True)
  vPixelFormat = pdSource["pix_fmt"]
  aX264Formats = ("yuv420p", "yuv422p", "yuv444p", "yuvj420p", "yuvj422p", "yuvj444p",
                  "yuv420p10le", "yuv422p10le", "yuv444p10le", "gray", "gray10le")
  if vPixelFormat in aX264Formats and pdSource["width"] % 2 == pdSource["height"] % 2 == 0:
    aEncoder = ["-c:v", "libx264", "-qp", "0", "-preset", "medium", "-bf", "0"]
  else:
    aEncoder = ["-c:v", "libaom-av1", "-crf", "0", "-b:v", "0", "-aom-params", "lossless=1",
                "-cpu-used", "6", "-lag-in-frames", "0"]

  vLast = (int(aClipPts[-2]) - int(aClipPts[0])) * pTimeBase
  vEnd = (int(aClipPts[-1]) - int(aClipPts[0])) * pTimeBase
  vVideoFilter = f"trim=start_frame={pMatch.vStart}:end_frame={pMatch.vEnd},setpts=PTS-STARTPTS"
  aCommand = [
    "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning", "-xerror", "-copyts",
    "-i", str(pSource), "-vf", vVideoFilter, *aEncoder, "-pix_fmt", f"+{vPixelFormat}",
    "-fps_mode:v", "passthrough", "-enc_time_base:v", "filter",
    *fMp4Options(pTarget, pTimeBase, vLast, vEnd),
  ]
  subprocess.run(aCommand, env=pdEnvironment, stdout=sys.stderr, check=True)
  dOutput = fVerifyLoop(pTarget, pdSource, len(aClipPts) - 1, vEnd, pdEnvironment)
  return dOutput | {"render_mode": "lossless_encode"}


def fProcessVideo(pVideoId: str, pArgs: argparse.Namespace, pDestination: Path,
                   pWorkRoot: Path, pdEnvironment: dict) -> dict:
  vOriginal = None
  vAudio = None
  try:
    with tempfile.TemporaryDirectory(prefix="youtube-loop-", dir=pWorkRoot) as vTempDirectory:
      vWork = Path(vTempDirectory)
      dEnvironment = dict(pdEnvironment, TMPDIR=vTempDirectory, DENO_DIR=str(vWork / "deno-cache"))
      if pArgs.reuse_original:
        vFolder = pDestination / pVideoId
        vOriginal, vStem = fSavedOriginal(vFolder, pVideoId)
      else:
        vDownload, vStem = fDownload(pVideoId, vWork, dEnvironment)
        vFolder = fResultFolder(pDestination, pVideoId)
        vOriginal = fPublishMedia(vDownload, vFolder, vStem, cOriginalSuffix)
        vStem = vOriginal.name.removesuffix(cOriginalSuffix)
      dSource = fProbeVideo(vOriginal, dEnvironment)
      vAudio = fExportAudio(vOriginal, vFolder, vStem, vWork, dEnvironment)
      dResult = {"video_id": pVideoId, "original": str(vOriginal),
                 "audio": str(vAudio) if vAudio else None,
                 "width": dSource["width"], "height": dSource["height"]}

      print("Analyzing video frames for a repeating segment…", file=sys.stderr, flush=True)
      aFrames, aPts, vBase = fReadFrames(vOriginal, vWork, dEnvironment)
      aSeconds = (aPts - aPts[0]) * float(vBase)
      vMatch = fFindLoop(aFrames, aSeconds, pArgs.tolerance, pArgs.min_seconds)
      del aFrames
      if vMatch is None:
        dResult.update(status="no_match", message="The video did not yield a reliable visual repeat.")
        return dResult

      print(f"Rendering frames {vMatch.vStart}–{vMatch.vEnd - 1}…", file=sys.stderr, flush=True)
      vRendered = vWork / "loop.mp4"
      dOutput = fRenderLoop(vOriginal, vRendered, dSource, vMatch, aPts, vBase, dEnvironment)
      vLoop = fPublishNumbered(vRendered, vFolder, vStem, "loop")
      dResult.update(
        status="ok", loop=str(vLoop), loop_width=dOutput["width"], loop_height=dOutput["height"],
        start_frame=vMatch.vStart, last_frame=vMatch.vEnd - 1, matched_frame=vMatch.vEnd,
        start_seconds=round(float(aSeconds[vMatch.vStart]), 6),
        matched_seconds=round(float(aSeconds[vMatch.vEnd]), 6),
        duration_seconds=round(float((int(aPts[vMatch.vEnd]) - int(aPts[vMatch.vStart])) * vBase), 6),
        mean_rgb_difference=round(vMatch.vMeanError, 4), repeated_sequence_frames=vMatch.vSequenceFrames,
        muted=True, render_mode=dOutput["render_mode"],
      )
      return dResult
  except Exception as vError:
    print(f"{pVideoId}: {vError}", file=sys.stderr, flush=True)
    vSaved = str(vOriginal) if vOriginal and vOriginal.is_file() else None
    return {"status": "error", "video_id": pVideoId, "original": vSaved,
            "audio": str(vAudio) if vAudio else None, "message": str(vError)}


def fProcessChannel(pUrl: str, pArgs: argparse.Namespace, pDestination: Path,
                     pWorkRoot: Path, pdEnvironment: dict) -> dict:
  print(f"Listing videos from {pUrl}…", file=sys.stderr, flush=True)
  with tempfile.TemporaryDirectory(prefix="youtube-channel-", dir=pWorkRoot) as vTempDirectory:
    vWork = Path(vTempDirectory)
    dEnvironment = dict(pdEnvironment, TMPDIR=vTempDirectory, DENO_DIR=str(vWork / "deno-cache"))
    dVideos = fChannelVideos(pUrl, dEnvironment)

  lResults = []
  for vIndex, (vVideoId, vPending) in enumerate(dVideos.items(), start=1):
    if vPending:
      print(f"[{vIndex}/{len(dVideos)}] Skipping live or pending video {vVideoId}.", file=sys.stderr, flush=True)
      lResults.append({"video_id": vVideoId, "status": "skipped", "message": "The stream is not ready as a video."})
      continue
    print(f"[{vIndex}/{len(dVideos)}] Processing {vVideoId}…", file=sys.stderr, flush=True)
    lResults.append(fProcessVideo(vVideoId, pArgs, pDestination, pWorkRoot, pdEnvironment))

  sStatuses = {dResult["status"] for dResult in lResults}
  vStatus = "ok"
  if "error" in sStatuses:
    vStatus = "partial" if sStatuses & {"ok", "no_match"} else "error"
  return {"status": vStatus, "channel_url": pUrl, "results": lResults}


def fMain() -> int:
  vParser = argparse.ArgumentParser(description="Download YouTube videos, export their audio and cut silent loops.")
  vParser.add_argument("url", help="URL of a YouTube video, channel, or channel uploads page")
  vParser.add_argument("--output-dir", type=Path, default=cProject / "downloads",
                       help="parent directory for the exported media (default: project downloads/)")
  vParser.add_argument("--work-dir", type=Path, default=cTemp,
                       help="parent directory for temporary media (default: project _/temp/)")
  vParser.add_argument("--reuse-original", action="store_true",
                       help="process the originals already saved in their output folders")
  vParser.add_argument("--tolerance", type=float, default=2.5,
                       help="maximum average RGB difference on a 0–255 scale (default: 2.5)")
  vParser.add_argument("--min-seconds", type=float, default=0.25,
                       help="minimum duration of the loop in seconds (default: 0.25)")
  # Earlier callers may still pass --mute. Every export is silent.
  vParser.add_argument("--mute", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
  vArgs = vParser.parse_args()
  if not 0 <= vArgs.tolerance <= 255:
    vParser.error("--tolerance must be between 0 and 255.")
  if not math.isfinite(vArgs.min_seconds) or vArgs.min_seconds < 0:
    vParser.error("--min-seconds must be finite and non-negative.")

  vChannel = None
  try:
    vChannel = fChannelUrl(vArgs.url)
    vVideoId = fVideoId(vArgs.url) if vChannel is None else ""
    dEnvironment = os.environ.copy()
    dEnvironment["PATH"] = str(cTemp / "bin") + os.pathsep + os.environ.get("PATH", os.defpath)
    lRequired = ["ffmpeg", "ffprobe"]
    if vChannel is not None or not vArgs.reuse_original:
      lRequired.append("yt-dlp")
    if not vArgs.reuse_original:
      lRequired.append("deno")
    lMissing = [vName for vName in lRequired if shutil.which(vName, path=dEnvironment["PATH"]) is None]
    if lMissing:
      raise RuntimeError("Install the required tools: " + ", ".join(lMissing))
    vWorkRoot = vArgs.work_dir.expanduser().resolve()
    vWorkRoot.mkdir(parents=True, exist_ok=True)
    vDestination = vArgs.output_dir.expanduser().resolve()
    if vChannel is None:
      dResult = fProcessVideo(vVideoId, vArgs, vDestination, vWorkRoot, dEnvironment)
    else:
      dResult = fProcessChannel(vChannel, vArgs, vDestination, vWorkRoot, dEnvironment)
    print(json.dumps(dResult))
    return {"ok": 0, "no_match": 3}.get(dResult["status"], 1)
  except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as vError:
    print(str(vError), file=sys.stderr)
    dResult = {"status": "error", "message": str(vError)}
    if vChannel is None:
      dResult.update(original=None, audio=None)
    else:
      dResult.update(channel_url=vChannel, results=[])
    print(json.dumps(dResult))
    return 1
  except KeyboardInterrupt:
    print("Interrupted.", file=sys.stderr)
    return 130


if __name__ == "__main__":
  raise SystemExit(fMain())
