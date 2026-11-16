"""Demostración HTTP de los seis recursos. Solo requiere Python estándar."""
import json
import sys
from urllib.request import Request, urlopen

BASE = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:8000'

def enviar(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(BASE + path, data=body, method=method,
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=10) as response:
        content = response.read()
        print(method, path, response.status)
        return json.loads(content) if content else None

if __name__ == '__main__':
    print(enviar('GET', '/salud'))
    records = []
    try:
        cliente = enviar('POST', '/clientes', {
            'nombre': 'Cliente demo', 'email': 'demo@example.com'})
        records.append(('clientes', cliente['id']))
        producto = enviar('POST', '/productos', {
            'nombre': 'Café 500 g', 'precio_centavos': 8950, 'stock': 12})
        records.append(('productos', producto['id']))
        cid, pid = cliente['id'], producto['id']
        for nombre, datos in [
            ('pedidos', {'cliente_id': cid, 'items': [{'producto_id': pid, 'cantidad': 2}]}),
            ('resenas', {'cliente_id': cid, 'producto_id': pid,
                        'puntuacion': 5, 'comentario': 'Buen producto'}),
            ('carritos', {'cliente_id': cid, 'items': [{'producto_id': pid, 'cantidad': 1}]}),
            ('preferencias', {'cliente_id': cid, 'tema': 'claro', 'idioma': 'es'}),
        ]:
            row = enviar('POST', '/' + nombre, datos)
            records.append((nombre, row['id']))
        cambios = {'clientes': {'nombre': 'Cliente actualizado'},
                   'productos': {'stock': 10}, 'pedidos': {'estado': 'pagado'},
                   'resenas': {'comentario': 'Excelente'},
                   'carritos': {'items': []}, 'preferencias': {'tema': 'oscuro'}}
        for nombre, id in records:
            enviar('GET', '/' + nombre)
            enviar('GET', f'/{nombre}/{id}')
            enviar('PATCH', f'/{nombre}/{id}', cambios[nombre])
    finally:
        # Se borran lógicamente los registros creados, incluso si falla la demo.
        for nombre, id in reversed(records):
            enviar('DELETE', f'/{nombre}/{id}')
