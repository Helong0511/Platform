import json
import os
import re

import wx

JSON_PATH = "regions.json"


def build_block(classname, region):
    """严格生成与第二张截图完全一致的格式（含 4 空格缩进）"""

    if classname == "apple":
        return (
            ".apple-btn {\n"
            f"			top: {region['top']}%;\n"
            f"			right: {region['right']}%;\n"
            f"			width: {region['width']}%;\n"
            f"			height: {region['height']}%;\n"
            "		}"
        )

    if classname == "google":
        return (
            ".google-btn {\n"
            f"			top: {region['top']}%;\n"
            f"			right: {region['right']}%;\n"
            f"			width: {region['width']}%;\n"
            f"			height: {region['height']}%;\n"
            "		}"
        )

    if classname == "bottom":
        return (
            ".bottom-btn {\n"
            f"			bottom: {region['bottom']}%;\n"
            f"			left: {region['left']}%;\n"
            f"			width: {region['width']}%;\n"
            f"			height: {region['height']}%;\n"
            "		}"
        )


class AutoWriter(wx.Frame):
    def __init__(self):
        super().__init__(None, title="全自动 HTML 热区写入工具（完美格式版）", size=(700, 300))
        self.Centre()

        panel = wx.Panel(self)

        btn_img = wx.Button(panel, label="选择 图片目录（jpg/png）")
        btn_html = wx.Button(panel, label="选择 HTML 目录")
        btn_start = wx.Button(panel, label="开始写入")

        self.txt_img = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.txt_html = wx.TextCtrl(panel, style=wx.TE_READONLY)

        btn_img.Bind(wx.EVT_BUTTON, self.select_img_dir)
        btn_html.Bind(wx.EVT_BUTTON, self.select_html_dir)
        btn_start.Bind(wx.EVT_BUTTON, self.start_run)

        layout = wx.BoxSizer(wx.VERTICAL)

        line1 = wx.BoxSizer(wx.HORIZONTAL)
        line1.Add(btn_img, 0, wx.ALL, 10)
        line1.Add(self.txt_img, 1, wx.ALL | wx.EXPAND, 10)

        line2 = wx.BoxSizer(wx.HORIZONTAL)
        line2.Add(btn_html, 0, wx.ALL, 10)
        line2.Add(self.txt_html, 1, wx.ALL | wx.EXPAND, 10)

        layout.Add(line1)
        layout.Add(line2)
        layout.Add(btn_start, 0, wx.ALL | wx.CENTER, 10)

        panel.SetSizer(layout)

        # 加载 regions.json
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                self.regions = json.load(f)
        else:
            wx.MessageBox("未找到 regions.json 文件！", "错误")

    def select_img_dir(self, e):
        dlg = wx.DirDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.img_dir = dlg.GetPath()
            self.txt_img.SetValue(self.img_dir)
        dlg.Destroy()

    def select_html_dir(self, e):
        dlg = wx.DirDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.html_dir = dlg.GetPath()
            self.txt_html.SetValue(self.html_dir)
        dlg.Destroy()

    def start_run(self, e):

        img_files = [
            f for f in os.listdir(self.img_dir)
            if f.lower().endswith(("jpg", "png"))
        ]

        html_map = {
            f.lower(): os.path.join(self.html_dir, f)
            for f in os.listdir(self.html_dir)
            if f.lower().endswith(".html")
        }

        count = 0
        for img in img_files:
            key = img
            html_name = os.path.splitext(img)[0] + ".html"

            if html_name.lower() not in html_map:
                print(f"❌ 无匹配 HTML：{img}")
                continue

            if key not in self.regions:
                print(f"❌ JSON 中没有热区：{img}")
                continue

            html_path = html_map[html_name.lower()]
            self.update_html(html_path, self.regions[key])
            count += 1

        wx.MessageBox(f"已成功更新 {count} 个 HTML 文件！", "完成")

    def update_html(self, path, region):

        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        # 生成 3 个 CSS 块
        apple_css = build_block("apple", region["apple"])
        google_css = build_block("google", region["google"])
        bottom_css = build_block("bottom", region["auto"])

        # 精准替换每一个 class
        html = re.sub(r"\.apple-btn\s*\{[^}]*\}", apple_css.strip(), html)
        html = re.sub(r"\.google-btn\s*\{[^}]*\}", google_css.strip(), html)
        html = re.sub(r"\.bottom-btn\s*\{[^}]*\}", bottom_css.strip(), html)

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"✔ 更新成功：{path}")


class App(wx.App):
    def OnInit(self):
        frame = AutoWriter()
        frame.Show()
        return True


if __name__ == "__main__":
    app = App()
    app.MainLoop()
