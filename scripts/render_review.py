#!/usr/bin/env python3
"""Render a PPTX for human review without editing its content or source fonts.

LibreOffice and Poppler must be available. Pillow is optional (contact sheet).
All paths and renderer/font substitutions are recorded in review.json.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
NS = {"p": P, "a": A, "r": R, "p14": P14}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preserve_namespaces(root: ET.Element, original: bytes) -> bytes:
    """Retain namespace declarations referenced by mc:Ignorable string values."""
    from xml.sax.saxutils import quoteattr
    declarations = list(dict.fromkeys(item for _, item in ET.iterparse(io.BytesIO(original), events=("start-ns",))))
    for prefix, uri in declarations:
        if not re.fullmatch(r"ns\d+", prefix):
            ET.register_namespace(prefix, uri)
    result = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    start = result.find(b"?>") + 2
    close = result.find(b">", start)
    tag = result[start:close]
    extra = []
    for prefix, uri in declarations:
        name = "xmlns:" + prefix if prefix else "xmlns"
        if not re.search(rb"\s" + re.escape(name.encode()) + rb"=", tag):
            extra.append(" " + name + "=" + quoteattr(uri))
    return result[:close] + "".join(extra).encode() + result[close:]


def poster_only_copy(source: Path, target: Path) -> dict:
    """Make a separate QA input with native movie pictures left as their posters.

    Unused embedded movie parts remain in this private copy. Only the affected
    slide XML/relationships are changed; the original PPTX is never written.
    """
    from urllib.parse import unquote, urlsplit
    if source.resolve() == target.resolve():
        raise ValueError("Poster-only QA input must differ from the original PPTX")
    changes, converted = {}, []
    with zipfile.ZipFile(source) as package:
        names = set(package.namelist())
        if len(names) != len(package.namelist()):
            raise ValueError("PPTX has duplicate ZIP entries")
        bad = package.testzip()
        if bad:
            raise ValueError(f"PPTX has a corrupt entry: {bad}")
        for name in sorted(names):
            if not re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                continue
            original = package.read(name)
            root = ET.fromstring(original)
            video_pictures = [pic for pic in root.findall(".//p:pic", NS)
                              if pic.find(".//a:videoFile", NS) is not None or pic.find(".//p14:media", NS) is not None]
            if not video_pictures:
                if root.find(".//a:videoFile", NS) is not None or root.find(".//p14:media", NS) is not None:
                    raise ValueError(f"Unsupported native video outside a picture object: {name}")
                continue
            directory, filename = posixpath.split(name)
            relation_name = posixpath.join(directory, "_rels", filename + ".rels")
            if relation_name not in names:
                raise ValueError(f"Native video slide has no relationships: {name}")
            relation_bytes = package.read(relation_name)
            relations = ET.fromstring(relation_bytes)
            relation_ids = {rel.get("Id"): rel for rel in relations}
            removed_ids, shape_ids, posters = set(), [], []
            for pic in video_pictures:
                metadata = pic.find("p:nvPicPr/p:cNvPr", NS)
                shape_ids.append(metadata.get("id") if metadata is not None else "unknown")
                blip = pic.find("p:blipFill/a:blip", NS)
                poster_id = blip.get(f"{{{R}}}embed") if blip is not None else None
                poster_rel = relation_ids.get(poster_id)
                if poster_rel is None or poster_rel.get("Type") != R + "/image" or poster_rel.get("TargetMode") == "External":
                    raise ValueError(f"Native video needs an embedded image poster: {name}")
                raw_target = poster_rel.get("Target", "")
                parsed = urlsplit(raw_target)
                if parsed.scheme or parsed.netloc or "\\" in raw_target:
                    raise ValueError(f"Video poster must be an internal image part: {name}")
                relative = unquote(parsed.path)
                poster = posixpath.normpath(relative.lstrip("/") if relative.startswith("/") else posixpath.join(directory, relative))
                if poster.startswith("../") or poster not in names:
                    raise ValueError(f"Video poster image is missing: {name}")
                with package.open(poster) as image:
                    signature = image.read(8)
                if not (signature.startswith(b"\x89PNG\r\n\x1a\n") or signature.startswith(b"\xff\xd8")):
                    raise ValueError(f"Video poster is not PNG/JPEG: {name}")
                posters.append(poster)
                for parent in pic.iter():
                    for child in list(parent):
                        if child.tag in {f"{{{A}}}videoFile", f"{{{P14}}}media"}:
                            removed_ids.update(value for key, value in child.attrib.items() if key.startswith("{" + R + "}"))
                            parent.remove(child)
                # A video picture's click action must not keep invoking a
                # removed player. Other picture objects keep their actions.
                for parent in pic.iter():
                    for child in list(parent):
                        if child.tag == f"{{{A}}}hlinkClick" or (child.tag == f"{{{A}}}hlinkMouseOver" and "media" in child.get("action", "")):
                            rid = child.get(f"{{{R}}}id")
                            if rid:
                                removed_ids.add(rid)
                            parent.remove(child)
                # Drop only emptied extension wrappers, never geometry a:ext.
                for parent in reversed(list(pic.iter())):
                    for child in list(parent):
                        if not len(child) and not (child.text or "").strip() and (
                            child.tag.rsplit("}", 1)[-1] == "extLst"
                            or child.tag.rsplit("}", 1)[-1] == "ext" and child.get("uri") is not None
                        ):
                            parent.remove(child)
            timing_removed = False
            for timing in root.findall("p:timing", NS):
                root.remove(timing)
                timing_removed = True
            still_used = {value for element in root.iter() for key, value in element.attrib.items()
                          if key.startswith("{" + R + "}") and value}
            cleaned = 0
            for relation in list(relations):
                if relation.get("Id") in removed_ids - still_used:
                    relations.remove(relation)
                    cleaned += 1
            if root.find(".//a:videoFile", NS) is not None or root.find(".//p14:media", NS) is not None:
                raise ValueError(f"Unconverted native video remains on {name}")
            changes[name] = preserve_namespaces(root, original)
            if cleaned:
                changes[relation_name] = preserve_namespaces(relations, relation_bytes)
            converted.append({"slide_part": name, "video_shape_ids": shape_ids, "poster_parts": posters,
                              "slide_animation_timing_removed": timing_removed, "relationships_removed": cleaned})
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w") as output:
            for info in package.infolist():
                if info.filename in changes:
                    output.writestr(info, changes[info.filename])
                else:
                    with package.open(info) as original_part, output.open(info, "w") as copied_part:
                        shutil.copyfileobj(original_part, copied_part)
    return {"mode": "video-posters-only", "video_objects_converted": sum(len(x["video_shape_ids"]) for x in converted),
            "converted_slides": converted,
            "note": "Static video-poster preview only. Does not test or prove video playback; original PPTX is unchanged."}


def executable(name: str, explicit: str | None = None) -> str:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Executable does not exist: {path}")
        return str(path)
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    candidates = [
        home / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override" / name,
        home / ".dsh/dsh-runtimes/dsh-primary-runtime/dependencies/bin/override" / name,
        Path("/opt/homebrew/bin") / name,
        Path("/usr/bin") / name,
    ]
    if name == "soffice":
        candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise ValueError(f"Missing {name}; install LibreOffice/Poppler or pass --{name}.")


def pages_arg(value: str | None) -> list[int] | None:
    if value is None:
        return None
    pages: set[int] = set()
    for item in value.split(","):
        if not re.fullmatch(r"\d+(?:-\d+)?", item):
            raise ValueError("--pages accepts page numbers/ranges, e.g. 1,3-5")
        first, _, last = item.partition("-")
        start, end = int(first), int(last or first)
        if start < 1 or end < start or end > 10000:
            raise ValueError("Invalid page range")
        pages.update(range(start, end + 1))
    return sorted(pages)


def fonts_config(out: Path, font_file: str | None) -> dict:
    """Use local font data only. Font aliases affect previews, never the PPTX."""
    folders = [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
               Path("/Library/Fonts"), Path.home() / "Library/Fonts",
               Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
               Path.home() / ".local/share/fonts"]
    chosen: Path | None = None
    if font_file:
        chosen = Path(font_file).expanduser().resolve()
        if not chosen.is_file():
            raise ValueError(f"Font file does not exist: {chosen}")
    elif sys.platform == "darwin":
        chosen = next(Path("/System/Library/AssetsV2").glob(
            "com_apple_MobileAsset_Font*/**/PingFang.ttc"), None)
    if chosen:
        folders.append(chosen.parent)
    root = ET.Element("fontconfig")
    for directory in dict.fromkeys(folders):
        if directory.is_dir():
            ET.SubElement(root, "dir").text = str(directory)
    ET.SubElement(root, "cachedir").text = str(out / ".fontcache")
    # Exact source fonts take precedence if installed. These aliases only add
    # fallbacks so headless renderers do not silently omit Chinese glyphs.
    families = ("微软雅黑", "Microsoft YaHei", "HarmonyOS Sans SC", "sans-serif")
    fallback = ["PingFang SC", "Heiti SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "Arial Unicode MS"]
    for family in families:
        alias = ET.SubElement(root, "alias")
        ET.SubElement(alias, "family").text = family
        prefer = ET.SubElement(alias, "prefer")
        for name in fallback:
            ET.SubElement(prefer, "family").text = name
    target = out / "fonts.conf"
    target.write_bytes(b'<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
                       + ET.tostring(root, encoding="utf-8"))
    return {
        "config": str(target),
        "local_font_file": str(chosen) if chosen else None,
        "fallback_families": fallback,
        "note": "Preview may substitute missing fonts. Source PPTX fonts are unchanged; verify target-app appearance separately.",
    }


def run(command: list[str], env: dict, timeout: int) -> str:
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} exited {result.returncode}: "
                           f"{result.stderr[-3000:]} {result.stdout[-1000:]}")
    return result.stdout + result.stderr


def page_number(path: Path) -> int:
    return int(path.stem.rsplit("-", 1)[1])


def contact_sheet(pngs: list[Path], out: Path) -> str | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    width, height, label = 560, 315, 26
    columns = 2 if len(pngs) > 1 else 1
    rows = (len(pngs) + columns - 1) // columns
    # A contact sheet is a composition of existing slide renders, not artwork.
    sheet = Image.new("RGB", (width * columns, (height + label) * rows), "#E8E8E8")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(pngs):
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((width, height))
        x = (index % columns) * width
        y = (index // columns) * (height + label)
        draw.text((x + 8, y + 6), f"Slide {page_number(path)}", fill="black")
        sheet.paste(thumb, (x, y + label))
    target = out / "contact-sheet.png"
    sheet.save(target)
    return str(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", help="PPTX to inspect (never modified)")
    parser.add_argument("--out", help="Review directory; default: <stem>-review")
    parser.add_argument("--pages", help="Optional 1-based pages/ranges, e.g. 1,3-5")
    parser.add_argument("--font-file", help="Optional local font file to expose to Fontconfig")
    parser.add_argument("--video-posters", action="store_true",
                        help="Render native movie posters from a separate static QA copy; does not test playback")
    parser.add_argument("--soffice", help="LibreOffice executable")
    parser.add_argument("--pdftoppm", help="Poppler pdftoppm executable")
    parser.add_argument("--size", type=int, default=1400, help="Longest PNG edge in pixels")
    parser.add_argument("--timeout", type=int, default=240, help="Per-renderer timeout in seconds")
    args = parser.parse_args()
    source = Path(args.pptx).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pptx":
        raise ValueError(f"Input must be an existing .pptx file: {source}")
    if not 300 <= args.size <= 5000 or not 10 <= args.timeout <= 1800:
        raise ValueError("--size must be 300–5000; --timeout must be 10–1800")
    pages = pages_arg(args.pages)
    out = Path(args.out).expanduser().resolve() if args.out else source.with_name(source.stem + "-review")
    out.mkdir(parents=True, exist_ok=True)
    # Distinct conversion directory prevents collisions with a source PDF or
    # stale PNGs in previous reviews. Only this run's paths enter review.json.
    render_dir = Path(tempfile.mkdtemp(prefix="render-", dir=out))
    font_info = fonts_config(out, args.font_file)
    env = os.environ.copy()
    env["FONTCONFIG_FILE"] = font_info["config"]
    soffice, poppler = executable("soffice", args.soffice), executable("pdftoppm", args.pdftoppm)
    render_input = source
    poster_review = None
    source_hash = file_sha256(source) if args.video_posters else None
    if args.video_posters:
        render_input = render_dir / "poster-only-input" / source.name
        poster_review = poster_only_copy(source, render_input)
        print("Static video-poster preview only; this does not test playback. Original PPTX remains unchanged.",
              file=sys.stderr, flush=True)
    print("Rendering PDF with local font fallback…", file=sys.stderr, flush=True)
    with tempfile.TemporaryDirectory(prefix="course-ppt-lo-") as profile:
        log = run([soffice, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless",
                   "--convert-to", "pdf:impress_pdf_Export", "--outdir", str(render_dir), str(render_input)],
                  env, args.timeout)
    pdf = render_dir / (source.stem + ".pdf")
    if not pdf.is_file() or pdf.stat().st_size < 100:
        raise RuntimeError(f"LibreOffice produced no PDF: {log[-2000:]}")
    print("Rendering slide PNGs…", file=sys.stderr, flush=True)
    prefix = render_dir / "slide"
    if pages:
        for page in pages:
            run([poppler, "-f", str(page), "-l", str(page), "-scale-to", str(args.size),
                 "-png", str(pdf), str(prefix)], env, args.timeout)
    else:
        run([poppler, "-scale-to", str(args.size), "-png", str(pdf), str(prefix)], env, args.timeout)
    pngs = sorted(render_dir.glob("slide-*.png"), key=page_number)
    if not pngs or (pages and [page_number(p) for p in pngs] != pages):
        raise RuntimeError("PNG page coverage does not match requested pages")
    sheet = contact_sheet(pngs, render_dir)
    if args.video_posters and file_sha256(source) != source_hash:
        raise RuntimeError("Original PPTX changed during review; cannot attest byte identity")
    report = {
        "source": str(source), "pdf": str(pdf), "rendered_pages": [page_number(p) for p in pngs],
        "pngs": [str(p) for p in pngs], "contact_sheet": sheet,
        "renderer": "LibreOffice + Poppler", "soffice": soffice, "pdftoppm": poppler,
        "fonts": font_info, "human_visual_review_required": True,
        "scope": "Render availability only; does not establish content accuracy, layout quality, or target-app fidelity.",
    }
    if poster_review is not None:
        report.update({"video_poster_review": poster_review, "render_input": str(render_input),
                       "source_sha256": source_hash, "source_unchanged": True,
                       "scope": "Poster-only static QA; does not test or prove video playback. Original PPTX byte identity verified."})
    report_path = out / "review.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"review": str(report_path), "pages": len(pngs), "contact_sheet": sheet}
    if poster_review is not None:
        summary.update({"preview_mode": "video-posters-only", "video_objects_converted": poster_review["video_objects_converted"],
                        "source_unchanged": True, "playback_tested": False,
                        "note": "Static video posters only; does not prove playback."})
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError, zipfile.BadZipFile, ET.ParseError) as error:
        print(f"Review failed: {error}", file=sys.stderr)
        raise SystemExit(1)
