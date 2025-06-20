# SPDX-FileCopyrightText: 2025 Tsolo.io
#
# SPDX-License-Identifier: Apache-2.0

import logging
import sys
import time
from typing import Any

import httpx
from dotenv import load_dotenv

from cycax_blender_worker.assembler import AssemblyBlender
from cycax_blender_worker.client import CycaxClient
from cycax_blender_worker.config import Config

logging.basicConfig(level=logging.INFO)


def dict_get(data: dict, *args) -> Any:
    dd = data
    for arg in args[:-1]:
        dd = dd.get(arg, {})
    return dd.get(args[-1])


def main():
    load_dotenv()
    config = Config()
    base_worker_path = config.temp_dir
    base_worker_path.mkdir(parents=True, exist_ok=True)
    try:
        server_address = config.server
    except KeyError:
        logging.error("CYCAX_SERVER environment variable not set")
        sys.exit(1)
    logging.info("Connect to CYCAX server at %s", server_address)

    server = CycaxClient(config.server)
    connection = None
    while connection is None:
        try:
            connection = server.connect()
        except httpx.ConnectError:
            logging.warning("Could not connect to CYCAX server as %s", config.server)
            time.sleep(20)

    while True:
        try:
            jobs = server.list_jobs(state_not_in="completed")
        except httpx.ConnectError:
            logging.warning("Could not connect to CYCAX server as %s", config.server)
            time.sleep(20)
            continue
        if not jobs:
            logging.info("No Jobs Sleep for 10 seconds.")
            time.sleep(10)
            continue
        for job in jobs:
            blender_state = dict_get(job, "attributes", "state", "tasks", "blender")
            if blender_state not in (None, "COMPLETED"):
                spec = server.get_job_spec(job["id"])
                assembly = AssemblyBlender(spec, base_worker_path, server)
                assembly.build(job_id=job["id"])
            else:
                logging.info("Job %s is not an assembly.", job["id"])


if __name__ == "__main__":
    main()
