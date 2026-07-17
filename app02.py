import os
import psycopg2
from flask import Flask, render_template, request, jsonify
from psycopg2.extras import RealDictCursor, execute_values

app = Flask(__name__)

# Configuração do banco de dados (Neon)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não configurada.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)

def inicializar_banco():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Criando tabela com suporte aos campos que o admin precisa
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rifas (
                numero INT PRIMARY KEY, 
                status VARCHAR(20) DEFAULT 'Disponível', 
                nome_comprador VARCHAR(100), 
                telefone VARCHAR(20), 
                pix_copia_cola TEXT, 
                qr_code TEXT, 
                payment_id VARCHAR(50)
            );
        """)
        cur.execute("SELECT COUNT(*) as total FROM rifas;")
        if cur.fetchone()["total"] == 0:
            valores = [(i, 'Disponível') for i in range(1, 101)] # Rifas de 1 a 100
            execute_values(cur, "INSERT INTO rifas (numero, status) VALUES %s", valores)
            conn.commit()
    except Exception as e:
        print(f"Erro ao inicializar: {e}")
    finally:
        if conn: conn.close()

inicializar_banco()

# --- ROTAS PRINCIPAIS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html') # Certifique-se de ter o admin.html na pasta templates

@app.route('/api/numeros')
def api_numeros():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM rifas ORDER BY numero ASC;")
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        if conn: conn.close()

# --- ROTAS DO PAINEL ADMIN ---

@app.route('/api/admin/editar-numero', methods=['POST'])
def editar_numero():
    data = request.json
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE rifas 
            SET status = %s, nome_comprador = %s, telefone = %s 
            WHERE numero = %s;
        """, (data['status'], data['nome_comprador'], data['telefone'], data['numero']))
        conn.commit()
        return jsonify({"sucesso": True})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/admin/participantes-pagos')
def participantes_pagos():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT numero, nome_comprador, telefone FROM rifas WHERE status = 'Pago';")
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/admin/reset', methods=['POST'])
def reset_rifa():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE rifas SET status = 'Disponível', nome_comprador = NULL, telefone = NULL;")
        conn.commit()
        return jsonify({"sucesso": True})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))