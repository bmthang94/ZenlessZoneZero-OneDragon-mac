# macOS 版设计

## 目标

本仓库是专为 macOS 开发的 fork，不再支持 Windows。目标是在 Apple Silicon Mac 上运行一条龙，通过 PlayCover 运行绝区零；游戏注入 `tools/macos/libUnityDesktopMode.dylib` 插件以 PC 桌面模式逻辑接收键鼠输入，不依赖 PlayCover 内置键位映射。游戏流程、画面识别和自动化逻辑继续复用现有实现。

macOS 控制器只使用前台键鼠模式：发送键盘或鼠标输入时，游戏窗口必须处于前台。截图按 PlayCover 游戏窗口 ID 获取，因此游戏窗口被其他窗口遮挡时仍可截图；窗口仍须可见，系统可能要求授予屏幕录制权限。系统级键鼠模拟需要用户授予辅助功能权限。权限未授予或游戏窗口未找到时，控制器应报告明确错误，不应假装操作成功。项目不提供手柄控制方案。

## 与 Windows 的区别

- 窗口枚举与位置查询使用 macOS 窗口信息；截图按窗口 ID 获取 PlayCover 内容，裁掉标题栏、转换到标准 sRGB 色彩空间（避免广色域显示器 Display P3 原始数值造成颜色阈值偏移）并缩放到项目标准分辨率，避免桌面上的其他窗口出现在游戏画面里。截图前先检查当前进程的屏幕录制授权；未授权时不继续调用截图 API，只记录一次明确提示，避免自动化反复触发系统权限弹窗。授权对象必须是实际运行一条龙的程序，授权给 GitHub Copilot 不会自动授权给 Python 或终端。
- macOS 的鼠标点击、按住、拖拽、相对视角移动、滚轮，以及键盘按下、松开、点按，都由 Karabiner-DriverKit-VirtualHIDDevice 虚拟设备发送。PlayCover 里的 GCKeyboard 收不到 pynput 或 CGEvent 合成出来的按键，所以键盘不能再退回 pynput。只有画面标记了 `pc_alt` 的点击仍用 pynput 按住 Option 来解锁光标。键盘设备没就绪时，鼠标命令照常可用，按键会明确报错。点击或移动指针后通过虚拟鼠标微移 `(+1, 0)` / `(-1, 0)` 触发 PlayCover 更新内部游标位置，再发送按下/松开；大世界转向等相对鼠标移动同样通过虚拟鼠标 `dx/dy` 报告发送。连接或发送失败会明确报错，不会回退到已确认无效的合成点击。
- `pynput` 键鼠控制器在 GUI 主线程创建，再交给后台初始化的游戏控制器使用。macOS 键鼠监听器直接管理 Quartz 事件循环，避免 `pynput` 调用在当前 PyObjC 环境中不可用的辅助功能权限检查，以及键盘监听时多余的键盘布局查询；无法创建系统事件监听器时会明确提示检查辅助功能权限。
- 仅在游戏画面区域明确标记 `pc_alt` 的点击中按住 Option/Alt（例如大世界中需要解锁鼠标的按钮）；其他游戏内点击不按住 Option/Alt。
- 后台点击和后台输入不适用于 macOS；本 fork 只提供前台键鼠控制，不提供后台运行模式或手柄控制。
- PlayCover 内置 Keymapping（键位映射）当前关闭；自动化输入需要兼容用户安装的 PC 逻辑插件。
- 插件 `InputManager::OnKeyChanged` 在对象偏移 `0x38` 的键盘开关不是 1 时，直接丢掉按键。`SetKeyboardInputEnable` 没有任何调用，这个字节一直是 0。所以物理键盘和脚本键盘一起失效，包括交互 F、移动 WASD、闪避 Shift、切换 Space / C、后援 R、特殊攻击 E、终结技 Q。鼠标左键和中键不走这里，点地图不受影响。仓库 `tools/macos/libUnityDesktopMode.dylib`、PlayCover 用户插件 `PlayTools/UserPlugins/com.HoYoverse.Nap/libUnityDesktopMode.dylib`，以及游戏包 `Frameworks/UserPlugins/libUnityDesktopMode.dylib`，都把文件偏移 `0x87e4` 的条件跳转（`a1 02 00 54`）改成了空指令（`1f 20 03 d5`）。正在运行的游戏要完全退出再打开，才会加载改过的插件。
- macOS 使用 ONNX Runtime 的 CPU 执行提供程序。模型推理与自动化流程保持不变；若后续增加 Apple GPU 加速，须单独验证模型兼容性与推理结果。
- 自动战斗的声音闪避识别通过 macOS 原生 `ScreenCaptureKit` 优先捕获 PlayCover 游戏应用的声音。无法按应用录制时，先尝试系统输出音频回环，再尝试 `BlackHole` 等虚拟音频设备。原生桥接库由 `tools/macos/sck_audio_capture.mm` 构建，使用屏幕与系统录音权限。[Apple ScreenCaptureKit 音频过滤说明](https://developer.apple.com/videos/play/wwdc2022/10155/)
- PlayCover 窗口识别支持常见中英文游戏标题。自定义标题仍按原值精确匹配。
- 在账户管理中选择 PlayCover 游戏的 `.app`，即可在需要时自动启动游戏。路径留空时仍可手动启动 PlayCover 游戏。请求关闭游戏时，一条龙通过 macOS 关闭已定位的游戏应用。
- 游戏覆盖层使用同一个游戏内容区域跟随窗口。日志面板标题显示开始、暂停、继续及停止等快捷键。

## 发行与验证

macOS 发行包应使用 Apple Silicon 运行时构建。打包前需要处理应用资源与用户可写配置目录，并验证未签名应用的启动与系统权限提示。

自动化验证必须在装有 PlayCover 和绝区零的 Mac 上完成。没有该环境时，只能验证依赖解析、应用启动和控制器单元行为，不能宣称游戏自动化已验证。邮件流程在确认前会检查 OCR 结果；若画面出现“删除”，就跳过确认，避免把误点“删除已读”当作领取奖励的确认。

## 开发入口

macOS 本机开发使用 Python 3.11 和 `uv`，源码根目录为 `src/`。平台实现应围绕窗口、截图、输入、剪贴板和系统集成边界组织。

在仓库根目录双击 `启动一条龙.command`，以当前登录用户构建并运行 GUI；不要使用 `sudo` 启动整套程序。启动时会请求一次管理员授权，仅供独立的 Karabiner 虚拟 HID 点击客户端连接驱动使用；GUI 和截图仍由当前用户运行。macOS 的屏幕录制和辅助功能授权按实际进程身份管理，授权给 GitHub Copilot 不会授权给一条龙；首次运行时，应按系统提示为实际运行一条龙的程序授予权限。首次构建需要 Git、Xcode Command Line Tools 和网络连接，以获取官方 v8.7.0 客户端头文件；之后会复用 `.install/macos-vhid/` 下的构建结果。脚本沿用当前用户的 HOME 和项目虚拟环境；如果根目录存在 `.env`，启动时会加载其中的环境变量。

鼠标和键盘都要求已安装并启动 Karabiner-DriverKit-VirtualHIDDevice 8.7.0。控制器使用官方客户端协议，并保持一个常驻客户端，避免每次点击或按键都重新初始化设备。键盘初始化失败不会让这个客户端退出，鼠标仍可用。仅 `pc_alt=True` 的点击会额外按住 Option；普通点击不按 Option。
