import asyncio
from ipaddress import ip_address
from pathlib import Path
import typing as t

import click
from bokeh.server.server import Server
from bokeh.application import Application
from bokeh.application.handlers import ScriptHandler

from .. import network

SERIAL_LOG_PATH = Path(__file__).parent/'computer_serial.log'


class IPAddress(click.ParamType):
    name = 'IP address'
    """Restricts the type to a string for a valid IPv4 or IPv6 address."""
    def convert(self, value, param, ctx):
        try:
            ip = ip_address(value)
        except ValueError:
            self.fail('Invalid IP Address', param, ctx)

        return str(ip)


class PacketID(click.IntRange):
    name = 'packet ID'

    def __init__(self):
        super().__init__(0, 255)
    
    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        
        try:
            if value[:2].lower() == "0x":
                return int(value[2:], 16)
            elif value[:1] == "0":
                return int(value, 8)
            return int(value, 10)
        except ValueError:
            self.fail(f"{value!r} is not a valid integer", param, ctx)

PACKET_ID = PacketID()


@click.group(chain=True)
@click.option('-a', '--address', default='0.0.0.0', type=IPAddress())
@click.option('-p', '--port', default='20501', type=click.IntRange(0, 65535))
@click.option('-f', '--from_file',
              type=click.Path(file_okay=True,
                              dir_okay=False,
                              path_type=Path))
@click.option('-s', '--speed', default='1.0',
              help='Playback speed.', type=click.FloatRange(min_open=0))
@click.option('--debug', is_flag=True)
def gse(**kwargs):
    """Receive UDP datagrams and add to parsers"""
    # Setup logging


@gse.result_callback()
def process_pipeline(processors, address, port, from_file, speed, debug):
    """Sets up the async run."""
    asyncio.run(network.receive_packets(address, port, processors,
                                        from_file, speed))


@gse.command()
@click.argument('target_address', default='127.0.0.1', type=IPAddress())
@click.argument('target_port', default='20502', type=click.IntRange(0, 65535))
# @click.option('--packet_id', help='Forward only this packet type.')
def forward(target_address, target_port):
    """Forward the UDP packets"""
    return network.PacketForwarder(target_address, target_port)


@gse.command()
@click.argument('packet_id', type=PACKET_ID)
@click.argument('target_serial', type=str)
def serial(packet_id, target_serial):
    """Pass the data from a selected device to a serial port"""
    return network.PacketSerial(packet_id, target_serial)


@gse.command()
def psuedoserial(address, port, from_file):
    """Pass networked BOOMS packets to pseudo-serial ports."""
    # log_file_handler = logging.FileHandler(SERIAL_LOG_PATH)
    # log_file_formatter = logging.Formatter(
    #     fmt='%(asctime)s - %(levelname)s - %(message)s')
    # log_file_handler.setFormatter(log_file_formatter)
    # network.logger.addHandler(log_file_handler)
    # network.logger.addHandler(logging.StreamHandler())
    # if kwargs['debug']:
    #     logging.basicConfig(level=logging.DEBUG)
    #     network.logger.setLevel(logging.DEBUG)

    return network.PacketPsuedoSerial()


@gse.command()
@click.argument('path',
                type=click.Path(file_okay=False,
                                writable=True,
                                path_type=Path))
def record(path):
    """Write networked BOOMS packets to files for each instrument."""
    # network.logger.addHandler(logging.StreamHandler())
    # if kwargs['debug']:
    #     network.logger.setLevel(logging.DEBUG)
    return network.PacketLogger(path)


class MMGSEPacket(network.PacketForwarder):
    def __init__(self):
        super().__init__('127.0.0.1', 20502)
        self.server = None

    def setup(self, transport):
        super().setup(transport)

        mm_gse_path = Path(__file__).parent.parent / 'mm_gse.py'
        print(mm_gse_path)
        apps = {'/': Application(ScriptHandler(filename=mm_gse_path))}
        self.server = Server(apps)
        self.server.start()
        url = f"http://localhost:{self.server.port}{self.server.prefix}/"
        print(f"Bokeh app running at: {url}")
        # self.server.io_loop.start()

    def stop(self):
        super().stop()
        self.server.stop()


@gse.command()
def mm_gse():
    return MMGSEPacket()


if __name__ == '__main__':
    gse()
