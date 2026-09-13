"""ZZZ terminology: how generic core nouns map to Zenless Zone Zero nouns."""

from __future__ import annotations

# generic concept -> ZZZ display name
ZZZ_TERMS = {
    "character": "Agent",
    "equipment": "W-Engine",
    "gear": "Drive Disc",
    "duplication": "Mindscape",
    "special_progression": "Core Skill",
    "team": "Team",
    "build": "Build",
}

# ZZZ skill keys -> in-game names (keys are stable slugs used in the DB)
SKILL_NAMES = {
    "basic_attack": "Basic Attack",
    "dodge": "Dodge",
    "assist": "Assist",
    "special_attack": "Special Attack",
    "chain_attack": "Chain Attack",
    "core_skill": "Core Skill",
}

ATTRIBUTE_NAMES = {
    "physical": "Physical",
    "fire": "Fire",
    "ice": "Ice",
    "electric": "Electric",
    "ether": "Ether",
}

SPECIALTY_NAMES = {
    "attack": "Attack",
    "stun": "Stun",
    "anomaly": "Anomaly",
    "support": "Support",
    "defense": "Defense",
}
