# grading_llm.py
import os
from groq import Groq
import json

# Initialize the Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_llm_grade(user_ans: str, reference_ans: str, max_marks: int) -> int:
    """Uses Groq Cloud to semantically grade short answers."""

    if not user_ans or str(user_ans).strip() == "" or str(user_ans).lower() == "none":
        return 0
    
    # Define a robust prompt for grading
    prompt = f"""
    You are grading a short-answer question using binary scoring.

    Reference Answer:
    {reference_ans}

    Student Answer:
    {user_ans}

    Grading Rules (STRICT):
    1. Decide whether the Student Answer is correct or incorrect overall.
    2. If the Student Answer is blank, meaningless, or irrelevant → score 0.
    3. Rounded or approximate numeric values are acceptable if reasonably close.
    4. Units may be ignored.
    5. Explanations are allowed, but the final conclusion must be correct.
    6. If the answer contains any incorrect or contradictory statement → score 0.
    7. Do not assume intent; judge only what is written.
    8. Be conservative: when in doubt, score 0.

    Output format (JSON only, no extra text):
    {{{{"score": 0}}}} or {{{{"score": 1}}}}
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
        return int(result.get("score", 0))
        
    except Exception as e:
        print(f"Groq LLM Grading Error: {e}")
        return 0