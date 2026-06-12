"""Declarative skill definitions.

Adding a new skill only requires a new entry in SKILLS. The engine reads
skill points through Team helpers, so no engine change is needed as long
as the effect is wired to an existing multiplier or to a generic hook.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDef:
    key: str
    label: str          # shown in the UI, French
    description: str    # shown in the UI, French
    kind: str           # "base" or "advanced"
    min_level: int = 1
    max_points: int = 10


SKILLS: dict[str, SkillDef] = {
    "exploration": SkillDef(
        key="exploration",
        label="Exploration",
        description="Vitesse de déplacement de toutes les unités.",
        kind="base",
    ),
    "combat": SkillDef(
        key="combat",
        label="Combat",
        description="Dégâts infligés et points de vie des unités.",
        kind="base",
    ),
    "recolte": SkillDef(
        key="recolte",
        label="Récolte",
        description="Vitesse de collecte sur les gisements.",
        kind="base",
    ),
    "transport": SkillDef(
        key="transport",
        label="Transport",
        description="Vitesse de ramassage et capacité de transport.",
        kind="base",
    ),
    "construction": SkillDef(
        key="construction",
        label="Construction",
        description="Vitesse de construction des bâtiments.",
        kind="base",
    ),
    "tradeur": SkillDef(
        key="tradeur",
        label="Tradeur",
        description="Meilleurs taux de revente au marché.",
        kind="base",
    ),
    "science": SkillDef(
        key="science",
        label="Science",
        description="Débloque la tour de garde, bâtiment défensif.",
        kind="advanced",
        min_level=2,
        max_points=3,
    ),
    "mecanique": SkillDef(
        key="mecanique",
        label="Mécanique",
        description="Réparation automatique des unités près des bâtiments.",
        kind="advanced",
        min_level=3,
        max_points=5,
    ),
    "logistique": SkillDef(
        key="logistique",
        label="Logistique",
        description="Routes plus efficaces, transporteurs plus rapides.",
        kind="advanced",
        min_level=4,
        max_points=5,
    ),
    "espionnage": SkillDef(
        key="espionnage",
        label="Espionnage",
        description="Révèle ponctuellement des zones adverses.",
        kind="advanced",
        min_level=5,
        max_points=3,
    ),
}


def unlocked_skills(level: int) -> list[SkillDef]:
    """Return skill definitions available at the given player level."""
    return [s for s in SKILLS.values() if s.min_level <= level]


def empty_allocation(level: int) -> dict[str, int]:
    return {s.key: 0 for s in unlocked_skills(level)}
