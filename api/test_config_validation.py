"""Standalone test for runtime config validation (no FastAPI dependencies)."""

import sys


def validate_runtime_config_standalone():
    """Standalone version of runtime config validation for testing."""

    class MockConfig:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    def _validate_runtime_config(config):
        """Validate runtime configuration values."""
        errors = []

        # Timeout validations (10s - 3600s)
        timeout_fields = [
            ("JOB_TIMEOUT_SECONDS", 10, 3600),
            ("OCR_PAGE_TIMEOUT_S", 10, 3600),
            ("OCR_TOTAL_TIMEOUT_S", 10, 7200),
            ("OCR_IMAGE_REGION_TIMEOUT_S", 5, 300),
        ]
        for field, min_val, max_val in timeout_fields:
            value = getattr(config, field, None)
            if value is not None and not (min_val <= value <= max_val):
                errors.append(f"{field} must be between {min_val} and {max_val} seconds")

        # Float timeout validations
        float_timeout_fields = [
            ("OCR_PADDLE_VL_PREDICT_TIMEOUT_S", 10.0, 600.0),
            ("OCR_AI_RETRY_BACKOFF_BASE_S", 0.1, 60.0),
            ("OCR_AI_RATE_LIMITED_MIN_DELAY_S", 0.1, 30.0),
        ]
        for field, min_val, max_val in float_timeout_fields:
            value = getattr(config, field, None)
            if value is not None and not (min_val <= value <= max_val):
                errors.append(f"{field} must be between {min_val} and {max_val} seconds")

        # DPI validations (50 - 600)
        if hasattr(config, "SCANNED_RENDER_DPI") and config.SCANNED_RENDER_DPI is not None:
            if not (50 <= config.SCANNED_RENDER_DPI <= 600):
                errors.append("SCANNED_RENDER_DPI must be between 50 and 600")

        # Concurrency validations (1 - 100)
        concurrency_fields = [
            "OCR_AI_PAGE_CONCURRENCY_MAX",
            "OCR_AI_BLOCK_CONCURRENCY_MAX",
            "OCR_AI_PAGE_CONCURRENCY_DEFAULT",
            "OCR_AI_BLOCK_CONCURRENCY_DEFAULT",
        ]
        for field in concurrency_fields:
            value = getattr(config, field, None)
            if value is not None and not (1 <= value <= 100):
                errors.append(f"{field} must be between 1 and 100")

        return errors

    print("Testing runtime config validation (standalone)...")

    # Valid config
    valid_config = MockConfig(
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
    invalid_config = MockConfig(JOB_TIMEOUT_SECONDS=5)
    errors = _validate_runtime_config(invalid_config)
    assert len(errors) > 0, "Expected validation errors for timeout too low"
    print(f"  ✓ Invalid timeout rejected: {errors[0]}")

    # Invalid config - DPI too high
    invalid_config = MockConfig(SCANNED_RENDER_DPI=1000)
    errors = _validate_runtime_config(invalid_config)
    assert len(errors) > 0, "Expected validation errors for DPI too high"
    print(f"  ✓ Invalid DPI rejected: {errors[0]}")

    # Invalid config - concurrency out of range
    invalid_config = MockConfig(OCR_AI_PAGE_CONCURRENCY_MAX=150)
    errors = _validate_runtime_config(invalid_config)
    assert len(errors) > 0, "Expected validation errors for concurrency too high"
    print(f"  ✓ Invalid concurrency rejected: {errors[0]}")

    print("✓ Runtime config validation tests passed\n")


if __name__ == "__main__":
    try:
        validate_runtime_config_standalone()
        print("✓ All standalone tests passed!")
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
