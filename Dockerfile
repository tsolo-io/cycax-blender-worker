# SPDX-FileCopyrightText: 2025 Tsolo.io
#
# SPDX-License-Identifier: Apache-2.0

FROM python:3.11

RUN apt-get update; apt-get install -y libxxf86vm-dev libxfixes-dev libxi-dev libxkbcommon-dev libgl-dev
RUN mkdir /app
WORKDIR /app
COPY dist/*.whl .
RUN pip install *.whl
ENTRYPOINT /usr/local/bin/cycax-blender-worker
