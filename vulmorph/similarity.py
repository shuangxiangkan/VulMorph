"""Similarity search between current functions and historical bug-fix snippets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .embeddings import _load_env_file, _repo_output_name, _required_path_setting


FALLBACK_OUTPUT_DIR = Path("data/similarity")


def search_similar_bug_fix_code(state: dict[str, Any]) -> dict[str, Any]:
    """Embed bug-fix snippets and rank current functions by cosine similarity."""

    embedding_result = state.get("embedding_result", {})
    snippets_result = state.get("bug_fix_snippets", {})
    if not embedding_result.get("ok"):
        return _failure(state, "function embedding failed; cannot search similarity")
    if not snippets_result.get("ok"):
        return _failure(state, "bug-fix snippet extraction failed; cannot search similarity")

    request = dict(state.get("repo_request", {}))
    top_k = int(request.get("bug_fix_top_k", 10))
    batch_size = max(1, int(request.get("embedding_batch_size", 4)))
    output_dir = Path(request.get("similarity_output_dir", FALLBACK_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_repo_output_name(state)}.bugfix_similarity.json"

    functions = _read_function_embeddings(Path(embedding_result["output_path"]))
    snippets = snippets_result.get("items", [])
    if not functions or not snippets:
        payload = {"ok": True, "count": 0, "items": [], "output_path": str(output_path)}
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"similarity_result": payload}

    _load_env_file()
    try:
        model_path = _required_path_setting(request, "embedding_model_path", "VULMORPH_EMBEDDING_MODEL_PATH")
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(str(model_path), trust_remote_code=True)
        snippet_vectors = model.encode(
            [_snippet_text(item) for item in snippets],
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
    except Exception as exc:
        return _failure(state, f"bug-fix snippet embedding failed: {exc}")

    function_matrix = np.array([item["embedding"] for item in functions], dtype=np.float32)
    snippet_matrix = np.array(snippet_vectors, dtype=np.float32)
    scores = snippet_matrix @ function_matrix.T

    matches = []
    for snippet_index, snippet in enumerate(snippets):
        row = scores[snippet_index]
        best_indices = np.argsort(row)[::-1][:top_k]
        for function_index in best_indices:
            function = functions[int(function_index)]
            matches.append(
                {
                    "similarity": float(row[int(function_index)]),
                    "bug_fix": {
                        "commit": snippet["commit"],
                        "subject": snippet["subject"],
                        "file": snippet["file"],
                        "hunk_header": snippet["hunk_header"],
                    },
                    "function": {
                        "name": function.get("name"),
                        "file": function.get("file"),
                        "location": function.get("location"),
                    },
                }
            )
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    matches = matches[:top_k]

    payload = {
        "ok": True,
        "count": len(matches),
        "top_k": top_k,
        "output_path": str(output_path),
        "items": matches,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"similarity_result": payload}


def _read_function_embeddings(path: Path) -> list[dict[str, Any]]:
    functions = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                functions.append(json.loads(line))
    return functions


def _snippet_text(item: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            f"commit: {item.get('commit', '')}",
            f"subject: {item.get('subject', '')}",
            f"file: {item.get('file', '')}",
            item.get("text", ""),
        ]
        if part
    )


def _failure(state: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "similarity_result": {"ok": False, "errors": [message]},
        "errors": [*state.get("errors", []), message],
    }
