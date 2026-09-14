from aqua_map_address import format_geocode_results, normalize_persian_address


def test_persian_address_normalization_variants():
    expected = "مرزداران گلستان 15"
    for value in ("مرزداران گلستان ۱۵", "مرزداران گلستان ١٥", "مرزداران  گلستان۱۵",
                  "مرزداران گلستان پانزده", "مرزداران گلستان پونزده"):
        assert normalize_persian_address(value) == expected


def test_provider_results_are_real_bounded_and_have_no_fake_confidence():
    fixture = [{"display_name": f"گلستان {i}, مرزداران, تهران", "lat": "35.7", "lon": f"51.{i}"} for i in range(5)]
    rows = format_geocode_results(fixture, str, 3)
    assert len(rows) == 3
    assert rows[0]["latitude"] == 35.7
    assert all("confidence" not in row for row in rows)
