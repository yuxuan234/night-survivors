"""Run this on your own computer:  python make_assets.py

It makes crisp 3x bigger copies of every picture in raw_art/ inside assets/,
plus two bright crystal gems coloured from gem.png (blue = XP 1, pink = XP 2).
Nothing else uses Pillow: main.py only loads the finished files from assets/.
"""

import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw_art")
OUT = os.path.join(HERE, "assets")
SCALE = 3

# (dark colour, light colour) for the crystal gems.
GEM_COLOURS = {
    "gem_blue.png": ((40, 90, 220), (170, 225, 255)),
    "gem_pink.png": ((215, 40, 140), (255, 190, 240)),
}


def upscale(image):
    return image.resize((image.width * SCALE, image.height * SCALE), Image.NEAREST)


def recolour(image, dark, light):
    """Keep the shape and the shading of the gem, but change its colours."""
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    shades = {}
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            shades[(x, y)] = 0.299 * r + 0.587 * g + 0.114 * b
    if not shades:
        return rgba
    lowest = min(shades.values())
    highest = max(shades.values())
    span = highest - lowest or 1.0
    out = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    target = out.load()
    for (x, y), value in shades.items():
        ratio = (value - lowest) / span
        r, g, b = [round(d + (l - d) * ratio) for d, l in zip(dark, light)]
        target[x, y] = (r, g, b, pixels[x, y][3])
    return out


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    made = []
    for name in sorted(os.listdir(RAW)):
        if not name.lower().endswith(".png"):
            continue
        if name == "gem.png":
            # The gem is only used to make the two coloured crystals below.
            continue
        image = Image.open(os.path.join(RAW, name)).convert("RGBA")
        upscale(image).save(os.path.join(OUT, name))
        made.append(name)

    gem = Image.open(os.path.join(RAW, "gem.png")).convert("RGBA")
    for name, (dark, light) in GEM_COLOURS.items():
        upscale(recolour(gem, dark, light)).save(os.path.join(OUT, name))
        made.append(name)

    size = gem.width * SCALE
    print("wrote %d files to %s/ (%d x %d pixels each):" % (len(made), OUT, size, size))
    for name in made:
        print("  ", name)


if __name__ == "__main__":
    main()
