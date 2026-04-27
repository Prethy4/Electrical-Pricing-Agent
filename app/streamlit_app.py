import streamlit as st
import requests

st.set_page_config(page_title="Chat IA", layout="wide", initial_sidebar_state="expanded")

# ===== CSS (CLEAN + FIXED) =====
st.markdown("""
<style>

/* ===== Base ===== */
html, body, .stApp {
    background: #0f172a;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* ===== Footer / Bottom strip ===== */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"],
.stBottom,
div[class*="bottom"],
div[style*="position: fixed"][style*="bottom"] {
    background: transparent !important;
    background-color: transparent !important;
}

/* ===== Main Container ===== */
.block-container {
    max-width: 900px;
    margin: auto;
    padding-bottom: 150px;
}

/* ===== Chat Messages ===== */
[data-testid="stChatMessage"] {
    margin: 12px 0;
    padding: 14px 18px;
    border-radius: 14px;
    background: #1e293b;
    border: 1px solid #334155;
    color: #e2e8f0;
    word-wrap: break-word; /* Ensure long words break */
}

[data-testid="stChatMessage"][data-testid*="user"] {
    background: #1d4ed8;
    color: #0b132b;
}

/* Adjust chat input width to make space for the upload button */
[data-testid="stChatInputContainer"] {
    margin-left: 100px !important;
}

/* Input text visibility */
.stChatInput textarea {
    color: #f8fafc !important;
}

/* Custom fixed container for the upload button */
.fixed-upload-button {
    position: fixed;
    bottom: 45px;
    left: calc(50% - 450px);
    z-index: 1000;
    display: flex;
    align-items: center;
}

/* ===== Buttons ===== */
.stButton > button {
    background: #0f172a;
    color: f8fafc;
    border-radius: 8px;
    border: none;
}

/* ===== Sidebar ===== */
[data-testid="stSidebar"] {
    background: #020617;
    border-right: 1px solid #1e3a8a;
    color: #e2e8f0;
}

[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
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
        background:#1e293b;
        padding:16px;
        border-radius:12px;
        text-align:center;
        color:#e2e8f0;
        font-weight:500;
    ">
    Commencez un nouveau chat pour débuter.
    </div>
    """, unsafe_allow_html=True)
else:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]): # type: ignore
            st.markdown(message["content"]) # type: ignore

    # Display Download Buttons at the bottom if results are ready
    list_resp = requests.get(f"{API_BASE_URL}/list/{st.session_state.session_id}")
    if list_resp.status_code == 200:
        updated_files = sorted(list(set(f for f in list_resp.json().get("files", []) if f.startswith('updated_'))))
        if updated_files:
            with st.expander("Télécharger les fichiers mis à jour", expanded=True):
                for f in updated_files:
                    download_url = f"{API_BASE_URL}/download/{st.session_state.session_id}/{f}"
                    file_content = requests.get(download_url).content
                    st.download_button(f"Enregistrer {f}", data=file_content, file_name=f, key=f"dl_main_{f}")

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
if st.session_state.session_id:
    st.markdown('<div class="fixed-upload-button">', unsafe_allow_html=True)
    with st.popover("Charger 🔗"):
        uploaded_files = st.file_uploader(
            "Fichiers",
            type=["pdf", "csv", "xlsx"],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )
        if uploaded_files and st.button("Traiter"):
            files_to_send = [
                ("files", (f.name, f.getvalue(), f.type))
                for f in uploaded_files
            ]
            with st.spinner("Traitement en cours..."):
                requests.post(f"{API_BASE_URL}/upload/{st.session_state.session_id}", files=files_to_send)
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
