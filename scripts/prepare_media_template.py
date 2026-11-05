#!/usr/bin/env python3
"""Append image/video teaching layouts to a bootstrapped seven-layout template.

Use either --template <base7.pptx> or --source <original Lesson02.pptx>, plus
--profile <base-profile.json>. The source option first bootstraps the original
seven layouts in a temporary directory. This preparation step then creates a
new controlled baseline; it does not modify the source deck or base profile.

The output profile adds derived layouts (source_layout/template_slide), not
additional source slide numbers. Rebuilding requires this preparation after
bootstrap; the derived profile cannot be bootstrapped from the original deck.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zlib

import pptx_engine as engine


MEDIA_RECT = [609600, 1371600, 6858000, 3857625]  # 7.5 × 4.21875 in, 16:9
MEDIA_ID = 500
CAPTION_ID = 501
PLACEHOLDER_PART = "ppt/media/course-placeholder-neutral.png"
PLACEHOLDER_RID = "rIdMediaVisual"


def neutral_png() -> bytes:
    """A single neutral color pixel, stretched by the native picture frame."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xf3\xf6\xff")) + chunk(b"IEND", b""))


def set_rect(shape: ET.Element, rect: list[int]) -> None:
    xfrm = shape.find("p:spPr/a:xfrm", engine.NS)
    if xfrm is None:
        raise engine.DeckError("Expected a direct shape transform in the comparison baseline")
    offset, size = xfrm.find("a:off", engine.NS), xfrm.find("a:ext", engine.NS)
    if offset is None or size is None:
        raise engine.DeckError("Incomplete comparison shape geometry")
    offset.attrib.update(x=str(rect[0]), y=str(rect[1]))
    size.attrib.update(cx=str(rect[2]), cy=str(rect[3]))


def picture() -> ET.Element:
    p, a, r = engine.P, engine.A, engine.R
    pic = ET.Element(f"{{{p}}}pic")
    nonvisual = ET.SubElement(pic, f"{{{p}}}nvPicPr")
    ET.SubElement(nonvisual, f"{{{p}}}cNvPr", {"id": str(MEDIA_ID), "name": "Media:visual",
                  "descr": "Unfilled teaching-media placeholder"})
    nv_picture = ET.SubElement(nonvisual, f"{{{p}}}cNvPicPr")
    ET.SubElement(nv_picture, f"{{{a}}}picLocks", {"noChangeAspect": "1"})
    ET.SubElement(nonvisual, f"{{{p}}}nvPr")
    fill = ET.SubElement(pic, f"{{{p}}}blipFill")
    ET.SubElement(fill, f"{{{a}}}blip", {f"{{{r}}}embed": PLACEHOLDER_RID})
    stretch = ET.SubElement(fill, f"{{{a}}}stretch")
    ET.SubElement(stretch, f"{{{a}}}fillRect")
    props = ET.SubElement(pic, f"{{{p}}}spPr")
    transform = ET.SubElement(props, f"{{{a}}}xfrm")
    ET.SubElement(transform, f"{{{a}}}off", {"x": str(MEDIA_RECT[0]), "y": str(MEDIA_RECT[1])})
    ET.SubElement(transform, f"{{{a}}}ext", {"cx": str(MEDIA_RECT[2]), "cy": str(MEDIA_RECT[3])})
    geometry = ET.SubElement(props, f"{{{a}}}prstGeom", {"prst": "rect"})
    ET.SubElement(geometry, f"{{{a}}}avLst")
    border = ET.SubElement(props, f"{{{a}}}ln", {"w": "12700"})
    border_fill = ET.SubElement(border, f"{{{a}}}solidFill")
    ET.SubElement(border_fill, f"{{{a}}}srgbClr", {"val": "DDE5F5"})
    return pic


def layout_definition(kind: str, number: int, comparison: dict) -> dict:
    slots = {}
    for name in ("title", "subtitle", "module", "heading1", "body1", "heading2", "body2",
                 "heading3", "body3", "course", "required", "page"):
        slots[name] = copy.deepcopy(comparison["slots"][name])
    slots["title"].update(max_chars=24, max_lines=1)
    slots["subtitle"].update(max_chars=40, max_lines=1)
    for i in range(1, 4):
        slots[f"heading{i}"].update(max_chars=16, max_lines=1)
        slots[f"body{i}"].update(max_chars=42, max_lines=3, max_chars_per_line=18)
    slots["caption"] = {"shape_id": CAPTION_ID, "max_chars": 46, "max_lines": 1}
    return {
        "source_layout": "comparison", "template_slide": number,
        "slots": slots,
        "media_slots": {"visual": {"shape_id": MEDIA_ID, "kind": kind, "fit": "contain",
                        "required": True, "rect_emu": MEDIA_RECT, "aspect_ratio": [16, 9],
                        "pending_caption_slot": "caption"}},
    }


def make_slide(original: bytes, definition: dict, kind: str, number: int) -> bytes:
    root = engine.parse(original)
    tree = root.find("p:cSld/p:spTree", engine.NS)
    if tree is None:
        raise engine.DeckError("Comparison baseline has no shape tree")
    source_shapes = engine.shapes(root)
    # Reuse the original note typography for the media caption, then remove
    # both comparison panels and all six associated text objects explicitly.
    caption = copy.deepcopy(source_shapes["25"])
    metadata = caption.find("p:nvSpPr/p:cNvPr", engine.NS)
    metadata.attrib.update(id=str(CAPTION_ID), name="Media caption")
    # The source note sat on a dark panel and used translucent white. The new
    # caption sits on a light background and needs explicit readable contrast.
    for color in caption.findall(".//a:srgbClr", engine.NS):
        color.set("val", "5B6478")
        for opacity in list(color):
            if opacity.tag in (f"{{{engine.A}}}alpha", f"{{{engine.A}}}alphaMod", f"{{{engine.A}}}alphaOff"):
                color.remove(opacity)
    engine.remove_shapes(root, list(range(21, 31)))
    existing = engine.shapes(root)
    # The three existing observation cards become a column beside the visual.
    # Each white card, colored top edge, heading and paragraph is moved, so no
    # old text or panel survives beneath a newly overlaid media rectangle.
    for index, first_id in enumerate((31, 35, 39)):
        top = 1371600 + index * 1333500
        card = [7848600, top, 3733800, 1143000]
        set_rect(existing[str(first_id)], card)
        set_rect(existing[str(first_id + 1)], card)
        set_rect(existing[str(first_id + 2)], [8020050, top + 171450, 3390900, 209550])
        set_rect(existing[str(first_id + 3)], [8020050, top + 438150, 3390900, 504825])
    set_rect(existing["17"], [819150, 352425, 8500000, 371475])
    set_rect(existing["18"], [819150, 752475, 8500000, 152400])
    set_rect(caption, [609600, 5353050, 6858000, 228600])
    # Insert after background/header decoration and before text so the native
    # picture never covers the header or caption in the new baseline.
    tree.insert(5, picture())
    tree.append(caption)
    content = {
        "title": "图片讲解页" if kind == "image" else "视频演示页",
        "subtitle": "放入参考图片，再补充三条课堂观察" if kind == "image" else "放入实操视频，配合三个观察任务",
        "module": "图片示范" if kind == "image" else "视频示范",
        "caption": "图片待填充 · 建议横向 16:9" if kind == "image" else "视频待填充 · 请提供 MP4 和封面",
        "heading1": "观察主体" if kind == "image" else "播放前",
        "body1": "说明图片中需要学员优先识别的对象。" if kind == "image" else "交代场景与观察目标，再开始播放。",
        "heading2": "解释细节" if kind == "image" else "观看时",
        "body2": "指出一个关键位置，并说明它的作用。" if kind == "image" else "指出需要暂停讲解的动作或状态变化。",
        "heading3": "联系任务" if kind == "image" else "播放后",
        "body3": "说明看完图片后学员应完成的下一步。" if kind == "image" else "请学员复述关键步骤，并完成一次练习。",
        "course": "课程名称", "required": "必讲", "page": f"{number} / 9",
    }
    all_shapes = engine.shapes(root)
    for name, value in content.items():
        engine.replace_text(all_shapes[str(definition["slots"][name]["shape_id"])], value)
    engine.check_coverage(root, definition, f"{kind}_explainer")
    return engine.xml_bytes(root, original)


def write_profile(profile: dict, output: Path, force: bool) -> bytes:
    data = (json.dumps(profile, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if output.exists() and not force:
        raise engine.DeckError(f"Profile output exists; use a new path or --force: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Profile and PPTX are written only after all in-memory validation succeeds.
    output.write_bytes(data)
    return data


def prepare(args: argparse.Namespace) -> dict:
    profile_path = Path(args.profile).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    profile_output = Path(args.profile_output).expanduser().resolve()
    input_path = Path(args.template or args.source).expanduser().resolve()
    inputs = {input_path, profile_path}
    if output in inputs or profile_output in inputs or output == profile_output:
        raise engine.DeckError("Outputs must differ from source inputs and from each other")
    if (output.exists() or profile_output.exists()) and not args.force:
        raise engine.DeckError("An output already exists; choose new paths or use --force")
    base_profile = engine.load_profile(profile_path)
    if len(base_profile["layouts"]) != 7 or "comparison" not in base_profile["layouts"]:
        raise engine.DeckError("Preparation requires the base seven-layout profile with comparison")
    if any("source_layout" in d or "media_slots" in d for d in base_profile["layouts"].values()):
        raise engine.DeckError("Use the base profile, not an already prepared media profile")
    with tempfile.TemporaryDirectory(prefix="course-media-base-") as temporary:
        template = input_path
        if args.source:
            extracted = Path(temporary) / "base-seven-source.pptx"
            engine.bootstrap(SimpleNamespace(source=str(input_path), profile=str(profile_path), output=str(extracted), force=False))
            # The portable template uses generic teaching prompts, not the old
            # lesson's visible course content. --template keeps its seven pages.
            generic_content = Path(__file__).resolve().parent.parent / "examples/template-content.json"
            if not generic_content.is_file():
                raise engine.DeckError("Rebuilding from source requires examples/template-content.json")
            template = Path(temporary) / "base-seven.pptx"
            engine.build(SimpleNamespace(template=str(extracted), profile=str(profile_path),
                         content=str(generic_content), output=str(template), force=False,
                         allow_pending_media=False, ffprobe=None))
        parts = engine.read_package(template)
        engine.check_template(parts, base_profile, profile_path)
        manifest = json.loads(parts[engine.MANIFEST])
        if manifest.get("layouts") != list(base_profile["layouts"]):
            raise engine.DeckError("Base template layout list differs from the base profile")
        base_parts = dict(parts)
        comparison_index = list(base_profile["layouts"]).index("comparison") + 1
        comparison_part = f"ppt/slides/slide{comparison_index}.xml"
        comparison_rels = engine.rels_name(comparison_part)
        if any(name not in parts for name in (comparison_part, comparison_rels)):
            raise engine.DeckError("Comparison baseline is missing slide data or relationships")
        profile = copy.deepcopy(base_profile)
        profile["derived_layout_schema"] = 1
        profile["preparation"] = {
            "script": "scripts/prepare_media_template.py",
            "base_profile_sha256": engine.sha(profile_path.read_bytes()),
            "base_template_sha256": engine.sha(Path(template).read_bytes()),
            "rebuild": "Bootstrap the base profile first, then run prepare_media_template.py; derived layouts are not original Lesson02 slide numbers.",
        }
        parts[PLACEHOLDER_PART] = neutral_png()
        derived = {}
        for number, (layout_name, kind) in enumerate((("image_explainer", "image"), ("video_explainer", "video")), 8):
            definition = layout_definition(kind, number, base_profile["layouts"]["comparison"])
            profile["layouts"][layout_name] = definition
            part = f"ppt/slides/slide{number}.xml"
            parts[part] = make_slide(parts[comparison_part], definition, kind, number)
            relations = engine.parse(parts[comparison_rels])
            if any(rel.get("Id") == PLACEHOLDER_RID for rel in relations):
                raise engine.DeckError("Media placeholder relationship ID already exists in the baseline")
            ET.SubElement(relations, f"{{{engine.PKG}}}Relationship", {"Id": PLACEHOLDER_RID,
                          "Type": engine.R + "/image", "Target": engine.relative_target(part, PLACEHOLDER_PART)})
            parts[engine.rels_name(part)] = engine.xml_bytes(relations, parts[comparison_rels])
            derived[layout_name] = {"source_layout": "comparison", "template_slide": number}
        selected = [f"ppt/slides/slide{i}.xml" for i in range(1, 10)]
        parts["ppt/presentation.xml"], parts["ppt/_rels/presentation.xml.rels"] = engine.set_slide_list(
            parts["ppt/presentation.xml"], parts["ppt/_rels/presentation.xml.rels"], selected)
        profile_data = (json.dumps(profile, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        for stale in ("content_sha256", "template_sha256", "output_layouts"):
            manifest.pop(stale, None)
        manifest.update({"profile_sha256": engine.sha(profile_data), "layouts": list(profile["layouts"]),
                         "media_slot_schema": 1, "derived_layouts": derived,
                         "base_template_sha256": engine.sha(Path(template).read_bytes())})
        parts[engine.MANIFEST] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        engine.update_metadata(parts, "Course template with media placeholders", 9)
        parts["[Content_Types].xml"] = engine.content_types(parts["[Content_Types].xml"], parts)
        types = engine.parse(parts["[Content_Types].xml"])
        if not any(t.get("Extension", "").lower() == "png" for t in types):
            ET.SubElement(types, f"{{{engine.CT}}}Default", {"Extension": "png", "ContentType": "image/png"})
            parts["[Content_Types].xml"] = engine.xml_bytes(types, parts["[Content_Types].xml"])
        engine.validate_relationships(parts)
        for i in range(1, 8):
            part = f"ppt/slides/slide{i}.xml"
            if parts[part] != base_parts[part] or parts.get(engine.rels_name(part)) != base_parts.get(engine.rels_name(part)):
                raise engine.DeckError(f"Preparation unexpectedly changed base slide {i}")
        if len(engine.parse(parts["ppt/presentation.xml"]).findall("p:sldIdLst/p:sldId", engine.NS)) != 9:
            raise engine.DeckError("Prepared presentation must contain nine slides")
        # No template finality is implied: required media are visibly pending.
        write_profile(profile, profile_output, args.force)
        engine.write_package(parts, output, args.force)
        return {"status": "ok", "output": str(output), "profile": str(profile_output),
                "slides": 9, "base_slides": "first seven slide and relationship parts byte-identical",
                "media_slot_schema": 1, "media_shape_id": MEDIA_ID, "caption_shape_id": CAPTION_ID,
                "media_rect_emu": MEDIA_RECT, "aspect_ratio": [16, 9],
                "new_layouts": list(derived), "media_status": "placeholders requiring user assets",
                "template_sha256": engine.sha(output.read_bytes()), "profile_sha256": engine.sha(profile_data),
                "visual_review": "required"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--template", help="Existing bootstrapped base-seven-layout PPTX")
    source.add_argument("--source", help="Original Lesson02 PPTX; first bootstrap its seven base layouts")
    parser.add_argument("--profile", required=True, help="Base seven-layout profile")
    parser.add_argument("--output", required=True, help="New nine-layout template PPTX")
    parser.add_argument("--profile-output", required=True, help="New profile with derived media layouts")
    parser.add_argument("--force", action="store_true", help="Replace generated outputs explicitly")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args), ensure_ascii=False, indent=2))
        return 0
    except (engine.DeckError, ValueError, OSError, ET.ParseError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
