import asyncio
import logging
import time
from enum import IntEnum

from Utils import async_start

from . import ClientComponent
from .studs import give_studs
from ..common import StaticUint
from ..common_addresses import CURRENT_AREA_ADDRESS, is_actively_playing, player_character_entity_iter, CustomSaveFlags1
from ..events import subscribe_event, OnReceiveSlotDataEvent, OnGameWatcherTickEvent, OnAreaChangeEvent
from ..type_aliases import TCSContext
from ...levels import (
    AREA_ID_TO_CHAPTER_AREA,
    VEHICLE_CHAPTER_SHORTNAMES,
    AREA_ID_TO_BONUS_AREA,
    VEHICLE_BONUS_AREA_NAMES,
    SHORT_NAME_TO_CHAPTER_AREA,
    BONUS_NAME_TO_BONUS_AREA,
)

logger = logging.getLogger("Client")
debug_logger = logging.getLogger("TCS Debug")


# Player death count in the current area. Resets to zero upon area change.
PLAYER_DEATH_COUNT_IN_CURRENT_AREA = StaticUint(0x951224)
# Player death count in the current level. Resets to zero upon level change.
# PLAYER_DEATH_COUNTER_IN_CURRENT_LEVEL = StaticUint(0x87b2d0)


# Flags for the currently active 'cheats' (Extras).
CHEAT_FLAGS = StaticUint(0x950d8c)
# For some reason, if the in-area death count is 0, but flag cheat 0x2000 is active, then the in-area death count is
# increased to 1.
CHEAT_FLAGS_STARTING_DEATH_COUNT = 0x2000


# There are a maximum of 8 playable characters in a level, pointers to their 'character entity' objects are in an
# entity*[8] array at this address.
PLAYER_CHARACTER_POINTERS_ARRAY_ADDRESS = 0x93d7f0


VEHICLE_AMNESTY_AREA_IDS = frozenset({
    SHORT_NAME_TO_CHAPTER_AREA["2-1"].area_id,
    SHORT_NAME_TO_CHAPTER_AREA["2-5"].area_id,
    SHORT_NAME_TO_CHAPTER_AREA["4-6"].area_id,
    SHORT_NAME_TO_CHAPTER_AREA["5-1"].area_id,
    SHORT_NAME_TO_CHAPTER_AREA["5-3"].area_id,
    SHORT_NAME_TO_CHAPTER_AREA["6-6"].area_id,
    BONUS_NAME_TO_BONUS_AREA["Mos Espa Pod Race (Original)"].area_id,
    BONUS_NAME_TO_BONUS_AREA["Anakin's Flight"].area_id,
    BONUS_NAME_TO_BONUS_AREA["Gunship Cavalry (Original)"].area_id,
})


class CharacterState(IntEnum):
    # # Original name "NoContext" is converted to NO_CONTEXT for enum names. Other names follow the same pattern.
    NO_CONTEXT = 0x0
    # LAND_JUMP = 0x1  # Landing from a normal jump
    # LAND_JUMP_2 = 0x2
    # LAND_FLIP = 0x3
    # LAND_COMBO_JUMP = 0x4
    # COMBO = 0x5  # Lightsaber basic (combo) attack
    # WEAPON_IN = 0x6  # Putting weapon away
    # WEAPON_OUT = 0x7  # Getting weapon out
    # FORCE = 0x8
    # COMBO_ROTATE = 0x9  # Unknown use
    # SHOOT = 0xa
    # INTERFACE = 0xb  # Interacting with a Bounty Hunter/Astromech/Protocol/Imperial panel
    # BLOCK = 0xc  # Unknown use
    # LAND_LUNGE = 0xd  # Landing from Jedi single-jump attack
    # # "LandSlam" appears to be next, but does not match the observed order
    # CRAWLING_THROUGH_VENT_ = 0xf  # Real name unknown
    # SWIPE = 0x10  # Lightsaber 'backwards attack' when an enemy is directly behind the character
    # TUBE = 0x11  # Floating in an updraft (internally, updrafts are called tubes)
    # FORCE_THROW = 0x12  # Unknown use, perhaps not implemented
    # HOVER_UP = 0x13  # Unknown use
    # ROCKET = 0x14  # Firing a Bounty Hunter Rocket from the Bounty Hunter Rockets Extra
    # TAKE_HIT = 0x15
    # ZAP = 0x16  # Astromech/jawa zap
    # DEACTIVATED = 0x17  # Zapped or force confused, also seen sometimes when exiting vehicles
    # HOLD = 0x18  # Blocking with a melee weapon
    # # "LandSpecial" appears to be next, but does not match the observed order
    # COMMUNICATE = 0x1a  # Using a Walkie Talkie (Battle Droid (Commander)/Imperial Spy)
    # # The next names do not match observed order and some do not seem to exist as force abilities in the game:
    # # "ForcePushed"
    # # "ForceDeflect"
    # # "ForceFrozen"
    # USING_FORCE_LIGHTNING_CHOKE_OR_CONFUSION_ = 0x1b  # Real name unknown
    # BEING_FORCED_ = 0x1c  # Real name unknown. Held by force lightning/choke or pushed by force as a droid
    # UNKNOWN_1D = 0x1d  # No idea
    # LAND_SLAM_ = 0x1e  # Real name unknown
    # FORCE_GRAPPLE_LEAP_ = 0x1f  # Real name unknown
    # BACK_FLIP = 0x20  # General Grievous' backflip
    # RECOIL = 0x21  # Unknown use, looks like being pushed backwards by something, maybe an air vent
    # FORCED_BACK = 0x22  # Unknown use, looks the same as RECOIL
    # # Unknown use, perhaps for an older drop-in implementation. Jedi go into a blocking animation. Characters
    # # sometimes instantly shrink tiny and then scale up to normal over time.
    # DROP_IN = 0x23
    # DROP_OUT = 0x24  # Unknown use, teleports P1 to P2 or vice versa
    # DODGE = 0x25  # When a blaster character performs a sidestep dodge of incoming blaster fire
    # PUNCH = 0x26  # Non Jedi (non-combo?) melee attacking
    # PUSH = 0x27  # Pushing a block
    # PUSH_SPINNER = 0x28  # Pushing a rotatable object
    # LAND_COMBAT_ROLL = 0x29  # Landing from a blaster character's roll, also used by Stormtroopers when they flop
    # TURN = 0x2a  # Vehicle 180 degree turn around

    DOOMED = 0x2b  # Falling death, body parts fall through the floor, seems to work on vehicles too

    # # "BuildIt" appears to be next, but does not match the observed order
    # GRABBED = 0x2c  # Suspected to be grabbed by a crane's claw, makes the character appear to be falling
    # BUILD_IT = 0x2d  # Building bricks
    # # "SpecialMoveVictim" appears to be next, but does not match the observed order
    # THERMAL_DETONATOR_ = 0x2e  # Real name unknown. Throwing a thermal detonator
    # UNKNOWN_2f = 0x2f  # Unknown use, it is not clear if this is actually "SpecialMoveVictim" or something else.
    # UNKNOWN_30 = 0x30  # Unknown use, see 0x2f
    # ROLL = 0x31  # Droideka roll movement
    # UN_ROLL = 0x32  # Droideka unrolling into standing pose
    # SLIDE = 0x33  # Sliding down a slippery surface, e.g. ice in 5-2
    # BEEN_DRAGGED = 0x34  # Unknown use
    # ZIP_DOWN = 0x35  # Unknown use
    # LOOP = 0x36  # Vehicle loop in-place
    # POO = 0x37  # Make ridden animal poo when the Fertilizer Extra is enabled
    # GRAB = 0x38  # Unknown use
    # EATEN = 0x39  # Unknown use, maybe Rancor related, makes the character disappear
    # BARREL_ROLL = 0x3a  # Vehicle aileron roll that is commonly mistakenly called a barrel roll
    # GET_IN = 0x3b  # Getting into a vehicle
    # # "Flatten" appears to be next, but does not match the observed order
    # IN_VEHICLE_ = 0x3c  # Real name unknown
    # FLATTEN = 0x3d  # Flattened by a vehicle
    # # Used by the vehicle in 5-2 that C-3PO is supposed to stand on the back of and then get launched by the vehicle,
    # # like a bucking horse.
    # BUCK = 0x3e
    # # "Eat"
    # # "Disorientate"
    # # "ZappedByFloor"  # Maybe this is used in 6-5?
    #
    # # These all look like they could be Lego Batman 1-specific states:
    # # "Climb"
    # # "Tightrope"
    # # "WallShuffle"
    # # "Grapple"
    # # "PlaceDetonator"
    # # "PickUpDetonator"
    # # "Float"
    # # "Signal"
    # # "Batarang"
    # # "Hang"
    # # "Glide"
    # # "Catch"
    # # "AttractoTarget"
    # # "AttractoDeposit"
    # # "Sonar"
    # # "LedgeTerrain"
    # # "Transform"
    # # "WallJumpWait"
    # # "SuperCarry"
    # # "PushObstacle"
    # # "Stunned"
    # # "Security"
    # # "Ballooning"
    # # "ThrowQuick"
    #
    # # ???
    # # "DieAir"
    # # "DieGround"
    #
    # # Seems like these could be Lego Indiana Jones-specific states
    # # "Whip"
    # # Is there a net in LIJ1?
    # # "NetWait"
    #
    # # Known names stop here besides "Walk" and "Idle", and there are a bunch of gaps, but the observed states
    # # continue:
    # VEHICLE_RELATED_41 = 0x41  # Seen very briefly sometimes when getting into vehicles
    # USING_ZIP_UP_ = 0x47  # Real name unknown. Using a grapple point with a grapple character
    # PULLING_LEVER_ = 0x4a  # Real name unknown

    THROWN_BY_FORCE_LIGHTNING_OR_CHOKE_ = 0x5f  # Real name unknown. Throw death, body parts have physics.

    # USING_HAT_MACHINE_ = 0x61  # Real name unknown. Used by both characters with and without hats.
    # # "Idle"
    # IDLE = 0xFF

    @classmethod
    def get(cls, ctx: TCSContext, character_address: int):
        return cls(ctx.read_uchar(character_address + 0x7b5, raw=True))

    def set(self, ctx: TCSContext, character_address: int):
        ctx.write_byte(character_address + 0x7b5, self.value, raw=True)


class CharacterDeathState(IntEnum):
    ALIVE = 0
    UNKNOWN_BUT_ALSO_DEAD = 1
    DEAD = 2

    @classmethod
    def get(cls, ctx: TCSContext, character_address: int):
        return cls(ctx.read_uchar(character_address + 0x28b, raw=True))

    def set(self, ctx: TCSContext, character_address: int):
        ctx.write_byte(character_address + 0x28b, self.value, raw=True)


class DeathLinkManager(ClientComponent):
    pending_received_death = False
    last_received_death_message: str = ""

    death_link_enabled = False

    waiting_for_respawn = False
    normal_death_link_amnesty = 0
    vehicle_death_link_amnesty = 0

    normal_death_amnesty_remaining = 0
    vehicle_death_amnesty_remaining = 0

    last_death_amnesty = time.time()

    death_link_stud_loss: int = 0
    death_link_stud_loss_scaling: bool = False

    _expected_area_death_count: int = 999_999_999

    @subscribe_event
    def init_from_slot_data(self, event: OnReceiveSlotDataEvent) -> None:
        slot_data = event.slot_data
        ctx = event.context

        # Death Link did not exist as an option in older apworld versions.
        if event.generator_version < (1, 2, 0):
            self.death_link_enabled = False
            self.normal_death_link_amnesty = 0
            self.vehicle_death_link_amnesty = 0
            self.death_link_stud_loss = 0
            self.death_link_stud_loss_scaling = False
        else:
            self.death_link_enabled = bool(slot_data["death_link"])
            self.normal_death_link_amnesty = slot_data["death_link_amnesty"]
            self.vehicle_death_link_amnesty = slot_data["vehicle_death_link_amnesty"]
            self.death_link_stud_loss = slot_data["death_link_studs_loss"]
            self.death_link_stud_loss_scaling = bool(slot_data["death_link_studs_loss_scaling"])

        if event.first_time_setup:
            # Write whether Death Link is enabled into slot data.
            self._update_death_link(ctx, self.death_link_enabled)
        else:
            # Read whether Death Link is enabled from save data, in-case the user toggled it on/off in the client.
            self.death_link_enabled = CustomSaveFlags1.DEATH_LINK_ENABLED.is_set(ctx)
            # Update the client tags for whether Death Link is enabled/disabled.
            self._update_client_tags(ctx)

        # Initialise remaining amnesty.
        self.normal_death_amnesty_remaining = self.normal_death_link_amnesty
        self.vehicle_death_amnesty_remaining = self.vehicle_death_link_amnesty

        # Set the expected death count to its current value.
        self._expected_area_death_count = PLAYER_DEATH_COUNT_IN_CURRENT_AREA.get(ctx)

    def _update_client_tags(self, ctx: TCSContext):
        """Update the client's tags to add/remove the DeathLink tag."""
        async_start(ctx.update_death_link(self.death_link_enabled))

    def _update_death_link(self, ctx: TCSContext, enabled: bool):
        if enabled:
            # The game's death counter increments even with Death Link is disabled, so update the current expected death
            # count to whatever the game's death counter is set to, to prevent sending a death as soon as Death Link is
            # enabled.
            self._expected_area_death_count = PLAYER_DEATH_COUNT_IN_CURRENT_AREA.get(ctx)
            CustomSaveFlags1.DEATH_LINK_ENABLED.set(ctx)
        else:
            CustomSaveFlags1.DEATH_LINK_ENABLED.unset(ctx)
        self.death_link_enabled = enabled
        self._update_client_tags(ctx)

    def toggle_death_link(self, ctx: TCSContext):
        """Toggle Death Link on/off."""
        self._update_death_link(ctx, not self.death_link_enabled)

    @staticmethod
    def _get_kill_state_to_set(ctx: TCSContext) -> CharacterState:
        area_id = CURRENT_AREA_ADDRESS.get(ctx)
        area = AREA_ID_TO_CHAPTER_AREA.get(area_id)
        is_vehicle_or_unknown: bool
        if area is None:
            bonus_area = AREA_ID_TO_BONUS_AREA.get(area_id)
            # if `bonus_area` is also None, then the player is somewhere that the apworld does not have information
            # about currently, e.g. an Episode's Minikit Bonus or 2-player Arcade.
            is_vehicle_or_unknown = bonus_area is None or bonus_area.name in VEHICLE_BONUS_AREA_NAMES
        else:
            is_vehicle_or_unknown = area.short_name in VEHICLE_CHAPTER_SHORTNAMES
        if is_vehicle_or_unknown:
            # Many of the vehicle levels ignore THROWN_BY_FORCE_LIGHTNING_OR_CHOKE_.
            return CharacterState.DOOMED
        else:
            # It is more pleasing for the character's parts to have physics instead of disappearing through the floor.
            return CharacterState.THROWN_BY_FORCE_LIGHTNING_OR_CHOKE_

    @staticmethod
    async def _kill_player_controlled_characters(ctx: TCSContext) -> bool:
        kill_state = DeathLinkManager._get_kill_state_to_set(ctx)
        expecting_death = []
        for player_number, character_address in player_character_entity_iter(ctx):
            if CharacterDeathState.get(ctx, character_address) == CharacterDeathState.ALIVE:
                expecting_death.append((player_number, character_address))
                kill_state.set(ctx, character_address)

        killed_at_least_one = len(expecting_death) > 0

        if kill_state != CharacterState.DOOMED:
            # The THROWN_BY_FORCE_LIGHTNING_OR_CHOKE_ state can take some time before it actually kills, especially for
            # Player 2 who sometimes ignores the state entirely for some reason.
            await asyncio.sleep(0.05)
            for player_number, character_address in expecting_death:
                if CharacterDeathState.get(ctx, character_address) == CharacterDeathState.ALIVE:
                    # Use the more forceful DOOMED death state because it is better at interrupting current actions,
                    # especially for Player 2.
                    CharacterState.DOOMED.set(ctx, character_address)
                    debug_logger.info("Retrying killing player %i with DOOMED", player_number)

            # Force kill implementation if needed.
            # if expecting_death:
            #     # Force kill characters that were still alive even after the check attempts.
            #     for player_number, character_address in expecting_death:
            #         debug_logger.info("Force killing player %i", player_number)
            #         CharacterDeathState.DEAD.set(ctx, character_address)

        return killed_at_least_one

    async def kill_player_characters(self, ctx: TCSContext) -> bool:
        self.waiting_for_respawn = True
        return await self._kill_player_controlled_characters(ctx)

    @staticmethod
    def _find_dead_player_controlled_character(ctx: TCSContext) -> tuple[bool, int]:
        for player_number, character_address in player_character_entity_iter(ctx):
            if CharacterDeathState.get(ctx, character_address) != CharacterDeathState.ALIVE:
                return True, player_number
        return False, -1

    @subscribe_event
    async def update_game_state(self, event: OnGameWatcherTickEvent) -> None:
        ctx = event.context
        if not self.death_link_enabled or not ctx.is_in_game() or not is_actively_playing(ctx):
            return

        now = time.time()

        if now < ctx.last_death_link + 2.25:
            # Respawn is typically 2.0s, so ignore any deaths to send and delay any received within just above this
            # time.
            # If something goes horrendously wrong with this Death Link implementation, this has the added benefit of
            # limiting death spam.
            return
        if self.waiting_for_respawn:
            dead_player_controlled_characters_found, _ = self._find_dead_player_controlled_character(ctx)
            if dead_player_controlled_characters_found:
                # Still dead, so don't send any more deaths or receive any more deaths.
                return
            else:
                self.waiting_for_respawn = False
                # Update the expected death count to match however many player controlled characters were killed by the
                # received death.
                self._expected_area_death_count = PLAYER_DEATH_COUNT_IN_CURRENT_AREA.get(ctx)
        # Receive death.
        if self.pending_received_death:
            # Kill player characters
            # TODO: Entirely skip the received death if all player characters are already dead.
            if await self.kill_player_characters(ctx):
                # At least one character was killed, so the death has been received.
                self.pending_received_death = False
                ctx.text_display.priority_message(self.last_received_death_message)
                # Remove studs from the player.
                studs_to_lose = self.death_link_stud_loss
                if studs_to_lose > 0:
                    if self.death_link_stud_loss_scaling:
                        studs_to_lose *= ctx.acquired_generic.current_score_multiplier
                    give_studs(ctx, -studs_to_lose, only_give_if_in_level=True, allow_power_up_multiplier=False)
            return

        if now < self.last_death_amnesty + 2.25:
            # Do not send another death if sending a death through Death Link was recently prevented due to amnesty.
            return

        # Check if players have died by comparing the expected death count to the actual death count.
        player_death_count = PLAYER_DEATH_COUNT_IN_CURRENT_AREA.get(ctx)
        expected_death_count = self._expected_area_death_count
        if player_death_count == expected_death_count:
            # Nothing to do.
            return
        elif player_death_count < expected_death_count:
            # The area has changed, resetting the game's death counter. Note that there is a delay between when the area
            # changes and when the game's death counter gets updated.
            self._expected_area_death_count = player_death_count
            return
        elif player_death_count == 1 and (CHEAT_FLAGS_STARTING_DEATH_COUNT & CHEAT_FLAGS.get(ctx)):
            # The game's level update function sets the in-area death count to at least 1 when an Extra with this flag
            # is active. I have no idea why.
            self._expected_area_death_count = 1
            return

        # Update for new deaths.
        self._expected_area_death_count = player_death_count

        # todo: Customise the death cause.
        #  Ideas:
        #  f"{alias name} crashed their {vehicle name}"
        #  f"{alias name} lost their studs"
        #  f"Caused by {alias name}'s {character name}"
        #  Special messages for when both P1 and P2 are player controlled?
        #  f"{alias name}'s P{player number} crashed their {vehicle name}"
        #  f"{alias name}'s P{player number} lost their studs"
        #  Special messages only when both P1 and P2 are player controlled and are the same character?
        #  f"Caused by {alias name}'s {character name} (P{player number})"

        amnesty_remaining = 0
        if CURRENT_AREA_ADDRESS.get(ctx) in VEHICLE_AMNESTY_AREA_IDS:
            if self.vehicle_death_amnesty_remaining <= 0:
                send_death = True
                # Reset amnesty.
                self.vehicle_death_amnesty_remaining = self.vehicle_death_link_amnesty
            else:
                send_death = False
                self.vehicle_death_amnesty_remaining -= 1
                amnesty_remaining = self.vehicle_death_amnesty_remaining
        else:
            if self.normal_death_amnesty_remaining <= 0:
                send_death = True
                # Reset amnesty.
                self.normal_death_amnesty_remaining = self.normal_death_link_amnesty
            else:
                send_death = False
                self.normal_death_amnesty_remaining -= 1
                amnesty_remaining = self.normal_death_amnesty_remaining

        if send_death:
            ctx.text_display.priority_message("DeathLink: Death Sent")
            # todo: This could probably be a fire-and-forget task.
            await ctx.send_death()
            # Ideally, we would kill any other player characters too, just like when receiving a death, but in levels
            # where death instantly respawns the player at an earlier checkpoint, this would result in the player, that
            # died, dying a second time after respawning at the checkpoint.
            # await self.kill_player_characters(ctx)
        else:
            if amnesty_remaining == 0:
                ctx.text_display.priority_message("DeathLink: No amnesty remaining")
            else:
                ctx.text_display.priority_message(f"DeathLink: {amnesty_remaining} amnesty remaining")

    def on_deathlink(self, ctx: TCSContext, message: str):
        if self.pending_received_death:
            # The current pending death is going to be skipped because another has been received before the current
            # pending death could be processed.
            ctx.text_display.priority_message(self.last_received_death_message)
        self.last_received_death_message = message
        self.pending_received_death = True

    @subscribe_event
    def on_area_change(self, _event: OnAreaChangeEvent) -> None:
        # The area has changed, so the expected death count should reset. The area changes before the game resets the
        # death count, so the DeathLinkManager relies on the OnGameWatcherTickEvent to reduce _expected_area_death_count
        # from this very large dummy value to the proper value.
        self._expected_area_death_count = 999_999_999
        debug_logger.info("Reset expected death count to 0 upon area change.")
