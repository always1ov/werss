import requests
import json


def send_wechat_message(webhook_url, title, text):
    """
    发送微信消息
    
    参数:
    - webhook_url: 微信机器人Webhook地址
    - title: 消息标题
    - text: 消息内容
    """
    # 截取 text 确保字符数不超过 4096 个
    text = text[:2048]
    headers = {'Content-Type': 'application/json'}
    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"{text}"
        }
    }
    try:
        response = requests.post(
            url=webhook_url,
            headers=headers,
            data=json.dumps(data)
        )
        print(response.text)
        # 企业微信返回 {"errcode":0,"errmsg":"ok"} 表示发送成功
        try:
            result = response.json()
        except Exception:
            return False
        return result.get('errcode') == 0
    except Exception as e:
        print('微信通知发送失败', e)
        return False