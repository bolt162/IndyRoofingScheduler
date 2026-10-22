"""
How many days a roof replacement should take, from the crew labor items on its Roofing work order.

Fit 2026-10-20 on 297 full roof replacements by the crews we still use (Faster, DCT, A&M, YRG, Alpha):
2026 JobNimbus work orders plus 2025 AccuLynx labor orders. Commercial jobs and repairs left out.
It picks the right number of days 87% of the time and catches 83% of the builds that took 2+ days
(86% / 81% on jobs it wasn't fit on).

  effective squares = squares x pitch factor x 1.1 if 2+ stories
                      + 6 if an extra layer comes off + 6 per skylight (max 3)
                      + 4 if trim is cut in + 4 if more than 20 sheets of decking
  A&M (a 4-person crew) x 1.4
  under 58 = 1 day, 58 to 119 = 2 days, 120+ = 3 days

The scheduler can always change it (a crew adding people, a note saying otherwise).
"""
PITCH = [("mansard", 2.0, "mansard"), ("12/12", 1.6, "12/12 or steeper"), ("13/12", 1.6, "12/12 or steeper"),
         ("10/12", 1.35, "10-11/12 pitch"), ("8/12", 1.15, "8-9/12 pitch")]
TWO_DAYS, THREE_DAYS = 58, 120
SLOW_CREWS = {"a&m": 1.4}


def _items(work_order: dict) -> list[tuple[str, float]]:
    return [((n or "").strip().lower(), float(q or 0)) for n, q in work_order.get("labor") or []]


def roofing_work_order(work_orders: list[dict] | None) -> dict | None:
    """The Roofing work order with the tear-off line (the one the crew builds from)."""
    for w in work_orders or []:
        if (w.get("trade") or "").lower() == "roofing" and any("tear off and install" in n for n, _ in _items(w)):
            return w
    return None


def estimate(work_orders: list[dict] | None, squares_fallback: float | None = None) -> dict | None:
    """{eff, squares, why: [...]} for the job, or None when there's nothing to go on."""
    wo = roofing_work_order(work_orders)
    if not wo:
        if squares_fallback:
            return {"eff": float(squares_fallback), "squares": float(squares_fallback),
                    "why": [f"{squares_fallback:.0f} squares (no work order yet)"]}
        return None
    items = _items(wo)
    sq = sum(q for n, q in items if "tear off and install" in n)
    factor, pitch_word = 1.0, None
    for key, f, word in PITCH:
        if any(key in n and ("steep" in n or "mansard" in n) for n, _ in items) and f > factor:
            factor, pitch_word = f, word
    stories = 3 if any("3rd story" in n for n, _ in items) else 2 if any(
        "2 story" in n or "2-story" in n for n, _ in items) else 1
    layers = any("extra layer" in n or "additional layer" in n for n, _ in items)
    skylights = int(sum(q or 1 for n, q in items if "skylight" in n))
    trim = any("trim" in n for n, _ in items)
    decking = sum(q for n, q in items if "osb" in n and n.startswith("install"))

    eff = sq * factor * (1.1 if stories >= 2 else 1.0)
    eff += (6 if layers else 0) + 6 * min(skylights, 3) + (4 if trim else 0) + (4 if decking > 20 else 0)
    why = [f"{sq:.0f} squares"]
    if pitch_word:
        why.append(pitch_word)
    if stories >= 2:
        why.append(f"{stories} story")
    if layers:
        why.append("extra layer to tear off")
    if skylights:
        why.append(f"{skylights} skylight{'s' if skylights > 1 else ''}")
    if trim:
        why.append("trim cut-in")
    if decking > 20:
        why.append(f"{decking:.0f} sheets of decking")
    return {"eff": round(eff, 1), "squares": sq, "why": why}


def siding_days(work_orders: list[dict] | None) -> int | None:
    """Days for the siding, from the labor lines on the job's Siding work orders (all of them; two can be one build).

    Fit 2026-10-22 on 22 Leon Leon jobs (actual days from crew photo dates): exact on 14, never off by more
    than a day. Work order dates as Greg sets them were exact on 7. Story count isn't on the labor lines.
      effective = siding squares + soffit/fascia feet / 30
      under 12 = 1 day, 12 to 17 = 2, 18 to 27 = 3, 28+ = 4 (anything past ~300 ft of soffit/fascia: look at it)
    """
    squares = feet = 0.0
    found = False
    for w in work_orders or []:
        if (w.get("trade") or "").strip().lower() != "siding":
            continue
        for n, q in _items(w):
            if (any(k in n for k in ("siding", "board & batten", "board &amp; batten", "shake"))
                    and any(k in n for k in ("install", "replace")) and "repair" not in n):
                squares += q
                found = True
            elif ("soffit" in n or "fascia" in n) and "vent" not in n and "paint" not in n:
                feet += q
    if not found:
        return None
    eff = squares + feet / 30
    return 1 if eff < 12 else 2 if eff < 18 else 3 if eff < 28 else 4


def days_for(eff: float | None, crew_name: str | None = None) -> int | None:
    if eff is None:
        return None
    crew = (crew_name or "").lower()
    for key, slow in SLOW_CREWS.items():
        if key in crew:
            eff *= slow
    return 1 if eff < TWO_DAYS else 2 if eff < THREE_DAYS else 3


SET_BY_PERSON = "Set by "


def apply_to_job(job) -> None:
    """Use the work order's suggestion as the job's build days, unless a person set them by hand."""
    if (getattr(job, "primary_trade", None) or "") == "siding" and not (job.duration_source or "").startswith(SET_BY_PERSON):
        days = siding_days(getattr(job, "jn_work_orders", None))
        if days:
            job.duration_days, job.duration_confirmed = days, True
            job.duration_source = "Siding work order (squares + soffit/fascia)"
        return
    est = job.days_estimate if isinstance(getattr(job, "days_estimate", None), dict) else None
    if not est or (job.duration_source or "").startswith(SET_BY_PERSON):
        return
    job.duration_days = days_for(est.get("eff")) or job.duration_days
    job.duration_confirmed = True
    job.duration_source = f"Work order: {', '.join(est.get('why') or [])}"[:255]


def suggestion(job, crew_name: str | None = None) -> dict | None:
    """{days, why} shown on the Weekly Plan card. Uses the crew picked for the job when there is one."""
    est = job.days_estimate if isinstance(getattr(job, "days_estimate", None), dict) else None
    if not est:
        return None
    days = days_for(est.get("eff"), crew_name)
    why = list(est.get("why") or [])
    if crew_name and any(k in crew_name.lower() for k in SLOW_CREWS):
        why.append(f"{crew_name} is a smaller crew")
    return {"days": days, "why": ", ".join(why)}
