# Context & Architecture Guide

## Project Name & Purpose
**Candidate Aptitude Assessment Platform**
A robust, secure, and timed web-based testing platform for candidate evaluations. It administers General Aptitude and Departmental tests while tightly integrating with Zoho. The system is designed with strict anti-cheating mechanisms, dynamic question generation, auto-grading, and background data synchronization.

---

## Tech Stack
- **Backend Framework**: Python / FastAPI
- **Database**: PostgreSQL / SQLAlchemy ORM (falls back to SQLite for local development)
- **Frontend**: HTML5, Vanilla JS, and CSS within Jinja2 Templates (served directly by FastAPI)
- **Integrations**: 
  - **Zoho API**: For candidate allocation, question bank synchronization, and syncing test results.
  - **LLM APIs (Groq)**: Used for evaluating and grading descriptive/subjective answers automatically.
- **Deployment Platform**: Render

---

## Core Features
*   **Tokenized & Expiring Links**: Candidates receive a secure, unique URL payload with a token that expires 24 hours after generation.
*   **Dynamic Question Banking**: Fetches questions directly from Zoho, filtering by "General" or "Departmental", and randomizing them per session via caching.
*   **Strict Proctoring Mechanisms**: 
    *   **Device Fingerprinting**: Locks a candidate's session to the first accessed device to prevent test-taking across multiple screens.
    *   **Tab-Switch Detection**: Monitors document visibility. Emits a warning on tab exit and limits users to 3 warnings.
    *   **Privacy Curtain**: Blurs or blacks out the interface if the window loses focus to prevent screenshots.
*   **Auto-Save & Status Recovery**: Test answers are saved automatically per interaction (`/save-answer`) preventing data loss during network interruptions.
*   **Auto-Grading Engine**: 
    *   **Objective**: Standard logic matching MCQs accurately against predefined criteria.
    *   **Subjective**: AI-assisted grading modules to score descriptive textual inputs.
*   **Background Data Sync**: Uses FastAPI Background Tasks to seamlessly push test scores and candidate status updates back to Zoho without blocking the final request.

---

## User Roles & Permissions
1.  **Candidate (Frontend User)**
    *   Receives a unique URL token.
    *   Only authorized to access their specific generated test session.
    *   Interacts with the testing interface in strict adherence to proctoring rules.
2.  **Admin / HR (Zoho Ecosystem User)**
    *   Manages question repositories and sets up tests in Zoho.
    *   Triggers candidate allocation via Zoho workflows.
    *   Views synchronized candidate scores, proctoring violations, and completion statuses natively on Zoho.

---

## System Architecture / Data Flow
1.  **Allocation**: A candidate is assigned a test via Zoho. A webhook calls `/api/webhook/add-candidate`, generating a placeholder `TestSession` in our database.
2.  **Access Validation**: The candidate opens the unique URL. The `/api/check-token` endpoint checks token validity, ensures the 24-hour limit hasn't passed, and registers the device footprint.
3.  **Initialization**: 
    - The `/api/start-test` endpoint generates the frontend interface.
    - All relevant questions are fetched from Zoho, randomized, partitioned (General vs. Departmental), and saved as JSON directly into the session database (`question_cache` and `grading_cache`) to prevent network lag.
4.  **Test Execution**: The candidate progresses through questions. Their actions trigger the `/save-answer` endpoint, continuously persisting state. The frontend controls the countdown timer.
5.  **Submission & Evaluation**:
    - User manually submits via `/submit-test` or the timer expires triggering an Auto-Submit. 
    - The grading engines run immediately (`services/grading.py`).
6.  **Zoho Sync**: Upon score calculation, a FastAPI `BackgroundTasks` function pushes the aggregated score, violation tally, and answers to the Zoho registry (`services/zoho_sync.py`), ensuring a seamless experience.

---

## Environment Setup & Local Development (Placeholder)
*(To be completed: Outline `.env` variables, API key procurement, and virtual environment initialization steps)*

## Prerequisites (Placeholder)
*(To be completed: List required software versions like Python 3.10+, PostgreSQL, etc.)*

## Future Scope / Roadmap (Placeholder)
*(To be completed: Document upcoming features such as advanced AI proctoring, new question types, or refined Zoho CRM integration methods)*
