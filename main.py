from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from auth import router
from schedules import router as schedules_router

app = FastAPI(title="1151 SE 學期專案")
app.include_router(router)
app.include_router(schedules_router)


@app.get("/calendar", response_class=FileResponse, include_in_schema=False)
def calendar():
    return FileResponse(Path(__file__).with_name("calendar.html"), media_type="text/html")


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
