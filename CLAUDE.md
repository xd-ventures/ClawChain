# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClawChain is "AI Agents as a Service, powered by Solana." Users deposit SOL via an on-chain program and receive a personal AI bot on Telegram — no accounts, no subscriptions. The MVP uses PicoClaw (<10MB RAM, single Go binary) deployed on dedicated GCP micro VMs.

## Architecture

Three main components:

1. **Solana Program (Anchor/Rust)** — On-chain state: user deposits, bot handle registry, active/stopped flags, billing transfers. Wallet-to-bot-handle mapping is intentionally public for cryptographic identity verification.
2. **Orchestrator (Python + SQLite)** — Watches blockchain for new deposits, provisions GCP micro VMs from a template, writes bot handles back on-chain, runs periodic billing loop (user → operator account).
3. **PicoClaw VMs (GCP)** — Each user gets a dedicated micro VM running a PicoClaw instance with native Telegram integration.

## Tech Stack

| Layer | Technology |
|---|---|
| Smart Contracts | Anchor (Rust) on Solana |
| Orchestrator | Python + SQLite |
| AI Agent | PicoClaw (Go binary) |
| Infrastructure (MVP) | GCP micro VMs |
| Infrastructure (planned) | Kubernetes on Talos Linux bare metal via tf-xd-venture-talos01 |
| User Interface | Telegram |

## Build & Development Commands

*This section should be updated as components are implemented.*

### Solana Program (Anchor)
```bash
anchor build          # compile the program
anchor test           # run tests (starts local validator)
anchor deploy         # deploy to configured cluster
```

### Orchestrator (Python)
```bash
# Commands TBD — update when orchestrator scaffolding is added
```

## Design Constraints

- Dedicated VMs (not containers) for isolation in the MVP; production target is Kubernetes on bare metal.
- PicoClaw was chosen over NemoClaw (NVIDIA OpenClaw) for minimal footprint and fast iteration.
- Bot handle is written on-chain after VM provisioning completes — the orchestrator must handle the write-back transaction.
- Billing is periodic (orchestrator-driven), not per-request.
