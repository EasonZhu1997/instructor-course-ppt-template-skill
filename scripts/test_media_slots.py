#!/usr/bin/env python3
"""Offline regression tests using the bundled examples and temporary outputs.

Run: python3 scripts/test_media_slots.py
No models, network, GUI, or external test framework are used. The portable
package includes the owner-authorized Lesson02 source. --source can override
it; an incomplete package explicitly skips integration tests.
Missing ffprobe skips video cases while image and planning cases still run.
Passing these checks does not establish target-app video playback or layout QA.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import posixpath
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
import zlib

import pptx_engine as engine

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
EXAMPLES = SKILL / "examples"
SOURCE = None
FFPROBE = None


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def command(script, *args, success=True):
    run = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                         capture_output=True, text=True, timeout=120)
    if success and run.returncode:
        raise AssertionError(f"{script} failed ({run.returncode}):\n{run.stdout[-2000:]}\n{run.stderr[-3000:]}")
    if not success:
        if run.returncode == 0:
            raise AssertionError(f"{script} unexpectedly succeeded:\n{run.stdout[-2000:]}")
        return run.stderr + run.stdout
    try:
        return json.loads(run.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"{script} did not return JSON: {run.stdout[-3000:]}")


def absolute_media(content):
    content = copy.deepcopy(content)
    for slide in content["slides"]:
        for record in slide.get("media", {}).values():
            for field in ["path", "poster"]:
                if field in record:
                    record[field] = str((EXAMPLES / record[field]).resolve())
    return content


def no_video(content):
    content = copy.deepcopy(content)
    content["slides"] = [s for s in content["slides"] if s["layout"] != "video_explainer"]
    return content


class DecoderTests(unittest.TestCase):
    def test_real_png_decodes_without_optional_dependencies(self):
        path = EXAMPLES / "media/hello-aiui.png"
        result = engine.media.image_info(path, engine.DeckError)
        self.assertGreater(result["width"], 0)
        self.assertGreater(result["height"], 0)
        self.assertEqual(result["data"], path.read_bytes())

    def test_crc_correct_png_with_invalid_pixels_is_rejected(self):
        def chunk(kind, value):
            return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)
        fake = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", b"not-a-zlib-stream") + chunk(b"IEND", b""))
        with tempfile.TemporaryDirectory(prefix="course-png-test-") as tmp:
            path = Path(tmp) / "corrupt.png"
            path.write_bytes(fake)
            with self.assertRaises(engine.DeckError):
                engine.media.image_info(path, engine.DeckError)

    def test_jpeg_header_without_pixel_data_is_rejected(self):
        # Valid-looking SOI/SOF dimensions and EOI, but no SOS/entropy stream.
        fake = (b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x08\x00\x08\x03"
                b"\x01\x11\x00\x02\x11\x00\x03\x11\x00\xff\xd9")
        with tempfile.TemporaryDirectory(prefix="course-jpeg-test-") as tmp:
            path = Path(tmp) / "corrupt.jpg"
            path.write_bytes(fake)
            with self.assertRaises(engine.DeckError):
                engine.media.image_info(path, engine.DeckError)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SOURCE is None:
            raise unittest.SkipTest("Original Lesson02 deck unavailable: use --source; no package build was tested")
        cls.storage = tempfile.TemporaryDirectory(prefix="course-media-regression-")
        cls.root = Path(cls.storage.name)
        cls.addClassCleanup(cls.storage.cleanup)
        cls.base_profile = SKILL / "references/base-profile.json"
        cls.base_template = cls.root / "base7.pptx"
        cls.profile = cls.root / "profile9.json"
        cls.template = cls.root / "template9.pptx"
        cls.original_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        command("pptx_engine.py", "bootstrap", "--source", SOURCE, "--profile", cls.base_profile,
                "--output", cls.base_template)
        command("prepare_media_template.py", "--source", SOURCE, "--profile", cls.base_profile,
                "--output", cls.template, "--profile-output", cls.profile)
        cls.ready = absolute_media(read(EXAMPLES / "rokid-aiui-media-content.json"))

    def setUp(self):
        self.directory = self.root / self._testMethodName
        self.directory.mkdir()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), self.original_hash,
                         "Regression tests changed the user's source presentation")

    def require_video(self):
        if FFPROBE is None:
            self.skipTest("ffprobe unavailable: H.264/video build, hash and playback structure were not tested")

    def build(self, content, *, name="output", pending=False, success=True, base=False):
        input_path, output = self.directory / (name + ".json"), self.directory / (name + ".pptx")
        write(input_path, content)
        args = ["build", "--template", self.base_template if base else self.template,
                "--profile", self.base_profile if base else self.profile,
                "--content", input_path, "--output", output]
        if pending:
            args += ["--allow-pending-media"]
        if FFPROBE:
            args += ["--ffprobe", FFPROBE]
        result = command("pptx_engine.py", *args, success=success)
        return input_path, output, result

    def validate(self, content_path, output, *, base=False, pending=False, success=True):
        args = ["validate", "--template", self.base_template if base else self.template,
                "--profile", self.base_profile if base else self.profile,
                "--content", content_path, "--pptx", output]
        if pending:
            args += ["--allow-pending-media"]
        if FFPROBE:
            args += ["--ffprobe", FFPROBE]
        return command("pptx_engine.py", *args, success=success)

    def test_legacy_seven_layouts_and_ten_page_course(self):
        for filename, count in [("template-content.json", 7), ("rokid-aiui-intro-content.json", 10)]:
            with self.subTest(content=filename):
                content = read(EXAMPLES / filename)
                path, output, result = self.build(content, name=filename[:-5], base=True)
                self.assertEqual(result["slides"], count)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(self.validate(path, output, base=True)["status"], "ok")

    def test_image_build_on_nine_layout_template_and_source_hash(self):
        path, output, result = self.build(no_video(self.ready))
        self.assertTrue(result["assets_complete"])
        self.assertEqual(result["pending_media_slots"], 0)
        self.assertEqual(self.validate(path, output)["status"], "ok")
        source = EXAMPLES / "media/hello-aiui.png"
        part = "ppt/media/course-" + hashlib.sha256(source.read_bytes()).hexdigest() + ".png"
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read(part), source.read_bytes())

    def test_video_build_embeds_mp4_poster_and_native_timing(self):
        self.require_video()
        path, output, result = self.build(self.ready)
        self.assertEqual(result["slides"], 4)
        self.assertEqual(self.validate(path, output)["status"], "ok")
        with zipfile.ZipFile(output) as archive:
            for source in [EXAMPLES / "media/hello-aiui.png", EXAMPLES / "media/hello-aiui-demo.mp4"]:
                part = "ppt/media/course-" + hashlib.sha256(source.read_bytes()).hexdigest() + source.suffix
                self.assertEqual(archive.read(part), source.read_bytes())
            slide = ET.fromstring(archive.read("ppt/slides/slide3.xml"))
            relations = ET.fromstring(archive.read("ppt/slides/_rels/slide3.xml.rels"))
            video_rel = next(r for r in relations if r.get("Type") == engine.R + "/video")
            media_rel = next(r for r in relations if r.get("Type") == engine.media.MEDIA_TYPE)
            self.assertEqual(video_rel.get("Target"), media_rel.get("Target"))
            self.assertIsNone(video_rel.get("TargetMode"))
            embedded = posixpath.normpath(posixpath.join("ppt/slides", video_rel.get("Target")))
            self.assertTrue(archive.read(embedded))
            self.assertEqual(slide.find(".//p:timing//p:video/p:cMediaNode/p:tgtEl/p:spTgt", engine.NS).get("spid"), "500")
            self.assertEqual(slide.find(".//p:pic/p:nvPicPr/p:cNvPr/a:hlinkClick", engine.NS).get("action"), "ppaction://media")
        self.assertEqual(result["target_app_video_playback"], "not-tested")

    def test_missing_image_wrong_slot_and_url_are_rejected(self):
        for case in ["missing", "slot", "url", "wrong_type"]:
            with self.subTest(case=case):
                content = no_video(self.ready)
                media = content["slides"][1]["media"]
                if case == "missing":
                    media["visual"]["path"] = str(self.directory / "does-not-exist.png")
                elif case == "slot":
                    media["unexpected"] = media.pop("visual")
                elif case == "url":
                    media["visual"]["path"] = "https://example.invalid/never-requested.png"
                else:
                    media["visual"]["path"] = str(EXAMPLES / "media/hello-aiui-demo.mp4")
                _, output, _ = self.build(content, name=case, success=False)
                self.assertFalse(output.exists())

    def test_missing_video_poster_and_wrong_ratio_are_rejected(self):
        self.require_video()
        for case in ["missing_poster", "ratio"]:
            with self.subTest(case=case):
                content = copy.deepcopy(self.ready)
                record = content["slides"][2]["media"]["visual"]
                if case == "missing_poster":
                    record.pop("poster")
                else:
                    # A real one-pixel neutral PNG is a genuine square poster.
                    import prepare_media_template
                    square = self.directory / "square.png"
                    square.write_bytes(prepare_media_template.neutral_png())
                    record["poster"] = str(square)
                _, output, _ = self.build(content, name=case, success=False)
                self.assertFalse(output.exists())

    def workflow(self, include_video):
        outline = read(EXAMPLES / "rokid-aiui-media-outline.json")
        if not include_video:
            outline = no_video(outline)
        outline_path = self.directory / "outline.json"
        write(outline_path, outline)
        work = self.directory / "plan"
        result = command("plan_course_media.py", "plan", "--outline", outline_path,
                         "--profile", self.profile, "--out", work)
        self.assertFalse(result["media_generated"])
        plan_path = work / "media-plan.json"
        command("plan_course_media.py", "collect", "--plan", plan_path, success=False)
        self.assertFalse((work / "content.ready.json").exists())
        planned_path = work / "content.planned.json"
        planned = read(planned_path)
        _, _, error = self.build(planned, name="pending-without-flag", success=False)
        self.assertIn("--allow-pending-media", error)
        _, _, report = self.build(planned, name="pending-draft", pending=True)
        self.assertEqual(report["status"], "pending_media")
        self.assertFalse(report["assets_complete"])
        self.assertFalse(report["delivery_ready"])
        self.assertEqual(report["pending_media_slots"], 2 if include_video else 1)
        unmarked = copy.deepcopy(planned)
        unmarked["slides"][1]["slots"]["caption"] = "表面上已经完成的图片"
        _, _, error = self.build(unmarked, name="unmarked-draft", pending=True, success=False)
        self.assertIn("must start with", error)
        for task in read(plan_path)["tasks"]:
            source = EXAMPLES / "media" / ("hello-aiui.png" if task["kind"] == "image" else "hello-aiui-demo.mp4")
            shutil.copyfile(source, work / task["expected_file"])
            if task["kind"] == "video":
                shutil.copyfile(EXAMPLES / "media/hello-aiui.png", work / task["expected_poster"])
        collected = command("plan_course_media.py", "collect", "--plan", plan_path)
        self.assertTrue(collected["assets_complete"])
        ready_path = work / "content.ready.json"
        ready = read(ready_path)
        for task in read(plan_path)["tasks"]:
            self.assertEqual(ready["slides"][task["slide"] - 1]["slots"][task["caption_slot"]], task["final_caption"])
        output = self.directory / "collected.pptx"
        args = ["build", "--template", self.template, "--profile", self.profile,
                "--content", ready_path, "--output", output]
        if FFPROBE:
            args += ["--ffprobe", FFPROBE]
        self.assertEqual(command("pptx_engine.py", *args)["status"], "ok")
        self.assertEqual(self.validate(ready_path, output)["pending_media_slots"], 0)

    def test_image_plan_collect_pending_and_caption_restoration(self):
        self.workflow(False)

    def test_video_plan_collect_pending_and_caption_restoration(self):
        self.require_video()
        self.workflow(True)

    def test_video_bytes_and_timing_tampering_are_rejected(self):
        self.require_video()
        path, output, _ = self.build(self.ready)
        with zipfile.ZipFile(output) as original:
            entries = {n: original.read(n) for n in original.namelist()}
        for case in ["video_bytes", "timing"]:
            with self.subTest(case=case):
                altered = dict(entries)
                if case == "video_bytes":
                    name = next(n for n in altered if n.endswith(".mp4"))
                    altered[name] += b"tampered"
                else:
                    name = "ppt/slides/slide3.xml"
                    root = ET.fromstring(altered[name])
                    root.find(".//p:timing//p:spTgt", engine.NS).set("spid", "999")
                    altered[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                bad = self.directory / (case + ".pptx")
                with zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as archive:
                    for name, value in altered.items():
                        archive.writestr(name, value)
                self.validate(path, bad, success=False)


def main():
    global SOURCE, FFPROBE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Override the bundled Lesson02 source")
    parser.add_argument("--ffprobe", help="Optional ffprobe executable; otherwise discover in PATH")
    args = parser.parse_args()
    candidate = args.source or SKILL / "assets/sources/lesson02-source.pptx"
    if args.source and not candidate.is_file():
        parser.error(f"Source deck does not exist: {candidate}")
    SOURCE = candidate.resolve() if candidate.is_file() else None
    FFPROBE = args.ffprobe or shutil.which("ffprobe")
    if args.ffprobe and not Path(args.ffprobe).is_file():
        parser.error(f"ffprobe executable does not exist: {args.ffprobe}")
    print(f"Source: {SOURCE or 'missing: package integration tests will SKIP'}", flush=True)
    print(f"ffprobe: {FFPROBE or 'missing: video cases will SKIP; PNG/image cases still run'}", flush=True)
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(DecoderTests),
                                unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationTests)])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"status": "failed" if not result.wasSuccessful() else "passed_with_skips" if result.skipped else "passed",
                      "tests_run": result.testsRun, "skipped": len(result.skipped), "failures": len(result.failures),
                      "errors": len(result.errors), "target_app_video_playback": "not-tested", "gui_used": False}, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
