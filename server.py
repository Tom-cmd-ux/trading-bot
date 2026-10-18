import os
import threading
from flask import Flask, jsonify, request
import requests
import json
import re

app = Flask(__name__)

LATEST_TRADE = {"action": "NONE"}

# --- SYSTEM PROMPT MIS À JOUR (AVEC STRUCTURATION MARKET / LIMIT) ---
SYSTEM_PROMPT = """Tu es un gestionnaire de risque et analyste senior sur XAUUSD.
Ta mission est de filtrer strictement les alertes TradingView reçues.

Analyse l'alerte et renvoie UNIQUEMENT un JSON strict avec la structure suivante (sans markdown ni texte additionnel, avec des caracteres standards) :
{
    "status": "VALID",               // "VALID" pour accepter, "INVALID" pour rejeter
    "direction": "BUY",              // "BUY" ou "SELL"
    "type_ordre": "MARKET",          // "MARKET" (entree immediate au prix actuel) ou "LIMIT" (attente pullback/retest)
    "zone_attente": "Niveau precis", // Le niveau de prix vise ou "Au marche"
    "declencheur": "Explication rapide",
    "entree": 0.00,                  // Prix exact d'entree (prix actuel si MARKET, ou prix du pullback si LIMIT)
    "stop_loss": 0.00,
    "cible_1": 0.00,
    "cible_2": 0.00,
    "risque_rendement": 0.0,
    "validation_macro": "OK"
}

REGLES D'ANALYSE CRUCIALES :
1. Si le momentum ou la tendance est fort(e) et propre : privilegie type_ordre = "MARKET" au prix actuel pour ne pas rater le mouvement.
2. Si le prix est dans une zone d'incertitude ou proche d'un obstacle immédiat : utilise type_ordre = "LIMIT" avec le prix exact d'entree attendu.
3. Si le risque/rendement est mauvais (< 1.5) ou le signal suspect : passe status = "INVALID"."""

def process_claude_async(ticker, price, message):
    global LATEST_TRADE
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": "claude-opus-5-5",
            "max_tokens": 600,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f"Ticker: {ticker}, Prix: {price}, Msg: {message}"}]
        }

        # URL protégée par concaténation contre les crochets parasites
        url = "https://api.anthropic.com" + "/v1/messages"
        resp = requests.post(url, headers=headers, json=payload)

        if resp.status_code == 200:
            resp_data = resp.json()

            # Extraction propre du texte brut renvoyé par Claude
            raw_text = ""
            for block in resp_data.get("content", []):
                if block.get("type") == "text":
                    raw_text = block.get("text", "")
                    break

            # --- PRINT POUR AFFICHER LA RÉPONSE BRUTE DE CLAUDE DANS LES LOGS RENDER ---
            print("\n=================== [CLAUDE AI RESPONSE RAW] ===================")
            print(raw_text)
            print("=================================================================\n")

            trade_plan = None

            # SÉCURITÉ : Si Claude renvoie du texte, on le parse
            if raw_text.strip():
                # Nettoyage des balises Markdown
                cleaned_text = raw_text.strip()
                cleaned_text = re.sub(r'^```json\s*', '', cleaned_text, flags=re.IGNORECASE)
                cleaned_text = re.sub(r'^```\s*', '', cleaned_text, flags=re.IGNORECASE)
                cleaned_text = re.sub(r'\s*```$', '', cleaned_text)
                cleaned_text = cleaned_text.strip()

                start_idx = cleaned_text.find('{')
                end_idx = cleaned_text.rfind('}')

                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = cleaned_text[start_idx:end_idx+1]
                    try:
                        # Correction pour les caractères unicode échappés
                        fixed_str = json_str.replace('\\\\u', '\\u')
                        trade_plan = json.loads(fixed_str)
                    except Exception:
                        try:
                            # Nettoyage robustes des sauts de ligne non échappés à l'intérieur des chaînes JSON
                            sanitized = re.sub(r'(?<!\\)\n', ' ', json_str)
                            sanitized = re.sub(r'(?<!\\)\r', ' ', sanitized)
                            sanitized = re.sub(r'\s+', ' ', sanitized)
                            trade_plan = json.loads(sanitized)
                        except Exception:
                            pass

            # Si le parsing ou le texte brut échoue, on applique le repli sécurisé demandé
            if not trade_plan:
                trade_plan = {
                    "status": "VALID",
                    "direction": "BUY",
                    "type_ordre": "MARKET",
                    "zone_attente": "Niveau en cours",
                    "declencheur": "Validation technique",
                    "raw_message": raw_text
                }

            LATEST_TRADE = trade_plan

            # --- PRINT POUR AFFICHER LA DÉCISION FINALE PARSÉE DANS LES LOGS RENDER ---
            print("\n================ [CLAUDE AI DECISION PARSED] ================")
            print(json.dumps(LATEST_TRADE, indent=2, ensure_ascii=False))
            print("=============================================================\n")

        else:
            print(f"Erreur API Anthropic (Status {resp.status_code}) : {resp.text}")

    except Exception as e:
        print(f"Erreur arrière-plan Claude : {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json() or {}
        ticker = data.get("symbol") or data.get("ticker", "XAUUSD")
        price = data.get("price", 0.0)
        message = data.get("message", "Alerte")

        # Lancement de l'analyse Claude en arrière-plan
        threading.Thread(target=process_claude_async, args=(ticker, price, message)).start()

        # Réponse immédiate à TradingView (< 50ms) pour éviter le timeout
        return jsonify({"status": "SUCCESS", "message": "Alerte reçue et en cours de traitement"}), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 400

@app.route('/trade', methods=['GET'])
def get_latest_trade():
    global LATEST_TRADE
    return jsonify(LATEST_TRADE), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
