import asyncio
import base64
from types import SimpleNamespace

import pytest

from .conftest import Event


async def command(plugin, event, action, *args):
    return [reply async for reply in plugin.control(event, action, *args)]


def text_only(**extra):
    return {"chat_weight": 1, "meme_weight": 0, "question_weight": 0, **extra}


async def test_non_admin_cannot_bind_change_or_trigger(plugin_factory):
    plugin = plugin_factory(text_only())
    event = Event(admin=False)
    for action in ("开启", "关闭", "状态", "立即触发", "间隔"):
        result = await command(plugin, event, action)
        assert "管理员" in result[0]
    assert plugin.store.get(plugin.scope(event)) is None
    assert not plugin.context.sent and not plugin.context.generated


async def test_private_commands_rejected(plugin_factory):
    plugin = plugin_factory(text_only())
    assert "目标群" in (await command(plugin, Event(group=""), "开启"))[0]


async def test_enable_is_not_an_immediate_send_and_group_isolation(plugin_factory):
    plugin = plugin_factory(text_only())
    event = Event()
    await command(plugin, event, "开启")
    row = plugin.store.get(plugin.scope(event))
    assert row["enabled"] and 3600 <= row["next_at"] - plugin.clock() <= 10800
    assert not plugin.context.sent
    assert plugin.store.get(plugin.scope(Event(group="other"))) is None
    await command(plugin, event, "固定间隔", "120")
    assert plugin.store.get(plugin.scope(event))["next_at"] == plugin.clock() + 7200
    await command(plugin, event, "关闭")
    assert plugin.store.get(plugin.scope(event))["enabled"] == 0


async def test_manual_trigger_uses_existing_model_and_same_target(plugin_factory):
    plugin = plugin_factory(text_only())
    event = Event()
    result = await command(plugin, event, "立即触发")
    assert "正常返回" in result[-1]
    assert len(plugin.context.sent) == 1
    assert plugin.context.sent[0][0] == event.unified_msg_origin
    assert plugin.context.generated[0]["chat_provider_id"] == "existing-deepseek"
    assert "tools" not in plugin.context.generated[0]
    row = plugin.store.get(plugin.scope(event))
    assert row["attempts"] == row["returned"] == 1 and row["enabled"] == 0


async def test_manual_limit_cannot_be_reset_by_toggle(plugin_factory):
    plugin = plugin_factory(text_only(daily_limit=1))
    event = Event()
    await command(plugin, event, "立即触发")
    await command(plugin, event, "开启")
    result = await command(plugin, event, "立即触发")
    assert "今日" in result[-1] and len(plugin.context.sent) == 1


async def test_shutdown_during_generation_prevents_delivery(plugin_factory):
    plugin = plugin_factory(text_only())
    event = Event()
    await command(plugin, event, "开启")
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(**kwargs):
        started.set()
        await release.wait()
        return SimpleNamespace(completion_text="不应该发出")

    plugin.context.llm_generate = generate
    task = asyncio.create_task(plugin.execute(plugin.scope(event), manual=True))
    await started.wait()
    await command(plugin, event, "关闭")
    release.set()
    assert "取消" in await task
    assert not plugin.context.sent


async def test_terminate_cancels_inflight_manual_work(plugin_factory):
    plugin = plugin_factory(text_only())
    event = Event()
    scope = await plugin._bind(event)
    started = asyncio.Event()

    async def generate(**kwargs):
        started.set()
        await asyncio.Event().wait()

    plugin.context.llm_generate = generate
    task = asyncio.create_task(plugin.execute(scope, manual=True))
    await started.wait()
    await plugin.terminate()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not plugin.context.sent
    assert plugin.store.get(scope)["attempts"] == 1


async def test_overlapping_due_triggers_send_once(plugin_factory):
    plugin = plugin_factory(text_only())
    event = Event()
    await command(plugin, event, "开启")
    scope = plugin.scope(event)
    plugin.store.defer(scope, plugin.clock() - 1, "test")
    await asyncio.gather(plugin.execute(scope), plugin.execute(scope))
    assert len(plugin.context.sent) == 1


async def test_adapter_false_return_counts_failure(plugin_factory):
    plugin = plugin_factory(text_only(daily_limit=10, failure_limit=3))
    event = Event()
    await command(plugin, event, "开启")
    plugin.context.send_result = False
    for _ in range(3):
        result = await command(plugin, event, "立即触发")
        assert "失败" in result[-1]
    row = plugin.store.get(plugin.scope(event))
    assert row["returned"] == 0 and row["failures"] == 3 and row["enabled"] == 0


async def test_restart_qq_waits_for_a_received_event(plugin_factory):
    first = plugin_factory(text_only())
    event = Event()
    await command(first, event, "开启")
    second = plugin_factory(text_only())
    scope = second.scope(event)
    second.store.defer(scope, second.clock() - 1, "test")
    assert "恢复 QQ 会话" in await second.execute(scope)
    assert second.store.get(scope)["attempts"] == 0
    now = second.clock() + 61
    second.clock = lambda: now
    await second.observe(event)
    assert "正常返回" in await second.execute(scope)


async def test_no_collection_in_unconfigured_group_or_from_self(plugin_factory):
    plugin = plugin_factory(text_only())
    event = Event(admin=False)
    await plugin.observe(event)
    assert plugin.store.get(plugin.scope(event)) is None
    await command(plugin, Event(), "开启")
    await plugin.observe(Event(sender="bot-self"))
    assert not plugin.store.recent(plugin.scope(event), 50, plugin.clock())
    await plugin.observe(Event(sender="member", text="正常聊天"))
    assert plugin.store.recent(plugin.scope(event), 50, plugin.clock())[0]["text"] == "正常聊天"


async def test_meme_paths_and_image_send(plugin_factory, tmp_path):
    root = tmp_path / "pack"
    (root / "memes/happy").mkdir(parents=True)
    gif = root / "memes/happy/test.gif"
    gif.write_bytes(base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"))
    plugin = plugin_factory(
        {
            "chat_weight": 0,
            "meme_weight": 1,
            "question_weight": 0,
            "meme_pack_dir": str(root),
            "meme_categories": ["happy"],
        }
    )
    result = await command(plugin, Event(), "立即触发")
    assert "meme" in result[-1]
    assert plugin.context.sent[0][1].chain[0].path == str(gif)
    assert not plugin.context.generated
    outside = tmp_path / "outside.gif"
    outside.write_bytes(gif.read_bytes())
    assert not plugin.valid_meme(outside, root)
    try:
        (root / "memes/happy/escape.gif").symlink_to(outside)
    except OSError:
        return
    assert not plugin.valid_meme(root / "memes/happy/escape.gif", root)
    assert len(plugin._scan_memes()) == 1


async def test_model_error_does_not_leak_secret(plugin_factory):
    plugin = plugin_factory(text_only())

    async def fail(**kwargs):
        raise RuntimeError("sensitive-token-value")

    plugin.context.llm_generate = fail
    result = await command(plugin, Event(), "立即触发")
    assert "失败" in result[-1] and "sensitive-token-value" not in result[-1]
    assert not plugin.context.sent
    assert "sensitive-token-value" not in plugin.store.get(plugin.scope(Event()))["last_error"]


async def test_empty_model_response_is_not_sent(plugin_factory):
    plugin = plugin_factory(text_only())

    async def empty(**kwargs):
        return SimpleNamespace(completion_text="   ")

    plugin.context.llm_generate = empty
    result = await command(plugin, Event(), "立即触发")
    assert "失败" in result[-1] and not plugin.context.sent
    assert plugin.store.get(plugin.scope(Event()))["attempts"] == 1


async def test_admin_can_select_daily_mode_without_enabling(plugin_factory):
    plugin = plugin_factory(text_only())
    event = Event()
    result = await command(plugin, event, "定时", "20:00")
    assert "每日时刻" in result[-1]
    row = plugin.store.get(plugin.scope(event))
    assert row["mode"] == "daily" and row["enabled"] == 0
    await command(plugin, event, "开启")
    assert plugin.store.get(plugin.scope(event))["next_at"] > plugin.clock()
    assert not plugin.context.sent
