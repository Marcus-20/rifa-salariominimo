import os
import psycopg2
import mercadopago
import random
from flask import Flask, render_template, request, jsonify
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL")
sdk = mercadopago.SDK(os.environ.get("MP_ACCESS_TOKEN"))

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data.get('action') == 'payment.updated' or data.get('type') == 'payment':
        payment_id = data.get('data', {}).get('id') if 'data' in data else data.get('id')
        payment_info = sdk.payment().get(payment_id)
        payment = payment_info.get('response', {})
        if payment.get('status') == 'approved':
            numeros_str = payment.get('external_reference')
            if numeros_str:
                numeros = numeros_str.split(',')
                conn = get_db_connection()
                cur = conn.cursor()
                for num in numeros:
                    cur.execute("UPDATE rifas SET status='Pago' WHERE numero=%s", (num,))
                conn.commit()
                conn.close()
    return '', 200

@app.route('/api/criar-pagamento', methods=['POST'])
def criar_pagamento():
    data = request.json
    numeros = data['numeros']
    valor_total = float(len(numeros) * 10)
    payment_data = {
        "transaction_amount": valor_total,
        "description": f"Rifa Números {numeros}",
        "external_reference": ",".join(map(str, numeros)),
        "payment_method_id": "pix",
        "payer": {"email": "cliente@email.com"}
    }
    result = sdk.payment().create(payment_data)
    if result["status"] == 201:
        conn = get_db_connection()
        cur = conn.cursor()
        for num in numeros:
            cur.execute("UPDATE rifas SET status='Reservado', nome_comprador=%s, telefone=%s WHERE numero=%s", 
                        (data['nome'], data['telefone'], num))
        conn.commit()
        conn.close()
        
        # Retorna o código para copiar e a imagem base64 do QR Code
        t_data = result["response"]["point_of_interaction"]["transaction_data"]
        return jsonify({
            "copia_cola": t_data["qr_code"],
            "qr_code_base64": t_data["qr_code_base64"]
        })
    return jsonify({"erro": "Falha"}), 400

@app.route('/api/admin/sortear', methods=['POST'])
def sortear():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT numero, nome_comprador FROM rifas WHERE status='Pago';")
    pagos = cur.fetchall()
    conn.close()
    if not pagos: return jsonify({"erro": "Nenhum número pago!"}), 400
    return jsonify({"vencedor": random.choice(pagos)})

# --- DEMAIS ROTAS ---
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