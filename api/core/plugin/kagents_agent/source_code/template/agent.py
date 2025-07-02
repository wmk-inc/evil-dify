import asyncio
import os
from collections.abc import Generator
from typing import Any
from uuid import uuid4

import httpx
from a2a.client import A2AClient
from a2a.types import (
    Message,
    MessageSendParams,
    SendStreamingMessageRequest,
    Task,
    TaskState,
    TaskStatusUpdateEvent,
)
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
response_queue: asyncio.Queue = asyncio.Queue()


async def run(send_message_payload):
    all_responses = []
    async with httpx.AsyncClient() as httpx_client:
        client = await A2AClient.get_client_from_agent_card_url(
            httpx_client, "http://192.168.8.41:8888"
        )
        streaming_request = SendStreamingMessageRequest(
            id=uuid4().hex, params=MessageSendParams(**send_message_payload)
        )
        stream_response = client.send_message_streaming(streaming_request)
        async for chunk in stream_response:
            event = chunk.root.result
            is_final_event = (
                (isinstance(event, TaskStatusUpdateEvent) and event.final)
                or isinstance(event, Message)
                or (
                    isinstance(event, Task)
                    and event.status.state
                    in (
                        TaskState.completed,
                        TaskState.canceled,
                        TaskState.failed,
                        TaskState.rejected,
                        TaskState.unknown,
                    )
                )
            )
            if is_final_event:
                await response_queue.put(chunk.model_dump())
        await response_queue.put(None)

    return all_responses


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

        asyncio.run(run(send_message_payload))
        steaming = True
        while steaming:
            chunk = asyncio.run(response_queue.get())
            if chunk is None:
                break
            yield self.create_json_message(chunk)
