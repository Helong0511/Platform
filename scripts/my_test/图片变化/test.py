import sys
import cv2
import numpy as np
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


class CameraThread(QThread):
    frame_signal = pyqtSignal(np.ndarray)   # 把图像传给主窗口

    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)  # 宽
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)  # 高
        self.cap.set(cv2.CAP_PROP_FPS, 30)  # 帧率（可选）

        # 自动对焦（如果摄像头支持）
        self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)


        self.running = True
        self.baseline = None

    def set_baseline(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        self.baseline = gray

    def run(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue

            # 镜像修正
            frame = cv2.flip(frame, 1)

            # 变化检测
            if self.baseline is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                diff = cv2.absdiff(self.baseline, gray)
                thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1]
                thresh = cv2.dilate(thresh, None, 2)

                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for c in contours:
                    if cv2.contourArea(c) > 5000:
                        x, y, w, h = cv2.boundingRect(c)
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)

            self.frame_signal.emit(frame)
            self.msleep(30)

    def stop(self):
        self.running = False
        self.cap.release()


class MonitorGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("智能监控系统（PyQt5）")
        self.setGeometry(200, 200, 900, 600)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # 显示视频的标签
        self.label = QLabel("视频未启动")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        # 按钮
        btn_layout = QHBoxLayout()
        layout.addLayout(btn_layout)

        self.btn_start = QPushButton("启动监控")
        self.btn_start.clicked.connect(self.start_camera)
        btn_layout.addWidget(self.btn_start)

        self.btn_set_base = QPushButton("设为基准图像")
        self.btn_set_base.clicked.connect(self.set_baseline)
        btn_layout.addWidget(self.btn_set_base)

        self.camera_thread = None

    def start_camera(self):
        if self.camera_thread is None:
            self.camera_thread = CameraThread()
            self.camera_thread.frame_signal.connect(self.update_frame)
            self.camera_thread.start()

    def set_baseline(self):
        if hasattr(self, "last_frame"):
            self.camera_thread.set_baseline(self.last_frame)
            QMessageBox.information(self, "提示", "基准图像已保存！")

    def update_frame(self, frame):
        """显示图像"""
        self.last_frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.label.setPixmap(QPixmap.fromImage(qt_img))

    def closeEvent(self, event):
        if self.camera_thread:
            self.camera_thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = MonitorGUI()
    gui.show()
    sys.exit(app.exec_())
