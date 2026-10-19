# Hệ thống phát hiện cháy (YOLOv8 `best.pt`)

```
 Điện thoại (camera)  --Wi-Fi LAN-->  Máy tính chạy server (main.py + best.pt)
                                           │ phát hiện cháy
                                           ▼
                              Internet → Telegram / ntfy → Điện thoại KHÁC (4G, mạng khác)
```
Model của bạn có 3 class: `fire`, `human`, `smoke`. Mặc định chỉ **lửa (fire)** mới gây báo động.

## 1. Cài đặt (Windows / Linux / macOS)
1. Cài **Python 3.9 – 3.12**.
2. Chép `best.pt` vào thư mục `models/` (đường dẫn `models/best.pt`).
3. *(Nếu có card NVIDIA)* nên cài PyTorch bản CUDA trước theo https://pytorch.org rồi mới chạy bước dưới, để AI chạy nhanh hơn rất nhiều. Không có GPU vẫn chạy được trên CPU (đặt `process_fps` thấp, ví dụ 2–5).

## 2. Biến điện thoại thành camera
Cài app trên điện thoại gắn ở vị trí cần giám sát, **cùng Wi-Fi với máy tính**:

| App | Link điền vào `camera.source` |
|---|---|
| Android – **IP Webcam** (bấm "Start server") | `http://IP_DIEN_THOAI:8080/video` |
| Android/iPhone – **DroidCam** | `http://IP_DIEN_THOAI:4747/video` |
| iPhone – app RTSP/IP camera bất kỳ | `rtsp://IP:PORT/...` |

Kiểm tra link: mở thử trên trình duyệt máy tính, thấy hình là được. Sau đó dán vào `config.yaml` → `camera.source`.
Mẹo: cắm sạc điện thoại, bật chế độ không tắt màn hình, đặt IP tĩnh cho điện thoại trong router.

## 3. Tạo kênh nhận tin trên điện thoại ở xa (Telegram – miễn phí)
1. Trên điện thoại nhận tin, cài **Telegram**, tìm **@BotFather** → gửi `/newbot` → đặt tên → nhận **BOT TOKEN**.
2. Mở bot vừa tạo, bấm **Start** (hoặc gửi "hi").
3. Trên máy tính chạy: `python get_chat_id.py <BOT_TOKEN>` → nhận **chat_id**.
   (Muốn nhiều người cùng nhận: mỗi người nhắn cho bot rồi thêm chat_id của họ, hoặc tạo nhóm, thêm bot vào nhóm.)
4. Điền vào `config.yaml`:
   ```yaml
   telegram:
     enabled: true
     bot_token: "123456:ABC..."
     chat_ids: ["123456789"]
   ```
5. Thử: `python test_notify.py` → điện thoại phải nhận được tin.

Máy tính chỉ cần **có Internet đi ra** – không cần mở port, không cần IP tĩnh, điện thoại nhận tin có thể ở bất kỳ nơi nào.
Tuỳ chọn dự phòng: bật `ntfy` trong config, cài app **ntfy** trên điện thoại và subscribe đúng topic.

## 4. Chạy
- Windows: bấm đúp **`run.bat`** (lần đầu tự tạo môi trường và cài thư viện).
- Linux/macOS: `./run.sh`
- Thủ công: `pip install -r requirements.txt` rồi `python main.py`

Tuỳ chọn dòng lệnh: `--source "http://..."` (ghi đè camera), `--show` (hiện cửa sổ xem), `--no-web`.
Test không cần camera: `python main.py --source video_chay.mp4 --show`

Xem trực tiếp trong LAN: `http://<IP-máy-tính>:5000` (đừng mở port này ra Internet vì không có mật khẩu).

## 5. Chống báo động giả (chỉnh trong `config.yaml`)
- `fire_conf`: ngưỡng tin cậy (tăng lên 0.6–0.7 nếu báo nhầm nhiều).
- `window_seconds` + `min_hits`: phải thấy lửa ≥ `min_hits` lần trong `window_seconds` giây mới báo (mặc định 8 lần / 5 giây).
- `cooldown_seconds`: sau khi báo, im lặng 120 giây rồi mới báo lại nếu vẫn cháy.
- Muốn báo cả khi có khói: `alert_classes: ["fire", "smoke"]`.
- Hệ thống cũng tự nhắn khi **mất kết nối camera** quá 60 giây và khi **khởi động**.
- Ảnh lúc phát hiện được lưu trong thư mục `alerts/`.

## 6. Chạy tự động khi bật máy (tuỳ chọn)
- Windows: Task Scheduler → tạo task "At startup" chạy `run.bat`.
- Linux: tạo service systemd chạy `run.sh`.

## 7. Lưu ý quan trọng
Đây là hệ thống **hỗ trợ cảnh báo**, không thay thế đầu báo cháy / chuông báo cháy chuẩn. AI có thể nhầm (ánh đèn, nắng chiều, vật màu cam đỏ…) hoặc bỏ sót. Hãy thử nghiệm kỹ ở nơi lắp đặt thật trước khi tin dùng.

## 8. Dùng Zalo thay cho Telegram (tuỳ chọn)
Hệ thống hỗ trợ **Zalo Bot Platform** (https://bot.zapps.me). Lưu ý: Zalo chỉ gửi được **chữ**, không kèm ảnh (API ảnh của Zalo chỉ nhận link ảnh công khai). Muốn có cả ảnh, hãy bật song song Telegram.
1. Trên Zalo, tìm "Zalo Bot Creator" và tạo bot theo hướng dẫn tại bot.zapps.me, lấy **bot token**.
2. Mở Zalo, tìm bot vừa tạo, nhắn một tin bất kỳ.
3. Chạy `python get_zalo_chat_id.py <ZALO_BOT_TOKEN>` để lấy **chat_id**.
4. Điền vào `config.yaml` mục `zalo` (đặt `enabled: true`), rồi chạy `python test_notify.py`.
Có thể bật Zalo và Telegram cùng lúc; tắt Telegram bằng `telegram.enabled: false`.

## 9. Các kênh khác gửi được ẢNH (ngoài Telegram)
Bật trong `config.yaml` (đặt `enabled: true`), có thể bật nhiều kênh cùng lúc, rồi chạy `python test_notify.py`:
- **Email (Gmail)**: gửi kèm ảnh, mọi điện thoại đều nhận được. Cần bật xác minh 2 bước và tạo "Mật khẩu ứng dụng" (App password) cho Gmail, điền vào `email.password`.
- **ntfy**: không cần tài khoản. Cài app ntfy (iOS/Android), subscribe đúng topic bí mật. Ảnh tối đa 15MB, giữ 3 giờ trên ntfy.sh.
- **Discord**: tạo Webhook trong kênh, dán URL vào `discord.webhook_url`, cài app Discord trên điện thoại nhận.
- **Zalo**: chỉ gửi chữ (xem mục 8).
Thông tin nhạy cảm (token, mật khẩu) có thể đặt bằng biến môi trường: `TELEGRAM_BOT_TOKEN`, `ZALO_BOT_TOKEN`, `DISCORD_WEBHOOK_URL`, `EMAIL_PASSWORD`.
