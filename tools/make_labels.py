"""Generates the box artwork (sprayed stencils, shipping label, barcode, QR, handling marks) as transparent PNGs.

Run with Pillow, qrcode and python-barcode installed:  python make_labels.py
Writes factory/textures/label_{side,end}_{0,1,2}.png and label_top.png. Each image maps onto one face of the
steel cover (1.30 m wide x 1.28 m tall; the top is 1.30 x 1.30). The QR code is decoration only.
"""
import os, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
import qrcode
import barcode
from barcode.writer import ImageWriter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'factory', 'textures')
SUP = '/System/Library/Fonts/Supplemental/'
STENCIL = SUP + 'DIN Condensed Bold.ttf'
BOLD = SUP + 'Arial Bold.ttf'
REG = '/System/Library/Fonts/Helvetica.ttc'
MONO = SUP + 'Courier New Bold.ttf'
N = 2048
INK = (22, 22, 24)
PERI = (154, 168, 255)
BRIDGED = set('ABDOPQR04689')


def font(path, size):
    return ImageFont.truetype(path, size)


def noise_mask(size, scale, seed, lo, hi):
    """Soft random blotches: 255 = keep, 0 = worn away."""
    rnd = random.Random(seed)
    w, h = size
    small = Image.new('L', (max(2, w // scale), max(2, h // scale)))
    small.putdata([rnd.randint(0, 255) for _ in range(small.size[0] * small.size[1])])
    m = small.resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(scale / 3))
    return m.point(lambda v: 0 if v < lo else 255 if v > hi else int((v - lo) * 255 / (hi - lo)))


def stencil_text(mask, xy, text, size, spacing=0.06):
    """Draw text into an L mask with stencil bridges cut through the closed letters."""
    d = ImageDraw.Draw(mask)
    f = font(STENCIL, size)
    x, y = xy
    for ch in text:
        if ch == ' ':
            x += int(size * 0.28)
            continue
        bb = d.textbbox((x, y), ch, font=f)
        d.text((x, y), ch, font=f, fill=255)
        if ch in BRIDGED:
            cx = (bb[0] + bb[2]) // 2
            bw = max(3, size // 28)
            d.rectangle((cx - bw, bb[1] - 2, cx + bw, bb[3] + 2), fill=0)
        x = bb[2] + int(size * spacing)
    return x


def fit(text, maxw, size):
    while size > 20 and text_width(text, size) > maxw:
        size -= 8
    return size


def text_width(text, size, spacing=0.06):
    m = Image.new('L', (8000, size * 2))
    return stencil_text(m, (0, 0), text, size, spacing)


def spray(img, mask, color, seed, wear=(35, 85), opacity=235):
    """Composite a stencil mask as sprayed paint: soft overspray halo, speckle, worn patches."""
    halo = mask.filter(ImageFilter.GaussianBlur(5)).point(lambda v: v * 0.35)
    core = mask.filter(ImageFilter.GaussianBlur(0.8))
    a = ImageChops.lighter(core, halo.convert('L'))
    rnd = random.Random(seed)
    speck = Image.new('L', mask.size)
    sd = ImageDraw.Draw(speck)
    grow = mask.filter(ImageFilter.MaxFilter(15))
    gw, gh = mask.size
    px = grow.load()
    for _ in range(9000):
        x, y = rnd.randrange(gw), rnd.randrange(gh)
        if px[x, y] > 0:
            r = rnd.choice((1, 1, 1, 2))
            sd.ellipse((x - r, y - r, x + r, y + r), fill=rnd.randint(60, 200))
    a = ImageChops.lighter(a, speck)
    a = ImageChops.multiply(a, noise_mask(mask.size, 40, seed + 1, *wear))
    a = a.point(lambda v: v * opacity // 255)
    layer = Image.new('RGBA', mask.size, (*color, 0))
    layer.putalpha(a)
    img.alpha_composite(layer)


def handling_marks(img, x, y, s):
    """This-way-up arrows, fragile glass, keep dry: painted black pictograms in a box."""
    m = Image.new('L', img.size)
    d = ImageDraw.Draw(m)
    w = int(s * 3.4)
    d.rectangle((x, y, x + w, y + s), outline=255, width=max(4, s // 30))
    # arrows
    for k in range(2):
        ax = x + int(s * 0.22) + k * int(s * 0.38)
        d.rectangle((ax + s * 0.1, y + s * 0.42, ax + s * 0.2, y + s * 0.85), fill=255)
        d.polygon([(ax, y + s * 0.45), (ax + s * 0.15, y + s * 0.13), (ax + s * 0.3, y + s * 0.45)], fill=255)
        d.rectangle((ax - s * 0.02, y + s * 0.87, ax + s * 0.32, y + s * 0.92), fill=255)
    # wine glass
    gx = x + int(s * 1.35)
    d.chord((gx, y + s * 0.12, gx + s * 0.5, y + s * 0.62), 0, 180, fill=255)
    d.rectangle((gx, y + s * 0.12, gx + s * 0.5, y + s * 0.36), fill=255)
    d.rectangle((gx + s * 0.22, y + s * 0.6, gx + s * 0.28, y + s * 0.82), fill=255)
    d.rectangle((gx + s * 0.08, y + s * 0.82, gx + s * 0.42, y + s * 0.88), fill=255)
    d.line((gx + s * 0.32, y + s * 0.14, gx + s * 0.22, y + s * 0.3, gx + s * 0.3, y + s * 0.38), fill=0, width=max(3, s // 40))
    # umbrella with rain
    ux = x + int(s * 2.25)
    d.chord((ux, y + s * 0.3, ux + s * 0.8, y + s * 0.9), 180, 360, fill=255)
    d.rectangle((ux + s * 0.38, y + s * 0.58, ux + s * 0.43, y + s * 0.86), fill=255)
    d.arc((ux + s * 0.22, y + s * 0.76, ux + s * 0.43, y + s * 0.94), 0, 180, fill=255, width=max(3, s // 40))
    for k in range(4):
        rx = ux + s * (0.1 + k * 0.2)
        d.line((rx, y + s * 0.08, rx - s * 0.04, y + s * 0.22), fill=255, width=max(3, s // 45))
    return m


def code128(data, w, h):
    bc = barcode.get('code128', data, writer=ImageWriter())
    im = bc.render({'module_height': 12.0, 'quiet_zone': 1.0, 'write_text': False, 'dpi': 300})
    bb = ImageChops.invert(im.convert('L')).getbbox()
    return im.convert('L').crop(bb).resize((w, h), Image.NEAREST)


def qr(data, s):
    q = qrcode.QRCode(border=0, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(data)
    q.make(fit=True)
    return q.make_image(fill_color='black', back_color='white').convert('L').resize((s, s), Image.NEAREST)


def shipping_label(w, h, lot, seed, big=False):
    rnd = random.Random(seed)
    lab = Image.new('RGBA', (w, h), (238, 234, 222, 255))
    d = ImageDraw.Draw(lab)
    pad = int(w * 0.05)
    lw = max(3, w // 160)
    d.rectangle((0, 0, w - 1, h - 1), outline=(30, 30, 30), width=lw)
    y = pad
    d.text((pad, y), "GRUNERT LABS", font=font(BOLD, int(w * 0.085)), fill=(15, 15, 15))
    y += int(w * 0.1)
    d.text((pad, y), "SOFTWARE FACTORY  /  LINE 05", font=font(REG, int(w * 0.045)), fill=(30, 30, 30))
    y += int(w * 0.07)
    d.line((pad, y, w - pad, y), fill=(20, 20, 20), width=lw)
    y += int(w * 0.03)
    small, mid = font(REG, int(w * 0.038)), font(BOLD, int(w * 0.06))
    d.text((pad, y), "SHIP TO", font=small, fill=(40, 40, 40))
    y += int(w * 0.05)
    d.text((pad, y), "DEPLOYED & MONITORED", font=mid, fill=(10, 10, 10))
    y += int(w * 0.075)
    d.text((pad, y), "ZONE 06  -  BAY 3  -  DOCK EAST", font=small, fill=(30, 30, 30))
    y += int(w * 0.07)
    d.line((pad, y, w - pad, y), fill=(20, 20, 20), width=lw)
    y += int(w * 0.03)
    d.text((pad, y), "CONTENTS: FEATURE SET  (1)", font=small, fill=(20, 20, 20))
    y += int(w * 0.055)
    d.text((pad, y), f"GROSS {rnd.uniform(38, 49):.1f} KG     PCS 1/1", font=small, fill=(20, 20, 20))
    y += int(w * 0.055)
    d.text((pad, y), f"LOT {lot}", font=font(MONO, int(w * 0.05)), fill=(10, 10, 10))
    y += int(w * 0.08)
    bh = int(h * (0.2 if big else 0.16))
    bc = code128(f"GL{lot.replace('-', '')}", w - 2 * pad, bh)
    lab.paste(Image.merge('RGBA', (bc, bc, bc, Image.new('L', bc.size, 255))), (pad, y))
    y += bh + int(w * 0.015)
    d.text((pad, y), f"(00) 0 0614 {lot[-4:]} {rnd.randint(10000, 99999)} 7", font=font(MONO, int(w * 0.042)), fill=(10, 10, 10))
    y += int(w * 0.075)
    qs = min(int(w * 0.32), h - y - pad)
    if qs > 40:
        q = qr(f"GL-SF-{lot}-{rnd.randint(1000, 9999)}", qs)
        lab.paste(Image.merge('RGBA', (q, q, q, Image.new('L', q.size, 255))), (w - pad - qs, y))
        tf = font(BOLD, int(w * 0.05))
        d.text((pad, y + int(qs * 0.05)), "HANDLE WITH", font=tf, fill=(150, 20, 20))
        d.text((pad, y + int(qs * 0.05) + int(w * 0.065)), "CARE:", font=tf, fill=(150, 20, 20))
        d.text((pad, y + int(qs * 0.05) + int(w * 0.13)), "IDEA INSIDE", font=tf, fill=(150, 20, 20))
    # paper wear: dirty edges, scuffs, slight yellowing
    grime = noise_mask((w, h), 18, seed + 7, 120, 230)
    dirt = Image.new('RGBA', (w, h), (120, 105, 80, 0))
    dirt.putalpha(ImageChops.invert(grime).point(lambda v: v * 55 // 255))
    lab.alpha_composite(dirt)
    return lab


def paste_label(img, lab, x, y, angle):
    lab = lab.rotate(angle, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(lab, (x, y))


def side(variant):
    rnd = random.Random(100 + variant)
    lot = f"2026-1109-{417 + variant * 23:04d}"
    img = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    # periwinkle painted band across the top (masked with tape: crisp edges, worn)
    band = Image.new('L', (N, N))
    ImageDraw.Draw(band).rectangle((0, 250, N, 300), fill=255)
    spray(img, band, PERI, 11 + variant, wear=(40, 90), opacity=220)
    # SOFTWARE PACKAGE
    sz = fit("SOFTWARE PACKAGE", 1760, 300)
    tw = text_width("SOFTWARE PACKAGE", sz)
    m = Image.new('L', (N, N))
    stencil_text(m, ((N - tw) // 2, 430), "SOFTWARE PACKAGE", sz)
    spray(img, m, INK, 20 + variant)
    m = Image.new('L', (N, N))
    x = stencil_text(m, ((N - tw) // 2 + 6, 760), "FEATURE SET", 150)
    stencil_text(m, (x + 70, 760), f"NO. {417 + variant * 23:04d}", 150)
    spray(img, m, INK, 30 + variant, wear=(20, 60))
    # handling marks, lower left
    spray(img, handling_marks(img, 150, 1240, 260), INK, 40 + variant, wear=(20, 60))
    # shipping label, lower right, slightly crooked
    paste_label(img, shipping_label(560, 760, lot, 50 + variant), 1320, 1080, rnd.uniform(-2.5, 2.5))
    return img


def end(variant):
    rnd = random.Random(200 + variant)
    lot = f"2026-1109-{417 + variant * 23:04d}"
    img = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    m = Image.new('L', (N, N))
    tw = text_width("FEATURE SET", 330)
    stencil_text(m, ((N - tw) // 2, 330), "FEATURE SET", 330)
    spray(img, m, INK, 60 + variant)
    m = Image.new('L', (N, N))
    tw = text_width("THIS SIDE UP", 120)
    stencil_text(m, ((N - tw) // 2, 760), "THIS SIDE UP", 120)
    spray(img, m, INK, 70 + variant, wear=(15, 50))
    paste_label(img, shipping_label(720, 940, lot, 80 + variant, big=True), 1100, 960, rnd.uniform(-1.5, 1.5))
    spray(img, handling_marks(img, 140, 1500, 230), INK, 90 + variant, wear=(20, 60))
    return img


def top():
    img = Image.new('RGBA', (N, N), (0, 0, 0, 0))
    m = Image.new('L', (N, N))
    d = ImageDraw.Draw(m)
    # lift points where the vacuum gripper's four cups land (0.46 m from the centre)
    c = N // 2
    r_off = int(0.46 / 1.30 * N)
    for (dx, dy) in ((r_off, 0), (-r_off, 0), (0, r_off), (0, -r_off)):
        cx, cy = c + dx, c + dy
        d.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), outline=255, width=10)
        d.line((cx - 95, cy, cx + 95, cy), fill=255, width=6)
        d.line((cx, cy - 95, cx, cy + 95), fill=255, width=6)
    spray(img, m, INK, 300, wear=(50, 100))
    m = Image.new('L', (N, N))
    for k, (txt, sz, yy) in enumerate((("SOFTWARE", 250, 430), ("PACKAGE", 250, 1310))):
        tw = text_width(txt, sz)
        stencil_text(m, ((N - tw) // 2, yy), txt, sz)
    spray(img, m, INK, 310)
    m = Image.new('L', (N, N))
    tw = text_width("LIFT POINTS  -  VACUUM ONLY", 80)
    stencil_text(m, ((N - tw) // 2, 1890), "LIFT POINTS  -  VACUUM ONLY", 80)
    spray(img, m, INK, 320, wear=(15, 50))
    return img


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for v in range(3):
        side(v).save(os.path.join(OUT, f"label_side_{v}.png"), optimize=True)
        end(v).save(os.path.join(OUT, f"label_end_{v}.png"), optimize=True)
    top().save(os.path.join(OUT, "label_top.png"), optimize=True)
    print("LABELS_DONE", sorted(os.listdir(OUT)))
