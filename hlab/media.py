import io

from PIL import Image, ImageDraw

from .storage import ident, sha, stored


def viewport_image(sample, directory=None):
    name = ident(sample["image_id"]) + ".png"
    path = stored("images", name, directory=directory)
    if sha(path) != sample["sha256"]:
        raise ValueError("Evidence image checksum mismatch")
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (12, 14, 20))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg


def png(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def sheet(rows):
    if not rows or not rows[0]:
        raise ValueError("Empty contact sheet")
    w, h = 352, 198
    result = Image.new("RGB", (max(map(len, rows))*w, len(rows)*(h+24)), (17,20,27))
    draw = ImageDraw.Draw(result)
    for ri, row in enumerate(rows):
        for ci, (label, sample) in enumerate(row):
            x, y = ci*w, ri*(h+24)
            result.paste(viewport_image(sample).resize((w,h), Image.Resampling.LANCZOS),(x,y+24))
            draw.text((x+9,y+5), label, fill=(237,226,199))
    return result
