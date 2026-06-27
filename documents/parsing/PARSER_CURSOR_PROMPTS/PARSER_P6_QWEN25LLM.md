TASK
====
Implement Qwen25LLMBackend — a concrete LLMBackend that wraps the
existing Qwen2.5-7B + Instructor extraction logic.

CONTEXT FILES TO READ
=====================
src/parsing/backends/_interfaces.py                  ← LLMBackend to implement
src/parsing/backends/_schemas.py                     ← LLMResponse type
src/parsing/backends/_registry.py                    ← where to register
src/datasheet/phase3_extract/extractor.py            ← InstructorWrapper to reuse
src/datasheet/phase3_extract/prompt_templates.py     ← existing prompts pattern
configs/default.yaml                                 ← config structure

FILES TO CREATE
===============
src/parsing/backends/llm/__init__.py
src/parsing/backends/llm/qwen25_backend.py

FILES TO MODIFY
===============
src/parsing/backends/_registry.py                   ← register "qwen25_7b" key
configs/default.yaml                                ← add llm_config block

DO NOT MODIFY
=============
src/datasheet/phase3_extract/extractor.py
Any existing test files

---

## BACKGROUND

The LLMBackend interface is:

    extract(self, text: str, system_prompt: str, output_schema: dict) -> LLMResponse

Think of it like a translator:
- text:          the raw content to extract from (table text, prose, etc.)
- system_prompt: what the model is being asked to do
- output_schema: the JSON Schema dict describing what shape the answer must be
- returns:       LLMResponse with raw_text + parsed_json + confidence

The backend is responsible for:
1. Loading the model (lazy, once)
2. Calling the model with the given inputs
3. Parsing the response into LLMResponse
4. Never raising — always returning something

---

## src/parsing/backends/llm/qwen25_backend.py

Class: Qwen25LLMBackend(LLMBackend)

Constructor: __init__(self, config: Config)
    Reads from config:
        parsing.llm_config.model_key  (default: "qwen25_7b")
        parsing.llm_config.device     (default: "cpu")
        parsing.llm_config.max_tokens (default: 1024)
    Does NOT load model here.
    self._instructor_wrapper = None   ← lazy

Method: extract(self, text: str, system_prompt: str, output_schema: dict) -> LLMResponse

    Step 1: Lazy-load InstructorWrapper
        If self._instructor_wrapper is None:
            from src.datasheet.phase3_extract.extractor import InstructorWrapper
            model_path = self._config.get_model_path(self._model_key)
            self._instructor_wrapper = InstructorWrapper(
                model_path=model_path,
                device=self._device,
            )

    Step 2: Build a dynamic Pydantic model from output_schema
        The interface receives output_schema as a JSON Schema dict.
        InstructorWrapper.extract() needs a Pydantic model class, not a dict.
        Build one dynamically:

        from pydantic import create_model
        import json

        Use output_schema["properties"] to get field names.
        All fields default to Optional[str] = None for simplicity —
        the caller is responsible for interpreting the parsed_json dict.

        DynamicModel = create_model(
            "DynamicExtractionModel",
            **{
                field_name: (Optional[str], None)
                for field_name in output_schema.get("properties", {}).keys()
            }
        )

    Step 3: Call InstructorWrapper
        result = self._instructor_wrapper.extract(
            response_model=DynamicModel,
            system_prompt=system_prompt,
            user_content=text,
        )

    Step 4: Build LLMResponse
        If result is None:
            Return LLMResponse(
                raw_text="",
                parsed_json=None,
                confidence=0.0,
                backend_used="qwen25_7b"
            )

        raw_text = str(result)
        parsed_json = result.model_dump(exclude_none=True)

        Return LLMResponse(
            raw_text=raw_text,
            parsed_json=parsed_json,
            confidence=0.85,       ← fixed base confidence for LLM extraction
            backend_used="qwen25_7b"
        )

    Error handling:
        Model load failure → log, return LLMResponse confidence=0.0
        Any runtime error  → log, return LLMResponse confidence=0.0
        Never raise from extract()

---

## src/parsing/backends/llm/__init__.py

Export Qwen25LLMBackend only.

---

## _registry.py modification

Add LLM_REGISTRY:
    "qwen25_7b": "src.parsing.backends.llm.qwen25_backend.Qwen25LLMBackend"

BackendRegistry.get_llm() follows same lazy-cache pattern as other getters.

---

## configs/default.yaml addition

Under parsing block add:

    llm_config:
      model_key: "qwen25_7b"
      device: "cpu"
      max_tokens: 1024

---

GATE TESTS
==========
File: tests/unit/parsing/test_qwen25_backend.py

All tests mock InstructorWrapper — no real model weights.

Test 1: Qwen25LLMBackend implements LLMBackend
    isinstance check passes

Test 2: InstructorWrapper is None at construction
    self._instructor_wrapper is None after __init__

Test 3: extract() with successful InstructorWrapper response
    Mock InstructorWrapper.extract to return a Pydantic object with:
        field "parameter" = "VCC"
        field "value"     = "3.3"
    Call backend.extract(
        text="VCC 3.3V typical",
        system_prompt="Extract parameter and value",
        output_schema={
            "properties": {
                "parameter": {"type": "string"},
                "value":     {"type": "string"}
            }
        }
    )
    Assert: result.backend_used == "qwen25_7b"
    Assert: result.parsed_json is not None
    Assert: result.parsed_json["parameter"] == "VCC"
    Assert: result.parsed_json["value"] == "3.3"
    Assert: result.confidence == 0.85

Test 4: extract() when InstructorWrapper returns None → LLMResponse confidence=0.0
    Mock InstructorWrapper.extract to return None
    result = backend.extract("text", "prompt", {"properties": {}})
    Assert: result.parsed_json is None
    Assert: result.confidence == 0.0
    Assert: result.backend_used == "qwen25_7b"

Test 5: extract() on model load failure → LLMResponse confidence=0.0
    Mock config.get_model_path to raise FileNotFoundError
    result = backend.extract("text", "prompt", {"properties": {}})
    Assert: result.confidence == 0.0
    Assert no exception raised

Test 6: extract() on runtime error → LLMResponse confidence=0.0
    InstructorWrapper loads fine but .extract raises RuntimeError
    result = backend.extract("text", "prompt", {"properties": {}})
    Assert: result.confidence == 0.0
    Assert no exception raised

Test 7: BackendRegistry with llm="qwen25_7b" returns
    Qwen25LLMBackend from get_llm()
    Assert isinstance check passes

Test 8: Second call to get_llm() returns same cached instance
    registry.get_llm() called twice
    Assert result1 is result2

CONSTRAINTS
===========
- Dynamic Pydantic model uses Optional[str] for all fields — no schema validation here
- All transformers/torch imports stay inside InstructorWrapper, never imported here
- Python 3.11+, Pydantic v2
- Never raise from extract()