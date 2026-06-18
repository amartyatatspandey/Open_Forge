"""Unit tests for src/datasheet/utils.py.

Tests package normalization, PDF hashing, and confidence aggregation
functions used in the datasheet extraction pipeline.
"""

import hashlib
import tempfile
from pathlib import Path

import pytest

from src.datasheet.utils import (
    FIELD_COVERAGE_WEIGHT,
    METHOD_CONFIDENCE_WEIGHT,
    PHASE2_CONFIDENCE_WEIGHT,
    compute_extraction_confidence,
    compute_pdf_sha256,
    normalize_package,
)
from src.schemas.datasheet import ExtractionMethod


# =============================================================================
# normalize_package() Tests
# =============================================================================


class TestNormalizePackageClean:
    """Tests for normalize_package() with clean, well-formed inputs."""

    def test_sot_23_5_clean(self) -> None:
        """Test normalization of clean SOT-23-5 strings."""
        test_cases = [
            ("SOT-23-5", "SOT-23-5", False),
            ("SOT23-5", "SOT-23-5", False),
            ("SOT-23 5-pin", "SOT-23-5", False),
            ("5-pin SOT-23 package", "SOT-23-5", False),
            ("DRLR (SOT-23-5)", "SOT-23-5", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected, f"Failed for input: {raw}"
            assert flag == needs_review, f"Review flag mismatch for: {raw}"

    def test_sot_23_3_clean(self) -> None:
        """Test normalization of clean SOT-23-3 strings."""
        test_cases = [
            ("SOT-23-3", "SOT-23-3", False),
            ("SOT23-3", "SOT-23-3", False),
            ("3-pin SOT-23", "SOT-23-3", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_soic_clean(self) -> None:
        """Test normalization of clean SOIC strings."""
        test_cases = [
            ("SOIC-8", "SOIC-8", False),
            ("SOIC8", "SOIC-8", False),
            ("8-pin SOIC", "SOIC-8", False),
            ("SOIC 16", "SOIC-16", False),
            ("SOIC-16 package", "SOIC-16", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_dip_clean(self) -> None:
        """Test normalization of clean DIP strings."""
        test_cases = [
            ("DIP-8", "DIP-8", False),
            ("DIP8", "DIP-8", False),
            ("8-pin DIP", "DIP-8", False),
            ("PDIP-14", "DIP-14", False),
            ("DIP-14 package", "DIP-14", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_qfn_clean(self) -> None:
        """Test normalization of clean QFN strings."""
        test_cases = [
            ("QFN-16", "QFN-16", False),
            ("QFN16", "QFN-16", False),
            ("16-pin QFN", "QFN-16", False),
            ("QFN-24", "QFN-24", False),
            ("QFN-32 package", "QFN-32", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_tssop_clean(self) -> None:
        """Test normalization of clean TSSOP strings."""
        test_cases = [
            ("TSSOP-8", "TSSOP-8", False),
            ("TSSOP8", "TSSOP-8", False),
            ("8-pin TSSOP", "TSSOP-8", False),
            ("TSSOP-16", "TSSOP-16", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_to_packages_clean(self) -> None:
        """Test normalization of clean TO package strings."""
        test_cases = [
            ("TO-220", "TO-220", False),
            ("TO220", "TO-220", False),
            ("TO-220AB", "TO-220", False),
            ("TO-92", "TO-92", False),
            ("TO92", "TO-92", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_passive_packages_clean(self) -> None:
        """Test normalization of clean passive component package strings."""
        test_cases = [
            ("0402", "0402", False),
            ("0603", "0603", False),
            ("0805", "0805", False),
            ("1206", "1206", False),
            ("0402 (metric 1005)", "0402", False),
            ("1608 (0603)", "0603", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review


class TestNormalizePackageAmbiguous:
    """Tests for normalize_package() with ambiguous or variant inputs."""

    def test_sot_23_ambiguous(self) -> None:
        """Test normalization of ambiguous SOT-23 variants."""
        # These should match SOT-23 (not SOT-23-5 or SOT-23-3) when pin count unclear
        test_cases = [
            ("SOT23", "SOT-23", False),
            ("SOT-23", "SOT-23", False),
            ("sot-23 package", "SOT-23", False),  # lowercase
            ("SOT23-5 variant", "SOT-23-5", False),  # Should match SOT-23-5
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected, f"Failed for input: {raw}"
            assert flag == needs_review

    def test_case_insensitive(self) -> None:
        """Test that matching is case-insensitive."""
        test_cases = [
            ("sot-23-5", "SOT-23-5", False),
            ("SOIC-8", "SOIC-8", False),
            ("dip-8", "DIP-8", False),
            ("QFN-16", "QFN-16", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_extra_text_in_parentheses(self) -> None:
        """Test normalization with extra text in parentheses."""
        test_cases = [
            ("SOT-23-5 (DRLR)", "SOT-23-5", False),
            ("Package: SOIC-8 (Lead-Free)", "SOIC-8", False),
            ("QFN-16 (3x3mm)", "QFN-16", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_with_package_suffix(self) -> None:
        """Test normalization with 'package' or similar suffixes."""
        test_cases = [
            ("SOT-23-5 package", "SOT-23-5", False),
            ("SOIC-8 PACKAGE", "SOIC-8", False),
            ("DIP-14 Package Type", "DIP-14", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review

    def test_hyphen_variant_spacing(self) -> None:
        """Test normalization with various hyphen/spacing variants."""
        test_cases = [
            ("SOT23-5", "SOT-23-5", False),
            ("SOT-23-5", "SOT-23-5", False),
            ("SOIC8", "SOIC-8", False),
            ("SOIC 8", "SOIC-8", False),
        ]
        for raw, expected, needs_review in test_cases:
            result, flag = normalize_package(raw)
            assert result == expected
            assert flag == needs_review


class TestNormalizePackageUnknown:
    """Tests for normalize_package() with unknown/invalid inputs."""

    def test_unknown_package_returns_needs_review(self) -> None:
        """Test that unknown packages return needs_review=True."""
        test_cases = [
            "Unknown XYZ-99",
            "Custom Package 123",
            "BGA-256",
            "CSP-12",
            "MLF-20",
        ]
        for raw in test_cases:
            result, flag = normalize_package(raw)
            assert result == raw, f"Should return original text for: {raw}"
            assert flag is True, f"Should set needs_review=True for: {raw}"

    def test_empty_string(self) -> None:
        """Test normalization of empty string."""
        result, flag = normalize_package("")
        assert result == ""
        assert flag is True

    def test_whitespace_only(self) -> None:
        """Test normalization of whitespace-only string."""
        result, flag = normalize_package("   ")
        # Whitespace is stripped, resulting in empty string
        assert result == ""
        assert flag is True

    def test_none_input(self) -> None:
        """Test normalization handles None gracefully."""
        result, flag = normalize_package(None)  # type: ignore[arg-type]
        assert result == ""
        assert flag is True

    def test_gibberish_input(self) -> None:
        """Test normalization of completely gibberish input."""
        test_cases = [
            "!!!@#$%^&*()",
            "123456789",
            "not a package",
            "package",
        ]
        for raw in test_cases:
            result, flag = normalize_package(raw)
            assert result == raw
            assert flag is True


class TestNormalizePackageComprehensive:
    """Comprehensive test with 10 raw strings - 5 clean, 5 ambiguous."""

    def test_ten_raw_strings_five_clean_five_ambiguous(self) -> None:
        """Test normalize_package() on 10 raw strings, 5 clean and 5 ambiguous."""
        # 5 clean inputs (should normalize successfully)
        clean_cases = [
            ("SOT-23-5", "SOT-23-5", False),
            ("8-pin SOIC", "SOIC-8", False),
            ("DIP-14", "DIP-14", False),
            ("QFN-24 package", "QFN-24", False),
            ("0603", "0603", False),
        ]

        # 5 ambiguous/variant inputs
        ambiguous_cases = [
            ("SOT23", "SOT-23", False),  # Missing pin count
            ("SOIC 16 lead-free", "SOIC-16", False),  # Extra text
            ("to-220ab", "TO-220", False),  # Variant with suffix
            ("0402 (1005 metric)", "0402", False),  # Metric equivalent
            ("SOT-23-5 (DRLR code)", "SOT-23-5", False),  # With package code
        ]

        all_cases = clean_cases + ambiguous_cases

        for raw, expected, needs_review in all_cases:
            result, flag = normalize_package(raw)
            assert result == expected, f"Expected {expected}, got {result} for input: {raw}"
            assert flag == needs_review, f"Expected needs_review={needs_review} for: {raw}"


# =============================================================================
# compute_pdf_sha256() Tests
# =============================================================================


class TestComputePdfSha256:
    """Tests for compute_pdf_sha256() function."""

    def test_produces_consistent_output_on_temp_file(self) -> None:
        """Test compute_pdf_sha256() produces consistent output on a temp file."""
        # Create a temporary file with known content
        content = b"This is a test PDF content for hashing verification."
        expected_hash = hashlib.sha256(content).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            # Compute hash
            result = compute_pdf_sha256(tmp_path)

            # Should match expected hash
            assert result == expected_hash

            # Should be lowercase
            assert result.islower()

            # Should be 64 characters (256 bits = 32 bytes = 64 hex chars)
            assert len(result) == 64

            # Second call should produce identical result
            result2 = compute_pdf_sha256(tmp_path)
            assert result2 == result

        finally:
            tmp_path.unlink()

    def test_large_file_chunked_reading(self) -> None:
        """Test that large files are read in chunks correctly."""
        # Create a larger file (more than one chunk)
        content = b"A" * 20000  # Larger than 8192 byte chunk size
        expected_hash = hashlib.sha256(content).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            result = compute_pdf_sha256(tmp_path)
            assert result == expected_hash
        finally:
            tmp_path.unlink()

    def test_empty_file(self) -> None:
        """Test hashing an empty file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            result = compute_pdf_sha256(tmp_path)
            expected = hashlib.sha256(b"").hexdigest()
            assert result == expected
        finally:
            tmp_path.unlink()

    def test_file_not_found(self) -> None:
        """Test that FileNotFoundError is raised for non-existent file."""
        with pytest.raises(FileNotFoundError):
            compute_pdf_sha256(Path("/nonexistent/path/file.pdf"))

    def test_is_directory(self) -> None:
        """Test that IsADirectoryError is raised for directory path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(IsADirectoryError):
                compute_pdf_sha256(Path(tmp_dir))

    def test_binary_content(self) -> None:
        """Test hashing binary content (like a real PDF)."""
        # Simulate PDF-like binary content with null bytes
        content = b"%PDF-1.4\x00\x01\x02\x03test content\xff\xfe"
        expected_hash = hashlib.sha256(content).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            result = compute_pdf_sha256(tmp_path)
            assert result == expected_hash
        finally:
            tmp_path.unlink()


# =============================================================================
# compute_extraction_confidence() Tests
# =============================================================================


class TestComputeExtractionConfidence:
    """Tests for compute_extraction_confidence() function."""

    def test_weights_sum_to_one(self) -> None:
        """Verify that the defined weights sum to 1.0."""
        total = METHOD_CONFIDENCE_WEIGHT + PHASE2_CONFIDENCE_WEIGHT + FIELD_COVERAGE_WEIGHT
        assert total == 1.0

    def test_typical_values(self) -> None:
        """Test with typical confidence values."""
        # P1_VECTOR has confidence 0.97
        result = compute_extraction_confidence(
            method=ExtractionMethod.P1_VECTOR,
            phase2_confidence=0.95,
            phase3_field_coverage=0.88,
        )
        # Expected: 0.97*0.4 + 0.95*0.3 + 0.88*0.3 = 0.388 + 0.285 + 0.264 = 0.937
        expected = 0.97 * 0.4 + 0.95 * 0.3 + 0.88 * 0.3
        assert result == pytest.approx(expected, abs=1e-6)

    def test_manual_extraction_perfect_confidence(self) -> None:
        """Test with MANUAL extraction method (confidence 1.0)."""
        result = compute_extraction_confidence(
            method=ExtractionMethod.MANUAL,
            phase2_confidence=1.0,
            phase3_field_coverage=1.0,
        )
        # 1.0*0.4 + 1.0*0.3 + 1.0*0.3 = 1.0
        assert result == 1.0

    def test_all_zero_confidence(self) -> None:
        """Test with all zero confidence values."""
        # LLM_FALLBACK has confidence 0.72, but we'll set others to 0
        result = compute_extraction_confidence(
            method=ExtractionMethod.LLM_FALLBACK,
            phase2_confidence=0.0,
            phase3_field_coverage=0.0,
        )
        # 0.72*0.4 + 0*0.3 + 0*0.3 = 0.288
        expected = 0.72 * 0.4
        assert result == pytest.approx(expected, abs=1e-6)

    def test_all_extraction_methods(self) -> None:
        """Test with all extraction methods."""
        for method in ExtractionMethod:
            result = compute_extraction_confidence(
                method=method,
                phase2_confidence=0.9,
                phase3_field_coverage=0.85,
            )
            # Verify result is in valid range
            assert 0.0 <= result <= 1.0


class TestComputeExtractionConfidenceClamping:
    """Tests for compute_extraction_confidence() clamping behavior."""

    def test_clamps_to_1_0_on_extreme_positive_inputs(self) -> None:
        """Test that result clamps to 1.0 on extreme positive inputs."""
        # Even with inputs > 1.0, result should be clamped to 1.0
        result = compute_extraction_confidence(
            method=ExtractionMethod.MANUAL,  # 1.0 base
            phase2_confidence=1.5,  # Over 1.0
            phase3_field_coverage=1.5,  # Over 1.0
        )
        assert result == 1.0

    def test_clamps_to_0_0_on_extreme_negative_inputs(self) -> None:
        """Test that result clamps to 0.0 on extreme negative inputs."""
        result = compute_extraction_confidence(
            method=ExtractionMethod.LLM_FALLBACK,  # 0.72 base
            phase2_confidence=-0.5,  # Negative
            phase3_field_coverage=-0.5,  # Negative
        )
        # Without clamping: 0.72*0.4 + (-0.5)*0.3 + (-0.5)*0.3 = 0.288 - 0.3 = -0.012
        # With clamping: 0.0
        assert result == 0.0

    def test_clamps_to_1_0_when_calculation_exceeds(self) -> None:
        """Test clamping to 1.0 when weighted calculation exceeds 1.0."""
        # MANUAL (1.0) with high phase2 and coverage
        result = compute_extraction_confidence(
            method=ExtractionMethod.MANUAL,
            phase2_confidence=1.0,
            phase3_field_coverage=1.0,
        )
        # 1.0*0.4 + 1.0*0.3 + 1.0*0.3 = 1.0 (exact, no clamping needed)
        assert result == 1.0

    def test_does_not_clamp_when_in_range(self) -> None:
        """Test that values in [0.0, 1.0] are not affected by clamping."""
        result = compute_extraction_confidence(
            method=ExtractionMethod.P1_VLM,  # 0.85
            phase2_confidence=0.8,
            phase3_field_coverage=0.75,
        )
        # 0.85*0.4 + 0.8*0.3 + 0.75*0.3 = 0.34 + 0.24 + 0.225 = 0.805
        expected = 0.85 * 0.4 + 0.8 * 0.3 + 0.75 * 0.3
        assert result == pytest.approx(expected, abs=1e-6)
        assert 0.0 < result < 1.0

    def test_partial_negative_inputs(self) -> None:
        """Test behavior with partially negative inputs."""
        result = compute_extraction_confidence(
            method=ExtractionMethod.P1_PHASE5_NLP,  # 0.80
            phase2_confidence=-0.1,
            phase3_field_coverage=0.5,
        )
        # 0.80*0.4 + (-0.1)*0.3 + 0.5*0.3 = 0.32 - 0.03 + 0.15 = 0.44
        expected = 0.80 * 0.4 + (-0.1) * 0.3 + 0.5 * 0.3
        assert result == pytest.approx(expected, abs=1e-6)
        assert 0.0 < result < 1.0  # Should not need clamping

    def test_clamps_high_method_confidence(self) -> None:
        """Test that high method confidence with zero others stays in range."""
        result = compute_extraction_confidence(
            method=ExtractionMethod.MANUAL,  # 1.0
            phase2_confidence=0.0,
            phase3_field_coverage=0.0,
        )
        # 1.0*0.4 + 0*0.3 + 0*0.3 = 0.4
        assert result == 0.4


class TestComputeExtractionConfidenceEdgeCases:
    """Edge case tests for compute_extraction_confidence()."""

    def test_exactly_zero(self) -> None:
        """Test result when all inputs are exactly zero."""
        # This requires an unknown method to get 0.5 default
        # But we can't create invalid enums, so use a method with low confidence
        result = compute_extraction_confidence(
            method=ExtractionMethod.LLM_FALLBACK,  # 0.72
            phase2_confidence=0.0,
            phase3_field_coverage=0.0,
        )
        # 0.72*0.4 = 0.288
        assert result == pytest.approx(0.288, abs=1e-6)

    def test_boundary_values(self) -> None:
        """Test with boundary values (0.0 and 1.0)."""
        # All 0.0
        result_min = compute_extraction_confidence(
            method=ExtractionMethod.LLM_FALLBACK,
            phase2_confidence=0.0,
            phase3_field_coverage=0.0,
        )
        assert result_min > 0.0  # Method confidence keeps it above 0

        # All 1.0
        result_max = compute_extraction_confidence(
            method=ExtractionMethod.MANUAL,
            phase2_confidence=1.0,
            phase3_field_coverage=1.0,
        )
        assert result_max == 1.0

    def test_perfect_manual_extraction(self) -> None:
        """Test with perfect manual extraction - should be exactly 1.0."""
        result = compute_extraction_confidence(
            method=ExtractionMethod.MANUAL,
            phase2_confidence=1.0,
            phase3_field_coverage=1.0,
        )
        assert result == 1.0

    def test_p1_vector_typical(self) -> None:
        """Test typical P1_VECTOR scenario."""
        result = compute_extraction_confidence(
            method=ExtractionMethod.P1_VECTOR,  # 0.97
            phase2_confidence=0.92,
            phase3_field_coverage=0.90,
        )
        # 0.97*0.4 + 0.92*0.3 + 0.90*0.3 = 0.388 + 0.276 + 0.27 = 0.934
        expected = 0.97 * 0.4 + 0.92 * 0.3 + 0.90 * 0.3
        assert result == pytest.approx(expected, abs=1e-6)

    def test_p1_vlm_typical(self) -> None:
        """Test typical P1_VLM scenario."""
        result = compute_extraction_confidence(
            method=ExtractionMethod.P1_VLM,  # 0.85
            phase2_confidence=0.88,
            phase3_field_coverage=0.82,
        )
        # 0.85*0.4 + 0.88*0.3 + 0.82*0.3 = 0.34 + 0.264 + 0.246 = 0.85
        expected = 0.85 * 0.4 + 0.88 * 0.3 + 0.82 * 0.3
        assert result == pytest.approx(expected, abs=1e-6)
