"""LLM assessment of current code against historical bug-fix patterns."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .embeddings import _repo_output_name


FALLBACK_OUTPUT_DIR = Path("data/risk")
DEFAULT_MAX_CASES = 10
DEFAULT_MAX_CODE_CHARS = 6000


def assess_similar_bug_risk(state: dict[str, Any]) -> dict[str, Any]:
    """Ask the configured LLM whether similar current code still has the bug."""

    similarity = state.get("similarity_result", {})
    snippets_result = state.get("bug_fix_snippets", {})
    repo_result = state.get("repo_result", {})
    if not similarity.get("ok"):
        return _failure(state, "similarity search failed; cannot assess bug risk")
    if not snippets_result.get("ok"):
        return _failure(state, "bug-fix snippet extraction failed; cannot assess bug risk")
    if not repo_result.get("ok"):
        return _failure(state, "repo acquisition failed; cannot assess bug risk")

    request = dict(state.get("repo_request", {}))
    output_dir = Path(request.get("risk_assessment_output_dir", FALLBACK_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_repo_output_name(state)}.bug_risk_assessment.json"

    matches = similarity.get("items", [])
    snippets = snippets_result.get("items", [])
    if not matches or not snippets:
        payload = {"ok": True, "count": 0, "items": [], "output_path": str(output_path)}
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"risk_assessment_result": payload}

    max_cases = max(1, int(request.get("bug_risk_max_cases", DEFAULT_MAX_CASES)))
    max_code_chars = max(1000, int(request.get("bug_risk_max_code_chars", DEFAULT_MAX_CODE_CHARS)))
    repo_path = Path(repo_result["path"])
    cases = _build_cases(matches[:max_cases], snippets, repo_path, max_code_chars)

    llm_client = state.get("_llm_client")
    if llm_client is None or not hasattr(llm_client, "assess_similar_bug_risk"):
        payload = {
            "ok": True,
            "skipped": True,
            "reason": "no LLM client configured",
            "count": 0,
            "cases": cases,
            "items": [],
            "output_path": str(output_path),
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"risk_assessment_result": payload}

    try:
        response = llm_client.assess_similar_bug_risk(cases)
        parsed = json.loads(response.get("content", "{}"))
    except Exception as exc:
        return _failure(state, f"bug risk LLM assessment failed: {exc}")

    assessments = parsed.get("items", [])
    by_case_id = {str(item.get("case_id", "")): item for item in assessments if item.get("case_id")}
    items = []
    for case in cases:
        assessment = by_case_id.get(case["case_id"], {})
        items.append(
            {
                "case_id": case["case_id"],
                "similarity": case["similarity"],
                "bug_fix": case["bug_fix"],
                "function": case["function"],
                "assessment": assessment,
            }
        )

    payload = {
        "ok": True,
        "count": len(items),
        "output_path": str(output_path),
        "model": response.get("model"),
        "raw_usage": response.get("raw_usage", {}),
        "input_cases": cases,
        "items": items,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"risk_assessment_result": payload}


def _build_cases(
    matches: list[dict[str, Any]],
    snippets: list[dict[str, Any]],
    repo_path: Path,
    max_code_chars: int,
) -> list[dict[str, Any]]:
    snippet_lookup = {
        _snippet_key(item): item
        for item in snippets
    }
    cases = []
    for index, match in enumerate(matches, start=1):
        bug_fix = match.get("bug_fix", {})
        function = match.get("function", {})
        snippet = snippet_lookup.get(_match_key(bug_fix), {})
        before, after = _split_patch_text(snippet.get("text", ""))
        current_code = _read_function_source(repo_path, function, max_code_chars)
        cases.append(
            {
                "case_id": f"case-{index}",
                "similarity": match.get("similarity"),
                "bug_fix": {
                    "commit": bug_fix.get("commit"),
                    "subject": bug_fix.get("subject"),
                    "file": bug_fix.get("file"),
                    "hunk_header": bug_fix.get("hunk_header"),
                    "vulnerable_code": _trim(before, max_code_chars),
                    "fixed_code": _trim(after, max_code_chars),
                    "patch": _trim(snippet.get("text", ""), max_code_chars),
                },
                "function": {
                    "name": function.get("name"),
                    "file": function.get("file"),
                    "location": function.get("location"),
                    "current_code": current_code,
                },
            }
        )
    return cases


def _snippet_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("commit", "")),
        str(item.get("file", "")),
        str(item.get("hunk_header", "")),
    )


def _match_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("commit", "")),
        str(item.get("file", "")),
        str(item.get("hunk_header", "")),
    )


def _split_patch_text(text: str) -> tuple[str, str]:
    before: list[str] = []
    after: list[str] = []
    for line in text.splitlines():
        if line.startswith("@@"):
            before.append(line)
            after.append(line)
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            before.append(line[1:])
            continue
        if line.startswith("+"):
            after.append(line[1:])
            continue
        if line.startswith(" "):
            line = line[1:]
        before.append(line)
        after.append(line)
    return "\n".join(before), "\n".join(after)


def _read_function_source(repo_path: Path, function: dict[str, Any], max_code_chars: int) -> str:
    location = function.get("location") or {}
    path = location.get("absolute_path")
    if not path and function.get("file"):
        path = repo_path / str(function["file"])
    if not path:
        return ""
    source_path = Path(path)
    if not source_path.exists():
        return ""
    range_info = location.get("range") or {}
    start = int((range_info.get("start") or {}).get("line") or 1)
    end = int((range_info.get("end") or {}).get("line") or start)
    lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
    snippet = "\n".join(lines[max(0, start - 1): min(len(lines), end)])
    return _trim(snippet, max_code_chars)


def _trim(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    marker = "\n\n/* ... trimmed ... */\n\n"
    budget = max(1, max_chars - len(marker))
    head = budget * 2 // 3
    tail = budget - head
    return text[:head].rstrip() + marker + text[-tail:].lstrip()


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "risk_assessment_result": {"ok": False, "errors": [message]},
        "errors": [*state.get("errors", []), message],
    }
