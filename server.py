import os
from flask import Flask, jsonify, request
import anthropic
import json

app = Flask(__name__)

# Initialisation du client Anthropic avec ta clé propre
client = anthropic.Anthropic(api_key="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")

# Stockage en mémoire du dernier trade validé (pour que MT5 puisse venir le chercher)
latest_trade = {"action": "NONE"}

SYSTEM_PROMPT = """
Tu es un assistant de trading algorithmique expert spécialisé exclusivement sur l'or (XAUUSD).
L'or réagit aux zones de liquidité institutionnelles. Ne te limite pas à une seule unité de temps fixe : analyse la structure selon les données reçues.
Lorsque tu reçois une alerte de TradingView, analyse la configuration et rends ta réponse sous un format JSON strict (SANS AUCUN TEXTE AUTRE QUE LE JSON).
Le format JSON de sortie doit être exactement celui-ci :
{
    "status": "VALID",
    "direction": "BUY",
    "zone_attente": "Niveau de référence ou de liquidité surveillé",
    "declencheur": "Description du déclencheur (ex: sweep de liquidité, cassure de structure, rejet sur unité de temps adaptée)",
    "entree": 0.00,
    "stop_loss": 0.00,
    "cible_1": 0.00,
    "cible_2": 0.00,
    "risque_rendement": 0.0,
    "validation_macro": "OK"
}
Si la configuration est non validée ou trop risquée, renvoie :
{
    "status": "INVALID",
    "direction": "NONE",
    "zone_attente": "",
    "declencheur": "",
    "entree": 0.0,
    "stop_loss": 0.0,
    "cible_1": 0.0,
    "cible_2": 0.0,
    "risque_rendement": 0.0,
    "validation_macro": "REFUSED"
}
"""

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        ticker = data.get("ticker", "XAUUSD")
        price = data.get("price", 0.0)
        message = data.get("message", "Pas de message")

        user_prompt = f"Alerte reçue - Ticker: {ticker}, Prix actuel: {price}, Message: {message}. Analyse cette configuration."

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )

        content = response.content[0].text.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()

        trade_plan = json.loads(content)
        
        global latest_trade
        latest_trade = trade_plan

        return jsonify({"status": "SUCCESS", "trade_plan": trade_plan}), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 400

@app.route('/trade', methods=['GET'])
def get_latest_trade():
    global latest_trade
    return jsonify(latest_trade), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
