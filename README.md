# VulMorph

VulMorph is a LangGraph-based pipeline for analyzing C/C++ repositories before
vulnerability-pattern extraction. The current MVP focuses on the first stages:

1. Clone or reuse a target Git repository.
2. Analyze the repository structure with an LLM.
3. Select the library source scope to avoid tests, fuzzers, examples, docs, and
   build artifacts.
4. Generate or reuse `compile_commands.json`.
5. Extract functions from the selected source files with CCScope.
6. Embed extracted functions with a local Jina code embedding model.

## Current Graph

```text
acquire_repo
-> analyze_repo_structure
-> select_source_scope
-> prepare_compile_commands
-> extract_functions_with_ccscope
-> embed_functions
```

## Setup

Clone with submodules:

```bash
git clone --recurse-submodules <repo-url>
```

If the repository was already cloned:

```bash
git submodule update --init --recursive
```

Create and activate the virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -r CCScope/requirements.txt
python -m pip install -e CCScope
```

CCScope requires `clangd >= 18` and a compilation database. For CMake projects,
VulMorph can generate `compile_commands.json` automatically, but `cmake` must be
installed.

On Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y cmake clangd-18
```

## Environment

Copy the template and fill in local values:

```bash
cp .env.example .env
```

Required fields:

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=
DEEPSEEK_MODEL=

VULMORPH_EMBEDDING_MODEL_PATH=
VULMORPH_EMBEDDING_OUTPUT_DIR=
VULMORPH_EMBEDDING_BATCH_SIZE=
```

`.env` is ignored by git. Do not commit real API keys.

## Run

Example with cJSON:

```bash
source .venv/bin/activate
python -m vulmorph.cli https://github.com/DaveGamble/cJSON.git --llm deepseek --force-pull
```

The CLI prints per-node progress while running, including periodic embedding
progress such as `10/250`, and outputs a short text summary at the end. Use
`--json` to print the full LangGraph state.

Outputs are written under `data/`, which is ignored by git. Function embeddings
are written to:

```text
data/embeddings/<repo-name>.functions.jsonl
```

## Notes

- `CCScope/` is tracked by the root repository as a Git submodule, so the root
  repository stores only the submodule URL and commit pointer.
- The local embedding model path is read from `VULMORPH_EMBEDDING_MODEL_PATH`
  in `.env`, or from `--embedding-model-path`.
- `transformers` is pinned below version 5 because the local Jina model depends
  on APIs from the 4.x series.
