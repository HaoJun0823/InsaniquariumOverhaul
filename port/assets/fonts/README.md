# 字体（不入库）

`resources.xml` 里 15 个字体声明都指向 `!sys:fonts/ui.ttf`，即运行时从
**游戏工作目录**下的 `fonts/ui.ttf` 加载。PopLib 的 `SysFont` 用 SDL_ttf
按 UTF-8 渲染，所以这个文件决定了能不能显示中文。

## 为什么不入库

- 中文字体通常 10–20 MB，不适合放进源码仓库；
- 微软雅黑 / 黑体等系统字体**不能随程序再分发**（版权）；
- 跨平台必须自带字体，不能假设目标机器装了某个字体。

## 推荐：SIL OFL 1.1 字体（可随 AGPL 程序分发）

| 字体 | 许可 | 说明 |
|---|---|---|
| **Noto Sans SC**（思源黑体） | SIL OFL 1.1 | 覆盖简体中文，字形现代，Google / Adobe 维护 |
| **LXGW WenKai**（霞鹜文楷） | SIL OFL 1.1 | 偏手写风格，适合游戏 UI |
| **Noto Sans CJK SC** | SIL OFL 1.1 | 完整 CJK，体积较大 |

下载后把文件**重命名为 `ui.ttf`** 放到 `port/assets/fonts/ui.ttf`，
`copy-assets.sh` 会把它拷到 `port/bin/fonts/ui.ttf`。

- Noto Sans SC: <https://github.com/notofonts/noto-cjk/tree/main/Sans>
- 字体许可证需登记进根目录 `THIRD-PARTY-NOTICES.md`。

## 本地验证（不分发）

如果你只是想在本机先跑起来，可以用系统字体顶一下：

```bash
python port/prepare-font.py --system
```

它会从 `C:\Windows\Fonts\simhei.ttf` 拷一份到 `port/assets/fonts/ui.ttf`。
**这份文件不会、也不应该提交**（见 `.gitignore`）。它仅用于本机验证；
公开发布前请换成 OFL 字体。

## 关于视觉差异

原版 `*_OUTLINE` 字体的描边是烘焙在位图图集里的，TTF 没有。
`make-resources.py` 对这些字体加了 `bold="1" shadow="1"`，用
`SysFont::mDrawShadow` 的 1px 偏移阴影近似。若要更接近原版的描边，
后续在 `port/ui/OutlineSysFont` 里做多层偏移绘制（属 L2/L3 打磨）。

## 字号

字号直接取字体 id 里的数字（JUNGLEFEVER10 → 10，LIDDIE18 → 18），
`TINY` / `TINYBOLD` 无数字，取 8。位图字体的像素高度与 TTF 的 point size
不完全等价，L1 阶段先用这个近似，后续在布局层统一校准。
