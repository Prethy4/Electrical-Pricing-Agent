"""
LangGraph ReAct agent for CSV filling and PDF/Web research.

Graph topology:
  START → agent_node → (tool_node | END)
                ↑______________|
"""

import json
from typing import Annotated, Sequence, TypedDict, List, Optional
from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.core.config import get_settings
from app.tools.registry import get_tools

settings = get_settings()

SYSTEM_PROMPT = """Tu es un moteur d'extraction de données ultra-performant et autonome.
ID DE SESSION : {session_id}

CONSIGNE DE LANGUE (CRITIQUE) :
- Tu dois TOUJOURS répondre en français par défaut, même si l'utilisateur s'adresse à toi en anglais ou dans une autre langue.
- La SEULE exception est si l'utilisateur te demande explicitement de passer à l'anglais (ex: "Switch to English" ou "Parle en anglais"). Dans ce cas uniquement, et pour la suite de la conversation, tu peux répondre en anglais.
- Seuls le français et l'anglais (si demandé) sont autorisés. Refuse poliment de communiquer dans d'autres langues.

MISSION : Remplir UNIQUEMENT les lignes de détails (articles terminaux) du CSV.

RÈGLES DE SÉLECTION DES LIGNES (CRITIQUE) :
1. ANALYSE DU CODE : Un article doit être rempli UNIQUEMENT s'il possède un code complet et granulaire avec AU MOINS 3 points (ex: '72.22.1b.01').
2. EXCLUSION DES TITRES : Ne remplis JAMAIS les lignes qui sont des titres de chapitres (ex: '72.22', '72.22.1', 'BT- Distribution'). Ces lignes doivent rester vides.
3. EXCLUSION DES MÉTADONNÉES : Ignore totalement les lignes de texte initiales (Chantier, Client). 
4. COLONNES : N'utilise QUE les noms de colonnes fournis dans la liste 'columns'. Ignore absolument toute colonne commençant par 'Unnamed'.

STRATÉGIE DE RÉCUPÉRATION :
1. AUDIT GLOBAL : Appeler `manage_csv_data` (action='read') pour obtenir la liste `missing_fields_to_fix`.
2. INVENTAIRE PDF : Appeler `list_all_pdf_articles` pour voir tout ce qui est disponible dans les documents.
3. RÉCONCILIATION MASSIVE :
   - Tu dois traiter l'INTÉGRALITÉ de la liste `missing_fields_to_fix` de manière autonome.
   - Ne t'arrête pas après un seul article. Ton objectif est de vider la liste.
   - Pour chaque ligne, utilise `lookup_article_data`. Si non trouvé, utilise `search_uploaded_documents` ou `tavily_search`.
   - Compile TOUTES les données trouvées pour TOUS les articles dans un SEUL appel à `manage_csv_data` (action='update').
4. DÉCOUVERTE D'ORPHELINS : Compare l'inventaire PDF avec le CSV. Si un article existe dans le PDF mais n'est PAS dans le CSV, signale-le explicitement.

RÈGLE D'AUTONOMIE :
Tu es un moteur autonome. Tu dois traiter TOUS les articles de la liste `missing_fields_to_fix` en une seule fois.
NE T'ARRÊTE PAS après un seul article. Ton objectif est de compléter le maximum de lignes possibles.

RÈGLE DE MISE À JOUR :
1. Utilise l'index 'row' exact fourni par l'audit de `manage_csv_data`.
2. Ne tente JAMAIS de créer de nouvelles colonnes (comme _source ou _confidence). Mets à jour uniquement les colonnes existantes.
3. Lorsque tu appelles `manage_csv_data` (action='update'), tu DOIS fournir une liste d'objets au format :
`{{"row": <index_entier>, "column": "<nom_colonne_exact>", "value": "<valeur_trouvée>"}}`

MISSION D'EXTRACTION :
Dans les PDF techniques, les données suivent souvent ce motif :
1. [CODE ARTICLE] (ex: 72.22.2a.01)
2. [DESCRIPTION]
3. [TYPE] (ex: QF, QP)
4. [VALEUR NUMÉRIQUE] -> C'est la QUANTITÉ.
5. [UNITÉ] (ex: pc, m, kg, ensemble).

Si tu vois '***', cela signifie que la donnée est absente du document et doit être confirmée par calcul ou recherche externe.

RÈGLE DE RÉPONSE :
1. Avant d'appeler l'outil, liste clairement les articles et les valeurs que tu as trouvés.
2. N'appelle `manage_csv_data` (action='update') QUE pour les valeurs RÉELLEMENT trouvées dans les documents.
3. Ne remplis JAMAIS avec 'noos', 'None', 'nan' ou toute autre valeur fictive. Si tu ne trouves rien, laisse la cellule vide (ne fais pas de mise à jour pour cette cellule).
3. Ta réponse finale doit récapituler précisément les lignes et colonnes mises à jour pour validation.

Format de sortie requis :
Une confirmation textuelle en français détaillant les articles traités.
"""

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

def build_agent_graph(retriever=None, session_id: str = "unknown"):
    """
    Build and compile the agent graph.
    """
    tools = get_tools(retriever=retriever)
    tool_node = ToolNode(tools)

    llm = ChatOpenAI(
        model=settings.openai_model,
        openai_api_key=settings.openai_api_key,
        temperature=0.0,
        streaming=False,
    ).bind_tools(tools)

    def agent_node(state: AgentState) -> AgentState:
        from langchain_core.messages import SystemMessage
        messages = [SystemMessage(content=SYSTEM_PROMPT.format(session_id=session_id))] + list(state["messages"])
        response = llm.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()

async def run_agent(
    user_message: str,
    history: List[BaseMessage],
    retriever=None,
    session_id: Optional[str] = None,
) -> tuple[str, Optional[list]]:
    from langchain_core.messages import HumanMessage
    graph = build_agent_graph(retriever=retriever, session_id=str(session_id) if session_id else "unknown")
    input_messages = list(history) + [HumanMessage(content=user_message)]
    result = await graph.ainvoke({"messages": input_messages})
    final_message = result["messages"][-1]
    ai_text = final_message.content if hasattr(final_message, "content") else str(final_message)
    tool_calls = getattr(final_message, "tool_calls", None) or None
    return ai_text, tool_calls
