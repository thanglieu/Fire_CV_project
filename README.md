# Fire Detection - YOLO

Chương trình phát hiện lửa trong ảnh .jpg bằng YOLOv8, dataset lấy từ Roboflow.

## 1. Cài đặt

```bash
# Tạo và kích hoạt virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# Cài thư viện
pip install -r requirements.txt
```

## 2. Tải dataset từ Roboflow

Mở `download_dataset.py`, thay các giá trị `API_KEY`, `WORKSPACE`,
`PROJECT_NAME`, `VERSION` bằng thông tin lấy từ trang Roboflow của bạn
(project -> Versions -> Export Dataset -> format "YOLOv8" -> Show download code).

Sau đó chạy:

```bash
python download_dataset.py
```

Dataset sẽ được tải về một thư mục (VD: `Fire-Detection-1/`) chứa `data.yaml`.

## 3. Huấn luyện model

Mở `train.py`, sửa biến `DATA_YAML` cho khớp đường dẫn `data.yaml` vừa tải về.

```bash
python train.py
```

Model tốt nhất sau khi train sẽ nằm tại:

```
runs/detect/fire_detector/weights/best.pt
```

> Nếu máy không có GPU, có thể giảm `epochs` trong `train.py` để train
> nhanh hơn khi test, hoặc train trên Google Colab (có GPU miễn phí)
> rồi tải file `best.pt` về đúng đường dẫn trên.

## 4. Phát hiện lửa trên một ảnh

Đặt ảnh cần kiểm tra vào thư mục `images_input/`, sau đó chạy:

```bash
python detect.py images_input/test1.jpg
```

hoặc chỉ định rõ nơi lưu kết quả:

```bash
python detect.py images_input/test1.jpg outputs/test1_result.jpg
```

Ảnh kết quả (đã khoanh vùng lửa + nhãn + độ tin cậy) sẽ được lưu trong
thư mục `outputs/`.

## 5. Điều chỉnh độ nhạy

Trong `detect.py`, chỉnh giá trị `CONFIDENCE_THRESHOLD`:

- Bỏ sót lửa thật nhiều -> giảm ngưỡng (VD: 0.25)
- Báo động giả nhiều -> tăng ngưỡng (VD: 0.5 - 0.6)

## Cấu trúc thư mục

```
fire-detection/
├── download_dataset.py   # tải dataset từ Roboflow
├── train.py               # huấn luyện model YOLO
├── detect.py               # phát hiện lửa trên 1 ảnh .jpg
├── requirements.txt
├── README.md
├── images_input/          # đặt ảnh .jpg cần kiểm tra vào đây
└── outputs/                # ảnh kết quả (đã khoanh vùng lửa) lưu tại đây
```
