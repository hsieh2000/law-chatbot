from flask import Flask, request,jsonify
import json
import pandas as pd
import os
from google.cloud.sql.connector import Connector, IPTypes
import pg8000
import sqlalchemy
import vertexai
from vertexai.generative_models import GenerativeModel

# 連線Cloud sql
def connect_with_connector() -> sqlalchemy.engine.base.Engine:
    """
    Initializes a connection pool for a Cloud SQL instance of Postgres.

    Uses the Cloud SQL Python Connector package.
    """
    # Note: Saving credentials in environment variables is convenient, but not
    # secure - consider a more secure solution such as
    # Cloud Secret Manager (https://cloud.google.com/secret-manager) to help
    # keep secrets safe.

    instance_connection_name = "law-chatbot-431613:us-central1:law-db"

    db_user = "admin"
    db_pass = "admin"
    db_name = "law-chatbot"

    ip_type = IPTypes.PRIVATE if os.environ.get("PRIVATE_IP") else IPTypes.PUBLIC

    # initialize Cloud SQL Python Connector object
    connector = Connector()

    def getconn() -> pg8000.dbapi.Connection:
        conn: pg8000.dbapi.Connection = connector.connect(
            instance_connection_name,
            "pg8000",
            user=db_user,
            password=db_pass,
            db=db_name,
            ip_type=ip_type,
        )
        return conn

    # The Cloud SQL Python Connector can be used with SQLAlchemy
    # using the 'creator' argument to 'create_engine'
    pool = sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        # ...
    )
    return pool

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    return 'Test', 200

@app.route("/dialogflow", methods=["GET", "POST"])
def dailogflow():
    req = request.get_json()
    print(req['sessionInfo']["parameters"]['$flow.regulation-id-response'])

    return jsonify({
        "fulfillmentResponse": {
            "messages": [{
                "text": {
                    "text": [
                        req['sessionInfo']["parameters"]['$flow.regulation-id-response']
                    ]
                }
            }]
        }
    })

@app.route("/send", methods=["GET", "POST"])
def send():
    req = request.get_json()
    law_num = req['sessionInfo']["parameters"]['$flow.regulation-id-response']
    print(law_num)

    pool = connect_with_connector()
    with pool.connect() as db_conn:
        results = db_conn.execute(sqlalchemy.text(f"SELECT * FROM LAW_CASE")).fetchall()
    print(results)

    df = pd.DataFrame(results, columns=['id', 'case_title', 'case_content',
                                    'court_opinion', 'court_opinion_seg',
                                    'vernacular_opinion',
                                    'cited_law'])
    
    law_num = law_num.replace("第", "").replace("條", "").replace(" ", "")
    print(law_num)
    
    court_opinion_seg = df[df['cited_law'].str.contains("31")]["court_opinion_seg"].iloc[0]
    print(court_opinion_seg)

    # 連線gemini
    vertexai.init(project="law-chatbot-431613", location="us-central1")
    model = GenerativeModel("gemini-1.5-flash-001")

    response = model.generate_content(f"請閱讀以下法院見解後轉換為白話文告訴我這在說什麼，回答請限縮在100字內。\n法院見解：{court_opinion_seg}")

    return jsonify({
        "fulfillmentResponse": {
            "messages": [{
                "text": {
                    "text": [
                        response.text
                    ]
                }
            }]
        }
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050,debug = True)