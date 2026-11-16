"""Persistencia real en tres motores; las actualizaciones no eliminan registros."""
import json
import os
from datetime import datetime, timezone
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pymongo import MongoClient, ReturnDocument
from redis import Redis, WatchError

def ahora():
    return datetime.now(timezone.utc).isoformat()

class Almacenes:
    def __init__(self):
        self.pg_url = os.environ["POSTGRES_URL"]
        self.mongo = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000,
                                 connectTimeoutMS=3000, socketTimeoutMS=3000)
        self.documentos = self.mongo[os.getenv("MONGO_DB", "tienda")]
        self.redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True,
                                    socket_connect_timeout=3, socket_timeout=3)

    def pg(self):
        return psycopg.connect(self.pg_url, row_factory=dict_row, connect_timeout=3)

    def iniciar(self):
        with self.pg() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS clientes (
                id TEXT PRIMARY KEY, nombre TEXT NOT NULL, email TEXT NOT NULL,
                creado_en TEXT NOT NULL, eliminado BOOLEAN NOT NULL DEFAULT FALSE,
                eliminado_en TEXT)""")
            con.execute("""CREATE TABLE IF NOT EXISTS productos (
                id TEXT PRIMARY KEY, nombre TEXT NOT NULL,
                precio_centavos BIGINT NOT NULL CHECK (precio_centavos >= 0),
                stock BIGINT NOT NULL CHECK (stock >= 0), creado_en TEXT NOT NULL,
                eliminado BOOLEAN NOT NULL DEFAULT FALSE, eliminado_en TEXT)""")
        for nombre in ("pedidos", "resenas"):
            self.documentos[nombre].create_index("id", unique=True)
        self.comprobar()

    def comprobar(self):
        with self.pg() as con:
            con.execute("SELECT 1")
        self.mongo.admin.command("ping")
        self.redis.ping()

    def cerrar(self):
        self.mongo.close()
        self.redis.close()

    def obtener(self, nombre, motor, id, incluir_borrado=False):
        if motor == "postgres":
            with self.pg() as con:
                row = con.execute(sql.SQL("SELECT * FROM {} WHERE id = %s").format(
                    sql.Identifier(nombre)), (id,)).fetchone()
        elif motor == "mongo":
            row = self.documentos[nombre].find_one({"id": id}, {"_id": 0})
        else:
            value = self.redis.get(f"t301:{nombre}:{id}")
            row = json.loads(value) if value else None
        return row if row and (incluir_borrado or not row["eliminado"]) else None

    def listar(self, nombre, motor, offset, limite):
        if motor == "postgres":
            with self.pg() as con:
                return con.execute(sql.SQL("""SELECT * FROM {} WHERE eliminado = FALSE
                    ORDER BY id LIMIT %s OFFSET %s""").format(sql.Identifier(nombre)),
                    (limite, offset)).fetchall()
        if motor == "mongo":
            return list(self.documentos[nombre].find({"eliminado": False}, {"_id": 0})
                        .sort("id", 1).skip(offset).limit(limite))
        # ponytail: recorrido O(n) para este proyecto académico; usar un índice
        # ordenado por recurso si el volumen requiere paginación eficiente.
        rows = []
        for key in self.redis.scan_iter(match=f"t301:{nombre}:*"):
            value = self.redis.get(key)
            if value:
                row = json.loads(value)
                if not row["eliminado"]:
                    rows.append(row)
        return sorted(rows, key=lambda row: row["id"])[offset:offset + limite]

    def crear(self, nombre, motor, datos):
        row = dict(datos, id=str(uuid4()), creado_en=ahora(),
                   eliminado=False, eliminado_en=None)
        if motor == "postgres":
            with self.pg() as con:
                con.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(nombre), sql.SQL(", ").join(map(sql.Identifier, row)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in row)), tuple(row.values()))
        elif motor == "mongo":
            self.documentos[nombre].insert_one(row.copy())
        else:
            self.redis.set(f"t301:{nombre}:{row['id']}", json.dumps(row), nx=True)
        return row

    def modificar(self, nombre, motor, id, cambios):
        if motor == "postgres":
            with self.pg() as con:
                return con.execute(sql.SQL("""UPDATE {} SET {} WHERE id = %s
                    AND eliminado = FALSE RETURNING *""").format(sql.Identifier(nombre),
                    sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k))
                                       for k in cambios)), (*cambios.values(), id)).fetchone()
        if motor == "mongo":
            return self.documentos[nombre].find_one_and_update(
                {"id": id, "eliminado": False}, {"$set": cambios},
                return_document=ReturnDocument.AFTER, projection={"_id": 0})
        key = f"t301:{nombre}:{id}"
        for _ in range(10):
            with self.redis.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    value = pipe.get(key)
                    if not value:
                        return None
                    row = json.loads(value)
                    if row["eliminado"]:
                        return None
                    row.update(cambios)
                    pipe.multi()
                    pipe.set(key, json.dumps(row))
                    pipe.execute()
                    return row
                except WatchError:
                    continue
        from fastapi import HTTPException
        raise HTTPException(409, "Conflicto concurrente; reintente la operación")
