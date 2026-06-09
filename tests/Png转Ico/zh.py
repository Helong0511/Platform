"""
PNG 转 ICO 小工具：将 16×16、32×32 PNG 分别保存为 favicon 用 ICO 文件。

依赖 Pillow；路径为本地开发机绝对路径，运行前请按实际素材目录修改。
"""
from PIL import Image

# Load images

img16 = Image.open('e:\\韩广告\\landing\\static\\16-16.png')
img32 = Image.open('e:\\韩广告\\landing\\static\\32-32.png')

# Save 16x16 PNG as ICO
ico_path_16 = 'e:\\韩广告\\landing\\static\\icon_16.ico'
img16.save(ico_path_16, format='ICO')
print(f"16x16 ICO file saved at: {ico_path_16}")

# Save 32x32 PNG as ICO
ico_path_32 = 'e:\\韩广告\\landing\\static\\icon_32.ico'
img32.save(ico_path_32, format='ICO')
print(f"32x32 ICO file saved at: {ico_path_32}")

# Also save combined ICO (both sizes)
ico_path_combined = 'e:\\韩广告\\landing\\static\\icon.ico'
img32.save(ico_path_combined, format='ICO', sizes=[(16,16),(32,32)])
print(f"Combined ICO file saved at: {ico_path_combined}")
