# Adaptive Concept Gap Detector & AI Study Assistant

## Overview

The Adaptive Concept Gap Detector is an AI-powered study assistant designed to help students identify and fix gaps in their understanding of technical subjects.

Students often struggle to determine which specific concepts they do not fully understand. Most learning platforms provide generic explanations rather than diagnosing individual knowledge gaps.

Our system analyzes uploaded study materials, answers questions based on those materials, generates quizzes, and detects weak concepts. It then provides targeted explanations to help students strengthen their understanding.

---

# Problem

Students studying technical subjects often struggle to identify which concepts they do not fully understand.

Existing learning platforms typically provide:

- General explanations
- Static study materials
- No personalized feedback on weak concepts

As a result, students may repeatedly study topics inefficiently without realizing their knowledge gaps.

---

# Solution

We developed an AI-powered study assistant that:

- Analyzes uploaded study materials
- Answers questions from those materials
- Generates quizzes automatically
- Detects concept gaps based on quiz performance
- Provides targeted explanations for weak concepts

This creates a personalized learning experience and helps students focus on concepts they truly need to improve.

---

# Core Features

## 1. Upload Study Materials

Students can upload learning resources such as:

- PDF notes
- textbooks
- lecture slides

These files are stored in Amazon S3 and processed for analysis.

---

## 2. AI Question Answering

Students can ask questions about the uploaded material.

Example:

"Explain recursion."

The system retrieves relevant content and uses AI to generate an explanation.

---

## 3. Quiz Generation

The AI automatically generates quizzes from the uploaded material to test understanding.

Example question:

"What is the time complexity of quicksort?"

---

## 4. Concept Gap Detection

The system analyzes quiz results to detect weak areas.

Example output:

Concept gaps detected:

- Recursion
- Divide and Conquer

---

## 5. AI Mini Tutor

After identifying weak concepts, the system provides simplified explanations and additional learning guidance.

---

# System Architecture

High-level architecture:

Student

↓

Frontend Web Application

↓

API Gateway

↓

AWS Lambda (Backend Logic)

↓

Amazon Bedrock (AI Processing)

↓

Amazon S3 (Study Material Storage)

↓

Amazon DynamoDB (Quiz Results & Concept Tracking)

---

# AWS Services Used

| Service | Purpose |
| --- | --- |
| Amazon S3 | Store uploaded study materials |
| AWS Lambda | Backend processing |
| Amazon Bedrock | AI model for answering questions and generating quizzes |
| Amazon DynamoDB | Store quiz results and concept gaps |
| API Gateway | Connect frontend to backend |

---

# Kiro Spec-Driven Development

This project was developed using **Kiro's spec-driven development workflow**.

The repository includes the `.kiro/specs` folder containing the project specification used to generate requirements and technical design.

---

# Project Structure

```
ai-study-assistant
│
├── .kiro
│   └── specs
│       └── study-assistant-spec.md
│
├── requirements.md
├── design.md
│
├── backend
├── frontend
│
├── architecture
│   └── architecture-diagram.png
│
└── README.md
```

---

# How the System Works

1. Student uploads study material (PDF)
2. File is stored in Amazon S3
3. Student asks a question
4. The system retrieves relevant content
5. Amazon Bedrock generates an answer
6. The system generates quizzes
7. Student answers quiz questions
8. Weak concepts are detected
9. AI explains the weak topics

---

# Demo Flow

1. Upload study material
2. Ask questions about the content
3. Generate quiz
4. Answer quiz
5. View detected concept gaps

---

# Technologies Used

- Python
- Amazon Web Services (AWS)
- Amazon Bedrock
- AWS Lambda
- Amazon S3
- DynamoDB
- API Gateway
- Kiro IDE

---

# Future Improvements

- Personalized learning plans
- Progress tracking dashboard
- Integration with LMS platforms
- Visual concept explanations

---

