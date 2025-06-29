import logging
from collections import Counter
from typing import cast, Iterable, Mapping, Any

from BaseClasses import Region, ItemClassification, CollectionState, Location, Entrance, Tutorial, Item, MultiWorld
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import components, Component, launch_subprocess, Type
from worlds.generic.Rules import set_rule

from . import constants
from .constants import CharacterAbility, GOLD_BRICK_EVENT_NAME
from .items import (
    ITEM_NAME_TO_ID,
    LegoStarWarsTCSItem,
    ExtraData,
    VehicleData,
    CharacterData,
    GenericCharacterData,
    ITEM_DATA_BY_NAME,
    CHARACTERS_AND_VEHICLES_BY_NAME,
    USEFUL_NON_PROGRESSION_CHARACTERS,
    MINIKITS_BY_COUNT,
    MINIKITS_BY_NAME,
)
from .levels import (
    BonusArea,
    CHAPTER_AREAS,
    BONUS_AREAS,
    EPISODE_TO_CHAPTER_AREAS,
    CHAPTER_AREA_CHARACTER_REQUIREMENTS,
    ALL_AREA_REQUIREMENT_CHARACTERS,
    IMPORTANT_LEVEL_REQUIREMENT_CHARACTERS,
)
from .locations import LOCATION_NAME_TO_ID, LegoStarWarsTCSLocation
from .options import LegoStarWarsTCSOptions


def launch_client():
    from .client import launch
    launch_subprocess(launch, name="LegoStarWarsTheCompleteSagaClient")


components.append(Component("Lego Star Wars: The Complete Saga Client",
                            func=launch_client,
                            component_type=Type.CLIENT))


class LegoStarWarsTCSWebWorld(WebWorld):
    theme = "partyTime"
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide for setting up Lego Star Wars: The Complete Saga to be played in Archipelago.",
        "English",
        "lsw_tcs_en.md",
        "setup/en",
        ["Mysteryem"]
    )]


logger = logging.getLogger("Lego Star Wars TCS")


class LegoStarWarsTCSWorld(World):
    """Lego Star Wars: The Complete Saga"""

    game = constants.GAME_NAME
    web = LegoStarWarsTCSWebWorld()
    options: LegoStarWarsTCSOptions
    options_dataclass = LegoStarWarsTCSOptions

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID

    origin_region_name = "Cantina"

    starting_character_abilities: CharacterAbility = CharacterAbility.NONE
    effective_character_ability_names: dict[str, tuple[str, ...]]
    effective_character_abilities: dict[str, CharacterAbility]
    effective_item_classifications: dict[str, ItemClassification]
    effective_item_collect_extras: dict[str, list[str] | None]

    minikit_bundle_name: str = ""
    available_chapters: int = 36  # Currently fixed
    available_minikits: int = -1
    minikit_bundle_count: int = -1
    goal_minikit_bundle_count: int = -1

    # Item Link worlds do not run generate early, but can create items, so it is necessary to know
    generate_early_run: bool = False

    def __init__(self, multiworld, player: int):
        super().__init__(multiworld, player)
        self.effective_character_abilities = {}
        self.effective_character_ability_names = {}

    def _log_info(self, message: str, *args, **kwargs):
        logger.info("Lego Star Wars TCS (%s): " + message, self.player_name, *args, **kwargs)

    def _log_warning(self, message: str, *args, **kwargs):
        logger.warning("Lego Star Wars TCS (%s): " + message, self.player_name, *args, **kwargs)

    def _log_error(self, message: str, *args, **kwargs):
        logger.error("Lego Star Wars TCS (%s): " + message, self.player_name, *args, **kwargs)

    def generate_early(self) -> None:
        # TODO: Current starting characters are fixed and always have these abilities.
        # FIXME: If starting characters are provided by adding them to start inventory, then most of this 'effective'
        #  abilities will want to be removed. The Playthrough needs to be able to correctly display start inventory
        #  characters that were actually needed to reach the goal.
        self.starting_character_abilities = CharacterAbility.JEDI | CharacterAbility.PROTOCOL_DROID

        effective_ability_cache: dict[CharacterAbility, tuple[str, ...]] = {}
        for name, char in CHARACTERS_AND_VEHICLES_BY_NAME.items():
            effective_abilities: CharacterAbility = char.abilities & ~self.starting_character_abilities
            self.effective_character_abilities[name] = effective_abilities
            if effective_abilities in effective_ability_cache:
                self.effective_character_ability_names[name] = effective_ability_cache[effective_abilities]
            else:
                effective_ability_names = tuple(cast(list[str], [ability.name for ability in effective_abilities]))
                effective_ability_cache[effective_abilities] = effective_ability_names
                self.effective_character_ability_names[name] = effective_ability_names

        bundle_size = self.options.minikit_bundle_size.value
        self.minikit_bundle_name = MINIKITS_BY_COUNT[bundle_size].name
        self.available_minikits = self.available_chapters * 10  # 10 Minikits per chapter.
        self.minikit_bundle_count = (self.available_minikits // bundle_size
                                     + (self.available_minikits % bundle_size != 0))

        # Adjust options.
        if self.options.minikit_goal_amount.value > self.available_minikits:
            self._log_warning("The number of minikits required to goal (%i) was higher than the number of available"
                              " minikits (%i). The number of minikits required to goal has been reduced to the number"
                              " of available minikits (%i).",
                              self.options.minikit_goal_amount.value,
                              self.available_minikits,
                              self.available_minikits)
            self.options.minikit_goal_amount.value = self.available_minikits

        # Only whole bundles are counted for logic, so any partial bundles require an extra whole bundle to goal.
        self.goal_minikit_bundle_count = (self.options.minikit_goal_amount.value // bundle_size
                                          + (self.options.minikit_goal_amount.value % bundle_size != 0))

        self.prepare_items()
        self.generate_early_run = True

    @staticmethod
    def evaluate_effective_item(name: str,
                                effective_character_abilities_lookup: dict[str, CharacterAbility] | None = None,
                                effective_character_ability_names_lookup: dict[str, tuple[str, ...]] | None = None):
        classification = ItemClassification.filler
        collect_extras: Iterable[str] = ()

        item_data = ITEM_DATA_BY_NAME[name]
        if item_data.code < 1:
            raise RuntimeError(f"Error: Item '{name}' cannot be created")
        assert item_data.code != -1
        if isinstance(item_data, ExtraData):
            classification = ItemClassification.useful
        elif isinstance(item_data, GenericCharacterData):
            if effective_character_abilities_lookup is not None:
                abilities = effective_character_abilities_lookup[name]
            else:
                abilities = item_data.abilities

            if effective_character_ability_names_lookup is not None:
                collect_extras = effective_character_ability_names_lookup[name]
            else:
                collect_extras = cast(list[str], [ability.name for ability in abilities])

            if name in IMPORTANT_LEVEL_REQUIREMENT_CHARACTERS:
                classification = ItemClassification.progression | ItemClassification.useful
            elif name in ALL_AREA_REQUIREMENT_CHARACTERS:
                classification = ItemClassification.progression
            elif abilities & constants.RARE_AND_USEFUL_ABILITIES:
                classification = ItemClassification.progression
            elif abilities:
                classification = ItemClassification.progression_skip_balancing
            elif name in USEFUL_NON_PROGRESSION_CHARACTERS:
                classification = ItemClassification.useful

            if name == "Admiral Ackbar":
                classification |= ItemClassification.trap
        else:
            if name in MINIKITS_BY_NAME:
                # A goal macguffin.
                classification = ItemClassification.progression_skip_balancing
            elif name == "Progressive Score Multiplier":
                # Generic item that grants Score multiplier Extras, which are all at least Useful.
                classification = ItemClassification.useful
            elif name == "Progressive Bonus Level":
                # Very few location checks.
                classification = ItemClassification.progression_skip_balancing
            elif name == "Restart Level Trap":
                # No client behaviour implemented. This item will probably be removed.
                classification = ItemClassification.trap
            elif name.startswith("Episode ") and name.endswith(" Unlock"):
                classification = ItemClassification.progression | ItemClassification.useful

        return classification, collect_extras if collect_extras else None

    def prepare_items(self):
        self.effective_item_classifications = {}
        self.effective_item_collect_extras = {}

        for item in self.item_name_to_id:
            classification, collect_extras = self.evaluate_effective_item(item,
                                                                          self.effective_character_abilities,
                                                                          self.effective_character_ability_names)
            self.effective_item_classifications[item] = classification
            self.effective_item_collect_extras[item] = collect_extras

    def get_filler_item_name(self) -> str:
        return "Purple Stud"

    def create_item(self, name: str) -> LegoStarWarsTCSItem:
        if self.generate_early_run:
            classification = self.effective_item_classifications[name]
            collect_extras = self.effective_item_collect_extras[name]
        else:
            # Support for Item Link worlds creating items without calling generate_early.
            assert self.player in self.multiworld.groups
            classification, collect_extras = self.evaluate_effective_item(name)
        code = self.item_name_to_id[name]

        return LegoStarWarsTCSItem(name, classification, code, self.player, collect_extras)

    def create_event(self, name: str) -> LegoStarWarsTCSItem:
        return LegoStarWarsTCSItem(name, ItemClassification.progression, None, self.player)

    def create_items(self) -> None:
        item_pool: list[LegoStarWarsTCSItem] = []
        count_overrides: dict[str, int] = {
            "Purple Stud": 0,
            "Restart Level Trap": 0,
            "Progressive Bonus Level": 6,
            "Progressive Score Multiplier": 5,
            # Default all Minikit items to `0`,
            **dict.fromkeys(MINIKITS_BY_NAME.keys(), 0),
            # then set the count for the Minikit bundle size that is being used.
            self.minikit_bundle_name: self.minikit_bundle_count,
        }

        for item in self.item_name_to_id:
            count = count_overrides.get(item, 1)
            for _ in range(count):
                item_pool.append(self.create_item(item))

        num_to_fill = len(self.multiworld.get_unfilled_locations(self.player))

        filler_to_make = num_to_fill - len(item_pool)
        # More items than locations does not crash, but would be a bug, and should not happen if we can help it.
        assert filler_to_make >= 0, f"Lego Star Wars TCS: There are not enough locations for all items"
        for _ in range(filler_to_make):
            item_pool.append(self.create_item("Purple Stud"))

        self.multiworld.itempool.extend(item_pool)

    def create_region(self, name: str) -> Region:
        r = Region(name, self.player, self.multiworld)
        self.multiworld.regions.append(r)
        return r

    def create_regions(self) -> None:
        cantina = self.create_region(self.origin_region_name)
        for episode_number in range(1, 7):
            episode_room = self.create_region(f"Episode {episode_number} Room")
            cantina.connect(episode_room, f"Episode {episode_number} Door")

            episode_chapters = EPISODE_TO_CHAPTER_AREAS[episode_number]
            for chapter_number, chapter in enumerate(episode_chapters, start=1):
                chapter_region = self.create_region(chapter.name)

                entrance_name = f"Episode {episode_number} Room, Chapter {chapter_number} Door"
                episode_room.connect(chapter_region, entrance_name)

                # Completion.
                completion_name = f"{chapter.short_name} Completion"
                completion_loc = LegoStarWarsTCSLocation(self.player, completion_name,
                                                         self.location_name_to_id[completion_name], chapter_region)
                chapter_region.locations.append(completion_loc)
                # Completion Gold Brick event.
                completion_gold_brick = LegoStarWarsTCSLocation(self.player, f"{completion_name} - Gold Brick",
                                                                None, chapter_region)
                completion_gold_brick.place_locked_item(self.create_event(GOLD_BRICK_EVENT_NAME))
                chapter_region.locations.append(completion_gold_brick)

                # True Jedi.
                true_jedi_name = f"{chapter.short_name} True Jedi"
                true_jedi_loc = LegoStarWarsTCSLocation(self.player, true_jedi_name,
                                                        self.location_name_to_id[true_jedi_name], chapter_region)
                chapter_region.locations.append(true_jedi_loc)
                # True Jedi Gold Brick event.
                true_jedi_gold_brick = LegoStarWarsTCSLocation(self.player, f"{true_jedi_name} - Gold Brick",
                                                               None, chapter_region)
                true_jedi_gold_brick.place_locked_item(self.create_event(GOLD_BRICK_EVENT_NAME))
                chapter_region.locations.append(true_jedi_gold_brick)

                # Power Brick.
                power_brick_location_name = chapter.power_brick_location_name
                power_brick_location = LegoStarWarsTCSLocation(self.player, power_brick_location_name,
                                                               self.location_name_to_id[power_brick_location_name],
                                                               chapter_region)
                chapter_region.locations.append(power_brick_location)

                # Character Purchases in the shop.
                # Character purchases unlocked upon completing the chapter (normally in Story mode).
                for shop_unlock in sorted(chapter.shop_unlocks):
                    shop_location = LegoStarWarsTCSLocation(self.player, shop_unlock,
                                                            self.location_name_to_id[shop_unlock], chapter_region)
                    chapter_region.locations.append(shop_location)

                # Minikits.
                chapter_minikits = self.create_region(f"{chapter.name} Minikits")
                chapter_region.connect(chapter_minikits, f"{chapter.name} - Collect All Minikits")
                for i in range(1, 11):
                    loc_name = f"{chapter.short_name} Minikit {i}"
                    location = LegoStarWarsTCSLocation(self.player, loc_name, self.location_name_to_id[loc_name],
                                                       chapter_minikits)
                    chapter_minikits.locations.append(location)
                # All Minikits Gold Brick.
                all_minikits_gold_brick = LegoStarWarsTCSLocation(self.player, f"{chapter_minikits.name} - Gold Brick",
                                                                  None, chapter_minikits)
                all_minikits_gold_brick.place_locked_item(self.create_event(GOLD_BRICK_EVENT_NAME))
                chapter_minikits.locations.append(all_minikits_gold_brick)

        # Bonuses.
        bonuses = self.create_region("Bonuses")
        cantina.connect(bonuses, "Bonuses Door")
        gold_brick_costs: dict[int, list[BonusArea]] = {}
        for area in BONUS_AREAS:
            gold_brick_costs.setdefault(area.item_requirements["Gold Brick"], []).append(area)

        previous_gold_brick_region = bonuses
        for gold_brick_cost, areas in sorted(gold_brick_costs.items(), key=lambda t: t[0]):
            if gold_brick_cost == 0:
                region = bonuses
            else:
                region = self.create_region(f"{gold_brick_cost} Gold Bricks Collected")
                player = self.player
                previous_gold_brick_region.connect(
                    region, f"Collect {gold_brick_cost} Gold Bricks",
                    lambda state, cost_=gold_brick_cost, item_=GOLD_BRICK_EVENT_NAME: state.has(item_, player, cost_))
                previous_gold_brick_region = region

            for area in areas:
                location = LegoStarWarsTCSLocation(self.player, area.name, self.location_name_to_id[area.name], region)
                region.locations.append(location)
                if not area.gold_brick:
                    continue
                gold_brick_location = LegoStarWarsTCSLocation(self.player, f"{area.name} - Gold Brick", None, region)
                gold_brick_location.place_locked_item(self.create_event(GOLD_BRICK_EVENT_NAME))
                region.locations.append(gold_brick_location)

        # Indiana Jones shop purchase. Unlocks in the shop after watching the Lego Indiana Jones trailer.
        purchase_indy_name = "Purchase Indiana Jones"
        purchase_indy = LegoStarWarsTCSLocation(self.player, purchase_indy_name,
                                                self.location_name_to_id[purchase_indy_name], bonuses)
        bonuses.locations.append(purchase_indy)

        # 'All Episodes' character purchases.
        all_episodes = self.create_region("All Episodes Unlocked")
        cantina.connect(all_episodes, "Unlock All Episodes")
        all_episodes_purchases = [
            "Purchase IG-88",
            "Purchase Dengar",
            "Purchase 4-LOM",
            "Purchase Ben Kenobi (Ghost)",
            "Purchase Anakin Skywalker (Ghost)",
            "Purchase Yoda (Ghost)",
            "Purchase R2-Q5",
        ]
        for purchase in all_episodes_purchases:
            location = LegoStarWarsTCSLocation(self.player, purchase, self.location_name_to_id[purchase], all_episodes)
            all_episodes.locations.append(location)

        # Starting character purchases.
        starting_purchases = [
            "Purchase Gonk Droid",
            "Purchase PK Droid",
        ]
        for purchase in starting_purchases:
            location = LegoStarWarsTCSLocation(self.player, purchase, self.location_name_to_id[purchase], cantina)
            cantina.locations.append(location)

        # Victory event
        victory = LegoStarWarsTCSLocation(self.player, "Minikits Goal", parent=cantina)
        victory.place_locked_item(self.create_event("Slave I"))
        cantina.locations.append(victory)

        from Utils import visualize_regions
        visualize_regions(cantina, "LegoStarWarsTheCompleteSage_Regions.puml", show_entrance_names=True)

    def set_abilities_rule(self, spot: Location | Entrance, abilities: CharacterAbility):
        if abilities:
            player = self.player
            ability_names = [ability.name for ability in abilities]
            if len(ability_names) == 1:
                ability_name = ability_names[0]
                set_rule(spot, lambda state: state.has(ability_name, player))
            else:
                set_rule(spot, lambda state: state.has_all(ability_names, player))

    def set_rules(self) -> None:
        player = self.player

        # Episodes.
        for episode_number in range(1, 7):
            if episode_number != 1:
                episode_entrance = self.get_entrance(f"Episode {episode_number} Door")
                item = f"Episode {episode_number} Unlock"
                set_rule(episode_entrance, lambda state, item_=item: state.has(item_, player))

            # Set chapter requirements.
            episode_chapters = EPISODE_TO_CHAPTER_AREAS[episode_number]
            for chapter_number, chapter in enumerate(episode_chapters, start=1):
                entrance = self.get_entrance(f"Episode {episode_number} Room, Chapter {chapter_number} Door")

                required_character_names = CHAPTER_AREA_CHARACTER_REQUIREMENTS[chapter.short_name]
                if required_character_names:
                    if len(required_character_names) == 1:
                        item = next(iter(required_character_names))
                        set_rule(entrance, lambda state, item_=item: state.has(item_, player))
                    else:
                        items = tuple(sorted(required_character_names))
                        set_rule(entrance, lambda state, items_=items: state.has_all(items_, player))

                entrance_abilities = CharacterAbility.NONE
                for character_name in required_character_names:
                    generic_character = CHARACTERS_AND_VEHICLES_BY_NAME[character_name]
                    entrance_abilities |= generic_character.abilities

                def set_chapter_spot_abilities_rule(spot: Location | Entrance, abilities: CharacterAbility):
                    # Remove any requirements already satisfied by the chapter entrance before setting the rule.
                    self.set_abilities_rule(spot, abilities & ~entrance_abilities)

                # Set Power Brick logic
                power_brick = self.get_location(chapter.power_brick_location_name)
                set_chapter_spot_abilities_rule(power_brick, chapter.power_brick_ability_requirements)

                # Set Minikits logic
                all_minikits_entrance = self.get_entrance(f"{chapter.name} - Collect All Minikits")
                set_chapter_spot_abilities_rule(all_minikits_entrance, chapter.all_minikits_ability_requirements)

        # Bonus levels.
        entrance = self.get_entrance("Bonuses Door")
        set_rule(entrance, lambda state: state.has("Progressive Bonus Level", player))
        entrance_requirements = Counter(["Progressive Bonus Level"])
        gold_brick_requirements: set[int] = set()
        for area in BONUS_AREAS:
            requirements = area.item_requirements - entrance_requirements
            gold_brick_requirements.add(requirements[GOLD_BRICK_EVENT_NAME])
            # Gold Brick requirements are set on the entrances.
            requirements[GOLD_BRICK_EVENT_NAME] = 0
            if requirements.total():
                completion = self.get_location(area.name)
                gold_brick = self.get_location(f"{area.name} - Gold Brick")
                item_counts: Mapping[str, int] = dict(+requirements)
                set_rule(completion, lambda state, items_=item_counts: state.has_all_counts(items_, player))
                set_rule(gold_brick, completion.access_rule)
        # Locations with 0 Gold Bricks required are added to the base Bonuses region.
        gold_brick_requirements.discard(0)

        for gold_brick_count in gold_brick_requirements:
            entrance = self.get_entrance(f"Collect {gold_brick_count} Gold Bricks")
            set_rule(
                entrance,
                lambda state, item_=GOLD_BRICK_EVENT_NAME, count_=gold_brick_count: state.has(item_, player, count_))

        # 'All Episodes' character unlocks.
        entrance = self.get_entrance("Unlock All Episodes")
        # Episode 1 is currently always unlocked.
        entrance_unlocks = [f"Episode {i} Unlock" for i in range(2, 7)]
        set_rule(entrance, lambda state: state.has_all(entrance_unlocks, player))

        # Victory.
        victory = self.get_location("Minikits Goal")
        set_rule(victory, lambda state: state.has(self.minikit_bundle_name, player, self.goal_minikit_bundle_count))

        self.multiworld.completion_condition[self.player] = lambda state: state.has("Slave I", player)

    @classmethod
    def stage_fill_hook(cls,
                        multiworld: MultiWorld,
                        progitempool: list[Item],
                        usefulitempool: list[Item],
                        filleritempool: list[Item],
                        fill_locations: list[Location],
                        ) -> None:
        game_player_ids = set(multiworld.get_game_players(cls.game))
        game_minimal_player_ids = {player for player in game_player_ids
                                   if multiworld.worlds[player].options.accessibility == "minimal"}

        def sort_func(item: Item):
            if item.player in game_player_ids and item.name in MINIKITS_BY_NAME:
                if item.player in game_minimal_player_ids:
                    # For minimal players, place Minikits first. This helps prevent fill from dumping logically relevant
                    # items into unreachable locations and reducing the number of reachable locations to fewer than the
                    # number of items remaining to be placed.
                    #
                    # Placing only the non-required Minikits first or slightly more than the number of non-required
                    # Minikits first was also tried, but placing all Minikits first seems to give fill the best chance
                    # of succeeding.
                    return 1
                else:
                    # For non-minimal players, place Minikits last. The helps prevent fill from filling most/all
                    # reachable locations with the Minikit macguffins that are only required for the goal.
                    return -1
            else:
                # Python sorting is stable, so this will leave everything else in its original order.
                return 0

        progitempool.sort(key=sort_func)

    def collect(self, state: CollectionState, item: LegoStarWarsTCSItem) -> bool:
        changed = super().collect(state, item)
        if changed:
            extras = item.collect_extras
            if extras is not None:
                state.prog_items[self.player].update(item.collect_extras)
            return True
        return False

    def remove(self, state: CollectionState, item: LegoStarWarsTCSItem) -> bool:
        changed = super().remove(state, item)
        if changed:
            extras = item.collect_extras
            if extras is not None:
                state.prog_items[self.player].subtract(item.collect_extras)
            return True
        return False

    def fill_slot_data(self) -> Mapping[str, Any]:
        return {
            "apworld_version": constants.AP_WORLD_VERSION,
            **self.options.as_dict(
                "received_item_messages",
                "checked_location_messages",
                "minikit_goal_amount",
                "minikit_bundle_size",
            )
        }


