from jwt import decode as jwt_decode
from typing import Optional, Tuple, TYPE_CHECKING
from websockets import WebSocketServerProtocol, HeadersLike, Headers

if TYPE_CHECKING:
    from .server import Server

class Client(WebSocketServerProtocol):
    TEXT_RESPONSE_HEADERS = {'Content-Type': 'text/plain'}

    def __init__(self, server: 'Server', *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.server = server
        self.user_ids = set()

    async def process_request(self, query: str, headers: Headers) -> Optional[Tuple[int, HeadersLike, bytes]]:
        path, _, parameters = query.partition('?')
        match path:
            case '/game':
                if len(parameters) > 0:
                    for parameter in parameters.split('&'):
                        key, _, value = parameter.partition('=')
                        if key != 'with_token' or not self.process_token(value):
                            return 400, Client.TEXT_RESPONSE_HEADERS, b'Bad Request'
                if not self.process_user_ids():
                    return 401, Client.TEXT_RESPONSE_HEADERS, b'Unauthorized'
                if self.is_already_connected():
                    return 409, Client.TEXT_RESPONSE_HEADERS, b'Conflict'
                return None
            case '/health':
                return 200, Client.TEXT_RESPONSE_HEADERS, b'OK'
        return 404, Client.TEXT_RESPONSE_HEADERS, b'Not Found'

    def process_token(self, token: str) -> bool:
        if len(self.user_ids) >= 2:
            return False
        if token == 'guest':
            user_id = -1
        else:
            try:
                payload = jwt_decode(token, self.server.jwt_secret, algorithms=['HS256'])
                user_id = payload['user_id']
            except:
                return False
        if user_id in self.user_ids:
            return False
        self.user_ids.add(user_id)
        return True

    def process_user_ids(self) -> bool:
        if len(self.user_ids) < 1:
            return False
        if -1 in self.user_ids:
            for user_id in self.user_ids:
                if user_id != -1:
                    break
            else:
                return False
            if not user_id in self.server.player_ids:
                return False
        return True

    def is_already_connected(self) -> bool:
        for client in self.server.clients:
            if not client.user_ids.isdisjoint(self.user_ids):
                return True
        return False
