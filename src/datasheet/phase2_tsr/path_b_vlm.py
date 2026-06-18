"""Phase 2 Path B: Vision-Language Model table extraction using Qwen2-VL-7B.

Implements table structure recognition using a VLM that interprets table images
and returns markdown-formatted tables. Handles borderless tables that Path A
cannot process.

This module's implementation is currently a placeholder due to the size and complexity of the Qwen2-VL-7B model. It follows the OpenAPI specification to define the expected interface and structure for VLM-based extraction.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

import numpy as np
from PIL import Image

from src.datasheet.phase1_dla._schemas import TableCrop
from src.datasheet.phase2_tsr._schemas import GridMatrix
from src.schemas.datasheet import TableSectionType

if TYPE_CHECKING:
    from src.config import Config

logger = logging.getLogger(__name__)

# VLM path confidence scores
VLM_CONFIDENCE_SUCCESS: float = 0.82
VLM_CONFIDENCE_PARSE_FAILURE: float = 0.50

# Prompt template for Qwen2-VL-7B
VLM_PROMPT_TEMPLATE: str = """Return this table as a markdown table. Include all rows and columns exactly as shown. Use | delimiters. If a cell is empty, use an empty cell ||."""


class VLMExtractionError(Exception):
    """Custom exception for VLM-related extraction failures."""
    pass


class VLMModelNotAvailableError(VLMExtractionError):
    """Raised when the VLM model is not available or cannot be loaded."""
    pass


def _encode_image_to_base64(image: Image.Image) -> str:
    """Encode PIL Image to base64 string for VLM API.

    Args:
        image: PIL Image to encode

    Returns:
        Base64-encoded PNG string
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    img_bytes = buffer.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')


def _load_qwen2_vl_model(model_path: Path) -> tuple[Any, Any]:
    """Load Qwen2-VL-7B-Instruct model.

    Args:
        model_path: Path to model weights

    Returns:
        Loaded model and processor

    Raises:
        VLMModelNotAvailableError: If model cannot be loaded
    """
    try:
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        
        logger.info(f"Loading Qwen2-VL model from {model_path}")
        
        model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype="auto",
            device_map="auto",
        )
        processor = AutoProcessor.from_pretrained(model_path)  # type: ignore[no-untyped-call]
        
        return model, processor
        
    except Exception as e:
        logger.error(f"Failed to load Qwen2-VL model: {e}")
        raise VLMModelNotAvailableError(f"Could not load VLM from {model_path}: {e}")


def _call_vlm_with_image(
    image: Image.Image,
    prompt: str,
    model: Any,
    processor: Any,
) -> str:
    """Call Qwen2-VL model with image and prompt.

    Args:
        image: Table crop image
        prompt: Text prompt for the model
        model: Loaded Qwen2-VL model
        processor: Model processor

    Returns:
        Model response text (markdown table)

    Raises:
        VLMExtractionError: If model inference fails
    """
    try:
        import torch
        
        # Prepare image for the model
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        inputs = processor(
            text=[text],
            images=[image],
            return_tensors="pt",
        )
        inputs = inputs.to(model.device)
        
        # Generate
        with torch.no_grad():
            generated_ids = model.generate(**inputs, max_new_tokens=1024)
            
        output_text = processor.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]
        
        return cast(str, output_text)
        
    except Exception as e:
        logger.error(f"VLM inference failed: {e}")
        raise VLMExtractionError(f"VLM inference failed: {e}")


def _parse_markdown_to_grid_matrix(
    markdown_text: str,
    section_type: TableSectionType,
    source_page: int,
    source_table_index: int,
) -> tuple[Optional[GridMatrix], float]:
    """Parse markdown table text into GridMatrix.

    Args:
        markdown_text: Markdown table output from VLM
        section_type: TableSectionType from Phase 1
        source_page: Page number
        source_table_index: Table index within page

    Returns:
        Tuple of (GridMatrix or None, confidence_score)
        - GridMatrix with extraction_path="vlm" on success, None on parse failure
        - confidence = 0.82 on success, 0.50 on parse failure
    """
    from src.datasheet.phase2_tsr._schemas import CellValue, GridMatrix

    lines = markdown_text.strip().split('\n')
    
    # Filter for table lines (contain |)
    table_lines = [line for line in lines if '|' in line]
    
    if len(table_lines) < 2:
        logger.warning("VLM output has insufficient table lines")
        return None, VLM_CONFIDENCE_PARSE_FAILURE
    
    # Remove separator lines (---|---|---)
    content_lines = [
        line for line in table_lines 
        if not all(c in '-|: ' for c in line)
    ]
    
    if len(content_lines) < 1:
        logger.warning("VLM output has no content after filtering separators")
        return None, VLM_CONFIDENCE_PARSE_FAILURE
    
    # First pass: parse all rows to determine max columns
    raw_rows = []
    for line in content_lines:
        cols = [c.strip() for c in line.split('|')]
        # Strip leading and trailing empty columns from the | delimiters
        while len(cols) > 0 and cols[0] == '':
            cols.pop(0)
        while len(cols) > 0 and cols[-1] == '':
            cols.pop()
        if cols:
            raw_rows.append(cols)
    
    if not raw_rows:
        return None, VLM_CONFIDENCE_PARSE_FAILURE
    
    # Determine consistent column count (max across all rows)
    num_cols = max(len(row) for row in raw_rows)
    
    # Second pass: create cells with consistent column count
    cells: list[CellValue] = []
    for row_idx, cols in enumerate(raw_rows):
        # Pad row to match max columns
        while len(cols) < num_cols:
            cols.append('')
        
        for col_idx, text in enumerate(cols[:num_cols]):
            is_header = row_idx == 0
            
            cells.append(
                CellValue(
                    text=text,
                    row=row_idx,
                    col=col_idx,
                    rowspan=1,
                    colspan=1,
                    is_header=is_header,
                )
            )
    
    num_rows = len(content_lines)
    
    if num_rows < 1 or num_cols < 1:
        logger.warning(f"VLM parse resulted in invalid grid: {num_rows}x{num_cols}")
        return None, VLM_CONFIDENCE_PARSE_FAILURE
    
    logger.info(f"VLM parsed {num_rows}x{num_cols} grid")
    
    grid = GridMatrix(
        cells=cells,
        num_rows=num_rows,
        num_cols=num_cols,
        section_type=section_type,
        source_page=source_page,
        source_table_index=source_table_index,
        extraction_path="vlm",
        confidence=VLM_CONFIDENCE_SUCCESS,
        has_merged_cells=False,
    )
    
    return grid, VLM_CONFIDENCE_SUCCESS


def extract_table_vlm_path(
    pdf_path: Path,
    table_crop: TableCrop,
    table_index: int,
    config: Config,
) -> Optional[GridMatrix]:
    """Extract table structure using VLM path (Qwen2-VL-7B).

    Path B uses a vision-language model to interpret table images.
    Handles borderless tables that Path A cannot process.

    Args:
        pdf_path: Path to source PDF
        table_crop: TableCrop from Phase 1 with image_bytes
        table_index: Index of table within page
        config: Application configuration

    Returns:
        GridMatrix with extraction_path="vlm" on success,
        None if model unavailable or extraction fails.
        Confidence = 0.82 on success, 0.50 on parse failure.

    Notes:
        If model path missing or model errors, returns None and logs WARNING,
        never raises an exception to the caller.
    """
    page_number = table_crop.page_number
    section_type = table_crop.section_type

    logger.info(f"Path B: Processing table {table_index} on page {page_number}")

    try:
        # Load model from config
        model_path = config.get_model_path("qwen2_vl_7b")
        
        if not model_path.exists():
            logger.warning(
                f"Qwen2-VL model not found at {model_path}, "
                "skipping VLM path"
            )
            return None

        model, processor = _load_qwen2_vl_model(model_path)

        # Convert image bytes to PIL Image
        image = Image.open(io.BytesIO(table_crop.image_bytes))

        # Call VLM with prompt
        vlm_output = _call_vlm_with_image(
            image,
            VLM_PROMPT_TEMPLATE,
            model,
            processor,
        )

        # Parse markdown to grid
        grid, _ = _parse_markdown_to_grid_matrix(
            vlm_output,
            section_type,
            page_number,
            table_index,
        )

        if grid is None:
            logger.warning(
                f"Path B: Failed to parse VLM output for table {table_index}, "
                f"returning None (parse failure)"
            )
            return None

        logger.info(
            f"Path B: Successfully extracted {grid.num_rows}x{grid.num_cols} grid "
            f"with confidence {grid.confidence}"
        )

        return grid

    except VLMModelNotAvailableError as e:
        logger.warning(f"Path B: Model not available - {e}")
        return None
    except VLMExtractionError as e:
        logger.warning(f"Path B: Extraction error - {e}")
        return None
    except Exception as e:
        logger.warning(f"Path B: Unexpected error - {e}")
        return None
