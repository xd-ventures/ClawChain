"""Generate cloud-init userdata for PicoClaw container VMs.

The VM runs GCP Container-Optimized OS (COS). Cloud-init writes the PicoClaw
config to a host directory that is then bind-mounted into the container.
"""

import json

PICOCLAW_CONFIG_TEMPLATE = {
    "agents": {
        "defaults": {
            "workspace": "~/.picoclaw/workspace",
            "model_name": "openrouter-auto",
            "max_tokens": 8192,
            "temperature": 0.7,
            "max_tool_iterations": 20,
        }
    },
    "model_list": [
        {
            "model_name": "openrouter-auto",
            "model": "openrouter/auto",
            "api_key": "__OPENROUTER_API_KEY__",
            "api_base": "https://openrouter.ai/api/v1",
            "request_timeout": 300,
        }
    ],
    "channels": {
        "telegram": {
            "enabled": True,
            "token": "__TELEGRAM_BOT_TOKEN__",
        }
    },
}

# Host path where config is written (bind-mounted into container as /root/.picoclaw)
HOST_CONFIG_DIR = "/home/picoclaw"
HOST_CONFIG_PATH = f"{HOST_CONFIG_DIR}/config.json"


def generate_cloud_init(openrouter_api_key: str, telegram_bot_token: str) -> str:
    """Generate cloud-init userdata that writes PicoClaw config to the host.

    The config file is placed at /home/picoclaw/config.json on the host,
    which GCP's container spec mounts into the container at /root/.picoclaw/.
    """
    config = json.loads(json.dumps(PICOCLAW_CONFIG_TEMPLATE))
    config["model_list"][0]["api_key"] = openrouter_api_key
    config["channels"]["telegram"]["token"] = telegram_bot_token

    config_json = json.dumps(config, indent=2)
    indented_json = "\n".join(f"      {line}" for line in config_json.splitlines())

    return f"""#cloud-config
write_files:
  - path: {HOST_CONFIG_PATH}
    permissions: '0600'
    content: |
{indented_json}
"""


def generate_container_declaration(container_image: str) -> str:
    """Generate GCP container declaration YAML.

    This is set as the 'gce-container-declaration' metadata value.
    COS reads it and runs the specified container with the volume mount.
    """
    return f"""spec:
  containers:
    - name: picoclaw
      image: {container_image}
      env:
        - name: PICOCLAW_GATEWAY_HOST
          value: "0.0.0.0"
      volumeMounts:
        - name: picoclaw-config
          mountPath: /root/.picoclaw
      stdin: false
      tty: false
  volumes:
    - name: picoclaw-config
      hostPath:
        path: {HOST_CONFIG_DIR}
  restartPolicy: Always
"""
