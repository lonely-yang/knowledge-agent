from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from models import KhDocument


# 查询 doc
async def get_doc(session:AsyncSession,id:int):
    doc = await session.get(KhDocument,id)
    return doc

# 新增doc
async def create_kh_doc(session: AsyncSession,dto):
    # 判断类型
    if isinstance(dto, dict):
        dto_data = dict(dto)
    else:
        dto_data = dto.model_dump()
    content = dto_data.pop('content', None)
    doc = KhDocument(**dto_data)
    doc.summary = content[:100]
    now = datetime.now()
    doc.create_at = now
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    if content:
        if doc.content_id is None:
            # 未显式指定 content_id 时，用 PG 自增主键作为 Mongo _id，保证关联唯一
            doc.content_id = doc.id
            await session.commit()
            await session.refresh(doc)
    return doc

# 删除doc
async def delete_kh_doc(session:AsyncSession,doc_id:int) -> bool:
    doc = await get_doc(session, id=doc_id)
    if not doc:
        return False
    await session.delete(doc)
    await session.commit()
    return True

# 修改doc
async def update_kh_doc(session:AsyncSession,dto,doc_id:int):
    doc = await get_doc(session, id=doc_id)
    if not doc:
        return None
    update_data = dto.model_dump(exclude_unset=True)  # exclude_unset=True：只更新前端传过来的字段，不传的保留原值
    update_data.pop("id", None)

    # 循环赋值给数据库ORM对象
    for key, value in update_data.items():
        setattr(doc, key, value)

    await session.commit()
    await session.refresh(doc)
    doc.content = dto.content
    return doc
