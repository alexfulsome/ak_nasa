import subprocess
import logging
import os
import sys
import time
import json
import http.client
from urllib.parse import urlencode, urlparse
from datetime import datetime, timedelta
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class RateLimiter:
    def __init__(self, rate, capacity):
        self.capacity = capacity
        self._tokens = capacity
        self.rate = rate
        self.last_refill = time.time()
        self._thread = threading.Thread(target=self._refill_task)
        self._thread.daemon = True
        self._thread.start()

    def consume(self, tokens=1):
        self.refill()
        if tokens <= self._tokens:
            self._tokens -= tokens
            return True

        return False

    def refill(self):
        now = time.time()
        added_tokens = (now - self.last_refill) * self.rate
        self._tokens = min(self.capacity, self._tokens + added_tokens)
        self.last_refill = now

    def _refill_task(self):
        while True:
            self.refill()
            time.sleep(1)


class Client:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_uri = "https://api.nasa.gov/mars-photos/api/v1"

    def get(self, endpoint, params=None):
        if params is None:
            params = {}
        params["api_key"] = self.api_key

        parsed_uri = urlparse(self.base_uri)
        netloc = parsed_uri.netloc
        scheme = parsed_uri.scheme

        path = f"{parsed_uri.path}/{endpoint}?{urlencode(params)}"

        if scheme == "https":
            connection = http.client.HTTPSConnection(netloc)
        else:
            connection = http.client.HTTPConnection(netloc)

        connection.request("GET", path)
        response = connection.getresponse()

        rate_limit_remaining = response.getheader('X-RateLimit-Remaining')
        logging.debug('Rate limit remaining:', rate_limit_remaining)


        if response.status < 200 or response.status >= 300:
            connection.close()
            raise http.client.HTTPException(
                f"HTTP request {path} failed with status {response.status}"
            )

        response_data = response.read()
        connection.close()

        response_json = json.loads(response_data)

        return Response(response_json)


class Response:
    def __init__(self, data):
        if isinstance(data, dict):
            self._data = {k: self._convert(v) for k, v in data.items()}
        else:
            self._data = data

    def _convert(self, value):
        if isinstance(value, dict):
            return Response(value)
        elif isinstance(value, list):
            return [self._convert(item) for item in value]
        return value

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"something went wrong trying to access '{name}'")

    def __repr__(self):
        return f"<Response {self._data}>"


class NasaApi:
    def __init__(self, api_key):
        self.client = Client(api_key)

    def get_manifest(self, rover):
        endpoint = f"manifests/{rover}"
        response = self.client.get(endpoint)
        return response

    def get_photos(self, rover, earth_date):
        endpoint = f"rovers/{rover}/photos"
        params = {"earth_date": earth_date}
        response = self.client.get(endpoint, params=params)
        return response


if __name__ == "__main__":
    api_key = os.getenv("API_KEY")
    rover = os.getenv("ROVER")
    camera_name = os.getenv("CAMERA")

    if not api_key or not rover or not camera_name:
        raise EnvironmentError("API_KEY, ROVER, and CAMERA must be set.")

    photos_dir = "photos"
    if not os.path.exists(photos_dir):
        os.makedirs(photos_dir)
        logging.info(f"Directory created: {photos_dir}")

    # this controls how quickly you hit the api. you technically have 1000/hr
    # but this plays it safe. change the 800 to whatever you want.
    rate_per_second = 800 / 3600  # 800 calls per hour divided by the number of seconds in an hour
    capacity = 800  # Assuming you want the bucket capacity to be 800 calls (full hour's worth)
    token_bucket = RateLimiter(rate=rate_per_second, capacity=capacity)

    nasa_api = NasaApi(api_key)

    manifest_response = nasa_api.get_manifest(rover)
    dates = [photo.earth_date for photo in manifest_response.photo_manifest.photos]
    cursor = f"{rover}_{camera_name}_next_date.txt"

    try:
        with open(cursor, "r") as file:
            last_processed_date = file.read().strip()
    except FileNotFoundError:
        last_processed_date = None

    start_index = 0
    if last_processed_date in dates:
        start_index = dates.index(last_processed_date) + 1

    dates_to_process = dates[start_index:]

    if not dates_to_process or all(item is None for item in dates_to_process):
        logging.info("Nothing left to process.")
        sys.exit(0)

    for date in dates_to_process:
        while not token_bucket.consume(tokens=1):
            time.sleep(1)

        logging.info(f"Starting {date}")
        photos_response = nasa_api.get_photos(rover, date)

        img_src_urls = [
            photo.img_src
            for photo in photos_response.photos
            if photo.camera.name == camera_name
        ]

        if any(img_src_urls):
            daily_photos_dir = os.path.join(
                photos_dir, f"{rover}_{camera_name}_{date}"
            )

            if not os.path.exists(daily_photos_dir):
                os.makedirs(daily_photos_dir)

            logfile_destination = os.path.join(daily_photos_dir, "urls.txt")
            with open(logfile_destination, "w") as file:
                file.writelines(f"{image_url}\n" for image_url in img_src_urls)

            for image_url in img_src_urls:
                file_path = os.path.join(daily_photos_dir, image_url.split("/")[-1])

                try:
                    # pulling the images with the http stdlib times out every time for some reason
                    subprocess.run(
                        ["curl", "-L", image_url, "-o", file_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True,
                    )
                    logging.info(f"Image downloaded: {file_path}")
                except subprocess.CalledProcessError as e:
                    logging.error(f"Failed to download image: {e.stderr.decode()}")
        else:
            logging.info(f"No {camera_name} photos for this date")

        date = datetime.strptime(date, "%Y-%m-%d")
        date += timedelta(days=1)

        with open(cursor, "w") as file:
            file.write(date.strftime("%Y-%m-%d"))

    logging.info("Finished.")
