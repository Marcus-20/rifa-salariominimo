import os
from flask import Flask, render_template, request, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import mercadopago

app = Flask(__name__)

# Configurações obtidas das variáveis de ambiente do Render
DATABASE_URL = os.environ.get("DATABASE_URL")
MERCADOPAGO_TOKEN = os.environ.get("MERCADOPAGO_TOKEN")

# Inicializa o SDK do Mercado Pago
sdk = mercadopago.SDK(MERCADOPAGO_TOKEN) if MERCADOPAGO_TOKEN else None

def get_db_connection():
    """Cria uma conexão rápida com o banco de dados do Supabase."""
    if not DATABASE_URL:
        raise ValueError("A variável de ambiente DATABASE_URL não está configurada.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def inicializar_banco():
    """Cria a tabela de rifas e gera os números de 0 a 500 caso não existam."""
    print("Iniciando verificação do banco de dados...")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 1. Cria a tabela se ela ainda não existir no Supabase
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
        
        # 2. Verifica quantos números já estão salvos
        cur.execute("SELECT COUNT(*) as total FROM rifas;")
        total = cur.fetchone()["total"]
        
        # 3. Se a tabela estiver vazia, gera de 0 a 500 em lote (super rápido!)
        if total == 0:
            print("Gerando números de 0 a 500 no Supabase...")
            valores = [(i, 'disponivel') for i in range(501)]
            execute_values(
                cur, 
                "INSERT INTO rifas (numero, status) VALUES %s", 
                valores
            )
            conn.commit()
            print("501 números gerados com sucesso!")
        else:
            print(f"Os números já estão criados no banco. Total encontrado: {total}")
            
    except Exception as e:
        print(f"Erro ao inicializar o banco de dados: {e}")
    finally:
        if conn:
            conn.close()

# Executa a geração automática assim que o Flask inicializa
inicializar_banco()

# --- ROTAS DO SITE ---

@app.route('/')
def index():
    """Página inicial que exibe os números da rifa."""
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
    """Reserva os números e gera o pagamento via Pix."""
    if not sdk:
        return jsonify({"erro": "Mercado Pago não configurado no servidor"}), 500
        
    data = request.json
    nome = data.get('nome')
    telefone = data.get('telefone')
    numeros_selecionados = data.get('numeros') # Espera uma lista de números, ex: [42, 107]
    
    if not nome or not telefone or not numeros_selecionados:
        return jsonify({"erro": "Dados incompletos"}), 400

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se os números escolhidos ainda estão disponíveis
        cur.execute(
            "SELECT numero FROM rifas WHERE numero = ANY(%s) AND status != 'disponivel';",
            (numeros_selecionados,)
        )
        ja_reservados = cur.fetchall()
        if ja_reservados:
            return jsonify({"erro": f"Os números {[r['numero'] for r in ja_reservados]} já foram comprados ou reservados."}), 400
            
        # Calcula o valor total da compra (ex: R$ 10,00 por número)
        valor_por_numero = 10.00  
        valor_total = float(len(numeros_selecionados) * valor_por_numero)
        
        # Cria a requisição de pagamento via Pix no Mercado Pago
        payment_data = {
            "transaction_amount": valor_total,
            "description": f"Rifa Salário Mínimo - Números {numeros_selecionados}",
            "payment_method_id": "pix",
            "payer": {
                "email": "comprador@email.com", # Email fictício exigido pela API
                "first_name": nome,
                "phone": {
                    "area_code": telefone[:2],
                    "number": telefone[2:]
                }
            }
        }
        
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]
        
        # Pega as informações do Pix de retorno
        payment_id = str(payment.get("id"))
        point_of_interaction = payment.get("point_of_interaction", {})
        transaction_data = point_of_interaction.get("transaction_data", {})
        qr_code = transaction_data.get("qr_code")
        qr_code_base64 = transaction_data.get("qr_code_base64")
        
        # Salva a reserva no Supabase
        for num in numeros_selecionados:
            cur.execute("""
                UPDATE rifas 
                SET status = 'reservado', nome_comprador = %s, telefone = %s, 
                    pix_copia_cola = %s, qr_code = %s, payment_id = %s
                WHERE numero = %s;
            """, (nome, telefone, qr_code, qr_code_base64, payment_id, num))
            
        conn.commit()
        
        return jsonify({
            "sucesso": True,
            "pix_copia_cola": qr_code,
            "qr_code_base64": qr_code_base64,
            "payment_id": payment_id
        })
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"erro": f"Erro interno: {e}"}), 500
    finally:
        if conn:
            conn.close()

@app.route('/admin')
def admin():
    """Painel administrativo para visualizar todas as reservas."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM rifas ORDER BY numero ASC;")
        rifas = cur.fetchall()
        return render_template('admin.html', rifas=rifas)
    except Exception as e:
        return f"Erro no painel: {e}", 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    # Localmente usa a porta 5000 por padrão
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)