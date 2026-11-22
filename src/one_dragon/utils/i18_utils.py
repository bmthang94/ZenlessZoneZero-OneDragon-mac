import gettext
import locale
import os

from one_dragon.utils import os_utils

_gt = {}
_default_lang = 'zh'


def detect_language():
    """自动检测系统语言"""
    try:
        system_locale = locale.getdefaultlocale()[0]
        if system_locale and system_locale.startswith('zh'):
            return 'zh'
        else:
            return 'en'
    except Exception:
        return 'zh'


def detect_and_set_default_language():
    """
    检测系统语言并设置为默认语言
    :return:
    """
    return update_default_lang(detect_language())


def resolve_ui_language(ui_language: str) -> str:
    """把界面语言配置解析成具体语言代码。

    ``auto`` 跟随系统语言，其余情况直接使用配置的语言代码。
    """
    from one_dragon.base.config.custom_config import UILanguageEnum
    if ui_language == UILanguageEnum.AUTO.value.value:
        return detect_language()
    return ui_language


def apply_ui_language(ui_language: str) -> str:
    """解析界面语言配置并应用为全局默认语言。

    :param ui_language: ``custom.yml`` 中的 ``ui_language`` 配置值
    :return: 实际生效的语言代码
    """
    lang = resolve_ui_language(ui_language)
    update_default_lang(lang)
    return lang

def get_translations(model: str, lang: str, install: bool = True):
    """
    加载语言
    :param model: 模块 将ocr 界面 日志等翻译区分开来
    :param lang: 语言
    :param install: 是否把该翻译注册为全局 gettext 函数 日志翻译只供内部查询 不注册
    :return:
    """
    translate_path = os_utils.get_resource_path('assets', 'text', 'output')
    lang_dir = os.path.join(translate_path, lang, 'LC_MESSAGES', f'{model}.mo')
    # 未有对应的文本mo文件
    if not os.path.exists(lang_dir):
        return None
    gettext.bindtextdomain(model, translate_path)
    translation = gettext.translation(model, localedir=translate_path, languages=[lang])
    if install:
        # 注册翻译函数为全局函数
        translation.install()
    return translation


def gt(msg: str | None, model: str = 'ui', lang: str | None = None) -> str:
    if msg is None or len(msg) == 0:
        return ''
    if lang is None:
        lang = _default_lang
    if model not in _gt:
        _gt[model] = {}
    if lang not in _gt[model]:
        _gt[model][lang] = get_translations(model, lang, install=model != 'log')

    trans = _gt[model][lang]
    return trans.gettext(msg) if trans is not None else msg


def coalesce_gt(msg: str | None, default: str, model: str = 'ui', lang: str | None = None) -> str:
    """
    带有默认值的获取多语言
    :param msg: 原字符串
    :param default: 默认值
    :param model:
    :param lang:
    :return:
    """
    if lang is None:
        lang = _default_lang
    return gt(msg if msg is not None else default, model, lang)


def update_default_lang(lang: str):
    global _default_lang
    _default_lang = lang


def get_default_lang() -> str:
    """
    获取默认语言
    :return:
    """
    global _default_lang
    return _default_lang
