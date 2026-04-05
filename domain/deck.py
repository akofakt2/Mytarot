from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Orientation = Literal["upright", "reversed"]


@dataclass(slots=True)
class Deck:
    """
    `back` – názov súboru zadnej strany (rovnaký adresár ako `image_path` kariet, napr. `back.png`).
    `images_dir` – absolútna cesta k tomu adresáru (napr. .../app/static/cards/default).
    """

    back: str
    images_dir: Path
    order: list[int] = field(default_factory=list)
    orientations: dict[int, Orientation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Deck.validate_back(self.back, self.images_dir)

    @staticmethod
    def validate_back(back: str, images_dir: Path) -> None:
        path = images_dir / back
        if not path.is_file():
            raise FileNotFoundError(f"Chýba obrázok zadnej strany karty: {path}")

    def reset(self, card_ids: list[int]) -> None:
        self.order = list(card_ids)
        self.orientations = {card_id: "upright" for card_id in self.order}

    def init(self, card_ids: list[int]) -> None:
        self.reset(card_ids)

    def shuffle(self) -> None:
        random.shuffle(self.order)
        self.orientations = {
            card_id: ("reversed" if random.random() < 0.5 else "upright") for card_id in self.order
        }

    def draw(self, n: int) -> list[tuple[int, Orientation]]:
        if n < 0:
            raise ValueError("n must be >= 0")

        drawn: list[tuple[int, Orientation]] = []
        for _ in range(min(n, len(self.order))):
            card_id = self.order.pop(0)
            orientation: Literal["upright", "reversed"] = self.orientations.get(card_id, "upright")
            drawn.append((card_id, orientation))
        return drawn
