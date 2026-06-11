import requests
import json


def send_custom_message(webhook_url, title, text):
    """
    发送微信消息
    
    参数:
    - webhook_url: 自定义Webhook地址
    - title: 消息标题
    - text: 消息内容
    """
    headers = {'Content-Type': 'application/json'}
    data = {
        "title": title,
        "content": text
    }
    try:
        response = requests.post(
            url=webhook_url,
            headers=headers,
            data=json.dumps(data)
        )
        print(response.text)
        # 自定义 webhook 以 HTTP 2xx 视为发送成功
        return 200 <= response.status_code < 300
    except Exception as e:
        print('自定义webhook通知发送失败', e)
        return False