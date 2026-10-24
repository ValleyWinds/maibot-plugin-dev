# MaiBot 插件 WebUI 页面扩展

> **校对基线：SDK 2.14.0 + MaiBot Host 1.3.9**（2026-10-17 逐行对照源码复核；2026-10-24 抽查与 SDK 2.16.0 / Host 1.3.15 源码一致，未发现漂移）

本文件已按当前源码逐项核对：权威声明模型 `src/plugin_runtime/webui_schema.py`、页面网关
`src/webui/routers/plugin/webui_extensions.py`、上传存储 `src/plugin_runtime/upload_store.py`、
加载器入口 `src/plugin_runtime/runner/runner_main.py` 的 `load_webui_extension`，
以及前端 `dashboard/src/lib/plugin-webui.ts` / `plugin-custom-page.ts` / `routes/plugin-webui.tsx` /
`components/layout/Layout.tsx`。行为结论均可用 `WebUIExtension.model_validate` 与
`load_webui_extension` 复现；本文的实测条目都注明了复现方式。

> 官方文档：https://docs.mai-mai.org/plugin/webui-pages
> ⚠️ 官方 `docs/zh/plugin/webui-pages.md` 的示例仍是 `schema_version: 1`，且能力名写的是
> `file_upload` / `interactive_controls`、上传组件写在声明式页 `content` 里——**全部与 Host 源码不符**。
> 以本文与源码为准。

## 机制总览

插件在自己目录下放一个 `webui.json`（与 `_manifest.json` 同级），向 WebUI 声明页面；
页面由宿主统一渲染，不需要打包前端、不注入 HTML/JS/CSS。页面只能调用**本插件**的
`@API` 组件，Host 代理认证、参数校验、结果体积校验与调用预算。

两种页面模型：

| 模式 | 载体 | 能力 |
|------|------|------|
| `declarative`（默认，可省略 `mode`） | `content` 里的白名单组件树 | 展示数据、表单、按钮触发 action |
| `custom`（必填 `mode: "custom"`） | `entry` 指向的插件内 `.html`，由 loader 读入 `document` | 整页自定义 HTML，经沙箱 iframe + `window.maibot` 桥调用 API |

```
webui.json
   │  load_webui_extension(plugin_dir)   ← Runner 工作线程读取，注册与热重载同一条校验路径
   ▼
WebUIExtension（StrictModel：extra="forbid", strict=True）
   ▼
GET  /api/webui/plugins/runtime/webui            列出全部扩展（cookie: maibot_session）
POST /api/webui/plugins/runtime/webui/{plugin}/{page}/{queries|actions}/{name}
POST /api/webui/plugins/runtime/webui/{plugin}/{page}/uploads/{name}
GET  /api/webui/plugins/runtime/webui/{plugin}/{page}/document
POST /api/webui/plugins/runtime/webui/{plugin}/reload
```

路由前缀来源：`webui_extensions` 的 router 无自身 prefix，由
`src/webui/routers/plugin/__init__.py` 以 `prefix="/plugins"` 挂载，再由
`src/webui/routes.py` 的 `APIRouter(prefix="/api/webui")` include。

### schema_version 规则

字段 `schema_version`，类型 `Literal[2]`，默认 2（`src/plugin_runtime/webui_schema.py`
的 `WebUIExtension`）。**实际起拦截作用的只有 before 校验器一层，`Literal[2]` 字段层不可达**——
任何非法取值都在 before 层被拒，永远不会出现 `Input should be 2 [type=literal_error]`。

拦截逻辑在 `WebUIExtension.validate_size`（mode="before"）：`value.get("schema_version", 2) != 2` →
`WebUI 协议已升级为 2；请按 docs/plugin-webui.md 迁移声明`。逐情形实测行为（pydantic 2.14，
`WebUIExtension.model_validate` / 关键字构造直接复现）：

- 传 `1`、`3`、字符串 `"2"`、布尔 `true`、`null`：均报上面那条迁移文案（before 层拦截）。
- 省略该字段：`value.get(...)` 缺省回落 2，放行，模型得到整数 `2`。
- 传浮点 `2.0`：**放行**——比较按值相等进行，数值等于 2 的任何值都通过，字段层归一存储为整数 `2`。
- 关键字直接构造（`WebUIExtension(schema_version=1, ...)`）：pydantic v2 同样把构造参数交给
  before 校验器，报同一条迁移文案，**不存在绕过路径**。
- 唯一能绕过 before 校验器的是 `model_construct()`：它跳过全部校验（字段层也不运行，所以也不报错），
  只会得到一个带非法值、未经校验的模型实例，不代表任何可观测的错误文案。

⚠️ 文案指向的 `docs/plugin-webui.md` **不存在**（全仓库只有 `docs/*/plugin/webui-pages.md`），
作者按此文案找不到迁移说明。旧的 manifest 页面扩展协议（v2 之前）的声明一律会被拒，
不存在兼容转换（源码注释：不转换任何已移除的组件或字段）。

### webui.json 顶层字段

| 字段 | 类型 / 默认 | 约束 |
|------|------------|------|
| `schema_version` | `Literal[2]`，默认 2 | 必须等于 2 |
| `required_capabilities` | `List[Literal[...]]`，默认 `[]` | 最多 4 项；取值见下节 |
| `workspace_title` | `Optional[Label]`，默认 None | 1-80 字符；**任一页 `placement == "workspace"` 时必填** |
| `pages` | `List[WebUIPage]` | 1-20 页；`WebUIPage` 是 `Union[DeclarativePage, CustomPage]`，以 `mode` 为 discriminator |

页面类型判别靠 `mode`：`DeclarativePage.mode = Literal["declarative"]` 默认 `"declarative"`；
`CustomPage.mode = Literal["custom"]` **无默认值，必须显式写**。loader 会给省略 `mode` 的页面对象
自动补 `{"mode": "declarative", **page}`，所以缺省 mode 即声明式页面（实测：无 `mode` 时
`model_validate` 与 loader 均按 declarative 处理）。

顶层约束（`WebUIExtension.validate_pages`）：页面 id 必须唯一 → `页面 ID 重复`；
有 workspace 页但缺 `workspace_title` → `顶部工作区必须声明 workspace_title`；
所有 custom 页面 `document` 的 UTF-8 字节总和不得超过 8 MiB → `自定义页面产物总量超过 8 MiB`。
模型是 StrictModel，未声明字段一律 `Extra inputs are not permitted`。

注册体积：`validate_json(metadata, max_bytes=MAX_REGISTRATION_BYTES, max_depth=32)`，
其中 metadata 是**剔除每页 `document` 键后**的整体声明，`MAX_REGISTRATION_BYTES = 524288`（512 KiB）。
即 HTML 单独计量，不与组件/API 元数据争用注册配额。

## required_capabilities

声明在 `webui.json` 顶层，用于**前端功能兼容性检查**（前端拿响应里的 `capabilities`
清单比对，不认识的标 `compatibility_error`），与 manifest `capabilities` 的 RPC 授权是两回事。
页面声明本身不需要写进 manifest 的 `capabilities`；上传领取等 SDK 接口才需要各自的 manifest 能力授权。

| 取值 | 何时必须声明 | 不声明会看到什么（逐字文案） |
|------|-------------|------------------------------|
| `declarative_basic` | **任何校验器都不强制**。`WEBUI_CAPABILITIES` 只是清单枚举，声明式页面的存在本身不要求它 | 无（未强制；实测声明式页面在 `required_capabilities: []` 下校验通过） |
| `custom_pages` | 存在 `mode == "custom"` 的页面 | `custom 页面需要声明 required_capabilities: custom_pages` |
| `image_upload` | custom 页的 `uploads` 非空 | `图片上传需要声明 required_capabilities: image_upload` |
| `structured_arguments` | 任一页面的 queries + actions 中，任一 `Parameter.type` 为 `"array"` 或 `"object"`。**对 declarative 与 custom 都生效** | `结构化参数需要声明 required_capabilities: structured_arguments` |

⚠️ 声明式页面的 `actions` 只能用**标量参数**：`DeclarativeBinding.validate_bindings` 有一条更早触发的
独立校验——任一 `parameters` 的类型为 array/object 时，无论是否声明 `structured_arguments`，都报
`预置表单仅接受标量参数；结构化交互请使用 custom 页面`（实测确认）。因此 `structured_arguments`
实际上只对 custom 页面有用。

## 声明式页面（DeclarativePage）

### 字段

| 字段 | 类型 / 默认 | 约束 |
|------|------------|------|
| `mode` | `Literal["declarative"]`，默认 `"declarative"` | 可省略 |
| `id` | `Identifier` 必填 | `^[a-zA-Z][a-zA-Z0-9_-]{0,63}$`，字母开头，总长 1-64 |
| `title` | `Label` 必填 | 1-80 字符 |
| `description` | `Text`，默认 `""` | 最长 4000 |
| `placement` | `Literal["sidebar","workspace"]`，默认 `"sidebar"` | 决定进侧边栏还是顶部工作区 |
| `icon` | `Literal["puzzle","chart","settings","database","list"]`，默认 `"puzzle"` | 前端 `extensionIcons` 只映射这五个 |
| `queries` | `Dict[Identifier, DeclarativeBinding]`，默认 `{}` | 最多 10 个 |
| `actions` | `Dict[Identifier, DeclarativeBinding]`，默认 `{}` | 最多 20 个 |
| `content` | `List[WebUINode]` | **至少 1 个、最多 50 个顶层组件** |
| `auto_refresh` | `bool`，默认 False | 前端在执行 action 成功后刷新查询 |
| `poll_interval_seconds` | `int`，默认 0 | `ge=0, le=60`；**1 和 2 非法** → `轮询间隔至少3秒；0表示关闭`，有效值为 0 或 3-60 |

`DeclarativeBinding` 继承 `APIBinding` 并新增 `arguments`：

| 字段 | 类型 / 默认 | 约束 |
|------|------------|------|
| `api` | `str` 必填 | `^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$`；**短名**，Host 解析为 `{plugin_id}.{api}` |
| `version` | `str`，默认 `"1"` | 1-40 字符 |
| `parameters` | `Dict[Identifier, Parameter]`，默认 `{}` | 最多 30 个 |
| `confirmation` | `Optional[Label]`，默认 None | action 确认弹窗文案；`variant == "danger"` 的按钮必填 |
| `arguments` | `Dict[Identifier, DataReference]`，默认 `{}` | 最多 30 个；键必须是已声明的 `parameters` |

`queries` 不得声明 `arguments` 或 `confirmation` → `queries 只接受表单参数，不声明 arguments 或 confirmation`。

### Parameter（参数声明）

| 字段 | 类型 / 默认 | 约束 |
|------|------------|------|
| `type` | `Literal["string","integer","number","boolean","array","object"]` 必填 | — |
| `required` | `bool`，默认 False | — |
| `max_length` | `int`，默认 4000 | ge=1，le=65536 |
| `minimum` / `maximum` | `Optional[float]`，默认 None | 不能 minimum > maximum |
| `choices` | `List[Scalar]`，默认 `[]` | 最多 100；array/object 参数禁用 |
| `items` | `Optional[Parameter]` | **双向绑定：`type == "array"` 必须声明、非 array 不得声明**（`validate_constraints` 判据 `(type == "array") != (items is not None)` 即报错） |
| `properties` | `Dict[Identifier, Parameter]`，默认 `{}` | 最多 30；**仅 `type == "object"` 可声明** |
| `max_items` | `int`，默认 1000 | ge=1，le=1000 |

参数校验文案（`Parameter.validate_constraints`）：`参数 minimum 不能大于 maximum`、
`array 参数必须声明 items；其它类型不能声明 items`、`仅 object 参数可以声明 properties`、
`结构化参数不能使用标量 choices`、`参数 choices 必须符合声明类型和范围`。

调用期参数校验（`APIBinding.validate_args`，HTTP 422）：`未声明的参数: {name}`、
`缺少参数: {name}`、`参数不符合声明: {name}`。`object` 只接受已声明属性，`number` 不接受布尔值，
`integer` 必须是 `type(value) is int`。

### DataReference（数据引用）

| 字段 | 类型 / 默认 | 约束 |
|------|------------|------|
| `scope` | `Literal["query","selection"]`，默认 `"query"` | **不存在 `"item"` scope**（实测：`scope="item"` 被拒） |
| `source` | `Identifier` 必填 | 必须存在于 `queries`（scope=query）或行选择名（scope=selection） |
| `field` | `str`，默认 `""` | `^(?:[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*)?$`，最长 200；留空取查询完整返回值 |

引用校验 → `未声明的数据上下文: {scope}.{source}`。行选择名由 table 的 `selection` 声明，
同一页内不得重复 → `行选择名称重复`。

### 页面级约束

- 嵌套深度 ≤ 8 层、组件总数 ≤ 200 → `页面超过 8 层或 200 个组件`（实测边界：8 层通过、9 层报错；196 个节点通过、208 个报错）
- `dialog` 必须在 `content` 顶层且 `name` 唯一 → `dialog 必须位于 content 顶层且名称唯一`（实测嵌套 dialog 报此条）
- `table.selection` 名称不得重复 → `行选择名称重复`
- `input` / `date` / `select` / `switch` / `pagination` 的 `name` 不得重复 → `重复输入字段: {name}`
- `button.action` 必须在 `actions` 中 → `未声明的操作: {action}`
- `variant == "danger"` 时对应 action 必须声明 `confirmation` → `danger 操作必须声明 confirmation`
- `table.detail` 必须指向已声明 dialog，且必须同时声明 `selection` → `未声明的详情弹窗: {detail}` / `table.detail 必须同时声明 selection`
- `select` 的默认值必须属于 `options` → `select 默认值必须属于 options`

### 运行时语义（前端 `routes/plugin-webui.tsx`）

- 进页后**顺序**执行所有 `queries`（遵守网关并发上限），整份快照成功后才替换页面数据
- 表单值来自 `content` 里的 input/date/select/switch 初始值；可用 `navigate(pageId, state)`
  把已声明的标量输入写进 URL `?state=`（`readPluginPageState`，上限 4 KiB）
- **action 参数的两条来源通道**（运行实例实测，2026-10-17）：
  ① **表单同名自动绑定**——`parameters` 里声明的参数名若与 `content` 中交互控件（input/switch/select/date）
  的 `name` 相同，前端执行 action 时自动把该控件的**当前值**填入 args，**不需要**任何 `arguments` 声明；
  用户没碰过的控件按初始值填入（如 switch value:false 原样发送）。这正是上文最小示例里
  `input name="limit"` + `save_limit` 参数 `limit` 能工作的机制。
  ② `arguments` 的 `DataReference` 绑定——把 **query 结果字段或行选择**注入参数（`{source:"summary",
  field:"count"}` / `{scope:"selection", source:"rows", ...}`），用于"用选中行的数据触发操作"场景。
  值缺失且参数 required 时抛 `Missing action argument: {name}`；非标量抛 `Action argument must be scalar: {name}`。
  两条通道互不冲突；`arguments` 显式声明的参数走 DataReference，其余参数走同名表单。
- 执行 action 时若 `busy` 则忽略；`confirmation` 非空时先弹确认，确认期间冻结当次参数
- `poll_interval_seconds >= 3` 时按秒轮询，`busy` 时跳过本轮

## 自定义页面（CustomPage）

### 字段

| 字段 | 类型 / 默认 | 约束 |
|------|------------|------|
| `mode` | `Literal["custom"]` 必填 | 无默认值，必须显式写 |
| `id` / `title` / `description` / `placement` / `icon` | 同声明式页 | 同上 |
| `entry` | `str` 必填 | 1-200 字符；指向插件内的相对 `.html` 文件 |
| `layout` | `Literal["document","viewport"]`，默认 `"document"` | `document` 由前端 ResizeObserver 量高；`viewport` 撑满视口 |
| `queries` | `Dict[Identifier, APIBinding]`，默认 `{}` | 最多 10 个。注意是 `APIBinding` 而非 `DeclarativeBinding`，**没有 `arguments`** |
| `actions` | `Dict[Identifier, APIBinding]`，默认 `{}` | 最多 20 个；可用 array/object 结构化参数（仍需 `structured_arguments` 能力） |
| `uploads` | `Dict[Identifier, ImageUpload]`，默认 `{}` | 最多 10 个 |
| `document` | `str` | **作者不应在 webui.json 里内联**：loader 遇到含 `document` 键的 custom 页报 `custom 页面必须通过 entry 读取 HTML，不能内联 document`；它由 loader 从 entry 文件读入后注入 |
| `document_revision` | property | `document` 的 sha256 hexdigest，序列化时输出给前端做变更检测 |

`ImageUpload` = `{action: Identifier, image_max_edge: Optional[int]}`，`image_max_edge` 范围 1-8192。
`queries` 不得声明 `confirmation` → `queries 不声明 confirmation`。
`document` strip 后为空或 UTF-8 超 2 MiB → `自定义页面必须非空且不超过 2 MiB`。

### 产物要求（entry 路径规则，loader 逐条检查）

1. 必须相对、不得绝对、不得含 `..`、后缀必须 `.html` → `entry 必须是插件内的相对 HTML 路径`
   （实测 `../outside.html`、`C:/outside.html`、`/outside.html`、`webui/config.toml` 均报此条）
2. 路径任一部分是 symlink 或 junction → `entry 路径不能包含链接`
3. 解析后必须仍在插件目录内 → `entry 超出插件目录`
4. 必须是普通文件 → `entry 必须是普通 HTML 文件`
5. 单文件 UTF-8 超 2 MiB → `自定义页面超过 2 MiB`
6. 累计超 8 MiB → `自定义页面总量超过 8 MiB`

`webui.json` 自身：必须位于插件目录内且不能是符号链接 → `webui.json 必须位于插件目录内，且不能是符号链接`；
文件本体 ≤ 128 KiB → `webui.json 超过 128 KiB`。没有 `webui.json` 的插件不注册 WebUI 扩展（loader 返回 None）。

### 沙箱与桥（前端 `lib/plugin-custom-page.ts` + `components/plugin-custom-page.tsx`）

- 页面放进 `sandbox="allow-scripts"` 的 iframe（srcdoc 不透明源），CSP 前置注入：
  `default-src 'none'; script-src 'unsafe-inline' blob:; style-src 'unsafe-inline'; img-src data: blob:;
  font-src data:; media-src data: blob:; connect-src 'none'; frame-src 'none'; worker-src 'none';
  object-src 'none'; base-uri 'none'; form-action 'none'`——**没有同源权限、不能直连 API/网络、
  不能表单提交、不能嵌套 frame 或 worker**
- 宿主通过 MessageChannel 注入 `window.maibot`：`context`（主题/语言/样式）、`page`（id/layout/state）、
  `query(name, args)` / `action(name, args)` / `upload(name, file, args, {signal, onProgress})` /
  `navigate(pageId, state)`；`api.ready` 是 Promise
- 桥上限：同页并发 2 个请求、消息令牌 200 突发/20 每秒、iframe 高度 ≤ 30000 px、
  连接 10 秒未就绪即停；`layout === 'document'` 才上报高度
- 上传的 `upload_id` 由宿主签发，页面传了会被拒（`Upload IDs are issued by the host`）

## 内容组件目录（声明式页）

公共字段：`label: Optional[Label]`、`when: Optional[VisibilityCondition]`（条件渲染）；
交互组件另有 `disabled_when` / `disabled_reason`。
`VisibilityCondition` = `{reference: DataReference, operator: "truthy"|"empty"|"not_empty"|"equals" (默认 truthy), expected: Scalar}`；
只有 `equals` 可以声明 `expected` → `只有 equals 条件可以声明 expected`。

### 容器（有 children）

| type | 关键字段 |
|------|---------|
| `stack` | `children: List[WebUINode]`，默认 `[]`，最多 50 |
| `card` | 同 stack |
| `grid` | 继承 stack；`columns: int` 必填，1-4 |
| `tabs` | 继承 stack；children 非空且**每个子节点必须有 label** |
| `collapsible` | 继承 stack；`label` 必填（覆写为必填）；`default_open` 默认 False |
| `dialog` | 继承 stack；`name: Identifier`、`label: Label`；必须位于 content 顶层且 name 唯一 |

### 展示

| type | 关键字段 |
|------|---------|
| `text` | `value: Union[Text, int, float, bool, DataReference, None]` 默认 None；`format: "plain"\|"log"` 默认 `"plain"` |
| `stat` | `value` 同上 |
| `progress` | `value: Union[float(0-100), DataReference]` 必填 |
| `image` | `value: DataReference` 必填；前端只接受 ≤24 KB 的 `data:image/(jpeg\|png\|webp);base64,...` |
| `table` | `value: DataReference` 必填；`columns: List[{field, label}]` 必填 1-20 项；`selection` / `detail` 可选。绑定对象数组，前端每页固定 50 行 |
| `chart` | `value: DataReference` 必填；`chart_type: "line"\|"bar"` 默认 `"line"`；`x` / `y` 必填。绑定对象数组，最多 2000 行 |
| `pagination` | `value: DataReference` 必填；`name: Identifier` 必填（计入重复输入检查）。绑定 `{page, pages, total}` 对象 |

### 表单

| type | 关键字段 |
|------|---------|
| `input` | `name: Identifier` 必填；`value: Union[Text, int, float, None]` 默认 None（数字默认值渲染数字输入框） |
| `date` | `name` 必填；`value: Optional[Text]` 默认 None |
| `switch` | `name` 必填；`value: bool` 默认 False |
| `select` | `name` 必填；`value: Optional[str]` 默认 None；`options: List[{label, value}]` 必填 1-100 项，value 1-200 字符 |
| `button` | `label: Label` 必填；`action: Identifier` 必填；`variant: "primary"\|"danger"\|"muted"` 默认 `"primary"` |

### 已移除的组件

`repeat` / `multi_select` / `checkbox` / `gallery` / `upload` 一律不接受，不做兼容转换：
实测报 `Input tag 'repeat' found using 'type' does not match any of the expected tags:
'stack', 'card', 'grid', 'tabs', 'collapsible', 'dialog', 'text', 'stat', 'progress', 'image',
'table', 'chart', 'pagination', 'input', 'date', 'switch', 'select', 'button'`。

### 最小可用示例

`plugins/my_plugin/webui.json`：

```json
{
  "schema_version": 2,
  "workspace_title": "我的统计",
  "pages": [
    {
      "id": "overview",
      "title": "统计概览",
      "placement": "workspace",
      "icon": "chart",
      "queries": { "summary": { "api": "summary", "version": "1" } },
      "actions": {
        "reset": {
          "api": "reset_counter",
          "version": "1",
          "confirmation": "确认清零？只影响插件内存计数。"
        }
      },
      "content": [
        {
          "type": "grid",
          "columns": 2,
          "children": [
            { "type": "stat", "label": "计数", "value": { "source": "summary", "field": "count" } },
            { "type": "text", "label": "说明", "value": "数据只来自本插件 API。" }
          ]
        },
        { "type": "button", "label": "清零", "action": "reset", "variant": "danger" }
      ]
    },
    {
      "id": "tune",
      "title": "参数调整",
      "placement": "sidebar",
      "icon": "settings",
      "actions": {
        "save": {
          "api": "save_limit",
          "version": "1",
          "parameters": { "limit": { "type": "integer", "required": true, "minimum": 1, "maximum": 1000 } }
        }
      },
      "content": [
        {
          "type": "card",
          "label": "统计范围",
          "children": [
            { "type": "input", "name": "limit", "label": "上限", "value": 100 },
            { "type": "button", "label": "保存", "action": "save" }
          ]
        }
      ]
    }
  ]
}
```

对应的 `@API`（短名，不要带插件 id 前缀；Host 解析为 `{plugin_id}.{name}`）：

```python
from maibot_sdk import API, MaiBotPlugin


class MyPlugin(MaiBotPlugin):
    @API("summary", description="页面只读数据", version="1")
    async def summary(self) -> dict:
        return {"count": 42}

    @API("save_limit", description="保存统计上限", version="1")
    async def save_limit(self, limit: int) -> dict:
        return {"limit": limit}
```

⚠️ 绑定的 API 必须是**静态注册**的：网关用 `api_registry.get_api(plugin_id, binding.api, version=...)`
查表，条目不存在或 `dynamic` 为真时报 `页面绑定的静态 API 已下线` / `上传操作的静态API已下线`。
绑定不要求 `public=True`。

## 配额与限制

| 项 | 上限 | 超限表现 |
|----|------|---------|
| `webui.json` 文件本体 | 128 KiB（`MAX_DECLARATION_BYTES`） | `webui.json 超过 128 KiB` |
| 注册元数据（剔除 document 后） | 512 KiB、深 32 层（`MAX_REGISTRATION_BYTES`） | `JSON 超过 32 层或 20000 个元素` 等 |
| 单页 custom document | 2 MiB（`MAX_CUSTOM_DOCUMENT_BYTES`） | `自定义页面超过 2 MiB` / `自定义页面必须非空且不超过 2 MiB` |
| custom document 总量 | 8 MiB（`MAX_DOCUMENTS_BYTES`） | `自定义页面总量超过 8 MiB` |
| 页面数 | 20 | `每插件最多 20 个页面`（loader 前置检查，先于 schema_version 校验：`schema_version=1` 且 21 页时先报这条）；模型层为 `List should have at most 20 items` |
| `required_capabilities` 数 | 4 | `List should have at most 4 items` |
| 每页 queries / actions / uploads | 10 / 20 / 10 | pydantic `too_long` |
| 每 binding 的 `parameters` | 30 | pydantic `too_long` |
| `DeclarativeBinding.arguments` | 30 | pydantic `too_long` |
| content 顶层组件 | 50 | pydantic `too_long` |
| 容器 children | 50 | pydantic `too_long` |
| 嵌套深度 / 组件总数 | 8 层 / 200 个 | `页面超过 8 层或 200 个组件` |
| `table.columns` / `select.options` | 20 / 100 | min_length/max_length |
| `Parameter.choices` / `properties` / `max_items` | 100 / 30 / 1000 | Field 约束 |
| 单次调用 args | JSON ≤ 64 KiB（`MAX_ARGUMENT_BYTES`）、≤ 30 项 | `JSON 超过 64 KiB`；`args` 超 30 项 `too_long` |
| 调用返回值 | 512 KiB（`_validate_result` 用 `validate_json(max_bytes=524288)`） | 502，详情为 validate_json 文案 |
| 插件调用超时 | RPC `timeout_ms=10000`，外层 `asyncio.wait_for(timeout=11)` | 504 `插件调用超时；操作可能仍在执行，请核实结果后再试` |
| 进行中请求并发 | 每插件 2（`_inflight`） | 429 `该插件已有两个进行中的 WebUI 请求` |
| 上传接收超时 | `asyncio.timeout(120)` 秒 | 408 `上传请求超时，请核实接收结果`；前端 XHR `timeout = 120000` |
| 上传文件大小 | 20 MiB（`MAX_BYTES`），路由层 limit = 20 MiB + 64 KiB | 两种结局并存：请求体整体越过 `WebUILimitedRoute` 的 limit → 413 `请求超过大小限制`；文件略超 20 MiB 但请求体仍在 limit 内 → 422 `文件为空或超过 20 MiB`（详见上传链路③） |
| 上传像素 | 4000 万（`MAX_PIXELS`） | `图片超过 4000 万像素` |
| 上传暂存配额 | 未领取 32 个总数 / 单插件 8 个 | 429 `未领取图片过多，请领取或等待暂存文件过期` |
| 上传并发配额 | 单插件 2、全局 4 | 429 `上传处理中，请稍后再试` |
| 上传 token 有效期 | 3600 秒 | `上传凭证不存在、已过期或已领取` |
| 前端轮询 | `poll_interval_seconds` 有效值 0 或 3-60 | 声明 1/2 → `轮询间隔至少3秒；0表示关闭` |

`validate_json` 通用上限：默认 `max_depth=12`（调用处可覆写，注册时用 32）、元素数 20000，
报错文案 `JSON 超过 {n} 层或 20000 个元素` / `JSON 超过 20000 个元素` /
`JSON 对象的键必须为字符串` / `仅接受 JSON 数据` / `JSON 超过 {n} KiB`。

## 图片上传链路

分四段，任一段缺失都会在中途失败。

### ① manifest 能力声明（授权）

`_manifest.json` 的 `capabilities` 数组里声明 `webui.claim_upload`。
宿主在 `src/plugin_runtime/capabilities/registry.py` 的 `register_capability_impls` 里注册实现
（`cap_service.register_capability("webui.claim_upload", claim_upload)`）。授权校验方法
`check_capability` **定义在 `src/plugin_runtime/host/authorization.py`**，未声明时由它返回
`插件 {plugin_id} 未获授权能力: webui.claim_upload`；`src/plugin_runtime/host/capability_service.py`
的 `handle_capability_request` 只是调用方——先 `self._authorization.check_capability(...)`，
拒绝时报 `E_CAPABILITY_DENIED`；「未注册的能力: {capability}」分支则在 capability_service 本身
（实现表查不到时）。
manifest 的 `capabilities` 只做去重与非空校验（`src/plugin_runtime/runner/manifest_validator.py`
的 `_validate_capabilities`），不校验取值白名单——**写错能力名不会拒载，死在运行时调用**。
SDK 侧 `maibot_sdk/capabilities/webui.py` 的 docstring 标注需要 host >= 1.3.6。

### ② webui.json 声明（页面侧）

custom 页面用 `uploads: Dict[Identifier, ImageUpload]`，被绑定的 action 必须声明一个名为
`upload_id`、类型 `string`、`required: true` 的参数，否则
`图片上传必须绑定接受必填字符串 upload_id 的 action`（实测：action 无参数 / `upload_id` 非必填 /
`upload_id` 为 integer / action 名不存在，四种情况均报此条）。同时页面存在 `uploads` 时必须声明
`image_upload` 能力。

### ③ 上传端点

`POST /api/webui/plugins/runtime/webui/{plugin_id}/{page_id}/uploads/{name}`，multipart 表单：
字段 `file`（必填）、`args`（str，默认 `"{}"`，JSON 文本）、`confirmed`（bool，默认 False）。

- `upload_id` 不允许由调用方提供，显式传入报 422 `upload_id 由宿主签发`；
  宿主在校验业务参数时用占位值 `"0" * 64` 顶替，拿到 token 后才写回 `request.args`
- action 声明了 `confirmation` 而 `confirmed=False` → 409 `该操作需要确认`
- 前端在调用端点前先经 `parseCustomPageRequest` 校验：`name` 必须在页面 `uploads` 里、
  参数名符合 Identifier 规则、文件类型限 `image/jpeg|png|webp`；声明了 `image_max_edge`
  时先用 canvas 预处理（超限缩放 + JPEG 重编码），单文件上限 20 MiB
- 大小超限有**两条路径、两种结局并存**：
  - `WebUILimitedRoute` 对上传路由的 limit 是 `MAX_BYTES + MAX_ARGUMENT_BYTES`（Content-Length 或实际接收字节越界）
    → **413** `请求超过大小限制`；
  - 文件本体略超 20 MiB 但整个请求体仍在上述 limit 内时，路由层放行，`upload_webui_file` 里
    `await file.read(MAX_BYTES + 1)` 读到截断字节后交给 `_stage_upload` → `validate_image`
    （`upload_store.py`）抛 `ValueError("文件为空或超过 20 MiB")`，被 `except (ValueError, OSError)` 捕获
    → **422**，详情即该文案

### ④ claim_upload（插件侧）

宿主实现 `claim_upload(plugin_id, capability, args)`（`src/plugin_runtime/upload_store.py`），
从 `args.get("upload_id", "")` 取 token，返回 `{"success": True, "upload": upload}`；
内层 `store.claim` 返回 `{"path": str, "sha256": str, "upload_id": token}`。
文件被移动到插件数据目录下 `data/plugins/{plugin_id}/uploads/{token}{后缀}`。

SDK 封装：`await ctx.webui.claim_upload(upload_id: str) -> dict[str, Any]`，
能力名 `"webui.claim_upload"`，result_key 为 `"upload"`（`maibot_sdk/context.py`）。
注意解包后拿到的是 `upload` 字典本身。

```python
from maibot_sdk import API, MaiBotPlugin


class MyPlugin(MaiBotPlugin):
    @API("add_image", version="1")
    async def add_image(self, upload_id: str, identity: str) -> dict:
        claimed = await self.ctx.webui.claim_upload(upload_id)
        # claimed["path"] / claimed["sha256"] / claimed["upload_id"]
        return {"path": claimed["path"], "identity": identity}
```

图片格式与配额（`validate_image`，均已实测）：

- 仅 JPEG、PNG、静态 WebP；动画（GIF/多帧 WebP）→ `仅支持静态图片`
- 文件为空或超 20 MiB → `文件为空或超过 20 MiB`
- 超 4000 万像素 → `图片超过 4000 万像素`；解码炸弹 → `图片解码尺寸超限`
- 后缀映射 JPEG→`.jpg`、PNG→`.png`、WEBP→`.webp`
- token 为 `secrets.token_hex(32)`，有效期 3600 秒；**一次性**，重复/过期/不存在 →
  `上传凭证不存在、已过期或已领取`
- 暂存上限：未领取 32 个总数 / 单插件 8 个。单文件 20 MiB 下，暂存总量最多 640 MiB、单插件最多 160 MiB
- 并发：`UploadBudget` 即时配额，单插件 2、全局 4，不排队
- 清理：`_cleanup` 删过期未领取文件与过期记录；后台任务每 60 秒跑一次 `cleanup_uploads`，
  失败记 `logger.exception("插件 WebUI 暂存图片清理失败")`
- 取消安全：取消请求不会终止工作线程，等解码/写盘结束再释放接收配额

## 端点清单

全部需要 `maibot_session` cookie（`require_plugin_token`）。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/webui/plugins/runtime/webui` | 列出全部扩展。返回 `{"success": True, "schema_version": 2, "capabilities": WEBUI_CAPABILITIES, "extensions": [...]}`，每项含 `plugin_id`、`workspace_title`、`required_capabilities`、`pages`。`_serialize_extensions` 给**所有页面**都输出 `document_revision` 字段（`page.document_revision if page.mode == "custom" else None`，declarative 页固定为 `null`），`document` 被 exclude |
| POST | `/api/webui/plugins/runtime/webui/{plugin_id}/reload` | 热重载该插件 custom 页面 HTML。插件未注册 404 `插件 WebUI 已下线`；校验失败 422 |
| GET | `/api/webui/plugins/runtime/webui/{plugin_id}/{page_id}/document` | 取 custom 页 HTML。返回 `{"success", "document", "revision"}`，带 `Cache-Control: no-store` 与 `X-Content-Type-Options: nosniff`（只返回 JSON，避免插件 HTML 被当同源页面执行）。页面不存在 404 `自定义页面不存在` |
| POST | `/api/webui/plugins/runtime/webui/{plugin_id}/{page_id}/{kind}/{name}` | 调用 query 或 action，`kind` 为 `queries`/`actions`。body 为 `{args, confirmed}`。成功返回 `{"success": True, "result": ...}` |
| POST | `/api/webui/plugins/runtime/webui/{plugin_id}/{page_id}/uploads/{name}` | 上传，见上节 |

调用期错误码：404 `插件 WebUI 已下线` / `插件页面不存在` / `页面绑定的静态 API 已下线`；
403 `页面未开放该查询或操作` / `页面未声明该上传操作`；409 `该操作需要确认` /
`插件 WebUI 归属冲突: {plugin_id}`；422 参数类错误详情为 `str(exc)`；502 `插件 API 执行失败，
请查看插件日志` / `插件运行时调用失败，请查看插件日志`；504 超时；413 `请求超过大小限制`；
400 `无效Content-Length`。

热重载的完整路径：HTTP 层 → `PluginSupervisor.reload_webui_documents` →
Runner `_handle_reload_webui_documents`（`src/plugin_runtime/runner/runner_main.py`）重新
`load_webui_extension`，只重读页面文件，不卸载插件 → `replace_webui_documents` 重新校验整份快照
（id/entry 集合必须一致，否则 `页面声明已改变或重复，请重载插件`）后一次性替换。
前端拿到新 `document_revision` 与旧值不一致时报 `Page changed; refresh the plugin registry`。

⚠️ 声明无效时**整个插件注册失败**：`runner_main.py` 的 `_register_plugin` 捕获
`(OSError, ValueError)`，记 `插件 {plugin_id} WebUI 声明无效: {exc}` 并返回 False。

## placement 与可见性（前端 `components/layout/Layout.tsx` + `lib/plugin-webui.ts`）

- `placement: "sidebar"`：只在 `sidebarWorkspaceMode === 'settings'` 时出现在侧边栏菜单，
  归入标题为 `workspace_title ?? plugin_id` 的分组；分组标题 literalTitle，图标取自
  `extensionIcons[page.icon]`（只映射 puzzle/chart/settings/database/list），
  路径 `/extensions/{pluginId}/{pageId}`
- `placement: "workspace"`：进入顶部工作区，`extensionWorkspace(pluginId) = "plugin:{pluginId}"`；
  当前路径命中某 workspace 页时 `workspaceMode` 切到该插件工作区，侧边栏只显示该插件页面，内置菜单让位
- 顶部工作区标签顺序由 `orderedWorkspaceExtensions` 决定，按 `preferences.workspaceOrder`
  （缺省回落 `order`）排序，未设置者排在末尾并按 `plugin_id` localeCompare；
  只有含至少一个 workspace 页的扩展才进入该列表
- `workspace_title` 缺失时前端回落显示 `plugin_id`，但宿主侧校验要求有 workspace 页时必须声明
- 用户可在管理页隐藏整个插件（`preferences.hidden`）并调整顺序
- 移动端没有桌面工作区顶栏，`mobileMenuSections` 列出插件的全部页面而不按 placement 过滤

## 与首页卡片（@HomeCard）的关系

两套完全独立的机制，不要混用：

| | `webui.json` 页面扩展 | `@HomeCard` 首页卡片 |
|---|---|---|
| 载体 | 插件目录下的 `webui.json` + custom 页的 `.html` 产物 | `plugin.py` 里的组件装饰器 |
| 声明处 | 数据文件，与 Python 代码分离 | Python 代码 |
| 渲染位置 | 侧边栏分组 / 顶部工作区，路由 `/extensions/{plugin}/{page}` | WebUI 首页 |
| 交互 | 表单、按钮、行选择、弹窗、分页、图表；custom 页可跑整页 HTML | 只读展示 + `link_url`/`link_label` 跳转 |
| 后端 | 绑定本插件 `@API`，Host 代理认证与参数校验 | 无后端调用，内容是装饰期写死的数据 |
| 安全边界 | custom 页 HTML 在沙箱 iframe 内执行，只能经桥调自己的 API | WebUI **不执行**插件提供的 HTML/JS，内容按声明式数据渲染并清洗（`src/webui/routers/plugin/runtime_routes.py` 的 `_sanitize_home_card_*`） |
| 适用场景 | 需要界面、需要读写操作的插件面板 | 首页上一眼的状态摘要 |

首页卡片的字段与上限（SDK `maibot_sdk/types.py` 的 `HomeCardComponentInfo` +
`runtime_routes.py`）：`width` 限 `small/medium/large/wide/full`；内容块类型限
`markdown/text/stat/key_value/list/actions`；文本 ≤ 4000、短文本 ≤ 120、块数 ≤ 20；
链接只允许 `http://`/`https://`/`mailto:`/`/` 前缀。与 `webui.json` 之间没有共享字段或能力。

## 排障速查

1. **注册即失败，插件整个加载不了**：先看日志里 `插件 {id} WebUI 声明无效: {exc}`，
   文案就是 `webui_schema.py` 抛出的那一条；`exc` 是 pydantic 错误时用 `/tmp/check_errors.py`
   同款手法复现：构造同样的 dict，`WebUIExtension.model_validate` 后读 `str(e)`
2. **页面在菜单里消失**：`placement` 是否 workspace（只在匹配工作区显示）、是否被用户在管理页隐藏、
   前端是否标了 `compatibility_error`（`required_capabilities` 里有前端不认识的取值）
3. **调用 403**：`kind`/`name` 不在该页的 `queries`/`actions` 里 → `页面未开放该查询或操作`；
   上传名不在 `uploads` 里 → `页面未声明该上传操作`
4. **调用 404 静态 API 已下线**：`api` 短名拼错、`version` 不匹配，或该 API 是动态注册的
5. **改 HTML 不生效**：custom 页要调 `POST .../reload`，且 `entry` 指向的文件内容变了才会更新
   `document_revision`；前端 revision 不一致时要求刷新注册表
6. **429 并发**：同插件同时只能有 2 个进行中的 WebUI 请求；前端查询是顺序执行的，
   自建并发脚本时注意这个上限
7. **上传 422 `upload_id 由宿主签发`**：前端或脚本自己传了 `upload_id`，删掉它

## 已知问题（源码现状）

- 主程序自带插件 `plugins/hello_world_plugin/webui.json` 的 `schema_version` 是 `1`，
  在当前 v2 模型下校验失败，报 `WebUI 协议已升级为 2；请按 docs/plugin-webui.md 迁移声明`；
  该文件还使用了 v2 已移除的 `repeat` 组件与 `scope: "item"`（`DataReference.scope` 只接受
  query/selection）。这是全仓库唯一的 `webui.json` 实例，即自带示例本身不符合 v2 协议，
  与「不转换任何已移除的组件或字段」的注释一致。
- ⚠️ **坏声明会导致插件整个注册失败，不只是页面丢失**（Host 1.3.9 运行时实测链路）：
  `runner_main._register_plugin` 中 `load_webui_extension` 抛出的 `ValidationError` 是 `ValueError`
  子类，被它的 `except (OSError, ValueError)` 接住 → 记 `插件 {id} WebUI 声明无效: …` 并 `return False`；
  上层依次是 `PluginSupervisor` 的「`插件 {id} 重载失败: 插件初始化失败（已恢复旧版本）`」→
  `PluginRuntimeManager.apply_plugin_config` 抛 `RuntimeError` → WebUI
  `POST /api/webui/plugins/config/{plugin_id}/toggle` 返回 **409**，插件列表变成
  `enabled: true` + `load_status: failed`（配置已写、运行时没起来）。
- **禁用态不触发这个校验**：`runner_main._prepare_plugin_activation` 在 `enabled=false` 时直接返回
  `INACTIVE` 并跳过激活，所以带非法 `webui.json` 的插件可以长期安静地躺在仓库里不报错——上游示例
  正是这样（启用它才会看到上面那条错误）。别把「它没报错」当成「声明合法」的证据：离线
  `load_webui_extension(插件目录)` 或实际启用一次才算验证。
- 错误文案指向的 `docs/plugin-webui.md` 不存在；官方 `webui-pages.md` 的示例与能力名
  （`file_upload` / `interactive_controls`、声明式页内的 `upload` 组件）均与 Host 源码不符。
- `ImageUpload.image_max_edge` 声明了 1-8192 的范围，但宿主上传链路
  （`upload_store.py` 与 `webui_extensions.py`）没有读取或强制执行它；实际消费点在前端
  `lib/upload-image.ts` 的 `prepareUploadImage`（声明时前端把单文件上限放宽到 64 MiB 再压缩）。
- `CustomPage.layout` 的 `document` / `viewport` 两种取值在 `layout === 'document'` 时由
  ResizeObserver 上报高度；`viewport` 的完整渲染差异未在本次阅读范围内确认。
- 本文的运行时结论有三处来源：① 直接调用权威模型与函数（`load_webui_extension`、`WebUIExtension.model_validate`）；
  ② 测试套件——`uv sync --frozen` 后 `pytests/webui/test_plugin_webui_extensions.py` 与
  `test_plugin_uploads.py` 共 **61 passed**、`pytests/webui` 插件相关四个文件 64 passed、
  `pytests/plugin_runtime` 216/217 passed；③ 对着运行中的 Host 打真实端点（见
  `isolated-import-testing.md` 的「对着运行中的 Host 验证」一节）。
