# Collectors

Collectors gather structured evidence that later LangGraph agents can inspect.

Current modules:

- `git_repo.py`: shared git operations, repository setup, log reading, commit stats.
- `commit_scoring.py`: heuristic ranking for bug/security-fix commits.
- `nodes.py`: small adapter that turns collector functions into stable LangGraph nodes.
- `git_log_bug_search.py`: LangGraph-ready node and CLI for finding candidate bug-fix commits.
- `patch_similarity_search.py`: placeholder node interface for recurring/incomplete-fix search.

Planned modules:

- `recurring_vulnerability_search.py`: search the same repository for code locations similar to a fixed bug.
- `incomplete_fix_search.py`: inspect whether a patch fixed one path but left sibling paths or variants unfixed.

Design rule:

Keep shared repository/diff utilities separate from task-specific collectors. A collector should expose one plain-dict function and one `CollectorNode`:

```python
def collect_x(request: dict) -> dict:
    ...

COLLECT_X_NODE = CollectorNode(
    name="collect_x",
    input_key="collect_x",
    output_key="collect_x_result",
    collect=collect_x,
)
```

The graph layer should connect nodes from `COLLECTOR_NODES` instead of importing collector internals directly.

`COLLECTOR_NODES` lives in `vulmorph.collectors.registry` to keep CLI modules import-safe.
