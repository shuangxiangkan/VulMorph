"""Local Jina embedding node."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


FALLBACK_OUTPUT_DIR = Path("data/embeddings")


def embed_functions(state: dict[str, Any]) -> dict[str, Any]:
    """Embed extracted functions with a local sentence-transformers model."""

    extraction = state.get("function_extraction", {})
    if not extraction.get("ok"):
        return _failure(state, "function extraction failed; cannot embed functions")

    request = dict(state.get("repo_request", {}))
    _load_env_file()
    try:
        model_path = _required_path_setting(
            request,
            "embedding_model_path",
            "VULMORPH_EMBEDDING_MODEL_PATH",
        )
    except RuntimeError as exc:
        return _failure(state, str(exc))
    output_dir = _path_setting(
        request,
        "embedding_output_dir",
        "VULMORPH_EMBEDDING_OUTPUT_DIR",
        FALLBACK_OUTPUT_DIR,
    )
    batch_size = max(1, int(request.get("embedding_batch_size") or os.environ.get("VULMORPH_EMBEDDING_BATCH_SIZE", 4)))
    output_dir.mkdir(parents=True, exist_ok=True)

    functions = extraction.get("functions", [])
    output_path = output_dir / f"{_repo_output_name(state)}.functions.jsonl"
    if not functions:
        output_path.write_text("", encoding="utf-8")
        return {
            "embedding_result": {
                "ok": True,
                "model_path": str(model_path),
                "output_path": str(output_path),
                "count": 0,
                "dimension": 0,
            }
        }

    texts = [_function_text(item) for item in functions]
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        return _failure(state, "sentence-transformers is required for embedding") | {
            "embedding_result": {
                "ok": False,
                "model_path": str(model_path),
                "errors": [str(exc)],
            }
        }

    try:
        model = SentenceTransformer(str(model_path), trust_remote_code=True)
    except Exception as exc:
        return _failure(state, f"embedding failed: {exc}")

    dimension = 0
    progress_callback = state.get("_progress_callback")
    progress_step = max(10, batch_size)
    last_reported = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for start in range(0, len(functions), batch_size):
            batch_functions = functions[start:start + batch_size]
            batch_texts = texts[start:start + batch_size]
            try:
                vectors = model.encode(
                    batch_texts,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                )
            except Exception as exc:
                return _failure(state, f"embedding failed at batch {start // batch_size}: {exc}")
            if len(vectors) and dimension == 0:
                dimension = int(vectors.shape[1])
            for function, vector in zip(batch_functions, vectors):
                handle.write(
                    json.dumps(
                        {
                            "name": function.get("name"),
                            "file": function.get("file"),
                            "location": function.get("location"),
                            "embedding": vector.tolist(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            completed = min(start + len(batch_functions), len(functions))
            if (
                callable(progress_callback)
                and (completed == len(functions) or completed - last_reported >= progress_step)
            ):
                last_reported = completed
                progress_callback(
                    "embed_functions",
                    "progress",
                    {
                        "embedding_progress": {
                            "completed": completed,
                            "total": len(functions),
                            "output_path": str(output_path),
                        }
                    },
                )

    return {
        "embedding_result": {
            "ok": True,
            "model_path": str(model_path),
            "output_path": str(output_path),
            "count": len(functions),
            "dimension": dimension,
            "batch_size": batch_size,
        }
    }


def _function_text(item: dict[str, Any]) -> str:
    snippet = item.get("snippet") or {}
    snippet_text = snippet.get("text") or ""
    return "\n".join(
        part
        for part in [
            f"name: {item.get('name', '')}",
            f"file: {item.get('file', '')}",
            snippet_text,
        ]
        if part
    )


def _path_setting(
    request: dict[str, Any],
    request_key: str,
    env_key: str,
    fallback: Path,
) -> Path:
    return Path(request.get(request_key) or os.environ.get(env_key) or fallback)


def _required_path_setting(
    request: dict[str, Any],
    request_key: str,
    env_key: str,
) -> Path:
    value = request.get(request_key) or os.environ.get(env_key)
    if not value:
        raise RuntimeError(f"{env_key} must be set in .env or passed as {request_key}")
    return Path(value)


def _repo_output_name(state: dict[str, Any]) -> str:
    repo_result = state.get("repo_result", {})
    repo_path = repo_result.get("path")
    if repo_path:
        return Path(repo_path).name
    repo_url = repo_result.get("repo_url") or state.get("repo_request", {}).get("repo_url") or "repo"
    return Path(str(repo_url).removesuffix(".git")).name or "repo"


def _load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "embedding_result": {"ok": False, "errors": [message]},
        "errors": [*state.get("errors", []), message],
    }
