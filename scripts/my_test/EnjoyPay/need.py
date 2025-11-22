import hashlib
import datetime
import random
import string

DEBUG = True  # 是否为测试环境 False:正式环境 True:测试环境

if DEBUG:
    Merchant_ID = 1
    appId = 1
    Share_Key = "F194D4E7CFA14D54842CEC1AF3637150"
else:
    Merchant_ID = 1000
    appId = 2
    Share_Key = "08ACA619BDFE4FF28C4011B864BA3496"

Request_Domain = 'pay-rx.com'

Request_Address = f"https://api.{Request_Domain}"

# 代收请求地址
Request_Order_url = f"{Request_Address}/v1/pay/payin"

# 代付请求地址
Request_Transfer_url = f"{Request_Address}/v1/pay/payout"

# 代收订单查询请求地址
Request_Query_Order_url = f"{Request_Address}/v1/pay/query"

# 退款请求地址
Request_Refund_url = f"{Request_Address}/v1/pay/refund"

# 余额查询请求地址
Request_Balance_url = f"{Request_Address}/v1/pay/queryBalance"

# 请求头
Request_Headers = {'Content-Type': 'application/json'}

# 通知域名
Notify_Domain = 'king-sms.com'

# 代收通知地址
in_notify_url = f"https://notify.{Notify_Domain}/global_pay_in_notify"

# 代付通知地址
out_notify_url = f"https://notify.{Notify_Domain}/global_pay_out_notify"

# 退款通知地址
refund_notify_url = f"https://notify.{Notify_Domain}/global_refund_notify"

Time_Out = 5  # 请求超时时间 秒


def get_str_md5(content):
    try:
        md5 = hashlib.md5(content.encode(encoding='utf-8'))  # 创建md5对象
        return md5.hexdigest()
    except Exception as e:
        print(f"MD5生成失败: {e}")
        return None


# 获取当前时间字符串
def get_str_order_number(test=False):
    try:
        now_time = datetime.datetime.now()
        temp_str = (str(now_time.year).rjust(4, "0") +
                    str(now_time.month).rjust(2, "0") +
                    str(now_time.day).rjust(2, "0") +
                    str(now_time.hour).rjust(2, "0") +
                    str(now_time.minute).rjust(2, "0") +
                    str(now_time.second).rjust(2, "0") +
                    str(now_time.microsecond).zfill(6))

        if test:
            return "Test-" + temp_str
        else:
            return temp_str
    except Exception as e:
        print(f"获取当前时间字符串失败: {e}")
        return None


# 随机生成一个巴西姓名
def get_brazil_random_name(sex=None, abbr=False):
    """
    生成一个随机的巴西名字，可以指定性别和是否缩写。
    :param sex: 男性 "male" 或 女性 "female"，如果为 None，则随机选择性别
    :param abbr:   True: 缩写形式，如 "J.P.Silva"；
    :return:
    """

    # 男性常见名字
    male_names = [
        "João", "Pedro", "Carlos", "Paulo", "José", "Lucas", "Gabriel", "Rafael",
        "Thiago", "Rodrigo", "Felipe", "Bruno", "Gustavo", "Diego", "André", "Daniel"
    ]

    # 女性常见名字
    female_names = [
        "Maria", "Ana", "Juliana", "Fernanda", "Mariana", "Camila", "Beatriz",
        "Larissa", "Patrícia", "Carolina", "Aline", "Cláudia", "Tatiane", "Renata",
        "Vanessa", "Sabrina"
    ]

    # 常见巴西姓氏
    last_names = [
        "Silva", "Santos", "Oliveira", "Souza", "Pereira", "Lima", "Carvalho",
        "Rodrigues", "Almeida", "Costa", "Gomes", "Martins", "Araújo", "Ribeiro",
        "Fernandes", "Barbosa", "Moura", "Dias", "Moreira", "Teixeira"
    ]

    # 随机确定性别
    if sex is None:
        sex = random.choice(["male", "female"])

    # 选名字
    if sex == "male":
        first = random.choice(male_names)
    else:
        first = random.choice(female_names)

    # 姓氏个数（1 ~ 3 个）
    num_surnames = random.choice([1, 2, 2, 3])  # 2个最常见
    surnames = random.sample(last_names, num_surnames)

    if abbr:
        # 缩写形式：名字 + 中间名首字母 + 姓氏
        if len(surnames) > 1:
            middle_initials = "".join([s[0] + "." for s in surnames[:-1]])
            return f"{first} {middle_initials} {surnames[-1]}"
        else:
            return f"{first} {surnames[0]}"
    else:
        # 全名形式
        return f"{first} {''.join(surnames)}"


# 随机生成一个巴西手机号
def get_brazil_random_mobile_number(mat=False):
    # 常见巴西 DDD 区号
    ddd_list = [
        11, 12, 13, 14, 15, 16, 17, 18, 19,  # São Paulo 州
        21, 22, 24,  # Rio de Janeiro 州
        31, 32, 33, 34, 35, 37, 38,  # Minas Gerais 州
        41, 42, 43, 44, 45, 46,  # Paraná 州
        47, 48, 49,  # Santa Catarina 州
        51, 53, 54, 55,  # Rio Grande do Sul 州
        61,  # Brasília
        62, 64,  # Goiás
        71, 73, 74, 75, 77,  # Bahia 州
        81, 82, 83, 84, 85, 86, 87, 88, 89,  # 东北地区
        91, 92, 93, 94, 95, 96, 97, 98, 99  # 北部地区
    ]

    ddd = random.choice(ddd_list)
    # 手机号固定以 9 开头 + 随机 8 位
    number = "9" + "".join([str(random.randint(0, 9)) for _ in range(8)])

    if mat:
        # 格式化为 +55 (DDD) 9XXXX-XXXX
        return f"+55 ({ddd}) {number[:5]}-{number[5:]}"
    else:
        # 国际简写形式：+55DDDNúmero
        return f"{ddd}{number}"


def get_random_email(name=None):
    # 常见邮箱域名
    domains = [
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "icloud.com", "aol.com", "protonmail.com",
        "uol.com.br", "bol.com.br", "terra.com.br",  # 巴西
        "rediffmail.com", "zoho.in"  # 印度
    ]

    # 如果传入了名字，就用名字拼接
    if name:
        username = name.lower().replace(" ", ".")
        # 可能加上数字以避免重复
        if random.random() < 0.5:
            username += str(random.randint(1, 99))
    else:
        # 随机生成用户名：字母 + 数字
        length = random.randint(6, 10)
        letters = string.ascii_lowercase
        username = "".join(random.choices(letters + string.digits, k=length))

    domain = random.choice(domains)

    return f"{username}@{domain}"

# print(get_brazil_random_name(sex="male", abbr=True))
# print(get_brazil_random_mobile_number())
# print(get_random_email(name=get_brazil_random_name(abbr=False)))
