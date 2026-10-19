# 菲比丘比表情包构建器

适用于 AstrBot meme_manager 的内容包构建工具。图源：[Phoebe-Hub](https://github.com/Kato-Shoko705/Phoebe-Hub)。

**本仓库暂不包含第三方表情包图片。** Phoebe-Hub 公开展示不意味着全部素材可以再分发；上传到公开 GitHub 前，请确认素材许可。

## 本地构建（Windows PowerShell）

```powershell
uv python install 3.12
uv venv --python 3.12
uv pip install -r requirements.txt
uv run --no-sync python scripts/build_pack.py --limit 20
```

确认图片归类、版权及格式后，可省略 `--limit 20` 构建完整图库。生成的 `manifest.json`、`semantic_metadata.json` 和 `memes/` 必须与此 README 同级，才能通过 AstrBot 表情包管理器的 GitHub 导入校验。

导入参数：仓库 `ifddis/feibi-meme-pack`；分支 `main`；目录 `.`。

本项目不是 AstrBot Python 插件，只有完成图片构建且获准发布的仓库才是可导入的内容包。
