FROM python:3.12

RUN mkdir /data
ENV CYCAX_VAR_DIR=/data
RUN mkdir /app
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
ENTRYPOINT /app/src/start.sh
