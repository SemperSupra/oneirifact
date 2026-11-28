"""Make a labelled technical contact sheet from the actual assembly renders."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CASES = [("brick_bridge", "Studded-block bridge", "10 parts · 2 definitions"),
         ("log_cabin", "Notched-beam cabin", "15 parts · 2 definitions"),
         ("rod_hub_frame", "Socketed tetrahedral frame", "10 parts · 5 definitions")]

def main(args):
    image = Image.new("RGB", (1500, 1010), "#edf0f2")
    draw = ImageDraw.Draw(image)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    title = ImageFont.truetype(font_path, 28)
    heading = ImageFont.truetype(font_path, 22)
    caption = ImageFont.truetype(font_path, 17)
    draw.text((25, 15), "Oneirifact · Reusable construction studies", font=title, fill="#142337")
    draw.text((25, 56), args.subtitle, font=caption, fill="#3c4d60")
    for col, (case, name, count) in enumerate(CASES):
        x = col * 500
        draw.text((x + 20, 95), name, font=heading, fill="#142337")
        draw.text((x + 20, 124), count, font=caption, fill="#3c4d60")
        for row, state in enumerate(["assembled", "exploded"]):
            source = args.renders / (args.prefix + case) / (state + ".png")
            with Image.open(source) as im:
                im.load()
                assert im.size == (1000, 800), source
                resized = im.convert("RGB").resize((500, 400), Image.Resampling.LANCZOS)
                image.paste(resized, (x, 155 + row * 415))
    draw.text((25, 980), "Canonical source, named instances and BOM retained · Source alignment checked · Physical fit and loads unqualified",
              font=caption, fill="#3c4d60")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("renders", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--prefix", default="")
    p.add_argument("--subtitle", default="Actual native Oneirifact meshes rendered in Blender; assembled above, exploded below")
    main(p.parse_args())
