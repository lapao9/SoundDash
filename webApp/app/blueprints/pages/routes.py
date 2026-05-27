from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.services.system_config import load_system_config

pages_bp = Blueprint('pages', __name__)


def _grafana_url():
    return load_system_config().get('grafana_url', '')


@pages_bp.route('/')
def home():
    return render_template('homepage.html', grafana_url=_grafana_url())


@pages_bp.route('/atual')
def atual():
    return render_template('atual.html', grafana_url=_grafana_url())


@pages_bp.route('/tempo')
def tempo():
    return render_template('tempo.html', grafana_url=_grafana_url())


@pages_bp.route('/mapa')
def mapa():
    return render_template('mapa.html', grafana_url=_grafana_url())


@pages_bp.route('/display')
def display():
    return render_template('display.html', grafana_url=_grafana_url())


@pages_bp.route('/eventos')
def eventos():
    return render_template('eventos.html', grafana_url=_grafana_url())


@pages_bp.route('/guia')
def guia():
    return render_template('guia.html', grafana_url=_grafana_url())


@pages_bp.route('/estatisticas')
def estatisticas():
    return render_template('estatisticas.html', grafana_url=_grafana_url())


@pages_bp.route('/controlo')
@login_required
def controlo():
    return render_template('controlo.html',
                           username=current_user.id,
                           grafana_url=_grafana_url())
