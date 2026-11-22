from concurrent.futures import Future

from one_dragon.utils.i18_utils import gt
from one_dragon.utils.log_utils import log


def handle_future_result(future: Future):
    try:
        future.result()
    except Exception:
        log.error(gt('异步执行失败', model='log'), exc_info=True)
