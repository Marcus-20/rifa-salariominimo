import os
import socket
import psycopg2
from flask import Flask, render_template, request, jsonify
from psycopg2.extras import RealDictCursor, execute_values
from urllib.parse import urlparse
import mercadopago

app = Flask(__name__)

# Configurações obtidas das variáveis de ambiente do Render
DATABASE_URL = os.environ.get("DATABASE_URL")
MERCADOPAGO_TOKEN = os.environ.get("MERCADOPAGO_TOKEN")

# Inicializa o SDK do Mercado Pago
sdk = mercadopago.SDK(MERCADOPAGO_TOKEN) if MERCADOPAGO_TOKEN else None

def get_db_connection():
    """Cria uma conexão com o banco de dados forçando IPv4 para evitar erros no Render."""
    if not DATABASE_URL:
        raise ValueError("A variável de ambiente DATABASE_URL não está configurada.")
    
    # Extrai o host da URL para resolver para IPv4
    parsed = urlparse(DATABASE_URL)
    host = parsed.hostname
    port = parsed.port or 5432
    
    # Tenta resolver o host para IPv4 especificamente
    try:
        ip_v4 = socket.getaddrinfo(host, port, socket.AF_INET)[0][4][0]
        # Monta uma nova URL usando o IP resolvido
        new_db_url = DATABASE_URL.replace(host, ip_v4)
        return psycopg2.connect(new_db_url, cursor_factory=RealDictCursor, connect_timeout=10)
    except Exception as e:
        print(f"Erro ao forçar IPv4, tentando conexão normal: {e}")
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)

def inicializar_banco():
    """Cria a tabela de rifas e gera os números de 0 a 500 caso não existam."""
    print("Iniciando verificação do banco de dados...")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rifas (
                numero INT PRIMARY KEY,
                status VARCHAR(20) DEFAULT 'disponivel',
                nome_comprador VARCHAR(100),
                telefone VARCHAR(20),
                pago BOOLEAN DEFAULT FALSE,
                pix_copia_cola TEXT,
                qr_code TEXT,
                payment_id VARCHAR(50)
            );
        """)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) as total FROM rifas;")
        total = cur.fetchone()["total"]
        
        if total == 0:
            print("Gerando números de 0 a 500 no Supabase...")
            valores = [(i, 'disponivel') for i in range(501)]
            execute_values(cur, "INSERT INTO rifas (numero, status) VALUES %s", valores)
            conn.commit()
            print("501 números gerados com sucesso!")
        else:
            print(f"Os números já estão criados no banco. Total: {total}")
            
    except Exception as e:
        print(f"Erro ao inicializar o banco de dados: {e}")
    finally:
        if conn:
            conn.close()

# Executa a geração automática
inicializar_banco()

# --- ROTAS ---

@app.route('/')
def index():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT numero, status FROM rifas ORDER BY numero ASC;")
        numeros = cur.fetchall()
        return render_template('index.html', numeros=numeros)
    except Exception as e:
        return f"Erro ao carregar os números: {e}", 500
    finally:
        if conn:
            conn.close()

@app.route('/comprar', methods=['POST'])
def comprar():
    if not sdk:
        return jsonify({"erro": "Mercado Pago não configurado"}), 500
        
    data = request.json
    nome, telefone, numeros_selecionados = data.get('nome'), data.get('telefone'), data.get('numeros')
    
    if not nome or not telefone or not numeros_selecionados:
        return jsonify({"erro": "Dados incompletos"}), 400

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT numero FROM rifas WHERE numero = ANY(%s) AND status != 'disponivel';", (numeros_selecionados,))
        if cur.fetchall():
            return jsonify({"erro": "Números já ocupados."}), 400
            
        valor_total = float(len(numeros_selecionados) * 10.00)
        
        payment_data = {
            "transaction_amount": valor_total,
            "description": f"Rifa Salário Mínimo",
            "payment_method_id": "pix",
            "payer": {"email": "comprador@email.com", "first_name": nome}
        }
        
        payment = sdk.payment().create(payment_data)["response"]
        payment_id = str(payment.get("id"))
        qr_code = payment.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code")
        
        for num in numeros_selecionados:
            cur.execute("UPDATE rifas SET status = 'reservado', nome_comprador = %s, pix_copia_cola = %s, payment_id = %s WHERE numero = %s;", 
                        (nome, qr_code, payment_id, num))
            
        conn.commit()
        return jsonify({"sucesso": True, "pix_copia_cola": qr_code})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))