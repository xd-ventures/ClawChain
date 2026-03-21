import json
import yaml
from orchestrator.cloud_init import generate_cloud_init, generate_container_declaration


def test_cloud_init_injects_keys():
    result = generate_cloud_init("sk-or-test-key", "123456:AAA-bot-token")
    assert "sk-or-test-key" in result
    assert "123456:AAA-bot-token" in result
    assert "__OPENROUTER_API_KEY__" not in result
    assert "__TELEGRAM_BOT_TOKEN__" not in result


def test_cloud_init_valid_yaml():
    result = generate_cloud_init("key123", "token456")
    parsed = yaml.safe_load(result)
    assert "write_files" in parsed
    assert len(parsed["write_files"]) == 1
    content = json.loads(parsed["write_files"][0]["content"])
    assert content["model_list"][0]["api_key"] == "key123"
    assert content["channels"]["telegram"]["token"] == "token456"


def test_container_declaration_gateway_host():
    result = generate_container_declaration("docker.io/sipeed/picoclaw:latest")
    parsed = yaml.safe_load(result)
    container = parsed["spec"]["containers"][0]
    env_vars = {e["name"]: e["value"] for e in container["env"]}
    assert env_vars["PICOCLAW_GATEWAY_HOST"] == "0.0.0.0"


def test_container_declaration_volume_mount():
    result = generate_container_declaration("my-image:v1")
    parsed = yaml.safe_load(result)
    container = parsed["spec"]["containers"][0]
    assert container["image"] == "my-image:v1"
    assert container["volumeMounts"][0]["mountPath"] == "/root/.picoclaw"
    assert parsed["spec"]["volumes"][0]["hostPath"]["path"] == "/home/picoclaw"
    assert parsed["spec"]["restartPolicy"] == "Always"
