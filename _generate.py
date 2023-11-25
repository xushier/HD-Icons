import pathlib
from pathlib import Path

root          = pathlib.Path(__file__).parent.resolve()
template_path = root / "_TEMPLATE.md"
readme_path   = root / "README.md"


# def generate_img_tag(file,folder,radius):
    # return f'<div style="width: 105px;text-align: center;display: inline-block;font-size: 12px;margin: 5px;"><img style="border: 1.5px dashed white;border-radius: {radius};" src="{folder}/{file.name}" alt="{file.stem}" /><br/>{file.stem}</div>'

def generate_img_tag(file,folder):
    return f'<img src="{folder}/{file.name}" alt="{file.stem}" width="95">'

imgs            = sorted(Path("./border-radius").glob("*.png"))
img_tags        = [generate_img_tag(x,"border-radius") for x in imgs]
circle_imgs     = sorted(Path("./circle").glob("*.png"))
circle_img_tags = [generate_img_tag(x,"circle") for x in circle_imgs]
svg_imgs     = sorted(Path("./svg").glob("*.svg"))
svg_img_tags = [generate_img_tag(x,"svg") for x in svg_imgs]
all_nums        = len(img_tags) + len(circle_img_tags) + len(svg_img_tags)

# Read the template file 
with open(template_path, "r", encoding="UTF-8") as f:
    lines = f.readlines()

# Find the line that starts with "<!-- ICONS -->"
# for line in lines:
#     if line.startswith("<!-- START BORDER-RADIUS ICONS -->"):
#         line_number = lines.index(line)
#         break
# for line in lines:
#     if line.startswith("<!-- START CIRCLE ICONS -->"):
#         circle_line_number = lines.index(line)
#         break
for line in lines:
    if line.startswith("<!-- START SVG ICONS -->"):
        svg_line_number = lines.index(line)
        break

# Insert the icons after the line
# lines.insert(line_number + 1, " ".join(img_tags))
# lines.insert(circle_line_number + 2, " ".join(circle_img_tags))
lines.insert(svg_line_number + 3, " ".join(svg_img_tags))

lines = ["# 图标预览（当前共计 " + str(all_nums) + " 个）" if '# 图标预览（当前共计 0 个）' in i else i for i in lines]

# Write the new file
with open(readme_path, "w", encoding="UTF-8") as f:
    f.write("".join(lines))
    f.write("\n")

print("文件已更新!")
