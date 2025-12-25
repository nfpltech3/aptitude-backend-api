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
    You are grading an objective aptitude exam answer.

    STRICT RULES (DO NOT VIOLATE):
    - The question has ONE objectively correct answer.
    - Focus on the FINAL ANSWER or CONCLUSION.
    - Ignore spelling mistakes, unit formatting, or minor language differences.
    - Accept answers written in English, Marathi, or mixed language.
    - Accept numerically equivalent answers (e.g., 12, ₹12, 12 rupees).
    - Do NOT award marks for correct method if final answer is wrong.
    - Do NOT guess intent.
    - If the final answer is missing, unclear, or incorrect → score 0.
    - Be strict like a competitive exam evaluator.

    Reference Answer (Correct Final Answer):
    {reference_ans}

    Student Answer:
    {user_ans}

    Task:
    Check whether the student's final answer is correct.

    Scoring:
    - Give FULL marks ({max_marks}) ONLY if the final answer is correct.
    - Otherwise give 0.

    Return ONLY a JSON object in this exact format:
    {{"score": <integer>}}
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