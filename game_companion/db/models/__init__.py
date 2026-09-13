"""All ORM models. Importing this package registers every table on Base.metadata."""

from game_companion.db.models.builds import BuildGearSlot, CharacterBuild
from game_companion.db.models.codes import PlayerCodeState, RedeemCode
from game_companion.db.models.equipment import EquipmentItem
from game_companion.db.models.gear import GearItem
from game_companion.db.models.history import CombatResult, TrainingGoal, TrainingIssue
from game_companion.db.models.imports_ import ScreenshotImport
from game_companion.db.models.misc import AuditResult, Encounter, EncounterSlot, Recommendation
from game_companion.db.models.profiles import SCOPE_GLOBAL, PlayerPreference, PlayerProfile
from game_companion.db.models.research import ChangeRecord, ResearchClaim, ResearchSource
from game_companion.db.models.resources import Resource, ResourcePlanEntry
from game_companion.db.models.roster import Character, CharacterSkill
from game_companion.db.models.teams import Team, TeamMember

__all__ = [
    "PlayerProfile",
    "PlayerPreference",
    "SCOPE_GLOBAL",
    "Character",
    "CharacterSkill",
    "EquipmentItem",
    "GearItem",
    "CharacterBuild",
    "BuildGearSlot",
    "Team",
    "TeamMember",
    "Resource",
    "ResourcePlanEntry",
    "CombatResult",
    "TrainingIssue",
    "TrainingGoal",
    "RedeemCode",
    "PlayerCodeState",
    "ResearchSource",
    "ResearchClaim",
    "ChangeRecord",
    "ScreenshotImport",
    "Encounter",
    "EncounterSlot",
    "Recommendation",
    "AuditResult",
]
