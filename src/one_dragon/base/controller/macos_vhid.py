from __future__ import annotations

import selectors
import subprocess
import threading
from pathlib import Path
from typing import Literal

# 修饰键走 HID 报告里的 modifier 位，不能当成普通按键 usage。
_MODIFIER_BITS: dict[str, int] = {
    'ctrl': 0x01,
    'ctrl_l': 0x01,
    'ctrl_r': 0x10,
    'shift': 0x02,
    'shift_l': 0x02,
    'shift_r': 0x20,
    'alt': 0x04,
    'alt_l': 0x04,
    'alt_r': 0x40,
    'alt_gr': 0x40,
    'option': 0x04,
    'cmd': 0x08,
    'cmd_l': 0x08,
    'cmd_r': 0x80,
    'win': 0x08,
    'command': 0x08,
}

_NAMED_KEY_USAGES: dict[str, int] = {
    'enter': 0x28,
    'return': 0x28,
    'esc': 0x29,
    'escape': 0x29,
    'backspace': 0x2A,
    'tab': 0x2B,
    'space': 0x2C,
    'spacebar': 0x2C,
    'caps_lock': 0x39,
    'print_screen': 0x46,
    'scroll_lock': 0x47,
    'pause': 0x48,
    'insert': 0x49,
    'home': 0x4A,
    'page_up': 0x4B,
    'delete': 0x4C,
    'end': 0x4D,
    'page_down': 0x4E,
    'right': 0x4F,
    'left': 0x50,
    'down': 0x51,
    'up': 0x52,
    '-': 0x2D,
    '=': 0x2E,
    '[': 0x2F,
    ']': 0x30,
    '\\': 0x31,
    ';': 0x33,
    "'": 0x34,
    '`': 0x35,
    ',': 0x36,
    '.': 0x37,
    '/': 0x38,
}


def resolve_macos_hid_key(key: str) -> tuple[Literal['key', 'mod'], int]:
    """把一条龙的按键名转成虚拟键盘的 usage 或修饰键位。

    不认识的按键直接报错。不能退回 pynput：PlayCover 的 GCKeyboard 收不到那种合成按键。
    """
    normalized = key.strip().lower()
    modifier_bit = _MODIFIER_BITS.get(normalized)
    if modifier_bit is not None:
        return 'mod', modifier_bit
    if len(normalized) == 1 and 'a' <= normalized <= 'z':
        return 'key', 0x04 + ord(normalized) - ord('a')
    if len(normalized) == 1 and normalized.isdigit():
        if normalized == '0':
            return 'key', 0x27
        return 'key', 0x1E + int(normalized) - 1
    named_usage = _NAMED_KEY_USAGES.get(normalized)
    if named_usage is not None:
        return 'key', named_usage
    if len(normalized) >= 2 and normalized[0] == 'f' and normalized[1:].isdigit():
        function_key = int(normalized[1:])
        if 1 <= function_key <= 12:
            return 'key', 0x3A + function_key - 1
    if (
        normalized.startswith('numpad_')
        and len(normalized) == 8
        and normalized[7].isdigit()
    ):
        numpad_digit = int(normalized[7])
        if numpad_digit == 0:
            return 'key', 0x62
        return 'key', 0x59 + numpad_digit - 1
    raise ValueError(f'不支持的 macOS 虚拟键盘按键：{key}')


class MacVirtualHIDMouse:
    """通过 Karabiner 虚拟 HID 发送鼠标和键盘输入。"""

    READY_TIMEOUT: float = 10
    RESPONSE_TIMEOUT: float = 10

    def __init__(self) -> None:
        project_dir = Path(__file__).resolve().parents[4]
        client_path = project_dir / '.install' / 'macos-vhid' / 'vhid-click-client'
        if not client_path.is_file():
            raise FileNotFoundError(
                f'找不到虚拟 HID 点击客户端：{client_path}。'
                '请先双击仓库根目录的启动一条龙.command'
            )

        self._process = subprocess.Popen(
            ['/usr/bin/sudo', '-n', str(client_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
        )
        self._lock = threading.Lock()
        try:
            response = self._read_line(self.READY_TIMEOUT)
            if response != 'READY':
                if 'password is required' in response.lower():
                    raise RuntimeError(
                        '启动虚拟 HID 客户端需要管理员授权；'
                        '请通过启动一条龙.command 重新启动并完成一次密码验证'
                    )
                raise RuntimeError(response.removeprefix('ERROR ').strip() or
                                   '虚拟鼠标设备未就绪')
        except Exception:
            self.close()
            raise

    def is_running(self) -> bool:
        """判断客户端进程是否仍在运行。"""
        return self._process.poll() is None

    def click(self, press_time: float = 0.1, button: str = 'left') -> None:
        """发送一次鼠标点击。"""
        duration_ms = min(60000, max(1, round(press_time * 1000)))
        self._send_command('click', button, duration_ms)

    def press(self, button: str = 'left') -> None:
        """按住鼠标按键。"""
        self._send_command('press', button, 0)

    def release(self, button: str = 'left') -> None:
        """释放鼠标按键。"""
        self._send_command('release', button, 0)

    def move_relative(self, dx: int, dy: int) -> None:
        """通过虚拟 HID 发送相对鼠标移动（自动拆分超过单次 HID 报告范围的位移）。"""
        rem_x = round(dx)
        rem_y = round(dy)
        if rem_x == 0 and rem_y == 0:
            return
        while rem_x != 0 or rem_y != 0:
            step_x = max(-127, min(127, rem_x))
            step_y = max(-127, min(127, rem_y))
            self._send_raw_command(f'move {step_x} {step_y}', '虚拟 HID 鼠标移动失败')
            rem_x -= step_x
            rem_y -= step_y

    def scroll(self, vertical: int, horizontal: int = 0) -> None:
        """通过虚拟 HID 发送滚轮事件。"""
        rem_v = round(vertical)
        rem_h = round(horizontal)
        if rem_v == 0 and rem_h == 0:
            return
        while rem_v != 0 or rem_h != 0:
            step_v = max(-127, min(127, rem_v))
            step_h = max(-127, min(127, rem_h))
            self._send_raw_command(f'wheel {step_v} {step_h}', '虚拟 HID 鼠标滚轮操作失败')
            rem_v -= step_v
            rem_h -= step_h

    def nudge_cursor(self) -> None:
        """在当前光标位置发送微小 HID 相对位移并归位，使 PlayCover 同步当前光标位置。"""
        self.move_relative(-1, 0)
        self.move_relative(1, 0)

    def key_down(self, usage: int) -> None:
        """按住一个普通键。usage 是 HID 键盘用法，不是修饰键位。"""
        self._send_keyboard_command(f'key down {usage}', 0)

    def key_up(self, usage: int) -> None:
        """松开一个普通键。"""
        self._send_keyboard_command(f'key up {usage}', 0)

    def key_tap(self, usage: int, press_time: float) -> None:
        """点按一个普通键。"""
        duration_ms = min(60000, max(1, round(press_time * 1000)))
        self._send_keyboard_command(f'key tap {usage} {duration_ms}', duration_ms)

    def modifier_down(self, bit: int) -> None:
        """按住修饰键。bit 是报告里的单个修饰键位。"""
        self._send_keyboard_command(f'mod down {bit}', 0)

    def modifier_up(self, bit: int) -> None:
        """松开修饰键。"""
        self._send_keyboard_command(f'mod up {bit}', 0)

    def modifier_tap(self, bit: int, press_time: float) -> None:
        """点按修饰键。"""
        duration_ms = min(60000, max(1, round(press_time * 1000)))
        self._send_keyboard_command(f'mod tap {bit} {duration_ms}', duration_ms)

    def _send_keyboard_command(self, line: str, duration_ms: int) -> None:
        timeout = max(self.RESPONSE_TIMEOUT, duration_ms / 1000 + 5)
        self._send_raw_command(line, '虚拟 HID 键盘操作失败', timeout)

    def _send_raw_command(self, line: str, error_msg: str, timeout: float | None = None) -> None:
        with self._lock:
            if self._process.poll() is not None:
                raise RuntimeError('虚拟 HID 点击客户端已退出')
            if self._process.stdin is None:
                raise RuntimeError('虚拟 HID 点击客户端输入通道不可用')
            self._process.stdin.write(f'{line}\n')
            self._process.stdin.flush()
            response = self._read_line(self.RESPONSE_TIMEOUT if timeout is None else timeout)
            if response != 'OK':
                raise RuntimeError(response.removeprefix('ERROR ').strip() or error_msg)

    def _send_command(self, command: str, button: str, duration_ms: int) -> None:
        button_id = {'left': 1, 'right': 2, 'middle': 3}.get(button)
        if button_id is None:
            raise ValueError(f'不支持的 macOS 虚拟鼠标按键：{button}')

        with self._lock:
            if self._process.poll() is not None:
                raise RuntimeError('虚拟 HID 点击客户端已退出')
            if self._process.stdin is None:
                raise RuntimeError('虚拟 HID 点击客户端输入通道不可用')
            self._process.stdin.write(
                f'{command} {button_id} {duration_ms}\n'
            )
            self._process.stdin.flush()
            timeout = max(self.RESPONSE_TIMEOUT, duration_ms / 1000 + 5)
            response = self._read_line(timeout)
            if response != 'OK':
                raise RuntimeError(response.removeprefix('ERROR ').strip() or
                                   '虚拟 HID 鼠标操作失败')

    def close(self) -> None:
        """释放鼠标按键并关闭客户端进程。"""
        process = getattr(self, '_process', None)
        if process is None:
            return
        with self._lock:
            if process.poll() is not None:
                return

            if process.stdin is not None:
                try:
                    process.stdin.write('quit\n')
                    process.stdin.flush()
                except BrokenPipeError:
                    pass

            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=2)

    def _read_line(self, timeout: float) -> str:
        if self._process.stdout is None:
            raise RuntimeError('虚拟 HID 点击客户端输出通道不可用')

        with selectors.DefaultSelector() as selector:
            selector.register(self._process.stdout, selectors.EVENT_READ)
            if not selector.select(timeout):
                raise TimeoutError('等待虚拟 HID 点击客户端响应超时')
            response = self._process.stdout.readline()

        if not response:
            return_code = self._process.poll()
            raise RuntimeError(
                f'虚拟 HID 点击客户端意外退出，退出码：{return_code}'
            )
        return response.strip()
