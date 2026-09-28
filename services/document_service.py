from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models import KhDocument

# MQ 流程名 -> kh_document 子状态列名
FLOW_COLUMNS = {'index': 'idx_status', 'rag': 'rag_status', 'kg': 'kg_status'}


# 查询 doc
async def get_doc(session:AsyncSession,id:int):
    doc = await session.get(KhDocument,id)
    return doc

# 聚合 3 个 MQ 流程子状态为总解析状态
# 子状态: None未开始 / 0解析中 / 1成功 / 2失败; 返回 0未解析 / 1解析中 / 2解析完成 / 3解析失败
def compute_parse_status(idx, rag, kg) -> int:
    vals = [idx, rag, kg]
    if all(v is None for v in vals):
        return 0
    if 2 in vals:
        return 3
    if all(v == 1 for v in vals):
        return 2
    return 1


# 发布时把 3 个流程子状态置为「解析中」
async def mark_parsing(session: AsyncSession, doc_id: int):
    await session.execute(
        update(KhDocument).where(KhDocument.id == doc_id).values(
            idx_status=0, rag_status=0, kg_status=0
        )
    )
    await session.commit()


# 单个 MQ 消费者回写自己的流程结果(status: 1成功 / 2失败)
async def update_flow_status(session: AsyncSession, doc_id: int, flow: str, status: int):
    col = FLOW_COLUMNS[flow]
    await session.execute(
        update(KhDocument).where(KhDocument.id == doc_id).values({col: status})
    )
    await session.commit()


# 新增doc
async def create_kh_doc(session: AsyncSession,dto):
    # 判断类型
    if isinstance(dto, dict):
        dto_data = dict(dto)
        content = dto_data.pop('content', None)
    else:
        # content 在 DTO 中 exclude=True,model_dump 拿不到,需单独取
        dto_data = dto.model_dump()
        content = dto.content
    # 过滤非表字段(uploader/parse_status 等只读响应字段),避免 KhDocument() 报错
    valid_cols = {c.name for c in KhDocument.__table__.columns}
    dto_data = {k: v for k, v in dto_data.items() if k in valid_cols}
    doc = KhDocument(**dto_data)
    if content:
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
    return doc
