"""The live verifier must distinguish the cited offer from the unrelated add-on."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_megafon_source import verify_page


class VerifySource(unittest.TestCase):
    def test_accepts_cited_topic_and_rejects_material_change(self):
        page = ("При вступлении в группу Моя Семья абоненту ежемесячно даётся пакет 1 ГБ. "
                "После исчерпания пакета скорость снижается до 64 кб/с. "
                "Услуга не доступна на планшетах, модемах и роутерах.")
        verify_page(page)
        for diff in (page.replace("64", "128"), page.replace("Моя Семья", "Базовый интернет")):
            with self.assertRaises(ValueError):
                verify_page(diff)
