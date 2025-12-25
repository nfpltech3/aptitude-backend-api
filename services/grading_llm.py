# grading_llm.py
import os
from groq import Groq
import json

# Initialize the Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def get_llm_grade(user_ans: str, reference_ans: str, max_marks: int) -> int:
    """Uses Groq Cloud to semantically grade short answers."""
    
    # Define a robust prompt for grading
    prompt = f"""
    Compare 'Student Answer' against 'Reference Answer'.
    Reference: {reference_ans}
    Student: {user_ans}
    
    Rules:
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