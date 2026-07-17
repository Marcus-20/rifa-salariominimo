import os
import socket
import psycopg2
from flask import Flask, render_template, request, jsonify
from psycopg2.extras import RealDictCursor, execute_values
from urllib.parse import urlparse
import mercadopago

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
MERCADOPAGO_TOKEN = os.environ.get("MERCADOPAGO_TOKEN")
sdk = mercadopago.SDK(MERCADOPAGO_TOKEN) if MERCADOPAGO_TOKEN else None

def get_db_connection():
    """Conexão otimizada para o Neon/Render."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não configurada.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)

def inicializar_banco():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS rifas (numero INT PRIMARY KEY, status VARCHAR(20) DEFAULT 'disponivel', nome_comprador VARCHAR(100), telefone VARCHAR(20), pix_copia_cola TEXT, qr_code TEXT, payment_id VARCHAR(50));")
        cur.execute("SELECT COUNT(*) as total FROM rifas;")
        if cur.fetchone()["total"] == 0:
            valores = [(i, 'disponivel') for i in range(501)]
            execute_values(cur, "INSERT INTO rifas (numero, status) VALUES %s", valores)
            conn.commit()
    except Exception as e:
        print(f"Erro ao inicializar: {e}")
    finally:
        if conn: conn.close()

inicializar_banco()

# --- ROTAS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/numeros')
def api_numeros():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT numero, status FROM rifas ORDER BY numero ASC;")
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/reservar', methods=['POST'])
def reservar():
    data = request.json
    # Lógica de reserva e Mercado Pago aqui...
    # (Mantive a estrutura para você integrar)
    return jsonify({"sucesso": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))