import os
import asyncio
from groq import AsyncGroq
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Initialize the async Groq client
# It will automatically look for the GROQ_API_KEY in your environment
try:
    client = AsyncGroq()
    print("Groq Cloud LLM Interface initialized successfully.")
except Exception as e:
    print(f"Error initializing Groq client: {e}")
    client = None

async def async_generate_llm_response(user_text: str, conversation_history: list) -> str:
    """
    Ultra-low latency conversational AI using Groq's cloud-hosted Llama 3.
    """
    if not client:
        return "I am experiencing a cloud connection issue. Please hold on."

    # 1. System Prompt: Force the LLM to act like a concise voice agent
    messages = [
        {
            "role": "system", 
            "content": (
                "You are Call-E, an incredibly helpful, human-like customer support voice assistant. "
                "CRITICAL RULES: "
                "1. Keep responses strictly under 2 short sentences. "
                "2. NEVER use emojis, markdown, asterisks, or numbered lists (this will be spoken out loud). "
                "3. Be direct, polite, and conversational. "
                "4. If the user is angry, apologize briefly and say you can transfer them to a human."
            )
        }
    ]
    
    # 2. Context Injection: Feed the last 4 turns to maintain memory
    for msg in conversation_history[-4:]:
        role = "assistant" if msg["role"] == "bot" else "user"
        if "text" in msg:
            messages.append({"role": role, "content": msg["text"]})
            
    # 3. Append the newest live input
    messages.append({"role": "user", "content": user_text})

    try:
        print("   [🧠 Cloud LLM is thinking...]")
        # Execute the async call to Groq using the Llama 3 8B model
        chat_completion = await client.chat.completions.create(
            messages=messages,
            model="llama3-8b-8192",
            temperature=0.5, # Keep it relatively deterministic and focused
            max_tokens=60,   # Force short responses
        )
        
        reply = chat_completion.choices[0].message.content.strip()
        
        return reply if reply else "I didn't quite catch that. Could you repeat?"

    except Exception as e:
        print(f"[LLM Execution Error]: {e}")
        return "I am experiencing a slight system delay. Please bear with me."