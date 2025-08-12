import logging
from typing import Mapping, Any, Literal

from .text_replacer import TextId
from ..common_addresses import CantinaRoom, CustomSaveFlags1, GameState1
from ..type_aliases import TCSContext, AreaId
from ...items import MINIKITS_BY_COUNT
from ...levels import SHORT_NAME_TO_CHAPTER_AREA, AREA_ID_TO_CHAPTER_AREA
from ...options import OnlyUniqueBossesCountTowardsGoal
from . import GameStateUpdater

MINIKIT_ITEMS: Mapping[int, int] = {item.code: count for count, item in MINIKITS_BY_COUNT.items()}

# Goal progress is written into Custom Character 2's name until a better place for this information is found.
CUSTOM_CHARACTER2_NAME_OFFSET = 0x86E524 + 0x14  # string[15]


logger = logging.getLogger("Client")

EPISODE_NUMBER_TO_EPISODE_TEXT = {
    1: TextId.EPISODE_1_NAME,
    2: TextId.EPISODE_2_NAME,
    3: TextId.EPISODE_3_NAME,
    4: TextId.EPISODE_4_NAME,
    5: TextId.EPISODE_5_NAME,
    6: TextId.EPISODE_6_NAME,
}


class GoalManager(GameStateUpdater):
    receivable_ap_ids = MINIKIT_ITEMS

    _goal_text_needs_update: bool = True

    goal_minikit_count: int = 999_999_999  # Set by an option and read from slot data.

    goal_bosses_count: int = 999_999_999  # Set by an option and read from slot data.
    goal_bosses_must_be_unique: bool = False
    goal_bosses_anakin_as_vader: bool = False
    enabled_boss_chapters: set[AreaId]
    enabled_unique_bosses: dict[str, set[AreaId]]
    _bosses_goal_text_needs_update: bool = True

    minikit_goal_complete: bool = False

    def __init__(self):
        self.enabled_boss_chapters = set()

    def init_from_slot_data(self, ctx: TCSContext, slot_data: dict[str, Any]) -> None:
        self.goal_minikit_count = slot_data["minikit_goal_amount"]

        if self.goal_minikit_count > 0:
            enabled_chapter_count = len(slot_data["enabled_chapters"])
            minimum_minikits_in_the_multiworld = 10 * enabled_chapter_count
            minikit_goal_info_text = (f"{self.goal_minikit_count} Minikits are needed to goal. There are a minimum of"
                                      f" {minimum_minikits_in_the_multiworld} Minikits to be found in the multiworld.")
            # If the save file says the minikits goal is complete, ensure the AP server also thinks the minikits goal is
            # complete.
            if CustomSaveFlags1.MINIKIT_GOAL_COMPLETE.is_set(ctx):
                ctx.update_datastorage_minikits_goal_submitted()
                self.minikit_goal_complete = True
                self.tag_for_update("minikit")
        else:
            minikit_goal_info_text = "Minikit items are not needed to goal."

        server_apworld_version = tuple(slot_data["apworld_version"])
        if server_apworld_version < (1, 1, 0):
            # Minikit goal was the only goal at this point.
            self.goal_bosses_count = 0
            self.enabled_boss_chapters = set()
            self.enabled_unique_bosses = {}
            boss_goal_info_text = "Bosses do not need to be defeated to goal."
        else:
            self.goal_bosses_count = slot_data["defeat_bosses_goal_amount"]
            enabled_boss_chapters = set(slot_data["enabled_bosses"])
            self.enabled_boss_chapters = {SHORT_NAME_TO_CHAPTER_AREA[chapter].area_id
                                          for chapter in enabled_boss_chapters}
            only_unique_bosses_count = slot_data["only_unique_bosses_count"]
            self.goal_bosses_must_be_unique = (
                    only_unique_bosses_count != OnlyUniqueBossesCountTowardsGoal.option_disabled)
            self.goal_bosses_anakin_as_vader = (
                    only_unique_bosses_count
                    == OnlyUniqueBossesCountTowardsGoal.option_enabled_and_count_anakin_as_vader)
            if self.goal_bosses_must_be_unique:
                unique_bosses: dict[str, set[AreaId]] = {}
                unique_bosses_to_chapters: dict[str, list[str]] = {}
                for chapter in enabled_boss_chapters:
                    area = SHORT_NAME_TO_CHAPTER_AREA[chapter]
                    boss = area.boss
                    if self.goal_bosses_anakin_as_vader and boss == "Anakin Skywalker":
                        boss = "Darth Vader"
                    unique_bosses.setdefault(boss, set()).add(area.area_id)
                    unique_bosses_to_chapters.setdefault(boss, []).append(area.short_name)
                self.enabled_unique_bosses = unique_bosses
                sorted_bosses = sorted(unique_bosses_to_chapters.items(), key=lambda t: min(t[1]))
                boss_strings = []
                for boss, chapters in sorted_bosses:
                    chapters.sort()
                    chapters_string = ", ".join(chapters)
                    boss_string = f"{boss} ({chapters_string})"
                    boss_strings.append(boss_string)

                if len(boss_strings) == 1:
                    boss_goal_info_text = (f"{self.goal_bosses_count} unique boss need to be defeated. There is 1 boss"
                                           f" enabled: {boss_strings[0]}")
                else:
                    boss_chapters_text = ", ".join(boss_strings[:-1])
                    boss_chapters_text += f" and {boss_strings[-1]}"
                    boss_goal_info_text = (f"{self.goal_bosses_count} unique bosses need to be defeated. There are"
                                           f" {len(unique_bosses)} bosses enabled: {boss_chapters_text}")
            else:
                self.enabled_unique_bosses = {}
                sorted_boss_chapters = sorted(enabled_boss_chapters)
                if len(sorted_boss_chapters) == 1:
                    boss_chapters_text = sorted_boss_chapters[0]
                    boss_goal_info_text = (f"{self.goal_bosses_count} boss needs to be defeated. There is"
                                           f" {len(self.enabled_boss_chapters)} boss enabled, in {boss_chapters_text}")
                else:
                    boss_chapters_text = ", ".join(sorted_boss_chapters[:-1])
                    boss_chapters_text += f" and {sorted_boss_chapters[-1]}"
                    boss_goal_info_text = (f"{self.goal_bosses_count} bosses need to be defeated. There are"
                                           f" {len(self.enabled_boss_chapters)} bosses enabled, in"
                                           f" {boss_chapters_text}")
        ctx.text_replacer.write_custom_string(TextId.SHOP_UNLOCKED_HINT_2, minikit_goal_info_text)
        ctx.text_replacer.write_custom_string(TextId.SHOP_UNLOCKED_HINT_3, boss_goal_info_text)

        self.tag_for_update("all")
        assert isinstance(self.goal_minikit_count, int)

    def _get_bosses_defeated_count(self, ctx: TCSContext) -> int:
        completed_free_play = ctx.free_play_completion_checker.completed_free_play
        if self.goal_bosses_must_be_unique:
            count = 0
            for area_ids in self.enabled_unique_bosses.values():
                if not area_ids.isdisjoint(completed_free_play):
                    count += 1
            return count
        else:
            return len(self.enabled_boss_chapters.intersection(completed_free_play))

    def _update_paused_text_goal_display(self, ctx: TCSContext):
        """
        Replace the current "Paused" text, displayed in the UI under the Player that paused the game, with current goal
        progress.
        """
        suffix_message = f" - Goal: "
        goals: list[str] = []
        if self.goal_minikit_count > 0:
            minikit_progress = f"{ctx.acquired_minikits.minikit_count}/{self.goal_minikit_count}"
            if self.minikit_goal_complete:
                minikit_goal = f"Minikit Goal Completed ({minikit_progress})"
            elif ctx.acquired_minikits.minikit_count >= self.goal_minikit_count:
                minikit_goal = f"Finish Minikit Goal at the Cantina Junkyard Minikit Display ({minikit_progress})"
            else:
                minikit_goal = f"{minikit_progress} Minikits"
            goals.append(minikit_goal)
        if self.goal_bosses_count > 0:
            defeated_count = self._get_bosses_defeated_count(ctx)
            if self.goal_bosses_must_be_unique:
                bosses_goal = f"{defeated_count}/{self.goal_bosses_count} Unique Bosses Defeated"
            else:
                bosses_goal = f"{defeated_count}/{self.goal_bosses_count} Bosses Defeated"
            goals.append(bosses_goal)
        if not goals:
            goals.append("Error, no goal found")
        suffix_message += ", ".join(goals)
        ctx.text_replacer.suffix_custom_string(TextId.PAUSED, suffix_message)

    def _update_episodes_text_for_boss_statuses(self, ctx: TCSContext):
        if self.goal_bosses_count <= 0:
            return
        completed_area_ids = ctx.free_play_completion_checker.completed_free_play
        bosses_per_episode: dict[int, list[tuple[int, str, bool]]] = {i: [] for i in range(1, 7)}

        if self.enabled_unique_bosses:
            for boss, area_ids in self.enabled_unique_bosses.items():
                defeated = not area_ids.isdisjoint(completed_area_ids)
                for area_id in area_ids:
                    area = AREA_ID_TO_CHAPTER_AREA[area_id]
                    # Anakin could count as Darth Vader, so use the boss name from self.enabled_unique_bosses instead of
                    # area.unique_boss_name.
                    bosses_per_episode[area.episode].append(
                        (area.number_in_episode, f"{boss} ({area.short_name})", defeated))
        else:
            for area_id in self.enabled_boss_chapters:
                defeated = area_id in completed_area_ids
                area = AREA_ID_TO_CHAPTER_AREA[area_id]
                bosses_per_episode[area.episode].append((area.number_in_episode, area.unique_boss_name, defeated))

        for episode, bosses in bosses_per_episode.items():
            if not bosses:
                continue
            # The chapter number within the episode is first, so is what will be used to sort.
            bosses.sort()
            defeat_boss_strings = []
            defeated_boss_strings = []
            for _, unique_boss_name, defeated in bosses:
                if defeated:
                    defeated_boss_strings.append(unique_boss_name)
                else:
                    defeat_boss_strings.append(unique_boss_name)
            text_to_append = " - "
            if defeat_boss_strings:
                text_to_append += "Defeat " + ", ".join(defeat_boss_strings)
                if defeated_boss_strings:
                    text_to_append += ". "
            if defeated_boss_strings:
                text_to_append += "Defeated " + ", ".join(defeated_boss_strings)
            episode_text_id = EPISODE_NUMBER_TO_EPISODE_TEXT[episode]
            ctx.text_replacer.suffix_custom_string(episode_text_id, text_to_append)

    async def update_game_state(self, ctx: TCSContext):
        if self._goal_text_needs_update:
            self._goal_text_needs_update = False
            self._update_paused_text_goal_display(ctx)

        if self._bosses_goal_text_needs_update:
            self._bosses_goal_text_needs_update = False
            self._update_episodes_text_for_boss_statuses(ctx)

    def tag_for_update(self, kind: Literal["all", "minikit", "boss"] = "all"):
        self._goal_text_needs_update = True
        if kind == "all":
            self._bosses_goal_text_needs_update = True
        elif kind == "minikit":
            # Only the shared goal text shows minikit progress currently.
            pass
        elif kind == "boss":
            self._bosses_goal_text_needs_update = True
        else:
            raise ValueError(f"Unexpected goal kind '{kind}'")

    def complete_minikit_goal_from_datastorage(self, ctx: TCSContext):
        """
        Mark the minikit goal as complete when datastorage says it is complete.

        Usually, the client and save file will already think the minikit goal is complete, but this means that, in
        same-slot co-op, only one player needs to submit the goal.
        """
        CustomSaveFlags1.MINIKIT_GOAL_COMPLETE.set(ctx)
        self.minikit_goal_complete = True
        self.tag_for_update("minikit")

    def _is_bosses_goal_complete(self, completed_area_ids: set[int]):
        required_count = self.goal_bosses_count
        if self.goal_bosses_must_be_unique:
            for area_ids in self.enabled_unique_bosses.values():
                for area_id in area_ids:
                    if area_id in completed_area_ids:
                        required_count -= 1
                        if required_count <= 0:
                            return True
                        break
        else:
            for area_id in self.enabled_boss_chapters:
                if area_id in completed_area_ids:
                    required_count -= 1
                    if required_count <= 0:
                        return True
        return False

    def is_goal_complete(self, ctx: TCSContext):
        if self.goal_minikit_count > 0 and not self.minikit_goal_complete:
            if not ctx.is_in_game():
                return False
            if (ctx.read_current_cantina_room() != CantinaRoom.JUNKYARD
                    or not GameState1.IN_JUNKYARD_MINIKITS_DISPLAY.is_set(ctx)):
                # The player is not in the Junkyard Minikits display, where the Minikit goal is submitted.
                return False
            if ctx.acquired_minikits.minikit_count < self.goal_minikit_count:
                # The goal is incomplete. The player needs to receive/find more Minikit items.
                return False
            CustomSaveFlags1.MINIKIT_GOAL_COMPLETE.set(ctx)
            self.minikit_goal_complete = True
            self.tag_for_update("minikit")
            ctx.update_datastorage_minikits_goal_submitted()
            ctx.text_display.priority_message("Minikit Goal Completed")
        if self.goal_bosses_count > 0:
            # todo: Once a boss has been defeated, reduce a remaining count and remove the boss from a set of remaining
            #  bosses. That way, the check becomes more efficient over time.
            if not self._is_bosses_goal_complete(ctx.free_play_completion_checker.completed_free_play):
                return False

        return True
