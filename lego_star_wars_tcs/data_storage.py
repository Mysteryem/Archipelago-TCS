import logging
import re

_KEY_PATTERN = re.compile(r"^(tcs_.+_)\d+_\d+$")

DATA_STORAGE_KEY_SUFFIX = "{team}_{player}"

COMPLETED_FREE_PLAY_KEY_PREFIX = "tcs_completed_free_play_"
COMPLETED_TRUE_JEDI_KEY_PREFIX = "tcs_completed_true_jedi_"
COMPLETED_10_MINIKITS_KEY_PREFIX = "tcs_completed_10_minikits_"
COMPLETED_BONUSES_KEY_PREFIX = "tcs_completed_bonuses_"
COLLECTED_POWER_BRICKS_KEY_PREFIX = "tcs_collected_power_bricks_"
# By writing whether the minikit goal has been submitted to datastorage, only one player in same-slot co-op needs to
# submit the minikits to the minikit display in the cantina's junkyard.
MINIKIT_GOAL_SUBMITTED_PREFIX = "tcs_minikit_goal_submitted_"

COMPLETED_FREE_PLAY_KEY = COMPLETED_FREE_PLAY_KEY_PREFIX + DATA_STORAGE_KEY_SUFFIX
COMPLETED_TRUE_JEDI_KEY = COMPLETED_TRUE_JEDI_KEY_PREFIX + DATA_STORAGE_KEY_SUFFIX
COMPLETED_10_MINIKITS_KEY = COMPLETED_10_MINIKITS_KEY_PREFIX + DATA_STORAGE_KEY_SUFFIX
COMPLETED_BONUSES_KEY = COMPLETED_BONUSES_KEY_PREFIX + DATA_STORAGE_KEY_SUFFIX
COLLECTED_POWER_BRICKS_KEY = COLLECTED_POWER_BRICKS_KEY_PREFIX + DATA_STORAGE_KEY_SUFFIX
MINIKIT_GOAL_SUBMITTED_KEY = MINIKIT_GOAL_SUBMITTED_PREFIX + DATA_STORAGE_KEY_SUFFIX


def unformat_datastorage_key(key: str) -> str:
    """UT passes in the keys with team and player already formatted, but UT provides no access to the team and player at
    UT generation time, meaning that it is not possible to match the full key directly.

    Instead, 'unformat' the key by finding and removing the formatted suffix, and replace it with the original suffix.

    "tcs_completed_free_play_0_1" -> "tcs_completed_free_play_" + "{team}_{player}"
    """
    match = _KEY_PATTERN.fullmatch(key)
    if not match:
        logging.error("Invalid data storage key: %s", key)
        return key
    else:
        # Put the original suffix back on.
        return match.group(1) + DATA_STORAGE_KEY_SUFFIX


assert all(
    unformat_datastorage_key(key.format(team=0, player=1)) == key for key in (
        COMPLETED_FREE_PLAY_KEY,
        COMPLETED_TRUE_JEDI_KEY,
        COMPLETED_10_MINIKITS_KEY,
        COMPLETED_BONUSES_KEY,
        COLLECTED_POWER_BRICKS_KEY,
        MINIKIT_GOAL_SUBMITTED_KEY,
    )
)
