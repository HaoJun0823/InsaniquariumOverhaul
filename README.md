# InsaniquariumOverhaul

Insaniquarium Deluxe 的**大修工程**：在反编译源码与社区跨平台框架之上，实现四大支柱——

1. **跨平台（Cross-platform）** — Windows / Linux / macOS 原生运行
2. **多语言（i18n）** — 抽出字符串表，中文只是其中一种语言
3. **高清化（HD）** — 高 DPI / 高分辨率整数缩放渲染
4. **兼容修复（Compat）** — 现代系统兼容 + bug 修复

当前重点：**重新设计 UI（放弃原版 4:3 位图）+ 用 TTF 替换烘焙字体**。
**L1 + TTF + 补丁集已实施并验证**，方案与决策记录见
**[docs/UI-I18N-DESIGN.md](docs/UI-I18N-DESIGN.md)**（L2/L3 待排期）。

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
├── docs/UI-I18N-DESIGN.md     # UI 现代化 + TTF 方案（待审批）
├── external/
│   ├── winfish/  (submodule → Vindirect/WinFish @ f919b3c，只读)
│   └── poplib/   (submodule → teampopwork/poplib @ adf1b914，只读)
└── port/                      # ← 唯一会改的地方
    ├── CMakeLists.txt         # 串起 PopLib + 派生源码，含 /utf-8
    ├── port.sh                # 派生：include 重写 / 类型改名 / fixups
    ├── include-map.txt        # SexyAppFramework → PopLib 头文件映射（40 条）
    ├── fixups/                # 移植补丁 + main() 入口
    ├── patches/poplib/        # 上游 poplib 的 5 个最小修复补丁（不 fork）
    ├── make-patches.py        # 从 pristine 子模块生成补丁
    ├── apply-patches.py       # 幂等应用 / --check / --revert
    ├── make-resources.py      # 生成 TTF 版 resources.xml
    ├── prepare-font.py        # 本机字体准备（字体二进制不入库）
    ├── assets/                # resources.xml 覆盖 + 字体说明（入库）
    ├── build-windows.bat      # MSVC x64 / Ninja 构建脚本
    ├── copy-assets.sh         # 零售资产 + 覆盖层铺设
    ├── verify-assets.py       # 资源校验（含 !sys: 支持 / 大小写修正）
    ├── winfish/               # 派生产物（gitignored，由 port.sh 生成）
    └── bin/                   # 可执行文件 + 资产（gitignored）
```

---

## 构建（Windows，MSVC x64）

```bash
# 0. 首次克隆后，拉嵌套子模块（不要加 --depth，会拉到错误版本）
git submodule update --init --recursive

# 1. 派生可构建源码 + 应用上游补丁（build-windows.bat 也会自动做第 2 步）
bash port/port.sh
python port/apply-patches.py

# 2. 准备字体（本机验证用系统字体；发布请换 OFL 字体，见 assets/fonts/README.md）
python port/prepare-font.py --system
python port/make-resources.py "<game>/properties/resources.xml"

# 3. 编译（普通终端执行，不要在工作区沙箱内）
port\build-windows.bat

# 4. 拷贝零售资产 + TTF 覆盖层并校验
bash port/copy-assets.sh "E:/SteamLibrary/steamapps/common/Insaniquarium Deluxe"
```

`build-windows.bat` 已显式把 Windows SDK 的 `rc.exe`/`mt.exe` 加入 PATH 并传给 CMake，
加 `/utf-8` 编译选项（TTF 中文路径必需），并在编译前自动应用 `apply-patches.py`。
补丁只改 `external/poplib` 的**工作树**，父仓库 gitlink 不变；上游更新后重跑
`port/make-patches.py` 重新生成即可。

### 构建状态（实测 2026-11-11）

| 项 | 状态 |
|---|---|
| 工具链（CMake 4.3.1 + Ninja + MSVC 19.51） | ✅ 满足 poplib 3.26 要求 |
| poplib 嵌套子模块 | ⚠️ 9/10；`discordrpc` 上游 404（补丁已绕过） |
| **派生链路 `port.sh`** | ✅ **跑通**：153 源文件 → 40 条 include 规则 → 150 文件重写 → 151 派生产物 |
| **上游补丁集（不 fork）** | ✅ 5 个补丁干净应用、幂等验证通过 |
| **TTF 资源表** | ✅ 15 个字体 → `!sys:`，严格 XML 校验通过（339 元素） |
| **资产铺设 + 资源校验** | ✅ 20M 资产 + TTF 表 + 字体就位；**328 个引用全部齐全，exit 0** |
| CMake configure 完整编译 | ⚠️ 唯一未验证环节：受本机沙箱限制（`reg.exe` 黑名单），需在普通终端跑 |

**决策已定**：留官库 poplib + `port/patches/` 补丁集（不 fork）；本轮 UI 只做
**L1 + TTF**；游戏资产来自用户零售版，版权资产与字体二进制均不入库。
L2（宽屏锚点布局）/ L3（素材重绘）待 Windows spike 后排期，详见设计文档第 5 节。

---

## 四支柱路线图

| 支柱 | 由谁解决 | 我们要做 |
|---|---|---|
| **跨平台** | poplib（SDL3 / OpenAL / x64 / stb_image 已免费提供） | CMake 串起来；`port.sh` 的 include 重定向 |
| **高清化** | SDL3 logical presentation + 整数缩放 | 视口/布局层（L1/L2）、HD 素材打磨 |
| **多语言** | **poplib 的 `SysFont` 已用 SDL_ttf**（UTF-8 原生） | 把 `resources.xml` 的 14 个烘焙字体改成 `!sys:` TTF 声明 + 抽 ~3366 个字符串字面量到语言表 |
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
