import datetime
import os
import mysql.connector as mysql

config = {
    "host": "43.156.101.243",
    "port": 3306,
    "user": "remote",
    "password": "kb7$rL3d8!tQ",
    "database": "platform",
    "charset": "utf8mb4",
    "raise_on_warnings": True
}

# 连接到 MySQL 数据库
conn = mysql.connect(**config)
cursor = conn.cursor()

sql_file = r"E:\data\Platform\scripts\data\append_data.sql"

if os.path.exists(sql_file):
    os.remove(sql_file)

hand = open(sql_file, "w", encoding="utf-8")

hand.write("USE platform;\n\n")

need_exp = [
    {
        "table_name": "`users`",
        "field_name": "`id`, `username`, `hashed_password`, `full_name`, `email`, `role`, `is_active`",
        "order": "`id`",
        "note": "-- 添加用户数据\n"
    },
    {
        "table_name": "`clients`",
        "field_name": "`id`, `user_id`, `company_name`, `key`, `is_active`, `api_enabled`, `password_change_enabled`",
        "order": "`id`",
        "note": "-- 添加客户数据\n"
    },
    {
        "table_name": "`products`",
        "field_name": "`id`, `client_id`, `name`, `ecpm_deduct_ratio`, `revenue_deduct_ratio`, `is_active`",
        "order": "`id`",
        "note": "-- 添加产品数据\n"
    },
    {
        "table_name": "`product_assignments`",
        "field_name": "`product_id`, `client_id`, `start_date`, `end_date`",
        "order": "`product_id`, `start_date`",
        "note": "-- 添加产品历史分配数据\n"
    },
    {
        "table_name": "`ad_data`",
        "field_name": "`date`, `product_id`, `request_count`, `match_count`, `display_count`, `click_count`, `ecpm_before_deduct`, `ecpm_after_deduct`, `revenue_before_deduct`, `revenue_after_deduct`",
        "order": "`date`, `product_id`",
        "note": "-- 添加广告数据\n",
        "exclude_today": True  # 添加标记，表示需要排除当天数据
    }
]

a = 0
for exp in need_exp:
    a = a + 1
    table_name = exp.get("table_name", "")
    field_name = exp.get("field_name", "")
    order = exp.get("order", "")
    note = exp.get("note", "")
    exclude_today = exp.get("exclude_today", False)  # 获取是否排除当天数据的标记

    if a > 1:
        hand.write("\n")

    hand.write(note)

    # 构建SQL查询语句
    if exclude_today:
        # 对于ad_data表，添加条件排除当天数据
        today = datetime.date.today()
        if order:
            sql = f"SELECT {field_name} FROM {table_name} WHERE `date` < '{today}' ORDER BY {order} ASC ;"
        else:
            sql = f"SELECT {field_name} FROM {table_name} WHERE `date` < '{today}' ;"
    else:
        # 其他表正常查询
        if order:
            sql = f"SELECT {field_name} FROM {table_name} ORDER BY {order} ASC ;"
        else:
            sql = f"SELECT {field_name} FROM {table_name} ;"

    cursor.execute(sql)
    info = cursor.fetchall()
    if info:
        if len(info) > 0:
            hand.write(f"INSERT INTO {table_name} ({field_name}) VALUES \n")
        i = 0
        for item in info:
            i = i + 1

            wr = "("
            for b in range(len(item)):

                if item[b] is None:
                    wr = wr + "NULL"
                elif isinstance(item[b], int):
                    wr = wr + str(item[b])
                elif isinstance(item[b], float):
                    wr = wr + f"{item[b]:.2f}"
                elif isinstance(item[b], str):
                    wr = wr + "'" + str(item[b]) + "'"
                elif isinstance(item[b], datetime.date):
                    wr = wr + "'" + str(item[b]) + "'"
                else:
                    print(type(item[b]))

                if b == len(item) - 1:
                    wr = wr + ")"
                else:
                    wr = wr + ","

            hand.write(wr)

            if i == len(info):
                hand.write(";\n")
            else:
                hand.write(",\n")

        print('表', table_name.replace('`', ''), f'{i}条数据生成完毕！')


    if table_name == "`users`":
        hand.write("\nUPDATE `users` SET `hashed_password` = '$2b$12$geFYoAmb0ZA7Be4LJX/40uudVPltdtwCGFxC5aDIP7xQ/ImTJPIdO' WHERE `username` = 'admin';\n")

    if table_name == "`ad_data`":
        hand.write("\n-- 更新广告数据统计字段（避免除零错误）\n")
        hand.write("UPDATE `ad_data` SET `coverage_rate` = CASE WHEN `request_count` > 0 THEN ROUND(`match_count` / `request_count` * 100, 2) ELSE 0 END;\n")
        hand.write("UPDATE `ad_data` SET `display_rate` = CASE WHEN `match_count` > 0 THEN ROUND(`display_count` / `match_count` * 100, 2) ELSE 0 END;\n")
        hand.write("UPDATE `ad_data` SET `click_rate` = CASE WHEN `display_count` > 0 THEN ROUND(`click_count` / `display_count` * 100, 2) ELSE 0 END;\n")




wr = """\nINSERT INTO `scheduled_tasks` (`task_name`, `cron_expression`, `description`, `function_path`, `is_active`) VALUES 
('数据归档任务', '0 1 1 * *', '归档6个月前的数据','app.scheduler_module.tasks.archive_old_data.archive_old_ad_data', 1),
('清理旧日志', '0 2 1 * *','清理90天前的用户操作日志，减少日志表数据量','app.scheduler_module.tasks.cleanup_old_logs.cleanup_old_audit_logs', 1),
('清理过期会话和黑名单', '0 2 * * *','清理过期超过30天的会话记录和黑名单记录，标记超过7天未活动的会话为非活跃','app.scheduler_module.tasks.cleanup_expired_sessions.cleanup_expired_sessions', 1),
('TQT API获取数据', '*/10 * * * *', '每隔10分钟执行一次，从TQT API获取广告数据并导入到数据库','app.scheduler_module.tasks.tqt_task.tqt_api_task', 1),
('Skymobi API获取数据', '*/10 * * * *', '每隔10分钟执行一次，从Skymobi API获取广告数据','app.scheduler_module.tasks.skymobi_task.skymobi_api_task', 1);\n"""
hand.write(wr)

wr = """\nINSERT INTO `countries` (`alpha_2_code`, `alpha_3_code`, `numeric_code`, `country_name_zh`, `country_name_en`, `official_name_zh`, `official_name_en`, `independent_status`, `continent`, `subregion`) VALUES 
('AA', 'AAA', '000', '未知区域', 'unknown', '未知区域', 'unknown', 1, '全球', '任意地区'),
('AF', 'AFG', '004', '阿富汗', 'Afghanistan', '阿富汗伊斯兰共和国', 'Islamic Republic of Afghanistan', 1, '亚洲', '中亚'),
('AX', 'ALA', '248', '奥兰群岛', 'Åland Islands', NULL, NULL, 0, '欧洲', '北欧'),
('AL', 'ALB', '008', '阿尔巴尼亚', 'Albania', '阿尔巴尼亚共和国', 'Republic of Albania', 1, '欧洲', '南欧'),
('DZ', 'DZA', '012', '阿尔及利亚', 'Algeria', '阿尔及利亚人民民主共和国', 'People''s Democratic Republic of Algeria', 1, '非洲', '北非'),
('AS', 'ASM', '016', '美属萨摩亚', 'American Samoa', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
('AD', 'AND', '020', '安道尔', 'Andorra', '安道尔公国', 'Principality of Andorra', 1, '欧洲', '南欧'),
('AO', 'AGO', '024', '安哥拉', 'Angola', '安哥拉共和国', 'Republic of Angola', 1, '非洲', '中非'),
('AI', 'AIA', '660', '安圭拉', 'Anguilla', NULL, NULL, 0, '美洲', '加勒比'),
('AQ', 'ATA', '010', '南极洲', 'Antarctica', NULL, NULL, 0, '南极洲', NULL),
('AG', 'ATG', '028', '安提瓜和巴布达', 'Antigua and Barbuda', NULL, NULL, 1, '美洲', '加勒比'),
('AR', 'ARG', '032', '阿根廷', 'Argentina', '阿根廷共和国', 'Argentine Republic', 1, '美洲', '南美洲'),
('AM', 'ARM', '051', '亚美尼亚', 'Armenia', '亚美尼亚共和国', 'Republic of Armenia', 1, '亚洲', '西亚'),
('AW', 'ABW', '533', '阿鲁巴', 'Aruba', NULL, NULL, 0, '美洲', '加勒比'),
('AU', 'AUS', '036', '澳大利亚', 'Australia', '澳大利亚联邦', 'Commonwealth of Australia', 1, '大洋洲', '澳大利亚和新西兰'),
('AT', 'AUT', '040', '奥地利', 'Austria', '奥地利共和国', 'Republic of Austria', 1, '欧洲', '中欧'),
('AZ', 'AZE', '031', '阿塞拜疆', 'Azerbaijan', '阿塞拜疆共和国', 'Republic of Azerbaijan', 1, '亚洲', '西亚'),
('BS', 'BHS', '044', '巴哈马', 'Bahamas', '巴哈马联邦', 'Commonwealth of the Bahamas', 1, '美洲', '加勒比'),
('BH', 'BHR', '048', '巴林', 'Bahrain', '巴林王国', 'Kingdom of Bahrain', 1, '亚洲', '西亚'),
('BD', 'BGD', '050', '孟加拉国', 'Bangladesh', '孟加拉人民共和国', 'People''s Republic of Bangladesh', 1, '亚洲', '南亚'),
('BB', 'BRB', '052', '巴巴多斯', 'Barbados', NULL, NULL, 1, '美洲', '加勒比'),
('BY', 'BLR', '112', '白俄罗斯', 'Belarus', '白俄罗斯共和国', 'Republic of Belarus', 1, '欧洲', '东欧'),
('BE', 'BEL', '056', '比利时', 'Belgium', '比利时王国', 'Kingdom of Belgium', 1, '欧洲', '西欧'),
('BZ', 'BLZ', '084', '伯利兹', 'Belize', NULL, NULL, 1, '美洲', '中美洲'),
('BJ', 'BEN', '204', '贝宁', 'Benin', '贝宁共和国', 'Republic of Benin', 1, '非洲', '西非'),
('BM', 'BMU', '060', '百慕大', 'Bermuda', NULL, NULL, 0, '美洲', '北大西洋'),
('BT', 'BTN', '064', '不丹', 'Bhutan', '不丹王国', 'Kingdom of Bhutan', 1, '亚洲', '南亚'),
('BO', 'BOL', '068', '玻利维亚', 'Bolivia', '多民族玻利维亚国', 'Plurinational State of Bolivia', 1, '美洲', '南美洲'),
('BQ', 'BES', '535', '荷兰加勒比区', 'Bonaire, Sint Eustatius and Saba', NULL, NULL, 0, '美洲', '加勒比'),
('BA', 'BIH', '070', '波黑', 'Bosnia and Herzegovina', '波斯尼亚和黑塞哥维那', 'Bosnia and Herzegovina', 1, '欧洲', '南欧'),
('BW', 'BWA', '072', '博茨瓦纳', 'Botswana', '博茨瓦纳共和国', 'Republic of Botswana', 1, '非洲', '南非'),
('BV', 'BVT', '074', '布韦岛', 'Bouvet Island', NULL, NULL, 0, '南极洲', NULL),
('BR', 'BRA', '076', '巴西', 'Brazil', '巴西联邦共和国', 'Federative Republic of Brazil', 1, '美洲', '南美洲'),
('IO', 'IOT', '086', '英属印度洋领地', 'British Indian Ocean Territory', NULL, NULL, 0, '亚洲', '印度洋'),
('BN', 'BRN', '096', '文莱', 'Brunei Darussalam', '文莱达鲁萨兰国', 'Nation of Brunei, the Abode of Peace', 1, '亚洲', '东南亚'),
('BG', 'BGR', '100', '保加利亚', 'Bulgaria', '保加利亚共和国', 'Republic of Bulgaria', 1, '欧洲', '东欧'),
('BF', 'BFA', '854', '布基纳法索', 'Burkina Faso', NULL, NULL, 1, '非洲', '西非'),
('BI', 'BDI', '108', '布隆迪', 'Burundi', '布隆迪共和国', 'Republic of Burundi', 1, '非洲', '东非'),
('CV', 'CPV', '132', '佛得角', 'Cabo Verde', '佛得角共和国', 'Republic of Cabo Verde', 1, '非洲', '西非'),
('KH', 'KHM', '116', '柬埔寨', 'Cambodia', '柬埔寨王国', 'Kingdom of Cambodia', 1, '亚洲', '东南亚'),
('CM', 'CMR', '120', '喀麦隆', 'Cameroon', '喀麦隆共和国', 'Republic of Cameroon', 1, '非洲', '中非'),
('CA', 'CAN', '124', '加拿大', 'Canada', NULL, NULL, 1, '美洲', '北美洲'),
('KY', 'CYM', '136', '开曼群岛', 'Cayman Islands', NULL, NULL, 0, '美洲', '加勒比'),
('CF', 'CAF', '140', '中非', 'Central African Republic', '中非共和国', 'Central African Republic', 1, '非洲', '中非'),
('TD', 'TCD', '148', '乍得', 'Chad', '乍得共和国', 'Republic of Chad', 1, '非洲', '中非'),
('CL', 'CHL', '152', '智利', 'Chile', '智利共和国', 'Republic of Chile', 1, '美洲', '南美洲'),
('CN', 'CHN', '156', '中国', 'China', '中华人民共和国', 'People''s Republic of China', 1, '亚洲', '东亚'),
('CX', 'CXR', '162', '圣诞岛', 'Christmas Island', NULL, NULL, 0, '亚洲', '印度洋'),
('CC', 'CCK', '166', '科科斯（基林）群岛', 'Cocos (Keeling) Islands', NULL, NULL, 0, '亚洲', '印度洋'),
('CO', 'COL', '170', '哥伦比亚', 'Colombia', '哥伦比亚共和国', 'Republic of Colombia', 1, '美洲', '南美洲'),
('KM', 'COM', '174', '科摩罗', 'Comoros', '科摩罗联盟', 'Union of the Comoros', 1, '非洲', '东非'),
('CG', 'COG', '178', '刚果（布）', 'Congo', '刚果共和国', 'Republic of the Congo', 1, '非洲', '中非'),
('CD', 'COD', '180', '刚果（金）', 'Congo, Democratic Republic of the', '刚果民主共和国', 'Democratic Republic of the Congo', 1, '非洲', '中非'),
('CK', 'COK', '184', '库克群岛', 'Cook Islands', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
('CR', 'CRI', '188', '哥斯达黎加', 'Costa Rica', '哥斯达黎加共和国', 'Republic of Costa Rica', 1, '美洲', '中美洲'),
('CI', 'CIV', '384', '科特迪瓦', 'Côte d''Ivoire', '科特迪瓦共和国', 'Republic of Côte d''Ivoire', 1, '非洲', '西非'),
('HR', 'HRV', '191', '克罗地亚', 'Croatia', '克罗地亚共和国', 'Republic of Croatia', 1, '欧洲', '南欧'),
('CU', 'CUB', '192', '古巴', 'Cuba', '古巴共和国', 'Republic of Cuba', 1, '美洲', '加勒比'),
('CW', 'CUW', '531', '库拉索', 'Curaçao', NULL, NULL, 0, '美洲', '加勒比'),
('CY', 'CYP', '196', '塞浦路斯', 'Cyprus', '塞浦路斯共和国', 'Republic of Cyprus', 1, '亚洲', '西亚'),
('CZ', 'CZE', '203', '捷克', 'Czechia', '捷克共和国', 'Czech Republic', 1, '欧洲', '中欧'),
('DK', 'DNK', '208', '丹麦', 'Denmark', '丹麦王国', 'Kingdom of Denmark', 1, '欧洲', '北欧'),
('DJ', 'DJI', '262', '吉布提', 'Djibouti', '吉布提共和国', 'Republic of Djibouti', 1, '非洲', '东非'),
('DM', 'DMA', '212', '多米尼克', 'Dominica', '多米尼克国', 'Commonwealth of Dominica', 1, '美洲', '加勒比'),
('DO', 'DOM', '214', '多米尼加', 'Dominican Republic', '多米尼加共和国', 'Dominican Republic', 1, '美洲', '加勒比'),
('EC', 'ECU', '218', '厄瓜多尔', 'Ecuador', '厄瓜多尔共和国', 'Republic of Ecuador', 1, '美洲', '南美洲'),
('EG', 'EGY', '818', '埃及', 'Egypt', '阿拉伯埃及共和国', 'Arab Republic of Egypt', 1, '非洲', '北非'),
('SV', 'SLV', '222', '萨尔瓦多', 'El Salvador', '萨尔瓦多共和国', 'Republic of El Salvador', 1, '美洲', '中美洲'),
('GQ', 'GNQ', '226', '赤道几内亚', 'Equatorial Guinea', '赤道几内亚共和国', 'Republic of Equatorial Guinea', 1, '非洲', '中非'),
('ER', 'ERI', '232', '厄立特里亚', 'Eritrea', '厄立特里亚国', 'State of Eritrea', 1, '非洲', '东非'),
('EE', 'EST', '233', '爱沙尼亚', 'Estonia', '爱沙尼亚共和国', 'Republic of Estonia', 1, '欧洲', '北欧'),
('SZ', 'SWZ', '748', '斯威士兰', 'Eswatini', '斯威士兰王国', 'Kingdom of Eswatini', 1, '非洲', '南非'),
('ET', 'ETH', '231', '埃塞俄比亚', 'Ethiopia', '埃塞俄比亚联邦民主共和国', 'Federal Democratic Republic of Ethiopia', 1, '非洲', '东非'),
('FK', 'FLK', '238', '福克兰群岛（马尔维纳斯）', 'Falkland Islands (Malvinas)', NULL, NULL, 0, '美洲', '南美洲'),
('FO', 'FRO', '234', '法罗群岛', 'Faroe Islands', NULL, NULL, 0, '欧洲', '北欧'),
('FJ', 'FJI', '242', '斐济', 'Fiji', '斐济共和国', 'Republic of Fiji', 1, '大洋洲', '美拉尼西亚'),
('FI', 'FIN', '246', '芬兰', 'Finland', '芬兰共和国', 'Republic of Finland', 1, '欧洲', '北欧'),
('FR', 'FRA', '250', '法国', 'France', '法兰西共和国', 'French Republic', 1, '欧洲', '西欧'),
('GF', 'GUF', '254', '法属圭亚那', 'French Guiana', NULL, NULL, 0, '美洲', '南美洲'),
('PF', 'PYF', '258', '法属波利尼西亚', 'French Polynesia', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
('TF', 'ATF', '260', '法属南部领地', 'French Southern Territories', NULL, NULL, 0, '南极洲', NULL),
('GA', 'GAB', '266', '加蓬', 'Gabon', '加蓬共和国', 'Gabonese Republic', 1, '非洲', '中非'),
('GM', 'GMB', '270', '冈比亚', 'Gambia', '冈比亚共和国', 'Republic of the Gambia', 1, '非洲', '西非'),
('GE', 'GEO', '268', '格鲁吉亚', 'Georgia', NULL, NULL, 1, '亚洲', '西亚'),
('DE', 'DEU', '276', '德国', 'Germany', '德意志联邦共和国', 'Federal Republic of Germany', 1, '欧洲', '中欧'),
('GH', 'GHA', '288', '加纳', 'Ghana', '加纳共和国', 'Republic of Ghana', 1, '非洲', '西非'),
('GI', 'GIB', '292', '直布罗陀', 'Gibraltar', NULL, NULL, 0, '欧洲', '南欧'),
('GR', 'GRC', '300', '希腊', 'Greece', '希腊共和国', 'Hellenic Republic', 1, '欧洲', '南欧'),
('GL', 'GRL', '304', '格陵兰', 'Greenland', NULL, NULL, 0, '美洲', '北美洲'),
('GD', 'GRD', '308', '格林纳达', 'Grenada', NULL, NULL, 1, '美洲', '加勒比'),
('GP', 'GLP', '312', '瓜德罗普', 'Guadeloupe', NULL, NULL, 0, '美洲', '加勒比'),
('GU', 'GUM', '316', '关岛', 'Guam', NULL, NULL, 0, '大洋洲', '密克罗尼西亚'),
('GT', 'GTM', '320', '危地马拉', 'Guatemala', '危地马拉共和国', 'Republic of Guatemala', 1, '美洲', '中美洲'),
('GG', 'GGY', '831', '根西', 'Guernsey', NULL, NULL, 0, '欧洲', '北欧'),
('GN', 'GIN', '324', '几内亚', 'Guinea', '几内亚共和国', 'Republic of Guinea', 1, '非洲', '西非'),
('GW', 'GNB', '624', '几内亚比绍', 'Guinea-Bissau', '几内亚比绍共和国', 'Republic of Guinea-Bissau', 1, '非洲', '西非'),
('GY', 'GUY', '328', '圭亚那', 'Guyana', '圭亚那合作共和国', 'Co-operative Republic of Guyana', 1, '美洲', '南美洲'),
('HT', 'HTI', '332', '海地', 'Haiti', '海地共和国', 'Republic of Haiti', 1, '美洲', '加勒比'),
('HM', 'HMD', '334', '赫德岛和麦克唐纳群岛', 'Heard Island and McDonald Islands', NULL, NULL, 0, '南极洲', NULL),
('VA', 'VAT', '336', '梵蒂冈', 'Holy See', '梵蒂冈城国', 'Vatican City State', 1, '欧洲', '南欧'),
('HN', 'HND', '340', '洪都拉斯', 'Honduras', '洪都拉斯共和国', 'Republic of Honduras', 1, '美洲', '中美洲'),
('HK', 'HKG', '344', '香港', 'Hong Kong', '中华人民共和国香港特别行政区', 'Hong Kong Special Administrative Region of China', 0, '亚洲', '东亚'),
('HU', 'HUN', '348', '匈牙利', 'Hungary', NULL, NULL, 1, '欧洲', '东欧'),
('IS', 'ISL', '352', '冰岛', 'Iceland', '冰岛共和国', 'Republic of Iceland', 1, '欧洲', '北欧'),
('IN', 'IND', '356', '印度', 'India', '印度共和国', 'Republic of India', 1, '亚洲', '南亚'),
('ID', 'IDN', '360', '印度尼西亚', 'Indonesia', '印度尼西亚共和国', 'Republic of Indonesia', 1, '亚洲', '东南亚'),
('IR', 'IRN', '364', '伊朗', 'Iran', '伊朗伊斯兰共和国', 'Islamic Republic of Iran', 1, '亚洲', '西亚'),
('IQ', 'IRQ', '368', '伊拉克', 'Iraq', '伊拉克共和国', 'Republic of Iraq', 1, '亚洲', '西亚'),
('IE', 'IRL', '372', '爱尔兰', 'Ireland', NULL, NULL, 1, '欧洲', '西欧'),
('IM', 'IMN', '833', '马恩岛', 'Isle of Man', NULL, NULL, 0, '欧洲', '北欧'),
('IL', 'ISR', '376', '以色列', 'Israel', '以色列国', 'State of Israel', 1, '亚洲', '西亚'),
('IT', 'ITA', '380', '意大利', 'Italy', '意大利共和国', 'Italian Republic', 1, '欧洲', '南欧'),
('JM', 'JAM', '388', '牙买加', 'Jamaica', NULL, NULL, 1, '美洲', '加勒比'),
('JP', 'JPN', '392', '日本', 'Japan', NULL, NULL, 1, '亚洲', '东亚'),
('JE', 'JEY', '832', '泽西', 'Jersey', NULL, NULL, 0, '欧洲', '北欧'),
('JO', 'JOR', '400', '约旦', 'Jordan', '约旦哈希姆王国', 'Hashemite Kingdom of Jordan', 1, '亚洲', '西亚'),
('KZ', 'KAZ', '398', '哈萨克斯坦', 'Kazakhstan', '哈萨克斯坦共和国', 'Republic of Kazakhstan', 1, '亚洲', '中亚'),
('KE', 'KEN', '404', '肯尼亚', 'Kenya', '肯尼亚共和国', 'Republic of Kenya', 1, '非洲', '东非'),
('KI', 'KIR', '296', '基里巴斯', 'Kiribati', '基里巴斯共和国', 'Republic of Kiribati', 1, '大洋洲', '密克罗尼西亚'),
('KP', 'PRK', '408', '朝鲜', 'Korea (Democratic People''s Republic of)', '朝鲜民主主义人民共和国', 'Democratic People''s Republic of Korea', 1, '亚洲', '东亚'),
('KR', 'KOR', '410', '韩国', 'Korea, Republic of', '大韩民国', 'Republic of Korea', 1, '亚洲', '东亚'),
('KW', 'KWT', '414', '科威特', 'Kuwait', '科威特国', 'State of Kuwait', 1, '亚洲', '西亚'),
('KG', 'KGZ', '417', '吉尔吉斯斯坦', 'Kyrgyzstan', '吉尔吉斯共和国', 'Kyrgyz Republic', 1, '亚洲', '中亚'),
('LA', 'LAO', '418', '老挝', 'Lao People''s Democratic Republic', '老挝人民民主共和国', 'Lao People''s Democratic Republic', 1, '亚洲', '东南亚'),
('LV', 'LVA', '428', '拉脱维亚', 'Latvia', '拉脱维亚共和国', 'Republic of Latvia', 1, '欧洲', '北欧'),
('LB', 'LBN', '422', '黎巴嫩', 'Lebanon', '黎巴嫩共和国', 'Republic of Lebanon', 1, '亚洲', '西亚'),
('LS', 'LSO', '426', '莱索托', 'Lesotho', '莱索托王国', 'Kingdom of Lesotho', 1, '非洲', '南非'),
('LR', 'LBR', '430', '利比里亚', 'Liberia', '利比里亚共和国', 'Republic of Liberia', 1, '非洲', '西非'),
('LY', 'LBY', '434', '利比亚', 'Libya', '利比亚国', 'State of Libya', 1, '非洲', '北非'),
('LI', 'LIE', '438', '列支敦士登', 'Liechtenstein', '列支敦士登公国', 'Principality of Liechtenstein', 1, '欧洲', '中欧'),
('LT', 'LTU', '440', '立陶宛', 'Lithuania', '立陶宛共和国', 'Republic of Lithuania', 1, '欧洲', '北欧'),
('LU', 'LUX', '442', '卢森堡', 'Luxembourg', '卢森堡大公国', 'Grand Duchy of Luxembourg', 1, '欧洲', '西欧'),
('MO', 'MAC', '446', '澳门', 'Macao', '中华人民共和国澳门特别行政区', 'Macao Special Administrative Region of China', 0, '亚洲', '东亚'),
('MG', 'MDG', '450', '马达加斯加', 'Madagascar', '马达加斯加共和国', 'Republic of Madagascar', 1, '非洲', '东非'),
('MW', 'MWI', '454', '马拉维', 'Malawi', '马拉维共和国', 'Republic of Malawi', 1, '非洲', '东非'),
('MY', 'MYS', '458', '马来西亚', 'Malaysia', NULL, NULL, 1, '亚洲', '东南亚'),
('MV', 'MDV', '462', '马尔代夫', 'Maldives', '马尔代夫共和国', 'Republic of Maldives', 1, '亚洲', '南亚'),
('ML', 'MLI', '466', '马里', 'Mali', '马里共和国', 'Republic of Mali', 1, '非洲', '西非'),
('MT', 'MLT', '470', '马耳他', 'Malta', '马耳他共和国', 'Republic of Malta', 1, '欧洲', '南欧'),
('MH', 'MHL', '584', '马绍尔群岛', 'Marshall Islands', '马绍尔群岛共和国', 'Republic of the Marshall Islands', 1, '大洋洲', '密克罗尼西亚'),
('MQ', 'MTQ', '474', '马提尼克', 'Martinique', NULL, NULL, 0, '美洲', '加勒比'),
('MR', 'MRT', '478', '毛里塔尼亚', 'Mauritania', '毛里塔尼亚伊斯兰共和国', 'Islamic Republic of Mauritania', 1, '非洲', '西非'),
('MU', 'MUS', '480', '毛里求斯', 'Mauritius', '毛里求斯共和国', 'Republic of Mauritius', 1, '非洲', '东非'),
('YT', 'MYT', '175', '马约特', 'Mayotte', NULL, NULL, 0, '非洲', '东非'),
('MX', 'MEX', '484', '墨西哥', 'Mexico', '墨西哥合众国', 'United Mexican States', 1, '美洲', '北美洲'),
('FM', 'FSM', '583', '密克罗尼西亚联邦', 'Micronesia (Federated States of)', '密克罗尼西亚联邦', 'Federated States of Micronesia', 1, '大洋洲', '密克罗尼西亚'),
('MD', 'MDA', '498', '摩尔多瓦', 'Moldova', '摩尔多瓦共和国', 'Republic of Moldova', 1, '欧洲', '东欧'),
('MC', 'MCO', '492', '摩纳哥', 'Monaco', '摩纳哥公国', 'Principality of Monaco', 1, '欧洲', '西欧'),
('MN', 'MNG', '496', '蒙古', 'Mongolia', '蒙古国', 'Mongolia', 1, '亚洲', '东亚'),
('ME', 'MNE', '499', '黑山', 'Montenegro', '黑山', 'Montenegro', 1, '欧洲', '南欧'),
('MS', 'MSR', '500', '蒙特塞拉特', 'Montserrat', NULL, NULL, 0, '美洲', '加勒比'),
('MA', 'MAR', '504', '摩洛哥', 'Morocco', '摩洛哥王国', 'Kingdom of Morocco', 1, '非洲', '北非'),
('MZ', 'MOZ', '508', '莫桑比克', 'Mozambique', '莫桑比克共和国', 'Republic of Mozambique', 1, '非洲', '东非'),
('MM', 'MMR', '104', '缅甸', 'Myanmar', '缅甸联邦共和国', 'Republic of the Union of Myanmar', 1, '亚洲', '东南亚'),
('NA', 'NAM', '516', '纳米比亚', 'Namibia', '纳米比亚共和国', 'Republic of Namibia', 1, '非洲', '南非'),
('NR', 'NRU', '520', '瑙鲁', 'Nauru', '瑙鲁共和国', 'Republic of Nauru', 1, '大洋洲', '密克罗尼西亚'),
('NP', 'NPL', '524', '尼泊尔', 'Nepal', '尼泊尔联邦民主共和国', 'Federal Democratic Republic of Nepal', 1, '亚洲', '南亚'),
('NL', 'NLD', '528', '荷兰', 'Netherlands', '荷兰王国', 'Kingdom of the Netherlands', 1, '欧洲', '西欧'),
('NC', 'NCL', '540', '新喀里多尼亚', 'New Caledonia', NULL, NULL, 0, '大洋洲', '美拉尼西亚'),
('NZ', 'NZL', '554', '新西兰', 'New Zealand', NULL, NULL, 1, '大洋洲', '澳大利亚和新西兰'),
('NI', 'NIC', '558', '尼加拉瓜', 'Nicaragua', '尼加拉瓜共和国', 'Republic of Nicaragua', 1, '美洲', '中美洲'),
('NE', 'NER', '562', '尼日尔', 'Niger', '尼日尔共和国', 'Republic of Niger', 1, '非洲', '西非'),
('NG', 'NGA', '566', '尼日利亚', 'Nigeria', '尼日利亚联邦共和国', 'Federal Republic of Nigeria', 1, '非洲', '西非'),
('NU', 'NIU', '570', '纽埃', 'Niue', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
('NF', 'NFK', '574', '诺福克岛', 'Norfolk Island', NULL, NULL, 0, '大洋洲', '澳大利亚和新西兰'),
('MK', 'MKD', '807', '北马其顿', 'North Macedonia', '北马其顿共和国', 'Republic of North Macedonia', 1, '欧洲', '南欧'),
('MP', 'MNP', '580', '北马里亚纳群岛', 'Northern Mariana Islands', NULL, NULL, 0, '大洋洲', '密克罗尼西亚'),
('NO', 'NOR', '578', '挪威', 'Norway', '挪威王国', 'Kingdom of Norway', 1, '欧洲', '北欧'),
('OM', 'OMN', '512', '阿曼', 'Oman', '阿曼苏丹国', 'Sultanate of Oman', 1, '亚洲', '西亚'),
('PK', 'PAK', '586', '巴基斯坦', 'Pakistan', '巴基斯坦伊斯兰共和国', 'Islamic Republic of Pakistan', 1, '亚洲', '南亚'),
('PW', 'PLW', '585', '帕劳', 'Palau', '帕劳共和国', 'Republic of Palau', 1, '大洋洲', '密克罗尼西亚'),
('PS', 'PSE', '275', '巴勒斯坦', 'Palestine, State of', '巴勒斯坦国', 'State of Palestine', 1, '亚洲', '西亚'),
('PA', 'PAN', '591', '巴拿马', 'Panama', '巴拿马共和国', 'Republic of Panama', 1, '美洲', '中美洲'),
('PG', 'PNG', '598', '巴布亚新几内亚', 'Papua New Guinea', '巴布亚新几内亚独立国', 'Independent State of Papua New Guinea', 1, '大洋洲', '美拉尼西亚'),
('PY', 'PRY', '600', '巴拉圭', 'Paraguay', '巴拉圭共和国', 'Republic of Paraguay', 1, '美洲', '南美洲'),
('PE', 'PER', '604', '秘鲁', 'Peru', '秘鲁共和国', 'Republic of Peru', 1, '美洲', '南美洲'),
('PH', 'PHL', '608', '菲律宾', 'Philippines', '菲律宾共和国', 'Republic of the Philippines', 1, '亚洲', '东南亚'),
('PN', 'PCN', '612', '皮特凯恩群岛', 'Pitcairn', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
('PL', 'POL', '616', '波兰', 'Poland', '波兰共和国', 'Republic of Poland', 1, '欧洲', '东欧'),
('PT', 'PRT', '620', '葡萄牙', 'Portugal', '葡萄牙共和国', 'Portuguese Republic', 1, '欧洲', '南欧'),
('PR', 'PRI', '630', '波多黎各', 'Puerto Rico', NULL, NULL, 0, '美洲', '加勒比'),
('QA', 'QAT', '634', '卡塔尔', 'Qatar', '卡塔尔国', 'State of Qatar', 1, '亚洲', '西亚'),
('RE', 'REU', '638', '留尼汪', 'Réunion', NULL, NULL, 0, '非洲', '东非'),
('RO', 'ROU', '642', '罗马尼亚', 'Romania', NULL, NULL, 1, '欧洲', '东欧'),
('RU', 'RUS', '643', '俄罗斯', 'Russian Federation', '俄罗斯联邦', 'Russian Federation', 1, '欧洲', '东欧'),
('RW', 'RWA', '646', '卢旺达', 'Rwanda', '卢旺达共和国', 'Republic of Rwanda', 1, '非洲', '东非'),
('BL', 'BLM', '652', '圣巴泰勒米', 'Saint Barthélemy', NULL, NULL, 0, '美洲', '加勒比'),
('SH', 'SHN', '654', '圣赫勒拿', 'Saint Helena, Ascension and Tristan da Cunha', NULL, NULL, 0, '非洲', '西非'),
('KN', 'KNA', '659', '圣基茨和尼维斯', 'Saint Kitts and Nevis', '圣基茨和尼维斯联邦', 'Federation of Saint Kitts and Nevis', 1, '美洲', '加勒比'),
('LC', 'LCA', '662', '圣卢西亚', 'Saint Lucia', NULL, NULL, 1, '美洲', '加勒比'),
('MF', 'MAF', '663', '法属圣马丁', 'Saint Martin (French part)', NULL, NULL, 0, '美洲', '加勒比'),
('PM', 'SPM', '666', '圣皮埃尔和密克隆', 'Saint Pierre and Miquelon', NULL, NULL, 0, '美洲', '北美洲'),
('VC', 'VCT', '670', '圣文森特和格林纳丁斯', 'Saint Vincent and the Grenadines', NULL, NULL, 1, '美洲', '加勒比'),
('WS', 'WSM', '882', '萨摩亚', 'Samoa', '萨摩亚独立国', 'Independent State of Samoa', 1, '大洋洲', '波利尼西亚'),
('SM', 'SMR', '674', '圣马力诺', 'San Marino', '圣马力诺共和国', 'Republic of San Marino', 1, '欧洲', '南欧'),
('ST', 'STP', '678', '圣多美和普林西比', 'Sao Tome and Principe', '圣多美和普林西比民主共和国', 'Democratic Republic of Sao Tome and Principe', 1, '非洲', '中非'),
('SA', 'SAU', '682', '沙特阿拉伯', 'Saudi Arabia', '沙特阿拉伯王国', 'Kingdom of Saudi Arabia', 1, '亚洲', '西亚'),
('SN', 'SEN', '686', '塞内加尔', 'Senegal', '塞内加尔共和国', 'Republic of Senegal', 1, '非洲', '西非'),
('RS', 'SRB', '688', '塞尔维亚', 'Serbia', '塞尔维亚共和国', 'Republic of Serbia', 1, '欧洲', '南欧'),
('SC', 'SYC', '690', '塞舌尔', 'Seychelles', '塞舌尔共和国', 'Republic of Seychelles', 1, '非洲', '东非'),
('SL', 'SLE', '694', '塞拉利昂', 'Sierra Leone', '塞拉利昂共和国', 'Republic of Sierra Leone', 1, '非洲', '西非'),
('SG', 'SGP', '702', '新加坡', 'Singapore', '新加坡共和国', 'Republic of Singapore', 1, '亚洲', '东南亚'),
('SX', 'SXM', '534', '荷属圣马丁', 'Sint Maarten (Dutch part)', NULL, NULL, 0, '美洲', '加勒比'),
('SK', 'SVK', '703', '斯洛伐克', 'Slovakia', '斯洛伐克共和国', 'Slovak Republic', 1, '欧洲', '中欧'),
('SI', 'SVN', '705', '斯洛文尼亚', 'Slovenia', '斯洛文尼亚共和国', 'Republic of Slovenia', 1, '欧洲', '南欧'),
('SB', 'SLB', '090', '所罗门群岛', 'Solomon Islands', NULL, NULL, 1, '大洋洲', '美拉尼西亚'),
('SO', 'SOM', '706', '索马里', 'Somalia', '索马里联邦共和国', 'Federal Republic of Somalia', 1, '非洲', '东非'),
('ZA', 'ZAF', '710', '南非', 'South Africa', '南非共和国', 'Republic of South Africa', 1, '非洲', '南非'),
('GS', 'SGS', '239', '南乔治亚和南桑威奇群岛', 'South Georgia and the South Sandwich Islands', NULL, NULL, 0, '南极洲', NULL),
('SS', 'SSD', '728', '南苏丹', 'South Sudan', '南苏丹共和国', 'Republic of South Sudan', 1, '非洲', '东非'),
('ES', 'ESP', '724', '西班牙', 'Spain', '西班牙王国', 'Kingdom of Spain', 1, '欧洲', '南欧'),
('LK', 'LKA', '144', '斯里兰卡', 'Sri Lanka', '斯里兰卡民主社会主义共和国', 'Democratic Socialist Republic of Sri Lanka', 1, '亚洲', '南亚'),
('SD', 'SDN', '729', '苏丹', 'Sudan', '苏丹共和国', 'Republic of the Sudan', 1, '非洲', '北非'),
('SR', 'SUR', '740', '苏里南', 'Suriname', '苏里南共和国', 'Republic of Suriname', 1, '美洲', '南美洲'),
('SJ', 'SJM', '744', '斯瓦尔巴和扬马延', 'Svalbard and Jan Mayen', NULL, NULL, 0, '欧洲', '北欧'),
('SE', 'SWE', '752', '瑞典', 'Sweden', '瑞典王国', 'Kingdom of Sweden', 1, '欧洲', '北欧'),
('CH', 'CHE', '756', '瑞士', 'Switzerland', '瑞士联邦', 'Swiss Confederation', 1, '欧洲', '中欧'),
('SY', 'SYR', '760', '叙利亚', 'Syrian Arab Republic', '阿拉伯叙利亚共和国', 'Syrian Arab Republic', 1, '亚洲', '西亚'),
('TW', 'TWN', '158', '台湾', 'Taiwan, Province of China', '中国台湾省', 'Taiwan, Province of China', 0, '亚洲', '东亚'),
('TJ', 'TJK', '762', '塔吉克斯坦', 'Tajikistan', '塔吉克斯坦共和国', 'Republic of Tajikistan', 1, '亚洲', '中亚'),
('TZ', 'TZA', '834', '坦桑尼亚', 'Tanzania', '坦桑尼亚联合共和国', 'United Republic of Tanzania', 1, '非洲', '东非'),
('TH', 'THA', '764', '泰国', 'Thailand', '泰王国', 'Kingdom of Thailand', 1, '亚洲', '东南亚'),
('TL', 'TLS', '626', '东帝汶', 'Timor-Leste', '东帝汶民主共和国', 'Democratic Republic of Timor-Leste', 1, '亚洲', '东南亚'),
('TG', 'TGO', '768', '多哥', 'Togo', '多哥共和国', 'Togolese Republic', 1, '非洲', '西非'),
('TK', 'TKL', '772', '托克劳', 'Tokelau', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
('TO', 'TON', '776', '汤加', 'Tonga', '汤加王国', 'Kingdom of Tonga', 1, '大洋洲', '波利尼西亚'),
('TT', 'TTO', '780', '特立尼达和多巴哥', 'Trinidad and Tobago', '特立尼达和多巴哥共和国', 'Republic of Trinidad and Tobago', 1, '美洲', '加勒比'),
('TN', 'TUN', '788', '突尼斯', 'Tunisia', '突尼斯共和国', 'Republic of Tunisia', 1, '非洲', '北非'),
('TR', 'TUR', '792', '土耳其', 'Turkey', '土耳其共和国', 'Republic of Turkey', 1, '亚洲', '西亚'),
('TM', 'TKM', '795', '土库曼斯坦', 'Turkmenistan', '土库曼斯坦', 'Turkmenistan', 1, '亚洲', '中亚'),
('TC', 'TCA', '796', '特克斯和凯科斯群岛', 'Turks and Caicos Islands', NULL, NULL, 0, '美洲', '加勒比'),
('TV', 'TUV', '798', '图瓦卢', 'Tuvalu', NULL, NULL, 1, '大洋洲', '波利尼西亚'),
('UG', 'UGA', '800', '乌干达', 'Uganda', '乌干达共和国', 'Republic of Uganda', 1, '非洲', '东非'),
('UA', 'UKR', '804', '乌克兰', 'Ukraine', NULL, NULL, 1, '欧洲', '东欧'),
('AE', 'ARE', '784', '阿联酋', 'United Arab Emirates', '阿拉伯联合酋长国', 'United Arab Emirates', 1, '亚洲', '西亚'),
('GB', 'GBR', '826', '英国', 'United Kingdom', '大不列颠及北爱尔兰联合王国', 'United Kingdom of Great Britain and Northern Ireland', 1, '欧洲', '西欧'),
('US', 'USA', '840', '美国', 'United States', '美利坚合众国', 'United States of America', 1, '美洲', '北美洲'),
('UM', 'UMI', '581', '美国本土外小岛屿', 'United States Minor Outlying Islands', NULL, NULL, 0, '大洋洲', '密克罗尼西亚'),
('UY', 'URY', '858', '乌拉圭', 'Uruguay', '乌拉圭东岸共和国', 'Oriental Republic of Uruguay', 1, '美洲', '南美洲'),
('UZ', 'UZB', '860', '乌兹别克斯坦', 'Uzbekistan', '乌兹别克斯坦共和国', 'Republic of Uzbekistan', 1, '亚洲', '中亚'),
('VU', 'VUT', '548', '瓦努阿图', 'Vanuatu', '瓦努阿图共和国', 'Republic of Vanuatu', 1, '大洋洲', '美拉尼西亚'),
('VE', 'VEN', '862', '委内瑞拉', 'Venezuela', '委内瑞拉玻利瓦尔共和国', 'Bolivarian Republic of Venezuela', 1, '美洲', '南美洲'),
('VN', 'VNM', '704', '越南', 'Viet Nam', '越南社会主义共和国', 'Socialist Republic of Viet Nam', 1, '亚洲', '东南亚'),
('VG', 'VGB', '092', '英属维尔京群岛', 'Virgin Islands (British)', NULL, NULL, 0, '美洲', '加勒比'),
('VI', 'VIR', '850', '美属维尔京群岛', 'Virgin Islands (U.S.)', NULL, NULL, 0, '美洲', '加勒比'),
('WF', 'WLF', '876', '瓦利斯和富图纳', 'Wallis and Futuna', NULL, NULL, 0, '大洋洲', '波利尼西亚'),
('EH', 'ESH', '732', '西撒哈拉', 'Western Sahara', NULL, NULL, 0, '非洲', '北非'),
('YE', 'YEM', '887', '也门', 'Yemen', '也门共和国', 'Republic of Yemen', 1, '亚洲', '西亚'),
('ZM', 'ZMB', '894', '赞比亚', 'Zambia', '赞比亚共和国', 'Republic of Zambia', 1, '非洲', '东非'),
('ZW', 'ZWE', '716', '津巴布韦', 'Zimbabwe', '津巴布韦共和国', 'Republic of Zimbabwe', 1, '非洲', '东非'),
('ZZ', 'ZZZ', '111', '全部区域', 'All Country', '全部区域', 'All Country', 1, '全球', '全部地区');"""

hand.write(wr)

# 关闭文件
hand.close()

# 关闭数据库连接
cursor.close()
conn.close()

print(f"数据已成功导出到{sql_file}")