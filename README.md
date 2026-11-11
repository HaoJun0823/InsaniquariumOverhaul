# InsaniquariumOverhaul

Insaniquarium Deluxe 的**大修工程**：在反编译源码与社区跨平台框架之上，实现四大支柱——

1. **跨平台（Cross-platform）** — Windows / Linux / macOS 原生运行
2. **多语言（i18n）** — 抽出字符串表，中文只是其中一种语言
3. **高清化（HD）** — 高 DPI / 高分辨率整数缩放渲染
4. **兼容修复（Compat）** — 现代系统兼容 + bug 修复

许可证：**AGPL-3.0**（强 copyleft，含网络使用也需开源）。

---

## 架构原则

用熟悉的 MVC 类比来理解三层边界：

| 层 | 仓库 | 角色 | 是否修改 |
|---|---|---|---|
| **Model / Controller** | `external/winfish` | 游戏逻辑：鱼、外星人、商店、各 Screen（约 4.7 万行反编译 C++） | **永不修改（只读）** |
| **View / 基础设施** | `external/poplib` | 跨平台框架：SDL3 渲染、OpenAL 音频、stb_image 图像、去 Windows API | **永不修改（只读）** |
| **你的增量** | `port/` | 四支柱全部落点：派生脚本、i18n、HD、compat、fixups | **唯一会改的地方** |

> 关键约定：`external/*` 是只读外部依赖。上游一更新，重跑 `port/derive.py`
> 即可从最新的反编译重新派生出可构建版本，**不用手动同步**。

### 为什么不是 fork

原 `WinFishCN` 是反编译 + 我的 fix #1–9；`poplib` 是社区跨平台框架。两者都是
"被消费"的底盘，不是"被改写"的对象。fork 会把我们锁死在上游历史里、还必须改反编译
本体——这违背了"反编译永不修改"的原则。新仓库 = 干净的整合层。

---

## 目录结构

```
InsaniquariumOverhaul/
├── .gitmodules
├── CMakeLists.txt        # 跨平台构建入口（替代原 vcxproj）
├── LICENSE               # AGPL-3.0
├── README.md             # 本文件
├── .gitignore
├── external/
│   ├── winfish/  (submodule → HaoJun0823/WinFishCN, 含 fix #1–9, 只读)
│   └── poplib/   (submodule → teampopwork/poplib, 跨平台框架, 只读)
└── port/                 # ← 唯一会改的地方
    ├── CMakeLists.txt
    ├── derive.py         # 从 external/winfish 派生可构建版
    ├── i18n/             # 多语言层（抽字符串表 + 中文渲染）
    ├── hd/               # 高清化（整数缩放 / HD 素材）
    ├── compat/           # 兼容修复（汇总 fix，作为 port 层补丁）
    └── fixups/           # 针对反编译的移植补丁集
```

---

## 四支柱路线图

| 支柱 | 由谁解决 | 我们要做 |
|---|---|---|
| **跨平台** | `poplib`（SDL3 / OpenAL / x64 / stb_image 已免费提供） | CMake 串起来，把 `derive.py` 的 include 重定向接到 poplib |
| **高清化** | poplib 的 GPU 渲染天然支持整数缩放 | HD 素材包 + 字体缩放打磨 |
| **多语言** | 框架层就绪，但**字符串表需自己抽** | i18n 层：抽取 `properties/*.xml` 与硬编码字面量 → 多语言表；用 FreeType/系统 CJK 字体替代位图字体（原 `ImageFont` 仅 256 字形，装不下中文） |
| **兼容修复** | — | 汇总现有 fix #1–9 + 后续，作为 `port/compat` 补丁 |

### 字体 / 中文可行性（已确认）

源码里 `ImageFont` 是字节寻址的位图字体（`CharData[256]`），**天生不支持中文**。
`SysFont` 走 GDI（`HFONT` + `TextOutW`）。跨平台下改用 **FreeType** 渲染系统/ bundled
CJK 字体，既解决中文、又天然支持高清缩放与可移植——这是 `port/i18n` 的核心。

---

## 派生工作流（`port/derive.py`）

反编译 `external/winfish` 永不修改。`derive.py` 读取它，产出一份可构建副本
（落在 `port/generated/`，gitignored），负责：

- 把 `#include <SexyAppFramework/...>` 改写为 `<poplib/...>`
- 把框架类型引用改名为 poplib 对应物
- 套用 `port/fixups/` 里的移植补丁

> 当前 `derive.py` 是 **scaffold**，实际改写规则要在摸清 poplib 的 API 表面后再填。

---

## 构建状态

- [ ] 摸清 `poplib` 的 API 表面与导出的 CMake target
- [ ] `derive.py` 实现 include 重定向 + 类型改名
- [ ] 顶层 / `port` CMake 串起 poplib + 派生源码
- [ ] Windows 上用 SDL3 后端跑通一个 spike（证明后端可替换、游戏逻辑零改动）
- [ ] 扩展到 Linux / macOS
- [ ] 逐柱叠加：高清 → 多语言 → 兼容修复

---

## 参考仓库（已记入长期记忆）

- `teampopwork/poplib` — PopCap SexyAppFramework 的跨平台重写（SDL3 / OpenAL / stb_image / x64）
- `SaMeiers/insaniquarium-port` — WinFish 反编译 + PopLib 已跑通 Win/Android/Linux aarch64；`port.sh` 派生模式范本
- `ChanseyIsTheBest/insaniquarium_nx` — Switch 原生移植（SDL2/MIT，存档与 PC 字节兼容）
- `sureandrew/SexyAppFramework` — 另一份框架参考实现
