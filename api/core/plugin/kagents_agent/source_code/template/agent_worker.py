# agent_worker.py
import asyncio, json, sys
from uuid import uuid4
import httpx
from a2a.client import A2AClient
from a2a.types import MessageSendParams, SendStreamingMessageRequest

async def main():
    payload = json.loads(sys.stdin.read())
    async with httpx.AsyncClient() as httpx_client:
        client = await A2AClient.get_client_from_agent_card_url(httpx_client, payload["agent_url"])
        streaming_request = SendStreamingMessageRequest(
            id=uuid4().hex,
            params=MessageSendParams(**payload["send_message_payload"])
        )
        async for chunk in client.send_message_streaming(streaming_request):
            print(json.dumps(chunk.model_dump(mode="json", exclude_none=True)), flush=True)

asyncio.run(main())
