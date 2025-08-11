import os
import json
import pytest

try:
    from langgraph_sdk import get_client
except Exception as e:
    raise RuntimeError("langgraph-sdk is required for E2E tests. Install via extras 'e2e' or add to your environment.") from e


def _log(title: str, payload):
    # Compact JSON logging for easier CI/debugging; fall back to str if non-serializable
    try:
        formatted = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception:
        formatted = str(payload)
    print(f"\n=== {title} ===\n{formatted}\n")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_history_endpoint_e2e():
    """
    End-to-end test against a running server using the LangGraph SDK.
    This verifies assistant creation, run execution, join endpoint, and history retrieval.
    Requires the server to be running and accessible.
    """
    server_url = os.getenv("SERVER_URL", "http://localhost:8000/v1")
    api_key = os.getenv("API_KEY", "test-key")
    print(f"Using SERVER_URL={server_url}")

    client = get_client(url=server_url, api_key=api_key)

    # Create an assistant (idempotent if server supports if_exists/do_nothing)
    assistant = await client.assistants.create(
        graph_id="agent",
        config={"tags": ["chat", "llm"]},
        if_exists="do_nothing",
    )
    _log("Assistant.create response", assistant)
    assert "assistant_id" in assistant, f"Invalid assistant response: {assistant}"

    # Create a thread
    thread = await client.threads.create()
    _log("Threads.create response", thread)
    assert "thread_id" in thread, f"Invalid thread response: {thread}"
    thread_id = thread["thread_id"]

    # Initial history (likely empty)
    initial_history = await client.threads.get_history(thread_id)
    _log("Threads.get_history initial", initial_history)
    assert isinstance(initial_history, list)

    # Create a run and wait for completion using join (also validates join endpoint behavior)
    run = await client.runs.create(
        thread_id=thread_id,
        assistant_id=assistant["assistant_id"],
        input={"messages": [{"role": "human", "content": "Hello! Tell me a short joke."}]},
    )
    _log("Runs.create response", run)
    assert "run_id" in run

    final_state = await client.runs.join(thread_id, run["run_id"])
    _log("Runs.join final_state", final_state)
    assert isinstance(final_state, dict)

    # Verify history has at least one snapshot after completing the run
    history_after = await client.threads.get_history(thread_id)
    _log("Threads.get_history after run", history_after)
    assert isinstance(history_after, list)
    assert len(history_after) >= 1, f"Expected at least one checkpoint after run; got {len(history_after)}"

    # Validate pagination with limit
    limited = await client.threads.get_history(thread_id, limit=1)
    _log("Threads.get_history limit=1", limited)
    assert isinstance(limited, list)
    assert len(limited) == 1
