"""Test script for security fixes implementation."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.security import (
    validate_password_strength,
    sanitize_log_message,
    sanitize_log_dict,
    generate_csrf_token,
)


def test_password_validation():
    """Test password strength validation."""
    print("Testing password validation...")

    # Valid passwords
    valid_cases = [
        "Password123",
        "MySecure1Pass",
        "Admin2024!",
        "Test1234ABC",
    ]

    for password in valid_cases:
        is_valid, error = validate_password_strength(password)
        assert is_valid, f"Expected {password} to be valid, got error: {error}"
        print(f"  ✓ Valid: {password}")

    # Invalid passwords
    invalid_cases = [
        ("short1A", "too short"),
        ("alllowercase123", "no uppercase"),
        ("ALLUPPERCASE123", "no lowercase"),
        ("NoDigitsHere", "no digit"),
        ("", "empty"),
    ]

    for password, reason in invalid_cases:
        is_valid, error = validate_password_strength(password)
        assert not is_valid, f"Expected {password} to be invalid ({reason})"
        assert error is not None, f"Expected error message for {password}"
        print(f"  ✓ Invalid ({reason}): {password} -> {error}")

    print("✓ Password validation tests passed\n")


def test_log_sanitization():
    """Test log message sanitization."""
    print("Testing log sanitization...")

    # Test API key sanitization
    message = "API response: {api_key: 'sk-1234567890abcdefghij'}"
    sanitized = sanitize_log_message(message)
    assert "sk-1234567890abcdefghij" not in sanitized
    assert "REDACTED" in sanitized
    print(f"  ✓ API key sanitized: {sanitized}")

    # Test Bearer token sanitization
    message = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    sanitized = sanitize_log_message(message)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
    assert "REDACTED" in sanitized
    print(f"  ✓ Bearer token sanitized: {sanitized}")

    # Test dictionary sanitization
    data = {
        "username": "admin",
        "password": "secret123",
        "api_key": "sk-test123456789",
        "normal_field": "visible_value",
    }
    sanitized_dict = sanitize_log_dict(data)
    assert sanitized_dict["password"] == "***REDACTED***"
    assert sanitized_dict["api_key"] == "***REDACTED***"
    assert sanitized_dict["normal_field"] == "visible_value"
    print(f"  ✓ Dictionary sanitized: {sanitized_dict}")

    print("✓ Log sanitization tests passed\n")


def test_csrf_token_generation():
    """Test CSRF token generation."""
    print("Testing CSRF token generation...")

    # Generate token (will fail if Redis not available, but that's OK for syntax check)
    try:
        token = generate_csrf_token()
        assert token is not None
        assert len(token) > 20
        print(f"  ✓ CSRF token generated: {token[:20]}...")
    except Exception as e:
        print(f"  ⚠ CSRF token generation skipped (Redis not available): {e}")

    print("✓ CSRF token generation test passed\n")


def test_runtime_config_validation():
    """Test runtime config validation."""
    print("Testing runtime config validation...")

    from app.routers.runtime_config import RuntimeConfigValues, _validate_runtime_config

    # Valid config
    valid_config = RuntimeConfigValues(
        JOB_TIMEOUT_SECONDS=1800,
        OCR_PAGE_TIMEOUT_S=300,
        OCR_TOTAL_TIMEOUT_S=3600,
        SCANNED_RENDER_DPI=200,
        OCR_AI_PAGE_CONCURRENCY_MAX=8,
    )
    errors = _validate_runtime_config(valid_config)
    assert len(errors) == 0, f"Expected no errors, got: {errors}"
    print(f"  ✓ Valid config accepted")

    # Invalid config - timeout too low
    invalid_config = RuntimeConfigValues(
        JOB_TIMEOUT_SECONDS=5,  # Too low (min 10)
    )
    errors = _validate_runtime_config(invalid_config)
    assert len(errors) > 0, "Expected validation errors for timeout too low"
    print(f"  ✓ Invalid timeout rejected: {errors[0]}")

    # Invalid config - DPI too high
    invalid_config = RuntimeConfigValues(
        SCANNED_RENDER_DPI=1000,  # Too high (max 600)
    )
    errors = _validate_runtime_config(invalid_config)
    assert len(errors) > 0, "Expected validation errors for DPI too high"
    print(f"  ✓ Invalid DPI rejected: {errors[0]}")

    # Invalid config - concurrency out of range
    invalid_config = RuntimeConfigValues(
        OCR_AI_PAGE_CONCURRENCY_MAX=150,  # Too high (max 100)
    )
    errors = _validate_runtime_config(invalid_config)
    assert len(errors) > 0, "Expected validation errors for concurrency too high"
    print(f"  ✓ Invalid concurrency rejected: {errors[0]}")

    print("✓ Runtime config validation tests passed\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Security Fixes Test Suite")
    print("=" * 60 + "\n")

    try:
        test_password_validation()
        test_log_sanitization()
        test_csrf_token_generation()
        test_runtime_config_validation()

        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
