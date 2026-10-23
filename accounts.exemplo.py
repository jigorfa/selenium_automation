"""Copie este arquivo para "accounts.py" (na mesma pasta do programa) e preencha.

NÃO compartilhe o accounts.py: ele guarda a senha e a chave em texto puro.
"""
EFFECTI = {
    "username": "seu-usuario-do-effecti",
    "password": "sua-senha-do-effecti",
}

# Só é preciso se o Claude for usado pela API paga (CLAUDE_MODO = "api" no config.py).
# Pela assinatura (padrão), deixe vazio: o login é feito pelo menu do programa.
# A chave é criada em https://platform.claude.com/settings/keys e começa com "sk-ant-".
CLAUDE = {
    "api_key": "",
}
