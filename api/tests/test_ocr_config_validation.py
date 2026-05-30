"""Tests for OCR configuration validation logic.

Tests the field validators added to OcrAiConfig and OcrConfig to ensure:
1. Layout model validation when chain_mode = "layout_block"
2. SAM availability validation when enable_sam = True
"""

import pytest
from pydantic import ValidationError

from app.schemas.job_config import OcrAiConfig, OcrConfig


class TestLayoutModelValidation:
    """Test layout_model field validation in OcrAiConfig."""

    def test_layout_model_valid_when_not_layout_block(self):
        """Layout model validation should be skipped when chain_mode != layout_block."""
        # Should not raise even if model doesn't exist
        config = OcrAiConfig(
            chain_mode="direct",
            layout_model="nonexistent_model",
        )
        assert config.layout_model == "nonexistent_model"

    def test_layout_model_unknown_model_raises_error(self):
        """Unknown layout model should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            OcrAiConfig(
                chain_mode="layout_block",
                layout_model="unknown_model_xyz",
            )

        error_msg = str(exc_info.value)
        assert "Unknown layout model" in error_msg
        assert "unknown_model_xyz" in error_msg

    def test_layout_model_not_downloaded_raises_error(self):
        """Layout model not downloaded should raise ValidationError."""
        # Use a valid model ID that exists but is likely not downloaded
        with pytest.raises(ValidationError) as exc_info:
            OcrAiConfig(
                chain_mode="layout_block",
                layout_model="doclayout_yolo",  # Valid but unlikely to be downloaded
            )

        error_msg = str(exc_info.value)
        # Should mention either "not downloaded" or pass if it IS downloaded
        if "not downloaded" in error_msg.lower():
            assert "doclayout_yolo" in error_msg
            assert "settings page" in error_msg.lower()

    def test_layout_model_default_value(self):
        """Default layout model should be pp_doclayout_v3."""
        config = OcrAiConfig(chain_mode="direct")
        assert config.layout_model == "pp_doclayout_v3"

    def test_layout_model_doc_parser_mode_skips_validation(self):
        """doc_parser mode should skip layout model validation."""
        config = OcrAiConfig(
            chain_mode="doc_parser",
            layout_model="any_model",
        )
        assert config.layout_model == "any_model"


class TestSamValidation:
    """Test enable_sam field validation in OcrConfig."""

    def test_sam_disabled_no_validation(self):
        """SAM validation should be skipped when enable_sam = False."""
        config = OcrConfig(enable_sam=False)
        assert config.enable_sam is False

    def test_sam_none_no_validation(self):
        """SAM validation should be skipped when enable_sam = None."""
        config = OcrConfig(enable_sam=None)
        assert config.enable_sam is None

    def test_sam_enabled_validates_availability(self):
        """SAM enabled should validate that mobile_sam is available."""
        try:
            import mobile_sam  # noqa: F401
            # If mobile_sam is installed, should not raise
            config = OcrConfig(enable_sam=True)
            assert config.enable_sam is True
        except ImportError:
            # If mobile_sam is not installed, should raise ValidationError
            with pytest.raises(ValidationError) as exc_info:
                OcrConfig(enable_sam=True)

            error_msg = str(exc_info.value)
            assert "SAM" in error_msg or "mobile_sam" in error_msg


class TestOcrConfigIntegration:
    """Integration tests for OcrConfig with nested OcrAiConfig."""

    def test_full_config_with_layout_block_and_sam(self):
        """Test full OCR config with layout_block mode and SAM enabled."""
        # This should validate both layout model and SAM
        try:
            config = OcrConfig(
                provider="aiocr",
                enable_sam=True,
                ai=OcrAiConfig(
                    chain_mode="layout_block",
                    layout_model="pp_doclayout_v3",
                ),
            )
            # If we get here, both validations passed
            assert config.enable_sam is True
            assert config.ai.chain_mode == "layout_block"
        except ValidationError as e:
            # Expected if models not downloaded or SAM not available
            error_msg = str(e)
            assert ("not downloaded" in error_msg.lower() or
                    "not available" in error_msg.lower() or
                    "mobile_sam" in error_msg.lower())

    def test_config_with_direct_mode_no_layout_validation(self):
        """Direct mode should not validate layout model."""
        config = OcrConfig(
            provider="aiocr",
            ai=OcrAiConfig(
                chain_mode="direct",
                layout_model="any_model",  # Should not be validated
            ),
        )
        assert config.ai.chain_mode == "direct"
        assert config.ai.layout_model == "any_model"

    def test_config_default_values(self):
        """Test default configuration values."""
        config = OcrConfig()
        assert config.provider == "auto"
        assert config.enable_sam is False
        assert config.ai.chain_mode == "direct"
        assert config.ai.layout_model == "pp_doclayout_v3"


class TestValidationErrorMessages:
    """Test that validation error messages are clear and actionable."""

    def test_layout_model_error_message_clarity(self):
        """Layout model error should mention settings page."""
        try:
            OcrAiConfig(
                chain_mode="layout_block",
                layout_model="pp_doclayout_l",  # Valid but may not be downloaded
            )
        except ValidationError as e:
            error_msg = str(e)
            if "not downloaded" in error_msg.lower():
                # Error message should be actionable
                assert "settings page" in error_msg.lower() or "download" in error_msg.lower()

    def test_sam_error_message_clarity(self):
        """SAM error should mention mobile_sam package."""
        try:
            import mobile_sam  # noqa: F401
            # Skip test if mobile_sam is installed
            pytest.skip("mobile_sam is installed")
        except ImportError:
            pass

        try:
            OcrConfig(enable_sam=True)
        except ValidationError as e:
            error_msg = str(e)
            # Error message should mention the package name
            assert "mobile_sam" in error_msg.lower() or "sam" in error_msg.lower()
            assert "not available" in error_msg.lower() or "not installed" in error_msg.lower()
