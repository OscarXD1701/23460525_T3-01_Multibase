"""Recolecta evidencia real de HTTP y de los motores sin modificar la aplicación."""
import argparse
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8000'
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'sesion-real'
OUT.mkdir(exist_ok=True)
traces = []

def now():
    return datetime.now(timezone.utc).isoformat()

def http(method, path, body=None, expected=200):
    start = perf_counter()
    stamp = now()
    payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = Request(BASE + path, data=payload, method=method,
                      headers={'Content-Type': 'application/json'})
    try:
        response = urlopen(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read().decode('utf-8')
        result = json.loads(raw) if raw else None
        trace = {'numero': len(traces)+1, 'fecha_utc': stamp,
                 'duracion_ms': round((perf_counter()-start)*1000, 2),
                 'peticion': {'metodo': method, 'url': BASE+path, 'json': body},
                 'respuesta': {'estado': response.status, 'cabeceras': dict(response.headers),
                               'json': result}}
        traces.append(trace)
        # Se guarda tras cada respuesta para conservar también fallos inesperados.
        (OUT/'http.jsonl').write_text(''.join(json.dumps(t,ensure_ascii=False)+'\n' for t in traces),encoding='utf-8')
        assert response.status == expected, trace
        return result

def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',errors='replace')
    assert result.returncode == 0, (args, result.stderr)
    return f'Fecha UTC: {now()}\n$ {shlex.join(args)}\n{result.stdout}\n'

def motores(ids, stage):
    folder = OUT/stage
    folder.mkdir(exist_ok=True)
    sql = "SELECT id,nombre,precio_centavos,stock,eliminado,eliminado_en FROM productos WHERE id = '"+ids['productos']+"';"
    text = command(['docker','compose','exec','-T','postgres','psql','-U','tienda','-d','tienda','-x','-c',sql])
    sql = "SELECT id,nombre,email,eliminado,eliminado_en FROM clientes WHERE id = '"+ids['clientes']+"';"
    text += command(['docker','compose','exec','-T','postgres','psql','-U','tienda','-d','tienda','-x','-c',sql])
    (folder/'postgresql.txt').write_text(text,encoding='utf-8')
    text = ''
    for name in ['pedidos','resenas']:
        js = f'JSON.stringify(db.{name}.findOne({{id:"{ids[name]}"}},{{_id:0}}),null,2)'
        text += command(['docker','compose','exec','-T','mongo','mongosh','tienda','--quiet','--eval',js])
    (folder/'mongodb.txt').write_text(text,encoding='utf-8')
    text = ''
    for name in ['carritos','preferencias']:
        key = f't301:{name}:{ids[name]}'
        for operation in ['GET','EXISTS','TTL']:
            text += command(['docker','compose','exec','-T','redis','redis-cli',operation,key])
    (folder/'redis.txt').write_text(text,encoding='utf-8')

if __name__ == '__main__':
    http('GET','/salud')
    cliente = http('POST','/clientes',{'nombre':'María Torres (demostración)',
                                    'email':'maria.torres@example.com'},201)
    producto = http('POST','/productos',{'nombre':'Café de Colima 500 g (demostración)',
                                       'precio_centavos':8950,'stock':24},201)
    ids = {'clientes':cliente['id'], 'productos':producto['id']}
    datos = {
        'pedidos': {'cliente_id':cliente['id'],'items':[{'producto_id':producto['id'],'cantidad':2}]},
        'resenas': {'cliente_id':cliente['id'],'producto_id':producto['id'],
                   'puntuacion':4,'comentario':'Buen aroma; empaque recibido sin daños.'},
        'carritos': {'cliente_id':cliente['id'],'items':[{'producto_id':producto['id'],'cantidad':1}]},
        'preferencias': {'cliente_id':cliente['id'],'tema':'claro','idioma':'es'},
    }
    for name, body in datos.items():
        ids[name] = http('POST','/'+name,body,201)['id']
    (OUT/'identificadores.json').write_text(json.dumps({'inicio_utc':traces[0]['fecha_utc'],
        'datos':'Datos ficticios de demostración, ejecutados contra motores reales.',
        'ids':ids},ensure_ascii=False,indent=2),encoding='utf-8')
    updates = {'clientes':{'nombre':'María Torres López (demostración)'},
               'productos':{'stock':18},'pedidos':{'estado':'pagado'},
               'resenas':{'puntuacion':5},'carritos':{'items':[]},
               'preferencias':{'tema':'oscuro'}}
    for name, id in ids.items():
        http('GET',f'/{name}/{id}')
        updated = http('PATCH',f'/{name}/{id}',updates[name])
        assert all(updated[k] == v for k,v in updates[name].items())
    # Casos de validación con respuestas reales, sin atribuir causas de negocio.
    http('POST','/productos',{'nombre':'Dato inválido de prueba','precio_centavos':-50},422)
    http('PATCH','/productos/'+ids['productos'],{'eliminado':False},422)
    motores(ids,'antes-del-borrado')
    for name in reversed(ids):
        id = ids[name]
        http('DELETE',f'/{name}/{id}',expected=204)
        http('GET',f'/{name}/{id}',expected=404)
        active = http('GET',f'/{name}?limite=100')
        assert id not in [row['id'] for row in active]
    motores(ids,'despues-del-borrado')
    status = command(['docker','compose','ps'])
    (OUT/'contenedores.txt').write_text(status,encoding='utf-8')
    transcript = ['SESION HTTP REAL',f'Base: {BASE}',
                  'Datos ficticios; respuestas capturadas sin editar.', '']
    for t in traces:
        r=t['peticion'];p=t['respuesta']
        transcript += [f"#{t['numero']:02d} | {t['fecha_utc']} | {t['duracion_ms']} ms",
                       f"{r['metodo']} {r['url']}",
                       'Cuerpo enviado: '+json.dumps(r['json'],ensure_ascii=False),
                       f"HTTP {p['estado']}",
                       'Respuesta: '+json.dumps(p['json'],ensure_ascii=False), '']
    (OUT/'http-completo.txt').write_text('\n'.join(transcript),encoding='utf-8')
    print(f'{len(traces)} peticiones verificadas. Evidencia guardada en {OUT}')
