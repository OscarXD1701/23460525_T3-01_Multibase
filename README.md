# T3-01 · Proyecto multibase de datos

**Asignatura:** TÓPICOS DE BASE DE DATOS  
**Estudiante:** Oscar Emiliano Ramírez García · **Control:** 23460525  
**Institución:** Tecnológico Nacional de México, Campus Colima  
**Docente:** Francisco Cervantes  
**Entrega de la actividad:** 17 de noviembre de 2026, 11:59  
**Integrantes actuales:** Oscar Emiliano Ramírez García (trabajo individual).

Servicio web de una tienda construido con Python y FastAPI. Conecta simultáneamente
con tres motores reales: PostgreSQL, MongoDB y Redis. Los seis recursos admiten
GET, POST, PATCH y DELETE. Todo DELETE es lógico: conserva el registro, establece
`eliminado=true` y registra `eliminado_en`. No hay un endpoint de eliminación física.

## Recursos y distribución

| Recurso | Motor | Datos propios |
|---|---|---|
| `/clientes` | PostgreSQL, relacional | nombre, email |
| `/productos` | PostgreSQL, relacional | nombre, precio_centavos, stock |
| `/pedidos` | MongoDB, documental NoSQL | cliente_id, items, estado |
| `/resenas` | MongoDB, documental NoSQL | producto_id, cliente_id, puntuacion, comentario |
| `/carritos` | Redis, clave-valor | cliente_id, items |
| `/preferencias` | Redis, clave-valor | cliente_id, tema, idioma |

PostgreSQL usa tablas con columnas tipadas, claves primarias y restricciones numéricas;
MongoDB usa dos colecciones con índice único sobre `id`; Redis guarda un JSON por clave
`t301:recurso:uuid`. Redis es almacenamiento principal de dos recursos, no solo caché.
Se habilita AOF sin TTL. Los tres motores guardan sus datos en volúmenes Docker.

```mermaid
flowchart LR
  C[Cliente HTTP / Swagger] --> A[API FastAPI]
  A --> P[PostgreSQL: clientes y productos]
  A --> M[MongoDB: pedidos y resenas]
  A --> R[Redis: carritos y preferencias]
```

## Instalación y ejecución con Docker (recomendado)

Requisitos: Git y Docker Desktop activo con contenedores Linux, o Docker Engine
con el complemento Compose en Linux. No requiere instalar los motores por separado.

1. Abra una terminal en la raíz de este repositorio, donde está `compose.yaml`.
2. Opcional: copie `.env.example` a `.env` y cambie `API_PORT` si 8000 está ocupado.
   PowerShell: `Copy-Item .env.example .env`. Linux/macOS: `cp .env.example .env`.
3. Ejecute:

```sh
docker compose up --build -d --wait
docker compose ps
```

4. Abra [Swagger UI](http://127.0.0.1:8000/docs). Puede probar cada operación con
   **Try it out**. [ReDoc](http://127.0.0.1:8000/redoc) y
   [OpenAPI JSON](http://127.0.0.1:8000/openapi.json) describen los contratos.
5. Consulte [salud](http://127.0.0.1:8000/salud):

```json
{"estado":"ok","motores":["postgresql","mongodb","redis"]}
```

La aplicación crea automáticamente tablas e índices al iniciar. Compose espera que
los tres motores estén saludables antes de iniciar la API. Solo publica la API en
`127.0.0.1`; las bases de datos permanecen dentro de la red Docker.

```sh
docker compose logs api
docker compose stop
docker compose start
```

`stop` y `start` conservan datos. `docker compose down` retira contenedores y red,
pero conserva volúmenes. **No use `down -v`: elimina los datos de los volúmenes.**

### Instalación sin Docker para la API

Requiere Python 3.12 y tres servidores accesibles, ya instalados. En PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
$env:POSTGRES_URL = 'postgresql://usuario:clave@localhost:5432/tienda'
$env:MONGO_URL = 'mongodb://localhost:27017'
$env:MONGO_DB = 'tienda'
$env:REDIS_URL = 'redis://localhost:6379/0'
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Cree previamente la base `tienda` en PostgreSQL. El usuario necesita permiso para
crear tablas. Estas variables se leen del entorno; no se carga `.env` automáticamente
fuera de Compose. `requirements.lock` fija las versiones comprobadas; los otros
archivos de requisitos declaran las dependencias directas para mantenimiento.

## Operaciones HTTP

Las siguientes rutas existen **para cada uno de los seis recursos**:

| Método | Ruta | Resultado |
|---|---|---|
| GET | `/recurso?offset=0&limite=50` | 200, lista de activos; límite máximo 100 |
| GET | `/recurso/{id}` | 200, registro activo; 404 si falta o está borrado |
| POST | `/recurso` | 201, registro creado y cabecera Location |
| PATCH | `/recurso/{id}` | 200, actualiza solamente los campos enviados |
| DELETE | `/recurso/{id}` | 204 sin cuerpo; marca el registro como eliminado |

Los IDs son UUID generados por el servidor. Todos los registros incluyen `id`,
`creado_en`, `eliminado` y `eliminado_en` (fechas UTC ISO 8601). El cliente no puede
crear ni cambiar estos metadatos. PATCH rechaza objetos vacíos, campos desconocidos,
valores nulos y valores que no cumplen el esquema. Los arreglos enviados en PATCH
sustituyen el arreglo completo. Un segundo DELETE devuelve 404 y no cambia la marca.

Errores: 422 para cuerpos, UUID o referencias inválidas; 404 para registros inactivos
o inexistentes; 409 si se agotan los reintentos de una modificación concurrente de
Redis; 503 si falla un motor. No se revelan credenciales en errores HTTP.

### Cuerpos para crear los seis recursos

Primero cree un cliente y un producto. Copie sus `id` en los campos indicados para
pedidos, reseñas, carritos y preferencias. Los textos `UUID_CLIENTE` y `UUID_PRODUCTO`
son marcadores y deben reemplazarse por UUID reales.

**POST /clientes**
```json
{"nombre":"Ana Pérez","email":"ana@example.com"}
```
**POST /productos**
```json
{"nombre":"Café molido 500 g","precio_centavos":8950,"stock":20}
```
**POST /pedidos**
```json
{"cliente_id":"UUID_CLIENTE","items":[{"producto_id":"UUID_PRODUCTO","cantidad":2}],"estado":"pendiente"}
```
**POST /resenas**
```json
{"cliente_id":"UUID_CLIENTE","producto_id":"UUID_PRODUCTO","puntuacion":5,"comentario":"Buen producto"}
```
**POST /carritos**
```json
{"cliente_id":"UUID_CLIENTE","items":[{"producto_id":"UUID_PRODUCTO","cantidad":1}]}
```
**POST /preferencias**
```json
{"cliente_id":"UUID_CLIENTE","tema":"oscuro","idioma":"es"}
```

Precio y stock son enteros no negativos. `precio_centavos=8950` representa $89.50 MXN.
Las cantidades van de 1 a 10000; puntuación de 1 a 5. Un pedido requiere al menos un
producto; un carrito puede quedar vacío. Estados: pendiente, pagado, enviado.
Temas: claro, oscuro. Idiomas: es, en.

### Ejemplo completo en PowerShell

```powershell
$base = 'http://127.0.0.1:8000'
$producto = Invoke-RestMethod "$base/productos" -Method Post -ContentType 'application/json' -Body '{"nombre":"Arroz","precio_centavos":3375,"stock":10}'
Invoke-RestMethod "$base/productos/$($producto.id)"
Invoke-RestMethod "$base/productos/$($producto.id)" -Method Patch -ContentType 'application/json' -Body '{"stock":8}'
Invoke-RestMethod "$base/productos/$($producto.id)" -Method Delete
# El siguiente GET devuelve 404; el registro sigue almacenado como eliminado.
Invoke-RestMethod "$base/productos/$($producto.id)"
```

También puede ejecutar una demostración de **los seis recursos** sin paquetes extra:

```sh
python scripts/demo.py
```

O dentro del contenedor, si no tiene Python en el equipo:

```sh
docker compose exec api python scripts/demo.py http://127.0.0.1:8000
```

La demo crea datos nuevos, hace GET y PATCH, y finalmente aplica DELETE lógico.
Para otro puerto: `python scripts/demo.py http://127.0.0.1:8080`.

## Pruebas y verificación del borrado lógico

```sh
docker compose exec -T api python -m unittest -v tests.test_api
```

Son pruebas de integración contra PostgreSQL, MongoDB y Redis reales, no sustitutos
en memoria. Cubren los 30 endpoints de recursos, los seis ciclos CRUD, contratos de
OpenAPI, referencias, entradas inválidas, paginación, metadatos protegidos y cambios
concurrentes en los tres motores. Después de DELETE inspeccionan directamente cada
motor y comprueban que el registro **todavía existe**, está marcado y no aparece en GET.
Las pruebas dejan sus registros borrados lógicamente como evidencia y pueden repetirse.
El flujo de GitHub Actions ejecuta la misma suite cuando se publique el repositorio.

Consulta manual de registros borrados:

```sh
docker compose exec postgres psql -U tienda -d tienda -c "SELECT id, eliminado, eliminado_en FROM productos;"
docker compose exec mongo mongosh tienda --quiet --eval 'db.pedidos.find({eliminado:true},{_id:0})'
docker compose exec redis redis-cli --scan --pattern 't301:preferencias:*'
# Copie una clave obtenida y consulte su contenido:
docker compose exec redis redis-cli GET 't301:preferencias:UUID_REAL'
```

## Decisiones y alcance

- Cada recurso tiene datos propios y un esquema distinto. Las referencias entre
  motores se comprueban al crear o modificar la referencia. Una referencia histórica
  puede permanecer apuntando a un registro borrado; no hay borrado en cascada.
- No se simula una transacción distribuida: una operación escribe en un solo motor.
  Una baja concurrente del registro referenciado podría ocurrir tras validar su existencia.
- PostgreSQL actualiza solo las columnas enviadas; MongoDB utiliza `$set`; Redis usa
  WATCH/MULTI/EXEC con reintentos para evitar que dos PATCH pierdan campos distintos.
- Es un servicio CRUD académico. Cambiar un pedido a pagado no cobra ni descuenta stock;
  no implementa contabilidad, precios históricos ni transiciones de negocio adicionales.
- Las listas usan orden por ID, no por fecha. En Redis se recorre el conjunto de claves
  del recurso; este enfoque está destinado al volumen pequeño del proyecto.
- No hay autenticación de usuarios. La configuración expone únicamente localhost y usa
  credenciales de demostración. Para desplegar públicamente debe añadirse autenticación,
  TLS y credenciales propias; no publique los puertos de los motores.

## Estructura

```text
app/models.py          Contratos y catálogo de recursos
app/stores.py          Conexiones y persistencia en tres motores
app/main.py            Rutas, validación de referencias y errores HTTP
tests/test_api.py      Pruebas HTTP con motores reales
scripts/demo.py        Demostración reproducible de los seis recursos
compose.yaml           API, motores, comprobaciones de salud y volúmenes
Dockerfile             Imagen de la aplicación, usuario sin privilegios
requirements.lock      Versiones exactas verificadas
.github/workflows/     Comprobación de integración al publicar en GitHub
evidencias/            Salida real de las comprobaciones de esta entrega
```

## Repositorio e integrantes

Repositorio público de entrega:

**https://github.com/OscarXD1701/23460525_T3-01_Multibase**

Incluye código, README, pruebas, evidencias y el historial completo. El docente puede
consultarlo sin iniciar sesión. El trabajo es individual: los commits conservan la
autoría de Oscar Emiliano Ramírez García. Si se incorpora otra persona, debe configurar
su identidad y realizar sus propios commits; agregar su nombre al README no sustituye
su contribución.

Para descargar e iniciar el proyecto:

```sh
git clone https://github.com/OscarXD1701/23460525_T3-01_Multibase.git
cd 23460525_T3-01_Multibase
docker compose up --build -d --wait
```

Para entregar en Classroom, comparta la URL del repositorio. El PDF de evidencias es
complementario y está disponible en
[evidencias/23460525_T3-01_Evidencias.pdf](evidencias/23460525_T3-01_Evidencias.pdf).
Las capturas y transcripciones documentan el estado del proyecto durante su ejecución
local, anterior a la publicación; no describen la visibilidad actual del repositorio.

Para revisar la autoría: `git log --format=fuller`.

## Uso de inteligencia artificial y referencias

Codex de OpenAI apoyó el diseño, la implementación, las pruebas y la documentación.
El estudiante conserva la responsabilidad de comprender el código y demostrar su
funcionamiento. Las evidencias distinguen verificaciones ejecutadas de pasos pendientes.

Documentación técnica consultada:

1. [FastAPI: actualizaciones parciales](https://fastapi.tiangolo.com/tutorial/body-updates/).
2. [Psycopg: uso básico y consultas parametrizadas](https://www.psycopg.org/psycopg3/docs/basic/usage.html).
3. [PyMongo: operaciones CRUD](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/).
4. [Redis: cliente Python](https://redis.io/docs/latest/develop/clients/redis-py/).
5. [Docker Compose: inicio de servicios](https://docs.docker.com/reference/cli/docker/compose/up/).

### Evidencia de persistencia

`evidencias/pruebas.txt` contiene la ejecución real de las siete pruebas de integración;
`evidencias/demo.txt`, la demostración HTTP; `evidencias/persistencia.txt`, la prueba de
indisponibilidad y reinicio. Se compararon los IDs y las marcas `eliminado` de los seis
recursos antes y después de reiniciar los tres motores. Coincidieron; Redis conservó
sus claves sin expiración. Con Redis detenido, GET /preferencias respondió 503.

Puede obtener su propia instantánea con:

```sh
docker compose exec -T api python -m scripts.verificar_retencion
```

Los registros de prueba se conservan marcados como eliminados. El servicio queda
listo para crear sus propios registros desde `/docs`. El repositorio se publicó posteriormente en GitHub, conservando estos archivos
como evidencia histórica de la ejecución local.
