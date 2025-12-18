from unittest import TestCase

from Options import Option, PerGameCommonOptions

from ..options import LegoStarWarsTCSOptions


BASE_OPTIONS = PerGameCommonOptions.type_hints
TCS_OPTIONS = {k: v for k, v in LegoStarWarsTCSOptions.type_hints.items() if k not in BASE_OPTIONS}


class TestOptions(TestCase):
    def test_options_have_display_name(self) -> None:
        """Test that all options have display_name set. display_name is used by webhost."""
        option_type: type[Option]
        for option_name, option_type in TCS_OPTIONS.items():
            with self.subTest(option_name):
                self.assertTrue(hasattr(option_type, "display_name"))

    def test_options_use_rich_text_doc(self) -> None:
        """Test that all options use rich_text_doc. This displays newlines better and allows for formatting."""
        option_type: type[Option]
        for option_name, option_type in TCS_OPTIONS.items():
            with self.subTest(option_name):
                self.assertTrue(option_type.rich_text_doc)
