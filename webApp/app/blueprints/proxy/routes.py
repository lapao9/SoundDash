import requests
from flask import Blueprint, request, Response, jsonify

proxy_bp = Blueprint('proxy', __name__)


@proxy_bp.route('/grafana/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def grafana_proxy(path):
    grafana_url = f'http://localhost:3000/{path}'
    if request.query_string:
        grafana_url += f'?{request.query_string.decode("utf-8")}'

    headers = {k: v for k, v in request.headers if k.lower() != 'host'}
    headers['Host'] = 'localhost:3000'

    try:
        resp = requests.request(
            method=request.method,
            url=grafana_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=10
        )
        excluded = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
        response_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
        return Response(resp.content, resp.status_code, response_headers)
    except Exception as e:
        return jsonify({'erro': f'Erro ao aceder ao Grafana: {str(e)}'}), 502
