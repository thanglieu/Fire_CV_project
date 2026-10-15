"""
Phát hiện lửa / khói / người trong một VIDEO (.mp4, .avi, ...) bằng model YOLO đã train.

Cách dùng:
    python detect_video.py <đường_dẫn_video_input> [đường_dẫn_video_output]

Ví dụ:
    python detect_video.py videos_input/test1.mp4
    python detect_video.py videos_input/test1.mp4 outputs/test1_result.mp4

Ghi chú cho người mới:
- Một video chỉ đơn giản là một chuỗi các ảnh (gọi là "frame") nối tiếp nhau.
- Nên cách xử lý video = đọc từng frame (giống hệt như xử lý 1 ảnh trong detect.py),
  chạy model detect trên frame đó, vẽ khung lên, rồi ghi frame đã vẽ vào video output.
- cv2.VideoCapture dùng để ĐỌC video (frame theo frame).
- cv2.VideoWriter dùng để GHI các frame đã xử lý thành 1 file video mới.
"""

import sys
import os
import time
from ultralytics import YOLO
import cv2

# Đường dẫn tới model đã train (sinh ra sau khi chạy train.py)
MODEL_PATH = "runs/detect/fire_detector/weights/best.pt"

# Ngưỡng độ tin cậy tối thiểu để coi là phát hiện thật
# - Bỏ sót nhiều -> giảm ngưỡng (VD: 0.25)
# - Báo động giả nhiều -> tăng ngưỡng (VD: 0.5 - 0.6)
CONFIDENCE_THRESHOLD = 0.4

# Mỗi class có 1 màu khung riêng cho dễ phân biệt (định dạng BGR của OpenCV)
# Nếu model của bạn có tên class khác (ví dụ "fire", "smoke", "person"),
# hãy sửa lại dict này cho khớp với model.names sau khi load model.
CLASS_COLORS = {
    "fire": (0, 0, 255),      # đỏ
    "smoke": (128, 128, 128), # xám
    "person": (0, 255, 0),    # xanh lá
}
DEFAULT_COLOR = (0, 255, 255)  # vàng, dùng nếu class không có trong dict trên
TEXT_COLOR = (255, 255, 255)

# Nếu True: vừa xử lý vừa hiển thị video lên màn hình (nhấn 'q' để dừng sớm)
# Đặt False nếu chạy trên server không có màn hình (ví dụ Google Colab)
SHOW_PREVIEW = True


def get_color_for_label(label: str):
    return CLASS_COLORS.get(label, DEFAULT_COLOR)


def draw_detections(frame, result, model):
    """Vẽ tất cả các khung phát hiện được lên 1 frame, trả về số lượng phát hiện."""
    count = 0
    for box in result.boxes:
        count += 1
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        label = model.names[int(box.cls[0])]
        color = get_color_for_label(label)

        # Khung chữ nhật quanh vùng phát hiện
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Nhãn + độ tin cậy phía trên khung
        text = f"{label} {conf:.2f}"
        (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        label_y1 = max(y1 - text_h - 8, 0)
        cv2.rectangle(frame, (x1, label_y1), (x1 + text_w, y1), color, -1)
        cv2.putText(frame, text, (x1, max(y1 - 4, text_h)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT_COLOR, 2)
    return count


def detect_video(video_path: str, output_path: str) -> None:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Không tìm thấy video: {video_path}")

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Không tìm thấy model tại: {MODEL_PATH}\n"
            "Hãy chạy 'python train.py' trước để tạo model, "
            "hoặc sửa MODEL_PATH cho khớp với vị trí file best.pt của bạn."
        )

    print("Đang load model...")
    model = YOLO(MODEL_PATH)

    # Mở video để đọc
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Không mở được video: {video_path}")

    # Lấy thông tin video gốc (kích thước, số khung hình/giây)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Chuẩn bị nơi ghi video kết quả (dùng codec mp4v cho file .mp4)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_idx = 0
    total_detections = 0
    start_time = time.time()

    print(f"Bắt đầu xử lý video: {total_frames} frame, {fps:.1f} fps, {width}x{height}")

    while True:
        ret, frame = cap.read()
        if not ret:
            break  # hết video

        frame_idx += 1

        # Chạy model detect trên frame hiện tại (giống hệt như detect trên 1 ảnh)
        results = model(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
        result = results[0]

        num_detections = draw_detections(frame, result, model)
        total_detections += num_detections

        # Hiển thị số frame đang xử lý ở góc trái trên
        progress_text = f"Frame {frame_idx}/{total_frames}"
        cv2.putText(frame, progress_text, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        # Ghi frame đã vẽ vào video output
        writer.write(frame)

        # Xem trực tiếp khi đang xử lý (tuỳ chọn)
        if SHOW_PREVIEW:
            cv2.imshow("Fire / Smoke / Person Detection", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("Đã dừng sớm theo yêu cầu người dùng (nhấn 'q').")
                break

        if frame_idx % 50 == 0:
            print(f"  Đã xử lý {frame_idx}/{total_frames} frame...")

    # Dọn dẹp tài nguyên
    cap.release()
    writer.release()
    if SHOW_PREVIEW:
        cv2.destroyAllWindows()

    elapsed = time.time() - start_time
    print(f"\nHoàn tất! Đã xử lý {frame_idx} frame trong {elapsed:.1f}s "
          f"({frame_idx / elapsed:.1f} fps trung bình).")
    print(f"Tổng số phát hiện: {total_detections}")
    print(f"Đã lưu video kết quả tại: {output_path}")


if __name__ == "__main__":
    input_video = "inputs/test1.mp4"
    output_video = "outputs/test1_result.mp4"

    detect_video(input_video, output_video)