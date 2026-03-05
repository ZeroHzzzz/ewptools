# ewptools

IAR Embedded Workbench (.ewp) 的 GUI 工具（单文件源码）。

## 当前结构

- 代码入口：`ewptools.py`
- 打包产物：`dist/ewptools.exe`

## GUI 功能

- 加载 `.ewp` 项目并显示 group/file 树
- 添加文件夹（自动递归子目录）
- 默认包含头文件（`.h/.hpp/.hh/.hxx/.inl/.tpp`）
- 自动同步 IAR 编译器 Include Path（预处理器搜索路径）
- 可添加到选中的 Group 下
- 支持一键展开/折叠文件树
- 支持仅同步 Include Path（不改分组树）
- 删除选中的 Group
- 自动保存到 `.ewp`

界面中可通过 `包含头文件` 勾选项控制是否一起加入头文件。
界面中可通过 `同步 Include Path` 勾选项控制是否写入 `.ewp` 的编译器搜索路径。

## 打包（无黑框）

```bash
uv run --with pyinstaller pyinstaller --noconfirm --clean --onefile --noconsole --name ewptools ewptools.py
```

## 集成到 IAR Tools

在 IAR 中：`Tools > Configure Tools > New`

- `Menu Text`: `add new folder`
- `Command`: `path\to\ewptools.exe`
- `Argument`: `"$PROJ_PATH$"`
- `Initial Directory`: `$PROJ_DIR$`

配置后从 IAR 的 `Tools` 菜单点击即可打开中文 GUI。

## 鸣谢

- 受 `iarsystems/ewptool` 启发：`https://github.com/iarsystems/ewptool`
