FROM python:3.12-alpine

RUN apk add --no-cache gcc musl-dev

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8765

CMD ["python", "-m", "matchmaker.matchmaker_service"]
