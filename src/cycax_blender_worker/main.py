import logging
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import bpy
import httpx
import matplotlib.colors as mcolors
from dotenv import load_dotenv

PART_NO_TEMPLATE = "Pn--pN"
logging.basicConfig(level=logging.INFO)


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
            self.set_task_state(job["id"], name, "COMPLETED")

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


def dict_get(data: dict, *args) -> Any:
    dd = data
    for arg in args[:-1]:
        dd = dd.get(arg, {})
    return dd.get(args[-1])


class AssemblyBlender:
    """Assemble the parts into an Blender model.

    Args:
        name: The part number of the complex part that is being assembled.
    """

    def __init__(self, spec: dict, base_worker_path: Path, client: CycaxClient) -> None:
        self.name = spec["name"]
        self._spec = spec
        self._client = client
        self._base_path = base_worker_path
        self.parts = {}
        objs = bpy.data.objects
        if "Cube" in objs:
            # Remove the small Cube that is on all new models.
            objs.remove(objs["Cube"], do_unlink=True)

    def _fetch_part(self, part_no: str, job_id: str):
        """Retrieves the part that will be imported and possitioned.

        Args:
            part: this is the name of the part that will be imported.
        """
        self._client.download_artifacts(
            job_id, part_no, self._base_path, extensions_only=[".stl"], overwrite=False, job_path=True
        )
        stl_file = self._base_path / job_id / f"{part_no}.stl"
        if not stl_file.exists():
            logging.warning("Referencing a file that does not exists. File name %s", stl_file)
            raise FileExistsError(stl_file)
        logging.info("Load file %s", stl_file)
        # bpy.ops.import_mesh.stl(filepath=str(stl_file))
        bpy.ops.wm.stl_import(filepath=str(stl_file))
        for obj in bpy.context.selected_objects:
            if part_no in self.parts:
                obj.name = f"{part_no}_{self.parts[part_no] + 1}"
                self.parts[part_no] = self.parts[part_no] + 1
            else:
                obj.name = f"{part_no}_{1}"
                self.parts[part_no] = 1

    def _swap_xy_(self, rotation: tuple, rot: float, rotmax: tuple) -> tuple:
        """Used to help rotate the object on the spot while freezing the top"""
        while rot != 0:
            max_x = rotmax[0]
            rotation[0], rotation[1] = rotation[1], max_x - rotation[0]
            rotmax[0], rotmax[1] = rotmax[1], rotmax[0]
            rot = rot - 1
        return rotation, rotmax

    def _swap_xz_(self, rotation: tuple, rot: float, rotmax: tuple) -> tuple:
        """Used to help rotate the object on the spot while freezing the front"""
        while rot != 0:
            max_z = rotmax[2]
            rotation[0], rotation[2] = max_z - rotation[2], rotation[0]
            rotmax[0], rotmax[2] = rotmax[2], rotmax[0]
            rot = rot - 1
        return rotation, rotmax

    def _swap_yz_(self, rotation: tuple, rot: float, rotmax: tuple) -> tuple:
        """Used to help rotate the object on the spot while freezing the left"""
        while rot != 0:
            max_y = rotmax[1]
            rotation[1], rotation[2] = rotation[2], max_y - rotation[1]
            rotmax[2], rotmax[1] = rotmax[1], rotmax[2]
            rot = rot - 1
        return rotation, rotmax

    def _move(self, rotmax: tuple, position: tuple, rotate: tuple):
        """Computes the moving and rotating of the STL to the desired location.

        Args:
            rotmax: This is the tuple that contains the original (x,y,z) location.
            position: This is the tuple that contains the amount which the (x,y,z) needs to move by.
            rotate: This is the tuple that contains the amount which the (x,y,z) needs to be rotated.
        """
        rotation = [0, 0, 0]
        for item in rotate:
            if item["axis"] == "x":
                bpy.ops.transform.rotate(value=math.radians(360 - 90), orient_axis="X")
                rotation, rotmax = self._swap_yz_(rotation, 3, rotmax)
            # blender does clockwise instead of anticlockwise rotations as we would expect in openscad.

            elif item["axis"] == "y":
                bpy.ops.transform.rotate(value=math.radians(360 - 90), orient_axis="Y")
                rotation, rotmax = self._swap_xz_(rotation, 3, rotmax)

            elif item["axis"] == "z":
                bpy.ops.transform.rotate(value=math.radians(360 - 90), orient_axis="Z")
                rotation, rotmax = self._swap_xy_(rotation, 3, rotmax)

        bpy.ops.transform.translate(
            value=(rotation[0] + position[0], rotation[1] + position[1], rotation[2] + position[2])
        )

    def _colour(self, colour: str, part: str):
        """Set the part colour.

        Args:
            colour: Colour which the part will become.
        """
        working_part = f"{part}_{self.parts[part]}"
        template_object = bpy.data.objects.get(working_part)
        colour_rgb = mcolors.to_rgb(colour)
        matcolour = bpy.data.materials.new(colour)
        matcolour.diffuse_color = (colour_rgb[0], colour_rgb[1], colour_rgb[2], 0.8)

        template_object.active_material = matcolour

    def add(self, part_operation: dict):
        """Add the part to the assembly."""
        self._fetch_part(part_operation["part_no"], part_operation["jobid"])
        self._move(part_operation["rotmax"], part_operation["position"], part_operation["rotate"])
        self._colour(part_operation["colour"], part_operation["part_no"])

    def build(self, job_id: str):
        """Create the assembly of the parts added."""

        for part in self._spec.get("parts", []):
            self.add(part)

        for screen_area in bpy.context.screen.areas:
            if screen_area.type == "VIEW_3D":
                # Set the clip depth from 1000 (1m) to 50m
                screen_area.spaces.active.clip_end = 50000
        logging.info("Saving the .blend file.")
        part_path = self._base_path / job_id
        part_path.mkdir(exist_ok=True)
        save_file = str(self._base_path / job_id / f"{self.name}.blend")
        bpy.ops.wm.save_as_mainfile(filepath=save_file)
        self._client.upload_artifacts("blender", job_id, self.name, self._base_path, job_path=True)


if __name__ == "__main__":
    load_dotenv()
    base_worker_path = Path("/tmp/cycax_blender_worker")
    base_worker_path.mkdir(parents=True, exist_ok=True)
    try:
        server_address = os.environ["CYCAX_SERVER"]
    except KeyError:
        logging.error("CYCAX_SERVER environment variable not set")
        sys.exit(1)
    logging.info("Connect to CYCAX server at %s", server_address)

    server = CycaxClient(server_address)
    while True:
        jobs = server.list_jobs(state_not_in="completed")
        if not jobs:
            time.sleep(10)
            logging.info("No Jobs Sleep for 10 seconds.")
            continue
        for job in jobs:
            blender_state = dict_get(job, "attributes", "state", "tasks", "blender")
            if blender_state not in (None, "COMPLETED"):
                spec = server.get_job_spec(job["id"])
                assembly = AssemblyBlender(spec, base_worker_path, server)
                assembly.build(job_id=job["id"])
            else:
                logging.info("Job %s is not an assembly.", job["id"])
