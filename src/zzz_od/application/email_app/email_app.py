from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_notify import NotifyTiming, node_notify
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from zzz_od.application.email_app import email_app_const
from zzz_od.application.zzz_application import ZApplication
from zzz_od.context.zzz_context import ZContext
from zzz_od.operation.back_to_normal_world import BackToNormalWorld


class EmailApp(ZApplication):

    """邮件:自动领取游戏内未读邮件奖励(菲林/材料)。无消耗。"""

    def __init__(self, ctx: ZContext):
        """
        每天自动接收邮件奖励
        """
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=email_app_const.APP_ID,
            op_name=email_app_const.APP_NAME,
        )

    def handle_init(self) -> None:
        """
        执行前的初始化 由子类实现
        注意初始化要全面 方便一个指令重复使用
        """
        pass

    @operation_node(name='打开邮件', is_start_node=True)
    def goto_email(self) -> OperationRoundResult:
        result = self.round_by_goto_screen(screen_name='邮件')
        if result.is_success:
            return result
        if not result.is_fail and self.ctx.screen_loader.current_screen_name is not None:
            return self.round_wait(result.status, wait=1)

        # 无法直接从当前画面前往邮件（如上一任务停留在地图等子画面），先统一返回大世界
        op = BackToNormalWorld(self.ctx)
        op_result = op.execute()
        if op_result.success:
            return self.round_retry(status='返回大世界后重试', wait=1)
        return result

    @node_from(from_name='打开邮件')
    @node_notify(when=NotifyTiming.CURRENT_SUCCESS)
    @operation_node(name='全部领取')
    def click_get_all(self) -> OperationRoundResult:
        """
        邮件画面 点击全部领取
        就算时灰色的也能识别到
        :return:
        """
        return self.round_by_find_and_click_area(self.last_screenshot, '邮件', '全部领取', success_wait=1, retry_wait=1)

    @node_from(from_name='全部领取')
    @operation_node(name='确认')
    def click_confirm(self) -> OperationRoundResult:
        """
        邮件画面 领取后点击确认
        :return:
        """
        screen = self.screenshot()
        if screen is None:
            return self.round_fail(status='Unable to verify the confirmation screen')
        ocr_result_list = self.ctx.ocr_service.get_ocr_result_list(
            image=screen,
        )
        screen_text = ''.join(
            ''.join(result.data.split()) for result in ocr_result_list
        )
        if any(
            warning in screen_text
            for warning in ('确认删除', '确定删除', '是否删除', '删除')
        ):
            return self.round_fail(status='Delete-related text detected; confirmation stopped')

        target_word_list = [
            '确认',  # 正常领取的情况
            '确定',  # 某种物品爆满了
        ]
        return self.round_by_ocr_and_click_by_priority(
            target_cn_list=target_word_list,
            screen=screen,
            success_wait=1,
            retry_wait=1,
        )

    @node_from(from_name='确认')  # 确认之后返回
    @node_from(from_name='确认', success=False)  # 无弹窗确认（已领取过）时也返回菜单
    @operation_node(name='返回菜单')
    def back_to_menu(self) -> OperationRoundResult:
        """
        返回菜单
        领取后的确认按钮可以不按 直接点击外层也可以返回
        :return:
        """
        return self.round_by_find_and_click_area(self.last_screenshot, '邮件', '按钮-返回', success_wait=1, retry_wait=1)

    @node_from(from_name='返回菜单')
    @node_from(from_name='返回菜单', success=False)
    @operation_node(name='返回大世界')
    def back_to_world(self) -> OperationRoundResult:
        op = BackToNormalWorld(self.ctx)
        return self.round_by_op_result(op.execute())
