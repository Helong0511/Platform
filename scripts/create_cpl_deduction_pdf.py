"""
生成CPL系统扣量和扣金额原理与操作说明PDF文档
完整版本 - 包含所有11个章节的详细内容
"""
import sys
import os
from pathlib import Path
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Preformatted, KeepTogether
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
except ImportError:
    print("请先安装依赖: pip install reportlab")
    print("安装命令: python -m pip install reportlab")
    sys.exit(1)


# 全局变量存储已注册的字体名称
_registered_font_name = None
_registered_bold_font_name = None

def register_chinese_fonts():
    """注册中文字体（只注册一次）"""
    global _registered_font_name, _registered_bold_font_name
    
    # 如果已经注册过，直接返回
    if _registered_font_name and _registered_bold_font_name:
        return _registered_font_name, _registered_bold_font_name
    
    # Windows系统字体路径
    windows_fonts_dir = Path("C:/Windows/Fonts")
    
    # 尝试注册的字体列表（按优先级）
    font_configs = [
        # 微软雅黑（推荐，现代美观）
        {
            'name': 'MSYaHei',
            'bold_name': 'MSYaHei-Bold',
            'paths': [
                (windows_fonts_dir / "msyh.ttf", windows_fonts_dir / "msyhbd.ttf"),  # 微软雅黑 + 粗体
            ]
        },
        # 黑体
        {
            'name': 'SimHei',
            'bold_name': 'SimHei-Bold',
            'paths': [
                (windows_fonts_dir / "simhei.ttf", windows_fonts_dir / "simhei.ttf"),  # 黑体（普通和粗体用同一个文件）
            ]
        },
        # 宋体
        {
            'name': 'SimSun',
            'bold_name': 'SimSun-Bold',
            'paths': [
                (windows_fonts_dir / "simsun.ttc", windows_fonts_dir / "simsun.ttc"),  # 宋体
            ]
        },
    ]
    
    registered = False
    
    for config in font_configs:
        for normal_path, bold_path in config['paths']:
            if normal_path.exists():
                try:
                    # 注册普通字体
                    pdfmetrics.registerFont(TTFont(config['name'], str(normal_path)))
                    _registered_font_name = config['name']
                    
                    # 注册粗体字体（如果粗体文件存在，使用粗体文件；否则使用普通字体文件）
                    if bold_path.exists() and bold_path != normal_path:
                        pdfmetrics.registerFont(TTFont(config['bold_name'], str(bold_path)))
                        _registered_bold_font_name = config['bold_name']
                    else:
                        # 使用同一个字体文件，但注册为粗体名称
                        pdfmetrics.registerFont(TTFont(config['bold_name'], str(normal_path)))
                        _registered_bold_font_name = config['bold_name']
                    
                    registered = True
                    print(f"✓ 已注册字体: {config['name']} ({normal_path.name})")
                    print(f"✓ 已注册粗体字体: {config['bold_name']}")
                    break
                except Exception as e:
                    print(f"⚠ 注册字体失败 {normal_path}: {str(e)}")
                    continue
        
        if registered:
            break
    
    if not registered:
        print("⚠ 警告: 未找到中文字体，将使用默认字体（可能无法正确显示中文）")
        print("提示: 请确保系统已安装中文字体（如微软雅黑、黑体、宋体等）")
        _registered_font_name = 'Helvetica'  # 回退到默认字体
        _registered_bold_font_name = 'Helvetica-Bold'
    
    return _registered_font_name, _registered_bold_font_name


def create_custom_styles():
    """创建自定义样式"""
    # 注册中文字体
    font_name, bold_font_name = register_chinese_fonts()
    
    styles = getSampleStyleSheet()
    
    # 修改现有Title样式
    styles['Title'].fontSize = 24
    styles['Title'].textColor = colors.HexColor('#2c3e50')
    styles['Title'].spaceAfter = 30
    styles['Title'].alignment = TA_CENTER
    styles['Title'].fontName = bold_font_name
    
    # 修改现有Heading1样式
    styles['Heading1'].fontSize = 18
    styles['Heading1'].textColor = colors.HexColor('#2c3e50')
    styles['Heading1'].spaceAfter = 12
    styles['Heading1'].spaceBefore = 20
    styles['Heading1'].fontName = bold_font_name
    
    # 修改现有Heading2样式
    styles['Heading2'].fontSize = 14
    styles['Heading2'].textColor = colors.HexColor('#34495e')
    styles['Heading2'].spaceAfter = 10
    styles['Heading2'].spaceBefore = 15
    styles['Heading2'].fontName = bold_font_name
    
    # 修改现有Heading3样式
    styles['Heading3'].fontSize = 12
    styles['Heading3'].textColor = colors.HexColor('#555')
    styles['Heading3'].spaceAfter = 8
    styles['Heading3'].spaceBefore = 12
    styles['Heading3'].fontName = bold_font_name
    
    # 修改Normal样式（正文使用中文字体）
    styles['Normal'].fontName = font_name
    
    # 修改现有Code样式（代码使用中文字体，支持中文注释）
    styles['Code'].fontSize = 9
    styles['Code'].fontName = font_name  # 使用中文字体以支持中文注释
    styles['Code'].backColor = colors.HexColor('#f8f8f8')
    styles['Code'].leftIndent = 15
    styles['Code'].rightIndent = 15
    styles['Code'].spaceBefore = 8
    styles['Code'].spaceAfter = 8
    
    # 添加新的BodyText样式（如果不存在）
    if 'BodyText' not in styles.byName:
        styles.add(ParagraphStyle(
            name='BodyText',
            parent=styles['Normal'],
            fontSize=11,
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
            fontName=font_name
        ))
    else:
        styles['BodyText'].fontSize = 11
        styles['BodyText'].leading = 16
        styles['BodyText'].alignment = TA_JUSTIFY
        styles['BodyText'].spaceAfter = 8
        styles['BodyText'].fontName = font_name
    
    return styles


def create_code_block(text, styles):
    """创建代码块，确保使用中文字体"""
    # 确保字体已注册
    font_name, bold_font_name = register_chinese_fonts()
    
    # 创建代码样式（使用中文字体）
    code_style = ParagraphStyle(
        name='CodeBlock',
        parent=styles['Code'],
        fontName=font_name,  # 确保使用中文字体
        fontSize=9,
        backColor=colors.HexColor('#f8f8f8'),
        leftIndent=15,
        rightIndent=15,
        spaceBefore=8,
        spaceAfter=8
    )
    
    return Preformatted(text, code_style)


def create_table(data, col_widths=None, styles=None):
    """创建表格，支持自动换行"""
    # 确保字体已注册
    font_name, bold_font_name = register_chinese_fonts()
    
    if col_widths is None:
        col_widths = [None] * len(data[0]) if data else []
    
    # 如果没有传入styles，使用默认样式
    if styles is None:
        from reportlab.lib.styles import getSampleStyleSheet
        styles = getSampleStyleSheet()
        styles['Normal'].fontName = font_name
    
    # 将表格数据转换为Paragraph对象，支持自动换行
    table_data = []
    for row_idx, row in enumerate(data):
        table_row = []
        for cell in row:
            if isinstance(cell, str):
                # 表头使用粗体样式
                if row_idx == 0:
                    cell_style = ParagraphStyle(
                        name='TableHeader',
                        parent=styles['Normal'],
                        fontName=bold_font_name,
                        fontSize=10,
                        leading=12,
                        alignment=TA_LEFT
                    )
                else:
                    # 表格内容使用普通样式，字体稍小
                    cell_style = ParagraphStyle(
                        name='TableCell',
                        parent=styles['Normal'],
                        fontName=font_name,
                        fontSize=9,
                        leading=11,
                        alignment=TA_LEFT
                    )
                table_row.append(Paragraph(cell, cell_style))
            else:
                table_row.append(cell)
        table_data.append(table_row)
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), bold_font_name),  # 表头使用粗体
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('FONTNAME', (0, 1), (-1, -1), font_name),  # 表格内容使用中文字体
        ('FONTSIZE', (0, 1), (-1, -1), 9),  # 表格内容字体稍小
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return table


def create_pdf_content(styles):
    """创建PDF内容 - 完整版本"""
    story = []
    
    # 标题页
    story.append(Spacer(1, 6*cm))
    story.append(Paragraph("CPL系统扣量和扣金额", styles['Title']))
    story.append(Spacer(1, 0.8*cm))
    story.append(Paragraph("原理与操作说明", styles['Title']))
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph(f"生成时间: {datetime.now().strftime('%Y年%m月%d日')}", styles['BodyText']))
    story.append(PageBreak())
    
    # 目录
    story.append(Paragraph("目录", styles['Heading1']))
    story.append(Spacer(1, 0.5*cm))
    
    toc_items = [
        "1. 系统概述",
        "2. 核心概念",
        "3. 扣量原理",
        "4. 扣金额原理",
        "5. 配置层级与优先级",
        "6. 扣减策略详解",
        "7. 系统架构",
        "8. 操作指南",
        "9. 数据模型",
        "10. 统计与监控",
        "11. 常见问题",
        "附录"
    ]
    
    for item in toc_items:
        story.append(Paragraph(item, styles['BodyText']))
        story.append(Spacer(1, 0.2*cm))
    
    story.append(PageBreak())
    
    # ========== 1. 系统概述 ==========
    story.append(Paragraph("1. 系统概述", styles['Heading1']))
    
    story.append(Paragraph("<b>1.1 系统简介</b>", styles['Heading2']))
    story.append(Paragraph(
        "CPL（Cost Per Lead）扣减系统是一个智能化的转化扣减管理平台，用于在转化处理过程中自动执行扣量和扣金额操作。"
        "系统支持灵活的配置方式，可以针对不同的广告主、Offer或渠道设置独立的扣减规则。",
        styles['BodyText']
    ))
    
    story.append(Paragraph("<b>1.2 核心功能</b>", styles['Heading2']))
    features = [
        "<b>按比例扣量</b>：根据配置的比例，自动扣减转化数量",
        "<b>按比例扣金额</b>：根据配置的比例，自动扣减转化金额",
        "<b>多层级配置</b>：支持广告主、Offer、渠道三个层级的配置",
        "<b>多种扣减策略</b>：支持随机、按比例、轮询三种扣减策略",
        "<b>完整日志记录</b>：记录所有扣减操作的详细信息",
        "<b>统计分析</b>：提供扣减数据的统计和分析功能"
    ]
    for feature in features:
        story.append(Paragraph(f"• {feature}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>1.3 应用场景</b>", styles['Heading2']))
    scenarios = [
        "控制转化成本，降低无效转化带来的损失",
        "优化渠道质量，对低质量渠道进行扣减",
        "平衡广告主和渠道之间的利益分配",
        "实现精细化的转化管理"
    ]
    for scenario in scenarios:
        story.append(Paragraph(f"• {scenario}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(PageBreak())
    
    # ========== 2. 核心概念 ==========
    story.append(Paragraph("2. 核心概念", styles['Heading1']))
    
    story.append(Paragraph("<b>2.1 扣量（Volume Deduction）</b>", styles['Heading2']))
    story.append(Paragraph(
        "<b>定义</b>：扣量是指将部分转化记录标记为无效，不计算到最终的转化统计中。"
        "被扣量的转化不会保存到主转化表（postback_conversions），但会在扣减日志表中记录。",
        styles['BodyText']
    ))
    story.append(Paragraph("<b>特点</b>：", styles['Heading3']))
    volume_features = [
        "扣量是\"全有或全无\"的操作，即一个转化要么被扣量（数量变为0），要么不被扣量（数量保持为1）",
        "扣量操作是隐藏的，被扣量的转化对渠道不可见",
        "扣量比例是动态计算的，确保在统计时间窗口内（默认24小时）达到目标比例"
    ]
    for feature in volume_features:
        story.append(Paragraph(f"• {feature}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>2.2 扣金额（Amount Deduction）</b>", styles['Heading2']))
    story.append(Paragraph(
        "<b>定义</b>：扣金额是指按照配置的比例，从转化金额中扣除一定比例，但转化记录仍然保留。",
        styles['BodyText']
    ))
    story.append(Paragraph("<b>特点</b>：", styles['Heading3']))
    amount_features = [
        "扣金额是比例操作，每个转化都会按比例扣减金额",
        "扣金额后的转化仍然会保存到主转化表",
        "扣金额比例是固定的，直接应用于每个转化"
    ]
    for feature in amount_features:
        story.append(Paragraph(f"• {feature}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>2.3 配置层级</b>", styles['Heading2']))
    story.append(Paragraph(
        "系统支持三个层级的配置，优先级从高到低：",
        styles['BodyText']
    ))
    levels = [
        "<b>Offer级别</b>：针对特定Offer的扣减配置（优先级最高）",
        "<b>Advertiser级别</b>：针对特定广告主的扣减配置",
        "<b>Publisher级别</b>：针对特定渠道的扣减配置（优先级最低）"
    ]
    for level in levels:
        story.append(Paragraph(f"• {level}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>2.4 扣减策略</b>", styles['Heading2']))
    story.append(Paragraph(
        "系统支持三种扣减策略：",
        styles['BodyText']
    ))
    strategies = [
        "<b>random（随机）</b>：随机选择转化进行扣量，但确保总体比例正确",
        "<b>proportional（按比例）</b>：按固定间隔扣量，如每10个扣1个",
        "<b>round_robin（轮询）</b>：轮询方式扣量，按固定间隔循环"
    ]
    for strategy in strategies:
        story.append(Paragraph(f"• {strategy}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(PageBreak())
    
    # ========== 3. 扣量原理 ==========
    story.append(Paragraph("3. 扣量原理", styles['Heading1']))
    
    story.append(Paragraph("<b>3.1 扣量计算流程</b>", styles['Heading2']))
    story.append(Paragraph(
        "扣量计算是一个动态过程，系统会实时统计最近的转化数据，并根据统计结果决定是否对当前转化进行扣量。",
        styles['BodyText']
    ))
    
    story.append(Paragraph("<b>3.1.1 统计时间窗口</b>", styles['Heading3']))
    story.append(Paragraph(
        "系统默认使用<b>24小时</b>作为统计时间窗口，统计最近24小时内的转化数据。"
        "这个时间窗口可以通过代码中的<font name='Courier'>hours</font>参数调整。",
        styles['BodyText']
    ))
    
    story.append(Paragraph("<b>3.1.2 统计指标</b>", styles['Heading3']))
    story.append(Paragraph("系统会统计以下指标：", styles['BodyText']))
    stats = [
        "<b>total（总转化数）</b>：统计时间窗口内所有转化记录的总数（包括被扣量的和未扣量的）",
        "<b>deducted（已扣量数）</b>：统计时间窗口内已经被扣量的转化数量",
        "<b>processed（已处理数）</b>：统计时间窗口内已经处理的转化数量（等于total）"
    ]
    for stat in stats:
        story.append(Paragraph(f"• {stat}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>3.1.3 扣量判断逻辑</b>", styles['Heading3']))
    story.append(Paragraph("系统使用以下逻辑判断是否对当前转化进行扣量：", styles['BodyText']))
    
    code_text = """# 1. 计算应该扣减的总数量
should_deduct_count = int(total * volume_deduction_ratio)

# 2. 如果已经扣减够了，不再扣减
if deducted >= should_deduct_count:
    return False  # 不扣量

# 3. 计算剩余需要扣减的数量
remaining_to_deduct = should_deduct_count - deducted

# 4. 计算剩余未处理的转化数
remaining_conversions = total - processed

# 5. 根据策略决定是否扣减当前转化"""
    
    story.append(create_code_block(code_text, styles))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>3.2 扣量策略详解</b>", styles['Heading2']))
    
    story.append(Paragraph("<b>3.2.1 随机策略（random）</b>", styles['Heading3']))
    story.append(Paragraph("<b>原理</b>：使用概率算法，确保在统计时间窗口内达到目标扣量比例。", styles['BodyText']))
    story.append(Paragraph("<b>计算公式</b>：", styles['BodyText']))
    story.append(create_code_block("probability = remaining_to_deduct / remaining_conversions", styles))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("<b>示例</b>：", styles['BodyText']))
    example1 = [
        "配置扣量比例：10%（0.1）",
        "统计窗口内总转化：100个",
        "应该扣量：10个",
        "已扣量：5个",
        "已处理：80个",
        "剩余需扣量：5个",
        "剩余未处理：20个",
        "当前转化扣量概率：5/20 = 25%"
    ]
    for item in example1:
        story.append(Paragraph(f"• {item}", styles['BodyText']))
        story.append(Spacer(1, 0.05*cm))
    story.append(Paragraph("<b>优点</b>：扣量分布随机，难以预测；能确保总体比例准确。", styles['BodyText']))
    story.append(Paragraph("<b>缺点</b>：可能出现短期波动。", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>3.2.2 按比例策略（proportional）</b>", styles['Heading3']))
    story.append(Paragraph("<b>原理</b>：按固定间隔扣量，如每N个扣1个。", styles['BodyText']))
    story.append(Paragraph("<b>计算公式</b>：", styles['BodyText']))
    story.append(create_code_block("interval = int(1 / volume_deduction_ratio)\nshould_deduct = (processed + 1) % interval == 0", styles))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("<b>示例</b>：配置扣量比例10%（0.1），间隔为10，第1、11、21、31...个转化会被扣量。", styles['BodyText']))
    story.append(Paragraph("<b>优点</b>：扣量分布均匀，可预测性强。", styles['BodyText']))
    story.append(Paragraph("<b>缺点</b>：容易被识别规律。", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>3.2.3 轮询策略（round_robin）</b>", styles['Heading3']))
    story.append(Paragraph("<b>原理</b>：轮询方式扣量，从第一个转化开始按间隔循环。", styles['BodyText']))
    story.append(Paragraph("<b>计算公式</b>：", styles['BodyText']))
    story.append(create_code_block("interval = int(1 / volume_deduction_ratio)\nshould_deduct = processed % interval == 0", styles))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("<b>示例</b>：配置扣量比例10%（0.1），间隔为10，第0、10、20、30...个转化会被扣量（从0开始）。", styles['BodyText']))
    story.append(Paragraph("<b>优点</b>：扣量分布均匀，实现简单。", styles['BodyText']))
    story.append(Paragraph("<b>缺点</b>：容易被识别规律。", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>3.3 扣量执行流程</b>", styles['Heading2']))
    story.append(Paragraph("当系统判断需要扣量时，执行以下流程：", styles['BodyText']))
    flow_steps = [
        "<b>标记扣量</b>：将should_deduct_volume设置为True",
        "<b>更新数量</b>：original_volume = 1, deducted_volume = 1, final_volume = 0",
        "<b>不保存转化</b>：被扣量的转化不会保存到postback_conversions表",
        "<b>记录日志</b>：在conversion_deduction_logs表中记录扣量信息"
    ]
    for step in flow_steps:
        story.append(Paragraph(f"• {step}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(PageBreak())
    
    # ========== 4. 扣金额原理 ==========
    story.append(Paragraph("4. 扣金额原理", styles['Heading1']))
    story.append(Paragraph(
        "扣金额计算相对简单，直接按照配置的比例从原始金额中扣除。",
        styles['BodyText']
    ))
    
    story.append(Paragraph("<b>4.1 计算公式</b>", styles['Heading2']))
    code_text2 = """deduction_amount = original_amount * amount_deduction_ratio
final_amount = original_amount - deduction_amount"""
    story.append(create_code_block(code_text2, styles))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>4.2 计算示例</b>", styles['Heading2']))
    example_data = [
        ['原始金额', '扣金额比例', '扣减金额', '最终金额'],
        ['100元', '10% (0.1)', '100 × 0.1 = 10元', '100 - 10 = 90元'],
        ['50元', '20% (0.2)', '50 × 0.2 = 10元', '50 - 10 = 40元']
    ]
    example_table = create_table(example_data, col_widths=[3*cm, 3*cm, 5*cm, 4*cm], styles=styles)
    story.append(example_table)
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>4.3 扣金额执行流程</b>", styles['Heading2']))
    amount_flow = [
        "<b>计算扣减金额</b>：根据配置的比例计算扣减金额",
        "<b>更新金额</b>：original_amount保持原始金额，deducted_amount记录扣减的金额，final_amount计算最终金额",
        "<b>保存转化</b>：扣金额后的转化仍然保存到postback_conversions表，但使用final_amount作为payout字段",
        "<b>记录日志</b>：在conversion_deduction_logs表中记录扣金额信息"
    ]
    for step in amount_flow:
        story.append(Paragraph(f"• {step}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>4.4 扣金额与扣量的区别</b>", styles['Heading2']))
    comparison_data = [
        ['特性', '扣量', '扣金额'],
        ['操作对象', '转化数量', '转化金额'],
        ['是否保存转化', '否', '是'],
        ['计算方式', '动态统计', '固定比例'],
        ['可见性', '隐藏', '可见'],
        ['应用场景', '完全拒绝低质量转化', '降低转化成本但保留转化']
    ]
    comparison_table = create_table(comparison_data, styles=styles)
    story.append(comparison_table)
    
    story.append(PageBreak())
    
    # ========== 5. 配置层级与优先级 ==========
    story.append(Paragraph("5. 配置层级与优先级", styles['Heading1']))
    
    story.append(Paragraph("<b>5.1 配置层级</b>", styles['Heading2']))
    story.append(Paragraph(
        "系统支持三个层级的配置，每个配置只能属于一个层级：",
        styles['BodyText']
    ))
    
    story.append(Paragraph("<b>5.1.1 Offer级别配置</b>", styles['Heading3']))
    story.append(Paragraph("<b>适用场景</b>：", styles['BodyText']))
    story.append(Paragraph("• 针对特定Offer设置扣减规则", styles['BodyText']))
    story.append(Paragraph("• 不同Offer有不同的扣减需求", styles['BodyText']))
    story.append(Paragraph("<b>配置方式</b>：offer_id指定Offer ID，advertiser_id和publisher_id为NULL", styles['BodyText']))
    story.append(Paragraph("<b>优先级</b>：最高（1）", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>5.1.2 Advertiser级别配置</b>", styles['Heading3']))
    story.append(Paragraph("<b>适用场景</b>：", styles['BodyText']))
    story.append(Paragraph("• 针对特定广告主设置统一的扣减规则", styles['BodyText']))
    story.append(Paragraph("• 适用于广告主下所有Offer", styles['BodyText']))
    story.append(Paragraph("<b>配置方式</b>：advertiser_id指定广告主ID，offer_id和publisher_id为NULL", styles['BodyText']))
    story.append(Paragraph("<b>优先级</b>：中等（2）", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>5.1.3 Publisher级别配置</b>", styles['Heading3']))
    story.append(Paragraph("<b>适用场景</b>：", styles['BodyText']))
    story.append(Paragraph("• 针对特定渠道设置扣减规则", styles['BodyText']))
    story.append(Paragraph("• 适用于该渠道的所有转化", styles['BodyText']))
    story.append(Paragraph("<b>配置方式</b>：publisher_id指定渠道ID，advertiser_id和offer_id为NULL", styles['BodyText']))
    story.append(Paragraph("<b>优先级</b>：最低（3）", styles['BodyText']))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>5.2 优先级查找逻辑</b>", styles['Heading2']))
    story.append(Paragraph("系统按以下顺序查找配置：", styles['BodyText']))
    priority_logic = [
        "1. 查找Offer级别配置 - 如果找到，使用该配置；如果未找到，继续查找",
        "2. 查找Advertiser级别配置 - 如果找到，使用该配置；如果未找到，继续查找",
        "3. 查找Publisher级别配置 - 如果找到，使用该配置；如果未找到，不应用扣减"
    ]
    for logic in priority_logic:
        story.append(Paragraph(logic, styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>5.3 优先级示例</b>", styles['Heading2']))
    story.append(Paragraph("<b>场景1</b>：Offer ID=100有配置（扣量10%），Advertiser ID=10有配置（扣量20%），Publisher ID=5有配置（扣量30%）。", styles['BodyText']))
    story.append(Paragraph("结果：使用Offer配置（扣量10%）", styles['BodyText']))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph("<b>场景2</b>：Offer ID=100无配置，Advertiser ID=10有配置（扣量20%），Publisher ID=5有配置（扣量30%）。", styles['BodyText']))
    story.append(Paragraph("结果：使用Advertiser配置（扣量20%）", styles['BodyText']))
    story.append(Spacer(1, 0.1*cm))
    story.append(Paragraph("<b>场景3</b>：Offer ID=100无配置，Advertiser ID=10无配置，Publisher ID=5有配置（扣量30%）。", styles['BodyText']))
    story.append(Paragraph("结果：使用Publisher配置（扣量30%）", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>5.4 配置激活状态</b>", styles['Heading2']))
    story.append(Paragraph("每个配置都有一个is_active字段，只有激活的配置才会被使用：", styles['BodyText']))
    story.append(Paragraph("• is_active = True：配置激活，会被使用", styles['BodyText']))
    story.append(Paragraph("• is_active = False：配置未激活，不会被使用", styles['BodyText']))
    
    story.append(PageBreak())
    
    # ========== 6. 扣减策略详解 ==========
    story.append(Paragraph("6. 扣减策略详解", styles['Heading1']))
    
    story.append(Paragraph("<b>6.1 策略选择建议</b>", styles['Heading2']))
    
    story.append(Paragraph("<b>6.1.1 随机策略（random）</b>", styles['Heading3']))
    story.append(Paragraph("<b>适用场景</b>：", styles['BodyText']))
    story.append(Paragraph("• 需要隐藏扣量规律", styles['BodyText']))
    story.append(Paragraph("• 对扣量分布要求不严格", styles['BodyText']))
    story.append(Paragraph("• 希望扣量难以被预测", styles['BodyText']))
    story.append(Paragraph("<b>推荐使用</b>：对渠道质量要求较高的场景，需要防止渠道识别扣量规律", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>6.1.2 按比例策略（proportional）</b>", styles['Heading3']))
    story.append(Paragraph("<b>适用场景</b>：", styles['BodyText']))
    story.append(Paragraph("• 需要均匀分布扣量", styles['BodyText']))
    story.append(Paragraph("• 对扣量时间分布有要求", styles['BodyText']))
    story.append(Paragraph("• 希望扣量可预测", styles['BodyText']))
    story.append(Paragraph("<b>推荐使用</b>：需要稳定扣量比例的场景，对扣量分布有明确要求", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>6.1.3 轮询策略（round_robin）</b>", styles['Heading3']))
    story.append(Paragraph("<b>适用场景</b>：", styles['BodyText']))
    story.append(Paragraph("• 需要简单的扣量逻辑", styles['BodyText']))
    story.append(Paragraph("• 对扣量分布要求不高", styles['BodyText']))
    story.append(Paragraph("• 希望实现简单", styles['BodyText']))
    story.append(Paragraph("<b>推荐使用</b>：简单的扣量需求，对扣量策略要求不高的场景", styles['BodyText']))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>6.2 策略对比</b>", styles['Heading2']))
    strategy_comparison = [
        ['策略', '扣量分布', '可预测性', '实现复杂度', '推荐度'],
        ['random', '随机', '低', '中等', '5星（最高）'],
        ['proportional', '均匀', '高', '低', '4星'],
        ['round_robin', '均匀', '高', '低', '3星']
    ]
    strategy_table = create_table(strategy_comparison, col_widths=[3*cm, 3*cm, 2.5*cm, 3*cm, 3.5*cm], styles=styles)
    story.append(strategy_table)
    
    story.append(PageBreak())
    
    # ========== 7. 系统架构 ==========
    story.append(Paragraph("7. 系统架构", styles['Heading1']))
    
    story.append(Paragraph("<b>7.1 核心模块</b>", styles['Heading2']))
    
    story.append(Paragraph("<b>7.1.1 扣减管理模块（deduction_manager.py）</b>", styles['Heading3']))
    story.append(Paragraph("位置：app/core/deduction/deduction_manager.py", styles['BodyText']))
    story.append(Paragraph("<b>主要功能</b>：", styles['BodyText']))
    manager_funcs = [
        "find_deduction_config()：查找扣减配置",
        "get_recent_conversion_stats()：获取转化统计",
        "should_deduct_volume()：判断是否扣量",
        "calculate_amount_deduction()：计算扣金额",
        "apply_deduction()：应用扣减",
        "log_deduction()：记录扣减日志"
    ]
    for func in manager_funcs:
        story.append(Paragraph(f"• {func}", styles['BodyText']))
        story.append(Spacer(1, 0.05*cm))
    
    story.append(Paragraph("<b>7.1.2 服务层（conversion_deduction_service.py）</b>", styles['Heading3']))
    story.append(Paragraph("位置：app/services/cpl/conversion_deduction_service.py", styles['BodyText']))
    story.append(Paragraph("<b>主要功能</b>：扣减配置的CRUD操作、扣减日志查询、扣减统计计算", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>7.1.3 API层（deductions.py）</b>", styles['Heading3']))
    story.append(Paragraph("位置：app/api/api_v1/endpoints/cpl/conversions/deductions.py", styles['BodyText']))
    story.append(Paragraph("<b>主要功能</b>：提供RESTful API接口、配置管理接口、日志查询接口、统计查询接口", styles['BodyText']))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>7.2 数据流程</b>", styles['Heading2']))
    # 使用Paragraph显示流程图，确保中文正确显示
    flow_steps = [
        "转化到达 (Postback)",
        "查找扣减配置 (find_deduction_config)",
        "获取转化统计 (get_recent_conversion_stats)",
        "判断是否扣量 (should_deduct_volume)",
        "计算扣金额 (calculate_amount_deduction)",
        "应用扣减 (apply_deduction)",
        "记录日志 (log_deduction)",
        "保存转化 (PostbackConversion)"
    ]
    for i, step in enumerate(flow_steps):
        if i > 0:
            story.append(Paragraph("    ↓", styles['BodyText']))
        story.append(Paragraph(step, styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>7.3 数据库表结构</b>", styles['Heading2']))
    story.append(Paragraph("<b>7.3.1 扣减配置表（conversion_deduction_configs）</b>", styles['Heading3']))
    story.append(Paragraph("存储扣减配置信息。", styles['BodyText']))
    story.append(Paragraph("<b>7.3.2 扣减日志表（conversion_deduction_logs）</b>", styles['Heading3']))
    story.append(Paragraph("记录所有扣减操作的详细信息。", styles['BodyText']))
    
    story.append(PageBreak())
    
    # ========== 8. 操作指南 ==========
    story.append(Paragraph("8. 操作指南", styles['Heading1']))
    
    story.append(Paragraph("<b>8.1 创建扣减配置</b>", styles['Heading2']))
    story.append(Paragraph("<b>8.1.1 通过API创建</b>", styles['Heading3']))
    story.append(Paragraph("接口：POST /api/v1/cpl/conversions/deductions/", styles['BodyText']))
    story.append(Paragraph("<b>请求示例</b>：", styles['BodyText']))
    request_example = """{
  "level": "offer",
  "target_id": 100,
  "enable_volume_deduction": true,
  "volume_deduction_ratio": 0.1,
  "deduction_strategy": "random",
  "enable_amount_deduction": true,
  "amount_deduction_ratio": 0.05,
  "priority": 0,
  "is_active": true
}"""
    story.append(create_code_block(request_example, styles))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>参数说明</b>：", styles['BodyText']))
    param_table = [
        ['参数', '类型', '必填', '说明'],
        ['level', 'string', '是', '配置层级：advertiser/offer/publisher'],
        ['target_id', 'int', '是', '配置对象ID'],
        ['enable_volume_deduction', 'bool', '否', '是否启用扣量（默认false）'],
        ['volume_deduction_ratio', 'float', '否', '扣量比例（0-1，默认0.0）'],
        ['deduction_strategy', 'string', '否', '扣减策略：random/proportional/round_robin（默认random）'],
        ['enable_amount_deduction', 'bool', '否', '是否启用扣金额（默认false）'],
        ['amount_deduction_ratio', 'float', '否', '扣金额比例（0-1，默认0.0）'],
        ['priority', 'int', '否', '优先级（默认0）'],
        ['is_active', 'bool', '否', '是否激活（默认true）']
    ]
    # 调整参数表格列宽：参数名、类型、必填、说明
    param_table_obj = create_table(param_table, col_widths=[4.5*cm, 2*cm, 2*cm, 6.5*cm], styles=styles)
    story.append(param_table_obj)
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>注意事项</b>：", styles['BodyText']))
    story.append(Paragraph("• 至少需要启用一种扣减方式（扣量或扣金额）", styles['BodyText']))
    story.append(Paragraph("• 同一层级同一对象只能有一个激活的配置", styles['BodyText']))
    story.append(Paragraph("• 扣量比例和扣金额比例必须在0-1之间", styles['BodyText']))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>8.1.2 配置示例</b>", styles['Heading3']))
    story.append(Paragraph("<b>示例1：仅扣量</b>", styles['BodyText']))
    example1_json = """{
  "level": "offer",
  "target_id": 100,
  "enable_volume_deduction": true,
  "volume_deduction_ratio": 0.15,
  "deduction_strategy": "random",
  "enable_amount_deduction": false,
  "is_active": true
}"""
    story.append(create_code_block(example1_json, styles))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>示例2：仅扣金额</b>", styles['BodyText']))
    example2_json = """{
  "level": "advertiser",
  "target_id": 10,
  "enable_volume_deduction": false,
  "enable_amount_deduction": true,
  "amount_deduction_ratio": 0.1,
  "is_active": true
}"""
    story.append(create_code_block(example2_json, styles))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>示例3：同时扣量和扣金额</b>", styles['BodyText']))
    example3_json = """{
  "level": "publisher",
  "target_id": 5,
  "enable_volume_deduction": true,
  "volume_deduction_ratio": 0.1,
  "deduction_strategy": "random",
  "enable_amount_deduction": true,
  "amount_deduction_ratio": 0.05,
  "is_active": true
}"""
    story.append(create_code_block(example3_json, styles))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>8.2 查询扣减配置</b>", styles['Heading2']))
    story.append(Paragraph("接口：GET /api/v1/cpl/conversions/deductions/", styles['BodyText']))
    story.append(Paragraph("支持分页、层级过滤、状态过滤、关键词搜索等功能。", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>8.3 更新扣减配置</b>", styles['Heading2']))
    story.append(Paragraph("接口：PUT /api/v1/cpl/conversions/deductions/{config_id}", styles['BodyText']))
    story.append(Paragraph("注意事项：只能更新配置的字段值，不能修改level和target_id。", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>8.4 删除扣减配置</b>", styles['Heading2']))
    story.append(Paragraph("接口：DELETE /api/v1/cpl/conversions/deductions/{config_id}", styles['BodyText']))
    story.append(Paragraph("注意事项：删除配置不会影响已记录的扣减日志。", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>8.5 查询扣减日志</b>", styles['Heading2']))
    story.append(Paragraph("接口：GET /api/v1/cpl/conversions/deductions/logs", styles['BodyText']))
    story.append(Paragraph("支持按日期范围、广告主ID、Offer ID、渠道ID过滤，支持分页查询。", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>8.6 查询扣减统计</b>", styles['Heading2']))
    story.append(Paragraph("接口：GET /api/v1/cpl/conversions/deductions/stats", styles['BodyText']))
    story.append(Paragraph("支持按日期范围、广告主ID、Offer ID、渠道ID过滤，支持按时间/广告主/Offer/渠道分组统计。", styles['BodyText']))
    
    story.append(PageBreak())
    
    # ========== 9. 数据模型 ==========
    story.append(Paragraph("9. 数据模型", styles['Heading1']))
    
    story.append(Paragraph("<b>9.1 扣减配置表（conversion_deduction_configs）</b>", styles['Heading2']))
    story.append(Paragraph("<b>9.1.1 表结构</b>", styles['Heading3']))
    config_table_data = [
        ['字段名', '类型', '说明'],
        ['id', 'int', '配置ID（主键）'],
        ['advertiser_id', 'int', '广告主ID（可为NULL）'],
        ['offer_id', 'int', 'Offer ID（可为NULL）'],
        ['publisher_id', 'int', '渠道ID（可为NULL）'],
        ['volume_deduction_ratio', 'float', '扣量比例（0-1）'],
        ['amount_deduction_ratio', 'float', '扣金额比例（0-1）'],
        ['deduction_strategy', 'string', '扣减策略'],
        ['enable_volume_deduction', 'bool', '是否启用扣量'],
        ['enable_amount_deduction', 'bool', '是否启用扣金额'],
        ['priority', 'int', '优先级'],
        ['is_active', 'bool', '是否激活'],
        ['created_at', 'datetime', '创建时间'],
        ['updated_at', 'datetime', '更新时间']
    ]
    # 调整配置表列宽：字段名、类型、说明
    config_table = create_table(config_table_data, col_widths=[4.5*cm, 2.5*cm, 8*cm], styles=styles)
    story.append(config_table)
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>9.1.2 索引</b>", styles['Heading3']))
    indexes = [
        "idx_advertiser_id：广告主ID索引",
        "idx_offer_id：Offer ID索引",
        "idx_publisher_id：渠道ID索引",
        "idx_is_active：激活状态索引",
        "idx_priority：优先级索引"
    ]
    for idx in indexes:
        story.append(Paragraph(f"• {idx}", styles['BodyText']))
        story.append(Spacer(1, 0.05*cm))
    
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("<b>9.2 扣减日志表（conversion_deduction_logs）</b>", styles['Heading2']))
    story.append(Paragraph("<b>9.2.1 表结构</b>", styles['Heading3']))
    log_table_data = [
        ['字段名', '类型', '说明'],
        ['id', 'int', '记录ID（主键）'],
        ['conversion_id', 'int', '转化记录ID（可为NULL）'],
        ['click_id', 'string', '点击ID'],
        ['advertiser_id', 'int', '广告主ID'],
        ['offer_id', 'int', 'Offer ID'],
        ['publisher_id', 'int', '渠道ID'],
        ['original_volume', 'int', '原始转化数量'],
        ['original_amount', 'float', '原始转化金额'],
        ['deducted_volume', 'int', '扣减的转化数量'],
        ['deducted_amount', 'float', '扣减的转化金额'],
        ['final_volume', 'int', '最终转化数量'],
        ['final_amount', 'float', '最终转化金额'],
        ['deduction_config_id', 'int', '使用的扣减配置ID'],
        ['volume_deduction_ratio', 'float', '使用的扣量比例'],
        ['amount_deduction_ratio', 'float', '使用的扣金额比例'],
        ['deduction_strategy', 'string', '使用的扣减策略'],
        ['deduction_reason', 'text', '扣减原因说明'],
        ['created_at', 'datetime', '创建时间']
    ]
    # 调整日志表列宽：字段名、类型、说明
    log_table = create_table(log_table_data, col_widths=[4.5*cm, 2.5*cm, 8*cm], styles=styles)
    story.append(log_table)
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>9.2.2 索引</b>", styles['Heading3']))
    log_indexes = [
        "idx_conversion_id：转化记录ID索引",
        "idx_click_id：点击ID索引",
        "idx_advertiser_id：广告主ID索引",
        "idx_offer_id：Offer ID索引",
        "idx_publisher_id：渠道ID索引",
        "idx_created_at：创建时间索引",
        "idx_deduction_config_id：扣减配置ID索引"
    ]
    for idx in log_indexes:
        story.append(Paragraph(f"• {idx}", styles['BodyText']))
        story.append(Spacer(1, 0.05*cm))
    
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("<b>9.3 数据关系</b>", styles['Heading2']))
    # 使用Paragraph显示数据关系，确保中文正确显示
    story.append(Paragraph("<b>ConversionDeductionConfig (扣减配置)</b>", styles['BodyText']))
    story.append(Paragraph("    • advertiser_id → Advertiser (广告主)", styles['BodyText']))
    story.append(Paragraph("    • offer_id → Offer (Offer)", styles['BodyText']))
    story.append(Paragraph("    • publisher_id → Publisher (渠道)", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("<b>ConversionDeductionLog (扣减日志)</b>", styles['BodyText']))
    story.append(Paragraph("    • conversion_id → PostbackConversion (转化记录)", styles['BodyText']))
    story.append(Paragraph("    • click_id → Click (点击记录)", styles['BodyText']))
    story.append(Paragraph("    • advertiser_id → Advertiser (广告主)", styles['BodyText']))
    story.append(Paragraph("    • offer_id → Offer (Offer)", styles['BodyText']))
    story.append(Paragraph("    • publisher_id → Publisher (渠道)", styles['BodyText']))
    story.append(Paragraph("    • deduction_config_id → ConversionDeductionConfig (扣减配置)", styles['BodyText']))
    
    story.append(PageBreak())
    
    # ========== 10. 统计与监控 ==========
    story.append(Paragraph("10. 统计与监控", styles['Heading1']))
    
    story.append(Paragraph("<b>10.1 关键指标</b>", styles['Heading2']))
    story.append(Paragraph("<b>10.1.1 扣量指标</b>", styles['Heading3']))
    volume_metrics = [
        "<b>原始转化数（original_volume）</b>：统计时间窗口内所有转化数量",
        "<b>已扣量数（deducted_volume）</b>：统计时间窗口内被扣量的转化数量",
        "<b>最终转化数（final_volume）</b>：统计时间窗口内未被扣量的转化数量",
        "<b>扣量比例（volume_deduction_ratio）</b>：已扣量数 / 原始转化数"
    ]
    for metric in volume_metrics:
        story.append(Paragraph(f"• {metric}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>10.1.2 扣金额指标</b>", styles['Heading3']))
    amount_metrics = [
        "<b>原始金额（original_amount）</b>：统计时间窗口内所有转化的原始金额总和",
        "<b>已扣金额（deducted_amount）</b>：统计时间窗口内被扣减的金额总和",
        "<b>最终金额（final_amount）</b>：统计时间窗口内扣减后的金额总和",
        "<b>扣金额比例（amount_deduction_ratio）</b>：已扣金额 / 原始金额"
    ]
    for metric in amount_metrics:
        story.append(Paragraph(f"• {metric}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>10.2 监控建议</b>", styles['Heading2']))
    story.append(Paragraph("<b>10.2.1 实时监控</b>", styles['Heading3']))
    realtime_monitoring = [
        "监控扣量比例是否达到配置目标",
        "监控扣金额是否正常计算",
        "监控扣减日志是否正常记录"
    ]
    for item in realtime_monitoring:
        story.append(Paragraph(f"• {item}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>10.2.2 定期检查</b>", styles['Heading3']))
    regular_checks = [
        "每周检查扣减统计，确保扣减比例符合预期",
        "每月分析扣减日志，识别异常模式",
        "定期审查配置，确保配置合理有效"
    ]
    for item in regular_checks:
        story.append(Paragraph(f"• {item}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(Paragraph("<b>10.3 告警设置</b>", styles['Heading2']))
    alerts = [
        "<b>扣量比例异常</b>：实际扣量比例与配置比例偏差超过5%",
        "<b>扣减日志缺失</b>：连续1小时没有扣减日志记录",
        "<b>配置异常</b>：发现无效或冲突的配置"
    ]
    for alert in alerts:
        story.append(Paragraph(f"• {alert}", styles['BodyText']))
        story.append(Spacer(1, 0.1*cm))
    
    story.append(PageBreak())
    
    # ========== 11. 常见问题 ==========
    story.append(Paragraph("11. 常见问题", styles['Heading1']))
    
    story.append(Paragraph("<b>11.1 扣量相关问题</b>", styles['Heading2']))
    story.append(Paragraph("<b>Q1：为什么扣量比例和配置不一致？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：扣量比例是动态计算的，基于统计时间窗口（默认24小时）内的数据。"
        "在时间窗口初期，扣量比例可能不稳定，随着数据积累会逐渐接近配置比例。",
        styles['BodyText']
    ))
    story.append(Paragraph("<b>解决方案</b>：", styles['BodyText']))
    story.append(Paragraph("• 等待统计时间窗口积累足够数据", styles['BodyText']))
    story.append(Paragraph("• 检查是否有多个配置冲突", styles['BodyText']))
    story.append(Paragraph("• 检查配置的激活状态", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>Q2：扣量后转化去哪里了？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：被扣量的转化不会保存到postback_conversions表，但会在conversion_deduction_logs表中记录。"
        "这是系统的设计，目的是隐藏扣量操作。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>Q3：如何调整扣量比例？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：通过更新扣减配置的volume_deduction_ratio字段。"
        "注意，调整后只影响新的转化，已处理的转化不会重新计算。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>11.2 扣金额相关问题</b>", styles['Heading2']))
    story.append(Paragraph("<b>Q1：扣金额是每个转化都扣吗？</b>", styles['Heading3']))
    story.append(Paragraph("A：是的，如果启用了扣金额，每个转化都会按照配置的比例扣减金额。", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>Q2：扣金额后的转化还能看到吗？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：可以，扣金额后的转化仍然会保存到postback_conversions表，但payout字段会使用扣减后的金额。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>Q3：如何计算扣金额？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：扣金额 = 原始金额 × 扣金额比例。例如，原始金额100元，扣金额比例10%，则扣减10元，最终金额90元。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>11.3 配置相关问题</b>", styles['Heading2']))
    story.append(Paragraph("<b>Q1：多个配置会冲突吗？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：不会，系统按优先级查找配置，只会使用优先级最高的配置。优先级：Offer > Advertiser > Publisher。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>Q2：如何禁用配置？</b>", styles['Heading3']))
    story.append(Paragraph("A：有两种方式：", styles['BodyText']))
    story.append(Paragraph("1. 更新配置的is_active字段为false", styles['BodyText']))
    story.append(Paragraph("2. 删除配置", styles['BodyText']))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>Q3：配置修改后何时生效？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：配置修改后立即生效，只影响新的转化，已处理的转化不会重新计算。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>11.4 性能相关问题</b>", styles['Heading2']))
    story.append(Paragraph("<b>Q1：扣减操作会影响性能吗？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：扣减操作会进行数据库查询和统计计算，但系统已优化，对性能影响较小。"
        "如果转化量非常大，建议定期清理旧的扣减日志。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>Q2：统计时间窗口可以调整吗？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：可以，在代码中修改get_recent_conversion_stats()函数的hours参数。"
        "但建议保持24小时，这是经过优化的默认值。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>11.5 数据一致性问题</b>", styles['Heading2']))
    story.append(Paragraph("<b>Q1：扣减日志和转化记录不一致怎么办？</b>", styles['Heading3']))
    story.append(Paragraph(
        "A：这是正常现象。被扣量的转化不会保存到转化表，但会在扣减日志表中记录。"
        "可以通过扣减日志表查询所有转化（包括被扣量的）。",
        styles['BodyText']
    ))
    story.append(Spacer(1, 0.2*cm))
    
    story.append(Paragraph("<b>Q2：如何验证扣减是否正确？</b>", styles['Heading3']))
    story.append(Paragraph("A：可以通过以下方式验证：", styles['BodyText']))
    story.append(Paragraph("1. 查询扣减统计，检查扣量比例和扣金额比例", styles['BodyText']))
    story.append(Paragraph("2. 查询扣减日志，检查具体扣减记录", styles['BodyText']))
    story.append(Paragraph("3. 对比原始金额和最终金额", styles['BodyText']))
    
    story.append(PageBreak())
    
    # ========== 附录 ==========
    story.append(Paragraph("附录", styles['Heading1']))
    
    story.append(Paragraph("<b>A. 代码文件位置</b>", styles['Heading2']))
    code_files = [
        "扣减管理模块：app/core/deduction/deduction_manager.py",
        "服务层：app/services/cpl/conversion_deduction_service.py",
        "API层：app/api/api_v1/endpoints/cpl/conversions/deductions.py",
        "数据模型：app/models/models.py（ConversionDeductionConfig、ConversionDeductionLog）",
        "Schema定义：app/schemas/cpl/deduction.py"
    ]
    for file in code_files:
        story.append(Paragraph(f"• {file}", styles['BodyText']))
        story.append(Spacer(1, 0.05*cm))
    
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("<b>B. API接口列表</b>", styles['Heading2']))
    api_table_data = [
        ['接口', '方法', '说明'],
        ['/api/v1/cpl/conversions/deductions/', 'POST', '创建扣减配置'],
        ['/api/v1/cpl/conversions/deductions/', 'GET', '获取扣减配置列表'],
        ['/api/v1/cpl/conversions/deductions/{config_id}', 'PUT', '更新扣减配置'],
        ['/api/v1/cpl/conversions/deductions/{config_id}', 'DELETE', '删除扣减配置'],
        ['/api/v1/cpl/conversions/deductions/{config_id}/status', 'PATCH', '更新配置状态'],
        ['/api/v1/cpl/conversions/deductions/stats', 'GET', '获取扣减统计'],
        ['/api/v1/cpl/conversions/deductions/logs', 'GET', '获取扣减日志']
    ]
    # 调整列宽：接口列更宽，方法列适中，说明列更宽
    # 调整列宽：接口列更宽以容纳长路径，方法列适中，说明列更宽
    # 调整列宽：接口列更宽以容纳长路径，方法列适中，说明列更宽
    api_table = create_table(api_table_data, col_widths=[8*cm, 2.5*cm, 4.5*cm], styles=styles)
    story.append(api_table)
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>C. 术语表</b>", styles['Heading2']))
    term_table_data = [
        ['术语', '说明'],
        ['CPL', 'Cost Per Lead，按转化付费'],
        ['扣量', '将转化标记为无效，不计算到统计中'],
        ['扣金额', '按比例从转化金额中扣除'],
        ['配置层级', '配置的作用范围（Offer/Advertiser/Publisher）'],
        ['扣减策略', '扣量的执行方式（random/proportional/round_robin）'],
        ['统计时间窗口', '用于计算扣量比例的统计时间范围（默认24小时）']
    ]
    # 术语表列宽：术语、说明
    term_table = create_table(term_table_data, col_widths=[4.5*cm, 10.5*cm], styles=styles)
    story.append(term_table)
    story.append(Spacer(1, 0.3*cm))
    
    story.append(Paragraph("<b>版本历史</b>", styles['Heading2']))
    story.append(Paragraph("• v1.0（2024-01-01）：初始版本，包含基本扣量和扣金额功能", styles['BodyText']))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("文档结束", styles['BodyText']))
    
    return story


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    pdf_file = project_root / "docs" / "CPL系统扣量和扣金额原理与操作说明.pdf"
    
    # 确保目录存在
    pdf_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 创建PDF文档
    doc = SimpleDocTemplate(
        str(pdf_file),
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2.5*cm,
        bottomMargin=2*cm
    )
    
    # 获取样式
    styles = create_custom_styles()
    
    # 创建内容
    story = create_pdf_content(styles)
    
    # 生成PDF
    try:
        doc.build(story)
        print(f"\n✅ 成功生成PDF文档!")
        print(f"📄 文件位置: {pdf_file}")
        print(f"📊 文件大小: {pdf_file.stat().st_size / 1024:.2f} KB")
        print(f"📑 包含所有11个章节的完整内容")
    except Exception as e:
        print(f"❌ 生成PDF失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
