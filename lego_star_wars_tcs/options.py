import itertools
from dataclasses import dataclass

from Options import PerGameCommonOptions, StartInventoryPool, Choice, Range


class StartingLevel(Choice):
    """Choose the starting level. The Episode the starting level belongs to will be accessible from the start.

    Due to the character requirements being shared between some levels, some starting levels will result in additional
    levels being open from the start:

    Starting with 1-1 will also open 1-6.
    Starting with 1-2 will also open 1-6.
    Starting with 1-3 will also open 1-6.
    Starting with 1-5 will also open 1-6.
    Starting with 3-2 will also open 3-6.
    Starting with 4-3 will also open 4-2."""
    display_name = "Starting Level"
    # todo: Try setting the attributes for specific levels such that they use 1-1 format rather than 1_1.
    # Variable names cannot use hyphens, so the options for specific levels are set programmatically.
    # option_1-1 = 11
    # option_1-2 = 12
    # etc.
    locals().update({f"option_{episode}-{chapter}": int(f"{episode}{chapter}")
                     for episode, chapter in itertools.product(range(1, 7), range(1, 7))})
    # option_1_1 = 11
    # option_1_2 = 12
    # option_1_3 = 13
    # option_1_4 = 14
    # option_1_5 = 15
    # option_1_6 = 16
    # option_2_1 = 21
    # option_2_2 = 22
    # option_2_3 = 23
    # option_2_4 = 24
    # option_2_5 = 25
    # option_2_6 = 26
    # option_3_1 = 31
    # option_3_2 = 32
    # option_3_3 = 33
    # option_3_4 = 34
    # option_3_5 = 35
    # option_3_6 = 36
    # option_4_1 = 41
    # option_4_2 = 42
    # option_4_3 = 43
    # option_4_4 = 44
    # option_4_5 = 45
    # option_4_6 = 46
    # option_5_1 = 51
    # option_5_2 = 52
    # option_5_3 = 53
    # option_5_4 = 54
    # option_5_5 = 55
    # option_5_6 = 56
    # option_6_1 = 61
    # option_6_2 = 62
    # option_6_3 = 63
    # option_6_4 = 64
    # option_6_5 = 65
    # option_6_6 = 66
    option_random_level = -1
    option_random_non_vehicle_level = -2
    option_random_vehicle_level = -3
    option_random_episode_1 = 1
    option_random_episode_2 = 2
    option_random_episode_3 = 3
    option_random_episode_4 = 4
    option_random_episode_5 = 5
    option_random_episode_6 = 6
    default = 11


class RandomStartingLevelMaxStartingCharacters(Range):
    """Specify the maximum number of starting characters allowed when picking a random starting level.

    1 Character: 1-4, 2-1, 2-5, 5-1 (all vehicle levels)
    2 Characters: 1-6, 2-2, 3-1 (v), 3-3, 3-4, 3-5, 3-6, 4-6 (v), 5-3 (v), 5-5, 6-3, 6-5, 6-6 (v)
    3 Characters: 1-1, 1-2, 2-6
    4 Characters: 1-3, 2-3, 2-4, 3-2, 4-2, 5-2, 5-4, 5-6
    5 Characters: 4-1
    6 Characters: 1-5, 4-3, 4-4, 4-5, 6-1, 6-4
    7 Characters: 6-2"""
    display_name = "Random Starting Level Max Starting Characters",
    default = 7
    range_start = 1
    range_end = 7


class MostExpensivePurchaseWithNoMultiplier(Range):
    """The most expensive individual purchase the player can be expected to make without any score multipliers, in
    thousands of Studs.

    The logical requirements for expensive purchases will scale with this value. For example, if a purchase of up to
    100,000 Studs is expected with no score multipliers, then a purchase of 100,001 up to 200,000 Studs is expected with
    a score multiplier of 2x.

    The most expensive purchase is "Score x10", which costs 20 million studs."""
    display_name = "Most Expensive Purchase Without Score Multipliers"
    default = 100
    range_start = 50
    range_end = 20000


class ReceivedItemMessages(Choice):
    """
    Determines whether an in-game notification is displayed when receiving an item.

    Note: Dying while a message is displayed results in losing studs as normal, but the lost studs do not drop, so
    cannot be recovered.
    Note: Collecting studs while a message is displayed plays the audio for collecting Blue/Purple studs, but this has
    no effect on the received value of the studs collected.

    - All: Every item shows a message
    - None: All items are received silently.
    """
    display_name = "Received Item Messages"
    default = 0
    option_all = 0
    option_none = 1
    # option_progression = 2  # Not Yet Implemented


class CheckedLocationMessages(Choice):
    """
    Determines whether an in-game notification is displayed when checking a location.

    Note: Dying while a message is displayed results in losing studs as normal, but the lost studs do not drop, so
    cannot be recovered.
    Note: Collecting studs while a message is displayed plays the audio for collecting Blue/Purple studs, but this has
    no effect on the received value of the studs collected.

    - All: Every checked location shows a message
    - None: No checked locations show a message
    """
    display_name = "Checked Location Messages"
    default = 0
    option_all = 0
    option_none = 1


@dataclass
class LegoStarWarsTCSOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    received_item_messages: ReceivedItemMessages
    checked_location_messages: CheckedLocationMessages
    # Future options, not implemented yet.
    # starting_level: StartingLevel
    # random_starting_level_max_starting_characters: RandomStartingLevelMaxStartingCharacters
    # most_expensive_purchase_with_no_multiplier: MostExpensivePurchaseWithNoMultiplier
