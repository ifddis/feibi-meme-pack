# 验证记录

记录日期：2026-10-20（Asia/Shanghai）。环境：Linux，Python 3.12.14，uv 0.12.23。

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

## 尚未验证

- Windows PowerShell 实机执行：当前机器没有 Windows；已配置 Windows/Ubuntu Actions 矩阵，
  需以远端实际运行结果为准。所有命令和路径处理均按跨平台设计。
- 没有连接真实 AstrBot、meme_manager、QQ 或 DeepSeek，不能宣称集成成功。
- 没有逐图视觉审核、OCR、全图库构建或再分发授权确认。

## 上游示例的额外诊断

对协议仓库固定提交 `2f173ca5dc0b460d9c6408a4f7f0e9a83371677f` 的
`examples/semantic/optional-semantic-demo` 运行本工具校验时，Pillow 报告
`broken PNG file (bad header checksum in b'IDAT')`。
独立使用 `zlib.crc32` 复算 PNG 块也确认 IDAT CRC 不匹配，IHDR/IEND CRC 匹配。
这是该外部占位图片自身的完整性问题，不是本项目生成包的失败。
本工具保留严格图片校验，没有关闭校验和或修改上游样本。
