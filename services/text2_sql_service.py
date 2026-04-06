import io
import json
import logging
from datetime import datetime

import duckdb
import pandas as pd
import requests
from sqlalchemy import text

from common.date_util import DateEncoder
from common.exception import MyException
from common.minio_util import MinioUtils
from common.sql_security import validate_read_only_sql
from constants.code_enum import SysCodeEnum as SysCode
from model.db_connection_pool import get_db_pool

logger = logging.getLogger(__name__)

pool = get_db_pool()


def _validate_or_raise(sql: str, dialect: str | None = None) -> None:
    is_allowed, security_error = validate_read_only_sql(sql, dialect=dialect)
    if not is_allowed:
        sql_preview = sql.replace("\n", " ")[:200]
        logger.warning("SQL 安全校验失败: %s | sql=%s", security_error, sql_preview)
        raise ValueError(security_error)


def query_ex(query: str) -> dict:
    """
    Execute SQL and return column desc and result
    Args:
        query SQL query to run
    Returns:
        dict: {"column":[],result:[]}
    """
    logger.info(f"query_sql: {query}")
    if not query:
        return {"column": [], "result": []}

    _validate_or_raise(query)

    try:
        with pool.get_session() as session:
            result = session.execute(text(query))
            rows = result.fetchall()
            columns = list(result.keys())

            # 将查询结果转换为指定格式
            result_list = []
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    if isinstance(value, datetime):
                        value = value.strftime("%Y-%m-%d %H:%M:%S")
                    row_dict[col] = value
                result_list.append(row_dict)

            return {"column": columns, "result": result_list}
    except Exception as e:
        logger.error(f"query_ex error query_sql: {query},{e}")
        return None


def get_multiple_tables_column_comments(tables, dbname="dap") -> dict:
    """
    获取mysql表schema信息
    Args:
        tables 表名称列表
        dbname 数据库名称
    Return:
        {
          "schema": [
            {
              "tableName": "table_1",
              "schema": [
                {
                  "column": "name",
                  "comment": "姓名"
                }
              ]
            }
          ]
        }
    """
    try:
        result_data = {"schema": []}
        with pool.get_session() as session:
            for table in tables:
                # 查询每个表的列信息及注释
                sql = f"""
                        SELECT COLUMN_NAME AS `column`, COLUMN_COMMENT AS `comment`
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_SCHEMA = '{dbname}' AND TABLE_NAME = '{table}';
                        """
                result = session.execute(text(sql))
                rows = result.fetchall()
                columns = list(result.keys())

                # 获取查询结果并构造字典
                columns_info = []
                for row in rows:
                    col_dict = {}
                    for i, col in enumerate(columns):
                        col_dict[col] = row[i]
                    columns_info.append({"column": col_dict["column"], "comment": col_dict["comment"]})

                # 将当前表的列信息添加到结果数据中
                result_data["schema"].append({"tableName": table, "schemaData": columns_info})

        return result_data
    except Exception as e:
        logger.error(f"get_multiple_tables_column_comments error {e}")
        return {"schema": []}


async def exe_sql_query(model_out_str):
    """
    执行大模型解析出的sql语句并返回结果集
    Args:
        model_out_text 大模型输出信息
    Return:
    """

    if model_out_str:
        try:
            # 尝试按'\n\n'分割，如果没有'\n\n'则直接使用原始字符串
            model_out_json = model_out_str.split("\n\n")[-1] if "\n\n" in model_out_str else model_out_str
            model_out_json = model_out_json.strip("```json\n").strip("\n```")
            if not isinstance(model_out_json, dict):
                model_out_json = json.loads(model_out_json)
            sql = model_out_json["sql"]
            if sql:
                result = query_ex(sql)
                table_schema_dict = get_multiple_tables_column_comments(["view_alarm_detail"])
                table_schema_dict["llm"] = model_out_json
                table_schema_dict["data"] = result
                return json.dumps(table_schema_dict, ensure_ascii=False, cls=DateEncoder)
            else:
                logger.error("数据应答大模型返回SQL语句为空")
                raise MyException(SysCode.c_9999)
        except Exception as e:
            logger.error(f"数据应答处理失败: {model_out_str} {e}")
            raise MyException(SysCode.c_9999)
    else:
        logger.error("数据应答大模型返回结果为空")
        raise MyException(SysCode.c_9999)


async def exe_file_sql_query(file_key, model_out_str):
    """
    文件问答: 执行大模型解析出的SQL语句并返回结果集

    Args:
        file_key (str): 文件key
        model_out_str (str): 大模型输出信息

    Returns:
        dict: {"column":[], "result":[]}

    Raises:
        MyException: 当文件问答大模型返回结果为空或SQL语句为空时抛出异常
    """
    if not model_out_str:
        logger.error("文件问答大模型返回结果为空")
        raise MyException(SysCode.c_9999)

    try:
        # 获取文件URL
        file_url = MinioUtils().get_file_url_by_key(object_key=file_key)
        extension = file_key.split(".")[-1].lower()

        # 根据文件类型读取数据
        if extension in ["xlsx", "xls"]:
            response = requests.get(file_url)
            df = pd.read_excel(io.BytesIO(response.content), engine="openpyxl")
        elif extension == "csv":
            df = pd.read_csv(file_url)
        else:
            logger.error(f"不支持的文件扩展名: {extension}")
            raise MyException(SysCode.c_9999)

        # 连接到DuckDB (这里使用内存数据库) 并注册DataFrame
        con = duckdb.connect(database=":memory:")
        con.register("excel_table", df)

        # 解析模型输出并获取SQL语句
        model_out_json = json.loads(model_out_str)
        sql = model_out_json.get("sql", "").replace("`", "")  # 移除反引号以避免SQL语法错误

        if not sql.strip():
            logger.error("文件问答大模型返回SQL语句为空")
            raise MyException(SysCode.c_9999)

        _validate_or_raise(sql, dialect="duckdb")

        # 执行SQL查询
        cursor = con.execute(sql)

        # 获取列名称和查询结果的数据行
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()

        # 构建结果字典
        result = [dict(zip(columns, row)) for row in rows]

        return json.dumps(
            {"llm": model_out_json, "data": {"column": columns, "result": result}}, ensure_ascii=False, cls=DateEncoder
        )

    except Exception as e:
        logger.error(f"文件问答处理失败: {model_out_str}, Error: {e}")
        raise MyException(SysCode.c_9999)
