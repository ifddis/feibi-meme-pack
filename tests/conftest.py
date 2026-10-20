"""Unit-test SDK doubles only. These tests never send messages to a real group."""

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


def module(name):
    value = types.ModuleType(name)
    value.__path__ = []
    sys.modules[name] = value
    return value


module("astrbot")
api = module("astrbot.api")
event_api = module("astrbot.api.event")
star_api = module("astrbot.api.star")
core_api = module("astrbot.core")
components = module("astrbot.api.message_components")


class Star:
    def __init__(self, context):
        self.context = context


class MessageChain:
    def __init__(self, chain):
        self.chain = chain


class Image:
    @staticmethod
    def fromFileSystem(path):
        return SimpleNamespace(path=path)


class Plain:
    def __init__(self, text):
        self.text = text


api.logger = SimpleNamespace(warning=lambda *args: None)
event_api.AstrMessageEvent = object
event_api.MessageChain = MessageChain
event_api.filter = SimpleNamespace(
    command=lambda *a, **k: lambda f: f,
    event_message_type=lambda *a, **k: lambda f: f,
    EventMessageType=SimpleNamespace(GROUP_MESSAGE=1),
)
star_api.Context = object
star_api.Star = Star
star_api.StarTools = SimpleNamespace(get_data_dir=lambda name: Path("/tmp") / name)
core_api.AstrBotConfig = dict
components.Plain = Plain
components.Image = Image


class Event:
    def __init__(
        self, *, admin=True, group="group-one", sender="owner", text="你好", platform="qq_official"
    ):
        self.admin = admin
        self.group = group
        self.sender = sender
        self.text = text
        self.platform = platform
        self.unified_msg_origin = f"bot:GroupMessage:{group}"
        self.message_obj = SimpleNamespace(message_id="id-" + text)

    def is_admin(self):
        return self.admin

    def get_group_id(self):
        return self.group

    def get_platform_id(self):
        return "bot"

    def get_platform_name(self):
        return self.platform

    def get_sender_id(self):
        return self.sender

    def get_self_id(self):
        return "bot-self"

    def get_sender_name(self):
        return self.sender

    def get_message_str(self):
        return self.text

    def plain_result(self, text):
        return text


class Context:
    def __init__(self):
        self.sent = []
        self.generated = []
        self.send_result = True

    async def get_current_chat_provider_id(self, umo):
        return "existing-deepseek"

    async def llm_generate(self, **kwargs):
        self.generated.append(kwargs)
        return SimpleNamespace(completion_text="今天过得怎么样喵？")

    async def send_message(self, umo, chain):
        self.sent.append((umo, chain))
        return self.send_result


@pytest.fixture
def plugin_factory(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from astrbot_plugin_random_events.main import RandomEventsPlugin

    monkeypatch.setattr(star_api.StarTools, "get_data_dir", lambda name: tmp_path / name)
    now = datetime(2026, 10, 20, 12, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()

    def create(config=None, context=None):
        instance = RandomEventsPlugin(context or Context(), config or {})
        instance.clock = lambda: now
        return instance

    return create
