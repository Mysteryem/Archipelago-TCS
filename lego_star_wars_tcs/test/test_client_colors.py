from typing import ClassVar
from unittest import TestCase

from ..client.client_text import COLOR_FORMATTING
from ..options import TextColorChoice, LegoStarWarsTCSOptions


class TestClientText(TestCase):
    expected_color_count: ClassVar[int] = 0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for v in LegoStarWarsTCSOptions.type_hints.values():
            if issubclass(v, TextColorChoice):
                cls.expected_color_count += 1

    def test_color_codes_are_1_byte(self):
        for name, value in COLOR_FORMATTING.items():
            with self.subTest(name):
                self.assertEqual(1, len(value.encode("utf-8")))

    def test_option_colors_exist(self):
        for value, name in TextColorChoice.name_lookup.items():
            with self.subTest(name):
                color = TextColorChoice(value)
                color_name = color.current_key_no_hex_value
                self.assertIn(color_name, COLOR_FORMATTING.keys())

    def test_options_slot_data_conversion_too_short(self):
        """Test that a list from slot data that is too short fills in missing values with their defaults."""
        result = TextColorChoice.colors_from_slot_data([])
        self.assertEqual(len(result), self.expected_color_count)

    def test_options_slot_data_conversion_too_long(self):
        """Test that a list from slot data that is too long gets truncated."""
        result = TextColorChoice.colors_from_slot_data([TextColorChoice.option_red_de0000] * 500)
        self.assertEqual(len(result), self.expected_color_count)

    def test_options_slot_data_conversion_unknown_value(self):
        """
        Test that a list from slot data that has unknown option values replaces the unknown values with their defaults.
        """
        result = TextColorChoice.colors_from_slot_data([-1,])
        self.assertEqual(len(result), self.expected_color_count)
