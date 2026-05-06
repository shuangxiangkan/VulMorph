# VulMorph

VulMorph is a LangGraph-based pipeline for analyzing C/C++ repositories before
vulnerability-pattern extraction. The current MVP focuses on the first stages:

1. Clone or reuse a target Git repository.
2. Analyze the repository structure with an LLM.
3. Select the library source scope to avoid tests, fuzzers, examples, docs, and
   build artifacts.
4. Generate or reuse `compile_commands.json` for CMake and supported
   Autotools projects.
5. Extract functions from the selected source files with CCScope.
6. Embed extracted functions with a local Jina code embedding model.
7. Find historical bug/security-fix commits with LLM batch filtering by default
   and extract native-code patch snippets.
8. Compare bug-fix snippets with current function embeddings and rank the most
   similar functions.

## Current Graph

```text
acquire_repo
-> analyze_repo_structure
-> select_source_scope
-> prepare_compile_commands
-> extract_functions_with_ccscope
-> embed_functions
-> find_bug_fix_commits
-> extract_bug_fix_snippets
-> search_similar_bug_fix_code
```

## Project Structure

```text
VulMorph/
  vulmorph/               Pipeline source code
  prompts/                LLM prompt templates
  CCScope/                Git submodule for C/C++ codebase analysis
  data/                   Local runtime outputs, ignored by git
    targets/              Cloned target repositories
    embeddings/           Function embedding JSONL files
    bugfixes/             Historical bug-fix patch snippets
    similarity/           Bug-fix/function similarity results
  .env.example            Environment variable template
  requirements.txt        Python dependencies for the root project
```

Python modules:

- `vulmorph/__init__.py`: package entry point with lazy graph import.
- `vulmorph/state.py`: shared LangGraph state type definitions.
- `vulmorph/graph.py`: assembles the LangGraph pipeline and progress callback
  wrapper.
- `vulmorph/cli.py`: command-line interface, progress printing, and final run
  summary formatting.
- `vulmorph/repos.py`: clones remote repositories or reuses an existing local
  repository path.
- `vulmorph/repo_analysis.py`: summarizes repository layout and optionally asks
  an LLM to analyze the structure. The summary includes a bounded directory
  tree, native source-file list, and candidate native source directories.
- `vulmorph/source_scope.py`: selects the library source files that should be
  analyzed, filtering out tests, fuzzers, examples, docs, and build artifacts.
- `vulmorph/build_setup.py`: prepares `compile_commands.json`, currently with
  automatic CMake and Autotools capture support.
- `vulmorph/function_extraction.py`: uses CCScope and clangd to extract
  function-like symbols from the selected source scope.
- `vulmorph/embeddings.py`: embeds extracted functions with the local Jina code
  embedding model and writes repo-specific JSONL output.
- `vulmorph/bug_history_mine.py`: searches git history for bug/security-fix commits
  with LLM batch filtering by default, and extracts native-code diff hunks from
  those commits.
- `vulmorph/similarity.py`: embeds bug-fix snippets and ranks current functions
  by cosine similarity against those snippets.
- `vulmorph/llm_clients.py`: LLM client integrations, currently DeepSeek's
  OpenAI-compatible chat completion API.

Prompt templates:

- `prompts/json_system.txt`: shared system prompt for JSON-only LLM tasks.
- `prompts/repo_structure_user.txt`: user prompt for repository structure
  analysis. It uses `{payload}` as the repository summary placeholder.
- `prompts/bug_fix_commit_user.txt`: user prompt for batched git log
  classification. It uses `{payload}` as the commit batch placeholder.

## Setup

System dependencies must be installed before creating the virtual environment
or running the pipeline. Use the helper script in the repository root first:

```bash
chmod +x install_system_deps.sh
./install_system_deps.sh
```

The script installs the required system dependencies:

- `cmake`
- `clangd`
- `autoconf`
- `automake`
- `libtool`
- `bear` or `intercept-build`

Clone with submodules after the system dependencies are ready:

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
VulMorph can generate `compile_commands.json` automatically with `cmake`.
For Autotools projects, VulMorph detects `configure.ac`, `Makefile.am`, or
`autogen.sh`, then uses `bear -- make` or `intercept-build make` to capture
`compile_commands.json`. Make sure these system tools are installed first.

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
python -m vulmorph.cli https://github.com/DaveGamble/cJSON.git
```

LLM structure analysis is enabled by default with DeepSeek. Use `--llm none`
to run the deterministic heuristic path without model calls.

The CLI prints per-node progress while running, including periodic embedding
progress such as `10/250`, and outputs a short text summary at the end. Use
`--json` to print the full LangGraph state.

Historical bug-fix commit filtering uses the configured LLM by default and
processes git log entries in batches. Use `--bug-fix-commit-filter keyword` to
fall back to keyword-only filtering, or `--bug-fix-llm-batch-size` to tune the
batch size.

Outputs are written under `data/`, which is ignored by git. Function embeddings
are written to:

```text
data/embeddings/<repo-name>.functions.jsonl
```

Historical bug-fix snippets and similarity results are written to:

```text
data/bugfixes/<repo-name>.bugfix_snippets.jsonl
data/similarity/<repo-name>.bugfix_similarity.json
```

## Notes

- `CCScope/` is tracked by the root repository as a Git submodule, so the root
  repository stores only the submodule URL and commit pointer.
- The local embedding model path is read from `VULMORPH_EMBEDDING_MODEL_PATH`
  in `.env`, or from `--embedding-model-path`.
- `transformers` is pinned below version 5 because the local Jina model depends
  on APIs from the 4.x series.
