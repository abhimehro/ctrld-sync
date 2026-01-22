import pytest
from unittest.mock import MagicMock
import main

def test_push_rules_filters_xss_payloads():
    """
    Verify that push_rules filters out malicious strings (XSS payloads).
    """
    mock_client = MagicMock()
    mock_post_form = MagicMock()

    # Patch the API call
    original_post_form = main._api_post_form
    main._api_post_form = mock_post_form

    # Patch the logger to verify warnings
    mock_log = MagicMock()
    original_log = main.log
    main.log = mock_log

    try:
        malicious_rules = [
            "<script>alert(1)</script>",
            "valid.com",
            "javascript:void(0)",
            "fail' OR '1'='1",
            "img src=x onerror=alert(1)",
            "safe-domain.com",
            "1.1.1.1",
            "*.wildcard.com"
        ]

        main.push_rules(
            profile_id="p1",
            folder_name="f1",
            folder_id="fid1",
            do=1,
            status=1,
            hostnames=malicious_rules,
            existing_rules=set(),
            client=mock_client
        )

        # Check what was sent
        assert mock_post_form.called
        calls = mock_post_form.call_args_list

        sent_rules = []
        for call in calls:
            args, kwargs = call
            data = kwargs['data']
            for k, v in data.items():
                if k.startswith("hostnames["):
                    sent_rules.append(v)

        # EXPECTED BEHAVIOR: Malicious rules are NOT sent
        assert "<script>alert(1)</script>" not in sent_rules
        assert "javascript:void(0)" not in sent_rules # Contains parenthesis/colon?
        # Wait, 'javascript:void(0)' has '('. My validator blocks '('.
        assert "fail' OR '1'='1" not in sent_rules # Contains '
        assert "img src=x onerror=alert(1)" not in sent_rules # Contains ( ) or =? No = is allowed?
        # "img src=x onerror=alert(1)" contains spaces?
        # My validator: isprintable() is True.
        # dangerous_chars: set("<>\"'`();{}[]")
        # <script> has < >
        # javascript:void(0) has ( )
        # fail' has '
        # img src=x ... has ( )

        # Valid rules MUST be sent
        assert "valid.com" in sent_rules
        assert "safe-domain.com" in sent_rules
        assert "1.1.1.1" in sent_rules
        assert "*.wildcard.com" in sent_rules

        # Check logs for warnings
        # We expect 4 skipped rules
        assert mock_log.warning.call_count >= 1
        found_unsafe_log = False
        for call in mock_log.warning.call_args_list:
            if "Skipping unsafe rule" in str(call):
                found_unsafe_log = True
        assert found_unsafe_log

    finally:
        main._api_post_form = original_post_form
        main.log = original_log
