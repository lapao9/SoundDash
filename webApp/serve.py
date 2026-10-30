"""
Arranque em produção (VM): servidor Waitress, sem o debugger do Flask.
O serviço SoundDash-Flask (nssm) corre este ficheiro; para desenvolvimento local continua a usar-se run.py.

    pip install waitress
    nssm set SoundDash-Flask AppParameters serve.py
"""
import logging

from waitress import serve
from app import create_app

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

app = create_app()

if __name__ == '__main__':
    # 0.0.0.0 mantém o acesso direto pela porta 5000; se tudo passar pelo Nginx pode passar a 127.0.0.1
    serve(app, host='0.0.0.0', port=5000, threads=8, channel_timeout=300)
