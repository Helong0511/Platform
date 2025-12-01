import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

# 配置你的 Gmail 账号信息
GMAIL_USER = 'hel290390@gmail.com'
GMAIL_PASSWORD = 'He800407'  # 这里填入你的 16位 应用专用密码


# ============================
# 1. 发送邮件功能 (SMTP)
# ============================
def send_email(to_email, subject, body):
    try:
        # 创建邮件对象
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = subject

        # 添加邮件正文
        msg.attach(MIMEText(body, 'plain'))

        # 连接到 Gmail SMTP 服务器
        # 端口 587 用于 TLS 加密
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # 开启加密传输

        # 登录并发送
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(GMAIL_USER, to_email, text)
        server.quit()

        print(f"✅ 邮件已成功发送给: {to_email}")

    except Exception as e:
        print(f"❌ 发送失败: {e}")


# ============================
# 2. 接收邮件功能 (IMAP)
# ============================
def receive_emails(limit=3):
    print(f"\n📥 正在读取最近的 {limit} 封邮件...")
    try:
        # 连接到 Gmail IMAP 服务器
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(GMAIL_USER, GMAIL_PASSWORD)

        # 选择收件箱
        mail.select("inbox")

        # 搜索所有邮件 (也可以搜索 'UNSEEN' 未读邮件)
        status, messages = mail.search(None, 'ALL')

        # 获取邮件 ID 列表
        mail_ids = messages[0].split()

        # 获取最近的 limit 封邮件 (倒序遍历)
        latest_email_ids = mail_ids[-limit:]

        for i in reversed(latest_email_ids):
            # 获取邮件数据
            res, msg_data = mail.fetch(i, "(RFC822)")

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    # 解析邮件内容
                    msg = email.message_from_bytes(response_part[1])

                    # 解码标题
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")

                    # 解码发送者
                    from_ = msg.get("From")

                    print("-" * 50)
                    print(f"Subject: {subject}")
                    print(f"From: {from_}")

                    # 解析正文 (处理纯文本和 HTML)
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = part.get("Content-Disposition")  # 处理附件

                            try:
                                body = part.get_payload(decode=True).decode()
                            except:
                                body = "[无法解码的内容]"

                            if content_type == "text/plain" and "attachment" not in str(content_disposition):
                                print(f"Body: {body.strip()[:100]}...")  # 只打印前100个字
                    else:
                        # 非多部分邮件（只有纯文本）
                        body = msg.get_payload(decode=True).decode()
                        print(f"Body: {body.strip()[:100]}...")

        mail.close()
        mail.logout()

    except Exception as e:
        print(f"❌ 读取失败: {e}")


# ============================
# 主程序入口
# ============================
if __name__ == "__main__":
    # 测试 1: 发送邮件
    # 请将下面的地址改为你真实的接收邮箱
    send_email("183072530@qq.com", "Python 测试邮件", "你好！这是通过 Python 脚本发送的邮件。")

    # 测试 2: 接收邮件
    receive_emails(limit=2)