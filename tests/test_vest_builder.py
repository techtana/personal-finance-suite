"""RSU vest schedules from the Plan form's cliff + later-vest settings."""

from engine.vest_builder import build_vest_schedule


def _total(schedule):
    return sum(v["shares"] for v in schedule)


def test_plan_form_default_vests_the_whole_grant():
    # 25 % cliff then 2.0833 % monthly, sent by templates/plan.html as 208 bps: 25 % + 36 x 2.08 % = 99.88 %.
    s = build_vest_schedule("2026-01-15", 48000, 12, 2500, "monthly", 208)
    assert len(s) == 37
    assert s[0] == {"date": "2027-01-15", "shares": 12000}
    assert s[1] == {"date": "2027-02-15", "shares": 998}
    assert s[-1]["date"] == "2030-01-15"
    assert s[-1]["shares"] == 48000 - 12000 - 35 * 998  # the last vest takes the remainder
    assert _total(s) == 48000


def test_even_split_is_unchanged():
    s = build_vest_schedule("2026-01-15", 100000, 12, 2500, "quarterly", 625)
    assert len(s) == 13 and {v["shares"] for v in s[1:]} == {6250}
    assert s[-1]["date"] == "2030-01-15" and _total(s) == 100000


def test_uneven_percent_rounds_to_the_nearest_count_of_vests():
    s = build_vest_schedule("2026-01-01", 10000, 12, 2500, "monthly", 1000)  # 7.5 later vests -> 8
    assert len(s) == 9 and s[-1]["shares"] == 10000 - 2500 - 7 * 1000 and _total(s) == 10000


def test_month_end_grant_returns_to_the_31st_and_no_cliff_means_no_zero_vest():
    s = build_vest_schedule("2026-01-31", 48000, 1, 0, "monthly", 5000)
    assert s == [{"date": "2026-03-31", "shares": 24000}, {"date": "2026-04-30", "shares": 24000}]


def test_monthly_one_in_48_with_no_cliff():
    s = build_vest_schedule("2026-01-15", 48000, 0, 0, "monthly", 208)
    assert len(s) == 48 and s[0]["date"] == "2026-02-15" and s[-1]["date"] == "2030-01-15" and _total(s) == 48000


def test_full_cliff_needs_no_later_vests():
    assert build_vest_schedule("2026-01-15", 1000, 12, 10000, "monthly", 0) == [{"date": "2027-01-15", "shares": 1000}]


def test_settings_that_cant_make_a_schedule_give_nothing():
    assert build_vest_schedule("2026-01-15", 1000, 12, 2500, "monthly", 0) == []
    assert build_vest_schedule("2026-01-15", 1000, 12, 12000, "monthly", 208) == []
    assert build_vest_schedule("2026-01-15", 1000, 12, 2500, "yearly", 208) == []
    assert build_vest_schedule("", 1000, 12, 2500, "monthly", 208) == []


RSU = {"name": "Grant", "rule_type": "rsu", "start_date": "2026-01-15",
       "config": {"ticker": "ACME", "total_shares": 48000, "grant_date": "2026-01-15", "cliff_months": 12,
                  "cliff_percent": 2500, "subsequent_frequency": "monthly", "subsequent_percent": 208}}


def test_rules_api_saves_the_plan_form_default(client):
    res = client.post("/api/rules", json=RSU)
    assert res.status_code == 201
    assert sum(v["shares"] for v in res.get_json()["schedule"]) == 48000


def test_rules_api_refuses_settings_that_make_no_schedule(client):
    bad = {**RSU, "config": {**RSU["config"], "subsequent_percent": 0}}
    res = client.post("/api/rules", json=bad)
    assert res.status_code == 400 and "schedule" in res.get_json()["error"]
    assert client.get("/api/rules").get_json() == []

    rule_id = client.post("/api/rules", json=RSU).get_json()["id"]
    res = client.patch(f"/api/rules/{rule_id}", json={"config": bad["config"]})
    assert res.status_code == 400
    assert len(client.get("/api/rules").get_json()[0]["schedule"]) == 37  # the saved schedule is untouched

    preview = client.post("/api/rules/rsu-preview", json={"config": bad["config"]}).get_json()
    assert preview["schedule"] == [] and preview["error"]
