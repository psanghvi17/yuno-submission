from langchain_core.language_models.chat_models import BaseChatModel


def build_chat_model(model_name: str, *, mock: bool) -> BaseChatModel:
    if mock:
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        return FakeListChatModel(
            responses=[
                (
                    "Mock research findings: multi-agent orchestration improves throughput. "
                    '{"confidence": 0.82, "category": "research"}'
                ),
                (
                    "Mock summary: Teams can coordinate Researcher and Writer agents "
                    "in a linear pipeline with persisted run messages."
                ),
                (
                    '{"confidence": 0.9, "category": "support", "summary": "Resolved."}'
                ),
                "Mock coordinator plan: delegate research then writing.",
                "Mock specialist resolution for the support ticket.",
                "Mock channel notification payload ready for Telegram.",
            ]
        )

    from langchain_openai import ChatOpenAI

    from app.config import get_settings

    settings = get_settings()
    return ChatOpenAI(
        model=model_name or "gpt-4o-mini",
        api_key=settings.openai_api_key,
        temperature=0.2,
    )
