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
        "--embedding-model-path",
        default=os.environ.get("VULMORPH_EMBEDDING_MODEL_PATH", ""),
    )
    parser.add_argument(
        "--embedding-output-dir",
        default=os.environ.get("VULMORPH_EMBEDDING_OUTPUT_DIR", "data/embeddings"),
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=int(os.environ.get("VULMORPH_EMBEDDING_BATCH_SIZE", "4")),
    )
    parser.add_argument("--force-pull", action="store_true")
    parser.add_argument("--llm", choices=["none", "deepseek"], default="deepseek")
    parser.add_argument("--json", action="store_true", help="Print the full LangGraph state as JSON.")
    args = parser.parse_args()

    llm_client = DeepSeekRepoStructureClient.from_env() if args.llm == "deepseek" else None
    result = run_vulmorph_pipeline(
        args.repo_url,
        target_dir=args.target_dir,
        embedding_model_path=args.embedding_model_path,
        embedding_output_dir=args.embedding_output_dir,
        embedding_batch_size=args.embedding_batch_size,
        force_pull=args.force_pull,
        llm_client=llm_client,
        progress_callback=_print_progress,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_format_summary(result))


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
    return ""


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    repo = result.get("repo_result", {})
    structure = result.get("structure_analysis", {})
    scope = result.get("source_scope", {})
    build = result.get("build_setup", {})
    extraction = result.get("function_extraction", {})
    embedding = result.get("embedding_result", {})

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
                "count": embedding.get("count"),
                "dimension": embedding.get("dimension"),
                "output_path": embedding.get("output_path"),
                "batch_size": embedding.get("batch_size"),
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
                f"batch_size={steps['embeddings'].get('batch_size')}"
            ),
            f"Embedding output: {steps['embeddings'].get('output_path')}",
        ]
    )
    if summary["errors"]:
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in summary["errors"])
    return "\n".join(lines)


if __name__ == "__main__":
    main()
