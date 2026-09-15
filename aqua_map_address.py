"""Pure Persian address normalization shared by map and Aria flows."""

import re


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
NUMBER_WORDS = {"پانزده": "15", "پونزده": "15"}


def normalize_persian_address(value):
    value = str(value or "").translate(DIGITS).replace("ي", "ی").replace("ك", "ک")
    value = value.replace("\u200c", " ")
    for word, number in NUMBER_WORDS.items():
        value = re.sub(rf"(?<!\S){word}(?!\S)", number, value)
    value = re.sub(r"(?<=[\u0600-\u06ff])(?=\d)|(?<=\d)(?=[\u0600-\u06ff])", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def format_geocode_results(raw, validator, limit=3):
    """Convert provider rows without synthesizing coordinates or confidence."""
    rows = []
    for index, item in enumerate(raw[: min(max(limit, 1), 3)]):
        if not item.get("lat") or not item.get("lon"):
            continue
        address = validator(item.get("display_name"))
        title = str(item.get("name") or address or "نشانی").split(",", 1)[0]
        rows.append({"id": f"address-{index}", "kind": "address", "title": title, "name": title,
                     "formatted_address": address, "address": address,
                     "latitude": float(item["lat"]), "longitude": float(item["lon"]),
                     "type": item.get("type")})
    return rows



NON_ADDRESS_TOPIC = re.compile(r"هوا|اخبار|خبر|قیمت|طلا|دلار|مشتری|فروش|هزینه|درآمد|چطوره|چگونه|چرا|چقدر|چه خبر")
ADDRESS_CUE = re.compile(r"خیابان|خیابون|کوچه|بلوار|میدان|بزرگراه|اتوبان|محله|پلاک|بن بست|مرزداران|صادقیه|آریاشهر|پونک|ستارخان|یوسف آباد|سعادت آباد|تهرانسر|فردیس|کرج|تهران")


def address_result_matches(query, item):
    """Require address terms, including exact street numbers, in provider text."""
    query = normalize_persian_address(query).replace("خیابون", "خیابان")
    stop = {"خیابان", "کوچه", "بلوار", "محله", "پلاک", "آدرس", "میدان", "بزرگراه", "اتوبان", "توی", "در", "به", "از", "شهر", "استان"}
    terms = [term for term in re.findall(r"[^\W_]+", query) if term not in stop]
    found = normalize_persian_address(" ".join(str(item.get(key) or "") for key in ("title", "name", "formatted_address", "address", "region")))
    numbers = re.findall(r"\d+", found)
    return bool(terms) and all(term in numbers if term.isdigit() else term in found for term in terms)
