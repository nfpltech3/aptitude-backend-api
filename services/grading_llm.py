# grading_llm.py
import os
from groq import Groq
import json

# Initialize the Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_llm_grade(user_ans: str, reference_ans: str, max_marks: int) -> int:
    """Uses Groq Cloud to semantically grade short answers."""

    if not user_ans or str(user_ans).strip() == "" or str(user_ans).lower() == "none":
        print("Empty answer detected. Skipping LLM and awarding 0 marks.")
        return 0
    
    # Define a robust prompt for grading
    prompt = f"""
    Compare 'Student Answer' against 'Reference Answer'.
    Reference: {reference_ans}
    Student: {user_ans}
    
    Rules:
    - If the Student Answer is blank or irrelevant, the score must be 0.
    - Ignore minor typos and case (e.g., 'Tinaa' = 'Tina').
    - Focus on intent and meaning, not perfect spelling.
    
    Score: 0 to {max_marks}.
    Format: {{"score": <integer>}}
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