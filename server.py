import os
from flask import Flask, jsonify, request
import anthropic
import json

app = Flask(__name__)

# Initialisation du client Anthropic avec ta clé API
client = anthropic.Anthropic(api_key="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")

# Stockage en mémoire du dernier trade validé (pour que MT5 puisse venir le chercher)
latest_trade = {"action": "NONE"}

SYSTEM_PROMPT = """
Tu es un assistant de trading algorithmique expert spécialisé exclusivement sur l'or (XAUUSD). 
L'or réagit aux zones de liquidité institutionnelles. Ne te limite pas à une seule unité de temps fixe : analyse la structure selon les données fournies par l'alerte (qu'il s'agisse de configurations Daily, 4H, 1H, 15m ou autres).

Lorsque tu reçois une alerte de TradingView, analyse la configuration et rends ta réponse sous un format JSON strict (SANS AUCUN TEXTE AUTRE QUE LE JSON, pas de balises markdown ```json).

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
  "status": "REJECTED",
  "raison": "Motif du refus"
}
"""

@app.route("/", methods=["GET"])
def home():
    return "Bot Trading XAUUSD Opérationnel !", 200

@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    global latest_trade
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    ticker = data.get('ticker', 'XAUUSD')
    price = data.get('price', 0)
    message = data.get('message', 'Alerte technique XAUUSD')

    user_prompt = f"""
    Analyse cette alerte reçue pour l'actif {ticker} :
    - Prix actuel du marché : {price}
    - Contexte / Message technique de l'alerte : {message}
    
    Détermine si un plan de trade rigoureux sur l'or peut être établi selon les critères de liquidité et de structure.
    """

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )
        
        raw_response = response.content[0].text.strip()
        
        # Nettoyage de sécurité des balises markdown si présentes
        if raw_response.startswith("```"):
            raw_response = raw_response.split("```")[1]
            if raw_response.startswith("json"):
                raw_response = raw_response[4:]
        raw_response = raw_response.strip()

        trade_plan = json.loads(raw_response)
        latest_trade = trade_plan  # On sauvegarde pour consultation future
        return jsonify(trade_plan), 200

    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/trade', methods=['GET'])
def get_latest_trade():
    global latest_trade
    return jsonify(latest_trade), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
