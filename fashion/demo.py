from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()


# state
class State(TypedDict):
    question: str
    need_search: bool
    context: str
    answer: str
    verified: bool

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

# 외부 검색이 필요한지 판단
def router(state: State):
    prompt = f"""
    다음 질문에 답하려면 외부 정보 검색이 필요한가? Yes 또는 No로만 답해라.

    질문: {state['question']}
    """
    result = llm.invoke(prompt).content
    need_search = "Yes" in result
    return {"need_search": need_search}

# 날ㄱ씨 정보(지금은 데모라 가짜)
def search(state: State):
    fake_context = "오늘 서울에는 비가 올 가능성이 있습니다."
    return {"context": fake_context}

# 답변 만들기
def answer(state: State):
    prompt = f"""
    질문: {state['question']}
    참고정보: {state.get('context', '')}
    위 정보를 바탕으로 사용자에게 답변을 생성하라.
    """
    result = llm.invoke(prompt).content
    return {"answer": result}

# 거ㅁ증
def verify(state: State):
    prompt = f"""
    다음 답변이 질문에 적절한가? Yes 또는 No로만 답해라.

    질문: {state['question']}
    답변: {state['answer']}
    """
    result = llm.invoke(prompt).content
    verified = "Yes" in result
    return {"verified": verified}

# Graph 구성
graph = StateGraph(State)

graph.add_node("router", router)
graph.add_node("search", search)
graph.add_node("answer", answer)
graph.add_node("verify", verify)

graph.set_entry_point("router")

graph.add_conditional_edges(
    "router",
    lambda state: "search" if state["need_search"] else "answer",
    {
        "search": "search",
        "answer": "answer"
    }
)

graph.add_edge("search", "answer")
graph.add_edge("answer", "verify")

graph.add_conditional_edges(
    "verify",
    lambda state: "end" if state["verified"] else "retry",
    {
        "end": END,
        "retry": "answer"
    }
)

app = graph.compile()

# 실행
result = app.invoke({
    "question": "오늘 비 올까? 우산 가져가야 할까?"
})

print("\n최종 답변:")
print(result["answer"])
