import logging
from typing import AbstractSet, Iterable

from ..type_aliases import TCSContext
from ...items import ITEM_DATA_BY_NAME, ITEM_DATA_BY_ID
from ...levels import ChapterArea, CHAPTER_AREAS, SHORT_NAME_TO_CHAPTER_AREA


debug_logger = logging.getLogger("TCS Debug")

ALL_CHAPTER_AREAS_SET = frozenset(CHAPTER_AREAS)


class UnlockedChapterManager:
    character_to_dependent_game_chapters: dict[int, list[str]]
    remaining_chapter_item_requirements: dict[str, set[int]]

    unlocked_chapters_per_episode: dict[int, set[ChapterArea]]

    def __init__(self) -> None:
        self.unlocked_chapters_per_episode = {i: set() for i in range(1, 7)}
        item_id_to_chapter_area_short_name: dict[int, list[str]] = {}
        remaining_chapter_item_requirements: dict[str, set[int]] = {}
        for chapter_area in CHAPTER_AREAS:
            character_requirements = chapter_area.character_requirements
            episode = chapter_area.episode
            # TODO: Make an Episode 1 Unlock item, then just give it to the player when the client starts if random
            #  starting chapter/episode is not implemented by the time the Episode 1 Unlock item is added..
            item_requirements: Iterable[str]
            if episode != 1:
                item_requirements = [f"Episode {episode} Unlock", *character_requirements]
            else:
                item_requirements = character_requirements
            # TODO: Once Obi-Wan, Qui-Gon and TC-14 are added as real items, remove this if-statement and precollect
            #  starting characters instead. Then, all chapters will start locked.
            if item_requirements:
                code_requirements = set()
                for item_name in item_requirements:
                    item_code = ITEM_DATA_BY_NAME[item_name].code
                    assert item_code != -1
                    item_id_to_chapter_area_short_name.setdefault(item_code, []).append(chapter_area.short_name)
                    code_requirements.add(item_code)
                remaining_chapter_item_requirements[chapter_area.short_name] = code_requirements
            else:
                # Immediately unlocked.
                self.unlocked_chapters_per_episode[episode].add(chapter_area)

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
        self.unlocked_chapters_per_episode[chapter_area.episode].add(chapter_area)
        debug_logger.info("Unlocked chapter %s (%s)", chapter_area.name, chapter_area.short_name)

    async def update_game_state(self, ctx: TCSContext):
        temporary_story_completion: AbstractSet[ChapterArea]
        if (len(ctx.acquired_generic.unlocked_episodes) == 6
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
            temporary_story_completion = ALL_CHAPTER_AREAS_SET
        else:
            cantina_room = ctx.read_current_cantina_room()
            if cantina_room.value in self.unlocked_chapters_per_episode:
                # If the player is in an Episode's room, Story mode needs to be completed for all the player's unlocked
                # chapters so that the player can skip playing through Story mode and go straight to Free Play.
                temporary_story_completion = self.unlocked_chapters_per_episode[cantina_room.value]
            else:
                # Do not temporarily complete any Story modes.
                temporary_story_completion = set()

        completed_free_play = ctx.free_play_completion_checker.completed_free_play

        # 36 writes on each game state update is undesirable, but necessary to easily allow for temporarily completing
        # Story modes.
        for area in CHAPTER_AREAS:
            if area in completed_free_play:
                # Set the chapter as unlocked and Story mode completed because Free Play has been completed.
                # The second bit in the third byte is custom to the AP client and signifies that Free Play has been
                # completed.
                ctx.write_bytes(area.address, b"\x03\x01", 2)
            elif area in temporary_story_completion:
                # Set the chapter as unlocked and Story mode completed because Story mode for this chapter needs to be
                # temporarily set as completed for some purpose.
                ctx.write_bytes(area.address, b"\x01\x01", 2)
            else:
                if area in self.unlocked_chapters_per_episode[area.episode]:
                    # Set the chapter as unlocked, but with Story mode incomplete because Free Play has not been
                    # completed. This prevents characters being for sale in the shop without completing Free Play for
                    # the chapter that unlocks those shop slots.
                    ctx.write_bytes(area.address, b"\x01\x00", 2)
                else:
                    # Set the chapter as locked, with Story mode incomplete.
                    ctx.write_bytes(area.address, b"\x00\x00", 2)
