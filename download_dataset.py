"""
Tải dataset phát hiện lửa từ Roboflow.

Cách dùng:
1. Vào project Roboflow của bạn -> Versions -> chọn phiên bản -> Export Dataset
   -> chọn format "YOLOv8" -> "Show download code".
2. Thay các giá trị YOUR_API_KEY, your-workspace, your-project-name, version bên dưới
   bằng thông tin lấy được từ Roboflow.
3. Chạy: python download_dataset.py
"""

from roboflow import Roboflow

# ==== THAY THÔNG TIN CỦA BẠN VÀO ĐÂY ====
API_KEY = "YOUR_API_KEY"
WORKSPACE = "your-workspace"
PROJECT_NAME = "your-project-name"
VERSION = 1
# =========================================



def main():
   rf = Roboflow(api_key="qd5CPSXOWsvHOT6hqxMK")
   project = rf.workspace("b23dccn836_nguyen-dinh-tra").project("fire-smoke-human-pfvce-stq4p")
   version = project.version(1)
   dataset = version.download("yolov8")
   print(f"Đã tải dataset về: {dataset.location}")
   print("Kiểm tra file data.yaml trong thư mục trên để dùng cho train.py")


if __name__ == "__main__":
   main()
