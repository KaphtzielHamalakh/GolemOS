"""Offline regression coverage for the GolemOS executive boundary."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from agentos.agentos_router.resident import ResidentExecutive
from agentos.provider.ollama import OllamaProvider
from agentos.provider.types import (
    ChatConfig,
    DoneEvent,
    ErrorEvent,
    Message,
    ModelInfo,
    StreamEvent,
    TextDeltaEvent,
    ToolDefinition,
    ToolUseEndEvent,
)


class FakeProvider:
    provider_name = "fake"

    def __init__(self, *events: StreamEvent, delay: float = 0) -> None:
        self.events = events
        self.delay = delay
        self.calls: list[tuple[list[Message], list[ToolDefinition] | None, ChatConfig | None]] = []
        self.closed = False

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        config: ChatConfig | None = None,
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append((messages, tools, config))
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            for event in self.events:
                yield event
        finally:
            self.closed = True

    async def list_models(self) -> list[ModelInfo]:
        return []


def response(text: str) -> FakeProvider:
    return FakeProvider(TextDeltaEvent(text=text), DoneEvent())


@pytest.mark.asyncio
async def test_local_answer_does_not_call_cloud() -> None:
    local = response('{"action":"answer","text":"Four."}')
    cloud = response("unused")
    result = await ResidentExecutive(local, cloud).run("What is 2 + 2?", allow_cloud=True)
    assert (result.status, result.text) == ("local", "Four.")
    assert not cloud.calls
    assert local.calls[0][1] is None
    assert local.calls[0][2].max_tokens == 512


@pytest.mark.asyncio
async def test_escalation_is_explicit_single_and_uses_original_task() -> None:
    local = response('{"action":"escalate","reason":"Needs deeper analysis"}')
    cloud = response("Cloud answer")
    executive = ResidentExecutive(local, cloud)
    blocked = await executive.run("Analyze this difficult problem")
    assert blocked.status == "needs_cloud"
    assert not cloud.calls
    result = await executive.run("Analyze this difficult problem", allow_cloud=True)
    assert (result.status, result.text) == ("cloud", "Cloud answer")
    assert len(cloud.calls) == 1
    assert cloud.calls[0][0] == [Message(role="user", content="Analyze this difficult problem")]
    assert cloud.calls[0][1] is None
    # Authorization is per invocation, never sticky.
    assert (await executive.run("Another task")).status == "needs_cloud"
    assert len(cloud.calls) == 1


@pytest.mark.asyncio
async def test_missing_cloud_stays_pending_even_with_permission() -> None:
    local = response('{"action":"escalate","reason":"Hard task"}')
    assert (await ResidentExecutive(local).run("Task", allow_cloud=True)).status == "needs_cloud"


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        "[]",
        '{"action":"answer","text":""}',
        '{"action":"answer","text":3}',
        '{"action":"escalate","reason":""}',
        '{"action":"escalate","reason":"hard","provider":"attacker"}',
        '{"action":"answer","text":"ok","tool":"shell"}',
        '{"action":"escalate","reason":true}',
    ],
)
@pytest.mark.asyncio
async def test_invalid_local_decisions_never_send_to_cloud(raw: str) -> None:
    cloud = response("must not run")
    result = await ResidentExecutive(response(raw), cloud).run("Task", allow_cloud=True)
    assert (result.status, result.reason) == ("error", "local_failed")
    assert not cloud.calls


@pytest.mark.parametrize(
    "events",
    [
        [ErrorEvent(message="secret upstream details")],
        [ToolUseEndEvent(tool_name="shell", arguments={"command": "anything"})],
        [TextDeltaEvent(text='{"action":"answer","text":"truncated"}')],
        [
            TextDeltaEvent(text='{"action":"answer","text":"truncated"}'),
            DoneEvent(stop_reason="length"),
        ],
        [TextDeltaEvent(text="x" * 16001), DoneEvent()],
        [DoneEvent()],
        [DoneEvent(), TextDeltaEvent(text="late data")],
    ],
)
@pytest.mark.asyncio
async def test_bad_streams_fail_closed_and_close(events: list[StreamEvent]) -> None:
    local = FakeProvider(*events)
    cloud = response("must not run")
    result = await ResidentExecutive(local, cloud).run("Task", allow_cloud=True)
    assert result.status == "error"
    assert "secret" not in result.reason
    assert local.closed
    assert not cloud.calls


@pytest.mark.asyncio
async def test_timeout_and_cancellation_do_not_escalate() -> None:
    local = FakeProvider(delay=10)
    cloud = response("unused")
    result = await ResidentExecutive(local, cloud, timeout=0.01).run("Task", allow_cloud=True)
    assert result.status == "error"
    assert local.closed
    task = asyncio.create_task(ResidentExecutive(local, cloud).run("Task", allow_cloud=True))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not cloud.calls


@pytest.mark.asyncio
async def test_cloud_failure_does_not_retry() -> None:
    local = response('{"action":"escalate","reason":"Hard"}')
    cloud = FakeProvider(ErrorEvent(message="secret"))
    result = await ResidentExecutive(local, cloud).run("Task", allow_cloud=True)
    assert (result.status, result.reason) == ("error", "cloud_failed")
    assert len(cloud.calls) == 1


@pytest.mark.parametrize("prompt", ["", "  ", "x" * 4001])
@pytest.mark.asyncio
async def test_input_limit_prevents_any_inference(prompt: str) -> None:
    local = response("unused")
    assert (await ResidentExecutive(local).run(prompt)).reason == "input_limit"
    assert not local.calls


@pytest.mark.asyncio
async def test_real_ollama_adapter_completes_locally_without_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        assert body["model"] == "golemos-gemma3-4b-q4"
        assert "tools" not in body
        assert body["options"]["num_predict"] == 512
        return httpx.Response(
            200,
            text=json.dumps(
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"action":"answer","text":"Tuesday."}',
                    },
                    "done": True,
                    "done_reason": "stop",
                }
            )
            + "\n",
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        "agentos.provider.ollama.httpx.AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handle), **kwargs),
    )
    executive = ResidentExecutive(
        OllamaProvider(model="golemos-gemma3-4b-q4", base_url="http://127.0.0.1:11434")
    )
    result = await executive.run("The meeting moved to Tuesday. When is it?")
    assert (result.status, result.text) == ("local", "Tuesday.")
    assert len(requests) == 1
    assert str(requests[0].url) == "http://127.0.0.1:11434/api/chat"
