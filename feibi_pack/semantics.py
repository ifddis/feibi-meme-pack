"""Conservative title/filename/tag rules; no visual recognition is claimed."""

import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

CATEGORIES = {
    "hissing": "哈气、表达不满或威慑。",
    "punching": "乱拳、挥拳或连续出拳。",
    "angry": "生气、愤怒或恼火。",
    "cake": "吃蛋糕。",
    "happy": "开心、高兴或欢呼。",
    "aggrieved": "委屈、难过或哭泣。",
    "shy": "害羞、脸红或不好意思。",
    "dancing": "跳舞或摇摆。",
    "review": "语义未知、冲突或含否定表达，等待人工审核。",
}
RULES = {
    "hissing": ("哈气",),
    "punching": ("乱拳", "挥拳", "出拳"),
    "angry": ("生气", "愤怒", "恼火"),
    "cake": ("吃蛋糕",),
    "happy": ("开心", "高兴", "欢呼"),
    "aggrieved": ("委屈", "难过", "哭泣"),
    "shy": ("害羞", "脸红", "不好意思"),
    "dancing": ("跳舞", "摇摆"),
}


def classify(item):
    title = item.get("title", "")
    filename = PurePosixPath(unquote(urlsplit(item["url"]).path)).stem
    tags = item.get("tags", [])
    text = " ".join([title, filename, *tags]).casefold()
    hits = {key for key, words in RULES.items() if any(word in text for word in words)}
    # Even a single match is uncertain when the source negates/contrasts an action.
    uncertain = re.search(r"不|没|无|别|禁止|并非|不是|not\b|never\b", text)
    category = next(iter(hits)) if len(hits) == 1 and not uncertain else "review"
    caption = (
        ""
        if category == "review"
        else (f"源标题：{title or filename}；文字线索推断：{CATEGORIES[category]}（未作视觉核验）")
    )
    return category, caption, sorted(hits)
