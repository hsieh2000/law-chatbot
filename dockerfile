FROM python:3.9.19

RUN mkdir /app/

WORKDIR /app/

COPY ./requirements.txt .

COPY ./py/FastAPI_app.py .

# COPY ./service_account_key/law-chatbot-431613-50d3c8fecd6d.json .

# ENV GOOGLE_APPLICATION_CREDENTIALS="/app/law-chatbot-431613-50d3c8fecd6d.json"

RUN pip install -r requirements.txt

EXPOSE 5050

CMD ["uvicorn", "FastAPI_app:app", "--reload", "--host", "0.0.0.0", "--port", "5050"]
# CMD ["python", "FastAPI_app.py"]

