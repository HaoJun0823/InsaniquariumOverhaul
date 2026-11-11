# UI 现代化与多语言（TTF）设计方案

> 状态（2026-11-11）：**L1 + TTF + 补丁集已实施；Windows x64 完整编译、链接、启动均已验证通过**；
> L2/L3 仍为待排期方案。
> 决策记录：留官库 poplib + `port/patches/` 补丁集（不 fork）；本轮 UI 只做
> **L1 + TTF**；游戏资产来自用户零售版 `E:\SteamLibrary\...\Insaniquarium Deluxe`。
> 目标：放弃原版 4:3 位图 UI、用 TTF 替换烘焙字体、支撑跨平台 + 多语言。

## 已实施（本轮，全部经过验证）

| 交付 | 位置 | 验证结果 |
|---|---|---|
| 上游 bug 补丁集（不 fork） | `port/patches/poplib/*.patch`（6 个文件 / 8 处修复） | `--check` 干净、apply 成功、二次运行识别"已应用"（幂等） |
| 补丁生成 / 应用工具 | `port/make-patches.py`、`port/apply-patches.py` | 支持 `--check` / `--revert` |
| 嵌套依赖修复 | `port/init-deps.py` | 13 个 gitlink 全部 checkout 到固定 commit |
| **L1 逻辑呈现**：设计分辨率 640×480 + SDL letterbox 缩放 | sdlinterface 补丁 | 补丁已应用 |
| 颜色值域、随机数、kerning、无引号 XML、`&cr;`/`&nbsp;`、discordrpc 404、`alldemos` | 各补丁 | 补丁已应用 |
| TTF 空字符串不再弹错误框；启动期致命错误写 stderr | sysfont / sdlinterface 补丁 | headless 运行 0 警告 |
| **TTF 资源表**（15 个 `<Font>` → `!sys:fonts/ui.ttf`） | `port/assets/properties/resources.xml` | 严格 XML 校验通过（339 元素） |
| 资源表生成器 | `port/make-resources.py` | 15 个重写 + 5 处无引号值 + 6 处无值属性规范化 |
| 字体准备 / 说明 | `port/prepare-font.py`、`port/assets/fonts/README.md` | 本机字体已铺好（不入库） |
| 资产铺设 + 覆盖层 + `default.xml` + `bass.dll` | `port/copy-assets.sh`、`port/CMakeLists.txt` | 45M 资产全部就位 |
| 资源校验（含 `!sys:` 支持、大小写修正） | `port/verify-assets.py` | **328 个引用全部齐全、退出码 0** |
| **完整编译 / 链接 / 启动** | `port/build-windows.bat` | **exit 0；`Insaniquarium.exe` 9.5 MB；headless 跑满 15 s 无崩溃** |

> 补丁作用于 `external/poplib` 的**工作树**，父仓库 gitlink 仍是
> `adf1b914`（仅显示 `-dirty`），不进 git 历史。上游更新后重跑
> `make-patches.py` 重新生成即可。

### 完整编译与启动：已验证（2026-11-11）

不绕过安全策略：沙箱把 `reg.exe` 列入程序黑名单、`vcvarsall.bat` 会查询注册表，
因此改用**手工设置 `INCLUDE` / `LIB` / `PATH`** 的标准无注册表方式驱动 MSVC + Ninja
（全程不运行被禁用的程序）。结果：

- CMake configure：`build.ninja`，1565 条 build 边；
- `cmake --build --parallel`：**exit 0**，910/911 步，`port/bin/Insaniquarium.exe` 9.5 MB；
- `dumpbin /dependents`：仅系统 DLL + VC runtime + `bass.dll`（其余依赖均静态链接）；
- headless（`SDL_VIDEODRIVER=dummy`）启动 15 s：`Resource Loading Time: 905`，**0 警告、0 崩溃**。

`port/build-windows.bat` 已把这些修复固化，普通终端直接运行即可；受限环境用
`set OVERHAUL_NO_VCVARS=1`。

---

## 1. 先分清三件被混在一起的事

用户说的"放弃原版的 4:3 位图"，其实包含三个**正交**的维度，改动量和风险完全不同。
用后端 MVC 类比：

| 维度 | MVC 对位 | 现状 | "现代化"要做什么 |
|---|---|---|---|
| **A. 逻辑坐标系** | Model 的世界坐标 | `Board.cpp: mWidth=640; mHeight=480`，全代码 92 处 `640/480` 字面量、27 个文件 | **不建议改成别的数字**——鱼、气泡、碰撞、外星人全在这套坐标里。应抽象成"设计画布"常量 |
| **B. 渲染分辨率** | View 的呈现 | 原版 DirectDraw 1:1 输出 640×480 | 由 SDL3 缩放/letterbox 到任意窗口、高 DPI、宽屏 |
| **C. UI 素材与布局** | View 的模板 | 按钮/面板/标题都是预烘焙位图；139 处 `Resize()` 用绝对坐标 | 锚点化布局 + 高分辨率/矢量素材 |

**关键结论**：A 是游戏逻辑的地基，**删掉 640×480 会让整个玩法坐标崩塌**。
正确做法不是"把 640 换成 1920"，而是引入一层**坐标系映射**：

```
游戏逻辑（Model/Controller）  仍用 640×480 设计坐标
        ↓  LayoutContext / 视口变换（新增的 port/ 层）
渲染输出（View, SDL3）        任意窗口尺寸、16:9、高 DPI
```

这跟后端里"数据库存 UTC、展示层按时区格式化"是同一类思路：底层保持单一事实来源，边界层做变换。

---

## 2. 字体：从烘焙位图到 TTF（低风险，可先做）

### 现状（已核实）
- 原版 `resources.xml` 有 15 个烘焙字体：`<Font id="JUNGLEFEVER10OUTLINE" path="JungleFever10outline.txt" />`，
  每个 `.txt` 描述一张字形图集；`Res.cpp` 用 `GetFontThrow("FONT_XXX")` 取出。
- `ImageFont` 是 `CharData[256]` / `uchar mCharMap[256]`——**按字节寻址，最多 256 字形，天生装不下 CJK**。
- 所以 TTF 不是"优化"，是**多语言的必要前提**。

### 好消息：poplib 已经把路铺好了
- `PopString = std::string`（UTF-8），`SysFont::DrawString` 用 `TTF_RenderText_Blended` → **SDL_ttf 原生按 UTF-8 渲染，中文直接可画**。
- `SysFont` 支持 `TTF_OpenFontIO` 从内存字节数组加载 → 中文字体可内嵌进程序，不依赖系统装了什么字体（跨平台刚需）。
- `ResourceManager::DoLoadFont` 已有 `!sys:` 分支。声明格式：

```xml
<!-- 原来（烘焙位图） -->
<Font id="JUNGLEFEVER10OUTLINE" path="JungleFever10outline.txt" />

<!-- 改为（TTF）-->
<Font id="JUNGLEFEVER10OUTLINE" path="!sys:fonts/NotoSansSC-Regular.ttf" size="10" />
<!-- 可选属性: bold / italic / shadow / underline -->
```

`size` 必填，`!sys:` 前缀触发 `SysFont` 路径。**游戏逻辑一行都不用改**——`GetFontThrow` 拿到的还是 `Font*`。

### 落地清单（全在 `port/` 层，反编译零改动）
1. `port/assets/properties/resources.xml` — 从原版派生，把 15 个 `<Font>` 换成 `!sys:` 声明。
   （这是资源覆盖，不改 `external/winfish`。）
2. `port/assets/fonts/` — 放可再分发的中文字体（推荐 **Noto Sans SC / 思源黑体，SIL OFL 1.1**，
   允许随 AGPL 程序分发；字体自身许可证需在 `THIRD-PARTY-NOTICES.md` 登记）。
3. 编译期加 **`/utf-8`**（MSVC）/ `-finput-charset=UTF-8`（GCC/Clang）——已写进 `port/CMakeLists.txt`。
   否则 MSVC 把中文源码字面量按本地 ANSI 转码，UTF-8 渲染出来就是乱码。
4. 描边效果：原版 `*_OUTLINE` 的描边是烘焙在图集里的，TTF 会丢失。
   用 SDL_ttf 多层偏移绘制或 `TTF_SetFontOutline` 在 `port/ui/` 补一个 `OutlineSysFont` 包装类。
5. `SysFont::CreateImageFont()` 在 poplib 里是 `return nullptr; // TODO` —— 若有代码路径依赖"把 SysFont 转位图字体"，
   需在 `port/` 侧规避或补实现。

### 多语言字符串表（i18n 主体工作量）
- 游戏层约 **3366 个字符串字面量**、242 处 `DrawString`。
- 方案：`port/fixups/extract-strings.py` 在派生阶段把字面量替换为 `TR("key")`，
  生成 `port/i18n/<lang>.json`（zh-CN / en / …），运行时按语言加载。
- 这是纯体力活但可脚本化；**注意存档/作弊码/资源 id 等字符串不能翻译**，需要先分类白名单。

---

## 3. UI 现代化：分三层推进，不要一次性重写

| 层级 | 内容 | 改动面 | 风险 |
|---|---|---|---|
| **L1 呈现层** | SDL3 logical presentation：设计画布 640×480 整数倍缩放、高 DPI、宽屏 letterbox 或扩展背景 | 只动框架配置 / `port/ui/` 视口 | 低 |
| **L2 布局层** | 引入 `LayoutContext`；把 92 处硬编码坐标 + 139 处 `Resize` 换成基于 `mWidth/mHeight` 的锚点表达式；16:9 下 UI 重排 | `port/fixups/` 批量改写派生源码 | 中 |
| **L3 素材层** | 位图 UI 换成高分辨率重绘或程序化绘制（9-slice 面板、圆角、渐变、矢量图标） | 需美术资源；最大工作量 | 高 |

**建议顺序**：先 L1 + TTF（立刻拿到"清晰 + 中文 + 跨平台"），验证 spike 后再做 L2，L3 视美术投入决定。
L2/L3 都只改 `port/` 派生层，符合"反编译永不修改"的架构契约。

---

## 4. 构建现状：已全部解决（实测 2026-11-11）

已验证 ✅
- 工具链：VS 18/Community 自带 **CMake 4.3.1 + Ninja + MSVC 19.51**，满足 poplib 的 3.26 要求。
- **派生链路跑通**：`bash port/port.sh` → 153 源文件、40 条 include 规则、150 文件重写、151 个派生产物。
- **完整编译 + 链接 + headless 启动**全部通过（见前文）。

本轮修掉的问题（都已固化进补丁集 / 脚本，不再需要人工干预）：

| 问题 | 修法 |
|---|---|
| `external/discordrpc` 上游 404，官库无条件 `add_subdirectory` | `CMakeLists.txt.patch` 用 `if(EXISTS ...)` 守卫 |
| 官库 `add_custom_command(TARGET alldemos ...)` 无条件执行，但 `BUILD_EXAMPLES/TOOLS=OFF` 时该 target 不存在 | 同补丁改为 `if(TARGET alldemos AND ...)` |
| 嵌套子模块浅克隆：**工作树全空**、HEAD 停在分支 tip 而非 gitlink | `port/init-deps.py` 按 gitlink SHA `fetch --depth 1` + `checkout --detach`（9 个 poplib + 4 个 SDL_ttf，共 13 个） |
| SDL_ttf 的 freetype / harfbuzz / plutosvg / plutovg 未初始化 | 同上 |
| `resources.xml` 的裸属性值 `cols=3`、`default.xml` 的私有实体 `&cr;` / `&nbsp;` | `xmlparser.cpp` 补丁：解析前归一化 |
| 归一化器漏写 `=`，把 `id="X"` 变成 `id"X"`（`XML_ERROR_PARSING_ATTRIBUTE`） | 同一补丁修正 |
| `MTRand` 丢掩码 / ARM 上 `char` 无符号 / `SDL_FColor` 值域 / L1 逻辑呈现 | 对应补丁 |
| TTF 空字符串触发模态错误框，每帧刷屏 | `sysfont.cpp` 补丁：zero-width 静默跳过 |
| 启动期致命错误在窗口创建前弹框崩溃 | `sdlinterface.cpp` 补丁：先写 stderr，有窗口才弹框 |
| `properties/default.xml` 被旧中文补丁移走，游戏启动即失败 | `copy-assets.sh` 搜索多个已知位置 |
| `bass.dll` 未随 exe 部署（BASS 是 import lib） | `port/CMakeLists.txt` POST_BUILD 拷贝 |
| CMake `-D` 路径用反斜杠被当成转义符 | `build-windows.bat` 统一用正斜杠 |
| 沙箱 `reg.exe` 黑名单 | `OVERHAUL_NO_VCVARS=1` 手工设置 MSVC 环境，不查注册表 |

> 这些大多源于**官库 poplib 上游已归档、依赖失修**。用补丁集而非 fork 修复，
> 是第 5 节决策的直接结果。

---

## 5. 决策记录（已拍板，2026-11-11）

1. **poplib 基线 = 留官库 + `port/patches/` 补丁集**（不 fork）。已落地 6 个补丁文件，
   只取桌面相关的通用修复，不夹带 Android/PortMaster 掌机代码。
2. **UI 范围 = 本轮 L1 + TTF 先行**。Windows spike 已验证通过；L2（锚点布局 / 16:9 自适应）、
   L3（素材重绘）留待后续排期。
3. **游戏资产**来自用户零售版，路径已写入 `copy-assets.sh` 调用示例；
   版权资产不入库，字体二进制也不入库（`ui.ttf` 已 gitignore）。

### 后续待办（未做）
- 在**真实桌面**双击运行、肉眼确认 TTF 中文渲染与 L1 letterbox 观感
  （headless 验证只能证明不崩，不能证明画面正确）；
- 换用 OFL 中文 TTF（发布时），当前本机验证用的是系统黑体（不可再分发）；
- `OutlineSysFont` 包装类，补回原版 `*_OUTLINE` 描边观感；
- `port/i18n/` 字符串表：把 ~3366 个字面量抽成 `TR("key")`，
  需先给存档/作弊码/资源 id 建白名单；
- 扩 Linux / macOS。
