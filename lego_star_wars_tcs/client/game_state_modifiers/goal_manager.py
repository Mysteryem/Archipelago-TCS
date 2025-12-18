import logging
from itertools import cycle
from time import perf_counter_ns
from typing import Mapping, Literal, Iterator

from .text_replacer import TextId
from ..common_addresses import CantinaRoom, CustomSaveFlags1, GameState1
from ..events import subscribe_event, OnReceiveSlotDataEvent, OnGameWatcherTickEvent
from ..type_aliases import TCSContext, AreaId
from ...items import MINIKITS_BY_COUNT
from ...levels import SHORT_NAME_TO_CHAPTER_AREA, AREA_ID_TO_CHAPTER_AREA, BONUS_NAME_TO_BONUS_AREA
from ...options import OnlyUniqueBossesCountTowardsGoal, MinikitGoalCompletionMethod
from . import ClientComponent

MINIKIT_ITEMS: Mapping[int, int] = {item.code: count for count, item in MINIKITS_BY_COUNT.items()}


logger = logging.getLogger("Client")

EPISODE_NUMBER_TO_EPISODE_TEXT = {
    1: TextId.EPISODE_1_NAME,
    2: TextId.EPISODE_2_NAME,
    3: TextId.EPISODE_3_NAME,
    4: TextId.EPISODE_4_NAME,
    5: TextId.EPISODE_5_NAME,
    6: TextId.EPISODE_6_NAME,
}


GOAL_TEXT_CYCLE_COOLDOWN_NS = int(2e9)  # 2s
GoalKeys = Literal["Minikits", "Bosses", "Areas", "Kyber Bricks", "Goal Chapter"]

_NO_GOAL_CHAPTER = -1


class GoalManager(ClientComponent):
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
    minikit_goal_completion_method: MinikitGoalCompletionMethod = (
        MinikitGoalCompletionMethod(MinikitGoalCompletionMethod.option_junkyard_minikit_display)
    )

    goal_areas_count: int = 999_999_999  # Set by an option and read from slot data.
    goal_areas_relevant_bonus_area_ids: set[AreaId]

    # Assume enabled to start with as an extra measure against any issues that could cause goal to send early.
    kyber_bricks_goal_enabled: bool = True

    # All goals that must be completed to unlock the Goal Chapter.
    sub_goals_complete: bool = False

    goal_chapter_area_id: int = 999_999_999  # Set by an option and read from slot data.

    _paused_goal_strings: dict[GoalKeys, str]
    _paused_goal_string_key_cycle: Iterator[GoalKeys]
    _last_paused_goal_string_cycle_key: GoalKeys | None = None
    _last_paused_goal_string_cycle: int = -1

    def __init__(self):
        self.enabled_boss_chapters = set()
        self._paused_goal_strings = {}
        self._paused_goal_string_key_cycle = cycle(self._paused_goal_strings.keys())

    @subscribe_event
    def init_from_slot_data(self, event: OnReceiveSlotDataEvent) -> None:
        slot_data = event.slot_data
        ctx = event.context
        self.goal_minikit_count = slot_data["minikit_goal_amount"]

        # Reset goal strings.
        self._paused_goal_strings.clear()
        self._paused_goal_string_key_cycle = cycle(self._paused_goal_strings.keys())
        self._last_paused_goal_string_cycle_key = None
        self._last_paused_goal_string_cycle = -1

        has_sub_goals = False

        if self.goal_minikit_count > 0:
            has_sub_goals = True
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

        if event.generator_version < (1, 2, 0):
            # The Minikit goal was completed by going to the Junkyard minikit display on previous 1.0.0 versions.
            self.minikit_goal_completion_method.value = MinikitGoalCompletionMethod.option_junkyard_minikit_display
        else:
            self.minikit_goal_completion_method.value = slot_data["minikit_goal_completion_method"]

        if event.generator_version < (1, 1, 0):
            # Minikit goal was the only goal at this point.
            goal_bosses_count = 0
        else:
            goal_bosses_count = slot_data["defeat_bosses_goal_amount"]

        if goal_bosses_count <= 0:
            self.goal_bosses_count = 0
            self.enabled_boss_chapters = set()
            self.enabled_unique_bosses = {}
            boss_goal_info_text = "Bosses do not need to be defeated to goal."
        else:
            has_sub_goals = True
            self.goal_bosses_count = goal_bosses_count
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
                                           f" {len(unique_bosses)} unique bosses enabled: {boss_chapters_text}")
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

        if event.generator_version < (1, 2, 0):
            self.goal_areas_count = 0
        else:
            self.goal_areas_count = slot_data["goal_area_completion_count"]

        # The "Levels" and Kyber Bricks goal info are written to the same shop hint text because they are both quite
        # short.
        hints_page_3_goal_info_texts = []

        # "Level" here is as a user-facing term, not that internal meaning of a "Level".
        goal_areas_relevant_bonus_area_ids = set()
        if self.goal_areas_count > 0:
            has_sub_goals = True
            enabled_chapter_count = len(slot_data["enabled_chapters"])
            if slot_data["enable_bonus_locations"]:
                enabled_bonus_level_count = 0
                for name in slot_data["enabled_bonuses"]:
                    bonus_area = BONUS_NAME_TO_BONUS_AREA[name]
                    if not bonus_area.gold_brick:
                        continue
                    enabled_bonus_level_count += 1
                    goal_areas_relevant_bonus_area_ids.add(bonus_area.area_id)
                total_level_count = enabled_chapter_count + enabled_bonus_level_count
                areas_goal_info_text = (f"{self.goal_areas_count}/{total_level_count} levels (Chapters and/or Bonus"
                                        f" levels) need to be completed to goal.")
            else:
                areas_goal_info_text = (f"{self.goal_areas_count}/{enabled_chapter_count} Chapters need to be"
                                        f" completed to goal.")
            hints_page_3_goal_info_texts.append(areas_goal_info_text)
        self.goal_areas_relevant_bonus_area_ids = goal_areas_relevant_bonus_area_ids

        if event.generator_version < (1, 2, 0):
            self.kyber_bricks_goal_enabled = False
        else:
            self.kyber_bricks_goal_enabled = bool(slot_data["goal_requires_kyber_bricks"])

        if event.generator_version < (1, 2, 0):
            self.goal_chapter_area_id = _NO_GOAL_CHAPTER
        else:
            goal_chapter = slot_data["goal_chapter"]
            if goal_chapter:
                self.goal_chapter_area_id = SHORT_NAME_TO_CHAPTER_AREA[goal_chapter].area_id
            else:
                # No goal chapter required.
                self.goal_chapter_area_id = _NO_GOAL_CHAPTER

        if self.kyber_bricks_goal_enabled:
            has_sub_goals = True
            hints_page_3_goal_info_texts.append("7 Kyber Bricks are needed to goal.")

        if self.goal_chapter_area_id != _NO_GOAL_CHAPTER:
            if has_sub_goals:
                goal_area = AREA_ID_TO_CHAPTER_AREA[self.goal_chapter_area_id]
                shortname = goal_area.short_name

                hints_page_3_goal_info_texts.append(
                    f"Once {shortname}'s usual requirements and all other goal requirements are completed,"
                    f" {shortname} will unlock, complete it to goal your game.")

        if not hints_page_3_goal_info_texts:
            hints_page_3_goal_info_texts.append("There are no additional goal requirements.")

        ctx.text_replacer.write_custom_string(TextId.SHOP_UNLOCKED_HINT_2, minikit_goal_info_text)
        ctx.text_replacer.write_custom_string(TextId.SHOP_UNLOCKED_HINT_3, boss_goal_info_text)
        ctx.text_replacer.write_custom_string(TextId.SHOP_UNLOCKED_HINT_4, " ".join(hints_page_3_goal_info_texts))

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
        goal_strings = self._paused_goal_strings
        if not goal_strings:
            last_cycle = None
        else:
            last_cycle = self._last_paused_goal_string_cycle_key

        is_first_time = last_cycle is None or self._last_paused_goal_string_cycle == -1

        goal_strings.clear()

        suffix_message = f" - Goal: "

        if self.goal_minikit_count > 0:
            minikit_progress = f"{ctx.acquired_minikits.minikit_count}/{self.goal_minikit_count}"
            if self.minikit_goal_complete:
                minikit_goal = f"Minikit Goal Completed ({minikit_progress})"
            elif ctx.acquired_minikits.minikit_count >= self.goal_minikit_count:
                minikit_goal = f"Finish Minikit Goal at the Cantina Junkyard Minikit Display ({minikit_progress})"
            else:
                minikit_goal = f"{minikit_progress} Minikits"
            goal_strings["Minikits"] = suffix_message + minikit_goal

        if self.goal_bosses_count > 0:
            defeated_count = self._get_bosses_defeated_count(ctx)
            if self.goal_bosses_must_be_unique:
                bosses_goal = f"{defeated_count}/{self.goal_bosses_count} Unique Bosses Defeated"
            else:
                bosses_goal = f"{defeated_count}/{self.goal_bosses_count} Bosses Defeated"
            goal_strings["Bosses"] = suffix_message + bosses_goal

        if self.goal_areas_count > 0:
            completed_areas_count = self._get_completed_area_count(ctx)
            # "Level" here is as a user-facing term, not that internal meaning of a "Level".
            areas_goal = f"{completed_areas_count}/{self.goal_areas_count} Levels Completed"
            goal_strings["Areas"] = suffix_message + areas_goal

        if self.kyber_bricks_goal_enabled:
            acquired_kyber_bricks_count = ctx.acquired_generic.kyber_brick_count
            kyber_bricks_goal = f"{acquired_kyber_bricks_count}/7 Kyber Bricks"
            goal_strings["Kyber Bricks"] = suffix_message + kyber_bricks_goal

        if self.goal_chapter_area_id != _NO_GOAL_CHAPTER:
            area = AREA_ID_TO_CHAPTER_AREA[self.goal_chapter_area_id]
            if self.sub_goals_complete:
                goal_strings["Goal Chapter"] = f" - Final Goal: Complete {area.short_name}"
            else:
                goal_strings["Goal Chapter"] = f" - Final Goal: Unlock and complete {area.short_name}"

        if len(goal_strings) > 1:
            # Add a " [x/total]" string to the end of each goal string to help make it clearer to the user that there
            # are multiple goals that will cycle.
            for i, (k, v) in enumerate(goal_strings.copy().items(), start=1):
                goal_strings[k] = v + f" [{i}/{len(goal_strings)}]"

        if is_first_time:
            if goal_strings:
                self._paused_goal_string_key_cycle = cycle(goal_strings.keys())
                first_key = next(self._paused_goal_string_key_cycle)
                self._last_paused_goal_string_cycle_key = first_key
                updated_message = goal_strings[first_key]
            else:
                updated_message = suffix_message + "Error, no goals found"
            self._last_paused_goal_string_cycle = perf_counter_ns()
        else:
            assert last_cycle is not None
            assert last_cycle in goal_strings
            updated_message = goal_strings[last_cycle]
        ctx.text_replacer.suffix_custom_string(TextId.PAUSED, updated_message)

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

    @subscribe_event
    async def update_game_state(self, event: OnGameWatcherTickEvent) -> None:
        if not event.context.slot:
            return

        if self._goal_text_needs_update:
            self._goal_text_needs_update = False
            self._update_paused_text_goal_display(event.context)

        if self._bosses_goal_text_needs_update:
            self._bosses_goal_text_needs_update = False
            self._update_episodes_text_for_boss_statuses(event.context)

        if not self._paused_goal_strings:
            return

        now = perf_counter_ns()
        if now > self._last_paused_goal_string_cycle + GOAL_TEXT_CYCLE_COOLDOWN_NS:
            next_paused_key = next(self._paused_goal_string_key_cycle)
            event.context.text_replacer.suffix_custom_string(TextId.PAUSED, self._paused_goal_strings[next_paused_key])
            self._last_paused_goal_string_cycle = now

    def tag_for_update(self, kind: Literal["all", "minikit", "boss", "area", "kyber brick"]):
        """Tell the GoalManager that the state of a potentially goal-relevant type of object has updated."""
        if kind == "all":
            # Update everything regardless of whether the goal is enabled. This is used during initialization from
            # slot_data.
            self._bosses_goal_text_needs_update = True
            self._goal_text_needs_update = True
        elif kind == "minikit":
            minikit_goal_enabled = self.goal_minikit_count > 0
            # Only the shared goal text shows minikit progress currently.
            if minikit_goal_enabled:
                self._goal_text_needs_update = True
        elif kind == "boss":
            bosses_goal_enabled = self.goal_bosses_count > 0
            if bosses_goal_enabled:
                self._bosses_goal_text_needs_update = True
                self._goal_text_needs_update = True
        elif kind == "area":
            levels_goal_enabled = self.goal_areas_count > 0
            if levels_goal_enabled:
                self._goal_text_needs_update = True
        elif kind == "kyber brick":
            if self.kyber_bricks_goal_enabled:
                self._goal_text_needs_update = True
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

    def _get_completed_area_count(self, ctx: TCSContext):
        completed_chapter_count = len(ctx.free_play_completion_checker.completed_free_play)
        if self.goal_areas_relevant_bonus_area_ids:
            incomplete_bonuses = ctx.bonus_area_completion_checker.remaining_story_completion_checks.keys()
            incomplete_relevant_bonuses = self.goal_areas_relevant_bonus_area_ids.intersection(incomplete_bonuses)
            completed_bonuses_count = len(self.goal_areas_relevant_bonus_area_ids) - len(incomplete_relevant_bonuses)
            return completed_chapter_count + completed_bonuses_count
        else:
            return completed_chapter_count

    def check_sub_goals_complete(self, ctx: TCSContext) -> bool:
        if self.sub_goals_complete:
            return True

        if self.goal_minikit_count > 0 and not self.minikit_goal_complete:
            if not ctx.is_in_game():
                return False
            if self.minikit_goal_completion_method == MinikitGoalCompletionMethod.option_junkyard_minikit_display:
                if (ctx.read_current_cantina_room() != CantinaRoom.JUNKYARD
                        or not GameState1.IN_JUNKYARD_MINIKITS_DISPLAY.is_set(ctx)):
                    # The player is not in the Junkyard Minikits display, where the Minikit goal is submitted.
                    return False
            elif self.minikit_goal_completion_method != MinikitGoalCompletionMethod.option_instant:
                raise AssertionError(f"Unexpected MinikitGoalCompletionMethod: {self.minikit_goal_completion_method}")
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
        if self.goal_areas_count > 0:
            if self._get_completed_area_count(ctx) < self.goal_areas_count:
                return False
        if self.kyber_bricks_goal_enabled:
            if ctx.acquired_generic.kyber_brick_count < 7:
                return False

        # Trigger the Goal Chapter unlock if all its usual requirements are completed.
        ctx.unlocked_chapter_manager.on_sub_goal_completion(ctx)
        self.sub_goals_complete = True

        return True

    def is_goal_chapter_complete(self, ctx: TCSContext) -> bool:
        if self.goal_chapter_area_id == _NO_GOAL_CHAPTER:
            # There is no goal chapter.
            return True
        return self.goal_chapter_area_id in ctx.free_play_completion_checker.completed_free_play

    def is_goal_complete(self, ctx: TCSContext) -> bool:
        return self.check_sub_goals_complete(ctx) and self.is_goal_chapter_complete(ctx)
