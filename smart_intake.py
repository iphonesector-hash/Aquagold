import re
from dataclasses import dataclass, asdict
from typing import Optional

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
PHONE_RE = re.compile(r"(?<!\d)(?:\+98|0098|98|0)?9\d{9}(?!\d)")
WEEKDAYS = ("شنبه","یکشنبه","دوشنبه","سه شنبه","سه‌شنبه","چهارشنبه","پنجشنبه","جمعه")
TIME_WORDS = WEEKDAYS + ("الی","ساعت","صبح","ظهر","عصر","شب","فردا","امروز")
SERVICE_MAP = {
    "ساید": "یخچال/ساید", "یخچال": "یخچال/ساید", "فریزر": "یخچال/ساید",
    "فیلتر": "فیلتر", "دستگاه": "دستگاه", "تصفیه": "دستگاه",
    "نصب": "نصب", "تعمیر": "تعمیر", "سرویس": "سرویس",
}
ADDRESS_HINTS = (
    "خیابان","خ ","خ.","کوچه","کوی","شهرک","بلوار","میدان","پلاک","پ ","پ.",
    "واحد","طبقه","اتوبان","بزرگراه","کرج","تهران","فردیس","آریاشهر","صادقیه","کاشانی",
    "جاده","میدون","فرعی","غربی","شرقی","شمالی","جنوبی","ویلایی","برج","مجتمع","شهر"
)


def normalize_digits(value: str) -> str:
    return (value or "").translate(PERSIAN_DIGITS)


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\u200c", " ")).strip()


def normalize_phone(value: str) -> str:
    p = normalize_digits(value)
    if p.startswith("0098"): p = "0" + p[4:]
    elif p.startswith("+98"): p = "0" + p[3:]
    elif p.startswith("98") and len(p) == 12: p = "0" + p[2:]
    return p


def parse_money(value: str) -> Optional[int]:
    digits = re.sub(r"[^0-9]", "", normalize_digits(value or ""))
    return int(digits) if digits else None


def _is_time(line: str) -> bool:
    if any(w in line for w in TIME_WORDS): return True
    return bool(re.fullmatch(r"\d{1,2}(?::\d{2})?\s*(?:تا|الی|-)\s*\d{1,2}(?::\d{2})?", line))


def _service(line: str):
    for token, label in SERVICE_MAP.items():
        if token in line and not PHONE_RE.search(line):
            return label
    return None


def _looks_address(line: str) -> bool:
    if any(h in line for h in ADDRESS_HINTS): return True
    return bool(re.search(r"(?:^|\s)(?:پ|پلاک|واحد|طبقه)\s*\d+", line))


def _name_from_phone_line(line: str, phones: list[str]) -> Optional[str]:
    scrubbed = normalize_digits(line)
    for p in phones:
        scrubbed = scrubbed.replace(p, "")
    scrubbed = PHONE_RE.sub(" ", scrubbed)
    scrubbed = re.sub(r"(?:آقا|خانم|مشتری|شماره|تلفن|موبایل)[:：]?", " ", scrubbed)
    scrubbed = normalize_spaces(scrubbed)
    words = re.findall(r"[آ-یA-Za-z‌\-]+", scrubbed)
    return " ".join(words[:4]).strip() or None


def _visitor_from_last(lines: list[str], excluded: set[int]) -> Optional[str]:
    for idx in range(len(lines)-1, -1, -1):
        if idx in excluded: continue
        line = lines[idx]
        if PHONE_RE.search(line) or _is_time(line) or _service(line) or _looks_address(line): continue
        # Visitor convention accepts both "سما ۳" and compact codes such as "مهمانی۳".
        if re.fullmatch(r"[آ-یA-Za-z‌\-]{2,}(?:\s*\d{1,3})?", line):
            return line
    return None


@dataclass
class IntakeResult:
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phones: list[str] = None
    address: Optional[str] = None
    visitor_code: Optional[str] = None
    service_type: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[int] = None
    time_text: Optional[str] = None
    raw_text: Optional[str] = None
    parser: str = "local-v8"

    def to_dict(self):
        data = asdict(self); data["phones"] = self.phones or []; return data


def parse_intake(text: str) -> dict:
    raw = text or ""
    normalized = normalize_digits(raw)
    lines = [normalize_spaces(x) for x in normalized.splitlines() if normalize_spaces(x)]
    phones = []
    for m in PHONE_RE.findall(normalized):
        p = normalize_phone(m)
        if p not in phones: phones.append(p)

    time_idx = next((i for i,l in enumerate(lines) if _is_time(l)), None)
    time_text = lines[time_idx] if time_idx is not None else None

    service_idx, service_type, service_line = None, None, None
    for i, line in enumerate(lines):
        label = _service(line)
        if label:
            service_idx, service_type, service_line = i, label, line
            break

    name_idx, last_name = None, None
    if phones:
        for i, line in enumerate(lines):
            if PHONE_RE.search(line):
                candidate = _name_from_phone_line(line, phones)
                if candidate:
                    name_idx, last_name = i, candidate
                    break

    excluded = {i for i in (time_idx, service_idx, name_idx) if i is not None}
    visitor_code = _visitor_from_last(lines, excluded)
    visitor_idx = next((i for i,l in enumerate(lines) if l == visitor_code), None) if visitor_code else None
    if visitor_idx is not None: excluded.add(visitor_idx)

    address_lines = []
    start = (name_idx + 1) if name_idx is not None else 0
    end = visitor_idx if visitor_idx is not None else len(lines)
    for i in range(start, end):
        if i in excluded: continue
        line = lines[i]
        if PHONE_RE.search(line): continue
        if _is_time(line) or _service(line): continue
        if name_idx is not None:
            address_lines.append(line)
        elif _looks_address(line) or address_lines:
            address_lines.append(line)
    if not address_lines:
        address_lines = [l for i,l in enumerate(lines) if i not in excluded and not PHONE_RE.search(l) and _looks_address(l)]

    amount = None
    money_match = re.search(r"(?:دریافتی|مبلغ|گرفتم|پرداخت)\s*[:：]?\s*([0-9۰-۹٠-٩][0-9۰-۹٠-٩/.,٬،\s]{2,})", raw, re.I)
    if money_match: amount = parse_money(money_match.group(1))

    description_bits = []
    if service_line and service_line != service_type: description_bits.append(service_line)

    return IntakeResult(
        first_name=None,
        last_name=last_name,
        phones=phones,
        address=normalize_spaces("، ".join(address_lines)) or None,
        visitor_code=visitor_code,
        service_type=service_type,
        description="، ".join(description_bits) or service_line,
        amount=amount,
        time_text=time_text,
        raw_text=raw,
    ).to_dict()
