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
    Compare the 'Student Answer' against the 'Reference Answer'.
    Reference Answer: {reference_ans}
    Student Answer: {user_ans}
    
    Grading Rules:
    1. If the meaning matches, mark it as Correct.
    2. Ignore minor spelling mistakes or typos (e.g., 'rahil' instead of 'rahul').
    3. Provide the score as an integer between 0 and {max_marks}.
    
    Response format: ONLY return a JSON object like {{"score": <integer>}}
    """
    
    try:
        # Generate chat completion
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
            model="llama-3.3-70b-versatile", # High-speed production model
            response_format={"type": "json_object"} # Force JSON mode
        )
        
        # Parse result
        result = json.loads(chat_completion.choices[0].message.content)
        return int(result.get("score", 0))
        
    except Exception as e:
        print(f"Groq LLM Grading Error: {e}")
        return 0