"""Function embedding node with local and OpenAI-compatible API providers."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


FALLBACK_OUTPUT_DIR = Path("data/embeddings")
DEFAULT_API_TIMEOUT = 120.0
DEFAULT_API_MAX_INPUT_CHARS = 12000
_LOCAL_MODELS: dict[str, Any] = {}


def embed_functions(state: dict[str, Any]) -> dict[str, Any]:
    """Embed extracted functions with the configured embedding provider."""

    extraction = state.get("function_extraction", {})
    if not extraction.get("ok"):
        return _failure(state, "function extraction failed; cannot embed functions")

    request = dict(state.get("repo_request", {}))
    _load_env_file()
    output_dir = _path_setting(
        request,
        "embedding_output_dir",
        "VULMORPH_EMBEDDING_OUTPUT_DIR",
        FALLBACK_OUTPUT_DIR,
    )
    batch_size = max(
        1,
        int(request.get("embedding_batch_size") or os.environ.get("VULMORPH_EMBEDDING_BATCH_SIZE", 4)),
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    functions = extraction.get("functions", [])
    output_path = output_dir / f"{_repo_output_name(state)}.functions.jsonl"
    if not functions:
        output_path.write_text("", encoding="utf-8")
        config = _embedding_config(request)
        return {
            "embedding_result": {
                "ok": True,
                "provider": config["provider"],
                "model": config.get("model"),
                "output_path": str(output_path),
                "count": 0,
                "dimension": 0,
            }
        }

    texts = [_function_text(item) for item in functions]

    dimension = 0
    progress_callback = state.get("_progress_callback")
    progress_step = max(10, batch_size)
    last_reported = 0
    current_batch_size = batch_size
    min_batch_size_used = batch_size
    with output_path.open("w", encoding="utf-8") as handle:
        start = 0
        while start < len(functions):
            batch_functions = functions[start:start + current_batch_size]
            batch_texts = texts[start:start + current_batch_size]
            try:
                vectors = embed_texts(batch_texts, request)
            except Exception as exc:
                if current_batch_size == 1:
                    return _failure(state, f"embedding failed at item {start}: {exc}")
                current_batch_size = max(1, current_batch_size // 2)
                min_batch_size_used = min(min_batch_size_used, current_batch_size)
                if callable(progress_callback):
                    progress_callback(
                        "embed_functions",
                        "progress",
                        {
                            "embedding_progress": {
                                "completed": start,
                                "total": len(functions),
                                "output_path": str(output_path),
                            }
                        },
                    )
                continue
            if vectors and dimension == 0:
                dimension = len(vectors[0])
            for function, vector in zip(batch_functions, vectors):
                handle.write(
                    json.dumps(
                        {
                            "name": function.get("name"),
                            "file": function.get("file"),
                            "location": function.get("location"),
                            "embedding": vector,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            start += len(batch_functions)
            completed = min(start, len(functions))
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

    config = _embedding_config(request)
    return {
        "embedding_result": {
            "ok": True,
            "provider": config["provider"],
            "model": config.get("model"),
            "output_path": str(output_path),
            "count": len(functions),
            "dimension": dimension,
            "batch_size": min_batch_size_used,
            "requested_batch_size": batch_size,
        }
    }


def embed_texts(texts: list[str], request: dict[str, Any]) -> list[list[float]]:
    """Embed text batches using the configured provider."""

    config = _embedding_config(request)
    if config["provider"] == "api":
        return _embed_texts_api(texts, config)
    if config["provider"] == "local":
        return _embed_texts_local(texts, config)
    raise RuntimeError(f"unsupported embedding provider: {config['provider']}")


def _embed_texts_local(texts: list[str], config: dict[str, Any]) -> list[list[float]]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("sentence-transformers is required for local embedding") from exc

    model_path = str(config["model_path"])
    model = _LOCAL_MODELS.get(model_path)
    if model is None:
        model = SentenceTransformer(model_path, trust_remote_code=True)
        _LOCAL_MODELS[model_path] = model
    vectors = model.encode(
        texts,
        batch_size=min(int(config["batch_size"]), len(texts)),
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return [vector.tolist() for vector in vectors]


def _embed_texts_api(texts: list[str], config: dict[str, Any]) -> list[list[float]]:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required for API embedding") from exc

    base_url = str(config["base_url"]).rstrip("/")
    input_texts = [_fit_api_input(text, int(config["max_input_chars"])) for text in texts]
    payload: dict[str, Any] = {
        "model": config["model"],
        "input": input_texts,
        "encoding_format": "float",
    }
    if config.get("dimensions"):
        payload["dimensions"] = int(config["dimensions"])

    with httpx.Client(timeout=float(config["timeout"])) as client:
        response = client.post(
            f"{base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"embedding API returned HTTP {response.status_code}: {response.text[:500]}")

    data = response.json()
    items = data.get("data")
    if not isinstance(items, list):
        raise RuntimeError("embedding API response missing data list")
    items = sorted(items, key=lambda item: item.get("index", 0))
    vectors = [item.get("embedding") for item in items]
    if len(vectors) != len(texts) or not all(isinstance(vector, list) for vector in vectors):
        raise RuntimeError("embedding API response size did not match request size")
    return _normalize_vectors(vectors)


def _embedding_config(request: dict[str, Any]) -> dict[str, Any]:
    provider = (
        request.get("embedding_provider")
        or os.environ.get("VULMORPH_EMBEDDING_PROVIDER")
        or "local"
    ).strip().lower()
    batch_size = max(
        1,
        int(request.get("embedding_batch_size") or os.environ.get("VULMORPH_EMBEDDING_BATCH_SIZE", 4)),
    )
    if provider == "local":
        model_path = _required_path_setting(
            request,
            "embedding_model_path",
            "VULMORPH_EMBEDDING_MODEL_PATH",
        )
        return {
            "provider": provider,
            "model_path": model_path,
            "model": str(model_path),
            "batch_size": batch_size,
        }
    if provider == "api":
        return {
            "provider": provider,
            "api_key": _required_string_setting(
                request,
                "embedding_api_key",
                "VULMORPH_EMBEDDING_API_KEY",
            ),
            "base_url": _required_string_setting(
                request,
                "embedding_base_url",
                "VULMORPH_EMBEDDING_BASE_URL",
            ),
            "model": _required_string_setting(
                request,
                "embedding_model",
                "VULMORPH_EMBEDDING_MODEL",
            ),
            "dimensions": request.get("embedding_dimensions") or os.environ.get("VULMORPH_EMBEDDING_DIMENSIONS", ""),
            "timeout": request.get("embedding_timeout") or os.environ.get("VULMORPH_EMBEDDING_TIMEOUT", DEFAULT_API_TIMEOUT),
            "max_input_chars": (
                request.get("embedding_max_input_chars")
                or os.environ.get("VULMORPH_EMBEDDING_MAX_INPUT_CHARS", DEFAULT_API_MAX_INPUT_CHARS)
            ),
            "batch_size": batch_size,
        }
    raise RuntimeError("VULMORPH_EMBEDDING_PROVIDER must be 'local' or 'api'")


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


def _required_string_setting(
    request: dict[str, Any],
    request_key: str,
    env_key: str,
) -> str:
    value = request.get(request_key) or os.environ.get(env_key)
    if not value:
        raise RuntimeError(f"{env_key} must be set in .env or passed as {request_key}")
    return str(value)


def _normalize_vectors(vectors: list[list[float]]) -> list[list[float]]:
    normalized = []
    for vector in vectors:
        numeric = [float(value) for value in vector]
        norm = math.sqrt(sum(value * value for value in numeric))
        if norm:
            numeric = [value / norm for value in numeric]
        normalized.append(numeric)
    return normalized


def _fit_api_input(text: str, max_chars: int) -> str:
    text = text.strip()
    if not text:
        return "(empty)"
    if max_chars <= 0 or len(text) <= max_chars:
        return text

    marker = "\n\n/* ... truncated for embedding API input limit ... */\n\n"
    if max_chars <= len(marker) + 2:
        return text[:max_chars]
    budget = max_chars - len(marker)
    head_chars = max(1, budget * 2 // 3)
    tail_chars = max(1, budget - head_chars)
    return text[:head_chars].rstrip() + marker + text[-tail_chars:].lstrip()


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
