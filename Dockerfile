FROM python:3.9

RUN python --version
COPY ./requirements.txt /app/requirements.txt

WORKDIR /app

RUN pip install -r requirements.txt

COPY . /app

EXPOSE 8888
CMD ["uvicorn", "paissadb.main:app", "--host", "0.0.0.0", "--port", "8888"]
