#!/usr/bin/env python3
"""Lấy chat_id Telegram.
Cách dùng:  1) Mở bot của bạn trên điện thoại, bấm Start / gửi chữ "hi".
            2) python get_chat_id.py <BOT_TOKEN>
"""
import sys
import requests

if len(sys.argv) < 2:
    sys.exit(__doc__)
r = requests.get(f"https://api.telegram.org/bot{sys.argv[1]}/getUpdates", timeout=30).json()
if not r.get("ok"):
    sys.exit(f"Lỗi: {r}")
seen = {}
for u in r.get("result", []):
    m = u.get("message") or u.get("channel_post") or u.get("my_chat_member", {})
    chat = m.get("chat") if m else None
    if chat:
        seen[chat["id"]] = chat.get("title") or chat.get("first_name") or chat.get("username")
if not seen:
    print("Chưa thấy tin nhắn nào. Hãy nhắn cho bot một tin rồi chạy lại.")
for cid, name in seen.items():
    print(f"chat_id = {cid}   ({name})")
