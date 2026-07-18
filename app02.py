import os
import psycopg2
import mercadopago
from flask import Flask, render_template, request, jsonify
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
# Configurações usando Variáveis de Ambiente
DATABASE_URL = os.environ.get("DATABASE_URL")
# IMPORTANTE: Garanta que MP_ACCESS_TOKEN esteja nas variáveis do Render
sdk = mercadopago.SDK(os.environ.get("MP_ACCESS_TOKEN"))

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- NOVA ROTA: WEBHOOK PARA PAGAMENTO AUTOMÁTICO ---
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    # Verifica se o evento é um pagamento
    if data.get('action') == 'payment.updated' or data.get('type') == 'payment':
        payment_id = data.get('data', {}).get('id') if 'data' in data else data.get('id')
        
        # Consulta os detalhes do pagamento no Mercado Pago
        payment_info = sdk.payment().get(payment_id)
        status = payment_info['response']['status']
        
        # Se aprovado, busca os números associados no banco e marca como 'Pago'
        if status == 'approved':
            # Nota: Você pode precisar salvar o external_reference ou um id de transação 
            # na tabela de rifas para vincular o pagamento aos números corretamente.
            pass 
            
    return '', 200

# --- ROTA DE CRIAÇÃO DE PIX ---
@app.route('/api/criar-pagamento', methods=['POST'])
def criar_pagamento():
    data = request.json
    valor_total = float(len(data['numeros']) * 10)
    
    # Criar pagamento via PIX
    payment_data = {
        "transaction_amount": valor_total,
        "description": f"Rifa Números {data['numeros']}",
        "payment_method_id": "pix",
        "payer": {"email": "cliente@email.com"}
    }
    result = sdk.payment().create(payment_data)
    
    if result["status"] == 201:
        # Salva como Reservado
        conn = get_db_connection()
        cur = conn.cursor()
        for num in data['numeros']:
            cur.execute("UPDATE rifas SET status='Reservado', nome_comprador=%s, telefone=%s WHERE numero=%s", 
                        (data['nome'], data['telefone'], num))
        conn.commit()
        conn.close()
        
        qr_code = result["response"]["point_of_interaction"]["transaction_data"]["qr_code"]
        copia_cola = result["response"]["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        
        return jsonify({"qr_code": qr_code, "copia_cola": copia_cola})
    
    return jsonify({"erro": "Falha ao criar pagamento"}), 400

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