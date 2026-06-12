"""Combat resolution: damage application between units and buildings."""
from __future__ import annotations

from .entities import Building, Unit

ATTACK_PERIOD = 6  # ticks between two attacks of the same unit


def in_melee_range(ax: int, ay: int, bx: int, by: int) -> bool:
    return max(abs(ax - bx), abs(ay - by)) <= 1


def compute_damage(attacker: Unit, damage_mult: float) -> int:
    return max(1, round(attacker.spec.damage * damage_mult))


def attack(attacker: Unit, target: Unit | Building, damage_mult: float) -> int:
    """Apply one attack, return the damage dealt.

    The caller is responsible for range checks, cooldowns and removing
    dead entities (the game loop owns entity collections).
    """
    dmg = compute_damage(attacker, damage_mult)
    target.hp -= dmg
    attacker.attack_cooldown = ATTACK_PERIOD
    return dmg
