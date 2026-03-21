import yaml
from orchestrator.chain import MockBackend


def test_fetch_operator_config(mock_backend):
    config = mock_backend.fetch_operator_config()
    assert config["billing_amount"] == 10_000_000
    assert config["min_deposit"] == 50_000_000
    assert "authority" in config


def test_fetch_all_user_bots(mock_backend):
    bots = mock_backend.fetch_all_user_bots()
    assert len(bots) == 2
    assert bots[0]["owner"].startswith("Wallet1")
    assert bots[0]["bot_handle"] == ""
    assert bots[0]["provisioning_status"] == 0
    assert bots[1]["provisioning_status"] == 2


def test_fetch_rereads_file(mock_state_file):
    backend = MockBackend(mock_state_file)
    bots = backend.fetch_all_user_bots()
    assert len(bots) == 2

    # Externally add a user
    with open(mock_state_file) as f:
        state = yaml.safe_load(f)
    state["user_bots"].append({
        "owner": "Wallet3CCC",
        "bot_handle": "",
        "is_active": True,
        "provisioning_status": 0,
        "available_balance": 50_000_000,
    })
    with open(mock_state_file, "w") as f:
        yaml.dump(state, f)

    bots = backend.fetch_all_user_bots()
    assert len(bots) == 3


def test_set_bot_handle(mock_backend, mock_state_file):
    tx = mock_backend.set_bot_handle("Wallet1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "@new_bot")
    assert tx.startswith("mock-tx-")

    with open(mock_state_file) as f:
        state = yaml.safe_load(f)
    user = state["user_bots"][0]
    assert user["bot_handle"] == "@new_bot"
    assert user["provisioning_status"] == 2  # Ready


def test_bill_deducts_balance(mock_backend, mock_state_file):
    mock_backend.bill("Wallet2BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")

    with open(mock_state_file) as f:
        state = yaml.safe_load(f)
    user = state["user_bots"][1]
    assert user["available_balance"] == 160_000_000
    assert user["total_billed"] == 40_000_000


def test_bill_auto_deactivates(mock_state_file):
    # Create a user with balance below billing amount
    with open(mock_state_file) as f:
        state = yaml.safe_load(f)
    state["user_bots"].append({
        "owner": "PoorWallet",
        "is_active": True,
        "provisioning_status": 2,
        "available_balance": 5_000_000,  # Less than 10M billing
    })
    with open(mock_state_file, "w") as f:
        yaml.dump(state, f)

    backend = MockBackend(mock_state_file)
    backend.bill("PoorWallet")

    with open(mock_state_file) as f:
        state = yaml.safe_load(f)
    poor = [u for u in state["user_bots"] if u["owner"] == "PoorWallet"][0]
    assert poor["is_active"] is False


def test_lock_for_provisioning(mock_backend, mock_state_file):
    mock_backend.lock_for_provisioning("Wallet1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    with open(mock_state_file) as f:
        state = yaml.safe_load(f)
    assert state["user_bots"][0]["provisioning_status"] == 1


def test_refund_failed_provision(mock_backend, mock_state_file):
    mock_backend.refund_failed_provision("Wallet1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    with open(mock_state_file) as f:
        state = yaml.safe_load(f)
    user = state["user_bots"][0]
    assert user["is_active"] is False
    assert user["provisioning_status"] == 3


def test_update_service_status(mock_backend, mock_state_file):
    mock_backend.update_service_status(5, True)

    with open(mock_state_file) as f:
        state = yaml.safe_load(f)
    assert state["service_status"]["active_instances"] == 5
    assert state["service_status"]["accepting_new"] is True


def test_tx_ids_increment(mock_backend):
    tx1 = mock_backend.lock_for_provisioning("Wallet1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    tx2 = mock_backend.lock_for_provisioning("Wallet2BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    assert tx1 == "mock-tx-1"
    assert tx2 == "mock-tx-2"
