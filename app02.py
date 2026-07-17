from flask import Flask, jsonify, request, render_template
import os
import re
import random
import psycopg2
from psycopg2.extras import RealDictCursor
import mercadopago

app = Flask(__name__)

# === CONFIGURAÇÕES DA RIFA DE ELITE ===
VALOR_NUMERO = 10.00  # R$ 10,00 por número

# O token será puxado das variáveis de ambiente do Render ou você pode colocar o seu novo aqui temporariamente para testes locais
MERCADOPAGO_TOKEN = os.environ.get("MERCADOPAGO_TOKEN", "SEU_NOVO_TOKEN_AQUI")

def conectar_banco():
    url_banco = os.environ.get("DATABASE_URL")
    if url_banco:
        return psycopg2.connect(url_banco)
    else:
        # Configuração padrão para teste local usando PostgreSQL
        return psycopg2.connect(
            host="localhost",
            database="postgres",
            user="postgres",
            password="03022007" # Altere para a senha do seu banco local, se necessário
        )

def inicializar_banco():
    """Cria a tabela 'sorteio_salario_minimo' de forma limpa e independente"""
    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sorteio_salario_minimo (
                numero INT PRIMARY KEY,
                status VARCHAR(20) DEFAULT 'Disponível',
                nome_comprador VARCHAR(100),
                telefone VARCHAR(20)
            )
        """)
        conexao.commit()

        cursor.execute("SELECT COUNT(*) FROM sorteio_salario_minimo")
        total = cursor.fetchone()[0]

        if total == 0:
            for i in range(1, 101):
                cursor.execute(
                    "INSERT INTO sorteio_salario_minimo (numero, status) VALUES (%s, 'Disponível')",
                    (i,)
                )
            conexao.commit()
            print("🔥 Tabela 'sorteio_salario_minimo' criada com 100 números!")
            
        cursor.close()
        conexao.close()
    except Exception as e:
        print(f"⚠️ Erro ao inicializar banco: {str(e)}")

# Inicializa o banco assim que o servidor ligar
inicializar_banco()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_painel():
    return render_template('admin.html')

# API para listar os números na tela do comprador
@app.route('/api/numeros', methods=['GET'])
def listar_numeros():
    try:
        conexao = conectar_banco()
        cursor = conexao.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT numero, status, nome_comprador, telefone FROM sorteio_salario_minimo ORDER BY numero ASC")
        numeros = cursor.fetchall()
        cursor.close()
        conexao.close()
        return jsonify(numeros)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# API para reservar e gerar o Pix
@app.route('/api/reservar', methods=['POST'])
def reservar_numeros():
    dados = request.json
    nome = dados.get('nome', 'Comprador Anonimo')
    telefone_bruto = dados.get('telefone', '')
    numeros_escolhidos = dados.get('numeros') 

    if not numeros_escolhidos:
        return jsonify({"erro": "Nenhum número selecionado"}), 400

    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        
        # Validar se algum número já foi pego
        format_strings = ','.join(['%s'] * len(numeros_escolhidos))
        cursor.execute(f"SELECT numero FROM sorteio_salario_minimo WHERE numero IN ({format_strings}) AND status != 'Disponível'", tuple(numeros_escolhidos))
        ocupados = cursor.fetchall()
        
        if ocupados:
            cursor.close()
            conexao.close()
            return jsonify({"erro": f"Os números {[o[0] for o in ocupados]} já foram comprados ou reservados."}), 400

        telefone_limpo = re.sub(r'\D', '', str(telefone_bruto))
        if len(telefone_limpo) < 10:
            return jsonify({"erro": "Digite um WhatsApp válido com DDD."}), 400
        
        ddd = telefone_limpo[:2]
        numero_tel = telefone_limpo[2:]
        valor_total = len(numeros_escolhidos) * VALOR_NUMERO

        # Conecta com a API do Mercado Pago
        mp = mercadopago.SDK(MERCADOPAGO_TOKEN)
        ref_id = f"salariominimo-{'_'.join(map(str, numeros_escolhidos))}"

        payment_data = {
            "transaction_amount": float(valor_total),
            "description": f"Rifa Salário Mínimo - Nr: {numeros_escolhidos}",
            "payment_method_id": "pix",
            "payer": {
                "email": f"cliente_{telefone_limpo}@gmail.com", 
                "first_name": nome,
                "phone": {
                    "area_code": ddd,
                    "number": numero_tel
                },
                "identification": {
                    "type": "CPF",
                    "number": "11122233344"
                }
            },
            "external_reference": ref_id
        }

        pagamento_resposta = mp.payment().create(payment_data)
        pagamento = pagamento_resposta.get("response", {})

        if "point_of_interaction" in pagamento:
            qr_code_copia_cola = pagamento["point_of_interaction"]["transaction_data"]["qr_code"]
            qr_code_base64 = pagamento["point_of_interaction"]["transaction_data"]["qr_code_base64"]
            id_pagamento_mp = pagamento["id"]

            for num in numeros_escolhidos:
                cursor.execute(
                    "UPDATE sorteio_salario_minimo SET nome_comprador=%s, telefone=%s, status='Reservado' WHERE numero=%s",
                    (nome, telefone_limpo, num)
                )
            conexao.commit()
            cursor.close()
            conexao.close()

            return jsonify({
                "status": "Reservado",
                "total": valor_total,
                "id_pagamento": id_pagamento_mp,
                "pix_copia_cola": qr_code_copia_cola,
                "pix_image": qr_code_base64
            })
        else:
            cursor.close()
            conexao.close()
            return jsonify({"erro": f"O Mercado Pago recusou o pagamento. Verifique suas credenciais."}), 400

    except Exception as e:
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

# API para o painel salvar alterações manuais
@app.route('/api/admin/editar-numero', methods=['POST'])
def editar_numero_manual():
    dados = request.json
    numero = dados.get('numero')
    novo_status = dados.get('status')
    novo_nome = dados.get('nome_comprador')
    novo_telefone = dados.get('telefone')

    if novo_status == 'Disponível':
        novo_nome = None
        novo_telefone = None

    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("""
            UPDATE sorteio_salario_minimo 
            SET status = %s, nome_comprador = %s, telefone = %s 
            WHERE numero = %s
        """, (novo_status, novo_nome, novo_telefone, numero))
        conexao.commit()
        cursor.close()
        conexao.close()
        return jsonify({"sucesso": True})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# API para buscar participantes pagos para o sorteio interativo
@app.route('/api/admin/participantes-pagos', methods=['GET'])
def buscar_participantes_pagos():
    try:
        conexao = conectar_banco()
        cursor = conexao.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT numero, nome_comprador, telefone FROM sorteio_salario_minimo WHERE status = 'Pago'")
        participantes = cursor.fetchall()
        cursor.close()
        conexao.close()
        return jsonify(participantes)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# API para resetar a Rifa
@app.route('/api/admin/reset', methods=['POST'])
def resetar_rifa():
    try:
        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute("UPDATE sorteio_salario_minimo SET nome_comprador=NULL, telefone=NULL, status='Disponível'")
        conexao.commit()
        cursor.close()
        conexao.close()
        return jsonify({"sucesso": True})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)