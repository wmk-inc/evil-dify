import asyncio
import os
from collections.abc import Generator
from queue import Queue
from typing import Any
from uuid import uuid4

import httpx
from a2a.client import A2AClient
from a2a.types import (
    MessageSendParams,
    SendStreamingMessageRequest,
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


async def run(send_message_payload, stream_response_queue, final_result_queue):
    async with httpx.AsyncClient() as httpx_client:
        client = await A2AClient.get_client_from_agent_card_url(
            httpx_client, "http://192.168.8.41:8888"
        )
        streaming_request = SendStreamingMessageRequest(
            id=uuid4().hex, params=MessageSendParams(**send_message_payload)
        )
        stream_response = client.send_message_streaming(streaming_request)
        async for chunk in stream_response:
            response_json = chunk.model_dump(mode="json", exclude_none=True)
            stream_response_queue.put(response_json)

            if response_json.get("result", {}).get("final") or (
                    response_json.get("result", {}).get("kind") == "artifact-update"
                    and response_json.get("result", {}).get("lastChunk")
            ):
                final_result_queue.put(response_json)

        final_result_queue.put(None)
        stream_response_queue.put(None)


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
        stream_response_queue: Queue = Queue()
        final_result_queue: Queue = Queue()
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
        loop = asyncio.new_event_loop()
        task = loop.create_task(run(send_message_payload, stream_response_queue, final_result_queue))
        
        asyncio.run(
            run(send_message_payload, stream_response_queue, final_result_queue)
        )

        steaming = True
        while steaming:
            chunk = stream_response_queue.get()
            if chunk is None:
                break
            yield self.create_stream_variable_message(
                "a2a_streaming_response", str(chunk)
            )
        yield self.create_text_message(str(final_result_queue.get()))
