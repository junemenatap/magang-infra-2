"""
config.py
=========
Single place to tune everything that influences the demo: how many logs get
generated, how often each anomaly type is injected, detector layer weights,
and the final decision threshold. All defaults reproduce exactly what the
pipeline was already doing -- change values here, not inside
log_generator.py / anomaly_detector.py / run_pipeline.py.
"""

from dataclasses import dataclass, field


@dataclass
class GeneratorConfig:
    # ---- overall volume ----
    total_minutes: int = 180          # length of the simulated stream
    train_minutes: int = 60           # leading clean (anomaly-free) training window
    sessions_per_min: float = 4.0     # vending-machine session arrival rate
    seed: int = None                  # None -> non-reproducible random stream each run

    # ---- background (non-session) event rates, events/minute ----
    background_rates: dict = field(default_factory=lambda: {
        "db_query": 6.0,
        "telemetry": 2.0,
    })

    # ---- volume/burst anomaly: db_query rate spike ----
    burst_offset_min: float = 20      # minutes after train_end when the burst starts
    burst_duration_min: float = 3
    burst_template: str = "db_query"
    burst_multiplier: float = 12.0    # rate multiplier during the burst

    # ---- volume/burst anomaly: auth brute-force ----
    brute_force_offset_min: float = 60
    brute_force_duration_min: float = 2
    brute_force_gap_range_sec: tuple = (0.5, 2.0)  # inter-attempt gap; smaller = more rapid-fire

    # ---- novel-template anomaly ----
    novel_offset_min: float = 45
    novel_duration_min: float = 5
    novel_emit_prob_per_tick: float = 0.02  # chance per 5s tick during the novel window

    # ---- rarity anomaly (coin_jam / refund incidents) ----
    rarity_offsets_min: tuple = (10, 35, 70, 90)  # minutes after train_end

    # ---- per-session sequence / metric anomaly injection rates ----
    sequence_anomaly_prob: float = 0.06   # fraction of test-window sessions
    metric_anomaly_prob: float = 0.06     # additional fraction (applied after sequence slice)

    # ---- metric baseline distributions: template -> (mean, std) ----
    metric_dist: dict = field(default_factory=lambda: {
        "payment_ok":      (5.5, 3.0),
        "inventory_check": (40, 15),
        "dispense_ok":     (350, 60),
        "session_end":     (9000, 2000),
        "db_query":        (18, 6),
        "telemetry_temp":  (24, 3),
        "telemetry_hum":   (45, 8),
        "refund":          (5.5, 3.0),
    })
    metric_spike_sd_multipliers: tuple = (9, -5.5)  # dispense_ok metric-anomaly spike, in std units


@dataclass
class DetectorConfig:
    window: str = "1min"  # bucket size for volume scoring
    weights: dict = field(default_factory=lambda: {
        "novelty": 1.0, "rarity": 0.5, "metric": 1.0, "volume": 1.0, "sequence": 1.0,
    })
    sequence_order: int = 1  # k in the k-order Markov sequence model (1 = current default)
    sequence_propagation_threshold: float = 0.5  # local score above this propagates anomaly to the whole session
    sequence_use_aggregate_likelihood: bool = False  # off by default -- see SequenceScorer docstring; propagation alone is more precise


@dataclass
class PipelineConfig:
    threshold: float = 0.50  # final_score above this -> flagged as anomaly


@dataclass
class Config:
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)


DEFAULT_CONFIG = Config()