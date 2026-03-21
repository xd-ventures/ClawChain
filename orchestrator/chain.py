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
        ...

    @abstractmethod
    def fetch_all_user_bots(self) -> list[dict]:
        ...

    @abstractmethod
    def set_bot_handle(self, user_wallet_pubkey: str, bot_handle: str) -> str:
        ...

    @abstractmethod
    def bill(self, user_wallet_pubkey: str) -> str:
        ...

    @abstractmethod
    def lock_for_provisioning(self, user_wallet_pubkey: str) -> str:
        """Lock funds on-chain while provisioning VM. Returns tx sig."""
        ...

    @abstractmethod
    def refund_failed_provision(self, user_wallet_pubkey: str) -> str:
        """Deactivate + mark Failed after VM provisioning failure. Returns tx sig."""
        ...

    @abstractmethod
    def update_service_status(self, active_instances: int, accepting_new: bool) -> str:
        """Update on-chain capacity status. Returns tx sig."""
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
            get_service_status_pda,
        )
        from .solana_tx import (
            send_set_bot_handle, send_bill,
            send_lock_for_provisioning, send_refund_failed_provision,
            send_update_service_status,
        )

        self._client = Client(rpc_url)
        self._keypair = operator_keypair
        self._fetch_config = _fetch_config
        self._fetch_bots = _fetch_bots
        self._send_set_bot_handle = send_set_bot_handle
        self._send_bill = send_bill
        self._send_lock = send_lock_for_provisioning
        self._send_refund = send_refund_failed_provision
        self._send_update_status = send_update_service_status
        self._operator_config_pda = get_operator_config_pda()
        self._service_status_pda = get_service_status_pda()
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

    def lock_for_provisioning(self, user_wallet_pubkey: str) -> str:
        return self._send_lock(
            self._client, self._keypair, user_wallet_pubkey,
            self._operator_config_pda,
        )

    def refund_failed_provision(self, user_wallet_pubkey: str) -> str:
        return self._send_refund(
            self._client, self._keypair, user_wallet_pubkey,
            self._operator_config_pda,
        )

    def update_service_status(self, active_instances: int, accepting_new: bool) -> str:
        return self._send_update_status(
            self._client, self._keypair, active_instances, accepting_new,
            self._operator_config_pda, self._service_status_pda,
        )


# ---------------------------------------------------------------------------
# Mock YAML-file backend
# ---------------------------------------------------------------------------

class MockBackend(ChainBackend):
    """Mock backend that reads/writes state from a YAML file."""

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
        self.reload()
        now = int(time.time())
        results = []
        for entry in self._state.get("user_bots", []):
            results.append({
                "owner": entry["owner"],
                "bot_handle": entry.get("bot_handle", ""),
                "is_active": entry.get("is_active", True),
                "provisioning_status": entry.get("provisioning_status", 0),
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
                entry["provisioning_status"] = 2  # Ready
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
                    log.info(f"[MOCK] bill auto-deactivated {user_wallet_pubkey}")
                else:
                    entry["available_balance"] = balance - billing_amount
                    entry["total_billed"] = entry.get("total_billed", 0) + billing_amount
                    entry["last_billed_at"] = int(time.time())
                break
        self._save()
        tx = self._next_tx()
        log.info(f"[MOCK] bill({user_wallet_pubkey}) -> {tx}")
        return tx

    def lock_for_provisioning(self, user_wallet_pubkey: str) -> str:
        for entry in self._state.get("user_bots", []):
            if entry["owner"] == user_wallet_pubkey:
                entry["provisioning_status"] = 1  # Locked
                break
        self._save()
        tx = self._next_tx()
        log.info(f"[MOCK] lock_for_provisioning({user_wallet_pubkey}) -> {tx}")
        return tx

    def refund_failed_provision(self, user_wallet_pubkey: str) -> str:
        for entry in self._state.get("user_bots", []):
            if entry["owner"] == user_wallet_pubkey:
                entry["is_active"] = False
                entry["provisioning_status"] = 3  # Failed
                break
        self._save()
        tx = self._next_tx()
        log.info(f"[MOCK] refund_failed_provision({user_wallet_pubkey}) -> {tx}")
        return tx

    def update_service_status(self, active_instances: int, accepting_new: bool) -> str:
        self._state.setdefault("service_status", {})
        self._state["service_status"]["active_instances"] = active_instances
        self._state["service_status"]["accepting_new"] = accepting_new
        self._save()
        tx = self._next_tx()
        log.info(f"[MOCK] update_service_status(active={active_instances}, accepting={accepting_new}) -> {tx}")
        return tx
