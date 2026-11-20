from fastapi import FastAPI

app = FastAPI(title="1151 SE 學期專案")


@app.get("/")
def home():
    return {"message": "FastAPI 啟動成功"}
