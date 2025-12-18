from typing import TYPE_CHECKING

from .universal_tracker import resolve_universal_tracker_options
from .normal import resolve_normal_options
from ..options import MinikitGoalAmount


if TYPE_CHECKING:
    from .. import LegoStarWarsTCSWorld
else:
    LegoStarWarsTCSWorld = object


__all__ = [
    "resolve_options"
]


def _resolve_common_options(world: LegoStarWarsTCSWorld):
    """Called after resolving specific options for normal vs Universal Tracker generation."""
    # Calculate goal_minikit_count when set to a percentage of the available minikits.
    if world.options.minikit_goal_amount == MinikitGoalAmount.special_range_names["use_percentage_option"]:
        world.goal_minikit_count = max(1, round(
            world.available_minikits * world.options.minikit_goal_amount_percentage / 100))
    else:
        world.goal_minikit_count = world.options.minikit_goal_amount.value

    # Only whole bundles are counted for logic, so any partial bundles require an extra whole bundle to goal.
    bundle_size = world.options.minikit_bundle_size
    world.goal_minikit_bundle_count = (world.goal_minikit_count // bundle_size
                                       + (world.goal_minikit_count % bundle_size != 0))

    world.prog_useful_level_access_threshold_count = int(world.PROG_USEFUL_LEVEL_ACCESS_THRESHOLD_PERCENT
                                                         * len(world.enabled_chapters))

    # enabled_chapters should always contain enabled_non_goal_chapters.
    assert world.enabled_non_goal_chapters <= world.enabled_chapters
    assert 0 <= len(world.enabled_chapters) - len(world.enabled_non_goal_chapters) <= 1
    assert world.enabled_chapters_with_locations <= world.enabled_chapters
    assert world.goal_chapter is None or world.goal_chapter in world.enabled_chapters


def resolve_options(world: LegoStarWarsTCSWorld):
    # Universal Tracker Support
    if passthrough := getattr(world.multiworld, "re_gen_passthrough", {}).get(world.game):
        resolve_universal_tracker_options(world, passthrough)
    else:
        resolve_normal_options(world)
    _resolve_common_options(world)

    # # Debug check to help with comparing passthrough values
    # for k, v in vars(world).items():
    #     print(f"{k}: {v}")
    #
    # if not passthrough:
    #     world.multiworld.re_gen_passthrough = {world.game: world.fill_slot_data()}
    #     # Recursive call, but with passthrough this time.
    #     world.generate_early()
    # else:
    #     # No recursive call the second time around.
    #     return
