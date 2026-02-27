from mangum import Mangum # pyright: ignore[reportMissingImports]
from main import app

handler = Mangum(app, lifespan="off")