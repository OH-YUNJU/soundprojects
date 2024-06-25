from fastapi import FastAPI, HTTPException, Request, status, File, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing_extensions import Annotated
import sys
import contextlib
import requests
import librosa
import librosa.display
from sklearn.preprocessing import LabelEncoder
from keras.models import load_model
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import tempfile
import os
import shutil
from pydub import AudioSegment
from io import BytesIO
from io import StringIO
import io
import json
from starlette.requests import Request
from datetime import datetime
from database import db_conn
from models import CycleData
from dotenv import load_dotenv
import csv
from io import BytesIO, StringIO
import base64
from pydantic import BaseModel
from sqlalchemy import create_engine, select, desc
from datetime import datetime, timedelta

# BASE_DIR 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.relpath("./")))
dotenv_path = os.path.join(BASE_DIR, '.env')

# .env 파일 로드
load_dotenv(dotenv_path)

# 환경 변수 가져오기
HOSTNAME = os.getenv("Mysql_Hostname")
PORT = os.getenv("Mysql_Port")
USERNAME = os.getenv("Mysql_Username")
PASSWORD = os.getenv("Mysql_Password")

app = FastAPI()

db = db_conn()
session = db.sessionmaker()


def extract_feature(file_name):
    print("Starting feature extraction for:", file_name)  # 디버그 출력 추가
    audio_data, sample_rate = librosa.load(file_name, sr=None, res_type='kaiser_fast')

    mfccs = librosa.feature.mfcc(y=audio_data, sr=sample_rate, n_mfcc=40)
    mfccsscaled = np.mean(mfccs.T, axis=0)
    print("Feature extraction successful")  
    return np.array([mfccsscaled])

#CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


################################################api start#################################################


@app.get('/test')
async def test():
    result = session.query(CycleData)
    return result.all()


@app.post('/cycle/record-analyze')
async def cycle_recordAnalyze(request: Request, file: UploadFile = UploadFile(...)):
    model = load_model('src/urban_sound_model.h5')
    metadata = pd.read_csv('src/UrbanSound8K.csv')
    le = LabelEncoder()
    le.fit(metadata['class'])

    try:
        form_data = await request.form()
        timestamp = form_data['timestamp']
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        print(timestamp) 
        
        print(type(file))
        file_name = f'{file.filename}'
        print(file_name)
        with open(f'{file_name}', "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        test_feature = extract_feature(file_name)
        print(test_feature)
        
        y, sr = librosa.load(file_name)
        S = np.abs(librosa.stft(y))
        dB = librosa.amplitude_to_db(S, ref=1e-05)
        dBm = str(int(np.mean(dB)))
        print(dBm, 'dB')
        
        # 업로드 완료 후 임시 파일 삭제
        os.remove(f'{file_name}')

        if test_feature is not None:
            predicted_proba_vector = model.predict(test_feature)
            predicted_class_index = np.argmax(predicted_proba_vector)
            predicted_class_label = le.inverse_transform([predicted_class_index])[0]
            
            print(f"The predicted class for {file.filename} is: {predicted_class_label}")
        else:
            print("Failed to extract features from the file.")
        
        decibel = dBm
        await cycle_makeTsv(predicted_class_label, timestamp, decibel)
        
        return {"STATUS": 200, "RESULT": {"analyze_result": predicted_class_label, "time" : timestamp, "decibel" : decibel, "MESSAGE" : "All result is successfully analyze"}}
        
    except Exception as e:
        print(f"Error during model prediction: {e}")
        return {"STATUS": 400, "RESULT": {"MESSAGE": "Error"}}

@app.post('/cycle/make-tsv')
async def cycle_makeTsv(predicted_class_label: str, timestamp: str, decibel: int):
    try:
        output = StringIO()
        tw = csv.writer(output, delimiter='\t')
        tw.writerow(['label', 'time', 'decibel'])
        tw.writerow([predicted_class_label, timestamp, decibel])
        tsv_data = output.getvalue()
        output.close()
        
        file_uuid = timestamp
        user_uuid = 'user'
        
        await cycle_dataInsert(file_uuid=file_uuid, user_uuid=user_uuid, tsv_data=tsv_data)
        
        return {"STATUS": 200, "RESULT": {"MESSAGE" : "Successfully Save"}}
    except Exception as e:
        return {"STATUS": 400, "RESULT": {"MESSAGE": "Error"}}

@app.post('/cycle/data-insert')
async def cycle_dataInsert(file_uuid: str, user_uuid: str, tsv_data: str):
    tsv_data = tsv_data.encode('utf-8')
    
    insert = CycleData(file_uuid=file_uuid, user_uuid=user_uuid, tsv=tsv_data)
    session.add(insert)
    session.commit()
    result = session.query(CycleData).all()
    
    #await cycle_drawGraph(file_uuid=file_uuid)
    return {"STATUS": 200, "RESULT": {"data" : result}}


@app.get('/cycle/draw-graph')
async def cycle_drawGraph():
    try:
        file_uuid = session.query(CycleData).order_by(desc(CycleData.file_uuid)).first()
        print(file_uuid.file_uuid)
        file_uuid = file_uuid.file_uuid
        tsv_data = session.query(CycleData.tsv).filter(CycleData.file_uuid == file_uuid).first()[0]
        tsv_str = tsv_data.decode('utf-8')
        
        # TSV 데이터 파싱
        labels = []
        decibels = []
        with StringIO(tsv_str) as tsv_file:
            tsv_reader = csv.reader(tsv_file, delimiter='\t')
            next(tsv_reader)  # Header skip
            for row in tsv_reader:
                label, _, decibel = row
                labels.append(label)
                decibels.append(int(decibel))
        
        # 그래프 그리기
        plt.figure()
        plt.scatter(decibels, labels)
        plt.xlabel('Decibel')
        plt.ylabel('Label')
        plt.title('My room')

        # 이미지를 Base64로 변환하여 반환
        img_buf = BytesIO()
        plt.savefig(img_buf, format='png')
        img_buf.seek(0)
        img_base64 = base64.b64encode(img_buf.getvalue()).decode('utf-8')
        
        plt.close()  # 그래프 종료
        
        return img_base64
    
    except Exception as e:
        print(f"Error during graph drawing: {e}")
        raise HTTPException(status_code=500, detail="Error during graph drawing")
    
from sqlalchemy import func
@app.post('/cycle/draw-day-graph')
async def cycle_draw_day_graph(request: Request):
    data = await request.json()
    startdate = data.get('startdate')
    enddate = data.get('enddate')
    try:
        #start_datetime = datetime.strptime(startdate, '%Y%m%d')
        #end_datetime = datetime.strptime(enddate, '%Y%m%d') + timedelta(days=1)  # enddate를 포함하도록 하루 추가
        labels = []
        decibels = []
        
        file_uuids = session.query(CycleData.file_uuid).filter(
            func.substr(CycleData.file_uuid, 1, 8).between(startdate, enddate)
        ).all()

        if not file_uuids:
            return {"status": 200, "message": "No data"}
        
        for file_uuid in file_uuids:
            tsv_data = session.query(CycleData.tsv).filter(CycleData.file_uuid == file_uuid[0]).first()

            if tsv_data:
                tsv_str = tsv_data[0].decode('utf-8')

                with StringIO(tsv_str) as tsv_file:
                    tsv_reader = csv.reader(tsv_file, delimiter='\t')
                    next(tsv_reader)  # Header skip
                    for row in tsv_reader:
                        label, _, decibel = row
                        labels.append(label)
                        decibels.append(int(decibel))
                        
        plt.figure()
        plt.scatter(decibels, labels)
        plt.xlabel('Decibel')
        plt.ylabel('Label')
        plt.title('My room')

        img_buf = BytesIO()
        plt.savefig(img_buf, format='png')
        img_buf.seek(0)
        img_base64 = base64.b64encode(img_buf.getvalue()).decode('utf-8')

        plt.close()  

        return {"status": 200, "message": "Graph drawn successfully", "image": img_base64}

    except Exception as e:
        print(f"Error during graph drawing: {e}")
        raise HTTPException(status_code=500, detail="Error during graph drawing")
    

@app.get('/cycle/delete')
async def cycle_delete(file_uuid=None):
    if file_uuid is None:
        return "file_uuid is None"
    else:
        result = session.query(CycleData).filter(CycleData.file_uuid==file_uuid).delete()
        session.commit()
        result = session.query(CycleData).all()
        return result

@app.get('/cycle/delete-all')
async def cycle_deleteAll():
    result = session.query(CycleData).delete()
    session.commit()
    result = session.query(CycleData).all()
    return result
    
    
    
