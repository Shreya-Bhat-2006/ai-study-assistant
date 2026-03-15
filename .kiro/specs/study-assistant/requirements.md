# Requirements Document

## Introduction

The Adaptive Concept Gap Detector & AI Study Assistant is a serverless backend system that helps students studying technical subjects identify and address gaps in their understanding. Students upload study materials (PDFs, text documents), ask questions, take AI-generated quizzes, and receive targeted explanations for concepts they struggle with. The system uses Amazon Bedrock for AI inference, S3 for material storage, DynamoDB for session and progress tracking, Lambda for compute, and API Gateway for HTTP access.

## Glossary

- **Study_Assistant**: The overall backend system described in this document
- **Material_Processor**: The Lambda function responsible for ingesting and indexing uploaded study materials
- **QA_Engine**: The Lambda function responsible for answering student questions using Bedrock
- **Quiz_Generator**: The Lambda function responsible for generating quizzes from study materials
- **Gap_Detector**: The Lambda function responsible for analyzing quiz results and identifying concept gaps
- **Explanation_Engine**: The Lambda function responsible for generating targeted explanations for weak concepts
- **Student**: An end user of the system who uploads materials and interacts with the assistant
- **Study_Material**: A document (PDF or plain text) uploaded by a Student containing subject matter content
- **Quiz**: A set of questions generated from a Study_Material to assess Student understanding
- **Quiz_Result**: A record of a Student's answers to a Quiz, including scores per concept
- **Concept_Gap**: A concept identified as poorly understood based on Quiz_Result analysis
- **Session**: A DynamoDB record tracking a Student's interactions, quiz history, and identified Concept_Gaps
- **Bedrock_Client**: The AWS SDK component used to invoke Amazon Bedrock foundation models
- **Material_Store**: The S3 bucket used to store uploaded Study_Materials
- **Session_Store**: The DynamoDB table used to persist Session records

---

## Requirements

### Requirement 1: Study Material Upload

**User Story:** As a Student, I want to upload study materials, so that the system can analyze them and use them as the basis for questions and quizzes.

#### Acceptance Criteria

1. WHEN a Student submits a Study_Material via the upload endpoint, THE Material_Processor SHALL store the file in the Material_Store under a key scoped to the Student's identifier.
2. WHEN a Study_Material is stored, THE Material_Processor SHALL extract text content and store a parsed representation in the Session_Store for later retrieval.
3. IF a submitted file exceeds 10 MB, THEN THE Material_Processor SHALL return an HTTP 400 response with a descriptive error message.
4. IF a submitted file is not a PDF or plain text format, THEN THE Material_Processor SHALL return an HTTP 400 response indicating the unsupported file type.
5. WHEN text extraction from a Study_Material fails, THE Material_Processor SHALL return an HTTP 422 response with a descriptive error message and SHALL NOT store a partial record.

---

### Requirement 2: AI Question Answering

**User Story:** As a Student, I want to ask questions about my uploaded study materials, so that I can get accurate, context-grounded answers without leaving the study workflow.

#### Acceptance Criteria

1. WHEN a Student submits a question referencing a Study_Material, THE QA_Engine SHALL retrieve the parsed material content from the Session_Store and pass it as context to the Bedrock_Client.
2. WHEN the Bedrock_Client returns a response, THE QA_Engine SHALL return the answer to the Student within 30 seconds.
3. IF the referenced Study_Material does not exist in the Session_Store, THEN THE QA_Engine SHALL return an HTTP 404 response with a descriptive error message.
4. IF the Bedrock_Client returns an error, THEN THE QA_Engine SHALL return an HTTP 502 response with a descriptive error message.
5. THE QA_Engine SHALL log each question and answer pair to the Session_Store associated with the Student's Session.

---

### Requirement 3: Quiz Generation

**User Story:** As a Student, I want the system to generate quizzes from my study materials, so that I can test my understanding across the key concepts covered.

#### Acceptance Criteria

1. WHEN a Student requests a quiz for a Study_Material, THE Quiz_Generator SHALL invoke the Bedrock_Client with the parsed material content and a prompt requesting multiple-choice questions covering distinct concepts.
2. WHEN the Bedrock_Client returns quiz content, THE Quiz_Generator SHALL parse the response into a structured Quiz object containing questions, answer options, correct answers, and associated concept labels.
3. THE Quiz_Generator SHALL generate between 5 and 20 questions per quiz request, with the count configurable via the request payload.
4. WHEN a Quiz is generated, THE Quiz_Generator SHALL persist the Quiz to the Session_Store linked to the Student's Session.
5. IF the Bedrock_Client returns malformed quiz content that cannot be parsed, THEN THE Quiz_Generator SHALL retry the Bedrock_Client invocation once before returning an HTTP 502 response.
6. IF the referenced Study_Material does not exist, THEN THE Quiz_Generator SHALL return an HTTP 404 response with a descriptive error message.

---

### Requirement 4: Quiz Submission and Scoring

**User Story:** As a Student, I want to submit my quiz answers and receive a score, so that I know how well I understood the material.

#### Acceptance Criteria

1. WHEN a Student submits answers for a Quiz, THE Gap_Detector SHALL compare each answer against the correct answer stored in the Session_Store and compute a score per concept label.
2. WHEN scoring is complete, THE Gap_Detector SHALL return the overall score as a percentage and a per-concept breakdown to the Student.
3. THE Gap_Detector SHALL persist the Quiz_Result to the Session_Store linked to the Student's Session.
4. IF a submitted Quiz identifier does not exist in the Session_Store, THEN THE Gap_Detector SHALL return an HTTP 404 response with a descriptive error message.
5. IF the submitted answer payload is missing required fields, THEN THE Gap_Detector SHALL return an HTTP 400 response listing the missing fields.

---

### Requirement 5: Concept Gap Detection

**User Story:** As a Student, I want the system to identify which concepts I struggle with, so that I can focus my study time effectively.

#### Acceptance Criteria

1. WHEN a Quiz_Result is persisted, THE Gap_Detector SHALL identify all concept labels where the Student's score is below 60% and record them as Concept_Gaps in the Session_Store.
2. WHEN a Student requests their current Concept_Gaps, THE Gap_Detector SHALL return the list of Concept_Gaps from the Session_Store for the Student's Session.
3. WHILE a Student has one or more Concept_Gaps recorded, THE Gap_Detector SHALL include the Concept_Gap list in every quiz score response.
4. THE Gap_Detector SHALL aggregate Concept_Gaps across multiple Quiz_Results within the same Session, updating gap severity based on the most recent score for each concept label.
5. IF a Student's Session does not exist, THEN THE Gap_Detector SHALL return an HTTP 404 response with a descriptive error message.

---

### Requirement 6: Targeted Explanations for Weak Concepts

**User Story:** As a Student, I want to receive focused explanations for concepts I struggle with, so that I can improve my understanding efficiently.

#### Acceptance Criteria

1. WHEN a Student requests an explanation for a Concept_Gap, THE Explanation_Engine SHALL retrieve the relevant Study_Material content and the Concept_Gap label from the Session_Store and pass both as context to the Bedrock_Client.
2. WHEN the Bedrock_Client returns an explanation, THE Explanation_Engine SHALL return the explanation to the Student within 30 seconds.
3. IF the requested concept label is not present in the Student's Concept_Gaps, THEN THE Explanation_Engine SHALL return an HTTP 404 response with a descriptive error message.
4. IF the Bedrock_Client returns an error, THEN THE Explanation_Engine SHALL return an HTTP 502 response with a descriptive error message.
5. WHEN an explanation is returned, THE Explanation_Engine SHALL log the explanation to the Session_Store so the Student can retrieve it later.

---

### Requirement 7: Session Management

**User Story:** As a Student, I want my study progress to be tracked across interactions, so that I can resume where I left off and review my history.

#### Acceptance Criteria

1. WHEN a Student makes their first request, THE Study_Assistant SHALL create a Session record in the Session_Store identified by the Student's identifier.
2. WHEN a Session already exists for a Student, THE Study_Assistant SHALL reuse the existing Session rather than creating a duplicate.
3. THE Study_Assistant SHALL associate all Study_Materials, Quizzes, Quiz_Results, Concept_Gaps, and Q&A logs with the Student's Session.
4. WHEN a Student requests their Session summary, THE Study_Assistant SHALL return the list of uploaded materials, quiz history, current Concept_Gaps, and Q&A log from the Session_Store.
5. IF a Student identifier is absent from a request, THEN THE Study_Assistant SHALL return an HTTP 400 response with a descriptive error message.

---

### Requirement 8: Material Parser Round-Trip Integrity

**User Story:** As a developer, I want parsed material representations to be stable and reversible, so that re-parsing stored content produces equivalent results and bugs in parsing are caught early.

#### Acceptance Criteria

1. THE Material_Processor SHALL serialize parsed Study_Material content to a JSON representation before storing it in the Session_Store.
2. THE Material_Processor SHALL deserialize the JSON representation back into an equivalent in-memory structure when retrieving material content.
3. FOR ALL valid Study_Material documents, parsing then serializing then deserializing SHALL produce a structure equivalent to the original parsed representation (round-trip property).
4. WHEN a stored JSON representation cannot be deserialized, THE Material_Processor SHALL return an HTTP 500 response with a descriptive error message and SHALL log the failure.
