from one_dragon.utils.i18_utils import gt, update_default_lang
from zzz_od.application.battle_assistant.operation_template_config import (
    get_operation_template_config_list,
)


def test_localization():
    # 1. Test Chinese (zh)
    update_default_lang('zh')

    dialog_intro_zh = "为了让您的自动战斗体验更加顺畅"
    assert dialog_intro_zh in gt("为了让您的自动战斗体验更加顺畅，这里有一些温馨的小建议给到您：\n\n1. 关于画面设置：建议您将游戏帧数限制在 30 帧，并适当降低画质设置。如果您的电脑配置非常强大，尝试 60 帧也是可以的，但请务必不要开启「无限帧率」哦。\n\n2. 释放电脑性能：自动战斗功能依托于 AI 视觉识别技术，需要消耗一定的计算资源。建议您在使用时尽量关闭不必要的后台程序，电脑运行越流畅，AI 的表现也会越出色。\n\n3. 截图间隔设置：为了不让 AI 错过每一个精彩瞬间，请确保截图频率至少达到每秒 20 次。毕竟，我们不能强求 AI 在 1 帧的画面里完成电竞级的操作呀。\n\n4. 按键设置建议：强烈建议您将连携技的「左」、「右」和「取消」设置为独立的按键，避免与普攻、闪避或终结技共用键位。特别需要强调的是，几乎所有的连携技释放错误都源自于使用了同一个按键。默认键位下，连携技出现时很容易被普攻误触，导致操作失误，分开设置会让战斗更精准。\n\n比如把连携左设置为1，连携右设置为3，取消设置为2\n\n5. 应对特殊情况：目前的 AI 还在学习中，暂时无法完美应对 BOSS 的转阶段或特殊状态攻击。遇到这种情况时，可能需要您稍微费心，暂停自动战斗并手动应对一下。\n\n6. 最佳显示环境：为了保证识别准确，请将游戏分辨率设置为 1920x1080，并关闭 HDR 功能。同时，请确保游戏画面没有被其他窗口遮挡，让 AI 能看清全局。\n\n祝您游戏愉快！")

    assert gt("安比-3A特殊攻击") == "安比-3A特殊攻击"
    assert gt("安比–3A特殊攻击") == "安比–3A特殊攻击"
    assert gt("11号-支援攻击") == "11号-支援攻击"
    assert gt("11号–支援攻击") == "11号–支援攻击"
    print("Chinese (zh) verified successfully!")

    # 2. Test English (en)
    update_default_lang('en')

    dialog_en = gt("为了让您的自动战斗体验更加顺畅，这里有一些温馨的小建议给到您：\n\n1. 关于画面设置：建议您将游戏帧数限制在 30 帧，并适当降低画质设置。如果您的电脑配置非常强大，尝试 60 帧也是可以的，但请务必不要开启「无限帧率」哦。\n\n2. 释放电脑性能：自动战斗功能依托于 AI 视觉识别技术，需要消耗一定的计算资源。建议您在使用时尽量关闭不必要的后台程序，电脑运行越流畅，AI 的表现也会越出色。\n\n3. 截图间隔设置：为了不让 AI 错过每一个精彩瞬间，请确保截图频率至少达到每秒 20 次。毕竟，我们不能强求 AI 在 1 帧的画面里完成电竞级的操作呀。\n\n4. 按键设置建议：强烈建议您将连携技的「左」、「右」和「取消」设置为独立的按键，避免与普攻、闪避或终结技共用键位。特别需要强调的是，几乎所有的连携技释放错误都源自于使用了同一个按键。默认键位下，连携技出现时很容易被普攻误触，导致操作失误，分开设置会让战斗更精准。\n\n比如把连携左设置为1，连携右设置为3，取消设置为2\n\n5. 应对特殊情况：目前的 AI 还在学习中，暂时无法完美应对 BOSS 的转阶段或特殊状态攻击。遇到这种情况时，可能需要您稍微费心，暂停自动战斗并手动应对一下。\n\n6. 最佳显示环境：为了保证识别准确，请将游戏分辨率设置为 1920x1080，并关闭 HDR 功能。同时，请确保游戏画面没有被其他窗口遮挡，让 AI 能看清全局。\n\n祝您游戏愉快！")
    assert "To make your auto battle experience smoother" in dialog_en
    assert "1. Graphics Settings:" in dialog_en
    assert "6. Optimal Display Environment:" in dialog_en

    # Presets
    anby_1 = gt("安比-3A特殊攻击")
    anby_2 = gt("安比–3A特殊攻击")
    soldier_1 = gt("11号-支援攻击")
    soldier_2 = gt("11号–支援攻击")

    print(f"安比-3A特殊攻击 -> {anby_1}")
    print(f"安比–3A特殊攻击 -> {anby_2}")
    print(f"11号-支援攻击 -> {soldier_1}")
    print(f"11号–支援攻击 -> {soldier_2}")

    assert anby_1 == "Anby - 3A Special Attack"
    assert anby_2 == "Anby - 3A Special Attack"
    assert soldier_1 == "Soldier 11 - Assist Attack"
    assert soldier_2 == "Soldier 11 - Assist Attack"

    # Custom preset preservation
    custom = gt("MyCustomPreset_123")
    assert custom == "MyCustomPreset_123"

    # Verify dropdown ConfigItems in English
    items = get_operation_template_config_list()
    anby_item = next(it for it in items if "安比-3A特殊攻击" in it.value)
    assert anby_item.value == "安比-3A特殊攻击", "Raw value must be preserved"
    assert anby_item.ui_text == "Anby - 3A Special Attack", "UI text must be localized in English"

    soldier_item = next(it for it in items if "11号-支援攻击" in it.value)
    assert soldier_item.value == "11号-支援攻击", "Raw value must be preserved"
    assert soldier_item.ui_text == "Soldier 11 - Assist Attack", "UI text must be localized in English"

    print("All English (en) verifications passed successfully!")

if __name__ == "__main__":
    test_localization()
