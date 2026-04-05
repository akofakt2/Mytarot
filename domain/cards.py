from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Arcana = Literal["major", "minor"]
Suit = Literal["wands", "cups", "swords", "pentacles"]


@dataclass(frozen=True, slots=True)
class Card:
    """
    Single-source model for a tarot card definition.

    Fields like `arcana/suit/rank/image_path` are stored inside `cards.<locale>.json`
    (even though they are language-neutral) to keep the data layout simple.
    """

    id: int
    arcana: Arcana
    number: int | None
    suit: Suit | None
    rank: str | None
    image_path: str

    name: str
    keywords: tuple[str, ...]
    meaning_upright: str
    meaning_reversed: str
    archetype: str | None = None
    description: str | None = None

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Card":
        required = (
            "id",
            "arcana",
            "image_path",
            "name",
            "keywords",
            "meaning_upright",
            "meaning_reversed",
        )
        missing = [k for k in required if k not in raw]
        if missing:
            raise ValueError(f"Card missing required fields: {missing}")

    
        arcana = raw["arcana"]
    
        suit = raw.get("suit")
    
        keywords = raw["keywords"]
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            raise ValueError("keywords must be a list[str]")

        return Card(
            id=int(raw["id"]),
            arcana=arcana,
            number=raw.get("number"),
            suit=suit,
            rank=raw.get("rank"),
            image_path=str(raw["image_path"]),
            name=str(raw["name"]),
            keywords=tuple(keywords),
            meaning_upright=str(raw["meaning_upright"]),
            meaning_reversed=str(raw["meaning_reversed"]),
            archetype=raw.get("archetype"),
            description=raw.get("description"),
        )


def validate_cards(cards: list[Card]) -> None:
    if len(cards) != 78:
        raise ValueError(f"Expected 78 cards, got {len(cards)}")

    ids = [c.id for c in cards]
    if sorted(ids) != list(range(0, 78)):
        raise ValueError("id must be a unique continuous range 0..77")

