# ClawChain

**AI Agents as a Service, powered by Solana.**

ClawChain lets you spawn your own AI agent with a single on-chain transaction. Deposit SOL, get a personal AI bot on Telegram — no accounts, no subscriptions, no DevOps. The MVP uses [PicoClaw](https://github.com/sipeed/picoclaw), an ultra-lightweight AI assistant (<10MB RAM, <1s boot), deployed on dedicated micro VMs in GCP.

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

- **ClawChain Program** (Solana) — On-chain state: user deposits, bot handle registry, active/stopped flags. The wallet address + bot handle are publicly visible on-chain by design — this enables cryptographic verification of bot identity.
- **Orchestrator** (Python + SQLite) — Watches the blockchain for new deposits, provisions GCP VMs from a template, writes bot handles back to the chain, and runs the billing loop.
- **PicoClaw VMs** (GCP) — Each user gets a dedicated micro VM running a [PicoClaw](https://github.com/sipeed/picoclaw) instance. Single Go binary, <10MB RAM, boots in under a second.

## User Flow

```
User                        Solana                    Orchestrator                GCP
 │                            │                            │                      │
 ├─── deposit SOL ──────────► │                            │                      │
 │                            ├─── new deposit event ────► │                      │
 │                            │                            ├─── create VM ──────► │
 │                            │                            │ ◄── VM ready ────────┤
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
```

## Design Decisions

**Why PicoClaw?** NemoClaw (NVIDIA's enterprise OpenClaw stack) was our initial target, but proved impractical for rapid iteration. PicoClaw's minimal footprint (<10MB RAM, single binary, native Telegram support) makes it ideal for spinning up isolated agent instances quickly and cheaply on micro VMs.

**Why wallet + bot handle on-chain?** This is a feature, not a leak. Public on-chain mapping of wallet addresses to Telegram bot handles enables cryptographic identity verification — you can prove a bot belongs to a specific wallet. Want a private bot? Create a fresh wallet.

**Why dedicated VMs instead of containers?** For the hackathon MVP, GCP micro VMs offer the simplest isolation model with acceptable cost. The production path is Kubernetes on bare metal via [tf-xd-venture-talos01](https://github.com/xd-ventures/tf-xd-venture-talos01).

**Why Telegram?** PicoClaw has native multi-channel support (Telegram, Discord, WhatsApp, Matrix, etc.). Telegram is the MVP channel — expanding to others is straightforward.

## Tech Stack

| Layer | Technology |
|---|---|
| AI Agent | [PicoClaw](https://github.com/sipeed/picoclaw) (Go, single binary, <10MB) |
| Blockchain | Solana |
| Smart Contracts | Anchor (Rust) |
| Orchestrator | Python + SQLite |
| Infrastructure (MVP) | GCP (micro VMs from template) |
| Infrastructure (planned) | Kubernetes ([Talos Linux](https://www.talos.dev/)) on bare metal via [tf-xd-venture-talos01](https://github.com/xd-ventures/tf-xd-venture-talos01) |
| User Interface | Telegram (via PicoClaw native integration) |

## Roadmap

- [x] Project concept & architecture design
- [ ] Solana program (deposits, bot registry, stop flag, billing)
- [ ] Orchestrator (blockchain watcher + GCP provisioning)
- [ ] PicoClaw VM template on GCP
- [ ] Web UI for deposit & bot status
- [ ] Proof-of-uptime mechanism (verify VM was actually running)
- [ ] Access control (restrict bot to wallet owner, optional sharing)
- [ ] Multi-channel support (Discord, WhatsApp, Matrix)
- [ ] Agent marketplace with discovery and ratings
- [ ] Multi-framework support (beyond PicoClaw)

## Why ClawChain?

The name reflects our vision: **Claw** for the AI agent ecosystem (OpenClaw/PicoClaw), **Chain** for the blockchain settlement layer — and the ambition to build a *chain* of interconnected AI agents that can discover, compose, and transact with each other autonomously.

## Team

**Maciej Sawicki** — Cloud Architect, SRE, Infrastructure Engineer

Background spanning Web3 infrastructure (validator operations), AI/ML platforms, and production-grade telecom systems. Certified GCP Cloud Architect and Kubernetes Application Developer.

- [xd.ventures](https://xd.ventures)
- [GitHub](https://github.com/xd-ventures)

## License

MIT

---

*Built for the [Solana Agent Hackathon](https://colosseum.com/agent-hackathon/) by [Colosseum](https://colosseum.com/).*
