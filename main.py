from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from auth import router

app = FastAPI(title="1151 SE 學期專案")
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    details = [
        {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


@app.get("/")
def home():
    return {"message": "FastAPI 啟動成功"}
