import sys
import json
import time
import requests
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QTextEdit, QPushButton,
    QComboBox, QListWidget, QMessageBox, QTabWidget, QCheckBox,
    QVBoxLayout, QHBoxLayout, QSizePolicy
)
from PyQt5.QtCore import Qt

HISTORY_FILE = Path("history.json")


class APITesterPro(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("API Tester Pro (PyQt5)")
        self.resize(1200, 780)

        self.history = []
        self.load_history()
        self.init_ui()
        self.refresh_history_ui()

    # ================= UI =================
    def init_ui(self):
        main_layout = QHBoxLayout(self)

        # ===== 左侧：历史区 =====
        left_layout = QVBoxLayout()

        self.clear_btn = QPushButton("清空历史")
        self.clear_btn.setFixedHeight(32)
        self.clear_btn.clicked.connect(self.clear_history)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.load_from_history)

        left_layout.addWidget(self.clear_btn)
        left_layout.addWidget(self.history_list)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_widget.setFixedWidth(260)

        # ===== 右侧 =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(6, 6, 6, 6)

        # --- 第一行 ---
        top_line = QHBoxLayout()
        self.method_box = QComboBox()
        self.method_box.addItems(["GET", "POST", "PUT", "DELETE"])
        self.method_box.setFixedWidth(90)

        self.url_input = QLineEdit()
        self.url_input.setText("https://client.btfrx.online/api/v1/bft/postback")
        self.url_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        top_line.addWidget(QLabel("Method"))
        top_line.addWidget(self.method_box)
        top_line.addSpacing(10)
        top_line.addWidget(QLabel("URL"))
        top_line.addWidget(self.url_input)

        # --- JWT ---
        jwt_line = QHBoxLayout()
        self.jwt_enable = QCheckBox("启用 JWT")
        self.jwt_input = QLineEdit()
        self.jwt_input.setPlaceholderText("Bearer Token")
        self.jwt_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        jwt_line.addWidget(self.jwt_enable)
        jwt_line.addWidget(self.jwt_input)

        # --- Tabs ---
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.headers_input = QTextEdit()
        self.params_input = QTextEdit()
        self.body_input = QTextEdit()
        self.response_output = QTextEdit()
        self.response_output.setReadOnly(True)

        self.headers_input.setText(
            '{\n  '
            '"Content-Type": "application/json"'
            '\n}'
        )

        self.params_input.setText(
            '{\n  '
            '"platform": "he_test",'

            '\n  '
            '"click_id": "bpwrchC4TreAaEC4tjWJGFWCRwPHR7kWTxynRKpcc",'

            '\n  '
            '"payout": 3.20'

            '\n}'
        )

        self.body_input.setText(
            '{\n  '
            '"username": "admin",'
            
            '\n  '
            '"password": "yinghexinx123"'
            
            '\n}'
        )

        self.tabs.addTab(self.headers_input, "Headers")
        self.tabs.addTab(self.params_input, "Params")
        self.tabs.addTab(self.body_input, "Body")
        self.tabs.addTab(self.response_output, "Response")

        # --- 底部 ---
        bottom_line = QHBoxLayout()
        self.send_btn = QPushButton("发送请求")
        self.send_btn.setFixedHeight(36)
        self.send_btn.clicked.connect(self.send_request)

        self.status_label = QLabel("Status: - | Time: - ms")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        bottom_line.addWidget(self.send_btn)
        bottom_line.addStretch()
        bottom_line.addWidget(self.status_label)

        # --- 组合 ---
        right_layout.addLayout(top_line)
        right_layout.addLayout(jwt_line)
        right_layout.addWidget(self.tabs, 1)
        right_layout.addLayout(bottom_line)

        main_layout.addWidget(left_widget)
        main_layout.addWidget(right_widget, 1)

    # ================= Logic =================
    def parse_json(self, text):
        text = text.strip()
        if not text:
            return {}
        return json.loads(text)

    def send_request(self):
        method = self.method_box.currentText()
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "错误", "URL 不能为空")
            return

        try:
            headers = self.parse_json(self.headers_input.toPlainText())
            params = self.parse_json(self.params_input.toPlainText())
            body = self.parse_json(self.body_input.toPlainText())
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "JSON 错误", str(e))
            return

        if self.jwt_enable.isChecked() and self.jwt_input.text().strip():
            headers["Authorization"] = f"Bearer {self.jwt_input.text().strip()}"

        try:
            start = time.time()
            resp = requests.request(
                method,
                url,
                headers=headers,
                params=params if method == "GET" else None,
                json=body if method != "GET" else None,
                timeout=10
            )
            cost = int((time.time() - start) * 1000)

            self.status_label.setText(
                f"Status: {resp.status_code} | Time: {cost} ms"
            )

            try:
                self.response_output.setText(
                    json.dumps(resp.json(), indent=2, ensure_ascii=False)
                )
            except Exception:
                self.response_output.setText(resp.text)

            self.tabs.setCurrentWidget(self.response_output)
            self.save_history(method, url, headers, params, body)

        except requests.RequestException as e:
            QMessageBox.critical(self, "请求失败", str(e))

    # ================= History =================
    def save_history(self, method, url, headers, params, body):
        item = {
            "method": method,
            "url": url,
            "headers": headers,
            "params": params,
            "body": body
        }
        self.history.insert(0, item)
        self.history = self.history[:50]
        HISTORY_FILE.write_text(
            json.dumps(self.history, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        self.refresh_history_ui()

    def load_history(self):
        if HISTORY_FILE.exists():
            self.history = json.loads(
                HISTORY_FILE.read_text(encoding="utf-8")
            )

    def refresh_history_ui(self):
        self.history_list.clear()
        for h in self.history:
            self.history_list.addItem(f"{h['method']} {h['url']}")

    def load_from_history(self, item):
        index = self.history_list.row(item)
        h = self.history[index]
        self.method_box.setCurrentText(h["method"])
        self.url_input.setText(h["url"])
        self.headers_input.setText(
            json.dumps(h["headers"], indent=2, ensure_ascii=False)
        )
        self.params_input.setText(
            json.dumps(h["params"], indent=2, ensure_ascii=False)
        )
        self.body_input.setText(
            json.dumps(h["body"], indent=2, ensure_ascii=False)
        )

    def clear_history(self):
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有历史记录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.history.clear()
        self.history_list.clear()

        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()

        QMessageBox.information(self, "完成", "历史记录已清空")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = APITesterPro()
    win.show()
    sys.exit(app.exec_())
