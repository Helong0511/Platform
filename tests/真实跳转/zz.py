# ==============================
# wxPython 跳转链分析工具（最终完整版）
# 功能：
# 1. 真实浏览器抓跳转（Playwright）
# 2. 只保留“文档跳转”（过滤JS/CSS等资源）
# 3. 域名解析 + 去重
# 4. 清晰输出（原始URL / 跳转次数 / 域名链）
# ==============================

# 安装：
# pip install wxPython playwright
# python -m playwright install chromium

import wx
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# ==============================
# 核心：抓取真实跳转链（只保留 document）
# ==============================

def trace_url(url):
    chain = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                "Mobile/15E148 Safari/604.1"
            )
        )

        page = context.new_page()

        # 只记录 document 类型（关键修复点）
        def handle_request(request):
            if request.resource_type == "document":
                chain.append(request.url)

        page.on("request", handle_request)

        try:
            page.goto(url, timeout=30000, wait_until="load")
        except:
            pass

        browser.close()

    # 去重（保留顺序）
    seen = set()
    result = []
    for u in chain:
        if u not in seen:
            seen.add(u)
            result.append(u)

    return result

# ==============================
# 域名提取 + 去重（更适合分析）
# ==============================

def extract_domains(chain):
    domains = []
    seen = set()

    for u in chain:
        domain = urlparse(u).netloc
        if domain and domain not in seen:
            seen.add(domain)
            domains.append(domain)

    return domains

# ==============================
# 简单风险标记
# ==============================

def classify_domain(domain):
    if ".click" in domain:
        return "高风险(广告链)"
    if "redirect" in domain or "track" in domain:
        return "中转域"
    if domain.count('.') <= 1:
        return "主站"
    return "普通"

# ==============================
# UI界面
# ==============================

class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="跳转链分析工具（专业版）", size=(1000, 700))

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 输入框
        self.url_input = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.url_input.SetHint("输入URL...")
        vbox.Add(self.url_input, flag=wx.EXPAND | wx.ALL, border=10)

        # 按钮
        self.btn = wx.Button(panel, label="开始分析")
        vbox.Add(self.btn, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

        # 输出框
        self.output = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        vbox.Add(self.output, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)

        panel.SetSizer(vbox)

        # 绑定事件
        self.btn.Bind(wx.EVT_BUTTON, self.on_trace)
        self.url_input.Bind(wx.EVT_TEXT_ENTER, self.on_trace)

    def on_trace(self, event):
        url = self.url_input.GetValue().strip()
        if not url:
            return

        self.output.SetValue(f"原始URL: {url}\n正在分析，请稍候...\n")
        wx.Yield()

        try:
            chain = trace_url(url)
            domains = extract_domains(chain)

            result_text = f"原始URL: {url}\n"
            result_text += f"真实跳转次数: {len(domains)}\n\n"

            result_text += "【域名跳转链】\n"
            for i, d in enumerate(domains):
                tag = classify_domain(d)
                result_text += f"[{i+1}] {d}  ({tag})\n"

            result_text += "\n【完整URL链】\n"
            for i, u in enumerate(chain):
                result_text += f"[{i+1}] {u}\n"

            if domains:
                result_text += f"\n最终落地页: {domains[-1]}\n"

            self.output.SetValue(result_text)

        except Exception as e:
            self.output.SetValue(f"错误: {e}")


# ==============================
# 启动
# ==============================

if __name__ == "__main__":
    app = wx.App()
    frame = MainFrame()
    frame.Show()
    app.MainLoop()
