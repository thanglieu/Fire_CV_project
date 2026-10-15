"""
Train tiếp (resume) từ checkpoint gần nhất, sau khi training bị dừng
giữa chừng (Ctrl+C, mất điện, tắt máy...).

Cách dùng:
    python resume_train.py
"""

from ultralytics import YOLO

LAST_CHECKPOINT = "runs/detect/fire_detector/weights/last.pt"


def main():
    model = YOLO(LAST_CHECKPOINT)
    model.train(resume=True)


if __name__ == "__main__":
    main()