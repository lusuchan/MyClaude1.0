"""Tests for the Anthropic wrapper: response flattening and retry policy."""

from __future__ import annotations

import pytest

from briefbot.config import Settings
from briefbot.llm import ClaudeClient, _extract, _is_retryable
from briefbot.retry import retry_call
from conftest import FakeAnthropic, make_message, search_result_block, text_block, tool_use_block


# ---------------------------------------------------------------------------
# Response flattening
# ---------------------------------------------------------------------------


def test_text_blocks_are_concatenated():
    message = make_message([text_block("Hello "), text_block("world")])
    assert _extract(message).text == "Hello world"


def test_citations_are_collected_from_text_blocks():
    message = make_message([text_block("news", [("https://x.com/a", "Story A")])])
    response = _extract(message)

    assert len(response.citations) == 1
    assert response.citations[0].url == "https://x.com/a"
    assert response.citations[0].cited is True


def test_search_results_are_recorded_but_not_marked_cited():
    message = make_message([search_result_block([("https://x.com/b", "Result B")])])
    response = _extract(message)

    assert len(response.citations) == 1
    assert response.citations[0].cited is False
    assert response.cited_sources == []


def test_a_search_result_later_cited_is_promoted():
    message = make_message(
        [
            search_result_block([("https://x.com/a", "Result A")]),
            text_block("as reported", [("https://x.com/a", "Story A")]),
        ]
    )
    response = _extract(message)

    assert len(response.citations) == 1, "the same URL must not appear twice"
    assert response.citations[0].cited is True


def test_duplicate_urls_are_deduplicated():
    message = make_message(
        [
            text_block("one", [("https://x.com/a", "A")]),
            text_block("two", [("https://x.com/a", "A")]),
        ]
    )
    assert len(_extract(message).citations) == 1


def test_searches_are_counted():
    message = make_message([tool_use_block(), tool_use_block(), text_block("done")])
    assert _extract(message).search_count == 2


def test_usage_is_carried_through():
    response = _extract(make_message([text_block("x")]))
    assert response.input_tokens == 100
    assert response.output_tokens == 200


def test_an_empty_response_is_falsy():
    assert not _extract(make_message([text_block("   ")]))
    assert _extract(make_message([text_block("real")]))


def test_missing_title_falls_back_to_the_url_in_markdown():
    response = _extract(make_message([text_block("x", [("https://x.com/a", "")])]))
    assert response.citations[0].as_markdown() == "[https://x.com/a](https://x.com/a)"


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class Boom(Exception):
    def __init__(self, status_code=None, message="boom"):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.parametrize("status", [429, 500, 502, 503, 529, 408])
def test_transient_statuses_are_retryable(status):
    assert _is_retryable(Boom(status_code=status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_not_retryable(status):
    assert not _is_retryable(Boom(status_code=status)), "a bad request fails identically every time"


def test_overloaded_text_is_retryable_regardless_of_type():
    assert _is_retryable(Exception("Error: overloaded_error"))


def test_connection_errors_are_retryable_by_type_name():
    class APIConnectionError(Exception):
        pass

    assert _is_retryable(APIConnectionError("network down"))


def test_client_retries_then_succeeds():
    slept: list[float] = []
    fake = FakeAnthropic([Boom(status_code=503), make_message([text_block("recovered")])])
    client = ClaudeClient(Settings(api_key="k"), client=fake, sleep=slept.append)

    response = client.complete(prompt="hi", attempts=3)

    assert response.text == "recovered"
    assert len(fake.calls) == 2
    assert len(slept) == 1


def test_client_does_not_retry_a_bad_request():
    slept: list[float] = []
    fake = FakeAnthropic([Boom(status_code=400), make_message([text_block("never reached")])])
    client = ClaudeClient(Settings(api_key="k"), client=fake, sleep=slept.append)

    with pytest.raises(Boom):
        client.complete(prompt="hi", attempts=3)

    assert len(fake.calls) == 1
    assert slept == []


def test_client_gives_up_after_the_attempt_budget():
    fake = FakeAnthropic([Boom(status_code=503)] * 5)
    client = ClaudeClient(Settings(api_key="k"), client=fake, sleep=lambda _: None)

    with pytest.raises(Boom):
        client.complete(prompt="hi", attempts=3)

    assert len(fake.calls) == 3


def test_backoff_grows_and_is_capped():
    delays: list[float] = []

    def always_fail():
        raise Boom(status_code=503)

    with pytest.raises(Boom):
        retry_call(
            always_fail,
            attempts=6,
            base_delay=2.0,
            max_delay=10.0,
            sleep=delays.append,
            should_retry=_is_retryable,
        )

    assert delays == [2.0, 4.0, 8.0, 10.0, 10.0]


# ---------------------------------------------------------------------------
# Request construction
# ---------------------------------------------------------------------------


def test_web_search_tool_is_attached_when_requested():
    fake = FakeAnthropic([make_message([text_block("ok")])])
    client = ClaudeClient(Settings(api_key="k", model="m", max_searches=4), client=fake)

    client.complete(prompt="p", web_search=True)

    tools = fake.calls[0]["tools"]
    assert tools[0]["type"] == "web_search_20250305"
    assert tools[0]["max_uses"] == 4


def test_no_tools_are_sent_when_search_is_off():
    fake = FakeAnthropic([make_message([text_block("ok")])])
    client = ClaudeClient(Settings(api_key="k"), client=fake)

    client.complete(prompt="p")

    assert "tools" not in fake.calls[0]


def test_system_prompt_and_model_are_passed_through():
    fake = FakeAnthropic([make_message([text_block("ok")])])
    client = ClaudeClient(Settings(api_key="k", model="my-model"), client=fake)

    client.complete(prompt="p", system="be terse", max_tokens=123)

    call = fake.calls[0]
    assert call["system"] == "be terse"
    assert call["model"] == "my-model"
    assert call["max_tokens"] == 123
    assert call["messages"] == [{"role": "user", "content": "p"}]


def test_a_missing_api_key_is_refused_up_front():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        ClaudeClient(Settings(api_key=None))
