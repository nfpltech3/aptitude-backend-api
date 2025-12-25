import os
import json
from groq import Groq
from dotenv import load_dotenv

# Load local .env file
load_dotenv()

def test_grading_logic():
    # 1. Initialize Client
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("❌ Error: GROQ_API_KEY not found in .env file.")
        return

    client = Groq(api_key=api_key)
    
    # 2. Mock Data for Testing
    reference_ans = "Rahul"
    student_ans = "Rahil"  # Intentional typo
    max_marks = 1

    print(f"Testing Groq with student answer: '{student_ans}'...")

    prompt = f"""
    Grade this Student Answer against the Reference Answer.
    Reference: {reference_ans}
    Student: {student_ans}
    
    Rules:
    - Ignore typos (e.g., 'parris' instead of 'paris').
    - Award full marks ({max_marks}) if the meaning is correct.
    - Respond ONLY in JSON: {{"score": <int>}}
    """

    try:
        # 3. Call Groq Cloud
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        # 4. Parse and Verify Response
        response_content = completion.choices[0].message.content
        result = json.loads(response_content)
        score = result.get("score")

        print(f"✅ Success! Groq returned score: {score}/{max_marks}")
        print(f"Full Response JSON: {response_content}")

    except Exception as e:
        print(f"❌ Test Failed: {e}")

if __name__ == "__main__":
    test_grading_logic()