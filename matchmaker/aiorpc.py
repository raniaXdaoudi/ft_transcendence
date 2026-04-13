from pika.channel import Channel
from pika import ConnectionParameters
from pika.spec import Basic, BasicProperties
from pika.adapters.asyncio_connection import AsyncioConnection

from tinyrpc import RPCRequest
from tinyrpc.dispatch import RPCDispatcher
from tinyrpc.exc import ServerError, RPCError
from tinyrpc.protocols.jsonrpc import JSONRPCProtocol

from types import CoroutineType
from typing import Any, Optional
from asyncio import Future, get_event_loop

class AioRPC:
    RECONNECT_DELAY = 5.0

    def __init__(self, host: str, queue: str, instance: object) -> None:
        self._host = host
        self._queue = queue
        self._protocol = JSONRPCProtocol()
        self._dispatcher = RPCDispatcher()
        self._dispatcher.register_instance(instance)
        self._connection = None
        self._channel = None

    async def __aenter__(self) -> None:
        self._connect()

    async def __aexit__(self, *_) -> None:
        if self._connection != None:
            self._connection.close()
            self._connection = None
            self._channel = None

    def _connect(self) -> None:
        self._connection = AsyncioConnection(
            ConnectionParameters(self._host),
            on_open_callback=self._on_connection_open,
            on_open_error_callback=self._on_connection_open_error,
            on_close_callback=self._on_connection_close
        )
        self._channel = None

    def _reconnect(self) -> None:
        if self._connection != None:
            try:
                self._connection.close()
            except:
                pass
        self._connection = None
        self._channel = None
        get_event_loop().call_later(AioRPC.RECONNECT_DELAY, self._connect)

    def _on_message(self, channel: Channel, method: Basic.Deliver, properties: BasicProperties, body: bytes) -> None:
        if channel.connection == self._connection and channel == self._channel:
            request = None
            delivery_tag = method.delivery_tag
            try:
                request = self._protocol.parse_request(body)
                method = self._dispatcher.get_method(request.method)
                RPCDispatcher.validate_parameters(method, request.args, request.kwargs)
            except Exception as exception:
                self._send_error(delivery_tag, properties, request, exception, False)
                return
            try:
                result = method(*request.args, **request.kwargs)
            except Exception as exception:
                self._send_error(delivery_tag, properties, request, exception, True)
                return
            if isinstance(result, (Future, CoroutineType)):
                async def wait_for_result() -> None:
                    try:
                        self._send_result(delivery_tag, properties, request, await result)
                    except Exception as exception:
                        self._send_error(delivery_tag, properties, request, exception, True)
                get_event_loop().create_task(wait_for_result())
            else:
                self._send_result(delivery_tag, properties, request, result)

    def _send_result(self, delivery_tag: int, properties: BasicProperties, request: RPCRequest, result: Any) -> None:
        try:
            body = request.respond(result)
            if body != None:
                body = body.serialize()
            self._send_reply(delivery_tag, properties, body)
        except Exception as error:
            self._send_error(delivery_tag, properties, request, error, False)

    def _send_error(
        self,
        delivery_tag: int,
        properties: BasicProperties,
        request: Optional[RPCRequest],
        error: BaseException,
        allow_non_rpc: bool
    ) -> None:
        try:
            response = None
            if isinstance(error, RPCError):
                if request == None:
                    response = error.error_respond()
                else:
                    response = request.error_respond(error)
            elif request != None:
                if allow_non_rpc:
                    response = request.error_respond(error)
                else:
                    response = request.error_respond(ServerError())
            if response != None:
                response = response.serialize()
            self._send_reply(delivery_tag, properties, response)
        except Exception:
            pass

    def _send_reply(self, delivery_tag: int, properties: BasicProperties, body: Optional[bytes]) -> None:
        try:
            if body != None:
                self._channel.basic_publish(
                    exchange='',
                    routing_key=properties.reply_to,
                    properties=BasicProperties(
                        correlation_id=properties.correlation_id
                    ),
                    body=body
                )
            self._channel.basic_ack(delivery_tag)
        except Exception:
            pass

    def _on_channel_open(self, channel: Channel) -> None:
        if channel.connection == self._connection:
            self._channel = channel
            try:
                channel.queue_declare(self._queue)
                channel.basic_consume(self._queue, self._on_message)
            except Exception:
                self._reconnect()

    def _on_connection_open(self, connection: AsyncioConnection) -> None:
        if connection == self._connection:
            try:
                connection.channel(on_open_callback=self._on_channel_open)
            except Exception:
                self._reconnect()

    def _on_connection_close(self, connection: AsyncioConnection, exception: BaseException) -> None:
        if connection == self._connection:
            self._reconnect()

    def _on_connection_open_error(self, connection: AsyncioConnection, exception: BaseException) -> None:
        if connection == self._connection:
            self._reconnect()
