from typing import Any, Dict, List

import pytest

from broky.core.context import BrokyContext
from broky.runtime.master import MasterAgentRuntime, MasterAgentOutput


class _DummyExecutor:
    def invoke(self, context: BrokyContext) -> BrokyContext:
        context.metadata = {
            "intents": [],
            "filters": {},
            "subagents": {},
        }
        return context


class _SpyAgent:
    def __init__(self, name: str, call_log: List[str], reply: str | None = None, metadata_update: Dict[str, Any] | None = None):
        self._name = name
        self._log = call_log
        self._reply = reply
        self._metadata_update = metadata_update

    def invoke(self, context: BrokyContext) -> BrokyContext:
        self._log.append(self._name)
        if self._reply is not None:
            context.metadata["reply"] = self._reply
        if self._metadata_update:
            context.metadata.setdefault("postprocess", {}).update(self._metadata_update)
        return context


def _build_runtime_with_spies(call_log: List[str]) -> MasterAgentRuntime:
    runtime = MasterAgentRuntime.__new__(MasterAgentRuntime)  # type: ignore
    runtime._settings = None  # type: ignore[attr-defined]
    runtime._memory = None  # type: ignore[attr-defined]
    runtime._history_repo = None  # type: ignore[attr-defined]
    runtime._profile_repo = None  # type: ignore[attr-defined]
    runtime._prospect_repo = None  # type: ignore[attr-defined]
    runtime._followup_repo = None  # type: ignore[attr-defined]

    runtime._executor = _DummyExecutor()  # type: ignore[attr-defined]
    runtime._response_agent = _SpyAgent("response", call_log, reply="Respuesta base")  # type: ignore[attr-defined]
    runtime._fixing_agent = _SpyAgent("fixing", call_log, reply="Respuesta ajustada")  # type: ignore[attr-defined]
    runtime._splitter_agent = _SpyAgent(
        "splitter",
        call_log,
        metadata_update={"split_messages": ["Mensaje final", "Siguiente fragmento"]},
    )  # type: ignore[attr-defined]
    runtime._justification_agent = _SpyAgent("justification", call_log)  # type: ignore[attr-defined]

    runtime._rag_agent = None  # type: ignore[attr-defined]
    runtime._project_interest_agent = None  # type: ignore[attr-defined]
    runtime._calification_agent = None  # type: ignore[attr-defined]
    runtime._schedule_agent = None  # type: ignore[attr-defined]
    runtime._files_agent = None  # type: ignore[attr-defined]

    return runtime


def test_master_runtime_executes_response_chain_in_order():
    call_log: List[str] = []
    runtime = _build_runtime_with_spies(call_log)

    state = {
        "payload": {
            "message": "hola",
            "from": "user-123",
        },
        "normalized": {},
    }

    output: MasterAgentOutput = runtime.run(state)

    assert call_log == ["response", "fixing", "splitter", "justification"]
    assert output.reply == "Mensaje final"
    assert output.metadata.get("postprocess", {}).get("split_messages") == ["Mensaje final", "Siguiente fragmento"]
