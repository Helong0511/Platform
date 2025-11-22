import cv2


def decode_qrcode_with_opencv(image_path):
    # 创建一个 OpenCV 二维码识别器
    detector = cv2.QRCodeDetector()

    # 读取图像
    img = cv2.imread(image_path)
    if img is None:
        print(f"错误：无法读取图片文件 '{image_path}'")
        return None

    # 解码二维码
    data, bbox, straight_qrcode = detector.detectAndDecode(img)

    if data:
        print(f"成功识别到二维码！内容是: {data}")
        return data
    else:
        print("图片中没有识别到二维码。")
        return None


# --- 使用示例 ---
if __name__ == "__main__":
    file_path = 'ewm.png'
    decoded_text = decode_qrcode_with_opencv(file_path)