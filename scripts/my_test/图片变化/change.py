import os
import time

import cv2  # py -m  pip install opencv-python numpy

# 保存截图的文件夹
SAVE_DIR = "captures"
os.makedirs(SAVE_DIR, exist_ok=True)

# 打开摄像头（0 为默认摄像头）
cap = cv2.VideoCapture(0)

baseline = None  # 基准帧
threshold = 25  # 变动阈值（越小越敏感）
min_area = 5000  # 最小变化区域（防止小波动误报）

print("按 S 设定基准图像")
print("按 Q 退出程序")

while True:
    ret, frame = cap.read()
    frame = cv2.flip(frame, 1)  # 水平镜像（左右翻转）
    # frame = cv2.flip(frame, 0)  # 垂直翻转（上下）
    # frame = cv2.flip(frame, 1)  # 矫正镜像

    if not ret:
        break

    # 显示原视频
    cv2.imshow("Video Monitor", frame)
    key = cv2.waitKey(1) & 0xFF

    # S 键设置基准帧
    if key == ord('s'):
        baseline = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        baseline = cv2.GaussianBlur(baseline, (21, 21), 0)
        print("基准图像已设置！")

        # 保存基准图像
        filename = os.path.join(SAVE_DIR, f"baseline_{int(time.time())}.jpg")
        cv2.imwrite(filename, frame)
        print("基准图像已保存：", filename)

    # 如果已有基准图像，则开始监控变化
    if baseline is not None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        # 计算差异
        diff = cv2.absdiff(baseline, gray)
        thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        # 找变化区域
        contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue  # 忽略小范围变化

            # 有明显变化 → 保存截图
            # filename = os.path.join(SAVE_DIR, f"change_{time.time_ns()}.jpg")
            filename = os.path.join(SAVE_DIR, f"change_{int(time.time())}.jpg")
            cv2.imwrite(filename, frame)
            print("检测到变化，已保存截图：", filename)

            # 将该帧显示为“有变化”
            cv2.rectangle(frame, (0, 0), (frame.shape[1], frame.shape[0]), (0, 0, 255), 4)

        cv2.imshow("Changes", thresh)

    # 按 Q 退出
    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
