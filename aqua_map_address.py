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
