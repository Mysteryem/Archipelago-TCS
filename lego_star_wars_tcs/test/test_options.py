from unittest import TestCase

from ..options import LegoStarWarsTCSOptions


class TestOptions(TestCase):
    def test_options_have_display_name(self):
        """Test that all options have display_name set. display_name is used by webhost."""
        for option_name, option_type in LegoStarWarsTCSOptions.type_hints.items():
            with self.subTest(option_name):
                self.assertTrue(hasattr(option_type, "display_name"))
