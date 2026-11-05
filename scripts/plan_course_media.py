#!/usr/bin/env python3
"""Plan course media from an outline, then collect generated local assets.

This helper does not call image, video or speech models. It makes a stable
handoff contract for such tools and never labels prompts as generated media.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys


class PlanError(ValueError):
    pass


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{label} must be nonempty text")
    return value.strip()


def local_under(base: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "://" in relative or Path(relative).is_absolute():
        raise PlanError("Plan asset names must be relative local paths")
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise PlanError("Plan asset path escapes the planning directory")
    return path


def plan(args):
    outline, profile = read(args.outline), read(args.profile)
    if not isinstance(outline, dict) or set(outline) != {"title", "slides"}:
        raise PlanError("Outline must contain exactly title and slides")
    title = text(outline["title"], "title")
    if not isinstance(outline["slides"], list) or not outline["slides"]:
        raise PlanError("Outline slides must be a nonempty array")
    tasks, slides = [], []
    for index, slide in enumerate(outline["slides"], 1):
        if not isinstance(slide, dict) or set(slide) - {"layout", "slots", "media"}:
            raise PlanError(f"Slide {index}: only layout, slots and media are supported")
        layout = profile.get("layouts", {}).get(slide.get("layout"))
        if layout is None or not isinstance(slide.get("slots"), dict):
            raise PlanError(f"Slide {index}: valid layout and text slots required")
        wanted_text = {k for k, v in layout["slots"].items() if "auto" not in v}
        if set(slide["slots"]) != wanted_text:
            raise PlanError(f"Slide {index}: text slots must be {sorted(wanted_text)}")
        for key, value in slide["slots"].items():
            text(value, f"Slide {index}/{key}")
        media = slide.get("media", {})
        definitions = layout.get("media_slots", {})
        if not isinstance(media, dict) or set(media) != set(definitions):
            raise PlanError(f"Slide {index}: media slots must be {sorted(definitions)}")
        current = {"layout": slide["layout"], "slots": dict(slide["slots"])}
        pending = {}
        for slot, definition in definitions.items():
            request = media[slot]
            allowed = {"kind", "prompt", "alt", "narration", "storyboard", "duration_seconds", "visual_context", "format"}
            if not isinstance(request, dict) or set(request) - allowed:
                raise PlanError(f"Slide {index}/{slot}: unsupported media request fields")
            kind = definition["kind"]
            if kind not in {"image", "video"} or request.get("kind", kind) != kind:
                raise PlanError(f"Slide {index}/{slot}: media kind must be {kind}")
            prompt = text(request.get("prompt"), f"Slide {index}/{slot}/prompt")
            alt = text(request.get("alt"), f"Slide {index}/{slot}/alt")
            context = request.get("visual_context", "general")
            if context not in {"general", "aiui_glasses"}:
                raise PlanError("visual_context must be general or aiui_glasses")
            if context == "aiui_glasses":
                prompt += "\nAIUI眼镜屏幕使用单绿层级；黑底仅作示意承托。其他课件区域保持通用配色，不伪称真机截图。"
            extension = request.get("format", "png" if kind == "image" else "mp4")
            if extension not in ({"png", "jpg", "jpeg"} if kind == "image" else {"mp4"}):
                raise PlanError(f"Slide {index}/{slot}: unsupported {kind} format")
            task_id = f"slide-{index:02d}-{slot}"
            if not all(c.isascii() and (c.isalnum() or c in "-_") for c in task_id):
                raise PlanError("Media slot names must use ASCII letters, digits, '-' or '_'")
            task = {"id": task_id, "slide": index, "layout": slide["layout"], "slot": slot,
                    "kind": kind, "status": "planned", "prompt": prompt, "alt": alt,
                    "fit": definition.get("fit", "contain"),
                    "aspect_ratio": definition.get("aspect_ratio"), "visual_context": context,
                    "expected_file": f"assets/{task_id}.{extension}"}
            caption_slot = definition.get("pending_caption_slot")
            if caption_slot not in wanted_text:
                raise PlanError(f"Slide {index}/{slot}: media definition needs a visible pending_caption_slot")
            task["caption_slot"] = caption_slot
            task["final_caption"] = slide["slots"][caption_slot]
            # Keep drafts visibly incomplete; collect restores the requested caption.
            marker = "待补图片" if kind == "image" else "待补视频"
            budget = layout["slots"][caption_slot].get("max_chars", 46)
            current["slots"][caption_slot] = (marker + "：" + task["final_caption"])[:budget]
            if kind == "video":
                task["narration"] = text(request.get("narration"), f"Slide {index}/{slot}/narration")
                storyboard = request.get("storyboard")
                if not isinstance(storyboard, list) or not storyboard:
                    raise PlanError(f"Slide {index}/{slot}: video storyboard is required")
                task["storyboard"] = [text(item, "storyboard item") for item in storyboard]
                duration = request.get("duration_seconds")
                if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 3600:
                    raise PlanError("Video duration_seconds must be a positive number up to 3600")
                task["duration_seconds"] = duration
                task["expected_poster"] = f"assets/{task_id}-poster.png"
            tasks.append(task)
            pending[slot] = {"status": "planned", "prompt": prompt, "alt": alt}
        if pending:
            current["media"] = pending
        slides.append(current)
    out = args.out.resolve()
    if out.exists():
        raise PlanError(f"Output directory already exists; choose a new one: {out}")
    (out / "assets").mkdir(parents=True)
    content = {"title": title, "slides": slides}
    write(out / "content.planned.json", content)
    manifest = {"version": 1, "title": title, "content": "content.planned.json", "tasks": tasks}
    write(out / "media-plan.json", manifest)
    lines = [f"# {title}：媒体生成任务", "", "当前为计划，图片、视频与旁白音频尚未生成。", ""]
    for task in tasks:
        lines += [f"## {task['id']} · {task['kind']}", "", f"文件：`{task['expected_file']}`", "",
                  f"配图说明：{task['alt']}", "", "### 生成提示词", "", task["prompt"], ""]
        if task["kind"] == "video":
            lines += [f"目标时长：{task['duration_seconds']} 秒", "", "### 视频讲解文案", "", task["narration"], "", "### 分镜", ""]
            lines += [f"{n}. {item}" for n, item in enumerate(task["storyboard"], 1)]
            lines += ["", f"海报：`{task['expected_poster']}`", ""]
    (out / "media-plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "planned", "media_tasks": len(tasks), "media_generated": False,
            "plan": str(out / "media-plan.json"), "content": str(out / "content.planned.json")}


def collect(args):
    plan_path = args.plan.resolve()
    manifest = read(plan_path)
    if manifest.get("version") != 1 or not isinstance(manifest.get("tasks"), list):
        raise PlanError("Unsupported media plan")
    base = plan_path.parent
    content = read(local_under(base, manifest["content"]))
    output = (args.output or base / "content.ready.json").resolve()
    if output.exists() and not args.force:
        raise PlanError(f"Output exists; use a new path or --force: {output}")
    pending, ready, observations = [], 0, []
    for task in manifest["tasks"]:
        asset = local_under(base, task["expected_file"])
        poster = local_under(base, task["expected_poster"]) if task["kind"] == "video" else None
        if poster is not None and asset.is_file() and not poster.exists() and args.make_posters:
            ffmpeg = args.ffmpeg or shutil.which("ffmpeg")
            if not ffmpeg:
                raise PlanError("--make-posters requires ffmpeg or --ffmpeg")
            result = subprocess.run([ffmpeg, "-v", "error", "-i", str(asset), "-frames:v", "1", "-update", "1", str(poster)],
                                    capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise PlanError(f"Poster extraction failed for {task['id']}: {result.stderr[-500:]}")
        available = asset.is_file() and asset.stat().st_size > 0 and (poster is None or poster.is_file() and poster.stat().st_size > 0)
        slide_index = task["slide"] - 1
        if not 0 <= slide_index < len(content["slides"]):
            raise PlanError("Task slide index is out of range")
        slide = content["slides"][slide_index]
        if slide["layout"] != task["layout"] or task["slot"] not in slide.get("media", {}):
            raise PlanError("Task does not match planned content")
        if available:
            value = {"path": os.path.relpath(asset, output.parent), "alt": task["alt"]}
            if poster:
                value["poster"] = os.path.relpath(poster, output.parent)
            slide["media"][task["slot"]] = value
            if task.get("caption_slot"):
                slide["slots"][task["caption_slot"]] = text(task.get("final_caption"), "final_caption")
            ready += 1
        else:
            pending.append(task["id"])
        observations.append({"id": task["id"], "file_present": asset.is_file(), "poster_present": poster.is_file() if poster else None})
    if pending and not args.allow_pending_media:
        raise PlanError("Media is still missing: " + ", ".join(pending))
    output.parent.mkdir(parents=True, exist_ok=True)
    write(output, content)
    return {"status": "pending_media" if pending else "assets_collected", "delivery_ready": False,
            "assets_complete": not pending, "structural_ready": False,
            "ready_media_slots": ready, "pending_media_slots": len(pending), "pending": pending,
            "content": str(output), "observations": observations,
            "note": "Media files still require PPT engine format/geometry validation and visual/playback review."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("plan", help="Write media tasks and an explicit pending-content file")
    p.add_argument("--outline", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    c = commands.add_parser("collect", help="Collect local generated assets without calling a media model")
    c.add_argument("--plan", type=Path, required=True)
    c.add_argument("--output", type=Path)
    c.add_argument("--allow-pending-media", action="store_true")
    c.add_argument("--make-posters", action="store_true", help="Use ffmpeg to extract a missing video poster")
    c.add_argument("--ffmpeg", help="ffmpeg executable for poster extraction")
    c.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        result = plan(args) if args.command == "plan" else collect(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PlanError, OSError, KeyError, TypeError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
