import streamlit as st
import requests

st.set_page_config(page_title="Chat IA", layout="wide", initial_sidebar_state="expanded")

# ===== CSS (CLEAN + FIXED) =====
st.markdown("""
<style>

/* ===== Base ===== */
html, body, .stApp {
    background: #515151;
    color: #f5f5f5;   /* FIX: readable on dark bg */
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* ===== Main Container ===== */
.block-container {
    max-width: 900px;
    margin: auto;
    padding-bottom: 120px;
}

/* ===== Chat Messages ===== */
[data-testid="stChatMessage"] {
    margin: 12px 0;
    padding: 14px 18px;
    border-radius: 14px;
    background: #000000;
    border: 1px solid #444;
    color: #f5f5f5;
}

[data-testid="stChatMessage"][data-testid*="user"] {
    background: #e8f0fe;
    color: #111;
}

/* ===== Chat Input (FIXED) ===== */
.stChatInput {
    position: center;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    width: 100%;
    max-width: 800px;
    background: #2f2f2f;   
    border: 1px solid #666;
    border-radius: 24px;
    padding: 8px 12px;
    z-index: 999;
}

/* Input text visibility */
.stChatInput textarea {
    background: transparent !important;
    color: #ffffff !important;   /* FIX: readable typing */
    caret-color: #ffffff !important;
    border: none !important;
    outline: none !important;
}

/* Placeholder */
.stChatInput textarea::placeholder {
    color: #cfcfcf !important;
}

/* ===== Buttons ===== */
.stButton > button {
    background: #515151;
    color: white;
    border-radius: 8px;
    border: none;
}

/* ===== Sidebar ===== */
[data-testid="stSidebar"] {
    background: #111111;
    border-right: 1px solid #333;
    color: #f5f5f5;
}

[data-testid="stSidebar"] * {
    color: #f5f5f5 !important;
}

</style>
""", unsafe_allow_html=True)

API_BASE_URL = "http://localhost:8000/api/v1"

# ===== Session State =====
if "session_id" not in st.session_state:
    st.session_state.session_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# ===== Functions =====
def load_history(sid):
    resp = requests.get(f"{API_BASE_URL}/sessions/{sid}")
    if resp.status_code == 200:
        data = resp.json()
        st.session_state.messages = [
            {"role": m["role"], "content": m["content"]}
            for m in data["messages"]
        ]
        st.session_state.session_id = sid

def create_new_chat():
    resp = requests.post(f"{API_BASE_URL}/sessions", json={"title": "Nouveau Chat"})
    if resp.status_code == 201:
        st.session_state.session_id = resp.json()["id"]
        st.session_state.messages = []
        st.rerun()

# ===== Sidebar =====
with st.sidebar:
    st.title("Chat IA")

    if st.button("+ Nouveau Chat", use_container_width=True):
        create_new_chat()

    st.divider()
    st.subheader("Historique")

    try:
        history_resp = requests.get(f"{API_BASE_URL}/sessions")
        if history_resp.status_code == 200:
            for session in history_resp.json():
                title = session["title"] or "Chat sans titre"
                if st.button(f"{title[:25]}...", key=session["id"], use_container_width=True):
                    load_history(session["id"])
                    st.rerun()
    except Exception:
        st.error("Impossible de charger l'historique.")

# ===== CHAT WRAPPER START =====
st.markdown('<div class="chat-wrapper">', unsafe_allow_html=True)

if not st.session_state.session_id:
    st.markdown("""
    <div style="
        background:#e8f0fe;
        padding:16px;
        border-radius:12px;
        text-align:center;
        color:#1a73e8;
        font-weight:500;
    ">
    Commencez un nouveau chat pour débuter.
    </div>
    """, unsafe_allow_html=True)
else:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

st.markdown('</div>', unsafe_allow_html=True)
# ===== CHAT WRAPPER END =====

# ===== INPUT + FILE ATTACH =====
input_col, attach_col = st.columns([0.8, 0.2])

with attach_col:
    if st.session_state.session_id:
        with st.popover("Charger 🔗"):
            st.markdown("### Joindre des documents")
            uploaded_files = st.file_uploader(
                "Télécharger PDF, CSV ou Excel",
                type=["pdf", "csv", "xlsx"],
                accept_multiple_files=True,
                label_visibility="collapsed"
            )

            if uploaded_files and st.button("Traiter les fichiers"):
                files_to_send = [
                    ("files", (f.name, f.getvalue(), f.type))
                    for f in uploaded_files
                ]
                try:
                    with st.spinner("Traitement en cours..."):
                        response = requests.post(
                            f"{API_BASE_URL}/upload/{st.session_state.session_id}",
                            files=files_to_send
                        )
                    if response.status_code == 200:
                        st.success(f"{len(uploaded_files)} fichiers joints.")
                    else:
                        st.error("Erreur de téléchargement.")
                except Exception as e:
                    st.error(f"Error: {e}")

# ===== CHAT INPUT =====
if prompt := st.chat_input("Ex: 'Remplir les valeurs manquantes dans mon Excel'"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        response_placeholder.markdown("*Réflexion en cours...*")

        try:
            payload = {
                "message": prompt,
                "session_id": st.session_state.session_id
            }

            resp = requests.post(f"{API_BASE_URL}/chat", json=payload)

            if resp.status_code == 200:
                data = resp.json()
                ai_content = data["message"]["content"]

                response_placeholder.markdown(ai_content)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": ai_content
                })

                st.rerun()
            else:
                response_placeholder.error(f"Erreur de l'agent: {resp.status_code}")

        except Exception as e:
            st.error(f"Erreur de communication: {e}")

# ===== RESULTS =====
if st.session_state.session_id:
    list_resp = requests.get(f"{API_BASE_URL}/list/{st.session_state.session_id}")

    if list_resp.status_code == 200:
        all_files = list_resp.json().get("files", [])
        # Filter for updated files and remove UI duplicates using a set
        updated_files = sorted(list(set(f for f in all_files if f.startswith('updated_'))))

        if updated_files:
            st.divider()
            st.write("### Résultats mis à jour")

            for f in updated_files:
                c1, c2 = st.columns([0.8, 0.2])
                c1.success(f"{f}")

                download_url = f"{API_BASE_URL}/download/{st.session_state.session_id}/{f}"

                try:
                    file_content = requests.get(download_url).content
                    c2.download_button("Télécharger", data=file_content, file_name=f, key=f"dl_{f}")
                except Exception:
                    c2.error("Erreur")
