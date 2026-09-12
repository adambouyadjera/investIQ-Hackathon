"""News sentiment, scored transparently and read point-in-time.

Three things this module refuses to do, each because the alternative produces
a backtest that cannot be believed:

1. **It never reads a headline published at or after the bar it is scoring.**
   `sentiment_at` filters on `published_at < bar_close`, strictly. A headline
   timestamped 16:00 on the day you are trading the 16:00 close is not
   information you had.

2. **It never hides why it scored what it scored.** Every `NewsScore` carries
   the headlines that moved it and the exact terms that matched inside each.
   A sentiment number you cannot decompose is not evidence, it is an assertion.

3. **It never lets the synthetic provider pretend to be real.** `SOURCE` is
   carried on every score and propagated all the way to the API response, and
   `SyntheticNewsProvider` is built from *past* returns and seeded noise only,
   so it is non-predictive by construction. That is deliberate: a synthetic
   corpus that correlated with future returns would manufacture alpha, and the
   harness would faithfully report it.

The scorer is a lexicon, not a language model. For a signal that has to be
auditable term-by-term and reproduce bit-for-bit across runs, a transparent
lexicon is the better engineering choice, and it has no API dependency.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NEWS_FILE = DATA_DIR / "news.jsonl"

HALF_LIFE_DAYS = 5.0
WINDOW_DAYS = 10
# Below this many headlines in the window the score is damped toward zero
# rather than reported at face value -- two headlines is an anecdote.
MIN_COVERAGE = 3


# ── Lexicon ──────────────────────────────────────────────────────────────────
# Weights are intentionally coarse. A finer-grained lexicon invites the belief
# that the number is precise; it is not, and the decision layer treats it as
# one piece of evidence among five.

POSITIVE: Dict[str, float] = {
    "beats": 1.0, "beat": 1.0, "record": 0.8, "surges": 1.0, "surge": 1.0,
    "raises": 0.8, "raised": 0.8, "upgrade": 1.0, "upgraded": 1.0,
    "outperform": 0.9, "strong": 0.6, "growth": 0.5, "expands": 0.5,
    "profit": 0.5, "wins": 0.7, "approval": 0.7, "beats-estimates": 1.0,
    "rally": 0.8, "rallies": 0.8, "beats expectations": 1.2, "buyback": 0.7,
    "dividend increase": 0.9, "guidance raised": 1.2,
}

NEGATIVE: Dict[str, float] = {
    "misses": 1.0, "miss": 1.0, "plunges": 1.2, "plunge": 1.2, "falls": 0.7,
    "cuts": 0.9, "cut": 0.9, "downgrade": 1.0, "downgraded": 1.0,
    "underperform": 0.9, "weak": 0.6, "decline": 0.6, "declines": 0.6,
    "loss": 0.7, "losses": 0.7, "probe": 0.8, "investigation": 0.9,
    "lawsuit": 0.8, "recall": 0.9, "selloff": 1.0, "sell-off": 1.0,
    "warns": 1.0, "warning": 0.9, "guidance cut": 1.2, "layoffs": 0.7,
    "misses estimates": 1.2, "slump": 0.9, "slumps": 0.9,
}

NEGATORS = ("not", "no", "never", "without", "fails to", "failed to")

LEXICON_VERSION = "lex-1"


@dataclass(frozen=True)
class Headline:
    symbol: str
    published_at: datetime
    text: str
    source: str = "unknown"

    def __post_init__(self) -> None:
        if self.published_at.tzinfo is None:
            raise ValueError(
                f"headline {self.text!r} has a naive timestamp; point-in-time "
                "filtering needs an explicit timezone"
            )


@dataclass(frozen=True)
class TermHit:
    term: str
    weight: float
    negated: bool

    @property
    def signed(self) -> float:
        return -self.weight if self.negated else self.weight


@dataclass(frozen=True)
class ScoredHeadline:
    headline: Headline
    polarity: float           # -1..1 before time decay
    decay: float              # 0..1, how much of it still counts today
    hits: Tuple[TermHit, ...] = ()

    @property
    def contribution(self) -> float:
        return self.polarity * self.decay

    def explain(self) -> str:
        if not self.hits:
            return "no lexicon terms matched"
        parts = [f"{'NOT ' if h.negated else ''}{h.term} ({h.signed:+.1f})" for h in self.hits]
        return ", ".join(parts)


@dataclass(frozen=True)
class NewsScore:
    """Aggregate sentiment for one symbol as of one moment."""

    symbol: str
    as_of: datetime
    value: float                       # -1..1, decay-weighted and coverage-damped
    coverage: int                      # headlines inside the window
    source: str
    raw_value: float = 0.0             # before coverage damping
    scored: Tuple[ScoredHeadline, ...] = ()

    @property
    def is_thin(self) -> bool:
        return self.coverage < MIN_COVERAGE

    def top_drivers(self, n: int = 3) -> List[ScoredHeadline]:
        return sorted(self.scored, key=lambda s: -abs(s.contribution))[:n]

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "value": round(self.value, 4),
            "raw_value": round(self.raw_value, 4),
            "coverage": self.coverage,
            "source": self.source,
            "thin_coverage": self.is_thin,
            "lexicon_version": LEXICON_VERSION,
            "drivers": [
                {
                    "text": s.headline.text,
                    "published_at": s.headline.published_at.isoformat(),
                    "source": s.headline.source,
                    "polarity": round(s.polarity, 3),
                    "decay": round(s.decay, 3),
                    "contribution": round(s.contribution, 4),
                    "matched_terms": s.explain(),
                }
                for s in self.top_drivers()
            ],
        }


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_text(text: str) -> Tuple[float, Tuple[TermHit, ...]]:
    """Polarity in -1..1, plus every term that contributed to it.

    Multi-word terms are matched before single words so that "guidance cut"
    scores once as a phrase rather than twice via "cut".
    """
    lowered = " " + text.lower().strip() + " "
    hits: List[TermHit] = []
    consumed = lowered

    for table, sign in ((POSITIVE, 1.0), (NEGATIVE, -1.0)):
        for term in sorted(table, key=len, reverse=True):
            needle = " " + term + " " if " " not in term else term
            idx = consumed.find(needle)
            if idx == -1:
                continue
            window = consumed[max(0, idx - 24):idx]
            negated = any(neg in window for neg in NEGATORS)
            hits.append(TermHit(term, sign * table[term], negated))
            consumed = consumed.replace(needle, " ", 1)

    if not hits:
        return 0.0, ()

    total = sum(h.signed for h in hits)
    # Squash so a headline stuffed with ten adjectives cannot outweigh ten
    # separate headlines that each say one thing.
    return math.tanh(total / 2.0), tuple(hits)


def _decay(age_days: float) -> float:
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


# ── Providers ────────────────────────────────────────────────────────────────

class NewsProvider:
    """Anything that can hand back headlines for a symbol in a time range."""

    source = "unknown"

    def headlines(self, symbol: str, start: datetime, end: datetime) -> Sequence[Headline]:
        raise NotImplementedError


class NullNewsProvider(NewsProvider):
    """No news at all. Every score is neutral and flagged as such."""

    source = "none"

    def headlines(self, symbol: str, start: datetime, end: datetime) -> Sequence[Headline]:
        return ()


class JsonlNewsProvider(NewsProvider):
    """Archived headlines from `data/news.jsonl`.

    One JSON object per line: {"symbol", "published_at" (ISO 8601 with offset),
    "text", "source"}. This is the hook for a real corpus; drop a file in and
    every score in the app switches over with `source: "archive"`.
    """

    source = "archive"

    def __init__(self, path: Path = NEWS_FILE):
        self.path = path
        self._by_symbol: Dict[str, List[Headline]] = {}
        if path.exists():
            self._load()

    def _load(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            ts = datetime.fromisoformat(raw["published_at"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            h = Headline(raw["symbol"], ts, raw["text"], raw.get("source", "archive"))
            self._by_symbol.setdefault(h.symbol, []).append(h)
        for v in self._by_symbol.values():
            v.sort(key=lambda h: h.published_at)

    @property
    def available(self) -> bool:
        return bool(self._by_symbol)

    def headlines(self, symbol: str, start: datetime, end: datetime) -> Sequence[Headline]:
        return [h for h in self._by_symbol.get(symbol, ()) if start <= h.published_at < end]


class SyntheticNewsProvider(NewsProvider):
    """Deterministic stand-in so the desk runs with no data feed.

    Built strictly from *already-observed* returns plus seeded noise, so it
    carries no information about what happens next. Any edge the harness
    measures from this provider is noise, and the harness says so in its
    output rather than leaving the reader to assume otherwise.
    """

    source = "synthetic"

    _POS_TEMPLATES = (
        "{sym} beats expectations as quarterly profit tops forecasts",
        "Analysts upgrade {sym} on strong demand and raised guidance",
        "{sym} rallies after announcing a buyback",
        "{sym} surges on record segment growth",
    )
    _NEG_TEMPLATES = (
        "{sym} misses estimates as margins decline",
        "Brokers downgrade {sym} after guidance cut",
        "{sym} slumps on a regulatory investigation",
        "{sym} warns of weak demand into next quarter",
    )
    _NEUTRAL_TEMPLATES = (
        "{sym} to present at an industry conference next month",
        "{sym} names a new chief operating officer",
        "{sym} files its routine quarterly report",
    )

    def __init__(self, prices: pd.DataFrame, seed: int = 20260912, per_week: float = 2.5):
        self.prices = prices
        self.seed = seed
        self.per_week = per_week
        self._cache: Dict[str, List[Headline]] = {}

    @staticmethod
    def _seed_for(symbol: str, seed: int) -> int:
        """Per-symbol seed that is stable across processes.

        Python's builtin `hash()` is salted per interpreter unless
        PYTHONHASHSEED is pinned, so seeding from `hash((symbol, seed))` makes
        the whole corpus -- and therefore every backtest that uses it -- a
        different number on every run. A backtest that cannot be reproduced
        cannot be checked, so the seed is derived from SHA-256 instead.
        """
        digest = hashlib.sha256(f"{symbol}:{seed}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % (2 ** 32)

    def _generate(self, symbol: str) -> List[Headline]:
        if symbol in self._cache:
            return self._cache[symbol]
        if symbol not in self.prices.columns:
            self._cache[symbol] = []
            return []

        close = self.prices[symbol].astype(float)
        # Tone tracks the trailing 5-day move -- information already in the
        # price, shifted so the headline can only reflect the past.
        trailing = (close.pct_change(5).shift(1)).fillna(0.0)
        rng = np.random.default_rng(self._seed_for(symbol, self.seed))

        out: List[Headline] = []
        prob = self.per_week / 5.0
        for date, move in trailing.items():
            if rng.random() > prob:
                continue
            tone = float(np.tanh(move * 25.0)) + float(rng.normal(0.0, 0.7))
            if tone > 0.5:
                tpl = self._POS_TEMPLATES[rng.integers(len(self._POS_TEMPLATES))]
            elif tone < -0.5:
                tpl = self._NEG_TEMPLATES[rng.integers(len(self._NEG_TEMPLATES))]
            else:
                tpl = self._NEUTRAL_TEMPLATES[rng.integers(len(self._NEUTRAL_TEMPLATES))]
            # Published pre-open on the bar's own day.
            stamp = pd.Timestamp(date).to_pydatetime().replace(
                hour=int(rng.integers(6, 13)), minute=int(rng.integers(0, 60)),
                tzinfo=timezone.utc,
            )
            out.append(Headline(symbol, stamp, tpl.format(sym=symbol), "synthetic"))

        out.sort(key=lambda h: h.published_at)
        self._cache[symbol] = out
        return out

    def headlines(self, symbol: str, start: datetime, end: datetime) -> Sequence[Headline]:
        return [h for h in self._generate(symbol) if start <= h.published_at < end]


def default_provider(prices: Optional[pd.DataFrame] = None) -> NewsProvider:
    """Archive if one is present, synthetic if prices are available, else none."""
    archive = JsonlNewsProvider()
    if archive.available:
        return archive
    if prices is not None:
        return SyntheticNewsProvider(prices)
    return NullNewsProvider()


# ── Point-in-time aggregation ────────────────────────────────────────────────

def sentiment_at(
    provider: NewsProvider,
    symbol: str,
    bar_close: datetime,
    window_days: int = WINDOW_DAYS,
) -> NewsScore:
    """Decay-weighted sentiment from headlines strictly before `bar_close`."""
    if bar_close.tzinfo is None:
        raise ValueError("bar_close must be timezone-aware")

    start = bar_close - timedelta(days=window_days)
    found = [h for h in provider.headlines(symbol, start, bar_close)
             if h.published_at < bar_close]

    scored: List[ScoredHeadline] = []
    for h in found:
        polarity, hits = score_text(h.text)
        age = (bar_close - h.published_at).total_seconds() / 86400.0
        scored.append(ScoredHeadline(h, polarity, _decay(age), hits))

    coverage = len(scored)
    if coverage == 0:
        return NewsScore(symbol, bar_close, 0.0, 0, provider.source, 0.0, ())

    weight_sum = sum(s.decay for s in scored)
    raw = sum(s.contribution for s in scored) / weight_sum if weight_sum else 0.0

    # Thin coverage is damped, not dropped: one strongly-worded headline should
    # nudge the score, not set it.
    damp = min(1.0, coverage / MIN_COVERAGE)
    return NewsScore(
        symbol=symbol,
        as_of=bar_close,
        value=float(np.clip(raw * damp, -1.0, 1.0)),
        coverage=coverage,
        source=provider.source,
        raw_value=float(raw),
        scored=tuple(scored),
    )


def sentiment_series(
    provider: NewsProvider,
    symbol: str,
    dates: Iterable[pd.Timestamp],
    close_hour: int = 21,
) -> pd.Series:
    """Sentiment on each date, for charting and for the feature frame.

    `close_hour` is 21:00 UTC, roughly the US equity close. Headlines published
    after it land on the next bar, which is the correct side of the line.
    """
    idx = list(dates)
    values = []
    for d in idx:
        bar_close = pd.Timestamp(d).to_pydatetime().replace(
            hour=close_hour, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
        values.append(sentiment_at(provider, symbol, bar_close).value)
    return pd.Series(values, index=pd.DatetimeIndex(idx), name="news")
