# 素材来源与分发边界

上游：<https://github.com/Kato-Shoko705/Phoebe-Hub>，仅使用 `data/memes.json` 的
`memes` 数组，不导入 `pending`。参考插件
<https://github.com/wjn1121/astrbot_plugin_phoebe> 用于了解来源结构，没有复制插件代码。

本次检查中，上游 README 未提供图片再分发授权，根目录 `LICENSE` 返回 404。
参考插件的 MIT 许可不能替代图片权利人的授权；该插件 README 也说明图片版权归原作者。
没有发现许可不等于断言任何人侵权，也不能作为公开再分发授权。

仓库仅提交构建代码、测试、文档及官方协议 Schema，不提交上游图片、索引快照、缓存或构建包。
测试图片由 Pillow 在运行时生成。GitHub Actions 不下载上游图片、不上传图片构件、不自动发布。
本地构建是审核工具，不构成下载或使用素材的法律授权。

公开分发前，应逐项确认图片权利人、许可范围、是否允许修改/再分发、署名要求，
保存授权证据，并审核 `provenance.json` 与 `review_queue.json`。语义人工确认不代表版权已确认。
在完成授权前不要移除忽略规则、将输出放进 Git、创建公开 Release 或上传 Actions 构件。
需受控交付时使用你已确认权限和保留策略的私有存储，本项目不自动上传。

官方 Schema 来源与固定提交见 [schemas/README.md](schemas/README.md)。
本项目没有替第三方素材声明开源许可证。
