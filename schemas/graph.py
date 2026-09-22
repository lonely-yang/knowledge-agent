from typing import List

from pydantic import BaseModel, ConfigDict, Field


class Neo4jSchema(BaseModel):
    entities:List[dict] = Field(description='单个实体结构,描述实体节点的信息')
    relationships:List[dict] = Field(description='描述实体节点之间的单个关系结构')
    cypher:str = Field(description='Cypher语句,提供给neo4j生成可视化图谱')
    query_cypher:str = Field(description='Cypher语句,neo4j查询语句')


class GraphDocCreate(BaseModel):
    doc_id: int
    entities: list[dict]
    relationships: list[dict]
    query_cypher: str
    cypher: str


class GraphDocOut(GraphDocCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
