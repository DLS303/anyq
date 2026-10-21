"""Supplier score from closed deals.

Weights: delivery on time 30%, invoice price equals the offer 25%,
quality and acceptance 25%, documents 10%, reply speed 10%.
Bayesian smoothing and time decay apply once a supplier has at least
five closed deals. Fewer than five deals stay at a neutral score with
the label «Новый» and are not penalised. Sort order has no commercial term.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

WEIGHT_DELIVERY = 0.30
WEIGHT_PRICE = 0.25
WEIGHT_QUALITY = 0.25
WEIGHT_DOCUMENTS = 0.10
WEIGHT_REPLY = 0.10

LATE_DELIVERY = 3.0
PRICE_MISS = 3.0
ACCEPTANCE_REMARKS = 2.0
DOCUMENTS_BAD = 0.0
REPLY_FAST = 5.0
REPLY_SLOW = 2.0
REPLY_WITHIN_HOURS = 24

HALF_LIFE_DAYS = 14
PRIOR_DEALS = 4
PRIOR_MEAN = 4.2
NEUTRAL_RATING = 4.0
NEW_UNDER_DEALS = 5
RELIABLE_MIN = 4.5
RELIABLE_DEALS = 5
FIXTURE_AS_OF = date(2026, 10, 21)


@dataclass(frozen=True)
class DealFact:
    closed_on: date
    on_time: bool
    price_matched: bool
    acceptance_ok: bool
    esf_ok: bool
    response_hours: float
    quality_star: float | None


@dataclass(frozen=True)
class Score:
    rating: float
    deal_count: int
    is_new: bool
    reliable: bool
    delivery: float
    price: float
    quality: float
    documents: float
    reply: float

    @property
    def label(self) -> str:
        if self.is_new:
            return "Новый"
        if self.reliable:
            return "Надёжный поставщик"
        return ""


def reply_points(hours: float) -> float:
    return REPLY_FAST if hours <= REPLY_WITHIN_HOURS else REPLY_SLOW


def deal_points(fact: DealFact) -> dict[str, float]:
    delivery = 5.0 if fact.on_time else LATE_DELIVERY
    price = 5.0 if fact.price_matched else PRICE_MISS
    acceptance = 5.0 if fact.acceptance_ok else ACCEPTANCE_REMARKS
    star = float(fact.quality_star) if fact.quality_star is not None else acceptance
    quality = (star + acceptance) / 2.0
    documents = 5.0 if fact.esf_ok else DOCUMENTS_BAD
    reply = reply_points(fact.response_hours)
    total = (
        WEIGHT_DELIVERY * delivery
        + WEIGHT_PRICE * price
        + WEIGHT_QUALITY * quality
        + WEIGHT_DOCUMENTS * documents
        + WEIGHT_REPLY * reply
    )
    return {
        "total": total,
        "delivery": delivery,
        "price": price,
        "quality": quality,
        "documents": documents,
        "reply": reply,
    }


def _decay(age_days: int) -> float:
    return 0.5 ** (max(age_days, 0) / HALF_LIFE_DAYS)


def aggregate(facts: list[DealFact], as_of: date) -> Score:
    count = len(facts)
    if count < NEW_UNDER_DEALS:
        return Score(
            rating=NEUTRAL_RATING,
            deal_count=count,
            is_new=True,
            reliable=False,
            delivery=0.0,
            price=0.0,
            quality=0.0,
            documents=0.0,
            reply=0.0,
        )
    num = PRIOR_DEALS * PRIOR_MEAN
    den = float(PRIOR_DEALS)
    buckets = {key: 0.0 for key in ("delivery", "price", "quality", "documents", "reply")}
    weight_sum = 0.0
    for fact in facts:
        weight = _decay((as_of - fact.closed_on).days)
        points = deal_points(fact)
        num += weight * points["total"]
        den += weight
        for key in buckets:
            buckets[key] += weight * points[key]
        weight_sum += weight
    rating = num / den if den else NEUTRAL_RATING
    scale = weight_sum or 1.0
    reliable = rating >= RELIABLE_MIN and count >= RELIABLE_DEALS
    return Score(
        rating=rating,
        deal_count=count,
        is_new=False,
        reliable=reliable,
        delivery=buckets["delivery"] / scale,
        price=buckets["price"] / scale,
        quality=buckets["quality"] / scale,
        documents=buckets["documents"] / scale,
        reply=buckets["reply"] / scale,
    )


def smoothed_closer_to_prior(raw: float, smoothed: float) -> bool:
    return abs(smoothed - PRIOR_MEAN) < abs(raw - PRIOR_MEAN) + 1e-9


def raw_mean(facts: list[DealFact]) -> float:
    if not facts:
        return NEUTRAL_RATING
    return sum(deal_points(fact)["total"] for fact in facts) / len(facts)


def decay_weight(age_days: int) -> float:
    return _decay(age_days)


def prior_pull(sample: float, sample_weight: float) -> float:
    """One observation pulled toward the prior. Used by the smoothing test."""
    return (PRIOR_DEALS * PRIOR_MEAN + sample_weight * sample) / (PRIOR_DEALS + sample_weight)


def math_half_life_ok() -> bool:
    return math.isclose(decay_weight(HALF_LIFE_DAYS), 0.5)
