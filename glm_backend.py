import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from datetime import date

# ── Paste your Groq key here ──────────────────────────────────────────────────
GROQ_API_KEY = "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"
client = Groq(api_key=GROQ_API_KEY)

app = FastAPI(title="InvenIQ Backend", version="3.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    messages: list
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.1
    max_tokens: int = 1024

MASTER_PROMPT = """You are InvenIQ, an inventory AI for Malaysian SME retail stores. Today is {today}.

RULES:
1. NEVER invent product names, brands, or numbers not in the CSV data.
2. If no CSV is uploaded, set direct_answer to "Please upload your inventory CSV first so I can give you accurate numbers." and set all other fields to "N/A".
3. Use ONLY exact product names/IDs from the CSV data provided.
4. Respond with ONLY a valid JSON object. No markdown, no code fences, no extra text.
5. Be concise - max 2 short sentences per field.

RESPONSE FORMAT:
{"direct_answer":"your answer","metrics":[{"label":"Metric","value":"X units","status":"green"}],"forecast":{"next_week":"X units","next_month":"X units","trend":"rising","confidence":"high","reasoning":"short reason"},"action":{"type":"reorder","title":"Action Title","what":"specific items","when":"timeframe","why":"reason"},"factors":[{"label":"Factor","direction":"pos","note":"note"}],"summary":"Two sentence summary for a shop owner."}

Status options: green, amber, red, blue
Action type options: reorder, discount, monitor, none"""


@app.post("/chat")
def chat(req: ChatRequest):
    try:
        print(f"=== INCOMING MESSAGES ===")
        for i, msg in enumerate(req.messages):
            print(f"[{i}] role={msg['role']} | content_length={len(str(msg.get('content','')))} | preview={str(msg.get('content',''))[:100]}")
        print(f"=========================")

        today_str = date.today().strftime("%A, %d %B %Y")
        csv_context = ""
        chat_messages = []

        for msg in req.messages:
            if msg["role"] == "system":
                csv_context = msg["content"][:2000]
            else:
                chat_messages.append(msg)

        chat_messages = chat_messages[-6:]

        system = MASTER_PROMPT.replace("{today}", today_str)
        if csv_context:
            system += f"\n\nUSER'S INVENTORY DATA:\n{csv_context}"
        else:
            system += "\n\nNo CSV uploaded yet. Tell the user to upload their CSV."

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                *chat_messages,
            ],
            temperature=0.1,
            max_tokens=900,
        )

        raw = response.choices[0].message.content or ""
        print(f"=== GROQ RAW OUTPUT ===")
        print(repr(raw))
        print(f"======================")

        raw = raw.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        start = raw.find("{")
        end   = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end+1]

        return {
            "content": raw,
            "model": response.model,
            "usage": {
                "input_tokens":  response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            },
        }

    except Exception as e:
        import traceback
        print(f"FULL ERROR:")
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/health")
def health():
    return {"status": "online", "model": "llama-3.3-70b-versatile", "provider": "Groq (free)"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)