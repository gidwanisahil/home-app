import streamlit as st
import json
import os
from datetime import datetime, timedelta
from openai import OpenAI
from duckduckgo_search import DDGS

# --- CONFIGURATION ---
# Safely handle API Key from Secrets or Fallback
try:
    API_KEY = st.secrets["NVIDIA_API_KEY"]
except Exception:
    # Fallback for local environment if secrets.toml is missing
    API_KEY = "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"

DB_FILE = "inventory.json"

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=API_KEY
)

# --- DATABASE HELPERS ---
def load_inventory():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_inventory(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_recipes(ingredients):
    try:
        with DDGS() as ddgs:
            query = f"simple recipes using {ingredients} no waste"
            results = ddgs.text(query, max_results=3)
            if not results: return "No recipes found."
            return "\n".join([f"- [{r['title']}]({r['href']})" for r in results])
    except Exception as e:
        return f"Search error: {str(e)}"

# --- UI SETUP ---
st.set_page_config(page_title="HomeBase AI", layout="wide", page_icon="🏠")
st.title("🏠 HomeBase AI: Butler")

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- SIDEBAR: INVENTORY ---
with st.sidebar:
    st.header("📦 Inventory Management")
    
    uploaded_file = st.file_uploader("Restore from Backup", type="json")
    if uploaded_file:
        save_inventory(json.load(uploaded_file))
        st.success("Data Restored!")
        st.rerun()

    st.divider()

    items = load_inventory()
    if not items:
        st.info("Your cupboard is empty!")
    else:
        for i, entry in enumerate(items):
            cols = st.columns([3, 1])
            cols[0].write(f"**{entry['item']}** ({entry['qty']}{entry['unit']})")
            cols[0].caption(f"Expires: {entry['expiry']}")
            if cols[1].button("❌", key=f"del_{i}"):
                items.pop(i)
                save_inventory(items)
                st.rerun()
    
    st.divider()
    
    st.download_button(
        label="💾 Download Backup",
        data=json.dumps(items, indent=4),
        file_name=f"inventory_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json"
    )

# --- CHAT INTERFACE ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ex: 'I bought 2kg of rice, lasts 30 days'"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Improved System Prompt for Nemotron-Mini-4B
    system_msg = """You are a JSON extraction engine.
    Convert user input into JSON. 
    Examples:
    1. "Bought 1kg apples, expires in 5 days" -> {"action": "add", "item": "apples", "qty": 1, "unit": "kg", "days": 5}
    2. "What can I cook?" -> {"action": "recipe"}
    
    Rules: Return ONLY raw JSON. No conversational text."""

    try:
        response = client.chat.completions.create(
            model="nvidia/nemotron-mini-4b-instruct",
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        raw_res = response.choices[0].message.content.strip()
        # Clean potential markdown backticks from LLM response
        if "```json" in raw_res:
            raw_res = raw_res.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_res:
            raw_res = raw_res.split("```")[1].split("```")[0].strip()
            
        data = json.loads(raw_res)
        
        if data.get("action") == "add":
            days = data.get("days", 7)
            expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            new_item = {
                "item": data.get("item", "Unknown"),
                "qty": data.get("qty", 0),
                "unit": data.get("unit", "pcs"),
                "expiry": expiry
            }
            current_items = load_inventory()
            current_items.append(new_item)
            save_inventory(current_items)
            ans = f"✅ Logged {new_item['qty']} {new_item['unit']} of {new_item['item']}. Expiry: {expiry}"
            
        elif data.get("action") == "recipe":
            current_items = load_inventory()
            ingreds = ", ".join([x["item"] for x in current_items])
            if not ingreds:
                ans = "Your inventory is empty! Add items before asking for recipes."
            else:
                ans = f"🍳 **Recipe Ideas:**\n{get_recipes(ingreds)}"
        else:
            ans = "I understood the request but don't have an action for it yet."

    except Exception as e:
        ans = f"I had trouble processing that. Please try: 'Add [item], [qty], lasts [days] days'."

    with st.chat_message("assistant"):
        st.markdown(ans)
    st.session_state.messages.append({"role": "assistant", "content": ans})