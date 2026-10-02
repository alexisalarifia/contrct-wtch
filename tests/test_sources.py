from sources import sam, sbir


def test_sbir_normalize():
    a = sbir.normalize({"firm": "Tiny Rockets LLC", "award_title": "Additive turbopump", "abstract": "We 3D print inconel turbopumps.",
                        "agency": "DOD", "branch": "USAF", "phase": "I", "program": "SBIR", "award_amount": "150000", "award_year": 2026, "contract": "FA8649-26-P-0001", "uei": "U1"})
    assert a["source"] == "sbir" and a["amount"] == 150000.0 and a["award_id"] == "FA8649-26-P-0001"
    assert "inconel" in a["description"]


def test_sam_normalize_and_skip_without_key(monkeypatch):
    o = sam.normalize({"noticeId": "n1", "title": "Sources Sought: cislunar SDA", "department": "DOD", "type": "Sources Sought",
                       "postedDate": "2026-09-01", "responseDeadLine": "2026-10-01", "naicsCode": "336414", "classificationCode": "AC13", "uiLink": "https://sam.gov/opp/n1"})
    assert o["notice_id"] == "n1" and o["naics"] == "336414"
    monkeypatch.setattr(sam.config, "SAM_API_KEY", None)
    assert sam.fetch() == []
