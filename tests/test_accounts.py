"""Тесты BrowserAccountManager: учёт кредитов, ротация, сброс по дням."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from fox2.providers.browser import (
    COST,
    AccountExhausted,
    BrowserAccount,
    BrowserAccountManager,
)


class AccountsManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mgr = BrowserAccountManager(root=self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_creates_profile_dir(self) -> None:
        a = self.mgr.add("acc1", "flow")
        self.assertEqual(a.provider, "flow")
        self.assertTrue(Path(a.profile_dir).is_dir())
        self.assertEqual(a.daily_limit(), 50)

    def test_duplicate_name_rejected(self) -> None:
        self.mgr.add("acc1", "flow")
        with self.assertRaises(ValueError):
            self.mgr.add("acc1", "flow")

    def test_unknown_provider_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.mgr.add("acc1", "midjourney")

    def test_persists_to_disk(self) -> None:
        self.mgr.add("acc1", "flow", note="primary")
        m2 = BrowserAccountManager(root=self.root)
        loaded = m2.get("acc1")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.provider, "flow")
        self.assertEqual(loaded.note, "primary")

    def test_consume_decrements_credits(self) -> None:
        a = self.mgr.add("acc1", "flow")
        self.assertEqual(a.credits_remaining(), 50)
        self.mgr.consume(a, COST["flow:video"])
        self.assertEqual(a.credits_used_today, 10)
        self.assertEqual(a.credits_remaining(), 40)

    def test_acquire_returns_first_with_capacity(self) -> None:
        a = self.mgr.add("acc1", "flow")
        b = self.mgr.add("acc2", "flow")
        # израсходуем acc1 до лимита 50, должен переключиться на acc2
        a.credits_used_today = 50
        a.last_reset = date.today().isoformat()
        self.mgr.save()
        acquired = self.mgr.acquire("flow", COST["flow:video"])
        self.assertEqual(acquired.name, b.name)

    def test_acquire_raises_when_all_exhausted(self) -> None:
        a = self.mgr.add("acc1", "flow")
        b = self.mgr.add("acc2", "flow")
        for acc in (a, b):
            acc.credits_used_today = 50
            acc.last_reset = date.today().isoformat()
        self.mgr.save()
        with self.assertRaises(AccountExhausted):
            self.mgr.acquire("flow", 1)

    def test_acquire_raises_when_no_accounts(self) -> None:
        with self.assertRaises(AccountExhausted):
            self.mgr.acquire("flow", 1)

    def test_reset_on_new_day(self) -> None:
        a = self.mgr.add("acc1", "flow")
        a.credits_used_today = 50
        a.last_reset = (date.today() - timedelta(days=1)).isoformat()
        # acquire должен сначала сбросить счётчик (новый день) и выдать аккаунт.
        acquired = self.mgr.acquire("flow", COST["flow:video"])
        self.assertEqual(acquired.name, a.name)
        self.assertEqual(acquired.credits_used_today, 0)

    def test_unknown_provider_rejected_on_add(self) -> None:
        with self.assertRaises(ValueError):
            self.mgr.add("x", "nano_banana")
        with self.assertRaises(ValueError):
            self.mgr.add("y", "midjourney")

    def test_nano_banana_uses_flow_accounts_with_zero_cost(self) -> None:
        """Nano Banana отдельных аккаунтов не имеет — использует Flow.
        С cost=0 любой Flow-аккаунт подойдёт, даже исчерпанный."""
        a = self.mgr.add("flow1", "flow")
        a.credits_used_today = 50  # полностью исчерпан
        self.mgr.save()
        acquired = self.mgr.acquire("flow", 0)
        self.assertEqual(acquired.name, "flow1")

    def test_remove_deletes_profile(self) -> None:
        a = self.mgr.add("acc1", "flow")
        profile = Path(a.profile_dir)
        self.assertTrue(profile.exists())
        self.mgr.remove("acc1")
        self.assertIsNone(self.mgr.get("acc1"))
        self.assertFalse(profile.exists())

    def test_reset_all(self) -> None:
        a = self.mgr.add("acc1", "flow")
        b = self.mgr.add("acc2", "flow")
        a.credits_used_today = 30
        b.credits_used_today = 10
        self.mgr.reset_all()
        self.assertEqual(a.credits_used_today, 0)
        self.assertEqual(b.credits_used_today, 0)
        # И на диске тоже сброшено
        m2 = BrowserAccountManager(root=self.root)
        self.assertEqual(m2.get("acc1").credits_used_today, 0)  # type: ignore[union-attr]

    def test_acquire_skips_no_capacity_but_still_uses_within(self) -> None:
        """Если для большой задачи (10 кред видео) аккаунту не хватает, но он не исчерпан полностью —
        нужно перейти к следующему, а не падать."""
        a = self.mgr.add("acc1", "flow")
        b = self.mgr.add("acc2", "flow")
        a.credits_used_today = 45  # осталось 5, для видео (10) не хватает
        b.credits_used_today = 0
        self.mgr.save()
        acquired = self.mgr.acquire("flow", COST["flow:video"])
        self.assertEqual(acquired.name, b.name)
        # но картинку (1 кред) на acc1 всё ещё можно сделать
        acquired = self.mgr.acquire("flow", COST["flow:image"])
        self.assertEqual(acquired.name, a.name)


class BrowserAccountModelTests(unittest.TestCase):
    def test_daily_limit_known(self) -> None:
        self.assertEqual(BrowserAccount(name="x", provider="flow").daily_limit(), 50)
        self.assertEqual(BrowserAccount(name="x", provider="grok").daily_limit(), 100)

    def test_credits_remaining_for_unknown_provider(self) -> None:
        # Неизвестный провайдер = лимит 0 = «бесконечность» (для бывшего nano_banana, если вдруг останется в json).
        x = BrowserAccount(name="x", provider="old_unknown", credits_used_today=999)
        self.assertGreater(x.credits_remaining(), 1000)
        self.assertTrue(x.has_capacity_for(10**9))


if __name__ == "__main__":
    unittest.main()
