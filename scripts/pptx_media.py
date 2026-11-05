#!/usr/bin/env python3
"""Local media slots for pptx_engine; no network or raster drawing dependencies.

Video OOXML follows the embedded MP4 in the supplied Lesson01 slide 10 and
Microsoft's Open XML example:
https://learn.microsoft.com/en-us/office/open-xml/presentation/how-to-add-a-video-to-a-slide-in-a-presentation
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zlib

P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
MEDIA_TYPE = "http://schemas.microsoft.com/office/2007/relationships/media"
MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".mp4": "video/mp4"}


def profile_check(definition, error):
    slots = definition.get("media_slots", {})
    if not isinstance(slots, dict):
        raise error("media_slots must be an object")
    text_ids = {str(s["shape_id"]) for s in definition.get("slots", {}).values()}
    ids = set()
    for name, slot in slots.items():
        if not isinstance(slot, dict) or "shape_id" not in slot:
            raise error(f"Media slot {name}: shape_id required")
        sid = str(slot["shape_id"])
        if sid in ids or sid in text_ids:
            raise error(f"Media slot {name}: duplicate or text-slot shape_id")
        ids.add(sid)
        if slot.get("kind") not in {"image", "video"} or slot.get("fit", "contain") not in {"contain", "cover"}:
            raise error(f"Media slot {name}: expected image/video and contain/cover")
        if not isinstance(slot.get("required", True), bool):
            raise error(f"Media slot {name}: required must be boolean")
        caption = slot.get("pending_caption_slot")
        if caption is not None and (caption not in definition.get("slots", {}) or definition["slots"][caption].get("auto")):
            raise error(f"Media slot {name}: pending_caption_slot must name a supplied text slot")


def picture(e, root, sid):
    candidates = [p for p in root.findall("p:cSld/p:spTree/p:pic", e.NS)
                  if p.find("p:nvPicPr/p:cNvPr", e.NS) is not None
                  and p.find("p:nvPicPr/p:cNvPr", e.NS).get("id") == str(sid)]
    if len(candidates) != 1:
        raise e.DeckError(f"Media shape {sid}: expected one p:pic directly in spTree")
    return candidates[0]


def rectangle(e, pic):
    transform = pic.find("p:spPr/a:xfrm", e.NS)
    if transform is None or any(transform.get(a, "0") not in {"0", "false"} for a in ["rot", "flipH", "flipV"]):
        raise e.DeckError("Media placeholder needs unrotated, unflipped a:xfrm")
    off, ext = transform.find("a:off", e.NS), transform.find("a:ext", e.NS)
    if off is None or ext is None:
        raise e.DeckError("Media placeholder needs offset and extent")
    box = tuple(int(x) for x in [off.get("x"), off.get("y"), ext.get("cx"), ext.get("cy")])
    if box[2] <= 0 or box[3] <= 0:
        raise e.DeckError("Media placeholder has nonpositive extent")
    return box


def check_placeholders(e, root, definition):
    for name, spec in definition.get("media_slots", {}).items():
        pic = picture(e, root, spec["shape_id"])
        box = rectangle(e, pic)
        if spec.get("rect_emu") is not None and list(box) != spec["rect_emu"]:
            raise e.DeckError(f"Media slot {name}: placeholder bounds differ from rect_emu")
        if pic.find("p:blipFill/a:blip", e.NS) is None:
            raise e.DeckError(f"Media slot {name}: placeholder needs a static image")
        if pic.find(".//a:videoFile", e.NS) is not None:
            raise e.DeckError(f"Media slot {name}: use a static p:pic placeholder, not source video")


def local_path(value, base, error):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise error("Media path must be a nonempty local path")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("//"):
        raise error("Media URLs are unsupported; supply a local file")
    path = Path(value).expanduser()
    if not path.is_absolute():
        if base is None:
            raise error("Relative media path needs the content file directory")
        path = Path(base) / path
    path = path.resolve()
    if not path.is_file():
        raise error(f"Media file does not exist: {path}")
    return path


def image_info(path, error):
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        offset, width, height, ended, compressed = 8, None, None, False, False
        header, idat, palette = None, [], False
        while offset + 12 <= len(data):
            size = struct.unpack(">I", data[offset:offset + 4])[0]
            kind = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + size]
            if offset + 12 + size > len(data):
                raise error(f"Truncated PNG: {path}")
            crc = struct.unpack(">I", data[offset + 8 + size:offset + 12 + size])[0]
            if zlib.crc32(kind + payload) & 0xffffffff != crc:
                raise error(f"PNG chunk CRC mismatch: {path}")
            if kind == b"IHDR":
                if offset != 8 or size != 13:
                    raise error(f"Invalid PNG header: {path}")
                width, height = struct.unpack(">II", payload[:8])
                header = payload
            if kind == b"IDAT":
                idat.append(payload)
            if kind == b"PLTE":
                if size == 0 or size % 3 or size > 768:
                    raise error(f"Invalid PNG palette: {path}")
                palette = True
            compressed |= kind == b"IDAT"
            offset += size + 12
            if kind == b"IEND":
                ended = True
                break
        if not width or not height or not ended or not compressed:
            raise error(f"Incomplete PNG: {path}")
        if offset != len(data):
            raise error(f"Unexpected data after PNG end: {path}")
        bit_depth, colour, compression, filtering, interlace = header[8:13]
        depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
        if colour not in depths or bit_depth not in depths[colour] or compression or filtering or interlace not in {0, 1}:
            raise error(f"Unsupported PNG header: {path}")
        if colour == 3 and not palette:
            raise error(f"Indexed PNG has no palette: {path}")
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
        passes = [(0, 0, 1, 1)] if not interlace else [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
        rows = []
        for x, y, step_x, step_y in passes:
            pass_width = max(0, (width - x + step_x - 1) // step_x)
            pass_height = max(0, (height - y + step_y - 1) // step_y)
            if pass_width and pass_height:
                rows.append(((pass_width * channels * bit_depth + 7) // 8 + 1, pass_height))
        expected_bytes = sum(size * count for size, count in rows)
        if expected_bytes > 512 * 1024 * 1024:
            raise error("PNG decoded payload exceeds 512 MiB; downscale the image")
        try:
            decoder = zlib.decompressobj()
            pixels = decoder.decompress(b"".join(idat), expected_bytes + 1)
        except zlib.error:
            raise error(f"PNG has an invalid compressed pixel stream: {path}")
        if len(pixels) != expected_bytes or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise error(f"PNG decoded scanline dimensions are invalid: {path}")
        cursor = 0
        for row_size, count in rows:
            for row in range(count):
                if pixels[cursor] > 4:
                    raise error(f"PNG has an invalid scanline filter: {path}")
                cursor += row_size
        extension = ".png"
    elif data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
        offset, width, height = 2, None, None
        while offset + 4 <= len(data):
            if data[offset] != 255:
                break
            while offset < len(data) and data[offset] == 255:
                offset += 1
            marker = data[offset]
            offset += 1
            if marker in {0xda, 0xd9}:
                break
            if marker in range(0xd0, 0xd9) or marker == 1:
                continue
            size = struct.unpack(">H", data[offset:offset + 2])[0]
            payload = data[offset + 2:offset + size]
            if size < 2 or offset + size > len(data):
                raise error(f"Truncated JPEG: {path}")
            if marker in {0xc0, 0xc1, 0xc2} and len(payload) >= 5:
                height, width = struct.unpack(">HH", payload[1:5])
            if marker == 0xe1 and payload.startswith(b"Exif\x00\x00"):
                tiff = payload[6:]
                endian = "<" if tiff[:2] == b"II" else ">"
                try:
                    start = struct.unpack(endian + "I", tiff[4:8])[0]
                    count = struct.unpack(endian + "H", tiff[start:start + 2])[0]
                    for n in range(count):
                        entry = tiff[start + 2 + n * 12:start + 14 + n * 12]
                        tag = struct.unpack(endian + "H", entry[:2])[0]
                        if tag == 274 and struct.unpack(endian + "H", entry[8:10])[0] != 1:
                            raise error("Normalize JPEG EXIF rotation before embedding")
                except (struct.error, IndexError):
                    raise error(f"Malformed JPEG EXIF: {path}")
            offset += size
        if not width or not height:
            raise error(f"Unsupported or incomplete JPEG: {path}")
        # JPEG entropy decoding is not available in Python's standard library.
        # Do not treat SOF dimensions and an end marker as a decoded photograph.
        try:
            from PIL import Image, ImageFile
        except ImportError:
            raise error("JPEG validation requires Pillow; install it or supply PNG")
        previous_truncated = ImageFile.LOAD_TRUNCATED_IMAGES
        try:
            ImageFile.LOAD_TRUNCATED_IMAGES = False
            with Image.open(io.BytesIO(data)) as decoded:
                if decoded.format != "JPEG":
                    raise error(f"Image is not a JPEG: {path}")
                decoded.load()
                if decoded.size != (width, height):
                    raise error(f"JPEG decoded dimensions disagree: {path}")
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise error(f"JPEG pixel decoding failed: {path}: {exc}")
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = previous_truncated
        extension = ".jpg"
    else:
        raise error(f"Images/posters must be genuine PNG or JPEG: {path}")
    if path.suffix.lower() not in ({".png"} if extension == ".png" else {".jpg", ".jpeg"}):
        raise error(f"Image extension disagrees with its contents: {path}")
    return {"data": data, "width": width, "height": height, "extension": extension, "path": str(path)}


def video_info(path, ffprobe, error):
    data = path.read_bytes()
    if path.suffix.lower() != ".mp4" or len(data) < 24 or data[4:8] != b"ftyp":
        raise error(f"Video must be a genuine MP4 file: {path}")
    program = str(Path(ffprobe).expanduser().resolve()) if ffprobe else shutil.which("ffprobe")
    if not program or not Path(program).is_file():
        raise error("MP4 video requires ffprobe to verify H.264; install it or pass --ffprobe")
    command = [program, "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=codec_name,width,height,sample_aspect_ratio:stream_tags=rotate:stream_side_data=rotation:format=duration",
               "-of", "json", str(path)]
    try:
        run = subprocess.run(command, capture_output=True, text=True, timeout=30)
        report = json.loads(run.stdout) if run.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise error(f"ffprobe failed: {exc}")
    streams = report.get("streams", [])
    if len(streams) != 1 or streams[0].get("codec_name") != "h264":
        raise error(f"MP4 video must contain an H.264 video stream: {path}")
    stream = streams[0]
    width, height = stream.get("width"), stream.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or min(width, height) <= 0:
        raise error(f"MP4 has invalid dimensions: {path}")
    rotation = stream.get("tags", {}).get("rotate", "0")
    rotations = [rotation] + [s.get("rotation", 0) for s in stream.get("side_data_list", [])]
    try:
        rotated = any(float(r) % 360 != 0 for r in rotations)
    except (ValueError, TypeError):
        raise error("Video rotation metadata is invalid")
    if rotated or stream.get("sample_aspect_ratio", "1:1") not in {"1:1", "N/A"}:
        raise error("Normalize video rotation and pixel aspect ratio before embedding")
    return {"data": data, "width": width, "height": height, "extension": ".mp4", "path": str(path),
            "codec": "h264", "codec_verified_by": str(Path(program).resolve()), "duration_seconds": report.get("format", {}).get("duration")}


def resolve_all(e, profile, content, base=None, allow_pending=False, ffprobe=None):
    plans, assets, pending, reports = [], {}, [], []
    for page, slide in enumerate(content["slides"], 1):
        specs = profile["layouts"][slide["layout"]].get("media_slots", {})
        supplied = slide.get("media", {})
        if not isinstance(supplied, dict) or set(supplied) - set(specs):
            raise e.DeckError(f"Slide {page}: unknown media slot or invalid media object")
        plan = {}
        for name, spec in specs.items():
            if name not in supplied:
                if spec.get("required", True):
                    raise e.DeckError(f"Slide {page}/{name}: required media is missing; declare planned media explicitly for drafts")
                continue
            item = supplied[name]
            if not isinstance(item, dict):
                raise e.DeckError(f"Slide {page}/{name}: media entry must be an object")
            alt = item.get("alt")
            if not isinstance(alt, str) or not alt.strip() or len(alt) > 1000 or any(ord(c) < 32 for c in alt):
                raise e.DeckError(f"Slide {page}/{name}: a nonblank alt text of at most 1000 characters is required")
            if item.get("status") == "planned":
                if set(item) != {"status", "prompt", "alt"} or not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
                    raise e.DeckError(f"Slide {page}/{name}: planned media needs exactly status, prompt and alt")
                if not allow_pending:
                    raise e.DeckError(f"Slide {page}/{name}: planned media requires --allow-pending-media; this is not a finished deck")
                caption_slot = spec.get("pending_caption_slot")
                if not caption_slot:
                    raise e.DeckError(f"Slide {page}/{name}: planned media requires media_slots.{name}.pending_caption_slot to name a visible text slot")
                marker = "待补图片" if spec["kind"] == "image" else "待补视频"
                caption = slide["slots"].get(caption_slot, "")
                if not isinstance(caption, str) or not caption.startswith(marker):
                    raise e.DeckError(f"Slide {page}/{name}: visible text slot {caption_slot!r} must start with {marker!r} for planned media")
                plan[name] = {"pending": True, "alt": alt, "prompt": item["prompt"]}
                pending.append({"slide": page, "slot": name, "kind": spec["kind"], "prompt": item["prompt"]})
                continue
            expected = {"path", "alt", "poster"} if spec["kind"] == "video" else {"path", "alt"}
            if set(item) != expected:
                raise e.DeckError(f"Slide {page}/{name}: expected media keys {sorted(expected)}")
            path = local_path(item["path"], base, e.DeckError)
            primary = image_info(path, e.DeckError) if spec["kind"] == "image" else video_info(path, ffprobe, e.DeckError)
            record = {"pending": False, "alt": alt, "primary": primary}
            if spec["kind"] == "video":
                poster = image_info(local_path(item["poster"], base, e.DeckError), e.DeckError)
                if abs((poster["width"] / poster["height"]) / (primary["width"] / primary["height"]) - 1) > 0.02:
                    raise e.DeckError(f"Slide {page}/{name}: poster aspect ratio must match the video within 2 percent")
                record["poster"] = poster
            for role in ["primary", "poster"]:
                if role not in record:
                    continue
                media = record[role]
                media["part"] = "ppt/media/course-" + hashlib.sha256(media["data"]).hexdigest() + media["extension"]
                assets[media["part"]] = media["data"]
            plan[name] = record
            reports.append({"slide": page, "slot": name, "kind": spec["kind"], "fit": spec.get("fit", "contain"),
                            "sha256": hashlib.sha256(primary["data"]).hexdigest(),
                            **({"codec": "h264", "codec_verified_by": primary["codec_verified_by"], "poster_sha256": hashlib.sha256(record["poster"]["data"]).hexdigest()} if spec["kind"] == "video" else {})})
        plans.append(plan)
    return {"slides": plans, "assets": assets, "pending": pending, "embedded": reports}


def fit_picture(e, pic, width, height, fit):
    x, y, box_width, box_height = rectangle(e, pic)
    transform = pic.find("p:spPr/a:xfrm", e.NS)
    crop = {}
    if fit == "contain":
        scale = min(box_width / width, box_height / height)
        new_width, new_height = round(width * scale), round(height * scale)
        x += (box_width - new_width) // 2
        y += (box_height - new_height) // 2
    else:
        new_width, new_height = box_width, box_height
        ratio, box_ratio = width / height, box_width / box_height
        if ratio > box_ratio:
            crop["l"] = crop["r"] = str(round((1 - box_ratio / ratio) * 50000))
        elif ratio < box_ratio:
            crop["t"] = crop["b"] = str(round((1 - ratio / box_ratio) * 50000))
    transform.find("a:off", e.NS).attrib.update(x=str(x), y=str(y))
    transform.find("a:ext", e.NS).attrib.update(cx=str(new_width), cy=str(new_height))
    fill = pic.find("p:blipFill", e.NS)
    for child in list(fill):
        if child.tag != f"{{{e.A}}}blip":
            fill.remove(child)
    if crop:
        ET.SubElement(fill, f"{{{e.A}}}srcRect", crop)
    ET.SubElement(ET.SubElement(fill, f"{{{e.A}}}stretch"), f"{{{e.A}}}fillRect")


def add_video_timing(e, root, sid):
    timing = root.find("p:timing", e.NS)
    used = [int(n.get("id")) for n in root.findall(".//p:cTn", e.NS)]
    next_id = max(used, default=0) + 1
    def tn(parent, attrs):
        nonlocal next_id
        node = ET.SubElement(parent, f"{{{e.P}}}cTn", {"id": str(next_id), **attrs})
        next_id += 1
        return node
    if timing is None:
        timing = ET.Element(f"{{{e.P}}}timing")
        # p:timing precedes p:extLst in the slide schema.
        ext = root.find("p:extLst", e.NS)
        root.insert(list(root).index(ext) if ext is not None else len(root), timing)
        tn_list = ET.SubElement(timing, f"{{{e.P}}}tnLst")
        main = tn(ET.SubElement(tn_list, f"{{{e.P}}}par"), {"dur": "indefinite", "restart": "never", "nodeType": "tmRoot"})
    else:
        main = next((n for n in timing.findall(".//p:cTn", e.NS) if n.get("nodeType") == "tmRoot"), None)
        if main is None:
            raise e.DeckError("Existing timing has no tmRoot; use a static media template")
    children = main.find("p:childTnLst", e.NS)
    if children is None:
        children = ET.SubElement(main, f"{{{e.P}}}childTnLst")
    video = ET.SubElement(children, f"{{{e.P}}}video", {"fullScrn": "0"})
    media = ET.SubElement(video, f"{{{e.P}}}cMediaNode")
    node = tn(media, {"fill": "hold", "display": "1"})
    ET.SubElement(ET.SubElement(node, f"{{{e.P}}}stCondLst"), f"{{{e.P}}}cond", {"delay": "indefinite"})
    ET.SubElement(ET.SubElement(media, f"{{{e.P}}}tgtEl"), f"{{{e.P}}}spTgt", {"spid": str(sid)})
    sequence = tn(ET.SubElement(children, f"{{{e.P}}}seq", {"concurrent": "1", "nextAc": "seek"}),
                  {"restart": "whenNotActive", "fill": "hold", "evtFilter": "cancelBubble", "nodeType": "interactiveSeq"})
    # Keep the source native media action and avoid adding a second click
    # trigger. This matches Lesson01 slide10 without assuming a WPS root cause.
    ET.SubElement(ET.SubElement(sequence, f"{{{e.P}}}endSync", {"evt": "end", "delay": "0"}), f"{{{e.P}}}rtn", {"val": "all"})
    parent = sequence
    for level in range(3):
        parent = tn(ET.SubElement(ET.SubElement(parent, f"{{{e.P}}}childTnLst"), f"{{{e.P}}}par"),
                    {"fill": "hold", **({"presetID": "2", "presetClass": "mediacall", "presetSubtype": "0", "nodeType": "clickEffect"} if level == 2 else {})})
        ET.SubElement(ET.SubElement(parent, f"{{{e.P}}}stCondLst"), f"{{{e.P}}}cond", {"delay": "0"})
    command = ET.SubElement(ET.SubElement(parent, f"{{{e.P}}}childTnLst"), f"{{{e.P}}}cmd", {"type": "call", "cmd": "togglePause"})
    behavior = ET.SubElement(command, f"{{{e.P}}}cBhvr", {"additive": "base"})
    tn(behavior, {"dur": "1", "fill": "hold"})
    ET.SubElement(ET.SubElement(behavior, f"{{{e.P}}}tgtEl"), f"{{{e.P}}}spTgt", {"spid": str(sid)})


def apply_slide(e, root, original_rels, definition, plan, slide_name):
    check_placeholders(e, root, definition)
    relroot = e.parse(original_rels) if original_rels else ET.Element(f"{{{e.PKG}}}Relationships")
    used = {n.get("Id") for n in relroot}
    counter = 1
    def relationship(kind, part):
        nonlocal counter
        while f"rIdCourse{counter}" in used:
            counter += 1
        rid = f"rIdCourse{counter}"
        counter += 1
        used.add(rid)
        ET.SubElement(relroot, f"{{{e.PKG}}}Relationship", {"Id": rid, "Type": kind, "Target": e.relative_target(slide_name, part)})
        return rid
    for name, record in plan.items():
        spec = definition["media_slots"][name]
        pic = picture(e, root, spec["shape_id"])
        nonvisual = pic.find("p:nvPicPr/p:cNvPr", e.NS)
        nonvisual.set("descr", ("[Pending media] " if record["pending"] else "") + record["alt"])
        if record["pending"]:
            continue
        primary = record["primary"]
        poster = record.get("poster", primary)
        image_rid = relationship(e.R + "/image", poster["part"])
        blip = pic.find("p:blipFill/a:blip", e.NS)
        blip.attrib.clear()
        blip.set(f"{{{e.R}}}embed", image_rid)
        # Ignore source image adjustment extensions; do not accidentally apply
        # a placeholder tint or local-DPI hint to a replacement source image.
        blip[:] = []
        fit_picture(e, pic, primary["width"], primary["height"], spec.get("fit", "contain"))
        if spec["kind"] == "video":
            for child in list(nonvisual):
                if child.tag in {f"{{{e.A}}}hlinkClick", f"{{{e.A}}}hlinkMouseOver"}:
                    nonvisual.remove(child)
            click = ET.Element(f"{{{e.A}}}hlinkClick", {f"{{{e.R}}}id": "", "action": "ppaction://media"})
            nonvisual.insert(0, click)
            properties = pic.find("p:nvPicPr/p:nvPr", e.NS)
            if properties is None:
                properties = ET.SubElement(pic.find("p:nvPicPr", e.NS), f"{{{e.P}}}nvPr")
            video_rid = relationship(e.R + "/video", primary["part"])
            media_rid = relationship(MEDIA_TYPE, primary["part"])
            video_file = ET.Element(f"{{{e.A}}}videoFile", {f"{{{e.R}}}link": video_rid})
            # CT_ApplicationNonVisualDrawingProps orders media before custData
            # and extensions. Retain any unrelated placeholder extensions.
            insert_at = next((i for i, child in enumerate(properties) if child.tag in {f"{{{e.P}}}custDataLst", f"{{{e.P}}}extLst"}), len(properties))
            properties.insert(insert_at, video_file)
            extensions = properties.find("p:extLst", e.NS)
            if extensions is None:
                extensions = ET.SubElement(properties, f"{{{e.P}}}extLst")
            extension = ET.SubElement(extensions, f"{{{e.P}}}ext", {"uri": "{DAA4B4D4-6D71-4841-9C94-3DE7FCFB9230}"})
            ET.SubElement(extension, f"{{{P14}}}media", {f"{{{e.R}}}embed": media_rid})
            add_video_timing(e, root, spec["shape_id"])
    referenced = {value for element in root.iter() for key, value in element.attrib.items() if key.startswith("{" + e.R + "}")}
    for rel in list(relroot):
        if rel.get("Id") not in referenced and rel.get("Type") in {e.R + "/image", e.R + "/video", MEDIA_TYPE}:
            relroot.remove(rel)
    return e.xml_bytes(relroot, original_rels)
