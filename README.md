# InsaniquariumOverhaul

> **Development contract:** [AGENTS.md](AGENTS.md) — English. AI agents implement; humans review.
> **Documentation language:** all new documents are written in English. This README and
> `docs/UI-I18N-DESIGN.md` are legacy Chinese documents, migrated when substantially edited.
> **Open defects:** see [AGENTS.md §13](AGENTS.md#13-known-issues-2026-11-11).

Insaniquarium Deluxe 的**大修工程**：在反编译源码与社区跨平台框架之上，实现四大支柱——

1. **跨平台（Cross-platform）** — Windows / Linux / macOS 原生运行
2. **多语言（i18n）** — 抽出字符串表，中文只是其中一种语言
3. **高清化（HD）** — 高 DPI / 高分辨率整数缩放渲染
4. **兼容修复（Compat）** — 现代系统兼容 + bug 修复

当前重点：**重新设计 UI（放弃原版 4:3 位图）+ 用 TTF 替换烘焙字体**。
**L1 + TTF + 补丁集已实施，Windows x64 已完整编译、链接并启动验证通过**，
方案与决策记录见 **[docs/UI-I18N-DESIGN.md](docs/UI-I18N-DESIGN.md)**（L2/L3 待排期）。

许可证：**AGPL-3.0**。第三方归属见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
**游戏资产不含在仓库里**，需从你自己的零售版拷贝。

---

## 架构原则

用熟悉的 MVC 类比来理解三层边界：

| 层 | 仓库 | 角色 | 是否修改 |
|---|---|---|---|
| **Model / Controller** | `external/winfish` | 游戏逻辑：鱼、外星人、商店、各 Screen（约 4.7 万行反编译 C++） | **永不修改（只读）** |
| **View / 基础设施** | `external/poplib` | 跨平台框架：SDL3 渲染、OpenAL 音频、stb_image、SDL_ttf | **永不修改（只读）** |
| **你的增量** | `port/` | 派生脚本、i18n、UI、HD、compat、fixups | **唯一会改的地方** |

> 关键约定：`external/*` 是只读外部依赖。上游一更新，重跑 `bash port/port.sh`
> 即可从最新反编译重新派生出可构建版本，**不用手动同步**。

### 为什么不是 fork

`Vindirect/WinFish` 是反编译，`poplib` 是跨平台框架，两者都是"被消费"的底盘，
不是"被改写"的对象。fork 会把我们锁死在上游历史里、还必须改反编译本体。
新仓库 = 干净的整合层。

---

## 目录结构

```
InsaniquariumOverhaul/
├── CMakeLists.txt             # 顶层：四支柱开关 + add_subdirectory(port)
├── LICENSE                    # AGPL-3.0
├── THIRD-PARTY-NOTICES.md     # 第三方归属
├── docs/UI-I18N-DESIGN.md     # UI 现代化 + TTF 方案（已实施 L1+TTF）
├── external/
│   ├── winfish/  (submodule → Vindirect/WinFish @ f919b3c，只读)
│   └── poplib/   (submodule → teampopwork/poplib @ adf1b914，只读)
└── port/                      # ← 唯一会改的地方
    ├── CMakeLists.txt         # 串起 PopLib + 派生源码，含 /utf-8
    ├── port.sh                # 派生：include 重写 / 类型改名 / fixups
    ├── include-map.txt        # SexyAppFramework → PopLib 头文件映射（40 条）
    ├── fixups/                # 移植补丁 + main() 入口
    ├── patches/poplib/        # 上游 poplib 的 6 个最小修复补丁（不 fork）
    ├── init-deps.py           # 把 13 个嵌套依赖 checkout 到 gitlink 固定 commit
    ├── make-patches.py        # 从 pristine 子模块生成补丁
    ├── apply-patches.py       # 幂等应用 / --check / --revert
    ├── make-resources.py      # 生成 TTF 版 resources.xml
    ├── prepare-font.py        # 本机字体准备（字体二进制不入库）
    ├── assets/                # resources.xml 覆盖 + 字体说明（入库）
    ├── build-windows.bat      # MSVC x64 / Ninja 构建脚本（含 bass.dll 拷贝）
    ├── copy-assets.sh         # 零售资产 + 覆盖层 + default.xml 铺设
    ├── verify-assets.py       # 资源校验（含 !sys: 支持 / 大小写修正）
    ├── winfish/               # 派生产物（gitignored，由 port.sh 生成）
    └── bin/                   # 可执行文件 + 资产（gitignored）
```

---

## 构建（Windows，MSVC x64）

```bash
# 0. 首次克隆后，拉嵌套子模块
git submodule update --init --recursive
python port/init-deps.py          # 修正浅克隆导致的工作树为空 / 版本漂移

# 1. 派生可构建源码（从只读反编译生成 port/winfish）
bash port/port.sh

# 2. 准备字体（本机验证用系统字体；发布请换 OFL 字体，见 assets/fonts/README.md）
python port/prepare-font.py --system
python port/make-resources.py "<game>/properties/resources.xml"

# 3. 编译（build-windows.bat 会自动跑 init-deps.py + apply-patches.py）
port\build-windows.bat

# 4. 拷贝零售资产 + TTF 覆盖层 + properties/default.xml，并校验
bash port/copy-assets.sh "E:/SteamLibrary/steamapps/common/Insaniquarium Deluxe"

# 5. 运行（工作目录必须是 port/bin，游戏按相对路径找 properties/）
cd port/bin && Insaniquarium.exe
```

`build-windows.bat` 会：调用 `init-deps.py` 补齐嵌套依赖 → `apply-patches.py` 打补丁 →
把 Windows SDK 的 `rc.exe`/`mt.exe` 以**正斜杠路径**传给 CMake（反斜杠会被写进
`.cmake` 文件当成转义符而报错）→ configure + build → 把 `bass.dll` 拷到 exe 旁。
`port/CMakeLists.txt` 对游戏源码加 `/utf-8`（TTF 中文路径必需）。

> 受限沙箱若把 `reg.exe` 列入黑名单，`vcvarsall.bat` 会失败。此时用
> `set OVERHAUL_NO_VCVARS=1` 再运行脚本，它会直接设置 `INCLUDE/LIB/PATH`，
> 不查注册表、不触发被禁用程序。补丁只改 `external/poplib` 的**工作树**，
> 父仓库 gitlink 不变；上游更新后重跑 `port/make-patches.py` 重新生成即可。

### 构建状态（实测 2026-11-11，Windows x64 / MSVC 19.51）

| 项 | 状态 |
|---|---|
| 工具链（CMake 4.3.1 + Ninja + MSVC 19.51） | ✅ 满足 poplib 3.26 要求 |
| **嵌套依赖（13 个 gitlink）** | ✅ `init-deps.py --check` 全部 OK；`discordrpc` 404 由补丁的 `if(EXISTS)` 守卫绕过 |
| **派生链路 `port.sh`** | ✅ 153 源文件 → 40 条 include 规则 → 150 文件重写 → 151 派生产物 |
| **上游补丁集（不 fork）** | ✅ 7 个补丁文件干净应用、幂等验证通过（含自动帧导出与坐标变换修复） |
| **TTF 资源表** | ✅ 15 个字体 → `!sys:`，严格 XML 校验通过（339 元素） |
| **资产铺设 + 资源校验** | ✅ 45M 资产 + TTF 表 + 字体 + `default.xml`；**328 个引用全部齐全** |
| **CMake configure** | ✅ 生成 `build.ninja`，1565 条 build 边 |
| **完整编译 + 链接** | ✅ **exit 0**，`port/bin/Insaniquarium.exe` 9.5 MB（仅少量无害 warning） |
| **启动验证（headless，15 s）** | ✅ 资源加载成功、无崩溃、0 警告；exe 仅依赖系统 DLL + `bass.dll` |
| **确定性 UI 回归（3 场景 × 7 帧）** | ✅ `python port/run-capture-test.py` 全绿；隔离 profile + manifest，逐帧可复现 |

本轮修掉的上游/移植问题：官库 `alldemos` 目标不存在导致 configure 失败、
嵌套子模块浅克隆漂移、PopCap XML 的裸属性与私有实体 `&cr;`/`&nbsp;`、
XML 归一化器漏写 `=`、TTF 空字符串触发模态错误框、启动时缺 `default.xml`、
以及 `bass.dll` 未随 exe 部署。

**决策已定**：留官库 poplib + `port/patches/` 补丁集（不 fork）；本轮 UI 只做
**L1 + TTF**；游戏资产来自用户零售版，版权资产与字体二进制均不入库。
L2（宽屏锚点布局）/ L3（素材重绘）待排期，详见设计文档第 5 节。

---

## 确定性 UI 回归（不用桌面、不用按键）

之前 headless 截图和真实桌面截图**不是同一个画面**，原因不是随机崩溃：
poplib 把全部持久化状态放在 `%LOCALAPPDATA%`，而 `ShouldCheckForUpdate()`
会读残留的 `InProgress` / `LastVerCheckQueryTime` 决定是否弹「Updates」询问框。
于是「上一轮留下什么状态」决定了「这一轮截到什么图」——验证因此不可信。

顺带查明的两个真实缺陷：

1. **`SysFont::DrawString` 没有应用 `Graphics::Translate()`**。`WidgetManager`
   绘制 widget 前会 translate 到 widget 自身坐标；`ImageFont` 走
   `Graphics::DrawImage` 会遵守，`SysFont` 却把绝对矩形直接交给 SDL 渲染器，
   结果对话框的框和按钮图片在中央、标题/正文/YES·NO 全被画到屏幕左上角。
   这是「整个乱套」的根因，且影响**所有**对话框，不是只影响这一个弹窗。
2. **失效的 PopCap 更新询问框**：其服务器早已下线，且 `InProgress: 1`
   （进程被强杀残留）会在下次启动时把它唤起。现已默认关闭，仅保留
   `OVERHAUL_UPDATE_DIALOG=legacy|force` 供回归测试复现。

现在验证是确定性的：

```bash
python port/run-capture-test.py                 # default / force / legacy 三场景
python port/run-capture-test.py --only force    # 只跑对话框渲染回归
```

脚本每次**重建一个隔离的全新 profile**（`OVERHAUL_USER_DATA_DIR`，只写在
`build/ui-regression/` 下，绝不碰玩家真实数据），用 headless 帧导出拿画面，
并把环境变量、`registry.json` 快照、每帧尺寸与 MD5 写进 `manifest.json`。

| 场景 | 开关 | 期望画面 |
|---|---|---|
| `default` | 无 | 干净的 `CLICK HERE TO PLAY!` 标题界面，**无更新弹窗** |
| `force` | `OVERHAUL_UPDATE_DIALOG=force` | 更新询问框显示，且标题/正文/YES·NO **都在框内** |
| `legacy` | `OVERHAUL_UPDATE_DIALOG=legacy` | 复刻原 `ShouldCheckForUpdate()` 分支 |

帧导出由 `sdlinterface.cpp` 补丁的 `OVERHAUL_CAPTURE_*` 提供，不设变量时零开销；
`force` 场景专门守着 `SysFont` 坐标修复，避免以后换字体或改布局时又把
所有对话框文字推回左上角。

---

## 四支柱路线图

| 支柱 | 由谁解决 | 我们要做 |
|---|---|---|
| **跨平台** | poplib（SDL3 / OpenAL / x64 / stb_image 已免费提供） | CMake 串起来；`port.sh` 的 include 重定向 |
| **高清化** | SDL3 logical presentation + 整数缩放 | 视口/布局层（L1/L2）、HD 素材打磨 |
| **多语言** | **poplib 的 `SysFont` 已用 SDL_ttf**（UTF-8 原生） | 把 `resources.xml` 的 15 个烘焙字体改成 `!sys:` TTF 声明 + 抽 ~3366 个字符串字面量到语言表 |
| **兼容修复** | — | 汇总 fix + 上游未修的框架 bug（补丁集或 fork） |

### 字体 / 中文可行性（已确认）

原版 `ImageFont` 是字节寻址的位图字体（`CharData[256]`），**装不下 CJK**。
而 poplib 的 `SysFont` 用 `TTF_RenderText_Blended`，`PopString = std::string`（UTF-8），
**中文直接可画**；还支持 `TTF_OpenFontIO` 从内存加载 TTF（可内嵌中文字体，跨平台不依赖系统字体）。
切换只需 `resources.xml` 里改成 `path="!sys:fonts/xxx.ttf" size="10"`，**游戏逻辑零改动**。

---

## 参考仓库

- `Vindirect/WinFish` — 反编译基线
- `teampopwork/poplib` — SexyAppFramework 跨平台重写（SDL3 / OpenAL / SDL_ttf / stb_image）
- `SaMeiers/insaniquarium-port` — 已跑通 Win/Android/Linux aarch64；`port.sh` 派生模式与构建脚手架范本
- `SaMeiers/PopLib` — 上游归档后的框架 bug 修复（`PORT-CHANGES.md`）
- `ChanseyIsTheBest/insaniquarium_nx` — Switch 移植
- `sureandrew/SexyAppFramework` — 另一份框架参考
