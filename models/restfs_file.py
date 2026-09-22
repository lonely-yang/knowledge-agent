from fastapi import APIRouter, Depends,UploadFile, File, HTTPException
from crud.RustFS import get_s3_client
from botocore.exceptions import ClientError
from fastapi.responses import StreamingResponse
from urllib.parse import quote
from crud.RustFS import settings
from datetime import datetime
from utils.parsers import pdf_parse, xlsx_parse, docx_parse, pptx_parse
from crud.postgre import get_db,create_kh_doc,pg_file_save
restFS_router = APIRouter(prefix="/restFS", tags=["RestFS 文件存储"])


# ========== 接口1：小文件直接上传（服务端中转） ==========
@restFS_router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    s3 = Depends(get_s3_client)
):
    try:
        file_bytes = await file.read()
        filename = file.filename
        # 拆分文件名和后缀
        if "." in filename:
            name_part, ext = filename.rsplit(".", 1)  # rsplit从右边分割，处理文件名包含.的情况 a.b.jpg
        else:
            name_part = filename
            ext = ""

        utc_ts = int(datetime.now().timestamp())
        # 拼接新key：原文件名-时间戳.后缀
        if ext:
            key = f"{name_part}-{utc_ts}.{ext}"
        else:
            key = f"{name_part}-{utc_ts}"

        await s3.put_object(
            Bucket=settings.RUSTFS_BUCKET,
            Key=key,
            Body=file_bytes,
            ContentType=file.content_type
        )

        # 校验文件类型
        # pdf 文件
        file_data = []
        """
           上传之后，拿到解析之后的文件，将基本信息存到mongodb和postgresql中
        """
        if ext.lower() == "pdf":
            # 调用pdf 解析文件工具
            file_data = await pdf_parse.extract_pdf_text_and_images(file_bytes,name_part,s3)
        elif ext.lower() == ("xlsx" or 'xls'):
            file_data = await xlsx_parse.extract_xlsx_text_and_images(file_bytes,name_part,s3)
        elif ext.lower() == ("docx" or 'doc'):
            file_data = await docx_parse.extract_docx_text_and_images(file_bytes, name_part, s3)
        elif ext.lower() == "pptx":
            file_data = await pptx_parse.extract_pptx_text_and_images(file_bytes, name_part, s3)


        await pg_file_save({"key": key,'data':file_data})





        return {"msg": "上传成功", "key": key, "size": len(file_bytes),'data':file_data}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"RustFS存储异常: {str(e)}")

# ========== 接口2：文件下载（流式返回） ==========
@restFS_router.get("/download/{filename}")
async def download_file(
    filename: str,
    s3 = Depends(get_s3_client)
):
    try:
        resp = await s3.get_object(Bucket=settings.RUSTFS_BUCKET, Key=filename)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise HTTPException(status_code=404, detail="文件不存在")
        raise HTTPException(status_code=500, detail=str(e))
    # Starlette 响应头只支持 latin-1，非 ASCII 文件名需 RFC 5987 编码
    try:
        filename.encode("latin-1")
        disposition = f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    # aiobotocore 的 Body 本身就是 async iterable，直接交给 StreamingResponse 按块输出，不整体读入内存
    return StreamingResponse(
        resp["Body"],
        media_type=resp.get("ContentType") or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )

# ========== 接口3：删除文件 ==========
@restFS_router.delete("/file/{filename}")
async def delete_file(
    filename: str,
    s3 = Depends(get_s3_client)
):
    try:
        await s3.delete_object(Bucket=settings.RUSTFS_BUCKET, Key=filename)
        return {"msg": "删除成功", "key": filename}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== 接口4：生成【前端直传预签名URL】（推荐大文件，不走服务端流量） ==========
@restFS_router.get("/presigned-upload/{filename}")
async def get_presigned_upload_url(
    filename: str,
    s3 = Depends(get_s3_client)
):
    try:
        url = await s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.RUSTFS_BUCKET,
                "Key": filename
            },
            ExpiresIn=settings.PRESIGNED_EXPIRE
        )
        return {"presigned_url": url, "expire": settings.PRESIGNED_EXPIRE}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== 接口5：生成预签名下载URL ==========
@restFS_router.get("/presigned-download/{filename}")
async def get_presigned_download_url(
    filename: str,
    s3 = Depends(get_s3_client)
):
    try:
        url = await s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": settings.RUSTFS_BUCKET,
                "Key": filename
            },
            ExpiresIn=settings.PRESIGNED_EXPIRE
        )
        return {"presigned_url": url, "expire": settings.PRESIGNED_EXPIRE}
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise HTTPException(status_code=404, detail="文件不存在")
        raise HTTPException(status_code=500, detail=str(e))

# ========== 接口6：大文件分片上传（后端分片，适合服务端中转大文件） ==========
# 分片上传流程：初始化分片 -> 依次上传分片 -> 合并分片
@restFS_router.post("/multipart/init/{filename}")
async def multipart_init(
    filename: str,
    s3 = Depends(get_s3_client)
):
    resp = await s3.create_multipart_upload(
        Bucket=settings.RUSTFS_BUCKET,
        Key=filename
    )
    upload_id = resp["UploadId"]
    return {"upload_id": upload_id, "key": filename}

@restFS_router.post("/multipart/upload/{filename}/{part_number}")
async def multipart_upload_part(
    filename: str,
    part_number: int,
    upload_id: str,
    file: UploadFile = File(...),
    s3 = Depends(get_s3_client)
):
    data = await file.read()
    resp = await s3.upload_part(
        Bucket=settings.RUSTFS_BUCKET,
        Key=filename,
        PartNumber=part_number,
        UploadId=upload_id,
        Body=data
    )
    return {"part_number": part_number, "etag": resp["ETag"]}

@restFS_router.post("/multipart/complete/{filename}")
async def multipart_complete(
    filename: str,
    upload_id: str,
    parts: list[dict],
    s3 = Depends(get_s3_client)
):
    await s3.complete_multipart_upload(
        Bucket=settings.RUSTFS_BUCKET,
        Key=filename,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts}
    )
    return {"msg": "分片合并完成", "key": filename}

