# alert_app/services/notifier.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from django.conf import settings
import os
from playsound import playsound

def send_fire_alert_email(image_path, confidence):
    """
    Hàm gửi email cảnh báo kèm ảnh bằng chứng
    """
    # Bạn có thể cấu hình thông tin email trực tiếp hoặc lấy từ settings.py
    sender_email = settings.ALERT_EMAIL_SENDER
    sender_password = settings.ALERT_EMAIL_PASSWORD
    receiver_email = settings.ALERT_EMAIL_RECEIVER

    try:
        msg = MIMEMultipart()
        msg['Subject'] = "🔥 CẢNH BÁO: Phát hiện có lửa/khói khẩn cấp! 🔥"
        msg['From'] = sender_email
        msg['To'] = receiver_email

        # Nội dung text
        body = f"Hệ thống giám sát đã phát hiện sự cố cháy!\nĐộ tin cậy: {confidence:.2f}\nHình ảnh hiện trường được đính kèm bên dưới."
        msg.attach(MIMEText(body, 'plain'))

        # Đính kèm hình ảnh bằng chứng
        with open(image_path, 'rb') as f:
            img_data = f.read()
        image = MIMEImage(img_data, name="fire_evidence.jpg")
        msg.attach(image)

        # Kết nối SMTP server của Gmail và gửi mail
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
            print("Đã gửi email cảnh báo thành công!")
    except Exception as e:
        print(f"Lỗi khi gửi email cảnh báo: {e}")

    try:
        # 2. Phát âm thanh cảnh báo trực tiếp tại server
        # Đường dẫn tới file còi hú (Ví dụ: đặt file alarm.mp3 trong thư mục sounds ở gốc project)
        sound_path = os.path.join(settings.BASE_DIR, 'sounds', 'alarm.mp3')
        
        if os.path.exists(sound_path):
            playsound(sound_path)
            print("Đã phát âm thanh cảnh báo thành công!")
        else:
            print(f"Không tìm thấy file âm thanh tại: {sound_path}")
            
    except Exception as e:
        print(f"Lỗi khi phát âm thanh cảnh báo: {e}")