# 验证记录

记录日期：2026-10-20（Asia/Shanghai）。环境：Linux，Python 3.12.14，uv 0.12.23。

## 可安装内容包发布（当前变更）

维护者确认上游图片再分发授权后，根目录已添加真正的 `manifest.json`、`memes/` 和
`semantic_metadata.json`，不再只有构建工具。

- 名称语义规则扩展，涵盖哭哭/呜呜、干饭/炫面、小拳拳、扭扭、不好意思、比心等原始名称。
- 当前本地测试：78 项通过；Ruff 及格式检查通过。
- 全量索引 1,139 条，实际发布 675 张不同内容图片、55 个分类；443 张有效图片的名称仍含糊，留待审核。
- 3 个源 URL 返回 404，另有 1 个文件无法识别为支持的图片格式；均记录并排除，没有假装下载成功。
- 675 条语义记录均通过官方 Schema、内容摘要、条目身份、分类路径和完整覆盖校验。
- 图片原字节合计 363,510,352 字节（约 347 MiB），未重编码 GIF 或静态图片。
- 直接执行当前 `anka-afk/astrbot_plugin_meme_manager` 提交
  `b96d6bedecca6d0bef27b70261fd6f787116ee49` 的真实目录校验函数
  `validate_pack_directory(..., context="GitHub 包目录")`，根目录包通过。
  这是独立运行其协议层函数，不是启动真实 AstrBot，也不是 QQ 消息发送测试。
- 新发布在 Windows/Ubuntu CI 中增加根目录内容包完整校验，最终结果以本发布 PR 的检查为准。

完整发布计数见 `release_summary.json`，来源见 `provenance.json`，未发布图片见
`review_queue.json`，同步错误见 `download_failures.json`。
名称描述标为 done 表示已按名称生成文本，不代表逐图视觉人工核验。

## 初版构建器验证（历史记录）

## 已验证

- `uv sync --frozen` 安装成功；依赖通过 `uv.lock` 固定。
- `uv run --frozen pytest -q`：50 项通过。
- Ruff 静态检查及格式检查通过。
- `scripts/smoke_fixture.py`：使用运行时生成的双帧 GIF，实际执行构建及完整协议校验成功。
- 默认上游索引路径：20 条记录的本地审核构建及完整语义覆盖校验成功；
  缓存离线重建成功。这 20 条文字线索不足，全部留在 review/pending。
- 另选上游明确文字线索的 5 条记录，涵盖哈气、乱拳、生气、开心、跳舞，
  本地构建和完整协议校验成功，包含真实 GIF。描述仍待视觉核验。
- 本地输出、索引快照和缓存均未加入提交。

校验包括官方 manifest/semantic JSON Schema、真实文件、目录、图片格式、内容 SHA-256
及 `content_sha256 + NUL + category + NUL + relative_path` 对应的条目身份。

## GitHub Actions 双平台验证

修复测试读取中文 JSON 时未显式指定 UTF-8 的 Windows 编码问题后，
[Actions 运行 39301951615](https://github.com/ifddis/feibi-meme-pack/actions/runs/39301951615)
在 Ubuntu 与 Windows 上均通过，包括 Python 安装、冻结依赖安装、Ruff、pytest、
以及默认 PowerShell 下的实际 CLI 离线构建和完整协议校验。
该运行对应实现提交 `787da833cd645cc11ec0b68011cfd946c067a67c`。

## 尚未验证

- 没有连接真实 AstrBot、meme_manager、QQ 或 DeepSeek，不能宣称集成成功。
- 没有逐图视觉审核或 OCR。全量索引同步和维护者授权确认已在上方当前发布记录中补充。

## 上游示例的额外诊断

对协议仓库固定提交 `2f173ca5dc0b460d9c6408a4f7f0e9a83371677f` 的
`examples/semantic/optional-semantic-demo` 运行本工具校验时，Pillow 报告
`broken PNG file (bad header checksum in b'IDAT')`。
独立使用 `zlib.crc32` 复算 PNG 块也确认 IDAT CRC 不匹配，IHDR/IEND CRC 匹配。
这是该外部占位图片自身的完整性问题，不是本项目生成包的失败。
本工具保留严格图片校验，没有关闭校验和或修改上游样本。
