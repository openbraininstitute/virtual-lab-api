from pathlib import Path

from fastapi import APIRouter, Response

COUNTRY = (Path(__file__).parent.parent / "static/country.json").open().read()


def read_countries() -> Response:
    return Response(content=COUNTRY, media_type="application/json")


router = APIRouter(
    prefix="/config",
    tags=["Configuration"],
)

read_countries = router.get("/countries")(read_countries)
