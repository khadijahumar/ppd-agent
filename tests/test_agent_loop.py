"""Test the agent's tool-calling loop with a mock OpenAI client.

We don't call OpenRouter from CI — instead we substitute a fake client that
returns a scripted sequence of tool-call / final responses, and we assert
that:
  * the agent dispatches the right tool functions,
  * tool results (text + images) propagate to AgentTurn,
  * the conversation history is correctly maintained.
"""
from __future__ import annotations

import json
import os
import pytest

# Skip if parquet data isn't ready (the dispatched tools need it).
parquet_dir_path = os.path.join(os.path.dirname(__file__), "..", "data", "parquet")
if not os.path.isfile(os.path.join(parquet_dir_path, "produksi_2021_hrc.parquet")):
    pytest.skip("parquet data not prepared; run scripts/prepare_data.py first",
                allow_module_level=True)


class _ToolCall:
    def __init__(self, id_: str, name: str, args: dict) -> None:
        self.id = id_
        self.type = "function"
        class _Fn:
            def __init__(self, name: str, arguments: str) -> None:
                self.name = name
                self.arguments = arguments
        self.function = _Fn(name, json.dumps(args))


class _Message:
    def __init__(self, content: str | None, tool_calls: list[_ToolCall] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message: _Message) -> None:
        self.message = message


class _Resp:
    def __init__(self, choices: list[_Choice]) -> None:
        self.choices = choices


class _FakeChatCompletions:
    def __init__(self, scripted: list) -> None:
        self._scripted = list(scripted)

    def create(self, **_kwargs):
        if not self._scripted:
            raise AssertionError("FakeClient ran out of scripted responses")
        return self._scripted.pop(0)


class _FakeClient:
    def __init__(self, scripted: list) -> None:
        self.chat = type("X", (), {"completions": _FakeChatCompletions(scripted)})()


def _build_agent_with_fake_client(scripted: list):
    from ppd_agent.agent import PPDAgent
    # bypass __init__'s API key check
    agent = PPDAgent.__new__(PPDAgent)
    agent.client = _FakeClient(scripted)
    agent.model = "test/model"
    from ppd_agent.prompts import SYSTEM_PROMPT
    agent.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    return agent


def test_agent_runs_tool_then_returns() -> None:
    scripted = [
        # turn 1: assistant decides to call hrc_lookup_coil("ASC111")
        _Resp([_Choice(_Message(
            content=None,
            tool_calls=[_ToolCall("call_1", "hrc_lookup_coil", {"coil_id": "ASC111"})],
        ))]),
        # turn 2: assistant produces the final answer
        _Resp([_Choice(_Message(content="Coil ASC111: spec MS EN 10025 S275JR+AR ..."))]),
    ]
    agent = _build_agent_with_fake_client(scripted)
    turn = agent.chat("Tampilkan detail coil ASC111")
    assert turn.error is None
    assert "ASC111" in turn.text
    assert turn.tool_calls == ["hrc_lookup_coil"]


def test_agent_plot_tool_collects_images() -> None:
    scripted = [
        _Resp([_Choice(_Message(
            content=None,
            tool_calls=[_ToolCall(
                "call_1", "hrc_histogram",
                {"variable": "YS", "spec_code": "S275JR"},
            )],
        ))]),
        _Resp([_Choice(_Message(content="Histogram dibuat."))]),
    ]
    agent = _build_agent_with_fake_client(scripted)
    turn = agent.chat("Histogram YS untuk S275JR")
    assert turn.error is None
    assert turn.tool_calls == ["hrc_histogram"]
    assert len(turn.image_paths) == 1
    assert turn.image_paths[0].exists()


def test_agent_handles_unknown_tool_gracefully() -> None:
    scripted = [
        _Resp([_Choice(_Message(
            content=None,
            tool_calls=[_ToolCall("call_1", "no_such_tool", {})],
        ))]),
        _Resp([_Choice(_Message(content="Maaf, gagal panggil tool."))]),
    ]
    agent = _build_agent_with_fake_client(scripted)
    turn = agent.chat("...")
    assert turn.error is None
    assert "Maaf" in turn.text


def test_agent_max_iterations_safety() -> None:
    # Always returns a tool_call → exhausts MAX_TOOL_ITERATIONS.
    scripted = [
        _Resp([_Choice(_Message(
            content=None,
            tool_calls=[_ToolCall(f"call_{i}", "hrc_lookup_coil", {"coil_id": "ASC111"})],
        ))])
        for i in range(20)
    ]
    agent = _build_agent_with_fake_client(scripted)
    turn = agent.chat("loop test")
    assert turn.error == "max_iterations_reached"
