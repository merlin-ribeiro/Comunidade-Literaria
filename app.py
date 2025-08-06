from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_file
from datetime import datetime, timedelta
from functools import wraps
from models import Usuario, Livro, Emprestimo, Doacao, UserType, QRCodeType, QRCodeData
from utils import DatabaseSingleton, QRCodeGenerator, CreditSystem, Logger, LivroFactory, QRCodeProcessor
import os
import io
import qrcode
from datetime import datetime


def format_datetime(value, format='%d/%m/%Y %H:%M'):
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime(format)


app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

app.jinja_env.filters['format_datetime'] = format_datetime
app.jinja_env.globals['UserType'] = UserType

db = DatabaseSingleton.instance()
credit_system = CreditSystem()
logger = Logger()
qr_processor = QRCodeProcessor()
print("QRCodeProcessor inicializado com estratégias:", [s.__class__.__name__ for s in qr_processor.strategies.values()])


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login primeiro', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def moderador_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, faça login primeiro', 'warning')
            return redirect(url_for('login'))
        user = db.get_usuario_by_id(session['user_id'])
        if not user or not user.is_moderador():
            flash('Acesso restrito a moderadores', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


@app.context_processor
def inject_user():
    if 'user_id' in session:
        user = db.get_usuario_by_id(session['user_id'])
        return {'usuario': user}
    return {}


@app.before_request
def load_user():
    g.user = None
    if 'user_id' in session:
        user = db.get_usuario_by_id(session['user_id'])
        if not user or user.is_banido():
            session.clear()
            flash('Sua conta foi banida', 'error')
            return redirect(url_for('login'))
        else:
            g.user = user


@app.route('/', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '').strip()

        if 'cadastro' in request.form:
            if db.get_usuario_by_email(email):
                flash('Email já cadastrado!', 'error')
            else:
                novo_usuario = Usuario.criar_usuario(email, senha)
                db.adicionar_usuario(novo_usuario)
                credit_system.adicionar_creditos(novo_usuario.id, 6)
                flash('Cadastro realizado com sucesso!', 'success')
                return redirect(url_for('login'))
        else:
            usuario = db.get_usuario_by_email(email)
            if usuario and usuario.verificar_senha(senha):
                session.clear()
                session['user_id'] = usuario.id
                return redirect(url_for('index'))
            flash('Credenciais inválidas!', 'error')

    return render_template('cadastrologin.html')


@app.route('/index')
@login_required
def index():
    return render_template('index.html')

@app.route('/emprestimo', methods=['GET', 'POST'])
@login_required
def emprestimo():
    if request.method == 'POST':
        if 'solicitar' in request.form:
            livro_id = int(request.form.get('livro_id', 0))
            if credit_system.tem_creditos_suficientes(g.user.id, 3):
                emprestimo = Emprestimo.criar_emprestimo(g.user.id, livro_id)
                if db.adicionar_emprestimo(emprestimo):
                    credit_system.deduzir_creditos(g.user.id, 3)
                    flash('Empréstimo solicitado com sucesso!', 'success')
                else:
                    flash('Erro ao processar empréstimo', 'error')
            else:
                flash('Créditos insuficientes!', 'error')

        elif 'cancelar' in request.form:
            emprestimo_id = int(request.form.get('emprestimo_id', 0))
            if db.cancelar_emprestimo(emprestimo_id):
                credit_system.adicionar_creditos(g.user.id, 3)
                flash('Empréstimo cancelado!', 'success')
            else:
                flash('Erro ao cancelar empréstimo', 'error')

    livros = [livro for livro in db.get_livros_disponiveis() if livro.aprovado]
    emprestimos = db.get_emprestimos_por_usuario(g.user.id)
    return render_template('emprestimo.html', livros=livros, emprestimos=emprestimos)

@app.route('/gerar_qrcode/<tipo>/<int:object_id>')
@login_required
def gerar_qrcode(tipo, object_id):
    try:
        qr_type = QRCodeType[tipo.upper()]
        qr_data = QRCodeData(
            qr_type=qr_type,
            object_id=object_id,
            user_id=g.user.id
        ).serialize()

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        logger.log(f"QRCode gerado para {tipo}: {object_id}")
        return send_file(buffer, mimetype='image/png')

    except KeyError:
        flash('Tipo de QR Code inválido', 'error')
    except Exception as e:
        flash(f'Erro ao gerar QR Code: {str(e)}', 'error')

    if tipo.upper() == 'EMPRESTIMO':
        return redirect(url_for('emprestimo'))
    elif tipo.upper() == 'DOACAO':
        return redirect(url_for('minhas_doacoes'))
    else:
        return redirect(url_for('index'))


@app.route('/doacao', methods=['GET', 'POST'])
@login_required
def doacao():
    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        autor = request.form.get('autor', '').strip()
        genero = request.form.get('genero', '').strip()

        if titulo and autor and genero:
            doacao = Doacao.criar_doacao(g.user.id, titulo, autor, genero)
            if db.adicionar_doacao(doacao):
                flash('Solicitação de doação enviada para aprovação!', 'success')
                return redirect(url_for('doacao'))
            else:
                flash('Erro ao registrar doação', 'error')
        else:
            flash('Preencha todos os campos', 'error')

    return render_template('doacao.html')


@app.route('/minhas_doacoes')
@login_required
def minhas_doacoes():
    doacoes = db.get_doacoes_por_usuario(g.user.id)
    return render_template('minhas_doacoes.html', doacoes=doacoes)

@app.route('/requisicoes')
@moderador_required
def requisicoes():
    doacoes_pendentes = db.get_doacoes_pendentes()
    usuarios = db.get_usuarios()
    return render_template('requisicoes.html',
                           doacoes=doacoes_pendentes,
                           usuarios=usuarios)

@app.route('/aprovar_doacao/<int:doacao_id>')
@moderador_required
def aprovar_doacao(doacao_id):
    if not db.atualizar_status_doacao(doacao_id, 'aprovado'):
        flash('Erro ao atualizar status da doação', 'error')
        return redirect(url_for('requisicoes'))

    doacao = db.get_doacao_by_id(doacao_id)
    if not doacao:
        flash('Doação não encontrada', 'error')
        return redirect(url_for('requisicoes'))

    qr_data = f"{doacao.id},{doacao.titulo},{doacao.usuario_id},{datetime.now().isoformat()},doacao"
    if not db.atualizar_qr_code_doacao(doacao_id, qr_data):
        flash('Erro ao gerar QR Code', 'error')
        return redirect(url_for('requisicoes'))

    flash('Doação aprovada com sucesso! O doador deve apresentar o QR Code na estante', 'success')
    return redirect(url_for('requisicoes'))


@app.route('/rejeitar_doacao/<int:doacao_id>')
@moderador_required
def rejeitar_doacao(doacao_id):
    if db.atualizar_status_doacao(doacao_id, 'rejeitado'):
        flash('Doação rejeitada', 'success')
    else:
        flash('Erro ao rejeitar doação', 'error')
    return redirect(url_for('requisicoes'))


@app.route('/banir_usuario/<int:usuario_id>')
@moderador_required
def banir_usuario(usuario_id):
    if db.banir_usuario(usuario_id):
        flash('Usuário banido com sucesso', 'success')
    else:
        flash('Erro ao banir usuário', 'error')
    return redirect(url_for('requisicoes'))


@app.route('/api/process_qr', methods=['POST'])
def api_process_qr():
    qr_data_str = request.json.get('qr_data')
    if not qr_data_str:
        return {'success': False, 'message': 'Dados inválidos'}, 400

    success, message = QRCodeProcessor().process(qr_data_str)
    return {'success': success, 'message': message}


@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado com sucesso', 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    app.run(debug=True)