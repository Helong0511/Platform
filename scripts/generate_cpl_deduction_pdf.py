"""
生成CPL系统扣量和扣金额原理与操作说明PDF文档
使用reportlab库生成PDF
"""
import os
import sys
from pathlib import Path
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Preformatted
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except ImportError:
    print("请先安装依赖: pip install reportlab")
    sys.exit(1)


def read_markdown_file(file_path: str) -> str:
    """读取Markdown文件内容"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def parse_markdown_to_elements(content: str, styles):
    """将Markdown内容解析为reportlab元素"""
    elements = []
    lines = content.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 跳过空行
        if not line:
            i += 1
            continue
        
        # 标题处理
        if line.startswith('# '):
            elements.append(Spacer(1, 0.5*cm))
            elements.append(Paragraph(line[2:], styles['Heading1']))
            elements.append(Spacer(1, 0.3*cm))
        elif line.startswith('## '):
            elements.append(Spacer(1, 0.4*cm))
            elements.append(Paragraph(line[3:], styles['Heading2']))
            elements.append(Spacer(1, 0.2*cm))
        elif line.startswith('### '):
            elements.append(Spacer(1, 0.3*cm))
            elements.append(Paragraph(line[4:], styles['Heading3']))
            elements.append(Spacer(1, 0.15*cm))
        elif line.startswith('#### '):
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(line[5:], styles['Heading4']))
            elements.append(Spacer(1, 0.1*cm))
        # 代码块
        elif line.startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            if code_lines:
                code_text = '\n'.join(code_lines)
                elements.append(Spacer(1, 0.2*cm))
                elements.append(Preformatted(code_text, styles['Code']))
                elements.append(Spacer(1, 0.2*cm))
        # 表格（简单处理）
        elif '|' in line and line.count('|') >= 2:
            table_data = []
            # 收集表格行
            while i < len(lines) and '|' in lines[i]:
                row = [cell.strip() for cell in lines[i].split('|')[1:-1]]
                if row and not all(c.startswith('-') for c in row):  # 跳过分隔行
                    table_data.append(row)
                i += 1
            i -= 1  # 回退一行
            
            if table_data:
                table = Table(table_data)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
                ]))
                elements.append(Spacer(1, 0.2*cm))
                elements.append(table)
                elements.append(Spacer(1, 0.2*cm))
        # 列表项
        elif line.startswith('- ') or line.startswith('* '):
            text = line[2:].strip()
            elements.append(Paragraph(f"• {text}", styles['Normal']))
        elif line.startswith(('1. ', '2. ', '3. ', '4. ', '5. ', '6. ', '7. ', '8. ', '9. ')):
            elements.append(Paragraph(line, styles['Normal']))
        # 普通段落
        else:
            # 处理内联代码
            processed_line = line.replace('`', '<font name="Courier">').replace('`', '</font>')
            elements.append(Paragraph(processed_line, styles['Normal']))
            elements.append(Spacer(1, 0.1*cm))
        
        i += 1
    
    return elements


def create_pdf(markdown_file: str, output_pdf: str):
    """创建PDF文档"""
    # 读取Markdown内容
    content = read_markdown_file(markdown_file)
    
    # 创建PDF文档
    doc = SimpleDocTemplate(
        output_pdf,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2.5*cm,
        bottomMargin=2*cm
    )
    
    # 获取样式
    styles = getSampleStyleSheet()
    
    # 创建自定义样式
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=30,
        alignment=1  # 居中
    ))
    
    styles.add(ParagraphStyle(
        name='Code',
        parent=styles['Code'],
        fontSize=9,
        fontName='Courier',
        backColor=colors.HexColor('#f8f8f8'),
        leftIndent=20,
        rightIndent=20,
        spaceBefore=10,
        spaceAfter=10
    ))
    
    # 构建文档内容
    story = []
    
    # 标题页
    story.append(Spacer(1, 5*cm))
    story.append(Paragraph("CPL系统扣量和扣金额", styles['CustomTitle']))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("原理与操作说明", styles['CustomTitle']))
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph(f"生成时间: {datetime.now().strftime('%Y年%m月%d日')}", styles['Normal']))
    story.append(PageBreak())
    
    # 解析Markdown内容
    elements = parse_markdown_to_elements(content, styles)
    story.extend(elements)
    
    # 生成PDF
    doc.build(story)
    print(f"PDF已生成: {output_pdf}")


if __name__ == "__main__":
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    
    # Markdown文件路径
    md_file = project_root / "docs" / "cpl_deduction_guide.md"
    
    # PDF输出路径
    pdf_file = project_root / "docs" / "CPL系统扣量和扣金额原理与操作说明.pdf"
    
    if not md_file.exists():
        print(f"错误: Markdown文件不存在: {md_file}")
        sys.exit(1)
    
    try:
        create_pdf(str(md_file), str(pdf_file))
        print(f"\n✅ 成功生成PDF文档!")
        print(f"📄 文件位置: {pdf_file}")
    except Exception as e:
        print(f"❌ 生成PDF失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

