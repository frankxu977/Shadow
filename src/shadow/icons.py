"""Generate Shadow's shield icon without external asset files."""
from PIL import Image, ImageDraw


def make_icon(color="#5d75ff"):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon([(32, 3), (57, 13), (53, 42), (44, 53), (32, 61),
                  (20, 53), (11, 42), (7, 13)], fill=color)
    draw.ellipse((19, 22, 45, 44), fill="white")
    draw.ellipse((26, 27, 38, 39), fill=color)
    return image
