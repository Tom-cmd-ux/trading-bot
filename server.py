import os
from flask import Flask, request, jsonify
from anthropic import Anthropic

app = Flask(__name__)

# Stockage en mémoire du dernier trade validé
latest_trade = {"action": "NONE"}

anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
client = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else None

@app.route("/", methods=["GET"])
def home():
    return "Bot Trading Opérationnel !", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    global latest_trade
    data = request.get_json(silent=True) or {}
    
    # Message/signal reçu de TradingView
    raw_message = data.get("message", str(data))
    
    # Demande d'analyse à Claude 3.5 Sonnet
    if client:
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=100,
                messages=[{
                    "role": "user",
                    "content": f"Analyse ce signal de trading: '{raw_message}'. Réponds UNIQUEMENT par 'BUY', 'SELL' ou 'REJECT'."
                }]
            )
            decision = response.content[0].text.strip().upper()
        except Exception as e:
            print(f"Erreur Claude API: {e}")
            decision = "BUY" if "BUY" in raw_message.upper() else ("SELL" if "SELL" in raw_message.upper() else "REJECT")
    else:
        decision = "BUY" if "BUY" in raw_message.upper() else ("SELL" if "SELL" in raw_message.upper() else "REJECT")

    # Si le trade est validé par Claude, on le stocke pour MT5
    if decision in ["BUY", "SELL"]:
        latest_trade = {
            "action": decision,
            "symbol": "XAUUSD",
            "volume": 0.01
        }
        print(f"[+] TRADE VALIDE : {decision}")
    else:
        print("[-] TRADE REJETÉ PAR CLAUDE")

    return jsonify({"status": "success", "decision": decision}), 200

@app.route("/get_trade", methods=["GET"])
def get_trade():
    global latest_trade
    # Remet à zéro après la lecture par MT5 pour ne pas réexécuter le même ordre
    trade_to_send = latest_trade.copy()
    latest_trade = {"action": "NONE"}
    return jsonify(trade_to_send), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
