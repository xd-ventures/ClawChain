"""Unit tests for binary deserialization of Solana accounts.

Uses the raw deserialization logic without importing solders (not needed for tests).
"""

import hashlib
import struct


def account_discriminator(name: str) -> bytes:
    """Local copy — avoids importing solana_rpc which requires solders."""
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]


def deserialize_user_bot_raw(data: bytes) -> dict:
    """Deserialize UserBot binary data — standalone test version."""
    offset = 8  # skip discriminator
    owner = data[offset : offset + 32]
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
    offset += 1
    provisioning_status = data[offset] if offset < len(data) else 0
    return {
        "owner": owner.hex(),
        "bot_handle": bot_handle,
        "is_active": is_active,
        "created_at": created_at,
        "last_billed_at": last_billed_at,
        "total_deposited": total_deposited,
        "total_billed": total_billed,
        "bump": bump,
        "provisioning_status": provisioning_status,
    }


def deserialize_operator_config_raw(data: bytes) -> dict:
    """Deserialize OperatorConfig binary data — standalone test version."""
    offset = 8
    authority = data[offset : offset + 32]
    offset += 32
    treasury = data[offset : offset + 32]
    offset += 32
    billing_amount = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    min_deposit = struct.unpack_from("<Q", data, offset)[0]
    offset += 8
    bump = data[offset]
    return {
        "authority": authority.hex(),
        "treasury": treasury.hex(),
        "billing_amount": billing_amount,
        "min_deposit": min_deposit,
        "bump": bump,
    }


def _build_user_bot_bytes(owner: bytes, bot_handle: str, is_active: bool,
                           created_at: int, last_billed_at: int,
                           total_deposited: int, total_billed: int,
                           bump: int, provisioning_status: int) -> bytes:
    disc = account_discriminator("UserBot")
    handle_bytes = bot_handle.encode("utf-8")
    return (
        disc
        + owner
        + struct.pack("<I", len(handle_bytes))
        + handle_bytes
        + bytes([1 if is_active else 0])
        + struct.pack("<q", created_at)
        + struct.pack("<q", last_billed_at)
        + struct.pack("<Q", total_deposited)
        + struct.pack("<Q", total_billed)
        + bytes([bump])
        + bytes([provisioning_status])
    )


def _build_operator_config_bytes(authority: bytes, treasury: bytes,
                                  billing_amount: int, min_deposit: int, bump: int) -> bytes:
    disc = account_discriminator("OperatorConfig")
    return disc + authority + treasury + struct.pack("<Q", billing_amount) + struct.pack("<Q", min_deposit) + bytes([bump])


# --- Tests ---

def test_operator_config_discriminator():
    disc = account_discriminator("OperatorConfig")
    expected = hashlib.sha256(b"account:OperatorConfig").digest()[:8]
    assert disc == expected
    assert len(disc) == 8


def test_user_bot_discriminator():
    disc = account_discriminator("UserBot")
    expected = hashlib.sha256(b"account:UserBot").digest()[:8]
    assert disc == expected


def test_deserialize_operator_config():
    auth = bytes(range(32))
    treas = bytes(range(32, 64))
    data = _build_operator_config_bytes(auth, treas, 10_000_000, 50_000_000, 254)
    result = deserialize_operator_config_raw(data)
    assert result["billing_amount"] == 10_000_000
    assert result["min_deposit"] == 50_000_000
    assert result["bump"] == 254


def test_deserialize_user_bot():
    owner = bytes(range(32))
    data = _build_user_bot_bytes(owner, "@my_bot", True, 1000, 2000, 100_000_000, 10_000_000, 255, 2)
    result = deserialize_user_bot_raw(data)
    assert result["bot_handle"] == "@my_bot"
    assert result["is_active"] is True
    assert result["created_at"] == 1000
    assert result["total_deposited"] == 100_000_000
    assert result["provisioning_status"] == 2


def test_deserialize_user_bot_empty_handle():
    owner = bytes(range(32))
    data = _build_user_bot_bytes(owner, "", True, 0, 0, 0, 0, 255, 0)
    result = deserialize_user_bot_raw(data)
    assert result["bot_handle"] == ""


def test_deserialize_user_bot_max_handle():
    owner = bytes(range(32))
    handle = "a" * 32
    data = _build_user_bot_bytes(owner, handle, True, 0, 0, 0, 0, 255, 1)
    result = deserialize_user_bot_raw(data)
    assert result["bot_handle"] == handle
    assert len(result["bot_handle"]) == 32
    assert result["provisioning_status"] == 1
