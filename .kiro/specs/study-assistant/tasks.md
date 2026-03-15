# Implementation Plan: Adaptive Concept Gap Detector & AI Study Assistant

## Overview

Implement a serverless Python backend with six Lambda functions, shared utilities, and a single DynamoDB table. Build incrementally: shared utilities first, then each Lambda, then wire everything together.

## Tasks

- [ ] 1. Set up project structure, shared utilities, and test infrastructure
  - Create directory layout: `lambdas/`, `shared/`, `tests/`
  - Implement `shared/errors.py` — standard HTTP error response builder
  - Implement `shared/db.py` — DynamoDB client wrapper with get/put/update helpers using single-table key patterns
  - Implement `shared/bedrock.py` — Bedrock Runtime client wrapper with `invoke_model` call and response parsing
  - Implement `shared/session.py` — session upsert and retrieval logic (create-or-reuse pattern)
  - Add `conftest.py` with Hypothesis profile (`max_examples=100`) and moto fixtures for DynamoDB and S3
  - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 1.1 Write property test for idempotent session creation (Property 14)
    - **Property 14: Idempotent Session Creation**
    - Generate random student IDs; call session upsert N times; assert exactly one SESSION#METADATA record exists
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 1.2 Write property test for entity scoping (Property 15)
    - **Property 15: Entity Scoping to Session**
    - For any entity creation call, assert `pk == SESSION#{student_id}`
    - **Validates: Requirements 7.3**

- [ ] 2. Implement `shared/parser.py` — text extraction and JSON serialization
  - Implement PDF text extraction using PyMuPDF (`fitz`) producing `sections` list with heading/text pairs
  - Implement plain-text extraction (utf-8 decode, single section)
  - Implement `serialize(parsed) -> str` (JSON) and `deserialize(json_str) -> dict`
  - Raise a typed exception on extraction failure; raise on deserialization failure
  - _Requirements: 1.2, 8.1, 8.2, 8.3, 8.4_

  - [ ]* 2.1 Write property test for parser round-trip integrity (Property 2)
    - **Property 2: Parser Round-Trip Integrity**
    - Generate random document text; parse → serialize → deserialize; assert structural equivalence
    - **Validates: Requirements 8.1, 8.2, 8.3, 1.2**

- [ ] 3. Implement Material Processor Lambda (`lambdas/material_processor.py`)
  - Validate `student_id` presence (400 if missing)
  - Validate file size ≤ 10 MB (400 if exceeded)
  - Validate file type is PDF or plain text (400 if unsupported)
  - Extract text via `parser.py`; on failure return 422 and do NOT write to DynamoDB (atomicity)
  - Store raw file in S3 under `{student_id}/{material_id}/{filename}`
  - Serialize parsed content and write to DynamoDB (`MATERIAL#{material_id}` under `SESSION#{student_id}`)
  - Upsert session record via `session.py`
  - On deserialization failure return 500 and log
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2, 8.1, 8.2, 8.4_

  - [ ]* 3.1 Write property test for material upload scoping (Property 1)
    - **Property 1: Material Upload Scoping**
    - Generate random student IDs and file content; assert S3 key starts with `{student_id}/`
    - **Validates: Requirements 1.1**

  - [ ]* 3.2 Write property test for atomicity on extraction failure (Property 3)
    - **Property 3: Atomicity on Extraction Failure**
    - Simulate extraction failure; assert zero DynamoDB items written for that material key
    - **Validates: Requirements 1.5**

  - [ ]* 3.3 Write unit tests for Material Processor error paths
    - Test 400 on file > 10 MB, unsupported type, missing student_id
    - Test 422 on extraction failure with no partial DynamoDB record
    - Test 500 on deserialization failure

- [ ] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement QA Engine Lambda (`lambdas/qa_engine.py`)
  - Validate `student_id`, `material_id`, `question` fields (400 if missing)
  - Load parsed material from DynamoDB; return 404 if not found
  - Build prompt with full material content + question
  - Invoke Bedrock via `bedrock.py`; return 502 on Bedrock error
  - Log Q&A pair to session (`QA#{timestamp}#{uuid}`)
  - Return `{ answer }` within 30-second Lambda timeout
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 7.3_

  - [ ]* 5.1 Write property test for context grounding in QA prompts (Property 4)
    - **Property 4: Context Grounding in Bedrock Prompts**
    - Generate random material content and questions; mock Bedrock; assert prompt contains full material text
    - **Validates: Requirements 2.1**

  - [ ]* 5.2 Write property test for Q&A interaction persistence (Property 5)
    - **Property 5: Interaction Persistence**
    - Generate random Q&A pairs; assert entry retrievable from mock DynamoDB after call
    - **Validates: Requirements 2.5**

  - [ ]* 5.3 Write unit tests for QA Engine error paths
    - Test 404 when material not found
    - Test 502 on Bedrock error

- [ ] 6. Implement Quiz Generator Lambda (`lambdas/quiz_generator.py`)
  - Validate `student_id`, `material_id`, `num_questions` (5–20) fields (400 if missing/invalid)
  - Load parsed material from DynamoDB; return 404 if not found
  - Build quiz generation prompt; invoke Bedrock; parse structured response into Quiz object
  - Retry Bedrock invocation once on `JSONDecodeError` or structural parse failure; return 502 after second failure
  - Validate each question has non-empty text, exactly 4 options, correct answer in options, non-empty concept label
  - Persist quiz to DynamoDB (`QUIZ#{quiz_id}` under `SESSION#{student_id}`)
  - Return `{ quiz_id, questions }`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 7.3_

  - [ ]* 6.1 Write property test for quiz structure completeness (Property 6)
    - **Property 6: Quiz Structure Completeness**
    - Generate random Bedrock quiz responses; assert every question has required fields and valid structure
    - **Validates: Requirements 3.2**

  - [ ]* 6.2 Write property test for quiz question count invariant (Property 7)
    - **Property 7: Quiz Question Count Invariant**
    - Generate N in [5, 20]; assert generated quiz contains exactly N questions
    - **Validates: Requirements 3.3**

  - [ ]* 6.3 Write property test for quiz persistence (Property 8)
    - **Property 8: Quiz Persistence**
    - Generate random quizzes; assert retrievable from mock DynamoDB immediately after generation
    - **Validates: Requirements 3.4**

  - [ ]* 6.4 Write unit tests for Quiz Generator error paths
    - Test 404 when material not found
    - Test retry-once behavior: assert Bedrock invoked exactly twice before 502
    - Test 502 after two malformed responses

- [ ] 7. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement Gap Detector Lambda (`lambdas/gap_detector.py`)
  - Handle two routes: POST `/quizzes/{quiz_id}/submit` and GET `/gaps`
  - **Submit path:**
    - Validate `student_id`, `quiz_id`, `answers` fields (400 listing missing fields)
    - Load quiz from DynamoDB; return 404 if not found
    - Score answers per concept label (correct / total per concept); compute overall percentage
    - Identify concepts with score < 60%; upsert `GAP#{concept_label}` records with latest score
    - Persist `RESULT#{quiz_id}` to DynamoDB
    - Return `{ score_pct, per_concept, gaps }` — include gaps list if any exist
  - **Gaps path:**
    - Validate `student_id`; return 404 if session not found
    - Return all `GAP#` items for the session
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 7.3_

  - [ ]* 8.1 Write property test for scoring correctness (Property 9)
    - **Property 9: Scoring Correctness**
    - Generate random quizzes and answer sets; assert per-concept and overall scores match expected ratio math
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 8.2 Write property test for quiz result persistence (Property 10)
    - **Property 10: Quiz Result Persistence**
    - Generate random quiz submissions; assert RESULT item retrievable from mock DynamoDB after scoring
    - **Validates: Requirements 4.3**

  - [ ]* 8.3 Write property test for gap detection threshold (Property 11)
    - **Property 11: Gap Detection Threshold**
    - Generate random per-concept scores; assert gap list exactly matches concepts with score < 60%
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 8.4 Write property test for gaps included in score response (Property 12)
    - **Property 12: Gaps Included in Score Response**
    - Generate sessions with existing gaps; assert score response payload contains non-empty `gaps` field
    - **Validates: Requirements 5.3**

  - [ ]* 8.5 Write property test for gap aggregation using latest score (Property 13)
    - **Property 13: Gap Aggregation Uses Latest Score**
    - Generate multiple quiz results for the same concept label; assert GAP record reflects most recent score
    - **Validates: Requirements 5.4**

  - [ ]* 8.6 Write unit tests for Gap Detector error paths
    - Test 404 when quiz not found
    - Test 400 when answer payload missing required fields
    - Test 404 when session not found on GET /gaps

- [ ] 9. Implement Explanation Engine Lambda (`lambdas/explanation_engine.py`)
  - Validate `student_id`, `concept_label`, `material_id` fields (400 if missing)
  - Verify concept label exists in student's `GAP#` records; return 404 if not
  - Load parsed material from DynamoDB
  - Build targeted explanation prompt with material content + concept label
  - Invoke Bedrock; return 502 on error
  - Log explanation to session (`EXPLANATION#{timestamp}#{uuid}`)
  - Return `{ explanation }` within 30-second Lambda timeout
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.3_

  - [ ]* 9.1 Write property test for context grounding in explanation prompts (Property 4 — explanation path)
    - **Property 4: Context Grounding in Bedrock Prompts (Explanation Engine)**
    - Generate random material content and concept labels; mock Bedrock; assert prompt contains full material text and concept label
    - **Validates: Requirements 6.1**

  - [ ]* 9.2 Write property test for explanation persistence (Property 5 — explanation path)
    - **Property 5: Interaction Persistence (Explanation Engine)**
    - Generate random explanations; assert EXPLANATION log entry retrievable from mock DynamoDB after call
    - **Validates: Requirements 6.5**

  - [ ]* 9.3 Write unit tests for Explanation Engine error paths
    - Test 404 when concept not in student's gaps
    - Test 502 on Bedrock error

- [ ] 10. Implement Session Manager Lambda (`lambdas/session_manager.py`)
  - Validate `student_id` (400 if missing)
  - Load session METADATA record; return 404 if not found
  - Query all items under `SESSION#{student_id}` and group by prefix (MATERIAL, QUIZ, RESULT, GAP, QA, EXPLANATION)
  - Return `{ session_id, materials, quizzes, gaps, qa_log }`
  - _Requirements: 7.3, 7.4, 7.5_

  - [ ]* 10.1 Write property test for session summary completeness (Property 16)
    - **Property 16: Session Summary Completeness**
    - Generate sessions with known sets of materials, quizzes, results, gaps, and Q&A entries; assert all items appear in summary response
    - **Validates: Requirements 7.4**

  - [ ]* 10.2 Write unit tests for Session Manager error paths
    - Test 404 when session not found
    - Test 400 when student_id missing

- [ ] 11. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Wire all Lambdas together and finalize integration
  - [ ] 12.1 Create `lambdas/__init__.py` and ensure all shared imports resolve correctly across all Lambda handlers
    - Verify `shared/` is on the Python path for each Lambda (e.g., via `sys.path` manipulation or packaging config)
    - _Requirements: 1.1–1.5, 2.1–2.5, 3.1–3.6, 4.1–4.5, 5.1–5.5, 6.1–6.5, 7.1–7.5_

  - [ ] 12.2 Create `template.yaml` (SAM) or `serverless.yml` defining all six Lambda functions, API Gateway routes, DynamoDB table, and S3 bucket
    - Map each route from the design's API Gateway table to its Lambda handler
    - Configure Lambda environment variables: `TABLE_NAME`, `BUCKET_NAME`, `BEDROCK_MODEL_ID`
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 6.1, 7.1_

  - [ ]* 12.3 Write integration tests covering end-to-end flows with moto
    - Upload material → ask question → generate quiz → submit answers → get gaps → get explanation → get session summary
    - Assert all entities are scoped to `SESSION#{student_id}` (Property 15)
    - _Requirements: 7.3, 7.4_

- [ ] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis with `max_examples=100`; unit tests use pytest + moto + unittest.mock
- Bedrock is mocked via `unittest.mock.patch` in all tests (moto does not cover Bedrock Runtime)
- The retry-once behavior in Quiz Generator (Requirement 3.5) must be verified by asserting Bedrock was called exactly twice
