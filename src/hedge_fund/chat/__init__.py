__all__ = ["ChatCommandRunner"]


def __getattr__(name: str):
    if name == "ChatCommandRunner":
        from hedge_fund.chat.command import ChatCommandRunner

        return ChatCommandRunner
    raise AttributeError(name)
