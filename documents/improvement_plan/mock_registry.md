Based on the test files in your codebase, here is the extraction of all `mock.patch`, `MagicMock`, and `unittest.mock` calls, grouped by their domain categories.

### DB/PostgreSQL mocks

| Mock Target | Real Module/Function | Test File | Status |
| --- | --- | --- | --- |
| `config` (via `MagicMock()`) | `supplier_cache_path` config parameter | `tests/unit/bom/test_bom_ladder.py` / `all_tests_dump.txt` | ⬜ Not real yet. |

### LLM/Model mocks

| Mock Target | Real Module/Function | Test File | Status |
| --- | --- | --- | --- |
| `"src.knowledge_graph.ingestion.triple_extractor.extract_with_llm"` | `extract_with_llm` | `tests/unit/test_triple_extractor.py` | ⬜ Not real yet. |
| `"src.knowledge_graph.ingestion.triple_extractor.extract_with_spacy"` | `extract_with_spacy` | `tests/unit/test_triple_extractor.py` | ⬜ Not real yet. |
| `"src.completion.engine.call_llm_with_instructor"` | `call_llm_with_instructor` | `tests/unit/test_semantic_search.py` / Smoke tests | ⬜ Not real yet. |
| `mock_model` (via `MagicMock()`) | `SentenceTransformer` embedding model | `tests/unit/test_semantic_search.py` | ⬜ Not real yet. |
| `mock_module` / `mock_index` (via `MagicMock()`) | `faiss` vector search flat index library | `tests/unit/test_semantic_search.py` | ⬜ Not real yet. |
| `"src.knowledge_graph.ingestion.extract_triples"` | `extract_triples` | `tests/unit/test_kg1_aac.py` | ⬜ Not real yet. |

### File I/O mocks

| Mock Target | Real Module/Function | Test File | Status |
| --- | --- | --- | --- |
| `"src.output.generate_design_report"` | `generate_design_report` | `tests/unit/test_orchestrator.py` | ⬜ Not real yet. |

### External API mocks

| Mock Target | Real Module/Function | Test File | Status |
| --- | --- | --- | --- |
| `"src.knowledge_graph.ingestion.kg1_aac.scraper._fetch_url"` | `_fetch_url` HTTP request engine | `tests/unit/test_kg1_aac.py` | ⬜ Not real yet. |
| `"src.knowledge_graph.ingestion.kg1_aac.scrape_volume"` | `scrape_volume` webpage batch scraper | `tests/unit/test_kg1_aac.py` | ⬜ Not real yet. |

### Internal pipeline mocks

| Mock Target | Real Module/Function | Test File | Status |
| --- | --- | --- | --- |
| `"src.datasheet.phase3_extract.component_header.normalize_package"` | `normalize_package` utility | `tests/unit/test_phase3_extract.py` | ⬜ Not real yet. |
| `config` (via `MagicMock(spec=Config)`) | Global system `Config` schema class | `tests/unit/test_phase3_extract.py` | ⬜ Not real yet. |
| `mock_config` (via `MagicMock()`) | `Config` provider dependency injection fixture | `tests/unit/test_schematic_synthesizer.py` | ⬜ Not real yet. |
| `mock_config` (via `MagicMock()`) | `Config` module fixture for methodology testing | `tests/unit/test_admin.py` | ⬜ Not real yet. |
| `"src.knowledge_graph.admin.cli._get_config"` | `_get_config` | `tests/unit/test_admin.py` | ⬜ Not real yet. |
| `"src.knowledge_graph.admin.cli._load_graph"` | `_load_graph` | `tests/unit/test_admin.py` | ⬜ Not real yet. |
| `"src.knowledge_graph.admin.cli._save_graph"` | `_save_graph` | `tests/unit/test_admin.py` | ⬜ Not real yet. |
| `"src.schematic.beam_search_escalation.verify_schematic"` | `verify_schematic` netlist scoring function | `tests/unit/schematic/test_beam_search_escalation.py` | ⬜ Not real yet. |
| `"src.schematic.sa_polisher.verify_schematic"` | `verify_schematic` optimizer evaluation engine | `tests/unit/schematic/test_sa_polisher.py` | ⬜ Not real yet. |
| `"src.bom.candidates.generate_bom"` | `generate_bom` knowledge graph search path parser | `tests/unit/bom/test_bom_candidates.py` | ⬜ Not real yet. |
| `"src.bom.candidates.ValidatedBOM"` | `ValidatedBOM` model constructor validation override | `tests/unit/bom/test_bom_candidates.py` | ⬜ Not real yet. |
| `mock_config` (via `MagicMock()`) | `Config` framework instance for builder orchestration | `tests/unit/test_nir_builder.py` | ⬜ Not real yet. |
| `mock_config` (via `MagicMock()`) | `Config` configuration mock for query handling | `tests/unit/test_intent_parser.py` | ⬜ Not real yet. |
| `"src.output.serialize_to_tscircuit"` | `serialize_to_tscircuit` serializer step | `tests/unit/test_orchestrator.py` | ⬜ Not real yet. |
| `"src.output.serialize_to_kicad"` | `serialize_to_kicad` EDA generation step | `tests/unit/test_orchestrator.py` | ⬜ Not real yet. |