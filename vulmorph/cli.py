"""Command-line entry point for the VulMorph MVP pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from .graph import run_vulmorph_pipeline
from .llm_clients import DeepSeekRepoStructureClient, load_env_file


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="Run the initial VulMorph LangGraph pipeline.")
    parser.add_argument("repo_url", help="Git repository URL to analyze")
    parser.add_argument("--target-dir", default="data/targets")
    parser.add_argument(
        "--embedding-provider",
        choices=["local", "api"],
        default=os.environ.get("VULMORPH_EMBEDDING_PROVIDER", "local"),
    )
    parser.add_argument(
        "--embedding-model-path",
        default=os.environ.get("VULMORPH_EMBEDDING_MODEL_PATH", ""),
    )
    parser.add_argument(
        "--embedding-base-url",
        default=os.environ.get("VULMORPH_EMBEDDING_BASE_URL", ""),
    )
    parser.add_argument(
        "--embedding-api-key",
        default=os.environ.get("VULMORPH_EMBEDDING_API_KEY", ""),
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("VULMORPH_EMBEDDING_MODEL", ""),
    )
    parser.add_argument(
        "--embedding-dimensions",
        default=os.environ.get("VULMORPH_EMBEDDING_DIMENSIONS", ""),
    )
    parser.add_argument(
        "--embedding-timeout",
        type=float,
        default=_env_float("VULMORPH_EMBEDDING_TIMEOUT", 120.0),
    )
    parser.add_argument(
        "--embedding-max-input-chars",
        type=int,
        default=_env_int("VULMORPH_EMBEDDING_MAX_INPUT_CHARS", 12000),
    )
    parser.add_argument(
        "--embedding-output-dir",
        default=os.environ.get("VULMORPH_EMBEDDING_OUTPUT_DIR", "data/embeddings"),
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=_env_int("VULMORPH_EMBEDDING_BATCH_SIZE", 4),
    )
    parser.add_argument("--force-pull", action="store_true")
    parser.add_argument("--llm", choices=["none", "deepseek"], default="deepseek")
    parser.add_argument("--bug-fix-max-commits", type=int, default=20)
    parser.add_argument("--bug-fix-max-snippets", type=int, default=100)
    parser.add_argument("--bug-fix-top-k", type=int, default=10)
    parser.add_argument("--bug-fix-commit-filter", choices=["llm", "keyword"], default="llm")
    parser.add_argument("--bug-fix-llm-batch-size", type=int, default=100)
    parser.add_argument("--bug-risk-max-cases", type=int, default=10)
    parser.add_argument("--bug-risk-max-code-chars", type=int, default=6000)
    parser.add_argument("--json", action="store_true", help="Print the full LangGraph state as JSON.")
    args = parser.parse_args()

    llm_client = DeepSeekRepoStructureClient.from_env() if args.llm == "deepseek" else None
    result = run_vulmorph_pipeline(
        args.repo_url,
        target_dir=args.target_dir,
        embedding_provider=args.embedding_provider,
        embedding_model_path=args.embedding_model_path,
        embedding_base_url=args.embedding_base_url,
        embedding_api_key=args.embedding_api_key,
        embedding_model=args.embedding_model,
        embedding_dimensions=args.embedding_dimensions,
        embedding_timeout=args.embedding_timeout,
        embedding_max_input_chars=args.embedding_max_input_chars,
        embedding_output_dir=args.embedding_output_dir,
        embedding_batch_size=args.embedding_batch_size,
        force_pull=args.force_pull,
        bug_fix_max_commits=args.bug_fix_max_commits,
        bug_fix_max_snippets=args.bug_fix_max_snippets,
        bug_fix_top_k=args.bug_fix_top_k,
        bug_fix_commit_filter=args.bug_fix_commit_filter,
        bug_fix_llm_batch_size=args.bug_fix_llm_batch_size,
        bug_risk_max_cases=args.bug_risk_max_cases,
        bug_risk_max_code_chars=args.bug_risk_max_code_chars,
        llm_client=llm_client,
        progress_callback=_print_progress,
    )
    if args.json:
        print(json.dumps(_json_safe_result(result), ensure_ascii=False, indent=2))
    else:
        print(_format_summary(result))


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _print_progress(node_name: str, event: str, payload: dict[str, Any] | None) -> None:
    if event == "start":
        print(f"[START] {node_name}", file=sys.stderr, flush=True)
        return
    if event == "progress":
        detail = _node_detail(payload)
        suffix = f" - {detail}" if detail else ""
        print(f"[PROG]  {node_name}{suffix}", file=sys.stderr, flush=True)
        return

    status = _node_status(payload)
    detail = _node_detail(payload)
    suffix = f" - {detail}" if detail else ""
    print(f"[DONE]  {node_name}: {status}{suffix}", file=sys.stderr, flush=True)


def _node_status(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "ok"
    first_value = next(iter(payload.values()), {})
    if isinstance(first_value, dict) and first_value.get("ok") is False:
        return "failed"
    return "ok"


def _node_detail(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    if "repo_result" in payload:
        repo = payload["repo_result"]
        return repo.get("path", "") or ", ".join(repo.get("errors", []))
    if "structure_analysis" in payload:
        analysis = payload["structure_analysis"]
        if analysis.get("llm_errors"):
            return f"used_llm={analysis.get('used_llm', False)}, llm_error={analysis['llm_errors'][0]}"
        return f"used_llm={analysis.get('used_llm', False)}"
    if "source_scope" in payload:
        scope = payload["source_scope"]
        return f"files={scope.get('count', 0)}"
    if "build_setup" in payload:
        build = payload["build_setup"]
        return build.get("compile_commands_path", "") or ", ".join(build.get("errors", []))
    if "function_extraction" in payload:
        extraction = payload["function_extraction"]
        return f"functions={extraction.get('count', 0)}"
    if "embedding_result" in payload:
        embedding = payload["embedding_result"]
        if embedding.get("ok") is False:
            return ", ".join(embedding.get("errors", []))
        return f"vectors={embedding.get('count', 0)}, output={embedding.get('output_path', '')}"
    if "embedding_progress" in payload:
        progress = payload["embedding_progress"]
        return f"{progress.get('completed', 0)}/{progress.get('total', 0)}"
    if "bug_fix_commits" in payload:
        commits = payload["bug_fix_commits"]
        return f"commits={commits.get('count', 0)}, mode={commits.get('filter_mode')}"
    if "bug_fix_commit_progress" in payload:
        progress = payload["bug_fix_commit_progress"]
        return f"{progress.get('completed', 0)}/{progress.get('total', 0)}"
    if "bug_fix_snippets" in payload:
        snippets = payload["bug_fix_snippets"]
        return f"snippets={snippets.get('count', 0)}, output={snippets.get('output_path', '')}"
    if "similarity_result" in payload:
        result = payload["similarity_result"]
        if result.get("ok") is False:
            return ", ".join(result.get("errors", []))
        return f"matches={result.get('count', 0)}, output={result.get('output_path', '')}"
    if "risk_assessment_result" in payload:
        result = payload["risk_assessment_result"]
        if result.get("ok") is False:
            return ", ".join(result.get("errors", []))
        if result.get("skipped"):
            return f"skipped={result.get('reason')}"
        return f"cases={result.get('count', 0)}, output={result.get('output_path', '')}"
    return ""


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    repo = result.get("repo_result", {})
    structure = result.get("structure_analysis", {})
    scope = result.get("source_scope", {})
    build = result.get("build_setup", {})
    extraction = result.get("function_extraction", {})
    embedding = result.get("embedding_result", {})
    commits = result.get("bug_fix_commits", {})
    snippets = result.get("bug_fix_snippets", {})
    similarity = result.get("similarity_result", {})
    risk = result.get("risk_assessment_result", {})

    return {
        "ok": not result.get("errors"),
        "steps": {
            "repo": {
                "ok": repo.get("ok"),
                "path": repo.get("path"),
                "head": repo.get("head"),
            },
            "structure_analysis": {
                "ok": structure.get("ok"),
                "used_llm": structure.get("used_llm"),
                "model": (structure.get("llm") or {}).get("model"),
            },
            "source_scope": {
                "ok": scope.get("ok"),
                "file_count": scope.get("count"),
                "files": scope.get("files", []),
            },
            "build_setup": {
                "ok": build.get("ok"),
                "compile_commands_path": build.get("compile_commands_path"),
                "source": build.get("source"),
            },
            "function_extraction": {
                "ok": extraction.get("ok"),
                "function_count": extraction.get("count"),
                "source_scope_count": extraction.get("source_scope_count"),
            },
            "embeddings": {
                "ok": embedding.get("ok"),
                "provider": embedding.get("provider"),
                "model": embedding.get("model"),
                "count": embedding.get("count"),
                "dimension": embedding.get("dimension"),
                "output_path": embedding.get("output_path"),
                "batch_size": embedding.get("batch_size"),
            },
            "bug_fix_commits": {
                "ok": commits.get("ok"),
                "count": commits.get("count"),
                "filter_mode": commits.get("filter_mode"),
                "llm_errors": commits.get("llm_errors", []),
            },
            "bug_fix_snippets": {
                "ok": snippets.get("ok"),
                "count": snippets.get("count"),
                "output_path": snippets.get("output_path"),
            },
            "similarity": {
                "ok": similarity.get("ok"),
                "count": similarity.get("count"),
                "output_path": similarity.get("output_path"),
                "top_matches": similarity.get("items", [])[:5],
            },
            "risk_assessment": {
                "ok": risk.get("ok"),
                "count": risk.get("count"),
                "output_path": risk.get("output_path"),
                "top_findings": risk.get("items", [])[:5],
            },
        },
        "errors": result.get("errors", []),
    }


def _format_summary(result: dict[str, Any]) -> str:
    summary = _summarize_result(result)
    steps = summary["steps"]
    lines = [
        "",
        "VulMorph run summary",
        f"Status: {'OK' if summary['ok'] else 'FAILED'}",
        f"Repository: {steps['repo'].get('path')}",
        f"Commit: {steps['repo'].get('head')}",
        (
            "Structure analysis: "
            f"{'LLM' if steps['structure_analysis'].get('used_llm') else 'heuristic'}"
            f"{' (' + steps['structure_analysis'].get('model') + ')' if steps['structure_analysis'].get('model') else ''}"
        ),
        f"Source files selected: {steps['source_scope'].get('file_count')}",
        "Selected files:",
    ]
    lines.extend(f"  - {path}" for path in steps["source_scope"].get("files", []))
    lines.extend(
        [
            f"compile_commands.json: {steps['build_setup'].get('compile_commands_path')}",
            f"Functions extracted: {steps['function_extraction'].get('function_count')}",
            (
                "Embeddings: "
                f"{steps['embeddings'].get('count')} vectors, "
                f"dim={steps['embeddings'].get('dimension')}, "
                f"batch_size={steps['embeddings'].get('batch_size')}, "
                f"provider={steps['embeddings'].get('provider')}"
            ),
            f"Embedding output: {steps['embeddings'].get('output_path')}",
            (
                "Bug-fix commits found: "
                f"{steps['bug_fix_commits'].get('count')} "
                f"(mode={steps['bug_fix_commits'].get('filter_mode')})"
            ),
            f"Bug-fix snippets extracted: {steps['bug_fix_snippets'].get('count')}",
            f"Bug-fix snippets output: {steps['bug_fix_snippets'].get('output_path')}",
            f"Similarity matches: {steps['similarity'].get('count')}",
            f"Similarity output: {steps['similarity'].get('output_path')}",
            f"Risk assessment cases: {steps['risk_assessment'].get('count')}",
            f"Risk assessment output: {steps['risk_assessment'].get('output_path')}",
        ]
    )
    if steps["similarity"].get("top_matches"):
        lines.append("Top similar matches:")
        for item in steps["similarity"]["top_matches"]:
            bug_fix = item.get("bug_fix", {})
            function = item.get("function", {})
            lines.append(
                "  - "
                f"{item.get('similarity', 0):.4f} "
                f"{bug_fix.get('commit', '')[:12]} {bug_fix.get('file', '')} "
                f"-> {function.get('name')} ({function.get('file')})"
            )
    if steps["risk_assessment"].get("top_findings"):
        lines.append("Top risk assessments:")
        for item in steps["risk_assessment"]["top_findings"]:
            assessment = item.get("assessment", {})
            function = item.get("function", {})
            risk = assessment.get("risk", "unknown")
            confidence = assessment.get("confidence", 0)
            lines.append(
                "  - "
                f"{risk} ({confidence}) "
                f"{function.get('name')} ({function.get('file')})"
            )
    if summary["errors"]:
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in summary["errors"])
    return "\n".join(lines)


def _json_safe_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if not key.startswith("_")}


if __name__ == "__main__":
    main()
