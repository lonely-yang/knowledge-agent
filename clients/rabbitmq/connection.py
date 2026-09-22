import aio_pika
from aio_pika.abc import AbstractChannel, AbstractConnection
from core.config import settings

DLX_NAME = "aiagent.dlx"


def queue_arguments(queue_name: str) -> dict:
    """主队列参数：失败消息（reject 且不 requeue）路由到死信交换机"""
    return {
        "x-dead-letter-exchange": DLX_NAME,
        "x-dead-letter-routing-key": queue_name,
    }


class RabbitMQManager:
    def __init__(self):
        self.connection: AbstractConnection | None = None

        # 每个队列独立 channel
        self.channel_index: AbstractChannel | None = None
        self.channel_rag: AbstractChannel | None = None
        self.channel_kg: AbstractChannel | None = None

    async def connect(self):
        # 创建连接
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        # 创建channel
        self.channel_index = await self.connection.channel()
        self.channel_rag = await self.connection.channel()
        self.channel_kg = await self.connection.channel()

        # 死信交换机 + 各队列对应的死信队列（失败消息落这里，可人工重发）
        dlx = await self.channel_index.declare_exchange(
            DLX_NAME, aio_pika.ExchangeType.DIRECT, durable=True
        )
        for name in (settings.QUEUE_INDEX, settings.QUEUE_RAG, settings.QUEUE_KG):
            dlq = await self.channel_index.declare_queue(f"{name}.dlq", durable=True)
            await dlq.bind(dlx, routing_key=name)

        # 各自channel声明自己的工作队列（幂等，参数必须与消费端一致）
        await self.declare_work_queue(self.channel_index, settings.QUEUE_INDEX)
        await self.declare_work_queue(self.channel_rag, settings.QUEUE_RAG)
        await self.declare_work_queue(self.channel_kg, settings.QUEUE_KG)

    async def declare_work_queue(self, channel: AbstractChannel, queue_name: str):
        return await channel.declare_queue(
            queue_name, durable=True, arguments=queue_arguments(queue_name)
        )

    async def close(self):
        # 依次关闭channel，最后关闭连接
        if self.channel_index:
            await self.channel_index.close()
        if self.channel_rag:
            await self.channel_rag.close()
        if self.channel_kg:
            await self.channel_kg.close()
        if self.connection:
            await self.connection.close()

# 全局单例，整个项目共用
rmq_manager = RabbitMQManager()
