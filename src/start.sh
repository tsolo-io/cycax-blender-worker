#!/usr/bin/bash

# SPDX-FileCopyrightText: 2025 Tsolo.io
#
# SPDX-License-Identifier: Apache-2.0
set -eu
while true
do
    # Run in an endless loop.
    # The blender drawings leave artifacts behind,
    # A simple solution is to restart the service after every drawing.
    python3 /app/src/cycax_blender_worker/main.py
done
