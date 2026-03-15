# Technical Design: Adaptive Concept Gap Detector & AI Study Assistant

## Overview

The Study Assistant is a fully serverless backend built on AWS. Students interact with it via API Gateway, which routes requests to a set of Python Lambda functions. Each Lambda handles a distinct concern: material ingestion, question answering, quiz generation, scoring/gap detection, and targeted explanations. Amazon Bedrock provides the AI inference layer. S3 stores raw uploaded files. DynamoDB stores all structured state (sessions, parsed materials, quizzes, results, Q&A logs, concept gaps).

The system is stateless at the compute layer — all state lives in DynamoDB and S3. Lambda functions are invoked per-request and share no in-process state.

### Key Design Decisions

- **Single DynamoDB table with composite keys**: A single table with `pk` (partition key) and `sk` (sort key) supports all entity types via key prefixes. This avoids managing multiple tables and enables efficient access patterns.
- **Bedrock via boto3**: All AI calls go through the `boto3` Bedrock Runtime client using the `invoke_model` API. The model ID is configurable via Lambda environment variables.
- **Parsed material stored in DynamoDB, raw file in S3**: Raw uploads live in S3 (cheap, durable). The extracted text representation is stored in DynamoDB for fast retrieval during AI calls.
- **Retry-once on malformed Bedrock output**: Quiz generation retries once on parse failure before returning 502, keeping latency bounded.

---

## Architecture

```mermaid
graph TD
    Student -->|HTTP| APIGW[API Gateway]
    APIGW -->|POST /materials| MP[Material Processor Lambda]
    APIGW -->|POST /qa| QA[QA Engine Lambda]
    APIGW -->|POST /quizzes| QG[Quiz Generator Lambda]
    APIGW -->|POST /quizzes/{id}/submit| GD[Gap Detector Lambda]
    APIGW -->|GET /gaps| GD
    APIGW -->|POST /explanations| EE[Explanation Engine Lambda]
    APIGW -->|GET /session| SM[Session Manager Lambda]

    MP -->|PutObject| S3[S3 Material Store]
    MP -->|PutItem / GetItem| DDB[DynamoDB Session Store]

    QA -->|GetItem| DDB
    QA -->|InvokeModel| Bedrock[Amazon Bedrock]
    QA -->|PutItem| DDB

    QG -->|GetItem| DDB
    QG -->|InvokeModel| Bedrock
    QG -->|PutItem| DDB

    GD -->|GetItem / PutItem| DDB

    EE -->|GetItem| DDB
    EE -->|InvokeModel| Bedrock
    EE -->|PutItem| DDB

    SM -->|GetItem| DDB
```

### Request Flow (Material Upload)

1. Student POSTs file to `/materials` with `student_id` header.
2. API Gateway invokes Material Processor Lambda.
3. Lambda validates file size (≤10 MB) and type (PDF or plain text).
4. Raw file is stored in S3 under `{student_id}/{material_id}/{filename}`.
5. Text is extracted (PyMuPDF for PDF, direct decode for `.txt`).
6. Parsed content is serialized to JSON and written to DynamoDB.
7. Session record is created or updated.
8. Lambda returns `{ material_id, status }`.

---

## Components and Interfaces

### API Gateway Routes

| Method | Path | Lambda | Description |
|--------|------|--------|-------------|
| POST | `/materials` | Material Processor | Upload study material |
| POST | `/qa` | QA Engine | Ask a question |
| POST | `/quizzes` | Quiz Generator | Generate a quiz |
| POST | `/quizzes/{quiz_id}/submit` | Gap Detector | Submit answers |
| GET | `/gaps` | Gap Detector | Get concept gaps |
| POST | `/explanations` | Explanation Engine | Get targeted explanation |
| GET | `/session` | Session Manager | Get session summary |

All routes require a `student_id` query parameter or header. API Gateway passes the full event to each Lambda.

### Lambda Functions

#### Material Processor (`material_processor.handler`)

```
Input:  multipart/form-data with file + student_id
Output: { material_id: str, status: "ok" }
Errors: 400 (size/type), 422 (extraction failure)
```

Responsibilities:
- Validate file constraints
- Extract text (PyMuPDF for PDF, utf-8 decode for text)
- Serialize parsed content to JSON
- Write to S3 (raw) and DynamoDB (parsed)
- Upsert session record

#### QA Engine (`qa_engine.handler`)

```
Input:  { student_id, material_id, question }
Output: { answer: str }
Errors: 404 (material not found), 502 (Bedrock error)
```

Responsibilities:
- Load parsed material from DynamoDB
- Build prompt with material context + question
- Invoke Bedrock
- Log Q&A pair to session
- Return answer

#### Quiz Generator (`quiz_generator.handler`)

```
Input:  { student_id, material_id, num_questions: int (5–20) }
Output: { quiz_id: str, questions: [Question] }
Errors: 404 (material not found), 502 (Bedrock/parse error)
```

Responsibilities:
- Load parsed material
- Build quiz generation prompt
- Invoke Bedrock, parse structured response
- Retry once on parse failure
- Persist quiz to DynamoDB
- Return quiz object

#### Gap Detector (`gap_detector.handler`)

```
Input (submit):  { student_id, quiz_id, answers: [{ question_id, answer }] }
Output (submit): { score_pct, per_concept: { label: score_pct }, gaps: [str] }
Errors:          404 (quiz not found), 400 (missing fields)

Input (gaps):    GET with student_id
Output (gaps):   { gaps: [ConceptGap] }
```

Responsibilities:
- Score answers per concept label
- Identify concepts below 60%
- Upsert concept gaps in session
- Return results

#### Explanation Engine (`explanation_engine.handler`)

```
Input:  { student_id, concept_label, material_id }
Output: { explanation: str }
Errors: 404 (concept not in gaps), 502 (Bedrock error)
```

Responsibilities:
- Verify concept is in student's gaps
- Load material content
- Build targeted explanation prompt
- Invoke Bedrock
- Log explanation to session
- Return explanation

#### Session Manager (`session_manager.handler`)

```
Input:  GET with student_id
Output: { session_id, materials: [...], quizzes: [...], gaps: [...], qa_log: [...] }
Errors: 404 (session not found), 400 (missing student_id)
```

### Shared Utilities

- `db.py` — DynamoDB client wrapper (get/put/update helpers)
- `bedrock.py` — Bedrock client wrapper (invoke with retry, response parsing)
- `parser.py` — Text extraction and JSON serialization/deserialization
- `session.py` — Session upsert and retrieval logic
- `errors.py` — Standard HTTP error response builder

---

## Data Models

### DynamoDB Table: `study-assistant`

Single table design. All entities share the table with key prefixes.

#### Key Schema

| Attribute | Type | Description |
|-----------|------|-------------|
| `pk` | String | Partition key — entity owner/scope |
| `sk` | String | Sort key — entity type + ID |

#### Entity Patterns

**Session**
```
pk: SESSION#{student_id}
sk: METADATA
Attributes: { created_at, updated_at, student_id }
```

**Parsed Material**
```
pk: SESSION#{student_id}
sk: MATERIAL#{material_id}
Attributes: {
  material_id,
  s3_key,
  filename,
  parsed_content: { sections: [{ heading, text }], raw_text },  # JSON
  created_at
}
```

**Quiz**
```
pk: SESSION#{student_id}
sk: QUIZ#{quiz_id}
Attributes: {
  quiz_id,
  material_id,
  questions: [{
    question_id,
    text,
    options: [str],
    correct_answer: str,
    concept_label: str
  }],
  created_at
}
```

**Quiz Result**
```
pk: SESSION#{student_id}
sk: RESULT#{quiz_id}
Attributes: {
  quiz_id,
  overall_score_pct: float,
  per_concept: { label: score_pct },
  submitted_at
}
```

**Concept Gap**
```
pk: SESSION#{student_id}
sk: GAP#{concept_label}
Attributes: {
  concept_label,
  latest_score_pct: float,
  updated_at
}
```

**Q&A Log Entry**
```
pk: SESSION#{student_id}
sk: QA#{timestamp}#{uuid}
Attributes: { question, answer, material_id, created_at }
```

**Explanation Log Entry**
```
pk: SESSION#{student_id}
sk: EXPLANATION#{timestamp}#{uuid}
Attributes: { concept_label, explanation, material_id, created_at }
```

### S3 Object Key Pattern

```
{student_id}/{material_id}/{original_filename}
```

### Parsed Material JSON Schema

```json
{
  "material_id": "string",
  "filename": "string",
  "sections": [
    {
      "heading": "string | null",
      "text": "string"
    }
  ],
  "raw_text": "string"
}
```

This is the canonical in-memory representation. `parser.py` is responsible for producing and consuming this schema, and the round-trip property (Requirement 8.3) applies to it.

### Question Object

```json
{
  "question_id": "string",
  "text": "string",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct_answer": "string",
  "concept_label": "string"
}
```


---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Material Upload Scoping

*For any* student identifier and any valid uploaded file, after a successful upload the S3 object key should begin with the student's identifier prefix, ensuring materials are always scoped to their owner.

**Validates: Requirements 1.1**

---

### Property 2: Parser Round-Trip Integrity

*For any* valid Study_Material document (PDF or plain text), parsing it into the in-memory representation, serializing that representation to JSON, then deserializing the JSON back should produce a structure equivalent to the original parsed representation.

**Validates: Requirements 8.1, 8.2, 8.3, 1.2**

---

### Property 3: Atomicity on Extraction Failure

*For any* Study_Material whose text extraction fails, no partial record should exist in the Session_Store after the failure — the DynamoDB item count for that material key should be zero.

**Validates: Requirements 1.5**

---

### Property 4: Context Grounding in Bedrock Prompts

*For any* QA request, quiz generation request, or explanation request, the prompt sent to the Bedrock_Client should contain the full parsed material content retrieved from the Session_Store, ensuring answers are grounded in the student's actual materials.

**Validates: Requirements 2.1, 3.1, 6.1**

---

### Property 5: Interaction Persistence

*For any* completed Q&A interaction or explanation interaction, the question/answer pair or explanation should be retrievable from the Session_Store under the student's session after the response is returned.

**Validates: Requirements 2.5, 6.5**

---

### Property 6: Quiz Structure Completeness

*For any* valid Bedrock quiz response, the parsed Quiz object should contain, for every question: a non-empty question text, exactly four answer options, a correct answer that is one of the options, and a non-empty concept label.

**Validates: Requirements 3.2**

---

### Property 7: Quiz Question Count Invariant

*For any* requested question count N where 5 ≤ N ≤ 20, the generated Quiz should contain exactly N questions.

**Validates: Requirements 3.3**

---

### Property 8: Quiz Persistence

*For any* successfully generated Quiz, the Quiz object should be retrievable from the Session_Store under the student's session immediately after generation.

**Validates: Requirements 3.4**

---

### Property 9: Scoring Correctness

*For any* Quiz and any set of submitted answers, the per-concept score for each concept label should equal the ratio of correctly answered questions for that concept to the total questions for that concept, and the overall score should equal the ratio of all correct answers to all questions.

**Validates: Requirements 4.1, 4.2**

---

### Property 10: Quiz Result Persistence

*For any* successfully scored Quiz submission, the Quiz_Result should be retrievable from the Session_Store under the student's session immediately after scoring.

**Validates: Requirements 4.3**

---

### Property 11: Gap Detection Threshold

*For any* Quiz_Result, every concept label with a score strictly below 60% should appear in the student's Concept_Gaps in the Session_Store, and no concept label with a score of 60% or above should appear as a gap.

**Validates: Requirements 5.1, 5.2**

---

### Property 12: Gaps Included in Score Response

*For any* quiz submission response where the student has one or more recorded Concept_Gaps, the response payload should include a non-empty `gaps` field containing those concept labels.

**Validates: Requirements 5.3**

---

### Property 13: Gap Aggregation Uses Latest Score

*For any* concept label that appears in multiple Quiz_Results within the same session, the Concept_Gap record in the Session_Store should reflect the score from the most recently submitted Quiz_Result for that concept.

**Validates: Requirements 5.4**

---

### Property 14: Idempotent Session Creation

*For any* student identifier, calling the session upsert operation any number of times should result in exactly one Session record in the Session_Store — repeated calls must not create duplicate records.

**Validates: Requirements 7.1, 7.2**

---

### Property 15: Entity Scoping to Session

*For any* entity created by the system (material, quiz, result, gap, Q&A log, explanation log), its DynamoDB partition key should be `SESSION#{student_id}`, ensuring all data is scoped to the owning student's session.

**Validates: Requirements 7.3**

---

### Property 16: Session Summary Completeness

*For any* student session containing a known set of materials, quizzes, quiz results, concept gaps, and Q&A log entries, the session summary response should include all of those items — no entity should be silently omitted.

**Validates: Requirements 7.4**

---

## Error Handling

### HTTP Error Response Format

All Lambda functions return a consistent error envelope:

```json
{
  "error": "SHORT_CODE",
  "message": "Human-readable description of the error"
}
```

### Error Codes by Component

| Component | Condition | HTTP Status |
|-----------|-----------|-------------|
| Material Processor | File > 10 MB | 400 |
| Material Processor | Unsupported file type | 400 |
| Material Processor | Text extraction failure | 422 |
| Material Processor | Deserialization failure | 500 |
| QA Engine | Material not found | 404 |
| QA Engine | Bedrock error | 502 |
| Quiz Generator | Material not found | 404 |
| Quiz Generator | Malformed Bedrock response (after retry) | 502 |
| Gap Detector | Quiz not found | 404 |
| Gap Detector | Missing answer fields | 400 |
| Gap Detector | Session not found | 404 |
| Explanation Engine | Concept not in gaps | 404 |
| Explanation Engine | Bedrock error | 502 |
| Session Manager | Session not found | 404 |
| All | Missing student_id | 400 |

### Atomicity

- On extraction failure (Requirement 1.5): the Lambda must not write to DynamoDB if S3 write or text extraction fails. Use a try/except that only calls DynamoDB after both S3 and extraction succeed.
- On quiz generation failure: the quiz is only persisted after successful parsing. A failed parse attempt does not write a partial quiz.

### Bedrock Retry Policy

- Quiz Generator: retry once on `JSONDecodeError` or structural parse failure.
- QA Engine and Explanation Engine: no retry (single attempt, return 502 on failure).
- All Bedrock calls: use `boto3` default retry config (3 retries on throttling/transient errors).

---

## Testing Strategy

### Dual Testing Approach

Both unit tests and property-based tests are required. They are complementary:

- **Unit tests** cover specific examples, integration points, and error conditions (the edge cases identified in prework).
- **Property tests** verify universal correctness across randomly generated inputs, catching bugs that specific examples miss.

### Property-Based Testing

**Library**: [`hypothesis`](https://hypothesis.readthedocs.io/) (Python)

Each correctness property from the design document maps to exactly one `@given`-decorated Hypothesis test. Tests are configured to run a minimum of 100 examples.

**Tag format** (comment above each test):
```
# Feature: study-assistant, Property {N}: {property_text}
```

**Property test targets** (one test per property):

| Property | Test Description |
|----------|-----------------|
| P1 | Generate random student IDs and file content; verify S3 key prefix |
| P2 | Generate random document text; parse → serialize → deserialize; assert equivalence |
| P3 | Simulate extraction failure; assert no DynamoDB item written |
| P4 | Generate random material content and questions; mock Bedrock; assert prompt contains material |
| P5 | Generate random Q&A pairs; assert retrievable from mock DynamoDB after call |
| P6 | Generate random Bedrock quiz responses; assert all required fields present in parsed output |
| P7 | Generate N in [5,20]; assert quiz has exactly N questions |
| P8 | Generate random quizzes; assert retrievable from mock DynamoDB after generation |
| P9 | Generate random quizzes and answer sets; assert per-concept and overall scores match expected math |
| P10 | Generate random quiz submissions; assert result retrievable from mock DynamoDB |
| P11 | Generate random per-concept scores; assert gap list matches threshold predicate |
| P12 | Generate sessions with existing gaps; assert score response includes gaps field |
| P13 | Generate multiple quiz results for same concept; assert gap reflects latest score |
| P14 | Generate random student IDs; call upsert N times; assert exactly one session record |
| P15 | Generate any entity creation call; assert pk == SESSION#{student_id} |
| P16 | Generate sessions with known contents; assert summary response includes all items |

### Unit Tests

Unit tests focus on:
- Specific error conditions (400, 404, 422, 500, 502 responses)
- The retry-once behavior for malformed Bedrock quiz responses (Property 3.5 — verify Bedrock called exactly twice)
- Integration between `parser.py` serialization and DynamoDB storage
- Session upsert logic with mocked DynamoDB

### Test Configuration

```python
# conftest.py / settings
from hypothesis import settings

settings.register_profile("ci", max_examples=100)
settings.load_profile("ci")
```

Each property test file imports and uses this profile to ensure minimum 100 iterations in CI.

### Mocking Strategy

- DynamoDB: use `moto` library to mock AWS services in-process
- S3: use `moto` for S3 as well
- Bedrock: use `unittest.mock.patch` on `boto3` client since `moto` does not cover Bedrock Runtime
- All tests run without real AWS credentials

