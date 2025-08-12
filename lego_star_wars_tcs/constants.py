from enum import auto, IntFlag

GAME_NAME = "Lego Star Wars: The Complete Saga"

AP_WORLD_VERSION: tuple[int, int, int] = (1, 1, 0)


# todo: These are the abilities from the manual logic, not the real abilities.
class CharacterAbility(IntFlag):
    NONE = 0
    ASTROMECH = auto()
    BLASTER = auto()
    BOUNTY_HUNTER = auto()
    HOVER = auto()
    HIGH_JUMP = auto()
    IMPERIAL = auto()
    JEDI = auto()
    PROTOCOL_DROID = auto()
    SHORTIE = auto()
    SITH = auto()
    # todo: Lots more abilities to add to split up and replace the basic existing ones...
    # GHOST = auto()
    # DROID = auto()
    # UNTARGETABLE = auto()  # Are there any characters other than Ghosts?
    VEHICLE_TIE = auto()
    VEHICLE_TOW = auto()
    # VEHICLE_BLASTER = auto()


# Workaround for Python 3.10 support. Iterating Flag instances was only added in Python 3.11.
# There is probably a better way to do this, but it will get the job done.
if getattr(CharacterAbility.NONE, "__iter__", None) is None:
    def __iter__(self: CharacterAbility):
        none_flag = CharacterAbility.NONE
        for flag in CharacterAbility:
            if flag is not none_flag and flag in self:
                yield flag
    CharacterAbility.__iter__ = __iter__  # type: ignore
    del __iter__


ASTROMECH = CharacterAbility.ASTROMECH
BLASTER = CharacterAbility.BLASTER
BOUNTY_HUNTER = CharacterAbility.BOUNTY_HUNTER
HOVER = CharacterAbility.HOVER
HIGH_JUMP = CharacterAbility.HIGH_JUMP
IMPERIAL = CharacterAbility.IMPERIAL
JEDI = CharacterAbility.JEDI
PROTOCOL_DROID = CharacterAbility.PROTOCOL_DROID
SHORTIE = CharacterAbility.SHORTIE
SITH = CharacterAbility.SITH
VEHICLE_TIE = CharacterAbility.VEHICLE_TIE
VEHICLE_TOW = CharacterAbility.VEHICLE_TOW

# todo: VEHICLE_TOW can probably be included in the future too.
# todo: GHOST can probably be included in the future too.
# todo: PROTOCOL_DROID_PANEL can probably be included in the future too.
RARE_AND_USEFUL_ABILITIES = ASTROMECH | BOUNTY_HUNTER | HIGH_JUMP | SHORTIE | SITH | PROTOCOL_DROID | HOVER

GOLD_BRICK_EVENT_NAME = "Gold Brick"
