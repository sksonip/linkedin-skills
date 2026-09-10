from __future__ import annotations

import os
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from lib import ApprovalError, issue_approval, publish
from lib import _env
from lib.backend_selector import active_backend


class ApprovalBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean_env = patch.dict(
            os.environ,
            {
                "PUBLORA_API_KEY": "",
                "LINKEDIN_PLATFORM_ID": "",
                "LINKEDIN_SKILLS_CUSTOM_POSTER": "",
                "LINKEDIN_SKILLS_ENABLE_CUSTOM_POSTER": "",
            },
            clear=False,
        )
        self.clean_env.start()

    def tearDown(self) -> None:
        self.clean_env.stop()

    def test_publish_rejects_missing_approval(self) -> None:
        with self.assertRaises(ApprovalError):
            publish("post", "draft", "https://www.linkedin.com/post/new/")

    def test_receipt_is_exact_action_bound_and_one_use(self) -> None:
        context = {"platforms": ["linkedin-test"], "scheduled_time": None}
        receipt = issue_approval(
            kind="post",
            draft_text="approved draft",
            target_url="https://www.linkedin.com/post/new/",
            user_confirmation="yes",
            action_context=context,
        )
        result = publish(
            "post",
            "approved draft",
            "https://www.linkedin.com/post/new/",
            approval=receipt,
            **context,
        )
        self.assertEqual(result["mode"], "manual")
        with self.assertRaises(ApprovalError):
            publish(
                "post",
                "approved draft",
                "https://www.linkedin.com/post/new/",
                approval=receipt,
                **context,
            )

    def test_changed_content_invalidates_receipt(self) -> None:
        receipt = issue_approval(
            kind="comment",
            draft_text="approved",
            target_url="https://www.linkedin.com/posts/example",
            user_confirmation="post",
            action_context={"post_urn": "urn:li:activity:123"},
        )
        with self.assertRaises(ApprovalError):
            publish(
                "comment",
                "changed",
                "https://www.linkedin.com/posts/example",
                approval=receipt,
                post_urn="urn:li:activity:123",
            )

    def test_non_confirmation_is_rejected(self) -> None:
        with self.assertRaises(ApprovalError):
            issue_approval(
                kind="post",
                draft_text="draft",
                target_url="https://www.linkedin.com/post/new/",
                user_confirmation="looks good but do not post",
            )

    def test_direct_publora_write_is_rejected(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.headers = {}

        fake_requests = types.SimpleNamespace(
            Session=FakeSession,
            ConnectionError=ConnectionError,
            Timeout=TimeoutError,
        )
        with patch.dict(sys.modules, {"requests": fake_requests}):
            module = importlib.import_module("lib.publora_client")
            client = module.PubloraClient(api_key="test-key")
            with self.assertRaises(module.PubloraError):
                client.create_comment(
                    post_urn="urn:li:activity:123",
                    message="draft",
                    platform_id="linkedin-test",
                )


class ConfigurationBoundaryTests(unittest.TestCase):
    def test_custom_backend_requires_explicit_enable_flag(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PUBLORA_API_KEY": "",
                "LINKEDIN_PLATFORM_ID": "",
                "LINKEDIN_SKILLS_CUSTOM_POSTER": "python poster.py",
                "LINKEDIN_SKILLS_ENABLE_CUSTOM_POSTER": "",
            },
            clear=False,
        ):
            self.assertEqual(active_backend(), "manual")
            os.environ["LINKEDIN_SKILLS_ENABLE_CUSTOM_POSTER"] = "true"
            self.assertEqual(active_backend(), "diy")

    def test_load_env_does_not_search_caller_parents(self) -> None:
        calls = []
        fake_dotenv = types.SimpleNamespace(
            load_dotenv=lambda path, override=False: calls.append((Path(path), override))
        )
        old_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "project" / "nested"
            nested.mkdir(parents=True)
            (root / ".env").write_text(
                "LINKEDIN_SKILLS_CUSTOM_POSTER=python malware.py\n",
                encoding="utf-8",
            )
            try:
                os.chdir(nested)
                with patch.dict(sys.modules, {"dotenv": fake_dotenv}):
                    _env.load_env(force=True)
            finally:
                os.chdir(old_cwd)
        self.assertEqual(calls, [])

    def test_explicit_env_path_is_honored(self) -> None:
        calls = []
        fake_dotenv = types.SimpleNamespace(
            load_dotenv=lambda path, override=False: calls.append((Path(path), override))
        )
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "trusted.env"
            env_path.write_text("EXAMPLE=1\n", encoding="utf-8")
            with patch.dict(sys.modules, {"dotenv": fake_dotenv}):
                _env.load_env(force=True, env_path=env_path)
        self.assertEqual(calls, [(env_path, False)])


if __name__ == "__main__":
    unittest.main()
