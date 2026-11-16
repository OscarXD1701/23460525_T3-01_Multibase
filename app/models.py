"""Contratos de los seis recursos. El dinero se representa en centavos MXN."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

Nombre = Annotated[str, Field(min_length=1, max_length=120)]
Entero = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)]
Cantidad = Annotated[int, Field(strict=True, ge=1, le=10_000)]

class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Cliente(Modelo):
    nombre: Nombre
    email: Annotated[str, Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]

class Producto(Modelo):
    nombre: Nombre
    precio_centavos: Entero
    stock: Entero = 0

class Linea(Modelo):
    producto_id: UUID
    cantidad: Cantidad

class Pedido(Modelo):
    cliente_id: UUID
    items: Annotated[list[Linea], Field(min_length=1, max_length=100)]
    estado: Literal["pendiente", "pagado", "enviado"] = "pendiente"

class Resena(Modelo):
    producto_id: UUID
    cliente_id: UUID
    puntuacion: Annotated[int, Field(strict=True, ge=1, le=5)]
    comentario: Annotated[str, Field(min_length=1, max_length=1000)]

class Carrito(Modelo):
    cliente_id: UUID
    items: Annotated[list[Linea], Field(max_length=100)] = []

class Preferencia(Modelo):
    cliente_id: UUID
    tema: Literal["claro", "oscuro"] = "claro"
    idioma: Literal["es", "en"] = "es"

RECURSOS = {
    "clientes": (Cliente, "postgres"),
    "productos": (Producto, "postgres"),
    "pedidos": (Pedido, "mongo"),
    "resenas": (Resena, "mongo"),
    "carritos": (Carrito, "redis"),
    "preferencias": (Preferencia, "redis"),
}
