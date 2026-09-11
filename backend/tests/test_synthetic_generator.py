from PIL import Image
from app.utils.synthetic_generator import SyntheticDocumentGenerator


def test_pasted_photo_is_feathered_at_the_border():
    """
    A hard-edged `img.paste(photo, (x, y))` leaves a sharp tonal
    discontinuity at the photo's border -- structurally the same signature
    as a real crop-and-replace forgery, which a tamper-detection model
    trained on real forgery examples is specifically built to catch (see
    scripts/train_tamper_cnn.py's SIDTD caution note). The paste must blend
    into the surrounding background at its edge rather than butt a hard
    rectangle against it.
    """
    background_color = (248, 250, 252)
    photo_color = (10, 10, 10)  # deliberately far from the background color

    canvas = Image.new("RGB", (400, 400), color=background_color)
    photo = Image.new("RGB", (300, 300), color=photo_color)
    photo_path = "/tmp/test_paste_feather_photo.png"
    photo.save(photo_path)

    SyntheticDocumentGenerator._paste_photo(canvas, photo_path, x=50, y=50, w=300, h=300)

    center_pixel = canvas.getpixel((200, 200))
    corner_pixel = canvas.getpixel((50, 50))

    # Center of the pasted box should closely match the photo.
    assert all(abs(c - p) < 15 for c, p in zip(center_pixel, photo_color))
    # The very corner (the hard edge of the old implementation) must be
    # blended -- neither pure photo nor pure background -- proving the
    # feather actually softened the boundary.
    assert corner_pixel != photo_color
    assert corner_pixel != background_color
