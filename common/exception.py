from constants.code_enum import SysCodeEnum


class MyException(Exception):
    """
    自定义异常
    """

    def __init__(self, ex_code: SysCodeEnum):
        super().__init__(f"{ex_code.name}({ex_code.value[0]})")

        self.code, self.message, self.detail = (
            ex_code.value[0],
            ex_code.value[1],
            ex_code.value[2],
        )

    def __str__(self):
        return f"MyException: " f"code: {self.code}, " f"message: {self.message} - " f"detail: {self.detail}"

    def to_dict(self):
        """

        :return:
        """
        return {"code": self.code, "message": self.message}
