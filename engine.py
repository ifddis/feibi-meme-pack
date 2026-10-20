"""Scheduling policy and transactional storage, independent of AstrBot."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    mode: str = "random"
    min_minutes: int = 60
    max_minutes: int = 180
    daily_times: tuple[str, ...] = ("10:00", "15:00", "20:00")
    daily_limit: int = 3
    active_start: int = 9
    active_end: int = 23
    timezone: str = "Asia/Shanghai"
    activity_minutes: int = 0
    failure_limit: int = 3
    context_messages: int = 20
    chat_weight: int = 50
    meme_weight: int = 30
    question_weight: int = 20
    provider_id: str = ""
    meme_pack_dir: str = ""
    meme_categories: tuple[str, ...] = ("happy", "cute", "affection", "dancing")
    persona_prompt: str = "你是菲比丘比群聊助手，语气自然可爱，简短，不冒充真实群成员。"

    @classmethod
    def from_config(cls, config):
        defaults = cls()
        values = {k: config.get(k, getattr(defaults, k)) for k in cls.__dataclass_fields__}
        for key in (
            "min_minutes",
            "max_minutes",
            "daily_limit",
            "active_start",
            "active_end",
            "activity_minutes",
            "failure_limit",
            "context_messages",
            "chat_weight",
            "meme_weight",
            "question_weight",
        ):
            if isinstance(values[key], bool):
                raise ValueError(f"{key} 必须是整数")
            values[key] = int(values[key])
        if not isinstance(values["meme_categories"], (list, tuple)) or not all(
            isinstance(v, str) for v in values["meme_categories"]
        ):
            raise ValueError("meme_categories 必须是分类名称列表")
        for key in ("mode", "timezone", "provider_id", "meme_pack_dir", "persona_prompt"):
            if not isinstance(values[key], str):
                raise ValueError(f"{key} 必须是字符串")
        values["meme_categories"] = tuple(values["meme_categories"])
        values["daily_times"] = normalize_times(values["daily_times"])
        if values["mode"] == "fixed":
            values["max_minutes"] = values["min_minutes"]
        obj = cls(**values)
        validate_interval(obj.mode, obj.min_minutes, obj.max_minutes)
        if not (1 <= obj.daily_limit <= 100 and 1 <= obj.failure_limit <= 10):
            raise ValueError("每日上限须为1..100，连续失败上限须为1..10")
        if not (0 <= obj.active_start <= 23 and 0 <= obj.active_end <= 24):
            raise ValueError("允许时段起点为0..23，终点为0..24")
        if not (0 <= obj.activity_minutes <= 10080 and 0 <= obj.context_messages <= 50):
            raise ValueError("活跃窗口须为0..10080分钟，上下文须为0..50条")
        weights = (obj.chat_weight, obj.meme_weight, obj.question_weight)
        if any(w < 0 or w > 1000 for w in weights) or not sum(weights):
            raise ValueError("权重须为0..1000且至少一个大于0")
        ZoneInfo(obj.timezone)
        return obj

    @property
    def tz(self):
        return ZoneInfo(self.timezone)


def validate_interval(mode, low, high):
    if mode not in ("random", "fixed", "daily") or not 1 <= low <= high <= 1440:
        raise ValueError("间隔须为1..1440分钟且最小值不大于最大值")
    if mode == "fixed" and low != high:
        raise ValueError("固定间隔的两个值必须相同")


def delay_seconds(mode, low, high, rng):
    validate_interval(mode, low, high)
    return low * 60 if mode == "fixed" else rng.randint(low * 60, high * 60)


def normalize_times(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 24:
        raise ValueError("每日时刻须为1..24个HH:MM字符串")
    result = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("时刻必须是HH:MM字符串")
        try:
            hour, minute = map(int, value.split(":"))
        except (ValueError, TypeError) as exc:
            raise ValueError("时刻格式须为HH:MM") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("时刻须在00:00～23:59之间")
        result.append(f"{hour:02d}:{minute:02d}")
    return tuple(sorted(set(result)))


def next_due(row, now, settings, rng):
    if row["mode"] != "daily":
        return next_open(now + delay_seconds(row["mode"], row["low"], row["high"], rng), settings)
    times = normalize_times(json.loads(row["daily_times"]))
    local = datetime.fromtimestamp(now, settings.tz)
    for day_offset in range(3):
        day = local + timedelta(days=day_offset)
        for value in times:
            hour, minute = map(int, value.split(":"))
            candidate = day.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()
            if candidate > now and is_open(candidate, settings):
                return candidate
    raise ValueError("每日定时点均不在允许发送时段内")


def quota_resume(row, now, settings, rng):
    if row["mode"] != "daily":
        return next_day(now, settings)
    local = datetime.fromtimestamp(now, settings.tz)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return next_due(row, midnight.timestamp() - 1, settings, rng)


def is_open(now, settings):
    hour = datetime.fromtimestamp(now, settings.tz).hour
    start, end = settings.active_start, settings.active_end
    if start == end:
        return True
    return start <= hour < end if start < end else hour >= start or hour < end


def next_open(now, settings):
    if is_open(now, settings):
        return now
    local = datetime.fromtimestamp(now, settings.tz)
    target = local.replace(hour=settings.active_start, minute=0, second=0, microsecond=0)
    if target.timestamp() <= now:
        target += timedelta(days=1)
    return target.timestamp()


def next_day(now, settings):
    local = datetime.fromtimestamp(now, settings.tz)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=1, microsecond=0)
    return next_open(midnight.timestamp(), settings)


def choose_action(settings, has_memes, rng):
    weights = {"chat": settings.chat_weight, "question": settings.question_weight}
    if has_memes:
        weights["meme"] = settings.meme_weight
    choices = [(action, weight) for action, weight in weights.items() if weight > 0]
    if not choices:
        raise ValueError("没有可执行行为：请配置可用表情目录或启用文字行为权重")
    return rng.choices([a for a, _ in choices], weights=[w for _, w in choices], k=1)[0]


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS groups (
                    scope TEXT PRIMARY KEY, umo TEXT NOT NULL, platform TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
                    mode TEXT NOT NULL, low INTEGER NOT NULL, high INTEGER NOT NULL,
                    daily_times TEXT NOT NULL DEFAULT '["10:00","15:00","20:00"]',
                    revision INTEGER NOT NULL DEFAULT 0, last_human REAL NOT NULL,
                    day TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
                    returned INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
                    last_at REAL NOT NULL DEFAULT 0, last_action TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, scope TEXT NOT NULL, message_id TEXT NOT NULL,
                    at REAL NOT NULL, sender TEXT NOT NULL, text TEXT NOT NULL,
                    UNIQUE(scope, message_id)
                );
                CREATE INDEX IF NOT EXISTS messages_scope ON messages(scope,id);
            """)

            columns = {row[1] for row in db.execute("PRAGMA table_info(groups)")}
            if "daily_times" not in columns:
                db.execute(
                    'ALTER TABLE groups ADD COLUMN daily_times TEXT NOT NULL DEFAULT \'["10:00","15:00","20:00"]\''
                )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def note(self, scope, umo, platform, now, settings, message_id="", sender="", text=""):
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO groups(scope,umo,platform,mode,low,high,last_human,daily_times) VALUES(?,?,?,?,?,?,?,?)",
                (
                    scope,
                    umo,
                    platform,
                    settings.mode,
                    settings.min_minutes,
                    settings.max_minutes,
                    now,
                    json.dumps(settings.daily_times),
                ),
            )
            db.execute("UPDATE groups SET last_human=? WHERE scope=?", (now, scope))
            if text and message_id:
                db.execute(
                    "INSERT OR IGNORE INTO messages(scope,message_id,at,sender,text) VALUES(?,?,?,?,?)",
                    (scope, message_id, now, sender[:80], text[:1000]),
                )
                db.execute(
                    "DELETE FROM messages WHERE scope=? AND id NOT IN (SELECT id FROM messages WHERE scope=? ORDER BY id DESC LIMIT 50)",
                    (scope, scope),
                )
            db.execute("DELETE FROM messages WHERE at<?", (now - 7 * 86400,))

    def get(self, scope):
        with self.connection() as db:
            row = db.execute("SELECT * FROM groups WHERE scope=?", (scope,)).fetchone()
            return dict(row) if row else None

    def due(self, now):
        with self.connection() as db:
            return [
                r[0]
                for r in db.execute(
                    "SELECT scope FROM groups WHERE enabled=1 AND next_at<=?", (now,)
                )
            ]

    def configure(
        self,
        scope,
        now,
        settings,
        rng,
        *,
        enabled=None,
        mode=None,
        low=None,
        high=None,
        umo=None,
        daily_times=None,
    ):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = dict(db.execute("SELECT * FROM groups WHERE scope=?", (scope,)).fetchone())
            if mode is not None:
                low = row["low"] if low is None else low
                high = row["high"] if high is None else high
                validate_interval(mode, low, high)
                row.update(mode=mode, low=low, high=high)
            if daily_times is not None:
                row["daily_times"] = json.dumps(normalize_times(daily_times))
            if row["mode"] == "daily":
                next_due(row, now, settings, rng)
            if enabled is not None:
                row["enabled"] = int(enabled)
                if enabled:
                    row["failures"] = 0
                    row["last_error"] = ""
            if umo is not None:
                row["umo"] = umo
            row["next_at"] = next_due(row, now, settings, rng) if row["enabled"] else 0
            db.execute(
                "UPDATE groups SET enabled=?,mode=?,low=?,high=?,umo=?,next_at=?,revision=revision+1,failures=?,last_error=?,daily_times=? WHERE scope=?",
                (
                    row["enabled"],
                    row["mode"],
                    row["low"],
                    row["high"],
                    row["umo"],
                    row["next_at"],
                    row["failures"],
                    row["last_error"],
                    row["daily_times"],
                    scope,
                ),
            )

    def defer(self, scope, now, reason):
        with self.connection() as db:
            db.execute(
                "UPDATE groups SET next_at=?,last_error=? WHERE scope=? AND enabled=1",
                (now, reason, scope),
            )

    def reserve(self, scope, now, settings, rng, manual=False):
        """Charge one attempt before side effects; concurrent workers share the quota."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM groups WHERE scope=?", (scope,)).fetchone()
            if row is None:
                return None, "会话尚未绑定"
            row = dict(row)
            if not manual and (not row["enabled"] or row["next_at"] > now):
                return None, "未到执行时间或已关闭"
            try:
                future = next_due(row, now, settings, rng)
            except ValueError as exc:
                db.execute(
                    "UPDATE groups SET enabled=0,last_error=? WHERE scope=?", (str(exc), scope)
                )
                return None, str(exc)
            if not is_open(now, settings):
                db.execute(
                    "UPDATE groups SET next_at=? WHERE scope=?",
                    ((future if row["mode"] == "daily" else next_open(now, settings)), scope),
                )
                return None, "当前处于安静时段"
            day = datetime.fromtimestamp(now, settings.tz).date().isoformat()
            attempts = row["attempts"] if row["day"] == day else 0
            returned = row["returned"] if row["day"] == day else 0
            if attempts >= settings.daily_limit:
                db.execute(
                    "UPDATE groups SET next_at=? WHERE scope=?",
                    (quota_resume(row, now, settings, rng), scope),
                )
                return None, "已达今日触发尝试上限"
            if (
                settings.activity_minutes
                and now - row["last_human"] > settings.activity_minutes * 60
            ):
                db.execute(
                    "UPDATE groups SET next_at=? WHERE scope=?",
                    (future, scope),
                )
                return None, "最近没有收到群成员消息"
            next_at = future
            db.execute(
                "UPDATE groups SET day=?,attempts=?,returned=?,next_at=?,last_at=?,last_error='' WHERE scope=?",
                (day, attempts + 1, returned, next_at, now, scope),
            )
            return row, ""

    def still_current(self, scope, revision, manual):
        row = self.get(scope)
        return row is not None and row["revision"] == revision and (manual or bool(row["enabled"]))

    def finish(self, scope, now, action, error, settings, revision, rng):
        with self.connection() as db:
            row = db.execute("SELECT * FROM groups WHERE scope=?", (scope,)).fetchone()
            if row is None:
                return
            current = row["revision"] == revision
            failures = (row["failures"] + 1 if error else 0) if current else row["failures"]
            paused = current and failures >= settings.failure_limit
            next_at = row["next_at"]
            if row["revision"] == revision and row["enabled"] and not paused:
                next_at = next_due(row, now, settings, rng)
            db.execute(
                "UPDATE groups SET last_action=?,last_at=?,last_error=?,failures=?,returned=returned+?,enabled=CASE WHEN ? THEN 0 ELSE enabled END,next_at=? WHERE scope=?",
                (action, now, error, failures, 0 if error else 1, paused, next_at, scope),
            )

    def recent(self, scope, count, now):
        with self.connection() as db:
            rows = db.execute(
                "SELECT at,sender,text FROM messages WHERE scope=? AND at>=? ORDER BY id DESC LIMIT ?",
                (scope, now - 7 * 86400, count),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]

    def prune(self, now):
        with self.connection() as db:
            db.execute("DELETE FROM messages WHERE at<?", (now - 7 * 86400,))
