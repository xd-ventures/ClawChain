import os
import pytest
import yaml

from orchestrator.db import DB
from orchestrator.chain import MockBackend


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh SQLite database in a temp directory."""
    db = DB(str(tmp_path / "test.db"))
    db.init_schema()
    return db


@pytest.fixture
def bot_pool_file(tmp_path):
    """Temp telegram_bots.txt with 3 fake bots."""
    path = tmp_path / "telegram_bots.txt"
    path.write_text(
        "# test bots\n"
        "alpha_bot:111111111:AAA-token-alpha\n"
        "beta_bot:222222222:AAA-token-beta\n"
        "gamma_bot:333333333:AAA-token-gamma\n"
    )
    return str(path)


@pytest.fixture
def mock_state_file(tmp_path):
    """Temp mock_state.yaml with sample data."""
    path = tmp_path / "mock_state.yaml"
    state = {
        "operator_config": {
            "authority": "MockAuth111111111111111111111111111111111111",
            "treasury": "MockTreasury1111111111111111111111111111111",
            "billing_amount": 10_000_000,
            "min_deposit": 50_000_000,
        },
        "user_bots": [
            {
                "owner": "Wallet1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "bot_handle": "",
                "is_active": True,
                "provisioning_status": 0,
                "total_deposited": 100_000_000,
                "total_billed": 0,
                "available_balance": 100_000_000,
            },
            {
                "owner": "Wallet2BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
                "bot_handle": "@beta_bot",
                "is_active": True,
                "provisioning_status": 2,
                "total_deposited": 200_000_000,
                "total_billed": 30_000_000,
                "available_balance": 170_000_000,
            },
        ],
    }
    with open(path, "w") as f:
        yaml.dump(state, f)
    return str(path)


@pytest.fixture
def mock_backend(mock_state_file):
    """MockBackend initialized from the temp YAML."""
    return MockBackend(mock_state_file)
