#!/usr/bin/env python3
"""Lấy chat_id của Zalo Bot.
Cách dùng:  1) Mở Zalo, tìm bot của bạn và nhắn 1 tin bất kỳ (ví dụ "hi").
            2) python get_zalo_chat_id.py <ZALO_BOT_TOKEN>
(Chạy xong tin nhắn đầu tiên bot nhận được sẽ in ra chat_id. Nhắn tin TRƯỚC hoặc NGAY SAU khi chạy lệnh,
 lệnh chờ tối đa ~2 phút.)
"""
import sys
import requests

BASE = "https://bot-api.zaloplatforms.com"


def find_chat_id(obj):
    if isinstance(obj, dict):
        chat = obj.get("chat")
        if isinstance(chat, dict) and chat.get("id"):
            return chat["id"]
        for v in obj.values():
            r = find_chat_id(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_chat_id(v)
            if r:
                return r
    return None


if len(sys.argv) < 2:
    sys.exit(__doc__)
tok = sys.argv[1]
# getUpdates không dùng được nếu đang đặt webhook -> xoá webhook trước
try:
    requests.post(f"{BASE}/bot{tok}/deleteWebhook", timeout=20)
except Exception:
    pass
for i in range(4):
    print(f"Đang chờ tin nhắn từ Zalo... ({i + 1}/4)")
    try:
        r = requests.post(f"{BASE}/bot{tok}/getUpdates", json={"timeout": "30"}, timeout=45)
    except requests.RequestException as e:
        print("Lỗi mạng:", e)
        continue
    data = r.json() if r.content else {}
    if r.status_code == 401 or data.get("ok") is False and data.get("error_code") == 401:
        sys.exit("Token sai (401). Kiểm tra lại token.")
    cid = find_chat_id(data.get("result"))
    if cid:
        print(f"\nchat_id = {cid}")
        sys.exit(0)
print("Không nhận được tin nhắn. Hãy nhắn cho bot trên Zalo rồi chạy lại.")
print("Phản hồi cuối cùng của server:", data)
