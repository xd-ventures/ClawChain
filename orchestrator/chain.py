"""Chain backend abstraction.

Provides a unified interface for reading/writing on-chain state.
Two implementations:
  - SolanaBackend: real Solana RPC + transaction signing
  - MockBackend: reads/writes state from a YAML file (no blockchain needed)
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path

import yaml

log = logging.getLogger("orchestrator.chain")


class ChainBackend(ABC):
    """Interface that both real and mock backends implement."""

    @abstractmethod
    def fetch_operator_config(self) -> dict:
        """Return operator config: authority, treasury, billing_amount, min_deposit."""
        ...

    @abstractmethod
    def fetch_all_user_bots(self) -> list[dict]:
        """Return all UserBot accounts.

        Each dict has: owner, bot_handle, is_active, created_at,
        last_billed_at, total_deposited, total_billed, pda,
        lamports, available_balance.
        """
        ...

    @abstractmethod
    def set_bot_handle(self, user_wallet_pubkey: str, bot_handle: str) -> str:
        """Write bot handle on-chain for a user. Returns tx signature or mock ID."""
        ...

    @abstractmethod
    def bill(self, user_wallet_pubkey: str) -> str:
        """Bill a user. Returns tx signature or mock ID."""
        ...


# ---------------------------------------------------------------------------
# Real Solana backend
# ---------------------------------------------------------------------------

class SolanaBackend(ChainBackend):
    """Real Solana RPC backend."""

    def __init__(self, rpc_url: str, operator_keypair):
        from solana.rpc.api import Client
        from .solana_rpc import (
            fetch_operator_config as _fetch_config,
            fetch_all_user_bots as _fetch_bots,
            get_operator_config_pda,
        )
        from .solana_tx import send_set_bot_handle, send_bill

        self._client = Client(rpc_url)
        self._keypair = operator_keypair
        self._fetch_config = _fetch_config
        self._fetch_bots = _fetch_bots
        self._send_set_bot_handle = send_set_bot_handle
        self._send_bill = send_bill
        self._operator_config_pda = get_operator_config_pda()
        self._operator_config: dict | None = None

    def fetch_operator_config(self) -> dict:
        self._operator_config = self._fetch_config(self._client)
        return self._operator_config

    def fetch_all_user_bots(self) -> list[dict]:
        return self._fetch_bots(self._client)

    def set_bot_handle(self, user_wallet_pubkey: str, bot_handle: str) -> str:
        return self._send_set_bot_handle(
            self._client, self._keypair, user_wallet_pubkey, bot_handle,
            self._operator_config_pda, self._operator_config,
        )

    def bill(self, user_wallet_pubkey: str) -> str:
        return self._send_bill(
            self._client, self._keypair, user_wallet_pubkey,
            self._operator_config_pda, self._operator_config,
        )


# ---------------------------------------------------------------------------
# Mock YAML-file backend
# ---------------------------------------------------------------------------

class MockBackend(ChainBackend):
    """Mock backend that reads/writes state from a YAML file.

    The YAML file format:

        operator_config:
          authority: "SomeBase58Pubkey"
          treasury: "SomeBase58Pubkey"
          billing_amount: 10000000      # lamports
          min_deposit: 50000000

        user_bots:
          - owner: "WalletPubkey1"
            bot_handle: ""              # empty = needs provisioning
            is_active: true
            total_deposited: 100000000
            total_billed: 0
            available_balance: 100000000

          - owner: "WalletPubkey2"
            bot_handle: "@some_bot"
            is_active: false            # deactivated
            total_deposited: 50000000
            total_billed: 30000000
            available_balance: 20000000

    Fields not specified get sensible defaults. The file is rewritten
    on every set_bot_handle / bill call so you can watch state evolve.
    """

    def __init__(self, state_file: str):
        self._path = Path(state_file)
        self._state = self._load()
        self._tx_counter = 0

    def _load(self) -> dict:
        if not self._path.exists():
            raise FileNotFoundError(f"Mock state file not found: {self._path}")
        with open(self._path) as f:
            return yaml.safe_load(f)

    def _save(self):
        with open(self._path, "w") as f:
            yaml.dump(self._state, f, default_flow_style=False, sort_keys=False)

    def _next_tx(self) -> str:
        self._tx_counter += 1
        return f"mock-tx-{self._tx_counter}"

    def reload(self):
        """Re-read the YAML file. Useful for external edits between loop ticks."""
        self._state = self._load()

    def fetch_operator_config(self) -> dict:
        cfg = self._state.get("operator_config", {})
        return {
            "authority": cfg.get("authority", "MockAuthority"),
            "treasury": cfg.get("treasury", "MockTreasury"),
            "billing_amount": cfg.get("billing_amount", 10_000_000),
            "min_deposit": cfg.get("min_deposit", 50_000_000),
            "bump": 255,
        }

    def fetch_all_user_bots(self) -> list[dict]:
        self.reload()  # re-read file each poll so you can edit it live
        now = int(time.time())
        results = []
        for entry in self._state.get("user_bots", []):
            results.append({
                "owner": entry["owner"],
                "bot_handle": entry.get("bot_handle", ""),
                "is_active": entry.get("is_active", True),
                "created_at": entry.get("created_at", now),
                "last_billed_at": entry.get("last_billed_at", now),
                "total_deposited": entry.get("total_deposited", 100_000_000),
                "total_billed": entry.get("total_billed", 0),
                "bump": 255,
                "pda": f"MockPDA-{entry['owner'][:8]}",
                "lamports": entry.get("available_balance", 100_000_000) + 1_000_000,
                "available_balance": entry.get("available_balance", 100_000_000),
            })
        return results

    def set_bot_handle(self, user_wallet_pubkey: str, bot_handle: str) -> str:
        for entry in self._state.get("user_bots", []):
            if entry["owner"] == user_wallet_pubkey:
                entry["bot_handle"] = bot_handle
                break
        self._save()
        tx = self._next_tx()
        log.info(f"[MOCK] set_bot_handle({user_wallet_pubkey}, {bot_handle}) -> {tx}")
        return tx

    def bill(self, user_wallet_pubkey: str) -> str:
        cfg = self._state.get("operator_config", {})
        billing_amount = cfg.get("billing_amount", 10_000_000)

        for entry in self._state.get("user_bots", []):
            if entry["owner"] == user_wallet_pubkey:
                balance = entry.get("available_balance", 0)
                if balance < billing_amount:
                    entry["is_active"] = False
                    log.info(f"[MOCK] bill auto-deactivated {user_wallet_pubkey} (balance {balance} < {billing_amount})")
                else:
                    entry["available_balance"] = balance - billing_amount
                    entry["total_billed"] = entry.get("total_billed", 0) + billing_amount
                    entry["last_billed_at"] = int(time.time())
                break
        self._save()
        tx = self._next_tx()
        log.info(f"[MOCK] bill({user_wallet_pubkey}) -> {tx}")
        return tx
