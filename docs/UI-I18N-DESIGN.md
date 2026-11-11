# UI 现代化与多语言（TTF）设计方案

> 状态（2026-11-11）：**L1 + TTF + 补丁集已实施并验证**；L2/L3 仍为待审批方案。
> 决策记录：留官库 poplib + `port/patches/` 补丁集（不 fork）；本轮 UI 只做
> **L1 + TTF**；游戏资产来自用户零售版 `E:\SteamLibrary\...\Insaniquarium Deluxe`。
> 目标：放弃原版 4:3 位图 UI、用 TTF 替换烘焙字体、支撑跨平台 + 多语言。

## 已实施（本轮，全部经过验证）

| 交付 | 位置 | 验证结果 |
|---|---|---|
| 上游 bug 补丁集（不 fork） | `port/patches/poplib/*.patch`（5 个） | `--check` 干净、apply 成功、二次运行识别"已应用"（幂等） |
| 补丁生成 / 应用工具 | `port/make-patches.py`、`port/apply-patches.py` | 支持 `--check` / `--revert` |
| **L1 逻辑呈现**：设计分辨率 640×480 + SDL letterbox 缩放 | sdlinterface 补丁 | 补丁已应用 |
| 颜色值域、随机数、kerning、无引号 XML、discordrpc 404 | sdlinterface/mtrand/imagefont/xmlparser/CMake 补丁 | 补丁已应用 |
| **TTF 资源表**（15 个 `<Font>` → `!sys:fonts/ui.ttf`） | `port/assets/properties/resources.xml` | 严格 XML 校验通过（339 元素） |
| 资源表生成器 | `port/make-resources.py` | 15 个重写 + 5 处无引号值 + 6 处无值属性规范化 |
| 字体准备 / 说明 | `port/prepare-font.py`、`port/assets/fonts/README.md` | 本机字体已铺好（不入库） |
| 资产铺设 + 覆盖层 | `port/copy-assets.sh` | 20M 资产 + TTF 表 + 字体全部就位 |
| 资源校验（含 `!sys:` 支持、大小写修正） | `port/verify-assets.py` | **328 个引用全部齐全、退出码 0** |

> 补丁作用于 `external/poplib` 的**工作树**，父仓库 gitlink 仍是
> `adf1b914`（仅显示 `-dirty`），不进 git 历史。上游更新后重跑
> `make-patches.py` 重新生成即可。

### 仍未验证：完整编译
CMake try_compile 受本机沙箱限制（`reg.exe` 黑名单 / `rc.exe`-`mt.exe` 路径）。
`port/build-windows.bat` 已显式补上 SDK rc/mt 并接入 `apply-patches.py`，
**需要在普通终端跑一次**：

```bash
python port/apply-patches.py
port\build-windows.bat
bash port/copy-assets.sh "E:/SteamLibrary/steamapps/common/Insaniquarium Deluxe"
```

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
- 原版 `resources.xml` 有 14 个烘焙字体：`<Font id="JUNGLEFEVER10OUTLINE" path="JungleFever10outline.txt" />`，
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
1. `port/assets/properties/resources.xml` — 从原版派生，把 14 个 `<Font>` 换成 `!sys:` 声明。
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

## 4. 构建现状与阻塞（实测 2026-11-11）

已验证 ✅
- 工具链：VS 18/Community 自带 **CMake 4.3.1 + Ninja + MSVC 19.51**，满足 poplib 的 3.26 要求。
- 嵌套子模块：`git submodule update --init --recursive --depth 1` 拉到 9/10。
- **派生链路跑通**：`bash port/port.sh` → 153 源文件、40 条 include 规则、150 文件重写、151 个派生产物，
  `Board.cpp` 的 include 已全部变成 `PopLib/...`。

待解决 ⚠️
1. **`external/discordrpc` 上游 404**（`EclipseMenu/discord-presence` 仓库已不存在）。
   构建时 `FEATURE_DISCORD_RPC=OFF` 可绕过功能，但官库 `CMakeLists.txt` 无条件
   `add_subdirectory(external/discordrpc)`，空目录会让 configure 失败 → 需 patch。
2. **官库 poplib 上游已归档且有未修 bug**。`SaMeiers/PopLib` 的 `PORT-CHANGES.md` 列出若干会让游戏跑不起来的问题：
   - `xmlparser` 不接受 `resources.xml` 里的**无引号属性值** → 资源加载直接失败；
   - `MTRand` 丢了 `& 0x7FFFFFFF` → 一半随机数为负，鱼每帧掉钱；
   - `char` 在 ARM 上无符号 → kerning `-2` 读成 `254`，文字宽度全错；
   - `SDL_FColor` 值域 0–1 却按 0–255 传 → 几何图形全白；
   - 还有 vsync / render target / 逻辑呈现缩放等渲染修复（**L1 正好需要它**）。
3. **完整编译未验证**：CMake configure 时 MSVC 识别成功，但 try_compile 因 `rc.exe`/`mt.exe`
   未进 PATH 失败，且沙箱把 `vcvarsall` 内部调用的 `reg.exe` 列入黑名单。
   `port/build-windows.bat` 已显式把 SDK rc/mt 加入 PATH 并传给 CMake，**需在普通终端执行验证**。
4. **游戏资产缺失**（`data/properties/images/music/sounds/fishsongs`）。属 PopCap 版权，
   需从你自己的零售版拷贝：`bash port/copy-assets.sh <游戏目录>`。
5. **嵌套子模块浅克隆版本漂移**：`--depth 1` 会把 SDL/SDL_ttf/curl/ogg/openal/tinyxml2/zlib
   停在各仓库最新 HEAD，而非官库 gitlink 记录的 commit（实测 7 个不一致），可能编不过。
   首次克隆建议直接 `git submodule update --init --recursive`（不加 `--depth`）；
   或对子模块按 gitlink 逐个 `git fetch origin <sha> && git checkout <sha>`。

> 注：以上 1/2/5 都源于**官库 poplib 上游已归档、依赖失修**。切到维护中的
> `SaMeiers/PopLib` 或以补丁集修复，是同一个决策的两面，见下节。

---

## 5. 决策记录（已拍板，2026-11-11）

1. **poplib 基线 = 留官库 + `port/patches/` 补丁集**（不 fork）。已落地 5 个最小补丁，
   只取桌面相关的通用修复，不夹带 Android/PortMaster 掌机代码。
2. **UI 范围 = 本轮 L1 + TTF 先行**。L2（锚点布局 / 16:9 自适应）、L3（素材重绘）
   留到 Windows spike 验证后再排期。
3. **游戏资产**来自用户零售版，路径已写入 `copy-assets.sh` 调用示例；
   版权资产不入库，字体二进制也不入库（`ui.ttf` 已 gitignore）。

### 后续待办（未做）
- 普通终端跑通 Windows SDL3 spike（唯一未验证环节）；
- 换用 OFL 中文 TTF（发布时），当前本机验证用的是系统黑体（不可再分发）；
- `OutlineSysFont` 包装类，补回原版 `*_OUTLINE` 描边观感；
- `port/i18n/` 字符串表：把 ~3366 个字面量抽成 `TR("key")`，
  需先给存档/作弊码/资源 id 建白名单；
- 扩 Linux / macOS。
