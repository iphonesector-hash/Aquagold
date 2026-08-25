"""Small, strict validation helpers shared by AquaGold API modules."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo


DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
IRAN_MOBILE = re.compile(r"^09\d{9}$")


class ValidationError(ValueError):
    pass


def text(value, label, *, required=False, max_length=500):
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not cleaned:
        raise ValidationError(f"{label} الزامی است")
    if len(cleaned) > max_length:
        raise ValidationError(f"{label} نباید بیشتر از {max_length} نویسه باشد")
    return cleaned or None


def phone(value):
    raw = str(value or "").translate(DIGIT_TRANS)
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0098") and len(digits) == 14:
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    if not IRAN_MOBILE.fullmatch(digits):
        raise ValidationError("شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود")
    return digits


def phones(values, *, maximum=5):
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValidationError("شماره‌ها باید به صورت فهرست ارسال شوند")
    if len(values) > maximum:
        raise ValidationError(f"حداکثر {maximum} شماره برای هر مشتری مجاز است")
    result = []
    for value in values:
        if value in (None, ""):
            continue
        cleaned = phone(value)
        if cleaned not in result:
            result.append(cleaned)
    return result


def integer(value, label, *, minimum=0, maximum=10**15, default=None):
    if value in (None, ""):
        if default is not None:
            return default
        raise ValidationError(f"{label} الزامی است")
    raw = str(value).translate(DIGIT_TRANS)
    raw = re.sub(r"[٬،,\s]", "", raw)
    if not re.fullmatch(r"-?\d+", raw):
        raise ValidationError(f"{label} باید عدد صحیح باشد")
    number = int(raw)
    if not minimum <= number <= maximum:
        raise ValidationError(f"{label} باید بین {minimum} و {maximum} باشد")
    return number


def decimal_number(value, label, *, minimum=0, maximum=100, default=None):
    if value in (None, ""):
        if default is not None:
            return Decimal(str(default))
        raise ValidationError(f"{label} الزامی است")
    try:
        result = Decimal(str(value).translate(DIGIT_TRANS))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{label} عدد معتبری نیست")
    if not result.is_finite() or not Decimal(str(minimum)) <= result <= Decimal(str(maximum)):
        raise ValidationError(f"{label} باید بین {minimum} و {maximum} باشد")
    return result


def choice(value, label, allowed, *, default=None):
    cleaned = str(value or default or "").strip()
    if cleaned not in allowed:
        raise ValidationError(f"{label} معتبر نیست")
    return cleaned


def uuid(value, label, *, required=True):
    if value in (None, "") and not required:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError(f"{label} معتبر نیست")


def timestamp(value, label, *, required=False):
    if value in (None, ""):
        if required:
            raise ValidationError(f"{label} الزامی است")
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        raise ValidationError(f"{label} باید تاریخ و زمان ISO معتبر باشد")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Tehran"))
    return parsed


def coordinates(latitude, longitude, *, required=False):
    if latitude in (None, "") and longitude in (None, "") and not required:
        return None, None
    try:
        lat, lng = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise ValidationError("مختصات معتبر لازم است")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValidationError("مختصات خارج از محدوده معتبر است")
    return lat, lng


def boolean(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if str(value).lower() in {"true", "1", "yes", "on"}:
        return True
    if str(value).lower() in {"false", "0", "no", "off"}:
        return False
    raise ValidationError("مقدار بله/خیر معتبر نیست")
