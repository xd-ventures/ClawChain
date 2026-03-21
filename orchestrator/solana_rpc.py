"""Solana read operations for the orchestrator."""

import hashlib
import struct

from solders.pubkey import Pubkey
from solana.rpc.api import Client
from solana.rpc.types import MemcmpOpts

from .config import get_program_id

LAMPORTS_PER_SOL = 1_000_000_000


def account_discriminator(name: str) -> bytes:
    """Anchor account discriminator: first 8 bytes of SHA256("account:<Name>")."""
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]


OPERATOR_CONFIG_DISC = account_discriminator("OperatorConfig")
USER_BOT_DISC = account_discriminator("UserBot")


def get_operator_config_pda() -> Pubkey:
    pda, _ = Pubkey.find_program_address([b"operator_config"], get_program_id())
    return pda


def get_user_bot_pda(owner: Pubkey) -> Pubkey:
    pda, _ = Pubkey.find_program_address([b"user_bot", bytes(owner)], get_program_id())
    return pda


def deserialize_operator_config(data: bytes) -> dict:
    offset = 8  # skip discriminator
    authority = Pubkey.from_bytes(data[offset : offset + 32])
    offset += 32
    treasury = Pubkey.from_bytes(data[offset : offset + 32])
    offset += 32
    billing_amount = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    min_deposit = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    bump = data[offset]
    return {
        "authority": str(authority),
        "treasury": str(treasury),
        "billing_amount": billing_amount,
        "min_deposit": min_deposit,
        "bump": bump,
    }


def deserialize_user_bot(data: bytes) -> dict:
    offset = 8  # skip discriminator
    owner = Pubkey.from_bytes(data[offset : offset + 32])
    offset += 32
    handle_len = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    bot_handle = data[offset : offset + handle_len].decode("utf-8")
    offset += handle_len
    is_active = bool(data[offset])
    offset += 1
    created_at = struct.unpack_from("<q", data, offset)[0]
    offset += 8
    last_billed_at = struct.unpack_from("<q", data, offset)[0]
    offset += 8
    total_deposited = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    total_billed = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    bump = data[offset]
    return {
        "owner": str(owner),
        "bot_handle": bot_handle,
        "is_active": is_active,
        "created_at": created_at,
        "last_billed_at": last_billed_at,
        "total_deposited": total_deposited,
        "total_billed": total_billed,
        "bump": bump,
    }


def fetch_operator_config(client: Client) -> dict:
    """Fetch and deserialize the OperatorConfig account."""
    pda = get_operator_config_pda()
    resp = client.get_account_info(pda)
    if resp.value is None:
        raise RuntimeError("OperatorConfig not found — program may not be initialized")
    return deserialize_operator_config(bytes(resp.value.data))


def fetch_all_user_bots(client: Client) -> list[dict]:
    """Fetch all UserBot accounts with their lamport balances."""
    filters = [MemcmpOpts(offset=0, bytes_=USER_BOT_DISC.hex())]
    resp = client.get_program_accounts(get_program_id(), filters=filters)
    if not resp.value:
        return []

    rent_resp = client.get_minimum_balance_for_rent_exemption(110)  # UserBot data size
    rent_exempt = rent_resp.value

    results = []
    for keyed_account in resp.value:
        account = keyed_account.account
        bot = deserialize_user_bot(bytes(account.data))
        bot["pda"] = str(keyed_account.pubkey)
        bot["lamports"] = account.lamports
        bot["available_balance"] = max(0, account.lamports - rent_exempt)
        results.append(bot)

    return results
