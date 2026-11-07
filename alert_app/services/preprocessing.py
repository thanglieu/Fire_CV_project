
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PreparedFrame:
    """Lưu frame đã chuẩn bị và thông tin ảnh gốc."""
    image: np.ndarray
    frame_id: int
    original_width: int
    original_height: int


class FramePreprocessor:
    """Kiểm tra và chuẩn bị frame trước khi đưa vào YOLO."""

    def process(self, frame: np.ndarray, frame_id: int) -> PreparedFrame:
        """
        Kiểm tra tính hợp lệ và chuẩn hóa định dạng frame.

        Input:
            frame: Ảnh BGR đọc từ OpenCV.
            frame_id: Số thứ tự của frame.

        Output:
            PreparedFrame chứa ảnh BGR và thông tin ảnh gốc.
        """

        # 1. Kiểm tra frame có tồn tại hay không
        if frame is None:
            raise ValueError("Frame đầu vào không tồn tại.")

        if not isinstance(frame, np.ndarray):
            raise TypeError("Frame phải có kiểu dữ liệu numpy.ndarray.")

        # 2. Kiểm tra kích thước frame
        if frame.size == 0 or frame.ndim != 3:
            raise ValueError("Frame không có cấu trúc ảnh hợp lệ.")

        height, width, channels = frame.shape

        if channels != 3:
            raise ValueError(f"Frame phải có 3 kênh màu BGR, nhận được {channels} kênh.")

        if width <= 0 or height <= 0:
            raise ValueError("Kích thước frame không hợp lệ.")

        # 3. Kiểm tra kiểu dữ liệu pixel
        if frame.dtype != np.uint8:
            raise TypeError(f"Frame phải có kiểu uint8, nhận được {frame.dtype}.")

        # 4. Đảm bảo dữ liệu ảnh liên tục trong bộ nhớ
        # Tạo bản sao để tránh ảnh hưởng đến frame gốc.
        processed_frame = np.ascontiguousarray(frame).copy()

        # 5. Trả về ảnh và thông tin ảnh gốc
        return PreparedFrame(
            image=processed_frame,
            frame_id=frame_id,
            original_width=width,
            original_height=height,
        )
