import asyncio
import os
import pty
import logging
from pathlib import Path
from itertools import chain

BOOMS_SERIAL_DIR = Path(
    os.environ.get('BOOMS_SERIAL_DIR', default='/dev/booms'))

PLAYBACK_PATH = Path(os.environ.get('BOOMS_PLAYBACK', default='playback'))
COMMAND_PACKET = b'\x90\xeb\xe3\x56\xa0\xa1\x00\x04\xc0\xa8\x02\x01'
COMPUTER_IP = '192.168.2.101'
COMMAND_PORT = 50501

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def write_with_lock(file, data, lock):
    async with lock:
        file.write(data)
        file.flush()


class FlightComputerReciever(asyncio.DatagramProtocol):
    def __init__(self, processors=None):
        if processors is None:
            processors = list()
        self.processors = processors
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

        for p in self.processors:
            p.setup()

    def connection_lost(self, exc):
        logger.info('Lost UDP connection')
        if exc is not None:
            logger.warning('UDP closed with exception.', exc_info=exc)

        for p in self.processors:
            p.close()

    def datagram_received(self, data, addr):
        logger.debug('Datagram received from %s', addr)

        for p in self.processors:
            p.receive(data)

    def error_received(self, exc):
        logger.warning('Flight Computer UDP error received', exc_info=exc)


class PacketProcessor:
    def setup(self):
        pass

    def receive(self, packet):
        pass

    def close(self):
        pass


class PacketLogger(PacketProcessor):
    IMAG_IDS = set([0xC0 + i for i in range(7)])
    SPEC_IDS = set([0xD0 + i for i in range(3)])

    def __init__(self, path_root=None, path_dict=None, fd_dict=None):
        if path_root is not None:
            Path(path_root).mkdir(exist_ok=True)
            if path_dict is not None:
                raise ValueError('Only one output file option may be selected')

            path_dict = dict()
            for spec_id in self.SPEC_IDS:
                path_dict[spec_id] = \
                    Path(path_root) / f'spec_{spec_id & 0x0F:}.dat'

            for imag_id in self.IMAG_IDS:
                path_dict[imag_id] = \
                    Path(path_root) / f'imag_{imag_id & 0x0F:}.dat'
        logger.debug('Paths: %s', path_dict)

        if path_dict is not None:
            if fd_dict is not None:
                raise ValueError('Only one output file option may be selected')
            fd_dict = dict()
            for device_id, path in path_dict.items():
                logger.debug('Creating %s', hex(device_id))
                # Get the fd
                fd_dict[device_id] = \
                    os.open(path, os.O_CREAT | os.O_WRONLY | os.O_NONBLOCK)

        if set(fd_dict.keys()) > self.SPEC_IDS.union(self.IMAG_IDS):
            raise ValueError('Invalid device id provided.')
        self.fds = fd_dict.copy()
        self.f_lock = asyncio.Lock()
        logger.debug('File Descriptors: %s', self.fds)
        self.open_files = {k: None for k in self.fds.keys()}

    def setup(self):
        self.open_files.update(
            {device_id: os.fdopen(fd, "wb")
             for device_id, fd in self.fds.items()})

    def close(self):
        # Cleanup Open Files
        for device_id, file in self.open_files.items():
            if file is not None:
                file.close()
            self.open_files[device_id] = None

    def receive(self, packet):
        # Write to files
        id_byte = packet[4]
        logger.debug('ID Byte: %s', hex(id_byte))

        if (file := self.open_files.get(id_byte, None)):
            asyncio.create_task(
                write_with_lock(file, packet[16:], self.f_lock))
        else:
            pass
            # logger.warning('File for %s is closed', hex(id_byte))


class PacketPsuedoSerial(PacketLogger):
    def __init__(self):
        self.serial = dict()

        fd_dict = dict()
        for device_id in chain(self.IMAG_IDS, self.SPEC_IDS):
            primary_fd, secondary_df = pty.openpty()
            fd_dict[device_id] = primary_fd
            self.serial[device_id] = Path(os.ttyname(secondary_df))

        super().__init__(fd_dict=fd_dict)


async def receive_packets(ip_addr, port, processors=None, from_file=None):
    loop = asyncio.get_running_loop()
    on_con_lost = loop.create_future()

    def create_endpoint(processors=processors):
        return FlightComputerReciever(processors)

    transport, comp_ser = \
        await loop.create_datagram_endpoint(create_endpoint,
                                            local_addr=(ip_addr, port))

    try:
        if from_file is not None:
            await start_playback(from_file, speed=2 << 15, port=port)
            await asyncio.sleep(1.0)  # Wait for buffers to process.
        else:
            await on_con_lost
    except asyncio.exceptions.CancelledError:
        logger.debug('Cancelled', stack_info=True, exc_info=True)            
    finally:
        transport.close()


async def start_playback(file, **kwargs):
    if not PLAYBACK_PATH.exists():
        raise RuntimeError('Could not find playback executable. '
                           'Set env variable BOOMS_PLAYBACK.')
    command = [str(PLAYBACK_PATH.absolute()), str(file.absolute())]

    # Options
    option_flags = {'address': '-i',
                    'port': '-p',
                    'system_id': '-fs',
                    'tm_type': '-ft',
                    'speed': '-s'}

    for option, flag in option_flags.items():
        if option in kwargs:
            command.extend([flag, str(kwargs[option])])

    command = [x.replace(' ', r'\ ') for x in command]
    command = ' '.join(command)
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()
    logger.warning(stderr.decode())
    logger.debug(stdout.decode())
