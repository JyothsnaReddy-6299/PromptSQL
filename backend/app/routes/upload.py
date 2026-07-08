from fastapi import APIRouter, UploadFile, File, HTTPException
import os

from app.services.upload_service import upload_dataset

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    try:

        filepath = os.path.join(
            UPLOAD_DIR,
            file.filename
        )

        with open(filepath, "wb") as buffer:
            buffer.write(await file.read())

        result = upload_dataset(
            filepath=filepath,
            filename=file.filename
        )

        return result

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )