from utils import DatabaseSingleton, CreditSystem  # Importação corrigida
from models import Usuario
import os
import shutil


def reset_database():
    # Limpa a pasta de dados
    if os.path.exists('data'):
        shutil.rmtree('data')

    # Cria instância do banco de dados
    db = DatabaseSingleton.instance()

    # Cria usuário admin
    admin = Usuario.criar_usuario("admin@biblioteca.com", "admin123")
    db.adicionar_usuario(admin)

    # Adiciona créditos
    credit_system = CreditSystem()
    credit_system.adicionar_creditos(admin.id, 10)

    print("=" * 50)
    print("Banco de dados reinicializado com sucesso!")
    print(f"Usuário admin criado:")
    print(f"Email: admin@biblioteca.com")
    print(f"Senha: admin123")
    print(f"Créditos iniciais: 10")
    print("=" * 50)


if __name__ == '__main__':
    reset_database()