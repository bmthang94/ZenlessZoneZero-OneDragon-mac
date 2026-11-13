import argparse
import ast
import os
import re
import struct
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parents[3]
CJK = re.compile(r'[㐀-䶿一-鿿豈-﫿\U00020000-\U0002fa1f]')
SETTERS = {'setText', 'setToolTip', 'setPlaceholderText', 'setWindowTitle'}
TEXT_WIDGETS = {'QPushButton', 'PushButton', 'PrimaryPushButton', 'QLabel', 'SettingCardGroup'}


def literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def argument(call: ast.Call, position: int, name: str) -> ast.expr | None:
    if len(call.args) > position:
        return call.args[position]
    return next((item.value for item in call.keywords if item.arg == name), None)


def callable_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def scan_source(root: Path) -> tuple[list[tuple[Path, int, str]], list[str]]:
    """收集可静态确定的翻译键和直接赋值的界面文字。"""
    keys: list[tuple[Path, int, str]] = []
    errors: list[str] = []
    for path in sorted((root / 'src').rglob('*.py')):
        relative = path.relative_to(root)
        if relative.parts[:3] == ('src', 'one_dragon_qt', 'demo'):
            continue
        widget_file = relative.parts[:2] in (('src', 'one_dragon_qt'), ('src', 'zzz_od')) and (
            relative.parts[:2] == ('src', 'one_dragon_qt') or relative.parts[:3] == ('src', 'zzz_od', 'gui')
        )
        try:
            tree = ast.parse(path.read_bytes(), filename=str(relative))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f'{relative}: 无法解析: {exc}')
            continue
        for node in ast.walk(tree):
            value: str | None = None
            if isinstance(node, ast.Call):
                name = callable_name(node.func)
                if name == 'gt':
                    model = argument(node, 1, 'model')
                    if model is None or literal(model) == 'ui':
                        value = literal(argument(node, 0, 'msg'))
                elif name == 'ConfigItem':
                    value = literal(argument(node, 0, 'label'))
                elif widget_file and name in SETTERS:
                    for arg in [*node.args, *(item.value for item in node.keywords)]:
                        text = literal(arg)
                        if text is not None and CJK.search(text):
                            errors.append(f'{relative}:{node.lineno}: {name} 直接使用中文: {text!r}')
                if (widget_file and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == 'QFileDialog'
                        and name is not None and name.startswith('get')):
                    text = literal(argument(node, 1, 'caption'))
                    if text is not None and CJK.search(text):
                        errors.append(f'{relative}:{node.lineno}: {name} 标题直接使用中文: {text!r}')
                if widget_file and name in TEXT_WIDGETS:
                    candidates = [*node.args, *(item.value for item in node.keywords if item.arg == 'text')]
                    for candidate in candidates:
                        text = literal(candidate)
                        if text is not None and CJK.search(text):
                            errors.append(f'{relative}:{node.lineno}: {name} 直接使用中文: {text!r}')
                if widget_file:
                    for item in node.keywords:
                        is_navigation = item.arg == 'nav_text_cn'
                        is_card_text = name is not None and (
                            (name.endswith('SettingCard') and item.arg in {'title', 'content'})
                            or (name in {'PushSettingCard', 'HelpCard'} and item.arg in {'text', 'title', 'content'})
                        )
                        text = literal(item.value)
                        if (is_navigation or is_card_text) and text is not None and CJK.search(text):
                            keys.append((relative, node.lineno, text))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(target, ast.Name) and target.id in {'APP_NAME', 'ONE_DRAGON_APP_NAME'}
                       for target in targets):
                    value = literal(node.value)
            if value is not None and CJK.search(value):
                keys.append((relative, node.lineno, value))
    return keys, errors


def check_ui_translations(lang: str = 'en', root: Path = ROOT) -> list[str]:
    """检查界面翻译键及编译后的语言文件。"""
    errors: list[str] = []
    if not re.fullmatch(r'[A-Za-z0-9_-]+', lang):
        return [f'无效语言名称: {lang!r}']
    po_path = root / 'assets' / 'text' / 'ui' / f'{lang}.po'
    mo_path = root / 'assets' / 'text' / 'output' / lang / 'LC_MESSAGES' / 'ui.mo'
    keys, errors = scan_source(root)
    try:
        po = polib.pofile(str(po_path))
    except (OSError, ValueError, UnicodeError) as exc:
        return errors + [f'{po_path}: 无法读取 PO: {exc}']
    entries = {entry.msgid: entry for entry in po if not entry.obsolete and entry.msgctxt is None}
    for path, line, key in keys:
        entry = entries.get(key)
        if entry is None or not entry.msgstr.strip() or entry.msgstr == key or 'fuzzy' in entry.flags:
            errors.append(f'{path}:{line}: 缺少有效翻译: {key!r}')
    try:
        mo = polib.mofile(str(mo_path))
    except (OSError, ValueError, UnicodeError, IndexError, struct.error) as exc:
        return errors + [f'{mo_path}: 无法读取 MO: {exc}']
    compiled = {(entry.msgctxt, entry.msgid): entry for entry in mo}
    expected = {(entry.msgctxt, entry.msgid): entry for entry in po.translated_entries()}
    for identity, entry in expected.items():
        actual = compiled.get(identity)
        if actual is None or actual.msgstr != entry.msgstr or dict(actual.msgstr_plural) != dict(entry.msgstr_plural):
            errors.append(f'{mo_path}: 与 PO 不一致: {entry.msgid!r}')
    for identity in compiled.keys() - expected.keys():
        if identity[1]:
            errors.append(f'{mo_path}: PO 中不存在有效翻译: {identity[1]!r}')
    return errors


def check_widgets(lang: str) -> list[str]:
    """离屏验证实际设置卡片使用当前语言。"""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    try:
        from PySide6.QtWidgets import QApplication

        from one_dragon.utils import i18_utils
        from one_dragon_qt.widgets.setting_card.setting_card_base import SettingCardBase

        app = QApplication.instance() or QApplication([])
        old_lang = i18_utils.get_default_lang()
        try:
            i18_utils.update_default_lang(lang)
            card = SettingCardBase(None, '设置', '游戏助手')
            errors = []
            if lang == 'en' and card.titleLabel.text() != 'Settings':
                errors.append(f'设置卡片标题应为 Settings，实际为 {card.titleLabel.text()!r}')
            if card.contentLabel.text() == '游戏助手':
                errors.append(f'设置卡片内容未翻译: {card.contentLabel.text()!r}')
            card.deleteLater()
            app.processEvents()
            return errors
        finally:
            i18_utils.update_default_lang(old_lang)
    except Exception as exc:
        return [f'无法检查界面组件: {exc}']


def main() -> int:
    parser = argparse.ArgumentParser(description='检查界面翻译和编译文件')
    parser.add_argument('--lang', default='en', help='语言名称，默认为 en')
    parser.add_argument('--widgets', action='store_true', help='同时离屏检查设置卡片')
    args = parser.parse_args()
    errors = check_ui_translations(args.lang)
    if args.widgets:
        errors.extend(check_widgets(args.lang))
    for error in errors:
        print(error)
    if errors:
        print(f'共发现 {len(errors)} 个问题')
        return 1
    print(f'{args.lang} 界面翻译检查通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
