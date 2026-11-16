"""Resumen de retención física para comparar antes y después de reiniciar motores."""
import json
from app.stores import Almacenes
from app.models import RECURSOS
s = Almacenes()
try:
    result = {}
    for nombre, (_, motor) in RECURSOS.items():
        if motor == 'postgres':
            from psycopg import sql
            with s.pg() as con:
                rows = con.execute(sql.SQL('SELECT id, eliminado FROM {} ORDER BY id').format(
                    sql.Identifier(nombre))).fetchall()
        elif motor == 'mongo':
            rows = list(s.documentos[nombre].find({}, {'_id': 0, 'id': 1, 'eliminado': 1}).sort('id', 1))
        else:
            rows = []
            for key in s.redis.scan_iter(match=f't301:{nombre}:*'):
                data = json.loads(s.redis.get(key))
                assert s.redis.ttl(key) == -1, 'Un registro no debe expirar'
                rows.append({'id': data['id'], 'eliminado': data['eliminado']})
            rows.sort(key=lambda r: r['id'])
        result[nombre] = rows
    print(json.dumps(result, sort_keys=True))
finally:
    s.cerrar()
