import streamlit as st
import json
import os
from datetime import datetime, timedelta
from openai import OpenAI
from duckduckgo_search import DDGS

# --- CONFIGURATION ---
# It's better to use st.secrets["NVIDIA_API_KEY"] on Streamlit Cloud
API_KEY = "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"
DB_FILE = "inventory.json"

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=API_KEY
)

# --- JSON DATABASE HELPERS ---
def load_inventory():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_inventory(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- TOOLS ---
def get_recipes(ingredients):
    with DDGS() as ddgs:
        query = f"simple recipes using {ingredients} no waste"
        results = ddgs.text(query, max_results=3)
        return "\n".join([f"- [{r['title']}]({r['href']})" for r in results])

# --- UI SETUP ---
st.set_page_config(page_title="HomeBase AI", layout="wide")
st.title("🏠 HomeBase AI: Butler")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar for Inventory Display
with st.sidebar:
    st.header("📦 Current Stock")
    items = load_inventory()
    if not items:
        st.info("Your cupboard is empty!")
    else:
        for i, entry in enumerate(items):
            st.write(f"**{entry['item']}**")
            st.caption(f"{entry['qty']} {entry['unit']} | Exp: {entry['expiry']}")
            if st.button(f"Remove {entry['item']}", key=f"del_{i}"):
                items.pop(i)
                save_inventory(items)
                st.rerun()
    
    st.divider()
    st.download_button("Download JSON Backup", json.dumps(items), "inventory.json")

# Chat Interface
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ex: 'I bought 2kg of rice, lasts 30 days'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Nemotron 4B Specific Instruction
    system_msg = """You are a JSON extractor. Convert user input into this EXACT format:
    {"action": "add", "item": "name", "qty": number, "unit": "kg/g/pcs", "days": number}
    OR
    {"action": "recipe"}
    Return ONLY the raw JSON block. No conversational text."""

    response = client.chat.completions.create(
        model="nvidia/nemotron-mini-4b-instruct",
        messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    try:
        raw_res = response.choices[0].message.content
        data = json.loads(raw_res)
        
        if data["action"] == "add":
            # Date Calculation
            expiry = (datetime.now() + timedelta(days=data.get("days", 7))).strftime("%Y-%m-%d")
            new_item = {
                "item": data["item"],
                "qty": data["qty"],
                "unit": data["unit"],
                "expiry": expiry
            }
            items.append(new_item)
            save_inventory(items)
            ans = f"✅ Logged {data['qty']} {data['unit']} of {data['item']}. It will expire on {expiry}."
            
        elif data["action"] == "recipe":
            ingreds = ", ".join([x["item"] for x in items])
            if not ingreds:
                ans = "Your inventory is empty! Add something first."
            else:
                ans = f"🍳 Found these for you:\n{get_recipes(ingreds)}"
        else:
            ans = "I'm not sure how to help with that yet."

    except Exception as e:
        ans = "Parsing error. Please try: 'Add [item], [qty], lasts [days] days'."

    with st.chat_message("assistant"):
        st.markdown(ans)
    st.session_state.messages.append({"role": "assistant", "content": ans})