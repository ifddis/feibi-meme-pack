# 菲比丘比 AstrBot 表情包构建器

为 AstrBot meme_manager 构建本地内容包的 Python 3.12 工具。**本仓库不是 AstrBot 插件，也没有内置第三方图片。**
默认输出 `build/pack/`，不覆盖仓库根目录或已有输出；图片、缓存和输出均被 Git 忽略。
素材来源：[Phoebe-Hub](https://github.com/Kato-Shoko705/Phoebe-Hub)。再分发许可尚未确认，见 [RIGHTS.md](RIGHTS.md)。

## 快速开始：Windows PowerShell / uv

先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Git，在仓库根目录执行。
下列命令同时适用于 PowerShell 和 Linux/macOS shell，不需要激活虚拟环境。

```powershell
uv python install 3.12
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen python scripts/smoke_fixture.py
uv run --frozen python scripts/build_pack.py --limit 20 --output build/first-review --include-review
uv run --frozen python scripts/validate_pack.py build/first-review --require-complete
```

前两条构建检查使用程序生成的图片，不依赖上游，也不包含第三方素材。
最后两条下载前 20 条正式索引记录并生成本地审核包。`--include-review` 会将未知图片放入
`review` 分类；不要把这个分类当作已确认情绪推荐给聊天机器人。

默认构建不带 `--include-review`，仅导出可由文字线索推断的分类，未知记录保留在审核清单。
若没有任何可用图片，构建仍保留审核结果，但 CLI 返回退出码 2，避免空包被当作成功导入。
构建/校验异常返回非零；校验通过不代表有可用图片，也不代表许可或语义已人工确认。
构建器不需要 DeepSeek、QQ、AstrBot 或 GitHub token。

## 输出与协议

```text
build/first-review/
  manifest.json
  memes/<category>/<content_sha256>.<原始格式>
  semantic_metadata.json
  provenance.json
  review_queue.json
  RIGHTS.md
```

实现官方 [协议修订 0.3](https://github.com/anka-afk/astrbot-meme-pack-index/blob/2f173ca5dc0b460d9c6408a4f7f0e9a83371677f/ASTRBOT_MEME_PACK_PROTOCOL_ZH.md)。
Schema 原样固定到 `schemas/`，离线使用 Draft 2020-12 校验。manifest 模式版本为整数 `1`；
语义扩展为 `version: 1`，元数据 `schema_version` 为字符串 `"2.0"`。
包 ID 为 `ifddis.feibi-chibi`，版本可通过 `--version` 指定。

每张导出图片均有一条语义记录：

```text
content_sha256 = SHA256(原始图片字节)
entry_id = SHA256(UTF8(content_sha256 + "\0" + category + "\0" + relative_path))
```

`\0` 表示一个零字节。图片路径为 `memes/<category>/<filename>`，以 `/` 分隔。
校验器除官方 Schema 外，还检查目录层数、分类存在性、预览引用、实际图片格式、
符号链接逃逸、包 ID、内容摘要、记录键和 entry_id；`--require-complete` 额外要求逐图完整覆盖。
基础协议允许部分/没有语义元数据，普通校验保留该兼容性。
未生成 icon/previews，它们在协议中可选。没有添加不存在的 GitHub 内容包来源字段；
构建工具仓库当前不能直接作为已发布内容包导入。

## 语义推断与人工审核

使用原始标题、URL 文件名与 tags；忽略上游仅用于展示的 `static`/`cute` category，
也不把 `featured`、`recommended` 当成情绪。规则位于 `feibi_pack/semantics.py`：

| 分类 | 明确文字线索 |
| --- | --- |
| hissing | 哈气 |
| punching | 乱拳、挥拳、出拳 |
| angry | 生气、愤怒、恼火 |
| cake | 吃蛋糕（单独“蛋糕”不足以推断正在吃） |
| happy | 开心、高兴、欢呼 |
| aggrieved | 委屈、难过、哭泣 |
| shy | 害羞、脸红、不好意思 |
| dancing | 跳舞、摇摆 |
| review | 无明确线索、多种分类冲突或否定表达 |

规则是保守的文字推断，无法保证画面内容准确，没有使用视觉模型或伪造 OCR。
自动 caption 明示推断依据，`caption_status` 保持 `pending`；未知 caption 留空。
同一内容不同来源的元数据先合并，分类冲突进入 review，避免下载顺序决定分类。
哈气等行为不会自动泛化为“生气”。同一图片只导出一次，来源别名保存在 `provenance.json`。

查看 `review_queue.json`、`provenance.json` 及本地原图后，以内容 SHA-256 为键建立覆盖文件：

```json
{
  "此处替换为真实的64位小写内容SHA256": {
    "category": "cake",
    "caption": "人工确认：菲比拿着蛋糕进食，适合表达享用甜点。"
  }
}
```

```powershell
uv run --frozen python scripts/build_pack.py --offline --overrides review.json --output build/reviewed
uv run --frozen python scripts/validate_pack.py build/reviewed --require-complete
```

仅人工覆盖的非 review 记录标记 `done`。覆盖允许使用上表分类，不允许自定义路径；
覆盖不会修改版权状态。`review.json` 请放在本地受控目录，不要包含私人信息。

## 下载、缓存和增量同步

```powershell
# 完整本地构建；默认不导出未知图片
uv run --frozen python scripts/build_pack.py --output build/full
# 重新获取索引，并用 ETag / Last-Modified 条件请求刷新图片
uv run --frozen python scripts/build_pack.py --refresh --output build/refreshed
# 不联网，仅复用完整缓存
uv run --frozen python scripts/build_pack.py --offline --output build/offline
# 指定本地的原始 Phoebe-Hub 索引（对象内必须含 memes 数组）
uv run --frozen python scripts/build_pack.py --index C:/data/memes.json --limit 20 --output build/local
```

默认缓存 `.cache/feibi`，按 URL SHA-256 存储字节和 ETag 等状态。普通运行复用通过摘要检查的缓存，
上游变化需 `--refresh`；离线缓存缺失/损坏明确失败。`--offline` 不支持同时拉取新的上游索引。
索引 `pending` 不导入。不同 URL 并发下载（默认 6，`--workers 1..32`），相同 URL 只下载一次，
内容 SHA-256 去重。整个图库不驻留内存，仅当前并发响应和当前处理图片占用内存。
每个响应上限 25 MB，连接/读取超时为 10/45 秒；连接故障、超时、429 和常见 5xx 最多重试 3 次，
指数退避；404 等永久错误不重试。失败构建不会留下半成品输出，已完成下载缓存可复用。
不支持多个进程同时写同一缓存目录；并行任务应指定不同 `--cache`。

只允许 HTTPS 和显式允许的上游主机，拒绝重定向、外部任意地址、用户信息、异常端口、路径穿越；
不使用标题拼接输出路径。输出文件名使用内容摘要，兼容 Windows；不解码再编码图片，
原样保留 GIF/WebP 动画及 PNG/JPEG 字节。输出路径已存在即失败，应使用新的版本目录，
不会自动删除旧文件或修改 AstrBot 现有配置。缓存目录不应放在输出目录内。

## 开发与 CI

```powershell
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
uv run --frozen python scripts/smoke_fixture.py
```

`uv.lock` 固定依赖，`requirements.txt` 提供非 uv 用户的运行时依赖范围。
GitHub Actions 在 Ubuntu 和 Windows 上执行同样的测试及离线 CLI 构建/校验。
不下载上游图库、不上传素材构件、不配置第三方 API 凭据，不自动公开发布。
测试覆盖协议身份、内容篡改、缓存刷新与损坏、重试、格式/GIF、去重、未知/冲突语义、
路径安全和重复构建。云环境若 uv 默认缓存只读，可设置 `UV_CACHE_DIR` 到可写目录。

## 验证边界与 AstrBot 导入

**协议验证成功 ≠ 已在真实 AstrBot 环境中测试成功。**
这里验证的是官方 Schema 和包文件关联，不连接你的 QQ 官方机器人、DeepSeek 或真实 AstrBot。
真实集成需要你在隔离测试环境中人工完成：

1. 确认图片许可、逐图分类/描述，去掉不适合实际检索的 review 内容。
2. 本地校验目标输出，确认图片数量及 `pending` 状态符合预期。
3. 在 meme_manager 当前版本支持的本地/受控导入入口导入完整包根目录，保持 manifest 与 memes 同级。
4. 检查包 ID、分类显示、GIF 动画、语义检索，再测试 QQ 实际发送。
5. 记录 AstrBot 和 meme_manager 版本、导入方式及结果。未执行这些步骤前，不宣称集成成功。

若最终使用 GitHub 导入，必须先得到图片再分发授权，再在单独审核流程中发布真正的内容包；
导入参数应指向那个已发布包的仓库、ref 和包根目录，不能直接使用当前构建工具仓库。
