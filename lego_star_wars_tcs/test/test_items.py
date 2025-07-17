from unittest import TestCase

from ..items import ITEM_DATA, GenericCharacterData, CHARACTER_SHOP_SLOTS, CHARACTERS_AND_VEHICLES_BY_NAME
from ..levels import SHORT_NAME_TO_CHAPTER_AREA


class TestItems(TestCase):
    def test_item_code_uniqueness(self):
        found_codes = set()
        for item in ITEM_DATA:
            if item.code == -1:
                continue
            self.assertGreater(item.code, 0)
            self.assertNotIn(item.code, found_codes)
            found_codes.add(item.code)

    def test_item_name_uniqueness(self):
        found_names = set()
        for item in ITEM_DATA:
            self.assertNotIn(item.name, found_names)
            found_names.add(item.name)

    def test_character_number_uniqueness(self):
        found_character_numbers = set()
        for item in ITEM_DATA:
            if not isinstance(item, GenericCharacterData):
                continue
            self.assertNotIn(item.character_index, found_character_numbers)
            self.assertGreaterEqual(item.character_index, 0)
            found_character_numbers.add(item.character_index)

    def test_shop_slots_count(self):
        """Test that there are the correct number of Character shop slots."""
        # The slots are from 0 to 88.
        self.assertEqual(len(CHARACTER_SHOP_SLOTS), 89)

    def test_shop_slots_characters(self):
        for character_name in CHARACTER_SHOP_SLOTS.keys():
            self.assertIn(character_name, CHARACTERS_AND_VEHICLES_BY_NAME)

    def test_shop_slots_unlocks(self):
        possible_unlocks = {
            *SHORT_NAME_TO_CHAPTER_AREA.keys(),  # Complete a story chapter (story chapters are auto-completed by the
            # client when free play is completed).
            "ALL_EPISODES",  # Complete all episode in vanilla, unlock all episodes in the rando.
            None,  # Available from the start.
            "INDY_TRAILER",  # Watch the Indy Trailer.
        }
        for area_name, _studs_cost in CHARACTER_SHOP_SLOTS.values():
            self.assertIn(area_name, possible_unlocks)
