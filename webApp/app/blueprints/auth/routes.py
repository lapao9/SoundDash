from flask import Blueprint, request, render_template, redirect, url_for, flash, session, make_response
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
from app.services.auth_service import User, load_users

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/acesso-tecnico', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        if username in users and check_password_hash(users[username]['password'], password):
            login_user(User(username), remember=remember)
            flash('Login efetuado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('pages.controlo'))
        flash('Credenciais inválidas.', 'danger')
    return render_template('login.html')


@auth_bp.route('/app-logout')
@login_required
def logout():
    logout_user()
    flash('Sessão terminada.', 'info')
    return redirect(url_for('pages.home'))


@auth_bp.route('/api/check_auth')
def check_auth():
    if 'user_id' in session or 'username' in session:
        username = session.get('username', 'viewer')
        response = make_response('', 200)
        response.headers['X-User'] = username
        return response
    return '', 401
