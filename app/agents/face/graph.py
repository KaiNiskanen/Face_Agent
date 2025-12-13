from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from app.agents.face.state import FaceAgentState

def build_face_graph(llm: ChatOpenAI):
    async def call_model(state: FaceAgentState) -> dict:
        messages = state["messages"]
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    graph = StateGraph(FaceAgentState)
    graph.add_node("model", call_model)
    graph.add_edge(START, "model")
    graph.add_edge("model", END)

    return graph.compile()
