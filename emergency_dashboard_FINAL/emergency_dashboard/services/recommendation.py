"""Rule-based route recommendation built only from the routing engine's returned numbers."""
from __future__ import annotations

from dataclasses import replace

from services.contracts import RouteRecommendation
from services.route_metrics import route_metrics

DISCLAIMER = ("Decision support only. A lower risk score is not a guarantee of safety. "
              "Follow instructions from emergency responders.")
_NAMES = {"primary": "Primary", "backup": "Backup", "baseline": "Baseline"}


def _fmt(v, nd, integer=False):
    if v is None:
        return "n/a"
    return str(int(v)) if integer else f"{v:.{nd}f}"


def _factors(m: dict) -> tuple:
    rows = []
    for label, field, nd, integer in (("Travel time (min)", "time_min", 1, False),
                                      ("Distance (km)", "distance_km", 2, False),
                                      ("Risk score", "risk", 2, False),
                                      ("Blocked segments", "blocked", 0, True)):
        rows.append({"Factor": label, **{_NAMES[k]: _fmt(m[k][field], nd, integer) for k in ("primary", "backup", "baseline")}})
    return tuple(rows)


def _ok(m: dict) -> bool:
    return m["time_min"] is not None and m["risk"] is not None


def build_recommendation(primary, backup=None, baseline=None, *, hazard_label=None, explainer=None) -> RouteRecommendation:
    m = {"primary": route_metrics(primary), "backup": route_metrics(backup), "baseline": route_metrics(baseline)}
    factors = _factors(m)
    limits = []

    if primary is None or not _ok(m["primary"]):
        return RouteRecommendation(
            "rule_based", None, "Not enough data to recommend a route",
            "The primary route is missing travel time or risk values.",
            factors, ("Routes cannot be compared reliably with the data returned.",))

    cands = ["primary"]
    if backup is None:
        limits.append("No independent backup route was returned; only the primary route was assessed.")
    elif _ok(m["backup"]):
        cands.append("backup")
    else:
        limits.append("The backup route lacks travel time or risk values and was excluded from the comparison.")
    if baseline is None or not _ok(m["baseline"]):
        limits.append("The baseline comparison is unavailable.")
    if any(m[c]["blocked"] is None for c in cands):
        limits.append("Blocked-segment counts were not provided, so blockage was not part of the ranking.")

    def key(c):  # ties keep the primary because sorted() is stable and primary is first
        return (m[c]["blocked"] or 0, m[c]["risk"], m[c]["time_min"])

    best = min(cands, key=key)
    cm = m[best]
    scenario = f" for the {hazard_label} scenario" if hazard_label else ""
    parts = [f"Candidate routes were ranked by blocked segments, then risk score, then travel time{scenario}."]
    if len(cands) == 2:
        other = "backup" if best == "primary" else "primary"
        om = m[other]
        parts.append(f"The {best} route has a risk score of {cm['risk']:.2f} and takes {cm['time_min']:.1f} min, "
                     f"versus {om['risk']:.2f} and {om['time_min']:.1f} min for the {other} route.")
        if (om["blocked"] or 0) > 0:
            parts.append(f"The {other} route crosses {int(om['blocked'])} blocked segment(s).")
    dists = [m[k]["distance_km"] for k in ("primary", "backup", "baseline") if m[k]["distance_km"] is not None]
    if cm["distance_km"] is not None and dists:
        extra_m = (cm["distance_km"] - min(dists)) * 1000
        if extra_m >= 5:
            parts.append(f"It is about {round(extra_m)} m longer than the shortest available route.")
    bm = m["baseline"]
    if baseline is not None and _ok(bm):
        dt = cm["time_min"] - bm["time_min"]
        s = f"Compared with the conventional baseline route, it takes {dt:+.1f} min"
        if bm["risk"] > 0:
            pct = round(abs(cm["risk"] - bm["risk"]) / bm["risk"] * 100)
            s += f" and its risk score is {pct}% {'lower' if cm['risk'] < bm['risk'] else 'higher'}"
        parts.append(s + ".")
        if dt > 0 and cm["risk"] < bm["risk"]:
            parts.append("This is a trade-off: extra travel time for a lower risk score.")
        if (bm["blocked"] or 0) > 0:
            parts.append(f"The baseline route crosses {int(bm['blocked'])} blocked segment(s).")

    rec = RouteRecommendation("rule_based", best, f"Recommended: {best.capitalize()} route",
                              " ".join(parts), factors, tuple(limits))
    if explainer is not None:
        try:
            text = explainer(rec)
        except Exception:
            text = None
        if text and str(text).strip():
            rec = replace(rec, mode="model_based_explanation", explanation=str(text).strip(),
                          limitations=rec.limitations + ("The explanation text was model-generated. "
                                                         "The route choice and all numbers come from the routing engine.",))
    return rec
