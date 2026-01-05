from unittest import TestCase

from ..items import CHARACTER_SHOP_SLOTS, CHARACTERS_AND_VEHICLES_BY_NAME
from ..locations import LOCATION_NAME_TO_ID


class TestLocations(TestCase):
    def test_shop_slot_locations(self):
        for character in CHARACTER_SHOP_SLOTS.keys():
            self.assertIn(character, CHARACTERS_AND_VEHICLES_BY_NAME)
            self.assertIn(CHARACTERS_AND_VEHICLES_BY_NAME[character].purchase_location_name, LOCATION_NAME_TO_ID)
