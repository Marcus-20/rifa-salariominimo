import os
import psycopg2
import mercadopago
from flask import Flask, render_template, request, jsonify
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
# Configurações
DATABASE_URL = os.environ.get("DATABASE_URL")
sdk = mercadopago.SDK(os.environ.get("MP_ACCESS_TOKEN"))

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- ROTAS DE PAGAMENTO ---

@app.route('/api/criar-pagamento', methods=['POST'])
def criar_pagamento():
    data = request.json
    valor_total = float(len(data['numeros']) * 10) # R$ 10 por número
    
    # Criar preferência no Mercado Pago
    payment_data = {
        "items": [{"title": f"Rifa Números {data['numeros']}", "quantity": 1, "unit_price": valor_total}],
        "payer": {"email": "cliente@email.com"},
        "payment_methods": {"excluded_payment_types": [{"id": "credit_card"}]}
    }
    result = sdk.payment().create(payment_data)
    
    # Salvar reserva no banco como 'Reservado'
    conn = get_db_connection()
    cur = conn.cursor()
    for num in data['numeros']:
        cur.execute("UPDATE rifas SET status='Reservado', nome_comprador=%s, telefone=%s WHERE numero=%s", 
                    (data['nome'], data['telefone'], num))
    conn.commit()
    conn.close()
    
    return jsonify({"qr_code": result["response"]["point_of_interaction"]["transaction_data"]["qr_code"], 
                    "copia_cola": result["response"]["point_of_interaction"]["transaction_data"]["qr_code_base64"]})

# --- DEMAIS ROTAS (Manter as que você já tinha) ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/numeros')
def api_numeros():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM rifas ORDER BY numero ASC;")
    data = cur.fetchall()
    conn.close()
    return jsonify(data)

@app.route('/api/admin/editar-numero', methods=['POST'])
def editar_numero():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE rifas SET status=%s, nome_comprador=%s, telefone=%s WHERE numero=%s", 
                (data['status'], data['nome_comprador'], data['telefone'], data['numero']))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})

@app.route('/api/admin/reset', methods=['POST'])
def reset_rifa():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE rifas SET status = 'Disponível', nome_comprador = NULL, telefone = NULL;")
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))