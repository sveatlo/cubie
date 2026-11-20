from unittest.mock import Mock
import unittest
from zoneinfo import ZoneInfoNotFoundError

from setup_laki_review import NAME, SCHEDULE, provision


PROMPT = "Review existing history; suggestions only."


class LakiReviewTests(unittest.TestCase):
    def test_new_job_is_paused_and_delivered_to_telegram(self):
        store = Mock()
        store.list_jobs.return_value = []
        provision(store, "Europe/Bratislava", PROMPT)
        store.list_jobs.assert_called_once_with(include_disabled=True)
        store.create_job.assert_called_once_with(
            name=NAME, prompt=PROMPT, schedule=SCHEDULE, timezone="Europe/Bratislava",
            deliver="telegram", paused=True, paused_reason="Awaiting provisioning verification",
            workdir="/opt/data/workspace",
        )

    def test_matching_paused_job_is_unchanged(self):
        store = Mock()
        job = {"id": "test", "name": NAME, "prompt": PROMPT,
               "schedule": {"kind": "cron", "expr": SCHEDULE},
               "timezone": "Europe/Bratislava", "deliver": "telegram", "state": "paused",
               "workdir": "/opt/data/workspace"}
        store.list_jobs.return_value = [job]
        self.assertEqual(provision(store, "Europe/Bratislava", PROMPT), job)
        store.create_job.assert_not_called()
        store.update_job.assert_not_called()

    def test_update_changes_managed_fields_without_resuming(self):
        store = Mock()
        store.list_jobs.return_value = [{"id": "test", "name": NAME, "state": "paused"}]
        provision(store, "Europe/Bratislava", PROMPT)
        store.update_job.assert_called_once_with("test", {
            "prompt": PROMPT, "timezone": "Europe/Bratislava", "deliver": "telegram",
            "schedule": SCHEDULE, "workdir": "/opt/data/workspace",
        })
        store.create_job.assert_not_called()

    def test_existing_job_without_workdir_gets_policy_workspace(self):
        store = Mock()
        store.list_jobs.return_value = [{
            "id": "existing", "name": NAME, "prompt": PROMPT,
            "schedule": {"kind": "cron", "expr": SCHEDULE},
            "timezone": "Europe/Bratislava", "deliver": "telegram", "state": "paused",
        }]
        provision(store, "Europe/Bratislava", PROMPT)
        store.update_job.assert_called_once_with("existing", {"workdir": "/opt/data/workspace"})
        store.create_job.assert_not_called()

    def test_duplicates_and_invalid_timezones_fail_before_mutation(self):
        store = Mock()
        store.list_jobs.return_value = [{"name": NAME}, {"name": NAME}]
        with self.assertRaises(RuntimeError):
            provision(store, "Europe/Bratislava", PROMPT)
        with self.assertRaises(ZoneInfoNotFoundError):
            provision(store, "Not/AZone", PROMPT)
        store.update_job.assert_not_called()
        store.create_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
