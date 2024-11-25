import requests
import json

url = "http://172.16.1.131:8088/llm/process_llm_out"
params = {
    "question": "诈骗金额最高的前十条数据"
}
headers = {
    "Content-Type": "application/json"
}
data = {
    "thoughts": "用户希望查询诈骗金额最高的前十条数据。根据提供的表结构定义，我们可以从`view_alarm_detail`表中选择`涉案资金`字段，并按其降序排>列，取前10条记录。这里使用`response_table`展示方式，因为它适合展示多列数据。",
    "sql": "SELECT * FROM view_alarm_detail ORDER BY `涉案资金` DESC LIMIT 10;",
    "type": "response_table",
    "status": "0"
}

response = requests.post(url, headers=headers, params=params, data=json.dumps(data))

print(response.status_code)
print(response.json())


{'code': 9999, 'msg': '系统异常', 'data': None}