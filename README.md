# ewptools

IAR Embedded Workbench (.ewp) 的 GUI 工具（单文件源码）。

## 当前结构

- 代码入口：`ewptools.py`
- 打包产物：`dist/ewptools.exe`

## GUI 功能

- 加载 `.ewp` 项目并显示 group/file 树
- 自动检测同名 `.ewt`，结构变更时同步写入（group/file）
- 统一添加路径（目录+文件可混合批量）
- 默认包含头文件（`.h/.hpp/.hh/.hxx/.inl/.tpp`）
- 自动同步 IAR 编译器 Include Path（预处理器搜索路径）
- 可删除选中项（Group 或 File，仅删除工程结构，不删除磁盘文件）
- 可添加到选中的 Group 下
- 支持一键展开/折叠文件树
- 支持仅同步 Include Path（不改分组树）
- 支持开关控制是否同步 `.ewt`
- 自动保存到 `.ewp`
- 内置日志面板：成功操作写日志，不再弹出成功对话框

说明：
- 当存在同名 `.ewt`（例如 `xxx.ewp` 对应 `xxx.ewt`）时，添加/删除 group 等结构操作会同时保存到 `.ewp` 和 `.ewt`。
- Include Path 仍以 `.ewp` 的编译配置为准（`.ewt` 主要用于工具配置与工程结构镜像）。

界面中可通过 `包含头文件` 勾选项控制是否一起加入头文件。
界面中可通过 `同步 Include Path` 勾选项控制是否写入 `.ewp` 的编译器搜索路径。
目录/文件输入框支持分号 `;` 分隔多个路径，便于批量添加。
路径选择入口为两个按钮：`选文件夹`（单次选一个并追加）和 `选文件`（可多选）。
单文件添加默认不再按“父目录名”自动新建 Group（除非你手动填写 `Group 名`）。
错误仍使用弹窗提示，成功信息统一在日志区查看。
删除 Group/File 时，若启用了 `同步 Include Path`，会自动清理不再被工程引用的目录搜索路径。
添加文件时，若启用了 `同步 Include Path`，会自动把文件所在目录加入 Include Path。

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

## TODO

- [ ] 代码疑似写的有点依托了，得整理一下

## 鸣谢

- 受 `iarsystems/ewptool` 启发：`https://github.com/iarsystems/ewptool`
