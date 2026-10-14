"""Build one self-contained, offline vector drawing player from a session snapshot.

Examples:
  python build_player.py
  python build_player.py --output recording/player-tests/partial.html --duration 28

The generated HTML contains the complete SVG-path session as JSON; it does not
fetch fonts, scripts, images, or the original raster illustration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SESSION = ROOT / "recording" / "session.json"
TEMPLATE = ROOT / "player-template.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, default=SESSION)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "miku-drawing-player.html")
    parser.add_argument("--duration", type=float, default=292,
                        help="Playback duration in seconds, including the final hold (default: 292)")
    parser.add_argument("--title", default="하츠네 미쿠 | 벡터 드로잉 과정")
    args = parser.parse_args()
    if args.duration < 6:
        parser.error("--duration must be at least 6 seconds")

    session_bytes = args.session.read_bytes()
    session = json.loads(session_bytes.decode("utf-8"))
    for key in ("width", "height", "batches", "strokes", "paths"):
        if key not in session:
            parser.error(f"Missing session property: {key}")
    if not session["strokes"] and not session["paths"]:
        parser.error("No strokes or paths in recording session")
    if session["width"] <= 0 or session["height"] <= 0:
        parser.error("Invalid artwork dimensions")

    # Preserve everything needed for Path2D playback. Contour polygons and the
    # optimization trace belong in source session.json; embedding them would
    # double an already sizable, high-detail standalone HTML's data payload.
    paint_fields = ("id", "d", "rgb", "bounds", "area", "batch", "stroke_width")
    stroke_fields = ("id", "d", "width", "batch", "type")
    batch_fields = ("id", "title", "decision", "total_paths")
    embedded = {
        "width": session["width"],
        "height": session["height"],
        "strokes": [{key: stroke[key] for key in stroke_fields if key in stroke}
                    for stroke in session["strokes"]],
        "underpainting": [{key: path[key] for key in paint_fields if key in path}
                          for path in session.get("underpainting", [])],
        "paths": [{key: path[key] for key in paint_fields if key in path}
                  for path in session["paths"]],
        "batches": [{key: batch[key] for key in batch_fields if key in batch}
                    for batch in session["batches"]],
        "finish_underpainting": bool(session.get("finish_underpainting", False)),
    }
    config = {
        "title": args.title,
        "duration": args.duration,
        "session_sha256": hashlib.sha256(session_bytes).hexdigest(),
        "source": "https://piapro.net/intl/en_character.html",
    }
    # Script data is deliberately escaped to avoid ending a script tag.
    data_json = json.dumps(embedded, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = TEMPLATE.read_text(encoding="utf-8")
    for marker in ("__EMBEDDED_SESSION_JSON__", "__PLAYER_CONFIGURATION_JSON__"):
        if template.count(marker) != 1:
            parser.error(f"Template marker must occur once: {marker}")
    html = template.replace("__EMBEDDED_SESSION_JSON__", data_json).replace("__PLAYER_CONFIGURATION_JSON__", config_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(json.dumps({
        "html": str(args.output.resolve()),
        "seconds": args.duration,
        "batches": len(session["batches"]),
        "sketch_strokes": len(session["strokes"]),
        "underpainting_ops": len(session.get("underpainting", [])),
        "colored_paths": len(session["paths"]),
        "total_paint_ops": len(session.get("underpainting", []))+len(session["paths"]),
        "html_size_bytes": args.output.stat().st_size,
        "session_sha256": config["session_sha256"],
        "offline": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
