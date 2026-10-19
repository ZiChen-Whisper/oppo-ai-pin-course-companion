# 课程管理界面规范

当前阶段：存量资料工作台整理；按用户标注调整组件变体、状态排布和滚动，保留 A 结构。

北极星：找到课程资料、看懂分类依据、用选择代替格式化文本输入。

## 已确认的结构

- 桌面：左侧学期/课程导航，主区为资料工作台；“课程资料 / 课程设置”页签分离高频资料处理与低频课程编辑。
- 文件使用 Data Grid，按用途、文件格式、来源与确认状态区分。选择文件后才展示详情；批量选择后出现 Action Bar。
- 手机：顶部课程选择器，文件列表在名称下呈现用途、格式、来源与状态，避免依赖横向滚动发现核心信息。
- 不加指标卡、海报标题或无关插画。保留 OPPO AI Pin 环形图标，沿用 HeroUI 系统字体与组件语法，浅灰工作区、白色表格及输入框，保留主题强调色。

## 组件与责任

- React 19、HeroUI React / Styles 3.2.6；Data Grid / Action Bar 由本机共享库提供，通过目录链接使用，不复制共享源码。
- 官方 TextField、Select / ListBox、SearchField、TimeField、Checkbox、Chip、Modal、Tabs、Button、Spinner 负责控件行为和外观。
- 消费项目只维护课程业务、状态与布局；公共组件修复回共享库，禁止修改 node_modules。
- `frontend/` 为开发源代码，`ui/` 为可离线加载的构建产物；插件运行不需要 Node.js。

## 数据与状态

- 中央 registry 是课程与人工分类的唯一来源。用途和格式分离，规则建议不可宣称为模型通读结论；人工确认优先并保留备注。
- 主要教材为单独角色；更换主要教材只清除其他资料的 primary，不清除其用途或备注。
- 搜索/筛选变化清除选择；批量操作只覆盖可见的选中资料。接口核对课程、文件集合及 revision，失败保留输入。
- 课程设置有未保存状态与离开提醒；旧格式时间附加说明保留。目录选择器不可用时提供粘贴路径入口。
- 目录变更后隐藏不匹配旧索引。索引更新仍由 gpt-6-luna / high 子 Agent 执行；界面只保存请求并展示真实任务状态。
- data_root 使用 MCP 返回的实际路径，不能由另一个终端的环境变量推断为另一份总表。

## 组件默认外观（0.3.4）

以本机 HeroUI 固定快照的 stories、组件 CSS 和实际运行预览为依据；已对照 Data Grid usage 示例。移除对 Select.Trigger、Checkbox.Control、Data Grid 表头/单元格、Tabs 内部、Action Bar 内部及 Modal 尺寸的消费端覆盖；不使用 !important、不重定义组件色彩 Token。

课程导航使用 ListBox + Avatar + Label / Description，课程图标从 12 个预设中选择并保存；别名使用 TagGroup / Tag 自带移除按钮；错误与保存结果使用 Alert，索引排队/运行状态使用 Chip + Description；未保存提醒使用 AlertDialog；资料判断使用 Card；折叠区使用 Accordion；空态使用共享 EmptyState；面包屑和链接使用 Breadcrumbs / Link；课程设置使用 Form。Tabs 使用 primary 变体和内容宽度，文本通过公开 className 使用 foreground 保证对比度；表格不限制高度，纵向滚动由页面负责。品牌图片使用主题圆角。页面容器、网格、间距由业务 CSS 负责，交互组件保留组件库默认皮肤及状态。

Modal 通过 Container 的 size / scroll 参数设置，不用 CSS 强制改宽。新增课程表单的保存/取消放在 Modal.Footer，借助 form 属性关联 Form，不随表单内容滚动；错误也在底部操作区呈现。共享库没有已导出的 Sidebar；侧栏采用语义 aside 布局与现有 ListBox 组合，不伪称使用 Sidebar 组件。

## 验证与限制

原有存储、索引及认证逻辑未改。本次在隔离副本验证课程设置、别名添加/移除和保存读回，检查资料详情、筛选和批量操作入口；真实课程数据不写入验收内容。已检查桌面和手机的默认、空结果、选中、批量编辑、详情、选项展开、设置、错误、未保存及新增弹窗状态；新增弹窗完成操作已通过实际创建和读回验证。截图保留在任务 outputs/design/，不发布个人课程截图。

构建检查仅验证 JS 语法和导入，不等于严格 TypeScript 类型检查。原生目录选择弹窗体验仍需用户在本机操作确认。
