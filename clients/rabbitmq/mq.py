# aio-pika 异步 RabbitMQ 生产者 + 消费者

# 特性清单：
#
# 1. 生产者：持久化消息 + publisher confirm（防止消息丢在生产者→MQ 之间）
# 2. 队列：durable 持久队列，绑定死信交换机 DLX
# 3. 消费者：**手动 ACK**，处理成功才 ack；失败进死信队列（管理界面可人工重发）
# 4. 幂等校验：用 `document_id + version` 判断是否已处理
import asyncio
import aio_pika
from .connection import rmq_manager
from .consumer import consume_index,consume_rag,consume_kg

_consumer_tasks: list[asyncio.Task] = []

# 初始化链接
async def init_mq():
    await rmq_manager.connect()
    print("RabbitMQ 连接成功")
    # 消费者是死循环协程，必须以后台任务启动，否则会阻塞 startup
    _consumer_tasks.extend([
        asyncio.create_task(consume_index()),
        asyncio.create_task(consume_rag()),
        asyncio.create_task(consume_kg()),
    ])


async def close_mq():
    for task in _consumer_tasks:
        task.cancel()
    await asyncio.gather(*_consumer_tasks, return_exceptions=True)
    _consumer_tasks.clear()
    await rmq_manager.close()
    print("RabbitMQ 连接已关闭")
