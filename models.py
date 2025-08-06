from dataclasses import dataclass
import bcrypt
from datetime import datetime
from enum import Enum, auto
import time
import hashlib

class UserType(Enum):
    NORMAL = 'normal'
    MODERADOR = 'moderador'
    BANIDO = 'banido'

@dataclass
class Usuario:
    id: int
    email: str
    senha_hash: str
    creditos: int = 0
    tipo: UserType = UserType.NORMAL

    @classmethod
    def criar_usuario(cls, email, senha, tipo=UserType.NORMAL):
        salt = bcrypt.gensalt()
        senha_hash = bcrypt.hashpw(senha.encode('utf-8'), salt)
        return cls(id=0, email=email, senha_hash=senha_hash.decode('utf-8'), tipo=tipo)

    def verificar_senha(self, senha):
        try:
            return bcrypt.checkpw(senha.encode('utf-8'), self.senha_hash.encode('utf-8'))
        except:
            return False

    def is_moderador(self):
        return self.tipo == UserType.MODERADOR

    def is_banido(self):
        return self.tipo == UserType.BANIDO


@dataclass
class Livro:
    id: int
    titulo: str
    autor: str
    genero: str
    disponivel: bool = True
    doador_id: int = None
    aprovado: bool = False


@dataclass
class Emprestimo:
    id: int
    usuario_id: int
    livro_id: int
    data_solicitacao: str
    data_retirada: str = None
    status: str = "pendente"  # pendente, retirado, devolvido, cancelado

    @classmethod
    def criar_emprestimo(cls, usuario_id, livro_id):
        return cls(
            id=0,
            usuario_id=usuario_id,
            livro_id=livro_id,
            data_solicitacao=datetime.now().isoformat(),
            status="pendente"
        )


@dataclass
class Doacao:
    id: int
    usuario_id: int
    titulo: str
    autor: str
    genero: str
    data_solicitacao: str
    status: str = "pendente"  # pendente, aprovado, rejeitado, concluido
    qr_code_data: str = None

    @classmethod
    def criar_doacao(cls, usuario_id, titulo, autor, genero):
        return cls(
            id=0,
            usuario_id=usuario_id,
            titulo=titulo,
            autor=autor,
            genero=genero,
            data_solicitacao=datetime.now().isoformat(),
            status="pendente"
        )


class QRCodeType(Enum):
    EMPRESTIMO = auto()
    DEVOLUCAO = auto()
    DOACAO = auto()


class QRCodeData:
    SECRET_KEY = "bibliocomunitaria_secret_123"

    def __init__(self, qr_type: QRCodeType, object_id: int, user_id: int, timestamp: float = None):
        self.qr_type = qr_type
        self.object_id = object_id
        self.user_id = user_id
        self.timestamp = timestamp or time.time()

    def serialize(self) -> str:
        base_str = f"{self.qr_type.name}:{self.object_id}:{self.user_id}:{self.timestamp}"
        security_hash = hashlib.sha256(f"{base_str}{self.SECRET_KEY}".encode()).hexdigest()[:8]
        return f"{base_str}:{security_hash}"

    @classmethod
    def deserialize(cls, qr_str: str):
        try:
            parts = qr_str.split(':')
            if len(parts) != 5:
                return None

            qr_type = QRCodeType[parts[0]]
            object_id = int(parts[1])
            user_id = int(parts[2])
            timestamp = float(parts[3])
            received_hash = parts[4]

            expected_hash = hashlib.sha256(f"{':'.join(parts[:4])}{cls.SECRET_KEY}".encode()).hexdigest()[:8]
            if received_hash != expected_hash:
                return None

            return QRCodeData(qr_type, object_id, user_id, timestamp)
        except:
            return None