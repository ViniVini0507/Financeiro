import os
import requests
import logging

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def fetch_database_pages(database_id: str) -> list:
    """Busca todas as páginas de um banco de dados do Notion tratando paginação."""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    pages = []
    has_more = True
    start_cursor = None
    
    if not NOTION_TOKEN:
        logging.error("NOTION_TOKEN não configurada!")
        return []

    while has_more:
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor
            
        try:
            response = requests.post(url, json=payload, headers=HEADERS, timeout=15)
            if response.status_code == 429:
                import time
                time.sleep(1) # Rate limiting simples
                continue
            response.raise_for_status()
            data = response.json()
            pages.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor", None)
        except Exception as e:
            logging.error(f"Erro ao buscar dados do database {database_id}: {e}")
            break
            
    return pages

def extract_property(page_data: dict, prop_name: str, prop_type: str):
    """Extração utilitária de propriedades brutas do json do Notion."""
    props = page_data.get("properties", {})
    prop = props.get(prop_name, {})
    
    if prop_type == "title" and prop.get("title"):
        return prop["title"][0]["plain_text"] if prop["title"] else "Sem Título"
    elif prop_type == "number":
        return prop.get("number", 0.0) or 0.0
    elif prop_type == "select" and prop.get("select"):
        return prop["select"]["name"]
    elif prop_type == "checkbox":
        return prop.get("checkbox", False)
    elif prop_type == "date" and prop.get("date"):
        return prop["date"]["start"]
    elif prop_type == "relation" and prop.get("relation"):
        relations = prop["relation"]
        return relations[0]["id"] if relations else None
    return None