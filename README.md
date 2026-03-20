# Bot Obsidian

Multi-Layer Crypto Decision Engine.

This repository contains the project skeleton for a modular crypto trading system with:

- market structure and derivatives-driven setup detection
- statistical regime analysis
- on-chain intelligence
- event/news filtering
- risk, execution, and venue selection layers
- Telegram Bot and Telegram Mini App control surface

## Current state

This is a bootstrap architecture commit. It includes:

- project structure
- domain models (DTOs)
- service interfaces (ports)
- config templates
- empty module implementations ready for iterative coding

## Planned modules

- `app/core`: orchestration and dependency wiring
- `app/models`: domain models and DTOs
- `app/ports`: service interfaces
- `app/analytics`: feature engine, regime classifier, expectancy models
- `app/strategy`: setup detection, fusion, and decision engine
- `app/risk`: sizing and portfolio risk controls
- `app/execution`: venue selection, order routing, and position management
- `app/feeds`: exchange, derivatives, news, on-chain, and social inputs
- `app/telegram`: bot and mini app adapters
- `tests`: unit tests and contract tests

## Next implementation order

1. Data contracts and interfaces
2. Feature engine
3. Strategy engine
4. Risk and execution
5. Telegram control plane

## Status

Architecture bootstrap only. No live trading logic has been implemented yet.
