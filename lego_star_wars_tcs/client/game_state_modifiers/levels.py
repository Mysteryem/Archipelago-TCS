import logging
from typing import AbstractSet, Callable, Any

from .text_replacer import TextId
from ..common import ClientComponent
from ..common_addresses import OPENED_MENU_DEPTH_ADDRESS
from ..type_aliases import TCSContext, AreaId
from ...items import ITEM_DATA_BY_NAME, ITEM_DATA_BY_ID
from ...levels import ChapterArea, CHAPTER_AREAS, SHORT_NAME_TO_CHAPTER_AREA, AREA_ID_TO_CHAPTER_AREA
from ... import options


debug_logger = logging.getLogger("TCS Debug")

ALL_CHAPTER_AREA_IDS_SET = frozenset({area.area_id for area in CHAPTER_AREAS})

# Changes according to what Area door the player is stand in front of. It is 0xFF while in the rest of the Cantina, away
# from an Area door.
CURRENT_AREA_DOOR_ADDRESS = 0x8795A0


class UnlockedChapterManager(ClientComponent):
    character_to_dependent_game_chapters: dict[int, list[str]]
    remaining_chapter_item_requirements: dict[str, set[int]]

    unlocked_chapters_per_episode: dict[int, set[AreaId]]
    should_unlock_all_episodes_shop_slots: Callable[[TCSContext], bool] = staticmethod(lambda _ctx: False)

    enabled_chapter_area_ids: set[int]

    def __init__(self) -> None:
        self.character_to_dependent_game_chapters = {}
        self.remaining_chapter_item_requirements = {}
        self.unlocked_chapters_per_episode = {}
        self.enabled_chapter_area_ids = set()

    def init_from_slot_data(self, ctx: TCSContext, slot_data: dict[str, Any]) -> None:
        enabled_chapters = slot_data["enabled_chapters"]
        enabled_episodes = slot_data["enabled_episodes"]
        episode_unlock_requirement = slot_data["episode_unlock_requirement"]
        all_episodes_character_purchase_requirements = slot_data["all_episodes_character_purchase_requirements"]
        all_episodes_purchases_enabled = bool(slot_data["enable_all_episodes_purchases"])

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
                self.should_unlock_all_episodes_shop_slots = (
                    lambda ctx: ctx.acquired_generic.all_episodes_token_counts == num_enabled_episodes)
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
        for chapter_area in CHAPTER_AREAS:
            if chapter_area.area_id not in self.enabled_chapter_area_ids:
                continue
            character_requirements = chapter_area.character_requirements
            episode = chapter_area.episode
            if episode_unlock_requirement == options.EpisodeUnlockRequirement.option_episode_item:
                item_requirements = [f"Episode {episode} Unlock", *character_requirements]
            elif episode_unlock_requirement == options.EpisodeUnlockRequirement.option_open:
                item_requirements = list(character_requirements)
            else:
                raise RuntimeError(f"Unexpected EpisodeUnlockRequirement: {episode_unlock_requirement}")
            code_requirements = set()
            for item_name in item_requirements:
                item_code = ITEM_DATA_BY_NAME[item_name].code
                assert item_code != -1
                item_id_to_chapter_area_short_name.setdefault(item_code, []).append(chapter_area.short_name)
                code_requirements.add(item_code)
            remaining_chapter_item_requirements[chapter_area.short_name] = code_requirements

        self.character_to_dependent_game_chapters = item_id_to_chapter_area_short_name
        self.remaining_chapter_item_requirements = remaining_chapter_item_requirements

    def on_character_or_episode_unlocked(self, character_ap_id: int):
        dependent_chapters = self.character_to_dependent_game_chapters.get(character_ap_id)
        if dependent_chapters is None:
            return

        for dependent_area_short_name in dependent_chapters:
            remaining_requirements = self.remaining_chapter_item_requirements[dependent_area_short_name]
            assert remaining_requirements
            assert character_ap_id in remaining_requirements, (f"{ITEM_DATA_BY_ID[character_ap_id].name} not found in"
                                                               f" {sorted([ITEM_DATA_BY_ID[code] for code in remaining_requirements], key=lambda data: data.name)}")
            remaining_requirements.remove(character_ap_id)
            debug_logger.info("Removed %s from %s requirements", ITEM_DATA_BY_ID[character_ap_id].name, dependent_area_short_name)
            if not remaining_requirements:
                self.unlock_chapter(SHORT_NAME_TO_CHAPTER_AREA[dependent_area_short_name])
                del self.remaining_chapter_item_requirements[dependent_area_short_name]

        del self.character_to_dependent_game_chapters[character_ap_id]

    def unlock_chapter(self, chapter_area: ChapterArea):
        self.unlocked_chapters_per_episode[chapter_area.episode].add(chapter_area.area_id)
        debug_logger.info("Unlocked chapter %s (%s)", chapter_area.name, chapter_area.short_name)

    async def update_game_state(self, ctx: TCSContext):
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
