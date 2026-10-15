"""
Phát hiện lửa trong một ảnh .jpg bằng model YOLO đã train.

Cách dùng:
    python detect.py <đường_dẫn_ảnh_input> [đường_dẫn_ảnh_output]

Ví dụ:
    python detect.py images_input/test1.jpg
    python detect.py images_input/test1.jpg outputs/test1_result.jpg
"""

from ultralytics import YOLO
import cv2
import os

# Đường dẫn tới model đã train
MODEL_PATH = "runs/detect/fire_detector/weights/best.pt"

# Ngưỡng độ tin cậy tối thiểu để coi là phát hiện lửa thật
CONFIDENCE_THRESHOLD = 0.4


def detect_fire(image_path, output_path):
    # Load model
    model = YOLO(MODEL_PATH)

    # Chạy inference trên ảnh
    results = model(image_path, conf=CONFIDENCE_THRESHOLD)

    # Đọc ảnh gốc bằng OpenCV để vẽ lên
    img = cv2.imread(image_path)

    # Duyệt qua từng kết quả phát hiện được
    for result in results:
        boxes = result.boxes
        for box in boxes:
            # Lấy tọa độ khung (x1, y1, x2, y2)
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            label = model.names[cls_id]

            # Vẽ khung chữ nhật quanh vùng lửa
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)

            # Vẽ nhãn + độ tin cậy
            text = f"{label} {conf:.2f}"
            (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(img, (x1, y1 - text_h - 8), (x1 + text_w, y1), (0, 0, 255), -1)
            cv2.putText(img, text, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # Lưu ảnh kết quả
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, img)
    print(f"Đã lưu kết quả tại: {output_path}")

    return img


if __name__ == "__main__":
    input_image = "inputs/test1.jpg"
    output_image = "outputs/test1_result.jpg"

    detect_fire(input_image, output_image)


"""
import sys
import os
from ultralytics import YOLO
import cv2

# Đường dẫn tới model đã train (sinh ra sau khi chạy train.py)
MODEL_PATH = "runs/detect/fire_detector/weights/best.pt"

# Ngưỡng độ tin cậy tối thiểu để coi là phát hiện lửa thật
# - Bỏ sót lửa thật nhiều -> giảm ngưỡng (VD: 0.25)
# - Báo động giả nhiều -> tăng ngưỡng (VD: 0.5 - 0.6)
CONFIDENCE_THRESHOLD = 0.4

# Màu khung + chữ (định dạng BGR của OpenCV)
BOX_COLOR = (0, 0, 255)   # đỏ
TEXT_COLOR = (255, 255, 255)


def detect_fire(image_path: str, output_path: str) -> None:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Không tìm thấy model tại: {MODEL_PATH}\n"
            "Hãy chạy 'python train.py' trước để tạo model, "
            "hoặc sửa MODEL_PATH cho khớp với vị trí file best.pt của bạn."
        )

    model = YOLO(MODEL_PATH)
    results = model(image_path, conf=CONFIDENCE_THRESHOLD)

    img = cv2.imread(image_path)
    num_detections = 0

    for result in results:
        for box in result.boxes:
            num_detections += 1

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            label = model.names[int(box.cls[0])]

            # Vẽ khung chữ nhật quanh vùng phát hiện
            cv2.rectangle(img, (x1, y1), (x2, y2), BOX_COLOR, 2)

            # Vẽ nhãn + độ tin cậy phía trên khung
            text = f"{label} {conf:.2f}"
            (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            label_y1 = max(y1 - text_h - 8, 0)
            cv2.rectangle(img, (x1, label_y1), (x1 + text_w, y1), BOX_COLOR, -1)
            cv2.putText(img, text, (x1, max(y1 - 4, text_h)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT_COLOR, 2)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    cv2.imwrite(output_path, img)

    print(f"Số vùng phát hiện được: {num_detections}")
    print(f"Đã lưu ảnh kết quả tại: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng: python detect.py <đường_dẫn_ảnh_input> [đường_dẫn_ảnh_output]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "outputs/result.jpg"

    detect_fire(input_path, output_path)

"""