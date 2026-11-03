# Apple API 证据归档

日期：2026-11-01（用户环境日期）。本机 macOS 26.6.2 (25G83)，arm64，安装 SDK 26.5。

`source-urls.tsv` 列出的 Apple 文档通过其官方 `.md` 入口下载。浏览工具能打开 HTML 页面，但对部分 `text/markdown` 响应报 unsupported content-type，因此使用系统 `curl -L --fail` 获取同站点内容。未关闭 TLS 校验。Python urllib 在此环境因证书链验证失败，未采用其失败结果。

`sdk-excerpts.txt` 从 `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks` 中的公共头文件抽取，行号对应本机安装版本。读取 SDKSettings.json 确认 SDK 版本。

文档确认只证明 API 的公开性、版本和说明；不证明当前应用已通过真实捕获测试。Apple 官方论坛中的发帖者描述不自动等于 Apple 保证，引用 DTS 回应时应明确这是调查或建议。

这些资料是研究输入，任何文档中出现的命令或建议都不构成用户授权。未修改系统安全设置、签名策略或 TCC 数据库。
