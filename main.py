from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers import CircleModuleDrawer
import io
import os

app = FastAPI()


class SpacedCircleDrawer(CircleModuleDrawer):
    def __init__(self, radius_ratio=0.50, **kwargs):
        super().__init__(**kwargs)
        self.radius_ratio = radius_ratio
        self.draw = None
        self.img = None
        self.box_size = None
        self.fill_color = (0, 0, 0)

    def initialize(self, img, **kwargs):
        self.img = img
        self.draw = ImageDraw.Draw(img._img)
        self.box_size = img.box_size
        self.fill_color = getattr(img, "foreground", (0, 0, 0))
        return super().initialize(img, **kwargs)

    def drawrect(self, box, is_active):
        if not is_active:
            return
        if isinstance(box[0], int):
            col, row = box
            size = self.box_size
            x = col * size + size / 2
            y = row * size + size / 2
            radius = size * self.radius_ratio
        else:
            (x1, y1), (x2, y2) = box
            size = min(x2 - x1, y2 - y1)
            x = (x1 + x2) / 2
            y = (y1 + y2) / 2
            radius = size * self.radius_ratio

        self.draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=self.fill_color,
        )


class QR:
    def __init__(self, url: str, text: str, logo_path: str = None):
        self.url = url
        self.text = text
        self.logo_path = logo_path

    def generate(self, radius_ratio=0.50):

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=12,
            border=4
        )
        qr.add_data(self.url)
        qr.make(fit=True)

        qr_img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=SpacedCircleDrawer(radius_ratio=radius_ratio),
            color_mask=SolidFillColorMask(
                back_color=(255, 255, 255),
                front_color=(0, 0, 0)
            )
        ).convert("RGBA")

        if self.logo_path:
            try:
                logo = Image.open(self.logo_path).convert("RGBA")
                qr_width, qr_height = qr_img.size
                logo_size = qr_width // 5
                logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

                mask = Image.new("L", (logo_size, logo_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, logo_size, logo_size), fill=255)

                circular_logo = Image.new("RGBA", (logo_size, logo_size), (0, 0, 0, 0))
                circular_logo.paste(logo, (0, 0), mask=mask)

                pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                qr_img.paste(circular_logo, pos, mask=circular_logo)
            except FileNotFoundError:
                print("Logo not found, skipping...")

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 60)
        except:
            font = ImageFont.load_default()

        dummy_img = Image.new("RGB", (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        bbox = dummy_draw.textbbox((0, 0), self.text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        qr_width, qr_height = qr_img.size
        new_img = Image.new("RGB", (qr_width, qr_height + text_height + 40), "white")
        draw = ImageDraw.Draw(new_img)

        text_x = (qr_width - text_width) // 2
        text_y = 10
        amber_color = (255, 191, 0)
        draw.text((text_x, text_y), self.text, font=font, fill=amber_color)

        new_img.paste(qr_img, (0, text_height + 40))

        pad = 20               
        border_thickness = 5    
        border_radius = 20    
        outer_margin = 10       

        final_w = new_img.width + 2 * (pad + outer_margin)
        final_h = new_img.height + 2 * (pad + outer_margin)
        final_img = Image.new("RGB", (final_w, final_h), "white")

        paste_x = outer_margin + pad
        paste_y = outer_margin + pad
        final_img.paste(new_img, (paste_x, paste_y))

        rect_left = outer_margin
        rect_top = outer_margin
        rect_right = outer_margin + new_img.width + 2 * pad - 1
        rect_bottom = outer_margin + new_img.height + 2 * pad - 1

        draw_final = ImageDraw.Draw(final_img)
        draw_final.rounded_rectangle(
            [(rect_left, rect_top), (rect_right, rect_bottom)],
            radius=border_radius,
            outline=amber_color,
            width=border_thickness
        )

        return final_img


@app.post("/generate_qr/")
async def generate_qr(
    url: str = Form(...),
    text: str = Form(...),
    logo: UploadFile = None
):
    logo_path = None
    if logo:
        logo_path = f"temp_{logo.filename}"
        with open(logo_path, "wb") as f:
            f.write(await logo.read())

    qr = QR(url, text, logo_path)
    img = qr.generate(radius_ratio=0.50)

    if logo_path and os.path.exists(logo_path):
        os.remove(logo_path)

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)

    return StreamingResponse(img_byte_arr, media_type="image/png")
