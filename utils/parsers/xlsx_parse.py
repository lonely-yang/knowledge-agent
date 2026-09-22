import openpyxl
import io
import asyncio
from datetime import datetime
from crud.RustFS import settings

async def extract_xlsx_text_and_images(xlsx_bytes, name_part, s3):
    # 内存加载xlsx
    bio = io.BytesIO(xlsx_bytes)
    wb = openpyxl.load_workbook(bio, read_only=False,data_only=True)
    result = []
    # 文档标题：优先取workbook标题，没有就用文件名
    xlsx_title = wb.properties.title or name_part

    try:
        # 遍历所有sheet
        for sheet_idx, sheet_name in enumerate(wb.sheetnames):
            sheet = wb[sheet_name]
            sheet_num = sheet_idx + 1
            rows_text = []
            sheet_images = []

            # 提取sheet上所有浮动图片，记录图片锚点（行号）
            img_map = {}
            for img_idx, img in enumerate(sheet._images):
                # 图片锚点位置：从哪一行
                anchor = img.anchor
                row_no = anchor._from.row + 1  # 转excel行号（从1开始）
                # 图片二进制
                img_bytes = img.ref.read()
                img_ext = img.format.lower()
                # 命名：原文件名-sheet名-行号-图片序号-时间戳
                ts = int(datetime.now().timestamp())
                img_key = f"{name_part}-sheet{sheet_num}-row{row_no}-img{img_idx+1}-{ts}.{img_ext}"

                # 上传RustFS
                await asyncio.to_thread(
                    s3.put_object,
                    Bucket=settings.RUSTFS_BUCKET,
                    Key=img_key,
                    Body=img_bytes,
                    ContentType=f"image/{img_ext}"
                )
                # 预签名预览url
                preview_url = await asyncio.to_thread(
                    s3.generate_presigned_url,
                    ClientMethod="get_object",
                    Params={"Bucket": settings.RUSTFS_BUCKET, "Key": img_key},
                    ExpiresIn=settings.PRESIGNED_EXPIRE
                )
                img_info = {
                    "key": img_key,
                    "preview_url": preview_url,
                    "ext": img_ext,
                    "row": row_no
                }
                sheet_images.append(img_info)
                # 按行分组图片
                if row_no not in img_map:
                    img_map[row_no] = []
                img_map[row_no].append(f"\n[IMAGE{img_idx+1}] {preview_url}")

            # 遍历每一行单元格文本
            for row in sheet.iter_rows():
                row_no = row[0].row
                # 把单元格转字符串，过滤None
                cell_text_list = []
                for cell in row:
                    val = cell.value
                    if val is not None:
                        cell_text_list.append(str(val))
                row_text = " | ".join(cell_text_list)

                # 如果这一行有图片，追加图片链接到本行末尾（和PDF逻辑一致）
                if row_no in img_map:
                    row_text += "\n=====图片预览链接====="
                    row_text += "".join(img_map[row_no])

                rows_text.append({
                    "row": row_no,
                    "text": row_text
                })

            result.append({
                "sheet": sheet_num,
                "sheet_name": sheet_name,
                "rows": rows_text,
                "images": sheet_images
            })
    finally:
        wb.close()
        bio.close()
    images = []
    text = ''
    for res in result:
        images.append(res.get('images'))
        text = text + res.get('sheet_name', '') + str(res.get('rows', [])) + '\n'
    return {
        "title": xlsx_title,
        "text": text,
        "images":images
    }
