#!/usr/bin/env python3
"""Measure natural DSH skill routing from native calls and reference reads.

Every case starts an independent headless deepseek-flash session. Case prompts
are sent unchanged; this harness never tells the model which skill to load.
Use frozen skill trees and distinct output folders for baseline/upgraded runs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time


MODEL = "deepseek-flash"
PROVIDER = "deepseek-account"
BUNDLED_CLI = Path("/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh")
ELECTRON = Path("/Applications/DeepSeek Harness.app/Contents/MacOS/DeepSeek Harness")
SKILL_PROVIDER = Path(
    "/Applications/DeepSeek Harness.app/Contents/Resources/app.asar/dsh/node_modules/"
    "@deepseek-ai/dsh-skill-filesystem/lib/index.js"
)
NEUTRAL_PREFIX = (
    "You are a coding agent powered by the {{model}} model. "
    "This is a read-only short-answer task. Return at most 250 Chinese characters. "
    "Do not create or edit files, build presentations, generate images, install packages, "
    "browse external services, or operate devices. Local reference reads are allowed. "
    "Do not inspect test harness files, test plans, runtime logs, sibling cases, "
    "or previous answers. Use only the current request and relevant local reference resources."
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path,
                        default=Path(__file__).resolve().parent.parent / "references/aiui-routing-tests.json")
    parser.add_argument("--skills-root", required=True, type=Path,
                        help="Frozen directory containing only the skills being compared")
    parser.add_argument("--phase", required=True, choices=("baseline", "upgraded"))
    parser.add_argument("--case", action="append", dest="case_ids",
                        help="Case ID from the plan; repeat to select several")
    parser.add_argument("--output", required=True, type=Path, help="New result directory")
    parser.add_argument("--timeout", type=float, default=180,
                        help="Per-session watchdog, 1–180 seconds (default: 180)")
    parser.add_argument("--concurrency", type=int, choices=(1, 2), default=2)
    parser.add_argument("--dsh-cli", type=Path, help="Defaults to PATH dsh or the app-bundled CLI")
    parser.add_argument("--dry-run", action="store_true",
                        help="Record native catalog/settings without inference")
    return parser.parse_args()


def native_catalog(root: Path) -> dict:
    """Exercise the real filesystem provider without booting an LLM or watchers."""
    if not ELECTRON.is_file():
        raise ValueError("Native preflight currently requires the installed macOS DSH app")
    script = f"""
const {{FileSystemSkillProvider}} = await import({json.dumps(str(SKILL_PROVIDER))});
const warnings=[];
const ctx={{get(){{return undefined;}},logger:{{warn(m){{warnings.push(String(m));}}}}}};
const abort=new AbortController();
const provider=new FileSystemSkillProvider(ctx,{{signal:abort.signal,invalidate(){{}}}},
  {{includeDefaultRoots:false,customSkillDirs:[{json.dumps(str(root))}],watch:false}});
try{{
 const observation=await provider.list({{cwd:{json.dumps(str(root.parent))}}});
 const candidates=Array.isArray(observation)?observation:observation.candidates;
 console.log(JSON.stringify({{complete:Array.isArray(observation)||observation.complete,
 warnings,candidates:candidates.map(c=>({{name:c.name,description:c.description,
 path:c.path,resourceBase:c.resourceBase,source:c.source,rank:c.rank}}))}}));
}}finally{{await provider.dispose();}}
"""
    env = os.environ.copy()
    env["ELECTRON_RUN_AS_NODE"] = "1"
    result = subprocess.run([str(ELECTRON), "--expose-internals", "-"], input=script,
                            capture_output=True, text=True, env=env, timeout=30)
    if result.returncode:
        raise ValueError(f"Native skill discovery failed: {result.stderr[-2000:]}")
    catalog = json.loads(result.stdout)
    catalog["implementation"] = str(SKILL_PROVIDER)
    for candidate in catalog["candidates"]:
        candidate["skill_sha256"] = sha256(Path(candidate["path"]).read_bytes())
    return catalog


def patch_entries(root: Path) -> list[dict]:
    return [
        {"id": "authorization", "disabled": False},
        {"id": "credentials", "disabled": False},
        {"id": "deepseek-account", "disabled": False},
        {"id": "agent-default-model", "config": {
            "provider": PROVIDER, "model": MODEL, "reasoningEffort": "high"}},
        {"id": "skill-filesystem", "config": {
            "includeDefaultRoots": False, "customSkillDirs": [str(root)], "watch": False}},
        {"id": "system-prompt", "config": {"personaPrefix": NEUTRAL_PREFIX}},
        {"id": "agent-instructions", "disabled": True},
        {"id": "sandbox-policy", "config": {"mode": "read-only"}},
        {"id": "approval", "config": {"policy": "never"}},
        {"id": "tool-web", "disabled": True},
        {"id": "session-title-llm", "disabled": True},
        {"id": "session-telemetry-otel", "disabled": True},
        {"id": "otel", "disabled": True},
    ]


def persisted_evidence(session_id: str | None, work: Path) -> dict:
    """Read only this newly created session, retaining its native seq records."""
    evidence = {"path": None, "models": [], "providers": [], "catalogs": [], "available": False}
    if not session_id or not re.fullmatch(r"session-[a-zA-Z0-9-]+", session_id):
        return evidence
    home = Path(os.environ.get("DSH_HOME", str(Path.home() / ".dsh"))).expanduser()
    files = list((home / "sessions").glob(f"*/{session_id}/session.v*.jsonl.zstd"))
    zstd = shutil.which("zstd")
    if not files or not zstd:
        evidence["note"] = "Own session persistence or local zstd unavailable; requested model remains recorded"
        return evidence
    result = subprocess.run([zstd, "-dc", str(sorted(files)[-1])],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        evidence["note"] = "Could not decode this session's compressed records"
        return evidence
    (work / "persisted-session.jsonl").write_text(result.stdout, encoding="utf-8")
    evidence.update(path=str(sorted(files)[-1]), available=True)
    models, providers = set(), set()
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant/message":
            source = event.get("data", {}).get("message", {}).get("source", {})
            if source.get("kind") == "model":
                if source.get("model"):
                    models.add(source["model"])
                if source.get("provider"):
                    providers.add(source["provider"])
                replay_model = source.get("replayState", {}).get("response", {}).get("model")
                if replay_model:
                    models.add(replay_model)
        elif event.get("type") == "user/message":
            source = event.get("data", {}).get("source", {})
            if source.get("kind") == "skill-catalog":
                evidence["catalogs"].append({"seq": event.get("seq"), "entries": source.get("entries", []),
                                             "incomplete": source.get("incomplete", False)})
    evidence["models"], evidence["providers"] = sorted(models), sorted(providers)
    return evidence


def successful(result: dict | None) -> bool:
    if not result or result.get("status") != "completed":
        return False
    rendered = json.dumps(result.get("result"), ensure_ascii=False)
    return not any(message in rendered for message in (
        "unknown or no longer available", "not available for model invocation",
        "File not found:", "ENOENT:", "EACCES:", "PERMISSION_DENIED"))


def file_read_evidence(call: dict, result: dict, cwd: str) -> list[dict]:
    """Recognize native reads and literal simple shell reads with source proof.

    A shell command is not itself reading evidence: its successful returned
    text must contain the requested file/line range verbatim. Echo, pipelines,
    substitutions and compound commands are deliberately not accepted here.
    """
    tool, params = call.get("tool"), call.get("input", {})
    if tool == "read":
        raw_path = params.get("file_path", params.get("path"))
        if not isinstance(raw_path, str):
            return []
        path = Path(raw_path).expanduser()
        path = (Path(cwd) / path).resolve() if not path.is_absolute() else path.resolve()
        return [{"path": path, "method": "read"}] if path.is_file() else []
    if tool != "bash":
        return []
    command = params.get("command", "")
    if not isinstance(command, str) or re.search(r"[|;&<>`]|\$\(", command):
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    if not tokens:
        return []
    executable = Path(tokens[0]).name
    line_range = None
    if executable == "cat" and len(tokens) >= 2 and all(not x.startswith("-") for x in tokens[1:]):
        raw_paths = tokens[1:]
    elif executable == "sed" and len(tokens) == 4 and tokens[1] == "-n":
        match = re.fullmatch(r"(\d+)(?:,(\d+))?p", tokens[2])
        if not match:
            return []
        line_range = (int(match[1]), int(match[2] or match[1]))
        raw_paths = [tokens[3]]
    else:
        return []
    rendered = str(result.get("result", ""))
    evidence = []
    for raw_path in raw_paths:
        path = Path(raw_path).expanduser()
        path = (Path(cwd) / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        requested = source
        if line_range:
            requested = "".join(source.splitlines(keepends=True)[line_range[0] - 1:line_range[1]])
        if len(requested.strip()) < 40 or requested.strip() not in rendered:
            continue
        evidence.append({"path": path, "method": f"bash:{executable}",
                         "source_literal_match": True, "source_line_range": line_range,
                         "verified_excerpt_sha256": sha256(requested.encode("utf-8"))})
    return evidence


def evaluate(case: dict, events: list[dict], catalog: dict, verified_aiui_roots: list[Path],
             process: dict, persisted: dict, work: Path) -> dict:
    calls, results = {}, {}
    session_id, final_text = None, ""
    turn_end = []
    substantive_text = []
    artifact_attempts, course_workflow_reads = [], []
    for seq, event in enumerate(events, 1):
        event_type = event.get("type")
        if event_type == "session":
            session_id = event.get("sessionId")
        elif event_type == "tool_call":
            calls[event["callId"]] = {**event, "trace_line": seq}
            tool, params = event.get("tool", ""), event.get("input", {})
            command = str(params.get("command", ""))
            if tool in ("write", "edit", "apply_patch", "imagegen", "image_gen") or re.search(
                    r"pptx_engine\.py\s+(?:build|bootstrap)|render_review\.py|imagegen|image_gen", command):
                artifact_attempts.append({"call_id": event["callId"], "seq": seq, "tool": tool, "input": params})
        elif event_type == "tool_result":
            results[event["callId"]] = {**event, "trace_line": seq}
        elif event_type == "status" and event.get("phase") == "turn_end":
            turn_end.append(event)
        elif event_type == "final":
            final_text = event.get("text", "")
        elif event_type == "text":
            value = event.get("text", "")
            if re.search(r"第[一二三123]页|(?:^|\n)\s*(?:[123][.、]|#{1,4}\s|[一二三]、)", value):
                substantive_text.append(seq)
    native_loads, reads = [], []
    for call_id, call in calls.items():
        result = results.get(call_id)
        if not successful(result):
            continue
        params = call.get("input", {})
        if call.get("tool") == "skill":
            native_loads.append({"name": params.get("name"), "call_id": call_id,
                                 "call_seq": call["trace_line"], "result_seq": result["trace_line"]})
        else:
            for observation in file_read_evidence(call, result, process["execution_cwd"]):
                path = observation["path"]
                if "course-ppt-template" in path.parts and (
                        path.name == "profile.json" or path.suffix.lower() == ".pptx"):
                    course_workflow_reads.append({"path": str(path), "call_id": call_id})
                for root in verified_aiui_roots:
                    if not path.is_relative_to(root):
                        continue
                    relative = path.relative_to(root).as_posix()
                    if not relative.startswith("references/"):
                        continue
                    response = str(result.get("result", ""))
                    reads.append({"path": str(path), "relative": relative, "call_id": call_id,
                                  **{key: value for key, value in observation.items() if key != "path"},
                                  "call_seq": call["trace_line"], "result_seq": result["trace_line"],
                                  "source_sha256": sha256(path.read_bytes()) if path.is_file() else None,
                                  "returned_result_sha256": sha256(response.encode("utf-8")),
                                  "returned_excerpt": response[:500]})
                    break
    first_load = {}
    for load in native_loads:
        first_load.setdefault(load["name"], load)
    expected = case.get("expected_native_skill_order", [])
    missing = [name for name in expected if name not in first_load]
    order_ok = not missing and all(first_load[left]["result_seq"] < first_load[right]["call_seq"]
                                   for left, right in zip(expected, expected[1:]))
    required_refs = case.get("expected_aiui_reference_reads", [])
    missing_refs = [name for name in required_refs if not any(r["relative"] == name for r in reads)]
    forbidden = [load for load in native_loads if load["name"] in case.get("forbidden_native_skills", [])]
    if "aiui-dev" in case.get("forbidden_native_skills", []):
        forbidden.extend({"reference_read": read} for read in reads)
    if "course-ppt-template" in case.get("forbidden_native_skills", []):
        forbidden.extend({"course_workflow_read": read} for read in course_workflow_reads)
    required_result_seqs = [r["result_seq"] for r in reads if r["relative"] in required_refs]
    outline_before_knowledge = bool(required_result_seqs and any(
        seq < max(required_result_seqs) for seq in substantive_text))
    model_match = not persisted["models"] or persisted["models"] == [MODEL]
    provider_match = not persisted["providers"] or persisted["providers"] == [PROVIDER]
    complete = bool(turn_end and turn_end[-1].get("reason", {}).get("kind") == "completed"
                    and process["exit_code"] == 0 and not process["timed_out"])
    preflight_names = {c["name"] for c in catalog["candidates"]}
    catalog_valid = {"course-ppt-template", "aiui-dev"}.issubset(preflight_names)
    if persisted["available"] and not persisted["catalogs"]:
        catalog_valid = False
    if persisted["catalogs"]:
        observed_names = {entry.get("name") for entry in persisted["catalogs"][-1]["entries"]}
        catalog_valid &= {"course-ppt-template", "aiui-dev"}.issubset(observed_names)
    errors = []
    if not catalog_valid:
        errors.append("blocked_missing_aiui_skill_or_incomplete_native_catalog")
    if not complete:
        errors.append("incomplete_or_failed_session")
    if not model_match or not provider_match:
        errors.append("observed_model_or_provider_mismatch")
    if missing:
        errors.append("missing_native_skills:" + ",".join(missing))
    if not missing and not order_ok:
        errors.append("both_loaded_but_native_order_not_met")
    if missing_refs:
        errors.append("missing_real_aiui_references:" + ",".join(missing_refs))
    if forbidden:
        errors.append("forbidden_loads_or_reads")
    if outline_before_knowledge:
        errors.append("substantive_outline_before_required_knowledge")
    if artifact_attempts:
        errors.append("artifact_or_mutation_attempt")
    raw_error = "\n".join(str(x.get("reason", {})) for x in turn_end)
    infrastructure_failure = (process["timed_out"] or not model_match or not provider_match or
                              bool(re.search(r"MISSING_CREDENTIAL|ACCOUNT_|AUTH|MODEL_NOT|PERMISSION|FS_ACCESS", raw_error)))
    report = {
        "variant": process["phase"], "case_id": case["id"], "kind": case.get("kind"),
        "session_id": session_id, "model_requested": MODEL, "provider_requested": PROVIDER,
        "model_observed_if_available": persisted["models"], "provider_observed_if_available": persisted["providers"],
        "catalog_valid": catalog_valid, "catalog_names": sorted(preflight_names),
        "native_skill_loads": native_loads,
        "course_native_call_seq": first_load.get("course-ppt-template", {}).get("call_seq"),
        "course_native_result_seq": first_load.get("course-ppt-template", {}).get("result_seq"),
        "aiui_native_call_seq": first_load.get("aiui-dev", {}).get("call_seq"),
        "aiui_native_result_seq": first_load.get("aiui-dev", {}).get("result_seq"),
        "sequence_basis": "1-based line number in unmodified native NDJSON trace",
        "actual_aiui_references_read": reads, "missing_expected_references": missing_refs,
        "forbidden_loads_or_reads": forbidden, "outline_before_knowledge": outline_before_knowledge,
        "artifact_side_effects": artifact_attempts, "course_workflow_reads": course_workflow_reads,
        "strict_route_pass": not errors,
        "strict_order": order_ok,
        "functional_route_pass": not [error for error in errors if error not in {
            "both_loaded_but_native_order_not_met", "substantive_outline_before_required_knowledge"}],
        "manual_reference_fallback": bool(reads and "aiui-dev" not in first_load),
        "content_sanity_pass": None, "content_sanity_review_required": True,
        "failure_reason": errors, "infrastructure_failure": infrastructure_failure,
        "evidence_call_ids": sorted({x["call_id"] for x in native_loads + reads}),
        "turn_end": turn_end, "process": process, "persisted_evidence": persisted,
        "final_text": final_text,
    }
    (work / "answer.txt").write_text(final_text, encoding="utf-8")
    return report


def run_case(case: dict, args: argparse.Namespace, cli: Path, catalog: dict,
             verified_aiui_roots: list[Path]) -> dict:
    work = args.output / case["id"]
    work.mkdir(mode=0o700)
    (work / "prompt.txt").write_text(case["prompt"], encoding="utf-8")
    save(work / "headless.patch.json", patch_entries(args.skills_root))
    command = [str(cli), "headless", "--patch", str(work / "headless.patch.json"), "--json", "-"]
    start = time.monotonic()
    process = {"phase": args.phase, "command": command, "exit_code": None, "timed_out": False}
    workspace_files = []
    with tempfile.TemporaryDirectory(prefix="dsh-routing-case-") as workspace, \
            (work / "native.ndjson").open("w", encoding="utf-8") as out, \
            (work / "stderr.log").open("w", encoding="utf-8") as err:
        process["execution_cwd"] = str(Path(workspace).resolve())
        child = subprocess.Popen(command, cwd=workspace, stdin=subprocess.PIPE, stdout=out, stderr=err,
                                 text=True, encoding="utf-8", start_new_session=True)
        try:
            child.communicate(case["prompt"], timeout=args.timeout)
        except subprocess.TimeoutExpired:
            process["timed_out"] = True
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        process["exit_code"] = child.returncode
        workspace_files = [str(path.relative_to(workspace)) for path in Path(workspace).rglob("*")
                           if path.is_file()]
    process["elapsed_seconds"] = round(time.monotonic() - start, 2)
    events = []
    malformed = []
    for number, line in enumerate((work / "native.ndjson").read_text(encoding="utf-8").splitlines(), 1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            malformed.append(number)
    session_id = next((e.get("sessionId") for e in events if e.get("type") == "session"), None)
    persisted = persisted_evidence(session_id, work)
    report = evaluate(case, events, catalog, verified_aiui_roots, process, persisted, work)
    report["malformed_trace_lines"] = malformed
    if malformed:
        report["strict_route_pass"] = False
        report["functional_route_pass"] = False
        report["failure_reason"].append("malformed_native_trace")
    unexpected_files = [str(path.relative_to(work)) for path in work.rglob("*")
                        if path.is_file() and path.name not in {
                            "prompt.txt", "headless.patch.json", "native.ndjson", "stderr.log",
                            "persisted-session.jsonl", "answer.txt"}]
    if unexpected_files:
        report["strict_route_pass"] = False
        report["functional_route_pass"] = False
        report["artifact_side_effects"].append({"unexpected_files": unexpected_files})
        report["failure_reason"].append("unexpected_session_files")
    if workspace_files:
        report["strict_route_pass"] = False
        report["functional_route_pass"] = False
        report["artifact_side_effects"].append({"unexpected_execution_workspace_files": workspace_files})
        report["failure_reason"].append("unexpected_execution_workspace_files")
    save(work / "result.json", report)
    return report


def main() -> int:
    args = arguments()
    args.skills_root, args.output, args.plan = (p.expanduser().resolve()
                                               for p in (args.skills_root, args.output, args.plan))
    if not 0 < args.timeout <= 180:
        raise ValueError("--timeout must be between 1 and 180 seconds")
    if not args.skills_root.is_dir():
        raise ValueError("--skills-root must be an existing frozen skill directory")
    if args.output.exists():
        raise ValueError("--output must be new, to preserve independent traces")
    cli = (args.dsh_cli or Path(shutil.which("dsh") or BUNDLED_CLI)).expanduser().resolve()
    if not cli.is_file() or not os.access(cli, os.X_OK):
        raise ValueError("DSH CLI unavailable; pass --dsh-cli")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in plan["cases"]}
    chosen = list(dict.fromkeys(args.case_ids or cases.keys()))
    if any(case_id not in cases for case_id in chosen):
        raise ValueError("Unknown --case ID")
    if any(re.search(r"course-ppt-template|aiui-dev|先.{0,3}(?:使用|用).{0,3}skill", cases[i]["prompt"], re.I)
           for i in chosen):
        raise ValueError("Routing prompts must not name or force the expected skills")
    catalog = native_catalog(args.skills_root)
    names = [item["name"] for item in catalog["candidates"]]
    if len(names) != len(set(names)) or set(names) - {"course-ppt-template", "aiui-dev"}:
        raise ValueError(f"Isolated root must contain no duplicate/unrelated skills: {names}")
    if "course-ppt-template" not in names:
        raise ValueError("Course skill missing from native discovery")
    if args.phase == "upgraded" and "aiui-dev" not in names:
        raise ValueError("Upgraded catalog is missing aiui-dev; refusing to spend inference")
    args.output.mkdir(parents=True, mode=0o700)
    args.output.chmod(0o700)
    save(args.output / "native-catalog.json", catalog)
    shutil.copy2(args.plan, args.output / "tests-plan.json")
    verified_aiui_roots = []
    for candidate in catalog["candidates"]:
        if candidate["name"] == "aiui-dev":
            verified_aiui_roots.append(Path(candidate["resourceBase"]["path"]).resolve())
    documented_root = Path(plan.get("observed_inputs", {}).get("real_aiui_skill", {}).get("path", ""))
    documented_hash = plan.get("observed_inputs", {}).get("real_aiui_skill", {}).get("sha256")
    if documented_root.is_file() and sha256(documented_root.read_bytes()) == documented_hash:
        actual = documented_root.resolve().parent
        if actual not in verified_aiui_roots:
            verified_aiui_roots.append(actual)
    reference_manifest = []
    required_references = {ref for case_id in chosen for ref in cases[case_id].get("expected_aiui_reference_reads", [])}
    for root in verified_aiui_roots:
        for relative in sorted(required_references):
            path = root / relative
            if path.is_file():
                reference_manifest.append({"path": str(path), "relative": relative,
                                           "sha256": sha256(path.read_bytes())})
    manifest = {"harness_protocol": 2, "phase": args.phase, "model": MODEL, "provider": PROVIDER,
                "reasoningEffort": "high", "timeout": args.timeout, "concurrency": args.concurrency,
                "skills_root": str(args.skills_root), "plan_sha256": sha256(args.plan.read_bytes()),
                "harness_sha256": sha256(Path(__file__).read_bytes()),
                "dsh_cli": str(cli), "dsh_version": subprocess.check_output([str(cli), "--version"], text=True).strip(),
                "neutral_prefix": NEUTRAL_PREFIX, "case_ids": chosen,
                "baseline_missing_aiui_is_environment_gap": "aiui-dev" not in names,
                "catalog": catalog, "reference_manifest": reference_manifest}
    save(args.output / "manifest.json", manifest)
    if args.dry_run:
        print(json.dumps({"status": "dry-run", "manifest": str(args.output / "manifest.json")}, ensure_ascii=False))
        return 0
    reports = []
    for start in range(0, len(chosen), args.concurrency):
        batch = chosen[start:start + args.concurrency]
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(run_case, cases[name], args, cli, catalog, verified_aiui_roots) for name in batch]
            for future in futures:
                report = future.result()
                reports.append(report)
                print(json.dumps({"case": report["case_id"], "functional_route_pass": report["functional_route_pass"],
                                  "strict_route_pass": report["strict_route_pass"], "strict_order": report["strict_order"],
                                  "loads": [x["name"] for x in report["native_skill_loads"]],
                                  "references": [x["relative"] for x in report["actual_aiui_references_read"]],
                                  "failure_reason": report["failure_reason"]}, ensure_ascii=False), flush=True)
        if any(report["infrastructure_failure"] for report in reports):
            break
    unchanged = all(Path(c["path"]).is_file() and sha256(Path(c["path"]).read_bytes()) == c["skill_sha256"]
                    for c in catalog["candidates"])
    summary = {"phase": args.phase, "model": MODEL, "cases_executed": len(reports),
               "functional_native_route_passes": sum(r["functional_route_pass"] for r in reports),
               "strict_native_route_passes": sum(r["strict_route_pass"] for r in reports),
               "catalog_valid": {"course-ppt-template", "aiui-dev"}.issubset(names),
               "frozen_skill_hashes_unchanged": unchanged,
               "results": [{"case_id": r["case_id"], "functional_route_pass": r["functional_route_pass"],
                            "strict_route_pass": r["strict_route_pass"], "strict_order": r["strict_order"],
                            "result": str(args.output / r["case_id"] / "result.json")} for r in reports],
               "content_sanity_review_required": True}
    save(args.output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if unchanged and all(r["functional_route_pass"] for r in reports) and len(reports) == len(chosen) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"test_aiui_routing: {error}", file=sys.stderr)
        raise SystemExit(2)
