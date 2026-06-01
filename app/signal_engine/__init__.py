"""Private signal engine (Stage 6) — ISOLATED from trade execution.

ISOLATION CONTRACT (enforced by tests/test_signal_engine_isolation.py):

1. This package MUST NOT import — directly or transitively — anything that can
   open, modify or close a real trade:
       * app.execution.*            (PaperExecutor, CcxtExecutor, ...)
       * app.core.orchestrator      (Orchestrator)
       * app.core.multi_orchestrator (MultiOrchestrator)
       * app.ports.execution_port   (ExecutionPort)
   The ONLY side effect this engine is allowed to produce is a *text message*
   sent to Telegram (see app.signal_engine.notifier).

2. The dependency is ONE-WAY. No module in the main ``app`` package (anything
   outside ``app.signal_engine``) is allowed to import ``app.signal_engine``.
   This guarantees the whole private engine can be removed with a single
       rm -rf app/signal_engine scripts/run_signal_engine.py
   without breaking the sellable main product.

3. The engine runs as a SEPARATE process (scripts/run_signal_engine.py) with a
   SEPARATE config / Telegram token loaded from ``.env.signal``.

Keep this ``__init__`` import-light: importing the package must not drag in any
heavy or execution-related module.
"""

from __future__ import annotations

__all__ = ["__doc__"]
