"""Japan species allow-list loading and logit masking."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPECIES_CSV = PACKAGE_ROOT / "data" / "species" / "species_japan.csv"
DEFAULT_GARDEN_CSV = PACKAGE_ROOT / "data" / "species" / "species_japan_garden.csv"
DEFAULT_LABELS = PACKAGE_ROOT / "data" / "models" / "labels.txt"


@dataclass(frozen=True)
class Species:
    perch_index: int
    ebird_code: str
    scientific_name: str
    scientific_name_perch: str
    wamei: str
    english_name: str
    in_garden: bool


def load_species_csv(path: str | Path) -> list[Species]:
    path = Path(path)
    rows: list[Species] = []
    with path.open(encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        cols = {name: i for i, name in enumerate(header)}
        for line in f:
            if not line.strip():
                continue
            parts = _split_csv_line(line.strip())
            rows.append(
                Species(
                    perch_index=int(parts[cols["perch_index"]]),
                    ebird_code=parts[cols["ebird_code"]],
                    scientific_name=parts[cols["scientific_name"]],
                    scientific_name_perch=parts[cols.get("scientific_name_perch", cols["scientific_name"])],
                    wamei=parts[cols["wamei"]],
                    english_name=parts[cols["english_name"]],
                    in_garden=parts[cols.get("in_garden", -1)] in ("1", "true", "True", "yes")
                    if "in_garden" in cols
                    else False,
                )
            )
    return rows


def _split_csv_line(line: str) -> list[str]:
    """Minimal CSV split supporting quoted fields."""
    out: list[str] = []
    cur: list[str] = []
    in_q = False
    for ch in line:
        if ch == '"':
            in_q = not in_q
            continue
        if ch == "," and not in_q:
            out.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    out.append("".join(cur))
    return out


def load_full_labels(path: str | Path = DEFAULT_LABELS) -> list[str]:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


class SpeciesMask:
    """Restrict Perch logits to an allow-list of perch indices."""

    def __init__(self, species: list[Species]):
        if not species:
            raise ValueError("species list is empty")
        self.species = species
        self.indices = np.array([s.perch_index for s in species], dtype=np.int32)
        self.by_index = {s.perch_index: s for s in species}

    @classmethod
    def from_csv(cls, path: str | Path, garden_only: bool = False) -> "SpeciesMask":
        rows = load_species_csv(path)
        if garden_only:
            rows = [r for r in rows if r.in_garden]
        return cls(rows)

    def masked_logits(self, logits: np.ndarray) -> np.ndarray:
        return logits[self.indices]

    def topk(
        self,
        logits: np.ndarray,
        k: int = 5,
        temperature: float = 1.0,
        *,
        mode: str = "full_softmax",
    ) -> list[tuple[Species, float, float]]:
        """Return top-k (species, logit, score) restricted to the allow-list.

        mode:
          - full_softmax: softmax over *all* logits, then keep allow-list rows
            (recommended; matches Perch training which used a global softmax).
          - masked_softmax: renormalize softmax only on the allow-list (can
            over-confidently force a garden species even when none is present).
          - logit: rank by raw logit within the allow-list.
        """
        logits = np.asarray(logits, dtype=np.float64)
        t = max(temperature, 1e-6)
        if mode == "full_softmax":
            shifted = logits / t
            shifted -= shifted.max()
            probs_full = np.exp(shifted)
            probs_full /= probs_full.sum()
            scores = probs_full[self.indices]
            masked = logits[self.indices]
        elif mode == "masked_softmax":
            masked = logits[self.indices]
            shifted = masked / t
            shifted -= shifted.max()
            exp = np.exp(shifted)
            scores = exp / exp.sum()
        elif mode == "logit":
            masked = logits[self.indices]
            scores = masked
        else:
            raise ValueError(f"unknown mode: {mode}")
        order = np.argsort(-scores)[:k]
        return [
            (self.species[int(i)], float(masked[int(i)]), float(scores[int(i)]))
            for i in order
        ]
