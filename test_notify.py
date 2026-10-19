#!/usr/bin/env python3
"""Gửi thử một tin nhắn để kiểm tra cấu hình Telegram/ntfy trong config.yaml."""
import logging
from main import Notifier, load_config, BASE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
cfg = load_config(BASE_DIR / "config.yaml")
n = Notifier(cfg)
ok = n.send_blocking("🧪 Tin nhắn thử từ hệ thống phát hiện cháy. Nếu bạn đọc được tin này là cấu hình đúng!")
print("THÀNH CÔNG ✅" if ok else "THẤT BẠI ❌ - xem lỗi phía trên")
