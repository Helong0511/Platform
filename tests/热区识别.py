import wx
import os
import json

JSON_PATH = "regions.json"


def fmt(v):
    return None if abs(v) < 0.5 else round(v, 2)


class ImagePanel(wx.Panel):
    def __init__(self, parent, image_path, regions_dict, callback):
        super().__init__(parent)

        self.parent = parent
        self.image_path = image_path
        self.regions = regions_dict
        self.callback = callback

        self.start_pos = None
        self.end_pos = None
        self.mouse_pos = None

        self.scale = 1.0
        self.min_scale = 0.1
        self.max_scale = 10.0

        self.mode = None
        self.region_order = ["apple", "google", "auto"]
        self.region_index = self.count_existing_regions()

        img = wx.Image(image_path, wx.BITMAP_TYPE_ANY)
        self.bitmap_raw = wx.Bitmap(img)
        self.img = img
        self.apply_scale()

        self.offset_x = 0
        self.offset_y = 0

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_resize)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_left_up)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_wheel)
        self.Bind(wx.EVT_MOTION, self.on_mouse_move)

    # 计算已经有几个区域
    def count_existing_regions(self):
        return sum(1 for k in ["apple", "google", "auto"] if self.regions.get(k))

    def apply_scale(self):
        w = int(self.bitmap_raw.GetWidth() * self.scale)
        h = int(self.bitmap_raw.GetHeight() * self.scale)
        img2 = self.img.Scale(w, h, wx.IMAGE_QUALITY_HIGH)
        self.bitmap_scaled = wx.Bitmap(img2)

    # 缩放
    def on_mouse_wheel(self, event):
        old_scale = self.scale

        if event.GetWheelRotation() > 0:
            self.scale *= 1.1
        else:
            self.scale /= 1.1

        self.scale = max(self.min_scale, min(self.max_scale, self.scale))
        if abs(self.scale - old_scale) < 0.0001:
            return

        mx, my = event.GetPosition()
        img_x = (mx - self.offset_x) / old_scale
        img_y = (my - self.offset_y) / old_scale

        self.apply_scale()

        self.offset_x = int(mx - img_x * self.scale)
        self.offset_y = int(my - img_y * self.scale)
        self.Refresh()

    # 居中
    def on_resize(self, event):
        self.center_image()
        self.Refresh()
        event.Skip()

    def center_image(self):
        pw, ph = self.GetSize()
        iw = self.bitmap_scaled.GetWidth()
        ih = self.bitmap_scaled.GetHeight()
        self.offset_x = int((pw - iw) / 2)
        self.offset_y = int((ph - ih) / 2)

    def screen_to_image(self, x, y):
        return (x - self.offset_x) / self.scale, (y - self.offset_y) / self.scale

    # 开始框选
    def on_left_down(self, event):
        self.start_pos = self.screen_to_image(*event.GetPosition())
        self.end_pos = None

    # 框选结束
    def on_left_up(self, event):
        if not self.start_pos:
            return

        self.end_pos = self.screen_to_image(*event.GetPosition())
        x0 = min(self.start_pos[0], self.end_pos[0])
        y0 = min(self.start_pos[1], self.end_pos[1])
        w = abs(self.end_pos[0] - self.start_pos[0])
        h = abs(self.end_pos[1] - self.start_pos[1])

        if w < 3 or h < 3:
            return

        iw = self.bitmap_raw.GetWidth()
        ih = self.bitmap_raw.GetHeight()

        left = x0 / iw * 100
        top = y0 / ih * 100
        width = w / iw * 100
        height = h / ih * 100
        right = 100 - (left + width)
        bottom = 100 - (top + height)

        region = {
            "left": fmt(left), "right": fmt(right),
            "top": fmt(top), "bottom": fmt(bottom),
            "width": round(width, 2), "height": round(height, 2)
        }

        # 自动分配 or 重选
        if self.mode:
            slot = self.mode
            self.mode = None
        else:
            slot = self.region_order[min(self.region_index, 2)]
            self.region_index += 1

        self.regions[slot] = region
        self.callback(slot, region)

        self.start_pos = None
        self.end_pos = None
        self.Refresh()

    def on_mouse_move(self, event):
        self.mouse_pos = self.screen_to_image(*event.GetPosition())
        if event.LeftIsDown() and self.start_pos:
            self.end_pos = self.screen_to_image(*event.GetPosition())
        self.Refresh()

    # 重选
    def reset_region(self, key):
        self.mode = key
        print(f"👉 正在重选：{key}")

    # 清空
    def clear_regions(self):
        self.regions = {"apple": None, "google": None, "auto": None}
        self.region_index = 0
        self.mode = None
        self.Refresh()

    # ⭐⭐⭐ GraphicsContext 透明绘制（核心）
    def draw_transparent_rect(self, gc, x, y, w, h):
        # 透明填充
        brush = gc.CreateBrush(wx.Brush(wx.Colour(0, 255, 0, 80)))  # 透明绿
        gc.SetBrush(brush)

        # 半透明边框
        pen = gc.CreatePen(wx.Pen(wx.Colour(0, 255, 0, 200), 3))
        gc.SetPen(pen)

        gc.DrawRectangle(x, y, w, h)

    # ⭐⭐⭐ 绘制事件
    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()

        self.center_image()
        dc.DrawBitmap(self.bitmap_scaled, int(self.offset_x), int(self.offset_y))

        # 使用 GraphicsContext
        gc = wx.GraphicsContext.Create(dc)

        # -------- 绘制已识别区域 --------
        for key, r in self.regions.items():
            if not r:
                continue

            iw = self.bitmap_raw.GetWidth()
            ih = self.bitmap_raw.GetHeight()

            x = int(r["left"] / 100 * iw * self.scale + self.offset_x)
            y = int(r["top"] / 100 * ih * self.scale + self.offset_y)
            w = int(r["width"] / 100 * iw * self.scale)
            h = int(r["height"] / 100 * ih * self.scale)

            self.draw_transparent_rect(gc, x, y, w, h)

        # -------- 绘制正在框选 --------
        if self.start_pos and self.end_pos:
            x0 = min(self.start_pos[0], self.end_pos[0])
            y0 = min(self.start_pos[1], self.end_pos[1])
            w = abs(self.end_pos[0] - self.start_pos[0])
            h = abs(self.end_pos[1] - self.start_pos[1])

            x = int(x0 * self.scale + self.offset_x)
            y = int(y0 * self.scale + self.offset_y)
            w = int(w * self.scale)
            h = int(h * self.scale)

            self.draw_transparent_rect(gc, x, y, w, h)

        # -------- 十字线 --------
        if self.mouse_pos:
            mx = int(self.mouse_pos[0] * self.scale + self.offset_x)
            my = int(self.mouse_pos[1] * self.scale + self.offset_y)

            ox = int(self.offset_x)
            oy = int(self.offset_y)
            iw = self.bitmap_scaled.GetWidth()
            ih = self.bitmap_scaled.GetHeight()

            dc.SetPen(wx.Pen(wx.Colour(255, 0, 0, 180), 1))
            dc.DrawLine(mx, oy, mx, oy + ih)
            dc.DrawLine(ox, my, ox + iw, my)


# =============================
# 主窗口
# =============================
class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="透明框自动识别热区工具", size=(900, 1100))
        self.Centre()

        # 加载 JSON
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                self.json_data = json.load(f)
        else:
            self.json_data = {}

        self.files = []
        self.index = 0
        self.panel = None
        self.image_dir = ""

        top = wx.Panel(self)
        choose_btn = wx.Button(top, label="选择图片目录")
        choose_btn.Bind(wx.EVT_BUTTON, self.choose_directory)

        reset_apple = wx.Button(top, label="重选苹果区域")
        reset_google = wx.Button(top, label="重选谷歌区域")
        reset_auto = wx.Button(top, label="重选自动识别")

        reset_apple.Bind(wx.EVT_BUTTON, lambda e: self.panel.reset_region("apple"))
        reset_google.Bind(wx.EVT_BUTTON, lambda e: self.panel.reset_region("google"))
        reset_auto.Bind(wx.EVT_BUTTON, lambda e: self.panel.reset_region("auto"))

        clear_btn = wx.Button(top, label="清空当前图片")
        clear_btn.Bind(wx.EVT_BUTTON, lambda e: self.panel.clear_regions())

        next_btn = wx.Button(top, label="下一张 →")
        next_btn.Bind(wx.EVT_BUTTON, self.next_image)
        self.next_btn = next_btn
        self.next_btn.Disable()

        h = wx.BoxSizer(wx.HORIZONTAL)
        h.Add(choose_btn, 0, wx.ALL, 10)
        h.Add(reset_apple, 0, wx.ALL, 10)
        h.Add(reset_google, 0, wx.ALL, 10)
        h.Add(reset_auto, 0, wx.ALL, 10)
        h.Add(clear_btn, 0, wx.ALL, 10)
        h.Add(next_btn, 0, wx.ALL, 10)
        top.SetSizer(h)

        self.main = wx.BoxSizer(wx.VERTICAL)
        self.main.Add(top, 0, wx.EXPAND)
        self.SetSizer(self.main)

    def choose_directory(self, event):
        dlg = wx.DirDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.image_dir = dlg.GetPath()
            self.load_images()
        dlg.Destroy()

    def load_images(self):
        self.files = [
            f for f in os.listdir(self.image_dir)
            if f.lower().endswith((".jpg", ".png"))
        ]

        if not self.files:
            wx.MessageBox("未找到图片")
            return

        self.index = 0
        self.next_btn.Enable()
        self.load_image_panel()

    def load_image_panel(self):
        if self.panel:
            self.panel.Destroy()

        fname = self.files[self.index]
        img_path = os.path.join(self.image_dir, fname)

        # 自动识别已有区域
        if fname in self.json_data:
            regions = self.json_data[fname]
        else:
            regions = {"apple": None, "google": None, "auto": None}

        self.json_data[fname] = regions

        self.panel = ImagePanel(self, img_path, regions, self.on_region_selected)
        self.main.Add(self.panel, 1, wx.EXPAND)
        self.Layout()

    def on_region_selected(self, slot, region):
        fname = self.files[self.index]
        self.json_data[fname][slot] = region
        print(f"✔ 更新 {slot}：", region)

    def next_image(self, event):
        self.index += 1
        if self.index >= len(self.files):
            self.save_json()
            return

        self.load_image_panel()

    def save_json(self):
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(self.json_data, f, indent=4, ensure_ascii=False)

        wx.MessageBox("regions.json 已保存！", "完成")
        self.Close()


class App(wx.App):
    def OnInit(self):
        frame = MainFrame()
        frame.Show()
        return True


if __name__ == "__main__":
    app = App()
    app.MainLoop()