# -*- coding: utf-8 -*-
"""ModelClient token usage streaming regression tests."""

from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

from phone_agent.model.client import ModelClient, ModelConfig


class _FakeCompletions:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._chunks)


class _FakeChat:
    def __init__(self, chunks):
        self.completions = _FakeCompletions(chunks)


class _FakeOpenAI:
    def __init__(self, chunks):
        self.chat = _FakeChat(chunks)


def _make_delta_chunk(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
        usage=None,
    )


def _make_usage_chunk(prompt: int, completion: int, total: int, cached: int):
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
        ),
    )


def test_request_collects_stream_usage_from_empty_choices_chunk_and_emits_numeric_tokens_line():
    client = ModelClient.__new__(ModelClient)
    client.config = ModelConfig(model_name="demo-model", lang="cn")
    client.client = _FakeOpenAI(
        [
            _make_delta_chunk("正在思考"),
            _make_delta_chunk("finish(message=完成)"),
            _make_usage_chunk(prompt=10, completion=42, total=52, cached=3),
        ]
    )

    stdout = StringIO()
    with redirect_stdout(stdout):
        response = client.request([{"role": "user", "content": "demo"}])

    output = stdout.getvalue()
    assert "[TOKENS] prompt=10 completion=42 total=52 cached=3" in output
    assert "ttft=" in output
    assert "throughput=" in output
    assert "tps" not in output.split("[TOKENS]", 1)[1].splitlines()[0]
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 42
    assert response.total_tokens == 52
    assert response.cached_tokens == 3
    assert response.action == "finish(message=完成)"
    create_kwargs = client.client.chat.completions.calls[0]
    assert create_kwargs["stream"] is True
    assert create_kwargs["stream_options"] == {"include_usage": True}


def test_request_normalizes_dict_usage_values_returned_as_strings():
    client = ModelClient.__new__(ModelClient)
    client.config = ModelConfig(model_name="demo-model", lang="en")
    client.client = _FakeOpenAI(
        [
            {"choices": [{"delta": {"content": "do(action=tap(point='1,1'))"}}], "usage": None},
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": "10",
                    "completion_tokens": "42",
                    "total_tokens": "52",
                    "prompt_tokens_details": {"cached_tokens": "3"},
                },
            },
        ]
    )

    stdout = StringIO()
    with redirect_stdout(stdout):
        response = client.request([{"role": "user", "content": "demo"}])

    assert "[TOKENS] prompt=10 completion=42 total=52 cached=3" in stdout.getvalue()
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 42
    assert response.total_tokens == 52
    assert response.cached_tokens == 3


def test_request_keeps_partial_usage_and_computes_missing_total():
    client = ModelClient.__new__(ModelClient)
    client.config = ModelConfig(model_name="demo-model", lang="en")
    client.client = _FakeOpenAI(
        [
            _make_delta_chunk("finish(message=done)"),
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 42,
                },
            },
            {"choices": [], "usage": {}},
        ]
    )

    stdout = StringIO()
    with redirect_stdout(stdout):
        response = client.request([{"role": "user", "content": "demo"}])

    assert "[TOKENS] prompt=10 completion=42 total=52 cached=0" in stdout.getvalue()
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 42
    assert response.total_tokens == 52
