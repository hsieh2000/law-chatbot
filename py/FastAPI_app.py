from fastapi import FastAPI, Request
import json
import pandas as pd
import re
import os
from google.cloud.sql.connector import Connector, IPTypes
import pg8000
import sqlalchemy
# import vertexai
# from vertexai.generative_models import GenerativeModel
import google.generativeai as genai
from fastapi.responses import JSONResponse

app = FastAPI()

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

@app.get("/")
def read_root():
    # 連線google ai
    genai.configure(api_key="YOUR_API_KRY")
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    response = model.generate_content("自我介紹")
    print(response.text)
    return {"Hello": response.text}


@app.post("/dialogflow")
async def dailogflow(request: Request):
    req = await request.json()
    print(req['sessionInfo']["parameters"]['$flow.regulation-id-response'])

    print(req)

    return JSONResponse(content={
        "fulfillmentResponse": {
            "messages": [{
                "text": {
                    "text": [
                        req['sessionInfo']["parameters"]['$flow.regulation-id-response']+" "+req['text']
                        # req['text']
                    ]
                }
            }]
        }
    }, status_code=200)

@app.post("/webhook")
async def send(request: Request):
    req = await request.json()
    law_num = req['sessionInfo']["parameters"]['$flow.regulation-id-response']
    law_num = "".join(law_num.split())

    law_list = re.findall("第\d+-*\d?條", law_num)
    law_preprocess_sting = list(map(lambda x: f"article_no = '{x}'", law_list))
    case_preprocess_sting = list(map(lambda x: f"cited_law like \'%{x.replace('第', '').replace('條', '')}%\'", law_list))
    law_query_condition = " and ".join(law_preprocess_sting)
    case_query_condition = " and ".join(case_preprocess_sting)

    print(law_num)
    print(f"""SELECT article_content FROM APARTMENT_LAW WHERE {law_query_condition}""")
    print(f"""SELECT * FROM LAW_CASE WHERE {case_query_condition}""")
    pool = connect_with_connector()
    with pool.connect() as db_conn:

        law = db_conn.execute(sqlalchemy.text(f"""SELECT article_content FROM APARTMENT_LAW WHERE {law_query_condition}""")).fetchall()
        results = db_conn.execute(sqlalchemy.text(f'SELECT * FROM LAW_CASE WHERE {case_query_condition}')).fetchall()

    law_ref = "\n".join(list(map(lambda x, y: f"公寓大廈管理條例{x} : {y}", law_list, law[0])))
    # print(law)
    # print(results)

    # 連線vertex ai
    # vertexai.init(project="law-chatbot-431613", location="us-central1")
    # model = GenerativeModel("gemini-1.5-flash-001")

    # 連線google ai
    genai.configure(api_key="AIzaSyBDyl6TNC3GgrjXymxy4EYcREM5uB27rVU")
    model = genai.GenerativeModel('gemini-1.5-flash')



    if len(results) == 0:
         response = model.generate_content(f"""你是一個法律專家，使用者的問題為:{req['text']}，
                                           請參考以下法規已盡可能通俗簡單的方式來回答使用者的問題，
                                           在回答時請先告知這是哪一條法規的規範範圍，
                                           再回答使用者的問題。
                                           回答盡可能限制在200字以內。
                                           {law_ref}""")
    else:

        df = pd.DataFrame(results, columns=['id', 'case_title',
                                        'court_opinion', 'court_opinion_seg',
                                        'vernacular_opinion',
                                        'cited_law'])
        
        law_num = law_num.replace("第", "").replace("條", "").replace(" ", "")
        print(law_num)

        # 目前僅使用由人工轉譯為白話文的欄位，自原始法院見解自動摘要並轉譯的功能尚未開發
        data = df.apply(lambda x: f"{x['case_title']}:{x['vernacular_opinion']}", axis=1).to_list()
        response = model.generate_content(f"""你是一個法律專家，使用者的問題為:{req['text']}，
                                          請參考以下的公寓大廈管理條例以及判決的法院見解後回答使用者的問題，
                                          回答時請告知你參考的法規是哪一條以及參考了哪些判決，以盡可能通俗簡單的方式回答使用者的問題。
                                          回答盡可能限制在200字以內。
                                          {law_ref}\n
                                          法院見解 : {data}""")

    return JSONResponse(
        content={
            "fulfillmentResponse": {
                "messages": [{
                    "text": {
                        "text": [
                            response.text
                        ]
                    }
                }]
            }
        }, status_code=200)


