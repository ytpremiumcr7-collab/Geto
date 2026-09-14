from app.sources.ais.adapter import AISFileAdapter
from app.sources.aviation_weather.adapter import AviationWeatherAdapter
from app.sources.base import SourceAdapter
from app.sources.celestrak.adapter import CelesTrakAdapter
from app.sources.copernicus.adapter import CopernicusSTACAdapter
from app.sources.firms.adapter import NASAFIRMSAdapter
from app.sources.goes.adapter import GOESAdapter
from app.sources.horizons.adapter import JPLHorizonsAdapter
from app.sources.minio_dropzone.adapter import MinIODropzoneAdapter
from app.sources.nexrad.adapter import NEXRADAdapter
from app.sources.opensky.adapter import OpenSkyAdapter
from app.sources.readsb.adapter import ReadsbLocalAdapter
from app.sources.usgs.adapter import USGSEarthquakeAdapter


def create_adapters() -> dict[str, SourceAdapter]:
    return {
        "opensky": OpenSkyAdapter(),
        "readsb_local": ReadsbLocalAdapter(),
        "ais_file": AISFileAdapter(),
        "jpl_horizons": JPLHorizonsAdapter(),
        "nexrad": NEXRADAdapter(),
        "goes": GOESAdapter(),
        "celestrak": CelesTrakAdapter(),
        "usgs_earthquake": USGSEarthquakeAdapter(),
        "nasa_firms": NASAFIRMSAdapter(),
        "aviation_weather": AviationWeatherAdapter(),
        "copernicus": CopernicusSTACAdapter(),
        "minio_dropzone": MinIODropzoneAdapter(),
    }
