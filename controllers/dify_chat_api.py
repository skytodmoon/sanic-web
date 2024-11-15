import logging

from sanic import Blueprint
from sanic.response import ResponseStream

from common.exception import MyException
from common.token_decorator import check_token
from constants.code_enum import SysCodeEnum
from services.dify_service import DiFyRequest

bp = Blueprint("fiFyApi", url_prefix="/dify")

dify = DiFyRequest()


@bp.post("/get_answer")
@check_token
async def get_answer(req):
    """
        调用diFy画布获取数据流式返回
    :param req:
    :return:
    """

    try:
        response = ResponseStream(dify.exec_query, content_type="text/event-stream")
        return response
    except Exception as e:
        logging.error(f"Error Invoke diFy: {e}")
        raise MyException(SysCodeEnum.c_9999)
