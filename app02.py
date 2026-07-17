import os
import psycopg2
from flask import Flask, render_template, request, jsonify
from psycopg2.extras import RealDictCursor, execute_values

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

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
    if data['status'] == 'Disponível':
        cur.execute("UPDATE rifas SET status='Disponível', nome_comprador=NULL, telefone=NULL WHERE numero=%s", (data['numero'],))
    else:
        cur.execute("UPDATE rifas SET status=%s, nome_comprador=%s, telefone=%s WHERE numero=%s", 
                    (data['status'], data['nome_comprador'], data['telefone'], data['numero']))
    conn.commit()
    conn.close()
    return jsonify({"sucesso": True})

@app.route('/api/admin/participantes-pagos')
def participantes_pagos():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT numero, nome_comprador, telefone FROM rifas WHERE status = 'Pago';")
    data = cur.fetchall()
    conn.close()
    return jsonify(data)

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