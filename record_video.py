"""Record the standalone offline vector player to a real H.264 MP4 on Windows.

Examples:
  python build_player.py
  python record_video.py --expect-paths 1600

  python build_player.py --output recording/player-tests/partial.html --duration 28
  python record_video.py --html recording/player-tests/partial.html \
      --output recording/player-tests/partial.mp4 --seconds 7 --start 10

The browser captures the live Canvas/Path2D drawing with MediaRecorder; a
local Playwright binding streams WebM chunks into Python, then FFmpeg converts
the complete stream to H.264. No raster is embedded in the generated player.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
DEFAULT_HTML = ROOT / "output" / "miku-drawing-player.html"
DEFAULT_MP4 = ROOT / "output" / "hatsune-miku-process.mp4"
DEFAULT_SESSION = ROOT / "recording" / "session.json"


def chrome_path() -> Path:
    for path in (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ):
        if path.is_file():
            return path
    raise RuntimeError("Installed Google Chrome or Microsoft Edge is required")


def ffprobe(mp4: Path, executable: str) -> dict:
    result = subprocess.run(
        [executable, "-v", "error", "-show_entries",
         "format=duration,size:stream=index,codec_name,width,height,avg_frame_rate,nb_frames",
         "-select_streams", "v:0", "-of", "json", str(mp4)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", check=True,
    )
    response = json.loads(result.stdout)
    stream = response["streams"][0]
    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "average_fps": stream.get("avg_frame_rate"),
        "frames": int(stream.get("nb_frames", 0)),
        "actual_seconds": float(response["format"]["duration"]),
        "file_bytes": int(response["format"]["size"]),
    }


def record(args: argparse.Namespace) -> dict:
    html = args.html.resolve()
    output = args.output.resolve()
    session = args.session.resolve()
    if not html.is_file():
        raise FileNotFoundError(f"Run build_player.py first: {html}")
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Output already exists (use --overwrite to replace): {output}")
    if not session.is_file():
        raise FileNotFoundError(session)
    original_sha = hashlib.sha256(session.read_bytes()).hexdigest()
    ffmpeg = shutil.which("ffmpeg")
    probe = shutil.which("ffprobe")
    if not ffmpeg or not probe:
        raise RuntimeError("FFmpeg and ffprobe must be in PATH")
    chrome = chrome_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    error_messages = []
    bytes_received = 0
    chunks_received = 0
    browser_info = {}
    final_state = {}
    page_chapters = []
    webm_codec = None
    duration = None
    start_time = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="miku-record-", dir=output.parent) as tmp:
        webm = Path(tmp) / "capture.webm"
        with webm.open("wb") as stream_file:
            def video_chunk(_source: object, base64_data: str, index: int) -> None:
                nonlocal bytes_received, chunks_received
                if index != chunks_received:
                    raise RuntimeError(f"Nonsequential video chunk {index}; expected {chunks_received}")
                chunk = base64.b64decode(base64_data, validate=True)
                stream_file.write(chunk)
                bytes_received += len(chunk)
                chunks_received += 1

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=not args.headful,
                    executable_path=str(chrome),
                    args=["--autoplay-policy=no-user-gesture-required"],
                )
                try:
                    page = browser.new_page(
                        viewport={"width":1920,"height":1080},device_scale_factor=1,
                        reduced_motion="reduce",
                    )
                    page.on("pageerror", lambda ex: error_messages.append(str(ex)))
                    page.on("console", lambda m: error_messages.append(m.text) if m.type == "error" else None)
                    page.expose_binding("__mikuVideoChunk", video_chunk)
                    page.goto(html.as_uri(), wait_until="load", timeout=120_000)
                    page.wait_for_function("window.__mikuReady===true && window.__mikuStudio?.ready===true",
                                           timeout=120_000)
                    browser_info = page.evaluate("window.__mikuStudio.getState()")
                    page_chapters = page.evaluate("window.__mikuPlayer.chapters")
                    if browser_info["sessionSha256"] != original_sha:
                        raise RuntimeError(
                            "HTML is stale relative to recording/session.json. "
                            "Re-run build_player.py on the finished session first."
                        )
                    if args.expect_paths is not None and browser_info["paths"] != args.expect_paths:
                        raise RuntimeError(
                            f"Expected {args.expect_paths} final SVG paths but HTML has "
                            f"{browser_info['paths']}"
                        )
                    if args.expect_underpainting is not None and browser_info["underpainting"] != args.expect_underpainting:
                        raise RuntimeError(
                            f"Expected {args.expect_underpainting} underpainting paths; "
                            f"found {browser_info['underpainting']}"
                        )
                    # Every source path is parsed lazily, during playback.
                    # Waiting for readiness outside capture prevents loading
                    # animation frames from appearing in the final recording.
                    settings = page.evaluate("([fps,from,seconds,bitrate]) => "
                                             "window.__mikuPlayer.startCapture({fps,from,seconds,bitrate})",
                                             [args.fps,args.start,args.seconds,args.bitrate])
                    webm_codec = settings["mime"]
                    duration = settings["seconds"]
                    print(json.dumps({"event":"capture_started", "seconds":duration,
                                      "fps":args.fps,"codec":webm_codec,
                                      "final_paths":browser_info["paths"],
                                      "underpainting":browser_info["underpainting"],
                                      "operations":browser_info["operations"]},ensure_ascii=False),flush=True)
                    deadline = time.monotonic() + max(60,duration*2.5+60)
                    last_report = 0.0
                    while True:
                        if time.monotonic() > deadline:
                            raise TimeoutError("MediaRecorder exceeded expected capture time")
                        page.wait_for_timeout(1000)
                        state = page.evaluate("""() => ({done:window.__mikuRecordingDone,
                          error:window.__mikuRecordingError, state:window.__mikuStudio.getState()})""")
                        if state.get("error"):
                            raise RuntimeError("Browser recording: "+state["error"])
                        if state.get("done"):
                            final_state = state["state"]
                            break
                        if time.monotonic()-last_report>=15:
                            last_report=time.monotonic()
                            print(f"Recording {state['state']['time']:.1f} / "
                                  f"{settings['from']+duration:.1f} s; {bytes_received:,} bytes received",
                                  flush=True)
                    if error_messages:
                        raise RuntimeError("Browser console errors:\n"+"\n".join(error_messages[-12:]))
                finally:
                    browser.close()
            stream_file.flush()

        if chunks_received == 0 or bytes_received == 0:
            raise RuntimeError("MediaRecorder did not produce any video chunks")

        if args.keep_webm:
            backup = output.with_suffix(".webm")
            if backup.exists() and not args.overwrite:
                raise FileExistsError(backup)
            shutil.copyfile(webm, backup)

        encoding = [
            ffmpeg,"-hide_banner","-loglevel","warning",
            "-y" if args.overwrite else "-n",
            "-i",str(webm),"-an",
            "-vf",f"fps={args.fps},scale=1920:1080:flags=lanczos,format=yuv420p",
            "-c:v","libx264","-preset",args.preset,"-crf",str(args.crf),
            "-movflags","+faststart",str(output)
        ]
        result = subprocess.run(
            encoding,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            encoding="utf-8",errors="replace",text=True,
        )
        if result.returncode:
            raise RuntimeError(f"FFmpeg failed ({result.returncode}):\n{result.stderr[-3500:]}")

    probe_result = ffprobe(output,probe)
    if probe_result["codec"]!="h264" or (probe_result["width"],probe_result["height"])!=(1920,1080):
        raise RuntimeError(f"Incorrect output codec or resolution: {probe_result}")
    if not math.isclose(probe_result["actual_seconds"],duration,abs_tol=max(.65,duration*.025)):
        raise RuntimeError(f"Unexpected encoded video duration; expected {duration}s: {probe_result}")
    if args.seconds is None and final_state.get("completedFinalPaths")!=final_state.get("paths"):
        raise RuntimeError("Full recording stopped before every final SVG path completed")
    if args.seconds is None and final_state.get("underpaintingAlpha",1)>.001 and browser_info.get("underpainting"):
        # Older partial sessions have no cleanup flag; this validation applies
        # only when the final artwork has a cleanup chapter.
        if any(c.get("kind")=="clean" for c in page_chapters):
            raise RuntimeError("Transient underpainting was still visible in the final frame")

    report = {
        "status":"PASS",
        "output":str(output),"html":str(html),"session":str(session),
        "session_sha256":original_sha,"sample":args.seconds is not None,
        "capture_start_seconds":args.start,"expected_video_seconds":duration,
        "captured_webm_codec":webm_codec,"captured_webm_bytes":bytes_received,
        "captured_chunks":chunks_received,"fps_requested":args.fps,
        "expected_sketch_strokes":browser_info["strokes"],
        "expected_underpainting_paths":browser_info["underpainting"],
        "expected_final_svg_paths":browser_info["paths"],
        "expected_total_paint_operations":browser_info["operations"],
        "expected_total_drawing_operations":browser_info["strokes"]+browser_info["operations"],
        "final_state":final_state,
        "ffmpeg_exit_code":result.returncode,
        "ffmpeg_command":encoding,
        "ffmpeg_video":probe_result,
        "elapsed_wall_seconds":round(time.monotonic()-start_time,1),
        "browser_errors":error_messages,
    }
    report_path = output.with_suffix(".report.json")
    report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"event":"completed","report":str(report_path),
                      "mp4":str(output),"video":probe_result},ensure_ascii=False),flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html",type=Path,default=DEFAULT_HTML)
    parser.add_argument("--output",type=Path,default=DEFAULT_MP4)
    parser.add_argument("--session",type=Path,default=DEFAULT_SESSION)
    parser.add_argument("--expect-paths",type=int,default=None,
                        help="Require this many FINAL SVG paths (e.g. 1600)")
    parser.add_argument("--expect-underpainting",type=int,default=None)
    parser.add_argument("--seconds",type=float,default=None,
                        help="Test mode: record only this many seconds; default captures the entire session")
    parser.add_argument("--start",type=float,default=0,
                        help="Timeline start for a sample; default 0")
    parser.add_argument("--fps",type=int,default=24)
    parser.add_argument("--bitrate",type=int,default=12_000_000)
    parser.add_argument("--preset",choices=("ultrafast","superfast","veryfast","faster","fast","medium","slow"),default="fast")
    parser.add_argument("--crf",type=int,default=18)
    parser.add_argument("--overwrite",action="store_true")
    parser.add_argument("--keep-webm",action="store_true")
    parser.add_argument("--headful",action="store_true")
    args=parser.parse_args()
    if args.seconds is not None and args.seconds<=0:
        parser.error("--seconds must be positive")
    if args.start<0 or args.fps<=0 or not 0<=args.crf<=51:
        parser.error("--start, --fps, or --crf out of range")
    record(args)


if __name__=="__main__":
    main()
