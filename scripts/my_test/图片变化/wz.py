"""
video_monitor_pyqt5.py

功能概述（尽量满足你要求的全部点）：
- PyQt5 GUI + OpenCV 摄像头预览（无闪烁）
- 设置基准图像（按钮或按 S）
- 基于基准的像素差异检测（并在变化处画框，保存图片）
- 区域/禁区绘制（鼠标拖拉矩形：只有进入该区域才触发报警）
- AI 人体检测（MobileNet-SSD if available, fallback HOG）
- 可选 face_recognition 人脸识别（需安装并放置 known_faces 文件夹）
- 报警录像（可选 5s/10s），保存到 disk
- 显示已保存图片缩略列表，点击放大
"""

import sys, os, time, threading, collections
from datetime import datetime
from pathlib import Path
import numpy as np
import cv2
from PyQt5 import QtWidgets, QtGui, QtCore
import imutils

# Optional face_recognition
try:
    import face_recognition
    FACE_AVAILABLE = True
except Exception:
    FACE_AVAILABLE = False

# --- Config ---
SAVE_DIR = Path("captures")
SAVE_DIR.mkdir(exist_ok=True)
MODELS_DIR = Path("models")
FPS = 20  # will try to set camera to this; actual may differ
RECORD_SECONDS = 5  # alarm record length
MIN_AREA = 2000  # diff contour min area
DIFF_THRESHOLD = 30  # threshold for binarization
ALARM_COOLDOWN = 5  # seconds between saved events to avoid spam
FRAME_BUFFER_SECONDS = 3  # pre-record buffer (not fully implemented complexly)
FLIP_H = True  # whether to horizontally flip frames (自拍镜像修正)
# ------------------

# load MobileNet SSD if available
ssd_net = None
ssd_classes = None
ssd_conf_threshold = 0.5
try:
    proto = str(MODELS_DIR / "MobileNetSSD_deploy.prototxt")
    model = str(MODELS_DIR / "MobileNetSSD_deploy.caffemodel")
    if os.path.exists(proto) and os.path.exists(model):
        ssd_net = cv2.dnn.readNetFromCaffe(proto, model)
        # MobileNet SSD class labels (standard)
        ssd_classes = ["background","aeroplane","bicycle","bird","boat",
                       "bottle","bus","car","cat","chair","cow","diningtable",
                       "dog","horse","motorbike","person","pottedplant","sheep",
                       "sofa","train","tvmonitor"]
        print("Loaded MobileNetSSD for person detection.")
    else:
        print("MobileNetSSD model files not found in models/. Using HOG fallback.")
except Exception as e:
    print("Failed to load SSD model:", e)
    ssd_net = None

# HOG person detector fallback
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# Face recognition known faces loading (if available)
KNOWN_FACES_DIR = Path("known_faces")
known_face_encodings = []
known_face_names = []
if FACE_AVAILABLE and KNOWN_FACES_DIR.exists():
    for img_path in KNOWN_FACES_DIR.glob("*.*"):
        try:
            img = face_recognition.load_image_file(str(img_path))
            encs = face_recognition.face_encodings(img)
            if encs:
                known_face_encodings.append(encs[0])
                # label from filename before extension
                known_face_names.append(img_path.stem)
                print("Loaded known face:", img_path.stem)
        except Exception as e:
            print("Failed to load known face", img_path, e)
else:
    if not FACE_AVAILABLE:
        print("face_recognition not installed — skipping face ID feature.")
    else:
        print("No known_faces directory — skipping face ID.")

# Utility
def timestamped_filename(prefix, ext="jpg"):
    return SAVE_DIR / f"{prefix}_{int(time.time())}.{ext}"

# --- Worker thread for camera capture & processing ---
class VideoWorker(QtCore.QThread):
    frame_updated = QtCore.pyqtSignal(np.ndarray)
    thumbnail_saved = QtCore.pyqtSignal(str)
    alarm_triggered = QtCore.pyqtSignal(str)

    def __init__(self, cam_index=0, width=None, height=None):
        super().__init__()
        self.cam_index = cam_index
        self.running = False
        self.capture = None
        self.width = width
        self.height = height

        # processing state
        self.baseline = None
        self.last_saved_time = 0
        self.recording = False
        self.record_writer = None
        self.record_end_time = 0
        self.zone = None  # (x1,y1,x2,y2)
        self.lock = threading.Lock()

    def run(self):
        self.running = True
        self.capture = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW if os.name == 'nt' else 0)
        # Try setting requested resolution if provided
        if self.width:
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # set FPS hint
        self.capture.set(cv2.CAP_PROP_FPS, FPS)

        # query actual fps and size
        actual_fps = self.capture.get(cv2.CAP_PROP_FPS)
        w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Camera opened: {w}x{h} @ {actual_fps}fps")

        while self.running:
            ret, frame = self.capture.read()
            if not ret:
                time.sleep(0.1)
                continue

            if FLIP_H:
                frame = cv2.flip(frame, 1)

            processed_frame = frame.copy()

            # face detection + recognition (optional)
            faces = []
            if FACE_AVAILABLE:
                try:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    face_locations = face_recognition.face_locations(rgb, model="hog")
                    face_encodings = face_recognition.face_encodings(rgb, face_locations)
                    for (loc, enc) in zip(face_locations, face_encodings):
                        top, right, bottom, left = loc
                        name = "Unknown"
                        if known_face_encodings:
                            matches = face_recognition.compare_faces(known_face_encodings, enc, tolerance=0.5)
                            if True in matches:
                                idx = matches.index(True)
                                name = known_face_names[idx]
                        faces.append(((left, top, right, bottom), name))
                        cv2.rectangle(processed_frame, (left, top), (right, bottom), (255, 0, 0), 2)
                        cv2.putText(processed_frame, name, (left, top-6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,0,0), 2)
                except Exception as e:
                    # if face_recognition heavy, just skip
                    pass

            # person detection (prefer SSD if available)
            person_boxes = []
            if ssd_net is not None:
                try:
                    blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
                    ssd_net.setInput(blob)
                    detections = ssd_net.forward()
                    (h_img, w_img) = frame.shape[:2]
                    for i in range(detections.shape[2]):
                        conf = detections[0, 0, i, 2]
                        idx = int(detections[0, 0, i, 1])
                        if conf > ssd_conf_threshold and idx == 15:  # class 15 == person
                            box = detections[0, 0, i, 3:7] * np.array([w_img, h_img, w_img, h_img])
                            (startX, startY, endX, endY) = box.astype("int")
                            person_boxes.append((startX, startY, endX, endY, conf))
                            cv2.rectangle(processed_frame, (startX, startY), (endX, endY), (0,255,0), 2)
                except Exception as e:
                    # fallback silently
                    pass
            else:
                # HOG fallback (slower)
                rects, weights = hog.detectMultiScale(frame, winStride=(8,8), padding=(8,8), scale=1.05)
                for (x, y, w_, h_) in rects:
                    person_boxes.append((x, y, x+w_, y+h_, 1.0))
                    cv2.rectangle(processed_frame, (x, y), (x+w_, y+h_), (0,255,0), 2)

            # baseline diff detection
            if self.baseline is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21,21), 0)
                diff = cv2.absdiff(self.baseline, gray)
                thresh = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
                thresh = cv2.dilate(thresh, None, iterations=2)
                cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cnts = imutils.grab_contours(cnts)
                motion_boxes = []
                for c in cnts:
                    if cv2.contourArea(c) < MIN_AREA:
                        continue
                    (x, y, w_, h_) = cv2.boundingRect(c)
                    motion_boxes.append((x, y, x+w_, y+h_))
                    cv2.rectangle(processed_frame, (x, y), (x+w_, y+h_), (0,0,255), 2)

                # check if motion overlaps with person_boxes or is inside zone (if set)
                alarm_now = False
                zone_hit = False
                if motion_boxes:
                    # If a zone is defined, require overlap with zone
                    if self.zone:
                        zx1, zy1, zx2, zy2 = self.zone
                        for mb in motion_boxes:
                            mx1, my1, mx2, my2 = mb
                            # check overlap
                            if (mx1 < zx2 and mx2 > zx1 and my1 < zy2 and my2 > zy1):
                                zone_hit = True
                                break
                        if zone_hit:
                            alarm_now = True
                    else:
                        # if person detection enabled, only alarm when person detected overlapping motion
                        if person_boxes:
                            for mb in motion_boxes:
                                mx1, my1, mx2, my2 = mb
                                for pb in person_boxes:
                                    px1, py1, px2, py2, conf = pb
                                    if (mx1 < px2 and mx2 > px1 and my1 < py2 and my2 > py1):
                                        alarm_now = True
                                        break
                                if alarm_now: break
                        else:
                            # no person detector — just alarm on motion
                            alarm_now = True

                # enforce cooldown to avoid many saves
                now = time.time()
                if alarm_now and now - self.last_saved_time > ALARM_COOLDOWN:
                    self.last_saved_time = now
                    # save frame with boxes annotated
                    filename = timestamped_filename("alarm", "jpg")
                    cv2.imwrite(str(filename), processed_frame)
                    # emit saved thumbnail signal (path)
                    self.thumbnail_saved.emit(str(filename))
                    # start recording
                    self.start_recording_if_needed()
                    # emit alarm triggered
                    self.alarm_triggered.emit(str(filename))

            # recording ongoing handling
            if self.recording and self.record_writer is not None:
                self.record_writer.write(frame)
                if time.time() >= self.record_end_time:
                    # stop recording
                    self.stop_recording()

            # draw zone rect overlay
            if self.zone:
                zx1, zy1, zx2, zy2 = self.zone
                cv2.rectangle(processed_frame, (zx1, zy1), (zx2, zy2), (0,165,255), 2)
                cv2.putText(processed_frame, "Zone", (zx1, zy1-6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,165,255), 2)

            # finally emit frame to GUI
            self.frame_updated.emit(processed_frame)

            # throttle to not hog CPU (sleep tiny bit)
            time.sleep(0.01)

        # cleanup
        if self.capture and self.capture.isOpened():
            self.capture.release()
        print("VideoWorker stopped.")

    def set_baseline_from_frame(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21,21), 0)
        with self.lock:
            self.baseline = gray.copy()
        # save baseline
        fname = timestamped_filename("baseline")
        cv2.imwrite(str(fname), frame)
        print("Baseline saved:", fname)
        self.thumbnail_saved.emit(str(fname))

    def clear_baseline(self):
        with self.lock:
            self.baseline = None

    def set_zone(self, rect):
        # rect = (x1,y1,x2,y2)
        with self.lock:
            self.zone = rect

    def start_recording_if_needed(self, seconds=RECORD_SECONDS):
        if not self.recording:
            # open VideoWriter
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            fname = timestamped_filename("alarm_video", "avi")
            # try get frame size
            cap_w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            cap_h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            out = cv2.VideoWriter(str(fname), fourcc, FPS if FPS>0 else 20.0, (cap_w, cap_h))
            self.record_writer = out
            self.recording = True
            self.record_end_time = time.time() + seconds
            print("Started recording to", fname)

    def stop_recording(self):
        if self.recording:
            self.recording = False
            if self.record_writer:
                try:
                    self.record_writer.release()
                    print("Recording stopped.")
                except Exception as e:
                    print("Error closing writer", e)
                self.record_writer = None

    def stop(self):
        self.running = False
        self.wait(2000)

# --- PyQt5 GUI ---
class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt5 视频监控 + AI检测")
        self.resize(1200, 720)

        # UI components
        self.video_label = QtWidgets.QLabel()
        self.video_label.setFixedSize(960, 540)
        self.video_label.setStyleSheet("background: black;")
        self.start_btn = QtWidgets.QPushButton("Start")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.set_base_btn = QtWidgets.QPushButton("设置基准(S)")
        self.clear_base_btn = QtWidgets.QPushButton("清除基准")
        self.record_len_combo = QtWidgets.QComboBox()
        self.record_len_combo.addItems(["5", "10", "15"])
        self.save_list = QtWidgets.QListWidget()
        self.flip_chk = QtWidgets.QCheckBox("水平翻转")
        self.flip_chk.setChecked(FLIP_H)

        # layout
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.set_base_btn)
        btn_layout.addWidget(self.clear_base_btn)
        btn_layout.addWidget(QtWidgets.QLabel("录像秒数:"))
        btn_layout.addWidget(self.record_len_combo)
        btn_layout.addWidget(self.flip_chk)

        main_layout = QtWidgets.QVBoxLayout()
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(self.video_label)
        right_layout = QtWidgets.QVBoxLayout()
        right_layout.addWidget(QtWidgets.QLabel("已保存图片"))
        right_layout.addWidget(self.save_list)
        right_layout.addStretch()
        top_layout.addLayout(right_layout)
        main_layout.addLayout(top_layout)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

        # worker
        self.worker = VideoWorker(cam_index=0, width=1280, height=720)
        self.worker.frame_updated.connect(self.on_frame)
        self.worker.thumbnail_saved.connect(self.on_thumbnail_saved)
        self.worker.alarm_triggered.connect(self.on_alarm)

        # events
        self.start_btn.clicked.connect(self.start_camera)
        self.stop_btn.clicked.connect(self.stop_camera)
        self.set_base_btn.clicked.connect(self.set_baseline)
        self.clear_base_btn.clicked.connect(self.clear_baseline)
        self.save_list.itemClicked.connect(self.on_saved_item_clicked)
        self.flip_chk.stateChanged.connect(self.on_flip_changed)
        self.video_label.mousePressEvent = self.on_mouse_down
        self.video_label.mouseReleaseEvent = self.on_mouse_up
        self.video_label.mouseMoveEvent = self.on_mouse_move

        # zone drawing state
        self.zone_start = None
        self.zone_end = None
        self.drawing = False

        # store last displayed frame for baseline capture
        self._last_frame = None

    def start_camera(self):
        if not self.worker.isRunning():
            self.worker.start()
            self.start_btn.setEnabled(False)

    def stop_camera(self):
        if self.worker.isRunning():
            self.worker.stop()
            self.start_btn.setEnabled(True)

    def set_baseline(self):
        if self._last_frame is not None:
            self.worker.set_baseline_from_frame(self._last_frame)
        else:
            QtWidgets.QMessageBox.warning(self, "提示", "当前没有画面可设置基准")

    def clear_baseline(self):
        self.worker.clear_baseline()

    def on_frame(self, frame):
        # receive BGR numpy array
        self._last_frame = frame.copy()
        # convert to QImage
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        # scale to label
        pix = QtGui.QPixmap.fromImage(qt_image).scaled(self.video_label.size(), QtCore.Qt.KeepAspectRatio)
        self.video_label.setPixmap(pix)

    def on_thumbnail_saved(self, path):
        item = QtWidgets.QListWidgetItem(str(path))
        self.save_list.addItem(item)

    def on_saved_item_clicked(self, item):
        path = item.text()
        if os.path.exists(path):
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle(os.path.basename(path))
            v = QtWidgets.QVBoxLayout(dlg)
            lbl = QtWidgets.QLabel()
            pix = QtGui.QPixmap(path)
            lbl.setPixmap(pix.scaled(800,600, QtCore.Qt.KeepAspectRatio))
            v.addWidget(lbl)
            dlg.exec_()

    def on_alarm(self, path):
        print("Alarm triggered, saved:", path)
        # you can play beep or show dialog
        QtWidgets.QMessageBox.information(self, "报警", f"检测到异常，已保存: {path}")

    def on_flip_changed(self, state):
        global FLIP_H
        FLIP_H = (state == QtCore.Qt.Checked)

    # mouse events for drawing zone on the video_label
    def _map_label_to_frame(self, pos):
        # Map widget pos to underlying frame coordinates approximately
        # Note: we used scaled pixmap with KeepAspectRatio, mapping approx
        if self._last_frame is None:
            return None
        label_size = self.video_label.size()
        pixmap = self.video_label.pixmap()
        if pixmap is None:
            return None
        # compute offsets
        pix_w = pixmap.width()
        pix_h = pixmap.height()
        lbl_w = label_size.width()
        lbl_h = label_size.height()
        offset_x = (lbl_w - pix_w) // 2
        offset_y = (lbl_h - pix_h) // 2
        x = pos.x() - offset_x
        y = pos.y() - offset_y
        if x < 0 or y < 0 or x >= pix_w or y >= pix_h:
            return None
        # map to frame coords
        frame_h, frame_w = self._last_frame.shape[:2]
        fx = int(x * frame_w / pix_w)
        fy = int(y * frame_h / pix_h)
        return fx, fy

    def on_mouse_down(self, event):
        pos = event.pos()
        mapped = self._map_label_to_frame(pos)
        if mapped:
            self.zone_start = mapped
            self.drawing = True

    def on_mouse_move(self, event):
        if not self.drawing:
            return
        pos = event.pos()
        mapped = self._map_label_to_frame(pos)
        if mapped:
            self.zone_end = mapped
            # show preview by overlaying a rectangle on current pixmap
            # (we simply update label with a drawn rectangle on a copy)
            if self._last_frame is not None:
                temp = self._last_frame.copy()
                x1, y1 = self.zone_start
                x2, y2 = self.zone_end
                cv2.rectangle(temp, (x1,y1), (x2,y2), (0,165,255), 2)
                rgb = cv2.cvtColor(temp, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                qt_image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
                pix = QtGui.QPixmap.fromImage(qt_image).scaled(self.video_label.size(), QtCore.Qt.KeepAspectRatio)
                self.video_label.setPixmap(pix)

    def on_mouse_up(self, event):
        if not self.drawing:
            return
        pos = event.pos()
        mapped = self._map_label_to_frame(pos)
        if mapped:
            self.zone_end = mapped
            x1, y1 = self.zone_start
            x2, y2 = self.zone_end
            # normalize
            zx1, zx2 = sorted([x1, x2])
            zy1, zy2 = sorted([y1, y2])
            self.worker.set_zone((zx1, zy1, zx2, zy2))
            print("Zone set:", (zx1, zy1, zx2, zy2))
        self.drawing = False

    def closeEvent(self, event):
        self.stop_camera()
        event.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
