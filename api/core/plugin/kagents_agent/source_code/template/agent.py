import os
import subprocess, json
from collections.abc import Generator

from typing import Any
from uuid import uuid4

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from ruamel.yaml import YAML

yaml = YAML()

file_exts = [
    ".txt",
    ".md",
    ".mdx",
    ".markdown",
    ".pdf",
    ".html",
    ".xlsx",
    ".xls",
    ".doc",
    ".docx",
    ".csv",
    ".eml",
    ".msg",
    ".pptx",
    ".ppt",
    ".xml",
    ".epub",
]


class agent(Tool):  # noqa: N801
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        agent_name = os.path.splitext(os.path.basename(__file__))[0]
        conf = None
        for root, _, files in os.walk("."):
            for file in files:
                if file.startswith(agent_name) and file.endswith(".yaml"):
                    with open(os.path.join(root, file), encoding="utf-8") as f:
                        conf = yaml.load(f)
        if conf is None:
            yield self.create_text_message("Configuration not found.")
            return

        parameters = conf["parameters"]
        api_key = conf["api_key"]
        dify_a2a_server_url = conf.get("agent_url", "http://192.168.8.41:8888")

        data_payload = {
            "inputs": [
                {
                    "name": p["name"],
                    "type": (
                        "file"
                        if any(
                            tool_parameters.get(p["name"], "").lower().endswith(ext)
                            for ext in file_exts
                        )
                        else "text"
                    ),
                    "value": tool_parameters.get(p["name"]),
                    "description": p["human_description"],
                    "required": p["required"],
                }
                for p in parameters
            ],
            "agent_request_params": {"api_key": api_key, "user_id": "user_id"},
        }

        send_message_payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "data", "data": data_payload}],
                "messageId": uuid4().hex,
            },
            "configuration": {
                "blocking": False,
                "acceptedOutputModes": ["text/plain", "application/json"],
            },
        }
        
        # call the agent_worker subprocess
        p = subprocess.Popen(
            [".venv/bin/python", "./template/agent_worker.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # send payload
        payload = json.dumps({
            "agent_url": dify_a2a_server_url,
            "send_message_payload": send_message_payload
        })
        p.stdin.write(payload)
        p.stdin.close()

        try:
            for line in p.stdout:
                try:
                    chunk = json.loads(line.strip())
                    if chunk.get("result", {}).get("final") or (
                                chunk.get("result", {}).get("kind") == "artifact-update"
                                and chunk.get("result", {}).get("lastChunk")
                        ):
                        yield self.create_text_message(str(chunk))
                    yield self.create_stream_variable_message("a2a_streaming_response", str(chunk))
                except Exception as e:
                    yield self.create_text_message(f"⚠️ Invalid stream: {e}")
        finally:
            p.wait()
            if p.returncode != 0:
                err = p.stderr.read()
                yield self.create_text_message(f"⚠️ Agent crashed: {err}")