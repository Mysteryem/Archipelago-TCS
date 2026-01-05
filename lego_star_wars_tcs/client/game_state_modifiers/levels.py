import logging
from typing import AbstractSet, Callable

from .text_replacer import TextId
from ..events import subscribe_event, OnAreaChangeEvent, OnReceiveSlotDataEvent, OnGameWatcherTickEvent
from ..common import ClientComponent, UintField
from ..common_addresses import (
    OPENED_MENU_DEPTH_ADDRESS,
    CURRENT_P_AREA_DATA_ADDRESS,
    ChapterDoorGameMode,
    IS_CHARACTER_SWAPPING_ENABLED,
    ChallengeMode,
    AREA_DATA_ID,
)
from ..type_aliases import TCSContext, AreaId
from ...items import ITEM_DATA_BY_NAME, ITEM_DATA_BY_ID, GenericItemData
from ...levels import (
    ChapterArea,
    CHAPTER_AREAS,
    SHORT_NAME_TO_CHAPTER_AREA,
    AREA_ID_TO_CHAPTER_AREA,
    DIFFICULT_OR_IMPOSSIBLE_TRUE_JEDI,
)
from ... import options


debug_logger = logging.getLogger("TCS Debug")

ALL_CHAPTER_AREA_IDS_SET = frozenset({area.area_id for area in CHAPTER_AREAS})

# Changes according to what Area door the player is stand in front of. It is 0xFF while in the rest of the Cantina, away
# from an Area door.
CURRENT_AREA_DOOR_ADDRESS = 0x8795A0

AREA_DATA_STORY_TRUE_JEDI_REQUIREMENT = UintField(0x8c)
AREA_DATA_FREE_PLAY_TRUE_JEDI_REQUIREMENT = UintField(0x90)

# For simplicity, the client locks the Goal Chapter by requiring a fake item that does not exist, so that no special
# handling is needed for unlocking the Goal Chapter.
_ITEM_DATA_BY_ID_PLUS_GOAL_SPECIAL = dict(ITEM_DATA_BY_ID)
_SUB_GOAL_SPECIAL_ID = 999_999_999
assert _SUB_GOAL_SPECIAL_ID not in _ITEM_DATA_BY_ID_PLUS_GOAL_SPECIAL, (
    f"The special item ID, {_SUB_GOAL_SPECIAL_ID} for all sub-goal completion already exists as a real item:"
    f" {_ITEM_DATA_BY_ID_PLUS_GOAL_SPECIAL[_SUB_GOAL_SPECIAL_ID]}")
_ITEM_DATA_BY_ID_PLUS_GOAL_SPECIAL[_SUB_GOAL_SPECIAL_ID] = GenericItemData(_SUB_GOAL_SPECIAL_ID,
                                                                           "_INTERNAL_ALL_SUB_GOALS_COMPLETE")


class UnlockedChapterManager(ClientComponent):
    ap_item_id_to_dependent_game_chapters: dict[int, list[str]]
    remaining_chapter_item_requirements: dict[str, set[int]]

    unlocked_chapters_per_episode: dict[int, set[AreaId]]
    should_unlock_all_episodes_shop_slots: Callable[[TCSContext], bool] = staticmethod(lambda _ctx: False)

    enabled_chapter_area_ids: set[int]

    easy_true_jedi: bool = False
    scale_true_jedi_with_score_multipliers: bool = False
    goal_chapter: str = ""
    goal_chapter_area_id: int = -1

    last_area_door: ChapterArea | None = None

    def __init__(self) -> None:
        self.ap_item_id_to_dependent_game_chapters = {}
        self.remaining_chapter_item_requirements = {}
        self.unlocked_chapters_per_episode = {}
        self.enabled_chapter_area_ids = set()

    @subscribe_event
    def init_from_slot_data(self, event: OnReceiveSlotDataEvent) -> None:
        slot_data = event.slot_data
        ctx = event.context

        enabled_chapters = slot_data["enabled_chapters"]
        enabled_episodes = slot_data["enabled_episodes"]
        episode_unlock_requirement = slot_data["episode_unlock_requirement"]
        all_episodes_character_purchase_requirements = slot_data["all_episodes_character_purchase_requirements"]
        all_episodes_purchases_enabled = bool(slot_data["enable_all_episodes_purchases"])

        # In older multiworlds, easier true jedi is never enabled because the option did not exist.
        if event.generator_version < (1, 2, 0):
            self.easy_true_jedi = False
        else:
            self.easy_true_jedi = slot_data["easier_true_jedi"]
        self._set_current_area_true_jedi_requirement(ctx)

        # In older multiworlds, there is no option to scale True Jedi with score multipliers, so it is always disabled
        # in those versions.
        if event.generator_version < (1, 2, 0):
            self.scale_true_jedi_with_score_multipliers = False
        else:
            self.scale_true_jedi_with_score_multipliers = bool(slot_data["scale_true_jedi_with_score_multipliers"])

        # In older multiworlds, chapters were always unlocked through Story Characters.
        if event.generator_version < (1, 3, 0):
            chapter_unlock_requirement = options.ChapterUnlockRequirement.option_story_characters
        else:
            chapter_unlock_requirement = slot_data["chapter_unlock_requirement"]

        num_enabled_episodes = len(enabled_episodes)

        self.enabled_chapter_area_ids = {SHORT_NAME_TO_CHAPTER_AREA[chapter_shortname].area_id
                                         for chapter_shortname in enabled_chapters}

        if len(enabled_chapters) == 1:
            chapters_text = enabled_chapters[0]
        else:
            sorted_chapters = sorted(enabled_chapters)
            chapters_text = ", ".join(sorted_chapters[:-1])
            chapters_text += f" and {sorted_chapters[-1]}"
        chapters_info_text = f"Enabled Chapters for this slot: {chapters_text}"
        ctx.text_replacer.write_custom_string(TextId.SHOP_UNLOCKED_HINT_1, chapters_info_text)

        # Set 'All Episodes' unlock requirement.
        if not all_episodes_purchases_enabled:
            self.should_unlock_all_episodes_shop_slots = UnlockedChapterManager.should_unlock_all_episodes_shop_slots
        else:
            tokens = options.AllEpisodesCharacterPurchaseRequirements.option_episodes_tokens
            unlocks = options.AllEpisodesCharacterPurchaseRequirements.option_episodes_unlocked
            if all_episodes_character_purchase_requirements == tokens:
                if event.generator_version < (1, 2, 0):
                    # Old versions unlock by having as many tokens as the number of enabled episodes.
                    # The tokens were previously called "All Episodes Token".
                    self.should_unlock_all_episodes_shop_slots = (
                        lambda ctx: ctx.acquired_generic.episode_completion_token_count == num_enabled_episodes)
                else:
                    self.should_unlock_all_episodes_shop_slots = (
                        lambda ctx: ctx.acquired_generic.episode_completion_token_count >= 6)
            elif all_episodes_character_purchase_requirements == unlocks:
                self.should_unlock_all_episodes_shop_slots = (
                    lambda ctx: len(ctx.acquired_generic.received_episode_unlocks) == num_enabled_episodes)
            else:
                self.should_unlock_all_episodes_shop_slots = (
                    UnlockedChapterManager.should_unlock_all_episodes_shop_slots)
                raise RuntimeError(f"Unexpected 'All Episodes' character purchase requirement:"
                                   f" {all_episodes_character_purchase_requirements}")

        self.unlocked_chapters_per_episode = {i: set() for i in enabled_episodes}
        item_id_to_chapter_area_short_name: dict[int, list[str]] = {}
        remaining_chapter_item_requirements: dict[str, set[int]] = {}

        if goal_chapter := slot_data.get("goal_chapter"):
            # Add the requirement for the fake sub-goals item to the Goal Chapter so that it will only unlock once all
            # sub-goals have been completed.
            item_id_to_chapter_area_short_name[_SUB_GOAL_SPECIAL_ID] = [goal_chapter]
            remaining_chapter_item_requirements[goal_chapter] = {_SUB_GOAL_SPECIAL_ID}
            self.goal_chapter = goal_chapter
            self.goal_chapter_area_id = SHORT_NAME_TO_CHAPTER_AREA[goal_chapter].area_id
            self.enabled_chapter_area_ids.add(self.goal_chapter_area_id)

        for chapter_area in CHAPTER_AREAS:
            if chapter_area.area_id not in self.enabled_chapter_area_ids:
                continue

            item_requirements: list[str]
            if chapter_unlock_requirement == options.ChapterUnlockRequirement.option_story_characters:
                item_requirements = list(chapter_area.character_requirements)
            elif chapter_unlock_requirement == options.ChapterUnlockRequirement.option_chapter_item:
                item_requirements = [f"{chapter_area.short_name} Unlock"]
            else:
                raise ValueError(f"Unexpected ChapterUnlockRequirement with value {chapter_unlock_requirement}")

            episode = chapter_area.episode
            if episode_unlock_requirement == options.EpisodeUnlockRequirement.option_episode_item:
                item_requirements.append(f"Episode {episode} Unlock")
            elif episode_unlock_requirement == options.EpisodeUnlockRequirement.option_open:
                pass
            else:
                raise RuntimeError(f"Unexpected EpisodeUnlockRequirement: {episode_unlock_requirement}")

            code_requirements = set()
            for item_name in item_requirements:
                item_code = ITEM_DATA_BY_NAME[item_name].code
                assert item_code != -1
                item_id_to_chapter_area_short_name.setdefault(item_code, []).append(chapter_area.short_name)
                code_requirements.add(item_code)
            remaining_chapter_item_requirements.setdefault(chapter_area.short_name, set()).update(code_requirements)

        self.ap_item_id_to_dependent_game_chapters = item_id_to_chapter_area_short_name
        self.remaining_chapter_item_requirements = remaining_chapter_item_requirements

    def on_sub_goal_completion(self, ctx: TCSContext):
        self.on_character_or_chapter_or_episode_unlocked(ctx, _SUB_GOAL_SPECIAL_ID)

    def on_character_or_chapter_or_episode_unlocked(self, ctx: TCSContext, ap_item_id: int):
        dependent_chapters = self.ap_item_id_to_dependent_game_chapters.get(ap_item_id)
        if dependent_chapters is None:
            return

        for dependent_area_short_name in dependent_chapters:
            remaining_requirements = self.remaining_chapter_item_requirements[dependent_area_short_name]
            assert remaining_requirements
            assert ap_item_id in remaining_requirements, (
                f"{_ITEM_DATA_BY_ID_PLUS_GOAL_SPECIAL[ap_item_id].name} not found in"
                f" {sorted([_ITEM_DATA_BY_ID_PLUS_GOAL_SPECIAL[code] for code in remaining_requirements], key=lambda data: data.name)}")
            remaining_requirements.remove(ap_item_id)
            debug_logger.info("Removed %s from %s requirements",
                              _ITEM_DATA_BY_ID_PLUS_GOAL_SPECIAL[ap_item_id].name, dependent_area_short_name)
            if not remaining_requirements:
                self.unlock_chapter(SHORT_NAME_TO_CHAPTER_AREA[dependent_area_short_name])
                # Display a message when the goal chapter is unlocked, but try to avoid telling the user if they are
                # connecting to a slot where the goal chapter is already completed.
                if (dependent_area_short_name == self.goal_chapter
                        and not ctx.finished_game
                        and self.goal_chapter_area_id not in ctx.free_play_completion_checker.completed_free_play):
                    msg = f"> Goal Chapter {self.goal_chapter} Unlocked! <"
                    # todo: This is something that would benefit from being able to control how long a message is
                    #  displayed for.
                    # Display the message twice because of its importance.
                    ctx.text_display.priority_messages(msg, msg)
                del self.remaining_chapter_item_requirements[dependent_area_short_name]

        del self.ap_item_id_to_dependent_game_chapters[ap_item_id]

    def unlock_chapter(self, chapter_area: ChapterArea):
        self.unlocked_chapters_per_episode[chapter_area.episode].add(chapter_area.area_id)
        debug_logger.info("Unlocked chapter %s (%s)", chapter_area.name, chapter_area.short_name)

    @subscribe_event
    async def update_game_state(self, event: OnGameWatcherTickEvent) -> None:
        ctx = event.context
        temporary_story_completion: AbstractSet[int]
        if (self.should_unlock_all_episodes_shop_slots(ctx)
                and ctx.acquired_characters.is_all_episodes_character_selected_in_shop(ctx)):
            # TODO: Instead of this, temporarily change the unlock conditions for these characters to 0 Gold Bricks.
            #  This will require finding the Collection data structs in memory at runtime.
            # In vanilla, the 'all episodes' characters unlock for purchase in the shop when the player has completed
            # every chapter in Story mode. In the AP randomizer, they need to be unlocked once all Episode Unlocks have
            # been acquired instead because completing all chapters in Story mode would basically never happen in a
            # playthrough of the randomized world.
            # Unfortunately, chapters being completed in Story mode is also what unlocks most other Character
            # purchases in the shop.
            # To work around this, all Story mode completions are temporarily set when all Episode Unlocks have been
            # acquired and the player has selected one of the 'all episodes' characters for purchase in the shop.
            temporary_story_completion = ALL_CHAPTER_AREA_IDS_SET
        else:
            temporary_story_completion = set()
            # TODO: Temporarily set the player's current chapter as completed so that they can save and exit from the
            #  chapter instead of having to exit without saving. This should happen once individual minikit logic is
            #  added because it can then be expected for a player to collect Minikits before a chapter is possible to
            #  complete.
            # If the player is in an Episode's room, and inside a Chapter door with the Chapter door's menu open, grant
            # them temporary Story mode completion so that they can select Free Play.
            cantina_room = ctx.read_current_cantina_room().value
            if cantina_room in self.unlocked_chapters_per_episode:
                # The player is in an Episode room in the cantina.
                unlocked_areas_in_room = self.unlocked_chapters_per_episode[cantina_room]
                if unlocked_areas_in_room:
                    # There are unlocked chapters in this room (the player shouldn't be able to access an Episode room
                    # unless it contains unlocked chapters...).
                    area_id_of_door_the_player_is_in_front_of = ctx.read_uchar(CURRENT_AREA_DOOR_ADDRESS)
                    area = AREA_ID_TO_CHAPTER_AREA.get(area_id_of_door_the_player_is_in_front_of)
                    if area is not None and area.area_id in unlocked_areas_in_room:
                        # The player is standing in front of, or within a chapter door that is unlocked.
                        if ctx.read_uchar(OPENED_MENU_DEPTH_ADDRESS) > 0:
                            # The player has a menu open (hopefully the menu within the chapter door.
                            temporary_story_completion = {area.area_id}
                            if self.last_area_door is not area:
                                # Force the selection in the menu to "Free Play" instead of "Story" or "Challenge".
                                # This is only done when the ChapterArea changes, so that users can still choose "Story"
                                # or "Challenge" if they really want to (not currently useful).
                                ChapterDoorGameMode.FREE_PLAY.set(ctx)
                                self.last_area_door = area

        completed_free_play = ctx.free_play_completion_checker.completed_free_play

        # 36 writes on each game state update is undesirable, but necessary to easily allow for temporarily completing
        # Story modes.
        for area in CHAPTER_AREAS:
            area_id = area.area_id
            enabled = area_id in self.enabled_chapter_area_ids
            if enabled and area_id in completed_free_play:
                # Set the chapter as unlocked and Story mode completed because Free Play has been completed.
                # The second bit in the third byte is custom to the AP client and signifies that Free Play has been
                # completed.
                ctx.write_bytes(area.address, b"\x03\x01", 2)
            elif area_id in temporary_story_completion:
                # Set the chapter as unlocked and Story mode completed because Story mode for this chapter needs to be
                # temporarily set as completed for some purpose.
                ctx.write_bytes(area.address, b"\x01\x01", 2)
            elif area_id not in self.enabled_chapter_area_ids:
                # Set the chapter as locked, with Story mode incomplete.
                ctx.write_bytes(area.address, b"\x00\x00", 2)
            else:
                if enabled and area_id in self.unlocked_chapters_per_episode[area.episode]:
                    # Set the chapter as unlocked, but with Story mode incomplete because Free Play has not been
                    # completed. This prevents characters being for sale in the shop without completing Free Play for
                    # the chapter that unlocks those shop slots.
                    ctx.write_bytes(area.address, b"\x01\x00", 2)
                else:
                    # Set the chapter as locked, with Story mode incomplete.
                    ctx.write_bytes(area.address, b"\x00\x00", 2)

    def _set_current_area_true_jedi_requirement(self, ctx: TCSContext, current_p_area_data: int | None = None,
                                                chapter_area: ChapterArea | None = None):
        if current_p_area_data is None or chapter_area is None:
            current_p_area_data = CURRENT_P_AREA_DATA_ADDRESS.get(ctx)

            if current_p_area_data == 0:
                # debug_logger.info("Current AreaData pointer is NULL. Nothing to do.")
                return

            current_area_id = AREA_DATA_ID.get(ctx, current_p_area_data)
            chapter_area = AREA_ID_TO_CHAPTER_AREA.get(current_area_id)

            if chapter_area is None:
                # The current area is not a chapter area, so there is nothing to do.
                debug_logger.info("The current area has ID %i, which is not a chapter Area", current_area_id)
                return

        if self.easy_true_jedi:
            true_jedi_requirement = chapter_area.story_true_jedi_requirement
        else:
            true_jedi_requirement = chapter_area.free_play_true_jedi_requirement

        if self.scale_true_jedi_with_score_multipliers:
            multiplier = ctx.acquired_generic.current_score_multiplier
            if (not self.easy_true_jedi
                    and multiplier >= 2
                    and chapter_area.short_name in DIFFICULT_OR_IMPOSSIBLE_TRUE_JEDI):
                # The chapter has a difficult or impossible True Jedi without the use of Score x2, so remove Score x2
                # from the multiplier.
                multiplier //= 2
            true_jedi_requirement *= multiplier

        AREA_DATA_FREE_PLAY_TRUE_JEDI_REQUIREMENT.set(ctx, current_p_area_data, true_jedi_requirement)
        debug_logger.info("Set the True Jedi requirement for %s to %i", chapter_area.name, true_jedi_requirement)

    @subscribe_event
    def on_area_change(self, event: OnAreaChangeEvent):
        ctx = event.context

        current_area_id = event.new_area_data_id
        if current_area_id == -1:
            # debug_logger.info("Current AreaData pointer is NULL. Nothing to do.")
            return
        chapter_area = AREA_ID_TO_CHAPTER_AREA.get(current_area_id)

        if chapter_area is None:
            # The current area is not a chapter area, so there is nothing to do.
            debug_logger.info("The current area has ID %i, which is not a chapter Area", current_area_id)
            return

        self._set_current_area_true_jedi_requirement(event.context, event.new_p_area_data, chapter_area)
        # Check if the player is in a chapter.
        if current_area_id in AREA_ID_TO_CHAPTER_AREA:
            if not IS_CHARACTER_SWAPPING_ENABLED.get(ctx):
                # The player must be in Story, Superstory or a Bounty Hunter Mission.
                # todo: Find a way to tell apart Story, Superstory and Bounty Hunter Missions while in the level itself.
                #  Currently, the client can only tell them apart on the 'status' screen.
                ctx.text_display.priority_messages("Chapters should only be played in Free Play",
                                                   "Other modes are not currently part of the randomizer.")
            else:
                if not ChallengeMode.NO_CHALLENGE.is_set(ctx):
                    # The player is in Challenge mode.
                    ctx.text_display.priority_messages("Chapters should only be played in Free Play",
                                                       "Challenge mode is not currently part of the randomizer")
