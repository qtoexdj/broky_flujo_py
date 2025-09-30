from operator import add
from typing import Annotated, List, TypedDict

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.core.config import Settings


class ConversationState(TypedDict):
    messages: Annotated[List[BaseMessage], add]


def build_conversation_graph(settings: Settings):
    """Create a minimal LangGraph flow that sends the conversation to the LLM."""

    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.temperature,
        api_key=settings.openai_api_key,
    )

    def call_model(state: ConversationState) -> ConversationState:
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(ConversationState)
    graph.add_node("generate", call_model)
    graph.set_entry_point("generate")
    graph.add_edge("generate", END)

    return graph.compile()
