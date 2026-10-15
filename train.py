"""
Fine-tune YOLOv8 với dataset phát hiện lửa đã tải từ Roboflow.

Cách dùng:
    python train.py

Kết quả (model tốt nhất) sẽ được lưu tại:
    runs/detect/fire_detector/weights/best.pt
"""

from ultralytics import YOLO

# Đường dẫn tới file data.yaml trong thư mục dataset đã tải từ Roboflow
# (sửa lại cho khớp với tên thư mục dataset thực tế của bạn)
DATA_YAML = "Fire/smoke/human-1/data.yaml"


def main():
    # Dùng model pretrained nhỏ (yolov8n) làm điểm khởi đầu — nhẹ, phù hợp
    # máy không có GPU mạnh. Có thể đổi sang "yolov8s.pt" nếu muốn độ chính
    # xác cao hơn (đổi lại train chậm hơn).
    model = YOLO("yolov8n.pt")

    model.train(
        data=DATA_YAML,
        epochs=100,
        imgsz=640,
        batch=16,
        name="fire_detector",   # kết quả lưu tại runs/detect/fire_detector
        patience=20,             # dừng sớm nếu không cải thiện sau 20 epoch
    )


if __name__ == "__main__":
    main()
