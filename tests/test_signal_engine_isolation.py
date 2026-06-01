"""Enforce the Stage 6 isolation contract of ``app.signal_engine``.

Two invariants, checked statically over the import graph (AST, no code is run):

1. FORWARD — ``app.signal_engine.*`` must not reach, *transitively*, any module
   that can open/modify/close a trade (executors, orchestrators, ExecutionPort).
   Its only allowed side effect is sending Telegram text.

2. REVERSE — no module of the main ``app`` package (anything outside
   ``app.signal_engine``) may import ``app.signal_engine``. This keeps the
   dependency one-way so the private engine is removable with a single
   ``rm -rf app/signal_engine`` without breaking the sellable product.

The test resolves imports transitively, so a violation hidden behind an
intermediate module (e.g. importing ``app.core`` whose ``__init__`` pulls in the
orchestrator) still fails the build.
"""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path

import app

APP_DIR = Path(app.__file__).resolve().parent
APP_PKG = "app"
SIGNAL_PKG = "app.signal_engine"

# Modules/prefixes the signal engine must never reach (directly or transitively).
FORBIDDEN_PREFIXES = (
    "app.execution",
    "app.core.orchestrator",
    "app.core.multi_orchestrator",
    "app.ports.execution_port",
)


def _module_name(path: Path) -> str:
    """Dotted module name for a .py file inside the app package."""
    rel = path.resolve().relative_to(APP_DIR.parent)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_package_init(path: Path) -> bool:
    return path.name == "__init__.py"


def _all_app_modules() -> dict[str, Path]:
    return {
        _module_name(p): p
        for p in APP_DIR.rglob("*.py")
        if "__pycache__" not in p.parts
    }


def _resolve_relative(module: str, is_pkg: bool, level: int, sub: str | None) -> str:
    """Resolve a ``from ... import`` relative target to an absolute module name."""
    if is_pkg:
        base = module
    else:
        base = module.rpartition(".")[0]
    for _ in range(level - 1):
        base = base.rpartition(".")[0]
    if sub:
        return f"{base}.{sub}" if base else sub
    return base


def _imports_of(module: str, path: Path) -> set[str]:
    """All ``app.*`` modules this file imports (direct edges in the graph)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    is_pkg = _is_package_init(path)
    edges: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                target = _resolve_relative(module, is_pkg, node.level, node.module)
            else:
                target = node.module or ""
            if not target:
                continue
            edges.add(target)
            # ``from pkg import name`` where name may itself be a submodule.
            for alias in node.names:
                edges.add(f"{target}.{alias.name}")

    return {e for e in edges if e == APP_PKG or e.startswith(APP_PKG + ".")}


def _build_graph() -> dict[str, set[str]]:
    """module -> set of app.* modules it imports, restricted to known modules."""
    modules = _all_app_modules()
    known = set(modules)
    graph: dict[str, set[str]] = {}
    for name, path in modules.items():
        resolved: set[str] = set()
        for edge in _imports_of(name, path):
            if edge in known:
                resolved.add(edge)
            else:
                # ``from pkg import symbol`` resolves to the package module.
                parent = edge.rpartition(".")[0]
                if parent in known:
                    resolved.add(parent)
        graph[name] = resolved
    return graph


def _is_forbidden(mod: str) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in FORBIDDEN_PREFIXES)


def test_signal_engine_does_not_reach_execution() -> None:
    """FORWARD: no transitive path from signal_engine to any trade-opening code."""
    graph = _build_graph()
    seeds = [m for m in graph if m == SIGNAL_PKG or m.startswith(SIGNAL_PKG + ".")]
    assert seeds, "signal_engine package not found — test would be vacuous"

    # BFS over the graph, remembering the path for a readable failure message.
    parent: dict[str, str | None] = {s: None for s in seeds}
    queue: deque[str] = deque(seeds)
    while queue:
        cur = queue.popleft()
        for nxt in graph.get(cur, ()):  # noqa: B007
            if _is_forbidden(nxt):
                # Reconstruct the offending chain.
                chain = [nxt, cur]
                node = parent.get(cur)
                while node is not None:
                    chain.append(node)
                    node = parent.get(node)
                chain.reverse()
                raise AssertionError(
                    "signal_engine reaches forbidden execution module via:\n  "
                    + " -> ".join(chain)
                )
            if nxt not in parent:
                parent[nxt] = cur
                queue.append(nxt)


def test_main_app_does_not_import_signal_engine() -> None:
    """REVERSE: nothing outside signal_engine may import it (rm -rf must be safe)."""
    graph = _build_graph()
    offenders: list[str] = []
    for module, edges in graph.items():
        if module == SIGNAL_PKG or module.startswith(SIGNAL_PKG + "."):
            continue
        if any(e == SIGNAL_PKG or e.startswith(SIGNAL_PKG + ".") for e in edges):
            offenders.append(module)

    assert not offenders, (
        "main app imports app.signal_engine (breaks one-way isolation / rm -rf):\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_signal_engine_notifier_only_output_is_telegram_text() -> None:
    """Guard: notifier never imports an executor/order/port — only sends text."""
    graph = _build_graph()
    notifier = "app.signal_engine.notifier"
    assert notifier in graph, "notifier module missing"
    for edge in graph[notifier]:
        assert not _is_forbidden(edge), f"notifier reaches forbidden module: {edge}"
