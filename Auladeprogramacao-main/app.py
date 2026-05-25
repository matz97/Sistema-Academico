import os
from io import BytesIO

from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for
from mysql.connector import Error
from werkzeug.security import check_password_hash, generate_password_hash

from db import IntegrityError, database_label, execute, fetch_all, fetch_one, is_sqlite
from relatorios import gerar_relatorio_json, gerar_relatorio_pdf


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "sistema-academico-dev")

LOGIN_USER = os.getenv("LOGIN_USER", "teste123")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "12345")
PERFIS = {"admin", "professor", "aluno"}


def parse_nota(valor):
    valor = valor.strip().replace(",", ".")

    if not valor:
        return None

    nota = float(valor)
    if nota < 0 or nota > 10:
        raise ValueError

    return nota


def parse_carga_horaria(valor):
    carga_horaria = int(valor.strip())
    if carga_horaria < 1:
        raise ValueError

    return carga_horaria


def form_campos_obrigatorios(campos):
    dados = {}
    faltando = []

    for nome, rotulo in campos.items():
        valor = request.form.get(nome, "").strip()
        dados[nome] = valor
        if not valor:
            faltando.append(rotulo)

    if faltando:
        flash("Preencha os campos obrigatorios: " + ", ".join(faltando) + ".", "warning")
        return None

    return dados


def flask_debug_ativo():
    return os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}


def perfil_atual():
    return session.get("perfil", "admin")


def usuario_admin():
    return perfil_atual() == "admin"


def usuario_professor():
    return perfil_atual() == "professor"


def usuario_aluno():
    return perfil_atual() == "aluno"


def exigir_perfil(*perfis):
    if perfil_atual() in perfis:
        return True

    flash("Seu perfil nao tem permissao para acessar esta area.", "warning")
    return False


def professor_pode_editar_matricula(matricula_id):
    if usuario_admin():
        return True

    professor_id = session.get("professor_id")
    if not professor_id:
        return False

    matricula = fetch_one(
        """
        SELECT m.id
          FROM matriculas m
          JOIN disciplinas d ON d.id = m.disciplina_id
         WHERE m.id = %s AND d.professor_id = %s
        """,
        (matricula_id, professor_id),
    )
    return bool(matricula)


@app.context_processor
def incluir_perfil_usuario():
    return {
        "perfil_atual": perfil_atual,
        "usuario_admin": usuario_admin,
        "usuario_professor": usuario_professor,
        "usuario_aluno": usuario_aluno,
    }


@app.before_request
def exigir_login():
    rotas_livres = {"login", "static"}

    if request.endpoint in rotas_livres or session.get("usuario_logado"):
        return None

    return redirect(url_for("login", next=request.full_path))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("usuario_logado"):
        return redirect(url_for("index"))

    if request.method == "POST":
        usuario = request.form["usuario"].strip()
        senha = request.form["senha"]
        usuario_cadastrado = fetch_one(
            """
            SELECT usuario, senha_hash, perfil, aluno_id, professor_id
              FROM usuarios
             WHERE usuario = %s
            """,
            (usuario,),
        )

        senha_valida = usuario == LOGIN_USER and senha == LOGIN_PASSWORD
        perfil = "admin"
        aluno_id = None
        professor_id = None
        if usuario_cadastrado:
            senha_valida = check_password_hash(usuario_cadastrado["senha_hash"], senha)
            perfil = usuario_cadastrado.get("perfil") or "admin"
            aluno_id = usuario_cadastrado.get("aluno_id")
            professor_id = usuario_cadastrado.get("professor_id")

        if senha_valida:
            session["usuario_logado"] = usuario
            session["perfil"] = perfil
            session["aluno_id"] = aluno_id
            session["professor_id"] = professor_id
            flash("Login realizado com sucesso.", "success")
            destino = request.args.get("next") or url_for("index")
            return redirect(destino)

        flash("Usuario ou senha invalidos.", "warning")

    return render_template("login.html")


def get_opcoes_vinculo():
    return {
        "alunos": fetch_all("SELECT id, nome, matricula FROM alunos ORDER BY nome"),
        "professores": fetch_all(
            "SELECT id, nome, registro FROM professores ORDER BY nome"
        ),
    }


def validar_dados_usuario(perfil, aluno_id, professor_id):
    if perfil not in PERFIS:
        flash("Selecione um perfil valido.", "warning")
        return False
    if perfil == "aluno" and not aluno_id:
        flash("Selecione o aluno vinculado a este acesso.", "warning")
        return False
    if perfil == "professor" and not professor_id:
        flash("Selecione o professor vinculado a este acesso.", "warning")
        return False
    return True


@app.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    if request.method == "POST":
        usuario = request.form["usuario"].strip()
        senha = request.form["senha"]
        confirmar_senha = request.form["confirmar_senha"]
        perfil = request.form.get("perfil", "aluno")
        aluno_id = request.form.get("aluno_id") or None
        professor_id = request.form.get("professor_id") or None

        if len(usuario) < 3:
            flash("O usuario precisa ter pelo menos 3 caracteres.", "warning")
        elif len(senha) < 4:
            flash("A senha precisa ter pelo menos 4 caracteres.", "warning")
        elif senha != confirmar_senha:
            flash("As senhas nao conferem.", "warning")
        elif not validar_dados_usuario(perfil, aluno_id, professor_id):
            pass
        else:
            if perfil != "aluno":
                aluno_id = None
            if perfil != "professor":
                professor_id = None

            try:
                execute(
                    """
                    INSERT INTO usuarios (usuario, senha_hash, perfil, aluno_id, professor_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        usuario,
                        generate_password_hash(senha),
                        perfil,
                        aluno_id,
                        professor_id,
                    ),
                )
                flash("Usuario cadastrado com sucesso.", "success")
                return redirect(url_for("usuarios"))
            except IntegrityError:
                flash("Ja existe um usuario com esse nome.", "warning")

    lista = fetch_all(
        """
        SELECT u.id, u.usuario, u.perfil, u.aluno_id, u.professor_id, u.criado_em,
               a.nome AS aluno, a.matricula,
               p.nome AS professor, p.registro
          FROM usuarios u
          LEFT JOIN alunos a ON a.id = u.aluno_id
          LEFT JOIN professores p ON p.id = u.professor_id
         ORDER BY u.usuario
        """
    )
    opcoes = get_opcoes_vinculo()
    return render_template(
        "usuarios.html",
        usuarios=lista,
        alunos=opcoes["alunos"],
        professores=opcoes["professores"],
    )


@app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
def editar_usuario(usuario_id):
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    usuario = fetch_one("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
    if not usuario:
        flash("Usuario nao encontrado.", "warning")
        return redirect(url_for("usuarios"))

    if request.method == "POST":
        nome_usuario = request.form["usuario"].strip()
        senha = request.form.get("senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")
        perfil = request.form.get("perfil", "aluno")
        aluno_id = request.form.get("aluno_id") or None
        professor_id = request.form.get("professor_id") or None

        if len(nome_usuario) < 3:
            flash("O usuario precisa ter pelo menos 3 caracteres.", "warning")
        elif senha and len(senha) < 4:
            flash("A senha precisa ter pelo menos 4 caracteres.", "warning")
        elif senha != confirmar_senha:
            flash("As senhas nao conferem.", "warning")
        elif not validar_dados_usuario(perfil, aluno_id, professor_id):
            pass
        else:
            if perfil != "aluno":
                aluno_id = None
            if perfil != "professor":
                professor_id = None

            try:
                if senha:
                    execute(
                        """
                        UPDATE usuarios
                           SET usuario = %s, senha_hash = %s, perfil = %s,
                               aluno_id = %s, professor_id = %s
                         WHERE id = %s
                        """,
                        (
                            nome_usuario,
                            generate_password_hash(senha),
                            perfil,
                            aluno_id,
                            professor_id,
                            usuario_id,
                        ),
                    )
                else:
                    execute(
                        """
                        UPDATE usuarios
                           SET usuario = %s, perfil = %s, aluno_id = %s, professor_id = %s
                         WHERE id = %s
                        """,
                        (nome_usuario, perfil, aluno_id, professor_id, usuario_id),
                    )
                flash("Usuario atualizado com sucesso.", "success")
                return redirect(url_for("usuarios"))
            except IntegrityError:
                flash("Ja existe um usuario com esse nome.", "warning")

    opcoes = get_opcoes_vinculo()
    return render_template(
        "editar_usuario.html",
        usuario=usuario,
        alunos=opcoes["alunos"],
        professores=opcoes["professores"],
    )


@app.post("/usuarios/<int:usuario_id>/excluir")
def excluir_usuario(usuario_id):
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    usuario = fetch_one("SELECT usuario FROM usuarios WHERE id = %s", (usuario_id,))
    if not usuario:
        flash("Usuario nao encontrado.", "warning")
        return redirect(url_for("usuarios"))

    if usuario["usuario"] == session.get("usuario_logado"):
        flash("Voce nao pode excluir o proprio usuario logado.", "warning")
        return redirect(url_for("usuarios"))

    execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
    flash("Usuario excluido com sucesso.", "success")
    return redirect(url_for("usuarios"))


@app.post("/logout")
def logout():
    session.clear()
    flash("Voce saiu do sistema.", "success")
    return redirect(url_for("login"))


def get_dashboard_counts():
    return {
        "alunos": fetch_one("SELECT COUNT(*) AS total FROM alunos")["total"],
        "professores": fetch_one("SELECT COUNT(*) AS total FROM professores")["total"],
        "disciplinas": fetch_one("SELECT COUNT(*) AS total FROM disciplinas")["total"],
        "matriculas": fetch_one(
            "SELECT COUNT(*) AS total FROM matriculas WHERE ativo = 1"
        )["total"],
    }


def get_dados_relatorio_banco():
    alunos = fetch_all(
        """
        SELECT id, nome, cpf, matricula, curso, criado_em
          FROM alunos
         ORDER BY nome
        """
    )
    professores = fetch_all(
        """
        SELECT id, nome, cpf, registro, area, criado_em
          FROM professores
         ORDER BY nome
        """
    )
    disciplinas = fetch_all(
        """
        SELECT d.id, d.nome, d.codigo, d.carga_horaria,
               COALESCE(p.nome, 'Sem professor') AS professor,
               d.criado_em
          FROM disciplinas d
          LEFT JOIN professores p ON p.id = d.professor_id
         ORDER BY d.nome
        """
    )
    matriculas = fetch_all(
        """
        SELECT m.id, a.nome AS aluno, a.matricula,
               d.nome AS disciplina, d.codigo,
               CASE WHEN m.ativo = 1 THEN 'ativa' ELSE 'removida' END AS status,
               m.criado_em, m.removido_em
          FROM matriculas m
          JOIN alunos a ON a.id = m.aluno_id
          JOIN disciplinas d ON d.id = m.disciplina_id
         ORDER BY d.nome, a.nome
        """
    )

    return {
        "banco": database_label(),
        "alunos": alunos,
        "professores": professores,
        "disciplinas": disciplinas,
        "matriculas": matriculas,
    }


@app.errorhandler(Error)
def handle_database_error(error):
    return render_template("erro.html", error=error), 500


@app.route("/")
def index():
    if usuario_aluno() and session.get("aluno_id"):
        return redirect(url_for("boletim", aluno_id=session["aluno_id"]))

    counts = get_dashboard_counts()
    disciplinas = fetch_all(
        """
        SELECT d.id, d.nome, d.codigo, d.carga_horaria,
               COALESCE(p.nome, 'Sem professor') AS professor,
               COUNT(m.aluno_id) AS total_alunos
          FROM disciplinas d
          LEFT JOIN professores p ON p.id = d.professor_id
          LEFT JOIN matriculas m ON m.disciplina_id = d.id AND m.ativo = 1
         GROUP BY d.id, d.nome, d.codigo, d.carga_horaria, p.nome
         ORDER BY d.nome
        """
    )
    return render_template(
        "index.html",
        counts=counts,
        database_label=database_label(),
        disciplinas=disciplinas,
    )


@app.get("/boletim")
def boletim():
    aluno_id = request.args.get("aluno_id", type=int)
    if usuario_aluno():
        aluno_id = session.get("aluno_id")
        alunos_lista = fetch_all(
            "SELECT id, nome, matricula FROM alunos WHERE id = %s ORDER BY nome",
            (aluno_id,),
        )
    elif usuario_professor():
        alunos_lista = fetch_all(
            """
            SELECT DISTINCT a.id, a.nome, a.matricula
              FROM alunos a
              JOIN matriculas m ON m.aluno_id = a.id AND m.ativo = 1
              JOIN disciplinas d ON d.id = m.disciplina_id
             WHERE d.professor_id = %s
             ORDER BY a.nome
            """,
            (session.get("professor_id"),),
        )
    else:
        alunos_lista = fetch_all("SELECT id, nome, matricula FROM alunos ORDER BY nome")

    aluno = None
    disciplinas = []

    if aluno_id:
        aluno_permitido = any(item["id"] == aluno_id for item in alunos_lista)
        if not aluno_permitido:
            flash("Seu perfil nao tem permissao para consultar este boletim.", "warning")
            return redirect(url_for("boletim"))

        aluno = fetch_one(
            """
            SELECT id, nome, cpf, matricula, curso
              FROM alunos
             WHERE id = %s
            """,
            (aluno_id,),
        )

        if aluno:
            filtro_professor = ""
            parametros = [aluno_id]
            if usuario_professor():
                filtro_professor = " AND d.professor_id = %s"
                parametros.append(session.get("professor_id"))

            disciplinas = fetch_all(
                f"""
                SELECT m.id AS matricula_id,
                       d.codigo, d.nome, d.carga_horaria,
                       COALESCE(p.nome, 'Sem professor') AS professor,
                       m.nota1, m.nota2
                  FROM matriculas m
                  JOIN disciplinas d ON d.id = m.disciplina_id
                  LEFT JOIN professores p ON p.id = d.professor_id
                 WHERE m.aluno_id = %s AND m.ativo = 1{filtro_professor}
                 ORDER BY d.nome
                """,
                tuple(parametros),
            )
        else:
            flash("Aluno nao encontrado para gerar boletim.", "warning")

    return render_template(
        "boletim.html",
        alunos=alunos_lista,
        aluno=aluno,
        disciplinas=disciplinas,
        aluno_id=aluno_id,
    )


@app.route("/boletim/<int:matricula_id>/editar", methods=["GET", "POST"])
def editar_boletim(matricula_id):
    matricula = fetch_one(
        """
        SELECT m.id, m.aluno_id, m.nota1, m.nota2,
               a.nome AS aluno, a.matricula, a.curso,
               d.id AS disciplina_id, d.nome AS disciplina, d.codigo, d.carga_horaria
          FROM matriculas m
          JOIN alunos a ON a.id = m.aluno_id
          JOIN disciplinas d ON d.id = m.disciplina_id
         WHERE m.id = %s AND m.ativo = 1
        """,
        (matricula_id,),
    )

    if not matricula:
        flash("Matricula nao encontrada para editar o boletim.", "warning")
        return redirect(url_for("boletim"))

    if not professor_pode_editar_matricula(matricula_id):
        flash("Seu perfil nao tem permissao para editar este boletim.", "warning")
        return redirect(url_for("boletim"))

    if request.method == "POST":
        try:
            nota1 = parse_nota(request.form.get("nota1", ""))
            nota2 = parse_nota(request.form.get("nota2", ""))
            carga_horaria = parse_carga_horaria(request.form.get("carga_horaria", ""))
        except ValueError:
            flash("As notas devem estar entre 0 e 10 e a carga horaria deve ser maior que zero.", "warning")
        else:
            execute(
                """
                UPDATE matriculas
                   SET nota1 = %s, nota2 = %s
                 WHERE id = %s
                """,
                (nota1, nota2, matricula_id),
            )
            execute(
                """
                UPDATE disciplinas
                   SET carga_horaria = %s
                 WHERE id = %s
                """,
                (carga_horaria, matricula["disciplina_id"]),
            )
            flash("Boletim atualizado com sucesso.", "success")
            return redirect(url_for("boletim", aluno_id=matricula["aluno_id"]))

    return render_template("editar_boletim.html", matricula=matricula)


@app.get("/relatorios/json")
def baixar_relatorio_json():
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    conteudo = gerar_relatorio_json(get_dados_relatorio_banco())
    return send_file(
        BytesIO(conteudo.encode("utf-8")),
        mimetype="application/json",
        as_attachment=True,
        download_name="relatorio_academico.json",
    )


@app.get("/relatorios/pdf")
def baixar_relatorio_pdf():
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    conteudo = gerar_relatorio_pdf(get_dados_relatorio_banco())
    return send_file(
        BytesIO(conteudo),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="relatorio_academico.pdf",
    )


@app.route("/alunos", methods=["GET", "POST"])
def alunos():
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    if request.method == "POST":
        dados = form_campos_obrigatorios(
            {
                "nome": "nome",
                "cpf": "CPF",
                "matricula": "matricula",
                "curso": "curso",
            }
        )
        if not dados:
            return redirect(url_for("alunos"))

        try:
            execute(
                """
                INSERT INTO alunos (nome, cpf, matricula, curso)
                VALUES (%s, %s, %s, %s)
                """,
                (dados["nome"], dados["cpf"], dados["matricula"], dados["curso"]),
            )
            flash("Aluno cadastrado com sucesso.", "success")
        except IntegrityError:
            flash("Ja existe aluno com este CPF ou matricula.", "warning")
        return redirect(url_for("alunos"))

    group_concat = "GROUP_CONCAT(d.nome, ', ')" if is_sqlite() else "GROUP_CONCAT(d.nome ORDER BY d.nome SEPARATOR ', ')"
    lista = fetch_all(
        f"""
        SELECT a.*,
               {group_concat} AS disciplinas
          FROM alunos a
          LEFT JOIN matriculas m ON m.aluno_id = a.id AND m.ativo = 1
          LEFT JOIN disciplinas d ON d.id = m.disciplina_id
         GROUP BY a.id
         ORDER BY a.nome
        """
    )
    return render_template("alunos.html", alunos=lista)


@app.route("/alunos/<int:aluno_id>/editar", methods=["GET", "POST"])
def editar_aluno(aluno_id):
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    aluno = fetch_one("SELECT * FROM alunos WHERE id = %s", (aluno_id,))
    if not aluno:
        flash("Aluno nao encontrado.", "warning")
        return redirect(url_for("alunos"))

    if request.method == "POST":
        dados = form_campos_obrigatorios(
            {
                "nome": "nome",
                "cpf": "CPF",
                "matricula": "matricula",
                "curso": "curso",
            }
        )
        if not dados:
            return redirect(url_for("editar_aluno", aluno_id=aluno_id))

        try:
            execute(
                """
                UPDATE alunos
                   SET nome = %s, cpf = %s, matricula = %s, curso = %s
                 WHERE id = %s
                """,
                (dados["nome"], dados["cpf"], dados["matricula"], dados["curso"], aluno_id),
            )
            flash("Aluno atualizado com sucesso.", "success")
            return redirect(url_for("alunos"))
        except IntegrityError:
            flash("Ja existe aluno com este CPF ou matricula.", "warning")

    return render_template("editar_aluno.html", aluno=aluno)


@app.route("/professores", methods=["GET", "POST"])
def professores():
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    if request.method == "POST":
        dados = form_campos_obrigatorios(
            {
                "nome": "nome",
                "cpf": "CPF",
                "registro": "registro",
                "area": "area",
            }
        )
        if not dados:
            return redirect(url_for("professores"))

        try:
            execute(
                """
                INSERT INTO professores (nome, cpf, registro, area)
                VALUES (%s, %s, %s, %s)
                """,
                (dados["nome"], dados["cpf"], dados["registro"], dados["area"]),
            )
            flash("Professor cadastrado com sucesso.", "success")
        except IntegrityError:
            flash("Ja existe professor com este CPF ou registro.", "warning")
        return redirect(url_for("professores"))

    group_concat = "GROUP_CONCAT(d.nome, ', ')" if is_sqlite() else "GROUP_CONCAT(d.nome ORDER BY d.nome SEPARATOR ', ')"
    lista = fetch_all(
        f"""
        SELECT p.*,
               {group_concat} AS disciplinas
          FROM professores p
          LEFT JOIN disciplinas d ON d.professor_id = p.id
         GROUP BY p.id
         ORDER BY p.nome
        """
    )
    return render_template("professores.html", professores=lista)


@app.route("/professores/<int:professor_id>/editar", methods=["GET", "POST"])
def editar_professor(professor_id):
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    professor = fetch_one("SELECT * FROM professores WHERE id = %s", (professor_id,))
    if not professor:
        flash("Professor nao encontrado.", "warning")
        return redirect(url_for("professores"))

    if request.method == "POST":
        dados = form_campos_obrigatorios(
            {
                "nome": "nome",
                "cpf": "CPF",
                "registro": "registro",
                "area": "area",
            }
        )
        if not dados:
            return redirect(url_for("editar_professor", professor_id=professor_id))

        try:
            execute(
                """
                UPDATE professores
                   SET nome = %s, cpf = %s, registro = %s, area = %s
                 WHERE id = %s
                """,
                (dados["nome"], dados["cpf"], dados["registro"], dados["area"], professor_id),
            )
            flash("Professor atualizado com sucesso.", "success")
            return redirect(url_for("professores"))
        except IntegrityError:
            flash("Ja existe professor com este CPF ou registro.", "warning")

    return render_template("editar_professor.html", professor=professor)


@app.route("/disciplinas", methods=["GET", "POST"])
def disciplinas():
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    if request.method == "POST":
        dados = form_campos_obrigatorios(
            {
                "nome": "nome",
                "codigo": "codigo",
                "carga_horaria": "carga horaria",
            }
        )
        if not dados:
            return redirect(url_for("disciplinas"))

        professor_id = request.form.get("professor_id") or None
        try:
            carga_horaria = parse_carga_horaria(dados["carga_horaria"])
            execute(
                """
                INSERT INTO disciplinas (nome, codigo, carga_horaria, professor_id)
                VALUES (%s, %s, %s, %s)
                """,
                (dados["nome"], dados["codigo"], carga_horaria, professor_id),
            )
            flash("Disciplina cadastrada com sucesso.", "success")
        except ValueError:
            flash("A carga horaria deve ser um numero maior que zero.", "warning")
        except IntegrityError:
            flash("Ja existe disciplina com este codigo.", "warning")
        return redirect(url_for("disciplinas"))

    professores_lista = fetch_all("SELECT id, nome FROM professores ORDER BY nome")
    lista = fetch_all(
        """
        SELECT d.*, COALESCE(p.nome, 'Sem professor') AS professor,
               COUNT(m.aluno_id) AS total_alunos
          FROM disciplinas d
          LEFT JOIN professores p ON p.id = d.professor_id
          LEFT JOIN matriculas m ON m.disciplina_id = d.id AND m.ativo = 1
         GROUP BY d.id, p.nome
         ORDER BY d.nome
        """
    )
    return render_template(
        "disciplinas.html", disciplinas=lista, professores=professores_lista
    )


@app.route("/disciplinas/<int:disciplina_id>/editar", methods=["GET", "POST"])
def editar_disciplina(disciplina_id):
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    disciplina = fetch_one("SELECT * FROM disciplinas WHERE id = %s", (disciplina_id,))
    if not disciplina:
        flash("Disciplina nao encontrada.", "warning")
        return redirect(url_for("disciplinas"))

    professores_lista = fetch_all("SELECT id, nome FROM professores ORDER BY nome")

    if request.method == "POST":
        dados = form_campos_obrigatorios(
            {
                "nome": "nome",
                "codigo": "codigo",
                "carga_horaria": "carga horaria",
            }
        )
        if not dados:
            return redirect(url_for("editar_disciplina", disciplina_id=disciplina_id))

        professor_id = request.form.get("professor_id") or None
        try:
            carga_horaria = parse_carga_horaria(dados["carga_horaria"])
            execute(
                """
                UPDATE disciplinas
                   SET nome = %s, codigo = %s, carga_horaria = %s, professor_id = %s
                 WHERE id = %s
                """,
                (dados["nome"], dados["codigo"], carga_horaria, professor_id, disciplina_id),
            )
            flash("Disciplina atualizada com sucesso.", "success")
            return redirect(url_for("disciplinas"))
        except ValueError:
            flash("A carga horaria deve ser um numero maior que zero.", "warning")
        except IntegrityError:
            flash("Ja existe disciplina com este codigo.", "warning")

    return render_template(
        "editar_disciplina.html",
        disciplina=disciplina,
        professores=professores_lista,
    )


@app.route("/matriculas", methods=["GET", "POST"])
def matriculas():
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    if request.method == "POST":
        dados = form_campos_obrigatorios(
            {"aluno_id": "aluno", "disciplina_id": "disciplina"}
        )
        if not dados:
            return redirect(url_for("matriculas"))

        aluno_id = dados["aluno_id"]
        disciplina_id = dados["disciplina_id"]
        matricula_existente = fetch_one(
            """
            SELECT id, ativo
              FROM matriculas
             WHERE aluno_id = %s AND disciplina_id = %s
            """,
            (aluno_id, disciplina_id),
        )

        if matricula_existente and matricula_existente["ativo"]:
            flash("Este aluno ja esta matriculado nessa disciplina.", "warning")
        elif matricula_existente:
            execute(
                """
                UPDATE matriculas
                   SET ativo = 1, removido_em = NULL
                 WHERE id = %s
                """,
                (matricula_existente["id"],),
            )
            flash("Matricula reativada com sucesso.", "success")
        else:
            try:
                execute(
                    """
                    INSERT INTO matriculas (aluno_id, disciplina_id, ativo)
                    VALUES (%s, %s, 1)
                    """,
                    (aluno_id, disciplina_id),
                )
                flash("Aluno matriculado com sucesso.", "success")
            except IntegrityError:
                flash("Este aluno ja esta matriculado nessa disciplina.", "warning")
        return redirect(url_for("matriculas"))

    alunos_lista = fetch_all("SELECT id, nome, matricula FROM alunos ORDER BY nome")
    disciplinas_lista = fetch_all("SELECT id, nome, codigo FROM disciplinas ORDER BY nome")
    lista = fetch_all(
        """
        SELECT m.id, a.nome AS aluno, a.matricula, d.nome AS disciplina, d.codigo
          FROM matriculas m
          JOIN alunos a ON a.id = m.aluno_id
          JOIN disciplinas d ON d.id = m.disciplina_id
         WHERE m.ativo = 1
         ORDER BY d.nome, a.nome
        """
    )
    return render_template(
        "matriculas.html",
        alunos=alunos_lista,
        disciplinas=disciplinas_lista,
        matriculas=lista,
    )


@app.route("/matriculas/<int:matricula_id>/editar", methods=["GET", "POST"])
def editar_matricula(matricula_id):
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    matricula = fetch_one("SELECT * FROM matriculas WHERE id = %s", (matricula_id,))
    if not matricula:
        flash("Matricula nao encontrada.", "warning")
        return redirect(url_for("matriculas"))

    alunos_lista = fetch_all("SELECT id, nome, matricula FROM alunos ORDER BY nome")
    disciplinas_lista = fetch_all("SELECT id, nome, codigo FROM disciplinas ORDER BY nome")

    if request.method == "POST":
        dados = form_campos_obrigatorios(
            {"aluno_id": "aluno", "disciplina_id": "disciplina"}
        )
        if not dados:
            return redirect(url_for("editar_matricula", matricula_id=matricula_id))

        try:
            execute(
                """
                UPDATE matriculas
                   SET aluno_id = %s, disciplina_id = %s, ativo = 1, removido_em = NULL
                 WHERE id = %s
                """,
                (dados["aluno_id"], dados["disciplina_id"], matricula_id),
            )
            flash("Matricula atualizada com sucesso.", "success")
            return redirect(url_for("matriculas"))
        except IntegrityError:
            flash("Este aluno ja esta matriculado nessa disciplina.", "warning")

    return render_template(
        "editar_matricula.html",
        matricula=matricula,
        alunos=alunos_lista,
        disciplinas=disciplinas_lista,
    )


@app.post("/matriculas/<int:matricula_id>/excluir")
def excluir_matricula(matricula_id):
    if not exigir_perfil("admin"):
        return redirect(url_for("index"))

    execute(
        """
        UPDATE matriculas
           SET ativo = 0, removido_em = CURRENT_TIMESTAMP
         WHERE id = %s
        """,
        (matricula_id,),
    )
    flash("Matricula removida da interface. O registro continua no banco.", "success")
    return redirect(url_for("matriculas"))


if __name__ == "__main__":
    app.run(debug=flask_debug_ativo())
