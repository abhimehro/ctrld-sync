import unittest
from unittest.mock import MagicMock
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

class TestFolderValidation(unittest.TestCase):
    def setUp(self):
        self.mock_log = MagicMock()
        self.original_log = main.log
        main.log = self.mock_log

    def tearDown(self):
        main.log = self.original_log

    def test_valid_folder_name(self):
        data = {"group": {"group": "Safe Folder"}}
        self.assertTrue(main.validate_folder_data(data, "test_url"))

    def test_xss_folder_name(self):
        # Should be rejected
        data = {"group": {"group": "<script>alert(1)</script>"}}
        self.assertFalse(main.validate_folder_data(data, "test_url"))
        # Check that error was logged
        self.assertTrue(self.mock_log.error.called)
        # We expect a specific error message about unsafe characters or invalid name
        args = str(self.mock_log.error.call_args_list)
        # Assuming we will log "Invalid folder name" or similar
        self.assertTrue("Invalid folder name" in args or "Unsafe characters" in args)

    def test_non_string_folder_name(self):
        data = {"group": {"group": 123}}
        self.assertFalse(main.validate_folder_data(data, "test_url"))
        self.assertTrue(self.mock_log.error.called)
        args = str(self.mock_log.error.call_args_list)
        self.assertTrue("must be a string" in args)

    def test_empty_folder_name(self):
        data = {"group": {"group": "   "}}
        self.assertFalse(main.validate_folder_data(data, "test_url"))
        self.assertTrue(self.mock_log.error.called)
