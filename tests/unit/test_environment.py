from importlib.metadata import version

import pytest
from pydantic import BaseModel, StrictInt, ValidationError
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver


def test_dependency_baseline():
    assert version("langgraph") == "1.2.18"
    assert version("langgraph-checkpoint-sqlite") == "3.1.2"
    assert version("pydantic") == "2.12.5"


def test_pydantic_strict_integer():
    class Input(BaseModel):
        budget: StrictInt

    with pytest.raises(ValidationError):
        Input(budget=True)


def test_checkpoint_resumes_completed_node_without_repeating_it(tmp_path):
    class State(TypedDict):
        count: int

    calls = []
    fail = [True]

    def first(state):
        calls.append("first")
        return {"count": state["count"] + 1}

    def second(state):
        if fail[0]:
            raise RuntimeError("injected interruption")
        calls.append("second")
        return {"count": state["count"] + 1}

    builder = StateGraph(State)
    builder.add_node("first", first)
    builder.add_node("second", second)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    db = str(tmp_path / "checkpoint.db")
    config = {"configurable": {"thread_id": "s0"}}
    with SqliteSaver.from_conn_string(db) as saver:
        graph = builder.compile(checkpointer=saver)
        with pytest.raises(RuntimeError):
            graph.invoke({"count": 0}, config)
    fail[0] = False
    with SqliteSaver.from_conn_string(db) as saver:
        result = builder.compile(checkpointer=saver).invoke(None, config)
    assert result["count"] == 2
    assert calls == ["first", "second"]
