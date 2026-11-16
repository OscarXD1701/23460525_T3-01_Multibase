"""Pruebas de integración: HTTP y tres motores reales, sin sustitutos en memoria."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.models import RECURSOS

class Integracion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.http = cls.context.__enter__()
        cls.cliente = cls.http.post('/clientes', json={
            'nombre': 'Cliente pruebas', 'email': 'pruebas@example.com'}).json()['id']
        cls.producto = cls.http.post('/productos', json={
            'nombre': 'Café pruebas', 'precio_centavos': 8950, 'stock': 20}).json()['id']

    @classmethod
    def tearDownClass(cls):
        cls.http.delete('/clientes/' + cls.cliente)
        cls.http.delete('/productos/' + cls.producto)
        cls.context.__exit__(None, None, None)

    def ejemplos(self):
        return {
            'clientes': ({'nombre': 'Ana', 'email': 'ana@example.com'}, {'nombre': 'Ana María'}),
            'productos': ({'nombre': 'Arroz', 'precio_centavos': 3375, 'stock': 5}, {'stock': 8}),
            'pedidos': ({'cliente_id': self.cliente, 'items': [
                {'producto_id': self.producto, 'cantidad': 2}]}, {'estado': 'pagado'}),
            'resenas': ({'cliente_id': self.cliente, 'producto_id': self.producto,
                         'puntuacion': 4, 'comentario': 'Bueno'}, {'puntuacion': 5}),
            'carritos': ({'cliente_id': self.cliente, 'items': []}, {'items': [
                {'producto_id': self.producto, 'cantidad': 1}]}),
            'preferencias': ({'cliente_id': self.cliente}, {'tema': 'oscuro'}),
        }

    def test_01_salud_y_contratos(self):
        self.assertEqual(self.http.get('/salud').json()['estado'], 'ok')
        schema = self.http.get('/openapi.json').json()
        for nombre in RECURSOS:
            self.assertIn('post', schema['paths']['/' + nombre])
            for method in ('get', 'patch', 'delete'):
                self.assertIn(method, schema['paths'][f'/{nombre}/{{id}}'])

    def test_02_ciclo_completo_seis_recursos_y_retencion_fisica(self):
        for nombre, (datos, cambios) in self.ejemplos().items():
            with self.subTest(recurso=nombre):
                response = self.http.post('/' + nombre, json=datos)
                self.assertEqual(response.status_code, 201, response.text)
                row = response.json()
                path = response.headers['location']
                self.assertFalse(row['eliminado'])
                self.assertEqual(self.http.get(path).status_code, 200)
                response = self.http.patch(path, json=cambios)
                self.assertEqual(response.status_code, 200, response.text)
                for key, value in cambios.items():
                    self.assertEqual(response.json()[key], value)
                self.assertEqual(self.http.delete(path).status_code, 204)
                self.assertEqual(self.http.get(path).status_code, 404)
                self.assertEqual(self.http.patch(path, json=cambios).status_code, 404)
                self.assertEqual(self.http.delete(path).status_code, 404)
                # Inspección directa: el registro sigue existiendo en su motor.
                _, motor = RECURSOS[nombre]
                raw = app.state.stores.obtener(nombre, motor, row['id'], True)
                self.assertIsNotNone(raw)
                self.assertTrue(raw['eliminado'])
                self.assertIsNotNone(raw['eliminado_en'])
                active = self.http.get('/' + nombre + '?limite=100').json()
                self.assertNotIn(row['id'], [r['id'] for r in active])

    def test_03_patch_invalido_y_metadatos(self):
        for nombre, (datos, cambios) in self.ejemplos().items():
            with self.subTest(recurso=nombre):
                path = self.http.post('/' + nombre, json=datos).headers['location']
                for body in ({}, {'eliminado': False}, {'id': str(uuid4())},
                             {next(iter(cambios)): None}, {'$set': {'nombre': 'x'}}):
                    self.assertEqual(self.http.patch(path, json=body).status_code, 422)
                self.http.delete(path)
        self.assertEqual(self.http.post('/productos', json={
            'nombre': 'Error', 'precio_centavos': -1}).status_code, 422)
        self.assertEqual(self.http.post('/clientes', json={
            'nombre': ' ', 'email': 'sin-formato'}).status_code, 422)

    def test_04_referencias_y_uuid(self):
        self.assertEqual(self.http.post('/carritos', json={
            'cliente_id': str(uuid4()), 'items': []}).status_code, 422)
        self.assertEqual(self.http.post('/pedidos', json={
            'cliente_id': self.cliente, 'items': [
                {'producto_id': str(uuid4()), 'cantidad': 2}]}).status_code, 422)
        for nombre in RECURSOS:
            self.assertEqual(self.http.get('/' + nombre + '/invalido').status_code, 422)
            self.assertEqual(self.http.get('/' + nombre + '/' + str(uuid4())).status_code, 404)
            self.assertEqual(self.http.get('/' + nombre + '?limite=0').status_code, 422)
            self.assertEqual(self.http.get('/' + nombre + '?offset=-1').status_code, 422)

    def test_05_actualizaciones_concurrentes_no_pierden_campos(self):
        casos = [
            ('productos', {'nombre': 'Concurrente', 'precio_centavos': 100, 'stock': 1},
             {'stock': 9}, {'precio_centavos': 200}),
            ('pedidos', {'cliente_id': self.cliente, 'items': [
                {'producto_id': self.producto, 'cantidad': 1}]},
             {'estado': 'pagado'}, {'items': [{'producto_id': self.producto, 'cantidad': 3}]}),
            ('preferencias', {'cliente_id': self.cliente}, {'tema': 'oscuro'}, {'idioma': 'en'}),
        ]
        for nombre, datos, a, b in casos:
            with self.subTest(motor=RECURSOS[nombre][1]):
                path = self.http.post('/' + nombre, json=datos).headers['location']
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(lambda patch: self.http.patch(path, json=patch), [a, b]))
                self.assertTrue(all(r.status_code == 200 for r in results))
                actual = self.http.get(path).json()
                for key, value in {**a, **b}.items():
                    self.assertEqual(actual[key], value)
                self.http.delete(path)

    def test_06_no_permite_referenciar_eliminados(self):
        response = self.http.post('/productos', json={'nombre': 'Borrado', 'precio_centavos': 100})
        id = response.json()['id']
        self.http.delete(response.headers['location'])
        self.assertEqual(self.http.post('/resenas', json={
            'producto_id': id, 'cliente_id': self.cliente,
            'puntuacion': 5, 'comentario': 'Prueba'}).status_code, 422)

    def test_07_paginacion_y_campos_obligatorios(self):
        for nombre, (datos, _) in self.ejemplos().items():
            with self.subTest(recurso=nombre):
                self.assertEqual(self.http.post('/' + nombre, json={}).status_code, 422)
                paths = [self.http.post('/' + nombre, json=datos).headers['location']
                         for _ in range(2)]
                first = self.http.get('/' + nombre + '?limite=1').json()
                second = self.http.get('/' + nombre + '?limite=1&offset=1').json()
                self.assertEqual(len(first), 1)
                self.assertEqual(len(second), 1)
                self.assertNotEqual(first[0]['id'], second[0]['id'])
                for path in paths:
                    self.http.delete(path)

if __name__ == '__main__':
    unittest.main(verbosity=2)
