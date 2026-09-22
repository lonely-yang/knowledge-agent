from sqlalchemy import Column, Integer, JSON, String

from core.database import Base


# -------------------------- SQLAlchemy ORM模型 --------------------------
class GraphDocModel(Base):
    __tablename__ = "graph_doc"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    doc_id = Column(Integer, unique=True, index=True, nullable=False)
    entities = Column(JSON, nullable=False)
    query_cypher = Column(String, nullable=False)
    relationships = Column(JSON, nullable=False)
    cypher = Column(String, nullable=False)
