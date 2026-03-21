# ClawChain

**AI Agents as a Service, powered by Solana.**

ClawChain lets you spawn your own AI agent with a single on-chain transaction. Deposit SOL, get a personal AI bot on Telegram — no accounts, no subscriptions, no DevOps. The MVP uses [PicoClaw](https://github.com/sipeed/picoclaw), an ultra-lightweight AI assistant (<10MB RAM), running in Docker on GCP Container-Optimized OS VMs.

## The Problem

AI agents are becoming mainstream, but running your own is still a pain:

- **Infrastructure overhead** — you need servers, configs, and ops knowledge just to keep a bot alive
- **Billing friction** — subscriptions, credit cards, invoices — all of it before your agent does anything useful
- **No verifiable identity** — how do you prove a bot is who it claims to be?

## The Solution

ClawChain makes it as simple as sending a transaction:

1. **Prepaid with SOL** — Deposit to the ClawChain program on Solana. That's your account.
2. **Automatic provisioning** — An orchestrator watches the chain, sees your deposit, and spins up a fresh PicoClaw instance on a dedicated VM.
3. **Telegram bot delivery** — Once your agent is live, its Telegram bot handle is written to your on-chain account. Open Telegram, start chatting.
4. **Pay-as-you-run** — The orchestrator periodically transfers a portion of your balance to the operational account while your bot is active.
5. **Stop anytime** — Set a flag on your on-chain account, and the orchestrator shuts down your VM and stops billing.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Solana Blockchain                       │
│                                                                │
│  ┌──────────────┐  ┌───────────────────┐  ┌─────────────────┐  │
│  │ User Account │  │ ClawChain Program │  │    Operator     │  │
│  │  (deposit,   │  │  (on-chain state, │  │    Account      │  │
│  │  bot handle, │  │   bot registry)   │  │  (operational   │  │
│  │  stop flag)  │  │                   │  │     funds)      │  │
│  └──────────────┘  └───────────────────┘  └─────────────────┘  │
└───────────────────────────┬────────────────────────────────────┘
                            │ watches
                            ▼
              ┌────────────────────────────┐
              │      Orchestrator VM       │
              │     (Python + SQLite)      │
              │                            │
              │  • Blockchain watcher      │
              │  • GCP API integration     │
              │  • Billing loop            │
              └─────────────┬──────────────┘
                            │ provisions / stops
                            ▼
          ┌──────────────────────────────────────┐
          │           GCP Micro VMs              │
          │                                      │
          │  ┌──────────┐  ┌──────────┐          │
          │  │ PicoClaw │  │ PicoClaw │   ...    │
          │  │ Instance │  │ Instance │          │
          │  │ (Bot @a) │  │ (Bot @b) │          │
          │  └──────────┘  └──────────┘          │
          └──────────────────┬───────────────────┘
                             │
                             ▼
                        [ Telegram ]
                      User interacts
                      with their bot
```

### Components

- **ClawChain Program** (Solana) — On-chain state: user deposits, bot handle registry, active/stopped flags, provisioning status, service capacity. Wallet address + bot handle are publicly visible on-chain by design — this enables cryptographic verification of bot identity. Includes escrow-like provisioning guarantees (funds locked during VM creation, refunded if provisioning fails).
- **Orchestrator** (Python + SQLite) — Watches the blockchain for new deposits, provisions GCP Container-Optimized OS VMs, writes bot handles back to the chain, runs the billing loop, and monitors container health. Supports mock mode for development without blockchain or GCP.
- **PicoClaw VMs** (GCP) — Each user gets a dedicated Container-Optimized OS VM running the [PicoClaw](https://github.com/sipeed/picoclaw) Docker image (`docker.io/sipeed/picoclaw:latest`). Config (LLM API key + Telegram bot token) injected via cloud-init.

## User Flow

```
User                        Solana                    Orchestrator                GCP
 │                            │                            │                      │
 ├─── deposit SOL ──────────► │                            │                      │
 │                            ├─── new deposit event ────► │                      │
 │                            │ ◄── lock funds ────────────┤                      │
 │                            │                            ├─── create VM ──────► │
 │                            │                            │ ◄── VM ready ────────┤
 │                            │                            ├─── health check ───► │
 │                            │                            │ ◄── healthy ─────────┤
 │                            │ ◄── write bot handle ──────┤                      │
 │◄── see bot handle in UI ───┤                            │                      │
 │                            │                            │                      │
 │─── chat on Telegram ──────────────────────────────────────────────────────────►│
 │                            │                            │                      │
 │                            │ ◄── periodic billing ──────┤                      │
 │                            │     (user → operator)      │                      │
 │                            │                            │                      │
 ├─── set stop flag ────────► │                            │                      │
 │                            ├─── stop flag detected ───► │                      │
 │                            │                            ├─── delete VM ──────► │
 │                            │                            ├─── stop billing      │
 │                            │                            │                      │
 │  [If VM fails to start within 5 min]                    │                      │
 │                            │ ◄── refund (deactivate) ───┤                      │
 │◄── withdraw deposit ───────┤                            │                      │
```

## Design Decisions

**Why PicoClaw?** NemoClaw (NVIDIA's enterprise OpenClaw stack) was our initial target, but proved impractical for rapid iteration. PicoClaw's minimal footprint (<10MB RAM, single binary, native Telegram support) makes it ideal for spinning up isolated agent instances quickly and cheaply on micro VMs.

**Why wallet + bot handle on-chain?** This is a feature, not a leak. Public on-chain mapping of wallet addresses to Telegram bot handles enables cryptographic identity verification — you can prove a bot belongs to a specific wallet. Want a private bot? Create a fresh wallet.

**Why Container-Optimized OS?** Each user gets a dedicated GCP VM running Container-Optimized OS with the PicoClaw Docker image. No custom base image to maintain — COS pulls the container automatically. Config is injected via cloud-init. The production path is Kubernetes on bare metal via [tf-xd-venture-talos01](https://github.com/xd-ventures/tf-xd-venture-talos01).

**Why Telegram?** PicoClaw has native multi-channel support (Telegram, Discord, WhatsApp, Matrix, etc.). Telegram is the MVP channel — expanding to others is straightforward.

## Tech Stack

| Layer | Technology |
|---|---|
| AI Agent | [PicoClaw](https://github.com/sipeed/picoclaw) (Go, Docker image, <10MB) |
| Blockchain | Solana (devnet) |
| Smart Contracts | Anchor (Rust), 10 instructions, 3 PDA account types |
| Orchestrator | Python + SQLite + mock chain backend for testing |
| LLM Provider | [OpenRouter](https://openrouter.ai/) (auto model selection) |
| Infrastructure (MVP) | GCP Container-Optimized OS VMs (europe-central2 / Warsaw) |
| Infrastructure (planned) | Kubernetes ([Talos Linux](https://www.talos.dev/)) on bare metal via [tf-xd-venture-talos01](https://github.com/xd-ventures/tf-xd-venture-talos01) |
| User Interface | Telegram (via PicoClaw native integration) |
| Testing | Anchor/Mocha (25 on-chain tests) + pytest (51 orchestrator tests) |

## Roadmap

- [x] Project concept & architecture design
- [x] Solana program (deposits, bot registry, stop flag, billing, escrow-like provisioning, capacity management)
- [x] Orchestrator (blockchain watcher + GCP provisioning + health monitoring + mock mode)
- [x] PicoClaw container deployment on GCP Container-Optimized OS
- [x] Test suite (25 on-chain + 51 orchestrator tests)
- [ ] Devnet E2E: initialize program state + test full flow with real Solana
- [ ] Web UI for deposit & bot status
- [ ] Access control (restrict bot to wallet owner, optional sharing)
- [ ] Multi-channel support (Discord, WhatsApp, Matrix)
- [ ] Proof-of-uptime mechanism (verify VM was actually running)
- [ ] Agent marketplace with discovery and ratings
- [ ] Multi-framework support (beyond PicoClaw)

## Why ClawChain?

The name reflects our vision: **Claw** for the AI agent ecosystem (OpenClaw/PicoClaw), **Chain** for the blockchain settlement layer — and the ambition to build a *chain* of interconnected AI agents that can discover, compose, and transact with each other autonomously.

## Team

**Maciej Sawicki** — Cloud Architect, SRE, Infrastructure Engineer

Background spanning Web3 infrastructure (validator operations), AI/ML platforms, and production-grade telecom systems. Certified GCP Cloud Architect and Kubernetes Application Developer.

- [xd.ventures](https://xd.ventures)
- [GitHub](https://github.com/xd-ventures)
- [Twitter/X](https://x.com/ClawChain_0x)

## License

MIT

---

*Forged at [Blockchain Hack Warsaw](https://luma.com/HACKWARSAW) — organized by [Superteam Poland](https://pl.superteam.fun/), the talent layer of [Solana](https://solana.com) in 🇵🇱. Heading to the [Colosseum](https://colosseum.com/) Hackathon — from Brain Embassy, Warsaw straight to the arena.*
