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
6. Embed extracted functions with a configurable local or API embedding model.
7. Find historical bug/security-fix commits with LLM batch filtering by default
   and extract native-code patch snippets.
8. Compare bug-fix snippets with current function embeddings and rank the most
   similar functions.
9. Ask the configured LLM to compare historical vulnerable code, fixed code,
   and similar current functions to judge whether a related bug may remain.

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
-> assess_similar_bug_risk
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
    risk/                 LLM assessments of similar-code bug risk
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
- `vulmorph/embeddings.py`: embeds extracted functions with a local
  sentence-transformers model or an OpenAI-compatible embedding API, and writes
  repo-specific JSONL output.
- `vulmorph/bug_history_mine.py`: searches git history for bug/security-fix commits
  with LLM batch filtering by default, and extracts native-code diff hunks from
  those commits.
- `vulmorph/similarity.py`: embeds bug-fix snippets and ranks current functions
  by cosine similarity against those snippets.
- `vulmorph/risk_assessment.py`: sends historical vulnerable/fixed snippets
  and similar current functions to the configured LLM for bug-risk judgment.
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
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_COMMIT_FILTER_MODEL=deepseek-v4-flash
DEEPSEEK_RISK_MODEL=deepseek-v4-pro
DEEPSEEK_TIMEOUT=
DEEPSEEK_MAX_RETRIES=

VULMORPH_EMBEDDING_PROVIDER=
VULMORPH_EMBEDDING_API_KEY=
VULMORPH_EMBEDDING_BASE_URL=
VULMORPH_EMBEDDING_MODEL=
VULMORPH_EMBEDDING_DIMENSIONS=
VULMORPH_EMBEDDING_TIMEOUT=
VULMORPH_EMBEDDING_MAX_INPUT_CHARS=
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

DeepSeek model usage can be split by task. `DEEPSEEK_MODEL` is the default
model for general analysis, `DEEPSEEK_COMMIT_FILTER_MODEL` is used for
historical commit classification, and `DEEPSEEK_RISK_MODEL` is used for the
final similar-bug risk assessment. A practical setup is flash for commit
filtering and pro for risk judgment.

The CLI prints per-node progress while running, including periodic embedding
progress such as `10/250`, and outputs a short text summary at the end. Use
`--json` to print the full LangGraph state.

Embedding uses `VULMORPH_EMBEDDING_PROVIDER=api` for OpenAI-compatible
embedding endpoints, or `local` for sentence-transformers models. For Alibaba
Cloud Model Studio/DashScope compatible mode, use:

```env
VULMORPH_EMBEDDING_PROVIDER=api
VULMORPH_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VULMORPH_EMBEDDING_MODEL=text-embedding-v4
VULMORPH_EMBEDDING_DIMENSIONS=1024
VULMORPH_EMBEDDING_MAX_INPUT_CHARS=12000
```

VulMorph trims each function text to `VULMORPH_EMBEDDING_MAX_INPUT_CHARS`
before API embedding, preserving the beginning and end of the function, so large
functions do not exceed the provider's per-input token limit.

For OpenAI-compatible Qwen3-Embedding-8B providers, set:

```env
VULMORPH_EMBEDDING_PROVIDER=api
VULMORPH_EMBEDDING_BASE_URL=<provider-compatible-base-url>
VULMORPH_EMBEDDING_MODEL=qwen3-embedding-8b
VULMORPH_EMBEDDING_DIMENSIONS=
```

If a provider exposes the model under a namespaced id, such as
`qwen/qwen3-embedding-8b`, use that exact id instead. API input texts are
trimmed to `VULMORPH_EMBEDDING_MAX_INPUT_CHARS` before embedding so unusually
large functions do not exceed provider token limits.

Historical bug-fix commit filtering uses the configured LLM by default and
processes git log entries in batches. Use `--bug-fix-commit-filter keyword` to
fall back to keyword-only filtering, or `--bug-fix-llm-batch-size` to tune the
batch size.

After similarity search, VulMorph sends the historical vulnerable code, the
fixed code, and similar current functions to the configured LLM. Use
`--bug-risk-max-cases` to control how many similar matches are assessed and
`--bug-risk-max-code-chars` to cap each code excerpt.

Outputs are written under `data/`, which is ignored by git. Function embeddings
are written to:

```text
data/embeddings/<repo-name>.functions.jsonl
```

Historical bug-fix snippets and similarity results are written to:

```text
data/bugfixes/<repo-name>.bugfix_snippets.jsonl
data/similarity/<repo-name>.bugfix_similarity.json
data/risk/<repo-name>.bug_risk_assessment.json
```

## Notes

- `CCScope/` is tracked by the root repository as a Git submodule, so the root
  repository stores only the submodule URL and commit pointer.
- The embedding provider is read from `VULMORPH_EMBEDDING_PROVIDER` in `.env`,
  or from `--embedding-provider`. Local mode uses
  `VULMORPH_EMBEDDING_MODEL_PATH`; API mode uses
  `VULMORPH_EMBEDDING_API_KEY`, `VULMORPH_EMBEDDING_BASE_URL`, and
  `VULMORPH_EMBEDDING_MODEL`.
- `transformers` is pinned below version 5 because the local Jina model depends
  on APIs from the 4.x series.
