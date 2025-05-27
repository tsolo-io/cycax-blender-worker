FROM python:3.11

RUN apt-get update; apt-get install -y libxxf86vm-dev libxfixes-dev libxi-dev libxkbcommon-dev libgl-dev
RUN mkdir /app
WORKDIR /app
# COPY . .
# RUN pip install --no-cache-dir -r requirements.txt
COPY dist/*.whl .
RUN pip install *.whl
ENTRYPOINT /app/src/start.sh
