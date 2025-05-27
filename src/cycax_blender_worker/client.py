# SPDX-FileCopyrightText: 2025 Tsolo.io
#
# SPDX-License-Identifier: Apache-2.0

import logging
import time
from pathlib import Path

import httpx

PART_NO_TEMPLATE = "Pn--pN"


def check_extension(extensions_only: list[str] | None, aid: str) -> bool:
    if not extensions_only:
        return True
    for ext in extensions_only:
        if aid.endswith(ext):
            return True
    return False


class CycaxClient:
    def __init__(self, server_address):
        self.server_address = server_address
        self._client = None

    def connect(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.server_address)
        return self._client

    def _get_resource(self, path: str) -> dict:
        client = self.connect()
        response = client.get(path)
        response.raise_for_status()
        data = response.json()
        return data["data"]

    def _get_resource_list(self, path: str, parameters: dict[str, str] | None = None) -> list[dict]:
        client = self.connect()
        response = client.get(path, params=parameters)
        response.raise_for_status()
        data = response.json()
        return list(data["data"])

    def list_jobs(self, state_in: str | None = None, state_not_in: str | None = None) -> list[dict]:
        logging.info("Listing jobs from CYCAX server at %s", self.server_address)
        parameters = {}
        if state_in:
            parameters["state_in"] = state_in.upper()
        if state_not_in:
            parameters["state_not_in"] = state_not_in.upper()
        return self._get_resource_list("/jobs", parameters=parameters)

    def get_job(self, job_id: str) -> dict:
        logging.info("Getting job from CYCAX server at %s for job %s", self.server_address, job_id)
        return self._get_resource(f"/jobs/{job_id}")

    def get_job_spec(self, job_id: str) -> dict:
        logging.info("Getting job spec from CYCAX server at %s for job %s", self.server_address, job_id)
        return self._get_resource(f"/jobs/{job_id}/spec")

    def upload_file(self, job_id: str, filepath: Path):
        client = self.connect()
        url = f"/jobs/{job_id}/artifacts"
        logging.info("Upload file %s to %s", filepath, url)
        files = {"upload_file": filepath.read_bytes()}
        file_details = {"filename": filepath.name}
        response = client.post(url, files=files, data=file_details, timeout=20)
        logging.info(response)

    def set_task_state(self, job_id: str, name: str, state: str):
        client = self.connect()
        url = f"/jobs/{job_id}/tasks"
        payload = {"name": name, "state": state}
        response = client.post(url, json=payload, timeout=20)
        logging.info(response)
        # Check the state. The server should raise some error if state change was not allowed.

    def upload_artifacts(
        self,
        name: str,
        job_id: str,
        part_no: str,
        base_path: Path,
        extensions_only: list[str] | None = None,
        *,
        job_path: bool = False,
    ):
        if job_path:
            part_path = base_path / job_id
        else:
            part_path = base_path / part_no

        count = 0
        for filepath in part_path.iterdir():
            if check_extension(extensions_only=extensions_only, aid=str(filepath)):
                retry = 3
                while retry > 0:
                    try:
                        self.upload_file(job_id, filepath)
                        count += 1
                    except Exception:
                        retry -= 1
                        time.sleep(3)
                    else:
                        break  # out of the while loop
                if retry == 0:
                    break  # out of the for loop, skip for-else.
        if count > 1:
            # Success
            self.set_task_state(job_id, name, "COMPLETED")

    def download_artifacts(
        self,
        job_id: str,
        part_no: str,
        base_path: Path,
        *,
        extensions_only: list[str] | None = None,
        overwrite: bool = True,
        job_path: bool = False,
    ):
        """Download the artifacts for a specific Job.

        Args:
            job_id: The Job ID on CyCAx server.
            part_no: The part number.
            base_path: The directory job or part directories are made in.
            extensions_only: Filter the downloaded file to only these types.
            overwrite: If we can overwrite existing files.
            job_path: If we are using job_id or part_no to make the directories.
        """

        client = self.connect()
        reply = client.get(f"/jobs/{job_id}/artifacts")

        if job_path:
            part_path = base_path / job_id
        else:
            part_path = base_path / part_no
        part_path.mkdir(exist_ok=True)
        for artifact_obj in reply.json().get("data"):
            logging.warning(artifact_obj)
            artifact_id = artifact_obj.get("id")
            if artifact_id and artifact_obj.get("type") == "artifact" and check_extension(extensions_only, artifact_id):
                artifact_path = part_path / artifact_id.replace(PART_NO_TEMPLATE, part_no)
                if not artifact_path.exists() or overwrite:
                    areply = client.get(f"/jobs/{job_id}/artifacts/{artifact_id}")
                    artifact_path.write_bytes(areply.content)
                    logging.info("Saved download to %s", artifact_path)
                else:
                    logging.info("Skip download of %s", artifact_path)
