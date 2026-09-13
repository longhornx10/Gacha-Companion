"""Multi-team allocation optimizer (Milestone 15).

Generic: ``optimize_team_allocation`` assigns DISTINCT characters to N
encounter slots, maximizing a global objective. It is the core's answer to
"agent X can't be on two teams at once" — moving a strong character between
teams is evaluated by global gain, not per-slot greed.

Deterministic exhaustive branch & bound over precomputed team scores; the
feasible size (roster <= ~15 with 3-4 slots) is enforced by caller input caps.
All scores come from the caller-supplied scoring functions (adapter hooks +
scoring.py components) and are labeled HEURISTIC — no fabricated percentages.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import combinations

TeamKey = tuple[str, ...]


@dataclass
class Allocation:
    total: float
    teams: list[dict] = field(default_factory=list)  # [{slot_index, members, score, components}]

    def assignment(self) -> dict[int, TeamKey]:
        return {t["slot_index"]: tuple(t["members"]) for t in self.teams}


@dataclass
class AllocationResult:
    feasible: bool
    best: Allocation | None
    alternatives: list[Allocation]
    greedy: Allocation | None
    explanation: list[str]
    evaluated_team_combos: int


def optimize_team_allocation(
    roster: Sequence[str],
    slot_count: int,
    team_size: int,
    team_score_fn: Callable[[Sequence[str], int], tuple[float, list[dict]]],
    *,
    max_roster: int = 15,
) -> AllocationResult:
    """Find the best disjoint assignment of characters to slots.

    ``team_score_fn(members, slot_index)`` must return (score, components)
    for any subset of distinct characters; it must be deterministic.
    """
    roster = sorted(set(roster))
    if len(roster) < team_size * slot_count:
        return AllocationResult(
            feasible=False,
            best=None,
            alternatives=[],
            greedy=None,
            explanation=[
                f"need at least {team_size * slot_count} owned characters to field "
                f"{slot_count} teams of {team_size}; got {len(roster)}"
            ],
            evaluated_team_combos=0,
        )
    if len(roster) > max_roster:
        roster = roster[:max_roster]  # documented deterministic cap

    # Precompute team scores per slot.
    per_slot_scores: list[dict[TeamKey, tuple[float, list[dict]]]] = []
    combo_count = 0
    for slot in range(slot_count):
        table: dict[TeamKey, tuple[float, list[dict]]] = {}
        for combo in combinations(roster, team_size):
            table[combo] = team_score_fn(combo, slot)
        per_slot_scores.append(table)
        combo_count += len(table)

    # Sort combos per slot by (-score, combo) for deterministic search order.
    ordered: list[list[tuple[float, TeamKey, list[dict]]]] = []
    for table in per_slot_scores:
        entries = sorted(
            ((score, combo, comps) for combo, (score, comps) in table.items()),
            key=lambda e: (-e[0], e[1]),
        )
        ordered.append(entries)

    best_total = float("-inf")
    best_alloc: Allocation | None = None
    top: list[Allocation] = []  # best-first bounded list

    def search(slot: int, used: frozenset[str], acc_total: float, chosen: list[tuple[int, TeamKey, float, list[dict]]]) -> None:
        nonlocal best_total, best_alloc, top
        if slot == slot_count:
            alloc = Allocation(
                total=round(acc_total, 4),
                teams=[
                    {"slot_index": s, "members": list(members), "score": round(score, 2), "components": comps}
                    for s, members, score, comps in chosen
                ],
            )
            if best_alloc is None or acc_total > best_total + 1e-9:
                best_total = acc_total
                best_alloc = alloc
            top.append(alloc)
            top.sort(key=lambda a: -a.total)
            del top[3:]
            return
        # Upper bound: current + best remaining scores ignoring overlap.
        bound = acc_total
        for s in range(slot, slot_count):
            if ordered[s]:
                bound += ordered[s][0][0]
        if best_alloc is not None and bound <= best_total + 1e-9:
            return
        for score, combo, comps in ordered[slot]:
            if any(c in used for c in combo):
                continue
            # Per-slot bound for this slot's choice.
            if best_alloc is not None:
                rest_bound = acc_total + score
                for s in range(slot + 1, slot_count):
                    if ordered[s]:
                        rest_bound += ordered[s][0][0]
                if rest_bound <= best_total + 1e-9:
                    continue
            chosen.append((slot, combo, score, comps))
            search(slot + 1, used | set(combo), acc_total + score, chosen)
            chosen.pop()

    search(0, frozenset(), 0.0, [])

    greedy = _greedy_allocation(ordered, slot_count, team_size)

    explanation: list[str] = []
    if best_alloc and greedy and best_alloc.total > greedy.total + 1e-9:
        explanation.append(
            f"global optimization gains +{best_alloc.total - greedy.total:.2f} over greedy "
            "per-slot picks: strong characters are worth more where their absence hurts least."
        )
        explanation.extend(_swap_explanations(greedy.assignment(), best_alloc.assignment()))
    elif best_alloc and greedy:
        explanation.append(
            "greedy per-slot picking already matches the global optimum for this roster."
        )

    alternatives = [a for a in top if best_alloc is None or a is not best_alloc][:2]
    return AllocationResult(
        feasible=best_alloc is not None,
        best=best_alloc,
        alternatives=alternatives,
        greedy=greedy,
        explanation=explanation,
        evaluated_team_combos=combo_count,
    )


def _greedy_allocation(
    ordered: list[list[tuple[float, TeamKey, list[dict]]]], slot_count: int, team_size: int
) -> Allocation | None:
    used: set[str] = set()
    chosen: list[tuple[int, TeamKey, float, list[dict]]] = []
    total = 0.0
    for slot in range(slot_count):
        for score, combo, comps in ordered[slot]:
            if any(c in used for c in combo):
                continue
            used |= set(combo)
            total += score
            chosen.append((slot, combo, score, comps))
            break
    if len(chosen) < slot_count:
        return None
    return Allocation(
        total=round(total, 4),
        teams=[
            {"slot_index": s, "members": list(members), "score": round(score, 2), "components": comps}
            for s, members, score, comps in chosen
        ],
    )


def _swap_explanations(greedy: dict[int, TeamKey], best: dict[int, TeamKey]) -> list[str]:
    lines: list[str] = []
    for slot in sorted(best):
        if greedy.get(slot) != best[slot]:
            moved_in = sorted(set(best[slot]) - set(greedy.get(slot, ())))
            moved_out = sorted(set(greedy.get(slot, ())) - set(best[slot]))
            if moved_in or moved_out:
                lines.append(
                    f"slot {slot + 1}: now fields {', '.join(best[slot])}"
                    + (f" (instead of {', '.join(moved_out)} elsewhere)" if moved_out else "")
                    + (f"; {', '.join(moved_in)} moved here" if moved_in else "")
                )
    return lines
