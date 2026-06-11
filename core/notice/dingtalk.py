import requests
import json
def send_dingtalk_message(webhook_url, title, text, is_at_all=False, at_mobiles=[]):
    """
    发送Markdown格式消息
    
    参数:
    - webhook_url: 机器人Webhook地址
    - title: 消息标题
    - text: Markdown格式内容
    - is_at_all: 是否@所有人
    - at_mobiles: 要@的手机号列表
    """
    headers = {'Content-Type': 'application/json'}
    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text
        },
        "at": {
            "atMobiles": at_mobiles,
            "isAtAll": is_at_all
        }
    }
    try:
        response = requests.post(
            url=webhook_url,
            headers=headers,
            data=json.dumps(data)
        )
        print(response.text)
        # 钉钉返回 {"errcode":0,"errmsg":"ok"} 表示发送成功
        try:
            result = response.json()
        except Exception:
            return False
        return result.get('errcode') == 0
    except Exception as e:
        print('通知发送失败', e)
        return False
# 使用示例
# markdown_text = """### 项目状态报告  
# - **项目名称**: XX系统升级  
# - **当前状态**: ✅正常运行  
# - **异常情况**: 无  
# - [查看详情](http://example.com)  
# """
# webhook="https://oapi.dingtalk.com/robot/send?access_token=xxx"
# send_dingtalk_markdown(webhook, "项目状态通知", markdown_text)
