import ollama


# ---------------------------------------------------------
# Ollama model
# ---------------------------------------------------------


MODEL_NAME = MODEL= "gemma4:e4b"
MODEL_PROVIDER = "ollama"
OLLAMA_HOST = "http://localhost:11434"
# ---------------------------------------------------------
# Chat function
# Used by agent.py for tool/function calling
# ---------------------------------------------------------

def chat(messages, tools=None):

    response = ollama.chat(
        model=MODEL,
        messages=messages,
        tools=tools
    )

    return response


# ---------------------------------------------------------
# Generate function
# Used by planner.py and reflector.py
# ---------------------------------------------------------

def generate(prompt):

    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response["message"]["content"]