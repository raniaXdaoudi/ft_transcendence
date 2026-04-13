from struct import unpack
from subprocess import Popen
from dataclasses import dataclass
from typing import Callable, Optional
from asyncio import Future, get_event_loop
from os import close, pipe2, read, O_NONBLOCK

FinishHandler = Callable[['GameServer', int, int, int], None]

QuitHandler = Callable[['GameServer'], None]

@dataclass
class GameServerSettings:
    port: int
    jwt_secret: str
    player_a_id: int
    player_b_id: int
    ssl_cert: Optional[str]
    ssl_key: Optional[str]

class GameServerProcess:
    def __init__(self, settings: GameServerSettings, on_readable: Callable[[], None]) -> None:
        if settings.ssl_cert != None and settings.ssl_key != None:
            ssl_arguments = ['-c', settings.ssl_cert, '-k', settings.ssl_key]
        else:
            ssl_arguments = []
        read_end, write_end = pipe2(O_NONBLOCK)
        try:
            self.fileno = read_end
            read_end = -1
            self.process = Popen(
                ['python3', '-m', 'server',
                 '-p', str(settings.port),
                 '-j', settings.jwt_secret,
                 '-I', str(settings.player_a_id), str(settings.player_b_id),
                 '-n', str(write_end)] + ssl_arguments,
                pass_fds=(write_end, )
            )
        finally:
            try:
                close(write_end)
            finally:
                if read_end != -1:
                    close(read_end)
        self.loop = get_event_loop()
        self.loop.add_reader(self.fileno, on_readable)

    def __del__(self) -> None:
        process = getattr(self, 'process', None)
        loop = getattr(self, 'loop', None)
        fileno = getattr(self, 'fileno')
        try:
            if process != None:
                process.kill()
                process.wait()
        finally:
            if fileno == None:
                return
            try:
                if loop != None:
                    loop.remove_reader(self.fileno)
            finally:
                close(fileno)

class GameServer:
    def __init__(self, game_id: int, settings: GameServerSettings, on_finished: FinishHandler, on_quit: QuitHandler) -> None:
        self.game_id = game_id
        self.settings = settings
        self.on_finished = on_finished
        self.on_quit = on_quit
        self.process = GameServerProcess(settings, self.on_process_readable)
        self.ready_future = Future()
        self.message_length = None
        self.message_buffer = bytearray()
        self.finish_reported = False

    def on_game_ready(self) -> None:
        if not self.ready_future.done():
            self.ready_future.set_result(None)

    def on_game_finished(self, winner: int, score_a: int, score_b: int) -> None:
        if not self.finish_reported:
            self.finish_reported = True
            self.on_finished(self, winner, score_a, score_b)

    def on_process_quit(self) -> None:
        if not self.ready_future.done():
            self.ready_future.set_exception(Exception('Server has quit unexpectedly'))
        else:
            if not self.finish_reported:
                self.finish_reported = True
                self.on_finished(self, -1, 0, 0)
            self.on_quit(self)

    def on_process_message(self, message: str) -> None:
        message = message.split(':')
        arguments = message[1:]
        match message[0]:
            case 'ready':
                if len(arguments) != 0:
                    raise TypeError(f'`ready` message takes 0 parameters, {len(arguments)} given')
                self.on_game_ready()
            case 'finished':
                if len(arguments) != 3:
                    raise TypeError(f'`finished` message takes 3 parameters, {len(arguments)} given')
                try:
                    arguments = map(int, arguments)
                except ValueError:
                    raise TypeError(f'`finished` message is malformed (int, int, int)')
                self.on_game_finished(*arguments)

    def on_process_readable(self) -> None:
        try:
            while self.process != None:
                data = read(self.process.fileno, 4096)
                if len(data) == 0:
                    raise EOFError()
                self.on_process_data(data)
        except BlockingIOError:
            pass
        except Exception:
            self.process = None
            self.on_process_quit()

    def on_process_data(self, data: bytes) -> None:
        offset = 0
        while offset < len(data):
            bytes_left = len(data) - offset
            bytes_required = 2 if (self.message_length == None) else self.message_length
            bytes_to_consume = min(bytes_required - len(self.message_buffer), bytes_left)
            self.message_buffer.extend(data[offset : offset + bytes_to_consume])
            offset += bytes_to_consume
            if bytes_to_consume == bytes_required:
                if self.message_length == None:
                    self.message_length, = unpack('<H', self.message_buffer)
                    self.message_buffer.clear()
                else:
                    try:
                        self.on_process_message(self.message_buffer.decode('utf-8'))
                    finally:
                        self.message_length = None
                        self.message_buffer.clear()
