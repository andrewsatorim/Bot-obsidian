"""Engine-level behaviour: the x2 leverage filter and edge-triggered dedup.

No network: we drive ``run_once`` by monkeypatching ``select_setups`` (so each
scan yields exactly the setups we choose) and capture what the notifier sends.
The collector/context-cache are inert stubs because ``select_setups`` is faked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

import app.signal_engine.engine as engine_mod
from app.signal_engine.config import SignalSettings
from app.signal_engine.engine import SignalEngine
from app.signal_engine.setups import SignalSetup


def _const_select(result: list):
    """Async ``select_setups`` stub returning the same list every scan."""

    async def _select(*_a, **_k):
        return list(result)

    return _select


def _seq_select(scans: Iterable[list]):
    """Async ``select_setups`` stub returning the next list per scan."""
    it = iter(scans)

    async def _select(*_a, **_k):
        return next(it)

    return _select


class _CaptureNotifier:
    """Records the text of every message instead of hitting Telegram."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


def _setup(symbol: str = "SOL/USDT:USDT", direction: str = "LONG", *, atr: float) -> SignalSetup:
    """A setup whose x2 leverage is driven by ``atr`` (bigger atr -> wider target
    -> lower leverage_for_2x). price=100 keeps the move math easy to reason about."""
    return SignalSetup(
        symbol=symbol,
        direction=direction,
        strength=0.8,
        quality=1.0,
        factors={"signal": True, "regime": True, "liquidity": None, "oi": None},
        price=100.0,
        atr=atr,
        regime="TREND_UP",
        reason="signal+regime",
    )


def _engine(notifier: _CaptureNotifier, settings: SignalSettings | None = None) -> SignalEngine:
    # select_setups is monkeypatched in every test, so collector/context_cache
    # are never actually called — inert stubs are fine.
    settings = settings or SignalSettings(symbols=["X/USDT:USDT"], max_leverage=50.0)
    return SignalEngine(
        settings=settings, notifier=notifier, collector=object(), context_cache=object()
    )


# atr=2.0 at price 100 (atr_mult 1.5, rr 2, fee 0.0005): target move 6%, net 5.9%
# -> leverage_for_2x ~= 16.95x  (<= 50, passes).
# atr=0.3: target move 0.9%, net 0.8% -> leverage_for_2x ~= 125x  (> 50, filtered).
_REACHABLE_ATR = 2.0
_UNREACHABLE_ATR = 0.3


def test_x2_filter_drops_setup_needing_more_than_max_leverage(monkeypatch) -> None:
    notifier = _CaptureNotifier()
    eng = _engine(notifier)
    monkeypatch.setattr(engine_mod, "select_setups", _const_select([_setup(atr=_UNREACHABLE_ATR)]))

    passed = asyncio.run(eng.run_once())

    assert passed == []          # filtered out, not returned
    assert notifier.sent == []   # and never sent to Telegram


def test_x2_reachable_setup_passes_and_is_sent(monkeypatch) -> None:
    notifier = _CaptureNotifier()
    eng = _engine(notifier)
    monkeypatch.setattr(engine_mod, "select_setups", _const_select([_setup(atr=_REACHABLE_ATR)]))

    passed = asyncio.run(eng.run_once())

    assert len(passed) == 1
    assert len(notifier.sent) == 1
    # The x2 line shows a capped leverage with the (<=50) annotation.
    assert "(≤50)" in notifier.sent[0]


def test_mixed_scan_sends_only_the_reachable_one(monkeypatch) -> None:
    notifier = _CaptureNotifier()
    eng = _engine(notifier)
    monkeypatch.setattr(
        engine_mod,
        "select_setups",
        _const_select(
            [
                _setup(symbol="SOL/USDT:USDT", atr=_REACHABLE_ATR),
                _setup(symbol="BTC/USDT:USDT", atr=_UNREACHABLE_ATR),
            ]
        ),
    )

    passed = asyncio.run(eng.run_once())

    assert [s.symbol for s in passed] == ["SOL/USDT:USDT"]
    assert len(notifier.sent) == 1
    assert "SOL/USDT:USDT" in notifier.sent[0]


def test_dedup_same_setup_not_resent_on_repeated_scans(monkeypatch) -> None:
    notifier = _CaptureNotifier()
    eng = _engine(notifier)
    monkeypatch.setattr(engine_mod, "select_setups", _const_select([_setup(atr=_REACHABLE_ATR)]))

    asyncio.run(eng.run_once())
    asyncio.run(eng.run_once())
    asyncio.run(eng.run_once())

    assert len(notifier.sent) == 1  # alerted once, not once per scan


def test_dedup_rearms_after_setup_disappears(monkeypatch) -> None:
    notifier = _CaptureNotifier()
    eng = _engine(notifier)

    monkeypatch.setattr(
        engine_mod,
        "select_setups",
        _seq_select(
            [
                [_setup(atr=_REACHABLE_ATR)],  # appears -> alert
                [],                            # gone -> re-arm
                [_setup(atr=_REACHABLE_ATR)],  # reappears -> alert again
            ]
        ),
    )

    asyncio.run(eng.run_once())
    asyncio.run(eng.run_once())
    asyncio.run(eng.run_once())

    assert len(notifier.sent) == 2  # one per appearance, not the middle empty scan


def test_dedup_distinguishes_direction_flip(monkeypatch) -> None:
    """A LONG then a SHORT on the same symbol are different trade ideas -> two alerts."""
    notifier = _CaptureNotifier()
    eng = _engine(notifier)

    monkeypatch.setattr(
        engine_mod,
        "select_setups",
        _seq_select(
            [
                [_setup(direction="LONG", atr=_REACHABLE_ATR)],
                [_setup(direction="SHORT", atr=_REACHABLE_ATR)],
            ]
        ),
    )

    asyncio.run(eng.run_once())
    asyncio.run(eng.run_once())

    assert len(notifier.sent) == 2
