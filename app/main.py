"""Servicio web de una tienda con seis recursos y borrado lógico."""
from contextlib import asynccontextmanager
import logging
from uuid import UUID
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
import psycopg
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from .models import RECURSOS
from .stores import Almacenes, ahora

@asynccontextmanager
async def lifespan(app):
    stores = Almacenes()
    app.state.stores = stores
    try:
        stores.iniciar()
        yield
    finally:
        stores.cerrar()

app = FastAPI(title="T3-01 · Tienda multibase", version="1.0.0", lifespan=lifespan,
              description="PostgreSQL, MongoDB y Redis. DELETE aplica borrado lógico.")

async def error_motor(request, error):
    logging.getLogger(__name__).error("Motor no disponible: %s", type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "Base de datos no disponible"})

for error in (psycopg.Error, PyMongoError, RedisError):
    app.add_exception_handler(error, error_motor)

@app.get("/salud", tags=["Sistema"])
def salud(request: Request):
    request.app.state.stores.comprobar()
    return {"estado": "ok", "motores": ["postgresql", "mongodb", "redis"]}

def referencias(stores, data):
    for field, collection in (("cliente_id", "clientes"), ("producto_id", "productos")):
        if field in data and not stores.obtener(collection, "postgres", data[field]):
            raise HTTPException(422, f"{field} no existe o está eliminado")
    for item in data.get("items", []):
        if not stores.obtener("productos", "postgres", item["producto_id"]):
            raise HTTPException(422, "Un producto no existe o está eliminado")

def registrar(nombre, modelo, motor):
    # Cada recurso mantiene su contrato de POST en OpenAPI, reutilizando el flujo.
    def listar(request: Request, offset: int = Query(0, ge=0),
               limite: int = Query(50, ge=1, le=100)):
        return request.app.state.stores.listar(nombre, motor, offset, limite)

    def obtener(id: UUID, request: Request):
        row = request.app.state.stores.obtener(nombre, motor, str(id))
        if not row:
            raise HTTPException(404, "Registro no encontrado")
        return row

    def crear(body, request: Request, response: Response):
        data = body.model_dump(mode="json")
        stores = request.app.state.stores
        referencias(stores, data)
        row = stores.crear(nombre, motor, data)
        response.headers["Location"] = f"/{nombre}/{row['id']}"
        return row
    crear.__annotations__["body"] = modelo

    def actualizar(id: UUID, body: dict, request: Request):
        stores = request.app.state.stores
        row = obtener(id, request)
        if not body or set(body) - set(modelo.model_fields):
            raise HTTPException(422, "PATCH requiere campos válidos; no acepta metadatos")
        current = {key: row[key] for key in modelo.model_fields}
        try:
            validated = modelo.model_validate({**current, **body}).model_dump(mode="json")
        except ValidationError:
            raise HTTPException(422, "Los valores enviados no cumplen el contrato del recurso")
        changes = {key: validated[key] for key in body}
        referencias(stores, changes)
        row = stores.modificar(nombre, motor, str(id), changes)
        if not row:
            raise HTTPException(404, "Registro no encontrado")
        return row

    def borrar(id: UUID, request: Request):
        row = request.app.state.stores.modificar(nombre, motor, str(id), {
            "eliminado": True, "eliminado_en": ahora()})
        if not row:
            raise HTTPException(404, "Registro no encontrado")
        return Response(status_code=204)

    for path, method, handler, status in [
        (f"/{nombre}", "GET", listar, 200),
        (f"/{nombre}/{{id}}", "GET", obtener, 200),
        (f"/{nombre}", "POST", crear, 201),
        (f"/{nombre}/{{id}}", "PATCH", actualizar, 200),
        (f"/{nombre}/{{id}}", "DELETE", borrar, 204),
    ]:
        app.add_api_route(path, handler, methods=[method], status_code=status,
                          tags=[nombre], name=f"{method}_{nombre}_{handler.__name__}")

for nombre, (modelo, motor) in RECURSOS.items():
    registrar(nombre, modelo, motor)
