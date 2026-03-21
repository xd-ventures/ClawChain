from orchestrator.db import DB


def test_init_schema(tmp_db):
    # Tables should exist after init
    row = tmp_db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r["name"] for r in row]
    assert "telegram_bots" in names
    assert "instances" in names


def test_import_bots(tmp_db):
    tmp_db.import_bots([("bot1", "tok1"), ("bot2", "tok2")])
    assert tmp_db.get_available_bot_count() == 2


def test_import_bots_idempotent(tmp_db):
    tmp_db.import_bots([("bot1", "tok1")])
    tmp_db.import_bots([("bot1", "tok1_updated"), ("bot2", "tok2")])
    assert tmp_db.get_available_bot_count() == 2
    row = tmp_db.conn.execute("SELECT bot_token FROM telegram_bots WHERE bot_name='bot1'").fetchone()
    assert row["bot_token"] == "tok1_updated"


def test_allocate_bot(tmp_db):
    tmp_db.import_bots([("bot1", "tok1"), ("bot2", "tok2")])
    result = tmp_db.allocate_bot("wallet_abc")
    assert result is not None
    bot_id, name, token = result
    assert name in ("bot1", "bot2")
    assert tmp_db.get_available_bot_count() == 1


def test_allocate_bot_empty_pool(tmp_db):
    result = tmp_db.allocate_bot("wallet_abc")
    assert result is None


def test_release_bot(tmp_db):
    tmp_db.import_bots([("bot1", "tok1")])
    bot_id, _, _ = tmp_db.allocate_bot("wallet_abc")
    assert tmp_db.get_available_bot_count() == 0
    tmp_db.release_bot(bot_id)
    assert tmp_db.get_available_bot_count() == 1


def test_create_instance(tmp_db):
    tmp_db.import_bots([("bot1", "tok1")])
    tmp_db.create_instance("wallet_abc", 1, "bot1", "vm-test", "us-central1-a")
    instances = tmp_db.get_active_instances()
    assert len(instances) == 1
    assert instances[0]["status"] == "provisioning"
    assert instances[0]["wallet_pubkey"] == "wallet_abc"


def test_update_instance_ip(tmp_db):
    tmp_db.import_bots([("bot1", "tok1")])
    tmp_db.create_instance("wallet_abc", 1, "bot1", "vm-test", "zone")
    tmp_db.update_instance_ip("wallet_abc", "10.0.0.1")
    inst = tmp_db.get_instance_by_wallet("wallet_abc")
    assert inst["vm_ip"] == "10.0.0.1"
    assert inst["status"] == "provisioning"  # Still provisioning


def test_update_instance_running(tmp_db):
    tmp_db.import_bots([("bot1", "tok1")])
    tmp_db.create_instance("wallet_abc", 1, "bot1", "vm-test", "zone")
    tmp_db.update_instance_running("wallet_abc")
    inst = tmp_db.get_instance_by_wallet("wallet_abc")
    assert inst["status"] == "running"


def test_increment_health_failures(tmp_db):
    tmp_db.import_bots([("bot1", "tok1")])
    tmp_db.create_instance("wallet_abc", 1, "bot1", "vm-test", "zone")
    count = tmp_db.increment_health_failures("wallet_abc", "timeout")
    assert count == 1
    count = tmp_db.increment_health_failures("wallet_abc", "timeout again")
    assert count == 2
    inst = tmp_db.get_instance_by_wallet("wallet_abc")
    assert inst["error_message"] == "timeout again"


def test_reset_health_failures(tmp_db):
    tmp_db.import_bots([("bot1", "tok1")])
    tmp_db.create_instance("wallet_abc", 1, "bot1", "vm-test", "zone")
    tmp_db.update_instance_running("wallet_abc")
    tmp_db.increment_health_failures("wallet_abc", "err")
    tmp_db.reset_health_failures("wallet_abc")
    inst = tmp_db.get_instance_by_wallet("wallet_abc")
    assert inst["health_failures"] == 0
    assert inst["error_message"] is None


def test_instance_lifecycle(tmp_db):
    tmp_db.import_bots([("bot1", "tok1")])
    tmp_db.create_instance("w", 1, "bot1", "vm", "z")
    tmp_db.update_instance_running("w")
    tmp_db.update_instance_bot_handle_set("w")
    inst = tmp_db.get_instance_by_wallet("w")
    assert inst["bot_handle_set_on_chain"] == 1
    tmp_db.update_instance_stopping("w")
    tmp_db.update_instance_stopped("w")
    inst = tmp_db.get_instance_by_wallet("w")
    assert inst["status"] == "stopped"
    assert inst["stopped_at"] is not None


def test_get_active_instances_filters(tmp_db):
    tmp_db.import_bots([("b1", "t1"), ("b2", "t2")])
    tmp_db.create_instance("w1", 1, "b1", "vm1", "z")
    tmp_db.create_instance("w2", 2, "b2", "vm2", "z")
    tmp_db.update_instance_running("w1")
    tmp_db.update_instance_stopping("w2")
    tmp_db.update_instance_stopped("w2")
    active = tmp_db.get_active_instances()
    assert len(active) == 1
    assert active[0]["wallet_pubkey"] == "w1"


def test_get_running_for_billing(tmp_db):
    tmp_db.import_bots([("b1", "t1")])
    tmp_db.create_instance("w1", 1, "b1", "vm1", "z")
    tmp_db.update_instance_running("w1")
    # Not billable yet — bot handle not set
    assert len(tmp_db.get_running_instances_for_billing()) == 0
    tmp_db.update_instance_bot_handle_set("w1")
    assert len(tmp_db.get_running_instances_for_billing()) == 1
