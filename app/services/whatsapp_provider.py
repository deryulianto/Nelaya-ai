# app/services/whatsapp_provider.py
import os

WA_PROVIDER = os.getenv("WA_PROVIDER", "mock")  # mock | prod
WA_DEV_SHOW_OTP = os.getenv("WA_DEV_SHOW_OTP", "1") == "1"

def send_whatsapp_otp(phone_e164: str, otp: str) -> None:
    """
    v0: mock provider. In production, replace with official WhatsApp API provider.
    """
    if WA_PROVIDER == "mock":
        if WA_DEV_SHOW_OTP:
            print(f"[WA-MOCK] Send OTP to {phone_e164}: {otp}")
        else:
            print(f"[WA-MOCK] Send OTP to {phone_e164}: (hidden)")
        return

    # Placeholder for production provider:
    # - call WhatsApp Business API / provider SDK
    raise RuntimeError("WA_PROVIDER=prod not implemented yet")
