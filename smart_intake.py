import re
from dataclasses import dataclass, asdict
from typing import Optional

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(value: str) -> str:
    return (value or "").translate(PERSIAN_DIGITS)


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def parse_money(value: str) -> Optional[int]:
    if not value:
        return None
    normalized = normalize_digits(value)
    digits = re.sub(r"[^0-9]", "", normalized)
    return int(digits) if digits else None


@dataclass
class IntakeResult:
    last_name: Optional[str] = None
    phones: list[str] = None
    address: Optional[str] = None
    visitor_code: Optional[str] = None
    service_type: Optional[str] = None
    amount: Optional[int] = None
    time_text: Optional[str] = None
    raw_text: Optional[str] = None

    def to_dict(self):
        data = asdict(self)
        data["phones"] = self.phones or []
        return data


SERVICE_WORDS = (
    "فیلتر", "یخچال", "تصفیه", "دستگاه", "سرویس", "نصب", "تعویض", "تعمیر"
)
ADDRESS_HINTS = (
    "خیابان", "خ ", "کوچه", "کوی", "شهرک", "بلوار", "میدان", "پلاک", "پ ",
    "واحد", "طبقه", "آریا", "صادقیه", "تهران", "کرج", "ولنجک", "کاشانی"
)
TIME_HINTS = ("شنبه", "یکشنبه", "دوشنبه", "سه شنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "الی", "ساعت")


def parse_intake(text: str) -> dict:
    raw = text or ""
    normalized = normalize_digits(raw)
    lines = [normalize_spaces(x) for x in normalized.splitlines() if normalize_spaces(x)]

    phones = []
    for match in re.findall(r"(?<!\d)(?:\+98|0098|98|0)?9\d{9}(?!\d)", normalized):
        phone = match
        if phone.startswith("0098"):
            phone = "0" + phone[4:]
        elif phone.startswith("+98"):
            phone = "0" + phone[3:]
        elif phone.startswith("98") and len(phone) == 12:
            phone = "0" + phone[2:]
        if phone not in phones:
            phones.append(phone)

    amount = None
    money_match = re.search(r"(?:دریافتی|مبلغ|گرفتم|پرداخت)\s*[:：]?\s*([0-9۰-۹٠-٩][0-9۰-۹٠-٩/.,٬،\s]{2,})", raw, re.I)
    if money_match:
        amount = parse_money(money_match.group(1))

    service_type = next((line for line in lines if any(word in line for word in SERVICE_WORDS) and not re.search(r"09\d{9}", line)), None)
    time_text = next((line for line in lines if any(hint in line for hint in TIME_HINTS)), None)

    visitor_code = None
    for line in reversed(lines):
        if re.fullmatch(r"[\wآ-ی‌\-]+\s*\d+", line) and not re.search(r"09\d{9}", line):
            if not any(hint in line for hint in ADDRESS_HINTS):
                visitor_code = line.replace(" ", "")
                break

    last_name = None
    for line in lines:
        scrubbed = line
        for p in phones:
            scrubbed = scrubbed.replace(p, "")
        scrubbed = normalize_spaces(scrubbed)
        if not scrubbed:
            continue
        if line == time_text or line == service_type or line == visitor_code:
            continue
        if any(hint in line for hint in ADDRESS_HINTS):
            continue
        if len(scrubbed.split()) <= 3 and re.fullmatch(r"[آ-ی‌\- ]+", scrubbed):
            last_name = scrubbed
            break

    address_lines = []
    for line in lines:
        if line in (time_text, service_type, visitor_code):
            continue
        if line == last_name or re.fullmatch(r"09\d{9}", line):
            continue
        if any(hint in line for hint in ADDRESS_HINTS):
            address_lines.append(line)
        elif address_lines and not re.search(r"09\d{9}", line) and line != visitor_code:
            address_lines.append(line)

    result = IntakeResult(
        last_name=last_name,
        phones=phones,
        address=normalize_spaces(" ".join(address_lines)) or None,
        visitor_code=visitor_code,
        service_type=service_type,
        amount=amount,
        time_text=time_text,
        raw_text=raw,
    )
    return result.to_dict()
