import csv
import os
from datetime import datetime
import tempfile
from models import Usuario, Livro, Emprestimo, Doacao, UserType, QRCodeType, QRCodeData
import qrcode
from io import BytesIO
from abc import ABC, abstractmethod
from dataclasses import asdict

class QRCodeStrategy(ABC):
    @abstractmethod
    def process(self, data):
        pass

class EmprestimoQRStrategy(QRCodeStrategy):
    def process(self, qr_data: QRCodeData):
        db = DatabaseSingleton.instance()
        emprestimo = db.get_emprestimo_by_id(qr_data.object_id)

        if not emprestimo or emprestimo.usuario_id != qr_data.user_id:
            return False, "Empréstimo não encontrado"

        if emprestimo.status == "pendente":
            db.atualizar_status_emprestimo(emprestimo.id, "retirado")
            return True, "Livro retirado com sucesso"
        return False, "Status inválido para empréstimo"

class DevolucaoQRStrategy(QRCodeStrategy):
    def process(self, qr_data: QRCodeData):
        db = DatabaseSingleton.instance()
        emprestimo = db.get_emprestimo_by_id(qr_data.object_id)

        if not emprestimo or emprestimo.usuario_id != qr_data.user_id:
            return False, "Empréstimo não encontrado"

        if emprestimo.status == "retirado":
            db.atualizar_status_emprestimo(emprestimo.id, "devolvido")
            return True, "Livro devolvido com sucesso"
        return False, "Status inválido para devolução"

class DoacaoQRStrategy(QRCodeStrategy):
    def process(self, qr_data: QRCodeData):
        db = DatabaseSingleton.instance()
        doacao = db.get_doacao_by_id(qr_data.object_id)

        if not doacao or doacao.usuario_id != qr_data.user_id:
            return False, "Doação não encontrada"

        if doacao.status == "aprovado":
            livro = Livro(
                id=0,
                titulo=doacao.titulo,
                autor=doacao.autor,
                genero=doacao.genero,
                disponivel=True,
                doador_id=doacao.usuario_id,
                aprovado=True
            )

            if db.adicionar_livro(livro):
                db.atualizar_status_doacao(doacao.id, "concluido")
                CreditSystem().adicionar_creditos(doacao.usuario_id, 9)
                return True, "Doação concluída! +9 créditos"
        return False, "Doação não pode ser processada"


class QRCodeProcessor:
    def __init__(self):
        self._initialize_strategies()

    def _initialize_strategies(self):
        """Garante que as estratégias sejam inicializadas corretamente"""
        self.strategies = {
            QRCodeType.EMPRESTIMO: EmprestimoQRStrategy(),
            QRCodeType.DEVOLUCAO: DevolucaoQRStrategy(),
            QRCodeType.DOACAO: DoacaoQRStrategy()
        }
        print("Estratégias de QR Code inicializadas:", self.strategies.keys())  # Log de depuração

    def process(self, qr_data_str: str):
        try:
            # Limpeza da string do QR Code
            qr_data_str = qr_data_str.strip().strip("('").strip("',)")
            print(f"Processando QR Code: {qr_data_str}")  # Log de depuração

            if not hasattr(self, 'strategies'):
                self._initialize_strategies()

            qr_data = QRCodeData.deserialize(qr_data_str)
            if not qr_data:
                return False, "QR Code inválido ou corrompido"

            strategy = self.strategies.get(qr_data.qr_type)
            if not strategy:
                return False, f"Tipo de QR Code não suportado: {qr_data.qr_type}"

            return strategy.process(qr_data)
        except Exception as e:
            print(f"Erro no processamento do QR Code: {str(e)}")  # Log detalhado
            return False, f"Erro no processamento: {str(e)}"

# Padrão Singleton para Database
class DatabaseSingleton:
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Inicializa todos os arquivos CSV necessários"""
        os.makedirs('data', exist_ok=True)
        for file_type in CSVManager.HEADERS:
            filename = f"{file_type}.csv"
            if not os.path.exists(f"data/{filename}") or os.stat(f"data/{filename}").st_size == 0:
                CSVManager.safe_write(filename, [])

    def _get_next_id(self, filename):
        data = CSVManager.safe_read(filename)
        if not data:
            return 1
        try:
            return max(int(row['id']) for row in data) + 1
        except:
            return 1

    # Métodos para usuários
    def get_usuario_by_email(self, email):
        usuarios = CSVManager.safe_read('usuarios.csv')
        for usuario in usuarios:
            if usuario['email'] == email:
                return Usuario(
                    id=int(usuario['id']),
                    email=usuario['email'],
                    senha_hash=usuario['senha_hash'],
                    creditos=int(usuario['creditos']),
                    tipo=UserType(usuario.get('tipo', 'normal'))
                )
        return None

    def get_usuario_by_id(self, usuario_id):
        usuarios = CSVManager.safe_read('usuarios.csv')
        for usuario in usuarios:
            if int(usuario['id']) == usuario_id:
                return Usuario(
                    id=int(usuario['id']),
                    email=usuario['email'],
                    senha_hash=usuario['senha_hash'],
                    creditos=int(usuario['creditos']),
                    tipo=UserType(usuario.get('tipo', 'normal'))
                )
        return None

    def adicionar_usuario(self, usuario):
        usuarios = CSVManager.safe_read('usuarios.csv')
        usuario.id = self._get_next_id('usuarios.csv')
        usuario_dict = {
            'id': usuario.id,
            'email': usuario.email,
            'senha_hash': usuario.senha_hash,
            'creditos': usuario.creditos,
            'tipo': usuario.tipo.value
        }
        usuarios.append(usuario_dict)
        return CSVManager.safe_write('usuarios.csv', usuarios)

    def get_usuarios(self):
        usuarios = CSVManager.safe_read('usuarios.csv')
        return [Usuario(
            id=int(u['id']),
            email=u['email'],
            senha_hash=u['senha_hash'],
            creditos=int(u['creditos']),
            tipo=UserType(u.get('tipo', 'normal')))
            for u in usuarios]

    def banir_usuario(self, usuario_id):
        usuarios = CSVManager.safe_read('usuarios.csv')
        updated = False

        for usuario in usuarios:
            if int(usuario['id']) == usuario_id:
                usuario['tipo'] = UserType.BANIDO.value
                updated = True
                break

        if updated:
            return CSVManager.safe_write('usuarios.csv', usuarios)
        return False

    # Métodos para livros
    def get_livro_by_id(self, livro_id):
        livros = CSVManager.safe_read('livros.csv')
        for livro in livros:
            if int(livro['id']) == livro_id:
                return Livro(
                    id=int(livro['id']),
                    titulo=livro['titulo'],
                    autor=livro['autor'],
                    genero=livro['genero'],
                    disponivel=livro['disponivel'].lower() == 'true',
                    doador_id=int(livro['doador_id']) if livro['doador_id'] else None,
                    aprovado=livro.get('aprovado', 'false').lower() == 'true'
                )
        return None

    def get_livros_disponiveis(self):
        livros = []
        for livro in CSVManager.safe_read('livros.csv'):
            if livro['disponivel'].lower() == 'true' and livro.get('aprovado', 'true').lower() == 'true':
                livros.append(Livro(
                    id=int(livro['id']),
                    titulo=livro['titulo'],
                    autor=livro['autor'],
                    genero=livro['genero'],
                    disponivel=True,
                    doador_id=int(livro['doador_id']) if livro['doador_id'] else None,
                    aprovado=True
                ))
        return livros

    def adicionar_livro(self, livro):
        livros = CSVManager.safe_read('livros.csv')
        livro.id = self._get_next_id('livros.csv')
        livros.append({
            'id': livro.id,
            'titulo': livro.titulo,
            'autor': livro.autor,
            'genero': livro.genero,
            'disponivel': str(livro.disponivel).lower(),
            'doador_id': livro.doador_id if livro.doador_id else '',
            'aprovado': str(livro.aprovado).lower()
        })
        return CSVManager.safe_write('livros.csv', livros)

    # Métodos para empréstimos
    def get_emprestimo_by_id(self, emprestimo_id):
        emprestimos = CSVManager.safe_read('emprestimos.csv')
        for emp in emprestimos:
            if int(emp['id']) == emprestimo_id:
                return Emprestimo(
                    id=int(emp['id']),
                    usuario_id=int(emp['usuario_id']),
                    livro_id=int(emp['livro_id']),
                    data_solicitacao=emp['data_solicitacao'],
                    data_retirada=emp.get('data_retirada'),
                    status=emp['status']
                )
        return None

    def get_emprestimos_por_usuario(self, usuario_id):
        emprestimos = []
        for emp in CSVManager.safe_read('emprestimos.csv'):
            if int(emp['usuario_id']) == usuario_id:
                livro = self.get_livro_by_id(int(emp['livro_id']))
                if livro:
                    emprestimos.append({
                        'id': int(emp['id']),
                        'livro': livro,
                        'data_solicitacao': emp['data_solicitacao'],
                        'status': emp['status']
                    })
        return emprestimos

    def adicionar_emprestimo(self, emprestimo):
        emprestimos = CSVManager.safe_read('emprestimos.csv')
        emprestimo.id = self._get_next_id('emprestimos.csv')
        emprestimos.append({
            'id': emprestimo.id,
            'usuario_id': emprestimo.usuario_id,
            'livro_id': emprestimo.livro_id,
            'data_solicitacao': emprestimo.data_solicitacao,
            'data_retirada': emprestimo.data_retirada if emprestimo.data_retirada else '',
            'status': emprestimo.status
        })
        return CSVManager.safe_write('emprestimos.csv', emprestimos)

    def cancelar_emprestimo(self, emprestimo_id):
        emprestimos = CSVManager.safe_read('emprestimos.csv')
        updated = False

        for emp in emprestimos:
            if int(emp['id']) == emprestimo_id and emp['status'] == 'pendente':
                emp['status'] = 'cancelado'
                updated = True
                break

        if updated:
            return CSVManager.safe_write('emprestimos.csv', emprestimos)
        return False

    def atualizar_status_emprestimo(self, emprestimo_id, novo_status):
        emprestimos = CSVManager.safe_read('emprestimos.csv')
        livros = CSVManager.safe_read('livros.csv')
        updated = False

        for emp in emprestimos:
            if int(emp['id']) == emprestimo_id:
                emp['status'] = novo_status

                if novo_status == 'retirado':
                    emp['data_retirada'] = datetime.now().isoformat()
                    for livro in livros:
                        if int(livro['id']) == int(emp['livro_id']):
                            livro['disponivel'] = 'False'
                            break

                elif novo_status == 'devolvido':
                    for livro in livros:
                        if int(livro['id']) == int(emp['livro_id']):
                            livro['disponivel'] = 'True'
                            break

                updated = True
                break

        if updated:
            CSVManager.safe_write('emprestimos.csv', emprestimos)
            CSVManager.safe_write('livros.csv', livros)
            return True
        return False

    # Métodos para doações
    def adicionar_doacao(self, doacao):
        doacoes = CSVManager.safe_read('doacoes.csv')
        doacao.id = self._get_next_id('doacoes.csv')
        doacao_dict = {
            'id': doacao.id,
            'usuario_id': doacao.usuario_id,
            'titulo': doacao.titulo,
            'autor': doacao.autor,
            'genero': doacao.genero,
            'data_solicitacao': doacao.data_solicitacao,
            'status': doacao.status,
            'qr_code_data': doacao.qr_code_data if doacao.qr_code_data else ''
        }
        doacoes.append(doacao_dict)
        return CSVManager.safe_write('doacoes.csv', doacoes)

    def get_doacao_by_id(self, doacao_id):
        doacoes = CSVManager.safe_read('doacoes.csv')
        for doacao in doacoes:
            if int(doacao['id']) == doacao_id:
                return Doacao(
                    id=int(doacao['id']),
                    usuario_id=int(doacao['usuario_id']),
                    titulo=doacao['titulo'],
                    autor=doacao['autor'],
                    genero=doacao['genero'],
                    data_solicitacao=doacao['data_solicitacao'],
                    status=doacao['status'],
                    qr_code_data=doacao.get('qr_code_data')
                )
        return None

    def get_doacoes_pendentes(self):
        doacoes = CSVManager.safe_read('doacoes.csv')
        return [Doacao(
            id=int(d['id']),
            usuario_id=int(d['usuario_id']),
            titulo=d['titulo'],
            autor=d['autor'],
            genero=d['genero'],
            data_solicitacao=d['data_solicitacao'],
            status=d['status'],
            qr_code_data=d.get('qr_code_data')
        ) for d in doacoes if d['status'] == 'pendente']

    def get_doacoes_por_usuario(self, usuario_id):
        doacoes = CSVManager.safe_read('doacoes.csv')
        return [Doacao(
            id=int(d['id']),
            usuario_id=int(d['usuario_id']),
            titulo=d['titulo'],
            autor=d['autor'],
            genero=d['genero'],
            data_solicitacao=d['data_solicitacao'],
            status=d['status'],
            qr_code_data=d.get('qr_code_data')
        ) for d in doacoes if int(d['usuario_id']) == usuario_id]

    def atualizar_status_doacao(self, doacao_id, novo_status):
        doacoes = CSVManager.safe_read('doacoes.csv')
        updated = False

        for doacao in doacoes:
            if int(doacao['id']) == doacao_id:
                doacao['status'] = novo_status
                updated = True
                break

        if updated:
            return CSVManager.safe_write('doacoes.csv', doacoes)
        return False

    def atualizar_doacao(self, doacao):
        doacoes = CSVManager.safe_read('doacoes.csv')
        updated = False

        for d in doacoes:
            if int(d['id']) == doacao.id:
                d.update({
                    'status': doacao.status,
                    'qr_code_data': doacao.qr_code_data if doacao.qr_code_data else ''
                })
                updated = True
                break

        if updated:
            return CSVManager.safe_write('doacoes.csv', doacoes)
        return False

    def atualizar_qr_code_doacao(self, doacao_id, qr_data):
        doacoes = CSVManager.safe_read('doacoes.csv')
        updated = False

        for doacao in doacoes:
            if int(doacao['id']) == doacao_id:
                doacao['qr_code_data'] = qr_data
                updated = True
                break

        if updated:
            return CSVManager.safe_write('doacoes.csv', doacoes)
        return False

# Padrão Factory para QR Code Generator
class QRCodeGenerator:
    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        try:
            import qrcode
            from PIL import Image
            self.available = True
        except ImportError:
            self.available = False

    def generate(self, data, fill_color="black", back_color="white"):
        if not self.available:
            raise ImportError("Bibliotecas para QR Code não estão disponíveis")

        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        return qr.make_image(fill_color=fill_color, back_color=back_color)


# Padrão Facade para o sistema de créditos
class CreditSystem:
    def adicionar_creditos(self, usuario_id, quantidade):
        db = DatabaseSingleton.instance()
        usuario = db.get_usuario_by_id(usuario_id)
        if not usuario:
            return False

        usuario.creditos += quantidade
        return self._atualizar_usuario(usuario)

    def deduzir_creditos(self, usuario_id, quantidade):
        db = DatabaseSingleton.instance()
        usuario = db.get_usuario_by_id(usuario_id)
        if not usuario or usuario.creditos < quantidade:
            return False

        usuario.creditos -= quantidade
        return self._atualizar_usuario(usuario)

    def tem_creditos_suficientes(self, usuario_id, quantidade):
        db = DatabaseSingleton.instance()
        usuario = db.get_usuario_by_id(usuario_id)
        return usuario and usuario.creditos >= quantidade

    def _atualizar_usuario(self, usuario):
        db = DatabaseSingleton.instance()
        usuarios = CSVManager.safe_read('usuarios.csv')
        updated = False

        for u in usuarios:
            if int(u['id']) == usuario.id:
                u['creditos'] = usuario.creditos
                updated = True
                break

        if updated:
            return CSVManager.safe_write('usuarios.csv', usuarios)
        return False


# Padrão Observer para Logger
class Logger:
    def log(self, mensagem):
        transacoes = CSVManager.safe_read('transacoes.csv')
        transacoes.append({
            'data': datetime.now().isoformat(),
            'mensagem': mensagem
        })
        CSVManager.safe_write('transacoes.csv', transacoes)


# Padrão Factory para criação de livros
class LivroFactory:
    @staticmethod
    def criar_livro(titulo, autor, genero, doador_id=None):
        return Livro(
            id=0,
            titulo=titulo,
            autor=autor,
            genero=genero,
            disponivel=True,
            doador_id=doador_id,
            aprovado=False
        )


# Padrão Template Method para CSVManager
class CSVManager:
    # Definição centralizada dos cabeçalhos
    HEADERS = {
        'usuarios': ['id', 'email', 'senha_hash', 'creditos', 'tipo'],
        'livros': ['id', 'titulo', 'autor', 'genero', 'disponivel', 'doador_id', 'aprovado'],
        'emprestimos': ['id', 'usuario_id', 'livro_id', 'data_solicitacao', 'data_retirada', 'status'],
        'transacoes': ['data', 'mensagem'],
        'doacoes': ['id', 'usuario_id', 'titulo', 'autor', 'genero', 'data_solicitacao', 'status', 'qr_code_data']
    }

    @classmethod
    def safe_write(cls, filename, data):
        """Escreve dados em CSV de forma segura e atômica"""
        file_type = filename.replace('.csv', '').replace('data/', '')

        if file_type not in cls.HEADERS:
            raise ValueError(f"Tipo de arquivo desconhecido: {filename}")

        filepath = f"data/{filename}" if not filename.startswith('data/') else filename
        temp_path = f"{filepath}.tmp"

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(temp_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=cls.HEADERS[file_type])
                writer.writeheader()
                if data:
                    writer.writerows(data)

            os.replace(temp_path, filepath)
            return True
        except Exception as e:
            print(f"Erro ao escrever {filename}: {str(e)}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False

    @classmethod
    def safe_read(cls, filename):
        """Lê um arquivo CSV com tratamento de erros robusto"""
        file_type = filename.replace('.csv', '').replace('data/', '')
        filepath = f"data/{filename}" if not filename.startswith('data/') else filename

        if not os.path.exists(filepath):
            return []

        try:
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or set(reader.fieldnames) != set(cls.HEADERS[file_type]):
                    raise ValueError("Cabeçalho inválido ou ausente")
                return list(reader)
        except Exception as e:
            print(f"Erro ao ler {filename}: {str(e)}")
            cls._repair_csv(filepath, file_type)
            return []

    @classmethod
    def _repair_csv(cls, filepath, file_type):
        """Tenta reparar um arquivo CSV corrompido"""
        backup_path = f"{filepath}.bak"
        try:
            os.rename(filepath, backup_path)
            print(f"Arquivo {filepath} corrompido - criando novo")
            cls.safe_write(filepath, [])
            return True
        except Exception as e:
            print(f"Falha ao reparar {filepath}: {str(e)}")
            return False