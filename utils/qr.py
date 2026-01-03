"""QR code generation utilities."""

from __future__ import annotations

import io

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

from telegram import InputFile


def generate_qr_image(data: str) -> io.BytesIO | None:
    """
    Generate QR code image from data string.
    Returns BytesIO buffer containing PNG image, or None if qrcode library not available.
    """
    if not QR_AVAILABLE:
        return None

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def send_qr_code(update_or_message, qr_data: str, caption: str | None = None) -> None:
    """
    Send QR code image to user.
    Args:
        update_or_message: Telegram Update or Message object
        qr_data: Data to encode in QR code
        caption: Optional caption for the image
    """
    qr_buf = generate_qr_image(qr_data)
    if not qr_buf:
        # Fallback: send text if QR library not available
        reply_method = update_or_message.reply_text if hasattr(update_or_message, "reply_text") else update_or_message.message.reply_text
        await reply_method(f"📱 QR Code data:\n\n`{qr_data}`", parse_mode="Markdown")
        return

    qr_file = InputFile(qr_buf, filename="qr.png")
    if hasattr(update_or_message, "message"):
        # Update object
        await update_or_message.message.reply_photo(qr_file, caption=caption)
    elif hasattr(update_or_message, "reply_photo"):
        # Message object
        await update_or_message.reply_photo(qr_file, caption=caption)
    else:
        # Fallback
        reply_method = update_or_message.reply_text if hasattr(update_or_message, "reply_text") else None
        if reply_method:
            await reply_method(f"📱 QR Code:\n\n`{qr_data}`", parse_mode="Markdown")


