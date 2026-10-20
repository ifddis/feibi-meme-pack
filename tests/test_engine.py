import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from astrbot_plugin_random_events.engine import (
    Settings,
    Store,
    choose_action,
    delay_seconds,
    is_open,
    next_day,
    next_open,
)


def stamp(hour, day=20):
    return datetime(2026, 10, day, hour, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()


def bind(store, settings=None):
    settings = settings or Settings()
    store.note("group", "bot:GroupMessage:one", "qq_official", stamp(12), settings)
    store.configure("group", stamp(12), settings, random.Random(1), enabled=True)
    return settings


@pytest.mark.parametrize(
    "config",
    [
        {"min_minutes": 0},
        {"max_minutes": 1441},
        {"daily_limit": 0},
        {"active_start": 24},
        {"active_end": -1},
        {"timezone": "bad/timezone"},
        {"chat_weight": -1},
        {"meme_categories": "happy"},
        {"chat_weight": 0, "meme_weight": 0, "question_weight": 0},
    ],
)
def test_invalid_configuration(config):
    with pytest.raises((ValueError, KeyError)):
        Settings.from_config(config)


@pytest.mark.parametrize("hour,expected", [(8, False), (9, True), (22, True), (23, False)])
def test_default_quiet_hours(hour, expected):
    assert is_open(stamp(hour), Settings()) is expected


def test_overnight_and_day_boundary():
    settings = Settings(active_start=22, active_end=7)
    assert is_open(stamp(23), settings) and is_open(stamp(1), settings)
    assert not is_open(stamp(12), settings)
    assert next_open(stamp(12), settings) == stamp(22)
    assert next_day(stamp(23), settings) == stamp(0, day=21) + 1
    assert next_day(stamp(12), Settings()) == stamp(9, day=21)
    assert next_open(stamp(23), Settings()) == stamp(9, day=21)


def test_random_range_and_weights():
    rng = random.Random(42)
    delays = [delay_seconds("random", 60, 180, rng) for _ in range(100)]
    assert min(delays) >= 3600 and max(delays) <= 10800
    assert len(set(delays)) > 1
    assert delay_seconds("fixed", 120, 120, rng) == 7200
    settings = Settings(chat_weight=1, question_weight=0, meme_weight=0)
    assert {choose_action(settings, False, rng) for _ in range(20)} == {"chat"}
    with pytest.raises(ValueError):
        choose_action(Settings(chat_weight=0, question_weight=0, meme_weight=1), False, rng)


def test_state_survives_restart_and_enable_does_not_reset_quota(tmp_path):
    path = tmp_path / "db.sqlite3"
    store = Store(path)
    settings = bind(store)
    row, _ = store.reserve("group", stamp(12), settings, random.Random(1), manual=True)
    assert row is not None
    restored = Store(path)
    assert restored.get("group")["attempts"] == 1
    assert restored.get("group")["enabled"] == 1
    restored.configure("group", stamp(12), settings, random.Random(1), enabled=True)
    assert restored.get("group")["attempts"] == 1


def test_concurrent_reservation_never_exceeds_daily_limit(tmp_path):
    store = Store(tmp_path / "db")
    settings = bind(store, Settings(daily_limit=3))

    def reserve(_):
        return store.reserve("group", stamp(12), settings, random.Random(1), manual=True)[0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(20)))
    assert sum(result is not None for result in results) == 3
    assert store.get("group")["attempts"] == 3
    assert store.get("group")["next_at"] == stamp(9, day=21)
    assert store.reserve("group", stamp(12, day=21), settings, random.Random(1), manual=True)[0]
    assert store.get("group")["attempts"] == 1


def test_recent_activity_and_quiet_hours_do_not_charge_attempts(tmp_path):
    store = Store(tmp_path / "db")
    settings = bind(store, Settings(activity_minutes=5))
    assert "最近" in store.reserve("group", stamp(13), settings, random.Random(1), True)[1]
    assert store.get("group")["attempts"] == 0
    assert "安静" in store.reserve("group", stamp(23), settings, random.Random(1), True)[1]
    assert store.get("group")["attempts"] == 0


def test_failures_pause_and_do_not_override_new_admin_settings(tmp_path):
    store = Store(tmp_path / "db")
    settings = bind(store)
    row, _ = store.reserve("group", stamp(12), settings, random.Random(1), True)
    for _ in range(3):
        store.finish(
            "group", stamp(12), "chat", "TimeoutError", settings, row["revision"], random.Random(1)
        )
    assert store.get("group")["enabled"] == 0
    store.configure("group", stamp(12), settings, random.Random(1), enabled=True)
    store.finish(
        "group", stamp(12), "chat", "old failure", settings, row["revision"], random.Random(1)
    )
    assert store.get("group")["enabled"] == 1
    assert store.get("group")["failures"] == 0


def test_delay_begins_after_completion(tmp_path):
    store = Store(tmp_path / "db")
    settings = bind(store)
    store.configure("group", stamp(12), settings, random.Random(1), mode="fixed", low=1, high=1)
    row, _ = store.reserve("group", stamp(12), settings, random.Random(1), True)
    store.finish("group", stamp(12) + 75, "chat", "", settings, row["revision"], random.Random(1))
    assert store.get("group")["next_at"] == stamp(12) + 135


def test_message_cache_is_scoped_deduplicated_and_bounded(tmp_path):
    store = Store(tmp_path / "db")
    settings = Settings()
    for index in range(60):
        store.note(
            "one", "umo", "test", stamp(12) + index, settings, str(index), "user", str(index)
        )
    store.note("other", "umo2", "test", stamp(12), settings, "1", "user", "private other group")
    store.note("one", "umo", "test", stamp(12), settings, "59", "user", "duplicate")
    messages = store.recent("one", 100, stamp(13))
    assert len(messages) == 50 and messages[0]["text"] == "10" and messages[-1]["text"] == "59"
    store.prune(stamp(12) + 8 * 86400)
    assert store.recent("one", 100, stamp(12) + 8 * 86400) == []


def test_daily_schedule_remains_on_clock_times_after_quota(tmp_path):
    store = Store(tmp_path / "db")
    settings = bind(store, Settings(daily_limit=1))
    rng = random.Random(1)
    store.configure(
        "group", stamp(12), settings, rng, mode="daily", daily_times=["10:00", "15:00", "20:00"]
    )
    assert store.get("group")["next_at"] == stamp(15)
    row, _ = store.reserve("group", stamp(15) + 1, settings, rng)
    assert row is not None
    store.finish("group", stamp(15) + 30, "chat", "", settings, row["revision"], rng)
    assert store.get("group")["next_at"] == stamp(20)
    assert "上限" in store.reserve("group", stamp(20), settings, rng)[1]
    assert store.get("group")["next_at"] == stamp(10, day=21)


def test_daily_rejects_invalid_or_all_quiet_times(tmp_path):
    store = Store(tmp_path / "db")
    settings = bind(store)
    for values in (["25:00"], ["bad"], ["01:00"], []):
        with pytest.raises(ValueError):
            store.configure(
                "group", stamp(12), settings, random.Random(1), mode="daily", daily_times=values
            )
    assert store.get("group")["mode"] == "random"


def test_daily_mode_defaults_are_persisted(tmp_path):
    store = Store(tmp_path / "db")
    settings = Settings.from_config({"mode": "daily", "daily_times": ["20:00"]})
    bind(store, settings)
    assert store.get("group")["next_at"] == stamp(20)
