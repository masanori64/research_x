from research_x import local_app
from research_x.cli import main


class InterruptingServer:
    def __init__(self, _address, _handler_cls) -> None:
        self.closed = False

    def serve_forever(self) -> None:
        raise KeyboardInterrupt()

    def server_close(self) -> None:
        self.closed = True


def test_app_keyboard_interrupt_closes_server_and_returns_zero(monkeypatch, capsys) -> None:
    servers = []

    def fake_server(address, handler_cls):
        server = InterruptingServer(address, handler_cls)
        servers.append(server)
        return server

    monkeypatch.setattr(local_app, "ThreadingHTTPServer", fake_server)

    assert main(["app", "--host", "127.0.0.1", "--port", "0", "--no-open-browser"]) == 0
    assert servers[0].closed is True

    output = capsys.readouterr()
    assert "research_x app: shutting down" in output.out
    assert "Traceback" not in output.err
    assert "KeyboardInterrupt" not in output.err
