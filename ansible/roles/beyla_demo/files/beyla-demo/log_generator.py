"""
log_generator.py
=================
Generates a synthetic log stream for a vending-machine microservices stack
(auth, payment, inventory, dispense, telemetry, db).

Every log line carries hidden ground-truth fields so the detector's output
can be scored:
    is_anomaly   : bool
    anomaly_type : one of {normal, novel, rarity, metric, volume, sequence}

Design:
- Sessions follow a state machine: START -> AUTH -> PAYMENT -> INVENTORY ->
  DISPENSE -> END. A background stream of DB queries and telemetry
  heartbeats runs independently of sessions.
- A held-out "training" period (first N minutes) is emitted CLEAN (no
  injected anomalies) so the detector can learn normal baselines exactly
  the way you'd deploy it in practice (train on a known-good window).
- After that, anomalies of all five kinds are injected at controlled rates.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

random.seed(42)

# ---------------------------------------------------------------------------
# Template catalog. {X} placeholders get filled with realistic values.
# ---------------------------------------------------------------------------

TEMPLATES = {
    "session_start":   "Session {sid} started for terminal {tid}",
    "auth_ok":         "User {uid} authentication successful",
    "auth_fail":       "User {uid} authentication failed",
    "payment_ok":      "Payment of {value:.2f} received via {method}",
    "inventory_check": "Inventory check for item {item} - stock={value:.0f}",
    "dispense_start":  "Dispensing item {item} from slot {slot}",
    "dispense_ok":     "Dispense completed for item {item} in {value:.0f}ms",
    "session_end":     "Session {sid} ended, duration={value:.0f}ms",
    "db_query":        "DB query executed in {value:.1f}ms",
    "telemetry":       "Telemetry heartbeat: temp={temp:.1f}C, humidity={hum:.1f}%",
    "coin_jam":        "Coin jam detected in slot {slot}",
    "refund":          "Refund issued: {value:.2f}",
}

# Base rates (expected occurrences per minute) for the *background* templates
# not tied to a session lifecycle.
BACKGROUND_RATES = {
    "db_query": 6.0,
    "telemetry": 2.0,
    # NOTE: coin_jam / refund are intentionally NOT modeled as a background
    # Poisson stream. They are rare-enough incident types that every
    # occurrence is worth flagging for review, so they're injected
    # explicitly below (see rarity_times) with a consistent ground-truth
    # label -- keeping them here too would make them indistinguishable
    # from their own "anomalous" injections (same template, same rate),
    # which no detector could resolve and would just be a mislabeled eval.
}

# Normal per-template metric distributions: (mean, std)
METRIC_DIST = {
    "payment_ok":      (5.5, 3.0),      # currency amount
    "inventory_check": (40, 15),        # stock count
    "dispense_ok":     (350, 60),       # ms
    "session_end":     (9000, 2000),    # ms
    "db_query":        (18, 6),         # ms
    "telemetry_temp":  (24, 3),         # C
    "telemetry_hum":   (45, 8),         # %
    "refund":          (5.5, 3.0),
}

ITEMS = ["A1_Chips", "A2_Soda", "B1_Water", "B2_Candy", "C1_Coffee"]
METHODS = ["card", "mobile_pay", "coin"]
TERMINALS = [f"T{i:03d}" for i in range(1, 6)]

SESSION_STATE_ORDER = [
    "session_start", "auth_ok", "payment_ok",
    "inventory_check", "dispense_start", "dispense_ok", "session_end",
]


@dataclass
class LogLine:
    ts: str
    session_id: str
    service: str
    template_id: str
    message: str
    value: float
    is_anomaly: bool
    anomaly_type: str  # normal, novel, rarity, metric, volume, sequence


SERVICE_OF = {
    "session_start": "gateway", "session_end": "gateway",
    "auth_ok": "auth-service", "auth_fail": "auth-service",
    "payment_ok": "payment-service", "refund": "payment-service",
    "inventory_check": "inventory-service",
    "dispense_start": "dispense-service", "dispense_ok": "dispense-service",
    "coin_jam": "dispense-service",
    "db_query": "db-proxy", "telemetry": "telemetry-agent",
}


def render(template_id, **kw):
    return TEMPLATES[template_id].format(**kw)


def make_line(ts, session_id, template_id, is_anomaly=False, anomaly_type="normal", value=None, **kw):
    if template_id == "telemetry":
        mu_t, sd_t = METRIC_DIST["telemetry_temp"]
        mu_h, sd_h = METRIC_DIST["telemetry_hum"]
        temp = value if value is not None else random.gauss(mu_t, sd_t)
        hum = kw.pop("hum", random.gauss(mu_h, sd_h))
        msg = render(template_id, temp=temp, hum=hum)
        val = temp
    elif template_id in ("payment_ok", "inventory_check", "dispense_ok", "session_end", "db_query", "refund"):
        mu, sd = METRIC_DIST[template_id]
        v = value if value is not None else max(0.1, random.gauss(mu, sd))
        msg = render(template_id, value=v, **kw)
        val = v
    else:
        msg = render(template_id, **kw)
        val = None
    return LogLine(
        ts=ts.isoformat(timespec="milliseconds"),
        session_id=session_id,
        service=SERVICE_OF[template_id],
        template_id=template_id,
        message=msg,
        value=val,
        is_anomaly=is_anomaly,
        anomaly_type=anomaly_type,
    )


def gen_normal_session(ts):
    """Yield a well-formed session sequence starting at ts, return end time."""
    sid = f"S{random.randint(100000,999999)}"
    tid = random.choice(TERMINALS)
    uid = f"U{random.randint(1000,9999)}"
    item = random.choice(ITEMS)
    slot = f"SLOT{random.randint(1,8)}"
    method = random.choice(METHODS)

    lines = []
    t = ts
    lines.append(make_line(t, sid, "session_start", sid=sid, tid=tid)); t += timedelta(milliseconds=random.randint(50,200))
    lines.append(make_line(t, sid, "auth_ok", uid=uid)); t += timedelta(milliseconds=random.randint(100,400))
    lines.append(make_line(t, sid, "payment_ok", method=method)); t += timedelta(milliseconds=random.randint(100,300))
    lines.append(make_line(t, sid, "inventory_check", item=item)); t += timedelta(milliseconds=random.randint(50,150))
    lines.append(make_line(t, sid, "dispense_start", item=item, slot=slot)); t += timedelta(milliseconds=random.randint(200,500))
    lines.append(make_line(t, sid, "dispense_ok", item=item)); t += timedelta(milliseconds=random.randint(50,150))
    lines.append(make_line(t, sid, "session_end", sid=sid)); t += timedelta(milliseconds=random.randint(20,80))
    return lines, t


def gen_sequence_anomaly_session(ts):
    """A session with an out-of-order / malformed state transition."""
    sid = f"S{random.randint(100000,999999)}"
    tid = random.choice(TERMINALS)
    uid = f"U{random.randint(1000,9999)}"
    item = random.choice(ITEMS)
    slot = f"SLOT{random.randint(1,8)}"
    method = random.choice(METHODS)

    kind = random.choice(["dispense_before_payment", "skip_auth", "double_dispense"])
    lines = []
    t = ts

    if kind == "dispense_before_payment":
        # dispense happens before payment is recorded -> illegal transition
        lines.append(make_line(t, sid, "session_start", sid=sid, tid=tid)); t += timedelta(milliseconds=100)
        lines.append(make_line(t, sid, "auth_ok", uid=uid)); t += timedelta(milliseconds=150)
        lines.append(make_line(t, sid, "inventory_check", item=item)); t += timedelta(milliseconds=80)
        anomalous = make_line(t, sid, "dispense_start", item=item, slot=slot,
                               is_anomaly=True, anomaly_type="sequence")
        lines.append(anomalous); t += timedelta(milliseconds=300)
        lines.append(make_line(t, sid, "dispense_ok", item=item, is_anomaly=True, anomaly_type="sequence")); t += timedelta(milliseconds=100)
        lines.append(make_line(t, sid, "payment_ok", method=method, is_anomaly=True, anomaly_type="sequence")); t += timedelta(milliseconds=60)
        lines.append(make_line(t, sid, "session_end", sid=sid)); t += timedelta(milliseconds=40)
    elif kind == "skip_auth":
        # payment happens with no auth_ok preceding it
        lines.append(make_line(t, sid, "session_start", sid=sid, tid=tid)); t += timedelta(milliseconds=100)
        anomalous = make_line(t, sid, "payment_ok", method=method,
                               is_anomaly=True, anomaly_type="sequence")
        lines.append(anomalous); t += timedelta(milliseconds=150)
        lines.append(make_line(t, sid, "inventory_check", item=item)); t += timedelta(milliseconds=80)
        lines.append(make_line(t, sid, "dispense_start", item=item, slot=slot)); t += timedelta(milliseconds=300)
        lines.append(make_line(t, sid, "dispense_ok", item=item)); t += timedelta(milliseconds=100)
        lines.append(make_line(t, sid, "session_end", sid=sid)); t += timedelta(milliseconds=40)
    else:  # double_dispense
        lines.append(make_line(t, sid, "session_start", sid=sid, tid=tid)); t += timedelta(milliseconds=100)
        lines.append(make_line(t, sid, "auth_ok", uid=uid)); t += timedelta(milliseconds=150)
        lines.append(make_line(t, sid, "payment_ok", method=method)); t += timedelta(milliseconds=120)
        lines.append(make_line(t, sid, "inventory_check", item=item)); t += timedelta(milliseconds=80)
        lines.append(make_line(t, sid, "dispense_start", item=item, slot=slot)); t += timedelta(milliseconds=300)
        lines.append(make_line(t, sid, "dispense_ok", item=item)); t += timedelta(milliseconds=100)
        anomalous = make_line(t, sid, "dispense_start", item=item, slot=slot,
                               is_anomaly=True, anomaly_type="sequence")
        lines.append(anomalous); t += timedelta(milliseconds=300)
        lines.append(make_line(t, sid, "dispense_ok", item=item, is_anomaly=True, anomaly_type="sequence")); t += timedelta(milliseconds=100)
        lines.append(make_line(t, sid, "session_end", sid=sid)); t += timedelta(milliseconds=40)

    return lines, t


def gen_metric_anomaly_session(ts, cfg=None):
    """A structurally-normal session but with one wildly out-of-range metric."""
    lines, end_t = gen_normal_session(ts)
    idx = next(i for i, l in enumerate(lines) if l.template_id == "dispense_ok")
    bad = lines[idx]
    mu, sd = METRIC_DIST["dispense_ok"]
    mult_choices = cfg.metric_spike_sd_multipliers if cfg is not None else (9, -5.5)
    # jam (way too slow) or physically-implausible instant dispense (way too fast)
    spike_val = mu + sd * random.choice(mult_choices)
    spike_val = max(1.0, spike_val)
    lines[idx] = make_line(
        datetime.fromisoformat(bad.ts), bad.session_id, "dispense_ok",
        item=None if False else "X", is_anomaly=True, anomaly_type="metric", value=spike_val
    )
    # fix message rendering (item name was lost above) - regenerate properly
    lines[idx].message = TEMPLATES["dispense_ok"].format(item="A1_Chips", value=spike_val)
    return lines, end_t


def generate(config=None, hours_back=None, **overrides):
    """
    Returns list[LogLine]. First `train_minutes` are 100% clean (normal-only)
    so the detector has a known-good training window, matching real deployment.

    `config` is a config.GeneratorConfig; omit it to use config.DEFAULT_CONFIG.generator
    (identical to the values this function used to hardcode). Individual fields
    can still be overridden ad hoc via keyword args, e.g. generate(seed=7).

    `hours_back`: if set, anchors the generated timeline to *now* instead of
    the fixed 2026-08-04 date -- the run spans the past `hours_back` hours,
    ending at the moment generate() is called. total_minutes/train_minutes
    are scaled to fill that window while preserving the configured
    train/total ratio (e.g. hours_back=24 with the default 60/180 config
    produces an 8h train window followed by 16h of test traffic). Leave
    unset to keep the original fixed-date behavior.
    """
    global BACKGROUND_RATES, METRIC_DIST
    from config import DEFAULT_CONFIG
    cfg = config or DEFAULT_CONFIG.generator
    if overrides:
        from dataclasses import replace
        cfg = replace(cfg, **overrides)

    if hours_back is not None:
        from dataclasses import replace
        train_fraction = cfg.train_minutes / cfg.total_minutes
        total_minutes = round(hours_back * 60)
        train_minutes = round(total_minutes * train_fraction)
        cfg = replace(cfg, total_minutes=total_minutes, train_minutes=train_minutes)

    # These two are read by module-level helpers (make_line, emit_background,
    # gen_metric_anomaly_session) as globals, so point them at the config's
    # versions for the duration of this call.
    BACKGROUND_RATES = cfg.background_rates
    METRIC_DIST = cfg.metric_dist

    random.seed(cfg.seed)
    if hours_back is not None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours_back)
    else:
        start = datetime(2026, 8, 4, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(minutes=cfg.total_minutes)
    train_end = start + timedelta(minutes=cfg.train_minutes)

    all_lines = []

    def emit_background(a, b, burst_windows=None, novel_windows=None):
        """Emit background events between datetimes a and b."""
        burst_windows = burst_windows or []
        novel_windows = novel_windows or []
        t = a
        tick = timedelta(seconds=5)
        while t < b:
            for tpl, rate_per_min in BACKGROUND_RATES.items():
                lam = rate_per_min * (tick.total_seconds() / 60.0)
                # volume-burst injection: multiply rate during burst window for target template
                in_burst = False
                for (bt0, bt1, btpl, mult) in burst_windows:
                    if btpl == tpl and bt0 <= t < bt1:
                        lam *= mult
                        in_burst = True
                n = poisson_sample(lam)
                for _ in range(n):
                    jitter = t + timedelta(seconds=random.uniform(0, tick.total_seconds()))
                    extra = {}
                    if tpl == "coin_jam":
                        extra["slot"] = f"SLOT{random.randint(1,8)}"
                    # every event emitted while the elevated-rate multiplier is active is
                    # part of the burst pattern -- a volume detector correctly flags the
                    # whole window, not just some subset of lines within it.
                    if in_burst:
                        extra["is_anomaly"] = True
                        extra["anomaly_type"] = "volume"
                    all_lines.append(make_line(jitter, "-", tpl, **extra))
            # novel template injection: a brand-new, never-seen log pattern
            for (nt0, nt1, msg) in novel_windows:
                if nt0 <= t < nt1 and random.random() < cfg.novel_emit_prob_per_tick:
                    all_lines.append(LogLine(
                        ts=t.isoformat(timespec="milliseconds"), session_id="-",
                        service="firmware-agent", template_id="__novel__",
                        message=msg, value=None, is_anomaly=True, anomaly_type="novel",
                    ))
            t += tick

    def poisson_sample(lam):
        # simple Knuth poisson sampler, fine for our small lambdas
        if lam <= 0:
            return 0
        L = math.exp(-lam)
        k = 0
        p = 1.0
        while True:
            k += 1
            p *= random.random()
            if p <= L:
                return k - 1

    # ---- TRAIN WINDOW: fully clean ----
    t = start
    while t < train_end:
        gap = timedelta(seconds=random.expovariate(cfg.sessions_per_min / 60.0))
        t += gap
        if t >= train_end:
            break
        lines, _ = gen_normal_session(t)
        all_lines.extend(lines)
    emit_background(start, train_end)

    # ---- TEST WINDOW: inject all anomaly types ----
    # volume burst: db_query rate spike
    burst_a0 = train_end + timedelta(minutes=cfg.burst_offset_min)
    burst_a1 = burst_a0 + timedelta(minutes=cfg.burst_duration_min)
    burst_windows = [(burst_a0, burst_a1, cfg.burst_template, cfg.burst_multiplier)]

    novel_t0 = train_end + timedelta(minutes=cfg.novel_offset_min)
    novel_t1 = novel_t0 + timedelta(minutes=cfg.novel_duration_min)
    novel_windows = [(novel_t0, novel_t1, f"Firmware update triggered for terminal T{random.randint(1,5):03d}, rollback=false")]

    emit_background(train_end, end, burst_windows=burst_windows, novel_windows=novel_windows)

    # auth_fail brute force burst (separate from background dict since normally session-driven auth_ok
    # dominates; auth_fail here simulates an attacker hammering a terminal with no valid session)
    brute_t0 = train_end + timedelta(minutes=cfg.brute_force_offset_min)
    brute_t1 = brute_t0 + timedelta(minutes=cfg.brute_force_duration_min)
    t = brute_t0
    gap_lo, gap_hi = cfg.brute_force_gap_range_sec
    while t < brute_t1:
        all_lines.append(make_line(t, "-", "auth_fail", uid=f"U{random.randint(1000,9999)}",
                                    is_anomaly=True, anomaly_type="volume"))
        t += timedelta(seconds=random.uniform(gap_lo, gap_hi))  # rapid-fire, way above normal auth_fail rate

    # occasional isolated rarity events (coin_jam/refund occurring is itself notable -> rarity flag target)
    rarity_times = [train_end + timedelta(minutes=m) for m in cfg.rarity_offsets_min]
    for rt in rarity_times:
        tpl = random.choice(["coin_jam", "refund"])
        all_lines.append(make_line(rt, "-", tpl, slot=f"SLOT{random.randint(1,8)}",
                                    is_anomaly=True, anomaly_type="rarity"))

    # normal sessions through the test window, interspersed with anomalous ones
    t = train_end
    while t < end:
        gap = timedelta(seconds=random.expovariate(cfg.sessions_per_min / 60.0))
        t += gap
        if t >= end:
            break
        roll = random.random()
        if roll < cfg.sequence_anomaly_prob:
            lines, _ = gen_sequence_anomaly_session(t)
        elif roll < cfg.sequence_anomaly_prob + cfg.metric_anomaly_prob:
            lines, _ = gen_metric_anomaly_session(t, cfg)
        else:
            lines, _ = gen_normal_session(t)
        all_lines.extend(lines)

    all_lines.sort(key=lambda l: l.ts)
    meta = {
        "start_ts": start.isoformat(timespec="milliseconds"),
        "end_ts": end.isoformat(timespec="milliseconds"),
        "train_end_ts": train_end.isoformat(timespec="milliseconds"),
        "total_minutes": cfg.total_minutes,
        "train_minutes": cfg.train_minutes,
    }
    return all_lines, meta


if __name__ == "__main__":
    lines, meta = generate()
    print(f"Generated {len(lines)} log lines. Train ends at {meta['train_end_ts']}")
    n_anom = sum(1 for l in lines if l.is_anomaly)
    print(f"Injected anomalies: {n_anom}")
    from collections import Counter
    print(Counter(l.anomaly_type for l in lines))