<h1><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/hero-dark.svg">
  <img src="assets/readme/hero.svg" width="100%" alt="OPPO AI Pin Course Companion">
</picture></h1>

面向大学生的 Codex 课程助手。上课时用心力球记录，课后让 Agent 帮你找回讲过的内容、结合教材做笔记，并整理考试、作业和实验要求。

<p align="center"><img src="assets/readme/product-white.png" width="480" alt="OPPO AI Pin 白底产品图"></p>

<p align="center">Local MCP + Skills · Python 3.10+ · 非 OPPO 官方插件</p>

<h2><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/section-overview-dark.svg">
  <img src="assets/readme/section-overview.svg" width="760" alt="课程里的三件事">
</picture></h2>

### 01 / 维护课程资料

**你可以说：“把操作系统的教材改成这个文件，这个目录是本学期课件。”**

插件集中维护每门课的课程名、别名、学期、教师、上课时间、资料目录和备注；可指定主要教材、课件和实验指导书。默认打开可视化管理界面，支持编辑、保存和索引更新请求。其他技能从同一份台账找到资料，不用每次重新告诉 Agent 文件位置。

### 02 / 回顾一节课

**你可以说：“看看今天有哪些课堂记录，把第二、三段合并成操作系统笔记。”**

每次先检查全时记和随口记，列出新增、变化及还没处理的记录，并给出课程匹配建议。**你选定记录、确认课程后才总结**；一节课录成多段时可以合并。

Agent 结合对应课本与课件生成可离线打开的 HTML：梳理概念、课堂例子、必要公式和步骤，区分老师当堂讲的内容与教材补充。关键依据附原文、章节或页码，并在笔记内跳转；识别不清或来源冲突会标为待核实，不补造内容。

```text
20261016-操作系统原理-1.2&1.3 操作系统的分类及发展.html
```

### 03 / 整理教学通知

**你可以说：“老师最近提了哪些作业和考试要求？更新到课程信息文档里。”**

检查历史记录和飞书已有事项，按课程整理考试时间、地点、形式与范围，作业内容、提交方式和 DDL，以及实验、报告和评分要求。每项保留来源时间与原话；同学转述单独标记，日期没说清就保留不确定性。

重复提及的事项合并来源；延期、改范围保留变更历史。你在飞书写的备注和确认不会被整篇覆盖。

<h2><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/section-start-dark.svg">
  <img src="assets/readme/section-start.svg" width="760" alt="开始使用">
</picture></h2>

需要 Python 3.10+、支持本地插件与子 Agent 的 Codex 环境，以及你自行授权的 OPPO AI Pin MCP。公开仓库只声明本地 MCP；远程服务的地址与登录方式请从产品官方入口取得。

1. 克隆仓库，通过宿主支持的插件导入方式加载根目录。需要 ZIP 时运行 `python scripts/package_plugin.py`。
2. 连接自己的 OPPO AI Pin MCP，确认可调用 `recall_memory` 与 `recall_note`。
3. 调用本地课程管理，首次登记课程和资料目录。

```text
使用 $oppo-ai-pin-course-manager 管理我的课程资料。
使用 $oppo-ai-pin-class-review 列出课堂记录，先让我选择。
使用 $oppo-ai-pin-course-info 整理课程关键信息。
```

### 换账号或换电脑

插件有三个独立部分：**账号中的私有插件条目、本机安装与课程数据、外部服务授权**。账号私有版本属于创建它的账号或工作区，换号后需要在新账号重新导入或安装；GitHub 源码本身不绑定某个 ChatGPT 账号。也可从仓库安装本地版，宿主的账号与工作区规则仍适用。

同一 Windows 用户下，本地课程数据按数据目录保存，不会随 ChatGPT 账号自动切换或隔离；换电脑时需要自行迁移课程目录与集中数据。OPPO AI Pin、飞书的授权单独配置，不能假定旧账号的连接会自动继承。请勿复制或分享登录凭据。

### 飞书配置

仅课程信息管理需要飞书。按照[飞书官方 CLI 安装与使用指南](https://www.feishu.cn/content/article/7623291503305083853)完成安装与授权；[官方仓库中文配置说明](https://github.com/larksuite/cli/blob/main/README.zh.md#安装与快速开始)提供具体步骤。安装配套的 `lark-doc`、`lark-shared` 等 Skills 后，按官方说明重新加载 Agent。

首次调用时创建或关联你的课程信息文档。没有配置飞书时，课程资料管理和本地笔记仍可独立使用；插件不会假装已同步云端。

<h2><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/section-customize-dark.svg">
  <img src="assets/readme/section-customize.svg" width="760" alt="选择你的笔记风格">
</picture></h2>

**不强制安装 whisper-html 或 whisper-illustration。** 你可以换成自己的 HTML、笔记或插画技能，例如：

```text
这门课程的笔记使用我的 my-course-notes 技能，插画省略。
```

- 默认优先使用已安装的 `whisper-html` 与 `whisper-illustration`。
- 缺少 HTML 技能时，Agent 自主生成有目录、引用跳转和移动端布局的离线 HTML。
- 缺少插画技能或生图能力时，省略装饰插画；需要解释关系时，可使用简单原创 SVG/HTML 图解。
- 如果模板的强制依赖不能满足，则整体切换到自主生成，不会为了遵循模板阻塞课程笔记。

无论采用哪种方式，课程确认、原文核对、来源标注和文件命名规则都保留。这些外部技能不会打包进本仓库。

<h2><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/section-privacy-dark.svg">
  <img src="assets/readme/section-privacy.svg" width="760" alt="数据与边界">
</picture></h2>

- **没有音频源文件**：只处理接口返回的转写、摘要与时间信息，不支持录音播放或下载。
- **索引由指定子 Agent 更新**：固定 `gpt-6-luna / high`，不可用时报告失败。界面保存更新请求，回到聊天调用课程管理后执行。课堂回顾发现索引距成功更新时间达到 72 小时，会派发更新。
- **个人连接独立配置**：仓库不含作者的远程 MCP 地址、OAuth 信息、课程数据或私人飞书链接。
- **本地存储不等于离线分析**：课程内容会进入所用 AI 会话，课程信息管理还会写入你指定的飞书文档。

集中数据默认位于 Windows 的 `%LOCALAPPDATA%/OPPO-AI-Pin-Campus`，其他系统使用 `~/Documents/OPPO-AI-Pin-Campus`；可用 `OPPO_AI_PIN_DATA` 更换。课程目录下的 `OPPO-AI-Pin/` 保存所选记录元数据和笔记。请勿提交这些个人数据。

<h2><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/readme/section-development-dark.svg">
  <img src="assets/readme/section-development.svg" width="760" alt="开发与许可">
</picture></h2>

运行时只使用 Python 标准库。`runtime/` 为本地 MCP 与存储，`skills/` 为三个工作流，`ui/` 为课程管理界面。

```bash
python -m unittest discover -s tests -v
python runtime/app.py open
python scripts/package_plugin.py
```

隔离资料上的索引、分页、去重、确认导出、来源变化保护和 MCP 读取已通过测试。真实课堂笔记与个人飞书写入需在首次配置后验证。

代码与原创 README SVG 使用 [MIT License](LICENSE)。OPPO 品牌、产品照片及图标的第三方权利不包含在 MIT 授权中；本页白底图由用户提供的照片经 AI 编辑背景生成。详见 [ASSET-NOTICE.md](ASSET-NOTICE.md)。

[提交问题或建议](https://github.com/ZiChen-Whisper/oppo-ai-pin-course-companion/issues)时，请勿附带私人转写、访问凭据或文档链接。
