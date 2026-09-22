import pymupdf
from core.config import settings
from datetime import datetime
async def extract_pdf_text_and_images(pdf_bytes,name_part,s3):
    # 在内存打开pdf，不用本地文件
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

    # ========== 提取文档元数据标题 ==========
    meta = doc.metadata
    pdf_title = meta.get("title", "").strip()
    # 如果元标题为空，降级使用文件名
    if not pdf_title:
        pdf_title = name_part
    result = []
    image_links = []  # 用来存放本页图片预览链接
    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        page_text = page.get_text()

        # 获取本页所有内嵌图片
        img_list = page.get_images(full=True)
        page_images = []

        for img_idx, img_info in enumerate(img_list):
            xref = img_info[0]
            img_data = doc.extract_image(xref)
            img_bytes = img_data["image"]
            img_ext = img_data["ext"]
            img_w = img_data["width"]
            img_h = img_data["height"]

            # ========== 图片命名：原pdf名-页码-图片序号-时间戳.后缀 ==========

            ts = int(datetime.now().timestamp())
            img_key = f"{name_part}-page{page_num}-img{img_idx + 1}-{ts}.{img_ext}"

            # 上传图片到RustFS（同步boto3包进线程池）
            await s3.put_object(
                Bucket=settings.RUSTFS_BUCKET,
                Key=img_key,
                Body=img_bytes,
                ContentType=f"image/{img_ext}"
            )
            # 生成图片预签名预览url
            img_preview_url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.RUSTFS_BUCKET, "Key": img_key},
                ExpiresIn=settings.PRESIGNED_EXPIRE
            )
            page_images.append({
                "key": img_key,
                "preview_url": img_preview_url,
                "ext": img_ext,
                "url":f'{settings.RUSTFS_ENDPOINT}/{settings.RUSTFS_BUCKET}/{img_key}'
            })
            image_links.append(f"\n[IMAGE{img_key}] {img_preview_url}")
        # ✅ 将图片链接追加到页面文本末尾
        if image_links:
            page_text += "\n=====图片预览链接====="
            page_text += "".join(image_links)
        result.append({
            "text": page_text,
            "images": page_images
        })
    doc.close()
    images = []
    text = ''
    for res in result:
        images.append(res.get('images'))
        text = text + res.get('text') + '/n'

    return {
        "title": pdf_title,
        "text": text,
        "images": images
    }


