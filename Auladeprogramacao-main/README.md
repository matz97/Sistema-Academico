# Sistema Academico Web

Sistema academico desenvolvido em Python com Flask. A aplicacao permite
gerenciar alunos, professores, disciplinas, matriculas, boletins, usuarios,
perfis de acesso e relatorios em JSON/PDF.

O sistema usa MySQL quando disponivel. Se o MySQL nao estiver acessivel, usa
automaticamente um banco SQLite local para facilitar testes.

## Funcionalidades

- Login com senha criptografada para usuarios cadastrados.
- Perfis de acesso: admin, professor e aluno.
- Admin gerencia alunos, professores, disciplinas, matriculas e usuarios.
- Professor consulta boletins dos alunos das suas disciplinas e gerencia notas.
- Aluno consulta somente o proprio boletim.
- Remocao logica de matriculas, mantendo historico no banco.
- Relatorios em JSON e PDF.
- Busca em tabelas pela interface.

## Acesso inicial

Existe um login administrativo de desenvolvimento configurado por variaveis de
ambiente:

```text
Usuario: teste123
Senha: 12345
Perfil: admin
```

Esses valores podem ser alterados com `LOGIN_USER` e `LOGIN_PASSWORD`.

## Instalar dependencias

```bash
python -m pip install -r requirements.txt
```

## Rodar com SQLite local

```bash
python app.py
```

Depois acesse:

```text
http://127.0.0.1:5000
```

## Rodar com MySQL

Crie o banco e as tabelas:

```bash
mysql -u root -p < schema.sql
```

Configure as variaveis de ambiente, se necessario:

```powershell
$env:MYSQL_HOST="localhost"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="sua_senha"
$env:MYSQL_DATABASE="sistema_academico"
```

No Linux/macOS, use `export`.

Para obrigar o uso do MySQL:

```powershell
$env:MYSQL_REQUIRED="1"
python app.py
```

## Variaveis de ambiente

```text
FLASK_SECRET_KEY  Chave de sessao do Flask.
FLASK_DEBUG       Ativa debug somente quando 1/true/yes.
LOGIN_USER        Usuario admin inicial de desenvolvimento.
LOGIN_PASSWORD    Senha do admin inicial de desenvolvimento.
MYSQL_HOST        Host do MySQL.
MYSQL_PORT        Porta do MySQL.
MYSQL_USER        Usuario do MySQL.
MYSQL_PASSWORD    Senha do MySQL.
MYSQL_DATABASE    Nome do banco MySQL.
MYSQL_REQUIRED    Se 1/true/yes, falha quando MySQL nao conectar.
SQLITE_PATH       Caminho do banco SQLite local.
```

## Principais arquivos

```text
app.py               Rotas, login, perfis e regras da aplicacao web.
db.py                Conexao MySQL/SQLite, criacao e migracao basica de schema.
relatorios.py        Geracao de relatorios JSON e PDF.
schema.sql           Script de criacao do banco MySQL.
templates/           Paginas HTML.
static/styles.css    Estilos da interface.
static/search.js     Busca em tabelas.
Sistema_academico.py Prototipo orientado a objetos executavel pelo terminal.
documentacao.txt     Documentacao completa do sistema.
```

## Documentacao completa

Consulte `documentacao.txt` para detalhes de arquitetura, banco de dados,
perfis de acesso, rotas, regras de negocio e plano de evolucao.
