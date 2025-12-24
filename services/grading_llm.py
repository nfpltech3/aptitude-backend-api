import requests
import json

def get_llm_grade(user_ans: str, reference_ans: str, max_marks: int) -> int:
    """Uses a local Ollama instance to semantically grade short answers."""
    prompt = f"""
    Compare the 'Student Answer' against the 'Reference Answer'.
    Reference Answer: {reference_ans}
    Student Answer: {user_ans}
    
    Grading Rules:
    1. If the meaning matches, mark it as Correct.
    2. Ignore minor spelling mistakes or typos (e.g., 'rahil' instead of 'rahul').
    3. Ignore case and punctuation.
    4. Provide the score as an integer between 0 and {max_marks}.
    
    Response format: {{"score": <integer>}}
    """
    
    try:
        # Assuming you have Ollama running locally
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:1b", 
                "prompt": prompt,
                "stream": False,
                "format": "json"
            },
            timeout=5
        )
        result = json.loads(response.json().get("response", "{}"))
        return int(result.get("score", 0))
    except Exception as e:
        print(f"LLM Grading Error: {e}")
        return 0