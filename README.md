# ewptools

IAR Embedded Workbench (.ewp) 的 GUI 工具（单文件源码）。

## 当前结构

- 代码入口：`ewptools.py`
- 打包产物：`dist/ewptools.exe`

## GUI 功能

- 加载 `.ewp` 项目并显示 group/file 树
- 添加文件夹（自动递归子目录）
- 可添加到选中的 Group 下
- 删除选中的 Group
- 自动保存到 `.ewp`

## 打包（无黑框）

```bash
uv run --with pyinstaller pyinstaller --noconfirm --clean --onefile --noconsole --name ewptools ewptools.py
```

## 集成到 IAR Tools

在 IAR 中：`Tools > Configure Tools > New`

- `Menu Text`: `add new folder`
- `Command`: `C:\Users\31903\Desktop\ewptools\dist\ewptools.exe`
- `Argument`: `"$PROJ_PATH$"`
- `Initial Directory`: `$PROJ_DIR$`

配置后从 IAR 的 `Tools` 菜单点击即可打开中文 GUI。

## 鸣谢

- 受 `iarsystems/ewptool` 启发：`https://github.com/iarsystems/ewptool`
