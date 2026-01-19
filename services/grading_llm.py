# grading_llm.py
import os
from groq import Groq
import json

# Initialize the Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_llm_grade(user_ans: str, reference_ans: str, max_marks: int) -> dict:
    """Uses Groq Cloud to semantically grade short answers."""

    if not user_ans or str(user_ans).strip() == "" or str(user_ans).lower() == "none":
        return {"score": 0, "reason": "No answer provided by the candidate."}
    
    # Define a robust prompt for grading
    prompt = f"""
    Evaluate the Student Answer against the Reference Answer.

    Reference Answer:
    {reference_ans}

    Student Answer:
    {user_ans}

    Grading Rules (BINARY – 0 or 1 ONLY):
    1. Give full marks ({max_marks}) if the core meaning or numeric value is correct.
    2. Ignore extra characters or units (e.g., '1125p', '1125 pages', '1125').
    3. Treat singular and plural forms as equivalent (e.g., 'letter' and 'letters').
    4. Accept rounded or approximate numeric values if reasonably close.
    5. Ignore minor typos or formatting issues (e.g., '0..11' ≈ '0.11').
    6. Give 0 only if the answer is logically wrong, irrelevant, contradictory, or blank.
    7. Judge correctness by meaning, not exact text match.

    Provide a brief 1-sentence explanation for the score.
    Output format (JSON only, no extra text):
    Format: {{"score": <int>, "reason": "<string>"}}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an automated grading assistant that only outputs JSON."
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        
        # Parse result
        result = json.loads(chat_completion.choices[0].message.content)
        return {
            "score": int(result.get("score", 0)),
            "reason": result.get("reason", "No reason provided")
        }
        
    except Exception as e:
        return {"score": 0, "reason": f"LLM Grading Error: {str(e)}"}
